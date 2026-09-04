"""
rag_pipeline.py -- Backward-compatible wrapper around pipeline.py.
"""
from __future__ import annotations
from .pipeline import SecureRAGPipeline, NaiveRAGPipeline, PipelineQueryResult, QueryResult

__all__ = ["SecureRAGPipeline", "NaiveRAGPipeline", "PipelineQueryResult", "QueryResult"]
