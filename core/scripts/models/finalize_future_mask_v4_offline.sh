#!/usr/bin/env bash
set -euo pipefail

mask_root="${1:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/capacity_history_future_mask_v4}"
old_root="${2:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/capacity_history_thesis_core_v3}"
extension_protocol="${3:-$mask_root/protocol/EXTENSION_PROTOCOL.json}"
pipeline_screen="${4:-mask_v4_offline}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
python_bin="${PYTHON_BIN:-python}"
finalizer_log="$mask_root/logs/offline_finalizer.log"

mkdir -p "$mask_root/logs" "$mask_root/audits" "$mask_root/figures"
exec >>"$finalizer_log" 2>&1
echo "FINALIZER_START=$(date -Iseconds)"

while [[ ! -f "$mask_root/OFFLINE_PIPELINE_COMPLETE" ]]; do
  if ! screen -ls 2>/dev/null | grep -Fq ".$pipeline_screen"; then
    echo "FINALIZER_BLOCKED=pipeline_screen_missing TIME=$(date -Iseconds)"
    exit 3
  fi
  training_count="$({ find "$mask_root/training" -name TRAINING_COMPLETE.json -type f 2>/dev/null || true; } | wc -l | tr -d ' ')"
  echo "FINALIZER_WAIT=$(date -Iseconds) training=$training_count/27"
  sleep 60
done

echo "FINALIZER_PHASE=pipeline_stage_seal START=$(date -Iseconds)"
"$python_bin" "$script_dir/seal_future_mask_v4_pipeline_stage.py" \
  --manifest "$old_root/protocol/thesis_core_run_manifest.json" \
  --training-root "$mask_root/training" \
  --calibration-root "$mask_root/postprocess/calibration" \
  --latency-root "$mask_root/postprocess/latency" \
  --heldout-root "$mask_root/postprocess/heldout" \
  --selection-freeze "$mask_root/postprocess/selection_freeze.json" \
  --synthesis "$mask_root/postprocess/offline_synthesis.json" \
  --pipeline-receipt "$mask_root/protocol/RUNNING_PIPELINE_RECEIPT.json" \
  --output "$mask_root/protocol/PIPELINE_STAGE_COMPLETE.json"

echo "FINALIZER_PHASE=foundation_mask_scope START=$(date -Iseconds)"
"$python_bin" "$script_dir/audit_foundation_future_mask_scope_v4.py" \
  --validation-jsonl ${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1/val.jsonl \
  --test-jsonl ${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1/test.jsonl \
  --b0-validation-evaluation "$repo_root/docs/paper/generated/day10/gaps/b0_offline/b0_validation_evaluation.json" \
  --b0-test-evaluation "$repo_root/docs/paper/generated/day10/gaps/b0_offline/b0_test_all.json" \
  --b1-test-evaluation "$repo_root/docs/paper/generated/day8/final_test/B1/seed_37/test_all.json" \
  --b0-summary "$repo_root/docs/paper/generated/day10/gaps/b0_offline/b0_frozen_offline_summary.json" \
  --legacy-evaluator-source ${LEGACY_DAY8_REPO:-/path/to/Research-Project-IMLS-day8}/core/scripts/models/evaluate_multipath_model_on_dataset.py \
  --output "$mask_root/audits/FOUNDATION_MASK_SCOPE_AUDIT.json"

echo "FINALIZER_PHASE=full_horizon_recalibration START=$(date -Iseconds)"
"$python_bin" "$script_dir/thesis_core_v3_postprocess.py" stage \
  --stage full_horizon \
  --manifest "$old_root/protocol/thesis_core_run_manifest.json" \
  --training-root "$mask_root/training" \
  --dataset-dir "$old_root/dataset_35_5_5" \
  --cache-dir "$mask_root/feature_cache_v4" \
  --base-model ${LEGACY_DAY8_REPO:-/path/to/Research-Project-IMLS-day8}/core/scripts/models/l5kit_multipath_10 \
  --anchors ${LEGACY_DAY8_REPO:-/path/to/Research-Project-IMLS-day8}/core/scripts/models/l5kit_clusters_16.npy \
  --output-root "$mask_root/postprocess/full_horizon_sensitivity" \
  --selection-freeze "$mask_root/postprocess/selection_freeze.json" \
  --shard-index 0 \
  --shard-count 1 \
  --python-bin "$python_bin" \
  --plan-output "$mask_root/postprocess/full_horizon_plan.json" \
  --execute

echo "FINALIZER_PHASE=audit START=$(date -Iseconds)"
"$python_bin" "$script_dir/audit_future_mask_v4_offline.py" \
  --old-cache "$old_root/feature_cache" \
  --corrected-cache "$mask_root/feature_cache_v4" \
  --dataset-dir "$old_root/dataset_35_5_5" \
  --old-selection-root "$old_root/postprocess/calibration" \
  --corrected-old-selection-root "$mask_root/impact_audit_old_checkpoints/calibration" \
  --corrected-selection-root "$mask_root/postprocess/calibration" \
  --training-root "$mask_root/training" \
  --manifest "$old_root/protocol/thesis_core_run_manifest.json" \
  --corrected-heldout-root "$mask_root/postprocess/heldout" \
  --full-horizon-root "$mask_root/postprocess/full_horizon_sensitivity" \
  --offline-synthesis "$mask_root/postprocess/offline_synthesis.json" \
  --old-offline-synthesis "$old_root/postprocess/offline_synthesis.json" \
  --selection-freeze "$mask_root/postprocess/selection_freeze.json" \
  --old-selection-freeze "$old_root/postprocess/selection_freeze.json" \
  --pipeline-receipt "$mask_root/protocol/RUNNING_PIPELINE_RECEIPT.json" \
  --pipeline-stage-receipt "$mask_root/protocol/PIPELINE_STAGE_COMPLETE.json" \
  --extension-protocol "$extension_protocol" \
  --output-dir "$mask_root/audits"

echo "FINALIZER_PHASE=figures START=$(date -Iseconds)"
"$python_bin" "$script_dir/plot_future_mask_v4_offline.py" \
  --impact-audit "$mask_root/audits/HISTORICAL_CHECKPOINT_IMPACT_AUDIT.json" \
  --offline-synthesis "$mask_root/postprocess/offline_synthesis.json" \
  --full-horizon-sensitivity "$mask_root/audits/FULL_HORIZON_SENSITIVITY.json" \
  --selection-freeze "$mask_root/postprocess/selection_freeze.json" \
  --output-dir "$mask_root/figures"

echo "FINALIZER_PHASE=paper_outputs START=$(date -Iseconds)"
"$python_bin" "$script_dir/materialize_future_mask_v4_paper_outputs.py" \
  --root "$mask_root" \
  --old-synthesis "$old_root/postprocess/offline_synthesis.json" \
  --foundation-scope "$mask_root/audits/FOUNDATION_MASK_SCOPE_AUDIT.json" \
  --extension-protocol "$extension_protocol" \
  --output-dir "$mask_root/paper_outputs"

test -s "$mask_root/audits/OFFLINE_EVIDENCE_RELEASE.json"
test -s "$mask_root/audits/CARLA_DEPLOYMENT_DECISION.json"
echo "FINALIZER_PHASE=seal START=$(date -Iseconds)"
"$python_bin" "$script_dir/seal_future_mask_v4_release.py" \
  --evidence "$mask_root/audits/OFFLINE_EVIDENCE_RELEASE.json" \
  --figures "$mask_root/figures/FIGURE_MANIFEST.json" \
  --paper-outputs "$mask_root/paper_outputs/PAPER_OUTPUTS_MANIFEST.json" \
  --foundation-scope "$mask_root/audits/FOUNDATION_MASK_SCOPE_AUDIT.json" \
  --output "$mask_root/OFFLINE_AUDIT_COMPLETE.json"
echo "FINALIZER_COMPLETE=$(date -Iseconds)"
