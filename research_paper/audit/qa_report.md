# Final quality-assurance report

Date 2026-10-14. Manuscript: `research_paper/`, IEEE Access class, 57 references.

## Major structural and scientific changes

1. **Filled eight empty result placeholders.** `results.tex` §`sec:res-review` consisted of
   eight `\todo{}` markers. Every experiment behind them had completed. They are now five
   written subsections (published-design baselines, collateral cost, paste-back laundering,
   authorization overhead, real text) plus a paraphrase-judge subsection, with five new tables.
2. **Removed claims about experiments that never ran.** Qwen2.5-7B and `gpt-oss-120b` via Groq
   were described in the methodology and the experiment grid as completed. Both directories hold
   a manifest and zero runs. The claims are gone; the limitations now say the configurations
   exist and were not executed.
3. **Corrected a model misidentification.** Every `_8b` experiment used `llama3.1:8b`; the
   manuscript called these runs Qwen2.5-7B in four places.
4. **Qualified the headline zero.** "Zero measured leakage" now carries its conditions: exactly
   zero with the stub and on Enron, 0.002 with Llama-3.1-8B, 0.007 extra leak rate under a
   semantic judge in one stub cell, and 0.142 under paste-back laundering.
5. **Added the comparative result the paper was missing.** Two published enforcement patterns
   remove index leakage entirely and still leak about 0.50, and the check-after-retrieve pattern
   exposes existence at AUC 0.992. This is now in the abstract, a contribution, a table and the
   discussion, with an explicit statement that these are reimplementations of the pattern rather
   than measurements of those systems.
6. **Added the defense's real cost.** In-session recall on retained documents falls 0.454 → 0.334
   and refusals roughly double; the ablation shows this cannot currently be separated from the
   component that closes the memory channel. The discussion and conclusion now lead with this
   rather than with the 306 ms.
7. **Reported the broken assumption.** Laundering succeeds in 45% of events and reaches an
   unauthorized colleague in 1.3%. A1 is no longer assumed away; it is measured and stated as the
   limit of the approach.
8. **Corrected the real-generator narrative.** The manuscript claimed the stub underestimates
   leakage. Qwen2.5-3B leaks more, Llama-3.1-8B leaks less; only the memory channel is
   consistently worse. The stub is no longer described as a uniform lower bound.
9. **Refreshed stale numbers** from the 2026-10-08 ledger to the 2026-10-14 re-analysis: RQ3 AUCs,
   the blast-radius table (role revocation now separates from single-document, so the paragraph
   explaining why it did not was deleted), and the latency-bucket residual figures.
10. **Rewrote abstract, introduction contributions, discussion, limitations and conclusion** to
    agree with the above.

## Verified findings now in the paper

Baseline leakage 0.634 with 81% of revocations leaking; per-artifact 0.627 / 0.491 / 0.366–0.505;
index lifetime equal to Δ/2 at two crawl periods; cache threshold sweep 0.464 → 0.254; existence
AUC 0.984 undefended and 0.498 defended; transitive taint worth 0.337; ACL pre-filter the dominant
metadata mitigation; published patterns at ~0.50 and 0.992; collateral recall 0.454 → 0.334;
laundering 45%; authorization 2.06 calls and ~70 ms unpadded; Enron baseline 0.415 and full 0.000;
Llama-3.1-8B full 0.002 and existence 0.535.

## References

57 entries, up from 51. Six added in the Phase 0 audit (Thoth, DELF, Qapla, FIDES, Arora et al.
TACL 2023, EnronQA). Seven metadata corrections applied. All 57 cited, no orphans, no duplicate
DOIs or keys. `arora2023reasoning` and `ryan2025enronqa` are cited in the rewritten sections.

## Verification passes

| Pass | Result |
|---|---|
| A — numerical consistency | Every headline value traced to an artifact (`traceability.md`). A scripted sweep for 24 required values and 12 stale values found all required present and no genuine stale value; the six initial flags were legitimate (reranker channel 0.983, latency channel 0.495, stub leak rate 0.820, and the unrun model names appearing only where the text states they were not run). |
| B — implementation consistency | `top_k=5`, `gen_k=3`, `min_relevance=0.25`, `cache_threshold=0.90`, `summary_after=8`, `keep_recent=4`, `pad_strategy="bucket"`, `pad_ms=500.0` and the `full` preset switches all match the manuscript. `provenance.response_taint` matches the paper's taint equation including the non-transitive mode. |
| C — historical regression | All twelve issues from `docs/UPGRADE_PLAN.md` verified resolved in the implementation (`issue_register.md` Part A). None reopened. |
| D — citation verification | Carried out in the earlier Phase 0 audit: 50 of 51 original entries confirmed against a registry or publisher record, 27 double-sourced, zero fabrications; the six additions verified against publisher records. |
| E — LaTeX compilation | **The project's `ieeeaccess.cls` is not present in the repository or on this machine, so the manuscript cannot be compiled as submitted here.** Verified instead on a throwaway copy outside the repository with a substitute class and `plain` bibliography style: final pass has 0 errors, 0 undefined citations, 0 undefined references, 0 multiply-defined labels, 57 bibitems, 32 pages, worst overfull box 45 pt (the author-address line, a single-column stub artifact). |
| F — critical review | Produced the fairness caveat on the baseline reimplementations and the explicit separation of what the patterns cover from what those systems do. |

## Remaining limitations and evidence gaps

- **Compilation under the real class is unverified.** Must be run on Overleaf with the IEEE Access
  template before submission; column widths for the six `table*` environments and the two new
  single-column tables may need adjustment.
- **No Qwen2.5-7B or hosted model.** Configured, not run. Nothing in the paper speaks to models
  above 8B.
- **Judge precision unmeasured.** 150 items per cell were sampled for hand-labelling;
  `human_label` is empty. The 0.007 extra leak rate is an upper bound, not a verified residual.
- **No embedder grid.** All results are specific to the MiniLM encoder and cross-encoder; the
  cache thresholds in particular do not transfer.
- **One machine, simulated time.** Timing results are internally comparable only.
- **Paraphrased laundering untested.** Fingerprinting closes the verbatim case only.
- **The Pareto figure does not include the new baseline presets.** `fig6_rq5_pareto.pdf` shows the
  four original presets; the `authz_*` points appear in `tab:baselines` only. Regenerating it
  would need `make_figures.py` to be extended.
- **Three analysis directories are older than the rest** (`model_grid_local`,
  `rq2_revocation_window`, `rq3_existence_local`, 2026-10-11 against 2026-10-14). Their numbers are
  used as-is; a re-analysis would align them but is not expected to change them.
- **Author biographies remain `\todo{}`** in `biographies.tex`, and the data-availability statement
  no longer promises a Zenodo DOI.

## Publication readiness

Not publication-ready without the items above, in particular a compile under the real class and a
decision on how to present the defense now that its cost and its laundering limit are measured.
The scientific content is, to the best of this audit, congruent with the evidence in `results/`:
no claim in the manuscript now rests on an experiment that did not run, and every quantitative
claim resolves to a named artifact.

---

## Post-review changes, 2026-10-15

Applied after the user's citation and consistency review.

**Thoth and DELF read at full text.** Both sentences in `related_work.tex` were rewritten from
the papers rather than their abstracts, and both got stronger.

- *Thoth* (USENIX Sec '16): policies attach to **conduits** (files, pipes, network connections,
  key-value tuples), cover **confidentiality and integrity** (the earlier text said confidentiality
  only), and derivation is tracked **per task**: "A task's taint set is the set of policies of
  conduits it has read." The prototype is a distributed Apache Lucene engine evaluated on a 258 GB
  Wikipedia snapshot. This yields a genuine distinction the paper can now state: Thoth's unit of
  taint is the process, which accumulates the union of everything it has read; ours is the
  individual artifact.
- *DELF* (USENIX Sec '20): the vague "annotations stay incomplete until validated" is replaced by
  its reported numbers — developers handled deletion for only **20%** of edge types they created
  before the framework enforced it; validation found **3266** omitted edge-type deletions over
  eleven months; **62.2%** of new object types failed static validation at some point. The paper
  also **deletes an object for everyone and never describes per-principal deletion**, which
  independently confirms the revocation-versus-deletion distinction.

**T8 added to the threat model.** Paste-back laundering is now a numbered threat with
`taint_user_input` as its mitigation, and the text explains that it differs in kind from T1–T7:
it does not come from a copy the application made but from the user re-supplying content.
`threat_model.tex` now says eight mechanisms.

**Baselines moved under RQ4.** `sec:res-baselines` is now the third subsubsection of RQ4
("How much do published access-control designs remove?"), matching the RQ4 question in the
introduction. A cross-reference inside the moved block that had become self-referential was
rewritten.

**Preset counts corrected.** `defense.tex` now says four defense presets plus two
published-pattern presets, six in total; `setup.tex` rows say "defense preset".

**New Figure 9** (`fig9_baselines.pdf`), leakage against existence AUC for the four presets of
the baselines experiment. Both axes come from the same paired experiment.

**Figure 6 was not extended, deliberately.** Latency was never measured for `authz_prefilter` or
`authz_postfilter` — `rq5_utility` contains only the four defense presets, and no other
`utility_summary.csv` has an `authz_*` cell. Placing them on a latency axis would have required
inventing a number. The caption now says why they are absent and points to Figure 9.

**Compilation after these changes:** 0 errors, 0 undefined citations, 0 undefined references,
0 multiply-defined labels, 57 bibitems, 37 pages.

**Still open:** judge precision (`judge_validation.csv`, `human_label` empty; only 4 of 150 rows
have `judge_yes=1`, so precision needs just those four labelled), and the two-column layout check
under `ieeeaccess.cls`.

---

## 2026-10-19

- The three "upper bound on the discrepancy" statements about the paraphrase judge
  (`limitations.tex`, `methodology.tex`, `results.tex`) were wrong and are corrected. The judge's
  recall on paraphrased disclosure was never measured, so its null result does not establish an
  absence and 0.007 is the discrepancy it surfaced, not a ceiling on the one that exists. $\LM$ is
  again described as a lower bound on disclosure throughout.
- `sections/biographies.tex` deleted and its `\input` removed from `main.tex`, matching the
  author's Overleaf copy. No `\todo` markers remain anywhere in the manuscript.
- Compile after both changes: 0 errors, 0 undefined citations, 0 undefined references, 38 pages.
- Author confirms the two-column IEEE Access layout renders correctly.

**Remaining:** judge sensitivity is unmeasured (`results/judge_sample/judge_validation.csv`,
`human_label` empty on all 150 rows; the 146 `judge_yes=0` rows are the ones that test recall).
The manuscript states this limitation accurately as written, so this is an optional
strengthening rather than an outstanding defect.

**Divergence warning:** the author edits in Overleaf and this repository is a separate copy.
Changes made here after 2026-10-19 must be carried across by hand.
