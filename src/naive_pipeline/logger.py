"""
logger.py Structured query event logger.

Produces the Step 9 evidence table described in the design doc:

    timestamp | actor | session_id | query | retrieved_doc_ids
    | ground_truth_restricted | response_text | similarity_score
    | latency_ms | refusal_type | cache_hit | step_label

Every query processed by NaiveRAGPipeline calls logger.log() once.
After all steps complete, logger.dump_csv() writes the flat table to disk.

Public API
    logger = QueryLogger()
    logger.log(actor="alice", session_id="s1", query="...", ...)
    logger.dump_csv("results/run_log.csv")
    rows = logger.rows()   # list[LogRow] for in process analysis
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class LogRow:
    """One row in the evidence table exactly maps to a single pipeline query."""
    timestamp:               str    # ISO 8601 UTC
    actor:                   str    # user ID (e.g. "alice", "bob")
    session_id:              str
    query:                   str
    retrieved_doc_ids:       str    # JSON list of ALL retrieved IDs before RBAC filter
    ground_truth_restricted: bool   # True if ANY retrieved doc is marked restricted
    response_text:           str
    similarity_score:        float  # highest cosine similarity among retrieved docs
    latency_ms:              float
    refusal_type:            str    # "access_denied" | "not_found" | "" (no refusal)
    cache_hit:               bool
    step_label:              str    # e.g. "step2_baseline", "step4_postrevoke_same_session"


_FIELDNAMES = [
    "timestamp",
    "actor",
    "session_id",
    "query",
    "retrieved_doc_ids",
    "ground_truth_restricted",
    "response_text",
    "similarity_score",
    "latency_ms",
    "refusal_type",
    "cache_hit",
    "step_label",
]


class QueryLogger:
    """Append only in memory logger that can be dumped to CSV."""

    def __init__(self) -> None:
        self._rows: list[LogRow] = []

    # Ingestion

    def log(
        self,
        *,
        actor:                   str,
        session_id:              str,
        query:                   str,
        retrieved_doc_ids:       list[str],
        ground_truth_restricted: bool,
        response_text:           str,
        similarity_score:        float,
        latency_ms:              float,
        refusal_type:            Optional[str],
        cache_hit:               bool,
        step_label:              str,
    ) -> None:
        self._rows.append(
            LogRow(
                timestamp=datetime.now(timezone.utc).isoformat(),
                actor=actor,
                session_id=session_id,
                query=query,
                retrieved_doc_ids=json.dumps(retrieved_doc_ids),
                ground_truth_restricted=ground_truth_restricted,
                response_text=response_text,
                similarity_score=round(similarity_score, 6),
                latency_ms=round(latency_ms, 2),
                refusal_type=refusal_type or "",
                cache_hit=cache_hit,
                step_label=step_label,
            )
        )

    # Output

    def dump_csv(self, path: str | Path) -> None:
        """Write all logged rows to a CSV file. Creates parent directories."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writeheader()
            for row in self._rows:
                writer.writerow(asdict(row))
        print(f"[Logger] {len(self._rows)} rows -> {out.resolve()}")

    # In process access

    def rows(self) -> list[LogRow]:
        """Return a copy of all logged rows for in process analysis."""
        return list(self._rows)

    def get_by_step(self, step_label: str) -> Optional[LogRow]:
        """Return the first row matching *step_label*, or None."""
        return next((r for r in self._rows if r.step_label == step_label), None)
