#!/usr/bin/env python3
"""
generate_corpus.py -- Build the frozen synthetic corpus v2 (data/corpus.jsonl, data/iam.json).

Deterministic: the same --seed always produces byte-identical files. The output is
committed so every experiment runs on exactly the same documents.

Corpus shape (per tenant):
- ~40 public docs     (group <t>_all: every tenant user)
- ~30 internal docs   (group <t>_staff: employees, not contractors)
- ~30 restricted docs (one department group each, e.g. <t>_finance)

Every document carries checkable facts (key/value pairs whose value appears verbatim
in the text) and question templates for utility queries. Every restricted document
also carries a unique random canary string ("codename QX-7731") so leakage can be
checked by exact match with zero ambiguity. Restricted documents are grouped into
projects (1-2 docs per codename), so a twin world that removes one document can still
contain a sibling document about the same project: negatives stay hard.

Usage:
    python scripts/generate_corpus.py            # writes data/corpus.jsonl, data/iam.json
    python scripts/generate_corpus.py --seed 7 --out data/
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

TENANTS = [
    {"tenant_id": "t1", "name": "Meridian Biopharma", "industry": "biopharma", "hq": "Cambridge, MA",
     "unit": "trial", "product": "therapy", "metric": "progression-free survival",
     "sites": ["Cambridge", "Basel", "Raleigh", "Singapore"]},
    {"tenant_id": "t2", "name": "Voltaic Systems", "industry": "energy", "hq": "Austin, TX",
     "unit": "field pilot", "product": "grid controller", "metric": "peak load reduction",
     "sites": ["Austin", "Denver", "Phoenix", "Calgary"]},
    {"tenant_id": "t3", "name": "Apex Financial", "industry": "fintech", "hq": "New York, NY",
     "unit": "backtest", "product": "trading engine", "metric": "risk-adjusted return",
     "sites": ["New York", "London", "Chicago", "Tokyo"]},
    {"tenant_id": "t4", "name": "Northwind Logistics", "industry": "logistics", "hq": "Rotterdam, NL",
     "unit": "route pilot", "product": "routing platform", "metric": "on-time delivery rate",
     "sites": ["Rotterdam", "Hamburg", "Memphis", "Shenzhen"]},
    {"tenant_id": "t5", "name": "Helix Retail", "industry": "retail", "hq": "Seattle, WA",
     "unit": "pricing pilot", "product": "storefront app", "metric": "basket conversion",
     "sites": ["Seattle", "Dallas", "Toronto", "Dublin"]},
]

FIRST_NAMES = [
    "Alice", "Bilal", "Chen", "Dana", "Emeka", "Farah", "Goran", "Hana", "Ivan", "Jia",
    "Kofi", "Lena", "Mateo", "Nadia", "Omar", "Priya", "Quinn", "Rosa", "Sven", "Tara",
    "Uma", "Victor", "Wen", "Ximena", "Yusuf", "Zoe", "Arjun", "Beatriz", "Cyrus", "Dmitri",
    "Elif", "Felix", "Grace", "Hugo", "Isla", "Jonas", "Keiko", "Luis", "Mira", "Nils",
]
LAST_NAMES = [
    "Okafor", "Lindqvist", "Ramirez", "Tanaka", "Hale", "Ong", "Rao", "Novak", "Mensah", "Duarte",
    "Fischer", "Kowalski", "Haddad", "Iyer", "Brennan", "Sato", "Moreau", "Petrov", "Achebe", "Larsen",
]
CODENAMES = [
    "Kestrel", "Nightingale", "Osprey", "Harrier", "Falcon", "Merlin", "Peregrine", "Condor", "Heron",
    "Ibis", "Kingfisher", "Lapwing", "Magpie", "Nuthatch", "Oriole", "Plover", "Quail", "Raven",
    "Sandpiper", "Tern", "Warbler", "Avocet", "Bittern", "Curlew", "Dunlin", "Egret", "Fulmar",
    "Gannet", "Hobby", "Jacana", "Kittiwake", "Linnet", "Martin", "Nighthawk", "Ortolan", "Petrel",
    "Redstart", "Siskin", "Thrush", "Veery", "Wagtail", "Waxwing", "Basalt", "Cobalt", "Dolomite",
    "Feldspar", "Garnet", "Hematite", "Jasper", "Kyanite", "Lazuli", "Malachite", "Obsidian",
    "Pyrite", "Quartz", "Rhodium", "Spinel", "Topaz", "Vanadium", "Zircon", "Antares", "Bellatrix",
    "Capella", "Deneb", "Electra", "Fomalhaut", "Gemma", "Hadar", "Izar", "Kochab", "Lesath",
    "Mirach", "Nashira", "Polaris", "Rigel", "Sadr", "Tarazed", "Vega", "Wezen", "Zaniah",
    "Alder", "Birch", "Cedar", "Dogwood", "Elm", "Fir", "Ginkgo", "Hawthorn", "Juniper", "Larch",
    "Maple", "Oak", "Poplar", "Rowan", "Sequoia", "Tamarack", "Willow", "Yew", "Acacia", "Banyan",
    "Andes", "Baltic", "Caspian", "Danube", "Everest", "Fjord", "Glacier", "Hudson", "Indus", "Jura",
    "Kilimanjaro", "Ladoga", "Mekong", "Nile", "Orinoco", "Pamir", "Rhine", "Sahara", "Tigris", "Ural",
    "Volga", "Yukon", "Zambezi", "Aurora", "Blizzard", "Cyclone", "Drizzle", "Equinox", "Flurry",
    "Gale", "Halo", "Monsoon", "Nimbus", "Solstice", "Tempest", "Zephyr", "Anvil", "Bastion", "Citadel",
    "Lantern", "Meridian", "Paragon", "Quiver", "Rampart", "Sentinel", "Trident", "Vanguard", "Keystone",
]
PRODUCT_PREFIX = ["Core", "Flex", "Grid", "Prime", "Swift", "Clear", "Bright", "True", "Nova", "Pulse",
                  "Atlas", "Orbit", "Vector", "Summit", "Harbor", "Beacon", "Cascade", "Ember"]
PRODUCT_SUFFIX = ["Link", "Flow", "Desk", "Sense", "Hub", "Path", "Scope", "Stack", "Wave", "Point"]
COMPANY_WORDS = ["Privata", "Genova", "Zynecor", "Lumina", "Corvex", "Altrea", "Brightwell", "Quorra",
                 "Talvex", "Nimbra", "Ostara", "Velquin", "Sarnex", "Kyrene", "Dovetail", "Halcyon"]

RESTRICTED_GROUPS = ["finance", "legal", "rnd", "exec", "security", "hr"]


class Gen:
    """Seeded value factories. All facts are rendered as strings that appear verbatim in text."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self._canaries: set[str] = set()

    def money(self, lo: float, hi: float, unit: str = "M") -> str:
        v = self.rng.uniform(lo, hi)
        return f"${v:,.1f}{unit}"

    def dollars(self, lo: int, hi: int) -> str:
        return f"${self.rng.randrange(lo, hi, 100):,}"

    def pct(self, lo: float, hi: float) -> str:
        return f"{self.rng.uniform(lo, hi):.1f}%"

    def count(self, lo: int, hi: int) -> str:
        return f"{self.rng.randint(lo, hi):,}"

    def date(self) -> str:
        month = self.rng.choice(["January", "February", "March", "April", "May", "June", "July",
                                 "August", "September", "October", "November", "December"])
        return f"{month} {self.rng.randint(1, 28)}, {self.rng.choice([2026, 2027])}"

    def person(self) -> str:
        return f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"

    def code(self, prefix: str) -> str:
        return f"{prefix}-{self.rng.randint(100, 999)}"

    def canary(self) -> str:
        while True:
            letters = "".join(self.rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(2))
            c = f"codename {letters}-{self.rng.randint(1000, 9999)}"
            if c not in self._canaries:
                self._canaries.add(c)
                return c


# ---- Restricted document templates -------------------------------------------
# Each returns (title_suffix, group, facts[(key, value)], paragraphs, question templates).
# Question templates use {topic}; the answer is the fact value with the same index.

def r_program_results(g: Gen, t: dict, project: str):
    primary, control = g.pct(48, 78), g.pct(20, 46)
    n, budget = g.count(300, 2400), g.money(12, 140)
    hr = f"{g.rng.uniform(0.38, 0.79):.2f}"
    facts = [("primary result", primary), ("control result", control),
             ("enrolled sample size", n), ("program budget", budget), ("hazard ratio", hr)]
    paras = [
        f"This report summarises the interim {t['unit']} results for {project}, the lead "
        f"{t['product']} program at {t['name']}. Distribution is limited to the program steering committee.",
        f"The {t['unit']} enrolled {n} participants across {g.rng.choice(t['sites'])} and two partner sites. "
        f"The primary endpoint was {t['metric']} measured at month eighteen.",
        f"PRIMARY RESULT: the treatment arm reached {primary} versus {control} in the control arm "
        f"(hazard ratio {hr}). The steering committee considers the effect clinically and commercially material.",
        f"The remaining program budget is {budget}. Results must not be disclosed before the "
        f"scheduled public readout.",
    ]
    qs = ["What was the primary result of the {topic} {unit}?",
          "What was the control arm result in {topic}?",
          "How many participants were enrolled in {topic}?",
          "What is the budget of {topic}?",
          "What hazard ratio did {topic} report?"]
    return "Interim Results", "rnd", facts, paras, qs


def r_acquisition(g: Gen, t: dict, project: str):
    target = f"{g.rng.choice(COMPANY_WORDS)} {g.rng.choice(['Therapeutics', 'Systems', 'Labs', 'Analytics', 'Holdings'])}"
    lo = g.rng.uniform(0.3, 2.5)
    valuation = f"${lo:.1f}B to ${lo * g.rng.uniform(1.1, 1.5):.1f}B"
    synergy, close = g.money(20, 220), g.date()
    facts = [("acquisition target", target), ("valuation range", valuation),
             ("expected synergies", synergy), ("target close date", close)]
    paras = [
        f"{project} is the internal codename for the proposed acquisition of {target}. "
        f"This memo is restricted to the corporate development and legal teams.",
        f"Advisors value the target at {valuation} on a cash-free, debt-free basis. "
        f"Expected annual run-rate synergies are {synergy} by year three.",
        f"The board has authorised exclusivity talks. The target close date is {close}, "
        f"subject to regulatory approval in two jurisdictions.",
    ]
    qs = ["Which company is {topic} planning to acquire?",
          "What is the valuation range for {topic}?",
          "What synergies are expected from {topic}?",
          "When is {topic} expected to close?"]
    return "Acquisition Assessment", "exec", facts, paras, qs


def r_security(g: Gen, t: dict, project: str):
    vuln = g.code("CVF-2026")
    cvss = f"{g.rng.uniform(7.0, 9.9):.1f}"
    affected, patch = g.count(40, 4000), f"v{g.rng.randint(2, 9)}.{g.rng.randint(0, 20)}.{g.rng.randint(1, 9)}"
    facts = [("vulnerability id", vuln), ("CVSS score", cvss),
             ("affected systems", affected), ("patch version", patch)]
    paras = [
        f"Security incident review for {project}. The red team identified finding {vuln}: "
        f"hard-coded service credentials in the {t['product']} deployment images.",
        f"The finding is rated CVSS {cvss}. {affected} production systems are affected, "
        f"including hosts in {g.rng.choice(t['sites'])}.",
        f"Remediation ships in release {patch}. Until then, the incident is under embargo "
        f"and must not be discussed with customers.",
    ]
    qs = ["What vulnerability was found in {topic}?",
          "What is the CVSS score of the {topic} finding?",
          "How many systems are affected by {topic}?",
          "Which release patches {topic}?"]
    return "Security Incident Review", "security", facts, paras, qs


def r_comp(g: Gen, t: dict, project: str):
    p1, p2 = g.person(), g.person()
    c1, c2 = g.dollars(900_000, 9_000_000), g.dollars(500_000, 6_000_000)
    pool = g.money(4, 60)
    facts = [("top retention award", c1), ("second retention award", c2),
             ("total retention pool", pool), ("top award recipient", p1)]
    paras = [
        f"{project} is the confidential executive retention plan for fiscal 2026. "
        f"Awards vest over thirty-six months.",
        f"The largest award goes to {p1} at {c1}, followed by {p2} at {c2}. "
        f"The total retention pool is {pool}.",
        "The compensation committee approved the plan in closed session. Do not forward.",
    ]
    qs = ["How large is the biggest award under {topic}?",
          "What award does the second recipient get under {topic}?",
          "How large is the {topic} retention pool?",
          "Who receives the largest award under {topic}?"]
    return "Retention Plan", "hr", facts, paras, qs


def r_restructuring(g: Gen, t: dict, project: str):
    cuts, site = g.count(80, 1800), g.rng.choice(t["sites"])
    savings, date = g.money(15, 300), g.date()
    facts = [("planned role reductions", cuts), ("site to close", site),
             ("annual savings", savings), ("announcement date", date)]
    paras = [
        f"{project} outlines the operating-model restructuring for {t['name']}.",
        f"The plan removes {cuts} roles and closes the {site} site. "
        f"Projected annual savings are {savings}.",
        f"Employee communication is scheduled for {date}. Until then the plan is strictly need-to-know.",
    ]
    qs = ["How many roles will {topic} remove?",
          "Which site closes under {topic}?",
          "What savings does {topic} project?",
          "When will {topic} be announced?"]
    return "Restructuring Plan", "exec", facts, paras, qs


def r_litigation(g: Gen, t: dict, project: str):
    plaintiff = f"{g.rng.choice(COMPANY_WORDS)} {g.rng.choice(['Inc.', 'GmbH', 'LLC', 'plc'])}"
    exposure, reserve = g.money(10, 400), g.money(5, 120)
    odds = g.pct(15, 70)
    facts = [("opposing party", plaintiff), ("maximum exposure", exposure),
             ("litigation reserve", reserve), ("probability of loss", odds)]
    paras = [
        f"Privileged and confidential legal memo on {project}, the dispute with {plaintiff}.",
        f"Outside counsel estimates maximum exposure at {exposure} and a probability of loss of {odds}.",
        f"Finance has booked a reserve of {reserve}. This memo is protected by attorney-client privilege.",
    ]
    qs = ["Who is the opposing party in {topic}?",
          "What is the maximum exposure in {topic}?",
          "What reserve was booked for {topic}?",
          "What is the probability of loss in {topic}?"]
    return "Litigation Memo", "legal", facts, paras, qs


def r_forecast(g: Gen, t: dict, project: str):
    rev, margin = g.money(0.4, 6, "B"), g.pct(8, 42)
    capex, guidance = g.money(30, 600), g.pct(2, 19)
    facts = [("revenue forecast", rev), ("operating margin", margin),
             ("capital expenditure", capex), ("growth guidance", guidance)]
    paras = [
        f"{project} board forecast for the next fiscal year. Material non-public information.",
        f"Revenue is forecast at {rev} with an operating margin of {margin}. "
        f"Planned capital expenditure is {capex}.",
        f"Management will guide to {guidance} growth at the next earnings call. Trading window is closed.",
    ]
    qs = ["What revenue does {topic} forecast?",
          "What operating margin does {topic} project?",
          "What is the planned capex in {topic}?",
          "What growth guidance is planned in {topic}?"]
    return "Board Forecast", "finance", facts, paras, qs


def r_pricing(g: Gen, t: dict, project: str):
    price, discount = g.dollars(9_000, 90_000), g.pct(5, 35)
    floor, launch = g.dollars(2_000, 8_900), g.date()
    facts = [("list price", price), ("maximum discount", discount),
             ("price floor", floor), ("launch date", launch)]
    paras = [
        f"Pricing strategy for {project}, the next-generation {t['product']}.",
        f"List price is set at {price} per unit with a maximum approved discount of {discount}. "
        f"Sales may not quote below the floor of {floor}.",
        f"Launch is planned for {launch}. Competitors must not learn the price architecture before launch.",
    ]
    qs = ["What is the list price of {topic}?",
          "What is the maximum discount for {topic}?",
          "What is the price floor for {topic}?",
          "When does {topic} launch?"]
    return "Pricing Strategy", "finance", facts, paras, qs


RESTRICTED_TYPES = [r_program_results, r_acquisition, r_security, r_comp, r_restructuring,
                    r_litigation, r_forecast, r_pricing]

BOILERPLATE = [
    "Background: this document builds on prior steering committee discussions and supersedes earlier drafts. "
    "Readers should treat all numbers as preliminary until the final review has been completed and signed off. "
    "Questions should be routed to the document owner rather than discussed in open channels.",
    "Methodology: figures were compiled from the internal reporting warehouse using the standard quarterly "
    "close process. Adjustments for one-off items follow the group accounting manual. Rounding may cause "
    "totals to differ slightly from the sum of their parts.",
    "Distribution: access is limited to the named group in the document management system. Copies must not "
    "be stored on personal devices or shared with external parties without written approval from legal.",
]


# ---- Public and internal templates ---------------------------------------------

def p_product(g: Gen, t: dict, product: str):
    customers, uptime, year = g.count(40, 900), g.pct(99.0, 99.99), str(g.rng.randint(2015, 2024))
    facts = [("customer count", customers), ("uptime", uptime), ("launch year", year)]
    paras = [f"{product} is a {t['product']} offered by {t['name']}, launched in {year}.",
             f"{product} serves {customers} customers and reports {uptime} uptime over the last year.",
             f"Support for {product} is available from the {g.rng.choice(t['sites'])} office."]
    qs = ["How many customers use {topic}?", "What uptime does {topic} report?", "When was {topic} launched?"]
    return f"{product} Product Sheet", facts, paras, qs


def p_policy(g: Gen, t: dict, topic: str):
    limit, days = g.dollars(1_000, 9_000), str(g.rng.randint(5, 45))
    facts = [("approval limit", limit), ("submission deadline in days", days)]
    paras = [f"This page describes the {topic} at {t['name']}.",
             f"Expenses up to {limit} may be approved by a line manager. "
             f"Claims must be submitted within {days} days.",
             "Exceptions require written approval from the finance business partner."]
    qs = ["What is the approval limit in the {topic}?", "How many days do I have to submit under the {topic}?"]
    return topic.title(), facts, paras, qs


def p_site(g: Gen, t: dict, site: str):
    staff, area, opened = g.count(60, 2400), g.count(5_000, 90_000), str(g.rng.randint(1995, 2023))
    facts = [("site headcount", staff), ("floor area in square feet", area), ("opening year", opened)]
    paras = [f"The {site} office of {t['name']} opened in {opened}.",
             f"It hosts {staff} staff across {area} square feet of space.",
             "Visitors must register at reception and wear a badge at all times."]
    qs = ["How many staff work at the {topic}?", "How large is the {topic}?", "When did the {topic} open?"]
    return f"{site} Office Guide", facts, paras, qs


def p_press(g: Gen, t: dict, product: str):
    partner = f"{g.rng.choice(COMPANY_WORDS)} {g.rng.choice(['Group', 'Partners', 'Health', 'Energy', 'Capital'])}"
    value, date = g.money(2, 80), g.date()
    facts = [("partner", partner), ("contract value", value), ("announcement date", date)]
    paras = [f"{t['name']} announced a partnership with {partner} around {product} on {date}.",
             f"The multi-year agreement is valued at {value}.",
             f"\"We are excited to bring {product} to more customers,\" said a company spokesperson."]
    qs = ["Who is the {topic} partnership with?", "What is the value of the {topic} partnership?",
          "When was the {topic} partnership announced?"]
    return f"{product} Partnership Announcement", facts, paras, qs


def i_ops(g: Gen, t: dict, site: str):
    metric, backlog, q = g.pct(60, 98), g.count(10, 900), g.rng.choice(["Q1", "Q2", "Q3", "Q4"])
    facts = [(t["metric"], metric), ("ticket backlog", backlog)]
    paras = [f"Internal operations review for the {site} site, {q} 2026.",
             f"{t['metric'].capitalize()} was {metric} this quarter. The open ticket backlog stands at {backlog}.",
             "Actions: hire two additional coordinators and refresh the on-call rota."]
    qs = ["What was the " + t["metric"] + " at the {topic}?", "What is the ticket backlog at the {topic}?"]
    return f"{site} Operations Review {q} 2026", facts, paras, qs


def i_arch(g: Gen, t: dict, product: str):
    p50, p99, nodes = f"{g.rng.uniform(2, 40):.1f}ms", f"{g.rng.uniform(40, 400):.1f}ms", g.count(12, 900)
    facts = [("median latency", p50), ("p99 latency", p99), ("node count", nodes)]
    paras = [f"Engineering architecture note for {product}.",
             f"The service runs on {nodes} nodes with median latency {p50} and p99 latency {p99}.",
             "Next steps: migrate the message queue and retire the legacy batch scheduler."]
    qs = ["What is the median latency of {topic}?", "What is the p99 latency of {topic}?",
          "How many nodes does {topic} run on?"]
    return f"{product} Architecture Note", facts, paras, qs


def i_minutes(g: Gen, t: dict, team: str):
    owner, budget, date = g.person(), g.money(0.1, 4), g.date()
    facts = [("action owner", owner), ("approved budget", budget), ("next review date", date)]
    paras = [f"Minutes of the {team} team meeting.",
             f"The team approved a budget of {budget} for tooling. {owner} owns the follow-up actions.",
             f"Next review is on {date}."]
    qs = ["Who owns the actions from the {topic} meeting?", "What budget did the {topic} meeting approve?",
          "When is the next {topic} review?"]
    return f"{team} Team Meeting Minutes", facts, paras, qs


TEAMS = ["Platform", "Data", "Customer Success", "Procurement", "Facilities", "Quality", "Analytics",
         "Field Operations", "Developer Experience", "Partnerships", "Compliance Training", "IT Service Desk"]
POLICIES = ["travel policy", "expense policy", "remote work policy", "equipment policy", "training policy",
            "relocation policy", "conference policy", "mobile phone policy"]


def _doc(doc_id, tenant, title, sensitivity, groups, topic, facts, paras, qs, canary=None, project=None):
    text = "\n\n".join(paras)
    if canary:
        text += f"\n\nInternal reference: {canary}."
    for _, v in facts:
        assert v in text, (doc_id, v)
    qa = [{"question": q.replace("{topic}", topic).replace("{unit}", tenant["unit"]), "answer": v}
          for q, (_, v) in zip(qs, facts)]
    return {
        "doc_id": doc_id,
        "tenant_id": tenant["tenant_id"],
        "title": title,
        "sensitivity": sensitivity,
        "acl_groups": groups,
        "topic": topic,
        "project": project,
        "facts": [{"key": k, "value": v} for k, v in facts],
        "canary": canary,
        "qa": qa,
        "text": text,
    }


def build(seed: int, n_public: int, n_internal: int, n_restricted: int) -> tuple[list[dict], dict]:
    g = Gen(seed)
    codenames = CODENAMES[:]
    g.rng.shuffle(codenames)
    docs: list[dict] = []
    iam = {"tenants": [], "users": [], "groups": {}}

    for tenant in TENANTS:
        tid = tenant["tenant_id"]
        iam["tenants"].append({k: tenant[k] for k in ("tenant_id", "name", "industry", "hq")})

        # Users: 6 employees + 2 contractors. Each department group gets 1-2 employees.
        names = g.rng.sample(FIRST_NAMES, 8)
        users = [f"{tid}_{n.lower()}" for n in names]
        employees, contractors = users[:6], users[6:]
        groups = {f"{tid}_all": list(users), f"{tid}_staff": list(employees)}
        for i, dept in enumerate(RESTRICTED_GROUPS):
            members = {employees[i % 6]}
            if g.rng.random() < 0.5:
                members.add(employees[(i + 3) % 6])
            groups[f"{tid}_{dept}"] = sorted(members)
        iam["groups"].update(groups)
        for u in users:
            iam["users"].append({
                "user_id": u, "tenant_id": tid,
                "role": "contractor" if u in contractors else "employee",
                "groups": sorted(gr for gr, m in groups.items() if u in m),
            })

        # Product names unique within tenant.
        products = [f"{a}{b}" for a in PRODUCT_PREFIX for b in PRODUCT_SUFFIX]
        g.rng.shuffle(products)
        k = 0

        # Public docs.
        pub_makers = [("product", p_product), ("policy", p_policy), ("site", p_site), ("press", p_press)]
        used_sites = 0
        for i in range(n_public):
            kind, maker = pub_makers[i % len(pub_makers)]
            if kind == "policy":
                topic = f"{POLICIES[(i // 4) % len(POLICIES)]}"
                if i // 4 >= len(POLICIES):
                    topic = f"{tenant['sites'][(i // 4) % 4]} {topic}"
            elif kind == "site":
                topic = f"{tenant['sites'][used_sites % 4]} office"
                if used_sites >= 4:
                    topic = f"{tenant['sites'][used_sites % 4]} annex {used_sites // 4}"
                used_sites += 1
            else:
                topic = products[k]; k += 1
            if kind == "site":
                title, facts, paras, qs = maker(g, tenant, topic.replace(" office", ""))
            else:
                title, facts, paras, qs = maker(g, tenant, topic)
            docs.append(_doc(f"{tid}_p{i:03d}", tenant, title, "public", [f"{tid}_all"],
                             topic, facts, paras, qs))

        # Internal docs.
        int_makers = [("ops", i_ops), ("arch", i_arch), ("minutes", i_minutes)]
        for i in range(n_internal):
            kind, maker = int_makers[i % 3]
            if kind == "ops":
                topic = f"{tenant['sites'][(i // 3) % 4]} site"
                if i // 3 >= 4:
                    topic = f"{tenant['sites'][(i // 3) % 4]} depot {i // 12}"
                title, facts, paras, qs = maker(g, tenant, topic.replace(" site", ""))
            elif kind == "arch":
                topic = products[k]; k += 1
                title, facts, paras, qs = maker(g, tenant, topic)
            else:
                topic = TEAMS[(i // 3) % len(TEAMS)]
                title, facts, paras, qs = maker(g, tenant, topic)
            docs.append(_doc(f"{tid}_i{i:03d}", tenant, title, "internal", [f"{tid}_staff"],
                             topic, facts, paras, qs))

        # Restricted docs grouped into projects of 1-2 docs.
        i = 0
        while i < n_restricted:
            project = f"Project {codenames.pop()}"
            n_docs = 2 if (g.rng.random() < 0.4 and i + 1 < n_restricted) else 1
            makers = g.rng.sample(RESTRICTED_TYPES, n_docs)
            for maker in makers:
                suffix, dept, facts, paras, qs = maker(g, tenant, project)
                if g.rng.random() < 0.5:
                    paras = paras + g.rng.sample(BOILERPLATE, 2)
                title = f"{project} -- {suffix} (CONFIDENTIAL)"
                docs.append(_doc(f"{tid}_r{i:03d}", tenant, title, "restricted", [f"{tid}_{dept}"],
                                 project, facts, paras, qs, canary=g.canary(), project=project))
                i += 1

    return docs, iam


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=20261006)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    ap.add_argument("--public", type=int, default=40)
    ap.add_argument("--internal", type=int, default=30)
    ap.add_argument("--restricted", type=int, default=30)
    args = ap.parse_args()

    docs, iam = build(args.seed, args.public, args.internal, args.restricted)
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "corpus.jsonl").open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    (args.out / "iam.json").write_text(json.dumps(iam, indent=2) + "\n", encoding="utf-8")
    n_r = sum(d["sensitivity"] == "restricted" for d in docs)
    print(f"Wrote {len(docs)} docs ({n_r} restricted) for {len(iam['tenants'])} tenants, "
          f"{len(iam['users'])} users -> {args.out}")


if __name__ == "__main__":
    main()
