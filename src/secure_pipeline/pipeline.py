"""
pipeline.py -- Multi-tenant RAG server, black-box client, and the Observation boundary.

Server (RAGPipeline.handle) returns two things:
- ApiResponse : what the HTTP API would send back
- Truth       : ground truth for the experimenter (retrieved docs, cache provenance,
                staleness, timings). The attacker never sees it.

Client (Client.ask) is the only way experiments talk to the server. It measures
latency with the shared Clock around the whole call and strips the ApiResponse down
to the fields the chosen exposure profile shows:

    text_only     : response text + latency
    with_sources  : + source titles/scores and a retrieval confidence (common RAG UIs)
    with_reranker : + reranker confidence

Query flow (each step gated by Mitigations, see mitigations.py):
    1. embed query
    2. semantic cache lookup (scope, lazy taint check)
    3. vector retrieval (ACL pre-filter on materialized index ACLs, or flat + post-filter)
    4. live IAM re-check (optional), rerank
    5. memory read (lazy taint check), LLM generation (or fast refusal)
    6. taint the response, write cache + memory
    7. quantize scores, pad latency to the configured shape
"""

from __future__ import annotations

import itertools
import random
from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np

from .access_control import AccessControlManager
from .clock import Clock
from .corpus import Corpus
from .index_store import SyncPolicy, VectorIndex
from .instrumentation import RunLogger
from .llm_client import LLMClient, MemoryItem
from .mitigations import Mitigations
from .normalization import pad_seconds, quantize, refusal_text
from .provenance import EMPTY, response_taint
from .semantic_cache import CacheEntry, SemanticCache
from .session_memory import SessionMemory

EXPOSURE_PROFILES = ("text_only", "with_sources", "with_reranker")


@dataclass(frozen=True)
class Observation:
    """Everything a black-box client can see. The attacker only ever gets this."""
    text: str
    latency_ms: float
    sources: Optional[tuple[tuple[str, float], ...]] = None
    confidence: Optional[float] = None
    rerank_confidence: Optional[float] = None


@dataclass
class ApiResponse:
    text: str
    sources: list[tuple[str, float]]
    confidence: float
    rerank_confidence: float


@dataclass
class Truth:
    query_id: int
    t: float
    user: str
    tenant: Optional[str]
    session: str
    query: str
    t_since_revocation_s: Optional[float] = None   # since this user's last revocation
    queries_since_revocation: Optional[int] = None # this user's queries since then (1 = first)
    cache_hit: bool = False
    cache_sim: float = 0.0
    cache_creator: str = ""
    cache_age_s: float = 0.0
    candidate_docs: list[str] = field(default_factory=list)
    candidate_scores: list[float] = field(default_factory=list)
    gen_docs: list[str] = field(default_factory=list)             # docs passed to the LLM now
    source_docs: list[str] = field(default_factory=list)          # docs the returned text came from
    stale_docs_used: list[str] = field(default_factory=list)      # index allowed, IAM denies
    live_denied_docs: list[str] = field(default_factory=list)     # caught by live_acl_check
    memory_turns: int = 0
    response_taint: list[str] = field(default_factory=list)
    llm_called: bool = False
    llm_cached: bool = False
    llm_latency_ms: float = 0.0
    model: str = ""
    refused: bool = False
    refusal_reason: str = ""
    raw_confidence: float = 0.0
    raw_rerank_confidence: float = 0.0
    server_latency_ms: float = 0.0
    pad_ms: float = 0.0
    observed_latency_ms: float = 0.0
    response: str = ""


@dataclass(frozen=True)
class PipelineConfig:
    top_k: int = 5                  # chunks retrieved
    gen_k: int = 3                  # chunks passed to the LLM
    min_relevance: float = 0.25     # cosine floor; below it a chunk is "not found"
    cache_ttl_s: float = 3600.0
    cache_threshold: float = 0.90
    summary_after: int = 8          # turns before rolling summary (0 = never)
    keep_recent: int = 4
    sync: str = "live"              # SyncPolicy spec, e.g. "periodic:3600", "event:0.05"


class RAGPipeline:
    def __init__(self, corpus: Corpus, chunk_embeddings: np.ndarray, embedder, reranker, llm: LLMClient,
                 clock: Clock, mitigations: Mitigations, config: PipelineConfig, seed: int) -> None:
        self.corpus = corpus
        self.embedder = embedder
        self.reranker = reranker
        self.llm = llm
        self.clock = clock
        self.m = mitigations
        self.cfg = config
        self.rng = random.Random(seed)
        self._qid = itertools.count(1)
        self._chunk_embeddings = chunk_embeddings
        self.index: Optional[VectorIndex] = None
        self.reset()

    # ---- State --------------------------------------------------------------

    def reset(self) -> None:
        """Fresh IAM, cache and memory; index ACLs resynced to the fresh IAM.

        The vector index itself (Chroma collection) is reused across trials because
        re-ingesting it is the expensive part.
        """
        self.acm = AccessControlManager.from_iam(self.corpus.iam, self.corpus.docs, self.clock)
        policy = SyncPolicy.parse(self.cfg.sync)
        if self.index is None:
            self.index = VectorIndex(self.corpus.chunks, self._chunk_embeddings, self.acm, policy,
                                     self.clock, self.rng)
        else:
            self.index.rebind(self.acm)
        self.cache = SemanticCache(self.clock, self.acm, self.cfg.cache_ttl_s, self.cfg.cache_threshold,
                                   self.m.cache_scope, self.m.cache_evict, self.m.cache_lazy_check)
        self.memory = SessionMemory(self.acm, self.cfg.summary_after, self.cfg.keep_recent,
                                    self.m.taint_transitive, self.m.memory_purge, self.m.memory_lazy_check)
        self._since_rev: dict[str, tuple[float, int]] = {}   # user -> (revocation time, queries since)

    def close(self) -> None:
        if self.index is not None:
            self.index.close()

    # ---- Request handling ---------------------------------------------------

    def handle(self, user: str, session: str, query: str) -> tuple[ApiResponse, Truth]:
        t0 = self.clock.now()
        m = self.m
        tenant = self.acm.tenant_of(user)
        truth = Truth(query_id=next(self._qid), t=t0, user=user, tenant=tenant, session=session, query=query,
                      model=self.llm.model_id)
        last_rev = self.acm.last_revocation_time(user)
        if last_rev is not None:
            prev = self._since_rev.get(user)
            n = prev[1] + 1 if prev and prev[0] == last_rev else 1
            self._since_rev[user] = (last_rev, n)
            truth.t_since_revocation_s, truth.queries_since_revocation = t0 - last_rev, n
        q_emb = self.embedder.encode([query])[0]

        hit = self.cache.get(q_emb, user, tenant)
        if hit is not None:
            entry, sim = hit
            truth.cache_hit, truth.cache_sim = True, sim
            truth.cache_creator, truth.cache_age_s = entry.created_by, t0 - entry.created_at
            truth.source_docs = list(entry.source_docs)
            text, taint = entry.response, entry.taint
            sources, conf, rr = list(entry.sources), entry.confidence, entry.rerank_confidence
        else:
            text, taint, sources, conf, rr = self._generate(user, tenant, session, query, q_emb, truth)

        self.memory.append(session, user, "user", query, EMPTY)
        self.memory.append(session, user, "assistant", text, taint)

        truth.response_taint = sorted(taint)
        truth.raw_confidence, truth.raw_rerank_confidence = conf, rr
        truth.response = text
        if m.score_quantize:
            sources = [(title, quantize(s)) for title, s in sources]
            conf, rr = quantize(conf), quantize(rr)

        elapsed = self.clock.now() - t0
        truth.server_latency_ms = elapsed * 1000.0
        if m.latency_pad:
            extra = pad_seconds(elapsed, m.pad_strategy, m.pad_ms, self.rng)
            self.clock.sleep(extra)
            truth.pad_ms = extra * 1000.0
        return ApiResponse(text=text, sources=sources, confidence=conf, rerank_confidence=rr), truth

    def _generate(self, user, tenant, session, query, q_emb, truth: Truth):
        m, cfg = self.m, self.cfg
        cands = self.index.query(q_emb, cfg.top_k, user, tenant, prefilter=m.acl_prefilter)
        relevant = [c for c in cands if c.score >= cfg.min_relevance]
        truth.candidate_docs = [c.doc_id for c in relevant]
        truth.candidate_scores = [round(c.score, 4) for c in relevant]

        authorized = [c for c in relevant if c.index_allows]
        if m.live_acl_check:
            truth.live_denied_docs = sorted({c.doc_id for c in authorized if not self.acm.has_access(user, c.doc_id)})
            authorized = [c for c in authorized if self.acm.has_access(user, c.doc_id)]

        # The ranking stage sees post-filter candidates only when filtering happens inside retrieval.
        ranked_set = authorized if m.acl_prefilter else relevant
        conf = max((c.score for c in ranked_set), default=0.0)
        rr_scores = self.reranker.score(query, [c.text for c in ranked_set])
        rr = max(rr_scores, default=0.0)
        rr_by_chunk = dict(zip((c.chunk_id for c in ranked_set), rr_scores))
        gen = sorted(authorized, key=lambda c: -rr_by_chunk.get(c.chunk_id, 0.0))[:cfg.gen_k]
        truth.gen_docs = list(dict.fromkeys(c.doc_id for c in gen))
        truth.source_docs = list(truth.gen_docs)
        truth.stale_docs_used = sorted({c.doc_id for c in gen if not self.acm.has_access(user, c.doc_id)})

        reason = "" if gen else ("access_denied" if relevant else "not_found")
        refusal = refusal_text(reason or "not_found", m.uniform_refusal)
        turns = self.memory.context(session, user)
        truth.memory_turns = len(turns)

        if not gen and m.fast_refusal:
            text, taint = refusal, EMPTY
        else:
            g = self.llm.answer(
                query,
                [(c.title, c.text) for c in gen],
                [MemoryItem(t.role, t.content) for t in turns],
                refusal,
            )
            truth.llm_called, truth.llm_cached, truth.llm_latency_ms = True, g.cached, g.latency_s * 1000.0
            text = g.text
            taint = response_taint((c.doc_id for c in gen), (t.taint for t in turns), m.taint_transitive)

        refused = text.strip() == refusal.strip()
        truth.refused = refused
        truth.refusal_reason = reason if refused else ""
        sources = [(c.title, c.score) for c in gen] if not refused else []
        if gen and not refused:
            self.cache.put(CacheEntry(
                embedding=q_emb, query=query, response=text, sources=sources, confidence=conf,
                rerank_confidence=rr, taint=taint, source_docs=tuple(truth.gen_docs), tenant_id=tenant, created_by=user,
                created_at=self.clock.now(),
            ))
        return text, taint, sources, conf, rr


class Client:
    """Black-box API client. Measures latency itself and applies the exposure profile."""

    def __init__(self, pipeline: RAGPipeline, exposure: str, logger: Optional[RunLogger] = None) -> None:
        if exposure not in EXPOSURE_PROFILES:
            raise ValueError(f"exposure must be one of {EXPOSURE_PROFILES}")
        self.pipeline = pipeline
        self.exposure = exposure
        self.logger = logger

    def ask(self, user: str, session: str, query: str, **tags) -> Observation:
        clock = self.pipeline.clock
        t0 = clock.now()
        resp, truth = self.pipeline.handle(user, session, query)
        latency_ms = (clock.now() - t0) * 1000.0
        truth.observed_latency_ms = latency_ms
        obs = Observation(text=resp.text, latency_ms=latency_ms)
        if self.exposure in ("with_sources", "with_reranker"):
            obs = Observation(text=resp.text, latency_ms=latency_ms,
                              sources=tuple((t, round(s, 4)) for t, s in resp.sources),
                              confidence=round(resp.confidence, 4))
        if self.exposure == "with_reranker":
            obs = Observation(text=obs.text, latency_ms=latency_ms, sources=obs.sources,
                              confidence=obs.confidence, rerank_confidence=round(resp.rerank_confidence, 4))
        if self.logger is not None:
            self.logger.log(tags=tags, truth=asdict(truth), obs=asdict(obs))
        return obs
