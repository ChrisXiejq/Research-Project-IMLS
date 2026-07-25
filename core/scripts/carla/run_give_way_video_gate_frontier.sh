#!/usr/bin/env bash
set -euo pipefail

# Representative video gate for the fixed-risk frontier.
#
# This intentionally uses the frozen reduced-clear-path-release tuning from
# 20260725_023251_5init_reduced_clear_path_release. Do not replace it with a
# minimal yield_supervisor_mode-only config; that changes the stop position and
# invalidates the qualitative comparison.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_video_gate_frontier_init${INIT_ID:-05}}"
PYTHON_BIN="${PYTHON_BIN:-python}"
INIT_ID="${INIT_ID:-05}"
PREDICTION_MODEL_WEIGHTS="${PREDICTION_MODEL_WEIGHTS:-l5kit_multipath_10_carla_finetuned_head_best}"
PREDICTION_MODEL_ANCHORS="${PREDICTION_MODEL_ANCHORS:-l5kit_clusters_16.npy}"
FROZEN_REDUCED_TUNING_CONFIG="${FROZEN_REDUCED_TUNING_CONFIG:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_frozen.json}"

if [[ -z "${CARLA_ROOT:-}" ]]; then
  cat >&2 <<'EOF'
ERROR: CARLA_ROOT is not set.

Please export the CARLA 0.9.14 root before running this batch, for example:
  export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
EOF
  exit 2
fi

if [[ ! -f "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py" ]]; then
  cat >&2 <<EOF
ERROR: CARLA Python agents were not found under:
  ${CARLA_ROOT}/PythonAPI/carla/agents
EOF
  exit 2
fi

if [[ ! -f "${FROZEN_REDUCED_TUNING_CONFIG}" ]]; then
  cat >&2 <<EOF
ERROR: frozen reduced-intervention tuning config not found:
  ${FROZEN_REDUCED_TUNING_CONFIG}
EOF
  exit 2
fi

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${PYTHONPATH:-}"

if [[ -z "${GUROBI_HOME:-}" && -d "${REPO_DIR}/gurobi/gurobi1103/linux64" ]]; then
  export GUROBI_HOME="${REPO_DIR}/gurobi/gurobi1103/linux64"
fi
if [[ -z "${GUROBI_VERSION:-}" ]]; then
  export GUROBI_VERSION="110"
fi
if [[ -z "${GRB_LICENSE_FILE:-}" && -f "${REPO_DIR}/gurobi/gurobi.lic" ]]; then
  export GRB_LICENSE_FILE="${REPO_DIR}/gurobi/gurobi.lic"
fi
if [[ -n "${GUROBI_HOME:-}" ]]; then
  export LD_LIBRARY_PATH="${GUROBI_HOME}/lib:${LD_LIBRARY_PATH:-}"
fi

MODEL_DIR="${CORE_DIR}/scripts/models/${PREDICTION_MODEL_WEIGHTS}"
if [[ "${PREDICTION_MODEL_WEIGHTS}" = /* ]]; then
  MODEL_DIR="${PREDICTION_MODEL_WEIGHTS}"
fi
if [[ ! -d "${MODEL_DIR}" ]]; then
  cat >&2 <<EOF
ERROR: prediction model directory not found:
  ${MODEL_DIR}

Set PREDICTION_MODEL_WEIGHTS to a model path or copy the fine-tuned model to core/scripts/models/.
EOF
  exit 2
fi

mkdir -p "${RESULTS_DIR}"
TUNING_CONFIG="${RESULTS_DIR}/tuning_reduced_clear_path_release_frozen.json"
cp "${FROZEN_REDUCED_TUNING_CONFIG}" "${TUNING_CONFIG}"

TMP_INIT_DIR="${RESULTS_DIR}/_ego_init_${INIT_ID}"
mkdir -p "${TMP_INIT_DIR}"
ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${INIT_ID}.json" \
  "${TMP_INIT_DIR}/ego_init_${INIT_ID}.json"

cd "${SCRIPT_DIR}"

run_arm() {
  local name="$1"
  local policy="$2"
  local risk_profile="$3"
  shift 3

  local arm_dir="${RESULTS_DIR}/${name}"
  mkdir -p "${arm_dir}"
  echo "Running video gate arm=${name}; results=${arm_dir}"
  "${PYTHON_BIN}" run_all_scenarios.py \
    --scenario_glob "scenario_uk_give_way.json" \
    --init_glob "${TMP_INIT_DIR}/ego_init_${INIT_ID}.json" \
    --results_dir "${arm_dir}" \
    --policies "${policy}" \
    --risk_profile "${risk_profile}" \
    --tuning_config "${TUNING_CONFIG}" \
    --prediction_model_weights "${PREDICTION_MODEL_WEIGHTS}" \
    --prediction_model_anchors "${PREDICTION_MODEL_ANCHORS}" \
    --enable_camera_viz \
    --postprocess_no_plots \
    "$@"
}

run_arm \
  "adaptive_floor_weak" \
  "smpc_var_risk" \
  "adaptive_interaction_severity" \
  --adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}'

run_arm \
  "fixed_medium" \
  "smpc_fixed_risk" \
  "fixed_frontier_medium"

cat > "${RESULTS_DIR}/README.txt" <<EOF
Video gate complete.

Frozen tuning:
  ${TUNING_CONFIG}

Expected qualitative checks:
  - EV should not stop farther upstream than the frozen reduced-clear-path-release run.
  - EV should release after target clearance without a multi-second mechanical pause.
  - EV must enter and maintain the correct post-turn lane.
EOF

echo "Video gate complete: ${RESULTS_DIR}"
