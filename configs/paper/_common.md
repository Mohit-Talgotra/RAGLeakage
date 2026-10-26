# Paper grid (post-audit)

Every config here is for the rented-GPU run. Shared choices, set in each file's `base`:

- `corpus: synthetic_v3@seed` gives each seed its own generated corpus (audit H1, H3);
  `enron_c` is the real-text corpus with canaries (build it first, see run_paper_grid.sh).
- Real models are the primary evidence (audit C4); the stub stays as a validation harness.
  `summarizer: llm` makes the chat-memory summary come from the same model.
- `probe_readonly: true` (probes do not refresh what they measure), `probe_unseen: true`
  (LM_new can be non-zero), `probe_paraphrase: file` (natural rewordings, audit H2).
- `llm_cache: false` in existence runs, so each call's latency is measured, not replayed.
- At least 200 events per real-model cell (audit H5): 5 seeds x 40 events.
