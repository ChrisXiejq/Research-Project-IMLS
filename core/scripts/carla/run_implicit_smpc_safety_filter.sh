#!/usr/bin/env bash
set -euo pipefail

# Supervisor-free implicit-SMPC give-way experiment.
#
# Default: one difficult pilot (ego_init_01).  For the formal 50-init matrix:
#   INIT_GLOB='paper_intersection_50/ego_init_*.json' ./run_implicit_smpc_safety_filter.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
INIT_GLOB="${INIT_GLOB:-paper_intersection_50/ego_init_01.json}"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_implicit_smpc_safety_filter}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"
CARLA_HOST="${CARLA_HOST:-127.0.0.1}"
CARLA_PORT="${CARLA_PORT:-2000}"
TUNING_CONFIG="${TUNING_CONFIG:-}"
RISK_PROFILE="${RISK_PROFILE:-paper_eps_002}"

if [[ -z "${CARLA_ROOT:-}" ]]; then
  echo "ERROR: CARLA_ROOT must point to the CARLA 0.9.14 installation." >&2
  exit 2
fi
if [[ ! -f "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py" ]]; then
  echo "ERROR: CARLA Python agents were not found below ${CARLA_ROOT}." >&2
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

"${PYTHON_BIN}" -c 'import casadi as ca, sys; ok=bool(ca.has_conic("gurobi")); print({"casadi": ca.__version__, "has_conic_gurobi": ok}); sys.exit(0 if ok else 2)'

camera_args=(--disable_camera_viz)
if [[ "${ENABLE_CAMERA_VIZ}" == "1" ]]; then
  camera_args=(--enable_camera_viz)
fi
tuning_args=()
if [[ -n "${TUNING_CONFIG}" ]]; then
  tuning_args=(--tuning_config "${TUNING_CONFIG}")
fi

mkdir -p "${RESULTS_DIR}"
cd "${SCRIPT_DIR}"
"${PYTHON_BIN}" run_all_scenarios.py \
  --scenario_glob scenario_implicit_smpc_give_way.json \
  --init_glob "${INIT_GLOB}" \
  --results_dir "${RESULTS_DIR}" \
  --carla_host "${CARLA_HOST}" \
  --carla_port "${CARLA_PORT}" \
  --policies smpc_var_risk \
  --risk_profile "${RISK_PROFILE}" \
  --target_style assertive_constant_speed \
  --skip_postprocess \
  "${tuning_args[@]}" \
  "${camera_args[@]}"

set +e
"${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" \
  "${RESULTS_DIR}" \
  --required-policies smpc_var_risk
gate_status=$?
"${PYTHON_BIN}" "${CORE_DIR}/scripts/analyze_implicit_smpc_safety_filter.py" \
  "${RESULTS_DIR}"
phase_status=$?
set -e

echo "Results: ${RESULTS_DIR}"
if [[ "${gate_status}" -ne 0 || "${phase_status}" -ne 0 ]]; then
  echo "Implicit-SMPC experiment failed one or more safety/behaviour gates." >&2
  exit 1
fi
echo "Implicit-SMPC experiment passed footprint safety and all three behaviour phases."
