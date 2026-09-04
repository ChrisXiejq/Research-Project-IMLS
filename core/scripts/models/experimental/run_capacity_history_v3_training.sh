#!/usr/bin/env bash
set -Eeuo pipefail

# GPU-server entry point. Defaults to a dry-run plan; pass execute explicitly
# to train all missing core and data-fraction runs sequentially.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
V3_ROOT="${V3_ROOT:-${CORE_DIR}/results/capacity_history_v3}"
MERGED_DIR="${MERGED_DIR:?Set MERGED_DIR to the sealed groups-1--45 training/validation dataset}"
BASE_MODEL="${BASE_MODEL:-${SCRIPT_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${SCRIPT_DIR}/assets/l5kit_clusters_16.npy}"
MODE="${1:-plan}"
MANIFEST="${V3_ROOT}/protocol/run_manifest.json"
RUN_ROOT="${V3_ROOT}/training"
PLAN="${V3_ROOT}/training_execution_plan.json"
AUDIT="${V3_ROOT}/training_audit.json"

mkdir -p "${V3_ROOT}/protocol" "${RUN_ROOT}"
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"
"${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/capacity_study_v3_runs.py" --output "${MANIFEST}"

args=(
  --manifest "${MANIFEST}"
  --merged-dir "${MERGED_DIR}"
  --base-model "${BASE_MODEL}"
  --anchors "${ANCHORS}"
  --output-root "${RUN_ROOT}"
  --python-bin "${PYTHON_BIN}"
  --plan-output "${PLAN}"
  --audit-output "${AUDIT}"
)
case "${MODE}" in
  plan|audit) ;;
  execute) args+=(--execute) ;;
  *) echo "Usage: $0 [plan|execute|audit]" >&2; exit 2 ;;
esac
"${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/capacity_study_v3_execute.py" "${args[@]}"
