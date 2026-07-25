#!/usr/bin/env bash
set -euo pipefail

# Supervisor ablation after supervisor feedback.
# Runs:
#   1) reduced_intervention supervisor: the frozen main baseline.
#   2) full supervisor: comparison condition that exposes supervisor masking.
#
# Both modes use the same frozen numeric tuning. The only intentional
# difference is yield_supervisor_mode.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_10init_supervisor_ablation}"
PYTHON_BIN="${PYTHON_BIN:-python}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"
INIT_COUNT="${INIT_COUNT:-10}"
PREDICTION_MODEL_WEIGHTS="${PREDICTION_MODEL_WEIGHTS:-l5kit_multipath_10_carla_finetuned_head_best}"
PREDICTION_MODEL_ANCHORS="${PREDICTION_MODEL_ANCHORS:-l5kit_clusters_16.npy}"
SUPERVISOR_MODES="${SUPERVISOR_MODES:-reduced_intervention full}"
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
    print(
        "ERROR: CasADi conic Gurobi plugin is unavailable. "
        "This experiment uses ca.Opti('conic'), so ca.has_conic('gurobi') must be True.",
        file=sys.stderr,
    )
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

if [[ ! -f "${FROZEN_REDUCED_TUNING_CONFIG}" ]]; then
  cat >&2 <<EOF
ERROR: frozen reduced-intervention tuning config not found:
  ${FROZEN_REDUCED_TUNING_CONFIG}
EOF
  exit 2
fi

mkdir -p "${RESULTS_DIR}"
cd "${SCRIPT_DIR}"

camera_args=()
if [[ "${ENABLE_CAMERA_VIZ}" == "1" ]]; then
  camera_args+=(--enable_camera_viz)
else
  camera_args+=(--disable_camera_viz)
fi

TMP_INIT_DIR="${RESULTS_DIR}/_ego_init_01_${INIT_COUNT}"
mkdir -p "${TMP_INIT_DIR}"
for idx_num in $(seq 1 "${INIT_COUNT}"); do
  idx="$(printf '%02d' "${idx_num}")"
  ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${idx}.json" \
    "${TMP_INIT_DIR}/ego_init_${idx}.json"
done

make_tuning_config() {
  local mode="$1"
  local out_path="$2"
  "${PYTHON_BIN}" - "$mode" "${FROZEN_REDUCED_TUNING_CONFIG}" "$out_path" <<'PY'
import json
import sys

mode = sys.argv[1]
base_path = sys.argv[2]
out_path = sys.argv[3]

with open(base_path, "r", encoding="utf-8") as f:
    config = json.load(f)

config["config_name"] = f"supervisor_ablation_{mode}_from_frozen_reduced"
config["description"] = (
    "Supervisor ablation config generated from the frozen reduced-clear-path-release "
    "numeric tuning. Only yield_supervisor_mode is changed."
)
config["vehicle_role_overrides"]["ego"]["yield_supervisor_mode"] = mode

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PY
}

run_mode() {
  local mode="$1"
  local label="$2"
  local mode_dir="${RESULTS_DIR}/${label}"
  local tuning_config="${RESULTS_DIR}/tuning_${label}.json"

  mkdir -p "${mode_dir}"
  make_tuning_config "${mode}" "${tuning_config}"

  echo "Running supervisor mode=${mode}; results=${mode_dir}"
  "${PYTHON_BIN}" run_all_scenarios.py \
    --scenario_glob "scenario_uk_give_way.json" \
    --init_glob "${TMP_INIT_DIR}/ego_init_*.json" \
    --results_dir "${mode_dir}" \
    --policies smpc_var_risk smpc_fixed_risk \
    --risk_profile adaptive_interaction_severity \
    --tuning_config "${tuning_config}" \
    --prediction_model_weights "${PREDICTION_MODEL_WEIGHTS}" \
    --prediction_model_anchors "${PREDICTION_MODEL_ANCHORS}" \
    "${camera_args[@]}" \
    --postprocess_no_plots

  if ! "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${mode_dir}"; then
    echo "WARNING: post-CARLA gate reported FAIL for ${mode}; continuing diagnostics." >&2
  fi
  if ! "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${mode_dir}"; then
    echo "WARNING: risk-by-conflict-distance diagnostics failed for ${mode}; continuing." >&2
  fi
  if ! "${PYTHON_BIN}" "${REPO_DIR}/docs/paper/diagnose_supervisor_feedback_step1.py" \
    --results-dir "${mode_dir}"; then
    echo "WARNING: supervisor feedback diagnostics failed for ${mode}; continuing." >&2
  fi
}

for mode in ${SUPERVISOR_MODES}; do
  case "${mode}" in
    full)
      run_mode "full" "full_supervisor"
      ;;
    reduced_intervention)
      run_mode "reduced_intervention" "reduced_intervention_supervisor"
      ;;
    *)
      echo "ERROR: unsupported supervisor mode in SUPERVISOR_MODES: ${mode}" >&2
      exit 2
      ;;
  esac
done

cat > "${RESULTS_DIR}/README.txt" <<EOF
Supervisor ablation complete.

Subdirectories:
  Generated according to SUPERVISOR_MODES=${SUPERVISOR_MODES}

Compare:
  diagnostics_after_supervisor_feedback/step1_diagnostic_report.md
  postcarla_trajectory_gate.md
  risk_by_conflict_distance_summary.md
  paper_metrics_summary.md
EOF

echo "10-init supervisor ablation complete: ${RESULTS_DIR}"
