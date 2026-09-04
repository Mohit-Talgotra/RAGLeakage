#!/usr/bin/env python3
"""
run_full_experiment.py -- Run the Complete RAG Leakage Experiment Matrix (§5).

Runs controlled A/B comparison across:
1. Baseline (Naive / Leaky) Pipeline
2. Mitigated (Secure) Pipeline

Evaluates:
- Leakage Magnitude (LM)
- Leakage Half-Life (LH)
- Existence Inference Accuracy (EIA)
- Side-Channel observables (T4, T5, T6, T7)
"""

import sys
from pathlib import Path

# Allow running from repository root
sys.path.insert(0, str(Path(__file__).parent))

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.secure_pipeline.experiment_runner import ExperimentRunner


def main() -> None:
    print("=" * 76)
    print("  ENTERPRISE RAG SECURE MULTI-TENANT TESTBED -- FULL EXPERIMENT SUITE")
    print("=" * 76)

    runner = ExperimentRunner(embedding_model="all-MiniLM-L6-v2")

    # Run primary A/B comparison on single-doc revocation
    runner.run_ab_comparison(
        revocation_type="single_doc",
        cache_ttl_seconds=3600.0,
        target_doc_id="doc_A6",
    )


if __name__ == "__main__":
    main()
