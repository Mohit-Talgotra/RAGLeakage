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

## Real LLM check: Qwen2.5-3B via Ollama (`model_grid_local`, `rq3_existence_local`)

Same pipeline with a real local model instead of the stub. Revocation: 5 seeds x 20 events, daily
sync, events paired with the stub. Existence: 3 seeds, insider and outsider attackers.

**Leakage after revocation (LM):**

| Preset | Stub | Qwen2.5-3B | Qwen minus stub (paired) |
|---|---|---|---|
| baseline | 0.646 [0.584, 0.702] | 0.743 [0.711, 0.771] | +0.097 [0.032, 0.169], p = 0.004 |
| full | 0.000 | 0.000 | |

- The real model leaks **more** than the stub, so the stub numbers are conservative.
- The gap is mostly chat memory: LM_memory is 0.715 with Qwen against 0.305 with the stub. With
  earlier answers in its context, Qwen repeats them; it refused only 1 of 100 same-session probes at
  48 h (stub: 21). In 96 of 100 events Qwen was still leaking at the 48 h horizon (stub: 38).
- The index copy behaves the same with either model: its leaks last a median 43200 s (Δ/2 for daily sync).
- The full defense stays at exactly 0 with the real model.
- Judge check: Qwen quotes figures verbatim. Among fact values the exact-match judge missed, none
  appear in reformatted form (e.g. "$1.8 billion" for "$1.8B"). Qwen drops the canary string more often
  than the stub (48 vs 101 of 2400 probes), so its LM is, if anything, slightly undercounted.

**Existence inference** (combined attacker, scores + reranker, all attackers):

| Preset | Stub | Qwen2.5-3B |
|---|---|---|
| strawman | 0.983 | 0.973 [0.959, 0.984] |
| baseline | 0.612 | 0.605 [0.563, 0.645] |
| full | 0.495 | 0.513 [0.474, 0.552] (chance) |

Same picture as the stub. One difference: with a real model, timing becomes a usable channel in
undefended deployments (latency AUC 0.66 strawman, 0.60 baseline, against 0.56 and 0.51 with the stub),
because a refusal is much faster than a real generation. Padding in the full defense removes it (0.507).

## Limitations to state in the paper

- **Mostly a stub LLM.** RQ1-RQ5 use the stub. The real-model check uses one small local model
  (Qwen2.5-3B) on two configs; it confirms the findings and shows the stub underestimates memory
  leakage. A large hosted model (`configs/model_grid.yaml`, Groq) has not been run.
- Corpus is template-generated and synthetic; EnronQA is not used.
- Latency comes from a simulated clock (real compute plus modelled LLM time). The attacker sees
  latency rounded to 1 ms, standing in for network jitter.
- Leaks are judged by exact fact/canary matches. A normalized-match check on Qwen output found no
  missed reformatted values; the LLM paraphrase judge (`--judge llm`) has not been run.
- One embedder and one reranker.

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
