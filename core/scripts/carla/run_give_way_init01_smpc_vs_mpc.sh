#!/usr/bin/env bash
set -euo pipefail

# Init01-focused fixed-risk frontier vs adaptive-risk SMPC comparison.
#
# This is intentionally not a 5-init frontier and does not strengthen the
# supervisor. The goal is to isolate whether phase-aware adaptive/variable-risk
# SMPC handles the hard init01 interaction better than the fixed-risk SMPC
# frontier under the current give-way setup.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_init01_smpc_fixed_frontier_vs_adaptive}"
PYTHON_BIN="${PYTHON_BIN:-python}"
INIT_ID="${INIT_ID:-01}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"
SKIP_COMPLETED_SUBRUNS="${SKIP_COMPLETED_SUBRUNS:-0}"
PREDICTION_MODEL_WEIGHTS="${PREDICTION_MODEL_WEIGHTS:-l5kit_multipath_10_carla_finetuned_head_best}"
PREDICTION_MODEL_ANCHORS="${PREDICTION_MODEL_ANCHORS:-l5kit_clusters_16.npy}"
FROZEN_REDUCED_TUNING_CONFIG="${FROZEN_REDUCED_TUNING_CONFIG:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_frozen.json}"

if [[ "${INIT_ID}" != "01" ]]; then
  cat >&2 <<EOF
ERROR: this focused comparison must run init01 only.
  got INIT_ID=${INIT_ID}
EOF
  exit 2
fi

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

"${PYTHON_BIN}" - <<'PY'
import os
import sys

import casadi as ca

ok = bool(ca.has_conic("gurobi"))
print(
    "CasADi/Gurobi preflight:",
    {
        "casadi": ca.__version__,
        "has_conic_gurobi": ok,
        "has_nlpsol_gurobi": bool(ca.has_nlpsol("gurobi")),
        "GUROBI_HOME": os.environ.get("GUROBI_HOME"),
        "GUROBI_VERSION": os.environ.get("GUROBI_VERSION"),
        "GRB_LICENSE_FILE": os.environ.get("GRB_LICENSE_FILE"),
    },
)
if not ok:
    print("ERROR: ca.has_conic('gurobi') must be True.", file=sys.stderr)
    sys.exit(2)
PY

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
START_EPOCH="$(date +%s)"
START_TIME="$(date '+%Y-%m-%dT%H:%M:%S%z')"

format_duration() {
  local total_seconds="$1"
  local hours=$((total_seconds / 3600))
  local minutes=$(((total_seconds % 3600) / 60))
  local seconds=$((total_seconds % 60))
  printf "%02d:%02d:%02d" "${hours}" "${minutes}" "${seconds}"
}

write_run_timing() {
  local exit_code="$1"
  local end_epoch
  local end_time
  local duration_seconds
  local duration_hms

  end_epoch="$(date +%s)"
  end_time="$(date '+%Y-%m-%dT%H:%M:%S%z')"
  duration_seconds=$((end_epoch - START_EPOCH))
  duration_hms="$(format_duration "${duration_seconds}")"

  cat > "${RESULTS_DIR}/run_timing.txt" <<EOF
script=$(basename "$0")
results_dir=${RESULTS_DIR}
init_id=${INIT_ID}
start_time=${START_TIME}
end_time=${end_time}
duration_seconds=${duration_seconds}
duration_hms=${duration_hms}
exit_code=${exit_code}
EOF

  echo "Run timing: ${duration_hms} (${duration_seconds}s), exit_code=${exit_code}"
  echo "Timing report: ${RESULTS_DIR}/run_timing.txt"
}

trap 'status=$?; write_run_timing "${status}"; exit "${status}"' EXIT

cd "${SCRIPT_DIR}"

camera_args=()
if [[ "${ENABLE_CAMERA_VIZ}" == "1" ]]; then
  camera_args+=(--enable_camera_viz)
else
  camera_args+=(--disable_camera_viz)
fi

resume_args=()
if [[ "${SKIP_COMPLETED_SUBRUNS}" == "1" ]]; then
  resume_args+=(--skip_completed_subruns)
fi

TMP_INIT_DIR="${RESULTS_DIR}/_ego_init_${INIT_ID}"
mkdir -p "${TMP_INIT_DIR}"
ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${INIT_ID}.json" \
  "${TMP_INIT_DIR}/ego_init_${INIT_ID}.json"

TUNING_CONFIG="${RESULTS_DIR}/tuning_reduced_intervention_frozen.json"
cp "${FROZEN_REDUCED_TUNING_CONFIG}" "${TUNING_CONFIG}"

cat > "${RESULTS_DIR}/comparison_manifest.jsonl" <<EOF
{"event":"batch_start","script":"$(basename "$0")","init_id":"${INIT_ID}","scenario_glob":"scenario_uk_give_way.json","arms":["smpc_fixed_aggressive","smpc_fixed_medium","smpc_fixed_conservative","smpc_adaptive_floor_weak"],"supervisor_change":"planner_ownership_stress_if_enabled_in_tuning","comparison":"fixed-risk SMPC frontier vs adaptive-risk SMPC"}
EOF

postprocess_arm() {
  local arm_dir="$1"
  local required_policy="$2"
  shift 2

  set +e
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" \
    "${arm_dir}" \
    --required-policies "${required_policy}" \
    "$@"
  local gate_exit=$?
  set -e

  printf '{"event":"postcarla_gate","arm_dir":"%s","required_policy":"%s","exit_code":%s}\n' \
    "${arm_dir}" "${required_policy}" "${gate_exit}" >> "${RESULTS_DIR}/comparison_manifest.jsonl"

  "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" \
    --results_dir "${arm_dir}" \
    --compute_metrics

  if [[ "${required_policy}" == smpc_* ]]; then
    "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${arm_dir}"
    if [[ -f "${REPO_DIR}/docs/paper/diagnose_supervisor_feedback_step1.py" ]]; then
      "${PYTHON_BIN}" "${REPO_DIR}/docs/paper/diagnose_supervisor_feedback_step1.py" \
        --results-dir "${arm_dir}"
    fi
  fi
}

run_arm() {
  local name="$1"
  local policy="$2"
  local risk_profile="$3"
  shift 3

  local arm_dir="${RESULTS_DIR}/${name}"
  mkdir -p "${arm_dir}"
  echo "Running init01 comparison arm=${name}; policy=${policy}; risk_profile=${risk_profile}"
  printf '{"event":"arm_start","name":"%s","policy":"%s","risk_profile":"%s"}\n' \
    "${name}" "${policy}" "${risk_profile}" >> "${RESULTS_DIR}/comparison_manifest.jsonl"

  "${PYTHON_BIN}" run_all_scenarios.py \
    --scenario_glob "scenario_uk_give_way.json" \
    --init_glob "${TMP_INIT_DIR}/ego_init_${INIT_ID}.json" \
    --results_dir "${arm_dir}" \
    --policies "${policy}" \
    --risk_profile "${risk_profile}" \
    --tuning_config "${TUNING_CONFIG}" \
    --prediction_model_weights "${PREDICTION_MODEL_WEIGHTS}" \
    --prediction_model_anchors "${PREDICTION_MODEL_ANCHORS}" \
    "${camera_args[@]}" \
    "${resume_args[@]}" \
    --postprocess_no_plots \
    "$@"

  printf '{"event":"arm_rollout_end","name":"%s","arm_dir":"%s"}\n' \
    "${name}" "${arm_dir}" >> "${RESULTS_DIR}/comparison_manifest.jsonl"
}

run_arm "smpc_fixed_aggressive" "smpc_fixed_risk" "fixed_frontier_aggressive"
postprocess_arm "${RESULTS_DIR}/smpc_fixed_aggressive" "smpc_fixed_risk"

run_arm "smpc_fixed_medium" "smpc_fixed_risk" "fixed_frontier_medium"
postprocess_arm "${RESULTS_DIR}/smpc_fixed_medium" "smpc_fixed_risk"

run_arm "smpc_fixed_conservative" "smpc_fixed_risk" "fixed_frontier_conservative"
postprocess_arm "${RESULTS_DIR}/smpc_fixed_conservative" "smpc_fixed_risk"

run_arm \
  "smpc_adaptive_floor_weak" \
  "smpc_var_risk" \
  "adaptive_interaction_severity" \
  --adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}'
postprocess_arm "${RESULTS_DIR}/smpc_adaptive_floor_weak" "smpc_var_risk"

cat > "${RESULTS_DIR}/README.md" <<EOF
# Init01 Fixed-Risk Frontier vs Adaptive-Risk SMPC Focus Run

This run intentionally focuses on \`ego_init_01\` only.

It does not strengthen supervisor logic and does not run deterministic MPC.
The comparison target is whether phase-aware adaptive/variable-risk SMPC handles
the hard give-way interaction better than the fixed-risk SMPC frontier under
the same scenario and current frozen tuning.

Primary evidence:

- post-CARLA footprint collision / min footprint separation
- give-way order timing
- completion validity
- risk-vs-conflict-distance trace
- supervisor masking diagnostics
EOF

echo "Init01 fixed-risk frontier vs adaptive-risk SMPC comparison complete: ${RESULTS_DIR}"
