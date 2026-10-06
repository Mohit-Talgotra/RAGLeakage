"""
experiments.py -- Experiment procedures. Each writes JSONL rows through Client; nothing is
scored at run time (analyze.py does that from the logs).

- revocation (RQ1, RQ2, RQ4): many revocation events. For each: a victim warms the
  cache and their chat memory on a restricted target, access is revoked, then the victim
  re-probes at scheduled times (same session -> memory + cache + index; fresh session ->
  cache + index). Leakage over time per event gives LM and the survival curve.
- existence (RQ3): twin worlds. Every target is probed by an attacker in a world that
  contains it and in an identical world without it. Labels are the world, so baseline
  and mitigated configurations share one ground truth.
- utility (RQ5): authorized users ask answerable questions; measures retrieval quality,
  correctness, over-refusal, latency and cache hit rate.

A "cell" is one fully specified configuration (see run.py for how YAML grids expand).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, fields
from typing import Optional

import numpy as np

from .attacker import make_probes
from .clock import Clock, SimClock, make_clock
from .corpus import Corpus, load_corpus
from .embedding import encode_cached, make_embedder
from .instrumentation import RunLogger
from .llm_client import LLMClient
from .mitigations import Mitigations, OPEN_SURFACE, preset
from .pipeline import Client, PipelineConfig, RAGPipeline
from .reranker import make_reranker

MITIGATION_FIELDS = {f.name for f in fields(Mitigations)}
PIPELINE_FIELDS = {f.name for f in fields(PipelineConfig)}

DEFAULT_PROBE_TIMES = [0, 60, 600, 1800, 3600, 7200, 14400, 28800, 43200, 86400, 129600, 172800]


@dataclass
class Env:
    """Heavy shared resources: corpus, embedder, chunk vectors, reranker."""
    corpus: Corpus
    embedder: object
    chunk_vecs: np.ndarray
    reranker: object

    @classmethod
    def build(cls, embedder: str, reranker: str, chunk_tokens: int = 300) -> "Env":
        corpus = load_corpus(chunk_tokens=chunk_tokens)
        emb = make_embedder(embedder)
        vecs = encode_cached(emb, [c.text for c in corpus.chunks])
        return cls(corpus, emb, vecs, make_reranker(reranker))


def mitigations_for(cell: dict) -> Mitigations:
    overrides = {k: v for k, v in cell.items() if k in MITIGATION_FIELDS}
    surface = cell.get("open_surface")
    if surface:
        overrides = {**OPEN_SURFACE[surface], **overrides}
    ablate = cell.get("ablate")
    if ablate and ablate != "none":
        overrides[ablate] = False
    return preset(cell.get("preset", "baseline"), **overrides)


def pipeline_config_for(cell: dict) -> PipelineConfig:
    return PipelineConfig(**{k: v for k, v in cell.items() if k in PIPELINE_FIELDS})


def run_cell(env: Env, cell: dict, seed: int, logger: RunLogger) -> None:
    random.seed(seed)
    np.random.seed(seed)
    clock = make_clock(cell.get("clock", "sim"))
    llm = LLMClient(cell.get("llm_backend", "stub"), clock, random.Random(f"{seed}-llm"),
                    model=cell.get("llm_model"), temperature=0.0)
    pipe = RAGPipeline(env.corpus, env.chunk_vecs, env.embedder, env.reranker, llm, clock,
                       mitigations_for(cell), pipeline_config_for(cell), seed=seed)
    client = Client(pipe, cell.get("exposure", "with_reranker"), logger)
    base_tags = {"cell": cell["cell_id"], "seed": seed}
    # Event sampling uses its own RNG so every cell sees the same targets for a seed (paired design).
    rng = random.Random(f"{seed}-events")
    try:
        experiment = cell["experiment"]
        if experiment == "revocation":
            run_revocation(pipe, client, cell, rng, base_tags)
        elif experiment == "existence":
            run_existence(pipe, client, cell, rng, base_tags)
        elif experiment == "utility":
            run_utility(pipe, client, cell, rng, base_tags)
        else:
            raise ValueError(f"unknown experiment {experiment!r}")
    finally:
        pipe.close()
        logger.flush()


def _wait(clock: Clock, seconds: float) -> None:
    """Let simulated time pass between user actions; a no-op under WallClock."""
    if isinstance(clock, SimClock):
        clock.advance(seconds)


# ---- Revocation window (RQ1, RQ2, RQ4) --------------------------------------------

def _revoke(pipe: RAGPipeline, kind: str, victim: str, target: dict) -> None:
    if kind == "single_doc":
        pipe.acm.revoke(victim, target["doc_id"])
    elif kind == "role":
        group = sorted(set(target["acl_groups"]) & pipe.acm.groups_of(victim))[0]
        pipe.acm.revoke_role(victim, group)
    elif kind == "user_offboard":
        pipe.acm.offboard_user(victim)
    else:
        raise ValueError(f"unknown revocation type {kind!r}")


def _fillers(corpus: Corpus, pipe: RAGPipeline, victim: str, target: dict, rng: random.Random, n: int) -> list[str]:
    pool = [d for d in corpus.docs if d["tenant_id"] == target["tenant_id"] and d["doc_id"] != target["doc_id"]
            and d["sensitivity"] != "restricted" and pipe.acm.has_access(victim, d["doc_id"])]
    return [rng.choice(d["qa"])["question"] for d in rng.sample(pool, min(n, len(pool)))]


def run_revocation(pipe: RAGPipeline, client: Client, cell: dict, rng: random.Random, base: dict) -> None:
    corpus = pipe.corpus
    events = int(cell.get("events", 50))
    kind = cell.get("revocation_type", "single_doc")
    probe_times = sorted(float(t) for t in cell.get("probe_times", DEFAULT_PROBE_TIMES))
    n_fillers = int(cell.get("warm_fillers", 4))
    targets = corpus.restricted(cell.get("tenants"))
    clock = pipe.clock
    if not isinstance(clock, SimClock):
        raise ValueError("the revocation experiment spans hours of simulated time; use clock: sim")

    for ev in range(events):
        pipe.reset()
        target = rng.choice(targets)
        tid = target["doc_id"]
        victim = rng.choice(sorted(pipe.acm.users_with_access(tid)))
        qa = target["qa"]
        fillers = _fillers(corpus, pipe, victim, target, rng, n_fillers)
        gap = rng.uniform(0, 600)
        tags = {**base, "experiment": "revocation", "event": ev, "target": tid, "victim": victim,
                "revocation_type": kind}
        session = f"ev{ev}-main"

        # Warm-up: authorized use that leaves copies in the cache, memory and summary.
        client.ask(victim, session, qa[0]["question"], phase="warm", **tags)
        for q in fillers:
            client.ask(victim, session, q, phase="warm", **tags)
        client.ask(victim, session, qa[1 % len(qa)]["question"], phase="warm", **tags)

        clock.advance(gap)
        t_rev = clock.now()
        _revoke(pipe, kind, victim, target)

        recall_q = f"Remind me what you told me earlier about {target['topic']} and its figures."
        for t in probe_times:
            wait = t_rev + t - clock.now()
            if wait > 0:
                clock.advance(wait)
            has = pipe.acm.has_access(victim, tid)
            ptags = {**tags, "phase": "probe", "probe_t": t, "has_access": has}
            client.ask(victim, session, recall_q, probe_kind="same_session", **ptags)
            client.ask(victim, f"ev{ev}-t{int(t)}", qa[0]["question"], probe_kind="new_session", **ptags)


# ---- Twin-world existence inference (RQ3) ------------------------------------------

def run_existence(pipe: RAGPipeline, client: Client, cell: dict, rng: random.Random, base: dict) -> None:
    corpus = pipe.corpus
    targets = corpus.restricted(cell.get("tenants"))
    per_tenant: Optional[int] = cell.get("targets_per_tenant")
    if per_tenant:
        chosen = []
        for t in corpus.tenants():
            pool = [d for d in targets if d["tenant_id"] == t]
            chosen += rng.sample(pool, min(per_tenant, len(pool)))
        targets = chosen
    attackers = cell.get("attackers", ["insider", "outsider"])
    p_warm = float(cell.get("victim_warmup", 0.5))

    for target in targets:
        tid, tenant = target["doc_id"], target["tenant_id"]
        publics = [d for d in corpus.docs if d["tenant_id"] == tenant and d["sensitivity"] == "public"]
        public_topic = rng.choice(publics)["topic"]
        probes = make_probes(target, public_topic)
        pipe.reset()
        holders = sorted(pipe.acm.users_with_access(tid))
        victim = rng.choice(holders)
        warm = rng.random() < p_warm
        gap = rng.uniform(1, 300)
        insider_pool = [u["user_id"] for u in corpus.users_of(tenant) if u["user_id"] not in holders]
        outsider_pool = [u["user_id"] for u in corpus.iam["users"] if u["tenant_id"] != tenant]
        picks = {"insider": rng.choice(insider_pool), "outsider": rng.choice(outsider_pool)}

        for world in (1, 0):
            for kind in attackers:
                pipe.reset()
                if world == 0:
                    pipe.index.remove_docs([tid])
                tags = {**base, "experiment": "existence", "target": tid, "tenant": tenant, "world": world,
                        "attacker": kind, "victim_warm": warm}
                if warm:
                    client.ask(victim, f"victim-{tid}", target["qa"][0]["question"], phase="warm", **tags)
                    _wait(pipe.clock, gap)
                user = picks[kind]
                for p in probes:
                    client.ask(user, f"atk-{tid}-{kind}-{world}", p.query, phase="probe",
                               strategy=p.strategy, probe_query=p.query, **tags)


# ---- Utility and cost (RQ5) ------------------------------------------------------------

def run_utility(pipe: RAGPipeline, client: Client, cell: dict, rng: random.Random, base: dict) -> None:
    corpus = pipe.corpus
    n = int(cell.get("queries", 100))
    pipe.reset()
    docs = rng.sample(corpus.docs, min(n, len(corpus.docs)))
    for i, doc in enumerate(docs):
        holders = sorted(pipe.acm.users_with_access(doc["doc_id"]))
        qa = rng.choice(doc["qa"])
        first, second = rng.choice(holders), rng.choice(holders)
        tags = {**base, "experiment": "utility", "doc": doc["doc_id"], "sensitivity": doc["sensitivity"],
                "answer": qa["answer"]}
        q = qa["question"]
        client.ask(first, f"u{i}-a", q, phase="first", **tags)
        _wait(pipe.clock, rng.uniform(1, 120))
        client.ask(second, f"u{i}-b", "Could you tell me " + q[0].lower() + q[1:], phase="repeat", **tags)
