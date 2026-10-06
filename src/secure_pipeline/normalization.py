"""
normalization.py -- Metadata normalization (threats T4-T7) and constant-shape responses.

- Score quantization (T4, T5): continuous scores -> coarse band values.
- Refusal text (T7): distinct "access denied" vs "not found" wording unless uniform.
- Latency padding (T6): computes how long to wait so the response leaves on a fixed
  shape. The pipeline sleeps on the shared Clock, so padding is real wall-clock time
  under WallClock and real virtual time under SimClock. Strategies:
    bucket   : round elapsed time up to the next multiple of pad_ms (constant-shape)
    deadline : release every response at pad_ms (responses slower than that leak)
    floor    : legacy max(elapsed, pad_ms) + jitter; does nothing against a ~1 s LLM
"""

from __future__ import annotations

import math
import random

UNIFORM_REFUSAL = "I can't help with that request based on the information available to you."
NOT_FOUND_REFUSAL = "I couldn't find any documents about that topic in the knowledge base."
ACCESS_DENIED_REFUSAL = "Some documents match your question, but you do not have permission to view them."

_BANDS = [(0.05, 0.0), (0.40, 0.25), (0.70, 0.50), (math.inf, 0.85)]


def quantize(score: float) -> float:
    for upper, value in _BANDS:
        if score < upper:
            return value
    return _BANDS[-1][1]


def refusal_text(reason: str, uniform: bool) -> str:
    if uniform:
        return UNIFORM_REFUSAL
    return ACCESS_DENIED_REFUSAL if reason == "access_denied" else NOT_FOUND_REFUSAL


def pad_seconds(elapsed_s: float, strategy: str, pad_ms: float, rng: random.Random) -> float:
    """Extra seconds to wait so the response is released on the padding schedule."""
    pad_s = pad_ms / 1000.0
    if strategy == "bucket":
        target = math.ceil(elapsed_s / pad_s) * pad_s if elapsed_s > 0 else pad_s
    elif strategy == "deadline":
        target = max(elapsed_s, pad_s)
    elif strategy == "floor":
        target = max(elapsed_s, pad_s) + rng.uniform(0.005, 0.020)
    else:
        raise ValueError(strategy)
    return max(0.0, target - elapsed_s)
