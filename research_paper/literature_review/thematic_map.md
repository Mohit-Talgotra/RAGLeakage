# Thematic literature map

Eight themes. For each: the foundational work, the recent work, where the
approaches genuinely differ, what is agreed, what is disputed, and the
connection to this project. Keys in backticks are existing `references.bib`
entries; **bold** names are newly verified additions.

---

## Theme 1 — Access control for search and retrieval

**Foundational.** `buttcher2005security` (FAST '05) — in multi-user full-text
search, ranking statistics computed over unreadable documents leak information
about them. `bailey2006secure` (CIKM '06, poster) — index-copied permissions vs.
query-time result checking. `zerr2009zerber` (EDBT '09) — top-*k* from a
confidential index. `sandhu1996rbac` — the RBAC model everything implements.

**Recent.** `jeong2025permissionrag` (IEEE Access 2025) — IAM-derived permission
filtering across resource types. `chen2025integrating` (SAC '25) — access
control for patient profiles in RAG. `zhong2026honeybee` (PACMMOD 2026) —
dynamic partitioning so RBAC filtering on a vector DB is efficient.

**Methodological split.** Pre-filter (trim candidates before scoring) vs.
post-filter (score then drop). Materialised ACL copy vs. live check. Both axes
are implemented as switches in this project, which is why its baselines are
faithful.

**Agreed.** Permissions must be enforced at retrieval. **Disputed / unexamined.**
Nothing in this theme examines artifacts produced *before* a permission changed,
which is this project's question. Büttcher & Clarke is the closest ancestor to
the score-channel results.

**Connection.** `authz_prefilter` and `authz_postfilter` presets model this
theme; `baseline` models the materialised-copy designs.

---

## Theme 2 — Authorization consistency and revocation

**Foundational.** `saltzer1975protection` — complete mediation: every access
checked against *current* authority. **Qapla** (USENIX Sec '17) — enforce
row/column policy at the database adapter without trusting the application.

**Recent.** `pang2019zanzibar` — the "new enemy" problem and consistency tokens.

**Agreed.** Stale authorization state is a correctness bug, not a performance
tuning parameter. **Disputed.** How much consistency to pay for; Zanzibar's
answer is tokens, Qapla's is pushing enforcement below the app.

**Connection.** Assumption A4 depends on Zanzibar-style consistent reads. Qapla
belongs in the manuscript because it is the strongest statement of "do not trust
the application to filter", which is also this paper's conclusion for caches
and memory.

---

## Theme 3 — Information-flow control, provenance, and policy on derived data

**Foundational.** `myers1997decentralized`, `sabelfeld2003language`,
`zeldovich2006making`, `krohn2007information`, `yip2009improving`,
`enck2010taintdroid`. Provenance: `buneman2001why`, `simmhan2005survey`.

**The key prior art this project is missing.** **Thoth** (USENIX Sec '16) —
declarative confidentiality/integrity policies on files, tuples and connections,
flow-tracked and enforced on derived data inside a *data retrieval system*,
prototyped on Apache Lucene. This is a policy-on-derived-artifacts reference
monitor for a search pipeline, which is structurally what the proposed defense
is.

**Recent.** **FIDES** (NeurIPS 2026) — confidentiality and integrity labels in
an LLM agent planner, with a formal model and a security/utility taxonomy.
Behind it sits a large arXiv body (APPA, AgentFlow, Ghost in the Agent,
AgentFlow-style policy languages) which confirms the space is active and
crowded.

**Methodological split that matters.** Thoth and FIDES label *at the boundary*
and propagate statically or through a planner. This project propagates at
*generation* time through the union of context taints, including through
LLM-produced summaries where no identifier survives. That is the real
distinction, and it is narrow — it should be stated as narrow.

**Shared limitation, agreed by everyone.** A principal who legitimately read
data can re-type it; content-agnostic tracking cannot follow that. A1.

**Connection.** This theme is where the manuscript's novelty claim is weakest
and must be rewritten.

---

## Theme 4 — Deletion, unlearning and removal propagation

**Foundational.** `cao2015towards` — a system must forget data together with
everything computed from it, and track lineage to do so.

**Deployed and evaluated.** **DELF** (USENIX Sec '20) — annotation-driven,
asynchronous, temporarily reversible deletion across heterogeneous stores at
Facebook, with static and dynamic validation of the annotations. Its headline
empirical result — thousands of omissions and dozens of mistakes found in
production — is direct evidence that eager, annotation-complete purging is hard,
which argues *for* read-time checking.

**Recent.** `bourtoule2021machine` — efficient unlearning for trained models.
`tavakoli2026deletion` (SIGIR '26) — auditing whether RAG forgets deleted
material. *Conditional:* "When Machine Unlearning Meets RAG" (IEEE 2026, venue
unresolved) — the closest adjacent framing.

**Where this project genuinely differs, and it should say so in one sentence.**
Deletion removes the document for everyone; revocation removes it for one
principal while others keep it. So derived copies cannot be deleted — they must
be *filtered per principal*. The manuscript already makes this point; it is
sound and it is the cleanest separation from the whole theme.

---

## Theme 5 — Caches, timing and multi-tenant side channels

**Foundational.** `kocher1996timing`; `felten2000timing`; `bortz2007exposing`;
`ristenpart2009hey`.

**Recent, LLM-specific.** `gu2025auditing` (ICML '25, PMLR v267) — prompt-cache
timing is detectable across real APIs. `song2025earlybird` (TIFS, early access)
— serving-optimisation timing channels. `wu2025know` (NDSS '25) — shared KV
cache leaks prompts across tenants. `weiss2024what` (USENIX Sec '24) — token
length leaks encrypted responses. `zhang2026keycollision` (ICML '26) — semantic
cache key collisions. `afiffy2026semanticcache` (Sci Rep 2026) — adversarial
resilience of semantic caching. *Non-journal, optional:* InputSnatch (APPT
2026) — cache-sharing timing channel in LLM services.

**Agreed.** Any optimisation that shortens one code path creates an oracle. The
manuscript's fast-refusal finding is an instance, and it says so.

**Disputed / unresolved in the literature.** Whether padding is a sufficient
defense. This paper's own bucket-count residual (AUC 0.508 with Qwen) is an
honest negative result in that direction and is worth keeping prominent.

**Connection.** T6, T7, and the padding component of the defense.

---

## Theme 6 — Privacy attacks on RAG and LLMs

**Foundational.** `shokri2017membership`, `carlini2022mia` (and its low-FPR
argument, which this paper correctly adopts), `carlini2019secret` (canaries),
`carlini2021extracting`.

**RAG-specific.** `huang2023privacy`, `zeng2024good`, `qi2025follow` (ICLR '25),
`anderson2025my` (ICISSP '25), `liu2025mask` (WWW '25). Surveys:
`bodea2026sok` (SaTML '26), `wang2025unique` (CSUR 2025).

**Methodological distinction to state explicitly.** These attacks ask whether a
record is *in the collection* and assume the attacker queries the system
normally. This paper's existence attacker asks the same question but is
constrained to *metadata of a system that already refuses it content* — and its
revocation attacker is a former authorised user, which is a different principal
entirely. The manuscript makes this distinction; it is correct and it is the
right place to anchor RQ3's framing, since RQ3's individual channels are all
previously known types.

**Out of scope, correctly.** Integrity attacks: `greshake2023not`,
`liu2024formalizing`, `zou2025poisonedrag`, `zhang2025traceback`.

---

## Theme 7 — Encrypted search and cryptographic revocation (adjacent; currently unacknowledged)

**What it is.** Backward privacy in dynamic searchable symmetric encryption
formalises exactly how much a server may learn about *deleted* entries — Bost
et al.'s forward/backward private constructions, and the follow-on journal
literature. Revocable attribute-based encryption formalises how long a revoked
principal can still decrypt (JCS, PLOS ONE, Science China Information Sciences,
FGCS all carry work here).

**Why it matters here.** It is the same intuition — removal must stop leaking —
formalised in a different trust model. A reviewer from the security side may ask
why it is absent.

**Why it is not a competing method.** It assumes the server is the adversary and
the data is encrypted. This paper's adversary is a *client* of a plaintext
application, and the leak carrier is an application-layer derived artifact, not a
ciphertext or a search index entry.

**Recommendation.** One sentence in §Positioning distinguishing the trust
models. Do not build out a sub-section; it would be padding.

---

## Theme 8 — Measurement methodology

**Foundational.** `kaplan1958nonparametric` (right-censored lifetimes),
`friedman2001gradient` (the attacker model), `carlini2022mia` (low-FPR
operating points), `reimers2019sbert` and `wang2020minilm` (the encoders).

**Agreed practice.** Paired comparisons, bootstrap CIs, train/test separation
for learned attackers, reporting TPR at low FPR rather than only AUC. The
manuscript follows all of this, including seed-clustered intervals and a Wilcoxon
test, which is above the norm for the venue.

**Gap in the literature, not in the paper.** There is no established protocol for
measuring leakage *lifetime* in an application pipeline. Survival analysis is
used for vulnerability remediation times (Farris et al.), not for this. That
absence is precisely what makes the measurement procedure the paper's real
contribution — and also means there is no external protocol to compare against,
which the limitations section should say.

---

## Themes with adequate coverage after this pass

1, 2, 4, 5, 6, 8 — adequate once Thoth, DELF and Qapla are added.
3 — adequate once FIDES is added and the novelty wording is narrowed.
7 — one distinguishing sentence is sufficient; no further searching needed.

## Themes that would need more searching if the paper's scope grew

- Semantic leak judging / LLM-as-judge validity, if the paraphrase judge becomes
  a headline result rather than a robustness check.
- Real enterprise corpora and ACL realism, if the Enron track becomes the main
  evidence rather than a check.
Neither is needed for the current scope.
