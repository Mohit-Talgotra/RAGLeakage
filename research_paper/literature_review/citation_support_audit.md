# Citation-support audit

Does each reference actually support the sentence citing it? Audit date
2026-10-14. **58 citation sites** across `sections/*.tex`, covering **all 51**
bibliography keys — no orphan entries, no uncited entries. The manuscript was
not edited.

Method: every `\cite{}` was extracted with its surrounding sentence. Sites
whose sentence is a title-level descriptor ("X studies Y", where Y is the
paper's own title claim) were checked against the verified metadata and
abstracts from the reference-verification pass. Sites whose sentence makes a
**specific factual claim about the cited paper's content** were checked against
the paper itself. Seven fell in the second class; six of their sources were
obtained and read at the relevant section, one could not be obtained.

## Summary

| Verdict | Sites |
|---|---|
| Supported as written | 52 |
| **Misstates the source — reword** | 3 (`pang2019zanzibar` ×2, `zhong2026honeybee` ×1) |
| **Source is stronger than the sentence claims — upgrade** | 1 (`buttcher2005security`) |
| **Support unverifiable — source unobtainable** | 1 (`bailey2006secure`) |
| Fabricated or wholly unsupported | **0** |
| Missing references found | 2 (EnronQA; Arora et al. TACL 2023) |

No citation was found attached to a claim the source contradicts. The three
rewording cases are over-reach or imprecision, not invention.

---

## Finding 1 — `pang2019zanzibar`: the "new enemy problem" is misdefined

**Sites:** `related_work.tex` (S25) and `defense.tex` A4 (S04).

**Current text (S25):** "Zanzibar addresses the ``new enemy'' problem, in which
a check evaluated against stale authorization state lets a user whose access was
just removed see protected content, by binding checks to consistency tokens."

**What Zanzibar §2.2 actually says.** The new enemy problem arises "when we fail
to respect the ordering between ACL updates or when we apply old ACLs to new
content", and it has **two distinct cases**:

- *Example A — ACL update order.* Alice removes Bob from a folder's ACL, then
  has Charlie move new documents into that folder. Bob sees them if the check
  ignores the ordering of the two ACL changes.
- *Example B — old ACL on new content.* Alice removes Bob from a document's
  ACL, then Charlie adds new content. Bob sees it if the check uses an ACL from
  before his removal.

The prevention mechanism is correctly described: zookies, opaque consistency
tokens encoding a global timestamp later than all prior ACL writes, so each
check is evaluated at a snapshot at least as fresh as the content version,
backed by Spanner's external consistency and TrueTime.

**The problem.** Both Zanzibar cases involve **content or ACL writes that happen
after the revocation**. This manuscript's situation is different: the artifact
was derived *before* the revocation and is re-served *after* it, with no
intervening write. That is neither Example A nor Example B. The current sentence
flattens Zanzibar's two specific ordering failures into generic staleness, and
then implicitly claims this paper's case as an instance of it.

**Why fixing this helps the paper.** Stated correctly, this paper's failure mode
is *not* the new enemy problem — it is a distinct third case: a derived artifact
that predates the revocation and carries no authorization check of its own. That
is a stronger position than "an instance of a known problem". Recommended
rewrite: give Zanzibar's definition as the two ordering cases it is, note that
both concern writes after the revocation, and state that post-revocation leakage
through pre-existing derived artifacts is adjacent but distinct. Keep the zookie
description and keep A4, which only needs the lagging-replica point and is
otherwise fine once the definition above it is correct.

**Related site, no change needed.** `methodology.tex` S13 describes
`authz_postfilter` as "Zanzibar-based ``check after retrieve''". This is
grounded: Zanzibar §3.2.5 states that search "requires conducting ACL checks for
all candidate results", and §1 notes search often needs "tens to hundreds of
checks". Zanzibar does not name or design the pattern, so the existing "in the
style of" hedge is doing the necessary work. Optionally cite §3.2.5.

---

## Finding 2 — `zhong2026honeybee`: "behaves like baseline" understates it

**Site:** `methodology.tex` S15.

**Current text:** "Designs that filter on a materialized copy of the ACL
(vector-store metadata filters, per-user indexes, or role
partitions~\cite{zhong2026honeybee}) behave like \texttt{baseline}."

**What HoneyBee actually does.** It materializes overlapping partitions, with
vectors duplicated where several roles need them, each partition carrying its
own similarity index, plus a precomputed routing table from role combinations
and users to partitions. So far the sentence holds. But HoneyBee has a
**Section 5.2, "Handling Updates"**, which states that because partitioning is
role-based, "these updates can be performed incrementally without requiring a
full rebuild of the partitions", and covers user addition and deletion, document
insertion and deletion, and role addition and deletion, with "only the indices
for the affected partitions need to be updated". **Section 7.4** benchmarks
this: incremental deletion "consistently maintains query latency comparable to
the complete rebuild approach", while large insertion batches degrade, so
HoneyBee "might benefit from rebuilding when permission workloads change
significantly".

**The problem.** `baseline` in this paper is defined as a materialised ACL copy
trusted between syncs, with no revocation hook on the cache and no memory purge.
HoneyBee has an explicit incremental update path on permission change, which
`baseline` does not. Putting it in the same behavioural class understates a
competitor's design, and a reviewer who knows the paper — or one of its authors
— will notice.

**What is genuinely true, and is the better claim.** HoneyBee does **not**
discuss staleness, the delay between a permission change and its effect on
queries, or consistency between permission data and partitions during updates.
Its contribution is partition efficiency, not revocation timeliness. So the
accurate and still-useful statement is: HoneyBee updates role partitions
incrementally when permissions change, but neither analyses the interval between
the change and the update nor addresses derived artifacts outside the index;
designs that filter on a materialised ACL copy *without* such an update path
behave like `baseline`. That keeps the preset mapping honest and sharpens the
gap at the same time.

Related sites S07 and S23 ("HoneyBee partitions a vector database dynamically to
make role-based filtering efficient") are accurate and need no change.

---

## Finding 3 — `buttcher2005security`: the source is stronger than the sentence

**Site:** `related_work.tex` S18.

**Current text:** "B\"uttcher and Clarke show that in multi-user full-text
search, ranking statistics computed over documents a user cannot read leak
information about those documents."

**Verified, and then some.** Section 5 of the FAST '05 paper shows that under a
post-processing design — a system-wide BM25-ranked index with unreadable files
removed afterwards — an arbitrary user can "obtain information about the content
of files for which he does not have read permission". The attack: create files
the attacker controls, submit queries, read the relevance scores or relative
ranks, and recover system-wide collection statistics such as how many files
contain a target term. The paper states that "the search system can be used as a
covert channel" and sketches a phrase-query extension that could reconstruct a
file's content.

**Two consequences the manuscript is currently missing.**

1. **Their threat model is the same shape as this paper's existence inference.**
   An unprivileged querier, no read access to the target, observing scores or
   ordering, aiming to learn about files they cannot read. The manuscript's line
   "Our index findings are the RAG counterpart of these results" is true and
   under-stated; it can say so much more directly, and should, because a
   twenty-year-old precedent that matches the threat model is grounding, not
   competition.
2. **Their fix is the ACL pre-filter.** Büttcher and Clarke's "query
   integration" restricts each posting list to searchable files *before*
   ranking, so the query processor never sees unreadable content and the
   statistics it computes are user-specific. That is exactly the pre-filter
   component of this paper's defense. It should therefore be cited in
   `defense.tex` where the ACL pre-filter is introduced, not only in related
   work. This narrows the pre-filter's novelty — which the paper never claimed —
   and makes the defense better grounded.

---

## Finding 4 — `bailey2006secure`: support unverifiable, source unobtainable

**Site:** `related_work.tex` S17.

**Current text:** "Bailey et al.\ compare implementations of document-level
security that copy permissions into the index with implementations that check
each result at query time, and analyze the trade-offs between them."

**Partial retraction of the earlier flag.** The paper's own full title is "Secure
Search in Enterprise Webs: Tradeoffs in Efficient Implementation for Document
Level Security", so the trade-off framing is supported by the title alone. My
earlier report implied the sentence was unsupported; that was too strong.

**What remains unresolved.** The publisher record starts the paper at p. 493 and
OpenAlex types it a conference abstract, consistent with a two-page CIKM 2006
poster. The ACM full text could not be retrieved (both the PDF and abstract URLs
returned client errors, and the author's own publication page was unreachable),
so the depth implied by "compare ... and analyze" cannot be confirmed.

**Action.** Retrieve it through VIT's ACM Digital Library access and either keep
the sentence or trim it. If it cannot be obtained, reduce to what the title
supports on its own — that Bailey et al. set out the trade-offs in implementing
document-level security — and let Büttcher & Clarke and Zerber+R carry the
analytical weight. Note this entry is from the unvetted expansion group.

---

## Finding 5 — two missing references

**EnronQA has no bibliography entry.** `methodology.tex` uses "the questions and
answers of the EnronQA benchmark" for the real-text track, citing it only as a
footnote naming "EnronQA (Ryan et al., 2025)" with a HuggingFace dataset URL.
The real-text track depends on this benchmark, so it needs a traceable citation.
It is arXiv 2505.00263, "EnronQA: Towards Personalized RAG over Private
Documents"; no peer-reviewed venue was found, so keeping it out of the
journal-tier set is correct — but it belongs in the bibliography as a `@misc`
entry with the arXiv identifier, not as a bare footnote URL. A staged entry is
in `new_references.bib`.

**Arora et al., TACL 2023 — a genuine journal-tier miss.** "Reasoning over
Public and Private Data in Retrieval-Based Systems", Transactions of the
Association for Computational Linguistics 11, pp. 902–921, DOI
10.1162/tacl_a_00580 (Arora, Lewis, Fan, Kahn, Ré). A peer-reviewed journal
paper directly on the public/private data split in retrieval-based systems —
the problem setting of this manuscript. It surfaced while resolving the EnronQA
footnote, which is a reminder that the footnote was hiding a reference trail.
Verified against the ACL Anthology record and staged in `new_references.bib`.

---

## Sites verified as written, worth noting individually

- **`cao2015towards` (S34)** — exact match, and carefully worded. The paper says
  forgetting systems "must carefully track data lineage even across statistical
  processing or machine learning". The manuscript says Cao and Yang "argue"
  this, which is precisely right: their concrete contribution is narrower
  (machine unlearning by transforming learning algorithms into a summation
  form), and full lineage tracking is explicitly their future work. Had the
  sentence said "show", it would have been wrong. No change.
- **`carlini2022mia` (S12)** — the low-FPR argument is the paper's central
  methodological claim. Correctly used.
- **`reimers2019sbert` + `wang2020minilm` (S01)** — cited jointly for
  `all-MiniLM-L6-v2`. Correct attribution: the model is a sentence-transformers
  encoder (Reimers & Gurevych) built on MiniLM (Wang et al.).
- **The IFC roll-call (S26–S31)** — HiStar, Flume, RESIN, TaintDroid,
  decentralised labels, language-based IFC. Every descriptor matches its source.
- **The side-channel roll-call (S37–S46)** — Kocher, Felten & Schneider, Bortz &
  Boneh, Ristenpart et al., Gu et al., Song et al., Wu et al., Weiss et al.,
  Zhang et al., Afiffy et al. Every descriptor is a title-level claim and holds.
- **The scope-exclusion sites (S56, S57)** — prompt injection and poisoning
  correctly labelled integrity threats and excluded.

## What this pass did not do

It judged whether each source *can* support its sentence, reading the specific
section at issue for the seven content-level claims. It did not read the other
44 sources end to end, so a citation whose sentence is a faithful title-level
descriptor but whose source has a caveat buried in its evaluation would not be
caught here. For the 21 author-vetted entries that risk is low. For the
expansion-30 it is the remaining residual, now reduced to title-level claims
only.

---

## Applied 2026-10-14

All of the following were applied to the manuscript after the audit. Pre-edit
copies of the four touched files are in `literature_review/pre_edit_backup/`.
No code, config, result or figure file was touched.

**`references.bib` — six metadata corrections, six entries added (51 → 57).**
`sandhu1996rbac` journal `IEEE Computer` → `Computer` plus DOI;
`jeong2025permissionrag` DOI added; `liu2025mask` pages 2894–2907;
`wang2025unique` author `Yu, P.` → `Yu, Philip S.` plus pages 1–36;
`bodea2026sok` stale "Accepted; preprint" note removed; `qi2025follow` pages
48733–48755. Added: `elnikety2016thoth`, `mehta2017qapla`,
`cohngordon2020delf`, `costa2026fides`, `arora2023reasoning`,
`ryan2025enronqa`.

**`sections/related_work.tex` — five edits.**
(a) Büttcher & Clarke upgraded to what §5 of the source actually shows, with
the threat-model parallel and the query-integration/pre-filter link stated.
(b) Arora et al. added to the access-control subsection.
(c) The "new enemy problem" restated as Zanzibar's two ordering cases, followed
by the distinction from this paper's case; Qapla added.
(d) Thoth and FIDES added to the IFC subsection.
(e) DELF added to the deletion subsection, with its annotation-incompleteness
finding tied to the read-time check.

**`sections/methodology.tex` — two edits.** HoneyBee's incremental update path
acknowledged and the `baseline` equivalence re-scoped; EnronQA given a real
citation, with the dataset URL kept as a footnote.

**`sections/defense.tex` — one edit.** Büttcher & Clarke cited at the ACL
pre-filter.

**One scope extension, flagged.** Edit (d) required narrowing the sentence "The
contribution here is to apply it to the derived state of LLM applications",
because placing FIDES beside it would have produced a direct contradiction in
adjacent sentences. The replacement concedes that prior work has already applied
IFC to retrieval systems and to LLM pipelines, and claims the *persistent*
derived state of a RAG application plus the measurement. This was the minimum
change needed for internal consistency; it is a one-sentence edit and the
pre-edit text is in the backup directory.

**Still pending, deliberately not applied.** The `bailey2006secure` sentence
(awaiting the poster); the abstract's "We propose provenance-tainted revocation"
and contribution 3, which are the remaining novelty-framing items from
`research_gap_assessment.md`; the optional `zeldovich2006making` page range; the
conditional unlearning-RAG reference and the optional InputSnatch reference.

**Build check.** The project's own `ieeeaccess.cls` is not present on this
machine, so `main.tex` cannot be compiled here as submitted — a pre-existing
condition, unrelated to these edits. Verified instead on a throwaway copy
outside the repository with a substitute class: the edited prose typesets with
no errors, and **BibTeX resolved all 57 keys with zero warnings and emitted 57
bibitems**. A key-resolution check across `sections/`, `tables/` and `main.tex`
reports 65 citation sites, 57 distinct keys, no undefined keys and no unused
entries.

---

## Correction to this audit, 2026-10-14 (later the same day)

**Finding 4 is withdrawn. `bailey2006secure` is a ten-page CIKM 2006 full
paper, pages 493–502, and the sentence citing it stands as written.**

dblp (`conf/cikm/BaileyHM06`) and a second independent publication index both
give the page range as 493–502. Ten pages is a CIKM full-paper length, and the
paper's own title is "Secure Search in Enterprise Webs: Tradeoffs in Efficient
Implementation for Document Level Security". A full paper with that title can
comfortably support "compare implementations … and analyze the trade-offs
between them". No change to `related_work.tex` is needed, and nothing is left
pending on this entry. The verified page range has been added to the bib entry.

**How the error happened, because it matters for how the rest of this audit
should be read.** The flag came from a single OpenAlex record, which reported
the page range as 493–493 and typed the work a "conference abstract". I treated
that one record as authoritative, inferred "poster" from the single-page start,
and raised it as the audit's only claim-level risk — across three separate
reports — without cross-checking a second registry. That is precisely the
failure this audit was commissioned to catch, committed by the audit itself.
The ACM Digital Library was unreachable throughout, which is why no publisher
record ever contradicted OpenAlex; the correct response to that was to consult
dblp, not to publish an inference.

**Consequences for the rest of the findings.** Findings 1, 2, 3 and 5 are
unaffected: each rests on the cited paper's own text, read at the section in
question (Zanzibar §2.2, HoneyBee §5.2 and §7.4, Büttcher & Clarke §5), not on
registry metadata. The entries whose verification rests on a *single* registry
record are the ones to re-check if precision matters: every row in
`literature_matrix.csv` whose `verification_status` names exactly one source.
Page ranges and publication types are the fields where OpenAlex has now been
shown to be unreliable for this bibliography; titles, authors, venues and years
matched independent evidence wherever two sources were available.

**Count effects.** `bailey2006secure` moves from "entry whose supported claim
needs softening" (now zero such entries) to verified with a corrected page
range. Metadata corrections applied: seven, not six.
