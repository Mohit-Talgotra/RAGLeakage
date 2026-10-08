# rq3_existence

seeds: [0, 1, 2, 3, 4]

## Existence inference (twin worlds, held-out tenants)

| cell | profile | model | channel | AUC | AUC_trial | TPR@1%FPR | balanced_acc | n_test |
|---|---|---|---|---|---|---|---|---|
| preset=strawman | text_only | threshold | rules | 0.598 [0.584, 0.611] | 0.627 [0.595, 0.657] | 0.000 | 0.533 | 4800 |
| preset=strawman | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=strawman | text_only | gboost | latency | 0.555 [0.540, 0.572] | 0.548 [0.516, 0.580] | 0.015 | 0.553 | 4800 |
| preset=strawman | text_only | gboost | refusal | 0.576 [0.560, 0.592] | 0.573 [0.543, 0.602] | 0.058 | 0.564 | 4800 |
| preset=strawman | text_only | gboost | content | 0.706 [0.692, 0.719] | 0.713 [0.692, 0.734] | 0.310 | 0.650 | 4800 |
| preset=strawman | text_only | gboost | combined | 0.698 [0.684, 0.713] | 0.706 [0.678, 0.734] | 0.310 | 0.639 | 4800 |
| preset=strawman | with_sources | threshold | rules | 0.599 [0.585, 0.612] | 0.624 [0.593, 0.653] | 0.000 | 0.504 | 4800 |
| preset=strawman | with_sources | gboost | score | 0.883 [0.873, 0.892] | 0.942 [0.929, 0.953] | 0.392 | 0.802 | 4800 |
| preset=strawman | with_sources | gboost | latency | 0.555 [0.540, 0.572] | 0.548 [0.516, 0.580] | 0.015 | 0.553 | 4800 |
| preset=strawman | with_sources | gboost | refusal | 0.576 [0.560, 0.592] | 0.573 [0.543, 0.602] | 0.058 | 0.564 | 4800 |
| preset=strawman | with_sources | gboost | content | 0.706 [0.692, 0.719] | 0.713 [0.692, 0.734] | 0.310 | 0.650 | 4800 |
| preset=strawman | with_sources | gboost | combined | 0.924 [0.917, 0.931] | 0.972 [0.964, 0.979] | 0.512 | 0.851 | 4800 |
| preset=strawman | with_reranker | threshold | rules | 0.599 [0.585, 0.612] | 0.624 [0.593, 0.653] | 0.000 | 0.504 | 4800 |
| preset=strawman | with_reranker | gboost | score | 0.883 [0.873, 0.892] | 0.942 [0.929, 0.953] | 0.392 | 0.802 | 4800 |
| preset=strawman | with_reranker | gboost | latency | 0.555 [0.540, 0.572] | 0.548 [0.516, 0.580] | 0.015 | 0.553 | 4800 |
| preset=strawman | with_reranker | gboost | refusal | 0.576 [0.560, 0.592] | 0.573 [0.543, 0.602] | 0.058 | 0.564 | 4800 |
| preset=strawman | with_reranker | gboost | content | 0.706 [0.692, 0.719] | 0.713 [0.692, 0.734] | 0.310 | 0.650 | 4800 |
| preset=strawman | with_reranker | gboost | combined | 0.983 [0.980, 0.987] | 1.000 [1.000, 1.000] | 0.689 | 0.948 | 4800 |
| preset=baseline | text_only | threshold | rules | 0.536 [0.526, 0.547] | 0.532 [0.510, 0.554] | 0.000 | 0.536 | 4800 |
| preset=baseline | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=baseline | text_only | gboost | latency | 0.513 [0.495, 0.529] | 0.517 [0.483, 0.549] | 0.008 | 0.512 | 4800 |
| preset=baseline | text_only | gboost | refusal | 0.525 [0.509, 0.540] | 0.516 [0.487, 0.545] | 0.030 | 0.521 | 4800 |
| preset=baseline | text_only | gboost | content | 0.615 [0.598, 0.631] | 0.621 [0.594, 0.648] | 0.157 | 0.573 | 4800 |
| preset=baseline | text_only | gboost | combined | 0.611 [0.594, 0.625] | 0.608 [0.578, 0.638] | 0.154 | 0.568 | 4800 |
| preset=baseline | with_sources | threshold | rules | 0.533 [0.521, 0.548] | 0.528 [0.498, 0.557] | 0.000 | 0.525 | 4800 |
| preset=baseline | with_sources | gboost | score | 0.530 [0.514, 0.546] | 0.532 [0.496, 0.562] | 0.029 | 0.524 | 4800 |
| preset=baseline | with_sources | gboost | latency | 0.513 [0.495, 0.529] | 0.517 [0.483, 0.549] | 0.008 | 0.512 | 4800 |
| preset=baseline | with_sources | gboost | refusal | 0.525 [0.509, 0.540] | 0.516 [0.487, 0.545] | 0.030 | 0.521 | 4800 |
| preset=baseline | with_sources | gboost | content | 0.615 [0.598, 0.631] | 0.621 [0.594, 0.648] | 0.157 | 0.573 | 4800 |
| preset=baseline | with_sources | gboost | combined | 0.612 [0.596, 0.626] | 0.617 [0.586, 0.648] | 0.158 | 0.574 | 4800 |
| preset=baseline | with_reranker | threshold | rules | 0.533 [0.521, 0.548] | 0.528 [0.498, 0.557] | 0.000 | 0.525 | 4800 |
| preset=baseline | with_reranker | gboost | score | 0.530 [0.514, 0.546] | 0.532 [0.496, 0.562] | 0.029 | 0.524 | 4800 |
| preset=baseline | with_reranker | gboost | latency | 0.513 [0.495, 0.529] | 0.517 [0.483, 0.549] | 0.008 | 0.512 | 4800 |
| preset=baseline | with_reranker | gboost | refusal | 0.525 [0.509, 0.540] | 0.516 [0.487, 0.545] | 0.030 | 0.521 | 4800 |
| preset=baseline | with_reranker | gboost | content | 0.615 [0.598, 0.631] | 0.621 [0.594, 0.648] | 0.157 | 0.573 | 4800 |
| preset=baseline | with_reranker | gboost | combined | 0.612 [0.596, 0.627] | 0.628 [0.598, 0.659] | 0.157 | 0.572 | 4800 |
| preset=legacy | text_only | threshold | rules | 0.536 [0.522, 0.549] | 0.536 [0.505, 0.564] | 0.000 | 0.529 | 4800 |
| preset=legacy | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=legacy | text_only | gboost | latency | 0.505 [0.489, 0.519] | 0.490 [0.455, 0.523] | 0.007 | 0.508 | 4800 |
| preset=legacy | text_only | gboost | refusal | 0.523 [0.507, 0.537] | 0.516 [0.487, 0.544] | 0.028 | 0.520 | 4800 |
| preset=legacy | text_only | gboost | content | 0.602 [0.588, 0.616] | 0.621 [0.594, 0.647] | 0.138 | 0.564 | 4800 |
| preset=legacy | text_only | gboost | combined | 0.592 [0.576, 0.608] | 0.608 [0.577, 0.640] | 0.139 | 0.552 | 4800 |
| preset=legacy | with_sources | threshold | rules | 0.531 [0.517, 0.547] | 0.530 [0.500, 0.560] | 0.000 | 0.519 | 4800 |
| preset=legacy | with_sources | gboost | score | 0.529 [0.512, 0.544] | 0.533 [0.501, 0.563] | 0.025 | 0.522 | 4800 |
| preset=legacy | with_sources | gboost | latency | 0.505 [0.489, 0.519] | 0.490 [0.455, 0.523] | 0.007 | 0.508 | 4800 |
| preset=legacy | with_sources | gboost | refusal | 0.523 [0.507, 0.537] | 0.516 [0.487, 0.544] | 0.028 | 0.520 | 4800 |
| preset=legacy | with_sources | gboost | content | 0.602 [0.588, 0.616] | 0.621 [0.594, 0.647] | 0.138 | 0.564 | 4800 |
| preset=legacy | with_sources | gboost | combined | 0.592 [0.576, 0.609] | 0.613 [0.582, 0.645] | 0.140 | 0.551 | 4800 |
| preset=legacy | with_reranker | threshold | rules | 0.531 [0.517, 0.547] | 0.530 [0.500, 0.560] | 0.000 | 0.519 | 4800 |
| preset=legacy | with_reranker | gboost | score | 0.529 [0.512, 0.544] | 0.533 [0.501, 0.563] | 0.025 | 0.522 | 4800 |
| preset=legacy | with_reranker | gboost | latency | 0.505 [0.489, 0.519] | 0.490 [0.455, 0.523] | 0.007 | 0.508 | 4800 |
| preset=legacy | with_reranker | gboost | refusal | 0.523 [0.507, 0.537] | 0.516 [0.487, 0.544] | 0.028 | 0.520 | 4800 |
| preset=legacy | with_reranker | gboost | content | 0.602 [0.588, 0.616] | 0.621 [0.594, 0.647] | 0.138 | 0.564 | 4800 |
| preset=legacy | with_reranker | gboost | combined | 0.592 [0.576, 0.608] | 0.611 [0.579, 0.644] | 0.135 | 0.549 | 4800 |
| preset=full | text_only | threshold | rules | 0.500 [0.494, 0.507] | 0.500 [0.486, 0.514] | 0.000 | 0.500 | 4800 |
| preset=full | text_only | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=full | text_only | gboost | latency | 0.499 [0.483, 0.514] | 0.496 [0.465, 0.526] | 0.010 | 0.497 | 4800 |
| preset=full | text_only | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=full | text_only | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=full | text_only | gboost | combined | 0.496 [0.485, 0.507] | 0.487 [0.455, 0.518] | 0.008 | 0.497 | 4800 |
| preset=full | with_sources | threshold | rules | 0.500 [0.487, 0.513] | 0.500 [0.471, 0.530] | 0.000 | 0.500 | 4800 |
| preset=full | with_sources | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=full | with_sources | gboost | latency | 0.499 [0.483, 0.514] | 0.496 [0.465, 0.526] | 0.010 | 0.497 | 4800 |
| preset=full | with_sources | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=full | with_sources | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=full | with_sources | gboost | combined | 0.495 [0.486, 0.505] | 0.483 [0.454, 0.512] | 0.010 | 0.497 | 4800 |
| preset=full | with_reranker | threshold | rules | 0.500 [0.487, 0.513] | 0.500 [0.471, 0.530] | 0.000 | 0.500 | 4800 |
| preset=full | with_reranker | gboost | score | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=full | with_reranker | gboost | latency | 0.499 [0.483, 0.514] | 0.496 [0.465, 0.526] | 0.010 | 0.497 | 4800 |
| preset=full | with_reranker | gboost | refusal | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=full | with_reranker | gboost | content | 0.500 [0.500, 0.500] | 0.500 [0.500, 0.500] | 0.000 | 0.500 | 4800 |
| preset=full | with_reranker | gboost | combined | 0.495 [0.481, 0.509] | 0.478 [0.449, 0.510] | 0.008 | 0.497 | 4800 |

Full table: existence_eia.csv. Figures (gboost, with_reranker, all attackers): rq3_roc.png
