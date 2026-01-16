#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python}"

benchmark_scripts=(
  "benchmarks/run_baseline_benchmark.py"
  "benchmarks/run_optimized_benchmark.py"
  "benchmarks/run_load_tests.py"
  "benchmarks/run_invariant_validation.py"
)

for script in "${benchmark_scripts[@]}"; do
  if [[ -f "$script" ]]; then
    echo "==> Running ${script}"
    "$PYTHON_BIN" "$script"
  else
    echo "==> Skipping missing ${script}"
  fi
done
