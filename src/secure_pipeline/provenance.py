"""
provenance.py -- Provenance taint: the set of source doc IDs a derived artifact came from.

Every derived artifact (cache entry, memory turn, rolling summary) carries
`taint: frozenset[doc_id]`. A response's taint is the union of the documents it was
generated from and, when taint is transitive, the taint of every memory turn that was
in its prompt. Revocation then becomes a set intersection, no matter how many times
the content was copied, paraphrased or summarised.
"""

from __future__ import annotations

from typing import Iterable

Taint = frozenset

EMPTY: Taint = frozenset()


def taint_union(*taints: Iterable[str]) -> Taint:
    out: set[str] = set()
    for t in taints:
        out.update(t)
    return frozenset(out)


def response_taint(doc_ids: Iterable[str], memory_taints: Iterable[Taint], transitive: bool) -> Taint:
    """Taint of a freshly generated response.

    Non-transitive mode is the old ID-match design: only directly retrieved documents
    are recorded, so content that arrived through memory is untracked.
    """
    if transitive:
        return taint_union(doc_ids, *memory_taints)
    return frozenset(doc_ids)
