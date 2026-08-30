#!/usr/bin/env bash
set -euo pipefail

source_root="$1"
destination_root="$2"
old_root="$3"
repository_root="$4"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-/root/miniconda3/bin/python}"
source_screen="${SOURCE_PIPELINE_SCREEN:-mask_v4_offline}"
source_finalizer_screen="${SOURCE_FINALIZER_SCREEN:-mask_v4_finalizer}"
destination_screen="${DESTINATION_PIPELINE_SCREEN:-mask_v4e_offline}"
destination_finalizer_screen="${DESTINATION_FINALIZER_SCREEN:-mask_v4e_finalizer}"
manifest="$old_root/protocol/thesis_core_run_manifest.json"
heldout_root="$source_root/postprocess/heldout"
transition_log="$source_root/logs/v4_to_v4e_transition.log"
trigger_audit="$source_root/postprocess/training_curve_audit_pre_freeze.json"
training_audit="$source_root/postprocess/training_audit_pre_freeze.json"
extension_protocol="$destination_root/protocol/EXTENSION_PROTOCOL.json"
spill_root="/dev/shm/mask_v4e_epoch_checkpoints_20fa5a3"

mkdir -p "$source_root/logs"
exec >>"$transition_log" 2>&1
echo "TRANSITION_WATCH_START=$(date -Iseconds)"

while true; do
  completed="$({ find "$source_root/training" -name TRAINING_COMPLETE.json -type f 2>/dev/null || true; } | wc -l | tr -d ' ')"
  heldout_json="$({ find "$heldout_root" -name '*.json' -type f 2>/dev/null || true; } | wc -l | tr -d ' ')"
  available_bytes="$(df -B1 --output=avail /root/autodl-tmp | tail -1 | tr -d ' ')"
  echo "TRANSITION_WAIT=$(date -Iseconds) training=$completed/27 heldout_json=$heldout_json available_bytes=$available_bytes"
  if [[ "$heldout_json" != "0" ]]; then
    echo "TRANSITION_BLOCKED=heldout_already_accessed"
    exit 10
  fi
  if (( available_bytes < 5368709120 )); then
    echo "TRANSITION_BLOCKED=persistent_disk_below_5GiB"
    exit 11
  fi
  if [[ "$completed" == "27" ]]; then
    break
  fi
  if ! screen -ls 2>/dev/null | grep -Fq ".$source_screen"; then
    echo "TRANSITION_BLOCKED=source_pipeline_screen_missing"
    exit 12
  fi
  sleep 60
done

echo "TRANSITION_PHASE=pre_freeze_training_integrity START=$(date -Iseconds)"
"$python_bin" "$script_dir/audit_thesis_core_v3_training.py" \
  --manifest "$manifest" \
  --training-root "$source_root/training" \
  --output "$training_audit"

echo "TRANSITION_PHASE=pre_freeze_curve_gate START=$(date -Iseconds)"
"$python_bin" "$script_dir/write_pre_freeze_training_curve_audit_v4.py" \
  --training-root "$source_root/training" \
  --manifest "$manifest" \
  --output "$trigger_audit"

"$python_bin" -c '
import json, sys
training = json.load(open(sys.argv[1], encoding="utf-8"))
curves = json.load(open(sys.argv[2], encoding="utf-8"))
if training.get("status") != "pass" or training.get("valid_runs") != 27:
    raise SystemExit("training integrity audit did not pass for 27 runs")
if curves.get("status") != "fail" or curves.get("runs") != 27:
    raise SystemExit("uniform extension trigger is not a failed 27-run audit")
if not curves.get("unresolved_boundary_underfit_runs"):
    raise SystemExit("uniform extension trigger contains no unresolved run")
if curves.get("heldout_accessed") is not False:
    raise SystemExit("pre-freeze audit does not prove held-out isolation")
' "$training_audit" "$trigger_audit"

heldout_json="$({ find "$heldout_root" -name '*.json' -type f 2>/dev/null || true; } | wc -l | tr -d ' ')"
if [[ "$heldout_json" != "0" ]]; then
  echo "TRANSITION_BLOCKED=heldout_race_before_amendment"
  exit 13
fi

echo "TRANSITION_PHASE=stop_superseded_80_epoch_pipeline START=$(date -Iseconds)"
screen -S "$source_screen" -X quit 2>/dev/null || true
screen -S "$source_finalizer_screen" -X quit 2>/dev/null || true
for _ in $(seq 1 30); do
  if ! screen -ls 2>/dev/null | grep -Fq ".$source_screen" \
    && ! ps -eo args= | grep -F "$source_root/training" | grep -Eq 'thesis_core_v3_execute|train_thesis_core_cached_v3'; then
    break
  fi
  sleep 1
done
if screen -ls 2>/dev/null | grep -Fq ".$source_screen" \
  || ps -eo args= | grep -F "$source_root/training" | grep -Eq 'thesis_core_v3_execute|train_thesis_core_cached_v3'; then
  echo "TRANSITION_BLOCKED=source_pipeline_did_not_stop"
  exit 14
fi

mkdir -p "$destination_root/protocol" "$destination_root/logs" "$destination_root/postprocess"
if [[ ! -e "$destination_root/feature_cache_v4" && ! -L "$destination_root/feature_cache_v4" ]]; then
  ln -s "$source_root/feature_cache_v4" "$destination_root/feature_cache_v4"
fi
if [[ ! -e "$destination_root/impact_audit_old_checkpoints" && ! -L "$destination_root/impact_audit_old_checkpoints" ]]; then
  ln -s "$source_root/impact_audit_old_checkpoints" "$destination_root/impact_audit_old_checkpoints"
fi
[[ "$(readlink -f "$destination_root/feature_cache_v4")" == "$(readlink -f "$source_root/feature_cache_v4")" ]]
[[ "$(readlink -f "$destination_root/impact_audit_old_checkpoints")" == "$(readlink -f "$source_root/impact_audit_old_checkpoints")" ]]

echo "TRANSITION_PHASE=seed_uniform_extension START=$(date -Iseconds)"
"$python_bin" "$script_dir/prepare_future_mask_v4e_extension.py" \
  --manifest "$manifest" \
  --source-training-root "$source_root/training" \
  --trigger-audit "$trigger_audit" \
  --corrected-heldout-root "$heldout_root" \
  --destination-root "$destination_root/training" \
  --spill-root "$spill_root" \
  --output "$extension_protocol"

if screen -ls 2>/dev/null | grep -Fq ".$destination_screen"; then
  echo "TRANSITION_BLOCKED=destination_pipeline_screen_already_exists"
  exit 15
fi

echo "TRANSITION_PHASE=start_uniform_extension START=$(date -Iseconds)"
cd "$script_dir"
screen -dmS "$destination_screen" bash "$script_dir/run_future_mask_v4e_pipeline.sh" \
  "$destination_root" "$old_root" "$destination_root/feature_cache_v4" "$extension_protocol"

pipeline_pid=""
for _ in $(seq 1 30); do
  pipeline_pid="$(ps -eo pid=,comm=,args= | awk -v needle="$script_dir/run_future_mask_v4e_pipeline.sh $destination_root $old_root $destination_root/feature_cache_v4 $extension_protocol" '$2 == "bash" && index($0, needle) > 0 {print $1; exit}')"
  if [[ -n "$pipeline_pid" ]]; then
    break
  fi
  sleep 1
done
if [[ -z "$pipeline_pid" ]]; then
  echo "TRANSITION_BLOCKED=live_destination_pipeline_pid_not_found"
  exit 16
fi

"$python_bin" "$script_dir/write_future_mask_v4e_pipeline_receipt.py" \
  --pid "$pipeline_pid" \
  --worktree "$repository_root" \
  --manifest "$manifest" \
  --dataset-complete "$old_root/dataset_35_5_5/THESIS_CORE_DATASET_COMPLETE.json" \
  --cache-complete "$source_root/feature_cache_v4/CACHE_COMPLETE.json" \
  --extension-protocol "$extension_protocol" \
  --output-root "$destination_root" \
  --output "$destination_root/protocol/RUNNING_PIPELINE_RECEIPT.json"

if screen -ls 2>/dev/null | grep -Fq ".$destination_finalizer_screen"; then
  echo "TRANSITION_BLOCKED=destination_finalizer_screen_already_exists"
  exit 17
fi
screen -dmS "$destination_finalizer_screen" bash "$script_dir/finalize_future_mask_v4_offline.sh" \
  "$destination_root" "$old_root" "$extension_protocol" "$destination_screen"

echo "TRANSITION_COMPLETE=$(date -Iseconds) pipeline_pid=$pipeline_pid"
