"""
session_memory.py -- Conversational Memory Buffer with Revocation Purging.

Design (§3.5, §3.6, Threat T3):
- Manages multi-turn conversational session buffers per user/session.
- Baseline mode: Stale conversational memory persists post-revocation. If an earlier
  turn quoted restricted documents, the LLM continues referencing them in-context (T3).
- Mitigated mode:
  - Invalidation Hook: on ACCESS_REVOKED, active user sessions are scanned and sanitized.
    Any turns containing or generated from revoked doc_ids are pruned or scrubbed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .access_control import RevocationEvent


@dataclass(frozen=True)
class Turn:
    role: str                       # "user" | "assistant" | "system"
    content: str
    referenced_doc_ids: list[str] = field(default_factory=list)


class SecureSessionMemory:
    """
    Conversational Session Memory with Revocation Purge Hooks.

    Parameters
    ----------
    max_turns : int
        Maximum number of turns to keep per session (default: 20).
    mode : str
        "baseline" or "mitigated".
    """

    def __init__(self, max_turns: int = 20, mode: str = "baseline") -> None:
        self._sessions: dict[str, list[Turn]] = {}
        self._session_owners: dict[str, str] = {}  # session_id -> user_id
        self._max_turns = max_turns
        self._mode = mode
        self.purged_turns_count = 0

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._mode = value

    # ---- Append / Read ------------------------------------------------------

    def append(
        self,
        session_id: str,
        role: str,
        content: str,
        referenced_doc_ids: Optional[list[str]] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Append a conversational turn to a session."""
        if user_id is not None:
            self._session_owners[session_id] = user_id

        turns = self._sessions.setdefault(session_id, [])
        turns.append(
            Turn(
                role=role,
                content=content,
                referenced_doc_ids=list(referenced_doc_ids or []),
            )
        )
        if len(turns) > self._max_turns:
            self._sessions[session_id] = turns[-self._max_turns:]

    def get_context(self, session_id: str) -> list[dict]:
        """Return message context list formatted for LLM."""
        turns = self._sessions.get(session_id, [])
        return [{"role": t.role, "content": t.content} for t in turns]

    def clear_session(self, session_id: str) -> None:
        """Clear all turns for a specific session."""
        self._sessions.pop(session_id, None)
        self._session_owners.pop(session_id, None)

    # ---- Invalidation Hook (§3.6) -------------------------------------------

    def on_revocation(self, event: RevocationEvent) -> None:
        """
        Invalidation callback triggered on ACCESS_REVOKED in mitigated mode.
        Purges turns referencing revoked document IDs for the user's sessions.
        """
        revoked_docs = set(event.doc_ids)

        for session_id, owner in list(self._session_owners.items()):
            if owner != event.user_id:
                continue

            if event.event_type == "user_offboard":
                # User completely offboarded -> drop all sessions
                self.clear_session(session_id)
                self.purged_turns_count += 1
                continue

            turns = self._sessions.get(session_id, [])
            cleaned_turns: list[Turn] = []
            for turn in turns:
                # Check if turn references any revoked document
                if any(d in revoked_docs for d in turn.referenced_doc_ids):
                    self.purged_turns_count += 1
                    continue
                # Also check if text explicitly mentions revoked doc IDs
                if any(d in turn.content for d in revoked_docs):
                    self.purged_turns_count += 1
                    continue
                cleaned_turns.append(turn)

            self._sessions[session_id] = cleaned_turns

    def session_ids(self) -> list[str]:
        return list(self._sessions.keys())


# Backward-compatible alias
SessionMemory = SecureSessionMemory
