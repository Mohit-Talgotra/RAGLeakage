"""
mitigations.py -- Ablation switches. Replaces the old "baseline" / "mitigated" mode string.

Each field turns one defense on or off, so a run can leave exactly one surface
vulnerable (RQ1) or remove one mitigation from the full set (RQ4).

Presets:
- strawman : flat cross-tenant retrieval, global cache, raw scores (including the scores of
             candidates it withholds). The textbook leaky app.
- baseline : ACL pre-filter on materialized index ACLs, a per-user semantic cache, no
             revocation hooks, raw metadata. The cache is per user so that no user is ever
             served an answer generated for someone else (audit C2).
- baseline_shared : baseline with a tenant-shared cache and no access check on hits. A named
             misconfiguration (GPTCache-style shared cache), measured as its own finding: it
             serves restricted answers to users who never had access, before any revocation.
- legacy   : the pre-upgrade "mitigated" mode (ID-match purge, fast refusal path,
             30 ms floor padding). Kept to show that its fixes re-open channels.
- full     : every mitigation, including transitive provenance taint and
             constant-shape responses.
- full_fine: full with sentence-level taint on extractive summaries, so a revocation drops
             only the summary sentences that came from the lost document (audit H6).
             With model-written summaries there is no sentence mapping and it equals full.
- full_user: full with a per-user cache, like epoch and flush.

Simple alternative defenses (audit C6), with the same retrieval and metadata settings as full:
- epoch    : per-user permission epoch. Any revocation bumps the user's epoch in IAM; cache
             entries and memory turns carry the epoch of the user who created them and are
             dropped on read when it is stale. Read-time, so it needs no event delivery.
- flush    : on ACCESS_REVOKED, eagerly drop every session and cache entry of that user.

Designs from practice and the literature, mapped onto the same switches:
- baseline doubles as the synced-ACL design: metadata filters in the vector store, per-user
  indexes, or HoneyBee-style role partitions all filter on a materialized copy of the ACL.
- authz_postfilter : tenant retrieval, then a live, consistent authorization check per chunk
             (Zanzibar/ReBAC-style "check after retrieve"). Exposed scores are computed over the
             authorized chunks only (audit C3); nothing hooks the cache or memory.
- authz_prefilter  : query-time security trimming against live IAM (pre-filter plus live
             re-check); again no derived-artifact hooks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace


@dataclass(frozen=True)
class Mitigations:
    # Retrieval
    acl_prefilter: bool = False      # filter by (materialized) ACL inside the vector query
    live_acl_check: bool = False     # re-check live IAM on every retrieved chunk
    cross_tenant: bool = False       # post-filter mode only: retrieve over every tenant (strawman)
    expose_withheld_scores: bool = False  # post-filter mode: exposed scores include withheld chunks
    # Semantic cache
    cache_scope: str = "global"      # "global" | "tenant" | "user"
    cache_evict: bool = False        # eager: evict tainted entries on ACCESS_REVOKED
    # Session memory
    memory_purge: bool = False       # eager: purge tainted turns on ACCESS_REVOKED
    # Provenance taint
    taint_transitive: bool = False   # response taint includes taint of memory turns in the prompt
    cache_lazy_check: bool = False   # on every cache read: user must still hold all taint docs
    memory_lazy_check: bool = False  # on every memory read: drop turns the user no longer may see
    taint_user_input: bool = False   # taint queries that contain restricted secrets (pasted content)
    summary_taint_union: bool = False  # non-transitive mode: a summary still carries its turns' taint (one hop)
    taint_granularity: str = "turn"  # "turn" | "sentence" (extractive summaries keep per-sentence taint)
    # Simple alternatives to taint
    epoch_invalidation: bool = False  # drop cache entries / memory turns made before the user's last revocation
    flush_on_revoke: bool = False    # eager: drop all of the revoked user's sessions and cache entries
    # Metadata normalization
    score_quantize: bool = False     # expose coarse score bands instead of raw floats
    uniform_refusal: bool = False    # one refusal text for not-found and access-denied
    latency_pad: bool = False        # pad wall-clock latency
    pad_strategy: str = "bucket"     # "bucket" (round up) | "deadline" (fixed) | "floor" (legacy)
    pad_ms: float = 500.0            # bucket size, deadline, or floor in ms
    fast_refusal: bool = False       # skip the LLM when nothing is authorized (a timing oracle)

    def __post_init__(self) -> None:
        if self.cache_scope not in ("global", "tenant", "user"):
            raise ValueError(f"cache_scope must be global|tenant|user, got {self.cache_scope!r}")
        if self.pad_strategy not in ("bucket", "deadline", "floor"):
            raise ValueError(f"pad_strategy must be bucket|deadline|floor, got {self.pad_strategy!r}")
        if self.taint_granularity not in ("turn", "sentence"):
            raise ValueError(f"taint_granularity must be turn|sentence, got {self.taint_granularity!r}")

    def to_dict(self) -> dict:
        return asdict(self)


_METADATA = dict(score_quantize=True, uniform_refusal=True, latency_pad=True, pad_strategy="bucket", pad_ms=500.0)

PRESETS: dict[str, Mitigations] = {
    "strawman": Mitigations(cross_tenant=True, expose_withheld_scores=True),
    "baseline": Mitigations(acl_prefilter=True, cache_scope="user"),
    "baseline_shared": Mitigations(acl_prefilter=True, cache_scope="tenant"),
    "legacy": Mitigations(
        acl_prefilter=True, cache_scope="tenant", cache_evict=True, memory_purge=True,
        score_quantize=True, uniform_refusal=True, latency_pad=True,
        pad_strategy="floor", pad_ms=30.0, fast_refusal=True,
    ),
    "authz_postfilter": Mitigations(live_acl_check=True, cache_scope="user"),
    "authz_prefilter": Mitigations(acl_prefilter=True, live_acl_check=True, cache_scope="user"),
    "full": Mitigations(
        acl_prefilter=True, live_acl_check=True, cache_scope="tenant", cache_evict=True,
        memory_purge=True, taint_transitive=True, cache_lazy_check=True, memory_lazy_check=True,
        **_METADATA,
    ),
    "epoch": Mitigations(acl_prefilter=True, live_acl_check=True, cache_scope="user",
                         epoch_invalidation=True, **_METADATA),
    "flush": Mitigations(acl_prefilter=True, live_acl_check=True, cache_scope="user",
                         flush_on_revoke=True, **_METADATA),
}
PRESETS["full_fine"] = replace(PRESETS["full"], taint_granularity="sentence")
# full with the alternatives' per-user cache: no cross-user reuse, so no laundered colleague path
# through the cache, at the price of hit rate.
PRESETS["full_user"] = replace(PRESETS["full"], cache_scope="user")

# Boolean switches that a leave-one-out ablation toggles off from "full".
ABLATABLE = [f.name for f in fields(Mitigations)
             if f.type in ("bool", bool) and getattr(PRESETS["full"], f.name) is True]

# RQ1: start from "full" and re-open exactly one derived artifact.
OPEN_SURFACE: dict[str, dict] = {
    "none": {},
    "index": {"live_acl_check": False},
    "cache": {"cache_evict": False, "cache_lazy_check": False},
    "memory": {"memory_purge": False, "memory_lazy_check": False},
}


def preset(name: str, **overrides) -> Mitigations:
    if name not in PRESETS:
        raise ValueError(f"unknown preset {name!r}; choose from {sorted(PRESETS)}")
    unknown = set(overrides) - {f.name for f in fields(Mitigations)}
    if unknown:
        raise ValueError(f"unknown mitigation fields: {sorted(unknown)}")
    return replace(PRESETS[name], **overrides)
