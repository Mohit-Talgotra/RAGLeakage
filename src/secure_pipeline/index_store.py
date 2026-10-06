"""
index_store.py -- ChromaDB chunk index with materialized ACLs and an ACL sync policy (threat T1).

At ingestion every chunk stores its tenant and one boolean metadata key per user
(acl__<user_id>) saying whether that user may read the chunk's document. This is the
pattern production SharePoint/M365 RAG pipelines use: permissions are copied into the
index so retrieval can filter with a `where` clause.

The copy goes stale. The live IAM (AccessControlManager) changes instantly on
revocation; the index metadata changes only when the SyncPolicy runs:

- live              : every ACCESS_REVOKED event is applied immediately
- periodic:<s>      : full re-crawl of all ACLs every <s> seconds (no events)
- event:<p>[:<s>]   : events applied immediately, but each is lost with probability <p>
                      (lost webhooks); optional full re-crawl backstop every <s> seconds

Retrieval:
- prefilter=True  : Chroma `where` on tenant + acl__<user> (stale ACL is what filters)
- prefilter=False : flat top-k over every tenant; caller post-filters on `index_allows`
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .access_control import AccessControlManager, RevocationEvent
from .clock import Clock
from .corpus import Chunk


@dataclass(frozen=True)
class SyncPolicy:
    kind: str = "live"                 # "live" | "periodic" | "event"
    interval_s: float = 0.0            # periodic interval
    drop_rate: float = 0.0             # event: probability an event is lost
    backstop_s: Optional[float] = None # event: periodic full crawl backstop

    @classmethod
    def parse(cls, spec: str) -> "SyncPolicy":
        parts = spec.split(":")
        if parts[0] == "live":
            return cls("live")
        if parts[0] == "periodic":
            return cls("periodic", interval_s=float(parts[1]))
        if parts[0] == "event":
            drop = float(parts[1]) if len(parts) > 1 else 0.0
            backstop = float(parts[2]) if len(parts) > 2 else None
            return cls("event", drop_rate=drop, backstop_s=backstop)
        raise ValueError(f"bad sync policy {spec!r}")

    def label(self) -> str:
        if self.kind == "periodic":
            return f"periodic:{self.interval_s:g}"
        if self.kind == "event":
            return f"event:{self.drop_rate:g}" + (f":{self.backstop_s:g}" if self.backstop_s else "")
        return "live"


@dataclass(frozen=True)
class Candidate:
    chunk_id: str
    doc_id: str
    tenant_id: str
    title: str
    text: str
    score: float           # cosine similarity in [0, 1]
    index_allows: bool     # what the (possibly stale) index ACL says for this user


def acl_key(user_id: str) -> str:
    return f"acl__{user_id}"


_CLIENT = None


def _client():
    global _CLIENT
    if _CLIENT is None:
        import chromadb
        _CLIENT = chromadb.EphemeralClient()
    return _CLIENT


class VectorIndex:
    def __init__(
        self,
        chunks: list[Chunk],
        embeddings: np.ndarray,
        acm: AccessControlManager,
        policy: SyncPolicy,
        clock: Clock,
        rng: random.Random,
    ) -> None:
        self.acm = acm
        self.policy = policy
        self.clock = clock
        self.rng = rng
        self.users = acm.users()
        self._chunks = {c.chunk_id: c for c in chunks}
        self._emb = {c.chunk_id: e for c, e in zip(chunks, embeddings)}
        self._doc_chunks: dict[str, list[str]] = {}
        for c in chunks:
            self._doc_chunks.setdefault(c.doc_id, []).append(c.chunk_id)
        self._removed: set[str] = set()
        self.dropped_events = 0
        self.applied_events = 0

        self._col = _client().create_collection(
            name=f"afterimage-{uuid.uuid4().hex[:12]}",
            metadata={"hnsw:space": "cosine"},
        )
        # Materialized ACL: doc_id -> users the index believes may read it.
        self._materialized: dict[str, frozenset[str]] = {
            d: frozenset(acm.users_with_access(d)) for d in self._doc_chunks
        }
        self._add_chunks(list(self._chunks))
        interval = policy.interval_s if policy.kind == "periodic" else policy.backstop_s
        self._last_full_sync = clock.now() - (rng.uniform(0, interval) if interval else 0.0)

        if policy.kind in ("live", "event"):
            acm.subscribe(self.on_event)

    # ---- Ingestion ----------------------------------------------------------

    def _meta(self, chunk: Chunk) -> dict:
        allowed = self._materialized[chunk.doc_id]
        meta = {"doc_id": chunk.doc_id, "tenant_id": chunk.tenant_id}
        meta.update({acl_key(u): (u in allowed) for u in self.users})
        return meta

    def _add_chunks(self, chunk_ids: list[str]) -> None:
        for i in range(0, len(chunk_ids), 1000):
            batch = chunk_ids[i:i + 1000]
            self._col.add(
                ids=batch,
                embeddings=[self._emb[c].tolist() for c in batch],
                metadatas=[self._meta(self._chunks[c]) for c in batch],
            )

    def close(self) -> None:
        _client().delete_collection(self._col.name)

    def rebind(self, acm: AccessControlManager) -> None:
        """Point the index at a fresh IAM (new trial): resync every ACL, restore removed docs,
        and start the crawl cycle at a random phase so revocations land uniformly within it."""
        self.acm = acm
        self.restore_docs(list(self._removed))
        self._sync_docs(list(self._doc_chunks))
        interval = self.policy.interval_s if self.policy.kind == "periodic" else self.policy.backstop_s
        self._last_full_sync = self.clock.now() - (self.rng.uniform(0, interval) if interval else 0.0)
        self.dropped_events = self.applied_events = 0
        if self.policy.kind in ("live", "event"):
            acm.subscribe(self.on_event)

    # ---- Twin worlds --------------------------------------------------------

    def remove_docs(self, doc_ids) -> None:
        ids = [c for d in doc_ids for c in self._doc_chunks[d] if d not in self._removed]
        if ids:
            self._col.delete(ids=ids)
        self._removed |= set(doc_ids)

    def restore_docs(self, doc_ids) -> None:
        back = [d for d in doc_ids if d in self._removed]
        self._removed -= set(back)
        self._add_chunks([c for d in back for c in self._doc_chunks[d]])

    # ---- ACL propagation ----------------------------------------------------

    def _sync_docs(self, doc_ids) -> None:
        changed = []
        for d in doc_ids:
            if d not in self._doc_chunks:
                continue
            live = frozenset(self.acm.users_with_access(d))
            if live != self._materialized[d]:
                self._materialized[d] = live
                changed.append(d)
        ids = [c for d in changed if d not in self._removed for c in self._doc_chunks[d]]
        if ids:
            self._col.update(ids=ids, metadatas=[self._meta(self._chunks[c]) for c in ids])

    def sync_all(self) -> None:
        self._sync_docs(list(self._doc_chunks))
        self._last_full_sync = self.clock.now()

    def on_event(self, event: RevocationEvent) -> None:
        if self.policy.kind == "event" and self.rng.random() < self.policy.drop_rate:
            self.dropped_events += 1
            return
        self.applied_events += 1
        self._sync_docs(event.doc_ids)

    def tick(self) -> None:
        """Run any periodic crawl that is due. Called before every query."""
        interval = self.policy.interval_s if self.policy.kind == "periodic" else self.policy.backstop_s
        if not interval:
            return
        now = self.clock.now()
        if now - self._last_full_sync >= interval:
            self.sync_all()
            # Stay on the crawl grid rather than drifting with query arrival times.
            self._last_full_sync = now - ((now - self._last_full_sync) % interval)

    def next_sync_in(self) -> Optional[float]:
        interval = self.policy.interval_s if self.policy.kind == "periodic" else self.policy.backstop_s
        if not interval:
            return None
        return interval - (self.clock.now() - self._last_full_sync)

    def is_stale(self, doc_id: str) -> bool:
        return self._materialized[doc_id] != frozenset(self.acm.users_with_access(doc_id))

    def index_allows(self, user_id: str, doc_id: str) -> bool:
        return user_id in self._materialized[doc_id]

    # ---- Retrieval ----------------------------------------------------------

    def query(self, q_emb: np.ndarray, top_k: int, user_id: str, tenant_id: Optional[str],
              prefilter: bool) -> list[Candidate]:
        self.tick()
        where = None
        if prefilter:
            where = {"$and": [{"tenant_id": tenant_id}, {acl_key(user_id): True}]}
        res = self._col.query(
            query_embeddings=[np.asarray(q_emb, dtype=np.float32).tolist()],
            n_results=top_k,
            where=where,
            include=["distances", "metadatas"],
        )
        out = []
        for cid, dist, meta in zip(res["ids"][0], res["distances"][0], res["metadatas"][0]):
            c = self._chunks[cid]
            out.append(Candidate(
                chunk_id=cid, doc_id=c.doc_id, tenant_id=c.tenant_id, title=c.title, text=c.text,
                score=float(min(1.0, max(0.0, 1.0 - dist))),
                index_allows=bool(meta.get(acl_key(user_id), False)),
            ))
        return out
