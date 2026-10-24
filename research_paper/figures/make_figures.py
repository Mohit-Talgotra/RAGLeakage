"""Regenerate the paper figures from the analysis CSVs in ../results.
Run from research_paper/:  python3 figures/make_figures.py
Figures 3 and 4 still need per-event / per-probe CSVs from a re-analysis of
rq2_cache_sweep and rq3_existence with the current analyze.py."""
import re
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = "../results/"
D = R + "data/"
COL = 3.45      # IEEE column width (in)
FULL = 7.16     # IEEE text width (in)
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.spines.top": False,
                     "axes.spines.right": False, "axes.linewidth": 0.6, "lines.linewidth": 1.4,
                     "legend.frameon": False, "savefig.bbox": "tight", "savefig.pad_inches": 0.02})
C4 = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a"]
BLUES = ["#9ecae1", "#4292c6", "#08519c"]


def pc(s):
    m = re.match(r"\s*([-\d.]+)\s*\[([-\d.]+),\s*([-\d.]+)\]", str(s))
    return tuple(map(float, m.groups())) if m else (float(s),) * 3


def km(dur, cens):
    """Kaplan-Meier survival of 'still leaking'. Returns step times and survival after each."""
    dur, ev = np.asarray(dur, float), ~np.asarray(cens, bool)
    ts = np.unique(dur[ev])
    s, out_t, out_s = 1.0, [0.0], [1.0]
    for t in ts:
        at_risk = (dur >= t).sum()
        d = ((dur == t) & ev).sum()
        s *= 1 - d / at_risk
        out_t.append(t); out_s.append(s)
    return np.array(out_t), np.array(out_s)


def step(ax, dur, cens, horizon=172800, **kw):
    t, s = km(dur, cens)
    t = np.append(t, horizon) / 3600; s = np.append(s, s[-1])
    ax.step(t, s, where="post", **kw)


def roc(y, s):
    o = np.argsort(-s, kind="mergesort"); y = y[o]; s = s[o]
    tp = np.cumsum(y); fp = np.cumsum(1 - y)
    keep = np.r_[np.diff(s) != 0, True]
    tpr = np.r_[0, tp[keep] / y.sum()]; fpr = np.r_[0, fp[keep] / (1 - y).sum()]
    return fpr, tpr, np.trapezoid(tpr, fpr)


# ---- Fig 1: RQ1 leakage by re-opened artifact
d = pd.read_csv(D + "rq1_surfaces/revocation_summary.csv")
d["surf"] = d.cell.str.extract(r"open_surface=(\w+)"); d["rt"] = d.cell.str.extract(r"revocation_type=(\w+)")
surf = ["none", "index", "cache", "memory"]; lab = ["None\n(full)", "Index\n(stale ACL)", "Semantic\ncache", "Chat\nmemory"]
rts = ["single_doc", "role", "user_offboard"]; rl = ["Single document", "Role", "Offboarding"]
fig, ax = plt.subplots(figsize=(COL, 2.1)); w = 0.26
for j, r in enumerate(rts):
    v = [pc(d[(d.surf == s) & (d.rt == r)].LM.iloc[0]) for s in surf]
    m = np.array([x[0] for x in v])
    ax.bar(np.arange(4) + (j - 1) * w, m, w, yerr=[m - [x[1] for x in v], [x[2] for x in v] - m],
           color=BLUES[j], label=rl[j], capsize=1.2, error_kw={"lw": 0.6})
ax.set_xticks(range(4)); ax.set_xticklabels(lab); ax.set_ylabel("Leakage magnitude (LM)"); ax.set_ylim(0, 0.75)
ax.legend(fontsize=7, loc="upper right", ncol=1)
fig.savefig("figures/fig1_rq1_leakage_by_artifact.pdf"); plt.close(fig)

# ---- Fig 2: RQ2 survival by sync policy x cache TTL (per-event lifetimes)
e = pd.read_csv(R + "rq2_revocation_window/analysis/revocation_events.csv")
e["sync"] = e.cell.str.extract(r"sync=([^,]+)"); e["ttl"] = e.cell.str.extract(r"cache_ttl_s=(\d+)").astype(int)
pols = [("periodic:3600", "Hourly crawl"), ("periodic:86400", "Daily crawl"),
        ("event:0.0", "Event-driven"), ("event:0.05:86400", "Event-driven, 5% lost")]
fig, axs = plt.subplots(1, 4, figsize=(FULL, 1.9), sharey=True)
for ax, (p, title) in zip(axs, pols):
    for ttl, c, ls, z in [(86400, C4[0], "-", 1), (3600, C4[1], "-", 2), (600, C4[2], "--", 3)]:
        x = e[(e.sync == p) & (e.ttl == ttl)]
        step(ax, x.lifetime_s, x.censored, color=c, ls=ls, zorder=z, label=f"TTL {ttl:,} s".replace(",", " "))
    ax.set_title(title, fontsize=8); ax.set_xlabel("Hours since revocation"); ax.set_xticks([0, 12, 24, 36, 48])
    ax.set_ylim(-0.02, 1.02)
axs[0].set_ylabel("Share still leaking"); axs[-1].legend(fontsize=7, loc="upper right")
fig.savefig("figures/fig2_rq2_survival_sync_policies.pdf"); plt.close(fig)

# ---- Fig 5: RQ4 inference ablation heatmap
e = pd.read_csv(D + "rq4_ablation_existence/existence_eia.csv")
e = e[(e.attacker == "all") & (e.profile == "with_reranker") & (e.model == "gboost") & (e.channel == "combined")].copy()
e["pf"] = e.cell.str.extract(r"acl_prefilter=(\w+)"); e["ab"] = e.cell.str.extract(r"ablate=(\w+)"); e["va"] = e.cell.str.extract(r"variant=(\w+)")
abs_ = ["none", "score_quantize", "uniform_refusal", "latency_pad", "cache_lazy_check"]
abl = ["None (full)", "Score quantization", "Uniform refusal", "Latency padding", "Cache lazy check"]
vs = ["as_is", "fast_refusal", "pad30", "deadline2s"]; vl = ["as is", "fast\nrefusal", "30 ms\nfloor", "2 s\ndeadline"]
M = np.array([[pc(e[(e.ab == a) & (e.pf == pf) & (e.va == v)].AUC.iloc[0])[0] for pf in ["True", "False"] for v in vs] for a in abs_])
fig, ax = plt.subplots(figsize=(FULL * 0.8, 2.2))
im = ax.imshow(M, cmap="RdYlBu_r", vmin=0.45, vmax=1, aspect="auto")
for i in range(5):
    for k in range(8):
        ax.text(k, i, f"{M[i, k]:.2f}", ha="center", va="center", fontsize=7, color="white" if M[i, k] > .85 else "black")
ax.set_xticks(range(8)); ax.set_xticklabels(vl * 2, fontsize=7); ax.set_yticks(range(5)); ax.set_yticklabels(abl)
ax.axvline(3.5, color="white", lw=3); ax.spines[:].set_visible(False)
ax.text(1.5, -0.85, "ACL pre-filter on", ha="center", fontsize=8); ax.text(5.5, -0.85, "Post-filter (pre-filter off)", ha="center", fontsize=8)
fig.colorbar(im, ax=ax, label="Existence AUC", fraction=0.03, pad=0.02)
fig.savefig("figures/fig5_rq4_ablation_heatmap.pdf"); plt.close(fig)

# ---- Fig 6: RQ5 leakage vs median latency
u = pd.read_csv(D + "rq5_utility/utility_summary.csv"); l = pd.read_csv(D + "rq5_leakage/revocation_summary.csv")
fig, ax = plt.subplots(figsize=(COL, 2.1))
off = {"strawman": (-2, 9, "center"), "baseline": (0, -13, "center"), "legacy": (9, 6, "left"), "full": (-7, 7, "right")}
for p, c in zip(["strawman", "baseline", "legacy", "full"], ["#d95f02", "#7570b3", "#1f78b4", "#1b9e77"]):
    x = float(u[u.cell == "preset=" + p].p50_ms.iloc[0]); y = pc(l[l.cell == "preset=" + p].LM.iloc[0])
    ax.errorbar(x, y[0], yerr=[[y[0] - y[1]], [y[2] - y[0]]], fmt="o", color=c, capsize=2, ms=5)
    dx, dy, ha = off[p]; ax.annotate(p, (x, y[0]), xytext=(dx, dy), textcoords="offset points", fontsize=7, color=c, ha=ha)
ax.set_xlabel("Median latency p50 (ms)"); ax.set_ylabel("Post-revocation LM"); ax.set_ylim(-0.05, 0.8); ax.set_xlim(500, 1080)
fig.savefig("figures/fig6_rq5_pareto.pdf"); plt.close(fig)

# ---- Fig 7: real-LLM survival (per-event lifetimes)
e = pd.read_csv(R + "model_grid_local/analysis/revocation_events.csv")
fig, ax = plt.subplots(figsize=(COL, 2.0))
for cell, lab_, c, ls in [("llm_backend=ollama,preset=baseline", "Qwen2.5-3B, baseline", C4[1], "-"),
                          ("llm_backend=stub,preset=baseline", "Stub, baseline", C4[2], "-"),
                          ("llm_backend=ollama,preset=full", "Qwen2.5-3B, full", C4[0], "-"),
                          ("llm_backend=stub,preset=full", "Stub, full", "black", ":")]:
    x = e[e.cell == cell]; step(ax, x.lifetime_s, x.censored, color=c, ls=ls, label=lab_)
ax.set_xlabel("Hours since revocation"); ax.set_ylabel("Share still leaking"); ax.set_xticks([0, 12, 24, 36, 48])
ax.set_ylim(-0.03, 1.03); ax.legend(fontsize=6.5, loc="upper right", bbox_to_anchor=(1, 0.93))
fig.savefig("figures/fig7_real_llm_survival.pdf"); plt.close(fig)

# ---- Fig 8: real-LLM ROC per channel (test probes, insider and outsider pooled)
p = pd.read_csv(R + "rq3_existence_local/analysis/probe_scores.csv")
chans = [("combined", "Combined", "black", "-"), ("score", "Score", C4[0], "-"), ("reranker", "Reranker", C4[1], "-"),
         ("latency", "Latency", C4[2], "--"), ("refusal", "Refusal", C4[3], "-."), ("content", "Content", "#a6761d", ":")]
fig, axs = plt.subplots(1, 3, figsize=(FULL, 2.3), sharey=True)
for ax, pre in zip(axs, ["strawman", "baseline", "full"]):
    x = p[p.cell == "preset=" + pre]; y = x.world.values.astype(int)
    for ch, name, c, ls in chans:
        f, t, a = roc(y, x["score_" + ch].values.astype(float))
        ax.plot(f, t, color=c, ls=ls, lw=1.1, label=f"{name} ({a:.2f})")
        if ch == "combined": print(pre, "combined AUC", round(a, 3))
    ax.plot([0, 1], [0, 1], color="0.8", lw=0.6); ax.set_title(pre, fontsize=8); ax.set_xlabel("False positive rate")
    ax.legend(fontsize=6, loc="lower right"); ax.set_aspect("equal")
axs[0].set_ylabel("True positive rate")
fig.savefig("figures/fig8_real_llm_rq3_roc.pdf"); plt.close(fig)

# ---- Fig 9: published enforcement patterns -- leakage vs existence inference
# Both axes measured in the same experiment pair (rq_baselines_*), so the four points are
# paired and directly comparable. Latency was never measured for the authz_* presets, which
# is why they do not appear in Fig 6.
lb = pd.read_csv(R + "rq_baselines_revocation/analysis/revocation_summary.csv")
eb = pd.read_csv(R + "rq_baselines_existence/analysis/existence_eia.csv")
eb = eb[(eb.channel == "combined") & (eb.model == "gboost") & (eb.profile == "with_reranker")]
eb = eb.sort_values("n_test").groupby("cell", as_index=False).last()      # pooled row = largest n_test
fig, ax = plt.subplots(figsize=(COL, 2.3))
pres = [("baseline", "baseline", "#7570b3", (6, 7, "left")),
        ("authz_prefilter", "authz\\_prefilter", "#4292c6", (6, -12, "left")),
        ("authz_postfilter", "authz\\_postfilter", "#d95f02", (-6, 7, "right")),
        ("full", "full", "#1b9e77", (8, 2, "left"))]
for key, lab_, c, (dx, dy, ha) in pres:
    row = lb[lb.cell == "preset=" + key + ",revocation_type=single_doc"]
    y = pc(row.LM.iloc[0])
    x = pc(eb[eb.cell == "preset=" + key].AUC.iloc[0])
    ax.errorbar(x[0], y[0], xerr=[[x[0] - x[1]], [x[2] - x[0]]],
                yerr=[[y[0] - y[1]], [y[2] - y[0]]], fmt="o", color=c, capsize=2, ms=5, lw=1.0)
    ax.annotate(lab_.replace("\\_", "_"), (x[0], y[0]), xytext=(dx, dy),
                textcoords="offset points", fontsize=7, color=c, ha=ha)
ax.axvline(0.5, color="0.75", lw=0.6, ls=":")
ax.text(0.505, 0.60, "chance", fontsize=6, color="0.45", rotation=90, va="top")
ax.set_xlabel("Existence inference AUC (combined attacker)")
ax.set_ylabel("Post-revocation LM")
ax.set_xlim(0.45, 1.03); ax.set_ylim(-0.05, 0.72)
fig.savefig("figures/fig9_baselines.pdf"); plt.close(fig)
print("wrote figures/fig9_baselines.pdf")
