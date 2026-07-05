#!/usr/bin/env bash
set -euo pipefail

# Full intersection-only batch for the validated give-way baseline.
# This uses the same scenario, tuning, and adaptive_interaction_severity risk
# profile as run_give_way_final_dissertation_batch.sh, but expands the initial
# conditions to the migrated 50 intersection initial states.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_50init_final_dissertation}"
PYTHON_BIN="${PYTHON_BIN:-python}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"

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

"${PYTHON_BIN}" run_all_scenarios.py \
  --scenario_glob "scenario_uk_give_way.json" \
  --init_glob "paper_intersection_50/ego_init_*.json" \
  --results_dir "${RESULTS_DIR}" \
  --policies smpc_var_risk smpc_fixed_risk smpc_open_loop \
  --risk_profile adaptive_interaction_severity \
  "${camera_args[@]}" \
  --postprocess_no_plots

"${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${RESULTS_DIR}"

echo "50-init final dissertation batch complete: ${RESULTS_DIR}"
