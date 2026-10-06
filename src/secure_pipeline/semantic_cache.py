"""
semantic_cache.py -- Embedding-keyed answer cache (threat T2).

Behaviour is set by Mitigations:
- cache_scope  : "global" (any user hits any entry), "tenant", or "user"
- cache_evict  : eager; on ACCESS_REVOKED evict every entry whose taint intersects the
                 revoked docs (conservative: other holders lose the entry too)
- lazy_check   : on every lookup, skip entries whose taint the requester does not fully hold
                 in the live IAM (covers lost events and lagging sync)

Entries expire after ttl_s on the shared Clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .access_control import AccessControlManager, RevocationEvent
from .clock import Clock
from .provenance import Taint


@dataclass
class CacheEntry:
    embedding: np.ndarray
    query: str
    response: str
    sources: list[tuple[str, float]]   # (title, score) shown with the original answer
    confidence: float
    rerank_confidence: float
    taint: Taint
    source_docs: tuple[str, ...]       # ground truth: docs the answer was generated from
    tenant_id: Optional[str]
    created_by: str
    created_at: float


class SemanticCache:
    def __init__(self, clock: Clock, acm: AccessControlManager, ttl_s: float, threshold: float,
                 scope: str, evict_on_revoke: bool, lazy_check: bool) -> None:
        self.clock = clock
        self.acm = acm
        self.ttl_s = ttl_s
        self.threshold = threshold
        self.scope = scope
        self.lazy_check = lazy_check
        self._entries: list[CacheEntry] = []
        self.evictions = 0
        if evict_on_revoke:
            acm.subscribe(self.on_revocation)

    def _visible(self, e: CacheEntry, user_id: str, tenant_id: Optional[str], now: float) -> bool:
        if now - e.created_at > self.ttl_s:
            return False
        if self.scope == "tenant" and e.tenant_id != tenant_id:
            return False
        if self.scope == "user" and e.created_by != user_id:
            return False
        if self.lazy_check and not self.acm.holds_all(user_id, e.taint):
            return False
        return True

    def get(self, q_emb: np.ndarray, user_id: str, tenant_id: Optional[str]) -> Optional[tuple[CacheEntry, float]]:
        now = self.clock.now()
        best, best_sim = None, -1.0
        for e in self._entries:
            if not self._visible(e, user_id, tenant_id, now):
                continue
            sim = float(np.dot(q_emb, e.embedding))
            if sim > best_sim:
                best, best_sim = e, sim
        if best is not None and best_sim >= self.threshold:
            return best, best_sim
        return None

    def put(self, entry: CacheEntry) -> None:
        self._entries.append(entry)

    def on_revocation(self, event: RevocationEvent) -> None:
        keep = [e for e in self._entries if not (e.taint & event.doc_ids)]
        self.evictions += len(self._entries) - len(keep)
        self._entries = keep

    def clear(self) -> None:
        self._entries.clear()

    def entries_tainted_by(self, doc_id: str) -> list[CacheEntry]:
        now = self.clock.now()
        return [e for e in self._entries if doc_id in e.taint and now - e.created_at <= self.ttl_s]

    def __len__(self) -> int:
        return len(self._entries)
