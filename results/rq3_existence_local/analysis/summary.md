# rq3_existence_local

seeds: [0, 1, 2]

## Existence inference (twin worlds, held-out tenants)

| cell | profile | model | channel | AUC | AUC_trial | TPR@1%FPR | balanced_acc | n_test |
|---|---|---|---|---|---|---|---|---|
| preset=strawman | text_only | threshold | rules | 0.548 [0.515, 0.580] | 0.552 [0.472, 0.624] | 0.000 | 0.523 | 768 |
| preset=strawman | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=strawman | text_only | gboost | latency | 0.659 [0.621, 0.695] | 0.801 [0.734, 0.854] | 0.000 | 0.604 | 768 |
| preset=strawman | text_only | gboost | refusal | 0.660 [0.618, 0.696] | 0.796 [0.734, 0.849] | 0.042 | 0.602 | 768 |
| preset=strawman | text_only | gboost | content | 0.656 [0.618, 0.692] | 0.772 [0.719, 0.819] | 0.102 | 0.598 | 768 |
| preset=strawman | text_only | gboost | combined | 0.677 [0.639, 0.712] | 0.830 [0.771, 0.882] | 0.062 | 0.622 | 768 |
| preset=strawman | with_sources | threshold | rules | 0.546 [0.514, 0.576] | 0.553 [0.476, 0.628] | 0.000 | 0.505 | 768 |
| preset=strawman | with_sources | gboost | score | 0.877 [0.854, 0.898] | 0.970 [0.948, 0.986] | 0.383 | 0.777 | 768 |
| preset=strawman | with_sources | gboost | latency | 0.659 [0.621, 0.695] | 0.801 [0.734, 0.854] | 0.000 | 0.604 | 768 |
| preset=strawman | with_sources | gboost | refusal | 0.660 [0.618, 0.696] | 0.796 [0.734, 0.849] | 0.042 | 0.602 | 768 |
| preset=strawman | with_sources | gboost | content | 0.656 [0.618, 0.692] | 0.772 [0.719, 0.819] | 0.102 | 0.598 | 768 |
| preset=strawman | with_sources | gboost | combined | 0.890 [0.868, 0.910] | 0.974 [0.950, 0.990] | 0.297 | 0.805 | 768 |
| preset=strawman | with_reranker | threshold | rules | 0.546 [0.514, 0.576] | 0.553 [0.476, 0.628] | 0.000 | 0.505 | 768 |
| preset=strawman | with_reranker | gboost | score | 0.877 [0.854, 0.898] | 0.970 [0.948, 0.986] | 0.383 | 0.777 | 768 |
| preset=strawman | with_reranker | gboost | latency | 0.659 [0.621, 0.695] | 0.801 [0.734, 0.854] | 0.000 | 0.604 | 768 |
| preset=strawman | with_reranker | gboost | refusal | 0.660 [0.618, 0.696] | 0.796 [0.734, 0.849] | 0.042 | 0.602 | 768 |
| preset=strawman | with_reranker | gboost | content | 0.656 [0.618, 0.692] | 0.772 [0.719, 0.819] | 0.102 | 0.598 | 768 |
| preset=strawman | with_reranker | gboost | combined | 0.973 [0.959, 0.984] | 1.000 [1.000, 1.000] | 0.435 | 0.957 | 768 |
| preset=baseline | text_only | threshold | rules | 0.545 [0.530, 0.561] | 0.632 [0.583, 0.682] | 0.000 | 0.546 | 768 |
| preset=baseline | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=baseline | text_only | gboost | latency | 0.596 [0.555, 0.638] | 0.681 [0.609, 0.754] | 0.047 | 0.566 | 768 |
| preset=baseline | text_only | gboost | refusal | 0.577 [0.540, 0.613] | 0.634 [0.581, 0.686] | 0.086 | 0.547 | 768 |
| preset=baseline | text_only | gboost | content | 0.575 [0.536, 0.614] | 0.624 [0.569, 0.676] | 0.078 | 0.549 | 768 |
| preset=baseline | text_only | gboost | combined | 0.607 [0.565, 0.648] | 0.695 [0.623, 0.764] | 0.099 | 0.582 | 768 |
| preset=baseline | with_sources | threshold | rules | 0.541 [0.510, 0.574] | 0.577 [0.495, 0.651] | 0.000 | 0.533 | 768 |
| preset=baseline | with_sources | gboost | score | 0.574 [0.535, 0.611] | 0.633 [0.560, 0.707] | 0.083 | 0.547 | 768 |
| preset=baseline | with_sources | gboost | latency | 0.596 [0.555, 0.638] | 0.681 [0.609, 0.754] | 0.047 | 0.566 | 768 |
| preset=baseline | with_sources | gboost | refusal | 0.577 [0.540, 0.613] | 0.634 [0.581, 0.686] | 0.086 | 0.547 | 768 |
| preset=baseline | with_sources | gboost | content | 0.575 [0.536, 0.614] | 0.624 [0.569, 0.676] | 0.078 | 0.549 | 768 |
| preset=baseline | with_sources | gboost | combined | 0.610 [0.569, 0.650] | 0.703 [0.633, 0.771] | 0.099 | 0.586 | 768 |
| preset=baseline | with_reranker | threshold | rules | 0.541 [0.510, 0.574] | 0.577 [0.495, 0.651] | 0.000 | 0.533 | 768 |
| preset=baseline | with_reranker | gboost | score | 0.574 [0.535, 0.611] | 0.633 [0.560, 0.707] | 0.083 | 0.547 | 768 |
| preset=baseline | with_reranker | gboost | latency | 0.596 [0.555, 0.638] | 0.681 [0.609, 0.754] | 0.047 | 0.566 | 768 |
| preset=baseline | with_reranker | gboost | refusal | 0.577 [0.540, 0.613] | 0.634 [0.581, 0.686] | 0.086 | 0.547 | 768 |
| preset=baseline | with_reranker | gboost | content | 0.575 [0.536, 0.614] | 0.624 [0.569, 0.676] | 0.078 | 0.549 | 768 |
| preset=baseline | with_reranker | gboost | combined | 0.605 [0.563, 0.645] | 0.706 [0.636, 0.778] | 0.096 | 0.583 | 768 |
| preset=full | text_only | threshold | rules | 0.500 [0.495, 0.505] | 0.500 [0.479, 0.519] | 0.005 | 0.500 | 768 |
| preset=full | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | text_only | gboost | latency | 0.507 [0.468, 0.546] | 0.511 [0.432, 0.589] | 0.000 | 0.507 | 768 |
| preset=full | text_only | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | text_only | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | text_only | gboost | combined | 0.511 [0.473, 0.549] | 0.514 [0.432, 0.595] | 0.003 | 0.508 | 768 |
| preset=full | with_sources | threshold | rules | 0.500 [0.469, 0.533] | 0.500 [0.420, 0.576] | 0.005 | 0.500 | 768 |
| preset=full | with_sources | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_sources | gboost | latency | 0.507 [0.468, 0.546] | 0.511 [0.432, 0.589] | 0.000 | 0.507 | 768 |
| preset=full | with_sources | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_sources | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_sources | gboost | combined | 0.514 [0.477, 0.553] | 0.517 [0.437, 0.596] | 0.005 | 0.508 | 768 |
| preset=full | with_reranker | threshold | rules | 0.500 [0.469, 0.533] | 0.500 [0.420, 0.576] | 0.005 | 0.500 | 768 |
| preset=full | with_reranker | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_reranker | gboost | latency | 0.507 [0.468, 0.546] | 0.511 [0.432, 0.589] | 0.000 | 0.507 | 768 |
| preset=full | with_reranker | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_reranker | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_reranker | gboost | combined | 0.513 [0.474, 0.552] | 0.519 [0.440, 0.601] | 0.005 | 0.507 | 768 |

Latency padding buckets (share of probes per bucket, by world):

| cell | bucket_ms | AUC_bucket_only | world1_bucket1 | world1_bucket2 | world1_bucket3+ | world0_bucket1 | world0_bucket2 | world0_bucket3+ |
|---|---|---|---|---|---|---|---|---|
| preset=full | 500.0 | 0.508 | 0.082 | 0.570 | 0.348 | 0.087 | 0.579 | 0.333 |

Full table: existence_eia.csv (per-probe gboost scores: probe_scores.csv). Figures (gboost, with_reranker, all attackers): rq3_roc.png
