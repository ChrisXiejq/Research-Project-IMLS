#!/usr/bin/env bash
set -euo pipefail

# Train/evaluate the interaction-aware Transformer-MultiPath residual adapter.
# This is the model-layer follow-up experiment after variable-risk SMPC did not
# produce stable final-metric dominance under the shared safety supervisor.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

RESULT_DIR="${RESULT_DIR:-${REPO_ROOT}/results/20260717_232553_prediction_dataset_collection}"
MERGED_DIR="${MERGED_DIR:-${RESULT_DIR}/prediction_dataset_merged}"
BASE_MODEL="${BASE_MODEL:-${SCRIPT_DIR}/l5kit_multipath_10_carla_finetuned_head_best}"
ANCHORS="${ANCHORS:-${SCRIPT_DIR}/l5kit_clusters_16.npy}"
OUTPUT_MODEL="${OUTPUT_MODEL:-${SCRIPT_DIR}/l5kit_multipath_10_carla_interaction_transformer}"
EPOCHS="${EPOCHS:-12}"
BATCH_SIZE="${BATCH_SIZE:-16}"
LEARNING_RATE="${LEARNING_RATE:-5e-5}"
FREEZE_BASE="${FREEZE_BASE:-true}"
NO_IMAGE="${NO_IMAGE:-0}"

cd "${SCRIPT_DIR}"

python prepare_prediction_dataset_split.py \
  --result_dir "${RESULT_DIR}" \
  --output_dir "${MERGED_DIR}"

python evaluate_multipath_model_on_dataset.py \
  --merged_dir "${MERGED_DIR}" \
  --split test \
  --model "${BASE_MODEL}" \
  --anchors "${ANCHORS}" \
  --batch_size "${BATCH_SIZE}" \
  --output_json "${MERGED_DIR}/current_multipath_best_metrics_test.json"

no_image_args=()
if [[ "${NO_IMAGE}" == "1" ]]; then
  no_image_args+=(--no_image)
fi

python finetune_interaction_transformer_multipath_carla.py \
  --merged_dir "${MERGED_DIR}" \
  --base_model "${BASE_MODEL}" \
  --anchors "${ANCHORS}" \
  --output_model "${OUTPUT_MODEL}" \
  --epochs "${EPOCHS}" \
  --batch_size "${BATCH_SIZE}" \
  --learning_rate "${LEARNING_RATE}" \
  --freeze_base "${FREEZE_BASE}" \
  "${no_image_args[@]}"

python evaluate_multipath_model_on_dataset.py \
  --merged_dir "${MERGED_DIR}" \
  --split test \
  --model "${OUTPUT_MODEL}_best" \
  --anchors "${ANCHORS}" \
  --batch_size "${BATCH_SIZE}" \
  --output_json "${MERGED_DIR}/interaction_transformer_best_metrics_test.json"

echo "Interaction-aware Transformer-MultiPath experiment complete."
echo "Base metrics: ${MERGED_DIR}/current_multipath_best_metrics_test.json"
echo "Interaction metrics: ${MERGED_DIR}/interaction_transformer_best_metrics_test.json"
echo "Best interaction model: ${OUTPUT_MODEL}_best"
