#!/usr/bin/env bash
set -euo pipefail

# One-command entry point for CARLA-domain MultiPath fine-tuning.
# Run this on a GPU server after syncing Research-Project-IMLS and the
# prediction dataset result directory.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

RESULT_DIR="${RESULT_DIR:-${REPO_ROOT}/results/20260717_232553_prediction_dataset_collection}"
MERGED_DIR="${MERGED_DIR:-${RESULT_DIR}/prediction_dataset_merged}"
BASE_MODEL="${BASE_MODEL:-${SCRIPT_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${SCRIPT_DIR}/l5kit_clusters_16.npy}"
OUTPUT_MODEL="${OUTPUT_MODEL:-${SCRIPT_DIR}/l5kit_multipath_10_carla_finetuned_head}"
EPOCHS="${EPOCHS:-10}"
BATCH_SIZE="${BATCH_SIZE:-16}"
LEARNING_RATE="${LEARNING_RATE:-1e-4}"
FREEZE="${FREEZE:-head}"

cd "${SCRIPT_DIR}"

python prepare_prediction_dataset_split.py \
  --result_dir "${RESULT_DIR}" \
  --output_dir "${MERGED_DIR}"

python evaluate_prediction_dataset.py \
  --merged_dir "${MERGED_DIR}" \
  --split test \
  --output_json "${MERGED_DIR}/logged_baseline_metrics_test.json"

python finetune_multipath_carla.py \
  --merged_dir "${MERGED_DIR}" \
  --base_model "${BASE_MODEL}" \
  --anchors "${ANCHORS}" \
  --output_model "${OUTPUT_MODEL}" \
  --epochs "${EPOCHS}" \
  --batch_size "${BATCH_SIZE}" \
  --learning_rate "${LEARNING_RATE}" \
  --freeze "${FREEZE}"

python evaluate_multipath_model_on_dataset.py \
  --merged_dir "${MERGED_DIR}" \
  --split test \
  --model "${OUTPUT_MODEL}_best" \
  --anchors "${ANCHORS}" \
  --batch_size "${BATCH_SIZE}" \
  --output_json "${MERGED_DIR}/finetuned_best_metrics_test.json"

echo "Fine-tuning complete."
echo "Best model: ${OUTPUT_MODEL}_best"
echo "Final model: ${OUTPUT_MODEL}"
echo "Baseline metrics: ${MERGED_DIR}/logged_baseline_metrics_test.json"
echo "Fine-tuned metrics: ${MERGED_DIR}/finetuned_best_metrics_test.json"
