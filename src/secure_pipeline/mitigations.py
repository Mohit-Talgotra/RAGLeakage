"""
mitigations.py -- Ablation switches. Replaces the old "baseline" / "mitigated" mode string.

Each field turns one defense on or off, so a run can leave exactly one surface
vulnerable (RQ1) or remove one mitigation from the full set (RQ4).

Presets:
- strawman : flat cross-tenant retrieval, global cache, raw scores. The textbook leaky app.
- baseline : what teams actually ship. ACL pre-filter on materialized index ACLs,
             tenant-scoped cache, no revocation hooks, raw metadata.
- legacy   : the pre-upgrade "mitigated" mode (ID-match purge, fast refusal path,
             30 ms floor padding). Kept to show that its fixes re-open channels.
- full     : every mitigation, including transitive provenance taint and
             constant-shape responses.

Designs from practice and the literature, mapped onto the same switches (RQ5 baselines):
- baseline doubles as the synced-ACL design: metadata filters in the vector store, per-user
  indexes, or HoneyBee-style role partitions all filter on a materialized copy of the ACL.
- authz_postfilter : flat retrieval, then a live, consistent authorization check per chunk
             (Zanzibar/ReBAC-style "check after retrieve"); nothing hooks the cache or memory.
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

    def to_dict(self) -> dict:
        return asdict(self)


PRESETS: dict[str, Mitigations] = {
    "strawman": Mitigations(),
    "baseline": Mitigations(acl_prefilter=True, cache_scope="tenant"),
    "legacy": Mitigations(
        acl_prefilter=True, cache_scope="tenant", cache_evict=True, memory_purge=True,
        score_quantize=True, uniform_refusal=True, latency_pad=True,
        pad_strategy="floor", pad_ms=30.0, fast_refusal=True,
    ),
    "authz_postfilter": Mitigations(live_acl_check=True, cache_scope="tenant"),
    "authz_prefilter": Mitigations(acl_prefilter=True, live_acl_check=True, cache_scope="tenant"),
    "full": Mitigations(
        acl_prefilter=True, live_acl_check=True, cache_scope="tenant", cache_evict=True,
        memory_purge=True, taint_transitive=True, cache_lazy_check=True, memory_lazy_check=True,
        score_quantize=True,
        uniform_refusal=True, latency_pad=True, pad_strategy="bucket", pad_ms=500.0,
    ),
}

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
