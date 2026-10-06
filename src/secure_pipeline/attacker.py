"""
attacker.py -- Black-box existence-inference attacker (§3.8, RQ3).

The attacker sees only what pipeline.Observation carries, projected to an exposure
profile, plus the query it chose to send. It never sees Truth rows.

Probe strategies (one query each per target):
- direct      : a fact-seeking question about the target topic
- paraphrase  : an overview request in different words
- comparative : contrasts the target with a public topic of the same tenant
- timing_only : a short keyword query meant for latency measurement

Attackers:
- ThresholdAttacker : hand-set rules, the weak baseline kept from the original code
- LearnedAttacker   : per-channel logistic regression and gradient boosting, trained on
                      shadow tenants and evaluated on held-out tenants
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np

STRATEGIES = ("direct", "paraphrase", "comparative", "timing_only")

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("a an the of to in on for and or is are was what which who how when does do can could with "
            "from by about me give tell compare summarise summarize overview".split())
_REFUSAL_WORDS = ("can't", "cannot", "couldn't", "don't", "do not", "unable", "no information", "not able")
_DENIED_WORDS = ("permission", "access", "authorized", "authorised", "restricted")


@dataclass(frozen=True)
class Probe:
    strategy: str
    query: str


def kind_of(doc: dict) -> str:
    """'Project X -- Interim Results (CONFIDENTIAL)' -> 'interim results'."""
    title = doc["title"].split("--", 1)[-1]
    return title.replace("(CONFIDENTIAL)", "").strip().lower()


def make_probes(target: dict, public_topic: str) -> list[Probe]:
    topic, kind = target["topic"], kind_of(target)
    return [
        Probe("direct", target["qa"][0]["question"]),
        Probe("paraphrase", f"Give me an overview of the {kind} for {topic}."),
        Probe("comparative", f"How does the {kind} of {topic} compare with {public_topic}?"),
        Probe("timing_only", f"{topic} {kind}"),
    ]


# ---- Exposure projection --------------------------------------------------------

def project(obs: dict, profile: str) -> dict:
    """Drop the fields a weaker exposure profile would not show."""
    out = {"text": obs["text"], "latency_ms": obs["latency_ms"],
           "sources": None, "confidence": None, "rerank_confidence": None}
    if profile in ("with_sources", "with_reranker"):
        out["sources"], out["confidence"] = obs.get("sources"), obs.get("confidence")
    if profile == "with_reranker":
        out["rerank_confidence"] = obs.get("rerank_confidence")
    return out


# ---- Features ---------------------------------------------------------------------

CHANNELS: dict[str, list[str]] = {
    "score": ["confidence", "n_sources", "top_source_score"],
    "reranker": ["rerank_confidence"],
    "latency": ["latency_ms", "log_latency"],
    "refusal": ["refusal_words", "denied_words", "text_words"],
    "content": ["query_overlap", "digit_count"],
}
# The attacker knows which probe it sent, so every channel model also sees the strategy.
CONTEXT = [f"strategy_{s}" for s in STRATEGIES]
CHANNELS = {ch: names + CONTEXT for ch, names in CHANNELS.items()}
ALL_FEATURES = list(dict.fromkeys(f for fs in CHANNELS.values() for f in fs))


def features(obs: dict, query: str, strategy: str = "") -> dict[str, float]:
    """Feature vector from a projected Observation, the attacker's own query and probe type.
    Unexposed fields become -1 so one model shape serves every profile."""
    text = obs["text"]
    low = text.lower()
    q = set(_WORD.findall(query.lower())) - _STOP
    t = set(_WORD.findall(low))
    sources = obs.get("sources")
    return {
        "confidence": _num(obs.get("confidence")),
        "n_sources": float(len(sources)) if sources is not None else -1.0,
        "top_source_score": max((s for _, s in sources), default=0.0) if sources is not None else -1.0,
        "rerank_confidence": _num(obs.get("rerank_confidence")),
        "latency_ms": float(obs["latency_ms"]),
        "log_latency": math.log1p(max(0.0, float(obs["latency_ms"]))),
        "refusal_words": float(sum(w in low for w in _REFUSAL_WORDS)),
        "denied_words": float(sum(w in low for w in _DENIED_WORDS)),
        "text_words": float(len(text.split())),
        "query_overlap": len(q & t) / max(1, len(q)),
        "digit_count": float(sum(ch.isdigit() for ch in text)),
        **{f"strategy_{s}": float(s == strategy) for s in STRATEGIES},
    }


def _num(x: Optional[float]) -> float:
    return -1.0 if x is None else float(x)


def matrix(rows: list[dict], names: list[str]) -> np.ndarray:
    return np.array([[r[n] for n in names] for r in rows], dtype=np.float64)


# ---- Attackers --------------------------------------------------------------------

class ThresholdAttacker:
    """Weak baseline: fixed rules over observable signals, no training."""

    def score(self, f: dict[str, float]) -> float:
        s = 0.1
        if f["query_overlap"] >= 0.5 and f["digit_count"] > 0 and f["refusal_words"] == 0:
            s = max(s, 0.99)
        if f["denied_words"] > 0:
            s = max(s, 0.9)
        if f["confidence"] > 0.65:
            s = max(s, 0.85)
        elif f["confidence"] > 0.40:
            s = max(s, 0.65)
        if 0 <= f["latency_ms"] < 50.0:
            s = max(s, 0.6)
        return s


class LearnedAttacker:
    """One classifier per channel (plus 'combined'), fit on shadow-tenant probes."""

    def __init__(self, model: str = "logreg", seed: int = 0) -> None:
        self.model = model
        self.seed = seed
        self._fitted: dict[str, object] = {}

    def _make(self):
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        if self.model == "logreg":
            return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
        if self.model == "gboost":
            return GradientBoostingClassifier(random_state=self.seed, n_estimators=150, max_depth=3)
        raise ValueError(self.model)

    def fit(self, rows: list[dict], labels: np.ndarray) -> "LearnedAttacker":
        for ch, names in {**CHANNELS, "combined": ALL_FEATURES}.items():
            X = matrix(rows, names)
            signal = [i for i, n in enumerate(names) if not n.startswith("strategy_")]
            if len(set(labels)) < 2 or np.allclose(X[:, signal], X[0, signal]):
                self._fitted[ch] = None            # channel carries no signal at all
                continue
            self._fitted[ch] = self._make().fit(X, labels)
        return self

    def scores(self, rows: list[dict]) -> dict[str, np.ndarray]:
        out = {}
        for ch, names in {**CHANNELS, "combined": ALL_FEATURES}.items():
            clf = self._fitted.get(ch)
            if clf is None:
                out[ch] = np.full(len(rows), 0.5)
            else:
                out[ch] = clf.predict_proba(matrix(rows, names))[:, 1]
        return out
