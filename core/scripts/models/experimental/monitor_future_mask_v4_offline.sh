#!/usr/bin/env bash
set -u

mask_root="${1:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/capacity_history_future_mask_v4}"
pipeline_log="$mask_root/logs/offline_pipeline.log"

echo "time=$(date -Iseconds)"
echo "root=$mask_root"
echo "screen:"
screen -ls 2>/dev/null | grep mask_v4_offline || echo "  mask_v4_offline not running"
echo "gpu:"
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu \
  --format=csv,noheader 2>/dev/null || echo "  nvidia-smi unavailable"
echo "phase:"
grep -E '^PHASE=' "$pipeline_log" 2>/dev/null | tail -n 12 || true

count_receipts() {
  local directory="$1"
  local filename="$2"
  find "$directory" -name "$filename" -type f 2>/dev/null | wc -l | tr -d ' '
}

echo "counts:"
echo "  historical_rescore=$(count_receipts "$mask_root/impact_audit_old_checkpoints/calibration" selection_metrics.json)/27"
echo "  training=$(count_receipts "$mask_root/training" TRAINING_COMPLETE.json)/27"
echo "  calibration=$(count_receipts "$mask_root/postprocess/calibration" calibration.json)/27"
echo "  latency=$(count_receipts "$mask_root/postprocess/latency" latency.json)/27"
echo "  heldout=$(count_receipts "$mask_root/postprocess/heldout" heldout_metrics.json)/27"
echo "  offline_complete=$([ -f "$mask_root/OFFLINE_PIPELINE_COMPLETE" ] && echo yes || echo no)"

echo "recent_training:"
tail -n 18 "$pipeline_log" 2>/dev/null || true
echo "error_scan:"
grep -E 'Traceback|ValueError|RuntimeError|ResourceExhausted|CUDA_ERROR|out of memory|non-finite|drift|mismatch|FAILED|ERROR' \
  "$pipeline_log" 2>/dev/null | tail -n 20 || true
