# RAGLeakage — Codebase Upgrade Plan

Oct 6, 2026 · @ayush

## TL;DR

The current code is a working demo, not yet publishable evidence: 11 documents, 13 probes, one run, hand-tuned attacker thresholds, and an attacker that reads internal signals it should never see. The upgrade turns it into a measurement study with a defensible thesis, a learned attacker, real timing, and statistics.

**Thesis to sell:** in RAG, revocation is a *consistency* problem across derived artifacts, not an access check. Every answer the system produces leaves copies (cache entries, chat turns, materialized ACLs in the index). Revoking access in the IAM system does not revoke those copies.

**Working title:** *Revoked but Not Forgotten: Measuring Post-Revocation and Metadata Leakage in Multi-Tenant RAG.* Framework name for the code and benchmark: **Afterimage** (what stays visible after the source is gone).

**Three contributions the paper will claim (and the code must support):**

1. **The revocation window, measured.** Leakage over time after revocation across three derived artifacts (index with lagging ACL sync, semantic cache, session memory), reported as a survival curve and median leakage lifetime, under realistic propagation policies (periodic sync, event-driven, TTL). Grounded in a real production behaviour: Microsoft 365 Copilot connectors synced permissions only in a daily full crawl until 2026.
2. **Metadata existence inference, done properly.** A twin-world (doc present vs absent) experiment with a trained black-box attacker, scored as AUC and TPR at 1% FPR per channel (score, reranker, latency, refusal, cache timing). Includes the finding that common "fixes" re-open channels (e.g. a fast refusal path is a timing oracle).
3. **Provenance-tainted revocation.** A defense where every derived artifact carries the source document IDs it came from, propagated transitively through chat memory, plus constant-shape responses. Measured against leakage, answer quality, over-refusal and latency.

## Audit: what a reviewer would reject today

The architecture (RBAC, cache, memory, reranker, normalizer, attacker, metrics) is the right skeleton. The problems are in validity, scale and measurement, ranked below by how fatal they are.

| # | Problem | Where | Why it kills the paper |
| --- | --- | --- | --- |
| 1 | Attacker reads internal values: `raw_similarity_score` and `raw_latency_ms`, even in mitigated mode | `attacker.py` `_infer_existence` | Not black-box. Every EIA number is invalid. |
| 2 | Latency padding is computed, not applied (`apply_latency_sleep=False`), and targets 30 ms while an LLM call takes \~1 s | `normalization.py`, `pipeline.py` | Timing "mitigation" exists only in a log column. A real attacker with a stopwatch still sees cache hit (\~5 ms) vs miss (\~1 s). |
| 3 | Mitigated mode skips the LLM on refusals ("Fix 5") | `pipeline.py` step 5 | Refusals return instantly: the defense itself is a timing oracle. |
| 4 | Stale index threat is not modelled: baseline checks live RBAC after retrieval, so the index is never stale; `on_revocation` is `pass` | `index_store.py`, `pipeline.py` | Threat T1 in the README is not actually tested. |
| 5 | Negative probes are nonsense topics ("zero-point flux battery") | `attacker.py` probe suite | Low similarity separates them without any restricted doc. Inflates baseline EIA. |
| 6 | EIA label (`ground_truth_restricted`) depends on which docs each mode retrieved | `pipeline.py` `_check_restricted` | Baseline and mitigated are scored against different ground truths. |
| 7 | 11 docs, whole-document embeddings, 13 probes, 1 run, no seeds or CIs | `corpus.py`, `experiment_runner.py` | Not statistically meaningful; one probe flips EIA by \~8 points. |
| 8 | LM is keyword substring match on hardcoded lists, and `LM_total = max()` of three numbers with different denominators | `metrics.py` | Misses paraphrased leaks, counts refusals that echo a term, and mixes units. |
| 9 | Leakage Half-Life comes from 5 binary points (0 or 1) | `experiment_runner.py` decay loop | LH is a step function: always 0 or inf, never a real half-life. |
| 10 | Baseline and mitigated differ in 7 things at once | `pipeline.py` `set_mode` | No ablation: cannot say which mitigation buys what. |
| 11 | LLM errors silently fall back to the stub | `llm_client.py` | Results can mix real and fake generations without anyone noticing. |
| 12 | `query_count_since_revocation` is a global counter; ChromaDB is written but never queried | `pipeline.py`, `index_store.py` | Wrong x-axis for LH; the "vector DB" is decoration. |

Housekeeping: README points to `src/naive/` and `src/full/` (folders are `naive_pipeline/` and `secure_pipeline/`), there is no `requirements.txt`, six wrapper files only re-export, and the `corpus/` folder and the in-code corpus disagree.

## Positioning: what is taken and what is open

The closest work is a SIGIR 2026 paper that already says "deletion isn't enough", so our gap claim in the Project-I report ("no post-revocation benchmark exists") must be narrowed. What remains open is the **time dimension, the application-layer artifacts, multi-tenant ACLs, and metadata channels together**.

| Work | What it covers | What it leaves open (our space) |
| --- | --- | --- |
| [Tavakoli & Sanderson, Deletion Isn't Enough (SIGIR'26)](https://marksanderson.org/files/papers/SIGIR2026_Leila_Main__Copy_.pdf) | Fact-level leakage after deletion; PRE / POST / FILT states; Leak@k, abstention, rank substitution; FEVER + BM25 + Llama-3-8B | Static snapshots, single user, no caches or chat memory instrumented, no notion of how long leakage lasts, no side channels |
| [Ghost Vectors (arXiv 2606.18497)](https://arxiv.org/abs/2606.18497) | Soft-deleted HNSW vectors in Chroma, FAISS, Weaviate stay reconstructible | Storage layer only; no RAG access revocation, cache or memory |
| [Microsoft 365 Copilot connector permission sync](https://m365admin.handsontek.net/microsoft-copilot-microsoft-365-support-permission-sync-missed-incremental-crawl/) and [Microsoft ISE SharePoint RAG post](https://devblogs.microsoft.com/ise/sharepoint-doc-level-access/) | Real systems: permissions synced in a daily full crawl (incremental sync GA June 2026); ISE pipeline accepted a "bounded delay" for ACL propagation | Industry evidence, no measurement. This is our motivation paragraph. |
| Membership inference on RAG (S2MIA, Riddle Me This, MBA at WWW'25, E-MIA) | Whether a doc is in the knowledge base, from generated text | Public-vs-absent membership, not authorized-vs-restricted; output text only, never scores, latency, or refusal shape |
| Serving-layer timing (Early Bird, prompt-cache auditing at ICML'25, SpliceLeak, PrefixWall) | KV and prompt-cache timing across tenants | Below the RAG app; no RBAC, no revocation |
| [CacheAttack (arXiv 2601.23088)](https://arxiv.org/abs/2601.23088) | Semantic-cache key collisions to hijack responses | Integrity only; no authorization or multi-tenant confidentiality |
| Agent memory leakage (MEXTRA, ACL'25); information-flow control for agents (FIDES) | Extracting stored memory; taint labels on agent data | No revocation lifecycle; FIDES gives us the vocabulary for provenance taint |

**What makes this unique, in one line:** the first study to measure leakage *as a function of time after revocation* across the derived artifacts of a multi-tenant RAG app, together with the metadata channels that reveal restricted documents, and a provenance-based defense evaluated on both.

Two framing choices make it land with reviewers:

- Treat revocation as **eventual consistency**. Borrow the distributed-systems words: staleness window, propagation policy, consistency level. Security reviewers know this framing and will find it fresh for RAG.
- Make the **negative results** a headline, not a footnote: padding to 30 ms does nothing against a 1 s LLM, and a fast refusal path leaks. "Common fixes that do not work" papers get cited.

## Code upgrade plan

Six phases, in dependency order. Phases 0 to 2 fix validity and must land before any number is reported; phases 3 to 5 produce the paper's results; phase 6 is a stretch that adds real-world weight.

### Phase 0: Clean up and make runs trustworthy

- Delete the six re-export wrappers in `secure_pipeline/` (`rbac.py`, `memory.py`, `vector_index.py`, `rag_pipeline.py`, `logger.py`, `corpus_loader.py`) and fix imports. Delete `naive_pipeline/` and `run_demo.py`: baseline mode already covers them.
- `llm_client.py`: remove the silent stub fallback (raise instead), log the model name in every row, and cache generations on disk keyed by hash(model, prompt) so reruns are free and identical.
- Add one clock: `pipeline.now()` that is simulated for TTL and sync experiments and real wall-clock for timing experiments. Replace the scattered `time.time()` and `simulated_time_offset_s`.
- Fix `query_count_since_revocation` to count from the last revocation of that user. Seed `random`, `numpy` and the LLM (temperature 0) from one `--seed`.
- Add `tests/test_invariants.py`: in full-mitigation mode a revoked doc's canary never appears; a revoked cache entry never hits; tainted memory turns are gone.
- Rewrite the README to match the folders.

### Phase 1: Enforce the black-box boundary

- New `Observation` dataclass in `pipeline.py` = exactly what the API returns: response text, client-measured wall-clock latency, and only the scores the chosen **exposure profile** shows. Profiles: `text_only`, `with_sources` (doc titles and scores, as many RAG UIs show), `with_reranker`.
- `attacker.py` takes only `Observation`. Ground truth stays in a separate log row the attacker never sees.
- Latency is measured at the client around the real call, with real sleeps. `effective_latency_ms` as a computed column goes away.

### Phase 2: Make the threats realistic

- **Index with materialized ACLs** (`index_store.py`): store `allowed_users` and `allowed_groups` on each chunk at ingestion, as the Microsoft ISE pattern does, and actually query ChromaDB with a `where` filter (drop the numpy loop). Add an ACL sync policy: `live`, `periodic(interval)`, or `event(drop_rate)` for lost webhooks. IAM changes instantly; index metadata changes only when the policy syncs. This makes threat T1 real.
- **Chunking**: \~300-token chunks inheriting the doc's ACL and doc\_id.
- **Realistic baseline cache** (`semantic_cache.py`): keep the global cache as the strawman, but make the main baseline a tenant-scoped cache with no revocation hook, which is what teams actually ship. Sweep threshold (0.80 to 0.95) and TTL.
- **Rolling summary memory** (`session_memory.py`): after N turns, older turns are compressed into a summary turn, as LangChain-style summary memory does. The summary inherits restricted content without naming any doc ID, which defeats the current ID-match purge. This is the case that motivates transitive taint.
- **Ablation switches**: replace the single `mode` string with one `Mitigations` dataclass of booleans (`acl_prefilter`, `live_acl_check`, `cache_scope`, `cache_evict`, `memory_purge`, `taint_transitive`, `score_quantize`, `latency_pad`, `uniform_refusal`). `baseline` and `full` become two presets.

### Phase 3: The defense (our contribution)

- **Provenance taint**: every artifact carries `taint: frozenset[doc_id]`. A response's taint = its retrieved chunks' taint plus the taint of every memory turn in its prompt. Cache entries, memory turns and summaries inherit it. One helper does this; no new classes.
- **Two enforcement points**: eager purge on the revocation event (what exists now, generalized to taint) and a lazy check on every read ("does the user still hold every doc in this artifact's taint?"). The lazy check covers lost events and lagging sync, and the paper can show each point's contribution separately.
- **Constant-shape responses** (`normalization.py`): pad wall-clock to fixed buckets (e.g. the next 500 ms, or a fixed deadline at the observed p99), apply the same padding to cache hits, keep one refusal text, and remove the fast refusal path or pad it to the same bucket. Report the cost honestly: how much of the cache's latency saving survives.

### Phase 4: Data, attacker, metrics

- **Synthetic corpus v2** (`corpus.py` becomes a generator script plus a frozen `data/corpus.jsonl`): 5 tenants, \~100 docs each, roles and groups, and per restricted doc 3 to 5 facts plus one random canary string (e.g. `codename QX-7731`), so leakage is checked by exact match with zero ambiguity. Generate once with an LLM, then commit it.
- **Real-data track**: EnronQA (103,638 emails, 150 inboxes, 528,304 QA pairs, CC BY 4.0). Inbox owner and recipients form the ACL; revocation removes a recipient. Real ACL structure plus gold QA for utility.
- **Twin-world probes**: for each target doc, run the same probes in a world with the doc and a world without it. Negatives become hard (same topic, doc absent), and both modes share one ground truth.
- **Learned attacker** (`attacker.py`): features from `Observation` (scores if exposed, latency, response length, refusal text, citation count), logistic regression and gradient boosting, trained on shadow tenants and tested on held-out tenants. Keep today's threshold attacker as a weak baseline.
- **Metrics** (`metrics.py`, rewritten):
  - LM = fraction of target facts disclosed post-revocation: canary exact match plus an LLM or NLI judge for paraphrased facts; per-surface LM from ablation runs (one surface left vulnerable at a time), not from step-label heuristics.
  - LH = from many revocation events, time (and queries) until the last leak, as a Kaplan–Meier survival curve with a median and 95% CI.
  - EIA = AUC, TPR at 1% FPR, and balanced accuracy, per channel and combined.
  - Utility = Recall@k / nDCG on authorized queries, answer correctness, over-refusal rate on lawful queries, p50 / p95 latency, cache hit rate.

### Phase 5: Runner and statistics

- One `run.py --config <yaml> --seeds 5` writes JSONL rows; one `analyze.py` turns them into the paper's tables and figures with bootstrap 95% CIs and paired tests between configs. Delete the console comparison table in `experiment_runner.py`.
- Grid: 2 LLMs (one local via Ollama, e.g. an 8B Llama or Qwen, plus Groq `gpt-oss-120b`), 2 embedders (MiniLM, a bge or e5 model), 3 revocation types, 3 sync policies, the ablation presets.

### Phase 6 (stretch): Case study on a real platform

Run the same probes against one open-source RAG app (Open WebUI or AnythingLLM): revoke a user's workspace or doc access, then check chat history, cached answers and vectors. Any confirmed issue goes through responsible disclosure before the paper. One real finding outweighs another synthetic table.

## Experiments the paper will report

Five research questions, each with one experiment, one primary metric and one figure. Every cell is run over 5 seeds with bootstrap 95% CIs.

| RQ | Question | Experiment | Primary metric | Figure |
| --- | --- | --- | --- | --- |
| RQ1 | How much leaks after revocation, and through which artifact? | Baseline preset, then one surface left vulnerable at a time; 3 revocation types | LM per surface (canary + judge) | Stacked bars: LM by surface × revocation type |
| RQ2 | How long does it last under real propagation policies? | 200 revocation events per policy: periodic sync (1 h, 24 h), event with 0% / 5% webhook loss, cache TTL sweep | Median leakage lifetime (Kaplan–Meier) | Survival curves, one line per policy, measured vs analytic prediction |
| RQ3 | Can an outsider tell a restricted doc exists, and from which signal? | Twin-world probes × 3 exposure profiles, learned attacker | AUC and TPR at 1% FPR per channel | ROC curves per channel, baseline vs full |
| RQ4 | What does each mitigation buy, and do any backfire? | Leave-one-out ablation from the full preset; include the fast-refusal and 30 ms-padding variants | ΔLM, ΔAUC vs full | Ablation heatmap: mitigation × metric |
| RQ5 | What does security cost? | Same grid on authorized queries (synthetic + EnronQA) | nDCG@5, answer correctness, over-refusal, p50 / p95 latency, cache hit rate | Pareto plot: leakage vs latency per preset |

The analytic prediction in RQ2 is cheap and reviewers like it: with periodic sync every Δ and a revocation at a uniformly random moment, the index stays stale for Δ/2 on average; a cache entry lives min(TTL, time to its next eviction). Showing measured curves sit on these lines validates the harness.

Two results to watch for, because they make the paper: (1) transitive taint is the only defense that closes the summary-memory leak, and (2) quantized scores still leak through latency unless padding is applied to cache hits as well.

## Timeline, owners, venues

Code work fits in about 8 weeks if three people run in parallel, with results frozen by Nov 30. I don't know your Project-II review dates, so shift the bars to fit them; owners are a suggestion.

&#91;embedded content: code plan · 8 weeks, 3 owners, 1 freeze\]

Ayush holds the pipeline path (phases 0 to 3) because everything else plugs into it; data and the attacker can start on day one because they only need the `Observation` format agreed in week 1.

**Venue tiers** (check each call for papers before committing; deadlines move every year):

| Tier | Options | Fit |
| --- | --- | --- |
| Conference | ACM AsiaCCS, ESORICS, ACSAC | Security venues that take measurement-plus-defense papers |
| IR / benchmark | SIGIR, CIKM resource track | Where the closest prior work (SIGIR'26) appeared; good if the benchmark is the main pitch |
| Workshop / fallback | AISec at ACM CCS, IEEE SaTML | Shorter, faster, still well cited in this area |
| Journal | Computers & Security, IEEE TDSC, IEEE Access | Use if the conference timing doesn't line up |

Release the code and frozen corpus as an open benchmark under the Afterimage name with one-command reproduction. Reusable benchmarks are what get cited.

## References to add

Keep all 15 from the Project-I report; these are new and each answers a reviewer question. Read the first four in full before writing related work.

1. [Tavakoli & Sanderson, *Deletion Isn't Enough: Auditing RAG for Selective Forgetting*, SIGIR 2026](https://marksanderson.org/files/papers/SIGIR2026_Leila_Main__Copy_.pdf). Closest work; we must state the difference in the first page.
2. [Chakraborttii et al., *Ghost Vectors: Soft-Deleted Embeddings Remain Reconstructible in HNSW Vector Databases*](https://arxiv.org/abs/2606.18497). Storage-layer counterpart to our app-layer study.
3. [Gu et al., *Auditing Prompt Caching in Language Model APIs*, ICML 2025](https://arxiv.org/abs/2502.07776). Timing-based cache-hit detection method for RQ3.
4. [Ryan et al., *EnronQA: Towards Personalized RAG over Private Documents*, 2025](https://arxiv.org/abs/2505.00263). Real-data track.
5. [*The Early Bird Catches the Leak: Timing Side Channels in LLM Serving Systems*](https://arxiv.org/abs/2409.20002). Serving-layer timing.
6. [Zhang et al., *From Similarity to Vulnerability: Key Collision Attack on LLM Semantic Caching*](https://arxiv.org/abs/2601.23088). Semantic-cache attacks.
7. [Anderson et al., *Is My Data in Your Retrieval Database? Membership Inference Attacks Against RAG*](https://arxiv.org/abs/2405.20446), [Naseh et al., *Riddle Me This!*](https://arxiv.org/abs/2502.00306), [*E-MIA*](https://arxiv.org/abs/2605.00955). Output-text MIA baselines we differ from.
8. [Wang et al., *Unveiling Privacy Risks in LLM Agent Memory* (MEXTRA), ACL 2025](https://arxiv.org/abs/2502.13172). Memory leakage.
9. [Costa et al., *Securing AI Agents with Information-Flow Control* (FIDES)](https://arxiv.org/abs/2505.23643). Vocabulary and prior art for taint labels.
10. [Microsoft 365 Copilot connectors: incremental permission sync](https://m365admin.handsontek.net/microsoft-copilot-microsoft-365-support-permission-sync-missed-incremental-crawl/) and [Microsoft ISE: document-level access in SharePoint RAG](https://devblogs.microsoft.com/ise/sharepoint-doc-level-access/). Industry evidence for the staleness window.
11. Carlini et al., *Membership Inference Attacks From First Principles* (IEEE S&P 2022). Justifies reporting TPR at low FPR instead of accuracy.
12. Carlini et al., *The Secret Sharer* (USENIX Security 2019). Justifies canary-based leakage measurement.

One correction for the Project-I report: drop the claim that no post-revocation benchmark exists (item 1 contradicts it). Say instead that no work measures leakage *over time* across *application-layer* artifacts in a *multi-tenant* RAG, together with metadata channels.
