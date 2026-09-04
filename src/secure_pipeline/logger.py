"""
logger.py -- Backward-compatible wrapper around instrumentation.py.
"""
from __future__ import annotations
from .instrumentation import InstrumentationLogger, QueryLogger, StructuredLogRow

__all__ = ["InstrumentationLogger", "QueryLogger", "StructuredLogRow"]
