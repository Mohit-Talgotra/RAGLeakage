"""
llm_client.py -- LLM generation layer supporting Groq (including Prompt Guard & Chat models).
"""

from __future__ import annotations

import os
from typing import Optional

# Optional imports for various backends
_GROQ_INSTALLED = False
try:
    from groq import Groq as _GroqClient
    _GROQ_INSTALLED = True
except ImportError:
    _GroqClient = None

_OPENAI_INSTALLED = False
try:
    from openai import OpenAI as _OpenAIClient
    _OPENAI_INSTALLED = True
except ImportError:
    _OpenAIClient = None

_GEMINI_INSTALLED = False
try:
    from google import genai as _genai
    from google.genai import types as _genai_types
    _GEMINI_INSTALLED = True
except ImportError:
    _genai = None


class LLMClient:
    """
    Unified LLM Client supporting Groq, OpenAI, Gemini, and deterministic stub.
    """

    DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
    DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
    DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

    def __init__(self, model: Optional[str] = None, temperature: float = 0.0) -> None:
        self._temperature = temperature
        self._backend = "stub"
        self._client = None

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

        # 1. Prioritize Groq
        if groq_key:
            self._model = model or os.getenv("LLM_MODEL") or self.DEFAULT_GROQ_MODEL
            if _GROQ_INSTALLED and _GroqClient is not None:
                self._client = _GroqClient(api_key=groq_key)
                self._backend = "groq"
                print(f"[LLMClient] Using Groq ({self._model}) via groq SDK")
            elif _OPENAI_INSTALLED and _OpenAIClient is not None:
                self._client = _OpenAIClient(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
                self._backend = "groq_openai"
                print(f"[LLMClient] Using Groq ({self._model}) via openai compatibility")
            else:
                print("[LLMClient] GROQ_API_KEY found, but neither 'groq' nor 'openai' package is installed. Falling back to stub.")

        # 2. Fallback to OpenAI
        if self._backend == "stub" and openai_key and _OPENAI_INSTALLED and _OpenAIClient is not None:
            self._model = model or self.DEFAULT_OPENAI_MODEL
            self._client = _OpenAIClient(api_key=openai_key)
            self._backend = "openai"
            print(f"[LLMClient] Using OpenAI ({self._model})")

        # 3. Fallback to Gemini
        if self._backend == "stub" and gemini_key and _GEMINI_INSTALLED and _genai is not None:
            self._model = model or self.DEFAULT_GEMINI_MODEL
            self._client = _genai.Client(api_key=gemini_key)
            self._backend = "gemini"
            print(f"[LLMClient] Using Gemini ({self._model})")

        # 4. Fallback to Deterministic Stub
        if self._backend == "stub":
            self._model = model or "deterministic-stub"
            print(f"[LLMClient] Using deterministic stub. Leak evidence will remain clearly visible in responses.")

    def generate(
        self,
        memory_context: list[dict],
        retrieved_docs: list[tuple[str, float, str]],
        query: str,
    ) -> str:
        if self._backend in ("groq", "groq_openai", "openai"):
            return self._chat_completions_generate(memory_context, retrieved_docs, query)
        elif self._backend == "gemini":
            return self._gemini_generate(memory_context, retrieved_docs, query)
        return self._stub_generate(memory_context, retrieved_docs, query)

    def _is_guard_model(self) -> bool:
        m = self._model.lower()
        return "guard" in m or "classification" in m

    def _build_system_prompt(
        self, retrieved_docs: list[tuple[str, float, str]]
    ) -> str:
        if not retrieved_docs:
            return (
                "You are a helpful knowledge-base assistant. "
                "You have no relevant documents for this query. "
                "If the user's prior messages contain relevant information, "
                "you may reference them. Otherwise, say you don't have "
                "the information available."
            )
        doc_block = "\n\n".join(
            f"[Document {i + 1} | id={doc_id} | score={score:.3f}]\n{text[:600]}"
            for i, (doc_id, score, text) in enumerate(retrieved_docs)
        )
        return (
            "You are a helpful knowledge-base assistant. "
            "Answer the user's question using ONLY the documents provided below. "
            "Quote specific figures and facts where possible.\n\n"
            f"--- RETRIEVED DOCUMENTS ---\n{doc_block}\n--- END ---"
        )

    def _chat_completions_generate(
        self,
        memory_context: list[dict],
        retrieved_docs: list[tuple[str, float, str]],
        query: str,
    ) -> str:
        # Prompt Guard models require a single user message and strictly <= 512 tokens (~1000 chars)
        if self._is_guard_model():
            clean_query = query.strip()[:800]
            messages = [{"role": "user", "content": clean_query}]
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=self._temperature,
                )
                guard_output = (response.choices[0].message.content or "").strip()
                return self._compose_rag_response(retrieved_docs, memory_context, guard_output)
            except Exception as exc:
                print(f"[LLMClient] Groq error on guard model: {exc}. Falling back to deterministic RAG synthesis.")
                return self._stub_generate(memory_context, retrieved_docs, query)

        system_prompt = self._build_system_prompt(retrieved_docs)
        messages = [{"role": "system", "content": system_prompt}]
        for turn in memory_context[-6:]:
            messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")[:500]})
        messages.append({"role": "user", "content": query[:500]})

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            print(f"[LLMClient] API error ({self._backend}): {exc}. Falling back to deterministic RAG synthesis.")
            return self._stub_generate(memory_context, retrieved_docs, query)

    def _compose_rag_response(
        self,
        retrieved_docs: list[tuple[str, float, str]],
        memory_context: list[dict],
        guard_output: str,
    ) -> str:
        if retrieved_docs:
            parts = []
            for doc_id, score, text in retrieved_docs:
                clean = text.replace("\n", " ").strip()
                parts.append(f"[{doc_id}]: {clean}")
            return f"Based on retrieved documentation:\n\n" + "\n\n".join(parts)

        prior_answers = [
            m["content"] for m in memory_context if m.get("role") == "assistant"
        ]
        if prior_answers:
            return "[Drawing on earlier conversation]: " + prior_answers[-1]

        return "I don't have access to information answering that question."

    def _gemini_generate(
        self,
        memory_context: list[dict],
        retrieved_docs: list[tuple[str, float, str]],
        query: str,
    ) -> str:
        system = self._build_system_prompt(retrieved_docs)
        history = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in memory_context
        )
        prompt = f"{system}\n\n--- CONVERSATION HISTORY ---\n{history}\n\nuser: {query}" if history else f"{system}\n\nuser: {query}"

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=_genai_types.GenerateContentConfig(
                    temperature=self._temperature,
                ),
            )
            return (response.text or "").strip()
        except Exception as exc:
            print(f"[LLMClient] Gemini error: {exc}. Falling back to stub.")
            return self._stub_generate(memory_context, retrieved_docs, query)

    def _stub_generate(
        self,
        memory_context: list[dict],
        retrieved_docs: list[tuple[str, float, str]],
        query: str,
    ) -> str:
        if retrieved_docs:
            parts = []
            for doc_id, score, text in retrieved_docs:
                excerpt = text.replace("\n", " ").strip()
                parts.append(f"[From {doc_id} (sim={score:.3f})]: {excerpt}")
            body = "\n\n".join(parts)
            return f"[STUB RESPONSE] Based on the retrieved documents:\n\n{body}"

        prior_answers = [
            m["content"]
            for m in memory_context
            if m.get("role") == "assistant"
        ]
        if prior_answers:
            return (
                "[STUB RESPONSE -- memory-assisted] "
                "Drawing on our earlier conversation:\n\n"
                + prior_answers[-1]
            )

        return (
            "[STUB RESPONSE] I have no relevant information about that topic "
            "in the knowledge base."
        )
