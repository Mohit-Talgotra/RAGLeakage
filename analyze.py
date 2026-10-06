#!/usr/bin/env python3
"""
analyze.py -- Turn run.py JSONL logs into the paper's tables and figures.

    python analyze.py results/rq2_revocation_window
    python analyze.py results/rq3_existence --train-tenants t1 t2 t3
    python analyze.py results/rq5_utility --leakage results/rq1_surfaces

Writes <dir>/analysis/summary.md, one CSV per table, and PNG figures.

revocation : per-event LM (secrets disclosed after revocation), per-surface LM
             (cache / stale index / memory, attributed from ground truth), leakage
             lifetime survival (Kaplan-Meier median + bootstrap CI), analytic sync
             prediction, paired differences against a reference cell.
existence  : learned black-box attacker (logistic regression and gradient boosting)
             trained on shadow tenants, tested on held-out tenants; AUC [95% CI],
             TPR@1%FPR and balanced accuracy per channel x exposure profile x attacker.
utility    : Recall@k, nDCG@k, answer correctness, over-refusal, p50/p95 latency,
             cache hit rate; optional Pareto plot against leakage from another run.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.secure_pipeline.attacker import (CHANNELS, LearnedAttacker, ThresholdAttacker, features,
                                          project)
from src.secure_pipeline.corpus import load_corpus
from src.secure_pipeline.instrumentation import read_rows
from src.secure_pipeline.judge import LLMJudge, disclosed
from src.secure_pipeline.metrics import (auc_ci, bootstrap_ci, eia_metrics, fmt_ci, kaplan_meier,
                                         km_median_ci, leak_lifetime, ndcg_at_k, paired_bootstrap,
                                         percentile, recall_at_k)

# Reference categorical palette (fixed slot order; see the dataviz skill's palette.md).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
SURFACE_COLORS = {"cache": SERIES[0], "index": SERIES[1], "memory": SERIES[2]}


# ---- I/O ---------------------------------------------------------------------------

def load(run_dir: Path):
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = read_rows(sorted((run_dir / "runs").glob("*.jsonl")))
    by_cell: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cell[r["tags"]["cell"]].append(r)
    cells = [c for c in manifest["cells"] if c["cell_id"] in by_cell]
    return manifest, cells, by_cell


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def md_table(rows: list[dict], cols: list[str]) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    return "\n".join(out)


def _style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    ax.set_xlabel(xlabel, color=INK_2)
    ax.set_ylabel(ylabel, color=INK_2)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK_2)


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "figure.dpi": 150, "savefig.bbox": "tight"})
    return plt


# ---- Revocation (RQ1, RQ2, RQ4) ------------------------------------------------------

def surface_of(truth: dict, target: str) -> str:
    if truth["cache_hit"]:
        return "cache"
    if target in truth["stale_docs_used"]:
        return "index"
    return "memory"


def collect_events(rows: list[dict], corpus, judge: LLMJudge | None = None) -> dict[tuple, dict]:
    """Group post-revocation probes by (seed, event) and record which target secrets leaked,
    through which surface, and whether anything leaked at each probe time."""
    events: dict[tuple, dict] = {}
    for r in rows:
        g, t = r["tags"], r["truth"]
        if g.get("phase") != "probe":
            continue
        ev = events.setdefault((g["seed"], g["event"]), {
            "target": g["target"], "secrets": set(), "by_surface": defaultdict(set),
            "times": defaultdict(bool), "n_secrets": len(corpus.secrets(g["target"]))})
        d = disclosed(corpus, g["target"], t["response"], t["source_docs"], judge)
        got = set(d.facts) | ({"<canary>"} if d.canary else set())
        ev["times"][g["probe_t"]] |= bool(got)
        if got:
            ev["secrets"] |= got
            ev["by_surface"][surface_of(t, g["target"])] |= got
    return events


def event_lm(events: dict[tuple, dict]) -> dict[tuple, float]:
    return {k: len(e["secrets"]) / e["n_secrets"] for k, e in events.items()}


def analyze_revocation(manifest, cells, by_cell, corpus, out: Path, reference: str | None,
                       judge: LLMJudge | None = None) -> str:
    table, events_by_cell, curves = [], {}, {}
    for cell in cells:
        events = collect_events(by_cell[cell["cell_id"]], corpus, judge)
        lm = event_lm(events)
        lm_s = {s: [len(e["by_surface"][s]) / e["n_secrets"] for e in events.values()] for s in SURFACE_COLORS}
        life = [leak_lifetime(list(e["times"]), list(e["times"].values())) for e in events.values()]
        dur, obs = [x[0] for x in life], [x[1] for x in life]
        med = km_median_ci(dur, obs)
        leaking = [(d_, o_) for d_, o_, lk in zip(dur, obs, lm.values()) if lk > 0]
        med_leaking = km_median_ci([x[0] for x in leaking], [x[1] for x in leaking])
        events_by_cell[cell["cell_id"]] = lm
        horizon = max((t for e in events.values() for t in e["times"]), default=0.0)
        curves[cell["label"]] = (*kaplan_meier(dur, obs), horizon)
        sync = cell.get("sync", "live")
        analytic = ""
        if str(sync).startswith("periodic:"):
            analytic = f"{float(str(sync).split(':')[1]) / 2:g}"
        table.append({
            "cell": cell["label"], "events": len(events),
            "LM": fmt_ci(*bootstrap_ci(list(lm.values()))),
            "LM_cache": fmt_ci(*bootstrap_ci(lm_s["cache"])),
            "LM_index": fmt_ci(*bootstrap_ci(lm_s["index"])),
            "LM_memory": fmt_ci(*bootstrap_ci(lm_s["memory"])),
            "leak_rate": f"{np.mean([v > 0 for v in lm.values()]):.3f}",
            "LH_median_s": fmt_ci(*med, digits=0),
            "LH_median_leaking_s": fmt_ci(*med_leaking, digits=0),
            "censored": f"{sum(not o for o in obs)}/{len(obs)}",
            "analytic_index_staleness_mean_s": analytic,
            "_lm_surface_means": {s: float(np.mean(v)) if v else 0.0 for s, v in lm_s.items()},
        })

    ref = next((c for c in cells if c["label"] == reference), cells[0]) if cells else None
    paired = []
    for cell in cells:
        if ref is None or cell is ref:
            continue
        a, b = events_by_cell[cell["cell_id"]], events_by_cell[ref["cell_id"]]
        keys = sorted(set(a) & set(b))
        res = paired_bootstrap([a[k] for k in keys], [b[k] for k in keys])
        paired.append({"cell": cell["label"], "vs": ref["label"], "delta_LM": fmt_ci(res["diff"], res["lo"], res["hi"]),
                       "p": f"{res['p']:.4f}", "pairs": res["n"]})

    surface_means = {r["cell"]: r.pop("_lm_surface_means") for r in table}
    write_csv(out / "revocation_summary.csv", table)
    write_csv(out / "revocation_paired.csv", paired)

    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for i, (label, (times, surv, horizon)) in enumerate(curves.items()):
        # Extend the last step to the probe horizon so censored (still leaking) events stay visible.
        hours = np.append(np.asarray(times), max(horizon, times[-1])) / 3600.0
        ax.step(hours, np.append(surv, surv[-1]), where="post", color=SERIES[i % len(SERIES)],
                linewidth=2, label=label)
    _style(ax, "Leakage survival after revocation", "hours since revocation", "share of events still leaking")
    ax.set_ylim(-0.02, 1.02)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK)
    fig.savefig(out / "rq2_survival.png")
    plt.close(fig)

    labels = list(surface_means)
    fig, ax = plt.subplots(figsize=(6.4, 0.9 + 0.75 * max(1, len(labels))))
    y = np.arange(len(labels))
    h = 0.8 / len(SURFACE_COLORS)
    for j, (surf, color) in enumerate(SURFACE_COLORS.items()):
        vals = [surface_means[l][surf] for l in labels]
        ax.barh(y + (j - 1) * h, vals, height=h, color=color, edgecolor="white", linewidth=1, label=surf)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    _style(ax, "Secrets disclosed after revocation, by artifact", "mean leakage magnitude per event", "")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.28),
              labelcolor=INK)
    fig.savefig(out / "rq1_surfaces.png")
    plt.close(fig)

    cols = ["cell", "events", "LM", "LM_cache", "LM_index", "LM_memory", "leak_rate", "LH_median_s",
            "LH_median_leaking_s", "censored",
            "analytic_index_staleness_mean_s"]
    text = "## Revocation window\n\n" + md_table(table, cols)
    if paired:
        text += "\n\nPaired difference in event LM (same seeds and events):\n\n" + md_table(
            paired, ["cell", "vs", "delta_LM", "p", "pairs"])
    text += "\n\nFigures: rq2_survival.png, rq1_surfaces.png\n"
    return text


# ---- Existence inference (RQ3) --------------------------------------------------------

def analyze_existence(manifest, cells, by_cell, out: Path, train_tenants: list[str] | None) -> str:
    profiles = ("text_only", "with_sources", "with_reranker")
    table, roc_data = [], {}
    for cell in cells:
        probes = [r for r in by_cell[cell["cell_id"]] if r["tags"].get("phase") == "probe"]
        tenants = sorted({r["tags"]["tenant"] for r in probes})
        train_t = set(train_tenants or tenants[: max(1, len(tenants) * 3 // 5)])
        for attacker in sorted({r["tags"]["attacker"] for r in probes}) + ["all"]:
            rows = [r for r in probes if attacker == "all" or r["tags"]["attacker"] == attacker]
            for profile in profiles:
                # Attacker inputs: projected obs + its own query and strategy (from tags). Never truth.
                feats = [features(project(r["obs"], profile), r["tags"]["probe_query"], r["tags"]["strategy"])
                         for r in rows]
                y = np.array([r["tags"]["world"] for r in rows])
                tr = np.array([r["tags"]["tenant"] in train_t for r in rows])
                if tr.all() or not tr.any():
                    continue
                f_tr = [f for f, m in zip(feats, tr) if m]
                f_te = [f for f, m in zip(feats, tr) if not m]
                y_tr, y_te = y[tr], y[~tr]
                # Trial = one attacker's four probes against one target in one world.
                trial = [(r["tags"]["seed"], r["tags"]["target"], r["tags"]["attacker"], r["tags"]["world"])
                         for r, m in zip(rows, tr) if not m]
                thr = np.array([ThresholdAttacker().score(f) for f in f_te])
                base = {"cell": cell["label"], "attacker": attacker, "profile": profile, "n_test": len(y_te)}
                table.append({**base, "model": "threshold", "channel": "rules", **_eia_cols(y_te, thr, trial)})
                for model in ("logreg", "gboost"):
                    scores = LearnedAttacker(model).fit(f_tr, y_tr).scores(f_te)
                    for ch in list(CHANNELS) + ["combined"]:
                        table.append({**base, "model": model, "channel": ch, **_eia_cols(y_te, scores[ch], trial)})
                        if model == "gboost" and profile == "with_reranker" and attacker == "all":
                            roc_data.setdefault(cell["label"], {})[ch] = (y_te, scores[ch])
    write_csv(out / "existence_eia.csv", table)

    plt = _plt()
    from sklearn.metrics import roc_curve
    if roc_data:
        n = len(roc_data)
        fig, axes = plt.subplots(1, n, figsize=(3.4 * n, 3.4), squeeze=False)
        for ax, (label, chans) in zip(axes[0], roc_data.items()):
            for i, ch in enumerate(list(CHANNELS) + ["combined"]):
                if ch not in chans:
                    continue
                y, s = chans[ch]
                if len(set(y)) < 2:
                    continue
                fpr, tpr, _ = roc_curve(y, s)
                ax.plot(fpr, tpr, color=SERIES[i % len(SERIES)], linewidth=2, label=ch)
            ax.plot([0, 1], [0, 1], color=GRID, linewidth=1)
            _style(ax, label, "false positive rate", "true positive rate")
        axes[0][0].legend(frameon=False, fontsize=7, labelcolor=INK)
        fig.savefig(out / "rq3_roc.png")
        plt.close(fig)

    key = [r for r in table if r["attacker"] == "all" and r["model"] in ("gboost", "threshold")
           and r["channel"] in ("combined", "rules", "latency", "refusal", "score", "content")]
    text = "## Existence inference (twin worlds, held-out tenants)\n\n" + md_table(
        key, ["cell", "profile", "model", "channel", "AUC", "AUC_trial", "TPR@1%FPR", "balanced_acc", "n_test"])
    text += "\n\nFull table: existence_eia.csv. Figure: rq3_roc.png (gboost, with_reranker, all attackers).\n"
    return text


def _eia_cols(y, s, trial_keys) -> dict:
    """Per-probe metrics, plus trial-level AUC where the attacker averages its four probe scores."""
    s = np.asarray(s)
    m = eia_metrics(y, s)
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, k in enumerate(trial_keys):
        groups[k].append(i)
    ty = np.array([y[idx[0]] for idx in groups.values()])
    ts = np.array([s[idx].mean() for idx in groups.values()])
    return {"AUC": fmt_ci(*auc_ci(y, s)), "AUC_trial": fmt_ci(*auc_ci(ty, ts)),
            "TPR@1%FPR": f"{m['tpr_at_1fpr']:.3f}", "balanced_acc": f"{m['balanced_acc']:.3f}"}


# ---- Utility (RQ5) ------------------------------------------------------------------

def analyze_utility(manifest, cells, by_cell, out: Path, leakage_dir: Path | None, corpus) -> str:
    table, points = [], {}
    for cell in cells:
        rows = by_cell[cell["cell_id"]]
        first = [r for r in rows if r["tags"]["phase"] == "first"]
        repeat = [r for r in rows if r["tags"]["phase"] == "repeat"]
        k = int(cell.get("top_k", 5))
        rec = [recall_at_k(r["truth"]["candidate_docs"], r["tags"]["doc"], k) for r in first]
        ndcg = [ndcg_at_k(r["truth"]["candidate_docs"], r["tags"]["doc"], k) for r in first]
        correct = [float(r["tags"]["answer"] in r["truth"]["response"]) for r in rows]
        refused = [float(r["truth"]["refused"]) for r in rows]
        lat = [r["obs"]["latency_ms"] for r in rows]
        hits = [float(r["truth"]["cache_hit"]) for r in repeat]
        table.append({
            "cell": cell["label"], "queries": len(rows),
            "Recall@k": fmt_ci(*bootstrap_ci(rec)), "nDCG@k": fmt_ci(*bootstrap_ci(ndcg)),
            "correct": fmt_ci(*bootstrap_ci(correct)), "over_refusal": fmt_ci(*bootstrap_ci(refused)),
            "p50_ms": f"{percentile(lat, 50):.0f}", "p95_ms": f"{percentile(lat, 95):.0f}",
            "cache_hit_rate": fmt_ci(*bootstrap_ci(hits)),
        })
        points[cell.get("preset", cell["label"])] = percentile(lat, 50)
    write_csv(out / "utility_summary.csv", table)
    text = "## Utility and cost\n\n" + md_table(
        table, ["cell", "queries", "Recall@k", "nDCG@k", "correct", "over_refusal", "p50_ms", "p95_ms",
                "cache_hit_rate"])

    if leakage_dir is not None:
        m2, cells2, by2 = load(leakage_dir)
        lm_by_preset = {}
        for c in cells2:
            vals = list(event_lm(collect_events(by2[c["cell_id"]], corpus)).values())
            lm_by_preset[c.get("preset", c["label"])] = float(np.mean(vals)) if vals else math.nan
        common = [p for p in points if p in lm_by_preset]
        if common:
            plt = _plt()
            fig, ax = plt.subplots(figsize=(5, 3.6))
            for i, p in enumerate(common):
                ax.scatter(points[p], lm_by_preset[p], s=60, color=SERIES[i % len(SERIES)], zorder=3)
                ax.annotate(p, (points[p], lm_by_preset[p]), xytext=(6, 4), textcoords="offset points",
                            color=INK, fontsize=8)
            _style(ax, "Security vs cost", "p50 latency (ms)", "leakage magnitude after revocation")
            fig.savefig(out / "rq5_pareto.png")
            plt.close(fig)
            text += "\n\nFigure: rq5_pareto.png\n"
    return text + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--reference", help="cell label used as the baseline for paired tests")
    ap.add_argument("--train-tenants", nargs="*", help="shadow tenants for the learned attacker")
    ap.add_argument("--leakage", type=Path, help="revocation run dir to join for the RQ5 Pareto plot")
    ap.add_argument("--judge", choices=["exact", "llm"], default="exact",
                    help="llm: also count paraphrased facts, judged by --judge-backend (cached on disk)")
    ap.add_argument("--judge-backend", default="groq")
    args = ap.parse_args()
    judge = None
    if args.judge == "llm":
        import random
        from src.secure_pipeline.clock import SimClock
        from src.secure_pipeline.llm_client import LLMClient
        judge = LLMJudge(LLMClient(args.judge_backend, SimClock(), random.Random(0)))

    manifest, cells, by_cell = load(args.run_dir)
    out = args.run_dir / "analysis"
    out.mkdir(exist_ok=True)
    corpus = load_corpus()
    kind = manifest["experiment"]
    if kind == "revocation":
        text = analyze_revocation(manifest, cells, by_cell, corpus, out, args.reference, judge)
    elif kind == "existence":
        text = analyze_existence(manifest, cells, by_cell, out, args.train_tenants)
    elif kind == "utility":
        text = analyze_utility(manifest, cells, by_cell, out, args.leakage, corpus)
    else:
        raise ValueError(kind)
    header = f"# {manifest['name']}\n\nseeds: {manifest['seeds']}\n\n"
    (out / "summary.md").write_text(header + text, encoding="utf-8")
    print(header + text)


if __name__ == "__main__":
    main()
