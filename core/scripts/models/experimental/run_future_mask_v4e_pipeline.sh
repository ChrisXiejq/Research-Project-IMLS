#!/usr/bin/env bash
set -euo pipefail

mask_root="$1"
old_root="$2"
cache_dir="$3"
extension_protocol="$4"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python}"
manifest="${THESIS_RUN_MANIFEST:-$old_root/protocol/thesis_core_run_manifest.json}"
dataset="${PREDICTION_DATASET_ROOT:-$old_root/dataset_35_5_5}"
base_model="${MULTIPATH_BASE_MODEL:?Set MULTIPATH_BASE_MODEL to the pretrained SavedModel}"
anchors="${MULTIPATH_ANCHORS:-$script_dir/assets/l5kit_clusters_16.npy}"

test -s "$extension_protocol"
test -s "$cache_dir/CACHE_COMPLETE.json"
test -s "$manifest"
test -d "$dataset"
test -e "$base_model"
test -s "$anchors"
mkdir -p "$mask_root/logs" "$mask_root/postprocess" "$mask_root/protocol"
exec >>"$mask_root/logs/offline_pipeline.log" 2>&1
export CUDA_VISIBLE_DEVICES=0
export TF_CPP_MIN_LOG_LEVEL=2

echo "PHASE=uniform_extension_training START=$(date -Iseconds)"
"$python_bin" "$script_dir/experimental/thesis_core_v4e_execute.py" \
  --run-manifest "$manifest" \
  --dataset-dir "$dataset" \
  --cache-dir "$cache_dir" \
  --base-model "$base_model" \
  --anchors "$anchors" \
  --output-root "$mask_root/training" \
  --python-bin "$python_bin" \
  --batch-size 64 \
  --shard-index 0 \
  --shard-count 1 \
  --plan-output "$mask_root/training_plan.json" \
  --execute
echo "PHASE=uniform_extension_training COMPLETE=$(date -Iseconds)"

echo "PHASE=training_audit START=$(date -Iseconds)"
"$python_bin" "$script_dir/experimental/audit_thesis_core_v4e_training.py" \
  --manifest "$manifest" \
  --training-root "$mask_root/training" \
  --output "$mask_root/postprocess/training_audit.json"

echo "PHASE=final_pre_heldout_convergence_gate START=$(date -Iseconds)"
"$python_bin" "$script_dir/experimental/write_pre_freeze_training_curve_audit_v4.py" \
  --manifest "$manifest" \
  --training-root "$mask_root/training" \
  --output "$mask_root/postprocess/training_curve_audit_final.json" \
  --require-pass

echo "PHASE=calibration START=$(date -Iseconds)"
"$python_bin" "$script_dir/experimental/thesis_core_v3_postprocess.py" stage \
  --stage calibrate \
  --manifest "$manifest" \
  --training-root "$mask_root/training" \
  --dataset-dir "$dataset" \
  --cache-dir "$cache_dir" \
  --base-model "$base_model" \
  --anchors "$anchors" \
  --output-root "$mask_root/postprocess/calibration" \
  --shard-index 0 \
  --shard-count 1 \
  --python-bin "$python_bin" \
  --plan-output "$mask_root/postprocess/calibration_plan.json" \
  --execute

echo "PHASE=latency START=$(date -Iseconds)"
"$python_bin" "$script_dir/experimental/thesis_core_v3_postprocess.py" stage \
  --stage latency \
  --manifest "$manifest" \
  --training-root "$mask_root/training" \
  --dataset-dir "$dataset" \
  --cache-dir "$cache_dir" \
  --base-model "$base_model" \
  --anchors "$anchors" \
  --output-root "$mask_root/postprocess/latency" \
  --shard-index 0 \
  --shard-count 1 \
  --python-bin "$python_bin" \
  --plan-output "$mask_root/postprocess/latency_plan.json" \
  --execute

echo "PHASE=freeze START=$(date -Iseconds)"
"$python_bin" "$script_dir/experimental/thesis_core_v3_postprocess.py" freeze \
  --manifest "$manifest" \
  --training-root "$mask_root/training" \
  --training-audit "$mask_root/postprocess/training_audit.json" \
  --calibration-root "$mask_root/postprocess/calibration" \
  --latency-root "$mask_root/postprocess/latency" \
  --output "$mask_root/postprocess/selection_freeze.json"

echo "PHASE=heldout START=$(date -Iseconds)"
"$python_bin" "$script_dir/experimental/thesis_core_v3_postprocess.py" stage \
  --stage heldout \
  --manifest "$manifest" \
  --training-root "$mask_root/training" \
  --dataset-dir "$dataset" \
  --cache-dir "$cache_dir" \
  --base-model "$base_model" \
  --anchors "$anchors" \
  --output-root "$mask_root/postprocess/heldout" \
  --calibration-root "$mask_root/postprocess/calibration" \
  --selection-freeze "$mask_root/postprocess/selection_freeze.json" \
  --shard-index 0 \
  --shard-count 1 \
  --python-bin "$python_bin" \
  --plan-output "$mask_root/postprocess/heldout_plan.json" \
  --execute

echo "PHASE=synthesis START=$(date -Iseconds)"
"$python_bin" "$script_dir/experimental/thesis_core_v3_postprocess.py" synthesize \
  --manifest "$manifest" \
  --selection-freeze "$mask_root/postprocess/selection_freeze.json" \
  --heldout-root "$mask_root/postprocess/heldout" \
  --output "$mask_root/postprocess/offline_synthesis.json" \
  --csv-output "$mask_root/postprocess/offline_cells.csv"

echo "PHASE=offline_complete COMPLETE=$(date -Iseconds)"
touch "$mask_root/OFFLINE_PIPELINE_COMPLETE"
