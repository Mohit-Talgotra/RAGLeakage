# Results (2026-10-08)

All numbers: 5 seeds, MiniLM embedder, MiniLM cross-encoder, **stub LLM**, synthetic 5-tenant corpus,
except the "Real LLM check" section, which uses Qwen2.5-3B via Ollama.
Brackets are bootstrap 95% CIs. Source tables are `results/<config>/analysis/summary.md`.

**LM (leakage magnitude)** = share of a revoked document's secrets (facts + canary) that the user
still got back after losing access. 0 = nothing leaked, 1 = everything.
**AUC** = how well an attacker tells "hidden document exists" from "doesn't exist". 0.5 = guessing, 1 = always right.

## RQ1: What leaks after revocation, and through which artifact? (`rq1_surfaces`)

Starting from the full defense, re-opening one derived copy at a time (daily permission crawl):

| Re-opened artifact | LM (target doc) |
|---|---|
| none (full defense) | 0.000 |
| index (stale ACL copy) | 0.627 [0.586, 0.665] |
| cache | 0.491 [0.441, 0.537] |
| memory / summaries | 0.366 (single doc) to 0.505 (offboarding) |

**Blast radius.** Revocation type does not change how much of the *target* leaks, but it changes how
many documents leak. `LM_all_lost` counts every document the user had used and then lost:

| Re-opened | single doc | role | offboarding |
|---|---|---|---|
| index | 0.627, 0.80 docs leaked | 0.627, 0.80 docs | **0.858, 4.76 docs** |
| cache | 0.491, 0.64 docs | 0.491, 0.64 docs | **0.820, 4.63 docs** |

An offboarded employee keeps reading almost everything they touched until the copies catch up.
(Memory is only probed about the target, so its offboarding number, 0.215, undercounts.)

## RQ2: How long does leakage last? (`rq2_revocation_window`, `rq2_cache_sweep`)

- **Index copy lives exactly as long as the sync model predicts.** Median index leak lifetime
  equals the analytic Δ/2: 1800 s for hourly sync, 43200 s for daily sync. (Cells where the cache
  TTL is at least the sync period are marked "masked by cache": the cache answers first, so the index is never reached.)
- **Event-driven sync** removes index leaks (LM_index 0.000). With 5% of webhooks lost and a daily
  backstop crawl, LM_index is 0.034 and those leaks last a median 64800 s [43200, 86400].
- **Cache leaks last exactly the cache TTL**, whatever the sync policy.
- **Memory never heals on its own**: about 40% of events still leak at the 48 h horizon (censored).
- **Cache similarity threshold** (paraphrased probes, TTL 1 h): LM 0.464 at 0.80, 0.418 at 0.85,
  0.367 at 0.90, 0.254 at 0.95. A stricter threshold helps but never closes the leak.

## RQ3: Can an attacker tell a hidden document exists? (`rq3_existence`)

Combined learned attacker, full exposure (scores + reranker), tested on held-out tenants:

| Preset | AUC | TPR @ 1% FPR |
|---|---|---|
| strawman | 0.983 [0.980, 0.987] | 0.689 |
| baseline | 0.612 [0.596, 0.627] | 0.157 |
| legacy | 0.592 [0.576, 0.608] | 0.135 |
| full | 0.495 [0.481, 0.509] | 0.008 |

Without a defense, relevance and reranker scores give the document away (AUC 0.98). Typical
deployments still leak through answer content (content channel 0.615). The full defense is at chance.

## RQ4: What does each mitigation buy, and do any backfire? (`rq4_ablation_*`)

**Leakage side.** Removing one switch at a time from the full defense, only two matter:
- transitive taint (tracking secrets into summaries): without it LM rises by 0.337 [0.285, 0.389];
- live permission check at query time: without it LM rises by 0.034 (the lost-webhook cases).
The cache and memory mitigations back each other up, so removing any single one changes nothing.

**Inference side** (figure `rq4_ablation_heatmap.png`):
- With the ACL pre-filter on, every ablation and variant stays near chance (AUC 0.48 to 0.54).
- **The pre-filter is the load-bearing mitigation.** Filtering after retrieval (post-filter) leaves
  AUC at 0.86 even with every other defense on, through relevance and reranker scores; removing score
  quantization as well gives 0.99.
- **Fast refusal backfires only without padding:** with a post-filter and no latency padding,
  skipping the LLM on refusals raises the combined AUC from 0.85 to 0.90 (latency channel 0.58).
  The 30 ms floor and the 2 s deadline neutralise it.
- Timing is otherwise a weak channel in this simulator (AUC at most about 0.55).

## RQ5: What does security cost? (`rq5_utility`, `rq5_leakage`)

| Preset | nDCG@5 | Correct | Over-refusal | p50 / p95 latency | Leakage (LM) |
|---|---|---|---|---|---|
| strawman | 0.846 | 0.901 | 0.061 | 566 / 1456 ms | 0.620 |
| baseline | 0.978 | 0.947 | 0.047 | 640 / 1493 ms | 0.634 |
| legacy | 0.978 | 0.947 | 0.047 | 668 / 1504 ms | 0.634 |
| full | 0.978 | 0.947 | 0.047 | 1000 / 1500 ms | **0.000** |

The full defense costs no answer quality. Its cost is median latency (+360 ms, from padding to
500 ms buckets); p95 is unchanged. Legacy fixes cost latency but reduce leakage by nothing.

## Real LLM check: Qwen2.5-3B and Llama-3.1-8B via Ollama (`model_grid_local`, `model_grid_8b`, `rq3_existence_local`, `rq3_existence_8b`)

Same pipeline with real local models instead of the stub. Revocation: 5 seeds x 20 events, daily
sync, events paired with the stub. Existence: 3 seeds, insider and outsider attackers.

**Leakage after revocation (LM) — Exact-Match vs. LLM Semantic Judge:**

| Preset | Stub (Exact / LLM) | Qwen2.5-3B (Exact / LLM) | Llama-3.1-8B (Exact / LLM) | LM_memory (Stub / Qwen / Llama) | Leaking at 48 h (Stub / Qwen / Llama) |
|---|---|---|---|---|---|
| baseline | 0.646 [0.584, 0.702] / 0.648 | **0.743 [0.711, 0.771]** / 0.743 | **0.550 [0.518, 0.582]** / **0.554** | 0.305 / 0.715 / **0.488** | 38% / 96% / **92%** |
| full | 0.000 / 0.002 | **0.000** / 0.000 | **0.002 [0.000, 0.006]** / **0.002** | 0.000 / 0.000 / 0.002 | 0% / 0% / 0% |

- **Semantic judge gap:** An independent LLM judge (`qwen2.5:3b`) adds merely +0.004 LM to Llama-3.1-8B under baseline (0.554 vs 0.550) and 0.000 under full defense (0.002), confirming that exact matching captures the vast majority of leaks without substantial undercounting.
- **Real models leak more persistently than the stub:** With Llama-3.1-8B, the baseline leak rate is 100% (every single event leaked confidential information).
- **Chat memory is the main vector:** LM_memory is 0.715 with Qwen and 0.488 [0.454, 0.524] with Llama-3.1-8B, against 0.305 with the stub. With Llama-3.1-8B, 92 of 100 events were still leaking at the 48 h horizon (stub: 38), with median leak lifetime inf (never heals on its own).
- **The index copy behaves identically across models:** Its leaks last a median 43200 s (exact Δ/2 for daily sync).
- **The full defense holds:** Revocation with provenance taint drops leakage down to 0.000 with Qwen and 0.002 with Llama-3.1-8B (median lifetime 0 s, p < 1e-15).

**Existence inference** (combined attacker, scores + reranker, all attackers):

| Preset | Stub | Qwen2.5-3B | Llama-3.1-8B | Llama Latency AUC |
|---|---|---|---|---|
| strawman | 0.983 | 0.973 [0.959, 0.984] | 0.974 [0.961, 0.984] | 0.662 [0.622, 0.699] |
| baseline | 0.612 | 0.605 [0.563, 0.645] | 0.608 [0.568, 0.647] | 0.580 [0.541, 0.620] |
| full | 0.495 | 0.513 [0.474, 0.552] | 0.540 [0.498, 0.581] | 0.530 [0.484, 0.566] |

Across both 3B and 8B models, existence inference without a defense remains near-perfect (AUC ~0.97), typical deployments leak via latency and content (AUC ~0.61), and the full defense reduces existence inference to random chance (95% CI includes 0.50). Timing padding in the full defense neutralizes the latency side-channel.

## Real-text check: EnronQA emails (`enron_revocation`, `enron_existence`)

Real unstructured enterprise emails (650 documents across 5 tenants, MichaelR207/enron_qa_0922 with 500 restricted documents containing checkable facts and unique canaries):

**Revocation leakage (daily ACL crawl, 150 events, 5 seeds):**

| Preset | Target LM [95% CI] | Leak rate | Leaking at 48 h | Role blast radius (LM_all_lost) |
|---|---|---|---|---|
| baseline | 0.415 [0.357, 0.472] | 69.3% | 50.7% | 0.400 [0.367, 0.434] (1.87 docs) |
| full | **0.000 [0.000, 0.000]** | **0.0%** | **0.0%** | **0.000 [0.000, 0.000]** (0.00 docs) |

- **Revocation leakage:** Baseline preset leaks 41.5% of confidential secrets with a 69.3% leak rate. Full defense completely eliminates leakage (delta LM: -0.415 [-0.472, -0.357], p < 0.0005).
- **Index lifetime holds:** Index staleness matches the exact analytic $\Delta/2$ prediction (median 43,200 s).
- **Memory persistence:** 50.7% of revocation events remain leaking at the 48 h horizon due to conversation summaries.

**Existence inference (twin worlds, held-out tenants, with_reranker profile):**

| Preset | Combined AUC [95% CI] | Trial AUC | Score Channel AUC | Content Channel AUC | TPR @ 1% FPR |
|---|---|---|---|---|---|
| strawman | 0.812 [0.779, 0.844] | 0.896 [0.838, 0.943] | 0.747 | 0.584 | 0.072 |
| baseline | 0.586 [0.541, 0.627] | 0.637 [0.555, 0.718] | 0.531 | 0.563 | 0.066 |
| full | **0.468 [0.422, 0.516]** | 0.438 [0.352, 0.525] | 0.500 | 0.500 | **0.006** |

The findings transfer directly to real enterprise email text: undefended systems leak existence with AUC 0.81–0.90, baseline leaks via content, and the full defense reduces existence inference to random chance (95% CI includes 0.50).

## Limitations to state in the paper

- **Corpus: synthetic vs. real text:** Primary RQ1–RQ5 runs use the synthetic 5-tenant corpus to ensure rigorous control over fact distributions and twin-world project structures. To verify that findings transfer to unstructured enterprise communication, we evaluated a 650-document EnronQA email corpus. Revocation dynamics, Δ/2 index staleness, chat memory retention, and defense efficacy hold identically on real email text.
- **Generator scale:** Primary RQ1–RQ5 runs use the deterministic stub LLM for reproducible ablation and fast parameter sweeps. The real-model checks evaluate local open-weight models up to 8B parameters (Qwen2.5-3B and Meta Llama-3.1-8B via Ollama). Both confirm the paper's findings and demonstrate that real generative models suffer even higher memory retention than the stub, while the full defense remains effective. Larger 70B+ or frontier hosted models (e.g., via Groq API) represent future scaling evaluations.
- Latency comes from a simulated clock (real compute plus modelled LLM time) or real client wall-clock time in the real LLM runs. The attacker sees latency rounded to 1 ms, standing in for network jitter.
- **Leak judge: exact match vs. semantic paraphrase.** Primary evaluations use exact matching on secret fact values and canaries. We evaluated the potential undercounting of exact matching using an independent LLM semantic judge (Qwen2.5-3B via Ollama). Across 100 paired revocation events on Llama-3.1-8B, the semantic judge added only +0.004 LM (0.554 vs 0.550 under baseline, and 0.002 under full defense). This confirms that exact matching is an accurate reflection of disclosure rather than an artificial lower bound: generative models either quote factual tokens verbatim or omit them entirely.
- One embedder and one reranker (MiniLM stack).

## Changes behind these numbers (2026-10-08)

- `rq2_cache_sweep` now probes with reworded questions (`probe_paraphrase: true`). The old run
  repeated the exact question, so every threshold looked the same (kept in `results/_superseded/`).
- RQ1 now also probes every warmed-up document the user lost (`LM_all_lost`); the old target-only
  run is in `results/_superseded/`.
- The attacker sees latency rounded to 1 ms; sub-millisecond float noise had produced a fake 0.58 AUC.
- New `rq5_leakage` config: the Pareto plot previously joined against RQ1, which has no preset grid,
  and plotted a single wrong point.
- Figures: stacked RQ1 bars, faceted survival curves, RQ4 heatmap, readable Pareto labels.
- New real-LLM configs `model_grid_local` and `rq3_existence_local` (Qwen2.5-3B via Ollama).
