"""
access_control.py -- Multi-tenant Access Control Manager with Revocation Event Bus.

Design (§3.2, §5.1):
- Role-Based Access Control (RBAC) mapping users to roles and roles to tenant document sets.
- Direct document grants and role grants.
- Supports 3 revocation event types:
  1. single_doc: revoke(user_id, doc_id)
  2. role: revoke_role(user_id, role)
  3. user_offboard: offboard_user(user_id)
- Event Bus / Listener pattern:
  - In baseline mode: updates RBAC store only (leaky baseline).
  - In mitigated mode: triggers registered invalidation listeners (Cache, Index, Memory).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class RevocationEvent:
    """Represents an ACCESS_REVOKED lifecycle event."""
    event_type: str                  # "single_doc" | "role" | "user_offboard"
    user_id: str
    tenant_id: Optional[str] = None
    doc_ids: list[str] = field(default_factory=list)
    role: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


# Type alias for invalidation callbacks
InvalidationListener = Callable[[RevocationEvent], None]


class AccessControlManager:
    """
    Enterprise Multi-Tenant Access Control Manager with RBAC and Event Publishing.

    Parameters
    ----------
    mode : str
        "baseline" (silent RBAC updates without invalidation notifications) or
        "mitigated" (publishes RevocationEvents to registered listeners).
    """

    def __init__(self, mode: str = "baseline") -> None:
        self.mode = mode
        # user_id -> set of direct doc_ids
        self._user_doc_grants: dict[str, set[str]] = {}
        # user_id -> set of doc_ids explicitly revoked from that user.
        # These deny entries override role grants for single-document revocation tests.
        self._user_doc_denies: dict[str, set[str]] = {}
        # user_id -> set of role names
        self._user_roles: dict[str, set[str]] = {}
        # role_name -> set of doc_ids
        self._role_docs: dict[str, set[str]] = {}
        # user_id -> primary tenant_id
        self._user_tenants: dict[str, str] = {}
        # Registered invalidation event listeners
        self._listeners: list[InvalidationListener] = []
        # Audit log of revocation events
        self._revocation_history: list[RevocationEvent] = []

    # ---- Configuration & Setup ----------------------------------------------

    def register_listener(self, listener: InvalidationListener) -> None:
        """Register a component callback (e.g. Cache, Memory) for revocation events."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def set_user_tenant(self, user_id: str, tenant_id: str) -> None:
        self._user_tenants[user_id] = tenant_id

    def get_user_tenant(self, user_id: str) -> Optional[str]:
        return self._user_tenants.get(user_id)

    def define_role(self, role: str, doc_ids: list[str]) -> None:
        """Define a role and its permitted doc_ids."""
        self._role_docs.setdefault(role, set()).update(doc_ids)

    # ---- Grants -------------------------------------------------------------

    def grant(self, user_id: str, doc_id: str) -> None:
        """Grant a user direct access to a document."""
        self._user_doc_grants.setdefault(user_id, set()).add(doc_id)
        self._user_doc_denies.setdefault(user_id, set()).discard(doc_id)

    def grant_role(self, user_id: str, role: str) -> None:
        """Assign a role to a user."""
        self._user_roles.setdefault(user_id, set()).add(role)

    # ---- Revocations (§5.1: 3 Revocation Types) -------------------------------

    def revoke(self, user_id: str, doc_id: str) -> RevocationEvent:
        """
        Type 1: Single-document revocation.
        Revokes user access to specific doc_id.
        """
        if user_id in self._user_doc_grants:
            self._user_doc_grants[user_id].discard(doc_id)
        self._user_doc_denies.setdefault(user_id, set()).add(doc_id)

        tenant = self._user_tenants.get(user_id)
        event = RevocationEvent(
            event_type="single_doc",
            user_id=user_id,
            tenant_id=tenant,
            doc_ids=[doc_id],
        )
        self._process_revocation(event)
        return event

    def revoke_role(self, user_id: str, role: str) -> RevocationEvent:
        """
        Type 2: Role revocation.
        Revokes an assigned role and all documents associated exclusively with that role.
        """
        affected_docs = list(self._role_docs.get(role, set()))
        if user_id in self._user_roles:
            self._user_roles[user_id].discard(role)

        tenant = self._user_tenants.get(user_id)
        event = RevocationEvent(
            event_type="role",
            user_id=user_id,
            tenant_id=tenant,
            doc_ids=affected_docs,
            role=role,
        )
        self._process_revocation(event)
        return event

    def offboard_user(self, user_id: str) -> RevocationEvent:
        """
        Type 3: Full user offboarding.
        Revokes all direct document grants and all roles for the user.
        """
        all_accessible = list(self.accessible_docs(user_id))
        self._user_doc_grants.pop(user_id, None)
        self._user_doc_denies.pop(user_id, None)
        self._user_roles.pop(user_id, None)
        tenant = self._user_tenants.pop(user_id, None)

        event = RevocationEvent(
            event_type="user_offboard",
            user_id=user_id,
            tenant_id=tenant,
            doc_ids=all_accessible,
        )
        self._process_revocation(event)
        return event

    def _process_revocation(self, event: RevocationEvent) -> None:
        """Log event and dispatch to listeners if in mitigated mode."""
        self._revocation_history.append(event)
        if self.mode == "mitigated":
            for listener in self._listeners:
                try:
                    listener(event)
                except Exception as exc:
                    print(f"[AccessControl] Error in revocation listener: {exc}")

    # ---- Queries ------------------------------------------------------------

    def has_access(self, user_id: str, doc_id: str) -> bool:
        """Check if user currently has access directly or through roles."""
        if doc_id in self._user_doc_denies.get(user_id, set()):
            return False
        # Direct grant check
        if doc_id in self._user_doc_grants.get(user_id, set()):
            return True
        # Role-based check
        for role in self._user_roles.get(user_id, set()):
            if doc_id in self._role_docs.get(role, set()):
                return True
        return False

    def accessible_docs(self, user_id: str) -> set[str]:
        """Return full set of doc_ids accessible to user."""
        docs = self._user_doc_grants.get(user_id, set()).copy()
        for role in self._user_roles.get(user_id, set()):
            docs.update(self._role_docs.get(role, set()))
        return docs - self._user_doc_denies.get(user_id, set())

    def last_revocation_time(self, user_id: Optional[str] = None) -> Optional[float]:
        """Return the timestamp of the latest revocation event."""
        if not self._revocation_history:
            return None
        if user_id is None:
            return self._revocation_history[-1].timestamp
        for ev in reversed(self._revocation_history):
            if ev.user_id == user_id:
                return ev.timestamp
        return None

    def revocation_history(self) -> list[RevocationEvent]:
        return list(self._revocation_history)


# Alias for backward compatibility
AccessControlStore = AccessControlManager
