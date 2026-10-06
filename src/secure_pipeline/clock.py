"""
clock.py -- The single time source for the testbed.

Every component reads time through a Clock, never through time.time() directly.

- WallClock: real time. sleep() really sleeps; advance() is refused. Use for timing
  experiments where an attacker holds a real stopwatch.
- SimClock: real elapsed compute time plus a virtual offset. sleep() and advance()
  add to the offset instead of blocking. Measured latency therefore equals real
  compute (embedding, vector search, reranking) plus simulated waits (LLM generation,
  latency padding). Use for TTL / ACL-sync experiments that span hours.

Both clocks expose the same API, so the pipeline code path is identical.
"""

from __future__ import annotations

import time


class Clock:
    """Interface: seconds since an arbitrary epoch."""

    def now(self) -> float:
        raise NotImplementedError

    def sleep(self, seconds: float) -> None:
        raise NotImplementedError

    def advance(self, seconds: float) -> None:
        raise NotImplementedError


class WallClock(Clock):
    def now(self) -> float:
        return time.perf_counter()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)

    def advance(self, seconds: float) -> None:
        raise RuntimeError("WallClock cannot jump forward; use SimClock for TTL/sync experiments.")


class SimClock(Clock):
    def __init__(self, start: float = 0.0) -> None:
        self._t0 = time.perf_counter()
        self._offset = start

    def now(self) -> float:
        return self._offset + (time.perf_counter() - self._t0)

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self._offset += seconds

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("time only moves forward")
        self._offset += seconds


def make_clock(kind: str) -> Clock:
    if kind == "wall":
        return WallClock()
    if kind == "sim":
        return SimClock()
    raise ValueError(f"unknown clock {kind!r} (expected 'wall' or 'sim')")
