"""
Process level UTF 8 helpers.

Windows terminals can still expose a legacy stdio encoding such as cp1252. The
demo prints Unicode status markers, so normalise stdout/stderr early at process
startup to avoid UnicodeEncodeError crashes.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO


def configure_utf8_stdio() -> None:
    """Force Python text stdio streams to UTF 8 when the runtime supports it."""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

    for stream in (sys.stdout, sys.stderr):
        _reconfigure_stream(stream)


def _reconfigure_stream(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        # Some wrapped captured streams cannot be reconfigured. They usually
        # already provide their own encoding policy, so leave them alone.
        return
