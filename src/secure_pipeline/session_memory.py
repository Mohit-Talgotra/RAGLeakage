"""
session_memory.py -- Per-session chat memory with rolling summaries (threat T3).

Each session keeps recent turns verbatim. When a session grows past `summary_after`
turns, everything except the last `keep_recent` turns is compressed into a single
summary turn, as LangChain-style summary memory does. The summary keeps the key
figures, so restricted content survives compression without naming any doc ID.

Taint (see provenance.py):
- a turn's taint is set by the pipeline from the response taint
- a summary's taint is the union of the turns it replaced when taint is transitive,
  and empty otherwise; this is the case that defeats an ID-match purge

Mitigations:
- memory_purge : eager; on ACCESS_REVOKED drop the user's turns whose taint intersects
                 the revoked docs (offboarding drops all the user's sessions)
- lazy_check   : on every read, drop turns whose taint the reader does not fully hold
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .access_control import AccessControlManager, RevocationEvent
from .provenance import EMPTY, Taint, taint_union

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_KEY_RE = re.compile(r"\d|[A-Z][a-z]+ [A-Z][a-z]+|codename")


@dataclass(frozen=True)
class Turn:
    role: str            # "user" | "assistant" | "summary"
    content: str
    taint: Taint = EMPTY


PREFIX_RE = re.compile(r"^(Summary of earlier conversation:|From our earlier conversation:|According to [^:]+:)\s*")


def strip_prefixes(sentence: str) -> str:
    """Remove generator/summary lead-ins so the same sentence is not stored twice."""
    while True:
        stripped = PREFIX_RE.sub("", sentence)
        if stripped == sentence:
            return sentence.strip()
        sentence = stripped


def summarize(turns: list[Turn], max_sentences: int = 12) -> str:
    """Extractive summary: keep unique sentences that carry figures, names or codenames.
    Sentences with figures are kept first when the budget is tight."""
    picked: list[str] = []
    for t in turns:
        if t.role == "user":
            continue
        for s in _SENT_RE.split(t.content.replace("\n", " ")):
            s = strip_prefixes(s)
            if s and _KEY_RE.search(s) and s not in picked:
                picked.append(s)
    if len(picked) > max_sentences:
        with_digits = [s for s in picked if any(ch.isdigit() for ch in s)]
        rest = [s for s in picked if s not in with_digits]
        keep = set((with_digits + rest)[:max_sentences])
        picked = [s for s in picked if s in keep]
    return "Summary of earlier conversation: " + " ".join(picked)


class SessionMemory:
    def __init__(self, acm: AccessControlManager, summary_after: int, keep_recent: int,
                 transitive: bool, purge_on_revoke: bool, lazy_check: bool) -> None:
        self.acm = acm
        self.summary_after = summary_after
        self.keep_recent = keep_recent
        self.transitive = transitive
        self.lazy_check = lazy_check
        self._sessions: dict[str, list[Turn]] = {}
        self._owner: dict[str, str] = {}
        self.purged = 0
        if purge_on_revoke:
            acm.subscribe(self.on_revocation)

    def append(self, session_id: str, user_id: str, role: str, content: str, taint: Taint) -> None:
        self._owner[session_id] = user_id
        turns = self._sessions.setdefault(session_id, [])
        turns.append(Turn(role, content, taint))
        if self.summary_after and len(turns) > self.summary_after:
            old, recent = turns[:-self.keep_recent], turns[-self.keep_recent:]
            s_taint = taint_union(*(t.taint for t in old)) if self.transitive else EMPTY
            self._sessions[session_id] = [Turn("summary", summarize(old), s_taint)] + recent

    def context(self, session_id: str, user_id: str) -> list[Turn]:
        turns = self._sessions.get(session_id, [])
        if self.lazy_check:
            turns = [t for t in turns if self.acm.holds_all(user_id, t.taint)]
        return list(turns)

    def turns(self, session_id: str) -> list[Turn]:
        return list(self._sessions.get(session_id, []))

    def on_revocation(self, event: RevocationEvent) -> None:
        for sid, owner in list(self._owner.items()):
            if owner != event.user_id:
                continue
            turns = self._sessions.get(sid, [])
            if event.event_type == "user_offboard":
                keep = []
            else:
                keep = [t for t in turns if not (t.taint & event.doc_ids)]
            self.purged += len(turns) - len(keep)
            self._sessions[sid] = keep

    def clear(self) -> None:
        self._sessions.clear()
        self._owner.clear()
