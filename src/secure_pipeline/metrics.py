"""
metrics.py -- Leakage, survival, inference and utility metrics with bootstrap CIs (§4).

- LM  (leakage magnitude): fraction of a revoked target's secrets (facts + canary)
      disclosed by any post-revocation probe, per revocation event.
- Leakage lifetime / LH: per event, the probe time at which leakage stopped for good
      (right-censored at the horizon if it never stopped). Aggregated with a
      Kaplan-Meier survival curve; LH is the KM median.
- EIA: AUC, TPR at a fixed low FPR, and balanced accuracy for existence inference.
- Utility: Recall@k, nDCG@k, answer correctness, over-refusal, latency percentiles,
      cache hit rate.

Confidence intervals are percentile bootstraps over the unit of analysis
(revocation events, probes, queries). Paired comparisons resample matched pairs.
"""

from __future__ import annotations

import math
from typing import Callable, Optional, Sequence

import numpy as np


# ---- Bootstrap ----------------------------------------------------------------

def bootstrap_ci(values: Sequence[float], stat: Callable = np.mean, n: int = 2000,
                 alpha: float = 0.05, seed: int = 0) -> tuple[float, float, float]:
    """(point, lo, hi) percentile bootstrap."""
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return (math.nan, math.nan, math.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n, len(v)))
    boots = np.array([stat(v[i]) for i in idx])
    return float(stat(v)), float(np.nanpercentile(boots, 100 * alpha / 2)), float(np.nanpercentile(boots, 100 * (1 - alpha / 2)))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], n: int = 2000, seed: int = 0) -> dict:
    """Mean difference a-b over matched pairs, its 95% CI, and a two-sided bootstrap p-value."""
    d = np.asarray(a, float) - np.asarray(b, float)
    if len(d) == 0:
        return {"diff": math.nan, "lo": math.nan, "hi": math.nan, "p": math.nan, "n": 0}
    rng = np.random.default_rng(seed)
    boots = d[rng.integers(0, len(d), size=(n, len(d)))].mean(axis=1)
    p = 2 * min((boots <= 0).mean(), (boots >= 0).mean())
    return {"diff": float(d.mean()), "lo": float(np.percentile(boots, 2.5)),
            "hi": float(np.percentile(boots, 97.5)), "p": float(min(1.0, p)), "n": int(len(d))}


# ---- Survival ---------------------------------------------------------------------

def kaplan_meier(durations: Sequence[float], observed: Sequence[bool]) -> tuple[np.ndarray, np.ndarray]:
    """Survival curve S(t) as step points (times, survival). observed=False means censored."""
    t = np.asarray(durations, float)
    e = np.asarray(observed, bool)
    times = np.unique(t[e])
    surv, s = [], 1.0
    for ti in times:
        at_risk = (t >= ti).sum()
        deaths = ((t == ti) & e).sum()
        s *= 1.0 - deaths / at_risk
        surv.append(s)
    return np.concatenate([[0.0], times]), np.concatenate([[1.0], surv])


def km_median(durations: Sequence[float], observed: Sequence[bool]) -> float:
    times, surv = kaplan_meier(durations, observed)
    below = np.where(surv <= 0.5)[0]
    return float(times[below[0]]) if len(below) else math.inf


def km_median_ci(durations, observed, n: int = 1000, seed: int = 0) -> tuple[float, float, float]:
    d, e = np.asarray(durations, float), np.asarray(observed, bool)
    if len(d) == 0:
        return (math.nan, math.nan, math.nan)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n):
        i = rng.integers(0, len(d), len(d))
        boots.append(km_median(d[i], e[i]))
    boots = np.sort(np.array(boots))   # inf sorts last; index percentiles to keep it
    lo, hi = boots[int(0.025 * (n - 1))], boots[int(0.975 * (n - 1))]
    return km_median(d, e), float(lo), float(hi)


def leak_lifetime(probe_times: Sequence[float], leaked: Sequence[bool]) -> tuple[float, bool]:
    """Lifetime of one revocation event from its probe series.

    Returns (duration, observed). Duration is the first probe time after the last leak
    (an upper bound on when leakage ended); 0 if nothing leaked. If the last probe still
    leaked, the event is censored at that time.
    """
    pairs = sorted(zip(probe_times, leaked))
    last = max((i for i, (_, lk) in enumerate(pairs) if lk), default=None)
    if last is None:
        return 0.0, True
    if last == len(pairs) - 1:
        return float(pairs[-1][0]), False
    return float(pairs[last + 1][0]), True


# ---- Existence inference ------------------------------------------------------------

def tpr_at_fpr(labels: np.ndarray, scores: np.ndarray, fpr_target: float = 0.01) -> float:
    from sklearn.metrics import roc_curve
    fpr, tpr, _ = roc_curve(labels, scores)
    ok = fpr <= fpr_target
    return float(tpr[ok].max()) if ok.any() else 0.0


def eia_metrics(labels: np.ndarray, scores: np.ndarray, threshold: float = 0.5) -> dict:
    from sklearn.metrics import balanced_accuracy_score, roc_auc_score
    labels = np.asarray(labels)
    if len(set(labels)) < 2:
        return {"auc": math.nan, "tpr_at_1fpr": math.nan, "balanced_acc": math.nan}
    return {
        "auc": float(roc_auc_score(labels, scores)),
        "tpr_at_1fpr": tpr_at_fpr(labels, scores, 0.01),
        "balanced_acc": float(balanced_accuracy_score(labels, scores >= threshold)),
    }


def fast_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Mann-Whitney AUC with average ranks for ties (equals sklearn's roc_auc_score)."""
    from scipy.stats import rankdata
    labels = np.asarray(labels).astype(bool)
    n_pos, n_neg = labels.sum(), (~labels).sum()
    if n_pos == 0 or n_neg == 0:
        return math.nan
    ranks = rankdata(scores)
    return float((ranks[labels].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def auc_ci(labels, scores, n: int = 1000, seed: int = 0) -> tuple[float, float, float]:
    labels, scores = np.asarray(labels), np.asarray(scores)
    if len(set(labels)) < 2:
        return (math.nan, math.nan, math.nan)
    rng = np.random.default_rng(seed)
    boots = [fast_auc(labels[i], scores[i]) for i in rng.integers(0, len(labels), size=(n, len(labels)))]
    boots = np.array([b for b in boots if not math.isnan(b)])
    return fast_auc(labels, scores), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


# ---- Utility ---------------------------------------------------------------------------

def recall_at_k(ranked: Sequence[str], relevant: str, k: int) -> float:
    return float(relevant in list(ranked)[:k])


def ndcg_at_k(ranked: Sequence[str], relevant: str, k: int) -> float:
    """Single relevant document: nDCG = 1/log2(rank+1) at its first position."""
    for i, d in enumerate(list(ranked)[:k]):
        if d == relevant:
            return 1.0 / math.log2(i + 2)
    return 0.0


def percentile(values: Sequence[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, float), q)) if len(values) else math.nan


def fmt_ci(point: float, lo: float, hi: float, digits: int = 3) -> str:
    def f(x: float) -> str:
        return "inf" if math.isinf(x) else ("n/a" if math.isnan(x) else f"{x:.{digits}f}")
    if math.isnan(point):
        return "n/a"
    return f"{f(point)} [{f(lo)}, {f(hi)}]"


def safe_mean(values: Sequence[float]) -> Optional[float]:
    return float(np.mean(values)) if len(values) else None
