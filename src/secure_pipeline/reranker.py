"""
reranker.py -- Second-stage reranker (threat T5: its confidence is a side channel).

- "overlap": deterministic lexical heuristic (no download; tests and smoke runs)
- anything else: a sentence-transformers CrossEncoder model name

A model that fails to load raises. There is no silent fallback.
"""

from __future__ import annotations

import math
import re

_WORD = re.compile(r"[a-z0-9]+")


class OverlapReranker:
    name = "overlap"

    def score(self, query: str, texts: list[str]) -> list[float]:
        q = set(_WORD.findall(query.lower()))
        out = []
        for t in texts:
            words = set(_WORD.findall(t.lower()))
            out.append(len(q & words) / max(1, len(q)))
        return out


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder
        self.name = model_name
        self._model = CrossEncoder(model_name)

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        logits = self._model.predict([[query, t] for t in texts], show_progress_bar=False)
        return [1.0 / (1.0 + math.exp(-float(x))) for x in logits]


def make_reranker(name: str):
    return OverlapReranker() if name == "overlap" else CrossEncoderReranker(name)
