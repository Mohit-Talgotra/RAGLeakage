"""
corpus_loader.py -- Backward-compatible wrapper around corpus.py.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from .corpus import load_corpus, CorpusManager, Document

__all__ = ["load_corpus", "CorpusManager", "Document"]
