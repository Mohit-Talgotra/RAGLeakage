# RAG Leakage MVP

Proof-of-concept demonstrating temporal and side-channel leakage in a
**naive multi-tenant RAG pipeline** — no mitigations, deliberately vulnerable.

---

## What this shows

| Leakage class | Surface | Step |
|---|---|---|
| **Temporal (cache)** | Semantic cache returns pre-revocation response without re-checking RBAC | 4, 5 |
| **Content leak (cross-tenant)** | Attacker receives alice's cached response containing D's restricted content | 6 |
| **Side-channel** | Refusal type / similarity score / latency differ between "D exists" and "topic absent" | 8 |

---

## Repository layout

```
RAGLeakage/
├── corpus/
│   ├── tenant_alpha/          # Meridian Corp (6 docs, 3 restricted)
│   │   ├── doc_A1.txt  public
│   │   ├── doc_A2.txt  public
│   │   ├── doc_A3.txt  public
│   │   ├── doc_A4.txt  RESTRICTED — executive compensation
│   │   ├── doc_A5.txt  RESTRICTED — M&A targets
│   │   └── doc_A6.txt  RESTRICTED — Project Nightingale trial data  <- D
│   └── tenant_beta/           # Voltaic Systems (5 docs, 2 restricted)
│       ├── doc_B1.txt  public
│       ├── doc_B2.txt  public
│       ├── doc_B3.txt  public
│       ├── doc_B4.txt  RESTRICTED — security audit
│       └── doc_B5.txt  RESTRICTED — data handling policy
├── src/
│   ├── corpus_loader.py   Reads YAML-frontmatter corpus files
│   ├── rbac.py            AccessControlStore - grant / revoke / check
│   ├── vector_index.py    VectorIndex - flat ChromaDB collection
│   ├── semantic_cache.py  SemanticCache - cosine-sim dict cache, long TTL
│   ├── memory.py          SessionMemory - rolling turn buffer, no purge
│   ├── llm_client.py      LLMClient - Gemini + deterministic stub fallback
│   ├── rag_pipeline.py    NaiveRAGPipeline - orchestrates all components
│   └── logger.py          QueryLogger - structured CSV evidence log
├── config.py              All tunable constants
├── run_demo.py            Entry point - runs Steps 2-8, saves run_log.csv
└── requirements.txt
```

---

## Setup

```bash
pip install -r requirements.txt
```

For real LLM responses (optional — the stub works without it):

```bash
# Create a .env file in the repo root
echo "GEMINI_API_KEY=..." > .env
```

---

## Run

```bash
python run_demo.py
```

`run_demo.py` normalises Python stdout/stderr to UTF-8 at startup, so Windows
terminals using a legacy code page should not crash on Unicode status symbols.

The first run downloads `all-MiniLM-L6-v2` (~90 MB) and builds the ChromaDB
index (stored in `.chroma/`). Subsequent runs reuse the index and are fast.

Evidence is written to `results/run_log.csv`.

---

## Three named naive flaws (in `src/rag_pipeline.py`)

| # | Flaw | Location |
|---|---|---|
| 1 | **Cache before RBAC** - cache hit returned without access check | `NaiveRAGPipeline.query()` |
| 2 | **Flat index, RBAC after retrieval** - similarity scores computed before filtering | `NaiveRAGPipeline.query()` |
| 3 | **Session memory never purged on revocation** - stale context injected into LLM | `NaiveRAGPipeline.query()` |

---

## Output columns (`results/run_log.csv`)

| Column | Description |
|---|---|
| `timestamp` | ISO-8601 UTC |
| `actor` | `alice` or `bob` |
| `session_id` | session identifier |
| `query` | raw query string |
| `retrieved_doc_ids` | JSON list of ALL docs retrieved (pre-RBAC) |
| `ground_truth_restricted` | `True` if any retrieved doc is tagged restricted |
| `response_text` | full LLM / stub response |
| `similarity_score` | highest cosine similarity among retrieved docs |
| `latency_ms` | end-to-end query latency |
| `refusal_type` | `access_denied` / `not_found` / empty |
| `cache_hit` | `True` if response came from semantic cache |
| `step_label` | which demo step produced this row |
