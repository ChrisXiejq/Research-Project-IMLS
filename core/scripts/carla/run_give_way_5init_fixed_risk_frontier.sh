#!/usr/bin/env bash
set -euo pipefail

# Fixed-risk frontier experiment after supervisor feedback.
#
# This script keeps the fine-tuned predictor, init set, and selected
# reduced-intervention supervisor fixed, while varying only the fixed-risk
# static tightening level. The adaptive-risk arm uses the selected floor_weak
# setting from the reduced-supervisor sensitivity sweep.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_5init_fixed_risk_frontier}"
PYTHON_BIN="${PYTHON_BIN:-python}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"
INIT_COUNT="${INIT_COUNT:-5}"
YIELD_SUPERVISOR_MODE="${YIELD_SUPERVISOR_MODE:-reduced_intervention}"
PREDICTION_MODEL_WEIGHTS="${PREDICTION_MODEL_WEIGHTS:-l5kit_multipath_10_carla_finetuned_head_best}"
PREDICTION_MODEL_ANCHORS="${PREDICTION_MODEL_ANCHORS:-l5kit_clusters_16.npy}"
RESUME_COMPLETED="${RESUME_COMPLETED:-0}"
INCLUDE_PERFORMANCE_ADAPTIVE="${INCLUDE_PERFORMANCE_ADAPTIVE:-0}"

if [[ -z "${CARLA_ROOT:-}" ]]; then
  cat >&2 <<'EOF'
ERROR: CARLA_ROOT is not set.

Please export the CARLA 0.9.14 root before running this batch, for example:
  export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
EOF
  exit 2
fi

if [[ "${YIELD_SUPERVISOR_MODE}" != "reduced_intervention" ]]; then
  cat >&2 <<EOF
ERROR: fixed-risk frontier must use the frozen reduced supervisor.
  got YIELD_SUPERVISOR_MODE=${YIELD_SUPERVISOR_MODE}
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
init_count=${INIT_COUNT}
yield_supervisor_mode=${YIELD_SUPERVISOR_MODE}
include_performance_adaptive=${INCLUDE_PERFORMANCE_ADAPTIVE}
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
if [[ "${RESUME_COMPLETED}" == "1" ]]; then
  resume_args+=(--skip_completed_subruns)
fi

TMP_INIT_DIR="${RESULTS_DIR}/_ego_init_01_${INIT_COUNT}"
mkdir -p "${TMP_INIT_DIR}"
for idx_num in $(seq 1 "${INIT_COUNT}"); do
  idx="$(printf '%02d' "${idx_num}")"
  ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${idx}.json" \
    "${TMP_INIT_DIR}/ego_init_${idx}.json"
done

TUNING_CONFIG="${RESULTS_DIR}/tuning_reduced_intervention.json"
"${PYTHON_BIN}" - "${TUNING_CONFIG}" <<'PY'
import json
import sys

out_path = sys.argv[1]
config = {
    "config_name": "fixed_risk_frontier_reduced_intervention",
    "version": 1,
    "description": "Frozen reduced-intervention supervisor for fixed-risk frontier.",
    "vehicle_role_overrides": {
        "ego": {
            "nominal_speed": 6.0,
            "N": 10,
            "dt": 0.2,
            "num_modes": 3,
            "collision_d_min": 0.5,
            "collision_ellipse_half_length": 3.8,
            "collision_ellipse_half_width": 1.8,
            "reference_regen_max_lateral_error": 1.5,
            "yield_stop_enabled": True,
            "yield_stop_speed": 0.2,
            "yield_caution_speed": 3.5,
            "yield_creep_speed": 1.5,
            "yield_caution_decel": -4.0,
            "yield_reference_min_speed": 0.8,
            "yield_reference_decel": -3.75,
            "yield_stop_decel": -5.0,
            "yield_emergency_brake_enabled": True,
            "yield_emergency_decel": -7.0,
            "yield_emergency_jerk_limit": 10.0,
            "yield_emergency_conflict_margin": 1.25,
            "yield_hard_stop_target_distance": 12.0,
            "yield_hard_stop_conflict_distance": 13.0,
            "yield_conflict_radius": 4.0,
            "yield_stop_buffer_distance": 7.0,
            "yield_footprint_clearance_margin": 1.5,
            "yield_brake_distance_margin": 3.5,
            "yield_wait_steer_lookahead_distance": 6.0,
            "yield_wait_steer_gain": 1.0,
            "yield_ttc_margin": 0.8,
            "yield_activation_distance": 12.0,
            "yield_hold_distance": 3.0,
            "yield_release_time": 0.3,
            "yield_release_clearance_margin": 0.5,
            "yield_observed_caution_enabled": True,
            "yield_observed_caution_distance": 12.0,
            "yield_observed_caution_min_target_speed": 0.5,
            "yield_steer_damping": 0.25,
            "yield_recovery_enabled": True,
            "yield_recovery_steps": 90,
            "yield_recovery_regen_period": 2,
            "yield_recovery_max_lateral_error": 12.0,
            "yield_recovery_speed": 4.5,
            "yield_recovery_accel": 1.0,
            "yield_supervisor_mode": "reduced_intervention",
        },
        "target": {
            "nominal_speed": 9.0,
            "init_speed": 9.0,
        },
    },
}

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PY

cat > "${RESULTS_DIR}/frontier_manifest.jsonl" <<EOF
{"event":"batch_start","script":"$(basename "$0")","init_count":${INIT_COUNT},"yield_supervisor_mode":"${YIELD_SUPERVISOR_MODE}","scenario_glob":"scenario_uk_give_way.json","frontier":["fixed_aggressive","fixed_medium","fixed_conservative","adaptive_floor_weak"],"include_performance_adaptive":${INCLUDE_PERFORMANCE_ADAPTIVE}}
EOF

postprocess_variant() {
  local variant_dir="$1"
  local required_policy="$2"

  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" \
    "${variant_dir}" \
    --required-policies "${required_policy}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${variant_dir}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" \
    --results_dir "${variant_dir}" \
    --compute_metrics

  if [[ -f "${REPO_DIR}/docs/paper/diagnose_supervisor_feedback_step1.py" ]]; then
    "${PYTHON_BIN}" "${REPO_DIR}/docs/paper/diagnose_supervisor_feedback_step1.py" \
      --results-dir "${variant_dir}"
  fi
}

run_fixed_variant() {
  local name="$1"
  local risk_profile="$2"
  local variant_dir="${RESULTS_DIR}/${name}"

  mkdir -p "${variant_dir}"
  echo "Running fixed-risk frontier variant: ${name} (${risk_profile})"
  printf '{"event":"variant_start","name":"%s","policy":"smpc_fixed_risk","risk_profile":"%s"}\n' \
    "${name}" "${risk_profile}" >> "${RESULTS_DIR}/frontier_manifest.jsonl"

  "${PYTHON_BIN}" run_all_scenarios.py \
    --scenario_glob "scenario_uk_give_way.json" \
    --init_glob "${TMP_INIT_DIR}/ego_init_*.json" \
    --results_dir "${variant_dir}" \
    --policies smpc_fixed_risk \
    --risk_profile "${risk_profile}" \
    --tuning_config "${TUNING_CONFIG}" \
    --prediction_model_weights "${PREDICTION_MODEL_WEIGHTS}" \
    --prediction_model_anchors "${PREDICTION_MODEL_ANCHORS}" \
    "${camera_args[@]}" \
    "${resume_args[@]}" \
    --postprocess_no_plots

  postprocess_variant "${variant_dir}" "smpc_fixed_risk"
  printf '{"event":"variant_end","name":"%s","variant_dir":"%s"}\n' \
    "${name}" "${variant_dir}" >> "${RESULTS_DIR}/frontier_manifest.jsonl"
}

run_adaptive_variant() {
  local name="$1"
  local config_json="$2"
  local variant_dir="${RESULTS_DIR}/${name}"

  mkdir -p "${variant_dir}"
  echo "Running adaptive-risk frontier variant: ${name}"
  printf '%s\n' "${config_json}" > "${variant_dir}/adaptive_risk_config.json"
  printf '{"event":"variant_start","name":"%s","policy":"smpc_var_risk","risk_profile":"adaptive_interaction_severity","adaptive_risk_config":%s}\n' \
    "${name}" "${config_json}" >> "${RESULTS_DIR}/frontier_manifest.jsonl"

  "${PYTHON_BIN}" run_all_scenarios.py \
    --scenario_glob "scenario_uk_give_way.json" \
    --init_glob "${TMP_INIT_DIR}/ego_init_*.json" \
    --results_dir "${variant_dir}" \
    --policies smpc_var_risk \
    --risk_profile "adaptive_interaction_severity" \
    --adaptive_risk_config_json "${config_json}" \
    --tuning_config "${TUNING_CONFIG}" \
    --prediction_model_weights "${PREDICTION_MODEL_WEIGHTS}" \
    --prediction_model_anchors "${PREDICTION_MODEL_ANCHORS}" \
    "${camera_args[@]}" \
    "${resume_args[@]}" \
    --postprocess_no_plots

  postprocess_variant "${variant_dir}" "smpc_var_risk"
  printf '{"event":"variant_end","name":"%s","variant_dir":"%s"}\n' \
    "${name}" "${variant_dir}" >> "${RESULTS_DIR}/frontier_manifest.jsonl"
}

run_fixed_variant "fixed_aggressive" "fixed_frontier_aggressive"
run_fixed_variant "fixed_medium" "fixed_frontier_medium"
run_fixed_variant "fixed_conservative" "fixed_frontier_conservative"
run_adaptive_variant \
  "adaptive_floor_weak" \
  '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}'

if [[ "${INCLUDE_PERFORMANCE_ADAPTIVE}" == "1" ]]; then
  run_adaptive_variant \
    "adaptive_severity_high_gain" \
    '{"variant_name":"severity_high_gain","mild_tightening_scale":0.50}'
fi

cat > "${RESULTS_DIR}/frontier_summary.md" <<EOF
# Fixed-Risk Frontier Experiment

Yield supervisor mode: \`${YIELD_SUPERVISOR_MODE}\`
Init count: \`${INIT_COUNT}\`
Resume completed subruns: \`${RESUME_COMPLETED}\`

Variants:

- \`fixed_aggressive\`: static tightening 1.28155, target probability about 0.90.
- \`fixed_medium\`: static tightening 1.64, current default fixed-risk baseline.
- \`fixed_conservative\`: static tightening 2.05375, paper epsilon 0.02 target probability.
- \`adaptive_floor_weak\`: selected phase-aware adaptive-risk candidate.

Decision goal:

\`\`\`text
Check whether adaptive_floor_weak is Pareto-favourable or at least not
Pareto-dominated by the fixed-risk frontier under the same reduced supervisor.
\`\`\`

Inspect each variant directory for:

- \`postcarla_trajectory_gate.md\`
- \`risk_by_conflict_distance_summary.md\`
- \`paper_metrics_summary.md\`
- \`diagnostics_after_supervisor_feedback/step1_diagnostic_report.md\`
EOF

if [[ -f "${REPO_DIR}/docs/paper/generate_fixed_risk_frontier_report.py" ]]; then
  "${PYTHON_BIN}" "${REPO_DIR}/docs/paper/generate_fixed_risk_frontier_report.py" \
    --result-dir "${RESULTS_DIR}"
fi

echo "Fixed-risk frontier experiment complete: ${RESULTS_DIR}"
