# Verified evidence ledger

Numerical source of truth for the manuscript. Built 2026-10-14 by reading
`results/*/analysis/` directly. Every value below was read from
`revocation_summary.csv`, `existence_eia.csv`, `utility_summary.csv` or the
corresponding `summary.md`.

## Provenance warning

`results/RESULTS_FOR_PAPER.md` is dated **2026-10-08** and its limitations
section states that the Enron track, the LLM paraphrase judge, larger models and
Groq "were not run". **That document is stale.** All analyses except three were
re-run on **2026-10-14** (`results/CHECKLIST.md`, same date). The manuscript was
written from the stale ledger, which is the root cause of most of the audit
findings. Stale analysis dirs: `model_grid_local`, `rq2_revocation_window`,
`rq3_existence_local` (2026-10-11), and `smoke` (2026-10-07).

## Experiments that did NOT run

| Dir | Evidence | Consequence |
|---|---|---|
| `model_grid_7b` | `manifest.json` only; 0 run files, no `analysis/` | Qwen2.5-7B was planned, never executed |
| `model_grid_groq` | `manifest.json` only; 0 run files, no `analysis/` | `gpt-oss-120b` via Groq was planned, never executed |

`methodology.tex` currently states both were run. That claim must be removed.

## Main revocation experiments (stub generator)

### rq1_surfaces — one artifact re-opened at a time, 250 events/cell, 5 seeds
| Open surface | Revocation type | LM [95% CI] | leak_rate |
|---|---|---|---|
| none (full defense) | all three | 0.000 [0.000, 0.000] | 0.000 |
| index | all three | 0.627 [0.586, 0.665] | 0.804 |
| cache | all three | 0.491 [0.441, 0.537] | 0.640 |
| memory | single_doc | 0.366 [0.315, 0.413] | 0.468 |
| memory | role | 0.458 [0.408, 0.505] | 0.580 |
| memory | user_offboard | 0.505 [0.454, 0.551] | 0.640 |

Target-only LM is identical across revocation types for index and cache by
construction. 750 full-defense events at exactly zero.

### rq2_revocation_window — propagation policy, 200 events/cell
| Sync | LM | LM_index | leak_rate |
|---|---|---|---|
| periodic:3600 (hourly) | 0.617 [0.569, 0.663] | 0.565 | 0.790 |
| periodic:86400 (daily) | 0.652 [0.608, 0.693] | 0.648 | 0.835 |
| event:0.0 (webhook, no loss) | 0.506 [0.453, 0.559] | 0.000 | 0.650 |
| event:0.05:86400 (5% loss + backstop) | 0.522 [0.468, 0.573] | 0.034 | 0.670 |

Index leak median lifetime equals the analytic Δ/2 exactly: 1800 s hourly,
43200 s daily. Cache TTL does not change LM. LM_memory 0.312–0.334.

### rq2_cache_sweep — similarity threshold, 200 events/cell, TTL 3600 s
0.80 → 0.464 [0.410, 0.516]; 0.85 → 0.418 [0.363, 0.473];
0.90 → 0.367 [0.312, 0.425]; 0.95 → 0.254 [0.203, 0.305].
TTL sets lifetime, not magnitude (LM identical within ±0.004 across 600/3600/21600 s).

### rq4_ablation_revocation — leave-one-out from full, lossy webhooks, 200 events
| Removed | LM |
|---|---|
| none | 0.000 |
| `taint_transitive` | **0.337 [0.285, 0.389]** (LM_memory 0.337, LM_cache 0.259) |
| `live_acl_check` | 0.034 [0.014, 0.058] |
| `acl_prefilter`, `cache_evict`, `cache_lazy_check`, `memory_purge`, `memory_lazy_check` | 0.000 each |

### rq5_leakage — presets, 250 events/cell, daily sync
strawman 0.620 [0.576, 0.659]; baseline 0.634 [0.593, 0.672] (leak_rate 0.808);
legacy 0.634 [0.593, 0.671]; full 0.000.

## Literature baselines (NEW — not in the manuscript)

### rq_baselines_revocation — 250 events/cell, 5 seeds
| Preset | single_doc LM | user_offboard LM_all_lost | docs leaked/event | LM_index |
|---|---|---|---|---|
| baseline | 0.634 [0.593, 0.672] | 0.798 [0.784, 0.813] | 6.42 | 0.627 |
| `authz_prefilter` | 0.500 [0.448, 0.544] | 0.771 [0.754, 0.787] | 6.24 | 0.000 |
| `authz_postfilter` | 0.497 [0.446, 0.541] | 0.769 [0.752, 0.785] | 6.18 | 0.000 |
| full | 0.000 | 0.000 | 0.00 | 0.000 |

Paired vs baseline: prefilter ΔLM −0.134 [−0.169, −0.100]; postfilter
−0.138 [−0.174, −0.102]; both p<0.0005. **Both published designs remove index
leakage entirely and still leak ~0.50, because neither touches cache or memory.**

### rq_baselines_existence — combined attacker, with_reranker, pooled
| Preset | AUC | TPR@1%FPR |
|---|---|---|
| baseline | 0.618 [0.595, 0.641] | 0.151 |
| `authz_prefilter` | 0.602 [0.577, 0.627] | 0.158 |
| `authz_postfilter` | **0.992 [0.989, 0.995]** | 0.887 |
| full | 0.514 [0.489, 0.538] | 0.014 |

**A check-after-retrieve design is near-perfectly vulnerable to existence
inference.** This is the strongest comparative result available and is absent
from the current manuscript.

## Existence inference (combined attacker, gboost, pooled insider+outsider)

### rq3_existence — 4800 test probes/cell, 5 seeds
| Preset | text_only | with_sources | with_reranker | TPR@1%FPR (reranker) |
|---|---|---|---|---|
| strawman | — | — | 0.984 [0.981, 0.987] | 0.728 |
| baseline | — | — | 0.616 [0.600, 0.632] | 0.158 |
| legacy | — | — | 0.592 [0.576, 0.607] | 0.133 |
| full | — | — | 0.498 [0.481, 0.513] | 0.008 |

NOTE: the manuscript cites 0.983 / 0.612 / 0.592 / 0.495 from the Oct 8 ledger.
The Oct 14 re-analysis gives 0.984 / 0.616 / 0.592 / 0.498. **Use the newer values.**

### rq3_existence_8b — Llama-3.1-8B, 1280 test probes/cell, 5 seeds
strawman 0.982 [0.974, 0.988] TPR 0.903; baseline 0.625 [0.595, 0.653];
full **0.535 [0.501, 0.568]** TPR 0.009.
Full is slightly above chance here, unlike the stub (0.498).

### rq3_existence_local — Qwen2.5-3B, 768 test probes/cell, 3 seeds
strawman 0.974 [0.961, 0.985]; baseline 0.550 [0.509, 0.590];
full 0.509 [0.469, 0.547]. Latency channel: strawman 0.659, baseline 0.596,
full 0.507 — timing becomes usable with a real model and padding removes it.

### enron_existence — real Enron text, 3200 test probes/cell, 5 seeds
strawman 0.836 [0.822, 0.849] TPR 0.118; baseline 0.573 [0.552, 0.592];
full 0.500 [0.480, 0.521] TPR 0.005.

## Real-model revocation

### model_grid_8b — Llama-3.1-8B vs stub, 100 events/cell, 5 seeds
| Cell | LM | LM_cache | LM_index | LM_memory | leak_rate | censored |
|---|---|---|---|---|---|---|
| stub, baseline | 0.646 [0.584, 0.702] | 0.646 | 0.638 | 0.305 | 0.820 | 38/100 |
| stub, full | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0/100 |
| ollama(8B), baseline | 0.550 [0.518, 0.582] | 0.442 | 0.538 | 0.488 | **1.000** | 92/100 |
| ollama(8B), full | **0.002 [0.000, 0.006]** | 0.002 | 0.000 | 0.002 | 0.010 | 0/100 |

Paired 8B−stub at baseline: **−0.096 [−0.161, −0.020], p=0.016, Wilcoxon 0.0025.**
**Llama-3.1-8B leaks LESS overall than the stub**, but its memory leakage is
higher (0.488 vs 0.305) and every event leaked (leak_rate 1.000, 92% censored
at 48 h). **The full defense is NOT exactly zero with 8B: LM 0.002, one event
in 100, median lifetime of that leak 7200 s.**

### model_grid_local — Qwen2.5-3B vs stub, 100 events/cell (analysis dated Oct 11)
baseline: stub 0.646, Qwen **0.743 [0.711, 0.771]**, paired +0.097 [0.032, 0.169], p=0.004.
LM_memory stub 0.305 / Qwen 0.715. Censored 38/100 vs 96/100. full 0.000 both.
**Qwen leaks more than the stub; Llama-3.1-8B leaks less. The direction is
model-dependent, so "the stub is conservative" does not generalise.**

### enron_revocation — real Enron text, stub, 150 events/cell, 5 seeds
baseline single_doc & role: LM 0.415 [0.357, 0.472], leak_rate 0.693,
LM_index 0.408, LM_memory 0.296, 76/150 censored, index lifetime 43200 s = Δ/2.
role LM_all_lost 0.400 [0.367, 0.434], 1.87 docs/event.
full (both types): 0.000, 0/150 censored.

### enron_revocation_8b — Enron + Llama-3.1-8B, 24 events/cell, 2 seeds
baseline 0.279 [0.189, 0.368], leak_rate 0.667; full 0.000, 0/24 censored.

## Defense cost

### rq5_utility — 3000 queries/preset, 5 seeds
| Preset | Recall@5 | nDCG@5 | Correct | Over-refusal | p50/p95 ms | Cache hit |
|---|---|---|---|---|---|---|
| strawman | 0.945 | 0.846 | 0.901 | 0.061 | 566 / 1456 | 0.936 |
| baseline | 0.993 | 0.978 | 0.947 | 0.047 | 640 / 1493 | 0.952 |
| legacy | 0.993 | 0.978 | 0.947 | 0.047 | 668 / 1504 | 0.952 |
| full | 0.993 | 0.978 | 0.947 | 0.047 | 1000 / 1500 | 0.930 |

### rq5_overhead — IAM round-trip cost, 3000 queries/cell (NEW)
p50: baseline 694/690/691 ms at 0/2/10 ms RPC; full 1000 ms at all three;
**full_nopad 764/769/794 ms**. p95: baseline ~1540, full 2000, full_nopad ~1550.
`authz_calls` per query: baseline 0.00, full 2.06.
**Padding is essentially the entire latency cost: +70 ms without it, +306 ms with
it. A remote IAM at 10 ms adds ~30 ms. p95 under full is 2000 ms, not 1500 —
the rq5_utility p95 of 1500 does not reproduce here.**

### rq5_collateral — cost of over-tainting, 200 events/cell, 5 seeds (NEW)
| Variant | retained_recall_same | retained_refusal_same | LM |
|---|---|---|---|
| baseline (single_doc) | 0.454 [0.429, 0.481] | 0.283 | 0.652 |
| legacy (single_doc) | 0.444 | 0.281 | 0.655 |
| **full (single_doc)** | **0.334 [0.311, 0.356]** | **0.499 [0.465, 0.530]** | 0.000 |
| full_no_transitive (single_doc) | 0.444 | 0.284 | 0.359 |
| baseline (role) | 0.505 | 0.206 | 0.652 |
| **full (role)** | **0.353 [0.331, 0.374]** | **0.516 [0.481, 0.551]** | 0.000 |
| full_no_transitive (role) | 0.451 | 0.215 | 0.460 |

`retained_recall_new` is 1.000 for every variant. **Over-tainting is a real cost:
in the session that triggered the revocation, recall on documents the user still
holds drops from 0.454 to 0.334 and refusals roughly double (0.283 → 0.499).
Dropping transitive taint restores retained recall but reinstates 0.36–0.46 LM.
This is a genuine security/utility trade-off the manuscript does not report.**

### rq5_collateral_8b — same with Llama-3.1-8B, 16 events/cell, 2 seeds
baseline retained_recall_same 0.944 → full **0.675 [0.560, 0.790]** (single_doc);
0.933 → 0.669 (role). retained_recall_new 1.000 under full.

## Assumption A1 under attack (NEW)

### rq6_taint_stress_8b — paste-back laundering, Llama-3.1-8B, 40 events/cell, 2 seeds
| Cell | LM | launder_success | LM_colleague |
|---|---|---|---|
| `taint_user_input=False` | 0.142 [0.087, 0.202] | **0.450** | 0.013 [0.000, 0.037] |
| `taint_user_input=True` | 0.000 | 0.000 | 0.000 |

Paired ΔLM −0.142 [−0.202, −0.087], p<0.0005.
**Assumption A1 is violated in practice. A revoked user who pastes a previously
received answer back into a fresh session launders it successfully 45% of the
time, recovering 14% of the target's secrets, and a colleague without access
receives the target's secrets in 1.3% of events. The optional query-fingerprinting
switch closes this completely in this testbed.** This is the most important
negative result in the project and it is absent from the manuscript.

## Paraphrase judge (NEW)

`results/judge_sample/` — independent `qwen2.5:7b` judge over 150 sampled
responses per cell, on Llama-3.1-8B outputs:
- `model_grid_8b` baseline: exact leak_rate 0.493 (stub) / 0.807 (8B);
  **extra_leak_rate_llm = 0.000**
- `model_grid_8b` full: exact 0.000, extra LLM 0.000
- `enron_revocation_8b` baseline: exact 0.260, extra LLM 0.000
- `enron_revocation_8b` full: exact 0.000, extra LLM 0.000

**The LLM judge found zero additional leaks over exact matching.** The
manuscript's claim that "a semantic judge was not run" is false and its
exact-match lower-bound caveat can now be tightened to an empirical result.

## Latency-padding residual (from CHECKLIST.md)

`rq3_existence_8b` preset=full, 500 ms bucket: AUC_bucket_only **0.516**;
world1 bucket shares 0.028 / 0.003 / 0.969, world0 0.031 / 0.003 / 0.966.
`rq3_existence_local` preset=full: AUC_bucket_only **0.509**; world1
0.317 / 0.386 / 0.297, world0 0.331 / 0.382 / 0.286.
The manuscript's discussion quotes 0.508 with shares 8.2/57.0/34.8 vs
8.7/57.9/33.3 — **those figures match neither current file. Replace them.**
