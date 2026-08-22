#!/usr/bin/env bash
set -u

V3_ROOT="${1:-/root/autodl-tmp/results/capacity_history_thesis_core_v3}"
PYTHON_BIN="${PYTHON_BIN:-/root/miniconda3/bin/python}"
MANIFEST="${V3_ROOT}/protocol/thesis_core_run_manifest.json"
LOG_DIR="${V3_ROOT}/logs"

date '+%F %T %Z'
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu \
  --format=csv,noheader

planned=0
complete=0
while IFS= read -r run_id; do
  planned=$((planned + 1))
  if [[ -f "${V3_ROOT}/training/${run_id}/TRAINING_COMPLETE.json" ]]; then
    complete=$((complete + 1))
  fi
done < <(
  "${PYTHON_BIN}" -c \
    'import json,sys; print("\n".join(x["run_id"] for x in json.load(open(sys.argv[1]))["runs"]))' \
    "${MANIFEST}"
)
echo "formal_complete=${complete}/${planned} remaining=$((planned - complete))"

for shard in 0 1 2 3 4 5; do
  log="${LOG_DIR}/shard_${shard}.log"
  epochs=$(grep -c '^Epoch ' "${log}" 2>/dev/null || true)
  outputs=$(grep -c 'capacity_history_thesis_core_training_complete_v3' "${log}" 2>/dev/null || true)
  latest=$(grep '^Epoch ' "${log}" 2>/dev/null | tail -n 1 || true)
  state="exited"
  if screen -ls 2>/dev/null | grep -q "thesis_core_${shard}"; then
    state="screen-alive"
  elif [[ -f "${LOG_DIR}/shard_${shard}.pid" ]] && \
       kill -0 "$(<"${LOG_DIR}/shard_${shard}.pid")" 2>/dev/null; then
    state="nohup-alive"
  fi
  echo "shard=${shard} state=${state} epoch_lines=${epochs} completed_outputs=${outputs} latest=${latest:-none}"
done

error_logs=$(grep -lE 'Traceback|ValueError|ResourceExhaustedError' \
  "${LOG_DIR}"/shard_[0-5].log 2>/dev/null || true)
if [[ -n "${error_logs}" ]]; then
  echo "ACTIVE_LOG_ERRORS"
  echo "${error_logs}"
else
  echo "active_log_errors=none"
fi
