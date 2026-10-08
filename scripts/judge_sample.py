#!/usr/bin/env python3
"""
judge_sample.py -- How much does the exact-match leak judge miss? (review item 1)

Samples post-revocation responses about the revoked target from finished revocation runs,
asks an LLM judge (judge.LLMJudge) about every fact the exact layer did not find, and reports
per cell: the exact leak rate, the extra leak rate the paraphrase judge adds, and the share of
secrets disclosed under each judge. Responses that are exactly a refusal string are scored NO
without a model call. Judge calls go through the LLM disk cache, so reruns are free.

Writes <out>/judge_sample.csv (one row per judged fact), judge_summary.md, and
judge_validation.csv: 150 rows (YES-heavy) with an empty human_label column. Label them by
hand (1 = the response really discloses the value) to estimate the judge's precision.

    python scripts/judge_sample.py results/model_grid_7b results/model_grid_local \
        --backend ollama --model qwen2.5:7b --per-cell 150
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analyze import load  # noqa: E402
from src.secure_pipeline.clock import SimClock  # noqa: E402
from src.secure_pipeline.corpus import corpus_dir, load_corpus  # noqa: E402
from src.secure_pipeline.judge import LLMJudge, disclosed  # noqa: E402
from src.secure_pipeline.llm_client import LLMClient  # noqa: E402
from src.secure_pipeline.normalization import (ACCESS_DENIED_REFUSAL, NOT_FOUND_REFUSAL,  # noqa: E402
                                               UNIFORM_REFUSAL)

REFUSALS = {UNIFORM_REFUSAL, NOT_FOUND_REFUSAL, ACCESS_DENIED_REFUSAL}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dirs", type=Path, nargs="+")
    ap.add_argument("--backend", default="ollama")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--per-cell", type=int, default=150, help="responses sampled per cell")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "judge_sample")
    args = ap.parse_args()
    judge = LLMJudge(LLMClient(args.backend, SimClock(), random.Random(0), model=args.model))
    rng = random.Random(20261008)
    rows, summary = [], []
    for run_dir in args.run_dirs:
        manifest, cells, by_cell = load(run_dir)
        corpus = load_corpus(corpus_dir(cells[0].get("corpus", "synthetic")))
        for cell in cells:
            probes = [r for r in by_cell[cell["cell_id"]] if r["tags"].get("phase") == "probe"
                      and r["tags"].get("probe_kind") in ("same_session", "new_session")]
            sample = rng.sample(probes, min(args.per_cell, len(probes)))
            n_exact = n_extra = sec_exact = sec_llm = sec_total = 0
            for r in sample:
                g, t = r["tags"], r["truth"]
                doc = corpus.doc(g["target"])
                d = disclosed(corpus, g["target"], t["response"], t["source_docs"])
                missed = [f for f in doc["facts"] if f["value"] not in d.facts]
                refusal = t["response"].strip() in REFUSALS
                yes = [] if refusal else [f for f in missed
                                          if judge.conveys(f["key"], f["value"], doc["topic"], t["response"])]
                n_secrets = len(doc["facts"]) + int(bool(doc.get("canary")))
                exact = len(d.facts) + int(d.canary)
                n_exact += exact > 0
                n_extra += exact == 0 and bool(yes)
                sec_exact += exact
                sec_llm += exact + len(yes)
                sec_total += n_secrets
                for f in missed:
                    rows.append({"run": manifest["name"], "cell": cell["label"], "seed": g["seed"],
                                 "event": g["event"], "probe_t": g["probe_t"], "probe_kind": g["probe_kind"],
                                 "fact": f["key"], "value": f["value"], "judge_yes": int(f in yes),
                                 "refusal": int(refusal), "response": t["response"]})
            n = max(1, len(sample))
            summary.append({"run": manifest["name"], "cell": cell["label"], "responses": len(sample),
                            "leak_rate_exact": f"{n_exact / n:.3f}", "extra_leak_rate_llm": f"{n_extra / n:.3f}",
                            "secrets_exact": f"{sec_exact / max(1, sec_total):.3f}",
                            "secrets_exact_plus_llm": f"{sec_llm / max(1, sec_total):.3f}"})
            print(f"[judge] {manifest['name']} {cell['label']}: {summary[-1]}", flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    _write(args.out / "judge_sample.csv", rows)
    yes_rows = [r for r in rows if r["judge_yes"]]
    no_rows = [r for r in rows if not r["judge_yes"] and not r["refusal"]]
    val = rng.sample(yes_rows, min(75, len(yes_rows)))
    val += rng.sample(no_rows, min(150 - len(val), len(no_rows)))
    rng.shuffle(val)
    _write(args.out / "judge_validation.csv", [{**r, "human_label": ""} for r in val])
    cols = list(summary[0]) if summary else []
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(str(s[c]) for c in cols) + " |" for s in summary]
    (args.out / "judge_summary.md").write_text(
        f"# Paraphrase-judge sample ({args.backend}/{args.model})\n\n" + "\n".join(md) +
        "\n\nleak_rate_exact: share of sampled responses with an exact-match leak. extra_leak_rate_llm: "
        "share where only the LLM judge finds one. secrets_*: share of the target's secrets disclosed.\n",
        encoding="utf-8")


def _write(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
