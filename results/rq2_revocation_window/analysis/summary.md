# rq2_revocation_window

seeds: [0, 1, 2, 3, 4]

## Revocation window

| cell | events | LM | LM_cache | LM_index | LM_memory | leak_rate | LM_all_lost | lost_docs_leaked_mean | LH_median_s | LH_median_leaking_s | censored | LH_index_median_leaking_s | analytic_index_staleness_mean_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sync=periodic:3600,cache_ttl_s=600 | 200 | 0.617 [0.569, 0.663] | 0.617 [0.569, 0.663] | 0.565 [0.513, 0.615] | 0.312 [0.257, 0.366] | 0.790 | n/a | n/a | 3600 [1800, 3600] | inf [3600, inf] | 80/200 | 1800 [1800, 1800] | 1800 |
| sync=periodic:3600,cache_ttl_s=3600 | 200 | 0.617 [0.569, 0.663] | 0.617 [0.569, 0.663] | 0.498 [0.446, 0.550] | 0.312 [0.257, 0.366] | 0.790 | n/a | n/a | 7200 [7200, 7200] | inf [7200, inf] | 80/200 | masked by cache | 1800 |
| sync=periodic:3600,cache_ttl_s=86400 | 200 | 0.617 [0.569, 0.663] | 0.617 [0.569, 0.663] | 0.498 [0.446, 0.550] | 0.312 [0.257, 0.366] | 0.790 | n/a | n/a | 129600 [129600, 129600] | inf [129600, inf] | 80/200 | masked by cache | 1800 |
| sync=periodic:86400,cache_ttl_s=600 | 200 | 0.652 [0.608, 0.693] | 0.652 [0.608, 0.693] | 0.648 [0.603, 0.691] | 0.328 [0.274, 0.385] | 0.835 | n/a | n/a | 86400 [64800, 86400] | inf [86400, inf] | 84/200 | 43200 [43200, 64800] | 43200 |
| sync=periodic:86400,cache_ttl_s=3600 | 200 | 0.652 [0.608, 0.693] | 0.652 [0.608, 0.693] | 0.644 [0.599, 0.687] | 0.328 [0.274, 0.385] | 0.835 | n/a | n/a | 86400 [64800, 86400] | inf [86400, inf] | 84/200 | 43200 [43200, 64800] | 43200 |
| sync=periodic:86400,cache_ttl_s=86400 | 200 | 0.652 [0.608, 0.693] | 0.652 [0.608, 0.693] | 0.556 [0.506, 0.604] | 0.328 [0.274, 0.385] | 0.835 | n/a | n/a | 129600 [129600, 129600] | inf [129600, inf] | 84/200 | masked by cache | 43200 |
| sync=event:0.0,cache_ttl_s=600 | 200 | 0.506 [0.453, 0.559] | 0.504 [0.451, 0.557] | 0.000 [0.000, 0.000] | 0.333 [0.281, 0.385] | 0.650 | n/a | n/a | 900 [300, 900] | inf [inf, inf] | 86/200 | n/a |  |
| sync=event:0.0,cache_ttl_s=3600 | 200 | 0.506 [0.453, 0.559] | 0.504 [0.451, 0.557] | 0.000 [0.000, 0.000] | 0.333 [0.281, 0.385] | 0.650 | n/a | n/a | 3600 [3600, 3600] | inf [inf, inf] | 86/200 | n/a |  |
| sync=event:0.0,cache_ttl_s=86400 | 200 | 0.506 [0.453, 0.559] | 0.504 [0.451, 0.557] | 0.000 [0.000, 0.000] | 0.333 [0.281, 0.385] | 0.650 | n/a | n/a | 86400 [86400, 86400] | inf [inf, inf] | 86/200 | n/a |  |
| sync=event:0.05:86400,cache_ttl_s=600 | 200 | 0.522 [0.468, 0.573] | 0.520 [0.466, 0.571] | 0.034 [0.014, 0.058] | 0.334 [0.280, 0.385] | 0.670 | n/a | n/a | 900 [900, 86400] | inf [inf, inf] | 86/200 | 64800 [43200, 86400] |  |
| sync=event:0.05:86400,cache_ttl_s=3600 | 200 | 0.522 [0.468, 0.573] | 0.520 [0.466, 0.571] | 0.034 [0.014, 0.058] | 0.334 [0.280, 0.385] | 0.670 | n/a | n/a | 3600 [3600, 86400] | inf [inf, inf] | 86/200 | 64800 [43200, 86400] |  |
| sync=event:0.05:86400,cache_ttl_s=86400 | 200 | 0.522 [0.468, 0.573] | 0.520 [0.466, 0.571] | 0.034 [0.014, 0.058] | 0.334 [0.280, 0.385] | 0.670 | n/a | n/a | 86400 [86400, 129600] | inf [inf, inf] | 86/200 | masked by cache |  |

Paired difference in event LM (same seeds and events):

| cell | vs | delta_LM | CI_cluster | p | p_wilcoxon | pairs |
|---|---|---|---|---|---|---|
| sync=periodic:3600,cache_ttl_s=3600 | sync=periodic:3600,cache_ttl_s=600 | 0.000 [0.000, 0.000] | [0.000, 0.000] | 1.0000 | 1.0000 | 200 |
| sync=periodic:3600,cache_ttl_s=86400 | sync=periodic:3600,cache_ttl_s=600 | 0.000 [0.000, 0.000] | [0.000, 0.000] | 1.0000 | 1.0000 | 200 |
| sync=periodic:86400,cache_ttl_s=600 | sync=periodic:3600,cache_ttl_s=600 | 0.036 [0.016, 0.060] | [0.008, 0.073] | <0.0005 | 0.0030 | 200 |
| sync=periodic:86400,cache_ttl_s=3600 | sync=periodic:3600,cache_ttl_s=600 | 0.036 [0.016, 0.060] | [0.008, 0.073] | <0.0005 | 0.0030 | 200 |
| sync=periodic:86400,cache_ttl_s=86400 | sync=periodic:3600,cache_ttl_s=600 | 0.036 [0.016, 0.060] | [0.008, 0.073] | <0.0005 | 0.0030 | 200 |
| sync=event:0.0,cache_ttl_s=600 | sync=periodic:3600,cache_ttl_s=600 | -0.111 [-0.145, -0.076] | [-0.162, -0.065] | <0.0005 | 6.4e-08 | 200 |
| sync=event:0.0,cache_ttl_s=3600 | sync=periodic:3600,cache_ttl_s=600 | -0.111 [-0.145, -0.076] | [-0.162, -0.065] | <0.0005 | 6.4e-08 | 200 |
| sync=event:0.0,cache_ttl_s=86400 | sync=periodic:3600,cache_ttl_s=600 | -0.111 [-0.145, -0.076] | [-0.162, -0.065] | <0.0005 | 6.4e-08 | 200 |
| sync=event:0.05:86400,cache_ttl_s=600 | sync=periodic:3600,cache_ttl_s=600 | -0.095 [-0.128, -0.062] | [-0.147, -0.049] | <0.0005 | 6.7e-07 | 200 |
| sync=event:0.05:86400,cache_ttl_s=3600 | sync=periodic:3600,cache_ttl_s=600 | -0.095 [-0.128, -0.062] | [-0.147, -0.049] | <0.0005 | 6.7e-07 | 200 |
| sync=event:0.05:86400,cache_ttl_s=86400 | sync=periodic:3600,cache_ttl_s=600 | -0.095 [-0.128, -0.062] | [-0.147, -0.049] | <0.0005 | 6.7e-07 | 200 |

CI: event-level bootstrap; CI_cluster: two-stage bootstrap over seeds, then events. p: bootstrap (resolution 1/2000); p_wilcoxon: Wilcoxon signed-rank, zero differences dropped.

Figures: rq2_survival.png, rq1_surfaces.png
