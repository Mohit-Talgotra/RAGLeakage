#!/usr/bin/env python3
"""
generate_enron_corpus.py -- Real-text track: transform EnronQA emails into Afterimage schema.

Dataset: EnronQA (Ryan et al., 2025, arXiv:2505.00263; HF: MichaelR207/enron_qa_0922).
License: CC BY 4.0 (Creative Commons Attribution 4.0 International).
Original Enron email repository: Public domain (released by FERC).

Writes:
  data_enron/corpus.jsonl (and data/enron/corpus.jsonl)
  data_enron/iam.json     (and data/enron/iam.json)

Schema per document:
  - doc_id: str
  - tenant_id: str (e1..e5)
  - title: str
  - sensitivity: "restricted" (30%) or "internal" (70%)
  - acl_groups: list[str]
  - topic: str
  - project: str | None
  - facts: list[{"key": str, "value": str}] -- verbatim spans appearing in thread and nowhere else in tenant
  - canary: str | None (inserted into restricted threads)
  - qa: list[{"question": str, "answer": str}]
  - text: str (with canary embedded for restricted documents)
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import glob
import json
from pathlib import Path
import random
import re

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data_enron"
ENRON_DATA_DIR = ROOT / "data" / "enron"
SEED = 20261008

_QUOTED = re.compile(r'"([^"]{3,60})"')
_NAME = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:of\s+)?[A-Z][a-z]+){1,3}\b")
_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?(?:\s?(?:million|billion|MW|MWh|mmbtu|Bcf|cents))?")


def header(email: str, field: str) -> str:
    m = re.search(rf"^{field}: (.*)$", email, re.M)
    return m.group(1).strip() if m else ""


def thread_key(subject: str) -> str:
    return re.sub(r"^((re|fw|fwd)\s*:\s*)+", "", subject.lower()).strip()


def extract_candidate_facts(email: str, questions: list[str], answers: list[str]) -> tuple[list[dict], list[dict]]:
    body = email.split("=====================================", 1)[-1]
    facts, qa, seen = [], [], set()
    for q, a in zip(questions, answers):
        spans = [s.strip() for s in _QUOTED.findall(a) + _NUMBER.findall(a) + _NAME.findall(a)]
        spans = [s for s in spans if len(s) >= 3 and s in body and s not in q and not re.fullmatch(r"(19|20)\d\d", s)]
        if not spans:
            continue
        span = max(spans, key=len)
        qa.append({"question": q, "answer": span})
        if span not in seen:
            seen.add(span)
            facts.append({"key": f"answer {len(facts) + 1}", "value": span})
    return facts, qa


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory")
    ap.add_argument("--also-write-data-enron", action="store_true", default=True,
                    help="Also write to data/enron for backward compatibility")
    args = ap.parse_args()

    import pandas as pd
    pattern = str(ROOT / ".cache/hf/datasets--MichaelR207--enron_qa_0922/snapshots/*/data/*.parquet")
    files = sorted(glob.glob(pattern))
    if len(files) < 4:
        raise SystemExit(
            "Dataset parquet files not found. Run download first: "
            "from huggingface_hub import snapshot_download; snapshot_download('MichaelR207/enron_qa_0922', cache_dir='.cache/hf')"
        )

    print(f"[enron] Loading {len(files)} parquet files with fastparquet...")
    parts = []
    for f in files:
        df_part = pd.read_parquet(f, columns=["path", "email", "questions", "gold_answers", "user"], engine="fastparquet")
        parts.append(df_part)

    df = pd.concat(parts).groupby("path", sort=True).agg(
        email=("email", "first"),
        user=("user", "first"),
        questions=("questions", lambda x: [q for qs in x for q in qs]),
        gold_answers=("gold_answers", lambda x: [a for ans in x for a in ans])
    )

    by_user: dict[str, list[dict]] = defaultdict(list)
    for email, qs, ans, user in zip(df.email, df.questions, df.gold_answers, df.user):
        facts, qa = extract_candidate_facts(email, list(qs), list(ans))
        if not facts or len(email) > 6000:
            continue
        subject = header(email, "Subject") or "(no subject)"
        recipients = header(email, "Recipients").count("@")
        sender = header(email, "Sender")
        mass = recipients >= 6 or not sender.endswith("@enron.com")
        by_user[user].append({"email": email, "facts": facts, "qa": qa, "subject": subject, "mass": mass})

    rng = random.Random(SEED)
    N_INBOXES = 10
    RESTRICTED_PER_INBOX = 50
    INTERNAL_PER_INBOX = 15

    eligible = sorted(
        u for u, es in by_user.items()
        if sum(not e["mass"] for e in es) >= RESTRICTED_PER_INBOX
        and sum(e["mass"] for e in es) >= INTERNAL_PER_INBOX
    )
    inboxes = sorted(rng.sample(eligible, N_INBOXES))
    print(f"[enron] Selected {len(inboxes)} inboxes across 5 tenants: {inboxes}")

    departments = [
        ("Trading Desk", "energy_trading"),
        ("Legal & Regulatory Affairs", "legal_regulatory"),
        ("Pipeline Operations", "infrastructure"),
        ("Finance & Risk Management", "finance_risk"),
        ("Executive & Strategy", "executive_strategy"),
    ]

    docs, users, groups, tenants = [], [], {}, []

    for t_i in range(N_INBOXES // 2):
        tid = f"e{t_i + 1}"
        pair = inboxes[2 * t_i: 2 * t_i + 2]
        dept_name, industry = departments[t_i]
        tenants.append({
            "tenant_id": tid,
            "name": f"Enron {dept_name}",
            "industry": industry,
            "hq": "Houston, TX"
        })

        members = []
        tenant_docs = []

        for owner in pair:
            name = owner.split("-")[0]
            owner_id = f"{tid}_{name}"
            assistant_id = f"{tid}_{name}_asst"
            inbox_group = f"{tid}_{name}_inbox"
            groups[inbox_group] = [owner_id, assistant_id]
            members += [owner_id, assistant_id]

            restricted_emails = rng.sample([e for e in by_user[owner] if not e["mass"]], RESTRICTED_PER_INBOX)
            internal_emails = rng.sample([e for e in by_user[owner] if e["mass"]], INTERNAL_PER_INBOX)

            threads = defaultdict(list)
            for e in restricted_emails:
                threads[thread_key(e["subject"])].append(e)

            for kind, emails in (("restricted", restricted_emails), ("internal", internal_emails)):
                for e in emails:
                    doc_id = f"{tid}_{name}_{len(docs) + len(tenant_docs):04d}"
                    shared = kind == "restricted" and len(threads[thread_key(e["subject"])]) > 1
                    body = "\n".join(l for l in e["email"].splitlines() if not l.startswith("File: "))
                    topic = thread_key(e["subject"])[:60] or "(no subject)"

                    # Generate and embed canary for restricted documents
                    canary = None
                    if kind == "restricted":
                        canary = f"codename QX-{rng.randint(1000, 9999)}"
                        body = f"{body}\n\nSecurity Notice: Project codename is {canary}."

                    tenant_docs.append({
                        "doc_id": doc_id,
                        "tenant_id": tid,
                        "title": f"{e['subject'][:80]} -- email",
                        "sensitivity": kind,
                        "acl_groups": [inbox_group] if kind == "restricted" else [f"{tid}_all"],
                        "topic": topic,
                        "project": f"{tid}_{name}:{topic}" if shared else None,
                        "candidate_facts": e["facts"],
                        "canary": canary,
                        "qa": e["qa"],
                        "text": body,
                    })

        # Tenant-wide uniqueness filtering for facts
        # Requirement: "keep only EnronQA answers that are exact strings appearing verbatim in their thread and nowhere else in that tenant"
        for i, doc in enumerate(tenant_docs):
            other_bodies = " ".join(d["text"] for j, d in enumerate(tenant_docs) if j != i)
            valid_facts = []
            for f in doc["candidate_facts"]:
                val = f["value"]
                # Must appear in this doc and NOT in any other doc of this tenant
                if val in doc["text"] and val not in other_bodies:
                    valid_facts.append(f)
            doc["facts"] = valid_facts
            del doc["candidate_facts"]
            docs.append(doc)

        colleagues = [f"{tid}_colleague{i}" for i in (1, 2)]
        contractors = [f"{tid}_contractor{i}" for i in (1, 2)]
        groups[f"{tid}_all"] = members + colleagues + contractors
        groups[f"{tid}_staff"] = members + colleagues

        for u in members + colleagues + contractors:
            users.append({
                "user_id": u,
                "tenant_id": tid,
                "role": "contractor" if u in contractors else "employee",
                "groups": sorted(g for g, ms in groups.items() if u in ms)
            })

    # Write output to target directory
    out_dirs = [args.out]
    if args.also_write_data_enron and ENRON_DATA_DIR != args.out:
        out_dirs.append(ENRON_DATA_DIR)

    for od in out_dirs:
        od.mkdir(parents=True, exist_ok=True)
        with (od / "corpus.jsonl").open("w", encoding="utf-8") as fh:
            for d in docs:
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        (od / "iam.json").write_text(
            json.dumps({"tenants": tenants, "users": users, "groups": groups}, indent=2),
            encoding="utf-8"
        )
        print(f"[enron] Wrote {len(docs)} documents ({sum(d['sensitivity'] == 'restricted' for d in docs)} restricted) -> {od}")

    print("[enron] Generation complete.")


if __name__ == "__main__":
    main()
