"""
llm_client.py -- Generation backends with a disk cache and no silent fallback.

Backends (chosen explicitly; never inferred from which env var happens to be set):
- stub   : deterministic extractive generator with a simulated latency model. Offline.
- groq   : Groq SDK, GROQ_API_KEY            (default model openai/gpt-oss-120b)
- openai : OpenAI SDK, OPENAI_API_KEY        (default model gpt-4o-mini)
- gemini : google-genai, GEMINI_API_KEY      (default model gemini-2.5-flash)
- ollama : OpenAI-compatible local server at OLLAMA_BASE_URL (default http://localhost:11434/v1)

Any API error raises after a few retries. A run therefore never mixes real and stub
generations.

Real-backend generations are cached on disk under .cache/llm/, keyed by
hash(backend, model, temperature, messages). The cache also stores the measured
generation latency; a cache hit sleeps that long on the shared Clock, so reruns are
free, identical, and keep their timing shape.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .clock import Clock
from .session_memory import strip_prefixes

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "llm"

DEFAULT_MODELS = {
    "stub": "stub-extractive-v1",
    "groq": "openai/gpt-oss-120b",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
    "ollama": "llama3.1:8b",
}

_STOP = set("""a an the of to in on for and or is are was were be been what which who whom how when
where why does do did can could would should will with from by at as about that this these those it its
there their they them our your you i me my we us any some tell give show me please summarise summarize
details detail project""".split())
_WORD = re.compile(r"[a-z0-9$%.,-]+")
_SENT = re.compile(r"(?<=[.!?])\s+")


def _content_words(text: str) -> set[str]:
    return {w.strip(".,") for w in _WORD.findall(text.lower())} - _STOP - {""}


@dataclass(frozen=True)
class Generation:
    text: str
    latency_s: float
    model: str
    cached: bool


@dataclass(frozen=True)
class MemoryItem:
    role: str      # "user" | "assistant" | "summary"
    content: str


class LLMClient:
    def __init__(self, backend: str, clock: Clock, rng: random.Random, model: Optional[str] = None,
                 temperature: float = 0.0, use_cache: bool = True) -> None:
        if backend not in DEFAULT_MODELS:
            raise ValueError(f"unknown LLM backend {backend!r}; choose from {sorted(DEFAULT_MODELS)}")
        self.backend = backend
        self.model = model or os.getenv("LLM_MODEL") or DEFAULT_MODELS[backend]
        self.temperature = temperature
        self.clock = clock
        self.rng = rng
        self.use_cache = use_cache
        self._client = None
        if backend != "stub":
            self._client = self._connect()

    @property
    def model_id(self) -> str:
        return f"{self.backend}/{self.model}"

    def _connect(self):
        if self.backend == "groq":
            from groq import Groq
            return Groq(api_key=_require_env("GROQ_API_KEY"), max_retries=8)  # free tier: 429s honour retry-after
        if self.backend == "openai":
            from openai import OpenAI
            return OpenAI(api_key=_require_env("OPENAI_API_KEY"))
        if self.backend == "ollama":
            from openai import OpenAI
            return OpenAI(api_key="ollama", base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
        if self.backend == "gemini":
            from google import genai
            return genai.Client(api_key=_require_env("GEMINI_API_KEY"))
        raise AssertionError(self.backend)

    # ---- RAG generation -----------------------------------------------------

    def answer(self, query: str, docs: list[tuple[str, str]], memory: list[MemoryItem],
               refusal: str) -> Generation:
        """docs: [(title, text)] authorized for this request. refusal: exact text to use if unanswerable."""
        if self.backend == "stub":
            return self._stub_answer(query, docs, memory, refusal)
        return self.complete(build_messages(query, docs, memory, refusal))

    def complete(self, messages: list[dict]) -> Generation:
        """Raw chat completion with disk cache and timing replay."""
        if self.backend == "stub":
            raise RuntimeError("stub backend has no free-form completion; use a real backend")
        key = hashlib.sha256(json.dumps(
            [self.backend, self.model, self.temperature, messages], sort_keys=True).encode()).hexdigest()
        path = CACHE_DIR / key[:2] / f"{key}.json"
        if self.use_cache and path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            self.clock.sleep(rec["latency_s"])
            return Generation(rec["text"], rec["latency_s"], self.model_id, cached=True)
        t0 = time.perf_counter()
        text = self._call_with_retry(messages)
        latency = time.perf_counter() - t0
        if self.use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": self.model_id, "text": text, "latency_s": latency}),
                            encoding="utf-8")
        return Generation(text, latency, self.model_id, cached=False)

    def _call_with_retry(self, messages: list[dict], attempts: int = 4) -> str:
        for i in range(attempts):
            try:
                return self._call(messages)
            except Exception as exc:  # noqa: BLE001 -- re-raised below
                if i == attempts - 1:
                    raise RuntimeError(f"LLM backend {self.model_id} failed: {exc}") from exc
                time.sleep(2 ** i)
        raise AssertionError("unreachable")

    def _call(self, messages: list[dict]) -> str:
        if self.backend == "gemini":
            from google.genai import types
            system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
            contents = [types.Content(role="model" if m["role"] == "assistant" else "user",
                                      parts=[types.Part(text=m["content"])])
                        for m in messages if m["role"] != "system"]
            resp = self._client.models.generate_content(
                model=self.model, contents=contents,
                config=types.GenerateContentConfig(system_instruction=system, temperature=self.temperature))
            return (resp.text or "").strip()
        resp = self._client.chat.completions.create(
            model=self.model, messages=messages, temperature=self.temperature)
        return (resp.choices[0].message.content or "").strip()

    # ---- Stub ---------------------------------------------------------------

    def _stub_answer(self, query: str, docs: list[tuple[str, str]], memory: list[MemoryItem],
                     refusal: str) -> Generation:
        # The stub treats every document and every earlier answer as one context unit,
        # answers from the unit that best matches the question (>= 2 shared content
        # words), and otherwise emits the exact refusal it was instructed to use. This
        # models an LLM that uses its whole context window, including chat history.
        q = _content_words(query)
        units = [(f"According to {title}: ", body.removeprefix(title).strip()) for title, body in docs]
        units += [("From our earlier conversation: ", m.content) for m in memory
                  if m.role != "user" and not m.content.startswith(refusal)]
        text = refusal
        best = max(units, key=lambda u: len(q & _content_words(u[1])), default=None)
        if best is not None and len(q & _content_words(best[1])) >= 2:
            sents = [strip_prefixes(s) for s in _SENT.split(best[1].replace("\n", " "))]
            sents = list(dict.fromkeys(s for s in sents if s))
            ranked = sorted(range(len(sents)), key=lambda i: (
                -(2 * len(q & _content_words(sents[i])) + 2 * any(ch.isdigit() for ch in sents[i])), i))
            text = best[0] + " ".join(sents[i] for i in sorted(ranked[:4]))
        prompt_tokens = sum(len(b.split()) for _, b in docs) + sum(len(m.content.split()) for m in memory)
        out_tokens = len(text.split()) * 1.3
        latency = (0.35 + 0.015 * out_tokens + 0.0002 * prompt_tokens) * math.exp(self.rng.gauss(0.0, 0.15))
        self.clock.sleep(latency)
        return Generation(text, latency, self.model_id, cached=False)


def build_messages(query: str, docs: list[tuple[str, str]], memory: list[MemoryItem], refusal: str) -> list[dict]:
    doc_block = "\n\n".join(f"[{i + 1}] {title}\n{text}" for i, (title, text) in enumerate(docs)) or "(none)"
    system = (
        "You are an enterprise knowledge-base assistant. Answer using only the documents below "
        "and the conversation so far. Quote exact figures. If they do not contain the answer, "
        f"reply with exactly this sentence and nothing else: \"{refusal}\"\n\n"
        f"--- DOCUMENTS ---\n{doc_block}\n--- END ---"
    )
    messages = [{"role": "system", "content": system}]
    for m in memory:
        if m.role == "summary":
            messages.append({"role": "system", "content": m.content})
        else:
            messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": query})
    return messages


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set (put it in .env or export it)")
    return value
