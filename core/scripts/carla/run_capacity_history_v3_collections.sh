#!/usr/bin/env bash
set -Eeuo pipefail

# Server entry point for the two fresh V3 collections. Safe to rerun: frozen
# manifests reject drift and completed CARLA subruns are skipped.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
V3_ROOT="${V3_ROOT:-${CORE_DIR}/results/capacity_history_v3}"
PROTOCOL_ROOT="${PROTOCOL_ROOT:-${V3_ROOT}/protocol}"
MODE="${1:-all}"

export PYTHONPATH="${MODELS_DIR}:${PYTHONPATH:-}"
"${PYTHON_BIN}" "${MODELS_DIR}/capacity_study_v3_collection.py" freeze \
  --output-root "${PROTOCOL_ROOT}"

run_set() {
  local collection_set="$1"
  COLLECTION_SET="${collection_set}" \
  PROTOCOL_ROOT="${PROTOCOL_ROOT}" \
  RESULTS_DIR="${V3_ROOT}/${collection_set}" \
  bash "${SCRIPT_DIR}/run_give_way_prediction_dataset_v3.sh"
}

case "${MODE}" in
  general_test) run_set general_test ;;
  interaction_challenge) run_set interaction_challenge ;;
  all)
    run_set general_test
    run_set interaction_challenge
    ;;
  *) echo "Usage: $0 [general_test|interaction_challenge|all]" >&2; exit 2 ;;
esac
