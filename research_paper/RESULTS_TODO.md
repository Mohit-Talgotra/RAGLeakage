# What the paper still needs

The paper was rewritten on 22 Oct 2026 to follow `afterimage_reviewer_audit.md`. Every red
`\pending{}` in the PDF comes from one of the runs below. Build with `\pendingfalse` in `main.tex`
before submission: any leftover marker then stops the build.

## 1. GPU runs → paper slots

Run `scripts/run_paper_grid.sh` (see its header for the order). Each run writes
`results/<name>/analysis/`. The table says which column fills which slot.

| Slot | Config | Analysis file → columns |
| --- | --- | --- |
| Tab. rq1, R1 | `p1_surfaces`, `p1_surfaces_enron` | `revocation_summary.csv` → `LM`, `LM_new`, `LM_re`, `LM_from_1h`, `LH_median_leaking_s`, `canary_leak_rate`, `LM_all_lost`, `summary_retains` |
| App. stub (S) | `p1_surfaces_stub` | same columns |
| R2a, App. V | `p2_lifetimes` | `revocation_summary.csv` → `LH_index_median_leaking_s`, `analytic_index_staleness_mean_s`, `LM`, `LM_from_1h`, `LM_memory`, `censored`; group by `memory_ttl_s` and `revoke_gap_s` |
| R2b | `p2_cache` | `revocation_summary.csv` → `LM`, `leak_rate`, `LH_median_leaking_s`; `revocation_paired.csv` vs threshold 0.80 |
| Tab. rq3, R3, R3t | `p3_existence`, `p3_existence_enron` (default tenant split; never pass `--train-tenants`) | `existence_eia.csv` (gboost, with_reranker, combined; `attacker` insider/outsider) → `AUC`, `TPR@1%FPR`; per channel for "strongest channel"; `pad_buckets.csv` for R3t; `existence_strata.csv` |
| R4a | `p4_ablation_revocation` | `revocation_summary.csv` → `LM`, `LM_memory`, `LM_cache`; variant `one_hop_summary` vs `as_is` |
| R4b | `p4_ablation_existence` | `existence_eia.csv`; heat map `rq4_ablation_heatmap.pdf` |
| Tab. defenses, R4c | `p4_defenses_revocation`, `p4_defenses_revocation_enron`, `p5_long_session`, `p4_defenses_existence` | `LM`, `LM_new`, `retained_recall_same`, `retained_refusal_same`, `authz_decisions_per_query`; insider AUC from existence. Report variants `llm_summary` and `extractive_summary` separately (full_fine = full with model-written summaries) |
| R4s | `p4_shared_state` | `LM_new`, `LM_cache` (colleague's cache entries reaching the victim) |
| R4l | `p4_lossy_hooks` | `LM`, `leak_rate` per preset (flush expected > 0; epoch, full, full_user 0) |
| R4r | `p4_reclassify` | `LM`, `retained_recall_same`, `bystander_recall`, `bystander_refusal` per preset and summary variant |
| R2w | `p2_writes` | `LM`, `LH_median_leaking_s`, `censored` by `probe_readonly` and `cache_ttl_s` |
| R5 | `p5_utility` (no revocation: overhead only) | `utility_summary.csv` → `correct`, `p50_ms`, `p95_ms`, `cache_hit_rate` (full vs full_user), `authz_calls`, `authz_decisions` |
| R6 | `p7_update`, `p7_update_enron` | `revocation_summary.csv` → `LM_update` |
| R7, D3 | `p6_launder` (full, full_user, epoch) | `launder_success`, `colleague_event_rate`, `LM_colleague` |
| R8 | `p8_models`, `p8_models_hosted` | `LM`, `LM_new`, `LM_memory`, `censored` per model |
| Setup: units "n" | existence configs | `n_test` |
| Setup: power | pilot logs | compute from the variance of per-event LM differences in `results/rq5_leakage` |
| Abstract, intro summary, discussion D1–D4, conclusion | all of the above | at most five numbers in the abstract |

Write the result text whichever way it comes out. In particular, if `epoch` keeps as much
retained-document recall as `full`/`full_fine`, the paper should say the simpler mechanism wins.

Before the grid: run `p0_smoke`, then check that `probe_template` varies across seeds in a model
run's logs and that Enron rows appear in `results/p3_existence_enron/analysis/existence_eia.csv`.

## 2. Human work (no GPU)

- **Judge validation (R9, methodology, limitations).** The methodology and limitations text has two
  versions in its `\pending` slot: keep the validated one only if the labelling is done. Two annotators label the sampled responses
  in `results/judge_sample/judge_validation.csv` (`human_label`), then report precision, recall and
  Cohen's kappa for the model judge. `scripts/judge_sample.py` draws the sample.
- **Paraphrase bank.** `run_paper_grid.sh` builds it for the five per-seed corpora and Enron; rerun
  until it reports 0 missing (a missing question stops a run). Commit `data/paraphrases.json`.
- **Venue.** `main.tex` uses IEEEtran conference mode. Switch the class for an ACM or USENIX venue
  and cut to its page limit (move the robustness paragraphs to the appendix if needed).
- **Real-stack demonstration (audit H4.3).** Not done. Show one leak end-to-end in an unmodified
  open-source stack (for example LangChain summary memory + Chroma + RedisVL semantic cache). This
  is the strongest external-validity evidence still missing.
- **Reference check.** Every bib entry under the "post-audit additions" marker was written from
  memory. Check each against the publisher record (author lists, venue, year); two are marked
  `VERIFY` because their author lists are incomplete (`wang2025mextra`, `wang2024unlearningrag`),
  and `jayaraman2025permissioned` needs its arXiv id. Check the product-documentation URLs and the
  claims in Table `tab:grounding` against the current documentation.
- **Related-work table.** Check each cell of `tab:related` against the cited paper.
- **Author names in the IEEEtran header**, and biographies only if the venue asks for them.

## 3. Numbers already in the paper (verified, pilot re-analysis)

Appendix `app:pilot`, the RQ3 paragraph and RQ4a cite numbers from the pilot logs re-analysed with
the new judge and statistics (`analyze.py`, judge mode `unique`, target-clustered intervals):

| Claim | Source run | Value |
| --- | --- | --- |
| stub baseline (shared cache) LM, LM_new, told | `results/rq5_leakage` | 0.585 [0.526, 0.641], 0.058 [0.025, 0.098], 0.663 |
| legacy vs baseline LM, LM_memory | `results/rq5_leakage` | 0.585 vs 0.585; 0.230 vs 0.322 |
| Qwen2.5-3B baseline LM, LM_new | `results/model_grid_local` | 0.694 [0.649, 0.733], 0.358 [0.306, 0.409] |
| Llama-3.1-8B baseline LM, LM_new | `results-calc/results/model_grid_8b` | 0.506 [0.458, 0.551], 0.145 [0.109, 0.183] |
| full defense, stub and Llama | same | 0.000 in 100/100 events each (both earlier non-zero events were shared values) |
| existence, old baseline, insider / outsider | `results/rq3_existence` | 0.714 [0.664, 0.765] / 0.512 [0.490, 0.532]; content 0.717 |
| existence, full, stub / Llama | `rq3_existence`, `rq3_existence_8b` | 0.495 [0.486, 0.504] / 0.540 [0.520, 0.560] |
| shared fact values | corpus | 129/619 (21%) v2; 553/1276 (43%) Enron |
