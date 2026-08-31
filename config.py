"""
config.py Central configuration for the RAG Leakage MVP.

All pipeline knobs in one place so the demo is reproducible and easy to tune.
"""
from pathlib import Path

BASE_DIR    = Path(__file__).parent
CORPUS_DIR  = BASE_DIR / "corpus"
CHROMA_DIR  = BASE_DIR / ".chroma"
RESULTS_DIR = BASE_DIR / "results"

# Embedding
# Local offline model with no API key required.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Vector index
TOP_K = 5           # number of nearest neighbour docs returned per query

# Semantic cache
# Intentionally long TTL and low threshold so the leakage window is clearly visible.
CACHE_TTL_SECONDS  = 3600   # 1 hour naive no eviction on revoke
CACHE_SIM_THRESHOLD = 0.70  # cosine similarity floor for a cache hit
                             # (0.70 catches paraphrases; real prod caches use ~0.92)

# Session memory
MEMORY_MAX_TURNS = 20   # large buffer naive never purged on revocation

# LLM
LLM_MODEL       = "gemini-2.5-flash"
LLM_TEMPERATURE = 0.0   # deterministic for reproducibility
