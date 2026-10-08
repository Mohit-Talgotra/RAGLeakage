# model_grid_local

seeds: [0, 1, 2, 3, 4]

## Revocation window

| cell | events | LM | LM_cache | LM_index | LM_memory | leak_rate | LM_all_lost | lost_docs_leaked_mean | LH_median_s | LH_median_leaking_s | censored | LH_index_median_leaking_s | analytic_index_staleness_mean_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llm_backend=stub,preset=baseline | 100 | 0.646 [0.584, 0.702] | 0.646 [0.584, 0.702] | 0.638 [0.574, 0.698] | 0.305 [0.229, 0.385] | 0.820 | 0.646 [0.584, 0.702] | 0.82 | 86400 [43200, 86400] | 86400 [86400, inf] | 38/100 | 43200 [28800, 86400] | 43200 |
| llm_backend=stub,preset=full | 100 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 [0.000, 0.000] | 0.00 | 0 [0, 0] | n/a | 0/100 | n/a | 43200 |
| llm_backend=ollama,preset=baseline | 100 | 0.743 [0.711, 0.771] | 0.743 [0.711, 0.771] | 0.739 [0.704, 0.769] | 0.715 [0.678, 0.748] | 1.000 | 0.743 [0.711, 0.771] | 1.00 | inf [inf, inf] | inf [inf, inf] | 96/100 | 43200 [43200, 86400] | 43200 |
| llm_backend=ollama,preset=full | 100 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 [0.000, 0.000] | 0.00 | 0 [0, 0] | n/a | 0/100 | n/a | 43200 |

Paired difference in event LM (same seeds and events):

| cell | vs | delta_LM | CI_cluster | p | p_wilcoxon | pairs |
|---|---|---|---|---|---|---|
| llm_backend=stub,preset=full | llm_backend=stub,preset=baseline | -0.646 [-0.702, -0.584] | [-0.743, -0.547] | <0.0005 | 3.4e-16 | 100 |
| llm_backend=ollama,preset=baseline | llm_backend=stub,preset=baseline | 0.097 [0.032, 0.169] | [0.011, 0.192] | 0.0040 | 0.0040 | 100 |
| llm_backend=ollama,preset=full | llm_backend=stub,preset=baseline | -0.646 [-0.702, -0.584] | [-0.743, -0.547] | <0.0005 | 3.4e-16 | 100 |

CI: event-level bootstrap; CI_cluster: two-stage bootstrap over seeds, then events. p: bootstrap (resolution 1/2000); p_wilcoxon: Wilcoxon signed-rank, zero differences dropped.

Figures: rq2_survival.png, rq1_surfaces.png
