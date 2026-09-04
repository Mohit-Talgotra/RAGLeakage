"""
experiment_runner.py -- Full Experiment Driver (§5, §7, Fixes 1-5).

Implements:
- Controlled A/B experiment matrix: Baseline Mode vs Mitigated Mode.
- Direction-aware formal metric reporting (Fix 1).
- Exact cache invalidation verification (Fix 2).
- Exercised probe logging and assertions for Memory & Factual recovery (Fix 3).
- Finite, measurable Leakage Half-Life calculation (Fix 4).
- Latency cost optimization and separate overhead tracking (Fix 5).
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
from .metrics import (
    COST_ONLY,
    HIGHER_IS_BETTER,
    LOWER_IS_BETTER,
    METRIC_DIRECTIONS,
    MetricsCalculator,
    SecurityMetricsReport,
)


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
        cache_ttl_seconds: float = 10.0,
        target_doc_id: str = "doc_A6",
    ) -> ExperimentResult:
        """
        Execute a full paired A/B comparison on identical corpus and query sets.
        """
        print("\n" + "=" * 78)
        print(f"  RUNNING A/B EXPERIMENT: Revocation='{revocation_type}' | TTL={cache_ttl_seconds}s")
        print("=" * 78)

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
            cache_ttl=cache_ttl_seconds,
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
            cache_ttl=cache_ttl_seconds,
        )
        mit_report = self.metrics_calc.evaluate_run(
            mode="mitigated",
            log_rows=mit_logger.rows(),
            inferences=mit_inferences,
            probe_definitions=STANDARD_PROBE_SUITE,
            decay_points=mit_decay,
            target_doc_id=target_doc_id,
        )

        # Assert that probes genuinely executed (Fix 3)
        assert base_report.factual_probes_count > 0, "Baseline factual probes count was 0!"
        assert base_report.memory_probes_count > 0, "Baseline memory probes count was 0!"
        assert mit_report.factual_probes_count > 0, "Mitigated factual probes count was 0!"
        assert mit_report.memory_probes_count > 0, "Mitigated memory probes count was 0!"

        # Dump CSV artifacts
        base_logger.dump_csv(self.results_dir / "experiment_baseline_log.csv")
        mit_logger.dump_csv(self.results_dir / "experiment_mitigated_log.csv")

        # Display formal direction-aware comparison table (Fix 1, Fix 5)
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
        normalizer = MetadataNormalizer(base_latency_target_ms=30.0, jitter_range_ms=(5.0, 20.0))
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
        cache_ttl: float,
    ) -> tuple[list[tuple[int, float]], list[AttackerInference]]:
        """
        Executes Steps 1-5 from §5.3 with measurable decay points (Fix 4).
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

        self._verify_cache_invalidation(
            pipeline=pipeline,
            target_doc_id=target_doc_id,
            warm_query=warm_query,
        )

        # 3. Post-Revocation Probe Sequence (t+0, t+1, t+5, t+15, t+30 queries / time steps)
        # Interval points simulate time progression across the TTL boundary to measure LH (Fix 4)
        decay_intervals = [0, 1, 5, 15, 30]

        for interval in decay_intervals:
            # Simulated time offset in seconds for this interval step
            sim_time_offset = float(interval) * (cache_ttl / 10.0)

            # Re-probe with Alice: Same session probe (tests memory and cache)
            r_post_same = pipeline.query(
                "alice", "alice_session_1", warm_query, step_label=f"alice_post_same_t{interval}",
                simulated_time_offset_s=sim_time_offset,
            )
            # Fresh session probe (tests cache in isolation without memory)
            r_post_new = pipeline.query(
                "alice", f"alice_session_{interval + 2}", "Can you summarise the Nightingale project outcomes?",
                step_label=f"alice_post_new_t{interval}",
                simulated_time_offset_s=sim_time_offset,
            )

            # Compute snapshot LM at this interval step
            has_fact_same = any(kw in r_post_same.response.lower() for kw in ["67.3%", "nextomazumab", "0.51", "3.2b", "18,400"])
            has_fact_new = any(kw in r_post_new.response.lower() for kw in ["67.3%", "nextomazumab", "0.51", "3.2b", "18,400"])

            is_refusal_same = r_post_same.refusal_flag or "don't have" in r_post_same.response.lower()
            is_refusal_new = r_post_new.refusal_flag or "don't have" in r_post_new.response.lower()

            current_lm = 0.0
            if (r_post_same.cache_hit or r_post_new.cache_hit) and (has_fact_same or has_fact_new) and not (is_refusal_same and is_refusal_new):
                current_lm = 1.0
            elif (has_fact_same or has_fact_new) and not (is_refusal_same and is_refusal_new):
                current_lm = 1.0

            decay_points.append((interval, current_lm))

        # 4. Attacker Probe Suite across all 4 strategies
        print("  [Attacker] Executing standard probe suite across all 4 strategies...")
        for probe_def in STANDARD_PROBE_SUITE:
            res, inf = attacker.probe(pipeline, probe_def, step_label=f"probe_{probe_def.strategy}_{probe_def.target_doc_id}")
            inferences.append(inf)

        return decay_points, inferences

    def _verify_cache_invalidation(
        self,
        pipeline: SecureRAGPipeline,
        target_doc_id: str,
        warm_query: str,
    ) -> None:
        """
        Re-test cache leakage in isolation immediately after ACCESS_REVOKED.
        The cache is embedding-keyed, so correctness is verified by provenance doc_id
        eviction plus an exact warm-query fresh-session probe.
        """
        current_time = time.time()
        active_target_entries = pipeline.cache.entries_for_doc(target_doc_id, current_time)

        if pipeline.mode == "mitigated":
            if active_target_entries:
                raise AssertionError(
                    f"Mitigated cache still has {len(active_target_entries)} active entries "
                    f"for revoked doc {target_doc_id}; ACCESS_REVOKED eviction missed."
                )
            if not pipeline.cache.revocation_audit:
                raise AssertionError("Mitigated cache did not record any ACCESS_REVOKED audit event.")

        isolation_result = pipeline.query(
            "alice",
            "alice_cache_isolation",
            warm_query,
            step_label=f"cache_isolation_{pipeline.mode}_{target_doc_id}",
            simulated_time_offset_s=0.0,
        )
        leaked_fact = self._contains_sensitive_fact(target_doc_id, isolation_result.response)

        if pipeline.mode == "mitigated":
            if isolation_result.cache_hit:
                raise AssertionError(
                    f"Mitigated cache isolation probe hit stale cache for revoked doc {target_doc_id}."
                )
            if leaked_fact and not isolation_result.refusal_flag:
                raise AssertionError(
                    f"Mitigated cache isolation probe leaked sensitive facts for revoked doc {target_doc_id}."
                )
            print("  [Cache Isolation] Mitigated cache eviction verified: no active target entry, no stale hit.")
        else:
            print(
                "  [Cache Isolation] Baseline fresh-session exact probe "
                f"cache_hit={isolation_result.cache_hit}, leaked_fact={leaked_fact}."
            )

    def _contains_sensitive_fact(self, doc_id: str, response_text: str) -> bool:
        facts = self.corpus_mgr.get_sensitive_facts(doc_id)
        return any(fact.lower() in response_text.lower() for fact in facts)

    def _print_comparison_table(
        self,
        base: SecurityMetricsReport,
        mit: SecurityMetricsReport,
    ) -> None:
        """
        Render direction-aware formal evaluation metrics table (Fix 1, Fix 5).
        """
        w = 24
        print("\n" + "=" * 78)
        print("  FORMAL SECURITY EVALUATION: BASELINE VS MITIGATED MODE")
        print("=" * 78)
        hdr = f"  {'Metric':<32} {'Baseline Mode':<{w}} {'Mitigated Mode':<{w}} Outcome"
        print(f"\n{hdr}")
        print("  " + "-" * (len(hdr) - 2))

        def _format_value(value: float, unit: str = "") -> str:
            if value == float("inf"):
                return "inf (no decay)"
            return f"{value:.3f}{unit}"

        def _metric_outcome(label: str, v_base: float, v_mit: float, unit: str = "") -> str:
            direction = METRIC_DIRECTIONS[label]
            if direction == COST_ONLY:
                diff = v_mit - v_base
                pct = (diff / max(1.0, v_base)) * 100.0
                sign = "+" if diff >= 0 else ""
                return f"Cost: {sign}{diff:.2f}{unit} ({sign}{pct:.1f}%)"

            if label == "Leakage Half-Life (LH)" and (
                v_base == float("inf") or v_mit == float("inf")
            ):
                if v_base == float("inf") and v_mit == float("inf"):
                    return "UNMEASURABLE (no decay observed)"
                if v_base == float("inf"):
                    return "BECAME MEASURABLE"
                return "BECAME UNMEASURABLE (REGRESSION)"
            if label == "Leakage Half-Life (LH)" and v_mit == 0.0 and v_base > 0.0:
                return "ELIMINATED (instant invalidation)"

            if direction == LOWER_IS_BETTER:
                diff = v_base - v_mit
                if v_mit == 0.0 and v_base > 0.0:
                    return f"ELIMINATED (from {_format_value(v_base, unit)} to 0.000{unit})"
                if diff > 0.0001:
                    return f"REDUCED by {diff:.3f}{unit} (SECURE)"
                if diff < -0.0001:
                    return f"INCREASED by {abs(diff):.3f}{unit} (REGRESSION)"
                return "UNCHANGED"

            if direction == HIGHER_IS_BETTER:
                diff = v_mit - v_base
                if diff > 0.0001:
                    return f"INCREASED by {diff:.3f}{unit} (SECURE)"
                if diff < -0.0001:
                    return f"DECREASED by {abs(diff):.3f}{unit} (REGRESSION)"
                return "UNCHANGED"

            raise ValueError(f"Unknown metric direction for {label}: {direction}")

        def _print_sec_row(label: str, v_base: float, v_mit: float, unit: str = ""):
            v_b_str = f"{v_base:.3f}{unit}"
            v_m_str = f"{v_mit:.3f}{unit}"
            outcome = _metric_outcome(label, v_base, v_mit, unit)

            print(f"  {label:<32} {v_b_str:<{w}} {v_m_str:<{w}} {outcome}")

        _print_sec_row("Leakage Magnitude (LM_total)", base.leakage_magnitude_total, mit.leakage_magnitude_total)
        _print_sec_row("LM (Cache Surface)", base.leakage_magnitude_cache, mit.leakage_magnitude_cache)
        _print_sec_row("LM (Memory Surface)", base.leakage_magnitude_memory, mit.leakage_magnitude_memory)
        _print_sec_row("LM (Factual Recovery)", base.leakage_magnitude_facts, mit.leakage_magnitude_facts)
        _print_sec_row("Existence Inference Acc (EIA)", base.existence_inference_accuracy, mit.existence_inference_accuracy)
        _print_sec_row("EIA Precision", base.eia_precision, mit.eia_precision)
        _print_sec_row("EIA Recall", base.eia_recall, mit.eia_recall)
        _print_sec_row("EIA F1-Score", base.eia_f1, mit.eia_f1)
        _print_sec_row("Raw Score Leaks (T4)", float(base.raw_score_leak_count), float(mit.raw_score_leak_count))

        lh_b_str = _format_value(base.leakage_half_life_queries, " steps")
        lh_m_str = _format_value(mit.leakage_half_life_queries, " steps")
        lh_outcome = _metric_outcome(
            "Leakage Half-Life (LH)",
            base.leakage_half_life_queries,
            mit.leakage_half_life_queries,
            " steps",
        )
        print(f"  {'Leakage Half-Life (LH)':<32} {lh_b_str:<{w}} {lh_m_str:<{w}} {lh_outcome}")

        # Diagnostic Counts Row (Fix 3)
        print("\n  " + "-" * (len(hdr) - 2))
        print("  PROBE EXECUTION AUDIT (Diagnostics):")
        print(f"  - Restricted Target Probes Exercised:  Baseline={base.restricted_target_probes_count}, Mitigated={mit.restricted_target_probes_count}")
        print(f"  - Memory Surface Probes Exercised:    Baseline={base.memory_probes_count}, Mitigated={mit.memory_probes_count}")
        print(f"  - Factual Probes Exercised:           Baseline={base.factual_probes_count}, Mitigated={mit.factual_probes_count}")

        # Latency / Operational Overhead Section (Fix 1, Fix 5)
        print("\n  " + "-" * (len(hdr) - 2))
        print("  OPERATIONAL OVERHEAD / PERFORMANCE COST (Latency):")
        print(f"  {'p50 Response Latency':<32} {f'{base.p50_latency_ms:.2f}ms':<{w}} {f'{mit.p50_latency_ms:.2f}ms':<{w}} {_metric_outcome('p50 Response Latency', base.p50_latency_ms, mit.p50_latency_ms, 'ms')}")
        print(f"  {'p95 Response Latency':<32} {f'{base.p95_latency_ms:.2f}ms':<{w}} {f'{mit.p95_latency_ms:.2f}ms':<{w}} {_metric_outcome('p95 Response Latency', base.p95_latency_ms, mit.p95_latency_ms, 'ms')}")
        print("=" * 78 + "\n")
