# Why provenance-tainted revocation holds, and when it does not

Reviewer question (item 2): zero leakage looks guaranteed by construction if the taint is
complete. When is it incomplete? This note gives the invariant, the argument that the code
enforces it, the assumptions it rests on, and the experiments built to break it.

## Invariant

> **I.** For every derived artifact *a* (cache entry, memory turn, rolling summary), if content of
> a restricted document *d* reached *a*, then *d* ∈ taint(*a*).

**Enforcement.** Revocation of *d* for user *u* must stop *a* from reaching *u*. It does so in
two ways:
- eagerly: evict or purge every artifact with *d* ∈ taint;
- lazily: on every read, require that *u* holds every document in taint(*a*).

If **I** holds, the lazy check alone makes post-revocation disclosure through derived artifacts
impossible: any artifact that carries *d* has *d* in its taint, and *u* no longer holds *d*. The
index itself is covered by the live ACL check.

## Why the code maintains I

Content enters an artifact only through a generation step. That step's inputs are:
1. the retrieved chunks passed to the LLM (`gen`);
2. the memory turns in the prompt;
3. the user's query.

The code covers each write path:
- `provenance.response_taint` is the only place a response taint is computed. It is the union
  of the docs in (1) and, in transitive mode, the taints of every turn in (2).
- Cache writes and memory writes take that taint unchanged (`pipeline.py`).
- A cache hit re-serves an entry together with its stored taint.
- A rolling summary's taint is the union of the turns it replaces (`session_memory.py`).

By induction over the sequence of writes, every artifact's taint covers every document that
reached it through (1) or (2), however many times the content was copied, paraphrased or
summarised. Taint follows data flow, not wording, so a paraphrasing model cannot launder content.
`tests/test_taint_invariant.py` checks **I** directly. It runs random sessions with frequent
summarisation, then verifies that no artifact holds a restricted secret (unique to one document)
without that document in its taint. It also checks that non-transitive taint breaks **I**, which is
the gap the defense closes.

## Assumptions

- **A1. User input is untainted.** Input (3) carries no taint by default. If a user pastes
  restricted content into a query, the response and the memory turn built from it are not
  tainted with its source. This is the case built to break **I**; see the experiment below.
  `taint_user_input` closes it for known secrets: the query is fingerprinted against the secrets
  of restricted documents and tainted on a match. The fingerprint only matches verbatim
  secrets, so a user who rewrites the content in their own words is outside any
  content-agnostic tracking. That is the standard declassification limit of information-flow
  control: a principal who legitimately read the data can always re-type it.
- **A2. No untracked inputs.** The prompt has no other inputs, such as tool output, web
  search or plug-ins. Each additional input source must label its output the same way.
- **A3. Document ACLs are correct.** If document *e* copies figures from restricted
  document *d* but has a broader ACL, *e* legitimately serves them. This is a data-governance
  error, not a revocation failure, and no artifact-level mechanism can see it.
- **A4. Consistent IAM reads.** The live check and the lazy checks read IAM state at least as
  new as the revocation. In Zanzibar's terms, a check must be evaluated at a snapshot no older
  than the revocation's zookie; otherwise the "new enemy" problem reappears for the length
  of the IAM replication lag.

## Experiments

| Case | Config | Expected | Measured |
|---|---|---|---|
| Paraphrase across sessions (real LLM) | `model_grid_7b` + `scripts/judge_sample.py` | 0 under full, also by the LLM judge | see `results/judge_sample/` |
| Paste-laundering: the revoked victim pastes the old answer, a colleague without access asks | `rq6_taint_stress` (`launder: true`) | leak to the colleague possible without `taint_user_input`; 0 with it | `LM_colleague` in `results/rq6_taint_stress/` |
| Derived document with a broader ACL (A3) | not run | leaks by design; out of scope | |
