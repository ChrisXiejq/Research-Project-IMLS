#!/usr/bin/env bash
set -Eeuo pipefail

# Excluded, camera-off, single-rollout preflight for the prospective
# same-state command-transmission experiment. This run is never pooled with
# the frozen 20-init formal protocol.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
PYTHON_BIN="${PYTHON_BIN:-python}"
RESULTS_DIR="${RESULTS_DIR:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/supervisor_masking_v2/smoke/init116_B1_fixed_medium_assertive}"
PROTOCOL="${PROTOCOL:-${REPO_DIR}/docs/paper/generated/supervisor_masking_v2/protocol/SAME_STATE_SHADOW_PROTOCOL_V2.json}"
SCENARIO_SOURCE="${SCENARIO_SOURCE:-${SCRIPT_DIR}/scenarios/scenario_uk_give_way.json}"
INIT_SOURCE="${INIT_SOURCE:-${SCRIPT_DIR}/scenarios/inits/supervisor_masking_shadow_v2/ego_init_116.json}"
TUNING_CONFIG="${TUNING_CONFIG:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json}"
ADAPTIVE_CONFIG="${ADAPTIVE_CONFIG:-${SCRIPT_DIR}/scenarios/tuning_configs/adaptive_floor_weak_v1.json}"

B1_MODEL="${B1_MODEL:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/capacity_history_thesis_core_v3/training/v3__head-large__lr1e-4__s23__data100/best_model}"
PSTAR_MODEL="${PSTAR_MODEL:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/capacity_history_thesis_core_v3/training/v3__transformer-h1p0-large__lr1e-4__s37__data100/best_model}"
B1_CALIBRATION="${B1_CALIBRATION:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/capacity_history_thesis_core_v3/postprocess/calibration/v3__head-large__lr1e-4__s23__data100/calibration.json}"
PSTAR_CALIBRATION="${PSTAR_CALIBRATION:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/capacity_history_thesis_core_v3/postprocess/calibration/v3__transformer-h1p0-large__lr1e-4__s37__data100/calibration.json}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/assets/l5kit_clusters_16.npy}"

GUROBI_ROOT="${GUROBI_ROOT:-${REPO_DIR}/gurobi}"
export GUROBI_HOME="${GUROBI_HOME:-${GUROBI_ROOT}/gurobi1103/linux64}"
export GUROBI_VERSION="${GUROBI_VERSION:-110}"
export GRB_LICENSE_FILE="${GRB_LICENSE_FILE:-${GUROBI_ROOT}/gurobi.lic}"
export LD_LIBRARY_PATH="${GUROBI_HOME}/lib:${LD_LIBRARY_PATH:-}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${MODELS_DIR}:${PYTHONPATH:-}"

for required in \
  "${PROTOCOL}" "${SCENARIO_SOURCE}" "${INIT_SOURCE}" "${TUNING_CONFIG}" \
  "${ADAPTIVE_CONFIG}" "${B1_MODEL}/saved_model.pb" \
  "${PSTAR_MODEL}/saved_model.pb" "${B1_CALIBRATION}" \
  "${PSTAR_CALIBRATION}" "${ANCHORS}" "${GRB_LICENSE_FILE}" \
  "${GUROBI_HOME}/lib/libgurobi110.so"; do
  test -e "${required}" || { echo "Missing smoke asset: ${required}" >&2; exit 2; }
done

mkdir -p "${RESULTS_DIR}"
exec > >(tee -a "${RESULTS_DIR}/smoke_runner.log") 2>&1

echo "[$(date --iso-8601=seconds)] supervisor-masking V2 excluded smoke start"
"${PYTHON_BIN}" -c 'import casadi as ca,sys; ok=ca.has_conic("gurobi"); print("Gurobi backend:",ok); sys.exit(0 if ok else 2)'
"${PYTHON_BIN}" -c 'import tensorflow as tf,sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'
"${PYTHON_BIN}" -c 'import carla,sys; c=carla.Client("127.0.0.1",2000); c.set_timeout(10); print("CARLA map before load:",c.get_world().get_map().name)'

"${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
  --scenario_glob "${SCENARIO_SOURCE}" \
  --init_glob "${INIT_SOURCE}" \
  --results_dir "${RESULTS_DIR}/rollout" \
  --policies smpc_fixed_risk \
  --risk_profile fixed_frontier_medium \
  --adaptive_risk_config_file "${ADAPTIVE_CONFIG}" \
  --tuning_config "${TUNING_CONFIG}" \
  --prediction_model_weights "${B1_MODEL}" \
  --prediction_model_anchors "${ANCHORS}" \
  --prediction_model_calibration "${B1_CALIBRATION}" \
  --target_style assertive_constant_speed \
  --enable_same_state_shadow_replay \
  --shadow_protocol "${PROTOCOL}" \
  --shadow_ego_init_id 116 \
  --shadow_factual_rollout_id smoke_excluded_init116_B1_fixed_medium_assertive \
  --shadow_factual_predictor B1 \
  --shadow_factual_risk_policy fixed_medium \
  --shadow_b1_weights "${B1_MODEL}" \
  --shadow_b1_anchors "${ANCHORS}" \
  --shadow_b1_calibration "${B1_CALIBRATION}" \
  --shadow_pstar_weights "${PSTAR_MODEL}" \
  --shadow_pstar_anchors "${ANCHORS}" \
  --shadow_pstar_calibration "${PSTAR_CALIBRATION}" \
  --disable_camera_viz \
  --skip_postprocess \
  --no_console_log

"${PYTHON_BIN}" - "${RESULTS_DIR}" <<'PY'
import csv, hashlib, json, sys
from pathlib import Path

root = Path(sys.argv[1])
csvs = list(root.glob("rollout/**/same_state_shadow_commands_v2.csv"))
contracts = list(root.glob("rollout/**/same_state_shadow_run_contract.json"))
if len(csvs) != 1 or len(contracts) != 1:
    raise SystemExit(f"Expected one CSV and one contract, found {len(csvs)} and {len(contracts)}")
rows = list(csv.DictReader(csvs[0].open(newline="", encoding="utf-8")))
states = {}
for row in rows:
    states.setdefault(row["state_key"], []).append(row)
if not states or any(len(group) != 8 for group in states.values()):
    raise SystemExit("Smoke factorial is incomplete")
if any(str(row["shadow_actuated"]).lower() in {"1", "true", "yes"} for row in rows):
    raise SystemExit("Shadow actuation detected")
factual = [row for row in rows if str(row["factual_branch"]).lower() in {"1", "true", "yes"}]
if len(factual) != len(states) or any(str(row["factual_command_parity"]).lower() not in {"1", "true", "yes"} for row in factual):
    raise SystemExit("Factual-command parity failed")
payload = {
    "schema_version": "supervisor_masking_shadow_smoke_v2",
    "status": "pass",
    "excluded_from_formal_analysis": True,
    "ego_init_id": 116,
    "states": len(states),
    "rows": len(rows),
    "shadow_actuation_count": 0,
    "input_csv": str(csvs[0]),
    "input_csv_sha256": hashlib.sha256(csvs[0].read_bytes()).hexdigest(),
    "run_contract": str(contracts[0]),
    "run_contract_sha256": hashlib.sha256(contracts[0].read_bytes()).hexdigest(),
}
target = root / "SMOKE_COMPLETE.json"
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(payload, sort_keys=True))
PY

echo "[$(date --iso-8601=seconds)] supervisor-masking V2 excluded smoke PASS"
