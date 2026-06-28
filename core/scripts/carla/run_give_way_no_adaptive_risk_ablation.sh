#!/usr/bin/env bash
set -euo pipefail

# No-adaptive-risk dissertation ablation.
# This keeps the validated rule-aware supervisor, +2.75m start geometry,
# 8.0m yield stop buffer, 1.0m release clearance margin, and bounded
# deterministic bypass. Only the adaptive interaction-severity risk update is
# disabled by using the static upstream-risk profile with rule-aware bypass.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_no_adaptive_risk_final_dissertation}"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "${SCRIPT_DIR}"

"${PYTHON_BIN}" run_all_scenarios.py \
  --scenario_glob "scenario_uk_give_way.json" \
  --init_glob "ego_init_01.json" \
  --results_dir "${RESULTS_DIR}" \
  --policies smpc_var_risk smpc_fixed_risk smpc_open_loop \
  --solver_backend gurobi \
  --risk_profile rule_aware_static_risk \
  --with_notv \
  --with_notv_cl \
  --postprocess_plot_scenario scenario_uk_give_way \
  --postprocess_plot_init 1

"${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${RESULTS_DIR}"

echo "No-adaptive-risk ablation batch complete: ${RESULTS_DIR}"
