"""
experiment_runner.py -- Full Experiment Driver (§5, §7).

Implements:
- Controlled A/B experiment matrix: Baseline Mode vs Mitigated Mode.
- Independent variables (§5.1):
  * Security Mode: baseline vs. mitigated
  * Revocation Types: single_doc, role, user_offboard
  * Cache TTLs: short (60s), medium (600s), long (3600s)
  * Time/Query decay progression: t+0, t+1, t+5, t+15, t+30 queries
- Automated warm-up queries to populate caches.
- Attacker simulation harness executing all 4 probe strategies.
- Automated computation and side-by-side reporting of:
  * Leakage Magnitude (LM)
  * Leakage Half-Life (LH)
  * Existence Inference Accuracy (EIA)
  * Side-channel leakage observables
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sentence_transformers import SentenceTransformer

from .corpus import CorpusManager
from .access_control import AccessControlManager
from .index_store import SecureVectorIndex
from .semantic_cache import SecureSemanticCache
from .session_memory import SecureSessionMemory
from .reranker import CrossEncoderReranker
from .normalization import MetadataNormalizer
from .llm_client import LLMClient
from .pipeline import SecureRAGPipeline
from .instrumentation import InstrumentationLogger
from .attacker import AttackerHarness, AttackerInference, STANDARD_PROBE_SUITE, ProbeDefinition
from .metrics import MetricsCalculator, SecurityMetricsReport


@dataclass
class ExperimentResult:
    """Encapsulates full results of an A/B experiment run."""
    baseline_report: SecurityMetricsReport
    mitigated_report: SecurityMetricsReport
    baseline_logger: InstrumentationLogger
    mitigated_logger: InstrumentationLogger


class ExperimentRunner:
    """
    Executes the formalized experimental methodology (§5).
    """

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        results_dir: Optional[Path] = None,
    ) -> None:
        self.results_dir = results_dir or Path("results")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        print(f"[ExperimentRunner] Loading embedding model '{embedding_model}' ...")
        self.embedder = SentenceTransformer(embedding_model)
        self.corpus_mgr = CorpusManager()
        self.metrics_calc = MetricsCalculator(self.corpus_mgr)

    def run_ab_comparison(
        self,
        revocation_type: str = "single_doc",
        cache_ttl_seconds: float = 3600.0,
        target_doc_id: str = "doc_A6",
    ) -> ExperimentResult:
        """
        Execute a full paired A/B comparison on identical corpus and query sets.
        """
        print("\n" + "=" * 76)
        print(f"  RUNNING A/B EXPERIMENT: Revocation='{revocation_type}' | TTL={cache_ttl_seconds}s")
        print("=" * 76)

        # 1. Run Baseline Mode
        print("\n>>> PHASE 1: Executing BASELINE (Unmitigated) Pipeline...")
        base_pipeline, base_rbac, base_logger = self._build_pipeline(
            mode="baseline", cache_ttl=cache_ttl_seconds
        )
        base_decay, base_inferences = self._execute_experiment_procedure(
            pipeline=base_pipeline,
            rbac=base_rbac,
            revocation_type=revocation_type,
            target_doc_id=target_doc_id,
        )
        base_report = self.metrics_calc.evaluate_run(
            mode="baseline",
            log_rows=base_logger.rows(),
            inferences=base_inferences,
            probe_definitions=STANDARD_PROBE_SUITE,
            decay_points=base_decay,
            target_doc_id=target_doc_id,
        )

        # 2. Run Mitigated Mode
        print("\n>>> PHASE 2: Executing MITIGATED (Secure) Pipeline...")
        mit_pipeline, mit_rbac, mit_logger = self._build_pipeline(
            mode="mitigated", cache_ttl=cache_ttl_seconds
        )
        mit_decay, mit_inferences = self._execute_experiment_procedure(
            pipeline=mit_pipeline,
            rbac=mit_rbac,
            revocation_type=revocation_type,
            target_doc_id=target_doc_id,
        )
        mit_report = self.metrics_calc.evaluate_run(
            mode="mitigated",
            log_rows=mit_logger.rows(),
            inferences=mit_inferences,
            probe_definitions=STANDARD_PROBE_SUITE,
            decay_points=mit_decay,
            target_doc_id=target_doc_id,
        )

        # Dump CSV artifacts
        base_logger.dump_csv(self.results_dir / "experiment_baseline_log.csv")
        mit_logger.dump_csv(self.results_dir / "experiment_mitigated_log.csv")

        # Display formal comparison table
        self._print_comparison_table(base_report, mit_report)

        return ExperimentResult(
            baseline_report=base_report,
            mitigated_report=mit_report,
            baseline_logger=base_logger,
            mitigated_logger=mit_logger,
        )

    def _build_pipeline(
        self,
        mode: str,
        cache_ttl: float,
    ) -> tuple[SecureRAGPipeline, AccessControlManager, InstrumentationLogger]:
        """Construct pipeline instance with seeded state."""
        docs_dict = self.corpus_mgr.to_dict_list()
        doc_meta = {d["doc_id"]: {"restricted": d["restricted"], "tenant_id": d["tenant_id"]} for d in docs_dict}

        rbac = AccessControlManager(mode=mode)
        # Configure multi-tenant users
        rbac.set_user_tenant("alice", "tenant_alpha")
        rbac.set_user_tenant("bob", "tenant_beta")
        rbac.set_user_tenant("charlie", "tenant_gamma")

        # Define roles
        rbac.define_role("alpha_clinical", ["doc_A6"])
        rbac.define_role("alpha_executive", ["doc_A4", "doc_A5", "doc_A6"])
        rbac.define_role("alpha_user", ["doc_A1", "doc_A2"])
        rbac.define_role("beta_user", ["doc_B1", "doc_B2", "doc_B3"])

        # Initial grants
        for d in docs_dict:
            if d["tenant_id"] == "tenant_alpha":
                rbac.grant("alice", d["doc_id"])
            elif d["tenant_id"] == "tenant_beta" and not d["restricted"]:
                rbac.grant("bob", d["doc_id"])
            elif d["tenant_id"] == "tenant_gamma" and not d["restricted"]:
                rbac.grant("charlie", d["doc_id"])

        rbac.grant_role("alice", "alpha_clinical")

        # Components
        vector_index = SecureVectorIndex(
            chroma_dir=".chroma_full",
            embedder=self.embedder,
            collection_name=f"exp_{mode}_{int(time.time())}",
            mode=mode,
        )
        vector_index.add_documents(docs_dict)

        cache = SecureSemanticCache(
            ttl_seconds=cache_ttl,
            sim_threshold=0.70,
            mode=mode,
        )
        memory = SecureSessionMemory(max_turns=20, mode=mode)
        llm = LLMClient(model="openai/gpt-oss-120b", temperature=0.0)
        logger = InstrumentationLogger()
        normalizer = MetadataNormalizer()
        reranker = CrossEncoderReranker()

        pipeline = SecureRAGPipeline(
            rbac=rbac,
            vector_index=vector_index,
            cache=cache,
            memory=memory,
            llm=llm,
            logger=logger,
            embedder=self.embedder,
            reranker=reranker,
            normalizer=normalizer,
            top_k=5,
            doc_metadata=doc_meta,
            mode=mode,
        )

        return pipeline, rbac, logger

    def _execute_experiment_procedure(
        self,
        pipeline: SecureRAGPipeline,
        rbac: AccessControlManager,
        revocation_type: str,
        target_doc_id: str,
    ) -> tuple[list[tuple[int, float]], list[AttackerInference]]:
        """
        Executes Steps 1-5 from §5.3.
        """
        attacker = AttackerHarness(actor="bob", session_id="attacker_session")
        inferences: list[AttackerInference] = []
        decay_points: list[tuple[int, float]] = []

        # 1. Warm-up Phase: Alice queries target document with valid access
        warm_query = "What are the details of Project Nightingale and its clinical trial findings?"
        print(f"  [Warm-up] Alice queries {target_doc_id} with authorized access (populates cache & memory)")
        r_warm = pipeline.query("alice", "alice_session_1", warm_query, step_label="warmup_alice")

        # 2. Fire Revocation Event (§3.2, §5.1)
        print(f"  [Event] Triggering ACCESS_REVOKED (type='{revocation_type}', target='{target_doc_id}')")
        if revocation_type == "single_doc":
            rbac.revoke("alice", target_doc_id)
        elif revocation_type == "role":
            rbac.revoke_role("alice", "alpha_clinical")
            rbac.revoke("alice", target_doc_id)
        elif revocation_type == "user_offboard":
            rbac.offboard_user("alice")

        # 3. Post-Revocation Probe Sequence (t+0, t+1, t+5, t+15 queries)
        decay_intervals = [0, 1, 5, 15, 30]

        for interval in decay_intervals:
            # Issue intermediate background queries to advance query count / decay
            for i in range(interval if interval in [0, 1] else 2):
                pipeline.query("charlie", "bg_session", "Platform routing latency update", step_label=f"bg_query_{interval}_{i}")

            # Re-probe with Alice (same session and fresh session)
            r_post_same = pipeline.query(
                "alice", "alice_session_1", warm_query, step_label=f"alice_post_same_t{interval}"
            )
            r_post_new = pipeline.query(
                "alice", f"alice_session_{interval + 2}", "Can you summarise the Nightingale project outcomes?",
                step_label=f"alice_post_new_t{interval}"
            )

            # Compute snapshot LM at this interval
            current_lm = 1.0 if (r_post_same.cache_hit or r_post_new.cache_hit) else 0.0
            if "nextomazumab" in r_post_same.response.lower() or "67.3%" in r_post_same.response.lower():
                current_lm = 1.0
            decay_points.append((interval, current_lm))

        # 4. Attacker Probe Suite across all 4 strategies
        print("  [Attacker] Executing standard probe suite across all 4 strategies...")
        for probe_def in STANDARD_PROBE_SUITE:
            res, inf = attacker.probe(pipeline, probe_def, step_label=f"probe_{probe_def.strategy}_{probe_def.target_doc_id}")
            inferences.append(inf)

        return decay_points, inferences

    def _print_comparison_table(
        self,
        base: SecurityMetricsReport,
        mit: SecurityMetricsReport,
    ) -> None:
        """Render side-by-side formal evaluation metrics table."""
        w = 26
        print("\n" + "=" * 76)
        print("  FORMAL SECURITY EVALUATION: BASELINE VS MITIGATED MODE")
        print("=" * 76)
        hdr = f"  {'Metric':<32} {'Baseline Mode':<{w}} {'Mitigated Mode':<{w}} Improvement"
        print(f"\n{hdr}")
        print("  " + "-" * (len(hdr) - 2))

        def _print_row(label: str, v_base: any, v_mit: any, unit: str = "", lower_is_better: bool = True):
            if isinstance(v_base, float) and isinstance(v_mit, float):
                v_b_str = f"{v_base:.3f}{unit}"
                v_m_str = f"{v_mit:.3f}{unit}"
                diff = v_base - v_mit if lower_is_better else v_mit - v_base
                if diff > 0:
                    badge = f"REDUCED by {diff:.3f}{unit} (SECURE)" if lower_is_better else f"INCREASED by {diff:.3f}{unit}"
                elif diff == 0:
                    badge = "EQUAL"
                else:
                    badge = f"+{abs(diff):.3f}{unit}"
            else:
                v_b_str = str(v_base)
                v_m_str = str(v_mit)
                badge = "ELIMINATED" if v_mit == 0 or v_mit == "0.0" else "-"
            print(f"  {label:<32} {v_b_str:<{w}} {v_m_str:<{w}} {badge}")

        _print_row("Leakage Magnitude (LM_total)", base.leakage_magnitude_total, mit.leakage_magnitude_total)
        _print_row("LM (Cache Surface)", base.leakage_magnitude_cache, mit.leakage_magnitude_cache)
        _print_row("LM (Memory Surface)", base.leakage_magnitude_memory, mit.leakage_magnitude_memory)
        _print_row("LM (Factual Recovery)", base.leakage_magnitude_facts, mit.leakage_magnitude_facts)
        _print_row("Leakage Half-Life (LH)", base.leakage_half_life_queries, mit.leakage_half_life_queries, unit=" queries")
        _print_row("Existence Inference Acc (EIA)", base.existence_inference_accuracy, mit.existence_inference_accuracy)
        _print_row("EIA Precision", base.eia_precision, mit.eia_precision)
        _print_row("EIA Recall", base.eia_recall, mit.eia_recall)
        _print_row("EIA F1-Score", base.eia_f1, mit.eia_f1)
        _print_row("Raw Score Leaks (T4)", base.raw_score_leak_count, mit.raw_score_leak_count)
        _print_row("p50 Response Latency", base.p50_latency_ms, mit.p50_latency_ms, unit="ms")
        _print_row("p95 Response Latency", base.p95_latency_ms, mit.p95_latency_ms, unit="ms")
        print("\n" + "=" * 76 + "\n")
