#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]] || [[ ! "$1" =~ ^(calibrate|latency|heldout)$ ]]; then
  echo "Usage: $0 {calibrate|latency|heldout}" >&2
  exit 2
fi

STAGE="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER="${SCRIPT_DIR}/thesis_core_v3_postprocess.py"
V3_ROOT="${V3_ROOT:?Set V3_ROOT under persistent storage}"
BASE_MODEL="${BASE_MODEL:?Set BASE_MODEL}"
ANCHORS="${ANCHORS:?Set ANCHORS}"
PYTHON_BIN="${PYTHON_BIN:-python}"
SHARD_COUNT=6
SHARDS="${SHARDS:-0 1 2 3 4 5}"
POST_ROOT="${V3_ROOT}/postprocess"
LOG_DIR="${POST_ROOT}/logs/${STAGE}"
PLAN_DIR="${POST_ROOT}/plans/${STAGE}"
OUTPUT_ROOT="${POST_ROOT}/${STAGE/calibrate/calibration}"
SELECTION_FREEZE="${POST_ROOT}/selection_freeze.json"

mkdir -p "${LOG_DIR}" "${PLAN_DIR}" "${OUTPUT_ROOT}"
if [[ "$(nvidia-smi --query-gpu=index --format=csv,noheader | wc -l)" -lt 6 ]]; then
  echo "Six-GPU post-processing requires at least six visible GPUs" >&2
  exit 2
fi
if [[ "${STAGE}" == "heldout" && ! -f "${SELECTION_FREEZE}" ]]; then
  echo "Held-out access blocked: missing ${SELECTION_FREEZE}" >&2
  exit 3
fi

for shard in ${SHARDS}; do
  if ! [[ "${shard}" =~ ^[0-5]$ ]]; then
    echo "Invalid shard index: ${shard}" >&2
    exit 2
  fi
  pid_file="${LOG_DIR}/shard_${shard}.pid"
  screen_name="thesis_v3_${STAGE}_${shard}"
  if screen -ls 2>/dev/null | grep -q "[.]${screen_name}[[:space:]]"; then
    echo "${STAGE} shard ${shard} is already running in screen ${screen_name}" >&2
    exit 3
  fi
  if [[ -f "${pid_file}" ]] && kill -0 "$(<"${pid_file}")" 2>/dev/null; then
    echo "${STAGE} shard ${shard} is already running with PID $(<"${pid_file}")" >&2
    exit 3
  fi
done

for shard in ${SHARDS}; do
  log_file="${LOG_DIR}/shard_${shard}.log"
  plan_file="${PLAN_DIR}/shard_${shard}.json"
  args=(
    "${DRIVER}" stage
    --stage "${STAGE}"
    --manifest "${V3_ROOT}/protocol/thesis_core_run_manifest.json"
    --training-root "${V3_ROOT}/training"
    --dataset-dir "${V3_ROOT}/dataset_35_5_5"
    --cache-dir "${V3_ROOT}/feature_cache"
    --base-model "${BASE_MODEL}"
    --anchors "${ANCHORS}"
    --output-root "${OUTPUT_ROOT}"
    --calibration-root "${POST_ROOT}/calibration"
    --selection-freeze "${SELECTION_FREEZE}"
    --shard-index "${shard}"
    --shard-count "${SHARD_COUNT}"
    --python-bin "${PYTHON_BIN}"
    --plan-output "${plan_file}"
    --execute
  )
  screen_name="thesis_v3_${STAGE}_${shard}"
  : >"${log_file}"
  screen -L -Logfile "${log_file}" -dmS "${screen_name}" \
    env CUDA_VISIBLE_DEVICES="${shard}" PYTHONPATH="${SCRIPT_DIR}" \
    "${PYTHON_BIN}" "${args[@]}"
  screen_pid="$(screen -ls | awk -v name=".${screen_name}" '$1 ~ name {split($1,a,"."); print a[1]; exit}')"
  if [[ -z "${screen_pid}" ]]; then
    echo "Failed to start screen ${screen_name}" >&2
    exit 4
  fi
  echo "${screen_pid}" >"${LOG_DIR}/shard_${shard}.pid"
  echo "stage=${STAGE} shard=${shard} pid=${screen_pid} screen=${screen_name} log=${log_file}"
done
