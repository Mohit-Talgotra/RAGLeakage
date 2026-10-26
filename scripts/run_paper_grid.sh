#!/usr/bin/env bash
# run_paper_grid.sh -- The post-audit experiment grid (configs/paper/), for a rented GPU box.
#
# If vllm is installed, the script serves each model itself: one server per GPU (per 2 GPUs for
# 32B), ports 8000 upwards, and spreads the (cell, seed) jobs of each config over them
# (run.py --workers). Configs that measure latency (llm_cache: false, the existence runs) get one
# worker per server, so every call is timed on an otherwise idle GPU, as in a sequential run.
# Without vllm it expects one server at OLLAMA_BASE_URL serving llama3.1:8b and runs sequentially.
#
#   PER_SERVER   concurrent jobs per server for the other configs (default 16)
#   VLLM_ARGS    extra vLLM flags, e.g. "--max-model-len 8192"
# p8_models_hosted needs OPENAI_API_KEY. The testbed's own encoder and reranker run on the CPU
# (CUDA_VISIBLE_DEVICES is cleared for run.py), so they do not compete with vLLM for GPU memory.
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
PER_SERVER=${PER_SERVER:-16}
WORKERS=${WORKERS:-1}

run() {  # run <config> [analyze args...]
  local cfg=configs/paper/$1.yaml
  shift
  CUDA_VISIBLE_DEVICES= "$PY" run.py --config "$cfg" --workers "$WORKERS"
  "$PY" analyze.py "results/$(basename "$cfg" .yaml)" "$@"
}

export OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:8000/v1}
NGPU=$(nvidia-smi -L 2>/dev/null | wc -l | tr -d ' ')
PIDS=()
stop_servers() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done; for p in "${PIDS[@]:-}"; do [ -n "$p" ] && wait "$p" 2>/dev/null; done; PIDS=(); }
serve() {  # serve <served name> <HF id> [GPUs per server]: replace the running servers with this model
  command -v vllm >/dev/null || return 0
  local tp=${3:-1} n=$((NGPU / ${3:-1})) urls="" i
  [ "$n" -ge 1 ] || { echo "[grid] $1 needs $tp GPUs, have $NGPU"; return 1; }
  stop_servers
  mkdir -p results
  for ((i = 0; i < n; i++)); do
    CUDA_VISIBLE_DEVICES=$(seq -s, $((i * tp)) $((i * tp + tp - 1))) \
      vllm serve "$2" --served-model-name "$1" --port $((8000 + i)) --tensor-parallel-size "$tp" ${VLLM_ARGS:-} \
      > "results/vllm_${1//:/_}_$i.log" 2>&1 &
    PIDS+=($!)
    urls+="${urls:+,}http://localhost:$((8000 + i))/v1"
  done
  for ((i = 0; i < n; i++)); do
    until curl -sf "localhost:$((8000 + i))/v1/models" >/dev/null; do
      kill -0 "${PIDS[$i]}" 2>/dev/null || { echo "[grid] vLLM $i for $1 died, see results/vllm_${1//:/_}_$i.log"; exit 1; }
      sleep 10
    done
  done
  export OLLAMA_BASE_URLS=$urls OLLAMA_BASE_URL=${urls%%,*}
  WORKERS=$((n * PER_SERVER))
  echo "[grid] serving $1 on $n server(s), $WORKERS workers"
}
trap stop_servers EXIT

# ---- Corpora and paraphrases -------------------------------------------------------
# Every corpus a run uses needs its questions in the bank (one generated corpus per seed). The
# script skips questions it already has; it must end with "0 questions still missing", since a
# missing question stops a run.
[ -f data/enron_c/corpus.jsonl ] || "$PY" scripts/build_enron_corpus.py --canaries --out data/enron_c
serve llama3.1:8b meta-llama/Llama-3.1-8B-Instruct
"$PY" scripts/make_paraphrases.py --backend ollama --model llama3.1:8b --workers 32 \
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
  for m in qwen2.5:3b=Qwen/Qwen2.5-3B-Instruct=1 llama3.1:8b=meta-llama/Llama-3.1-8B-Instruct=1 \
           qwen2.5:7b=Qwen/Qwen2.5-7B-Instruct=1 qwen2.5:32b=Qwen/Qwen2.5-32B-Instruct=2; do
    IFS== read -r name hf tp <<< "$m"
    serve "$name" "$hf" "$tp" || continue
    CUDA_VISIBLE_DEVICES= "$PY" run.py --config configs/paper/p8_models.yaml --only "llm_model=$name" --workers "$WORKERS"
  done
  "$PY" analyze.py results/p8_models
else
  echo "[grid] vllm not installed: run p8_models per model with run.py --only llm_model=<name>"
fi
WORKERS=8  # hosted API: stay under its rate limit
run p8_models_hosted || echo "[grid] hosted model skipped (set OPENAI_API_KEY)"
echo "[grid] done; fill research_paper/RESULTS_TODO.md slots from results/*/analysis/"
