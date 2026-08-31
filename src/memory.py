"""
memory.py — Per-session conversational memory buffer.

Design (naive / vulnerable)
---------------------------
* Each session has a rolling list of (role, content) turns.
* When `rbac.revoke()` is called, NO session is purged.  The buffer for an
  active session therefore retains the full content of any response that
  was generated *before* the revocation event.
* On the next query in the same session, the pipeline injects the stale
  buffer as context for the LLM.  If a restricted document's content was
  included in an earlier assistant turn, the LLM sees it and may reproduce
  or paraphrase it — leaking it post-revocation through the memory surface.

Public API
----------
    mem = SessionMemory(max_turns=20)
    mem.append("session-1", "user",      "What is Project Nightingale?")
    mem.append("session-1", "assistant", "<response containing D's content>")
    mem.get_context("session-1")
    # -> [{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]

    # Explicit clear (NOT called by the naive pipeline on revocation)
    mem.clear_session("session-1")
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Turn:
    role: str     # "user" | "assistant" | "system"
    content: str


class SessionMemory:
    """
    Rolling conversational buffer, one list of turns per session ID.

    Parameters
    ----------
    max_turns : int
        Maximum number of turns to retain per session (oldest are dropped).
        Set high (default: 20) to maximise the leakage window.
    """

    def __init__(self, max_turns: int = 20) -> None:
        self._sessions: dict[str, list[Turn]] = {}
        self._max_turns = max_turns

    # ── Mutations ──────────────────────────────────────────────────────────────

    def append(self, session_id: str, role: str, content: str) -> None:
        """Append one turn to *session_id*'s buffer."""
        turns = self._sessions.setdefault(session_id, [])
        turns.append(Turn(role=role, content=content))
        # Trim oldest turns if over the limit.
        if len(turns) > self._max_turns:
            self._sessions[session_id] = turns[-self._max_turns :]

    def clear_session(self, session_id: str) -> None:
        """
        Explicitly clear a session buffer.

        This method exists but is NEVER called by NaiveRAGPipeline
        (or by the RBAC layer on revocation).  It is provided so that
        a *mitigated* pipeline can call it without changing this module.
        """
        self._sessions.pop(session_id, None)

    # ── Queries ────────────────────────────────────────────────────────────────

    def get_context(self, session_id: str) -> list[dict]:
        """
        Return the conversation history for *session_id* as a list of
        Chat-style message dicts: [{"role": ..., "content": ...}, ...].

        Returns an empty list for unknown session IDs.
        """
        turns = self._sessions.get(session_id, [])
        return [{"role": t.role, "content": t.content} for t in turns]

    def session_ids(self) -> list[str]:
        """Return all known session IDs."""
        return list(self._sessions.keys())
