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
