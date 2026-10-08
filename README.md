# Afterimage: post-revocation and metadata leakage in multi-tenant RAG

Afterimage is a measurement testbed for one question: **when you revoke someone's access to a document, how long do the copies keep leaking?**

A RAG application leaves derived copies of every answer it produces: semantic-cache entries, chat-memory turns and rolling summaries, and ACLs copied into the vector index. Revoking access in the IAM system does not revoke those copies. Afterimage measures:

- **The revocation window.** How much of a revoked document still leaks, through which artifact, and for how long. Each artifact is measured under realistic propagation policies (periodic ACL crawls, lossy webhooks, cache TTLs).
- **Metadata existence inference.** Whether a black-box attacker can tell a restricted document exists, using scores, reranker confidence, latency, refusal wording or cache timing. This is tested in twin worlds: one with the document and one without it.
- **Provenance-tainted revocation.** The defense. Every derived artifact carries the set of source documents it came from (transitively through chat memory). Revocation is enforced eagerly on the event and lazily on every read. Responses have a constant shape.

The roadmap and the paper framing are in [`docs/UPGRADE_PLAN.md`](docs/UPGRADE_PLAN.md).

## Quick start

```bash
uv sync                                   # Python 3.13+
uv run pytest                             # ~5 s, fully offline
uv run python run.py --config configs/smoke.yaml --seeds 1
uv run python analyze.py results/smoke
```

`configs/smoke.yaml` uses a hashed bag-of-words embedder, a lexical reranker and the stub LLM, so it needs no downloads. The paper configs use `all-MiniLM-L6-v2` and `cross-encoder/ms-marco-MiniLM-L-6-v2` from Hugging Face. These download on first use.

## Experiments

| RQ | Config | What it measures |
|---|---|---|
| RQ1 | `configs/rq1_surfaces.yaml` | Leakage by artifact. Starts from the full defense and re-opens one artifact at a time, for each of 3 revocation types. `LM_all_lost` measures the blast radius: secrets of every warmed-up document the user lost. |
| RQ2 | `configs/rq2_revocation_window.yaml`, `rq2_cache_sweep.yaml` | Leakage lifetime (Kaplan–Meier survival) under periodic/event ACL sync and cache TTL / threshold sweeps, compared with the analytic Δ/2 staleness. |
| RQ3 | `configs/rq3_existence.yaml` | Twin-world existence inference. A learned attacker is trained on shadow tenants t1–t3 and tested on t4–t5. Reports AUC, TPR@1%FPR and balanced accuracy for each channel and exposure profile. |
| RQ4 | `configs/rq4_ablation_revocation.yaml`, `rq4_ablation_existence.yaml` | Leave-one-out ablation from the full defense, plus backfiring variants (fast refusal path, 30 ms padding). |
| RQ5 | `configs/rq5_utility.yaml`, `rq5_leakage.yaml` | Cost of security: Recall@k, nDCG@k, correctness, over-refusal, p50/p95 latency, cache hit rate. `rq5_leakage` gives the leakage axis of the Pareto plot. |
| — | `configs/model_grid.yaml` | Robustness across generators (Groq `gpt-oss-120b`, local Ollama) and embedders. |
| Review | `rq5_collateral`, `rq6_taint_stress`, `rq_baselines_{revocation,existence}`, `rq5_overhead`, `model_grid_7b`, `rq3_existence_7b`, `model_grid_groq`, `enron_*` | Review-round additions: collateral cost of transitive taint, taint-breaking cases, practice baselines (live post/pre-filter), remote-IAM overhead, Qwen2.5-7B, GPT-OSS-120B (Groq), EnronQA real-text track. All in `scripts/run_review.sh`; the judge sample is `scripts/judge_sample.py`. |
| — | `configs/model_grid_local.yaml`, `rq3_existence_local.yaml` | Real-LLM check with local Qwen2.5-3B via Ollama (`ollama pull qwen2.5:3b`): revocation stub vs Qwen paired on events, and RQ3 with Qwen. |

```bash
uv run python run.py --config configs/rq2_revocation_window.yaml --seeds 5
uv run python analyze.py results/rq2_revocation_window
uv run python analyze.py results/rq5_utility --leakage results/rq5_leakage   # Pareto plot
```

`run.py` writes one JSONL file per (cell, seed) and skips runs it has already finished. `analyze.py` writes `analysis/summary.md`, CSVs and PNG figures. All confidence intervals are 95% bootstrap intervals. Comparisons between configurations are paired on the same seeds and revocation events.

### LLM backends

Set `llm_backend` in a config: `stub` (default, offline, deterministic, with a simulated latency model), `groq`, `openai`, `gemini` or `ollama`. Keys come from `.env` (`GROQ_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_BASE_URL`). If an API call fails, the run fails; the client never falls back to the stub. Real generations are cached under `.cache/llm/`, together with their measured latency. A rerun replays both the text and the timing.

## How it works

```
data/corpus.jsonl, data/iam.json     frozen synthetic corpus v2 (scripts/generate_corpus.py)
src/secure_pipeline/
  access_control.py   live IAM + ACCESS_REVOKED event bus (single_doc, role, user_offboard)
  index_store.py      ChromaDB chunks with materialized per-user ACLs + sync policy (T1)
  semantic_cache.py   global / tenant / user scope, eager eviction, lazy taint check (T2)
  session_memory.py   chat memory with rolling summaries, purge + lazy check (T3)
  provenance.py       taint = frozenset of source doc IDs, transitive through memory
  normalization.py    score bands (T4/T5), refusal wording (T7), latency padding (T6)
  pipeline.py         server (ApiResponse + Truth) and black-box Client (Observation)
  mitigations.py      ablation switches and presets: strawman, baseline, legacy, full
  attacker.py         probes, exposure projection, threshold + learned attackers
  judge.py            canary / fact disclosure check (optional LLM paraphrase judge)
  metrics.py          LM, Kaplan–Meier, AUC / TPR@FPR, utility, bootstrap
  experiments.py      revocation, existence, utility procedures
  clock.py            WallClock (real) / SimClock (real compute + virtual waits)
run.py, analyze.py    grid runner and analysis
configs/              one YAML per research question
tests/                security invariants and component tests
```

**Corpus v2.** 5 tenants, 100 documents each (40 public, 30 internal, 30 restricted), 8 users per tenant (6 employees, 2 contractors) and department groups. Each document has checkable facts. Each restricted document also has a unique random canary (`codename QX-7731`), so leakage is an exact match. Restricted documents come in projects of 1–2 documents, so removing one in the twin world still leaves related material: the negatives are hard.

**Black-box boundary.** `RAGPipeline.handle` returns an `ApiResponse` and a `Truth` row. `Client.ask` times the whole call on the shared clock and returns only an `Observation`, projected to an exposure profile (`text_only`, `with_sources`, `with_reranker`). The attacker code only ever receives `Observation` fields.

**Presets** (`mitigations.py`):

| preset | retrieval | cache | memory | metadata |
|---|---|---|---|---|
| `strawman` | flat across tenants, post-filter | global, no hooks | no purge | raw scores, distinct refusals, no padding |
| `baseline` | ACL pre-filter on materialized (stale) ACLs | tenant-scoped, no hooks | no purge | raw |
| `legacy` | pre-filter | evict on revoke | ID-match purge (non-transitive) | bands, uniform refusal, 30 ms floor, fast refusal path |
| `full` | pre-filter + live IAM re-check | evict + lazy taint check | transitive taint purge + lazy check | bands, uniform refusal, 500 ms bucket padding |

## Threat model

| Threat | Leak mechanism | Mitigation switch |
|---|---|---|
| T1 Stale index ACLs | ACLs copied into the index sync on a schedule or by webhook. A revoked user still retrieves the document until the sync runs. | `live_acl_check` |
| T2 Semantic cache | A cached answer outlives the permission it was built on. With a global scope it also crosses tenants. | `cache_scope`, `cache_evict`, `cache_lazy_check` |
| T3 Chat memory | Earlier turns and rolling summaries keep the content. A summary has no doc IDs, so an ID-match purge misses it. | `memory_purge`, `taint_transitive`, `memory_lazy_check` |
| T4 Similarity scores | The retrieval confidence of an unauthorized candidate reveals that the document exists. | `acl_prefilter`, `score_quantize` |
| T5 Reranker confidence | The same leak, through the reranker score. | `acl_prefilter`, `score_quantize` |
| T6 Latency | Cache hit vs miss, and a fast refusal path vs an LLM call, take different times. | `latency_pad` (`bucket` / `deadline` / `floor`), `fast_refusal` |
| T7 Refusal wording | "No permission" vs "not found" reveals that a restricted document exists. | `uniform_refusal` |

## Status against the upgrade plan

Done: phases 0 to 3, and phases 4 and 5 except the items below.

Not done yet:

- **EnronQA real-data track.** It needs the dataset download and an adapter.
- **LLM-written corpus text.** The v2 corpus is template-generated. It is deterministic and committed, but the plan suggested having an LLM write it.
- **Groq runs and the LLM paraphrase judge** (`analyze.py --judge llm`). Ollama has been run with Qwen2.5-3B (`model_grid_local`, `rq3_existence_local`); Groq and the LLM judge have not been run against a live API.
- **Phase 6 case study.**
