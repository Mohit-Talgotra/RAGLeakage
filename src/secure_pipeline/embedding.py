"""
embedding.py -- Text embedders with an on-disk cache for corpus vectors.

- "hash": deterministic hashed bag-of-words (no download, used by tests and smoke runs).
- anything else: a sentence-transformers model name (e.g. all-MiniLM-L6-v2, BAAI/bge-small-en-v1.5).

Corpus chunk embeddings are cached under .cache/embeddings/ keyed by model name and
a hash of the chunk texts, so repeated runs do not re-encode 500+ chunks.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "embeddings"

_TOKEN_RE = re.compile(r"[a-z0-9$%.,-]+")


class HashEmbedder:
    """Signed feature hashing of unigrams and bigrams. L2-normalised. Deterministic."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        toks = [t.strip(".,") for t in _TOKEN_RE.findall(text.lower())]
        toks = [t for t in toks if t]
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        v = np.zeros(self.dim, dtype=np.float32)
        for f in feats:
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
            v[h % self.dim] += 1.0 if (h >> 63) == 0 else -1.0
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim), np.float32)


class STEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer
        self.name = model_name
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float32,
        )


def make_embedder(name: str):
    return HashEmbedder() if name == "hash" else STEmbedder(name)


def encode_cached(embedder, texts: list[str]) -> np.ndarray:
    key = hashlib.sha256(("\x00".join(texts)).encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", embedder.name)
    path = CACHE_DIR / f"{safe}_{key}.npy"
    if path.exists():
        return np.load(path)
    vecs = embedder.encode(texts)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(path, vecs)
    return vecs
