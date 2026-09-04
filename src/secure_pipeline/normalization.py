"""
normalization.py -- Metadata Normalization Layer (§3.6).

Mitigation components:
1. Score Quantization: Quantizes raw vector similarity and reranker confidence into
   coarse discrete bands (e.g. Low, Medium, High) to eliminate fine-grained score
   variations that enable side-channel existence inference (Threats T4, T5).
2. Jittered Latency Padding: Adds randomized latency noise / target padding to
   decouple observable response times from retrieval cache hits vs. filtered misses (Threat T6).
3. Refusal Standardization: Enforces identical refusal wording for "not found" and
   "access denied" cases so refusal phrasing cannot act as an existence oracle (Threat T7).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalizedMetadata:
    """Normalized side-channel outputs."""
    similarity_band: str            # "None" | "Low" | "Medium" | "High"
    quantized_similarity: float     # Coarse float representation (e.g. 0.0, 0.33, 0.66, 1.0)
    reranker_band: str              # "None" | "Low" | "Medium" | "High"
    quantized_reranker: float
    effective_latency_ms: float
    standardized_refusal_text: Optional[str]
    standardized_refusal_type: Optional[str]


class MetadataNormalizer:
    """
    Applies security normalization to prevent side-channel leakage.

    Parameters
    ----------
    base_latency_target_ms : float
        Target floor latency to normalize timing variations (default: 50.0 ms).
    jitter_range_ms : tuple of (float, float)
        Random uniform latency jitter added to responses (default: 5.0 - 25.0 ms).
    standard_refusal_message : str
        Uniform refusal string used for ALL empty / unauthorized / filtered outcomes.
    """

    DEFAULT_REFUSAL = "I don't have access to information answering that question."

    def __init__(
        self,
        base_latency_target_ms: float = 30.0,
        jitter_range_ms: tuple[float, float] = (5.0, 20.0),
        standard_refusal_message: str = DEFAULT_REFUSAL,
    ) -> None:
        self.base_latency_target_ms = base_latency_target_ms
        self.jitter_range_ms = jitter_range_ms
        self.standard_refusal_message = standard_refusal_message

    # ---- 1. Score Quantization (§3.6) ---------------------------------------

    def quantize_similarity_score(self, score: float) -> tuple[str, float]:
        """
        Quantizes a continuous similarity score into a coarse categorical band.
        Eliminates sub-decimal variations that leak document presence.
        """
        if score <= 0.05:
            return "None", 0.0
        elif score < 0.40:
            return "Low", 0.25
        elif score < 0.70:
            return "Medium", 0.50
        else:
            return "High", 0.85

    def quantize_reranker_score(self, score: float) -> tuple[str, float]:
        """Quantizes reranker confidence score into discrete buckets."""
        if score <= 0.10:
            return "None", 0.0
        elif score < 0.45:
            return "Low", 0.25
        elif score < 0.75:
            return "Medium", 0.50
        else:
            return "High", 0.85

    # ---- 2. Latency Jitter / Padding (§3.6) ----------------------------------

    def apply_latency_padding(self, raw_latency_ms: float, sleep: bool = False) -> float:
        """
        Calculates and optionally injects jittered latency to mask cache-hit / miss differences.
        """
        jitter = random.uniform(*self.jitter_range_ms)
        padded_latency = max(raw_latency_ms, self.base_latency_target_ms) + jitter

        if sleep:
            diff_s = max(0.0, (padded_latency - raw_latency_ms) / 1000.0)
            if diff_s > 0:
                time.sleep(diff_s)

        return round(padded_latency, 2)

    # ---- 3. Refusal Standardization (§3.6) -----------------------------------

    def normalize_refusal(
        self,
        response_text: str,
        refusal_type: Optional[str],
        has_accessible_docs: bool,
    ) -> tuple[str, Optional[str]]:
        """
        Standardizes refusal responses.
        If no accessible documents were retrieved, replaces any response with the
        canonical uniform refusal string, masking whether a restricted doc existed.
        """
        if not has_accessible_docs or refusal_type is not None:
            return self.standard_refusal_message, "standardized_refusal"
        return response_text, None

    # ---- Full Normalization Pipeline ----------------------------------------

    def normalize(
        self,
        raw_similarity: float,
        raw_reranker: float,
        raw_latency_ms: float,
        response_text: str,
        raw_refusal_type: Optional[str],
        has_accessible_docs: bool,
        apply_sleep: bool = False,
    ) -> tuple[str, NormalizedMetadata]:
        """Apply all metadata normalization mitigations in sequence."""
        sim_band, sim_quant = self.quantize_similarity_score(raw_similarity)
        rrk_band, rrk_quant = self.quantize_reranker_score(raw_reranker)
        norm_latency = self.apply_latency_padding(raw_latency_ms, sleep=apply_sleep)
        norm_response, norm_refusal = self.normalize_refusal(
            response_text, raw_refusal_type, has_accessible_docs
        )

        metadata = NormalizedMetadata(
            similarity_band=sim_band,
            quantized_similarity=sim_quant,
            reranker_band=rrk_band,
            quantized_reranker=rrk_quant,
            effective_latency_ms=norm_latency,
            standardized_refusal_text=norm_response if norm_refusal else None,
            standardized_refusal_type=norm_refusal,
        )
        return norm_response, metadata
