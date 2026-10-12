# model_grid_8b

seeds: [0, 1, 2, 3, 4]

## Revocation window

| cell | events | LM | LM_cache | LM_index | LM_memory | leak_rate | LM_all_lost | lost_docs_leaked_mean | LH_median_s | LH_median_leaking_s | censored | LH_index_median_leaking_s | analytic_index_staleness_mean_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llm_backend=stub,preset=baseline | 100 | 0.648 [0.587, 0.705] | 0.648 [0.587, 0.705] | 0.640 [0.576, 0.699] | 0.305 [0.229, 0.385] | 0.820 | 0.648 [0.587, 0.705] | 0.82 | 86400 [43200, 86400] | 86400 [86400, inf] | 38/100 | 43200 [28800, 86400] | 43200 |
| llm_backend=stub,preset=full | 100 | 0.002 [0.000, 0.005] | 0.002 [0.000, 0.005] | 0.000 [0.000, 0.000] | 0.002 [0.000, 0.005] | 0.010 | 0.002 [0.000, 0.005] | 0.01 | 0 [0, 0] | inf [inf, inf] | 1/100 | n/a | 43200 |
| llm_backend=ollama,preset=baseline | 100 | 0.554 [0.522, 0.587] | 0.442 [0.403, 0.483] | 0.538 [0.501, 0.575] | 0.492 [0.458, 0.528] | 1.000 | 0.554 [0.522, 0.587] | 1.00 | inf [inf, inf] | inf [inf, inf] | 92/100 | 43200 [43200, 86400] | 43200 |
| llm_backend=ollama,preset=full | 100 | 0.002 [0.000, 0.006] | 0.002 [0.000, 0.006] | 0.000 [0.000, 0.000] | 0.002 [0.000, 0.006] | 0.010 | 0.002 [0.000, 0.006] | 0.01 | 0 [0, 0] | 7200 [7200, 7200] | 0/100 | n/a | 43200 |

Paired difference in event LM (same seeds and events):

| cell | vs | delta_LM | CI_cluster | p | p_wilcoxon | pairs |
|---|---|---|---|---|---|---|
| llm_backend=stub,preset=full | llm_backend=stub,preset=baseline | -0.646 [-0.703, -0.584] | [-0.743, -0.549] | <0.0005 | 2.9e-16 | 100 |
| llm_backend=ollama,preset=baseline | llm_backend=stub,preset=baseline | -0.094 [-0.159, -0.016] | [-0.189, 0.003] | 0.0170 | 0.0042 | 100 |
| llm_backend=ollama,preset=full | llm_backend=stub,preset=baseline | -0.646 [-0.703, -0.584] | [-0.743, -0.548] | <0.0005 | 3.4e-16 | 100 |

CI: event-level bootstrap; CI_cluster: two-stage bootstrap over seeds, then events. p: bootstrap (resolution 1/2000); p_wilcoxon: Wilcoxon signed-rank, zero differences dropped.

Figures: rq2_survival.png, rq1_surfaces.png
