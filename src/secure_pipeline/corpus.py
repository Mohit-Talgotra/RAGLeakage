"""
corpus.py -- Load the frozen corpus v2 and split documents into chunks.

The corpus is generated once by scripts/generate_corpus.py and committed as
data/corpus.jsonl (documents) and data/iam.json (tenants, users, groups).

Each chunk inherits its document's doc_id, tenant and ACL groups, so authorization
and provenance taint work at document granularity even though retrieval works on chunks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    tenant_id: str
    title: str
    text: str


@dataclass
class Corpus:
    docs: list[dict]
    iam: dict
    chunks: list[Chunk] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.by_id = {d["doc_id"]: d for d in self.docs}

    def doc(self, doc_id: str) -> dict:
        return self.by_id[doc_id]

    def restricted(self, tenants: Optional[list[str]] = None) -> list[dict]:
        return [d for d in self.docs if d["sensitivity"] == "restricted"
                and (tenants is None or d["tenant_id"] in tenants)]

    def tenants(self) -> list[str]:
        return [t["tenant_id"] for t in self.iam["tenants"]]

    def users_of(self, tenant_id: str) -> list[dict]:
        return [u for u in self.iam["users"] if u["tenant_id"] == tenant_id]

    def secrets(self, doc_id: str) -> list[str]:
        """Strings whose appearance in a response proves disclosure: fact values + canary."""
        d = self.by_id[doc_id]
        out = [f["value"] for f in d["facts"]]
        if d.get("canary"):
            out.append(d["canary"])
        return out


def corpus_dir(name: str = "synthetic") -> Path:
    """synthetic: data/ (generate_corpus.py); enron: data/enron/ (build_enron_corpus.py)."""
    return DATA_DIR if name == "synthetic" else DATA_DIR / name


def load_corpus(data_dir: Path = DATA_DIR, chunk_tokens: int = 300) -> Corpus:
    corpus_path = data_dir / "corpus.jsonl"
    if not corpus_path.exists():
        raise FileNotFoundError(f"{corpus_path} missing; run scripts/generate_corpus.py")
    docs = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    iam = json.loads((data_dir / "iam.json").read_text(encoding="utf-8"))
    corpus = Corpus(docs=docs, iam=iam)
    corpus.chunks = [c for d in docs for c in chunk_document(d, chunk_tokens)]
    return corpus


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _approx_tokens(text: str) -> int:
    # WordPiece averages ~1.3 tokens per English word on this corpus.
    return int(len(text.split()) * 1.3) + 1


def chunk_document(doc: dict, chunk_tokens: int = 300) -> list[Chunk]:
    """Greedy sentence packing into ~chunk_tokens chunks. The title prefixes each chunk."""
    sentences = [s for p in doc["text"].split("\n\n") for s in _SENTENCE_RE.split(p.strip()) if s]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for s in sentences:
        n = _approx_tokens(s)
        if current and size + n > chunk_tokens:
            chunks.append(" ".join(current))
            current, size = [], 0
        current.append(s)
        size += n
    if current:
        chunks.append(" ".join(current))
    return [
        Chunk(
            chunk_id=f"{doc['doc_id']}#{i}",
            doc_id=doc["doc_id"],
            tenant_id=doc["tenant_id"],
            title=doc["title"],
            text=f"{doc['title']}\n{body}",
        )
        for i, body in enumerate(chunks)
    ]
