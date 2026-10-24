# Afterimage — reviewer audit

22 Oct 2026 · Ayush Govindwar

As written, the paper would likely be rejected at a security or ML conference, mainly on methodology. Six issues could each sink it on their own, and four of them sit in the testbed rather than the text, so fixing them changes headline numbers (the 63%, the 0.992 AUC, "about half the leakage").

Audited: the LaTeX sources of 19 Oct, the code in `src/`, and the run logs in `results/` and `results-calc/`. The `main.pdf` in the folder is the 8 Oct build and no longer matches the sources; the external review you shared was written against that build, so some of its points are already fixed (see the cross-check below). Nothing was re-run; every claim below cites the file it came from.

## Summary and recommendation

**What the paper claims.** Multi-tenant RAG applications copy permissions and content into derived artifacts: ACLs in the vector index, semantic-cache entries, and chat memory with rolling summaries. Revoking access in the identity system does not revoke those copies, and response metadata (scores, reranker confidence, latency, refusal wording) reveals that a hidden document exists. In a testbed with paired revocation events, a 48-hour horizon and Kaplan–Meier lifetimes, a daily-crawl deployment still discloses 63% of a revoked document's secrets. Two published access-control patterns remove index leakage but leave about half. The proposed defense, provenance-tainted revocation with constant-shape responses, gives zero measured leakage with the stub and on Enron, 0.002 with Llama-3.1-8B, at a cost in in-session recall (0.454 → 0.334) and 306 ms median latency.

**Recommendation: reject in the current form** (weak reject at a top security venue). The question is real and the measurement design is above average, but four headline results come from testbed choices rather than from RAG systems (C1–C4), the leak judge has false positives (C5), and the defense is never compared with the simple alternative a reviewer will propose (C6).

**Confidence: high on C1–C6.** Each was verified in the code and run logs, not inferred from the text.

**What would change the verdict.** Fixing C1–C6 and adding one leak shown in an unmodified open-source stack (H4) would make this a credible measurement paper. The defense then stands or falls on beating permission-epoch invalidation on retained-document utility.

## Strengths

These are worth protecting in any rewrite.

- **A real, timely problem with a clean distinction.** Revocation differs from deletion: the document stays for other users, so derived copies must be filtered per principal rather than removed. The paper states this well.
- **Per-artifact attribution over time.** Paired events across configurations, right-censored lifetimes and per-artifact LM are, as far as the search reached, new for RAG. This measurement procedure is the paper's most defensible contribution.
- **A clean attacker boundary.** The attacker only ever receives the `Observation` an API client would see, and is trained and tested on disjoint tenants; TPR at 1% FPR is reported alongside AUC.
- **Ablations on both sides.** Switch-level presets make leave-one-out ablation possible for revocation and for existence inference.
- **The paper attacks its own assumption.** The paste-back laundering experiment tests A1 directly and reports that it breaks.
- **A non-obvious, practical finding.** A fast-refusal path raises existence AUC from 0.854 to 0.897 when latency is not padded.
- **Honest scope.** Limitations are stated plainly, and the stub is no longer described as a uniform lower bound.

## Issue register

Critical = a reviewer can reject on this alone. High = drives a major-revision or reject verdict together with the others.

| ID | Severity | Issue | Fix needs |
| --- | --- | --- | --- |
| C1 | Critical | "Leakage" re-serves text the victim already received; no new information is gained | Re-analysis, threat-model rewrite, one small experiment |
| C2 | Critical | Baseline and both literature baselines share a tenant-wide cache with no access check, so users who never had access get restricted answers | Code change, re-run baseline cells |
| C3 | Critical | Post-filter existence AUC 0.992 comes from exposing the scores of withheld documents | Code change, re-run |
| C4 | Critical | Summaries come from a regex extractor built to keep figures, not an LLM; the stub sets absolute LM | New real-model runs |
| C5 | Critical | The exact-match judge counts shared values as leaks; both "leaks under full" are judge errors | Re-analysis |
| C6 | Critical | No simple alternative defense; the "ID purge reduced nothing" evidence is confounded | New presets, re-run |
| H1 | High | CIs treat clustered events and probes as independent; seeds do not vary the corpus | Re-analysis |
| H2 | High | Several headline findings hold by construction | Writing, small re-runs |
| H3 | High | Corpus too small and regular; half the existence targets have no sibling | Re-analysis, corpus change |
| H4 | High | Presets and the offboarding threat are not grounded in real systems | Writing, one real-stack demo |
| H5 | High | Robustness runs underpowered; the colleague number is misreported | Re-run at scale |
| H6 | High | Collateral cost measured with a probe the stub fails even without the defense | Re-run, one design change |
| H7 | High | Related work is a list, misses six lines of work, has no comparison table | Writing |
| H8 | High | Journal format for a conference goal, stale PDF, text advertises unfinished work | Writing |
| H9 | High | Taint growth in long sessions and the real authorization cost are unmeasured | Re-analysis, one new experiment |

## Critical issues

### C1 — The leakage metric measures re-disclosure, not new disclosure

**Problem.** In every revocation event the victim asks about the target twice during warm-up and gets the answer. Documents average 51 words and the stub returns up to 4 of about 6 sentences, so the warm-up answer already holds most of the secrets (Project Drizzle: 4 of 5). The fresh-session probe then repeats the warm-up question word for word. LM counts secrets the victim already has.

**Why a reviewer rejects.** "The attacker learns nothing new; they can scroll up their own chat." That undercuts RQ1, RQ2 and the 63% headline.

**Evidence.** `experiments.py`, `run_revocation`: warm-up asks `qa[0]` and `qa[1]`; `fresh_q = qa[0]`. `analyze.py`, `collect_events` already records what was `told` at warm-up but never subtracts it from LM.

**Fix.**

1. Split the metric: LM_new (secrets disclosed after revocation that never appeared in a pre-revocation response to that user) and LM_re (re-disclosure). LM_new needs re-analysis only. Lead with LM_new and cross-user leakage; present re-disclosure as a complete-mediation violation.
2. Narrow the warm-up so unseen secrets exist: one fact per answer (cap the stub at one sentence; tell real models to give only the asked figure).
3. Add a post-revocation update: edit the target (new figure, new canary) after revoking. Whatever the stale index serves from the new version is genuine new information, and it is the real "new enemy" case.
4. In the threat model, state why re-disclosure still matters: answers that combine revoked content with other documents, spread to other users through shared state, retention and compliance duties. Cite each.

### C2 — The baseline gives restricted content to users who never had access

**Problem.** `baseline`, `authz_prefilter` and `authz_postfilter` all use `cache_scope="tenant"` with no lazy check. Any tenant member whose question matches a cached entry gets it, before any revocation. In the existence runs this is a content breach, scored as a weak "content channel".

**Evidence.** `results/rq3_existence/runs/preset=baseline-1e9129f7_s0.jsonl`: insider `t1_cyrus`, who has no access, asks "What is the list price of Project Drizzle?" and receives `t1_sven`'s cached answer with $51,200, 19.1%, $5,000 and April 13, 2027 (cache similarity 1.0). In that seed 45 of 150 direct insider probes in world 1 are cache hits. In `existence_eia.csv` the baseline outsider AUC is exactly 0.500 on every single channel; the insider reaches 0.714 combined, 0.717 on content. The paper pools both into 0.616 and calls it existence inference.

**Why a reviewer rejects.** RQ3 mislabels an authorization failure. The "published designs leave about half the leakage" result rests on a cross-user cache that neither permission-aware RAG nor Zanzibar prescribes, so both baselines read as straw men. "Baseline is what teams ship" is unsupported. The laundering experiment's colleague leak also travels through this shared cache (its config file says so), so T8 needs re-checking too.

**Fix.**

1. Give `baseline` and both `authz_*` presets a user-scoped cache, or key entries by user plus a hash of the permission set. Re-run `rq3_existence`, `rq_baselines_*` and the baseline cells of `rq5_leakage`.
2. Keep the tenant-shared cache as a separately named misconfiguration and report its cross-user leak as its own finding. It is real and fits the semantic-cache attack literature.
3. Report insider and outsider separately in every existence table.

### C3 — "Check-after-retrieve exposes existence at AUC 0.992" is an implementation artifact

**Problem.** With the ACL pre-filter off, the API's confidence and reranker confidence are the maximum over all relevant candidates, including documents the user may not see, and they are returned even on refusals. The attacker reads the hidden document's own score.

**Evidence.** `pipeline.py`, `_generate`: `ranked_set = authorized if m.acl_prefilter else relevant`, then `conf = max(...ranked_set)` and `rr = max(rr_scores)`.

**Why a reviewer rejects.** No cited system reports a confidence computed over documents it withholds. The 0.992, the 0.993 ablation cell and the "correct about content, transparent about existence" conclusion are produced by the testbed.

**Fix.**

1. In post-filter mode compute every exposed score over authorized chunks only. Re-run `rq_baselines_existence` and the post-filter half of `rq4_ablation_existence`.
2. Measure the residual channels post-filtering really has: fewer than k sources returned, rank displacement of authorized results, extra reranking latency, and collection statistics (the Büttcher and Clarke mechanism).
3. If you keep the current behaviour, cite a real API that exposes such a score and present it as that specific misconfiguration.

### C4 — Memory results come from a hand-written summarizer and a stub, not from LLMs

**Problem.** `session_memory.summarize()` is a regex extractor that keeps every sentence with a digit, a capitalised name pair or the word "codename". It is built to keep secrets, and it is used in every run, the Llama and Qwen runs included. So contribution 4 ("including LLM-generated summaries") and the Thoth distinction in Related Work ("an artifact produced by a generative model") do not describe the experiments. Separately, the stub returns up to 4 sentences of a ~6-sentence document, so absolute LM values (0.63, 0.49, 0.37) mostly reflect the stub's output length.

**Why a reviewer rejects.** The memory channel and the "transitive taint is load-bearing" result depend on a summarizer designed to preserve exactly what LM counts. Real models already disagree with the stub in direction (Qwen higher, Llama lower).

**Fix.**

1. In real-model runs, summarise with the same model (a ConversationSummaryMemory-style prompt) and report the share of secrets that survive summarisation.
2. Make real models the primary evidence for RQ1, RQ2 and the defense; keep the stub as a validation harness. Add one larger hosted model; `llm_client.py` already has gpt-4o-mini and Gemini Flash backends.
3. Lead with leak rate and lifetimes, which depend less on output length; report LM second.
4. Until then, drop "LLM-generated summaries" from the contributions and the Thoth paragraph (the wording is yours).

### C5 — The judge has false positives, and both "leaks under full" are judge errors

**Problem.** 129 of 619 restricted fact values (21%) appear verbatim in another document: "Dallas" in 11 documents, "0.58" in 3. `judge.disclosed()` only excludes values found in the current response's `source_docs`, so a value that arrives through memory or a document title counts as a leak.

**Evidence.**

- Llama under `full` (`results-calc/results/model_grid_8b`, seed 2, event 14, `t5_r014`): the response says "There is no mention of a 'Dallas expense policy' in the documents". "Dallas" was scored as the target's site to close.
- The stub under `full` also "leaks" in that grid (seed 3, event 7, `t4_r008`; LM 0.002, censored at 48 h). The answer is about Project Elm, which shares "hazard ratio 0.58" with the target.
- Table X reports stub/full as 0.000 (taken from the Qwen grid), and the text calls Llama "the only cell" that is non-zero. Your own artifact contradicts both.

**Why a reviewer rejects.** The paper argues an invariant holds by induction, then reports a violation it "did not isolate". A reviewer will doubt either the defense or the measurement.

**Fix** (re-analysis, no re-run).

1. Score only corpus-unique values plus the canary, or exclude any value present in a document the user can still read, or require the value to co-occur with its key or topic in one sentence.
2. Report a canary-only leak rate as a high-precision check.
3. Regenerate the corpus with unique fact values for future runs.
4. In the paper, explain both events as judge false positives and quote the responses.
5. Finish the 150 human labels already sampled in `judge_validation.csv` and report precision and recall for both judges.

### C6 — No simple alternative defense, and the transitive-taint evidence is confounded

**Problem.** The only alternative defense is `legacy`, whose summaries get an empty taint by construction. A reviewer will ask: why not bump a per-user permission epoch on any revocation and drop cache entries and memory turns stamped with an older epoch, checked at read time so lost webhooks are covered? That is about ten lines and also reaches zero.

**Confound.** "An identifier-based purge reduced leakage by nothing (0.634 vs 0.634)" compares totals, but `legacy` has no live ACL check, so its total is carried by the stale index (LM_index 0.634). Its memory leakage actually fell from 0.339 to 0.245 (`results/rq5_leakage/analysis/revocation_summary.csv`).

**Fix.**

1. Add two presets: epoch invalidation (cache and memory) and session flush on revocation. Run them through revocation, collateral and existence.
2. Make the claim the one taint can win: the same zero leakage with better retained-document utility than coarse invalidation. That comparison is the defense's contribution.
3. Remove the legacy-based "reduced nothing" sentences (Discussion, Conclusion, practical guidance) and cite the RQ4 ablation instead (0.337 without transitive taint).

## High issues

### H1 — Confidence intervals are too narrow

**Problem.** The corpus is fixed (seed 20261006); seeds only change event sampling. Each cell's 250 events are draws with replacement from 150 restricted documents, about 122 distinct targets, and the same documents recur across seeds. The 4800 existence test probes are 60 test targets × 5 seeds × 16 probes, yet `metrics.auc_ci` resamples probes as if independent. The "seed-clustered" interval has only 5 clusters. No correction across roughly 50 reported tests.

**Fix.** Cluster-bootstrap by target document for revocation and by target for existence (Obuchowski's clustered AUC); report target-level AUC as primary. Regenerate the corpus per seed so seeds are real replicates. Apply Holm to the reported family, or drop p-values for differences that are deterministic (zero against non-zero).

### H2 — Findings that hold by construction are presented as findings

- Index lifetime = Δ/2 and cache lifetime = TTL are simulator checks (the text already concedes the first).
- "Memory never heals": `session_memory.py` has no session expiry or retention at all.
- Full-defense existence at chance: with the pre-filter on, the target is invisible in both worlds (your own `CLAUDE.md` says so).
- Cache leakage in RQ1 and RQ5: the fresh-session probe repeats the warm-up question verbatim (cosine 1.0), so it hits at any threshold.
- Threshold sweep: LM against threshold is a step function of 7 hand-written templates assigned by `ev % 7`.

**Fix.** Move Δ/2 and TTL into one paragraph of simulator validation. Model memory retention (sweep session lifetime: 1 h, 24 h, 7 d, none) and report leak lifetime as a function of it. Say which RQ3 cells are structural and which carry an empirical signal. Turn on `probe_paraphrase` everywhere and draw rewordings from a natural source (model-generated user rephrasings or a paraphrase dataset) instead of 7 templates.

### H3 — The corpus is too small and regular for the claims

**Problem.** 8 restricted templates, 51 words per document on average, one chunk per document. 76 of 113 projects are singletons, covering 51% of restricted targets, so in world 0 nothing about the project exists and the "hard negatives" claim is false for half the targets. Held-out tenants share templates with training tenants. Enron has no canaries, and its Llama run has 24 events.

**Fix.** Stratify RQ3 by singleton against sibling targets (re-analysis). Give every target a sibling or a same-template decoy. Use multi-chunk documents (hundreds to thousands of words) so one revocation spans many chunks. Vary templates between training and test tenants. Scale the Enron track with a real model.

### H4 — The deployment model is not grounded in real systems

**Problem.** "Baseline is what teams actually ship", the daily crawl (justified only by a config comment, "as M365 connectors did until 2026"), the tenant-wide cache and summary memory are all asserted. Offboarding assumes a deprovisioned user can still query; with SSO their session normally ends.

**Fix.**

1. Add a table that grounds each preset parameter in the documentation of real frameworks and products, with citations: LangChain and LlamaIndex memory, GPTCache and Redis semantic-cache scoping, Chroma, Pinecone and Qdrant metadata filters, Azure AI Search security trimming, Microsoft Graph connector crawl schedules, Glean permission sync.
2. Replace offboarding with a "mover" (department transfer), or justify it with documented session and token lifetimes after deprovisioning.
3. Show one leak end-to-end in an unmodified open-source stack (for example LangChain + Chroma + a semantic cache). This is the strongest external-validity evidence you can add.

### H5 — Robustness runs are underpowered, and one number is misreported

**Problem.** Laundering has 40 events over 2 seeds, collateral with Llama 16, Enron with Llama 24, and Qwen existence 3 seeds. The colleague result is LM_colleague 0.013 [0.000, 0.037]: across 40 events that is about half of one document's secrets in total, so one or two events. The abstract, discussion and conclusion still say it "reaches a colleague … in 1.3% of events", but 0.013 is a mean fraction of secrets, not an event rate (`analyze.py`, line 252). Table X also pairs Llama against the stub arm of the Qwen grid (0.646) instead of its own grid's stub arm (0.648, with full at 0.002).

**Fix.** Run at least 200 events per real-model cell, sized by a power calculation for the effects you claim. Report event rate and LM as separate columns. Take paired arms from the same grid, and regenerate every table from one analysis version.

### H6 — The collateral cost is measured with a probe the stub fails anyway

**Problem.** Under `baseline`, with no defense at all, same-session recall on retained documents is only 0.454 and refusals are 0.283; with Llama the same baseline is 0.944. The stub's unit picker mishandles "Remind me what you told me earlier about X and its figures", so 0.454 → 0.334 is measured on a broken ruler. The paper then calls separating utility from leakage a problem it "does not know how to solve", which reads as giving up on the defense's main weakness.

**Fix.**

1. Make the real-model collateral run primary, at scale.
2. Reduce over-tainting instead of conceding it. The summarizer is extractive, so per-sentence taint is easy: each kept sentence carries its own turn's taint, and the lazy check drops only tainted sentences.
3. Compare against coarse invalidation (C6): taint should keep more retained recall. Cite permissive information-flow analysis and context attribution as the general route.

### H8 — Venue, format and manuscript state

**Problem.**

- `main.tex` uses the IEEE Access class, a journal, but the goal is a conference. The proof build is 38 single-column pages; conference limits are usually about 12–13 two-column pages plus appendix.
- `main.pdf` is the 8 Oct build and disagrees with the sources (old abstract with +360 ms and "zero in all 750 events", about 21 references, 7 threats).
- The text advertises unfinished work: labels "never completed", models "configured but not run", a leak whose cause "we did not isolate", an explanation "we did not test", problems the work "does not know how to solve".
- Locally, `rq1_surfaces`, `rq4_ablation_revocation`, `rq5_collateral` and `rq_baselines_revocation` have partial runs and no analysis, and the stress and overhead results are absent. The availability statement promises them in the repository.

**Fix.** Pick the venue and cut to its limit: threat model, RQ1–RQ3, and the defense against simple alternatives in the main paper; robustness in an appendix. Delete every mention of unrun configurations, and either finish an item or drop its sentence. Rebuild the PDF from current sources. Check the public repository holds every analysis directory the paper cites.

### H9 — Taint growth in long sessions and the real cost of read-time checks are unmeasured

**Problem.**

- **Sessions are short.** The revocation warm-up is 6–8 questions. The utility workload asks every question in its own fresh session (`run_utility`: sessions `u{i}-a` and `u{i}-b`), so the 0.047 over-refusal is measured where memory and taint never apply. A summary's taint is the union of every turn it condenses, and the lazy check drops the whole summary if the user loses any one of those documents. In a 50–100-turn session, one revocation could wipe most of the context. Nothing measures taint-set size or how much context a revocation discards as sessions grow.
- **The cost model undercounts.** `SemanticCache.get` runs `holds_all` on every cache entry in scope at every lookup, and `holds_all` checks every document in that entry's taint. That is (entries × taint size) authorization decisions per query, billed as one batched IAM call in `_authz`. The overhead run (300 documents, a small cache) cannot show how this scales.
- **One chunk per document** keeps taint sets and IAM lookups artificially small.

**Why a reviewer rejects.** The defense's two costs, utility and authorization load, grow with exactly the variables the testbed holds small.

**Fix.**

1. Report the distribution of taint-set sizes from existing logs; `response_taint` is logged per query (re-analysis).
2. Add a long-session experiment: 50–100 turns over many documents, revoke one, and measure retained recall, refusals and summary loss for `full`, per-sentence taint (H6) and epoch invalidation (C6).
3. Count authorization decisions per query, not calls, and sweep cache size (10² to 10⁵ entries) and query rate. Index cache entries by source document so a lookup checks only the candidates above the similarity threshold.
4. Use multi-turn sessions in the utility workload so over-refusal reflects memory.

## H7 — Literature review

The current related work (57 references) is broader than the 8 Oct build but still reads as a list: most sentences say what a paper does, few say how it differs on a dimension that matters here. Six relevant lines of work are missing, and a security reviewer will name several of them. There is also no comparison table, which is the first thing a reviewer looks for when judging novelty.

**How to restructure it.**

1. Organise around the paper's three claims, not by topic: (a) derived state outlives authorization changes, (b) response metadata reveals hidden documents, (c) provenance-based read-time enforcement. End each subsection with one sentence on what this paper does that the cited work does not.
2. Add a comparison table. Rows: Thoth, Qapla, DELF, FIDES, CaMeL, HoneyBee, permission-aware RAG, Zanzibar, Tavakoli and Sanderson, MEXTRA. Columns: covers index / cache / memory; revocation or deletion; per-principal; handles generated artifacts; measures lifetimes; mechanism or measurement.
3. Replace "We have not done an exhaustive survey and make no priority claim" with one sentence on the search protocol (databases, query terms, date range); `literature_review/search_log.md` already has it. The novelty sentence itself is your call.
4. Cut the textbook IFC list (HiStar, Flume, RESIN, TaintDroid) to one sentence and spend the space on 2023–2026 LLM work.

**What to add.** Verify each venue against the publisher record before citing; several are recent preprints.

| Line of work | Papers to add | Why a reviewer expects it |
| --- | --- | --- |
| Chat and agent memory, and its privacy | Packer et al., MemGPT (2023); Park et al., Generative Agents (UIST 2023); Zhong et al., MemoryBank (AAAI 2024); Wang et al., Recursively Summarizing Enables Long-Term Dialogue Memory (2023); Wang et al., Unveiling Privacy Risks in LLM Agent Memory (MEXTRA, ACL 2025) | Memory is one of your three artifacts; the paper cites no memory architecture and no memory attack |
| IFC and taint for LLM systems | Debenedetti et al., CaMeL (2025); Wu et al., f-secure, an IFC view of prompt-injection defense (2024); Wu et al., IsolateGPT (NDSS 2025); Zhong et al., RTBAS (2025); Siddiqui et al., Permissive Information-Flow Analysis for LLMs (2024); Tiwari et al., IFC in ML through Modular Model Architecture (USENIX Security 2024); Jayaraman et al., Permissioned LLMs (2025); Bagdasarian et al., AirGapAgent (CCS 2024) | FIDES alone undersells how crowded this is; permissive IFA targets exactly your over-tainting cost (H6) |
| Authorization caching and revocation measurement | Crampton, Leung and Beznosov, SAAM (SACMAT 2006); Wei, Ripeanu and Beznosov, cooperative secondary authorization recycling (TPDS 2009); Redell and Fabry, Selective Revocation of Capabilities (1974); Liu et al., An End-to-End Measurement of Certificate Revocation in the Web's PKI (IMC 2015) | Stale cached authorization is an old problem; the IMC paper is the methodological template for measuring revocation windows |
| Derived data, deletion and access control in data systems | Garg, Goldwasser and Vasudevan, Formalizing Data Deletion and the Right to Be Forgotten (EUROCRYPT 2020); Albab et al., K9db (OSDI 2023); Tsai et al., Edna (SOSP 2023); Shastri et al., GDPR and database systems (VLDB 2020); Park, Nguyen and Sandhu, Provenance-Based Access Control (PST 2012); Rizvi et al., query rewriting for fine-grained access control (SIGMOD 2004); Gupta and Mumick, materialized view maintenance (1995); Bost, Minaud and Ohrimenko, backward-private SSE (CCS 2017) | The index ACL copy is a materialized view; PBAC is the named model for your defense; Garg et al. give the formal definition reviewers will ask for |
| Semantic caches and search side channels | Bang, GPTCache (NLP-OSS 2023); Gill et al., MeanCache (2024); Zheng et al., InputSnatch (2024); Carlini and Nasr, Remote Timing Attacks on Efficient LM Inference (2024); Gelernter and Herzberg, Cross-Site Search Attacks (CCS 2015); Chen et al., Side-Channel Leaks in Web Applications (S&P 2010) | The cache systems you model, and the closest prior timing and existence attacks |
| RAG privacy attacks and defenses not yet cited | Li et al., Generating Is Believing (S²MIA, 2024); Naseh et al., Riddle Me This! (2025); Di Maio et al., Pirates of the RAG (2024); Morris et al., Text Embeddings Reveal (Almost) As Much As Text (EMNLP 2023); Koga et al., DP-RAG (2024); Zeng et al., SAGE synthetic-data RAG (2024); Wang et al., When Machine Unlearning Meets RAG (2024); Cohen-Wang et al., ContextCite (NeurIPS 2024) | Existence inference must be placed against current RAG membership inference; ContextCite is the obvious route to finer taint |

Two methods citations also belong in the paper: Obuchowski, nonparametric analysis of clustered ROC data (Biometrics 1997) for H1, and product documentation for the H4 grounding table.

## Questions for the authors

These are the rebuttal questions a reviewer would send. Have an answer, backed by a number, for each one before submitting.

1. What does a revoked user learn after revocation that they had not already been shown before it? (C1)
2. Which production system shares cached answers between users with different permissions, as `baseline` does? (C2)
3. Which real API returns a confidence score computed over documents it withholds? (C3)
4. Were summaries ever written by the LLM, and how many secrets survive a model-written summary? (C4)
5. What caused the two non-zero events under `full`? (C5)
6. How does the defense compare with a per-user permission epoch that invalidates cache and memory on any revocation? (C6)
7. With intervals clustered by target document, which of the reported differences remain significant? (H1)
8. How large do taint sets get in 50–100-turn sessions, and what share of context does one revocation discard? (H9)
9. How many authorization decisions does the lazy cache check make per query as the cache grows? (H9)
10. Does the colleague leak in the laundering experiment survive a user-scoped cache? (C2, H5)

## Cross-check against the external review

The review you shared read the 8 Oct `main.pdf` (+360 ms, one 3B model, no Zanzibar or IFC). Against the 19 Oct sources, three of its points are already fixed, two of its "best findings" do not hold up, and two of its concerns were new to this audit and are now H9.

| Their point | Status in the 19 Oct sources | Verdict |
| --- | --- | --- |
| Defense is close to true by construction | Still open; collateral and laundering runs only partly answer it | Agree. C6 gives the comparison that turns it into a result |
| Taint sets grow in long sessions; over-refusal 0.047 because sessions are ~6 turns | Open | Agree, and worse: over-refusal is measured on one-question sessions, so it cannot show over-tainting at all. Now H9 |
| Cost of a live IAM check at production query rates | Partly addressed (simulated 0/2/10 ms round trip) | Agree. The cost model counts one call where the code makes entries × taint decisions. Now H9 |
| One chunk per document makes taint trivially precise | Open | Agree; H3 and H9 |
| Synthetic corpus, stub generator, only a 3B model | Partly addressed: Enron track and Llama-3.1-8B added | Still the main external-validity gap; C4, H3, H5 |
| Real model doubled memory leakage, so the stub understates | Superseded: Llama-3.1-8B leaks less than the stub overall | The paper already says direction is model-dependent; no action |
| Δ/2 and TTL lifetimes are true by definition | Conceded in the text | Agree, and two more are structural: "memory never heals" and pre-filter existence at chance (H2) |
| Baseline is your own construction; audit real frameworks | Open | Agree; the single most valuable addition (H4). The baseline also leaks across users (C2) |
| Exact-match judge is only a lower bound; add an LLM judge | Partly addressed: qwen2.5:7b judge on Llama runs, recall unmeasured | Not even a clean lower bound: it also has false positives (C5) |
| Existence attacker is narrow; padding makes timing chance by construction | Conceded in Limitations | Agree; H2 and minor issues |
| Related work misses Zanzibar, IFC (DLM, Flume, HiStar) and provenance | Fixed: all cited since 14 Oct | Done. The remaining gaps are different (H7) |
| Code, corpus generator and logs not released | Sources name the GitHub repo; raw logs "on request" | Confirm the repo is public and holds every cited analysis directory; deposit the logs with a DOI (H8) |
| Strength: ID-based purges fail because summaries carry no IDs | Claimed in Discussion and Conclusion | Evidence is confounded by the stale index (C6). Cite the RQ4 ablation instead |
| Strength: chat memory never heals | Claimed throughout | True by construction: no session expiry exists (H2) |
| Strength: fast refusal raises inference leakage | Supported | Holds, but only with a post-filter and no padding (0.854 → 0.897) |

## Order of work

Do the re-analysis first: it is cheap and it decides what the re-runs have to show. C2, C3 and C6 will move the abstract's numbers, so rewrite the abstract last.

1. **Re-analysis of existing logs, no runs.** C5 judge fix and the two false-positive events; C1 split into LM_new and LM_re; H1 clustered intervals; H3 RQ3 split by singleton and sibling targets; H5 colleague wording and Table X pairing.
2. **Code change, then re-run the stub cells.** C2 user-scoped cache for `baseline` and `authz_*`; C3 post-filter scores over authorized chunks; C6 epoch-invalidation and session-flush presets; H2 paraphrased probes everywhere and a memory-retention sweep.
3. **New real-model runs.** C4 model-written summaries with real models as primary evidence, plus one hosted model; H5 at least 200 events per cell; H6 collateral with a real model and per-sentence taint; H9 long sessions and an authorization-cost sweep.
4. **Writing.** H4 grounding table and one real-stack demonstration; H7 related-work rewrite and comparison table; H8 cut to the venue's limit, remove unfinished-work admissions, rebuild the PDF.

## Minor issues

Not reject-worthy alone; fix them while the sections are open.

- `analyze.surface_of` labels any leak that is not a cache hit or a stale-index doc as memory, by elimination. The "Dallas" false positive was labelled memory.
- LM is the union over about 24 probes per event; add a per-probe leak probability.
- The utility experiment contains no revocations, so identical answer quality across presets says nothing about the defense. State that.
- Stub latency is a formula (0.35 s + 0.015 s per output token, times log-normal noise); stub timing results describe that formula.
- The attacker is gradient boosting on 2–3 features per channel with 4 fixed probes; no adaptive or repeated-probing attacker. "Chance" holds for this attacker only.
- The security argument is informal. A short formal statement of the invariant over the write rules would help at a security venue.
- "Remind me what you told me earlier about X and its figures" is a leading probe; add natural follow-up questions.
- Figures 3 and 4 are older PNGs not regenerated from current results.
- The abstract carries about 20 numbers; keep four or five.
