#!/usr/bin/env bash
# Overnight queue for the review round (about 11-12 h on an M-series laptop). Resumable: finished
# (cell, seed) runs are skipped and real-LLM generations are cached, so just rerun it.
# Needs `ollama serve` with qwen2.5:7b pulled. Groq (GROQ_API_KEY in .env) is best effort:
# when the free-tier quota runs out, that job fails and everything else carries on.
#
# Timing-sensitive runs (existence, utility latency) run alone; revocation runs in parallel.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=results/_logs
mkdir -p "$LOG"
run() { echo "[review] start $1 $(date +%T)"; $PY run.py --config "configs/$1.yaml" > "$LOG/$1.log" 2>&1
        echo "[review] done $1 exit=$? $(date +%T)"; }
par() { OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 run "$1"; }

[ -f data/enron/corpus.jsonl ] || $PY scripts/build_enron_corpus.py > "$LOG/build_enron.log" 2>&1

# A: revocation runs in parallel (stub on CPU, Qwen-7B on the GPU).
for c in rq1_surfaces rq4_ablation_revocation rq5_collateral rq_baselines_revocation enron_revocation; do
  par "$c" &
done
run model_grid_7b &
wait

# B: latency-sensitive stub runs, one at a time.
for c in rq5_overhead rq_baselines_existence enron_existence; do run "$c"; done

# C: existence with the real model, alone (its latency channel is measured).
run rq3_existence_7b

# D: remaining real-model runs and the paraphrase-judge sample.
run rq6_taint_stress
run rq5_collateral_7b
run enron_revocation_7b
echo "[review] judge sample $(date +%T)"
$PY scripts/judge_sample.py results/model_grid_7b results/enron_revocation_7b \
    --backend ollama --model qwen2.5:7b --per-cell 150 > "$LOG/judge_sample.log" 2>&1
echo "[review] judge exit=$? $(date +%T)"

# Groq last, so its CPU use never overlaps a timing-sensitive run. Stops when the quota does.
run model_grid_groq

# E: analysis.
for c in rq1_surfaces rq4_ablation_revocation rq5_collateral rq_baselines_revocation enron_revocation \
         model_grid_7b model_grid_groq rq6_taint_stress rq5_collateral_7b enron_revocation_7b \
         rq_baselines_existence enron_existence rq3_existence_7b rq5_overhead; do
  [ -d "results/$c" ] && { $PY analyze.py "results/$c" > "$LOG/analyze_$c.log" 2>&1; echo "[review] analyzed $c exit=$?"; }
done
echo "[review] all done $(date +%T)"
