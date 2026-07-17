#!/usr/bin/env bash
set -euo pipefail

# Comprehensive mechanism ablation for the phase-aware adaptive-risk design.
# Defaults to the primary four variants. Use VARIANT_SET=sensitivity or
# VARIANT_SET=all for the parameter-sensitivity matrix.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_10init_comprehensive_adaptive_risk_ablation}"
PYTHON_BIN="${PYTHON_BIN:-python}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"
INIT_COUNT="${INIT_COUNT:-10}"
VARIANT_SET="${VARIANT_SET:-primary}"

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
for idx in $(seq -w 1 "${INIT_COUNT}"); do
  ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${idx}.json" \
    "${TMP_INIT_DIR}/ego_init_${idx}.json"
done

cat > "${RESULTS_DIR}/ablation_manifest.jsonl" <<EOF
{"event":"batch_start","script":"$(basename "$0")","variant_set":"${VARIANT_SET}","init_count":${INIT_COUNT},"scenario_glob":"scenario_uk_give_way.json","policies":["smpc_var_risk","smpc_fixed_risk"],"baseline_commit":"eea6c53f547304af92f697d683f3f12d8af70226"}
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

This run keeps the same scenario, initial states, rule-aware supervisor, and
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
