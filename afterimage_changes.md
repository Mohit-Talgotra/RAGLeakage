# Afterimage — changes to make before the GPU runs

From the re-audit of 22 Oct (evening). Each item: what to change, where, and how. Items 1–7 change the code or the grid and must land before `run_paper_grid.sh`; items 8–11 are smaller or text-only.

One correction to the re-audit: for item 5 (document reclassification), a fair `epoch` must bump the epoch of **every** user who loses the document, not only the user you revoke. Done that way, `epoch` stays safe. The difference from taint is then cost: one reclassification wipes the sessions of everyone who held the document. The item below is written that way.

---

## 1. Paraphrase bank covers only seed 0 (N1, blocking)

**Problem.** The bank is built from `synthetic_v3`, which is the same corpus as `synthetic_v3_s0`. Seeds 1–4 have different questions, so `reword()` silently returns the original question, a cosine-1.0 cache hit at any threshold.

**`src/secure_pipeline/experiments.py`, inside `reword()`.** Replace

```python
options = bank.get(q) or [q]
```

with

```python
if q not in bank:
    raise KeyError(f"no paraphrases for {q!r}; rebuild data/paraphrases.json for this corpus")
options = bank[q]
```

**`scripts/run_paper_grid.sh`.** Replace the paraphrase line with

```bash
"$PY" scripts/make_paraphrases.py --backend ollama --model llama3.1:8b \
  --corpus synthetic_v3_s0 synthetic_v3_s1 synthetic_v3_s2 synthetic_v3_s3 synthetic_v3_s4 enron_c
```

and remove the `[ -f data/paraphrases.json ] ||` guard, or delete the old file first. The script skips questions it already has.

**Check.** `make_paraphrases.py` drops a question when the model's JSON fails to parse, so rerun it until it prints `0 to generate`. With the `KeyError` above, a gap now stops the run instead of hiding.

---

## 2. `full_fine` equals `full` with every real model (N2, blocking for the defense claim)

**Problem.** `SessionMemory` forces `granularity="turn"` whenever a summarizer is passed, and every real-model config sets `summarizer: llm`. Real models also return `used_memory=None`.

**Fix: add an extractive-summary arm for real models.** Sentence taint stays sound with any generator, because the filtered summary's taint is the union of its kept sentences. In `configs/paper/p4_defenses_revocation.yaml` and `p5_long_session.yaml`, remove `summarizer: llm` from `base` and add

```yaml
variants:
  - {variant: llm_summary, summarizer: llm}
  - {variant: extractive_summary, summarizer: extractive}
```

The claim then reads: with model-written summaries, `full_fine` = `full`; with extractive summaries, `full_fine` keeps X of retained recall that `full` and `epoch` discard.

**Optional, stronger:** source-tagged model summaries. Prompt the model to end each summary line with the turn numbers it came from (`[t3,t5]`), set each line's taint to the union of those turns' taints, and extend `tests/test_taint_invariant.py` to check that no line holds a unique secret of a document missing from its tags. Report how often the tags were wrong.

**`sections/defense.tex`, paragraph "Sentence-level taint".** Add: "With model-written summaries the summary has no sentence-to-source mapping, so `full_fine` reduces to `full`; we report it with an extractive summarizer."

---

## 3. New disclosure can only come from the index (N3, framing)

**Problem.** The cache and memory hold only what the victim was told before revocation, so LM_new is structurally about zero for them and for every preset with a live IAM check. The "never-seen secrets" headline will be a stale-index result.

**Add a real new-disclosure path through shared state.** In `run_revocation`, a new option `colleague_unseen`: after revocation, an authorized colleague asks about facts the victim never saw, writing to the cache; the victim then asks the same facts.

```python
# with the other options
colleague_unseen = bool(cell.get("colleague_unseen", False))

# per event, before _revoke(...)
holder = None
if colleague_unseen:
    others = sorted(pipe.acm.users_with_access(tid) - {victim})
    holder = others[0] if others else None

# inside the probe loop, before the victim's probes
if holder and unseen_qs:
    q = qa[2 + i % len(qa[2:])]["question"]
    client.ask(holder, f"ev{ev}-t{int(t)}-holder", q, write=True,
               phase="holder", probe_doc=tid, **{k: v for k, v in ptags.items() if k != "phase"})
```

The victim's existing `new_session_unseen` probe asks the reworded form of that question in a fresh session, and it already counts toward LM_new. Add `colleague_unseen: true` and `probe_unseen: true` to a cell of `p4_defenses_revocation` covering `baseline_shared`, `full`, `full_user` (item 6) and `epoch`. Expected: `baseline_shared` leaks new secrets, `full` blocks them through the lazy check, and per-user caches never see them.

**Paper.** In RQ1, state that LM_new for the cache and memory rows is structural, since they only hold what the victim was shown. Put the argument for cache and memory on (a) re-disclosure as a complete-mediation violation and (b) shared state, including the path above. Write the abstract's first result sentence after you have this number.

---

## 4. Eager hooks never miss an event (N4)

**Problem.** Cache and memory listeners are called in-process, so `flush` (and `full`'s eager eviction) never miss a revocation. Only index sync models lost webhooks.

**`src/secure_pipeline/access_control.py`:**

```python
def __init__(self, clock, hook_drop: float = 0.0, rng=None) -> None:
    ...
    self.hook_drop, self._rng = hook_drop, rng
    self._lossy: set = set()
    self.dropped_hooks = 0

def subscribe(self, listener, lossy: bool = False) -> None:
    if listener not in self._listeners:
        self._listeners.append(listener)
    if lossy:
        self._lossy.add(listener)

# in _emit, replace the listener loop
for listener in self._listeners:
    if listener in self._lossy and self.hook_drop and self._rng.random() < self.hook_drop:
        self.dropped_hooks += 1
        continue
    listener(event)
```

`from_iam(...)` passes `hook_drop` and `rng` through to the constructor.

**`semantic_cache.py` and `session_memory.py`:** subscribe with `lossy=True` (`on_revocation`, `on_flush`).

**`pipeline.py`:** add `hook_drop: float = 0.0` to `PipelineConfig`. In `__init__`, create `self._hook_rng = random.Random(f"{seed}-hooks")` once (not in `reset()`, or every event repeats the same draw). In `reset()`, pass `hook_drop=self.cfg.hook_drop, rng=self._hook_rng` to `from_iam`. One revocation per event keeps the draws paired across cells.

**Config:** add to `p4_defenses_revocation`

```yaml
  - {variant: lossy, sync: "event:0.05:86400", hook_drop: 0.05}
```

Expected: `flush` leaks in the dropped events and `epoch` and `full` do not, which is the read-time-versus-eager point the paper makes in words.

---

## 5. Document reclassification (N5)

**Problem.** Every revocation type changes the user; none narrows a document's ACL. That is the case where taint's per-document check differs from a per-user epoch.

**`access_control.py`:**

```python
def reclassify(self, doc_id: str, group: str) -> list[RevocationEvent]:
    """Remove a group from a document's ACL; every user who loses the document gets an event
    (and an epoch bump)."""
    before = {u: self.accessible_docs(u) for u in self._user_tenant}
    self._doc_groups[doc_id] = self._doc_groups.get(doc_id, frozenset()) - {group}
    return [self._emit("reclassify", u, b, group=group)
            for u, b in before.items() if b - self.accessible_docs(u)]
```

**`experiments._revoke`:**

```python
elif kind == "reclassify":
    group = sorted(set(target["acl_groups"]) & pipe.acm.groups_of(victim))[0]
    pipe.acm.reclassify(target["doc_id"], group)
```

**Bystander cost.** Add option `bystander: true`. Before revocation, a second holder in the same group runs the same warm-up in session `ev{ev}-by`, with `phase="warm"` and `warm_doc` tags plus `who="bystander"`. After revocation, at each probe time, they ask the "remind me" question about each retained filler in that session (`probe_kind="bystander_retained"`). In `analyze.collect_events`, key the `warm` dict by `(seed, event, who)` and score `bystander_retained` the way `retained_same` is scored.

**Config:** a cell with `revocation_type: reclassify`, `bystander: true` and presets `epoch, flush, full, full_fine` (with the extractive-summary variant from item 2).

**What it shows.** All three stay at zero leakage. `epoch` and `flush` wipe every affected user's sessions, while taint drops only artifacts containing the reclassified document. If you also want the safety failure, run a naive `epoch` that bumps only on user-side events.

---

## 6. `full` shares its cache across the tenant; the alternatives do not (N6)

**`mitigations.py`:**

```python
PRESETS["full_user"] = replace(PRESETS["full"], cache_scope="user")
```

**Configs:**
- `p4_defenses_revocation`, `p5_long_session`, `p5_utility`: add `full_user` to the preset list.
- `p6_launder`: change `preset: full` to a grid entry `preset: [full, full_user, epoch]`.

**Paper.** Report the trade-off: cache hit rate `full` vs `full_user` (from `p5_utility`), against the colleague event rate `full` vs `full_user` (from `p6_launder`).

---

## 7. Analysis wiring (N7)

**`scripts/run_paper_grid.sh`:** remove `--train-tenants t1 t2 t3` from every line. The default split (first 3/5 of the sorted tenants) gives t1–t3 on the generated corpus and e1–e3 on Enron. With the flag, every Enron existence cell is skipped silently.

**Cross-corpus pairing.** Split each config that varies `corpus` into one file per corpus:
- `p4_defenses_revocation.yaml` → `p4_defenses_revocation.yaml` (G) + `p4_defenses_revocation_enron.yaml` (E)
- `p7_update.yaml` → `p7_update.yaml` + `p7_update_enron.yaml`
- `p3_existence.yaml` → `p3_existence.yaml` + `p3_existence_enron.yaml` (no pairing problem there, but it keeps the train/test split per corpus)

Give each its own `--reference` line in `run_paper_grid.sh`, and update the slot table in `RESULTS_TODO.md`.

---

## 8. Read-only probes (N8)

New config `configs/paper/p2_writes.yaml`:

```yaml
name: p2_writes
experiment: revocation
seeds: 5
base:
  embedder: all-MiniLM-L6-v2
  reranker: cross-encoder/ms-marco-MiniLM-L-6-v2
  corpus: synthetic_v3@seed
  preset: baseline
  sync: periodic:86400
  events: 40
  probe_paraphrase: file
  llm_backend: ollama
  llm_model: llama3.1:8b
  summarizer: llm
grid:
  probe_readonly: [true, false]
  cache_ttl_s: [3600, 86400]
```

Report it in RQ2 as "how much re-caching of leaked answers extends the leak in a deployment where every query writes".

---

## 9. Utility workload has no revocation (N9)

Simplest is to change the text, not the code. In `sections/methodology.tex`, paragraph "Utility and authorization load", replace

> Authorized users ask answerable questions in ten-turn sessions, so answers draw on memory and its taint.

with

> Authorized users ask answerable questions in ten-turn sessions with no revocation, which measures the defenses' overhead (latency, IAM calls and per-document decisions) during normal use. What a revocation costs in the session is measured by the collateral and long-session experiments.

Do the same in the R5 pending text in `results.tex`: drop "over-refusal" from what `p5_utility` is said to show.

---

## 10. Text that predicts results (N10)

| File | Current | Change to |
| --- | --- | --- |
| `abstract.tex` | "an insider infers existence at AUC [A], mostly through answer content served from shared caches, and constant-shape responses reduce this to [chance / near chance]" | Leave a single slot, "[existence result]", and write the sentence from `p3_existence`. With a per-user `baseline` cache, the shared-cache explanation probably no longer holds |
| `abstract.tex` | "sentence-level taint keeps [Z] of the in-session answers that coarse invalidation discards" | Write after item 2; name the summary design it holds for |
| `abstract.tex` | "chat memory keeps leaking for as long as sessions are retained" | Slot it; it is a prediction until `p2_lifetimes` runs |
| `results.tex`, R2a slot | "Expected shape: cache leakage vanishes … memory leakage is bounded by retention." | Delete the sentence |
| `results.tex`, R6 slot | "reached through the stale index under baseline and under neither epoch nor full" | "[R6: LM_upd per preset]" |
| `methodology.tex`, judge | "We report the model judge's precision and recall against [N] hand-labelled responses" | Keep only if the labelling is done; otherwise say the judge is unvalidated and drop "measured recall" from the Scope paragraph of `introduction.tex` and from Limitations |
| `related_work.tex`, Search protocol | lists ACM DL, IEEE Xplore, USENIX, DBLP, Semantic Scholar, arXiv, 2005–2026, citation chasing | Make it match `literature_review/search_log.md` exactly: only the databases, terms and years actually searched |
| `data.tex` | "carry six to twelve paragraphs of realistic memo text" | "carry six to twelve filler paragraphs drawn from seven boilerplate memo templates" |

---

## 11. Small fixes (N11)

**Clusters across per-seed corpora** (`analyze.py`). A doc id names a different document in each seed's corpus. In `analyze_revocation`:

```python
per_seed = str(cell.get("corpus", "")).endswith("@seed")
tkey = (lambda k, e: (k[0], e["target"])) if per_seed else (lambda k, e: e["target"])
targets = [tkey(k, e) for k, e in events.items()]
targets_by_cell[cell["cell_id"]] = {k: tkey(k, e) for k, e in events.items()}
```

In `analyze_existence`, the same rule for `clusters`: use `(r["tags"]["seed"], r["tags"]["target"])` when the corpus is per-seed.

**Updated values must be corpus-unique** (`experiments._updated_doc`). Pass the corpus in and loop while the new value occurs in any document:

```python
while True:
    nv = _DIGITS.sub(lambda m: str(rng.randint(1, 9)), v)
    if nv != v and nv not in text and not any(nv in d["text"] for d in corpus.docs):
        break
```

**Enron siblings.** In Limitations, say that 457 of 500 restricted Enron e-mails have no same-thread sibling, so the sibling/singleton split is effectively a corpus split.

**Bibliography.** Resolve every `VERIFY` entry and check each documentation URL before submission (already listed in `RESULTS_TODO.md`).

---

## Order

1. Items 1 and 7 (bugs).
2. Items 2, 4, 5, 6 (code and grid).
3. Item 3 (new path and framing).
4. Add tests: a missing paraphrase raises; a dropped hook makes `flush` leak while `epoch` does not; `reclassify` bumps every affected user's epoch; `full_fine` with `summarizer: extractive` keeps more retained recall than `full` on a small stub session.
5. `p0_smoke`, then check the logs: `probe_template` should vary across seeds, and Enron rows should appear in `existence_eia.csv`.
6. Items 8–11 any time before writing results.
