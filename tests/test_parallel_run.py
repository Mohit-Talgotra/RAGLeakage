"""run.py --workers: parallel jobs write the same rows as a sequential run (timing fields aside)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMING = {"t", "llm_latency_ms", "server_latency_ms", "observed_latency_ms", "pad_ms", "latency_ms",
          "cache_age_s", "t_since_revocation_s"}


def _rows(out: Path) -> dict[str, list]:
    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in TIMING}
        return [strip(v) for v in o] if isinstance(o, list) else o
    return {p.name: [strip(json.loads(line)) for line in p.read_text().splitlines()]
            for p in sorted(out.glob("*/runs/*.jsonl"))}


def test_parallel_matches_sequential(tmp_path):
    cmd = [sys.executable, "run.py", "--config", "configs/smoke.yaml", "--seeds", "2"]
    subprocess.run(cmd + ["--out", str(tmp_path / "seq")], cwd=ROOT, check=True, capture_output=True)
    subprocess.run(cmd + ["--out", str(tmp_path / "par"), "--workers", "3"], cwd=ROOT, check=True,
                   capture_output=True)
    seq, par = _rows(tmp_path / "seq"), _rows(tmp_path / "par")
    assert seq.keys() == par.keys() and seq
    assert seq == par
