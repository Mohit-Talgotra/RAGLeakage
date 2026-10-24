# Claim-to-evidence traceability

Every quantitative claim in the rewritten manuscript, with the artifact it came from.
All paths are relative to the repository root.

| Claim (manuscript location) | Value | Source artifact |
|---|---|---|
| Baseline leakage, daily crawl (abstract, intro, RQ5) | LM 0.634 [0.593, 0.672], leak rate 0.808 | `results/rq5_leakage/analysis/revocation_summary.csv` |
| Index leaks alone (abstract, RQ1) | 0.627 [0.586, 0.665], leak rate 0.804 | `results/rq1_surfaces/analysis/revocation_summary.csv` |
| Cache leaks alone (abstract, RQ1) | 0.491 [0.441, 0.537] | same |
| Memory leaks alone (abstract, RQ1) | 0.366 / 0.458 / 0.505 by revocation type | same |
| Memory censoring at 48 h (abstract, RQ1) | 108 / 134 / 160 of 250 | same, `censored` column |
| Blast radius, index (RQ1, `tab:blast`) | 0.627 (0.80 docs) / 0.660 (2.31) / 0.793 (6.38) | same, `LM_all_lost`, `lost_docs_leaked_mean` |
| Blast radius, cache (`tab:blast`) | 0.491 (0.64) / 0.607 (2.14) / 0.767 (6.24) | same |
| Blast radius, memory (`tab:blast`) | 0.366 (0.47) / 0.171 (0.59) / 0.119 (0.94) | same |
| Index lifetime = Δ/2 (RQ2) | 1800 s hourly, 43 200 s daily | `results/rq2_revocation_window/analysis/summary.md` |
| Sync policy LM (RQ2, `tab:rq2sync`) | 0.617 / 0.652 / 0.506 / 0.522 | `results/rq2_revocation_window/analysis/revocation_summary.csv` |
| Event-driven ΔLM (RQ2, discussion) | −0.111 [−0.145, −0.076] | `revocation_paired.csv`, same dir |
| Cache threshold sweep (RQ2, `tab:rq2cache`) | 0.464 / 0.418 / 0.367 / 0.254 | `results/rq2_cache_sweep/analysis/revocation_summary.csv` |
| Existence AUC by preset (RQ3, `tab:rq3`) | 0.984 / 0.616 / 0.592 / 0.498 (with reranker) | `results/rq3_existence/analysis/existence_eia.csv`, channel `combined`, pooled rows |
| TPR@1%FPR strawman (abstract, RQ3) | 0.728 | same |
| Per-channel AUC (`tab:rq3chan`) | reranker 0.983, score 0.883, latency 0.563, refusal 0.576, content 0.706 | same, per `channel` |
| Taint-transitive ablation (abstract, RQ4) | 0.337 [0.285, 0.389] | `results/rq4_ablation_revocation/analysis/revocation_summary.csv` |
| live_acl_check ablation (RQ4) | 0.034 [0.014, 0.058] | same |
| Pre-filter off AUC (RQ4, `tab:rq4eia`) | 0.857; 0.993 without score quantization | `results/rq4_ablation_existence/analysis/summary.md` |
| Fast-refusal backfire (RQ4, discussion) | 0.854 → 0.897 [0.885, 0.910] | same |
| Utility per preset (RQ5, `tab:rq5`) | Recall 0.993, nDCG 0.978, correct 0.947, over-refusal 0.047 | `results/rq5_utility/analysis/utility_summary.csv` |
| Latency full vs baseline (abstract, RQ5) | 1000 vs 640 ms p50 | same |
| p95 discrepancy (RQ5) | 1500 (`rq5_utility`) vs 2000 (`rq5_overhead`) | both `utility_summary.csv` files |
| **Literature baselines LM** (abstract, `tab:baselines`) | prefilter 0.500 [0.448, 0.544], postfilter 0.497 [0.446, 0.541] | `results/rq_baselines_revocation/analysis/revocation_summary.csv` |
| **Baselines ΔLM vs baseline** | −0.134 [−0.169, −0.100]; −0.138 [−0.174, −0.102] | `revocation_paired.csv`, same dir |
| **authz_postfilter existence AUC** (abstract, `tab:baselines`) | 0.992 [0.989, 0.995], TPR 0.887 | `results/rq_baselines_existence/analysis/existence_eia.csv` |
| **Collateral recall** (abstract, `tab:collateral`) | 0.454 → 0.334; refusal 0.283 → 0.499 | `results/rq5_collateral/analysis/revocation_summary.csv` |
| **Collateral, Llama-3.1-8B** (`tab:collateral`) | 0.944 → 0.675 | `results/rq5_collateral_8b/analysis/revocation_summary.csv` |
| **No-transitive-taint variant** (`tab:collateral`) | LM 0.359 / 0.460; recall 0.444 / 0.451 | `results/rq5_collateral/analysis/revocation_summary.csv` |
| **Laundering** (abstract, `tab:stress`) | LM 0.142 [0.087, 0.202], success 0.450, colleague 0.013 | `results/rq6_taint_stress_8b/analysis/revocation_summary.csv` |
| **Authz overhead** (`tab:overhead`) | 2.06 calls/query; 764 / 794 ms nopad; 1000 ms padded | `results/rq5_overhead/analysis/utility_summary.csv` |
| **Enron revocation** (abstract, `tab:enron`) | baseline 0.415 [0.357, 0.472]; full 0.000 | `results/enron_revocation/analysis/revocation_summary.csv` |
| **Enron + Llama-3.1-8B** (`tab:enron`) | baseline 0.279 [0.189, 0.368]; full 0.000 | `results/enron_revocation_8b/analysis/revocation_summary.csv` |
| **Enron existence** (`tab:enron`) | 0.836 / 0.573 / 0.500 | `results/enron_existence/analysis/existence_eia.csv` |
| Qwen2.5-3B revocation (`tab:realllm`) | 0.743 [0.711, 0.771]; paired +0.097, p=0.004 | `results/model_grid_local/analysis/` |
| **Llama-3.1-8B revocation** (`tab:realllm`) | baseline 0.550 [0.518, 0.582]; paired −0.096, p=0.016 | `results/model_grid_8b/analysis/` |
| **Llama-3.1-8B full is non-zero** (abstract, RQ real) | 0.002 [0.000, 0.006], 1/100 events, 7200 s | same |
| **Llama-3.1-8B existence under full** | 0.535 [0.501, 0.568]; latency 0.529 | `results/rq3_existence_8b/analysis/existence_eia.csv` |
| Qwen2.5-3B existence (`tab:realllm-eia`) | 0.974 / 0.550 / 0.509; latency 0.645 / 0.530 / 0.502 | `results/rq3_existence_local/analysis/existence_eia.csv` |
| **Paraphrase judge** (RQ judge, limitations) | extra 0.000 on 8B cells; 0.007 on stub full | `results/judge_sample/judge_summary.md` |
| **Bucket residual** (discussion) | 0.516 (8B), 0.509 (Qwen) | `results/CHECKLIST.md` §3, `*/analysis/pad_buckets.csv` |

## Values deliberately NOT claimed

| Not claimed | Why |
|---|---|
| Judge precision | `results/judge_sample/judge_validation.csv` has `human_label` empty on all 150 rows |
| Qwen2.5-7B, `gpt-oss-120b` results | `results/model_grid_7b/`, `results/model_grid_groq/` hold a manifest and zero runs |
| Embedder sensitivity | `configs/model_grid.yaml` exists, no results directory |
| Paraphrased laundering | only verbatim laundering was run |
| Absolute timing on other hardware | one machine for every run |

## Figures

`fig1`–`fig8` are unchanged and correspond to the main experiments. The five new
experiments are reported in tables only; `fig6_rq5_pareto.pdf` therefore shows the four
original presets and does not include the `authz_*` points.
