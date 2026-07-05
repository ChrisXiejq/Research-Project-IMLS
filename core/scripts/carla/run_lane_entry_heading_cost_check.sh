#!/usr/bin/env bash
set -euo pipefail

# Stage B1.1: stronger bounded lane-entry heading objective plus a small
# anti-early-stop completion delay.
# The controller change is enabled through give_way_smpc_tuning.json and only
# applies after the priority target has cleared the conflict zone near the
# original goal. This script keeps the same validation/gate surface as Stage A.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_lane_entry_heading_cost_b11_check}"
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

echo "Lane-entry heading cost B1.1 check complete: ${RESULTS_DIR}"
