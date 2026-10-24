#!/usr/bin/env python3
"""
run.py -- Run an experiment grid from a YAML config. Writes JSONL rows only.

    python run.py --config configs/rq2_revocation_window.yaml --seeds 5
    python run.py --config configs/smoke.yaml --seeds 1 --out results/

Config format:

    name: rq2_revocation_window
    experiment: revocation            # revocation | existence | utility
    base:                             # applied to every cell
      embedder: all-MiniLM-L6-v2
      reranker: cross-encoder/ms-marco-MiniLM-L-6-v2
      llm_backend: stub
      preset: baseline
      events: 50
    grid:                             # cartesian product; one cell per combination
      sync: [periodic:3600, event:0.05]
      preset: [baseline, full]
    variants:                         # optional: named override sets, crossed with the grid
      - {variant: default}
      - {variant: fast_refusal, fast_refusal: true}

Cell keys can be: any Mitigations field, any PipelineConfig field, preset, open_surface,
ablate, embedder, reranker, llm_backend, llm_model, llm_cache, stub_sentences, clock, exposure,
corpus, and experiment parameters (events, revocation_type, probe_times, warm_fillers, tenants,
targets_per_tenant, attackers, victim_warmup, queries, session_turns, revoke_gap_s,
probe_readonly, probe_unseen, update_after_revoke, probe_paraphrase).

corpus: synthetic_v3@seed gives every seed its own generated corpus (synthetic_v3_s<seed>),
so seeds are independent replicates rather than re-draws of events from one corpus.

Output: <out>/<name>/manifest.json and <out>/<name>/runs/<cell_id>_s<seed>.jsonl.
Finished runs are skipped on re-invocation unless --force is given.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import yaml

from src.secure_pipeline.encoding import configure_utf8_stdio


def expand(config: dict) -> list[dict]:
    base = dict(config.get("base", {}))
    base["experiment"] = config["experiment"]
    grid = config.get("grid", {}) or {}
    variants = config.get("variants") or [{}]
    keys = list(grid)
    cells = []
    for values, variant in itertools.product(itertools.product(*(grid[k] for k in keys)), variants):
        cell = {**base, **dict(zip(keys, values)), **variant}
        parts = [f"{k}={v}" for k, v in zip(keys, values)]
        if "variant" in variant:
            parts.append(f"variant={variant['variant']}")
        label = ",".join(parts) or "default"
        digest = hashlib.sha1(json.dumps(cell, sort_keys=True, default=str).encode()).hexdigest()[:8]
        cell["cell_id"] = f"{_slug(label)}-{digest}"
        cell["label"] = label
        cells.append(cell)
    return cells


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "=,._-" else "_" for ch in s)[:80]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=None, help="number of seeds (default: config 'seeds' or 5)")
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    ap.add_argument("--force", action="store_true", help="rerun cells that already have output")
    ap.add_argument("--only", action="append", default=[], metavar="KEY=VALUE",
                    help="run only cells with this field value (repeatable); the manifest keeps every cell")
    args = ap.parse_args()
    configure_utf8_stdio()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    n_seeds = args.seeds or int(config.get("seeds", 5))
    seeds = [args.seed_offset + i for i in range(n_seeds)]
    cells = expand(config)
    out_dir = args.out / config["name"]
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)
    manifest = {"name": config["name"], "experiment": config["experiment"], "config": config,
                "seeds": seeds, "cells": cells}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    from src.secure_pipeline.corpus import seeded_corpus
    from src.secure_pipeline.experiments import Env, run_cell
    from src.secure_pipeline.instrumentation import RunLogger

    for kv in args.only:
        k, v = kv.split("=", 1)
        cells = [c for c in cells if str(c.get(k)) == v]
    envs: dict[tuple, Env] = {}
    total = len(cells) * len(seeds)
    done = 0
    for cell in cells:
        for seed in seeds:
            key = (cell.get("embedder", "all-MiniLM-L6-v2"),
                   cell.get("reranker", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
                   int(cell.get("chunk_tokens", 300)), seeded_corpus(cell.get("corpus", "synthetic"), seed))
            done += 1
            path = out_dir / "runs" / f"{cell['cell_id']}_s{seed}.jsonl"
            if path.exists() and not args.force:
                print(f"[run] {done}/{total} skip {path.name} (exists)")
                continue
            if key not in envs:
                print(f"[run] loading embedder={key[0]} reranker={key[1]} corpus={key[3]}", flush=True)
                envs[key] = Env.build(*key)
            tmp = path.with_suffix(".partial")
            tmp.unlink(missing_ok=True)
            t0 = time.time()
            logger = RunLogger(tmp)
            try:
                run_cell(envs[key], cell, seed, logger)
            finally:
                logger.close()
            tmp.rename(path)
            print(f"[run] {done}/{total} {cell['label']} seed={seed} ({time.time() - t0:.1f}s) -> {path.name}",
                  flush=True)
    print(f"[run] done. Analyze with: python analyze.py {out_dir}")


if __name__ == "__main__":
    main()
