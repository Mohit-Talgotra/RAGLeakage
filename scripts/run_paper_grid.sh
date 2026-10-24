#!/usr/bin/env bash
# run_paper_grid.sh -- The post-audit experiment grid (configs/paper/), for a rented GPU box.
#
# If vllm is installed, the script serves each model itself (one at a time, port 8000) and points
# the ollama backend at it; otherwise it expects a server at OLLAMA_BASE_URL serving llama3.1:8b,
# and skips the model-scale grid. Extra vLLM flags go in VLLM_ARGS, e.g. on two GPUs:
#   VLLM_ARGS="--tensor-parallel-size 2 --max-model-len 8192" bash scripts/run_paper_grid.sh
# p8_models_hosted needs OPENAI_API_KEY.
#
# Order: corpora and paraphrases first, then the cheap stub runs (CPU is fine), then the model
# runs from most to least important for the paper. Every run skips finished cells, so the script
# can be restarted after an interruption.
#
#   bash scripts/run_paper_grid.sh            # everything
#   bash scripts/run_paper_grid.sh stub       # only the stub runs
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
only=${1:-all}

run() {  # run <config> [analyze args...]
  local cfg=configs/paper/$1.yaml
  shift
  "$PY" run.py --config "$cfg"
  "$PY" analyze.py "results/$(basename "$cfg" .yaml)" "$@"
}

export OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:8000/v1}
VLLM_PID=
serve() {  # serve <served name> <HF id>: replace the running vLLM server with this model
  command -v vllm >/dev/null || return 0
  if [ -n "$VLLM_PID" ]; then kill "$VLLM_PID"; wait "$VLLM_PID" || true; fi
  mkdir -p results
  vllm serve "$2" --served-model-name "$1" --port 8000 ${VLLM_ARGS:-} > "results/vllm_${1//:/_}.log" 2>&1 &
  VLLM_PID=$!
  until curl -sf localhost:8000/v1/models >/dev/null; do
    kill -0 "$VLLM_PID" 2>/dev/null || { echo "[grid] vLLM for $1 died, see results/vllm_${1//:/_}.log"; exit 1; }
    sleep 10
  done
  echo "[grid] serving $1"
}
trap '[ -n "$VLLM_PID" ] && kill "$VLLM_PID"' EXIT

# ---- Corpora and paraphrases -------------------------------------------------------
# Every corpus a run uses needs its questions in the bank (one generated corpus per seed). The
# script skips questions it already has; it must end with "0 questions still missing", since a
# missing question stops a run.
[ -f data/enron_c/corpus.jsonl ] || "$PY" scripts/build_enron_corpus.py --canaries --out data/enron_c
serve llama3.1:8b meta-llama/Llama-3.1-8B-Instruct
"$PY" scripts/make_paraphrases.py --backend ollama --model llama3.1:8b \
  --corpus synthetic_v3_s0 synthetic_v3_s1 synthetic_v3_s2 synthetic_v3_s3 synthetic_v3_s4 enron_c

# The attacker trains on the first 3/5 of the sorted tenants (t1-t3, or e1-e3 on Enron) by default;
# do not pass --train-tenants, or the Enron existence cells are skipped.

# ---- Stub runs ------------------------------------------------------------------------
if [ "$only" = all ] || [ "$only" = stub ]; then
  run p0_smoke
  run p1_surfaces_stub
  run p2_cache --reference "cache_threshold=0.8,cache_ttl_s=3600"
  run p4_ablation_existence
  run p4_defenses_existence
fi
[ "$only" = stub ] && exit 0

# ---- Model runs, most important first ---------------------------------------------------
run p4_defenses_revocation --reference "preset=baseline,revocation_type=single_doc,variant=llm_summary"
run p4_defenses_revocation_enron --reference "preset=baseline,revocation_type=single_doc,variant=llm_summary"
run p4_shared_state --reference "preset=baseline_shared,revocation_type=single_doc"
run p4_reclassify --reference "preset=baseline,variant=llm_summary"
run p4_lossy_hooks --reference "preset=full,revocation_type=single_doc"
run p1_surfaces --reference "open_surface=none,revocation_type=single_doc"
run p1_surfaces_enron --reference "open_surface=none,revocation_type=single_doc"
run p3_existence
run p3_existence_enron
run p5_long_session --reference "preset=baseline,variant=llm_summary"
run p4_ablation_revocation --reference "ablate=none,variant=as_is"
run p2_lifetimes
run p2_writes --reference "probe_readonly=True,cache_ttl_s=3600"
run p7_update --reference "preset=baseline"
run p7_update_enron --reference "preset=baseline"
run p6_launder
run p5_utility

# ---- Model scale: one server per model ----------------------------------------------------
if command -v vllm >/dev/null; then
  for m in qwen2.5:3b=Qwen/Qwen2.5-3B-Instruct llama3.1:8b=meta-llama/Llama-3.1-8B-Instruct \
           qwen2.5:7b=Qwen/Qwen2.5-7B-Instruct qwen2.5:32b=Qwen/Qwen2.5-32B-Instruct \
           llama3.3:70b=meta-llama/Llama-3.3-70B-Instruct; do
    serve "${m%%=*}" "${m#*=}"
    "$PY" run.py --config configs/paper/p8_models.yaml --only "llm_model=${m%%=*}"
  done
  "$PY" analyze.py results/p8_models
else
  echo "[grid] vllm not installed: run p8_models per model with run.py --only llm_model=<name>"
fi
run p8_models_hosted || echo "[grid] hosted model skipped (set OPENAI_API_KEY)"
echo "[grid] done; fill research_paper/RESULTS_TODO.md slots from results/*/analysis/"
