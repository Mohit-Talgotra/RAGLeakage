"""
corpus_loader.py Reads synthetic corpus files from disk.

Each document is a plain text file with a YAML frontmatter block
that carries metadata. Example:

    yaml marker
    doc_id: doc_A6
    tenant_id: tenant_alpha
    restricted: true
    title: Project Nightingale ...
    yaml marker

    Body text starts here ...

Returns a list of dicts:
    {
        "doc_id":    str,
        "tenant_id": str,
        "restricted": bool,
        "title":     str,
        "text":      str,   # body only frontmatter stripped
    }
"""

import re
from pathlib import Path

import yaml

# Matches the YAML block between the first pair of marker lines.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def load_corpus(corpus_dir: Path) -> list[dict]:
    """Load all .txt documents from corpus_dir recursively."""
    docs: list[dict] = []

    for tenant_dir in sorted(corpus_dir.iterdir()):
        if not tenant_dir.is_dir():
            continue
        for doc_file in sorted(tenant_dir.glob("*.txt")):
            raw = doc_file.read_text(encoding="utf-8")
            meta, body = _parse(raw, doc_file)
            docs.append(
                {
                    "doc_id": meta.get("doc_id", doc_file.stem),
                    "tenant_id": meta.get("tenant_id", tenant_dir.name),
                    "restricted": bool(meta.get("restricted", False)),
                    "title": meta.get("title", ""),
                    "text": body,
                }
            )

    return docs


def _parse(raw: str, path: Path) -> tuple[dict, str]:
    """Split a document into (frontmatter_dict, body_text)."""
    m = _FRONTMATTER_RE.match(raw)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Bad frontmatter in {path}: {exc}") from exc
        body = raw[m.end():].strip()
    else:
        meta = {}
        body = raw.strip()
    return meta, body
