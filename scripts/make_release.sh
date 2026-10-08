#!/usr/bin/env bash
# Builds release/ for a public repository plus an archived DOI (review item 13).
# release/afterimage-code.tar.gz : code, configs, corpus + generator, tests, docs
# release/afterimage-results.tar.gz : every analysis/ folder (summaries, CSVs incl. per-event
#                                     and per-probe tables, figures) and manifests
# release/afterimage-rawlogs.tar.gz : raw per-query JSONL logs (large; upload to Zenodo only)
# Secrets (.env), caches, superseded runs and data/enron (rebuilt from EnronQA by
# scripts/build_enron_corpus.py; its licence is not stated, so we do not redistribute it) are left out.
set -eu
cd "$(dirname "$0")/.."
mkdir -p release
tar --exclude='.env' --exclude='.venv' --exclude='.cache' --exclude='__pycache__' --exclude='results' \
    --exclude='release' --exclude='paper_package*' --exclude='data/enron' --exclude='*.pdf' --exclude='.DS_Store' \
    -czf release/afterimage-code.tar.gz \
    README.md CLAUDE.md pyproject.toml uv.lock run.py analyze.py sitecustomize.py \
    src configs data scripts tests docs
find results -maxdepth 2 \( -name analysis -o -name manifest.json \) -not -path "results/_superseded/*" \
    -not -path "results/smoke*" | tar -czf release/afterimage-results.tar.gz -T -
find results -maxdepth 3 -path "*/runs/*.jsonl" -not -path "results/_superseded/*" -not -path "results/smoke*" \
    | tar -czf release/afterimage-rawlogs.tar.gz -T -
ls -lh release
