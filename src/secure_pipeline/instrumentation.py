"""
instrumentation.py -- Comprehensive Security and Performance Instrumentation Logger (§3.7).

Logs all observable and ground-truth signals across every query for downstream
Leakage Magnitude (LM), Leakage Half-Life (LH), and Existence Inference Accuracy (EIA)
metric calculation.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class StructuredLogRow:
    """Comprehensive log entry capturing all ground-truth and observable signals."""
    timestamp: str                         # ISO-8601 UTC
    relative_time_s: float                 # Seconds since latest revocation event
    query_count_since_revocation: int      # Queries issued since latest revocation
    mode: str                              # "baseline" | "mitigated"
    actor: str                             # user ID
    tenant_id: str                         # actor's tenant
    session_id: str
    query: str
    raw_similarity_score: float            # Unnormalized vector similarity
    normalized_similarity_score: float     # Quantized similarity (mitigated)
    similarity_band: str                   # Discrete band: None/Low/Medium/High
    raw_reranker_score: float              # Unnormalized cross-encoder score
    normalized_reranker_score: float       # Quantized reranker score
    latency_ms: float                      # Raw execution time
    normalized_latency_ms: float           # Padded / jittered latency
    retrieved_doc_ids: str                 # JSON list of candidate IDs (ground truth)
    accessible_doc_ids: str                # JSON list of RBAC-authorized IDs
    ground_truth_restricted: bool          # True if any retrieved doc is restricted
    response_text: str                     # Actual response returned to user
    refusal_flag: bool                     # True if query resulted in a refusal
    refusal_type: str                      # "access_denied" | "not_found" | "standardized_refusal" | ""
    cache_hit: bool                        # True if returned from semantic cache
    step_label: str                        # Experiment step identifier
    strategy: str                          # Probing strategy label


_FIELDNAMES = list(StructuredLogRow.__annotations__.keys())


class InstrumentationLogger:
    """Structured in-memory logger with export capabilities."""

    def __init__(self) -> None:
        self._rows: list[StructuredLogRow] = []

    def log(
        self,
        *,
        relative_time_s: float = 0.0,
        query_count_since_revocation: int = 0,
        mode: str = "baseline",
        actor: str,
        tenant_id: str = "",
        session_id: str = "",
        query: str,
        raw_similarity_score: float = 0.0,
        normalized_similarity_score: float = 0.0,
        similarity_band: str = "None",
        raw_reranker_score: float = 0.0,
        normalized_reranker_score: float = 0.0,
        latency_ms: float = 0.0,
        normalized_latency_ms: float = 0.0,
        retrieved_doc_ids: list[str],
        accessible_doc_ids: list[str],
        ground_truth_restricted: bool = False,
        response_text: str = "",
        refusal_flag: bool = False,
        refusal_type: Optional[str] = None,
        cache_hit: bool = False,
        step_label: str = "",
        strategy: str = "direct",
    ) -> StructuredLogRow:
        row = StructuredLogRow(
            timestamp=datetime.now(timezone.utc).isoformat(),
            relative_time_s=round(relative_time_s, 3),
            query_count_since_revocation=query_count_since_revocation,
            mode=mode,
            actor=actor,
            tenant_id=tenant_id,
            session_id=session_id,
            query=query,
            raw_similarity_score=round(raw_similarity_score, 4),
            normalized_similarity_score=round(normalized_similarity_score, 4),
            similarity_band=similarity_band,
            raw_reranker_score=round(raw_reranker_score, 4),
            normalized_reranker_score=round(normalized_reranker_score, 4),
            latency_ms=round(latency_ms, 2),
            normalized_latency_ms=round(normalized_latency_ms, 2),
            retrieved_doc_ids=json.dumps(retrieved_doc_ids),
            accessible_doc_ids=json.dumps(accessible_doc_ids),
            ground_truth_restricted=ground_truth_restricted,
            response_text=response_text,
            refusal_flag=refusal_flag,
            refusal_type=refusal_type or "",
            cache_hit=cache_hit,
            step_label=step_label,
            strategy=strategy,
        )
        self._rows.append(row)
        return row

    def rows(self) -> list[StructuredLogRow]:
        return list(self._rows)

    def get_by_step(self, step_label: str) -> Optional[StructuredLogRow]:
        for r in self._rows:
            if r.step_label == step_label:
                return r
        return None

    def dump_csv(self, path: str | Path) -> None:
        """Write logs to CSV file."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writeheader()
            for row in self._rows:
                writer.writerow(asdict(row))
        print(f"[Logger] {len(self._rows)} rows -> {out.resolve()}")

    def dump_jsonl(self, path: str | Path) -> None:
        """Write logs to JSONL file."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for row in self._rows:
                fh.write(json.dumps(asdict(row)) + "\n")
        print(f"[Logger] {len(self._rows)} rows (JSONL) -> {out.resolve()}")

    def to_pandas(self) -> Any:
        """Convert rows to a pandas DataFrame if pandas is installed."""
        try:
            import pandas as pd
            return pd.DataFrame([asdict(r) for r in self._rows])
        except ImportError:
            return [asdict(r) for r in self._rows]


# Backward-compatible alias
QueryLogger = InstrumentationLogger
