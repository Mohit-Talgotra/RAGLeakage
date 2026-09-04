#!/usr/bin/env python3
"""
run_demo.py -- RAG Leakage MVP: single-run proof-of-concept.

Runs Steps 2-7 from the design spec in sequence:

  Step 2  -- U (alice) queries D with valid access               -> baseline response
  Step 3  -- revoke(alice, D)  [RBAC only -- nothing else flushed]
  Step 4  -- Alice re-probes, same session, exact same query     -> cache leak?
  Step 5  -- Alice re-probes, new session, paraphrased query     -> cross-session cache leak?
  Step 6  -- Attacker (bob) queries D's topic, exact phrasing    -> content/cache leak?
  Step 7  -- Bob queries a completely non-existent topic          -> true-negative baseline
  Step 8  -- Side-channel comparison: Step 6 vs Step 7

Evidence is written to results/run_log.csv.
"""

import sys
from pathlib import Path

# Allow running as `python run_demo.py` from the repo root
sys.path.insert(0, str(Path(__file__).parent))

# Load .env before importing anything that reads env vars (e.g. LLMClient).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; user can export OPENAI_API_KEY manually

import config
from sentence_transformers import SentenceTransformer
from src.naive_pipeline.corpus_loader import load_corpus
from src.naive_pipeline.rbac import AccessControlStore
from src.naive_pipeline.vector_index import VectorIndex
from src.naive_pipeline.semantic_cache import SemanticCache
from src.naive_pipeline.memory import SessionMemory
from src.naive_pipeline.llm_client import LLMClient
from src.naive_pipeline.rag_pipeline import NaiveRAGPipeline, QueryResult
from src.naive_pipeline.logger import QueryLogger

# ---- Roles ------------------------------------------------------------------
LEGIT_USER = "alice"   # tenant_alpha; starts with full access, revoked mid-run
ATTACKER   = "bob"     # tenant_beta; never had access to D in any session

SESSION_ALICE_1 = "alice-session-1"   # pre- and immediately post-revocation
SESSION_ALICE_2 = "alice-session-2"   # fresh session, cache still warm
SESSION_BOB     = "bob-session-1"

TARGET_DOC = "doc_A6"  # D -- the sensitive Project Nightingale document

# ---- Queries ----------------------------------------------------------------
# Q_PRIMARY: used by Alice in Step 2 and by Bob in Step 6.
# Exact same phrasing -> guaranteed cache hit from Alice's session.
Q_PRIMARY    = "What are the details of Project Nightingale and its clinical trial findings?"
# Q_PARAPHRASE: different surface form but same semantic intent.
# Used in Step 5 to test whether cache catches paraphrases.
Q_PARAPHRASE = "Can you summarise the Nightingale project outcomes and trial results?"
# Q_GHOST: topic that genuinely does not exist anywhere in the corpus.
# Used in Step 7 as the true-negative baseline for the side-channel comparison.
Q_GHOST      = "What is Meridian Corp's partnership with the Andromeda Mining Consortium?"


# =============================================================================
def setup() -> tuple[AccessControlStore, NaiveRAGPipeline, QueryLogger]:
# =============================================================================
    print("\n" + "=" * 68)
    print("  RAG LEAKAGE MVP -- NAIVE PIPELINE PROOF-OF-CONCEPT")
    print("=" * 68)

    # -- Corpus ---------------------------------------------------------------
    print("\n[Setup] Loading corpus ...")
    docs = load_corpus(config.CORPUS_DIR)
    doc_meta = {
        d["doc_id"]: {"restricted": d["restricted"], "tenant_id": d["tenant_id"]}
        for d in docs
    }
    tenant_ids = sorted({d["tenant_id"] for d in docs})
    print(f"[Setup] {len(docs)} documents across {len(tenant_ids)} tenants: {tenant_ids}")
    for d in docs:
        tag = "RESTRICTED" if d["restricted"] else "public   "
        print(f"         [{tag}] {d['tenant_id']}/{d['doc_id']} -- {d['title']}")

    # -- RBAC -----------------------------------------------------------------
    rbac = AccessControlStore()
    alpha_docs       = [d["doc_id"] for d in docs if d["tenant_id"] == "tenant_alpha"]
    beta_public_docs = [d["doc_id"] for d in docs
                        if d["tenant_id"] == "tenant_beta" and not d["restricted"]]

    for doc_id in alpha_docs:
        rbac.grant(LEGIT_USER, doc_id)
    for doc_id in beta_public_docs:
        rbac.grant(ATTACKER, doc_id)

    print(f"\n[Setup] RBAC: {LEGIT_USER} -> {sorted(alpha_docs)}")
    print(f"        (ALL alpha docs, incl. D={TARGET_DOC})")
    print(f"[Setup] RBAC: {ATTACKER} -> {sorted(beta_public_docs)}")
    print(f"        (beta-public only; D={TARGET_DOC} NEVER granted)")

    # -- Embedding model (shared instance) ------------------------------------
    print(f"\n[Setup] Loading embedding model '{config.EMBEDDING_MODEL}' ...")
    embedder = SentenceTransformer(config.EMBEDDING_MODEL)

    # -- Vector index ---------------------------------------------------------
    print("[Setup] Building vector index (first run encodes all docs) ...")
    index = VectorIndex(str(config.CHROMA_DIR), embedder)
    index.add_documents(docs)
    print(f"[Setup] Vector index ready -- {index.count()} documents indexed "
          "(flat, no tenant isolation)")

    # -- Pipeline components --------------------------------------------------
    cache  = SemanticCache(ttl_seconds=config.CACHE_TTL_SECONDS,
                           sim_threshold=config.CACHE_SIM_THRESHOLD)
    memory = SessionMemory(max_turns=config.MEMORY_MAX_TURNS)
    llm    = LLMClient(model=config.LLM_MODEL, temperature=config.LLM_TEMPERATURE)
    logger = QueryLogger()

    pipeline = NaiveRAGPipeline(
        rbac=rbac,
        vector_index=index,
        cache=cache,
        memory=memory,
        llm=llm,
        logger=logger,
        embedder=embedder,
        top_k=config.TOP_K,
        doc_metadata=doc_meta,
    )

    return rbac, pipeline, logger


# =============================================================================
def print_result(step: str, actor: str, r: QueryResult) -> None:
# =============================================================================
    cache_tag    = " [CACHE HIT]"            if r.cache_hit               else ""
    restrict_tag = " [!!! RESTRICTED CONTENT TOUCHED]" if r.ground_truth_restricted else ""
    print(f"\n  [{step}] actor={actor}{cache_tag}{restrict_tag}")
    print(f"  sim_score={r.similarity_score:.4f}  latency={r.latency_ms:.1f}ms  "
          f"refusal={r.refusal_type or '(none)'}")
    print(f"  retrieved={r.retrieved_doc_ids}")
    preview = r.response[:300].replace("\n", " ")
    suffix  = "..." if len(r.response) > 300 else ""
    print(f"  response: {preview}{suffix}")


# =============================================================================
def run_demo() -> None:
# =============================================================================
    rbac, pipeline, logger = setup()

    # -------------------------------------------------------------------------
    # STEP 2 -- Baseline: U queries D with valid access
    # Expected: D is retrieved, LLM quotes its content. Cache populated.
    # -------------------------------------------------------------------------
    sep()
    print("STEP 2 -- Baseline: alice queries D with valid access")
    print(f'         query: "{Q_PRIMARY}"')
    r2 = pipeline.query(LEGIT_USER, SESSION_ALICE_1, Q_PRIMARY,
                        step_label="step2_baseline")
    print_result("Step 2", LEGIT_USER, r2)
    assert not r2.cache_hit, "Step 2 should be a cache miss (first query)"

    # -------------------------------------------------------------------------
    # STEP 3 -- Revoke alice's access to D (RBAC only -- no cache/memory flush)
    # -------------------------------------------------------------------------
    sep()
    print("STEP 3 -- REVOCATION EVENT")
    print(f"         rbac.revoke({LEGIT_USER!r}, {TARGET_DOC!r})")
    rbac.revoke(LEGIT_USER, TARGET_DOC)
    print("         [!] RBAC table updated.")
    print("         [!] Semantic cache  -> NOT flushed  (naive flaw #1)")
    print("         [!] Session memory  -> NOT purged   (naive flaw #3)")
    print("         [!] Vector index    -> NOT changed  (naive flaw #2)")
    print(f"         alice now has access to: {sorted(rbac.accessible_docs(LEGIT_USER))}")

    # -------------------------------------------------------------------------
    # STEP 4 -- Immediate re-probe: same session, same query
    # Expected leakage: cache returns Step 2 response without RBAC check.
    # -------------------------------------------------------------------------
    sep()
    print("STEP 4 -- Post-revocation re-probe (same session, identical query)")
    print("          Tests: semantic cache leak")
    r4 = pipeline.query(LEGIT_USER, SESSION_ALICE_1, Q_PRIMARY,
                        step_label="step4_postrevoke_same_session")
    print_result("Step 4", LEGIT_USER, r4)
    if r4.cache_hit:
        print("\n  *** TEMPORAL LEAKAGE -- CACHE: revoked user received cached "
              f"response from pre-revocation session! "
              f"(sim={r4.similarity_score:.4f}) ***")
    elif r4.ground_truth_restricted and "no relevant" not in r4.response.lower():
        print("\n  *** TEMPORAL LEAKAGE -- MEMORY: response contains restricted "
              "content surfaced via session memory! ***")

    # -------------------------------------------------------------------------
    # STEP 5 -- Delayed re-probe: new session, paraphrased query
    # Expected leakage: cache hits on the paraphrase (sim >= threshold).
    # -------------------------------------------------------------------------
    sep()
    print("STEP 5 -- Post-revocation re-probe (NEW session, paraphrased query)")
    print("          Tests: semantic cache leak across session boundaries")
    print(f'         query: "{Q_PARAPHRASE}"')
    r5 = pipeline.query(LEGIT_USER, SESSION_ALICE_2, Q_PARAPHRASE,
                        step_label="step5_postrevoke_new_session")
    print_result("Step 5", LEGIT_USER, r5)
    if r5.cache_hit:
        print("\n  *** TEMPORAL LEAKAGE -- CACHE (cross-session): paraphrase "
              f"matched cache with sim={r5.similarity_score:.4f}; revoked user "
              "received restricted content in a brand-new session! ***")

    # -------------------------------------------------------------------------
    # STEP 6 -- Cross-tenant attacker probe (topic exists, doc is restricted)
    # Same exact phrasing as Q_PRIMARY -> guaranteed cache hit if cache is warm.
    # -------------------------------------------------------------------------
    sep()
    print("STEP 6 -- Attacker (bob, tenant_beta) probes D's topic")
    print("          Same phrasing as Step 2 -> will hit alice's cached response")
    print(f'         query: "{Q_PRIMARY}"')
    r6 = pipeline.query(ATTACKER, SESSION_BOB, Q_PRIMARY,
                        step_label="step6_attacker_exists")
    print_result("Step 6", ATTACKER, r6)
    if r6.cache_hit:
        print("\n  *** CONTENT LEAK -- CACHE: cross-tenant attacker received "
              "alice's cached response containing RESTRICTED content! "
              f"(sim={r6.similarity_score:.4f}) ***")
    elif r6.similarity_score > 0.5 and r6.ground_truth_restricted:
        print(f"\n  *** SIDE-CHANNEL: attacker sees sim={r6.similarity_score:.4f} "
              "for a restricted doc -> existence inferable from score alone ***")

    # -------------------------------------------------------------------------
    # STEP 7 -- Attacker queries a genuinely non-existent topic (true negative)
    # -------------------------------------------------------------------------
    sep()
    print("STEP 7 -- Attacker probes a non-existent topic (true-negative baseline)")
    print(f'         query: "{Q_GHOST}"')
    r7 = pipeline.query(ATTACKER, SESSION_BOB, Q_GHOST,
                        step_label="step7_attacker_nonexistent")
    print_result("Step 7", ATTACKER, r7)

    # -------------------------------------------------------------------------
    # STEP 8 -- Side-channel comparison table
    # -------------------------------------------------------------------------
    sep()
    print("STEP 8 -- Side-channel comparison: Step 6 (D exists) vs Step 7 (nothing exists)")
    row6 = logger.get_by_step("step6_attacker_exists")
    row7 = logger.get_by_step("step7_attacker_nonexistent")

    if row6 and row7:
        w = 34
        header = (f"  {'Signal':<22} {'Step 6 -- D exists (restricted)':<{w}} "
                  f"{'Step 7 -- topic absent':<{w}} Distinguishable?")
        print(f"\n{header}")
        print("  " + "-" * (len(header) - 2))

        def _row(label, v6, v7, numeric_thresh=None):
            if numeric_thresh is not None:
                try:
                    diff_val = abs(float(v6) - float(v7))
                    distinguishable = diff_val > numeric_thresh
                    badge = f"YES (delta={diff_val:.4f})" if distinguishable else "marginal"
                except (TypeError, ValueError):
                    badge = "YES" if str(v6) != str(v7) else "no"
            else:
                badge = "YES" if str(v6) != str(v7) else "no"
            print(f"  {label:<22} {str(v6):<{w}} {str(v7):<{w}} {badge}")

        _row("Cache hit",        row6.cache_hit,        row7.cache_hit)
        _row("Similarity score", row6.similarity_score, row7.similarity_score, 0.05)
        _row("Latency (ms)",     row6.latency_ms,       row7.latency_ms,       50.0)
        _row("Refusal type",     row6.refusal_type or "(none)", row7.refusal_type or "(none)")

    # -------------------------------------------------------------------------
    # Evidence log
    # -------------------------------------------------------------------------
    sep()
    csv_path = config.RESULTS_DIR / "run_log.csv"
    logger.dump_csv(csv_path)

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    all_rows = logger.rows()
    temporal_cache_leaked = any(
        r.cache_hit and r.ground_truth_restricted
        and r.actor == LEGIT_USER
        and r.step_label in ("step4_postrevoke_same_session",
                             "step5_postrevoke_new_session")
        for r in all_rows
    )
    content_leak_attacker = (row6 is not None
                             and row6.cache_hit
                             and row6.ground_truth_restricted)
    sidechannel_leaked = (
        row6 is not None and row7 is not None
        and (
            row6.cache_hit != row7.cache_hit
            or abs(row6.similarity_score - row7.similarity_score) > 0.05
            or (row6.refusal_type or "") != (row7.refusal_type or "")
        )
    )

    print("\n" + "=" * 68)
    print("  RUN SUMMARY")
    print("=" * 68)
    ok  = "[CONFIRMED]"
    no  = "[not observed]"
    print(f"\n  Temporal leakage  (cache, post-revocation):    "
          f"{ok if temporal_cache_leaked else no}")
    print(f"  Content leakage   (attacker received D):       "
          f"{ok if content_leak_attacker  else no}")
    print(f"  Side-channel leak (distinguishable signal):    "
          f"{ok if sidechannel_leaked     else no}")
    print(f"\n  Evidence log -> {csv_path.resolve()}")
    print()


# ---- Helpers ----------------------------------------------------------------

def sep() -> None:
    print("\n" + "-" * 68)


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    run_demo()
