#!/usr/bin/env python3
"""
make_paraphrases.py -- Natural rewordings of every target question, for probe_paraphrase: file.

The revocation experiment's reworded probes used seven hand-written templates, so the cache
threshold sweep was a step function of those templates (audit H2). This script asks a real
model to rephrase each question the way different users would, and stores the result in
data/paraphrases.json ({question: [rewording, ...]}). The experiment then picks one rewording
per event by event index, so cells stay paired.

    python scripts/make_paraphrases.py --backend ollama --model llama3.1:8b \
        --corpus synthetic_v3_s0 synthetic_v3_s1 synthetic_v3_s2 synthetic_v3_s3 synthetic_v3_s4 enron_c

Name every corpus a run uses: with corpus: synthetic_v3@seed each seed has its own corpus and its
own questions. Questions of every document are covered, since a role, mover or offboarding
revocation probes lost filler documents too. The experiment raises on a missing question, so rerun
this script until it reports "0 questions still missing". A reply that is not a JSON list is retried
with a reworded instruction (--attempts variants); failed replies are cached, so a rerun only helps
with a higher --attempts. Questions still without rewordings are listed at the end.

Generations go through the LLM disk cache, so a rerun is free; commit data/paraphrases.json with
the results.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.secure_pipeline.clock import SimClock  # noqa: E402
from src.secure_pipeline.corpus import corpus_dir, load_corpus  # noqa: E402
from src.secure_pipeline.llm_client import LLMClient  # noqa: E402

PROMPT = (
    "Rewrite the question below {n} times, the way {n} different employees might type it into a "
    "company chat assistant: vary wording, length and politeness, keep the meaning and every name "
    "exactly, and do not add facts. Return a JSON list of strings and nothing else.\n\nQuestion: {q}"
)


def rewordings(llm: LLMClient, question: str, n: int, attempts: int = 3) -> list[str]:
    for attempt in range(attempts):
        # A different suffix per attempt gives a different disk-cache key, so a retry is a new call.
        suffix = "" if attempt == 0 else f"\n\nAttempt {attempt + 1}: reply with a valid JSON list of strings only."
        text = llm.complete([{"role": "user", "content": PROMPT.format(n=n, q=question) + suffix}]).text
        start, end = text.find("["), text.rfind("]")
        try:
            out = json.loads(text[start:end + 1])
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(out, list):
            good = [s.strip() for s in out if isinstance(s, str) and s.strip() and s.strip() != question][:n]
            if good:
                return good
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="ollama")
    ap.add_argument("--model")
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--scope", choices=["all", "restricted"], default="all",
                    help="questions of every document (default) or of restricted documents only")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--workers", type=int, default=1, help="concurrent requests to the server")
    ap.add_argument("--attempts", type=int, default=3,
                    help="instruction variants per question; failed replies are cached, so raise this "
                         "(3, 6, 9, ...) to give still-missing questions new attempts on a rerun")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "paraphrases.json")
    args = ap.parse_args()

    llm = LLMClient(args.backend, SimClock(), random.Random(0), model=args.model)
    bank = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    def docs(name):
        corpus = load_corpus(corpus_dir(name))
        return corpus.docs if args.scope == "all" else corpus.restricted()
    questions = sorted({x["question"] for name in args.corpus for d in docs(name) for x in d["qa"]})
    missing = [q for q in questions if q not in bank]
    print(f"[paraphrase] {len(questions)} questions, {len(missing)} to generate")
    # Questions are independent; threads only overlap the server round trips (results in order).
    pool = ThreadPoolExecutor(args.workers)
    for i, (q, options) in enumerate(zip(missing, pool.map(lambda q: rewordings(llm, q, args.n, args.attempts), missing)), 1):
        if options:
            bank[q] = options
        if i % 50 == 0:
            args.out.write_text(json.dumps(bank, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"[paraphrase] {i}/{len(missing)}")
    args.out.write_text(json.dumps(bank, indent=1, ensure_ascii=False), encoding="utf-8")
    still = [q for q in questions if q not in bank]
    print(f"[paraphrase] wrote {len(bank)} entries -> {args.out}; {len(still)} questions still missing")
    for q in still[:20]:
        print(f"[paraphrase]   missing: {q}")


if __name__ == "__main__":
    main()
