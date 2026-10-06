import json
import math
import random
import subprocess
import sys

import numpy as np
import pytest

from conftest import ROOT
from src.secure_pipeline.clock import SimClock, WallClock
from src.secure_pipeline.experiments import mitigations_for
from src.secure_pipeline.index_store import SyncPolicy
from src.secure_pipeline.llm_client import LLMClient
from src.secure_pipeline.metrics import (kaplan_meier, km_median, leak_lifetime, paired_bootstrap,
                                         tpr_at_fpr)
from src.secure_pipeline.mitigations import ABLATABLE, PRESETS
from src.secure_pipeline.normalization import pad_seconds


# ---- Clock -------------------------------------------------------------------------

def test_sim_clock_sleep_and_advance_are_virtual():
    c = SimClock()
    t0 = c.now()
    c.sleep(3600)
    c.advance(60)
    assert 3660 <= c.now() - t0 < 3661


def test_wall_clock_refuses_to_jump():
    with pytest.raises(RuntimeError):
        WallClock().advance(1)


# ---- ACL sync policies -----------------------------------------------------------------

def _stale_after_revoke(make_pipeline, sync):
    pipe, _ = make_pipeline("baseline", sync=sync)
    target = pipe.corpus.restricted()[0]
    victim = sorted(pipe.acm.users_with_access(target["doc_id"]))[0]
    pipe.acm.revoke(victim, target["doc_id"])
    return pipe, target, victim


def test_live_sync_is_never_stale(make_pipeline):
    pipe, target, victim = _stale_after_revoke(make_pipeline, "live")
    assert not pipe.index.is_stale(target["doc_id"])


def test_periodic_sync_stays_stale_until_next_crawl(make_pipeline):
    pipe, target, victim = _stale_after_revoke(make_pipeline, "periodic:3600")
    assert pipe.index.is_stale(target["doc_id"])
    assert pipe.index.index_allows(victim, target["doc_id"])
    wait = pipe.index.next_sync_in()
    assert 0 <= wait <= 3600
    pipe.clock.advance(wait + 1)
    pipe.index.tick()
    assert not pipe.index.is_stale(target["doc_id"])


def test_event_sync_with_total_loss_needs_backstop(make_pipeline):
    pipe, target, _ = _stale_after_revoke(make_pipeline, "event:1.0:86400")
    assert pipe.index.dropped_events == 1 and pipe.index.is_stale(target["doc_id"])
    pipe.clock.advance(86401)
    pipe.index.tick()
    assert not pipe.index.is_stale(target["doc_id"])


def test_stale_index_serves_revoked_doc_without_live_check(make_pipeline):
    pipe, target, victim = _stale_after_revoke(make_pipeline, "periodic:86400")
    emb = pipe.embedder.encode([target["qa"][0]["question"]])[0]
    cands = pipe.index.query(emb, 20, victim, pipe.acm.tenant_of(victim), prefilter=True)
    assert target["doc_id"] in {c.doc_id for c in cands}


def test_sync_policy_parse_roundtrip():
    for spec in ["live", "periodic:3600", "event:0.05", "event:0.05:86400"]:
        assert SyncPolicy.parse(spec).label() == spec


# ---- LLM client -----------------------------------------------------------------------

def test_unknown_backend_rejected():
    with pytest.raises(ValueError):
        LLMClient("nope", SimClock(), random.Random(0))


def test_missing_key_raises_instead_of_falling_back(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        LLMClient("groq", SimClock(), random.Random(0))


def test_stub_is_deterministic_per_seed():
    def gen(seed):
        c = SimClock()
        g = LLMClient("stub", c, random.Random(seed)).answer(
            "What is the list price of Project X?", [("Project X", "List price is set at $10,100 per unit.")], [],
            "refuse")
        return g.text, round(g.latency_s, 9)
    assert gen(1) == gen(1)
    assert gen(1)[0] == gen(2)[0]


# ---- Padding, presets ------------------------------------------------------------------

def test_bucket_padding_rounds_up():
    rng = random.Random(0)
    assert math.isclose(0.2 + pad_seconds(0.2, "bucket", 500, rng), 0.5)
    assert math.isclose(1.2 + pad_seconds(1.2, "bucket", 500, rng), 1.5)
    assert pad_seconds(0.2, "deadline", 1000, rng) == pytest.approx(0.8)
    assert pad_seconds(1.2, "deadline", 1000, rng) == 0.0


def test_open_surface_and_ablation_mapping():
    m = mitigations_for({"preset": "full", "open_surface": "memory"})
    assert not m.memory_purge and not m.memory_lazy_check and m.cache_evict
    m = mitigations_for({"preset": "full", "ablate": "latency_pad"})
    assert not m.latency_pad and m.uniform_refusal
    assert "fast_refusal" not in ABLATABLE and "taint_transitive" in ABLATABLE
    assert PRESETS["strawman"].cache_scope == "global"


# ---- Metrics ----------------------------------------------------------------------------

def test_leak_lifetime_cases():
    assert leak_lifetime([0, 60, 600], [False, False, False]) == (0.0, True)
    assert leak_lifetime([0, 60, 600], [True, False, False]) == (60.0, True)
    assert leak_lifetime([0, 60, 600], [True, False, True]) == (600.0, False)


def test_kaplan_meier_median():
    times, surv = kaplan_meier([1, 2, 3, 4], [True, True, True, True])
    assert list(surv) == [1.0, 0.75, 0.5, 0.25, 0.0]
    assert km_median([1, 2, 3, 4], [True, True, True, True]) == 2.0
    assert km_median([5, 5], [False, False]) == math.inf


def test_paired_bootstrap_and_tpr():
    res = paired_bootstrap([1.0] * 20, [0.0] * 20)
    assert res["diff"] == 1.0 and res["p"] == 0.0
    y = np.array([0] * 100 + [1] * 100)
    s = np.concatenate([np.linspace(0, 0.5, 100), np.linspace(0.51, 1, 100)])
    assert tpr_at_fpr(y, s, 0.01) == 1.0


# ---- Corpus and runner ------------------------------------------------------------------------

def test_corpus_generator_is_deterministic(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_corpus.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    assert (tmp_path / "corpus.jsonl").read_bytes() == (ROOT / "data" / "corpus.jsonl").read_bytes()
    assert (tmp_path / "iam.json").read_bytes() == (ROOT / "data" / "iam.json").read_bytes()


def test_corpus_invariants(env):
    corpus = env.corpus
    canaries = [d["canary"] for d in corpus.restricted()]
    assert len(canaries) == len(set(canaries)) == 150
    for d in corpus.docs:
        for f in d["facts"]:
            assert f["value"] in d["text"]
    for d in corpus.restricted():
        users = {u["user_id"] for u in corpus.users_of(d["tenant_id"])}
        groups = set(d["acl_groups"])
        holders = {u["user_id"] for u in corpus.iam["users"] if groups & set(u["groups"])}
        assert holders and users - holders, d["doc_id"]


def test_grid_expansion():
    sys.path.insert(0, str(ROOT))
    from run import expand
    cells = expand({"experiment": "revocation", "base": {"events": 2},
                    "grid": {"preset": ["baseline", "full"], "sync": ["live", "periodic:60"]}})
    assert len(cells) == 4
    assert len({c["cell_id"] for c in cells}) == 4
    assert all(c["events"] == 2 and c["experiment"] == "revocation" for c in cells)
    json.dumps(cells)


def test_queries_since_revocation_counts_per_user(make_pipeline):
    pipe, client = make_pipeline("baseline")
    target = pipe.corpus.restricted()[0]
    victim = sorted(pipe.acm.users_with_access(target["doc_id"]))[0]
    other = pipe.corpus.iam["users"][-1]["user_id"]
    client.ask(victim, "s", "hello there")
    assert client.logger.rows[-1]["truth"]["queries_since_revocation"] is None
    pipe.acm.revoke(victim, target["doc_id"])
    for _ in range(3):
        client.ask(other, "o", "travel policy approval limit")
    client.ask(victim, "s", "hello again")
    client.ask(victim, "s", "and again")
    assert client.logger.rows[-1]["truth"]["queries_since_revocation"] == 2
    assert client.logger.rows[-3]["truth"]["queries_since_revocation"] is None
