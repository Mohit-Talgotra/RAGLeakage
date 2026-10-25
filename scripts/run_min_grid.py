#!/usr/bin/env python3
"""
run_min_grid.py -- The reduced Enron grid (configs/min/), for one laptop GPU. Cross-platform.

    python scripts/run_min_grid.py pilot        # 2 seeds x 1 event of the model run; prints s per call
    python scripts/run_min_grid.py paraphrases  # rewordings of every Enron question (once, ~2 h)
    python scripts/run_min_grid.py stub         # stub runs (CPU only): defenses, existence, update
    python scripts/run_min_grid.py model        # the model run: Llama-3.1-8B via Ollama, 100 events/cell
    python scripts/run_min_grid.py all          # stub, paraphrases, then model

The model run rewords its fresh-session probes from data/paraphrases.json and raises a KeyError on
the first question the bank lacks, so "model" refuses to start unless every Enron question is
covered; "paraphrases" retries missing questions with new instruction variants (up to five rounds)
and must end with "0 questions still missing". Failed replies are cached, so running it again repeats
the same attempts; if questions are still missing after five rounds, report them.

Each config is run cell by cell (run.py --only cell_id=...), then analysed with analyze.py. The
reference for paired tests is the baseline cell of revocation runs; existence runs have none, and
--train-tenants is never passed (the default split puts e4-e5 in the test set). Finished cells are
skipped, so the script can be restarted. The stub runs can run in a second terminal while the
model run is going. Uses the interpreter it is started with (sys.executable), so it works with
.venv\\Scripts\\python.exe on Windows and .venv/bin/python elsewhere.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from run import expand  # noqa: E402
from src.secure_pipeline.corpus import corpus_dir, load_corpus  # noqa: E402

CONFIGS = ROOT / "configs" / "min"
STUB = ["p_min_defenses_stub", "p_min_existence_stub", "p_min_update_stub"]
MODEL = ["p_min_enron"]
PILOT = ["p_min_pilot"]
BANK = ROOT / "data" / "paraphrases.json"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _py(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, env=ENV, check=True)


def run_config(name: str, analyze: bool = True) -> Path:
    config = yaml.safe_load((CONFIGS / f"{name}.yaml").read_text(encoding="utf-8"))
    cells = expand(config)
    for i, cell in enumerate(cells, 1):
        t0 = time.time()
        print(f"[min] {name} cell {i}/{len(cells)} start: {cell['label']}", flush=True)
        _py("run.py", "--config", str(CONFIGS / f"{name}.yaml"), "--only", f"cell_id={cell['cell_id']}")
        print(f"[min] {name} cell {i}/{len(cells)} end: {cell['label']} ({time.time() - t0:.0f}s)", flush=True)
    out = ROOT / "results" / config["name"]
    if analyze:
        args = ["analyze.py", str(out)]
        if config["experiment"] == "revocation":
            ref = next((c["label"] for c in cells if c.get("preset") == "baseline"), None)
            if ref:
                args += ["--reference", ref]
        _py(*args)
    return out


def missing_questions() -> list[str]:
    """Questions of the Enron corpus without rewordings in the bank (the model run probes with any of
    them: target, unseen-fact and lost-document questions)."""
    corpus = load_corpus(corpus_dir("enron_c"))
    questions = sorted({x["question"] for d in corpus.docs for x in d["qa"]})
    bank = json.loads(BANK.read_text(encoding="utf-8")) if BANK.exists() else {}
    return [q for q in questions if q not in bank]


def make_paraphrases(rounds: int = 5) -> list[str]:
    for r in range(1, rounds + 1):
        _py("scripts/make_paraphrases.py", "--backend", "ollama", "--model", "llama3.1:8b",
            "--corpus", "enron_c", "--workers", "2", "--attempts", str(3 * r))
        missing = missing_questions()
        print(f"[min] paraphrases round {r}: {len(missing)} questions still missing", flush=True)
        if not missing:
            break
    return missing


def require_bank() -> None:
    missing = missing_questions()
    if missing:
        sys.exit(f"[min] {len(missing)} questions still missing from {BANK.name} (first: {missing[0]!r}); "
                 f"the model run would stop with a KeyError. Run 'run_min_grid.py paraphrases' until it "
                 f"reports 0 missing.")
    print("[min] paraphrase bank covers every Enron question", flush=True)


def pilot_timing(out: Path) -> None:
    """Mean seconds per model call, and what that means for the full model run."""
    lat, events = [], set()
    for path in (out / "runs").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            events.add((path.name, row["tags"].get("event")))
            t = row["truth"]
            if t.get("llm_called") and not t.get("llm_cached"):
                lat.append(t["llm_latency_ms"] / 1000)
    if not lat:
        print("[min] pilot: no uncached model calls in the logs (rerun with an empty .cache/llm?)")
        return
    mean = sum(lat) / len(lat)
    full = yaml.safe_load((CONFIGS / "p_min_enron.yaml").read_text(encoding="utf-8"))
    full_events = len(expand(full)) * int(full["seeds"]) * int(full["base"]["events"])
    hours = mean * len(lat) / max(1, len(events)) * full_events / 3600
    print(f"[min] pilot: {len(lat)} model calls, mean {mean:.2f} s per call, "
          f"{len(lat) / max(1, len(events)):.0f} calls per event")
    print(f"[min] estimate for p_min_enron ({full_events} events): about {hours:.1f} h of model time")


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what not in ("pilot", "paraphrases", "stub", "model", "all"):
        sys.exit(__doc__)
    if what == "pilot":
        pilot_timing(run_config(PILOT[0], analyze=False))
        return
    if what in ("stub", "all"):
        for name in STUB:
            run_config(name)
    if what in ("paraphrases", "all"):
        if make_paraphrases():
            require_bank()  # exits with the count and the first missing question
    if what in ("model", "all"):
        require_bank()
        for name in MODEL:
            run_config(name)
    print("[min] done; fill research_paper/RESULTS_TODO.md slots from results/p_min_*/analysis/")


if __name__ == "__main__":
    main()
