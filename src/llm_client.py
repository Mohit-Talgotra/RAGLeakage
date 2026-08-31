"""
llm_client.py — LLM generation layer with a Gemini backend and a deterministic stub.

Stub mode
---------
If `GEMINI_API_KEY` is absent or the `google-genai` package is not installed, the
client falls back to a deterministic stub that echoes retrieved document content
directly into the response.  This makes the leakage maximally visible even
without a live API key: the stub's output will literally contain the restricted
text verbatim, so any post-revocation or cross-tenant response that includes
it is unambiguous evidence of a leak.

If session memory contains a previous assistant turn (from before revocation),
the stub explicitly surfaces it to simulate the LLM continuing from context.

Public API
----------
    llm = LLMClient(model="gemini-2.5-flash", temperature=0.0)
    response = llm.generate(
        memory_context=[{"role": "user", "content": "..."}, ...],
        retrieved_docs=[("doc_A6", 0.91, "body text...")],
        query="What are the clinical findings of Project Nightingale?",
    )
"""

from __future__ import annotations

import os

# Optional import — falls back to stub if package is missing.
try:
    from google import genai as _genai
    from google.genai import types as _genai_types
    _GEMINI_INSTALLED = True
except ImportError:
    _GEMINI_INSTALLED = False


class LLMClient:
    """
    Thin wrapper that selects Gemini or the deterministic stub at construction time.

    Parameters
    ----------
    model : str
        Gemini model ID (only used when a real client is available).
    temperature : float
        Sampling temperature (0.0 = deterministic, best for reproducibility).
    """

    def __init__(self, model: str = "gemini-2.5-flash", temperature: float = 0.0) -> None:
        self._model = model
        self._temperature = temperature
        api_key = os.getenv("GEMINI_API_KEY", "").strip()

        if _GEMINI_INSTALLED and api_key:
            self._client = _genai.Client(api_key=api_key)
            self._use_stub = False
            print(f"[LLMClient] Using Gemini ({model})")
        else:
            self._client = None
            self._use_stub = True
            reason = "google-genai not installed" if not _GEMINI_INSTALLED else "no GEMINI_API_KEY"
            print(f"[LLMClient] Using deterministic stub ({reason}). "
                  "Leak evidence will still be clearly visible in responses.")

    # ── Public ─────────────────────────────────────────────────────────────────

    def generate(
        self,
        memory_context: list[dict],
        retrieved_docs: list[tuple[str, float, str]],
        query: str,
    ) -> str:
        """
        Generate a response given memory context, retrieved docs, and the query.

        Parameters
        ----------
        memory_context : list[dict]
            Chat-style message history: [{"role": ..., "content": ...}, ...]
        retrieved_docs : list[tuple[str, float, str]]
            (doc_id, cosine_similarity, document_text) — already RBAC-filtered.
            Empty list means the pipeline found no accessible docs.
        query : str
            The user's current question.

        Returns
        -------
        str
            The generated (or stubbed) response text.
        """
        if self._use_stub:
            return self._stub_generate(memory_context, retrieved_docs, query)
        return self._gemini_generate(memory_context, retrieved_docs, query)

    # ── Gemini backend ─────────────────────────────────────────────────────────

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
            f"[Document {i + 1} | id={doc_id} | score={score:.3f}]\n{text}"
            for i, (doc_id, score, text) in enumerate(retrieved_docs)
        )
        return (
            "You are a helpful knowledge-base assistant. "
            "Answer the user's question using ONLY the documents provided below. "
            "Quote specific figures and facts where possible.\n\n"
            f"--- RETRIEVED DOCUMENTS ---\n{doc_block}\n--- END ---"
        )

    def _build_gemini_prompt(
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
        if history:
            return f"{system}\n\n--- CONVERSATION HISTORY ---\n{history}\n\nuser: {query}"
        return f"{system}\n\nuser: {query}"

    def _gemini_generate(
        self,
        memory_context: list[dict],
        retrieved_docs: list[tuple[str, float, str]],
        query: str,
    ) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=self._build_gemini_prompt(memory_context, retrieved_docs, query),
            config=_genai_types.GenerateContentConfig(
                temperature=self._temperature,
            ),
        )
        return (response.text or "").strip()

    # ── Deterministic stub ─────────────────────────────────────────────────────

    def _stub_generate(
        self,
        memory_context: list[dict],
        retrieved_docs: list[tuple[str, float, str]],
        query: str,
    ) -> str:
        """
        Return a response that quotes retrieved doc content verbatim.

        If no docs are accessible but memory contains a prior assistant turn,
        the stub reproduces it (simulating an LLM that continues from context).
        This makes BOTH cache-level and memory-level leakage unambiguous in logs.
        """
        # ── Case 1: accessible docs provided → quote them directly ─────────────
        if retrieved_docs:
            parts = []
            for doc_id, score, text in retrieved_docs:
                excerpt = text.replace("\n", " ").strip()
                parts.append(f"[From {doc_id} (sim={score:.3f})]: {excerpt}")
            body = "\n\n".join(parts)
            return f"[STUB RESPONSE] Based on the retrieved documents:\n\n{body}"

        # ── Case 2: no accessible docs, but memory has prior assistant turns ────
        prior_answers = [
            m["content"]
            for m in memory_context
            if m.get("role") == "assistant"
        ]
        if prior_answers:
            last = prior_answers[-1]
            return (
                "[STUB RESPONSE — memory-assisted] "
                "Drawing on our earlier conversation:\n\n"
                + last
            )

        # ── Case 3: truly empty — no docs, no useful memory ────────────────────
        return (
            "[STUB RESPONSE] I have no relevant information about that topic "
            "in the knowledge base."
        )
