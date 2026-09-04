#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"
DAY7_RESULTS="${DAY7_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day8/day8_validation_v1}"
DISTINCTION_RESULTS="${DISTINCTION_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/distinction_v1/e2_b1_inputs}"

MODEL="${MODEL:-${DAY8_RESULTS}/runs/B1/seed_37/best_model}"
CALIBRATION="${CALIBRATION:-${DAY8_RESULTS}/runs/B1/seed_37/calibration.json}"
ANCHORS="${ANCHORS:-${REPO_ROOT}/core/scripts/models/assets/l5kit_clusters_16.npy}"
LOG="${DISTINCTION_RESULTS}/e2_runner.log"

mkdir -p "${DISTINCTION_RESULTS}"
for required in "${DAY7_RESULTS}/train.jsonl" "${DAY7_RESULTS}/test.jsonl" "${MODEL}/saved_model.pb" "${CALIBRATION}" "${ANCHORS}"; do
  if [[ ! -e "${required}" ]]; then
    echo "Missing required E2 asset: ${required}" >&2
    exit 2
  fi
done

exec > >(tee -a "${LOG}") 2>&1
echo "[$(date --iso-8601=seconds)] Starting/resuming E2 B1 input diagnostics"
python "${REPO_ROOT}/core/scripts/models/experimental/run_b1_base_input_diagnostics.py" \
  --merged-dir "${DAY7_RESULTS}" \
  --model "${MODEL}" \
  --anchors "${ANCHORS}" \
  --calibration "${CALIBRATION}" \
  --output-dir "${DISTINCTION_RESULTS}" \
  --batch-size "${BATCH_SIZE:-8}" \
  --seed 20260808
echo "[$(date --iso-8601=seconds)] E2 complete"
