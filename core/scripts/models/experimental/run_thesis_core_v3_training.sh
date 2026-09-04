#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
V3_ROOT="${V3_ROOT:?Set V3_ROOT under persistent storage}"
SOURCE_DATASET="${SOURCE_DATASET:?Set SOURCE_DATASET to sealed Day7 groups 1--45}"
BASE_MODEL="${BASE_MODEL:?Set BASE_MODEL to pretrained B0 SavedModel}"
ANCHORS="${ANCHORS:?Set ANCHORS to the frozen anchor array}"
DATASET_DIR="${V3_ROOT}/dataset_35_5_5"
CACHE_DIR="${V3_ROOT}/feature_cache"
MANIFEST="${V3_ROOT}/protocol/thesis_core_run_manifest.json"
TRAINING_ROOT="${V3_ROOT}/training"
MODE="${1:-plan}"
SHARD_INDEX="${SHARD_INDEX:-0}"
SHARD_COUNT="${SHARD_COUNT:-6}"
BATCH_SIZE="${BATCH_SIZE:-64}"

mkdir -p "${V3_ROOT}/protocol" "${TRAINING_ROOT}" "${V3_ROOT}/plans"
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"

case "${MODE}" in
  prepare)
    "${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/prepare_thesis_core_v3_dataset.py" \
      --source-dir "${SOURCE_DATASET}" --output-dir "${DATASET_DIR}"
    "${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/build_thesis_core_feature_cache_v3.py" \
      --dataset-dir "${DATASET_DIR}" --base-model "${BASE_MODEL}" \
      --output-dir "${CACHE_DIR}" --batch-size 32
    ;;
  plan|execute|audit)
    if [[ ! -s "${MANIFEST}" ]]; then
      candidate="${MANIFEST}.$$.candidate"
      "${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/thesis_core_v3_runs.py" --output "${candidate}"
      mv "${candidate}" "${MANIFEST}"
    fi
    args=(
      --run-manifest "${MANIFEST}"
      --dataset-dir "${DATASET_DIR}"
      --cache-dir "${CACHE_DIR}"
      --base-model "${BASE_MODEL}"
      --anchors "${ANCHORS}"
      --output-root "${TRAINING_ROOT}"
      --python-bin "${PYTHON_BIN}"
      --batch-size "${BATCH_SIZE}"
      --shard-index "${SHARD_INDEX}"
      --shard-count "${SHARD_COUNT}"
      --plan-output "${V3_ROOT}/plans/shard_${SHARD_INDEX}.json"
    )
    if [[ "${MODE}" == "execute" ]]; then
      args+=(--execute)
    fi
    "${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/thesis_core_v3_execute.py" "${args[@]}"
    ;;
  *)
    echo "Usage: $0 [prepare|plan|execute|audit]" >&2
    exit 2
    ;;
esac
