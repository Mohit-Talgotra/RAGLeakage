"""
rag_pipeline.py — The naive multi-tenant RAG pipeline.

Vulnerability map
-----------------
Three deliberate design flaws are embedded here, each clearly labelled:

  NAIVE FLAW #1 — Cache before RBAC
      The semantic cache is checked before access rights are verified.
      Any user — including a post-revocation user or a cross-tenant attacker —
      receives a cached response from an earlier authorised session without
      any access check.

  NAIVE FLAW #2 — Flat index, RBAC after retrieval
      The vector index is queried across all tenants and all documents.
      RBAC filtering happens *after* retrieval, so similarity scores for
      restricted documents are computed and logged for every query regardless
      of who is asking.  This produces the side-channel: even when access is
      denied, the score distribution differs from "document doesn't exist".

  NAIVE FLAW #3 — Session memory never purged on revocation
      The pipeline injects the full session buffer as LLM context on every
      query.  If the buffer contains a pre-revocation turn that included
      content from a now-revoked document, the LLM sees that content and
      may reproduce it in its answer.

Public API
----------
    pipeline = NaiveRAGPipeline(rbac, vector_index, cache, memory, llm,
                                logger, embedder, top_k=5, doc_metadata={})
    result = pipeline.query(
        actor="alice",
        session_id="alice-session-1",
        query_text="What are the Project Nightingale trial results?",
        step_label="step2_baseline",
    )
    # result.response, result.cache_hit, result.similarity_score, ...
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from .logger import QueryLogger
from .memory import SessionMemory
from .rbac import AccessControlStore
from .semantic_cache import SemanticCache
from .vector_index import VectorIndex
from .llm_client import LLMClient


@dataclass
class QueryResult:
    """Structured return value from NaiveRAGPipeline.query()."""
    response:                str
    retrieved_doc_ids:       list[str]   # ALL retrieved IDs before RBAC filter
    accessible_doc_ids:      list[str]   # IDs that passed RBAC filter (may be empty)
    similarity_score:        float       # highest cosine sim among ALL retrieved docs
    latency_ms:              float
    cache_hit:               bool
    refusal_type:            Optional[str]   # "access_denied" | "not_found" | None
    ground_truth_restricted: bool            # True if any retrieved doc is restricted


class NaiveRAGPipeline:
    """
    Multi-tenant RAG pipeline — intentionally naive / unmitigated.

    Parameters
    ----------
    rbac : AccessControlStore
    vector_index : VectorIndex
    cache : SemanticCache
    memory : SessionMemory
    llm : LLMClient
    logger : QueryLogger
    embedder : SentenceTransformer
        Shared embedding model (same instance used by VectorIndex so the
        cache and index live in the same vector space).
    top_k : int
        Number of nearest-neighbour docs to retrieve.
    doc_metadata : dict[str, dict]
        Mapping of doc_id → {"restricted": bool, "tenant_id": str}.
        Used to populate ground_truth_restricted in the log.
    """

    def __init__(
        self,
        rbac:         AccessControlStore,
        vector_index: VectorIndex,
        cache:        SemanticCache,
        memory:       SessionMemory,
        llm:          LLMClient,
        logger:       QueryLogger,
        embedder:     SentenceTransformer,
        top_k:        int = 5,
        doc_metadata: Optional[dict[str, dict]] = None,
    ) -> None:
        self._rbac    = rbac
        self._index   = vector_index
        self._cache   = cache
        self._memory  = memory
        self._llm     = llm
        self._logger  = logger
        self._embedder = embedder
        self._top_k    = top_k
        self._doc_meta = doc_metadata or {}

    # ── Public ─────────────────────────────────────────────────────────────────

    def query(
        self,
        actor:      str,
        session_id: str,
        query_text: str,
        step_label: str = "",
    ) -> QueryResult:
        """
        Process one query through the naive pipeline and return a QueryResult.

        The three naive flaws are clearly marked with inline comments.
        """
        t0 = time.perf_counter()

        # ── Embed the query (once — shared across cache and index) ─────────────
        q_emb: np.ndarray = self._embedder.encode(
            query_text, normalize_embeddings=True
        )

        # ──────────────────────────────────────────────────────────────────────
        # NAIVE FLAW #1 — Cache checked BEFORE RBAC
        # ──────────────────────────────────────────────────────────────────────
        # If any previous session cached a response for a semantically similar
        # query, that response is returned immediately — without verifying that
        # the current actor still has access to the underlying documents.
        cache_result = self._cache.get(q_emb)
        if cache_result is not None:
            entry, sim = cache_result
            latency_ms = (time.perf_counter() - t0) * 1000
            gt_restricted = self._any_restricted(entry.doc_ids)

            self._logger.log(
                actor=actor,
                session_id=session_id,
                query=query_text,
                retrieved_doc_ids=entry.doc_ids,
                ground_truth_restricted=gt_restricted,
                response_text=entry.response,
                similarity_score=sim,
                latency_ms=latency_ms,
                refusal_type=None,
                cache_hit=True,
                step_label=step_label,
            )
            return QueryResult(
                response=entry.response,
                retrieved_doc_ids=entry.doc_ids,
                accessible_doc_ids=entry.doc_ids,   # assumed accessible (no check)
                similarity_score=sim,
                latency_ms=latency_ms,
                cache_hit=True,
                refusal_type=None,
                ground_truth_restricted=gt_restricted,
            )

        # ──────────────────────────────────────────────────────────────────────
        # NAIVE FLAW #2 — Vector retrieval across the flat index (no tenant filter)
        #                 RBAC applied AFTER retrieval
        # ──────────────────────────────────────────────────────────────────────
        # The index contains documents from all tenants.  The top-k results are
        # fetched first; RBAC is applied as a post-filter.  This means:
        #   a) Similarity scores for restricted docs are computed and logged
        #      regardless of the requester's access rights.
        #   b) After revocation, the revoked document still ranks highly — the
        #      vector index has no awareness of the access-control event.
        retrieved: list[tuple[str, float, str]] = self._index.query(
            q_emb.tolist(), top_k=self._top_k
        )
        all_retrieved_ids = [r[0] for r in retrieved]
        top_score = retrieved[0][1] if retrieved else 0.0

        # RBAC filter (post-retrieval — the naive flaw is already realised above)
        accessible = [
            (doc_id, score, text)
            for doc_id, score, text in retrieved
            if self._rbac.has_access(actor, doc_id)
        ]
        accessible_ids = [r[0] for r in accessible]

        # Determine refusal type for logging / side-channel analysis
        refusal_type: Optional[str] = None
        if not accessible:
            refusal_type = "access_denied" if retrieved else "not_found"

        # ──────────────────────────────────────────────────────────────────────
        # NAIVE FLAW #3 — Session memory injected without purge on revocation
        # ──────────────────────────────────────────────────────────────────────
        # The full session buffer — including any turns that were generated
        # before revocation — is passed to the LLM as context.  If the prior
        # assistant turn quoted from a now-revoked document, the LLM can
        # "remember" and paraphrase that content.
        memory_ctx: list[dict] = self._memory.get_context(session_id)

        # ── LLM generation ─────────────────────────────────────────────────────
        response: str = self._llm.generate(memory_ctx, accessible, query_text)

        # ── Store in cache and memory ──────────────────────────────────────────
        # Store unconditionally so the next similar query hits the cache.
        self._cache.put(q_emb, response, accessible_ids)
        self._memory.append(session_id, "user",      query_text)
        self._memory.append(session_id, "assistant", response)

        latency_ms = (time.perf_counter() - t0) * 1000
        gt_restricted = self._any_restricted(all_retrieved_ids)

        self._logger.log(
            actor=actor,
            session_id=session_id,
            query=query_text,
            retrieved_doc_ids=all_retrieved_ids,
            ground_truth_restricted=gt_restricted,
            response_text=response,
            similarity_score=top_score,
            latency_ms=latency_ms,
            refusal_type=refusal_type,
            cache_hit=False,
            step_label=step_label,
        )
        return QueryResult(
            response=response,
            retrieved_doc_ids=all_retrieved_ids,
            accessible_doc_ids=accessible_ids,
            similarity_score=top_score,
            latency_ms=latency_ms,
            cache_hit=False,
            refusal_type=refusal_type,
            ground_truth_restricted=gt_restricted,
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _any_restricted(self, doc_ids: list[str]) -> bool:
        """True if any doc_id in the list is tagged restricted in ground truth."""
        return any(
            self._doc_meta.get(d, {}).get("restricted", False)
            for d in doc_ids
        )
