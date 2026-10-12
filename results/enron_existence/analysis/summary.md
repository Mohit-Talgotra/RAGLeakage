# enron_existence

seeds: [0]

## Existence inference (twin worlds, held-out tenants)

| cell | profile | model | channel | AUC | AUC_trial | TPR@1%FPR | balanced_acc | n_test |
|---|---|---|---|---|---|---|---|---|
| preset=strawman | text_only | threshold | rules | 0.615 [0.575, 0.655] | 0.642 [0.557, 0.719] | 0.000 | 0.541 | 640 |
| preset=strawman | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=strawman | text_only | gboost | latency | 0.515 [0.474, 0.561] | 0.521 [0.430, 0.611] | 0.000 | 0.503 | 640 |
| preset=strawman | text_only | gboost | refusal | 0.458 [0.412, 0.502] | 0.443 [0.346, 0.530] | 0.006 | 0.486 | 640 |
| preset=strawman | text_only | gboost | content | 0.584 [0.539, 0.627] | 0.605 [0.518, 0.689] | 0.044 | 0.569 | 640 |
| preset=strawman | text_only | gboost | combined | 0.552 [0.506, 0.592] | 0.572 [0.482, 0.659] | 0.013 | 0.539 | 640 |
| preset=strawman | with_sources | threshold | rules | 0.622 [0.583, 0.662] | 0.675 [0.597, 0.754] | 0.000 | 0.500 | 640 |
| preset=strawman | with_sources | gboost | score | 0.747 [0.709, 0.783] | 0.843 [0.776, 0.898] | 0.134 | 0.694 | 640 |
| preset=strawman | with_sources | gboost | latency | 0.515 [0.474, 0.561] | 0.521 [0.430, 0.611] | 0.000 | 0.503 | 640 |
| preset=strawman | with_sources | gboost | refusal | 0.458 [0.412, 0.502] | 0.443 [0.346, 0.530] | 0.006 | 0.486 | 640 |
| preset=strawman | with_sources | gboost | content | 0.584 [0.539, 0.627] | 0.605 [0.518, 0.689] | 0.044 | 0.569 | 640 |
| preset=strawman | with_sources | gboost | combined | 0.746 [0.707, 0.781] | 0.826 [0.758, 0.881] | 0.097 | 0.689 | 640 |
| preset=strawman | with_reranker | threshold | rules | 0.622 [0.583, 0.662] | 0.675 [0.597, 0.754] | 0.000 | 0.500 | 640 |
| preset=strawman | with_reranker | gboost | score | 0.747 [0.709, 0.783] | 0.843 [0.776, 0.898] | 0.134 | 0.694 | 640 |
| preset=strawman | with_reranker | gboost | latency | 0.515 [0.474, 0.561] | 0.521 [0.430, 0.611] | 0.000 | 0.503 | 640 |
| preset=strawman | with_reranker | gboost | refusal | 0.458 [0.412, 0.502] | 0.443 [0.346, 0.530] | 0.006 | 0.486 | 640 |
| preset=strawman | with_reranker | gboost | content | 0.584 [0.539, 0.627] | 0.605 [0.518, 0.689] | 0.044 | 0.569 | 640 |
| preset=strawman | with_reranker | gboost | combined | 0.812 [0.779, 0.844] | 0.896 [0.838, 0.943] | 0.072 | 0.739 | 640 |
| preset=baseline | text_only | threshold | rules | 0.545 [0.509, 0.585] | 0.544 [0.461, 0.628] | 0.000 | 0.533 | 640 |
| preset=baseline | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=baseline | text_only | gboost | latency | 0.502 [0.454, 0.549] | 0.496 [0.410, 0.582] | 0.006 | 0.514 | 640 |
| preset=baseline | text_only | gboost | refusal | 0.502 [0.459, 0.549] | 0.494 [0.406, 0.583] | 0.003 | 0.508 | 640 |
| preset=baseline | text_only | gboost | content | 0.563 [0.521, 0.607] | 0.572 [0.489, 0.662] | 0.062 | 0.539 | 640 |
| preset=baseline | text_only | gboost | combined | 0.596 [0.550, 0.639] | 0.645 [0.565, 0.730] | 0.041 | 0.569 | 640 |
| preset=baseline | with_sources | threshold | rules | 0.556 [0.515, 0.600] | 0.560 [0.470, 0.650] | 0.000 | 0.511 | 640 |
| preset=baseline | with_sources | gboost | score | 0.531 [0.485, 0.578] | 0.548 [0.461, 0.642] | 0.013 | 0.530 | 640 |
| preset=baseline | with_sources | gboost | latency | 0.502 [0.454, 0.549] | 0.496 [0.410, 0.582] | 0.006 | 0.514 | 640 |
| preset=baseline | with_sources | gboost | refusal | 0.502 [0.459, 0.549] | 0.494 [0.406, 0.583] | 0.003 | 0.508 | 640 |
| preset=baseline | with_sources | gboost | content | 0.563 [0.521, 0.607] | 0.572 [0.489, 0.662] | 0.062 | 0.539 | 640 |
| preset=baseline | with_sources | gboost | combined | 0.573 [0.529, 0.617] | 0.619 [0.539, 0.703] | 0.062 | 0.548 | 640 |
| preset=baseline | with_reranker | threshold | rules | 0.556 [0.515, 0.600] | 0.560 [0.470, 0.650] | 0.000 | 0.511 | 640 |
| preset=baseline | with_reranker | gboost | score | 0.531 [0.485, 0.578] | 0.548 [0.461, 0.642] | 0.013 | 0.530 | 640 |
| preset=baseline | with_reranker | gboost | latency | 0.502 [0.454, 0.549] | 0.496 [0.410, 0.582] | 0.006 | 0.514 | 640 |
| preset=baseline | with_reranker | gboost | refusal | 0.502 [0.459, 0.549] | 0.494 [0.406, 0.583] | 0.003 | 0.508 | 640 |
| preset=baseline | with_reranker | gboost | content | 0.563 [0.521, 0.607] | 0.572 [0.489, 0.662] | 0.062 | 0.539 | 640 |
| preset=baseline | with_reranker | gboost | combined | 0.586 [0.541, 0.627] | 0.637 [0.555, 0.718] | 0.066 | 0.562 | 640 |
| preset=full | text_only | threshold | rules | 0.500 [0.471, 0.534] | 0.500 [0.415, 0.581] | 0.000 | 0.500 | 640 |
| preset=full | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=full | text_only | gboost | latency | 0.480 [0.437, 0.527] | 0.425 [0.337, 0.512] | 0.013 | 0.478 | 640 |
| preset=full | text_only | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=full | text_only | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=full | text_only | gboost | combined | 0.468 [0.422, 0.515] | 0.421 [0.338, 0.504] | 0.006 | 0.466 | 640 |
| preset=full | with_sources | threshold | rules | 0.500 [0.459, 0.544] | 0.500 [0.412, 0.587] | 0.000 | 0.500 | 640 |
| preset=full | with_sources | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=full | with_sources | gboost | latency | 0.480 [0.437, 0.527] | 0.425 [0.337, 0.512] | 0.013 | 0.478 | 640 |
| preset=full | with_sources | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=full | with_sources | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=full | with_sources | gboost | combined | 0.472 [0.423, 0.520] | 0.431 [0.342, 0.518] | 0.009 | 0.473 | 640 |
| preset=full | with_reranker | threshold | rules | 0.500 [0.459, 0.544] | 0.500 [0.412, 0.587] | 0.000 | 0.500 | 640 |
| preset=full | with_reranker | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=full | with_reranker | gboost | latency | 0.480 [0.437, 0.527] | 0.425 [0.337, 0.512] | 0.013 | 0.478 | 640 |
| preset=full | with_reranker | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=full | with_reranker | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 640 |
| preset=full | with_reranker | gboost | combined | 0.468 [0.422, 0.516] | 0.438 [0.352, 0.525] | 0.006 | 0.467 | 640 |

Latency padding buckets (share of probes per bucket, by world):

| cell | bucket_ms | AUC_bucket_only | world1_bucket1 | world1_bucket2 | world1_bucket3+ | world0_bucket1 | world0_bucket2 | world0_bucket3+ |
|---|---|---|---|---|---|---|---|---|
| preset=full | 500.0 | 0.498 | 0.050 | 0.255 | 0.695 | 0.050 | 0.250 | 0.700 |

Full table: existence_eia.csv (per-probe gboost scores: probe_scores.csv). Figures (gboost, with_reranker, all attackers): rq3_roc.png
