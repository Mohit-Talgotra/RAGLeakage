# CLAUDE.md

**Afterimage** is a research testbed for a paper on **post-revocation leakage** and **metadata existence inference** in multi-tenant RAG. Its thesis is that revocation is a consistency problem across derived artifacts (cache entries, chat memory and summaries, ACLs copied into the index), not an access check. The roadmap and source of truth is `docs/UPGRADE_PLAN.md`; read it before you change experiment logic or metrics.

Leaky behaviour is intentional when a preset or switch asks for it. Do not "fix" the `strawman`, `baseline`, `baseline_shared` or `legacy` presets.

The reviewer audit (`afterimage_reviewer_audit.md`, 22 Oct 2026) changed the testbed: `baseline` now has a per-user cache (the old tenant-shared one is `baseline_shared`), exposed scores cover authorized chunks only unless `expose_withheld_scores` (strawman), the judge scores corpus-unique values only, and there are new presets (`epoch`, `flush`, `full_fine`), revocation type `mover`, and experiment options. The post-audit grid is `configs/paper/` (run with `scripts/run_paper_grid.sh`); the paper's open slots are listed in `research_paper/RESULTS_TODO.md`.

## Commands

```bash
uv sync                                                   # Python >=3.13; uv.lock may need re-locking
uv run pytest                                             # offline, ~5 s
uv run python scripts/generate_corpus.py                  # regenerates data/ (deterministic)
uv run python run.py --config configs/smoke.yaml --seeds 1
uv run python analyze.py results/smoke                    # --reference, --train-tenants, --leakage, --judge llm, --judge-mode
uv run python run.py --config configs/paper/p0_smoke.yaml # every post-audit switch, offline, seconds
```

- Tests and `configs/smoke.yaml` use `embedder: hash` and `reranker: overlap` (no downloads). The paper configs use `all-MiniLM-L6-v2` and `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- `run.py` writes `results/<name>/runs/<cell>_s<seed>.jsonl` and skips runs it has already finished (use `--force` to redo them). `--only key=value` runs a subset of cells (one model per vLLM server in `p8_models`). `analyze.py` writes `results/<name>/analysis/`.
- Caches, all gitignored: `.cache/embeddings/` (corpus vectors) and `.cache/llm/` (real-LLM generations plus their measured latency, replayed on reruns).

## Architecture (`src/secure_pipeline/`)

The package name is historical; it holds every preset, leaky and secure. Import modules directly; `__init__.py` is empty on purpose, so light modules don't load torch.

- **Server/client boundary.** `RAGPipeline.handle()` returns `(ApiResponse, Truth)`. `Client.ask()` times the call on the shared clock, logs `{tags, truth, obs}` and returns only an `Observation` for the exposure profile (`text_only` / `with_sources` / `with_reranker`). The attacker code (`attacker.features`, `ThresholdAttacker`, `LearnedAttacker`, `analyze_existence`) must use only `obs` fields, its own query and its own strategy. **Never feed it `truth`.**
- **Clock.** Every component reads time through `clock.py`. `SimClock` = real compute time plus virtual `sleep()`/`advance()` (LLM latency, padding, hours between probes). `WallClock` is real time and refuses `advance()`. Never call `time.time()` in pipeline code.
- **Mitigations.** The `Mitigations` dataclass of switches lives in `mitigations.py`. Presets are `strawman`, `baseline`, `baseline_shared`, `legacy`, `authz_prefilter`, `authz_postfilter`, `epoch`, `flush`, `full` and `full_fine`. `OPEN_SURFACE` re-opens one artifact (RQ1). `ABLATABLE` lists the switches for leave-one-out (RQ4). Config cells can set any field directly, or use `open_surface:` or `ablate:`.
- **IAM vs derived copies.** `AccessControlManager` is live and emits a `RevocationEvent` (with `doc_ids` = docs actually lost) to its subscribers. Which components subscribe depends on the mitigations and on the `SyncPolicy` (`live`, `periodic:<s>`, `event:<drop>[:<backstop_s>]`). `VectorIndex` stores per-user `acl__<user>` booleans in Chroma metadata and filters with `where`; that copy is what goes stale (T1).
- **Taint.** `provenance.response_taint()` is the only place taint is computed. Cache entries and memory turns carry `taint: frozenset[doc_id]`. Non-transitive mode deliberately gives summaries an empty taint; that is the gap the paper's defense closes.
- **Ground truth.** `Truth.source_docs` holds the docs the returned text came from (fresh generation or the cache entry's sources). `judge.disclosed()` (mode `unique`, the default) counts only fact values that occur in no other document (`Corpus.unique_facts`), plus the canary; mode `source` is the pre-audit rule. `Corpus.secrets(doc, scorable=True)` is the denominator. Leak = canary or scorable fact value of the target doc in the response. `analyze.py` splits LM into `LM_new` (never shown at warm-up) and `LM_re`, and clusters intervals by target document.
- **Experiments** (`experiments.py`): `revocation`, `existence` (twin worlds; both worlds share the same RNG draws) and `utility`. Event sampling uses `Random(f"{seed}-events")`, so every cell sees the same targets and comparisons stay paired.
- **LLM** (`llm_client.py`): the backend is explicit (`stub|groq|openai|gemini|ollama`) and errors raise; there is never a silent stub fallback. The stub answers from the best-matching context unit (a doc or an earlier answer) and simulates latency on the clock.

- **Alternatives to taint.** `epoch_invalidation` (per-user permission epoch in `AccessControlManager.epoch`, checked on every cache/memory read; summaries never absorb stale turns) and `flush_on_revoke` (eager drop of the user's sessions and cache entries). `taint_granularity: sentence` keeps per-sentence taint on extractive summaries and, when the generator reports `Generation.used_memory` (the stub does), taints answers only with the memory items actually used.
- **Delivery and reclassification.** `PipelineConfig.hook_drop` makes eager cache/memory hooks (subscribed `lossy=True`) miss events; read-time checks never miss. `AccessControlManager.reclassify(doc, group)` narrows a document's ACL and emits one event (and epoch bump) per affected user; revocation type `reclassify`. `full_user` is `full` with a per-user cache. Revocation options `colleague_unseen` (a holder's answers about never-asked facts enter the cache) and `bystander` (second holder's session, `probe_kind=bystander_retained`).
- **Memory.** `PipelineConfig.memory_ttl_s` expires idle sessions; `summarizer: llm` writes summaries with the generator (`LLMClient.summarize`), the extractive summarizer otherwise.

## Data

`data/corpus.jsonl` and `data/iam.json` are the v2 corpus, generated by `scripts/generate_corpus.py` (seed 20261006) and committed. `--profile v3` gives every restricted doc a project sibling, multi-chunk text, corpus-unique numeric values and disjoint train/test templates; `corpus: synthetic_v3@seed` generates one v3 corpus per seed on first use (`data/synthetic_v3_s<k>/`, gitignored). `corpus: enron_c` is Enron with canaries (`scripts/build_enron_corpus.py --canaries --out data/enron_c`). A test checks they are byte-identical to a fresh generation, so after editing the generator, regenerate them and commit the result. The corpus has 5 tenants × 100 docs. Restricted docs have facts plus a unique canary and come in projects of 1–2 docs (hard twin-world negatives). Each tenant has 6 employees and 2 contractors; contractors are natural insider attackers.

## Conventions

- Module docstrings explain the threat (T1–T7) and the design choice; keep them current when behaviour changes.
- Style: `from __future__ import annotations`, dataclasses, type hints, `# ---- Section ----` banners, `print("[component] ...")` for progress (no `logging`).
- Nothing is aggregated at run time. Add new measurements as `Truth` fields or `tags`, and compute metrics in `analyze.py` / `metrics.py`.
- CIs are percentile bootstraps clustered by target document; existence AUCs resample targets. Cross-config comparisons are paired on `(seed, event)`, with Holm-adjusted p per table.
- Figures use the fixed categorical palette order in `analyze.py` (`SERIES`), one axis, thin marks, and a legend when there are ≥2 series.

## Gotchas

- The `min_relevance` default (0.25) is tuned for MiniLM. The hash embedder needs ~0.15 (tests use 0.15).
- In the existence experiment with the ACL pre-filter on, the target is invisible to the attacker in both worlds. Metadata channels can then differ only through a shared cache. `rq4_ablation_existence.yaml` therefore also runs `acl_prefilter: false`.
- The revocation experiment's fresh-session probe repeats the warm-up question verbatim (cosine 1.0), so it hits the cache at any threshold. Set `probe_paraphrase: true` (as `rq2_cache_sweep.yaml` does) whenever the cache threshold should matter.
- Revocation `LM` counts only the target's secrets, so it can't tell revocation types apart. `LM_all_lost` counts every warmed-up doc the victim lost (offboarding loses all of them), using the extra `probe_kind="lost_doc"` probes.
- `attacker.features()` rounds latency to whole milliseconds (a remote client's resolution). Without that, float noise from the padding arithmetic and sub-ms CPU time outside the padded section become a fake timing signal.
- Revocation options added by the audit (off by default): `revoke_gap_s`, `probe_readonly` (probes write neither cache nor memory), `probe_unseen`, `update_after_revoke`, `probe_paraphrase: file` (needs `data/paraphrases.json` from `scripts/make_paraphrases.py` covering every corpus the run uses, per seed; a missing question raises). Utility: `session_turns`. Real-model timing runs: `llm_cache: false`.
- Revocation options (off by default, so older configs reproduce): `warm_restricted` (warm restricted docs too, so role revocations lose more than the target), `probe_retained` (collateral probes on docs the victim still holds), `launder` (paste-back plus a colleague probe). Target metrics use only `same_session`/`new_session` probes; `analyze.collect_events` keeps the other probe kinds out of LM.
- User input is untainted (assumption A1 in `docs/TAINT_SOUNDNESS.md`); `taint_user_input` fingerprints queries against restricted secrets. `tests/test_taint_invariant.py` checks the taint invariant.
- `corpus: enron` selects `data/enron/` (built by `scripts/build_enron_corpus.py` from EnronQA; gitignored, needs pyarrow). Enron has no public docs; existence probes fall back to internal mail for the comparison topic.
- Paired tests report a Wilcoxon p (`p_wilcoxon`) and a seed-clustered CI; the bootstrap p cannot go below 1/2000.
- Chroma runs in-process (`EphemeralClient`), one collection per pipeline. Always `pipeline.close()`. `pipeline.reset()` reuses the index (and restores removed docs) but rebuilds IAM, cache and memory.
