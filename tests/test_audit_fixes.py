"""
Checks for the changes made after the reviewer audit (afterimage_reviewer_audit.md):
per-user baseline cache (C2), post-filter scores over authorized chunks (C3), corpus-unique
judging (C5), the epoch and flush alternatives (C6), sentence-level summary taint (H6),
memory retention, read-only probes, post-revocation document updates and mover revocation
(C1, H2, H4), the v3 corpus (H3) and the clustered statistics (H1).
"""

import random

import numpy as np
import pytest

from src.secure_pipeline.corpus import chunk_document
from src.secure_pipeline.experiments import _updated_doc
from src.secure_pipeline.judge import disclosed
from src.secure_pipeline.metrics import cluster_ci, holm

from test_invariants import REVOCATIONS, _probe_disclosures, _revoke, _victim, _warm


def _insider(pipe, target):
    return next(u["user_id"] for u in pipe.corpus.users_of(target["tenant_id"])
                if not pipe.acm.has_access(u["user_id"], target["doc_id"]))


# ---- C2: no cross-user cache hits in baseline ----------------------------------------------

@pytest.mark.parametrize("name,expect_hit", [("baseline", False), ("authz_prefilter", False),
                                             ("baseline_shared", True)])
def test_cache_is_per_user_unless_misconfigured(make_pipeline, name, expect_hit):
    pipe, client = make_pipeline(name)
    target = pipe.corpus.restricted()[0]
    q = target["qa"][0]["question"]
    client.ask(_victim(pipe, target), "v", q)
    client.ask(_insider(pipe, target), "i", q)
    assert client.logger.rows[-1]["truth"]["cache_hit"] == expect_hit


# ---- C3: post-filter exposes scores of authorized chunks only --------------------------------

def test_postfilter_scores_cover_authorized_chunks_only(make_pipeline):
    for name, leaks_withheld in (("authz_postfilter", False), ("strawman", True)):
        pipe, client = make_pipeline(name)
        target = pipe.corpus.restricted()[0]
        client.ask(_insider(pipe, target), "i", target["qa"][0]["question"])
        truth = client.logger.rows[-1]["truth"]
        if not leaks_withheld:
            shown = [s for d, s in zip(truth["candidate_docs"], truth["candidate_scores"])
                     if pipe.acm.has_access(truth["user"], d)]
            assert truth["raw_confidence"] == pytest.approx(max(shown, default=0.0), abs=1e-3)
        else:
            assert truth["raw_confidence"] == pytest.approx(max(truth["candidate_scores"]), abs=1e-3)


# ---- C5: only corpus-unique values count ---------------------------------------------------------

def test_shared_fact_values_are_not_scored(env):
    corpus = env.corpus
    shared = [(d, f["value"]) for d in corpus.restricted() for f in d["facts"]
              if f["value"] not in corpus.unique_facts(d["doc_id"])]
    assert shared, "the v2 corpus has shared values (e.g. site names)"
    doc, value = shared[0]
    assert not disclosed(corpus, doc["doc_id"], f"... {value} ...", [], mode="unique").any
    assert disclosed(corpus, doc["doc_id"], f"... {doc['canary']} ...", [], mode="unique").canary


# ---- C6: simple alternatives also close revocation ---------------------------------------------

@pytest.mark.parametrize("name", ["epoch", "flush", "full_fine"])
@pytest.mark.parametrize("kind", REVOCATIONS + ["mover"])
def test_alternatives_never_disclose_revoked_doc(make_pipeline, name, kind):
    pipe, client = make_pipeline(name, sync="periodic:86400")
    for target in pipe.corpus.restricted()[:8]:
        pipe.reset()
        victim = _victim(pipe, target)
        _warm(client, victim, target, "main")
        if kind == "mover":
            from src.secure_pipeline.experiments import _revoke as revoke
            revoke(pipe, "mover", victim, target)
        else:
            _revoke(pipe, kind, victim, target)
        assert not pipe.acm.has_access(victim, target["doc_id"])
        assert not any(_probe_disclosures(client, victim, target, "main")), (name, kind, target["doc_id"])


def test_mover_bumps_epoch_and_reports_lost_docs(make_pipeline):
    pipe, _ = make_pipeline("baseline")
    target = pipe.corpus.restricted()[0]
    victim = _victim(pipe, target)
    from src.secure_pipeline.experiments import _revoke as revoke
    revoke(pipe, "mover", victim, target)
    ev = pipe.acm.history()[-1]
    assert ev.event_type == "mover" and target["doc_id"] in ev.doc_ids
    assert pipe.acm.epoch(victim) == 1


# ---- H6: sentence-level taint keeps retained material in the summary --------------------------

def test_sentence_taint_keeps_more_of_the_summary(make_pipeline):
    kept = {}
    for name in ("full", "full_fine"):
        pipe, client = make_pipeline(name, summary_after=4, keep_recent=2)
        target = pipe.corpus.restricted()[0]
        victim = _victim(pipe, target)
        _warm(client, victim, target, "main", fillers=4)
        pipe.acm.revoke(victim, target["doc_id"])
        ctx = pipe.memory.context("main", victim)
        kept[name] = sum(len(t.content) for t in ctx if t.role == "summary")
    assert kept["full_fine"] > kept["full"]


# ---- H2: retention, read-only probes -------------------------------------------------------------

def test_memory_expires_after_idle_ttl(make_pipeline):
    pipe, client = make_pipeline("baseline", memory_ttl_s=3600)
    target = pipe.corpus.restricted()[0]
    victim = _victim(pipe, target)
    _warm(client, victim, target, "main")
    assert pipe.memory.context("main", victim)
    pipe.clock.advance(7200)
    assert pipe.memory.context("main", victim) == []


def test_readonly_probe_writes_nothing(make_pipeline):
    pipe, client = make_pipeline("baseline")
    target = pipe.corpus.restricted()[0]
    victim = _victim(pipe, target)
    _warm(client, victim, target, "main")
    n_cache, n_mem = len(pipe.cache), len(pipe.memory.turns("main"))
    client.ask(victim, "main", f"Remind me what you told me earlier about {target['topic']}.", write=False)
    client.ask(victim, "other", target["qa"][2 % len(target["qa"])]["question"], write=False)
    assert len(pipe.cache) == n_cache and len(pipe.memory.turns("main")) == n_mem


def test_stub_answers_recall_question_from_memory(make_pipeline):
    pipe, client = make_pipeline("baseline")
    target = pipe.corpus.restricted()[0]
    victim = _victim(pipe, target)
    _warm(client, victim, target, "main")
    pipe.acm.revoke(victim, target["doc_id"])
    client.ask(victim, "main", f"Remind me what you told me earlier about {target['topic']} and its figures.")
    assert not client.logger.rows[-1]["truth"]["refused"]


# ---- C1: post-revocation update -----------------------------------------------------------------

def test_updated_doc_is_served_through_stale_index_and_restored(make_pipeline):
    pipe, client = make_pipeline("baseline", sync="periodic:86400")
    target = pipe.corpus.restricted()[0]
    victim = _victim(pipe, target)
    pipe.acm.revoke(victim, target["doc_id"])
    new_doc, secrets = _updated_doc(target, random.Random(0))
    assert secrets and all(v not in target["text"] for v in secrets)
    chunks = chunk_document(new_doc)
    pipe.index.update_doc(target["doc_id"], chunks, pipe.embedder.encode([c.text for c in chunks]))
    client.ask(victim, "x", target["qa"][0]["question"])
    response = client.logger.rows[-1]["truth"]["response"]
    assert any(v in response for v in secrets)
    pipe.reset()
    client.ask(victim, "y", target["qa"][0]["question"])
    assert not any(v in client.logger.rows[-1]["truth"]["response"] for v in secrets)


# ---- H3: v3 corpus ------------------------------------------------------------------------------

def test_v3_corpus_shape(tmp_path):
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("gen", root / "scripts" / "generate_corpus.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    docs, iam = gen.build(1, 40, 30, 30, profile="v3")
    assert gen.build(1, 40, 30, 30, profile="v3")[0] == docs
    restricted = [d for d in docs if d["sensitivity"] == "restricted"]
    projects = {}
    for d in restricted:
        projects.setdefault(d["project"], []).append(d)
    assert all(len(v) == 2 for v in projects.values())
    assert np.mean([len(chunk_document(d)) for d in restricted]) >= 2
    numeric = [f["value"] for d in restricted for f in d["facts"] if any(c.isdigit() for c in f["value"])]
    assert len(numeric) == len(set(numeric))
    train = {d["title"].split("--")[1] for d in restricted if d["tenant_id"] in ("t1", "t2", "t3")}
    test = {d["title"].split("--")[1] for d in restricted if d["tenant_id"] in ("t4", "t5")}
    assert not train & test


# ---- H1: statistics -------------------------------------------------------------------------------

def test_cluster_ci_and_holm():
    m, lo, hi = cluster_ci([1, 1, 1, 0, 0, 0], ["a", "a", "a", "b", "b", "b"])
    assert m == 0.5 and lo == 0.0 and hi == 1.0
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


# ---- Re-audit (afterimage_changes.md) ----------------------------------------------------------

def test_missing_paraphrase_raises(make_pipeline, tmp_path, monkeypatch):
    import json
    from src.secure_pipeline import experiments
    (tmp_path / "paraphrases.json").write_text(json.dumps({"some other question?": ["x"]}))
    monkeypatch.setattr(experiments, "DATA_DIR", tmp_path)
    pipe, client = make_pipeline("baseline")
    cell = {"events": 1, "probe_paraphrase": "file", "probe_times": [0]}
    with pytest.raises(KeyError, match="no paraphrases"):
        experiments.run_revocation(pipe, client, cell, random.Random(0), {"seed": 0})


def test_dropped_hook_breaks_flush_but_not_epoch(make_pipeline):
    leaked = {}
    for name in ("flush", "epoch"):
        pipe, client = make_pipeline(name, sync="periodic:86400", hook_drop=1.0)
        target = pipe.corpus.restricted()[0]
        victim = _victim(pipe, target)
        _warm(client, victim, target, "main")
        pipe.acm.revoke(victim, target["doc_id"])
        # epoch has no eager hooks to drop; its check runs on every read.
        assert (pipe.acm.dropped_hooks > 0) == (name == "flush")
        leaked[name] = any(_probe_disclosures(client, victim, target, "main"))
    assert leaked == {"flush": True, "epoch": False}


def test_reclassify_bumps_every_affected_user(make_pipeline):
    pipe, _ = make_pipeline("epoch")
    target = pipe.corpus.restricted()[0]
    group = target["acl_groups"][0]
    holders = sorted(pipe.acm.users_with_access(target["doc_id"]))
    events = pipe.acm.reclassify(target["doc_id"], group)
    lost = {e.user_id for e in events}
    assert lost and lost <= set(holders)
    assert all(pipe.acm.epoch(u) == 1 for u in lost)
    assert all(not pipe.acm.has_access(u, target["doc_id"]) for u in lost)


def test_reclassify_closes_leak_and_bystander_session_survives_under_taint(make_pipeline):
    """Taint drops only artifacts derived from the reclassified document; epoch wipes the
    bystander's session too."""
    kept = {}
    for name in ("full_fine", "epoch"):
        pipe, client = make_pipeline(name, sync="periodic:86400", summary_after=4, keep_recent=2)
        target = next(d for d in pipe.corpus.restricted()
                      if len(pipe.acm.users_with_access(d["doc_id"])) >= 2)
        victim, by = sorted(pipe.acm.users_with_access(target["doc_id"]))[:2]
        _warm(client, victim, target, "main")
        _warm(client, by, target, "by")
        for g in target["acl_groups"]:
            pipe.acm.reclassify(target["doc_id"], g)
        assert not any(_probe_disclosures(client, victim, target, "main"))
        kept[name] = len(pipe.memory.context("by", by))
    assert kept["full_fine"] > kept["epoch"]


def test_updated_values_are_corpus_unique(env):
    target = env.corpus.restricted()[0]
    _, secrets = _updated_doc(target, random.Random(0), env.corpus)
    assert secrets and not any(v in d["text"] for v in secrets for d in env.corpus.docs)
