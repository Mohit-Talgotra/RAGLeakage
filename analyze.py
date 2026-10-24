#!/usr/bin/env python3
"""
analyze.py -- Turn run.py JSONL logs into the paper's tables and figures.

    python analyze.py results/rq2_revocation_window
    python analyze.py results/rq3_existence --train-tenants t1 t2 t3
    python analyze.py results/rq5_utility --leakage results/rq5_leakage

Writes <dir>/analysis/summary.md, one CSV per table, and PNG figures.

revocation : per-event LM (secrets disclosed after revocation), split into LM_new (secrets the
             victim was never shown before revocation) and LM_re (re-disclosure); LM_update
             (secrets of the post-revocation version of the document); canary-only leak rate;
             per-probe leak probability; LM from probes at >= 1 h and >= 24 h; per-surface LM
             (cache / stale index / memory, attributed from ground truth), leakage lifetime
             survival (Kaplan-Meier median + bootstrap CI), analytic sync prediction, share of
             secrets that survive into summaries, taint-set size and authorization decisions per
             query, paired differences against a reference cell (target-clustered CI, Wilcoxon on
             per-target differences, Holm-adjusted p).
             Secrets are judged with --judge-mode unique (default: corpus-unique values + canary).
existence  : learned black-box attacker (logistic regression and gradient boosting)
             trained on shadow tenants, tested on held-out tenants; AUC [95% CI clustered by
             target], TPR@1%FPR and balanced accuracy per channel x exposure profile x attacker
             (insider and outsider reported separately), and the same split by whether the target
             has a project sibling (existence_strata.csv).
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
from src.secure_pipeline.corpus import corpus_dir, load_corpus, seeded_corpus
from src.secure_pipeline.instrumentation import read_rows
from src.secure_pipeline.judge import LLMJudge, disclosed
from src.secure_pipeline.metrics import (auc_ci, auc_ci_cluster, bootstrap_ci, cluster_ci, eia_metrics, fast_auc,
                                         fmt_ci, holm, kaplan_meier, km_median_ci, leak_lifetime, ndcg_at_k,
                                         paired_test, fmt_p, percentile, recall_at_k)

JUDGE_MODE = "unique"
TARGET_KINDS = ("same_session", "new_session", "new_session_unseen")

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


# Paper labels for raw config keys. Unknown keys fall back to "key: value".
SYNC_LABELS = {"periodic:3600": "Hourly crawl", "periodic:86400": "Daily crawl", "event:0.0": "Event-driven",
               "event:0.05:86400": "Event-driven, 5% loss", "live": "Live ACLs"}
VALUE_LABELS = {
    "preset": {"strawman": "Strawman", "baseline": "Baseline", "baseline_shared": "Baseline, shared cache",
               "legacy": "Legacy", "full": "Full defense", "full_fine": "Full, sentence taint",
               "epoch": "Epoch invalidation", "flush": "Session flush",
               "authz_postfilter": "Live post-filter", "authz_prefilter": "Live pre-filter"},
    "open_surface": {"none": "None re-opened", "index": "Index re-opened", "cache": "Cache re-opened",
                     "memory": "Memory re-opened"},
    "revocation_type": {"single_doc": "single doc", "role": "role", "user_offboard": "offboarding",
                        "mover": "mover"},
    "acl_prefilter": {"True": "pre-filter", "False": "post-filter"},
    "variant": {"as_is": "as is", "fast_refusal": "fast refusal", "pad30": "30 ms floor", "deadline2s": "2 s deadline"},
}
MODEL_LABELS = {"qwen2.5:3b": "Qwen2.5-3B", "qwen2.5:7b": "Qwen2.5-7B", "llama3.1:8b": "Llama-3.1-8B",
                "qwen2.5:32b": "Qwen2.5-32B", "llama3.3:70b": "Llama-3.3-70B",
                "openai/gpt-oss-120b": "GPT-OSS-120B", "gpt-4o-mini": "GPT-4o-mini"}


def pretty(label: str, cell: dict | None = None) -> str:
    parts = []
    for kv in label.split(","):
        k, _, v = kv.partition("=")
        if k == "sync":
            parts.append(SYNC_LABELS.get(v, v))
        elif k == "cache_ttl_s":
            parts.append(f"TTL {float(v):,.0f} s")
        elif k == "cache_threshold":
            parts.append(f"threshold {v}")
        elif k == "llm_backend":
            parts.append("Stub LLM" if v == "stub" else MODEL_LABELS.get((cell or {}).get("llm_model", ""), v))
        elif k == "ablate":
            parts.append("Full defense" if v == "none" else f"without {v}")
        elif k == "llm_model":
            parts.append(MODEL_LABELS.get(v, v))
        elif k == "taint_user_input":
            parts.append("paste fingerprint" if v == "True" else "no fingerprint")
        elif k == "iam_rpc_ms":
            parts.append(f"IAM {v} ms")
        elif k in VALUE_LABELS:
            parts.append(VALUE_LABELS[k].get(v, v))
        else:
            parts.append(f"{k}: {v}" if v else k)
    return ", ".join(parts)


def _save(fig, out: Path, stem: str) -> None:
    fig.savefig(out / f"{stem}.png")
    fig.savefig(out / f"{stem}.pdf")


def _style(ax, title: str, xlabel: str, ylabel: str) -> None:
    if title:  # panel labels only; figures carry no in-image title (the caption does that)
        ax.set_title(title, loc="left", fontsize=9, color=INK)
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
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                         "mathtext.fontset": "stix", "font.size": 9, "figure.dpi": 150,
                         "savefig.bbox": "tight", "pdf.fonttype": 42, "ps.fonttype": 42})
    return plt


# ---- Revocation (RQ1, RQ2, RQ4) ------------------------------------------------------

def surface_of(truth: dict, target: str) -> str:
    if truth["cache_hit"]:
        return "cache"
    if target in truth["stale_docs_used"]:
        return "index"
    # Only a response whose prompt held memory can have leaked through memory.
    return "memory" if truth.get("memory_turns", 1) else "other"


_LOADED: dict[str, object] = {}


class Corpora:
    """Corpus per seed: one shared corpus, or one per seed for 'synthetic_v3@seed' runs."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, seed: int):
        key = seeded_corpus(self.name, seed)
        if key not in _LOADED:
            _LOADED[key] = load_corpus(corpus_dir(key))
        return _LOADED[key]


def corpora_for(cell: dict) -> Corpora:
    """Grids may vary the corpus (synthetic_v3@seed vs enron_c), so resolve it per cell."""
    return Corpora(cell.get("corpus", "synthetic"))


def _got(d) -> set:
    return set(d.facts) | ({"<canary>"} if d.canary else set())


def collect_events(rows: list[dict], corpora, judge: LLMJudge | None = None) -> dict[tuple, dict]:
    """Group post-revocation probes by (seed, event) and record which target secrets leaked,
    through which surface, and whether anything leaked at each probe time. Separately, count
    the secrets of every warmed doc the victim lost (lost_docs), over all probes.
    corpora: a Corpus or a seed -> Corpus callable (Corpora)."""
    corpus_of = corpora if callable(corpora) else (lambda _seed: corpora)
    events: dict[tuple, dict] = {}
    warm: dict[tuple, dict[str, set]] = defaultdict(dict)   # (seed, event, who) -> doc -> secrets told at warm-up
    laundered: dict[tuple, bool] = {}
    summaries: dict[tuple, list[str]] = defaultdict(list)
    for r in rows:
        g, t = r["tags"], r["truth"]
        if "event" not in g:
            continue
        corpus = corpus_of(g["seed"])
        key = (g["seed"], g["event"])
        if g.get("who", "victim") == "victim" and g.get("phase") != "holder":
            summaries[key] += t.get("summaries_written", [])
        warm_doc = g.get("warm_doc")
        if warm_doc is None and g.get("phase") == "warm" and g.get("target"):
            # Older logs carry no warm_doc tag; the target's own warm-up questions are its QA questions.
            if t["query"] in {x["question"] for x in corpus.doc(g["target"])["qa"]}:
                warm_doc = g["target"]
        who = g.get("who", "victim")
        if g.get("phase") == "warm" and warm_doc:
            d = disclosed(corpus, warm_doc, t["response"], [], mode=JUDGE_MODE)
            warm[(*key, who)].setdefault(warm_doc, set()).update(_got(d))
        if g.get("phase") == "launder" and g.get("launder_final"):
            # The revoked victim's own answer after pasting: did the laundering work at all?
            d = disclosed(corpus, g["target"], t["response"], t["source_docs"], judge, mode=JUDGE_MODE)
            laundered[key] = bool(d.facts) or d.canary
        if g.get("phase") != "probe":
            continue
        ev = events.setdefault(key, {
            "target": g["target"], "secrets": set(), "by_surface": defaultdict(set),
            "times": defaultdict(bool), "index_times": defaultdict(bool), "secrets_at": defaultdict(set),
            "n_secrets": len(corpus.secrets(g["target"], scorable=True)), "lost": set(),
            "n_lost": sum(len(corpus.secrets(x, scorable=True)) for x in g.get("lost_docs", [])),
            "retained": defaultdict(list), "colleague": set(), "probes": 0, "leaky_probes": 0,
            "told": warm[(*key, "victim")].get(g["target"], set()), "has_canary": bool(corpus.doc(g["target"]).get("canary")),
            "updated": list(g.get("updated_secrets") or []), "updated_got": set(),
            "summaries": summaries[key], "taint_sizes": [], "authz_decisions": [],
            "gap": g.get("revoke_gap_s"), "laundered": laundered.get(key)})
        ev["taint_sizes"].append(len(t.get("response_taint", [])))
        ev["authz_decisions"].append(t.get("authz_decisions", 0))
        kind = g.get("probe_kind")
        if kind in ("retained_same", "retained_new", "bystander_retained"):
            # Collateral: share of what the victim (or the bystander) was told about a doc they still may read.
            told = warm[(*key, who)].get(g["probe_doc"], set()) - {"<canary>"}
            if told:
                got = set(disclosed(corpus, g["probe_doc"], t["response"], [], mode=JUDGE_MODE).facts)
                ev["retained"][kind].append(len(got & told) / len(told))
                ev["retained"][kind + "_refused"].append(float(t["refused"]))
            continue
        if kind == "colleague":
            d = disclosed(corpus, g["target"], t["response"], t["source_docs"], judge, mode=JUDGE_MODE)
            ev["colleague"] |= _got(d)
            continue
        for doc in g.get("lost_docs", []):
            dd = disclosed(corpus, doc, t["response"], t["source_docs"], judge, mode=JUDGE_MODE)
            ev["lost"] |= {(doc, v) for v in _got(dd)}
        if g.get("probe_doc", g["target"]) != g["target"] or kind not in TARGET_KINDS:
            continue  # probes about other lost docs feed only the blast-radius count above
        got = _got(disclosed(corpus, g["target"], t["response"], t["source_docs"], judge, mode=JUDGE_MODE))
        ev["updated_got"] |= {v for v in ev["updated"] if v in t["response"]}
        ev["probes"] += 1
        ev["leaky_probes"] += bool(got)
        ev["times"][g["probe_t"]] |= bool(got)
        ev["index_times"][g["probe_t"]] |= bool(got) and surface_of(t, g["target"]) == "index"
        if got:
            ev["secrets"] |= got
            ev["secrets_at"][g["probe_t"]] |= got
            ev["by_surface"][surface_of(t, g["target"])] |= got
    return {k: e for k, e in events.items() if e["n_secrets"]}


def event_lm(events: dict[tuple, dict]) -> dict[tuple, float]:
    return {k: len(e["secrets"]) / e["n_secrets"] for k, e in events.items()}


def _summary_retention(e: dict, corpus) -> float | None:
    """Share of the target's scorable secrets present in any summary written during the event."""
    if not e["summaries"]:
        return None
    secrets = corpus.secrets(e["target"], scorable=True)
    blob = "\n".join(e["summaries"])
    return sum(v in blob for v in secrets) / len(secrets)


def analyze_revocation(manifest, cells, by_cell, out: Path, reference: str | None,
                       judge: LLMJudge | None = None) -> str:
    table, events_by_cell, targets_by_cell, curves, event_rows = [], {}, {}, {}, []
    for cell in cells:
        corpus_of = corpora_for(cell)
        events = collect_events(by_cell[cell["cell_id"]], corpus_of, judge)
        lm = event_lm(events)
        # A doc id names a different document in each seed's corpus when corpora are per seed.
        per_seed = str(cell.get("corpus", "")).endswith("@seed")
        tkey = (lambda k, e: (k[0], e["target"])) if per_seed else (lambda k, e: e["target"])
        targets = [tkey(k, e) for k, e in events.items()]
        targets_by_cell[cell["cell_id"]] = {k: tkey(k, e) for k, e in events.items()}
        lm_new = [len(e["secrets"] - e["told"]) / e["n_secrets"] for e in events.values()]
        lm_re = [len(e["secrets"] & e["told"]) / e["n_secrets"] for e in events.values()]
        told = [len(e["told"]) / e["n_secrets"] for e in events.values()]
        lm_1h = [len(set().union(*[v for t_, v in e["secrets_at"].items() if t_ >= 3600])) / e["n_secrets"]
                 for e in events.values()]
        lm_24h = [len(set().union(*[v for t_, v in e["secrets_at"].items() if t_ >= 86400])) / e["n_secrets"]
                  for e in events.values()]
        canary_rate = [float("<canary>" in e["secrets"]) for e in events.values() if e["has_canary"]]
        probe_rate = [e["leaky_probes"] / e["probes"] for e in events.values() if e["probes"]]
        upd = [len(e["updated_got"]) / len(e["updated"]) for e in events.values() if e["updated"]]
        retention = [x for e_key, e in events.items()
                     if (x := _summary_retention(e, corpus_of(e_key[0]))) is not None]
        taint_sizes = [x for e in events.values() for x in e["taint_sizes"]]
        decisions = [x for e in events.values() for x in e["authz_decisions"]]
        lm_s = {s: [len(e["by_surface"][s]) / e["n_secrets"] for e in events.values()] for s in SURFACE_COLORS}
        lm_lost = [len(e["lost"]) / e["n_lost"] for e in events.values() if e["n_lost"]]
        n_lost_docs = [len({doc for doc, _ in e["lost"]}) for e in events.values() if e["n_lost"]]
        life = [leak_lifetime(list(e["times"]), list(e["times"].values())) for e in events.values()]
        dur, obs = [x[0] for x in life], [x[1] for x in life]
        life_by_key = dict(zip(events, life))
        med = km_median_ci(dur, obs)
        leaking = [(d_, o_) for d_, o_, lk in zip(dur, obs, lm.values()) if lk > 0]
        med_leaking = km_median_ci([x[0] for x in leaking], [x[1] for x in leaking])
        # Index-only lifetime, for the analytic sync check. A probe answered from the cache never
        # reaches the index, so this is only clean where cache_ttl_s is short next to the sync period.
        idx = [leak_lifetime(list(e["index_times"]), list(e["index_times"].values())) for e in events.values()
               if any(e["index_times"].values())]
        med_index = km_median_ci([x[0] for x in idx], [x[1] for x in idx]) if idx else None
        parts = str(cell.get("sync", "live")).split(":")
        sync_period = float(parts[1]) if parts[0] == "periodic" else float(parts[2]) if len(parts) > 2 else None
        index_masked = sync_period is not None and float(cell.get("cache_ttl_s", 3600.0)) >= sync_period
        events_by_cell[cell["cell_id"]] = lm
        horizon = max((t for e in events.values() for t in e["times"]), default=0.0)
        curves[cell["label"]] = (*kaplan_meier(dur, obs), horizon)
        sync = cell.get("sync", "live")
        analytic = ""
        if str(sync).startswith("periodic:"):
            analytic = f"{float(str(sync).split(':')[1]) / 2:g}"
        def ev_mean(key):
            vals = [float(np.mean(e["retained"][key])) for e in events.values() if e["retained"][key]]
            return fmt_ci(*bootstrap_ci(vals)) if vals else "n/a"
        coll = [len(e["colleague"]) / e["n_secrets"] for e in events.values()]
        coll_rate = [float(bool(e["colleague"])) for e in events.values()]
        has_coll = any(r["tags"].get("probe_kind") == "colleague" for r in by_cell[cell["cell_id"]])
        for e_key, e in events.items():
            event_rows.append({"cell": cell["label"], "seed": e_key[0], "event": e_key[1], "target": e["target"],
                               "LM": round(lm[e_key], 4),
                               "LM_all_lost": round(len(e["lost"]) / e["n_lost"], 4) if e["n_lost"] else "",
                               "lifetime_s": life_by_key[e_key][0], "censored": not life_by_key[e_key][1]})
        def cci(vals):
            return fmt_ci(*cluster_ci(vals, targets)) if len(vals) == len(targets) and vals else "n/a"
        table.append({
            "cell": cell["label"], "events": len(events), "targets": len(set(targets)),
            "LM": cci(list(lm.values())),
            "LM_new": cci(lm_new), "LM_re": cci(lm_re), "told_at_warmup": f"{np.mean(told):.3f}",
            "LM_from_1h": cci(lm_1h), "LM_from_24h": cci(lm_24h),
            "LM_update": fmt_ci(*bootstrap_ci(upd)) if upd else "n/a",
            "canary_leak_rate": f"{np.mean(canary_rate):.3f}" if canary_rate else "n/a",
            "probe_leak_prob": f"{np.mean(probe_rate):.3f}" if probe_rate else "n/a",
            "LM_cache": cci(lm_s["cache"]),
            "LM_index": cci(lm_s["index"]),
            "LM_memory": cci(lm_s["memory"]),
            "leak_rate": f"{np.mean([v > 0 for v in lm.values()]):.3f}",
            "summary_retains": f"{np.mean(retention):.3f}" if retention else "n/a",
            "taint_size_mean": f"{np.mean(taint_sizes):.2f}" if taint_sizes else "n/a",
            "taint_size_p95": f"{percentile(taint_sizes, 95):.0f}" if taint_sizes else "n/a",
            "authz_decisions_per_query": f"{np.mean(decisions):.2f}" if decisions else "n/a",
            "LM_all_lost": fmt_ci(*bootstrap_ci(lm_lost)) if lm_lost else "n/a",
            "lost_docs_leaked_mean": f"{np.mean(n_lost_docs):.2f}" if n_lost_docs else "n/a",
            "LH_median_s": fmt_ci(*med, digits=0),
            "LH_median_leaking_s": fmt_ci(*med_leaking, digits=0),
            "censored": f"{sum(not o for o in obs)}/{len(obs)}",
            "LH_index_median_leaking_s": ("masked by cache" if index_masked else
                                          fmt_ci(*med_index, digits=0) if med_index else "n/a"),
            "analytic_index_staleness_mean_s": analytic,
            "retained_recall_same": ev_mean("retained_same"),
            "retained_recall_new": ev_mean("retained_new"),
            "bystander_recall": ev_mean("bystander_retained"),
            "bystander_refusal": ev_mean("bystander_retained_refused"),
            "retained_refusal_same": ev_mean("retained_same_refused"),
            "LM_colleague": fmt_ci(*bootstrap_ci(coll)) if has_coll else "n/a",
            "colleague_event_rate": f"{np.mean(coll_rate):.3f}" if has_coll else "n/a",
            "launder_success": (f"{np.mean([bool(e['laundered']) for e in events.values()]):.3f}" if has_coll
                                else "n/a"),
            "_lm_surface_means": {s: float(np.mean(v)) if v else 0.0 for s, v in lm_s.items()},
        })

    ref = next((c for c in cells if c["label"] == reference), cells[0]) if cells else None
    paired = []
    for cell in cells:
        if ref is None or cell is ref:
            continue
        a, b = events_by_cell[cell["cell_id"]], events_by_cell[ref["cell_id"]]
        keys = sorted(set(a) & set(b))
        tgt = targets_by_cell[cell["cell_id"]]
        res = paired_test([a[k] for k in keys], [b[k] for k in keys], [tgt[k] for k in keys])
        paired.append({"cell": cell["label"], "vs": ref["label"], "delta_LM": fmt_ci(res["diff"], res["lo"], res["hi"]),
                       "CI_cluster": f"[{res['lo_cluster']:.3f}, {res['hi_cluster']:.3f}]",
                       "p": fmt_p(res["p"]), "p_wilcoxon": res["p_wilcoxon"], "pairs": res["n"],
                       "targets": res.get("clusters", "")})
    if paired:
        for row, adj in zip(paired, holm([r["p_wilcoxon"] for r in paired])):
            row["p_holm"] = fmt_p(adj, None)
            row["p_wilcoxon"] = fmt_p(row["p_wilcoxon"], None)

    surface_means = {r["cell"]: r.pop("_lm_surface_means") for r in table}
    write_csv(out / "revocation_summary.csv", table)
    write_csv(out / "revocation_paired.csv", paired)
    write_csv(out / "revocation_events.csv", event_rows)

    plt = _plt()
    cell_by_label = {c["label"]: c for c in cells}
    # Up to len(SERIES) curves share one panel. Beyond that, facet by the first grid key so no
    # color repeats: one panel per value of the first key, one color per remaining key.
    if len(curves) <= len(SERIES):
        panels = {"": list(curves)}
    else:
        panels = defaultdict(list)
        for label in curves:
            panels[label.split(",")[0]].append(label)
    rests = list(dict.fromkeys(",".join(l.split(",")[1:]) or l for ls in panels.values() for l in ls))
    fig, axes = plt.subplots(1, len(panels), figsize=(max(6.4, 3.2 * len(panels)), 3.6), squeeze=False,
                             sharey=True)
    dashes = ["-", "--", ":", "-."]
    for ax, (title, labels_) in zip(axes[0], panels.items()):
        for label in labels_:
            times, surv, horizon = curves[label]
            rest = (",".join(label.split(",")[1:]) or label) if title else label
            i = rests.index(rest) if title else labels_.index(label)
            # Extend the last step to the probe horizon so censored (still leaking) events stay visible.
            # Earlier series sit on top with their own dash, so identical curves stay visible.
            hours = np.append(np.asarray(times), max(horizon, times[-1])) / 3600.0
            ax.step(hours, np.append(surv, surv[-1]), where="post", color=SERIES[i % len(SERIES)],
                    linewidth=1.6, linestyle=dashes[i % len(dashes)], zorder=10 - i,
                    label=pretty(rest, cell_by_label.get(label)))
        _style(ax, pretty(title) if title else "", "hours since revocation",
               "share of events still leaking" if ax is axes[0][0] else "")
        ax.set_ylim(-0.02, 1.02)
    axes[0][-1].legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    _save(fig, out, "rq2_survival")
    plt.close(fig)

    labels = list(surface_means)
    fig, ax = plt.subplots(figsize=(6.4, 0.9 + 0.75 * max(1, len(labels))))
    y = np.arange(len(labels))
    left = np.zeros(len(labels))
    for surf, color in SURFACE_COLORS.items():
        # Stacked: a secret can leak through several artifacts, so the total can exceed LM.
        vals = np.array([surface_means[l][surf] for l in labels])
        ax.barh(y, vals, left=left, height=0.6, color=color, edgecolor="white", linewidth=1, label=surf)
        left += vals
    ax.set_yticks(y, [pretty(l, cell_by_label.get(l)) for l in labels])
    ax.invert_yaxis()
    ax.set_xlim(0, max(1.0, float(left.max())))
    _style(ax, "", "mean leakage magnitude per event", "")
    ax.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=INK)
    _save(fig, out, "rq1_surfaces")
    plt.close(fig)

    cols = ["cell", "events", "targets", "LM", "LM_new", "LM_re", "told_at_warmup", "LM_from_1h", "LM_from_24h",
            "canary_leak_rate", "probe_leak_prob", "LM_cache", "LM_index", "LM_memory", "leak_rate", "LM_all_lost",
            "lost_docs_leaked_mean", "LH_median_s",
            "LH_median_leaking_s", "censored", "LH_index_median_leaking_s",
            "analytic_index_staleness_mean_s"]
    cols += [c for c in ("LM_update", "summary_retains", "taint_size_mean", "taint_size_p95",
                         "authz_decisions_per_query", "retained_recall_same", "retained_recall_new",
                         "bystander_recall", "bystander_refusal",
                         "retained_refusal_same", "LM_colleague", "colleague_event_rate", "launder_success")
             if any(r[c] != "n/a" for r in table)]
    text = "## Revocation window\n\n" + md_table(table, cols)
    if paired:
        text += "\n\nPaired difference in event LM (same seeds and events):\n\n" + md_table(
            paired, ["cell", "vs", "delta_LM", "CI_cluster", "p", "p_wilcoxon", "p_holm", "pairs", "targets"])
        text += ("\n\nCI: event-level bootstrap; CI_cluster: bootstrap over target documents. "
                 "p: bootstrap (resolution 1/2000); p_wilcoxon: Wilcoxon signed-rank on per-target mean "
                 "differences, zero differences dropped; p_holm: Holm-adjusted over this table.")
    text += ("\n\nLM, LM_new, LM_re and per-surface intervals are clustered by target document. "
             f"Judge mode: {JUDGE_MODE}.")
    text += "\n\nFigures: rq2_survival.png, rq1_surfaces.png\n"
    return text


# ---- Existence inference (RQ3) --------------------------------------------------------

def _has_sibling(corpus, doc_id: str) -> bool:
    project = corpus.doc(doc_id).get("project")
    return bool(project) and sum(d.get("project") == project for d in corpus.restricted()) > 1


def analyze_existence(manifest, cells, by_cell, out: Path, train_tenants: list[str] | None) -> str:
    profiles = ("text_only", "with_sources", "with_reranker")
    table, roc_data, score_rows, bucket_rows, strata_rows = [], {}, [], [], []
    for cell in cells:
        corpora = corpora_for(cell)
        probes = [r for r in by_cell[cell["cell_id"]] if r["tags"].get("phase") == "probe"]
        if any(r["truth"]["pad_ms"] > 0 for r in probes) and cell.get("pad_strategy", "bucket") == "bucket":
            # Residual timing signal of bucket padding: a response slower than one bucket lands in
            # the next one. Share of probes per bucket and world, and the AUC of the bucket alone.
            size = float(cell.get("pad_ms", 500.0))
            b = np.array([math.ceil(round(r["obs"]["latency_ms"]) / size - 1e-9) for r in probes])
            w = np.array([r["tags"]["world"] for r in probes])
            row = {"cell": cell["label"], "bucket_ms": size, "AUC_bucket_only": f"{fast_auc(w, b):.3f}"}
            for world in (1, 0):
                for k in (1, 2):
                    row[f"world{world}_bucket{k}"] = f"{np.mean(b[w == world] == k):.3f}"
                row[f"world{world}_bucket3+"] = f"{np.mean(b[w == world] >= 3):.3f}"
            bucket_rows.append(row)
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
                # CI clusters: the target document (it recurs across seeds, worlds and probes).
                per_seed = str(cell.get("corpus", "")).endswith("@seed")
                clusters = [(r["tags"]["seed"], r["tags"]["target"]) if per_seed else r["tags"]["target"]
                            for r, m in zip(rows, tr) if not m]
                sibling = np.array([bool(r["tags"]["has_sibling"]) if "has_sibling" in r["tags"] else
                                    _has_sibling(corpora(r["tags"]["seed"]), r["tags"]["target"])
                                    for r, m in zip(rows, tr) if not m])
                thr = np.array([ThresholdAttacker().score(f) for f in f_te])
                base = {"cell": cell["label"], "attacker": attacker, "profile": profile, "n_test": len(y_te)}
                table.append({**base, "model": "threshold", "channel": "rules",
                              **_eia_cols(y_te, thr, trial, clusters)})
                for model in ("logreg", "gboost"):
                    scores = LearnedAttacker(model).fit(f_tr, y_tr).scores(f_te)
                    for ch in list(CHANNELS) + ["combined"]:
                        table.append({**base, "model": model, "channel": ch,
                                      **_eia_cols(y_te, scores[ch], trial, clusters)})
                    if model == "gboost":
                        for name, mask in (("sibling", sibling), ("singleton", ~sibling)):
                            if mask.any() and len(set(y_te[mask])) == 2:
                                idx = np.where(mask)[0]
                                strata_rows.append({**base, "stratum": name, "n_test": int(mask.sum()),
                                                    "targets": len({clusters[i] for i in idx}),
                                                    **_eia_cols(y_te[mask], scores["combined"][mask],
                                                                [trial[i] for i in idx], [clusters[i] for i in idx])})
                        if model == "gboost" and profile == "with_reranker" and attacker == "all":
                            roc_data.setdefault(cell["label"], {})[ch] = (y_te, scores[ch])
                    if model == "gboost" and profile == "with_reranker" and attacker == "all":
                        test_rows = [r for r, m in zip(rows, tr) if not m]
                        for i, r in enumerate(test_rows):
                            g = r["tags"]
                            score_rows.append({"cell": cell["label"], "seed": g["seed"], "target": g["target"],
                                               "attacker": g["attacker"], "world": g["world"],
                                               "strategy": g["strategy"],
                                               **{f"score_{ch}": round(float(scores[ch][i]), 5)
                                                  for ch in list(CHANNELS) + ["combined"]}})
    write_csv(out / "existence_eia.csv", table)
    write_csv(out / "probe_scores.csv", score_rows)
    write_csv(out / "pad_buckets.csv", bucket_rows)
    write_csv(out / "existence_strata.csv", strata_rows)

    plt = _plt()
    from sklearn.metrics import roc_curve
    figures = []
    if any(c.get("ablate") for c in cells):
        # RQ4: combined-attacker AUC per ablated switch (rows) and per remaining setting (columns).
        def rest_of(label: str) -> str:
            return ",".join(p for p in label.split(",") if not p.startswith("ablate=")) or "-"
        rows_ = list(dict.fromkeys(c.get("ablate", "none") for c in cells))
        cols_ = list(dict.fromkeys(rest_of(c["label"]) for c in cells))
        grid = np.full((len(rows_), len(cols_)), np.nan)
        for c in cells:
            if c["label"] in roc_data and "combined" in roc_data[c["label"]]:
                y, sc = roc_data[c["label"]]["combined"]
                grid[rows_.index(c.get("ablate", "none")), cols_.index(rest_of(c["label"]))] = fast_auc(y, sc)
        fig, ax = plt.subplots(figsize=(1.2 + 0.9 * len(cols_), 0.8 + 0.45 * len(rows_)))
        ax.imshow(grid, cmap="Blues", vmin=0.5, vmax=1.0, aspect="auto")
        for i in range(len(rows_)):
            for j in range(len(cols_)):
                if not np.isnan(grid[i, j]):
                    ax.text(j, i, f"{grid[i, j]:.2f}", ha="center", va="center", fontsize=7,
                            color="white" if grid[i, j] > 0.8 else INK)
        ax.set_xticks(range(len(cols_)), [pretty(c).replace(", ", "\n") for c in cols_], fontsize=7)
        ax.set_yticks(range(len(rows_)), [f"without {r}" if r != "none" else "full defense" for r in rows_])
        for side in ax.spines.values():
            side.set_visible(False)
        _save(fig, out, "rq4_ablation_heatmap")
        plt.close(fig)
        figures.append("rq4_ablation_heatmap.png")
    if roc_data and len(roc_data) <= 6:
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
            _style(ax, pretty(label, next((c for c in cells if c["label"] == label), None)),
                   "false positive rate", "true positive rate" if ax is axes[0][0] else "")
        axes[0][0].legend(frameon=False, fontsize=7, labelcolor=INK)
        _save(fig, out, "rq3_roc")
        plt.close(fig)
        figures.append("rq3_roc.png")

    key = [r for r in table if r["model"] in ("gboost", "threshold")
           and r["channel"] in ("combined", "rules", "latency", "refusal", "score", "content")]
    text = "## Existence inference (twin worlds, held-out tenants)\n\n" + md_table(
        key, ["cell", "attacker", "profile", "model", "channel", "AUC", "AUC_trial", "TPR@1%FPR", "balanced_acc",
              "n_test"])
    text += "\n\nAUC intervals resample target documents (clustered ROC). Insider and outsider are separate rows."
    if strata_rows:
        text += "\n\nBy whether the target has a project sibling (gboost, combined):\n\n" + md_table(
            strata_rows, ["cell", "attacker", "profile", "stratum", "AUC", "AUC_trial", "TPR@1%FPR", "n_test", "targets"])
    if bucket_rows:
        text += "\n\nLatency padding buckets (share of probes per bucket, by world):\n\n" + md_table(
            bucket_rows, list(bucket_rows[0]))
    text += ("\n\nFull table: existence_eia.csv (per-probe gboost scores: probe_scores.csv). Figures (gboost, with_reranker, all attackers): "
             + ", ".join(figures) + "\n")
    return text


def _eia_cols(y, s, trial_keys, clusters=None) -> dict:
    """Per-probe metrics, plus trial-level AUC where the attacker averages its four probe scores.
    With clusters (target ids), intervals resample targets instead of probes or trials."""
    s = np.asarray(s)
    m = eia_metrics(y, s)
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, k in enumerate(trial_keys):
        groups[k].append(i)
    ty = np.array([y[idx[0]] for idx in groups.values()])
    ts = np.array([s[idx].mean() for idx in groups.values()])
    if clusters is None:
        return {"AUC": fmt_ci(*auc_ci(y, s)), "AUC_trial": fmt_ci(*auc_ci(ty, ts)),
                "TPR@1%FPR": f"{m['tpr_at_1fpr']:.3f}", "balanced_acc": f"{m['balanced_acc']:.3f}"}
    tc = [clusters[idx[0]] for idx in groups.values()]
    return {"AUC": fmt_ci(*auc_ci_cluster(y, s, clusters)), "AUC_trial": fmt_ci(*auc_ci_cluster(ty, ts, tc)),
            "AUC_probe_iid": fmt_ci(*auc_ci(y, s)),
            "TPR@1%FPR": f"{m['tpr_at_1fpr']:.3f}", "balanced_acc": f"{m['balanced_acc']:.3f}"}


# ---- Utility (RQ5) ------------------------------------------------------------------

def analyze_utility(manifest, cells, by_cell, out: Path, leakage_dir: Path | None) -> str:
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
            "authz_calls": f"{np.mean([r['truth'].get('authz_calls', 0) for r in rows]):.2f}",
            "authz_decisions": f"{np.mean([r['truth'].get('authz_decisions', 0) for r in rows]):.2f}",
        })
        points[cell.get("preset", cell["label"])] = percentile(lat, 50)
    write_csv(out / "utility_summary.csv", table)
    text = "## Utility and cost\n\n" + md_table(
        table, ["cell", "queries", "Recall@k", "nDCG@k", "correct", "over_refusal", "p50_ms", "p95_ms",
                "cache_hit_rate", "authz_calls", "authz_decisions"])

    if leakage_dir is not None:
        m2, cells2, by2 = load(leakage_dir)
        lm_by_preset = {}
        for c in cells2:
            key = c.get("preset", c["label"])
            if key in lm_by_preset:
                raise ValueError(f"--leakage run has several cells with preset {key!r}; "
                                 "use a run whose grid varies preset only (configs/rq5_leakage.yaml)")
            vals = list(event_lm(collect_events(by2[c["cell_id"]], corpora_for(c))).values())
            lm_by_preset[key] = float(np.mean(vals)) if vals else math.nan
        common = [p for p in points if p in lm_by_preset]
        if common:
            plt = _plt()
            fig, ax = plt.subplots(figsize=(5, 3.6))
            for i, p in enumerate(common):
                ax.scatter(points[p], lm_by_preset[p], s=60, color=SERIES[i % len(SERIES)], zorder=3)
                # Alternate above/below so neighbouring presets' labels don't collide.
                ax.annotate(pretty(f"preset={p}"), (points[p], lm_by_preset[p]), xytext=(6, 6 if i % 2 == 0 else -12),
                            textcoords="offset points",
                            color=INK, fontsize=8)
            _style(ax, "", "p50 latency (ms)", "leakage magnitude after revocation")
            _save(fig, out, "rq5_pareto")
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
    ap.add_argument("--judge-model", help="model for --judge-backend (default: the backend's default)")
    ap.add_argument("--judge-mode", choices=["unique", "source"], default="unique",
                    help="unique: score only corpus-unique fact values + canary; source: the pre-audit rule")
    args = ap.parse_args()
    global JUDGE_MODE
    JUDGE_MODE = args.judge_mode
    judge = None
    if args.judge == "llm":
        import random
        from src.secure_pipeline.clock import SimClock
        from src.secure_pipeline.llm_client import LLMClient
        judge = LLMJudge(LLMClient(args.judge_backend, SimClock(), random.Random(0), model=args.judge_model))

    manifest, cells, by_cell = load(args.run_dir)
    out = args.run_dir / "analysis"
    out.mkdir(exist_ok=True)
    kind = manifest["experiment"]
    if kind == "revocation":
        text = analyze_revocation(manifest, cells, by_cell, out, args.reference, judge)
    elif kind == "existence":
        text = analyze_existence(manifest, cells, by_cell, out, args.train_tenants)
    elif kind == "utility":
        text = analyze_utility(manifest, cells, by_cell, out, args.leakage)
    else:
        raise ValueError(kind)
    header = f"# {manifest['name']}\n\nseeds: {manifest['seeds']}\n\n"
    (out / "summary.md").write_text(header + text, encoding="utf-8")
    print(header + text)


if __name__ == "__main__":
    main()
