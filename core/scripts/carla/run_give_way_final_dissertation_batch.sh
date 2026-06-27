#!/usr/bin/env bash
set -euo pipefail

# Final dissertation batch for the right-hand-traffic give-way scenario.
# It keeps the validated +2.75m ego start geometry and runs the proposed
# adaptive-risk method together with the baseline required for paper panels.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_final_dissertation}"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "${SCRIPT_DIR}"

"${PYTHON_BIN}" run_all_scenarios.py \
  --scenario_glob "scenario_uk_give_way.json" \
  --init_glob "ego_init_01.json" \
  --results_dir "${RESULTS_DIR}" \
  --policies smpc_var_risk smpc_fixed_risk smpc_open_loop \
  --solver_backend gurobi \
  --risk_profile adaptive_interaction_severity \
  --with_notv \
  --with_notv_cl \
  --postprocess_plot_scenario scenario_uk_give_way \
  --postprocess_plot_init 1

"${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${RESULTS_DIR}"

echo "Final dissertation batch complete: ${RESULTS_DIR}"
