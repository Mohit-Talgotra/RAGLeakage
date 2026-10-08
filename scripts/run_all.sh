#!/usr/bin/env bash
# Runs every RQ config (5 seeds) and analyzes them. Resumable: finished cells are skipped.
# Timing-sensitive configs (rq5, rq3, rq4 existence) run alone so CPU contention
# doesn't add latency noise; the revocation configs run in parallel.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=results/_logs
mkdir -p "$LOG"
run() { echo "[run_all] start $1 $(date +%T)"; $PY run.py --config "configs/$1.yaml" --seeds 5 > "$LOG/$1.log" 2>&1; echo "[run_all] done $1 exit=$? $(date +%T)"; }

run rq5_utility                       # alone; also downloads models and warms .cache/embeddings
for c in rq1_surfaces rq2_revocation_window rq2_cache_sweep rq4_ablation_revocation rq5_leakage; do
  OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 run "$c" &
done
wait
run rq3_existence
run rq4_ablation_existence

echo "[run_all] analyze $(date +%T)"
for c in rq1_surfaces rq2_revocation_window rq2_cache_sweep rq3_existence rq4_ablation_existence rq4_ablation_revocation rq5_leakage; do
  $PY analyze.py "results/$c" > "$LOG/analyze_$c.log" 2>&1; echo "[run_all] analyzed $c exit=$?"
done
$PY analyze.py results/rq5_utility --leakage results/rq5_leakage > "$LOG/analyze_rq5_utility.log" 2>&1; echo "[run_all] analyzed rq5_utility exit=$?"
echo "[run_all] all done $(date +%T)"

# Optional real-LLM check (needs `ollama serve` and `ollama pull qwen2.5:3b`; about 1.5 h on a laptop):
#   for c in model_grid_local rq3_existence_local; do $PY run.py --config configs/$c.yaml && $PY analyze.py results/$c; done
