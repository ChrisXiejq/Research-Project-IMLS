#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/3] Running CARLA experiments (intersection scenarios, all strategies)..."
cd "$ROOT_DIR/core/scripts/carla"
python run_all_scenarios.py \
  --scenario_glob "scenario_0*.json" \
  --init_glob "ego_init_*.json" \
  --policies smpc_var_risk smpc_open_loop smpc_fixed_risk \
  --with_notv \
  --with_notv_cl

echo "[2/3] Computing aggregated metrics..."
cd "$ROOT_DIR/core"
MPLBACKEND=Agg python scripts/compute_scenario_results.py --compute_metrics

echo "[3/3] Done. Check outputs under:"
echo "  $ROOT_DIR/core/results"

