"""real_stack_demo.py -- Post-revocation leakage in an unmodified open-source RAG stack (audit H4.3).

The application is built only from documented library defaults:
  - Chroma (chromadb) as the vector store, with an ACL filter evaluated against the *live* identity
    system on every retrieval, so the index itself never serves a revoked document;
  - a LangChain agent (`create_agent`) with a retrieval tool, `SummarizationMiddleware` for chat
    memory and an `InMemorySaver` checkpointer for sessions;
  - a RedisVL `SemanticCache` in front of the agent, scoped per user with a tag filter (the
    documented way to keep users' cached answers apart).

For each target (a restricted Enron e-mail with canary, from data/enron_c) the victim warms up in
one session, loses the target's group in the identity system, and then probes:
  cache      fresh session, same question            -> RedisVL returns the stored answer (T2)
  memory     same session, "remind me", cache bypass  -> answered from the LangChain summary (T3)
  control    fresh session, same question, cache bypass -> retrieval is denied, nothing leaks
A secret is disclosed when a corpus-unique fact value or the canary appears in the response
(`judge.disclosed`, mode "unique"); `judge` also counts paraphrases accepted by the model judge
(Enron answers are long phrases, which models reword). Every answer is saved for hand checking.

Needs Redis 8 (or Redis Stack) on localhost:6379 and Ollama with the model below:
  docker run -d --name afterimage-redis -p 6379:6379 redis:8
  python scripts/real_stack_demo.py --model qwen2.5:7b --targets 5
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chromadb  # noqa: E402
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction  # noqa: E402
from langchain.agents import create_agent  # noqa: E402
from langchain.agents.middleware import SummarizationMiddleware  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langchain_ollama import ChatOllama  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from redisvl.extensions.cache.llm import SemanticCache  # noqa: E402
from redisvl.query.filter import Tag  # noqa: E402
from redisvl.utils.vectorize import HFTextVectorizer  # noqa: E402

from src.secure_pipeline.corpus import corpus_dir, load_corpus  # noqa: E402
from src.secure_pipeline.clock import SimClock  # noqa: E402
from src.secure_pipeline.judge import LLMJudge, disclosed  # noqa: E402
from src.secure_pipeline.llm_client import LLMClient  # noqa: E402

EMBED = "sentence-transformers/all-MiniLM-L6-v2"
SYSTEM = ("You are a company assistant. Use the search_documents tool to answer questions about "
          "company e-mails and documents. Answer briefly and include the specific names, numbers "
          "and codes you find.")


# ---- Application -----------------------------------------------------------------------
class App:
    """Chroma + LangChain agent with summary memory + per-user RedisVL semantic cache."""

    def __init__(self, corpus, tenant: str, groups: dict[str, set[str]], model: str):
        self.corpus, self.groups, self.user = corpus, groups, ""
        client = chromadb.EphemeralClient()
        self.col = client.create_collection("demo", embedding_function=SentenceTransformerEmbeddingFunction(EMBED))
        docs = [d for d in corpus.docs if d["tenant_id"] == tenant]
        self.col.add(ids=[d["doc_id"] for d in docs],
                     documents=[f"{d['title']}\n{d['text']}" for d in docs],
                     metadatas=[{"doc_id": d["doc_id"], **{f"grp__{g}": True for g in d["acl_groups"]}}
                                for d in docs])

        @tool
        def search_documents(query: str) -> str:
            """Search the company documents the current user may read."""
            allowed = [{f"grp__{g}": True} for g in self.groups[self.user]]
            where = allowed[0] if len(allowed) == 1 else {"$or": allowed}
            r = self.col.query(query_texts=[query], n_results=3, where=where)
            self.last_sources += r["ids"][0]
            return "\n\n".join(r["documents"][0]) or "No documents found."

        llm = ChatOllama(model=model, temperature=0)
        self.agent = create_agent(
            llm, tools=[search_documents], system_prompt=SYSTEM, checkpointer=InMemorySaver(),
            middleware=[SummarizationMiddleware(model=llm, trigger=("messages", 8), keep=("messages", 4))])
        self.cache = SemanticCache(name="afterimage_demo", distance_threshold=0.1, ttl=3600,
                                   vectorizer=HFTextVectorizer(model=EMBED), overwrite=True,
                                   filterable_fields=[{"name": "user", "type": "tag"}])
        self.cache.clear()
        self.last_sources: list[str] = []

    def ask(self, user: str, session: str, question: str, use_cache: bool = True) -> dict:
        self.user, self.last_sources = user, []
        if use_cache:
            hit = self.cache.check(prompt=question, filter_expression=Tag("user") == user)
            if hit:
                return {"answer": hit[0]["response"], "cache_hit": True, "sources": []}
        out = self.agent.invoke({"messages": [{"role": "user", "content": question}]},
                                {"configurable": {"thread_id": session}})
        answer = out["messages"][-1].content
        if use_cache:
            self.cache.store(prompt=question, response=answer, filters={"user": user})
        return {"answer": answer, "cache_hit": False, "sources": list(self.last_sources)}

    def summary(self, session: str) -> str:
        msgs = self.agent.get_state({"configurable": {"thread_id": session}}).values.get("messages", [])
        return "\n".join(m.content for m in msgs if m.additional_kwargs.get("lc_source") == "summarization")


def _n(d) -> int:
    """Secrets disclosed: corpus-unique fact values plus the canary."""
    return len(d.facts) + d.canary


# ---- Experiment ------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--corpus", default="enron_c")
    ap.add_argument("--tenant", default="e1")
    ap.add_argument("--targets", type=int, default=5)
    ap.add_argument("--judge-model", default="qwen2.5:7b")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "real_stack_demo")
    args = ap.parse_args()

    corpus = load_corpus(corpus_dir(args.corpus))
    rng = random.Random(args.seed)
    iam = {u["user_id"]: set(u["groups"]) for u in corpus.users_of(args.tenant)}
    app = App(corpus, args.tenant, iam, args.model)
    judge = LLMJudge(LLMClient("ollama", SimClock(), random.Random(0), model=args.judge_model))

    targets = [d for d in corpus.restricted([args.tenant]) if corpus.unique_facts(d["doc_id"]) and d.get("qa")]
    rng.shuffle(targets)
    rows = []
    for i, target in enumerate(targets[:args.targets]):
        group = target["acl_groups"][0]
        iam.update({u["user_id"]: set(u["groups"]) for u in corpus.users_of(args.tenant)})  # undo last revocation
        victim = sorted(u for u, g in iam.items() if group in g)[0]
        kept = [d for d in corpus.docs if d["tenant_id"] == args.tenant and d["qa"]
                and group not in d["acl_groups"] and set(d["acl_groups"]) & iam[victim]]
        fillers = rng.sample(kept, 3)
        q = target["qa"][0]["question"]
        session = f"t{i}-main"
        print(f"[demo] target {target['doc_id']} victim {victim} group {group}", flush=True)

        warm = [app.ask(victim, session, q)]
        warm += [app.ask(victim, session, f["qa"][0]["question"]) for f in fillers]
        warm.append(app.ask(victim, session, f"Thanks. And once more: {q}"))
        shown = " ".join(w["answer"] for w in warm)
        summary = app.summary(session)

        iam[victim].discard(group)  # revocation in the identity system; retrieval sees it at once

        probes = {
            "cache": app.ask(victim, f"t{i}-fresh", q),
            "memory": app.ask(victim, session, f"Remind me what you told me earlier about {target['topic']}.",
                              use_cache=False),
            "control": app.ask(victim, f"t{i}-control", q, use_cache=False),
        }
        row = {"target": target["doc_id"], "victim": victim, "question": q,
               "warmup_disclosed": _n(disclosed(corpus, target["doc_id"], shown, [])),
               "summary_written": bool(summary),
               "summary_disclosed": _n(disclosed(corpus, target["doc_id"], summary, [], llm_judge=judge)),
               "summary": summary,
               "scorable": len(corpus.unique_facts(target["doc_id"])) + 1}
        for name, p in probes.items():
            d = disclosed(corpus, target["doc_id"], p["answer"], [])
            dj = disclosed(corpus, target["doc_id"], p["answer"], [], llm_judge=judge)
            row[name] = {"disclosed": _n(d), "judge": _n(dj), "canary": d.canary, "cache_hit": p["cache_hit"],
                         "retrieved_target": target["doc_id"] in p["sources"], "answer": p["answer"]}
            print(f"[demo]   {name:8s} exact={_n(d)} judge={_n(dj)} cache_hit={p['cache_hit']} "
                  f"retrieved_target={target['doc_id'] in p['sources']}", flush=True)
        rows.append(row)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "demo.json").write_text(json.dumps({"model": args.model, "corpus": args.corpus, "rows": rows},
                                                   indent=2), encoding="utf-8")
    n = len(rows)
    for name in ("cache", "memory", "control"):
        k = sum(r[name]["disclosed"] > 0 for r in rows)
        kj = sum(r[name]["judge"] > 0 for r in rows)
        print(f"[demo] {name:8s} leaked in {k}/{n} targets (exact), {kj}/{n} (with model judge)")
    print(f"[demo] summaries holding a secret: {sum(r['summary_disclosed'] > 0 for r in rows)}/{n}; "
          f"wrote {args.out / 'demo.json'}")


if __name__ == "__main__":
    main()
