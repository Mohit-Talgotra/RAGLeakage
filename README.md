# Secure Multi-Tenant RAG: Temporal & Side-Channel Leakage Testbed

Simulation testbed and formal evaluation suite for researching and mitigating **temporal and side-channel leakage** in multi-tenant enterprise RAG systems.

---

## 1. Overview & Project Structure

The codebase is structured into two parallel implementations:
- **`src/naive/`**: The Naive Baseline MVP demonstrating unmitigated temporal & side-channel vulnerabilities.
- **`src/full/`**: The Complete Product Architecture implementing the full experimental matrix, multi-tenant isolation, proactive revocation invalidation, metadata normalization, cross-encoder reranking, black-box attacker probing, and formal metrics.

```
RAGLeakage/
├── corpus/                    # Multi-tenant document corpus
│   ├── tenant_alpha/          # Biopharma (Meridian Corp)
│   └── tenant_beta/           # Energy-Tech (Voltaic Systems)
├── src/
│   ├── naive/                 # MVP Baseline implementation (unmitigated)
│   │   ├── rag_pipeline.py
│   │   ├── semantic_cache.py
│   │   └── ...
│   └── full/                  # Full Architecture (§1-§8)
│       ├── access_control.py  # RBAC + Revocation Event Bus (3 revocation types)
│       ├── attacker.py        # Black-box probe suite (4 strategies) + EIA inference
│       ├── corpus.py          # 3-tenant synthetic corpus & sensitive fact index
│       ├── index_store.py     # Partitioned / ACL pre-filtered vector index
│       ├── instrumentation.py # Structured logger for all observable & ground-truth signals
│       ├── llm_client.py      # Generation with Gemini / OpenAI / deterministic stub
│       ├── metrics.py         # Formal LM, LH, and EIA metric calculators
│       ├── normalization.py   # Score quantization, latency jitter, uniform refusals
│       ├── pipeline.py        # Unified pipeline supporting Baseline & Mitigated modes
│       ├── reranker.py        # Cross-Encoder candidate reranker & confidence scoring
│       ├── semantic_cache.py  # ACL-aware cache with revocation eviction hooks
│       ├── session_memory.py  # Session memory with revocation purging
│       └── experiment_runner.py # Automated A/B experiment matrix (§5)
├── run_demo.py                # MVP single-run demo (using naive baseline)
├── run_full_experiment.py     # Full A/B experiment suite (Baseline vs Mitigated)
└── requirements.txt
```

---

## 2. Threat Model & Mitigations

| Threat | Vulnerability Mechanism (Baseline Mode) | Mitigation (Mitigated Mode) |
|---|---|---|
| **T1: Vector Index Staleness** | Flat global retrieval computes similarity across all tenants/docs. | Tenant isolation and ACL pre-filtering before vector scoring. |
| **T2: Semantic Cache Staleness** | Cache lookup before RBAC; no eviction on revocation. | ACL-aware cache verification + immediate eviction on `ACCESS_REVOKED`. |
| **T3: Conversational Memory** | Prior turn context retained post-revocation in session buffer. | Revocation hook purges turns referencing revoked document IDs. |
| **T4: Similarity Score Side-Channel** | High raw cosine similarity leaks restricted doc existence. | Continuous scores quantized into coarse discrete bands (Low/Med/High). |
| **T5: Reranker Confidence** | Raw cross-encoder confidence reveals candidate presence. | Reranking restricted to authorized docs; scores quantized. |
| **T6: Latency Timing Side-Channel** | Cache hits and filtered misses exhibit distinct response times. | Uniform latency target padding with random jitter. |
| **T7: Refusal Phrasing Oracle** | "Access denied" vs "Not found" reveals restricted existence. | Standardized refusal message across all empty/filtered outcomes. |

---

## 3. Formal Security Metrics (§4)

- **Leakage Magnitude ($LM \in [0, 1]$)**: Fraction of sensitive ground-truth facts recovered post-revocation ($LM_{\text{total}}$, $LM_{\text{cache}}$, $LM_{\text{memory}}$, $LM_{\text{facts}}$).
- **Leakage Half-Life ($LH$)**: Query count / time for $LM$ to decay to $50\%$ of $LM(0+)$.
- **Existence Inference Accuracy ($EIA \in [0, 1]$)**: Attacker's classification accuracy, precision, recall, and F1 in inferring restricted document existence strictly from side-channel observations.

---

## 4. Setup & Running

### Requirements
```bash
pip install -r requirements.txt
```

### LLM API Key (Groq / OpenAI / Gemini)
```bash
# Set GROQ_API_KEY in .env (or export it in your shell):
echo "GROQ_API_KEY=gsk_..." > .env
```

### Running the Full Product Experiment Suite
```bash
python run_full_experiment.py
```

### Running the MVP Baseline Demo
```bash
python run_demo.py
```
