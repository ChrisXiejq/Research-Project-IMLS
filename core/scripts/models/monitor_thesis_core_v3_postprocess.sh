#!/usr/bin/env bash
set -u

V3_ROOT="${1:-/root/autodl-tmp/results/capacity_history_thesis_core_v3}"
POST_ROOT="${V3_ROOT}/postprocess"

date '+%F %T %Z'
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu \
  --format=csv,noheader

for stage in calibration latency heldout; do
  case "${stage}" in
    calibration) marker="selection_metrics.json"; log_stage="calibrate" ;;
    latency) marker="latency.json"; log_stage="latency" ;;
    heldout) marker="heldout_metrics.json"; log_stage="heldout" ;;
  esac
  complete=$(find "${POST_ROOT}/${stage}" -mindepth 2 -maxdepth 2 -name "${marker}" 2>/dev/null | wc -l | tr -d ' ')
  active=0
  for pid_file in "${POST_ROOT}/logs/${log_stage}"/shard_*.pid; do
    [[ -e "${pid_file}" ]] || continue
    if kill -0 "$(<"${pid_file}")" 2>/dev/null; then
      active=$((active + 1))
    fi
  done
  screen_active=$(screen -ls 2>/dev/null | grep -c "[.]thesis_v3_${log_stage}_" || true)
  if [[ "${screen_active}" -gt "${active}" ]]; then
    active="${screen_active}"
  fi
  errors=$(grep -lE 'Traceback|ValueError|ResourceExhaustedError|FAILED' \
    "${POST_ROOT}/logs/${log_stage}"/shard_*.log 2>/dev/null | wc -l | tr -d ' ')
  echo "stage=${stage} complete=${complete}/27 active_shards=${active} error_logs=${errors}"
done

if [[ -f "${POST_ROOT}/selection_freeze.json" ]]; then
  echo "selection_freeze=present"
else
  echo "selection_freeze=absent"
fi
if [[ -f "${POST_ROOT}/offline_synthesis.json" ]]; then
  echo "offline_synthesis=present"
else
  echo "offline_synthesis=absent"
fi
