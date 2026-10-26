"""
access_control.py -- The live IAM system and its ACCESS_REVOKED event bus.

This is the source of truth for permissions. It changes instantly. Everything derived
from it (index ACL metadata, cache entries, memory turns) changes only when a
propagation mechanism runs: an event listener, a periodic sync, or a lazy check.

Model:
- users belong to one tenant and to groups (e.g. t1_all, t1_staff, t1_finance)
- documents list the groups that may read them (doc ACL)
- per-user denies override group grants (single-document revocation)

Revocation types (§5.1):
1. single_doc    : revoke(user, doc_id)       -> add a deny entry
2. role          : revoke_role(user, group)   -> remove the user from a group
3. user_offboard : offboard_user(user)        -> remove the user from every group
4. mover         : move_user(user, old, new)  -> department transfer: leave one group, join
                   another. The user keeps an active account (unlike offboarding, where SSO
                   would normally end the session), so this is the realistic "leaver of a
                   role who still queries" case.
5. reclassify    : reclassify(doc, group)     -> remove a group from a document's ACL. Every
                   user who loses the document gets their own event (and epoch bump).

Delivery: listeners subscribed with lossy=True (eager cache and memory hooks) miss each event
with probability hook_drop, as webhook or message-bus consumers do. Read-time checks are not
listeners, so they cannot miss anything.

Every revocation also bumps the user's permission epoch, read live by the epoch-invalidation
defense (mitigations.epoch_invalidation).

Listeners are always notified; which components subscribe is decided by the
pipeline from its Mitigations and SyncPolicy, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .clock import Clock


@dataclass(frozen=True)
class RevocationEvent:
    """One ACCESS_REVOKED lifecycle event."""
    event_type: str                   # "single_doc" | "role" | "user_offboard" | "mover" | "reclassify"
    user_id: str
    tenant_id: Optional[str]
    doc_ids: frozenset[str]           # docs the user could read before and cannot read now
    timestamp: float
    group: Optional[str] = None


Listener = Callable[[RevocationEvent], None]


class AccessControlManager:
    def __init__(self, clock: Clock, hook_drop: float = 0.0, rng=None) -> None:
        self.clock = clock
        self.hook_drop, self._rng = hook_drop, rng
        self._lossy: list[Listener] = []
        self.dropped_hooks = 0
        self._user_tenant: dict[str, str] = {}
        self._user_groups: dict[str, set[str]] = {}
        self._user_denies: dict[str, set[str]] = {}
        self._doc_groups: dict[str, frozenset[str]] = {}
        self._listeners: list[Listener] = []
        self._history: list[RevocationEvent] = []
        self._epoch: dict[str, int] = {}

    # ---- Setup --------------------------------------------------------------

    @classmethod
    def from_iam(cls, iam: dict, docs: list[dict], clock: Clock, hook_drop: float = 0.0,
                 rng=None) -> "AccessControlManager":
        acm = cls(clock, hook_drop, rng)
        for u in iam["users"]:
            acm.add_user(u["user_id"], u["tenant_id"], u["groups"])
        for d in docs:
            acm.set_doc_acl(d["doc_id"], d["acl_groups"])
        return acm

    def add_user(self, user_id: str, tenant_id: str, groups: list[str]) -> None:
        self._user_tenant[user_id] = tenant_id
        self._user_groups[user_id] = set(groups)
        self._user_denies.setdefault(user_id, set())

    def set_doc_acl(self, doc_id: str, groups: list[str]) -> None:
        self._doc_groups[doc_id] = frozenset(groups)

    def subscribe(self, listener: Listener, lossy: bool = False) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)
        if lossy and listener not in self._lossy:
            self._lossy.append(listener)

    # ---- Queries ------------------------------------------------------------

    def users(self) -> list[str]:
        return sorted(self._user_tenant)

    def tenant_of(self, user_id: str) -> Optional[str]:
        return self._user_tenant.get(user_id)

    def groups_of(self, user_id: str) -> set[str]:
        return set(self._user_groups.get(user_id, set()))

    def has_access(self, user_id: str, doc_id: str) -> bool:
        if user_id not in self._user_tenant:
            return False
        if doc_id in self._user_denies.get(user_id, set()):
            return False
        return bool(self._doc_groups.get(doc_id, frozenset()) & self._user_groups.get(user_id, set()))

    def holds_all(self, user_id: str, doc_ids) -> bool:
        return all(self.has_access(user_id, d) for d in doc_ids)

    def epoch(self, user_id: str) -> int:
        """Number of revocations this user has had; any derived artifact older than that is stale."""
        return self._epoch.get(user_id, 0)

    def accessible_docs(self, user_id: str) -> set[str]:
        return {d for d in self._doc_groups if self.has_access(user_id, d)}

    def users_with_access(self, doc_id: str) -> set[str]:
        return {u for u in self._user_tenant if self.has_access(u, doc_id)}

    def history(self) -> list[RevocationEvent]:
        return list(self._history)

    def last_revocation_time(self, user_id: str) -> Optional[float]:
        for ev in reversed(self._history):
            if ev.user_id == user_id:
                return ev.timestamp
        return None

    # ---- Revocations --------------------------------------------------------

    def revoke(self, user_id: str, doc_id: str) -> RevocationEvent:
        before = self.accessible_docs(user_id)
        self._user_denies.setdefault(user_id, set()).add(doc_id)
        return self._emit("single_doc", user_id, before)

    def revoke_role(self, user_id: str, group: str) -> RevocationEvent:
        before = self.accessible_docs(user_id)
        self._user_groups.get(user_id, set()).discard(group)
        return self._emit("role", user_id, before, group=group)

    def offboard_user(self, user_id: str) -> RevocationEvent:
        before = self.accessible_docs(user_id)
        self._user_groups[user_id] = set()
        return self._emit("user_offboard", user_id, before)

    def move_user(self, user_id: str, old_group: str, new_group: str) -> RevocationEvent:
        before = self.accessible_docs(user_id)
        groups = self._user_groups.setdefault(user_id, set())
        groups.discard(old_group)
        groups.add(new_group)
        return self._emit("mover", user_id, before, group=old_group)

    def reclassify(self, doc_id: str, group: str) -> list[RevocationEvent]:
        """Remove a group from a document's ACL; every user who loses access gets an event."""
        before = {u: self.accessible_docs(u) for u in sorted(self._user_tenant)}
        self._doc_groups[doc_id] = self._doc_groups.get(doc_id, frozenset()) - {group}
        return [self._emit("reclassify", u, b, group=group)
                for u, b in before.items() if b - self.accessible_docs(u)]

    def restore(self, user_id: str, doc_id: Optional[str] = None, group: Optional[str] = None) -> None:
        """Undo a revocation (used between trials). Emits nothing."""
        if doc_id is not None:
            self._user_denies.get(user_id, set()).discard(doc_id)
        if group is not None:
            self._user_groups.setdefault(user_id, set()).add(group)

    def _emit(self, event_type: str, user_id: str, before: set[str], group: Optional[str] = None) -> RevocationEvent:
        lost = frozenset(before - self.accessible_docs(user_id))
        event = RevocationEvent(
            event_type=event_type,
            user_id=user_id,
            tenant_id=self._user_tenant.get(user_id),
            doc_ids=lost,
            timestamp=self.clock.now(),
            group=group,
        )
        self._history.append(event)
        self._epoch[user_id] = self._epoch.get(user_id, 0) + 1
        for listener in self._listeners:
            if listener in self._lossy and self.hook_drop and self._rng.random() < self.hook_drop:
                self.dropped_hooks += 1
                continue
            listener(event)
        return event
