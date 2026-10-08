#!/usr/bin/env python3
"""
build_enron_corpus.py -- Real-text track: turn EnronQA emails into the testbed's corpus schema.

Source: EnronQA (Ryan et al., 2025, arXiv:2505.00263), Hugging Face MichaelR207/enron_qa_0922.
The train, dev and test splits hold different questions about the same emails (same order), so
all three are merged per email. Needs pyarrow. Writes data/enron/corpus.jsonl and iam.json.

Mapping (the tenancy is ours; the text, questions and answers are real):
- 10 inboxes, two per tenant, 5 tenants. Each inbox owner has an assistant (delegate).
- An email addressed to few people is restricted to its inbox group {owner, assistant}.
  Mass mail (newsletters, many recipients) is internal to the tenant, which gives the
  revocation experiment its authorized filler documents.
- Facts are short spans (numbers, amounts, quoted strings, proper names) taken from the gold answers that
  appear verbatim in the email and not in the question, so the exact-match judge applies.
  Emails without such a span are dropped. There are no canaries.
- Emails in the same thread (same normalized subject in an inbox) share a project, which gives
  twin-world existence inference hard negatives, as in the synthetic corpus.

    python scripts/build_enron_corpus.py            # deterministic, seed 20261008
"""

from __future__ import annotations

import glob
import json
import random
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "enron"
SEED = 20261008
N_INBOXES, RESTRICTED_PER_INBOX, INTERNAL_PER_INBOX = 10, 50, 15

_QUOTED = re.compile(r'"([^"]{3,60})"')
_NAME = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:of\s+)?[A-Z][a-z]+){1,3}\b")
_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?(?:\s?(?:million|billion|MW|MWh|mmbtu|Bcf|cents))?")


def facts_of(email: str, questions, answers) -> tuple[list[dict], list[dict]]:
    """(facts, qa) for one email; one QA pair per question whose answer yields a span."""
    body = email.split("=====================================", 1)[-1]
    facts, qa, seen = [], [], set()
    for q, a in zip(questions, answers):
        spans = [s.strip() for s in _QUOTED.findall(a) + _NUMBER.findall(a) + _NAME.findall(a)]
        # Bare years recur in every email header and prove nothing.
        spans = [s for s in spans if len(s) >= 3 and s in body and s not in q and not re.fullmatch(r"(19|20)\d\d", s)]
        if not spans:
            continue
        span = max(spans, key=len)
        qa.append({"question": q, "answer": span})
        if span not in seen:
            seen.add(span)
            facts.append({"key": f"answer {len(facts) + 1}", "value": span})
    return facts, qa


def header(email: str, field: str) -> str:
    m = re.search(rf"^{field}: (.*)$", email, re.M)
    return m.group(1).strip() if m else ""


def thread_key(subject: str) -> str:
    return re.sub(r"^((re|fw|fwd)\s*:\s*)+", "", subject.lower()).strip()


def main() -> None:
    import pandas as pd
    files = sorted(glob.glob(str(ROOT / ".cache/hf/datasets--MichaelR207--enron_qa_0922/snapshots/*/data/*.parquet")))
    if len(files) < 4:
        raise SystemExit("download first: huggingface_hub.snapshot_download('MichaelR207/enron_qa_0922', "
                         "repo_type='dataset', cache_dir='.cache/hf')")
    parts = [pd.read_parquet(f, columns=["path", "email", "questions", "gold_answers", "user"]) for f in files]
    df = pd.concat(parts).groupby("path", sort=True).agg(
        email=("email", "first"), user=("user", "first"),
        questions=("questions", lambda x: [q for qs in x for q in qs]),
        gold_answers=("gold_answers", lambda x: [a for ans in x for a in ans]))

    by_user: dict[str, list[dict]] = defaultdict(list)
    for email, qs, ans, user in zip(df.email, df.questions, df.gold_answers, df.user):
        facts, qa = facts_of(email, list(qs), list(ans))
        if not facts or len(email) > 6000:
            continue
        subject = header(email, "Subject") or "(no subject)"
        recipients = header(email, "Recipients").count("@")
        sender = header(email, "Sender")
        mass = recipients >= 6 or not sender.endswith("@enron.com")
        by_user[user].append({"email": email, "facts": facts, "qa": qa, "subject": subject, "mass": mass})

    rng = random.Random(SEED)
    eligible = sorted(u for u, es in by_user.items()
                      if sum(not e["mass"] for e in es) >= RESTRICTED_PER_INBOX
                      and sum(e["mass"] for e in es) >= INTERNAL_PER_INBOX)
    inboxes = sorted(rng.sample(eligible, N_INBOXES))
    print(f"[enron] {len(eligible)} eligible inboxes, using {inboxes}")

    docs, users, groups = [], [], {}
    tenants = []
    for t_i in range(N_INBOXES // 2):
        tid = f"e{t_i + 1}"
        pair = inboxes[2 * t_i: 2 * t_i + 2]
        tenants.append({"tenant_id": tid, "name": f"Enron desk {t_i + 1}", "industry": "energy", "hq": "Houston, TX"})
        members = []
        for owner in pair:
            name = owner.split("-")[0]
            owner_id, assistant_id = f"{tid}_{name}", f"{tid}_{name}_asst"
            groups[f"{tid}_{name}_inbox"] = [owner_id, assistant_id]
            members += [owner_id, assistant_id]
            restricted = rng.sample([e for e in by_user[owner] if not e["mass"]], RESTRICTED_PER_INBOX)
            internal = rng.sample([e for e in by_user[owner] if e["mass"]], INTERNAL_PER_INBOX)
            threads = defaultdict(list)
            for e in restricted:
                threads[thread_key(e["subject"])].append(e)
            for kind, emails in (("restricted", restricted), ("internal", internal)):
                for e in emails:
                    doc_id = f"{tid}_{name}_{len(docs):04d}"
                    shared = kind == "restricted" and len(threads[thread_key(e["subject"])]) > 1
                    body = "\n".join(l for l in e["email"].splitlines() if not l.startswith("File: "))
                    topic = thread_key(e["subject"])[:60] or "(no subject)"
                    docs.append({
                        "doc_id": doc_id, "tenant_id": tid, "title": f"{e['subject'][:80]} -- email",
                        "sensitivity": kind,
                        "acl_groups": [f"{tid}_{name}_inbox"] if kind == "restricted" else [f"{tid}_all"],
                        "topic": topic, "project": f"{tid}_{name}:{topic}" if shared else None,
                        "facts": e["facts"], "canary": None, "qa": e["qa"], "text": body,
                    })
        colleagues = [f"{tid}_colleague{i}" for i in (1, 2)]
        contractors = [f"{tid}_contractor{i}" for i in (1, 2)]
        groups[f"{tid}_all"] = members + colleagues + contractors
        groups[f"{tid}_staff"] = members + colleagues
        for u in members + colleagues + contractors:
            users.append({"user_id": u, "tenant_id": tid, "role": "contractor" if u in contractors else "employee",
                          "groups": sorted(g for g, ms in groups.items() if u in ms)})

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "corpus.jsonl").open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    (OUT / "iam.json").write_text(json.dumps({"tenants": tenants, "users": users, "groups": groups}, indent=2),
                                  encoding="utf-8")
    n_r = sum(d["sensitivity"] == "restricted" for d in docs)
    print(f"[enron] wrote {len(docs)} docs ({n_r} restricted), {len(users)} users -> {OUT}")


if __name__ == "__main__":
    main()
