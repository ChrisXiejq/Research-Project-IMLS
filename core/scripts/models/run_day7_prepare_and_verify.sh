#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/root/miniconda3/envs/carla_modern/bin/python}"
DAY6_RESULTS="${DAY6_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day6/formal/day6_formal_v2_200}"
DAY7_RESULTS="${DAY7_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1}"
BASE_MODEL="${BASE_MODEL:-${SCRIPT_DIR}/l5kit_multipath_10_carla_finetuned_head_best}"
ANCHORS="${ANCHORS:-${SCRIPT_DIR}/l5kit_clusters_16.npy}"
LOG_DIR="$(dirname "${DAY7_RESULTS}")"
LOCK_DIR="${LOG_DIR}/.day7_prepare.lock"

mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_DIR}/day7_runner.log") 2>&1

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  old_pid=""
  [[ -f "${LOCK_DIR}/pid" ]] && old_pid="$(<"${LOCK_DIR}/pid")"
  if [[ "${old_pid}" =~ ^[0-9]+$ ]] && kill -0 "${old_pid}" 2>/dev/null; then
    echo "ERROR: Day 7 runner already active (pid=${old_pid})." >&2
    exit 3
  fi
  echo "Removing stale Day 7 lock: ${LOCK_DIR}"
  rm -f "${LOCK_DIR}/pid"
  rmdir "${LOCK_DIR}"
  mkdir "${LOCK_DIR}"
fi
printf '%s\n' "$$" > "${LOCK_DIR}/pid"
cleanup() {
  rc=$?
  rm -f "${LOCK_DIR}/pid"
  rmdir "${LOCK_DIR}" 2>/dev/null || true
  if [[ "${rc}" != "0" ]]; then
    echo "Day 7 stopped with exit code ${rc}; rerun the identical command to resume."
  fi
  exit "${rc}"
}
trap cleanup EXIT

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERROR: Python is not executable: ${PYTHON_BIN}" >&2
  exit 2
fi
if [[ ! -f "${DAY6_RESULTS}/DAY6_COMPLETE.json" ]]; then
  echo "ERROR: passing Day 6 completion marker is missing." >&2
  exit 2
fi

"${PYTHON_BIN}" "${SCRIPT_DIR}/prepare_prediction_dataset_v2_day7.py" \
  --day6-results "${DAY6_RESULTS}" \
  --output-dir "${DAY7_RESULTS}"

if [[ -f "${DAY7_RESULTS}/DAY7_MODEL_IMPLEMENTATION_COMPLETE.json" ]]; then
  echo "Day 7 model implementation gate already passed; skipping repeated smoke test."
else
  "${PYTHON_BIN}" "${SCRIPT_DIR}/verify_day7_prediction_models_v2.py" \
    --merged-dir "${DAY7_RESULTS}" \
    --base-model "${BASE_MODEL}" \
    --anchors "${ANCHORS}" \
    --output-json "${DAY7_RESULTS}/day7_model_smoke.json" \
    --completion-json "${DAY7_RESULTS}/DAY7_MODEL_IMPLEMENTATION_COMPLETE.json"
fi

echo "Day 7 merge, grouped split, normalization and model implementation gates passed."
echo "Results: ${DAY7_RESULTS}"
