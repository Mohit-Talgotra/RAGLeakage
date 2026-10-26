"""
session_memory.py -- Per-session chat memory with rolling summaries (threat T3).

Each session keeps recent turns verbatim. When a session grows past `summary_after`
turns, everything except the last `keep_recent` turns is compressed into a single
summary turn, as LangChain-style summary memory does. Two summarizers:

- extractive (default) : keep unique sentences that carry figures, names or codenames. It is
                         a deterministic stand-in and is biased towards keeping secrets, so it
                         gives an upper bound on what a summary retains.
- callable             : any function turns -> text, e.g. LLMClient.summarize, so real-model
                         runs summarise with the same model (audit C4). Its output has no
                         sentence-to-source mapping, so it only supports turn-level taint.

Taint (see provenance.py):
- a turn's taint is set by the pipeline from the response taint
- a summary's taint is the union of the turns it replaced when taint is transitive (or when
  summary_union asks for that one hop), and empty otherwise; the empty case is the one that
  defeats an ID-match purge
- granularity "sentence": an extractive summary keeps each sentence's own taint (the turn it
  came from), so a revocation drops only the sentences derived from the lost document (H6)

Mitigations:
- memory_purge : eager; on ACCESS_REVOKED drop the user's turns whose taint intersects
                 the revoked docs (offboarding drops all the user's sessions)
- lazy_check   : on every read, drop turns whose taint the reader does not fully hold
- epoch_check  : on every read, drop turns written before the owner's latest revocation
- flush        : on ACCESS_REVOKED, drop every session of that user

Retention: with ttl_s > 0 a session idle for longer than ttl_s is discarded on its next read,
as chat products expire or archive old conversations (audit H2: without it memory can never
heal, by construction).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from .access_control import AccessControlManager, RevocationEvent
from .clock import Clock
from .provenance import EMPTY, Taint, taint_union

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_KEY_RE = re.compile(r"\d|[A-Z][a-z]+ [A-Z][a-z]+|codename")

Part = tuple[str, Taint]   # (sentence, its taint)


@dataclass(frozen=True)
class Turn:
    role: str            # "user" | "assistant" | "summary"
    content: str
    taint: Taint = EMPTY
    epoch: int = 0       # owner's permission epoch when written
    parts: tuple[Part, ...] = ()   # sentence-level taint of an extractive summary (granularity "sentence")


PREFIX_RE = re.compile(r"^(Summary of earlier conversation:|From our earlier conversation:|According to [^:]+:)\s*")
SUMMARY_PREFIX = "Summary of earlier conversation: "


def strip_prefixes(sentence: str) -> str:
    """Remove generator/summary lead-ins so the same sentence is not stored twice."""
    while True:
        stripped = PREFIX_RE.sub("", sentence)
        if stripped == sentence:
            return sentence.strip()
        sentence = stripped


def summarize_parts(turns: list[Turn], max_sentences: int = 12) -> list[Part]:
    """Extractive summary as (sentence, taint) pairs: unique sentences that carry figures,
    names or codenames, figures first when the budget is tight. A sentence seen in several
    turns carries the union of their taints."""
    order: list[str] = []
    taints: dict[str, set] = {}
    for t in turns:
        if t.role == "user":
            continue
        pieces = t.parts or tuple((s, t.taint) for s in _SENT_RE.split(t.content.replace("\n", " ")))
        for s, taint in pieces:
            s = strip_prefixes(s)
            if s and _KEY_RE.search(s):
                if s not in taints:
                    order.append(s)
                    taints[s] = set()
                taints[s] |= taint
    if len(order) > max_sentences:
        with_digits = [s for s in order if any(ch.isdigit() for ch in s)]
        rest = [s for s in order if s not in with_digits]
        keep = set((with_digits + rest)[:max_sentences])
        order = [s for s in order if s in keep]
    return [(s, frozenset(taints[s])) for s in order]


def summarize(turns: list[Turn], max_sentences: int = 12) -> str:
    return SUMMARY_PREFIX + " ".join(s for s, _ in summarize_parts(turns, max_sentences))


class SessionMemory:
    def __init__(self, acm: AccessControlManager, summary_after: int, keep_recent: int,
                 transitive: bool, purge_on_revoke: bool, lazy_check: bool, *,
                 clock: Optional[Clock] = None, ttl_s: float = 0.0, epoch_check: bool = False,
                 flush_on_revoke: bool = False, summary_union: bool = False, granularity: str = "turn",
                 summarizer: Optional[Callable[[list[Turn]], str]] = None) -> None:
        self.acm = acm
        self.summary_after = summary_after
        self.keep_recent = keep_recent
        self.transitive = transitive
        self.lazy_check = lazy_check
        self.clock = clock
        self.ttl_s = ttl_s
        self.epoch_check = epoch_check
        self.summary_union = summary_union
        self.granularity = granularity if summarizer is None else "turn"
        self.summarizer = summarizer
        self._sessions: dict[str, list[Turn]] = {}
        self._owner: dict[str, str] = {}
        self._last_active: dict[str, float] = {}
        self.purged = 0
        self.last_decisions = 0
        if purge_on_revoke:
            acm.subscribe(self.on_revocation, lossy=True)
        if flush_on_revoke:
            acm.subscribe(self.on_flush, lossy=True)

    # ---- Writes ---------------------------------------------------------------

    def append(self, session_id: str, user_id: str, role: str, content: str, taint: Taint) -> Optional[str]:
        """Add a turn; returns the summary text if this append triggered a summarization."""
        self._expire(session_id)
        self._owner[session_id] = user_id
        if self.clock is not None:
            self._last_active[session_id] = self.clock.now()
        turns = self._sessions.setdefault(session_id, [])
        epoch = self.acm.epoch(user_id)
        turns.append(Turn(role, content, taint, epoch))
        if self.summary_after and len(turns) > self.summary_after:
            old, recent = turns[:-self.keep_recent], turns[-self.keep_recent:]
            if self.epoch_check:
                # A summary is stamped with the current epoch, so it must not absorb stale turns.
                old = [t for t in old if t.epoch == epoch]
            carries = self.transitive or self.summary_union
            s_taint = taint_union(*(t.taint for t in old)) if carries else EMPTY
            if self.summarizer is not None:
                summary = Turn("summary", SUMMARY_PREFIX + self.summarizer(old), s_taint, epoch)
            else:
                parts = summarize_parts(old)
                if not carries:
                    parts = [(s, EMPTY) for s, _ in parts]
                summary = Turn("summary", SUMMARY_PREFIX + " ".join(s for s, _ in parts), s_taint, epoch,
                               tuple(parts) if self.granularity == "sentence" else ())
            self._sessions[session_id] = [summary] + recent
            return summary.content
        return None

    # ---- Reads ----------------------------------------------------------------

    def _expire(self, session_id: str) -> None:
        if not self.ttl_s or self.clock is None or session_id not in self._last_active:
            return
        if self.clock.now() - self._last_active[session_id] > self.ttl_s:
            self.purged += len(self._sessions.get(session_id, []))
            self._sessions[session_id] = []

    def _filter(self, t: Turn, user_id: str, owner: str) -> Optional[Turn]:
        if self.epoch_check:
            self.last_decisions += 1
            if t.epoch != self.acm.epoch(owner):
                return None
        if not self.lazy_check:
            return t
        if t.parts:
            self.last_decisions += sum(len(tt) for _, tt in t.parts)
            kept = tuple((s, tt) for s, tt in t.parts if self.acm.holds_all(user_id, tt))
            if not kept:
                return None
            if len(kept) == len(t.parts):
                return t
            return Turn(t.role, SUMMARY_PREFIX + " ".join(s for s, _ in kept),
                        taint_union(*(tt for _, tt in kept)), t.epoch, kept)
        self.last_decisions += len(t.taint)
        return t if self.acm.holds_all(user_id, t.taint) else None

    def context(self, session_id: str, user_id: str) -> list[Turn]:
        self._expire(session_id)
        self.last_decisions = 0
        turns = self._sessions.get(session_id, [])
        owner = self._owner.get(session_id, user_id)
        out = []
        for t in turns:
            f = self._filter(t, user_id, owner)
            if f is not None:
                out.append(f)
        return out

    def turns(self, session_id: str) -> list[Turn]:
        return list(self._sessions.get(session_id, []))

    # ---- Revocation hooks -------------------------------------------------------

    def on_revocation(self, event: RevocationEvent) -> None:
        for sid, owner in list(self._owner.items()):
            if owner != event.user_id:
                continue
            turns = self._sessions.get(sid, [])
            if event.event_type == "user_offboard":
                keep = []
            else:
                keep = []
                for t in turns:
                    if t.parts and self.granularity == "sentence":
                        parts = tuple((s, tt) for s, tt in t.parts if not (tt & event.doc_ids))
                        if parts:
                            keep.append(t if len(parts) == len(t.parts) else
                                        Turn(t.role, SUMMARY_PREFIX + " ".join(s for s, _ in parts),
                                             taint_union(*(tt for _, tt in parts)), t.epoch, parts))
                    elif not (t.taint & event.doc_ids):
                        keep.append(t)
            self.purged += len(turns) - len(keep)
            self._sessions[sid] = keep

    def on_flush(self, event: RevocationEvent) -> None:
        for sid, owner in list(self._owner.items()):
            if owner == event.user_id:
                self.purged += len(self._sessions.get(sid, []))
                self._sessions[sid] = []

    def clear(self) -> None:
        self._sessions.clear()
        self._owner.clear()
        self._last_active.clear()
