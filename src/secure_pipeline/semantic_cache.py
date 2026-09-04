"""
semantic_cache.py -- Secure Semantic Cache with Invalidation & Multi-Tenant Isolation.

Design (§3.4, §3.6, §5.1):
- Embedding-keyed query-response cache with configurable TTL (short, medium, long).
- Baseline mode: Naive cache. Lookups happen before RBAC checks. No tenant boundary.
  No invalidation on revocation (primary temporal leakage surface, Threat T2).
- Mitigated mode:
  1. ACL-Aware Cache Lookup: Validates that the current user currently possesses
     active permissions to ALL doc_ids that produced the cached response within
     the requesting tenant.
  2. Invalidation Hook: Listens for ACCESS_REVOKED events and immediately purges
     any cache entry that references revoked document IDs or belongs to revoked users.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from .access_control import RevocationEvent, AccessControlManager


@dataclass
class CacheEntry:
    """A cached query-response record with full security provenance."""
    embedding: np.ndarray          # normalised query embedding
    response: str                  # LLM generated response text
    doc_ids: list[str]             # doc_ids that contributed to this response
    tenant_id: Optional[str] = None
    created_by: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: float = 3600.0

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return (now - self.timestamp) > self.ttl_seconds


class SecureSemanticCache:
    """
    Semantic Cache supporting both Naive and Mitigated security modes.

    Parameters
    ----------
    ttl_seconds : float
        Time-to-live in seconds (e.g. 60=short, 600=medium, 3600=long).
    sim_threshold : float
        Minimum cosine similarity for a cache hit (default: 0.70).
    mode : str
        "baseline" or "mitigated".
    """

    def __init__(
        self,
        ttl_seconds: float = 3600.0,
        sim_threshold: float = 0.70,
        mode: str = "baseline",
    ) -> None:
        self._entries: list[CacheEntry] = []
        self._ttl = ttl_seconds
        self._threshold = sim_threshold
        self._mode = mode
        # Eviction statistics for metrics
        self.eviction_count = 0

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._mode = value

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    @ttl_seconds.setter
    def ttl_seconds(self, value: float) -> None:
        self._ttl = value

    # ---- Querying -----------------------------------------------------------

    def get(
        self,
        query_embedding: np.ndarray,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        rbac: Optional[AccessControlManager] = None,
        mode_override: Optional[str] = None,
        current_time: Optional[float] = None,
    ) -> Optional[tuple[CacheEntry, float]]:
        """
        Look up a query in the cache.

        In Baseline mode: Returns any matching entry without verifying access rights.
        In Mitigated mode: Verifies tenant isolation and that user_id has valid access
        to all doc_ids in the cached entry.
        """
        active_mode = mode_override or self._mode
        now = current_time if current_time is not None else time.time()

        best_sim: float = -1.0
        best_entry: Optional[CacheEntry] = None

        for entry in self._entries:
            # Check TTL
            if entry.is_expired(now):
                continue

            # MITIGATED MODE: Check tenant match and user permissions
            if active_mode == "mitigated":
                if tenant_id and entry.tenant_id and entry.tenant_id != tenant_id:
                    continue
                if user_id and rbac is not None:
                    # User must still have active access to every document used in this cached response
                    if any(not rbac.has_access(user_id, d_id) for d_id in entry.doc_ids):
                        continue

            sim = _cosine_sim(query_embedding, entry.embedding)
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry is not None and best_sim >= self._threshold:
            return best_entry, best_sim
        return None

    # ---- Insertion ----------------------------------------------------------

    def put(
        self,
        query_embedding: np.ndarray,
        response: str,
        doc_ids: list[str],
        tenant_id: Optional[str] = None,
        created_by: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """Store a new query-response record."""
        entry = CacheEntry(
            embedding=np.array(query_embedding, dtype=np.float32),
            response=response,
            doc_ids=list(doc_ids),
            tenant_id=tenant_id,
            created_by=created_by,
            timestamp=timestamp if timestamp is not None else time.time(),
            ttl_seconds=self._ttl,
        )
        self._entries.append(entry)

    # ---- Invalidation Hook (§3.6) -------------------------------------------

    def on_revocation(self, event: RevocationEvent) -> None:
        """
        Revocation listener called by AccessControlManager in mitigated mode.
        Purges affected cache entries immediately.
        """
        revoked_docs = set(event.doc_ids)
        surviving_entries: list[CacheEntry] = []
        evicted = 0

        for entry in self._entries:
            should_evict = False

            # If user offboarded, evict all entries created by that user
            if event.event_type == "user_offboard" and entry.created_by == event.user_id:
                should_evict = True
            # If entry contains any revoked document
            elif any(d in revoked_docs for d in entry.doc_ids):
                should_evict = True

            if should_evict:
                evicted += 1
            else:
                surviving_entries.append(entry)

        self._entries = surviving_entries
        self.eviction_count += evicted

    def clear(self) -> None:
        self._entries.clear()

    def size(self) -> int:
        return len(self._entries)

    def active_entries(self, current_time: Optional[float] = None) -> list[CacheEntry]:
        now = current_time if current_time is not None else time.time()
        return [e for e in self._entries if not e.is_expired(now)]


# ---- Helpers ----------------------------------------------------------------

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# Backward-compatible alias
SemanticCache = SecureSemanticCache
