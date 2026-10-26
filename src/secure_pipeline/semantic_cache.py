"""
semantic_cache.py -- Embedding-keyed answer cache (threat T2).

Behaviour is set by Mitigations:
- cache_scope  : "global" (any user hits any entry), "tenant", or "user"
- cache_evict  : eager; on ACCESS_REVOKED evict every entry whose taint intersects the
                 revoked docs (conservative: other holders lose the entry too)
- lazy_check   : on every lookup, skip entries whose taint the requester does not fully hold
                 in the live IAM (covers lost events and lagging sync)
- epoch_check  : on every lookup, skip entries created before their creator's latest
                 revocation (the permission-epoch alternative to taint, audit C6)
- flush        : on ACCESS_REVOKED, drop every entry the revoked user created

Lookup order: entries in scope are ranked by similarity and checked from the most similar
down, stopping at the first one above the threshold that passes the checks. The result is
the same entry a check-everything-first scan would pick, but authorization is evaluated only
for candidates that could be served. `last_decisions` counts the per-document authorization
decisions the last lookup made (audit H9: decisions, not calls).

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
    epoch: int = 0                     # creator's permission epoch at write time


class SemanticCache:
    def __init__(self, clock: Clock, acm: AccessControlManager, ttl_s: float, threshold: float,
                 scope: str, evict_on_revoke: bool, lazy_check: bool, epoch_check: bool = False,
                 flush_on_revoke: bool = False) -> None:
        self.clock = clock
        self.acm = acm
        self.ttl_s = ttl_s
        self.threshold = threshold
        self.scope = scope
        self.lazy_check = lazy_check
        self.epoch_check = epoch_check
        self._entries: list[CacheEntry] = []
        self.evictions = 0
        self.last_decisions = 0
        if evict_on_revoke:
            acm.subscribe(self.on_revocation, lossy=True)
        if flush_on_revoke:
            acm.subscribe(self.on_flush, lossy=True)

    def _in_scope(self, e: CacheEntry, user_id: str, tenant_id: Optional[str], now: float) -> bool:
        if now - e.created_at > self.ttl_s:
            return False
        if self.scope == "tenant" and e.tenant_id != tenant_id:
            return False
        if self.scope == "user" and e.created_by != user_id:
            return False
        return True

    def _authorized(self, e: CacheEntry, user_id: str) -> bool:
        if self.epoch_check:
            self.last_decisions += 1
            if e.epoch != self.acm.epoch(e.created_by):
                return False
        if self.lazy_check:
            self.last_decisions += len(e.taint)
            if not self.acm.holds_all(user_id, e.taint):
                return False
        return True

    def get(self, q_emb: np.ndarray, user_id: str, tenant_id: Optional[str]) -> Optional[tuple[CacheEntry, float]]:
        now = self.clock.now()
        self.last_decisions = 0
        # Ties go to the oldest entry, as in a first-maximum scan.
        ranked = sorted(((float(np.dot(q_emb, e.embedding)), i) for i, e in enumerate(self._entries)
                         if self._in_scope(e, user_id, tenant_id, now)), key=lambda x: (-x[0], x[1]))
        for sim, i in ranked:
            if sim < self.threshold:
                break
            if self._authorized(self._entries[i], user_id):
                return self._entries[i], sim
        return None

    def put(self, entry: CacheEntry) -> None:
        self._entries.append(entry)

    def on_revocation(self, event: RevocationEvent) -> None:
        keep = [e for e in self._entries if not (e.taint & event.doc_ids)]
        self.evictions += len(self._entries) - len(keep)
        self._entries = keep

    def on_flush(self, event: RevocationEvent) -> None:
        keep = [e for e in self._entries if e.created_by != event.user_id]
        self.evictions += len(self._entries) - len(keep)
        self._entries = keep

    def clear(self) -> None:
        self._entries.clear()

    def entries_tainted_by(self, doc_id: str) -> list[CacheEntry]:
        now = self.clock.now()
        return [e for e in self._entries if doc_id in e.taint and now - e.created_at <= self.ttl_s]

    def __len__(self) -> int:
        return len(self._entries)
