"""
rbac.py -- Backward-compatible wrapper around access_control.py.
"""
from __future__ import annotations
from .access_control import AccessControlManager, AccessControlStore, RevocationEvent

__all__ = ["AccessControlManager", "AccessControlStore", "RevocationEvent"]
