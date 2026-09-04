"""
reranker.py -- Cross-Encoder Reranker layer for deep retrieval scoring.

Design (§3.3, §6, Threat T5):
- Evaluates candidate pairs (query, doc_text) with a Cross-Encoder to produce
  deep relevance / confidence scores.
- Baseline mode: Evaluates unfiltered candidate sets. Exposes raw continuous
  reranker confidence, enabling side-channel existence inference (T5).
- Mitigated mode: Reranks only pre-authorized candidates and provides normalized
  confidence scores.
"""

from __future__ import annotations

import math
from typing import Optional

# Optional import for cross-encoder model
_CROSS_ENCODER_AVAILABLE = False
try:
    from sentence_transformers import CrossEncoder as _CrossEncoder
    _CROSS_ENCODER_AVAILABLE = True
except ImportError:
    pass


class CrossEncoderReranker:
    """
    Reranks retrieved candidate documents using a Cross-Encoder or neural heuristic.

    Parameters
    ----------
    model_name : str
        Pretrained CrossEncoder model name.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name
        self._model = None
        self._is_stub = True

        if _CROSS_ENCODER_AVAILABLE:
            try:
                self._model = _CrossEncoder(model_name)
                self._is_stub = False
            except Exception:
                self._model = None
                self._is_stub = True

    def rerank(
        self,
        query: str,
        candidates: list[tuple[str, float, str]],
        top_k: Optional[int] = None,
    ) -> list[tuple[str, float, float, str]]:
        """
        Rerank candidates with Cross-Encoder.

        Parameters
        ----------
        query : str
            Query text.
        candidates : list of (doc_id, vector_similarity, doc_text)

        Returns
        -------
        list of (doc_id, vector_similarity, reranker_score, doc_text)
            Sorted descending by reranker_score.
        """
        if not candidates:
            return []

        if not self._is_stub and self._model is not None:
            pairs = [[query, text] for _, _, text in candidates]
            raw_scores = self._model.predict(pairs)
            # Apply sigmoid if logits
            scores = [1.0 / (1.0 + math.exp(-float(s))) if isinstance(s, (int, float)) else float(s) for s in raw_scores]
        else:
            # Deterministic simulation heuristic combining vector similarity with term overlap
            scores = []
            q_terms = set(query.lower().split())
            for _, vec_sim, text in candidates:
                t_terms = set(text.lower().split())
                overlap = len(q_terms.intersection(t_terms)) / max(1, len(q_terms))
                # Hybrid simulated score in [0, 1]
                sim_score = min(1.0, 0.6 * vec_sim + 0.4 * overlap)
                scores.append(round(sim_score, 4))

        results = [
            (doc_id, vec_sim, score, text)
            for (doc_id, vec_sim, text), score in zip(candidates, scores)
        ]
        results.sort(key=lambda x: x[2], reverse=True)

        if top_k is not None:
            results = results[:top_k]
        return results
