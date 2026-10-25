# What the paper still needs

The paper was scoped on 25 Oct 2026 to the reduced Enron grid in `configs/min/` (branch
`min-enron-run`): Llama-3.1-8B (Ollama default 4-bit build) on one laptop GPU, plus stub runs. Every
red `\pending{}` in the PDF comes from one of the runs below or from the human work in section 2.
Build with `\pendingfalse` in `main.tex` before submission: any leftover marker then stops the build.

## 1. Runs → paper slots

Run `python scripts/run_min_grid.py pilot`, then `paraphrases` (must end with "0 questions still
missing"; `model` refuses to start otherwise), then `model`, with `stub` alongside (see
`README_MIN_RUN.md`). Commit the resulting `data/paraphrases.json` with the results. Each
run writes `results/<name>/analysis/`. Revocation runs are analysed with the baseline cell as the
paired reference; existence runs with the default tenant split (never `--train-tenants`).

| Slot | Config | Analysis file → columns |
| --- | --- | --- |
| Tab. rq1, R1 | `p_min_enron` | `revocation_summary.csv` → `LM`, `LM_new`, `LM_re`, `LM_from_1h`, `LM_index`, `LM_cache`, `LM_memory`, `canary_leak_rate`, `summary_retains` |
| R2 | `p_min_enron`, `p_min_defenses_stub` | `revocation_summary.csv` → `LH_median_leaking_s`, `LH_index_median_leaking_s`, `censored`, `LM_from_24h` |
| Tab. rq3, R3 | `p_min_existence_stub` | `existence_eia.csv` (gboost, with_reranker, combined; `attacker` insider/outsider) → `AUC`, `TPR@1%FPR`, per channel for "strongest channel"; `existence_strata.csv` |
| Tab. defenses (L8 rows), R4 | `p_min_enron` | `revocation_summary.csv` → `LM`, `LM_new`, `retained_recall_same`, `retained_refusal_same`, `authz_decisions_per_query`; `revocation_paired.csv` (Holm column) |
| Tab. defenses (stub rows) | `p_min_defenses_stub`; insider AUC from `p_min_existence_stub` | same columns; `existence_eia.csv` → `AUC` (insider) |
| R5 | `p_min_enron`, `p_min_defenses_stub` | `retained_recall_same`, `retained_refusal_same`, `authz_calls`, `authz_decisions_per_query` |
| R6 | `p_min_update_stub` | `revocation_summary.csv` → `LM_update` |
| Setup: units "n" | `p_min_existence_stub` | `existence_eia.csv` → `n_test` |
| Setup: Ollama version | the laptop | `ollama --version` |
| App. V | `p_min_defenses_stub` | `LH_index_median_leaking_s` vs `analytic_index_staleness_mean_s` (daily crawl), cache lifetime vs 3600 s TTL |
| App. S | `p_min_defenses_stub` | per-artifact `LM_*` and `summary_retains` |
| Abstract, intro summary, discussion D1–D2, conclusion | all of the above | at most five numbers in the abstract |

`p_min_pilot` is a timing check only and fills no slot. Write the result text whichever way it comes
out; if `epoch` keeps as much retained-document recall as `full`, say the simpler mechanism wins.

## 2. Human work

- **Judge validation.** `results-calc/results/judge_sample/judge_validation.csv` has 150 rows and an
  empty `human_label` column, so the paper calls the model judge unvalidated. If two annotators label
  it later, restore a measured precision/recall sentence in methodology and limitations.
- **Ethics.** Done: no maintainer notification (documented, configurable behaviour); `sections/ethics.tex`.
- **Availability.** Repository URL and log deposit (`sections/availability.tex`); the current URL
  names an author, which breaks double-blind review.
- **Venue.** `main.tex` uses IEEEtran conference mode. Switch the class for an ACM or USENIX venue
  and cut to its page limit.
- **Reference check.** Done 25 Oct 2026 for the post-audit entries (Crossref, arXiv, USENIX pages;
  documentation URLs and the claims of Table `tab:grounding` checked against the pages). Left for
  you: `redell1974selective` has no online record (venue from textbook bibliographies), and IEEE's
  record of `backes2005lazy` lists two authors where IBM's report lists three (Cachin); the bib keeps three.
- **Related-work table.** Check each cell of `tab:related` against the cited paper.
- **Author names** in the IEEEtran header.
- **Real-stack demonstration.** Done 25 Oct 2026 with Llama-3.1-8B (`results/real_stack_demo/demo.json`,
  judge Qwen2.5-7B) and earlier with Qwen2.5-7B (`demo_qwen2.5-7b.json`); paragraph `sec:res-realstack`,
  all answers hand-checked.

## 3. Numbers already in the paper (verified, pilot re-analysis)

Appendix `app:pilot`, the RQ3 paragraph and the "Defenses compared" paragraph cite numbers from the pilot logs re-analysed with
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
| real-stack demo (Llama-3.1-8B), cache / reworded cache / memory / control | `results/real_stack_demo/demo.json` | 6/10, 6/10, 5/10 (1 new), 0/10; memory values in summary 4, tool output 2 |
| real-stack demo (Qwen2.5-7B), cache / memory / control | `results/real_stack_demo/demo_qwen2.5-7b.json` | 6/10 (7/10 judge), 5/10 (6/10), 0/10 |
