"""
Taint invariant (docs/TAINT_SOUNDNESS.md): no derived artifact (cache entry, memory turn,
summary) holds a restricted document's secret unless that document is in its taint.
Only secrets that occur in no other document's text count, so finding one in an artifact
proves the content came from that document, whatever path it took.
"""

import random

from src.secure_pipeline.provenance import EMPTY


def _artifacts(pipe):
    for e in pipe.cache._entries:
        yield e.response, e.taint
    for turns in pipe.memory._sessions.values():
        for t in turns:
            yield t.content, t.taint


def _unique_secrets(corpus):
    texts = {d["doc_id"]: d["text"] for d in corpus.docs}
    return [(d["doc_id"], v) for d in corpus.restricted() for v in corpus.secrets(d["doc_id"])
            if len(v) >= 4 and not any(v in t for o, t in texts.items() if o != d["doc_id"])]


def _check(pipe):
    """(artifacts holding some unique secret, violations of the invariant)."""
    secrets = _unique_secrets(pipe.corpus)
    holding, bad = 0, []
    for text, taint in _artifacts(pipe):
        hits = [(doc, v) for doc, v in secrets if v in text]
        holding += bool(hits)
        bad += [(doc, v, text[:80]) for doc, v in hits if doc not in taint]
    return holding, bad


def _random_sessions(pipe, client, n_queries=60, seed=0):
    rng = random.Random(seed)
    corpus = pipe.corpus
    user = max((u["user_id"] for u in corpus.users_of("t1")),
               key=lambda u: sum(pipe.acm.has_access(u, d["doc_id"]) for d in corpus.restricted(["t1"])))
    docs = [d for d in corpus.docs if d["tenant_id"] == "t1" and pipe.acm.has_access(user, d["doc_id"])]
    for i in range(n_queries):
        d = rng.choice(docs)
        q = rng.choice(d["qa"])["question"] if rng.random() < 0.8 else \
            f"Remind me what you told me earlier about {d['topic']} and its figures."
        client.ask(user, f"s{i % 3}", q)


def test_invariant_holds_with_transitive_taint(make_pipeline):
    pipe, client = make_pipeline("full", summary_after=4, keep_recent=2)
    _random_sessions(pipe, client)
    holding, bad = _check(pipe)
    assert holding > 0, "vacuous: no artifact carried a restricted secret"
    assert bad == []


def test_non_transitive_taint_breaks_invariant(make_pipeline):
    pipe, client = make_pipeline("full", taint_transitive=False, summary_after=4, keep_recent=2)
    _random_sessions(pipe, client)
    _, bad = _check(pipe)
    assert bad, "summaries should carry content without taint when taint is not transitive"


def test_pasted_content_is_untainted_unless_fingerprinted(make_pipeline):
    """Assumption A1: user input carries no taint. taint_user_input closes that gap."""
    secret = next(d for d in make_pipeline("full")[0].corpus.restricted() if d["tenant_id"] == "t1")
    outsider = "t1_ivan"  # contractor without access to restricted docs
    for fingerprint, expect_bad in ((False, True), (True, False)):
        pipe, client = make_pipeline("full", taint_user_input=fingerprint)
        assert not pipe.acm.has_access(outsider, secret["doc_id"])
        client.ask(outsider, "paste", f"My colleague sent me this: {secret['canary']}. What does it mean?")
        _, bad = _check(pipe)
        assert bool(bad) == expect_bad
        user_turns = [t for t in pipe.memory._sessions["paste"] if t.role == "user"]
        assert (user_turns[0].taint == EMPTY) == (not fingerprint)
