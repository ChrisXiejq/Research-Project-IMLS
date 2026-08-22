#!/usr/bin/env bash
set -u

V3_ROOT="${1:-/root/autodl-tmp/results/capacity_history_thesis_core_v3}"
RESULTS_DIR="${V3_ROOT}/closed_loop"

date '+%F %T %Z'
map_status="unavailable"
if /root/miniconda3/envs/carla_modern/bin/python -c \
  'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(3); print(c.get_world().get_map().name)' \
  >/tmp/thesis_v3_carla_map.txt 2>/dev/null; then
  map_status="$(</tmp/thesis_v3_carla_map.txt)"
fi
echo "carla_map=${map_status}"

successful=$(find "${RESULTS_DIR}" -name scenario_run_summary.json -type f -print0 2>/dev/null \
  | xargs -0 -r /root/miniconda3/envs/carla_modern/bin/python -c \
  'import json,sys; print(sum(json.load(open(p)).get("ran_successfully") is True for p in sys.argv[1:]))' 2>/dev/null)
successful="${successful:-0}"
complete=$(find "${RESULTS_DIR}" -name ROLLOUT_COMPLETE.json -type f 2>/dev/null | wc -l | tr -d ' ')
echo "successful_scenarios=${successful}/80 formal_completion_gates=${complete}/80"

if screen -ls 2>/dev/null | grep -q '[.]thesis_v3_online[[:space:]]'; then
  echo "runner=active"
else
  echo "runner=inactive"
fi
if [[ -f "${RESULTS_DIR}/CLOSED_LOOP_COMPLETE.json" ]]; then
  echo "closed_loop_complete=present"
else
  echo "closed_loop_complete=absent"
fi

log="${RESULTS_DIR}/online_runner.log"
if [[ -f "${log}" ]]; then
  echo "latest_log:"
  tail -n 8 "${log}"
fi
