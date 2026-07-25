#!/usr/bin/env bash
set -euo pipefail

# Comprehensive mechanism ablation for the phase-aware adaptive-risk design.
# Defaults to the primary four variants. Use VARIANT_SET=sensitivity or
# VARIANT_SET=all for the parameter-sensitivity matrix.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_10init_comprehensive_adaptive_risk_ablation}"
PYTHON_BIN="${PYTHON_BIN:-python}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"
INIT_COUNT="${INIT_COUNT:-10}"
VARIANT_SET="${VARIANT_SET:-primary}"
YIELD_SUPERVISOR_MODE="${YIELD_SUPERVISOR_MODE:-full}"
PREDICTION_MODEL_WEIGHTS="${PREDICTION_MODEL_WEIGHTS:-l5kit_multipath_10_carla_finetuned_head_best}"
PREDICTION_MODEL_ANCHORS="${PREDICTION_MODEL_ANCHORS:-l5kit_clusters_16.npy}"

if [[ -z "${CARLA_ROOT:-}" ]]; then
  cat >&2 <<'EOF'
ERROR: CARLA_ROOT is not set.

Please export the CARLA 0.9.14 root before running this batch, for example:
  export CARLA_ROOT=/root/autodl-tmp/CARLA_0.9.14

If you are unsure of the path, locate it with:
  find /root -maxdepth 4 -type f -name CarlaUE4.sh 2>/dev/null
then export CARLA_ROOT to the directory that contains CarlaUE4.sh.
EOF
  exit 2
fi

if [[ "${YIELD_SUPERVISOR_MODE}" != "full" && "${YIELD_SUPERVISOR_MODE}" != "reduced_intervention" ]]; then
  echo "Unsupported YIELD_SUPERVISOR_MODE=${YIELD_SUPERVISOR_MODE}; use full or reduced_intervention." >&2
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
variant_set=${VARIANT_SET}
init_count=${INIT_COUNT}
yield_supervisor_mode=${YIELD_SUPERVISOR_MODE}
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

TMP_INIT_DIR="${RESULTS_DIR}/_ego_init_01_${INIT_COUNT}"
mkdir -p "${TMP_INIT_DIR}"
for idx_num in $(seq 1 "${INIT_COUNT}"); do
  idx="$(printf '%02d' "${idx_num}")"
  ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${idx}.json" \
    "${TMP_INIT_DIR}/ego_init_${idx}.json"
done

TUNING_CONFIG="${RESULTS_DIR}/tuning_${YIELD_SUPERVISOR_MODE}.json"
"${PYTHON_BIN}" - "${YIELD_SUPERVISOR_MODE}" "${TUNING_CONFIG}" <<'PY'
import json
import sys

mode = sys.argv[1]
out_path = sys.argv[2]

config = {
    "config_name": f"adaptive_risk_sweep_{mode}",
    "version": 1,
    "description": (
        "Adaptive-risk sweep tuning config generated by "
        "run_give_way_10init_comprehensive_adaptive_risk_ablation.sh"
    ),
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
            "yield_release_clearance_margin": 1.0,
            "yield_observed_caution_enabled": True,
            "yield_observed_caution_distance": 12.0,
            "yield_observed_caution_min_target_speed": 0.5,
            "yield_steer_damping": 0.25,
            "yield_recovery_enabled": True,
            "yield_recovery_steps": 180,
            "yield_recovery_regen_period": 2,
            "yield_recovery_max_lateral_error": 12.0,
            "yield_recovery_speed": 5.5,
            "yield_recovery_accel": 1.8,
            "yield_supervisor_mode": mode,
        },
        "target": {
            "nominal_speed": 9.0,
            "init_speed": 9.0,
        },
    },
}

if mode == "reduced_intervention":
    ego = config["vehicle_role_overrides"]["ego"]
    ego["yield_recovery_steps"] = 90
    ego["yield_release_clearance_margin"] = 0.5
    ego["yield_recovery_speed"] = 4.5
    ego["yield_recovery_accel"] = 1.0

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PY

cat > "${RESULTS_DIR}/ablation_manifest.jsonl" <<EOF
{"event":"batch_start","script":"$(basename "$0")","variant_set":"${VARIANT_SET}","init_count":${INIT_COUNT},"yield_supervisor_mode":"${YIELD_SUPERVISOR_MODE}","scenario_glob":"scenario_uk_give_way.json","policies":["smpc_var_risk","smpc_fixed_risk"],"baseline_commit":"eea6c53f547304af92f697d683f3f12d8af70226"}
EOF

run_variant() {
  local name="$1"
  local risk_profile="$2"
  local config_json="$3"
  local variant_dir="${RESULTS_DIR}/${name}"

  mkdir -p "${variant_dir}"
  echo "Running ablation variant: ${name} (${risk_profile})"
  printf '%s\n' "${config_json}" > "${variant_dir}/adaptive_risk_config.json"
  printf '{"event":"variant_start","name":"%s","risk_profile":"%s","adaptive_risk_config":%s}\n' \
    "${name}" "${risk_profile}" "${config_json}" >> "${RESULTS_DIR}/ablation_manifest.jsonl"

  "${PYTHON_BIN}" run_all_scenarios.py \
    --scenario_glob "scenario_uk_give_way.json" \
    --init_glob "${TMP_INIT_DIR}/ego_init_*.json" \
    --results_dir "${variant_dir}" \
    --policies smpc_var_risk smpc_fixed_risk \
    --risk_profile "${risk_profile}" \
    --adaptive_risk_config_json "${config_json}" \
    --tuning_config "${TUNING_CONFIG}" \
    --prediction_model_weights "${PREDICTION_MODEL_WEIGHTS}" \
    --prediction_model_anchors "${PREDICTION_MODEL_ANCHORS}" \
    "${camera_args[@]}" \
    --postprocess_no_plots

  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${variant_dir}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${variant_dir}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" \
    --results_dir "${variant_dir}" \
    --compute_metrics

  printf '{"event":"variant_end","name":"%s","variant_dir":"%s"}\n' \
    "${name}" "${variant_dir}" >> "${RESULTS_DIR}/ablation_manifest.jsonl"
}

run_primary_variants() {
  run_variant \
    "phase_floor" \
    "adaptive_interaction_severity" \
    '{"variant_name":"phase_floor"}'

  run_variant \
    "no_phase_floor" \
    "adaptive_interaction_severity_no_floor" \
    '{"variant_name":"no_phase_floor"}'

  run_variant \
    "no_post_clearance_relaxation" \
    "adaptive_interaction_severity_no_relax" \
    '{"variant_name":"no_post_clearance_relaxation"}'

  run_variant \
    "no_phase_awareness" \
    "adaptive_interaction_severity_no_phase_awareness" \
    '{"variant_name":"no_phase_awareness"}'
}

run_sensitivity_variants() {
  run_variant \
    "floor_weak" \
    "adaptive_interaction_severity" \
    '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}'

  run_variant \
    "floor_strong" \
    "adaptive_interaction_severity" \
    '{"variant_name":"floor_strong","approach_preclearance_floor":1.72,"critical_preclearance_floor":1.88,"near_preclearance_floor":1.95}'

  run_variant \
    "relax_mild" \
    "adaptive_interaction_severity" \
    '{"variant_name":"relax_mild","relaxed_after_clearance_tight":1.4395314709384563}'

  run_variant \
    "severity_low_gain" \
    "adaptive_interaction_severity" \
    '{"variant_name":"severity_low_gain","mild_tightening_scale":0.20}'

  run_variant \
    "severity_high_gain" \
    "adaptive_interaction_severity" \
    '{"variant_name":"severity_high_gain","mild_tightening_scale":0.50}'
}

case "${VARIANT_SET}" in
  primary)
    run_primary_variants
    ;;
  sensitivity)
    run_sensitivity_variants
    ;;
  all)
    run_primary_variants
    run_sensitivity_variants
    ;;
  *)
    echo "Unsupported VARIANT_SET=${VARIANT_SET}; use primary, sensitivity, or all." >&2
    exit 2
    ;;
esac

cat > "${RESULTS_DIR}/ablation_summary.md" <<EOF
# Comprehensive Adaptive Risk Ablation

Variant set: \`${VARIANT_SET}\`
Yield supervisor mode: \`${YIELD_SUPERVISOR_MODE}\`

This run keeps the same scenario, initial states, selected supervisor, and
fixed-risk baseline. Only the adaptive-risk mapping used by \`smpc_var_risk\`
is changed across variants.

Primary variants:

- \`phase_floor\`: frozen phase-aware method.
- \`no_phase_floor\`: disables the pre-clearance risk floor.
- \`no_post_clearance_relaxation\`: keeps the pre-clearance floor but disables post-clearance relaxation.
- \`no_phase_awareness\`: disables both pre-clearance floor and post-clearance relaxation.

Sensitivity variants:

- \`floor_weak\`
- \`floor_strong\`
- \`relax_mild\`
- \`severity_low_gain\`
- \`severity_high_gain\`

Inspect each variant directory for:

- \`postcarla_trajectory_gate.md\`
- \`risk_by_conflict_distance_summary.md\`
- \`risk_by_conflict_distance_comparison.csv\`
- \`paper_metrics_summary.md\`
EOF

echo "Comprehensive adaptive risk ablation complete: ${RESULTS_DIR}"
