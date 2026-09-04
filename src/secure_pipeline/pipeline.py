"""
pipeline.py -- Multi-Tenant RAG Pipeline supporting Baseline and Mitigated Modes (§1, §3, §3.6).

Architectural Modes:
1. Baseline Mode:
   - Cache checked before RBAC without tenant boundary.
   - Flat global vector index retrieval with post-retrieval RBAC filtering.
   - Unfiltered cross-encoder reranking exposing raw confidence.
   - Stale conversational memory injected without revocation purging.
   - Raw similarity, reranker scores, latency, and distinct refusal texts exposed.

2. Mitigated Mode:
   - Invalidation listener automatically bound to AccessControlManager on revocation.
   - Tenant-isolated and ACL pre-filtered vector retrieval.
   - Cross-encoder reranker applied strictly to authorized candidates.
   - ACL-aware semantic cache with active invalidation eviction.
   - Revocation-purged conversational session memory.
   - Metadata Normalization: score quantization, latency jitter, and standardized refusals.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from .access_control import AccessControlManager
from .index_store import SecureVectorIndex
from .reranker import CrossEncoderReranker
from .semantic_cache import SecureSemanticCache
from .session_memory import SecureSessionMemory
from .normalization import MetadataNormalizer, NormalizedMetadata
from .llm_client import LLMClient
from .instrumentation import InstrumentationLogger, StructuredLogRow


@dataclass
class PipelineQueryResult:
    """Standardized response from RAG Pipeline."""
    response: str
    retrieved_doc_ids: list[str]            # Ground truth candidate doc IDs
    accessible_doc_ids: list[str]           # Authorized doc IDs
    raw_similarity_score: float
    normalized_similarity_score: float
    similarity_band: str
    raw_reranker_score: float
    normalized_reranker_score: float
    raw_latency_ms: float
    effective_latency_ms: float
    cache_hit: bool
    refusal_flag: bool
    refusal_type: Optional[str]
    ground_truth_restricted: bool
    log_row: Optional[StructuredLogRow] = None

    # Backward compatibility properties for MVP test scripts
    @property
    def similarity_score(self) -> float:
        return self.raw_similarity_score

    @property
    def latency_ms(self) -> float:
        return self.effective_latency_ms


class SecureRAGPipeline:
    """
    Unified Multi-Tenant RAG Pipeline.

    Parameters
    ----------
    rbac : AccessControlManager
    vector_index : SecureVectorIndex
    cache : SecureSemanticCache
    memory : SecureSessionMemory
    llm : LLMClient
    logger : InstrumentationLogger
    embedder : SentenceTransformer
    reranker : Optional[CrossEncoderReranker]
    normalizer : Optional[MetadataNormalizer]
    top_k : int
    doc_metadata : Optional[dict]
    mode : str
        "baseline" or "mitigated".
    """

    def __init__(
        self,
        rbac: AccessControlManager,
        vector_index: SecureVectorIndex,
        cache: SecureSemanticCache,
        memory: SecureSessionMemory,
        llm: LLMClient,
        logger: InstrumentationLogger,
        embedder: SentenceTransformer,
        reranker: Optional[CrossEncoderReranker] = None,
        normalizer: Optional[MetadataNormalizer] = None,
        top_k: int = 5,
        doc_metadata: Optional[dict[str, dict]] = None,
        mode: str = "baseline",
    ) -> None:
        self.rbac = rbac
        self.vector_index = vector_index
        self.cache = cache
        self.memory = memory
        self.llm = llm
        self.logger = logger
        self.embedder = embedder
        self.reranker = reranker or CrossEncoderReranker()
        self.normalizer = normalizer or MetadataNormalizer()
        self.top_k = top_k
        self.doc_metadata = doc_metadata or {}
        self._mode = mode

        # Configure sub-components
        self.set_mode(mode)
        self._query_counter = 0

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Switch operating mode between 'baseline' and 'mitigated'."""
        self._mode = mode
        self.rbac.mode = mode
        self.cache.mode = mode
        self.memory.mode = mode

        # In mitigated mode, automatically register invalidation listeners
        if mode == "mitigated":
            self.rbac.register_listener(self.cache.on_revocation)
            self.rbac.register_listener(self.memory.on_revocation)
            self.rbac.register_listener(self.vector_index.on_revocation)

    def query(
        self,
        actor: str,
        session_id: str,
        query_text: str,
        step_label: str = "",
        strategy: str = "direct",
        tenant_id: Optional[str] = None,
        apply_latency_sleep: bool = False,
    ) -> PipelineQueryResult:
        """
        Execute an end-to-end RAG query through the active mode pipeline.
        """
        t0 = time.perf_counter()
        self._query_counter += 1

        user_tenant = tenant_id or self.rbac.get_user_tenant(actor)
        last_revocation_ts = self.rbac.last_revocation_time()
        now_ts = time.time()
        rel_time_s = max(0.0, now_ts - last_revocation_ts) if last_revocation_ts else 0.0

        # 1. Embed query
        q_emb: np.ndarray = self.embedder.encode(
            query_text, normalize_embeddings=True, show_progress_bar=False
        )

        # ---------------------------------------------------------------------
        # 2. Semantic Cache Check
        # ---------------------------------------------------------------------
        cache_result = self.cache.get(
            query_embedding=q_emb,
            user_id=actor if self.mode == "mitigated" else None,
            tenant_id=user_tenant if self.mode == "mitigated" else None,
            rbac=self.rbac if self.mode == "mitigated" else None,
            mode_override=self.mode,
        )

        if cache_result is not None:
            entry, cache_sim = cache_result
            raw_latency_ms = (time.perf_counter() - t0) * 1000.0
            gt_restricted = self._check_restricted(entry.doc_ids)

            if self.mode == "mitigated":
                norm_resp, meta = self.normalizer.normalize(
                    raw_similarity=cache_sim,
                    raw_reranker=cache_sim,
                    raw_latency_ms=raw_latency_ms,
                    response_text=entry.response,
                    raw_refusal_type=None,
                    has_accessible_docs=True,
                    apply_sleep=apply_latency_sleep,
                )
                final_response = norm_resp
                eff_latency_ms = meta.effective_latency_ms
                norm_sim = meta.quantized_similarity
                sim_band = meta.similarity_band
                norm_rrk = meta.quantized_reranker
            else:
                final_response = entry.response
                eff_latency_ms = raw_latency_ms
                norm_sim = cache_sim
                sim_band = "High" if cache_sim >= 0.70 else "Medium"
                norm_rrk = cache_sim

            log_row = self.logger.log(
                relative_time_s=rel_time_s,
                query_count_since_revocation=self._query_counter,
                mode=self.mode,
                actor=actor,
                tenant_id=user_tenant or "",
                session_id=session_id,
                query=query_text,
                raw_similarity_score=cache_sim,
                normalized_similarity_score=norm_sim,
                similarity_band=sim_band,
                raw_reranker_score=cache_sim,
                normalized_reranker_score=norm_rrk,
                latency_ms=raw_latency_ms,
                normalized_latency_ms=eff_latency_ms,
                retrieved_doc_ids=entry.doc_ids,
                accessible_doc_ids=entry.doc_ids,
                ground_truth_restricted=gt_restricted,
                response_text=final_response,
                refusal_flag=False,
                refusal_type=None,
                cache_hit=True,
                step_label=step_label,
                strategy=strategy,
            )

            return PipelineQueryResult(
                response=final_response,
                retrieved_doc_ids=entry.doc_ids,
                accessible_doc_ids=entry.doc_ids,
                raw_similarity_score=cache_sim,
                normalized_similarity_score=norm_sim,
                similarity_band=sim_band,
                raw_reranker_score=cache_sim,
                normalized_reranker_score=norm_rrk,
                raw_latency_ms=raw_latency_ms,
                effective_latency_ms=eff_latency_ms,
                cache_hit=True,
                refusal_flag=False,
                refusal_type=None,
                ground_truth_restricted=gt_restricted,
                log_row=log_row,
            )

        # ---------------------------------------------------------------------
        # 3. Vector Retrieval
        # ---------------------------------------------------------------------
        accessible_set = self.rbac.accessible_docs(actor)

        if self.mode == "mitigated":
            # Pre-filtered retrieval by tenant and RBAC
            retrieved = self.vector_index.query(
                query_embedding=q_emb,
                top_k=self.top_k,
                user_tenant=user_tenant,
                accessible_doc_ids=accessible_set,
                mode_override="mitigated",
            )
            all_retrieved_ids = [r[0] for r in retrieved]
            accessible = retrieved
            accessible_ids = all_retrieved_ids
        else:
            # Baseline: Flat retrieval across all tenants/docs
            retrieved = self.vector_index.query(
                query_embedding=q_emb,
                top_k=self.top_k,
                user_tenant=None,
                accessible_doc_ids=None,
                mode_override="baseline",
            )
            all_retrieved_ids = [r[0] for r in retrieved]
            # Post-retrieval RBAC filtering
            accessible = [r for r in retrieved if self.rbac.has_access(actor, r[0])]
            accessible_ids = [r[0] for r in accessible]

        raw_top_sim = retrieved[0][1] if retrieved else 0.0

        # ---------------------------------------------------------------------
        # 4. Cross-Encoder Reranking
        # ---------------------------------------------------------------------
        if self.mode == "mitigated":
            reranked = self.reranker.rerank(query_text, accessible, top_k=self.top_k)
            raw_top_rrk = reranked[0][2] if reranked else 0.0
            docs_for_generation = [(r[0], r[1], r[3]) for r in reranked]
        else:
            # Baseline: Reranks full candidate set before post-filtering
            reranked_all = self.reranker.rerank(query_text, retrieved, top_k=self.top_k)
            raw_top_rrk = reranked_all[0][2] if reranked_all else 0.0
            docs_for_generation = [
                (r[0], r[1], r[3]) for r in reranked_all
                if self.rbac.has_access(actor, r[0])
            ]

        # Determine raw refusal type
        has_accessible_docs = len(docs_for_generation) > 0
        raw_refusal_type: Optional[str] = None
        if not has_accessible_docs:
            if self.mode == "baseline":
                raw_refusal_type = "access_denied" if all_retrieved_ids else "not_found"
            else:
                raw_refusal_type = "standardized_refusal"

        # ---------------------------------------------------------------------
        # 5. Conversational Memory & LLM Generation
        # ---------------------------------------------------------------------
        memory_ctx = self.memory.get_context(session_id)
        raw_response = self.llm.generate(memory_ctx, docs_for_generation, query_text)

        # Store in cache & memory
        self.cache.put(
            query_embedding=q_emb,
            response=raw_response,
            doc_ids=accessible_ids,
            tenant_id=user_tenant,
            created_by=actor,
        )
        self.memory.append(
            session_id=session_id,
            role="user",
            content=query_text,
            user_id=actor,
        )
        self.memory.append(
            session_id=session_id,
            role="assistant",
            content=raw_response,
            referenced_doc_ids=accessible_ids,
            user_id=actor,
        )

        raw_latency_ms = (time.perf_counter() - t0) * 1000.0
        gt_restricted = self._check_restricted(all_retrieved_ids)

        # ---------------------------------------------------------------------
        # 6. Metadata Normalization & Output Construction
        # ---------------------------------------------------------------------
        if self.mode == "mitigated":
            final_response, meta = self.normalizer.normalize(
                raw_similarity=raw_top_sim,
                raw_reranker=raw_top_rrk,
                raw_latency_ms=raw_latency_ms,
                response_text=raw_response,
                raw_refusal_type=raw_refusal_type,
                has_accessible_docs=has_accessible_docs,
                apply_sleep=apply_latency_sleep,
            )
            eff_latency_ms = meta.effective_latency_ms
            norm_sim = meta.quantized_similarity
            sim_band = meta.similarity_band
            norm_rrk = meta.quantized_reranker
            final_refusal_type = meta.standardized_refusal_type
        else:
            final_response = raw_response
            eff_latency_ms = raw_latency_ms
            norm_sim = raw_top_sim
            sim_band = "High" if raw_top_sim >= 0.70 else ("Medium" if raw_top_sim >= 0.40 else "Low")
            norm_rrk = raw_top_rrk
            final_refusal_type = raw_refusal_type

        refusal_flag = not has_accessible_docs

        log_row = self.logger.log(
            relative_time_s=rel_time_s,
            query_count_since_revocation=self._query_counter,
            mode=self.mode,
            actor=actor,
            tenant_id=user_tenant or "",
            session_id=session_id,
            query=query_text,
            raw_similarity_score=raw_top_sim,
            normalized_similarity_score=norm_sim,
            similarity_band=sim_band,
            raw_reranker_score=raw_top_rrk,
            normalized_reranker_score=norm_rrk,
            latency_ms=raw_latency_ms,
            normalized_latency_ms=eff_latency_ms,
            retrieved_doc_ids=all_retrieved_ids,
            accessible_doc_ids=accessible_ids,
            ground_truth_restricted=gt_restricted,
            response_text=final_response,
            refusal_flag=refusal_flag,
            refusal_type=final_refusal_type,
            cache_hit=False,
            step_label=step_label,
            strategy=strategy,
        )

        return PipelineQueryResult(
            response=final_response,
            retrieved_doc_ids=all_retrieved_ids,
            accessible_doc_ids=accessible_ids,
            raw_similarity_score=raw_top_sim,
            normalized_similarity_score=norm_sim,
            similarity_band=sim_band,
            raw_reranker_score=raw_top_rrk,
            normalized_reranker_score=norm_rrk,
            raw_latency_ms=raw_latency_ms,
            effective_latency_ms=eff_latency_ms,
            cache_hit=False,
            refusal_flag=refusal_flag,
            refusal_type=final_refusal_type,
            ground_truth_restricted=gt_restricted,
            log_row=log_row,
        )

    def _check_restricted(self, doc_ids: list[str]) -> bool:
        return any(
            self.doc_metadata.get(d, {}).get("restricted", False)
            for d in doc_ids
        )


# Backward-compatible alias
NaiveRAGPipeline = SecureRAGPipeline
QueryResult = PipelineQueryResult
