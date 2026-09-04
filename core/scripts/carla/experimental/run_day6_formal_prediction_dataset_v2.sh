#!/usr/bin/env bash
set -Eeuo pipefail

# Day 6 formal collection wrapper. This script does not change the frozen V2
# collection runner; it adds resume guards, provenance, progress and final audit.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
RESULTS_DIR="${RESULTS_DIR:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day6/formal/day6_formal_v2_200}"
FROZEN_CONFIG="${FROZEN_CONFIG:-${REPO_DIR}/docs/paper/generated/day5/day5_final_6b71ccc_frozen_config.json}"
PROTOCOL_MANIFEST="${MODELS_DIR}/protocols/give_way_interaction_v2_collection_manifest.json"
FEATURE_SCHEMA="${MODELS_DIR}/protocols/give_way_interaction_sequence_v2.schema.json"
MODEL_WEIGHTS="l5kit_multipath_10_carla_finetuned_head_best"
MODEL_ANCHORS="assets/l5kit_clusters_16.npy"
PREDICTION_GIT_COMMIT="6b71ccc"
MIN_FREE_KB="${MIN_FREE_KB:-5242880}"

case "${RESULTS_DIR}" in
  ""|/|/root|${EXPERIMENT_STORAGE_ROOT:-/path/to/persistent-storage}|${EXPERIMENT_RESULTS_ROOT:-/path/to/results})
    echo "ERROR: RESULTS_DIR is too broad: ${RESULTS_DIR}" >&2
    exit 2
    ;;
esac
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERROR: PYTHON_BIN is not executable: ${PYTHON_BIN}" >&2
  exit 2
fi
for required in "${FROZEN_CONFIG}" "${PROTOCOL_MANIFEST}" "${FEATURE_SCHEMA}"; do
  if [[ ! -f "${required}" ]]; then
    echo "ERROR: required frozen artifact missing: ${required}" >&2
    exit 2
  fi
done
if [[ -z "${CARLA_ROOT:-}" ]]; then
  echo "ERROR: CARLA_ROOT is not set." >&2
  exit 2
fi
if [[ ! -f "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py" ]]; then
  echo "ERROR: invalid CARLA_ROOT=${CARLA_ROOT}" >&2
  exit 2
fi

mkdir -p "${RESULTS_DIR}"
exec > >(tee -a "${RESULTS_DIR}/day6_runner.log") 2>&1

LOCK_DIR="${RESULTS_DIR}/.day6_runner.lock"
LOCK_HELD=0
COMPLETED=0
acquire_lock() {
  if mkdir "${LOCK_DIR}" 2>/dev/null; then
    LOCK_HELD=1
  else
    local old_pid=""
    [[ -f "${LOCK_DIR}/pid" ]] && old_pid="$(<"${LOCK_DIR}/pid")"
    if [[ "${old_pid}" =~ ^[0-9]+$ ]] && kill -0 "${old_pid}" 2>/dev/null; then
      local old_command
      old_command="$(ps -p "${old_pid}" -o args= 2>/dev/null || true)"
      if [[ "${old_command}" == *"experimental/run_day6_formal_prediction_dataset_v2.sh"* ]]; then
        echo "ERROR: another Day 6 wrapper is active (pid=${old_pid})." >&2
        exit 3
      fi
    fi
    echo "Removing stale Day 6 lock: ${LOCK_DIR}"
    rm -f "${LOCK_DIR}/pid" "${LOCK_DIR}/host" "${LOCK_DIR}/started_at_utc"
    rmdir "${LOCK_DIR}"
    mkdir "${LOCK_DIR}"
    LOCK_HELD=1
  fi
  printf '%s\n' "$$" > "${LOCK_DIR}/pid"
  hostname > "${LOCK_DIR}/host"
  date -u +%Y-%m-%dT%H:%M:%SZ > "${LOCK_DIR}/started_at_utc"
}

write_progress() {
  local phase="$1"
  local exit_code="${2:-}"
  local args=(
    --results-dir "${RESULTS_DIR}"
    --phase "${phase}"
  )
  if [[ -n "${exit_code}" ]]; then
    args+=(--exit-code "${exit_code}")
  fi
  "${PYTHON_BIN}" "${MODELS_DIR}/experimental/summarize_prediction_dataset_v2_day6_progress.py" "${args[@]}"
}

cleanup() {
  local rc=$?
  trap - EXIT
  set +e
  if [[ "${COMPLETED}" != "1" && "${LOCK_HELD}" == "1" ]]; then
    write_progress "wrapper_exit" "${rc}"
  fi
  if [[ "${LOCK_HELD}" == "1" ]]; then
    rm -f "${LOCK_DIR}/pid" "${LOCK_DIR}/host" "${LOCK_DIR}/started_at_utc"
    rmdir "${LOCK_DIR}" 2>/dev/null || true
  fi
  if [[ "${rc}" != "0" ]]; then
    echo "Day 6 wrapper stopped with exit code ${rc}; rerun the identical command to resume."
  fi
  exit "${rc}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

acquire_lock
active_collection_processes="$(
  pgrep -af 'run_give_way_prediction_dataset_v2[.]sh|run_all_scenarios[.]py' || true
)"
if [[ -n "${active_collection_processes}" ]]; then
  echo "ERROR: an underlying collection process is already active:" >&2
  echo "${active_collection_processes}" >&2
  echo "Do not resume until that process has exited." >&2
  exit 3
fi
echo "Day 6 result directory: ${RESULTS_DIR}"
echo "Repository: ${REPO_DIR}"
echo "Python: ${PYTHON_BIN}"
write_progress "wrapper_start"

available_kb="$(df -Pk "${RESULTS_DIR}" | awk 'NR==2 {print $4}')"
if [[ ! "${available_kb}" =~ ^[0-9]+$ ]] || (( available_kb < MIN_FREE_KB )); then
  echo "ERROR: insufficient free space: ${available_kb:-unknown} KB; require ${MIN_FREE_KB} KB" >&2
  exit 4
fi

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${MODELS_DIR}:${PYTHONPATH:-}"
"${PYTHON_BIN}" -c 'import gurobipy as gp; print("Gurobi:", gp.gurobi.version())'
"${PYTHON_BIN}" -c 'import carla; c=carla.Client("127.0.0.1", 2000); c.set_timeout(10.0); w=c.get_world(); print("CARLA map:", w.get_map().name)'

CONTRACT_JSON="${RESULTS_DIR}/day6_run_contract.json"
PREFLIGHT_JSON="${RESULTS_DIR}/day6_preflight_latest.json"
"${PYTHON_BIN}" "${MODELS_DIR}/experimental/verify_prediction_dataset_v2_day6_preflight.py" \
  --repo-dir "${REPO_DIR}" \
  --frozen-config "${FROZEN_CONFIG}" \
  --contract-json "${CONTRACT_JSON}" \
  --report-json "${PREFLIGHT_JSON}" \
  --model-weights "${MODEL_WEIGHTS}" \
  --model-anchors "${MODEL_ANCHORS}"

SNAPSHOT_DIR="${RESULTS_DIR}/protocol_snapshot"
mkdir -p "${SNAPSHOT_DIR}"
copy_or_verify() {
  local source="$1"
  local destination="${SNAPSHOT_DIR}/$(basename "${source}")"
  if [[ -f "${destination}" ]]; then
    cmp --silent "${source}" "${destination}" || {
      echo "ERROR: protocol snapshot drift: ${destination}" >&2
      exit 5
    }
  else
    cp "${source}" "${destination}"
  fi
}
copy_or_verify "${FROZEN_CONFIG}"
copy_or_verify "${PROTOCOL_MANIFEST}"
copy_or_verify "${FEATURE_SCHEMA}"
copy_or_verify "${BASH_SOURCE[0]}"

if [[ -f "${RESULTS_DIR}/DAY6_COMPLETE.json" ]]; then
  echo "DAY6_COMPLETE.json already exists and the resume contract still matches."
  COMPLETED=1
  exit 0
fi

REACTIVE_CONFIG_JSON="$("${PYTHON_BIN}" -c '
import json, sys
frozen=json.load(open(sys.argv[1]))["reactive_parameters"]
keys=("caution_speed_mps","minimum_speed_mps","activation_distance_m","release_clearance_m","arrival_time_gap_s","closest_approach_time_s","closest_approach_distance_m","release_hold_s")
print(json.dumps({key:frozen[key] for key in keys}, separators=(",",":")))
' "${FROZEN_CONFIG}")"

echo "Starting/resuming frozen 200-rollout collection."
RESULTS_DIR="${RESULTS_DIR}" \
PYTHON_BIN="${PYTHON_BIN}" \
INIT_START=1 \
INIT_END=50 \
LOG_STRIDE=4 \
LOG_HORIZON=10 \
ENABLE_CAMERA_VIZ=0 \
SKIP_COMPLETED_SUBRUNS=1 \
PREDICTION_MODEL_WEIGHTS="${MODEL_WEIGHTS}" \
PREDICTION_MODEL_ANCHORS="${MODEL_ANCHORS}" \
PREDICTION_GIT_COMMIT="${PREDICTION_GIT_COMMIT}" \
REACTIVE_CONFIG_JSON="${REACTIVE_CONFIG_JSON}" \
bash "${SCRIPT_DIR}/experimental/run_give_way_prediction_dataset_v2.sh"

write_progress "collection_runner_returned" 0
AUDIT_JSON="${RESULTS_DIR}/day6_collection_audit.json"
"${PYTHON_BIN}" "${MODELS_DIR}/experimental/audit_prediction_dataset_v2_day6.py" \
  --results-dir "${RESULTS_DIR}" \
  --frozen-config-json "${FROZEN_CONFIG}" \
  --preflight-report-json "${PREFLIGHT_JSON}" \
  --output-json "${AUDIT_JSON}" \
  --expected-git-commit "${PREDICTION_GIT_COMMIT}"

write_progress "audit_passed" 0
"${PYTHON_BIN}" "${MODELS_DIR}/experimental/finalize_prediction_dataset_v2_day6.py" \
  --results-dir "${RESULTS_DIR}" \
  --audit-json "${AUDIT_JSON}" \
  --contract-json "${CONTRACT_JSON}" \
  --preflight-json "${PREFLIGHT_JSON}"

COMPLETED=1
echo "Day 6 formal collection and audit complete: ${RESULTS_DIR}"
