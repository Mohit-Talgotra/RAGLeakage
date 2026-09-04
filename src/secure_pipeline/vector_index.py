"""
vector_index.py -- Backward-compatible wrapper around index_store.py.
"""
from __future__ import annotations
from .index_store import SecureVectorIndex, VectorIndex

__all__ = ["SecureVectorIndex", "VectorIndex"]
