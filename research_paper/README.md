# Afterimage paper (conference version, post-audit)

Rewritten on 22 Oct 2026 to address `../afterimage_reviewer_audit.md`. The IEEE Access journal
version of 19 Oct, its tables, the old proof build and the 8 Oct PDF are in `_pre_audit_backup/`.

## Build
`main.tex` uses `IEEEtran` in conference mode, which is in TeX Live, so it builds locally:

    tectonic -X compile main.tex          # or: pdflatex main && bibtex main && pdflatex main && pdflatex main

Switch the class line for an ACM (`acmart`, sigconf) or USENIX venue once the venue is chosen.

## State
Methodology, threat model, related work, defenses and setup describe the post-audit testbed. Results
are red `\pending{}` slots until the GPU grid runs (`../scripts/run_paper_grid.sh`, configs in
`../configs/paper/`). `RESULTS_TODO.md` maps every slot to its config and analysis column, lists the
human tasks (judge labels, reference check, real-stack demo), and lists the pilot numbers already in
the paper with their sources. Set `\pendingfalse` in `main.tex` for the submission build: any slot
left unfilled then fails the build.

`figures/make_figures.py` still draws the pre-audit figures from `../results/`; update it for the new
result directories once they exist.
