# rq3_existence_8b

seeds: [0, 1, 2]

## Existence inference (twin worlds, held-out tenants)

| cell | profile | model | channel | AUC | AUC_trial | TPR@1%FPR | balanced_acc | n_test |
|---|---|---|---|---|---|---|---|---|
| preset=strawman | text_only | threshold | rules | 0.620 [0.582, 0.653] | 0.685 [0.608, 0.759] | 0.169 | 0.591 | 768 |
| preset=strawman | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=strawman | text_only | gboost | latency | 0.662 [0.622, 0.699] | 0.779 [0.714, 0.840] | 0.000 | 0.611 | 768 |
| preset=strawman | text_only | gboost | refusal | 0.729 [0.691, 0.762] | 0.805 [0.744, 0.863] | 0.260 | 0.665 | 768 |
| preset=strawman | text_only | gboost | content | 0.684 [0.647, 0.720] | 0.776 [0.710, 0.838] | 0.177 | 0.646 | 768 |
| preset=strawman | text_only | gboost | combined | 0.729 [0.695, 0.760] | 0.846 [0.790, 0.895] | 0.271 | 0.660 | 768 |
| preset=strawman | with_sources | threshold | rules | 0.644 [0.608, 0.678] | 0.769 [0.699, 0.834] | 0.169 | 0.520 | 768 |
| preset=strawman | with_sources | gboost | score | 0.869 [0.844, 0.892] | 0.951 [0.917, 0.975] | 0.323 | 0.768 | 768 |
| preset=strawman | with_sources | gboost | latency | 0.662 [0.622, 0.699] | 0.779 [0.714, 0.840] | 0.000 | 0.611 | 768 |
| preset=strawman | with_sources | gboost | refusal | 0.729 [0.691, 0.762] | 0.805 [0.744, 0.863] | 0.260 | 0.665 | 768 |
| preset=strawman | with_sources | gboost | content | 0.684 [0.647, 0.720] | 0.776 [0.710, 0.838] | 0.177 | 0.646 | 768 |
| preset=strawman | with_sources | gboost | combined | 0.908 [0.886, 0.928] | 0.983 [0.969, 0.994] | 0.523 | 0.829 | 768 |
| preset=strawman | with_reranker | threshold | rules | 0.644 [0.608, 0.678] | 0.769 [0.699, 0.834] | 0.169 | 0.520 | 768 |
| preset=strawman | with_reranker | gboost | score | 0.869 [0.844, 0.892] | 0.951 [0.917, 0.975] | 0.323 | 0.768 | 768 |
| preset=strawman | with_reranker | gboost | latency | 0.662 [0.622, 0.699] | 0.779 [0.714, 0.840] | 0.000 | 0.611 | 768 |
| preset=strawman | with_reranker | gboost | refusal | 0.729 [0.691, 0.762] | 0.805 [0.744, 0.863] | 0.260 | 0.665 | 768 |
| preset=strawman | with_reranker | gboost | content | 0.684 [0.647, 0.720] | 0.776 [0.710, 0.838] | 0.177 | 0.646 | 768 |
| preset=strawman | with_reranker | gboost | combined | 0.974 [0.961, 0.984] | 1.000 [1.000, 1.000] | 0.799 | 0.956 | 768 |
| preset=baseline | text_only | threshold | rules | 0.536 [0.519, 0.552] | 0.636 [0.579, 0.688] | 0.047 | 0.535 | 768 |
| preset=baseline | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=baseline | text_only | gboost | latency | 0.580 [0.541, 0.620] | 0.688 [0.608, 0.760] | 0.062 | 0.561 | 768 |
| preset=baseline | text_only | gboost | refusal | 0.580 [0.540, 0.617] | 0.667 [0.609, 0.720] | 0.094 | 0.549 | 768 |
| preset=baseline | text_only | gboost | content | 0.560 [0.520, 0.597] | 0.620 [0.559, 0.680] | 0.065 | 0.536 | 768 |
| preset=baseline | text_only | gboost | combined | 0.592 [0.554, 0.632] | 0.711 [0.635, 0.780] | 0.099 | 0.547 | 768 |
| preset=baseline | with_sources | threshold | rules | 0.531 [0.497, 0.565] | 0.571 [0.488, 0.645] | 0.052 | 0.523 | 768 |
| preset=baseline | with_sources | gboost | score | 0.553 [0.515, 0.594] | 0.613 [0.535, 0.692] | 0.065 | 0.530 | 768 |
| preset=baseline | with_sources | gboost | latency | 0.580 [0.541, 0.620] | 0.688 [0.608, 0.760] | 0.062 | 0.561 | 768 |
| preset=baseline | with_sources | gboost | refusal | 0.580 [0.540, 0.617] | 0.667 [0.609, 0.720] | 0.094 | 0.549 | 768 |
| preset=baseline | with_sources | gboost | content | 0.560 [0.520, 0.597] | 0.620 [0.559, 0.680] | 0.065 | 0.536 | 768 |
| preset=baseline | with_sources | gboost | combined | 0.607 [0.566, 0.644] | 0.731 [0.660, 0.799] | 0.081 | 0.570 | 768 |
| preset=baseline | with_reranker | threshold | rules | 0.531 [0.497, 0.565] | 0.571 [0.488, 0.645] | 0.052 | 0.523 | 768 |
| preset=baseline | with_reranker | gboost | score | 0.553 [0.515, 0.594] | 0.613 [0.535, 0.692] | 0.065 | 0.530 | 768 |
| preset=baseline | with_reranker | gboost | latency | 0.580 [0.541, 0.620] | 0.688 [0.608, 0.760] | 0.062 | 0.561 | 768 |
| preset=baseline | with_reranker | gboost | refusal | 0.580 [0.540, 0.617] | 0.667 [0.609, 0.720] | 0.094 | 0.549 | 768 |
| preset=baseline | with_reranker | gboost | content | 0.560 [0.520, 0.597] | 0.620 [0.559, 0.680] | 0.065 | 0.536 | 768 |
| preset=baseline | with_reranker | gboost | combined | 0.608 [0.568, 0.647] | 0.731 [0.662, 0.798] | 0.081 | 0.562 | 768 |
| preset=full | text_only | threshold | rules | 0.500 [0.488, 0.512] | 0.500 [0.463, 0.538] | 0.000 | 0.500 | 768 |
| preset=full | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | text_only | gboost | latency | 0.530 [0.484, 0.566] | 0.560 [0.487, 0.637] | 0.000 | 0.525 | 768 |
| preset=full | text_only | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | text_only | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | text_only | gboost | combined | 0.537 [0.494, 0.577] | 0.572 [0.490, 0.649] | 0.016 | 0.526 | 768 |
| preset=full | with_sources | threshold | rules | 0.500 [0.469, 0.531] | 0.500 [0.421, 0.577] | 0.000 | 0.500 | 768 |
| preset=full | with_sources | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_sources | gboost | latency | 0.530 [0.484, 0.566] | 0.560 [0.487, 0.637] | 0.000 | 0.525 | 768 |
| preset=full | with_sources | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_sources | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_sources | gboost | combined | 0.540 [0.500, 0.582] | 0.588 [0.506, 0.664] | 0.018 | 0.527 | 768 |
| preset=full | with_reranker | threshold | rules | 0.500 [0.469, 0.531] | 0.500 [0.421, 0.577] | 0.000 | 0.500 | 768 |
| preset=full | with_reranker | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_reranker | gboost | latency | 0.530 [0.484, 0.566] | 0.560 [0.487, 0.637] | 0.000 | 0.525 | 768 |
| preset=full | with_reranker | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_reranker | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 768 |
| preset=full | with_reranker | gboost | combined | 0.540 [0.498, 0.581] | 0.587 [0.505, 0.665] | 0.010 | 0.526 | 768 |

Latency padding buckets (share of probes per bucket, by world):

| cell | bucket_ms | AUC_bucket_only | world1_bucket1 | world1_bucket2 | world1_bucket3+ | world0_bucket1 | world0_bucket2 | world0_bucket3+ |
|---|---|---|---|---|---|---|---|---|
| preset=full | 500.0 | 0.519 | 0.029 | 0.004 | 0.967 | 0.031 | 0.005 | 0.964 |

Full table: existence_eia.csv (per-probe gboost scores: probe_scores.csv). Figures (gboost, with_reranker, all attackers): rq3_roc.png
