#!/usr/bin/env bash
set -euo pipefail

# Lightweight ablation for the dissertation give-way experiment.
# It compares the final phase-aware adaptive risk mapping against the same
# adaptive severity mapping with the pre-clearance tightening floor disabled.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_10init_adaptive_risk_ablation}"
PYTHON_BIN="${PYTHON_BIN:-python}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"
INIT_COUNT="${INIT_COUNT:-10}"

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

cat > "${RESULTS_DIR}/ablation_manifest.json" <<EOF
{
  "script": "$(basename "$0")",
  "purpose": "Compare phase-aware adaptive risk floor against adaptive severity mapping without the pre-clearance floor.",
  "baseline_commit": "eea6c53f547304af92f697d683f3f12d8af70226",
  "scenario_glob": "scenario_uk_give_way.json",
  "init_count": ${INIT_COUNT},
  "policies": ["smpc_var_risk", "smpc_fixed_risk"],
  "variants": [
    {
      "name": "phase_floor",
      "risk_profile": "adaptive_interaction_severity",
      "description": "Final dissertation method with approach/critical/near pre-clearance tightening floors."
    },
    {
      "name": "no_phase_floor",
      "risk_profile": "adaptive_interaction_severity_no_floor",
      "description": "Ablation that keeps adaptive severity and target-clearance relaxation but disables the pre-clearance tightening floor."
    }
  ]
}
EOF

run_variant() {
  local name="$1"
  local risk_profile="$2"
  local variant_dir="${RESULTS_DIR}/${name}"

  mkdir -p "${variant_dir}"
  echo "Running ablation variant: ${name} (${risk_profile})"

  "${PYTHON_BIN}" run_all_scenarios.py \
    --scenario_glob "scenario_uk_give_way.json" \
    --init_glob "${TMP_INIT_DIR}/ego_init_*.json" \
    --results_dir "${variant_dir}" \
    --policies smpc_var_risk smpc_fixed_risk \
    --risk_profile "${risk_profile}" \
    "${camera_args[@]}" \
    --postprocess_no_plots

  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${variant_dir}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${variant_dir}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" \
    --results_dir "${variant_dir}" \
    --compute_metrics
}

run_variant "phase_floor" "adaptive_interaction_severity"
run_variant "no_phase_floor" "adaptive_interaction_severity_no_floor"

cat > "${RESULTS_DIR}/ablation_summary.md" <<EOF
# Adaptive Risk Ablation

This run compares:

- \`phase_floor\`: final phase-aware adaptive risk mapping.
- \`no_phase_floor\`: same adaptive severity mapping with pre-clearance floors disabled.

Inspect each variant directory:

- \`${RESULTS_DIR}/phase_floor/postcarla_trajectory_gate.md\`
- \`${RESULTS_DIR}/phase_floor/risk_by_conflict_distance_summary.md\`
- \`${RESULTS_DIR}/no_phase_floor/postcarla_trajectory_gate.md\`
- \`${RESULTS_DIR}/no_phase_floor/risk_by_conflict_distance_summary.md\`

Expected dissertation evidence:

- \`phase_floor\` should show positive \`var_minus_fixed_risk_tightening_mean\` in pre-clearance approach/critical buckets.
- \`no_phase_floor\` should show weaker or non-monotonic pre-clearance tightening, especially in the critical bucket.
- Both variants should preserve PASS safety gates before considering a larger ablation.
EOF

echo "10-init adaptive risk ablation complete: ${RESULTS_DIR}"
