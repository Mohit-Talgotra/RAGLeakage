"""
src/full -- Full Secure Multi-Tenant RAG Testbed Package (§1-§8).
"""

from .access_control import AccessControlManager, AccessControlStore, RevocationEvent
from .attacker import AttackerHarness, AttackerInference, ProbeDefinition, STANDARD_PROBE_SUITE
from .corpus import CorpusManager, Document, load_corpus
from .index_store import SecureVectorIndex, VectorIndex
from .instrumentation import InstrumentationLogger, QueryLogger, StructuredLogRow
from .llm_client import LLMClient
from .metrics import MetricsCalculator, SecurityMetricsReport
from .normalization import MetadataNormalizer, NormalizedMetadata
from .pipeline import SecureRAGPipeline, NaiveRAGPipeline, PipelineQueryResult, QueryResult
from .reranker import CrossEncoderReranker
from .semantic_cache import SecureSemanticCache, SemanticCache, CacheEntry
from .session_memory import SecureSessionMemory, SessionMemory, Turn
from .experiment_runner import ExperimentRunner, ExperimentResult

__all__ = [
    # Access Control
    "AccessControlManager",
    "AccessControlStore",
    "RevocationEvent",
    # Attacker
    "AttackerHarness",
    "AttackerInference",
    "ProbeDefinition",
    "STANDARD_PROBE_SUITE",
    # Corpus
    "CorpusManager",
    "Document",
    "load_corpus",
    # Index
    "SecureVectorIndex",
    "VectorIndex",
    # Instrumentation
    "InstrumentationLogger",
    "QueryLogger",
    "StructuredLogRow",
    # LLM
    "LLMClient",
    # Metrics
    "MetricsCalculator",
    "SecurityMetricsReport",
    # Normalization
    "MetadataNormalizer",
    "NormalizedMetadata",
    # Pipeline
    "SecureRAGPipeline",
    "NaiveRAGPipeline",
    "PipelineQueryResult",
    "QueryResult",
    # Reranker
    "CrossEncoderReranker",
    # Semantic Cache
    "SecureSemanticCache",
    "SemanticCache",
    "CacheEntry",
    # Session Memory
    "SecureSessionMemory",
    "SessionMemory",
    "Turn",
    # Experiment Runner
    "ExperimentRunner",
    "ExperimentResult",
]
