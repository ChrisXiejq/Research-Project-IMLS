#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[0/4] Activating environment carla_modern ..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate carla_modern

echo "[1/4] Smoke check imports ..."
python - <<'PY'
import carla
import tensorflow as tf
import casadi
print("carla:", carla.__version__ if hasattr(carla, "__version__") else "ok")
print("tensorflow:", tf.__version__)
print("casadi:", casadi.__version__)
PY

echo "[2/4] Running intersection experiments ..."
cd "$ROOT_DIR/core/scripts/carla"
python run_all_scenarios.py \
  --scenario_glob "scenario_0*.json" \
  --init_glob "ego_init_*.json" \
  --policies smpc_var_risk smpc_open_loop smpc_fixed_risk \
  --with_notv \
  --with_notv_cl

echo "[3/4] Aggregating metrics ..."
cd "$ROOT_DIR/core"
MPLBACKEND=Agg python scripts/compute_scenario_results.py --compute_metrics

echo "[4/4] Done."
echo "Results directory: $ROOT_DIR/core/results"
