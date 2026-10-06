"""
instrumentation.py -- JSONL run logger.

One line per query: {"tags": {...}, "truth": {...}, "obs": {...}}.
- tags  : experiment labels (run id, seed, preset, world, target doc, phase, ...)
- truth : server-side ground truth (pipeline.Truth); never shown to the attacker
- obs   : the black-box Observation the client received

analyze.py reads these files back; nothing is aggregated at run time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class RunLogger:
    def __init__(self, path: Optional[Path] = None, keep_in_memory: bool = False) -> None:
        self.path = path
        self.rows: list[dict] = []
        self._keep = keep_in_memory or path is None
        self._fh = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("a", encoding="utf-8")

    def log(self, **record) -> None:
        if self._keep:
            self.rows.append(record)
        if self._fh is not None:
            self._fh.write(json.dumps(record, default=_default) + "\n")

    def flush(self) -> None:
        if self._fh is not None:
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def _default(o):
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(type(o))


def read_rows(paths) -> list[dict]:
    rows = []
    for p in paths:
        with Path(p).open(encoding="utf-8") as fh:
            rows.extend(json.loads(line) for line in fh if line.strip())
    return rows
