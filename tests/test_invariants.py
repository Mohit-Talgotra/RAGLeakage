"""
Security invariants of the full-mitigation preset, plus checks that the harness can
still see the leaks it is meant to measure (otherwise a zero would mean nothing).
"""

import numpy as np
import pytest

from src.secure_pipeline.judge import disclosed
from src.secure_pipeline.provenance import EMPTY

REVOCATIONS = ["single_doc", "role", "user_offboard"]


def _victim(pipe, target):
    return sorted(pipe.acm.users_with_access(target["doc_id"]))[0]


def _revoke(pipe, kind, victim, target):
    if kind == "single_doc":
        pipe.acm.revoke(victim, target["doc_id"])
    elif kind == "role":
        group = sorted(set(target["acl_groups"]) & pipe.acm.groups_of(victim))[0]
        pipe.acm.revoke_role(victim, group)
    else:
        pipe.acm.offboard_user(victim)


def _warm(client, victim, target, session, fillers=4):
    corpus = client.pipeline.corpus
    client.ask(victim, session, target["qa"][0]["question"])
    pool = [d for d in corpus.docs if d["tenant_id"] == target["tenant_id"] and d["sensitivity"] == "public"]
    for d in pool[:fillers]:
        client.ask(victim, session, d["qa"][0]["question"])
    client.ask(victim, session, target["qa"][1]["question"])


def _probe_disclosures(client, victim, target, session, times=(0, 600, 7200, 90000)):
    corpus, clock = client.pipeline.corpus, client.pipeline.clock
    t0 = clock.now()
    leaks = []
    for t in times:
        clock.advance(max(0.0, t0 + t - clock.now()))
        for sess, q in ((session, f"Remind me what you told me earlier about {target['topic']} and its figures."),
                        (f"fresh-{t}", target["qa"][0]["question"])):
            client.ask(victim, sess, q)
            truth = client.logger.rows[-1]["truth"]
            d = disclosed(corpus, target["doc_id"], truth["response"], truth["source_docs"])
            leaks.append(d.any)
    return leaks


@pytest.mark.parametrize("kind", REVOCATIONS)
def test_full_preset_never_discloses_revoked_doc(make_pipeline, kind):
    pipe, client = make_pipeline("full", sync="periodic:86400")
    for target in pipe.corpus.restricted()[:12]:
        pipe.reset()
        victim = _victim(pipe, target)
        _warm(client, victim, target, "main")
        _revoke(pipe, kind, victim, target)
        assert not any(_probe_disclosures(client, victim, target, "main")), target["doc_id"]


def test_baseline_does_leak(make_pipeline):
    """Sanity: the same procedure on the shipped baseline must leak, or the test above is vacuous."""
    pipe, client = make_pipeline("baseline", sync="periodic:86400")
    leaked = 0
    for target in pipe.corpus.restricted()[:12]:
        pipe.reset()
        victim = _victim(pipe, target)
        _warm(client, victim, target, "main")
        _revoke(pipe, "single_doc", victim, target)
        leaked += any(_probe_disclosures(client, victim, target, "main"))
    assert leaked > 0


def test_revoked_cache_entry_never_hits(make_pipeline):
    pipe, client = make_pipeline("full")
    target = pipe.corpus.restricted()[0]
    victim = _victim(pipe, target)
    q = target["qa"][0]["question"]
    client.ask(victim, "s", q)
    assert pipe.cache.entries_tainted_by(target["doc_id"]), "warm-up should have cached an answer"
    pipe.acm.revoke(victim, target["doc_id"])
    assert not pipe.cache.entries_tainted_by(target["doc_id"])
    emb = pipe.embedder.encode([q])[0]
    assert pipe.cache.get(emb, victim, pipe.acm.tenant_of(victim)) is None


def test_lazy_check_alone_blocks_revoked_user_but_serves_holders(make_pipeline):
    pipe, client = make_pipeline("full", cache_evict=False)
    target = pipe.corpus.restricted()[0]
    holders = sorted(pipe.acm.users_with_access(target["doc_id"]))
    victim = holders[0]
    q = target["qa"][0]["question"]
    client.ask(victim, "s", q)
    pipe.acm.revoke(victim, target["doc_id"])
    emb = pipe.embedder.encode([q])[0]
    tenant = pipe.acm.tenant_of(victim)
    assert pipe.cache.entries_tainted_by(target["doc_id"]), "no eager eviction in this config"
    assert pipe.cache.get(emb, victim, tenant) is None
    if len(holders) > 1:
        assert pipe.cache.get(emb, holders[1], tenant) is not None


def test_tainted_memory_turns_and_summaries_are_gone(make_pipeline):
    pipe, client = make_pipeline("full", summary_after=6, keep_recent=2)
    target = pipe.corpus.restricted()[0]
    victim = _victim(pipe, target)
    _warm(client, victim, target, "main")
    turns = pipe.memory.turns("main")
    assert any(t.role == "summary" for t in turns), "warm-up should trigger a rolling summary"
    assert any(target["doc_id"] in t.taint for t in turns)
    pipe.acm.revoke(victim, target["doc_id"])
    assert all(target["doc_id"] not in t.taint for t in pipe.memory.turns("main"))
    secrets = pipe.corpus.secrets(target["doc_id"])
    assert not any(s in t.content for t in pipe.memory.turns("main") for s in secrets)


def test_id_match_purge_misses_the_summary(make_pipeline):
    """The legacy (non-transitive) design leaves restricted content in an untainted summary.
    This is the gap provenance taint is meant to close; the experiment depends on it existing."""
    pipe, client = make_pipeline("legacy", summary_after=6, keep_recent=2)
    for target in pipe.corpus.restricted()[:10]:
        pipe.reset()
        victim = _victim(pipe, target)
        _warm(client, victim, target, "main")
        summaries = [t for t in pipe.memory.turns("main") if t.role == "summary"]
        secrets = pipe.corpus.secrets(target["doc_id"])
        if not any(s in t.content for t in summaries for s in secrets):
            continue
        assert all(t.taint == EMPTY for t in summaries)
        pipe.acm.revoke(victim, target["doc_id"])
        surviving = [t for t in pipe.memory.turns("main") if t.role == "summary"]
        assert any(s in t.content for t in surviving for s in secrets)
        return
    pytest.skip("no warm-up put target secrets into a summary with the hash embedder")


def test_constant_shape_latency_full_preset(make_pipeline):
    pipe, client = make_pipeline("full")
    lat = [client.ask(u["user_id"], f"s{i}", d["qa"][0]["question"]).latency_ms
           for i, (u, d) in enumerate(zip(pipe.corpus.iam["users"], pipe.corpus.docs[::13]))]
    buckets = np.array(lat) / 500.0
    assert np.allclose(buckets, np.round(buckets), atol=0.01)


def test_attacker_sees_only_exposure_profile(make_pipeline):
    from src.secure_pipeline.pipeline import Client
    pipe, _ = make_pipeline("baseline")
    user = pipe.corpus.iam["users"][0]["user_id"]
    obs = Client(pipe, "text_only").ask(user, "s", "What is the travel policy approval limit?")
    assert obs.sources is None and obs.confidence is None and obs.rerank_confidence is None
    obs = Client(pipe, "with_sources").ask(user, "s", "What is the travel policy approval limit?")
    assert obs.confidence is not None and obs.rerank_confidence is None
