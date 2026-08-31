"""
semantic_cache.py — In-memory semantic cache with a long TTL and no eviction on revocation.

Design (naive / vulnerable)
---------------------------
* A query hits the cache if its embedding is within `sim_threshold` cosine
  similarity of any previously cached query.
* No RBAC check is performed on retrieval — whoever asks gets whatever was
  cached, regardless of whether they have (or still have) access to the
  underlying documents.
* TTL is deliberately long (default: 1 hour) to widen the temporal leakage
  window. Expired entries are skipped but never removed from the list.
* There is NO eviction hook that `rbac.revoke()` can call.

This makes the cache the primary leakage surface:
  1. Temporal leak:     U queries D before revocation → cached.
                        U (post-revocation) or A re-asks → cache hit, full content returned.
  2. Existence signal:  Even a partial/near-miss that scores below `sim_threshold`
                        still produces a measurable latency difference (cache-miss
                        path is slower) that is logged and visible to analysts.

Public API
----------
    cache = SemanticCache(ttl_seconds=3600, sim_threshold=0.70)

    # Check (returns None on miss)
    result = cache.get(query_embedding)
    if result:
        entry, similarity = result
        print(entry.response)

    # Store
    cache.put(query_embedding, response_text, doc_ids_used)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class CacheEntry:
    """A single cached query-response pair."""
    embedding: np.ndarray          # normalised query embedding
    response: str                  # LLM-generated response text
    doc_ids: list[str]             # doc_ids that contributed to this response
    timestamp: float = field(default_factory=time.time)


class SemanticCache:
    """
    In-memory semantic cache.

    Parameters
    ----------
    ttl_seconds : float
        How long an entry is considered fresh (default: 3600 s / 1 hour).
    sim_threshold : float
        Minimum cosine similarity for a cache hit (default: 0.70).
        Set low deliberately to catch paraphrases and demonstrate leakage.
    """

    def __init__(
        self,
        ttl_seconds: float = 3600.0,
        sim_threshold: float = 0.70,
    ) -> None:
        self._entries: list[CacheEntry] = []
        self._ttl = ttl_seconds
        self._threshold = sim_threshold

    # ── Public interface ───────────────────────────────────────────────────────

    def get(
        self, embedding: np.ndarray
    ) -> Optional[tuple[CacheEntry, float]]:
        """
        Look up a query by its embedding.

        Returns
        -------
        (CacheEntry, cosine_similarity)  if a hit is found, else None.

        NO access-control check is performed here — that's the vulnerability.
        """
        now = time.time()
        best_sim: float = -1.0
        best_entry: Optional[CacheEntry] = None

        for entry in self._entries:
            # Skip expired entries (but don't delete them — they still occupy
            # memory and could be re-activated if TTL logic is later changed).
            if now - entry.timestamp > self._ttl:
                continue
            sim = _cosine_sim(embedding, entry.embedding)
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry is not None and best_sim >= self._threshold:
            return best_entry, best_sim
        return None

    def put(
        self,
        embedding: np.ndarray,
        response: str,
        doc_ids: list[str],
    ) -> None:
        """Store a new query-response pair. Duplicate queries just add a new entry."""
        self._entries.append(
            CacheEntry(embedding=embedding, response=response, doc_ids=list(doc_ids))
        )

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def size(self) -> int:
        """Total number of entries (including expired)."""
        return len(self._entries)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two 1-D vectors.

    Both vectors are assumed to be L2-normalised (as produced by
    SentenceTransformer with normalize_embeddings=True), so this
    reduces to a simple dot product — kept explicit for clarity.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
