# RAGLeakage — Codebase Upgrade Plan

Source of truth for the code upgrade before writing the paper. As of 2026-10-06.

## TL;DR

The current code is a working demo, not yet publishable evidence: 11 documents, 13 probes, one run, hand-tuned attacker thresholds, and an attacker that reads internal signals it should never see. The upgrade turns it into a measurement study with a defensible thesis, a learned attacker, real timing, and statistics.

**Thesis:** in RAG, revocation is a *consistency* problem across derived artifacts, not an access check. Every answer the system produces leaves copies (cache entries, chat turns, materialized ACLs in the index). Revoking access in the IAM system does not revoke those copies.

**Working title:** *Revoked but Not Forgotten: Measuring Post-Revocation and Metadata Leakage in Multi-Tenant RAG.* Framework/benchmark name: **Afterimage**.

**Three contributions the code must support:**

1. **The revocation window, measured.** Leakage over time after revocation across three derived artifacts (index with lagging ACL sync, semantic cache, session memory), reported as a survival curve and median leakage lifetime, under realistic propagation policies (periodic sync, event-driven, TTL). Grounded in production behaviour: Microsoft 365 Copilot connectors synced permissions only in a daily full crawl until 2026.
2. **Metadata existence inference, done properly.** Twin-world (doc present vs absent) experiment with a trained black-box attacker, scored as AUC and TPR at 1% FPR per channel (score, reranker, latency, refusal, cache timing). Includes the finding that common "fixes" re-open channels (a fast refusal path is a timing oracle).
3. **Provenance-tainted revocation.** Every derived artifact carries the source doc IDs it came from, propagated transitively through chat memory, plus constant-shape responses. Measured against leakage, answer quality, over-refusal and latency.

## Audit: what a reviewer would reject today

| # | Problem | Where | Why it kills the paper |
|---|---|---|---|
| 1 | Attacker reads internal values `raw_similarity_score` and `raw_latency_ms`, even in mitigated mode | `attacker.py` `_infer_existence` | Not black-box. Every EIA number is invalid. |
| 2 | Latency padding computed, not applied (`apply_latency_sleep=False`), and targets 30 ms while an LLM call takes ~1 s | `normalization.py`, `pipeline.py` | Mitigation exists only in a log column. Cache hit (~5 ms) vs miss (~1 s) still visible to a stopwatch. |
| 3 | Mitigated mode skips the LLM on refusals ("Fix 5") | `pipeline.py` step 5 | Refusals return instantly: the defense is a timing oracle. |
| 4 | Stale index threat not modelled: baseline checks live RBAC after retrieval; `on_revocation` is `pass` | `index_store.py`, `pipeline.py` | Threat T1 is not tested. |
| 5 | Negative probes are nonsense topics | `attacker.py` probe suite | Low similarity separates them without any restricted doc. Inflates baseline EIA. |
| 6 | EIA label (`ground_truth_restricted`) depends on which docs each mode retrieved | `pipeline.py` `_check_restricted` | Modes scored against different ground truths. |
| 7 | 11 docs, whole-doc embeddings, 13 probes, 1 run, no seeds or CIs | `corpus.py`, `experiment_runner.py` | Not statistically meaningful. |
| 8 | LM = keyword substring match on hardcoded lists; `LM_total = max()` of three numbers with different denominators | `metrics.py` | Misses paraphrased leaks, mixes units. |
| 9 | Leakage Half-Life from 5 binary points | `experiment_runner.py` decay loop | LH is always 0 or inf. |
| 10 | Baseline and mitigated differ in 7 things at once | `pipeline.py` `set_mode` | No ablation possible. |
| 11 | LLM errors silently fall back to the stub | `llm_client.py` | Real and fake generations can mix unnoticed. |
| 12 | `query_count_since_revocation` is a global counter; ChromaDB written but never queried | `pipeline.py`, `index_store.py` | Wrong x-axis for LH; vector DB is decoration. |

Housekeeping: README points to `src/naive/` and `src/full/` (folders are `naive_pipeline/`, `secure_pipeline/`), no `requirements.txt`, six wrapper files only re-export, `corpus/` folder and in-code corpus disagree.

## Positioning (what is taken, what is open)

| Work | Covers | Leaves open |
|---|---|---|
| Tavakoli & Sanderson, *Deletion Isn't Enough*, SIGIR'26 | Fact-level leakage after deletion; PRE/POST/FILT; Leak@k, abstention | Static, single user, no caches/memory, no time dimension, no side channels |
| Ghost Vectors (arXiv 2606.18497) | Soft-deleted HNSW vectors reconstructible | Storage layer only |
| M365 Copilot connector permission sync; Microsoft ISE SharePoint RAG | Daily permission crawl; "bounded delay" accepted | Evidence, no measurement — our motivation |
| RAG membership inference (S2MIA, Riddle Me This, MBA, E-MIA) | Doc in KB? from generated text | Not authorized-vs-restricted; never scores/latency/refusal |
| Serving-layer timing (Early Bird, prompt-cache audit ICML'25, SpliceLeak, PrefixWall) | KV/prompt cache timing | Below the RAG app; no RBAC/revocation |
| CacheAttack (arXiv 2601.23088) | Semantic cache collisions | Integrity only |
| MEXTRA; FIDES (IFC for agents) | Memory extraction; taint labels | No revocation lifecycle |

Unique claim: first study measuring leakage *as a function of time after revocation* across application-layer derived artifacts in multi-tenant RAG, together with metadata channels, plus a provenance-based defense evaluated on both. Frame revocation as eventual consistency (staleness window, propagation policy). Headline the negative results (30 ms padding vs 1 s LLM; fast refusal path leaks).

## Code upgrade plan

Phases 0–2 fix validity and must land before any number is reported; 3–5 produce results; 6 is a stretch.

### Phase 0: Clean up and make runs trustworthy
- Delete the six re-export wrappers in `secure_pipeline/` (`rbac.py`, `memory.py`, `vector_index.py`, `rag_pipeline.py`, `logger.py`, `corpus_loader.py`) and fix imports. Delete `naive_pipeline/` and `run_demo.py`: baseline mode covers them.
- `llm_client.py`: remove silent stub fallback (raise instead; stub only when explicitly selected), log model name in every row, cache generations on disk keyed by hash(model, prompt).
- One clock: `pipeline.now()`, simulated for TTL/sync experiments, real wall-clock for timing experiments. Replace scattered `time.time()` and `simulated_time_offset_s`.
- Fix `query_count_since_revocation` to count from that user's last revocation. Seed `random`, `numpy`, LLM (temperature 0) from one `--seed`.
- Add `tests/test_invariants.py`: in full-mitigation mode a revoked doc's canary never appears; a revoked cache entry never hits; tainted memory turns are gone.
- Rewrite README to match folders.

### Phase 1: Enforce the black-box boundary
- New `Observation` dataclass = exactly what the API returns: response text, client-measured wall-clock latency, only the scores the chosen **exposure profile** shows (`text_only`, `with_sources`, `with_reranker`).
- `attacker.py` takes only `Observation`. Ground truth in a separate log row the attacker never sees.
- Latency measured at the client around the real call, with real sleeps. Remove computed `effective_latency_ms`.

### Phase 2: Make the threats realistic
- **Index with materialized ACLs** (`index_store.py`): store `allowed_users`/`allowed_groups` on each chunk at ingestion; query ChromaDB with a `where` filter (drop the numpy loop). ACL sync policy: `live`, `periodic(interval)`, `event(drop_rate)`. IAM changes instantly; index metadata changes only when the policy syncs.
- **Chunking**: ~300-token chunks inheriting doc ACL and doc_id.
- **Realistic baseline cache**: keep global cache as strawman; main baseline = tenant-scoped cache without revocation hook. Sweep threshold (0.80–0.95) and TTL.
- **Rolling summary memory** (`session_memory.py`): after N turns compress older turns into a summary turn. The summary carries restricted content without doc IDs, defeating the ID-match purge.
- **Ablation switches**: replace `mode` string with one `Mitigations` dataclass of booleans (`acl_prefilter`, `live_acl_check`, `cache_scope`, `cache_evict`, `memory_purge`, `taint_transitive`, `score_quantize`, `latency_pad`, `uniform_refusal`). `baseline` and `full` are presets.

### Phase 3: The defense
- **Provenance taint**: every artifact carries `taint: frozenset[doc_id]`. Response taint = retrieved chunks' taint ∪ taint of every memory turn in its prompt. Cache entries, memory turns, summaries inherit it. One helper; no new class hierarchy.
- **Two enforcement points**: eager purge on revocation event (generalized to taint) + lazy check on every read (user still holds every doc in the artifact's taint?). Lazy check covers lost events and lagging sync.
- **Constant-shape responses** (`normalization.py`): pad wall-clock to fixed buckets (next 500 ms, or fixed deadline at observed p99), same padding for cache hits, one refusal text, remove or pad the fast refusal path. Report how much of the cache's latency saving survives.

### Phase 4: Data, attacker, metrics
- **Synthetic corpus v2**: generator script + frozen `data/corpus.jsonl`. 5 tenants, ~100 docs each, roles/groups, per restricted doc 3–5 facts plus one random canary string (e.g. `codename QX-7731`). Generate once, commit.
- **Real-data track**: EnronQA (103,638 emails, 150 inboxes, 528,304 QA pairs, CC BY 4.0). Inbox owner + recipients = ACL; revocation removes a recipient.
- **Twin-world probes**: same probes in a world with the target doc and one without. Hard negatives, shared ground truth.
- **Learned attacker**: features from `Observation`; logistic regression + gradient boosting; train on shadow tenants, test on held-out tenants. Keep the threshold attacker as weak baseline.
- **Metrics** (rewrite `metrics.py`):
    - LM = fraction of target facts disclosed post-revocation: canary exact match + LLM/NLI judge for paraphrase; per-surface LM via ablation runs.
    - LH = from many revocation events, time (and queries) until last leak; Kaplan–Meier survival curve, median + 95% CI.
    - EIA = AUC, TPR@1%FPR, balanced accuracy, per channel and combined.
    - Utility = Recall@k / nDCG on authorized queries, answer correctness, over-refusal on lawful queries, p50/p95 latency, cache hit rate.

### Phase 5: Runner and statistics
- `run.py --config <yaml> --seeds 5` writes JSONL; `analyze.py` produces tables/figures with bootstrap 95% CIs and paired tests. Delete console comparison table in `experiment_runner.py`.
- Grid: 2 LLMs (local via Ollama, e.g. 8B Llama/Qwen, plus Groq `gpt-oss-120b`), 2 embedders (MiniLM, bge/e5), 3 revocation types, 3 sync policies, ablation presets.

### Phase 6 (stretch): Case study
Same probes against Open WebUI or AnythingLLM: revoke workspace/doc access, check chat history, cached answers, vectors. Responsible disclosure before publishing.

## Experiments the paper reports (5 seeds, bootstrap 95% CIs)

| RQ | Question | Experiment | Primary metric | Figure |
|---|---|---|---|---|
| RQ1 | How much leaks after revocation, through which artifact? | Baseline preset, one surface vulnerable at a time; 3 revocation types | LM per surface | Stacked bars |
| RQ2 | How long does it last? | 200 revocation events per policy: periodic (1 h, 24 h), event with 0%/5% loss, TTL sweep | Median leakage lifetime (KM) | Survival curves vs analytic prediction |
| RQ3 | Can an outsider tell a restricted doc exists, from which signal? | Twin-world × 3 exposure profiles, learned attacker | AUC, TPR@1%FPR per channel | ROC per channel |
| RQ4 | What does each mitigation buy; do any backfire? | Leave-one-out from full; include fast-refusal and 30 ms-padding variants | ΔLM, ΔAUC | Ablation heatmap |
| RQ5 | What does security cost? | Authorized queries (synthetic + EnronQA) | nDCG@5, correctness, over-refusal, p50/p95, cache hit rate | Pareto: leakage vs latency |

Analytic check for RQ2: periodic sync every Δ, revocation at uniform random time → expected index staleness Δ/2; cache entry lives min(TTL, time to next eviction).

## References to add
1. Tavakoli & Sanderson, Deletion Isn't Enough, SIGIR 2026 — https://marksanderson.org/files/papers/SIGIR2026_Leila_Main__Copy_.pdf
2. Ghost Vectors — https://arxiv.org/abs/2606.18497
3. Gu et al., Auditing Prompt Caching in LM APIs, ICML 2025 — https://arxiv.org/abs/2502.07776
4. EnronQA — https://arxiv.org/abs/2505.00263
5. The Early Bird Catches the Leak — https://arxiv.org/abs/2409.20002
6. CacheAttack — https://arxiv.org/abs/2601.23088
7. RAG MIA: https://arxiv.org/abs/2405.20446, https://arxiv.org/abs/2502.00306, https://arxiv.org/abs/2605.00955
8. MEXTRA — https://arxiv.org/abs/2502.13172
9. FIDES — https://arxiv.org/abs/2505.23643
10. M365 Copilot permission sync — https://m365admin.handsontek.net/microsoft-copilot-microsoft-365-support-permission-sync-missed-incremental-crawl/ ; Microsoft ISE — https://devblogs.microsoft.com/ise/sharepoint-doc-level-access/
11. Carlini et al., MIA From First Principles (S&P 2022)
12. Carlini et al., The Secret Sharer (USENIX Sec 2019)
