# Research-gap assessment

Internal document. Answers the fourteen questions of Phase 0 §13 against the
verified literature. The manuscript has **not** been edited; the wording
recommendations below are proposals.

**Bibliography provenance note.** `references.bib` holds two groups: the
author's vetted baseline of 21 entries, and a later expansion of 30 (everything
below the line-190 marker). Every reference this assessment relies on to
*narrow* a novelty claim — `elnikety2016thoth`, `cohngordon2020delf`,
`mehta2017qapla`, `costa2026fides` — is a new addition verified in this pass.
Every reference it relies on to *support* a surviving claim was verified too;
see `verification_report.md`. The one claim-level risk sits in the expansion
group (`bailey2006secure`) and is flagged in the verdict table.

## 1. What is already well established

- **Retrieval-time permission enforcement in RAG.** Copy ACLs into the index and
  filter on them, or check live against IAM. Settled design space:
  `jeong2025permissionrag` (IEEE Access 2025), `chen2025integrating` (SAC '25),
  `zhong2026honeybee` (PACMMOD 2026).
- **Document-level security in enterprise/multi-user search**, including the
  observation that statistics computed over documents a user cannot read leak
  information about them: `buttcher2005security`, `bailey2006secure`,
  `zerr2009zerber`. This is twenty years old and the manuscript correctly
  identifies its own index finding as the RAG counterpart.
- **Complete mediation and authorization consistency.** `saltzer1975protection`;
  `pang2019zanzibar` names and solves the "new enemy" problem directly.
- **Dynamic information-flow control and taint tracking as a mechanism.**
  `myers1997decentralized`, `sabelfeld2003language`, `zeldovich2006making`,
  `krohn2007information`, `yip2009improving`, `enck2010taintdroid`.
- **Policy propagation through *derived* data in *retrieval* systems.**
  **Thoth** (USENIX Security '16) attaches declarative confidentiality policies
  to files, tuples and connections, tracks flows through an indexing/retrieval
  pipeline, and enforces them on derived data — prototyped on Apache Lucene.
  **Qapla** (USENIX Security '17) does the equivalent for database-backed
  systems without trusting the application.
- **Deletion must propagate to everything computed from the data.**
  `cao2015towards` argues it; **DELF** (USENIX Security '20) is a deployed,
  evaluated framework for exactly that across heterogeneous stores at Facebook
  scale, including annotation validation and the finding that developers get
  derived-data deletion wrong thousands of times.
- **IFC applied to LLM systems.** **FIDES** (NeurIPS 2026) gives a formal
  planner model with confidentiality *and* integrity labels for LLM agents, plus
  a security/utility taxonomy. A large arXiv body sits behind it.
- **Timing and cache side channels in LLM serving.** `kocher1996timing`,
  `felten2000timing`, `bortz2007exposing`, `ristenpart2009hey`,
  `gu2025auditing`, `song2025earlybird`, `wu2025know`, `weiss2024what`,
  `zhang2026keycollision`, `afiffy2026semanticcache`, and (non-journal)
  InputSnatch.
- **Privacy attacks on the RAG datastore.** `huang2023privacy`, `zeng2024good`,
  `qi2025follow`, `anderson2025my`, `liu2025mask`, surveyed by `bodea2026sok`
  and `wang2025unique`.
- **Deletion auditing in RAG specifically.** `tavakoli2026deletion` (SIGIR '26)
  audits whether RAG systems forget deleted material.

## 2. Methods commonly used

Retrieval-time ACL filtering (pre- or post-); materialised ACL copies in vector
metadata; per-user or per-role index partitions (`zhong2026honeybee`);
query-time authorization checks against a consistent store
(`pang2019zanzibar`); declarative policy labels propagated by a reference
monitor (Thoth, Qapla); annotation-driven deletion propagation (DELF);
label-tracking planners (FIDES); unlearning for parametric knowledge
(`bourtoule2021machine`).

## 3. Strongest / most relevant alternatives

Ranked by how much of this paper's defense they already cover:

1. **Thoth.** A reference monitor that propagates confidentiality policies
   through a retrieval system's derived data. If one asks "has anyone attached
   policies to derived artifacts in a search pipeline and enforced them at read
   time?", Thoth is the answer, and it is ten years old.
2. **DELF.** If one asks "has anyone treated removal as a consistency problem
   across every derived copy, and measured how often that goes wrong?", DELF is
   the answer, at production scale.
3. **FIDES.** If one asks "has anyone done IFC labelling for LLM pipelines?",
   FIDES is the answer, with a formal model this paper does not have.
4. **Zanzibar.** Already cited, and already a baseline preset in the code.
5. **`tavakoli2026deletion`.** The nearest RAG-specific measurement work.
6. **`zhong2026honeybee` / `jeong2025permissionrag`.** The deployment designs
   being measured; already baselines in the code.
7. **Backward-private dynamic SSE** (theme 7 of the thematic map). A separate
   cryptographic literature whose whole point is that deleted entries must stop
   leaking. Not a competing *system*, but an adjacent formalisation of the same
   intuition that the paper does not acknowledge at all.

## 4–5. Documented limitations, and which are relevant here

- IFC cannot stop a principal who legitimately read data from re-typing it.
  Already correctly handled as assumption A1 and tested by the paste-back
  experiment. Thoth and Qapla share the limitation.
- Policy/label completeness depends on every input being labelled. DELF's own
  result is that annotations are routinely incomplete in practice. This is
  assumption A2 and it is weaker than the paper's framing suggests: DELF is
  empirical evidence that "just label everything" fails at scale, which is a
  point *in favour* of the paper's lazy read-time check and worth citing as
  such.
- Over-tainting costs utility. Already measured by the collateral-cost
  experiment. Nothing in the literature gives a comparable number for RAG, so
  that measurement stands on its own.
- Side-channel AUCs are attacker-relative. Already stated in §Limitations.
- Thoth and Qapla report overhead on non-LLM workloads; their numbers are **not
  comparable** to the +360 ms figure here (different systems, different
  pipelines, no LLM call). Do not place them in the same table.

## 6–7. What the project attempts, and the evidence for it

Attempted: (a) attribute post-revocation leakage to individual derived
artifacts; (b) resolve its lifetime against the propagation policy; (c) measure
metadata existence inference in the same deployments; (d) show a read-time
transitive-taint defense closes both; (e) ablate which switches matter.

Evidence held: paired, seeded revocation events across presets with per-artifact
LM and right-censored lifetimes; twin-world existence experiment with
train/test tenant separation; leave-one-out ablation; utility and latency
measurement; a real-model check (Qwen2.5-3B, with 7B and a hosted model in the
extended track); a taint-invariant unit test; literature baselines implemented as
presets (`authz_postfilter`, `authz_prefilter`).

## 8. What remains unproven

- That absolute leakage values transfer off a synthetic, template-generated
  corpus. The Enron track is designed to address this; until it is reported, the
  numbers are testbed-internal.
- That "zero measured leakage" means zero. It means zero under an exact-match
  judge against this attacker set. The paper already says this; it must keep
  saying it in the abstract, not only in §Limitations.
- That the defense generalises past three artifact types. Logs, fine-tuning
  corpora, tool outputs and downstream indexes are untouched.
- That the proposed taint mechanism is better than an alternative provenance
  mechanism. No comparison was run. §Discussion already concedes this.
- That the latency cost is meaningful. 360 ms is one unsearched bucket
  parameter on one machine.
- That the timing AUCs survive real network jitter.

## 9. Which contributions are engineering/integration rather than methodological novelty

Stated plainly, because the audit changes the answer:

- **Provenance taint on derived artifacts is not novel.** Thoth did policy
  propagation through a retrieval system's derived data; DELF did removal
  propagation across derived stores; FIDES does label tracking for LLM
  pipelines. The *mechanism* is textbook dynamic IFC, which the related-work
  section already concedes ("We use the same mechanism").
- **Read-time (lazy) enforcement is not novel** — it is complete mediation, and
  the manuscript already attributes it to Saltzer & Schroeder.
- **ACL pre-filtering, uniform refusals, score banding and latency bucketing**
  are standard side-channel hygiene. Integration, not novelty.
- **The testbed, the preset matrix and the baseline presets** are engineering —
  valuable engineering, and the artifact is a genuine contribution, but not a
  methodological claim.
- **What *is* methodologically new**, as far as the search reached: the
  *measurement procedure*. Per-artifact attribution of leakage, lifetimes
  resolved against propagation policy with right-censored survival estimates,
  paired events across configurations, and existence inference measured in the
  *same* deployments as the revocation leakage. No peer-reviewed work found does
  this for RAG, or for any retrieval system.
- Also defensible as new: **the transitivity result for LLM-generated
  summaries.** A rolling summary has no document identifiers, so an
  identifier-based purge cannot touch it; the measured 0.634 → 0.634 result for
  the `legacy` preset is a concrete demonstration that the artifact type
  introduced by LLM applications breaks the identifier-based deletion approach
  DELF-style systems rely on. That is a specific, evidenced observation about
  *what is different* in the LLM setting, and it is the strongest novelty the
  evidence actually supports.

## 10. Narrowest defensible statement of the contribution

> We measure post-revocation leakage in a multi-tenant RAG pipeline, attributed
> to each derived artifact and resolved over time against the ACL propagation
> policy, and we measure metadata-based existence inference in the same
> deployments. We show that an identifier-based purge — the approach that works
> for derived artifacts with recoverable provenance — cannot reach an
> LLM-generated rolling summary, and that carrying a transitive source set and
> checking it at read time closes the measured channels in this testbed at
> unchanged answer quality and a bucket-sized latency cost. The enforcement
> mechanism is standard dynamic information-flow control, applied to a new class
> of derived artifact; the contribution is the measurement and the artifact-level
> attribution, not the mechanism.

## Verdict on the manuscript's current claims

| Current claim | Verdict | Recommended action |
|---|---|---|
| Revocation in RAG is a consistency problem across derived artifacts, not an access check | **Defensible, but not original as a thesis.** DELF makes precisely this argument for derived data, and `cao2015towards` makes it for computed data. | Keep the framing; add "this is the DELF/Cao–Yang argument, instantiated for RAG" and cite both. Stop implying the framing is new. |
| "A defense, provenance-tainted revocation, that attaches a transitive source set to every derived artifact" listed as contribution 3 | **Overclaimed as a contribution.** The mechanism is Thoth/Qapla/FIDES-class IFC. | Reword contribution 3 from a mechanism contribution to an *instantiation and evaluation* contribution: "an instantiation of read-time information-flow enforcement for the three derived artifacts of a RAG pipeline, including LLM-generated summaries, and its evaluation." |
| "To our knowledge, the combination of artifact-level attribution, propagation-policy lifetimes, transitive treatment of summaries, and an ablation of the mitigations is not covered by the works above" | **Survives the audit.** No peer-reviewed work found does this combination, for RAG or otherwise. | Keep, and keep the existing "We have not done an exhaustive survey and make no priority claim" disclaimer — it is doing real work. Strengthen by naming Thoth, DELF and FIDES as the nearest prior art *in the same paragraph*, so the claim is bounded by named work rather than by silence. |
| Related work §Information-flow control and provenance: "The contribution here is to apply it to the derived state of LLM applications" | **Needs correction.** FIDES already applies IFC to LLM application state, and Thoth already applied it to retrieval-system derived state. | Narrow to: "to the *persistent* derived state of a retrieval pipeline — cache entries, memory turns and rolling summaries — and to measure what happens without it." The word that carries the novelty is *measure*, and *persistent*. |
| Related work §Deletion and machine unlearning | **Incomplete.** Cites Cao & Yang, Bourtoule et al., Tavakoli & Sanderson, but not DELF — the one deployed system for derived-data deletion correctness. | Add DELF, and add the observation that DELF's annotation-incompleteness finding motivates read-time checking over eager purging. |
| Related work §Access control for search and retrieval | **Incomplete.** No mention of Thoth or Qapla, which enforce policy on derived data in retrieval and database systems. | Add both. Thoth in particular must appear before the defense is introduced, not after. |
| Abstract: "We propose provenance-tainted revocation" | **Reads as a mechanism claim.** | "We evaluate provenance-tainted revocation" or "We apply ... and evaluate". One word. |
| Positioning paragraph: no acknowledgement of the backward-privacy / revocable-encryption literature | **Gap in coverage, not an error.** | One sentence distinguishing it: that literature formalises what a server may learn about deleted entries under encryption; this paper measures what a plaintext application-layer pipeline actually discloses after a permission change. |

## Bottom line

The research gap is **narrower than the manuscript currently implies, and it
survives**. Nothing found in peer-reviewed literature measures post-revocation
leakage per derived artifact in RAG, resolves its lifetime against propagation
policy, or measures existence inference in the same deployment — and the summary
transitivity finding is a genuine, evidenced observation about what the LLM
setting breaks. But the *defense* is not a novel mechanism and should stop being
presented as one. Four references must be added for the paper to be honest about
its prior art: Thoth, DELF, Qapla and FIDES. The first two are the ones a
reviewer in this area will know, and their absence is currently the most
exposed part of the submission.
