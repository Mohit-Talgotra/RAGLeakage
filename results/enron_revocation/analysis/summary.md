# enron_revocation

seeds: [0, 1, 2, 3, 4]

## Revocation window

| cell | events | LM | LM_cache | LM_index | LM_memory | leak_rate | LM_all_lost | lost_docs_leaked_mean | LH_median_s | LH_median_leaking_s | censored | LH_index_median_leaking_s | analytic_index_staleness_mean_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| preset=baseline,revocation_type=single_doc | 150 | 0.415 [0.357, 0.472] | 0.415 [0.357, 0.472] | 0.408 [0.351, 0.466] | 0.296 [0.239, 0.354] | 0.693 | 0.415 [0.357, 0.472] | 0.69 | inf [43200, inf] | inf [inf, inf] | 76/150 | 43200 [43200, 86400] | 43200 |
| preset=baseline,revocation_type=role | 150 | 0.415 [0.357, 0.472] | 0.415 [0.357, 0.472] | 0.408 [0.351, 0.466] | 0.296 [0.239, 0.353] | 0.693 | 0.400 [0.367, 0.434] | 1.87 | inf [43200, inf] | inf [inf, inf] | 76/150 | 43200 [43200, 86400] | 43200 |
| preset=full,revocation_type=single_doc | 150 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 [0.000, 0.000] | 0.00 | 0 [0, 0] | n/a | 0/150 | n/a | 43200 |
| preset=full,revocation_type=role | 150 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 | 0.000 [0.000, 0.000] | 0.00 | 0 [0, 0] | n/a | 0/150 | n/a | 43200 |

Paired difference in event LM (same seeds and events):

| cell | vs | delta_LM | CI_cluster | p | p_wilcoxon | pairs |
|---|---|---|---|---|---|---|
| preset=baseline,revocation_type=role | preset=baseline,revocation_type=single_doc | 0.000 [0.000, 0.000] | [0.000, 0.000] | 1.0000 | 1.0000 | 150 |
| preset=full,revocation_type=single_doc | preset=baseline,revocation_type=single_doc | -0.415 [-0.472, -0.357] | [-0.515, -0.328] | <0.0005 | 4.6e-19 | 150 |
| preset=full,revocation_type=role | preset=baseline,revocation_type=single_doc | -0.415 [-0.472, -0.357] | [-0.515, -0.328] | <0.0005 | 4.6e-19 | 150 |

CI: event-level bootstrap; CI_cluster: two-stage bootstrap over seeds, then events. p: bootstrap (resolution 1/2000); p_wilcoxon: Wilcoxon signed-rank, zero differences dropped.

Figures: rq2_survival.png, rq1_surfaces.png
