#!/usr/bin/env bash
set -euo pipefail

# Stage A diagnostic run for the post-turn heading problem.
# This does not change controller behaviour.  It only exports
# smpc_lane_entry_heading_diagnostics.{json,csv} from each SMPC subrun.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_lane_entry_heading_diagnostics_check}"
PYTHON_BIN="${PYTHON_BIN:-python}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-1}"

cd "${SCRIPT_DIR}"

ARGS=(
  run_all_scenarios.py
  --scenario_glob "scenario_uk_give_way.json"
  --init_glob "ego_init_01.json"
  --results_dir "${RESULTS_DIR}"
  --policies smpc_var_risk smpc_fixed_risk smpc_open_loop
  --solver_backend gurobi
  --risk_profile adaptive_interaction_severity
  --with_notv
  --with_notv_cl
  --postprocess_plot_scenario scenario_uk_give_way
  --postprocess_plot_init 1
)

if [[ "${ENABLE_CAMERA_VIZ}" != "0" ]]; then
  ARGS+=(--enable_camera_viz)
fi

"${PYTHON_BIN}" "${ARGS[@]}"

"${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${RESULTS_DIR}"

"${PYTHON_BIN}" "${CORE_DIR}/scripts/summarize_lane_entry_heading_diagnostics.py" "${RESULTS_DIR}"

echo "Lane-entry heading diagnostics check complete: ${RESULTS_DIR}"
