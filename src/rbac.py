"""
rbac.py — Minimal document-level access control store.

This is the *naive* implementation: grant() and revoke() only modify the
in-memory RBAC table. They do NOT propagate to the semantic cache, vector
index, or session memory — that deliberate absence is the vulnerability
under study.

Public API
----------
    store = AccessControlStore()
    store.grant("alice", "doc_A6")
    store.revoke("alice", "doc_A6")
    store.has_access("alice", "doc_A6")  # -> False
    store.accessible_docs("alice")       # -> set of doc_ids
"""


class AccessControlStore:
    """
    Doc-level RBAC store.

    Internal state:  _grants: dict[user_id, set[doc_id]]

    Thread-safety: none — this is a single-process MVP demo.
    """

    def __init__(self) -> None:
        self._grants: dict[str, set[str]] = {}

    # ── Mutations ──────────────────────────────────────────────────────────────

    def grant(self, user: str, doc_id: str) -> None:
        """Grant *user* access to *doc_id*."""
        self._grants.setdefault(user, set()).add(doc_id)

    def revoke(self, user: str, doc_id: str) -> None:
        """
        Revoke *user*'s access to *doc_id*.

        NAIVE: does not flush the semantic cache, purge session memory,
        or re-partition the vector index. Call sites in run_demo.py will
        print a banner making this explicit.
        """
        if user in self._grants:
            self._grants[user].discard(doc_id)

    # ── Queries ────────────────────────────────────────────────────────────────

    def has_access(self, user: str, doc_id: str) -> bool:
        """Return True iff *user* currently has access to *doc_id*."""
        return doc_id in self._grants.get(user, set())

    def accessible_docs(self, user: str) -> set[str]:
        """Return a copy of the set of doc_ids *user* currently has access to."""
        return self._grants.get(user, set()).copy()

    # ── Debug ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:  # pragma: no cover
        entries = {u: sorted(ds) for u, ds in self._grants.items()}
        return f"AccessControlStore({entries})"
