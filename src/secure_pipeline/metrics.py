"""
metrics.py -- Formalized Security and Performance Metrics Calculator (§4).

Implements:
1. Leakage Magnitude (LM): Fraction of restricted ground-truth facts recovered post-revocation.
   Broken down by artifact (Index, Cache, Memory, Total).
2. Leakage Half-Life (LH): Decay point t where LM(t) = 0.5 * LM(0+).
3. Existence Inference Accuracy (EIA): Binary classification accuracy, precision, recall,
   and F1-score of attacker side-channel existence inferences.
4. Latency Statistics: p50 and p95 latency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .attacker import AttackerInference, ProbeDefinition
    from .corpus import CorpusManager
    from .instrumentation import StructuredLogRow


@dataclass
class SecurityMetricsReport:
    """Formalized evaluation metrics bundle for a test suite run."""
    mode: str
    total_probes: int
    leakage_magnitude_total: float       # LM in [0.0, 1.0]
    leakage_magnitude_cache: float       # LM attributable to cache hits
    leakage_magnitude_memory: float      # LM attributable to conversational memory
    leakage_magnitude_facts: float       # Fraction of ground-truth sensitive facts leaked
    leakage_half_life_queries: float     # LH in query-count units
    existence_inference_accuracy: float  # EIA in [0.0, 1.0]
    eia_precision: float
    eia_recall: float
    eia_f1: float
    p50_latency_ms: float
    p95_latency_ms: float
    raw_score_leak_count: int


class MetricsCalculator:
    """
    Computes formalized metrics (§4) from probe logs and ground truth.
    """

    def __init__(self, corpus_manager: Optional[CorpusManager] = None) -> None:
        self.corpus_manager = corpus_manager

    def compute_leakage_magnitude(
        self,
        log_rows: list[StructuredLogRow],
        target_doc_id: str = "doc_A6",
    ) -> dict[str, float]:
        """
        Computes Leakage Magnitude (LM = restricted_info_recovered / restricted_info_total).
        """
        if not log_rows:
            return {"LM_total": 0.0, "LM_cache": 0.0, "LM_memory": 0.0, "LM_facts": 0.0}

        # Look up sensitive facts for the target doc
        facts = []
        if self.corpus_manager:
            facts = self.corpus_manager.get_sensitive_facts(target_doc_id)
        if not facts:
            facts = ["nextomazumab", "67.3%", "41.2%", "HR 0.51", "3.2B", "18,400"]

        total_facts = len(facts)
        recovered_facts = set()

        cache_hits_on_restricted = 0
        memory_leaks = 0
        restricted_probes = 0

        for r in log_rows:
            if not r.ground_truth_restricted and target_doc_id not in r.retrieved_doc_ids:
                continue

            restricted_probes += 1
            if r.cache_hit:
                cache_hits_on_restricted += 1

            if "memory-assisted" in r.response_text or "earlier conversation" in r.response_text:
                memory_leaks += 1

            for fact in facts:
                if fact.lower() in r.response_text.lower():
                    recovered_facts.add(fact)

        fact_lm = len(recovered_facts) / max(1, total_facts)
        cache_lm = cache_hits_on_restricted / max(1, restricted_probes)
        memory_lm = memory_leaks / max(1, restricted_probes)

        # Total combined LM is the maximum of factual recovery or unauthorized cache/memory delivery
        total_lm = max(fact_lm, cache_lm, memory_lm)

        return {
            "LM_total": round(total_lm, 4),
            "LM_cache": round(cache_lm, 4),
            "LM_memory": round(memory_lm, 4),
            "LM_facts": round(fact_lm, 4),
        }

    def compute_leakage_half_life(
        self,
        decay_points: list[tuple[int, float]],
    ) -> float:
        """
        Calculates Leakage Half-Life (LH = query count or time where LM(t) = 0.5 * LM(0+)).

        Parameters
        ----------
        decay_points : list of (query_count_since_revocation, LM_value)
        """
        if not decay_points:
            return 0.0

        # Sort by step/time
        sorted_points = sorted(decay_points, key=lambda x: x[0])
        initial_lm = sorted_points[0][1]

        if initial_lm <= 0.001:
            # Immediate elimination -> LH is 0.0
            return 0.0

        target_lm = 0.5 * initial_lm

        # Search for crossover point
        for i in range(len(sorted_points) - 1):
            t1, lm1 = sorted_points[i]
            t2, lm2 = sorted_points[i + 1]

            if lm1 >= target_lm and lm2 <= target_lm:
                # Linear interpolation
                if lm1 == lm2:
                    return float(t1)
                frac = (lm1 - target_lm) / (lm1 - lm2)
                return float(round(t1 + frac * (t2 - t1), 2))

        # If it never decayed below 50% within the probe window:
        last_t, last_lm = sorted_points[-1]
        if last_lm > target_lm:
            return float(math.inf)  # Indefinite half-life (e.g. baseline without TTL expiry)
        return float(last_t)

    def compute_existence_inference_accuracy(
        self,
        inferences: list[AttackerInference],
        probe_definitions: list[ProbeDefinition],
    ) -> dict[str, float]:
        """
        Computes Existence Inference Accuracy (EIA), Precision, Recall, and F1.
        """
        if not inferences or not probe_definitions:
            return {"EIA": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}

        truth_map = {p.query_text: p.is_true_positive for p in probe_definitions}

        tp = 0
        fp = 0
        tn = 0
        fn = 0

        for inf in inferences:
            gt = truth_map.get(inf.query_text, False)
            pred = inf.inferred_exists

            if pred and gt:
                tp += 1
            elif pred and not gt:
                fp += 1
            elif not pred and not gt:
                tn += 1
            elif not pred and gt:
                fn += 1

        total = tp + fp + tn + fn
        accuracy = (tp + tn) / max(1, total)
        precision = tp / max(1, (tp + fp))
        recall = tp / max(1, (tp + fn))
        f1 = (2 * precision * recall) / max(1e-9, (precision + recall))

        return {
            "EIA": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    def compute_latency_percentiles(self, log_rows: list[StructuredLogRow]) -> tuple[float, float]:
        """Compute p50 and p95 latency."""
        if not log_rows:
            return 0.0, 0.0
        latencies = sorted(r.normalized_latency_ms if r.mode == "mitigated" else r.latency_ms for r in log_rows)
        n = len(latencies)
        p50 = latencies[int(0.50 * (n - 1))]
        p95 = latencies[int(0.95 * (n - 1))]
        return round(p50, 2), round(p95, 2)

    def evaluate_run(
        self,
        mode: str,
        log_rows: list[StructuredLogRow],
        inferences: list[AttackerInference],
        probe_definitions: list[ProbeDefinition],
        decay_points: Optional[list[tuple[int, float]]] = None,
        target_doc_id: str = "doc_A6",
    ) -> SecurityMetricsReport:
        """
        Aggregate all metrics into a comprehensive SecurityMetricsReport.
        """
        lm_dict = self.compute_leakage_magnitude(log_rows, target_doc_id)
        eia_dict = self.compute_existence_inference_accuracy(inferences, probe_definitions)
        p50, p95 = self.compute_latency_percentiles(log_rows)

        lh = self.compute_leakage_half_life(decay_points or [(0, lm_dict["LM_total"])])

        raw_score_leaks = sum(
            1 for r in log_rows
            if r.ground_truth_restricted and r.raw_similarity_score > 0.40 and not r.cache_hit
        )

        return SecurityMetricsReport(
            mode=mode,
            total_probes=len(log_rows),
            leakage_magnitude_total=lm_dict["LM_total"],
            leakage_magnitude_cache=lm_dict["LM_cache"],
            leakage_magnitude_memory=lm_dict["LM_memory"],
            leakage_magnitude_facts=lm_dict["LM_facts"],
            leakage_half_life_queries=lh,
            existence_inference_accuracy=eia_dict["EIA"],
            eia_precision=eia_dict["precision"],
            eia_recall=eia_dict["recall"],
            eia_f1=eia_dict["f1"],
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            raw_score_leak_count=raw_score_leaks,
        )
