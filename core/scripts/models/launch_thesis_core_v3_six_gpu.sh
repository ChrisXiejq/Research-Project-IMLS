#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/run_thesis_core_v3_training.sh"
V3_ROOT="${V3_ROOT:?Set V3_ROOT under persistent storage}"
SOURCE_DATASET="${SOURCE_DATASET:?Set SOURCE_DATASET}"
BASE_MODEL="${BASE_MODEL:?Set BASE_MODEL}"
ANCHORS="${ANCHORS:?Set ANCHORS}"
PYTHON_BIN="${PYTHON_BIN:-python}"
BATCH_SIZE="${BATCH_SIZE:-64}"
SHARD_COUNT=6
SHARDS="${SHARDS:-0 1 2 3 4 5}"
LOG_DIR="${V3_ROOT}/logs"

mkdir -p "${LOG_DIR}"
if [[ "$(nvidia-smi --query-gpu=index --format=csv,noheader | wc -l)" -lt 6 ]]; then
  echo "Six-GPU thesis launcher requires at least six visible GPUs" >&2
  exit 2
fi

for shard in ${SHARDS}; do
  if ! [[ "${shard}" =~ ^[0-5]$ ]]; then
    echo "Invalid shard index: ${shard}" >&2
    exit 2
  fi
  pid_file="${LOG_DIR}/shard_${shard}.pid"
  if [[ -f "${pid_file}" ]] && kill -0 "$(<"${pid_file}")" 2>/dev/null; then
    echo "Shard ${shard} is already running with PID $(<"${pid_file}")" >&2
    exit 3
  fi
done

for shard in ${SHARDS}; do
  log_file="${LOG_DIR}/shard_${shard}.log"
  nohup env \
    CUDA_VISIBLE_DEVICES="${shard}" \
    SHARD_INDEX="${shard}" \
    SHARD_COUNT="${SHARD_COUNT}" \
    V3_ROOT="${V3_ROOT}" \
    SOURCE_DATASET="${SOURCE_DATASET}" \
    BASE_MODEL="${BASE_MODEL}" \
    ANCHORS="${ANCHORS}" \
    PYTHON_BIN="${PYTHON_BIN}" \
    BATCH_SIZE="${BATCH_SIZE}" \
    bash "${RUNNER}" execute >"${log_file}" 2>&1 </dev/null &
  echo "$!" >"${LOG_DIR}/shard_${shard}.pid"
  echo "shard=${shard} pid=$! log=${log_file}"
done
