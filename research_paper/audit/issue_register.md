# Historical issue register and manuscript audit

Phases 2 and 4. Sources: `docs/UPGRADE_PLAN.md` (the prior review, dated
2026-10-06), `results/CHECKLIST.md` (2026-10-14), `results/RESULTS_FOR_PAPER.md`
(2026-10-08, stale), the code, and the manuscript itself.

## Part A — the twelve issues from the prior review (UPGRADE_PLAN.md)

| # | Original problem | Status | Evidence |
|---|---|---|---|
| 1 | Attacker read internal `raw_similarity_score` / `raw_latency_ms` | **Resolved & verified** | `Client.ask()` returns only `Observation`; `attacker.features()` consumes `obs` alone; `CLAUDE.md` states truth is never passed. Exposure profiles implemented. |
| 2 | Latency padding computed but not applied; 30 ms target vs ~1 s LLM | **Resolved & verified** | `full` preset pads to 500 ms buckets; `rq5_overhead` shows `full` p50 1000 ms vs `full_nopad` 764 ms, so padding is really applied. The 30 ms floor survives only as the `legacy` preset and the `pad30` ablation variant. |
| 3 | Mitigated mode skipped the LLM on refusals (timing oracle) | **Resolved, and turned into a result** | `fast_refusal` is now an explicit ablation variant; measured AUC rise 0.854 → 0.897 with a post-filter and no padding. |
| 4 | Stale index threat not modelled; `on_revocation` was `pass` | **Resolved & verified** | `SyncPolicy` live/periodic/event implemented; `rq2_revocation_window` measures index lifetime = Δ/2. |
| 5 | Negative probes were nonsense topics | **Resolved** | Twin-world design with projects of 1–2 related documents; negatives retain related material. |
| 6 | EIA label depended on what each mode retrieved | **Resolved** | Label is the world (1/0), shared across presets by construction. |
| 7 | 11 docs, 13 probes, 1 run, no seeds or CIs | **Resolved** | 5 tenants × 100 docs; 5 seeds; percentile bootstrap CIs; seed-clustered intervals and Wilcoxon added. |
| 8 | LM was keyword substring matching; `LM_total = max()` of mixed denominators | **Resolved** | LM is now fraction of the target's secrets, exact value or canary, excluding values legitimately present in other source docs (`judge.disclosed()`). |
| 9 | Leakage half-life from 5 binary points | **Resolved** | Kaplan–Meier with right-censoring at 48 h over 200–250 events. |
| 10 | Baseline and mitigated differed in 7 things at once | **Resolved** | `Mitigations` dataclass; leave-one-out ablation (`rq4_ablation_*`). |
| 11 | LLM errors silently fell back to the stub | **Resolved** | `llm_client.py` raises; backend explicit. |
| 12 | `query_count_since_revocation` global; Chroma written but never queried | **Resolved** | `VectorIndex` filters with Chroma `where` on `acl__<user>`. |

All twelve are addressed in the implementation. None was found still open.

## Part B — manuscript defects found in this audit

Severity: **S1** scientifically wrong or unsupported; **S2** stale or imprecise;
**S3** editorial.

### S1 — claims experiments that were never run

| Location | Claim | Reality |
|---|---|---|
| `methodology.tex` "Larger and hosted generators" | "repeated with Qwen2.5-7B-Instruct served locally with Ollama, and the revocation experiment with a hosted model (`gpt-oss-120b` through Groq)" | `results/model_grid_7b/` and `results/model_grid_groq/` contain **only `manifest.json`** — zero run files, no `analysis/`. Neither executed. `rq3_existence_7b`, `rq5_collateral_7b`, `enron_revocation_7b` likewise have no results directory. |
| `setup.tex` `tab:grid` | Rows for "Qwen2.5-7B revocation", "Qwen2.5-7B existence", "gpt-oss-120b (Groq)" | Same. Rows must be deleted. |
| `setup.tex` `tab:grid` | Rows `1'` (RQ1 with restricted warm-up as a separate experiment) and `4a'` (4a with an 18 h probe) | No separate result directories. The restricted warm-up was folded into `rq1_surfaces` itself (its blast-radius numbers changed), so these are not separate experiments. |
| `methodology.tex` "Paraphrase judge" | "Two authors label 150 judged items by hand to estimate the judge's precision." | `results/judge_sample/judge_validation.csv` holds 150 sampled rows with **`human_label` empty on all 150**. The hand-labelling was not done. Judge precision is unestimated. |
| `setup.tex` `tab:grid`, stress row | "generator ∈ {Qwen2.5-3B, Qwen2.5-7B}" | `rq6_taint_stress_8b` used **llama3.1:8b** only; the grid axis is `taint_user_input` {off, on}, not generator. |

### S1 — model misidentification throughout

Every `_8b` experiment used **`llama3.1:8b`** (Meta Llama 3.1 8B Instruct), confirmed
from each `manifest.json`. The manuscript calls these runs "Qwen2.5-7B". Affects
`setup.tex` (four rows) and `methodology.tex`.

### S1 — "zero leakage" is overstated

| Evidence | Value |
|---|---|
| stub, `full`, all main experiments | LM exactly 0.000 (750 events in `rq1_surfaces`, 250 in `rq5_leakage`, 200 in `rq4_ablation_revocation`) |
| Enron, `full`, stub | 0.000 (300 events) |
| Enron, `full`, Llama-3.1-8B | 0.000 (24 events) |
| **synthetic, `full`, Llama-3.1-8B** | **0.002 [0.000, 0.006]; 1 of 100 events leaked; that leak's median lifetime 7200 s** |
| **stub, `full`, LLM paraphrase judge** | **extra leak rate 0.007; 0.001 of secrets** (`judge_summary.md`) |
| **`full` under paste-back laundering** | **LM 0.142, laundering succeeds 45% of events** (`rq6_taint_stress_8b`, fingerprinting off) |

The abstract, conclusion and §RQ5 state zero without qualification. The honest
claim is zero under exact matching with the stub and on Enron, and 0.002 with
Llama-3.1-8B, with named conditions under which it is not zero.

### S1 — "the stub underestimates leakage" does not generalise

`discussion.tex` says memory "contributed more leakage than the stub suggested
(0.715 against 0.305)" — true for Qwen2.5-3B. But Llama-3.1-8B leaks **less**
overall than the stub: 0.550 vs 0.646, paired −0.096 [−0.161, −0.020], p = 0.016.
Its memory leakage is higher (0.488 vs 0.305) while its cache leakage is lower
(0.442 vs 0.646). Direction of the overall effect is model-dependent.

### S2 — stale numbers superseded by the 2026-10-14 re-analysis

| Location | Manuscript | Current evidence |
|---|---|---|
| `results.tex` RQ3, `t05_rq3`, `t06_rq3chan` | strawman 0.983, baseline 0.612, legacy 0.592, full 0.495; TPR 68.9% | 0.984 [0.981, 0.987], 0.616 [0.600, 0.632], 0.592 [0.576, 0.607], 0.498 [0.481, 0.513]; TPR 0.728 |
| `results.tex` blast radius, `t02_blast` | index offboard 0.858 [0.842, 0.874], 4.76 docs; cache 0.820, 4.63 docs; memory offboard 0.215, 1.08 docs | index 0.793 [0.775, 0.809], 6.38 docs; cache 0.767 [0.750, 0.783], 6.24 docs; memory 0.119, 0.94 docs |
| `results.tex` RQ1 blast paragraph | "Role revocation is therefore not distinguished from single-document revocation by the blast-radius probes" and the warm-up explanation | **No longer true.** Role now differs: index 0.660 [0.632, 0.686] / 2.31 docs vs single-doc 0.627 / 0.80 docs. The explanation must be deleted. |
| `discussion.tex` bucket residual | "AUC 0.508: 8.2%, 57.0% and 34.8% … against 8.7%, 57.9% and 33.3%" | Matches no current file. `rq3_existence_8b` full: AUC_bucket_only 0.516, shares 0.028/0.003/0.969 vs 0.031/0.003/0.966. `rq3_existence_local` full: 0.509, 0.317/0.386/0.297 vs 0.331/0.382/0.286. |
| `results.tex` RQ5 p95 | "p95 is 1500 against 1493 ms" | `rq5_utility` gives 1500/1493, but `rq5_overhead` gives `full` p95 **2000** vs baseline ~1540. Both must be reported with their configs. |

### S1 — results that exist but are unwritten

`results.tex` §`sec:res-review` is **eight `\todo{}` placeholders**. Every one of
those experiments completed. Unreported findings, in order of importance:

1. **Paste-back laundering breaks assumption A1.** 45% laundering success, LM 0.142,
   colleague leakage 0.013; query fingerprinting reduces all three to 0.000.
2. **Literature baselines leak ~0.50.** `authz_prefilter` 0.500, `authz_postfilter`
   0.497 vs baseline 0.634 and full 0.000. Both zero out index leakage and leave
   cache and memory open.
3. **`authz_postfilter` existence AUC 0.992 [0.989, 0.995]**, TPR@1%FPR 0.887 — a
   published check-after-retrieve design is near-perfectly vulnerable.
4. **Over-tainting has a real cost.** Retained-document recall in the triggering
   session falls 0.454 → 0.334 and refusals roughly double 0.283 → 0.499;
   with Llama-3.1-8B 0.944 → 0.675. Fresh-session recall is unaffected (1.000).
   Dropping transitive taint restores recall and reinstates LM 0.36–0.46.
5. **Real text works.** Enron: baseline 0.415, full 0.000 over 300 events;
   index lifetime 43200 s = Δ/2 on real email.
6. **Authorization overhead is negligible; padding is the cost.** +70 ms without
   padding, +306 ms with it; a 10 ms IAM round trip adds ~30 ms; 2.06 authz
   calls per query.
7. **The paraphrase judge largely validates exact matching** — 0.000 extra on the
   8B cells, 0.007 on the stub full cell.

### S2 — limitations section contradicts the evidence

`limitations.tex` states "A real-data track was not run", "Larger models were not
run", and "a semantic judge was not run". All three are false as of 2026-10-14.
Its `\todo` acknowledges this. The section needs rewriting around the limitations
that remain real: no Qwen2.5-7B or hosted model, no embedder grid, unestimated
judge precision, single machine, probe-grid resolution, A1 violated without
fingerprinting, and the newly measured collateral cost.

### S3 — editorial

- Nine `\todo{}` markers remain in `results.tex`, `limitations.tex`, `setup.tex`,
  `availability.tex` plus four in `biographies.tex`.
- `availability.tex` has a placeholder Zenodo DOI.
- `setup.tex` environment paragraph has a `\todo` for the robustness-run hardware.
- `data.tex` names only Qwen2.5-3B as the real generator; Llama-3.1-8B is absent.

## Part C — issues that cannot be resolved from available evidence

| Item | Why |
|---|---|
| Judge precision | `human_label` column is empty; no hand-labelled ground truth exists. The manuscript must drop the claim, not estimate a number. |
| Qwen2.5-7B / Groq behaviour | Never executed. Must be stated as future work, not as a result. |
| Embedder sensitivity | `configs/model_grid.yaml` exists; no results directory. |
| Hardware for the robustness runs | `setup.tex` `\todo` asks for it; not recorded in any manifest or log I could find. Must be stated as a single-machine caveat instead. |
