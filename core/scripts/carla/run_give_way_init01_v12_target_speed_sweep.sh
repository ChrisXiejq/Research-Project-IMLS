#!/usr/bin/env bash
set -euo pipefail

# Difficulty sweep for the current-best v12 give-way baseline.
#
# This script intentionally keeps the shared v12 planner/supervisor settings
# fixed and varies only the priority target speed. The goal is to expose the
# fixed-risk SMPC frontier's safety-efficiency trade-off against adaptive-risk
# SMPC, without giving adaptive an exclusive mechanism.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_init01_v12_target_speed_sweep}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INIT_ID="${INIT_ID:-01}"
TARGET_SPEEDS="${TARGET_SPEEDS:-8.0 8.5 9.0 9.5 10.0}"
BASE_TUNING_CONFIG="${BASE_TUNING_CONFIG:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v12_current_best.json}"
RESUME="${RESUME:-0}"

if [[ "${INIT_ID}" != "01" ]]; then
  cat >&2 <<EOF
ERROR: this focused difficulty sweep must run init01 only.
  got INIT_ID=${INIT_ID}
EOF
  exit 2
fi

if [[ ! -f "${BASE_TUNING_CONFIG}" ]]; then
  cat >&2 <<EOF
ERROR: v12 current-best tuning config not found:
  ${BASE_TUNING_CONFIG}
EOF
  exit 2
fi

mkdir -p "${RESULTS_DIR}/tuning_configs"

if [[ "${RESUME}" == "1" && -f "${RESULTS_DIR}/sweep_manifest.jsonl" ]]; then
  printf '{"event":"sweep_resume_start","script":"%s","init_id":"%s","target_speeds":"%s","base_tuning_config":"%s","fixed_shared_baseline":"v12_current_best","varied_parameter":"target.nominal_speed/init_speed","resume":1}\n' \
    "$(basename "$0")" "${INIT_ID}" "${TARGET_SPEEDS}" "${BASE_TUNING_CONFIG}" >> "${RESULTS_DIR}/sweep_manifest.jsonl"
else
  cat > "${RESULTS_DIR}/sweep_manifest.jsonl" <<EOF
{"event":"sweep_start","script":"$(basename "$0")","init_id":"${INIT_ID}","target_speeds":"${TARGET_SPEEDS}","base_tuning_config":"${BASE_TUNING_CONFIG}","fixed_shared_baseline":"v12_current_best","varied_parameter":"target.nominal_speed/init_speed","resume":${RESUME}}
EOF
fi

make_speed_tuning() {
  local speed="$1"
  local out_path="$2"
  "${PYTHON_BIN}" -c '
import json
import sys

speed = float(sys.argv[1])
base_path = sys.argv[2]
out_path = sys.argv[3]

with open(base_path, "r", encoding="utf-8") as f:
    config = json.load(f)

config["config_name"] = f"give_way_v12_target_speed_{speed:.1f}".replace(".", "p")
config["description"] = (
    "Generated from v12 current-best baseline for target-speed difficulty sweep. "
    "Only priority target nominal_speed/init_speed is changed; ego planner, "
    "supervisor, stop-clearance, and adaptive-risk settings are unchanged."
)
target = config.setdefault("vehicle_role_overrides", {}).setdefault("target", {})
target["nominal_speed"] = speed
target["init_speed"] = speed

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
' "${speed}" "${BASE_TUNING_CONFIG}" "${out_path}"
}

format_label() {
  local speed="$1"
  printf "target_speed_%s" "${speed//./p}"
}

speed_complete() {
  local speed_dir="$1"
  local arm
  for arm in smpc_fixed_aggressive smpc_fixed_medium smpc_fixed_conservative smpc_adaptive_floor_weak; do
    if [[ ! -f "${speed_dir}/${arm}/postcarla_trajectory_gate.json" ]]; then
      return 1
    fi
    if [[ ! -f "${speed_dir}/${arm}/paper_metrics_summary.csv" ]]; then
      return 1
    fi
  done
  return 0
}

for speed in ${TARGET_SPEEDS}; do
  label="$(format_label "${speed}")"
  speed_dir="${RESULTS_DIR}/${label}"
  tuning_config="${RESULTS_DIR}/tuning_configs/${label}.json"

  make_speed_tuning "${speed}" "${tuning_config}"

  if [[ "${RESUME}" == "1" ]] && speed_complete "${speed_dir}"; then
    echo "Skipping completed v12 sweep point: ${label}"
    printf '{"event":"difficulty_skipped_completed","label":"%s","target_speed":%s,"results_dir":"%s"}\n' \
      "${label}" "${speed}" "${speed_dir}" >> "${RESULTS_DIR}/sweep_manifest.jsonl"
    continue
  fi

  printf '{"event":"difficulty_start","label":"%s","target_speed":%s,"tuning_config":"%s"}\n' \
    "${label}" "${speed}" "${tuning_config}" >> "${RESULTS_DIR}/sweep_manifest.jsonl"

  echo "Running v12 init01 fixed-frontier vs adaptive sweep point: ${label}"
  RESULTS_DIR="${speed_dir}" \
  FROZEN_REDUCED_TUNING_CONFIG="${tuning_config}" \
  INIT_ID="${INIT_ID}" \
  SKIP_COMPLETED_SUBRUNS="${RESUME}" \
  "${SCRIPT_DIR}/run_give_way_init01_fixed_frontier_vs_adaptive.sh"

  printf '{"event":"difficulty_end","label":"%s","target_speed":%s,"results_dir":"%s"}\n' \
    "${label}" "${speed}" "${speed_dir}" >> "${RESULTS_DIR}/sweep_manifest.jsonl"
done

if [[ -f "${REPO_DIR}/docs/paper/generate_v12_target_speed_sweep_report.py" ]]; then
  "${PYTHON_BIN}" "${REPO_DIR}/docs/paper/generate_v12_target_speed_sweep_report.py" \
    "${RESULTS_DIR}"
fi

cat > "${RESULTS_DIR}/README.md" <<EOF
# Init01 v12 Target-Speed Difficulty Sweep

This sweep freezes the current-best v12 shared planner/supervisor baseline and
varies only the priority target vehicle speed:

\`\`\`text
${TARGET_SPEEDS}
\`\`\`

Each difficulty point runs:

- \`smpc_fixed_aggressive\`
- \`smpc_fixed_medium\`
- \`smpc_fixed_conservative\`
- \`smpc_adaptive_floor_weak\`

Interpretation target:

- fixed aggressive should expose safety / infeasibility / supervisor burden first;
- fixed conservative may preserve safety but should pay delay or completion cost;
- adaptive/floor_weak should be checked for conservative-like safety with
  medium/aggressive-like efficiency.
EOF

echo "v12 target-speed difficulty sweep complete: ${RESULTS_DIR}"
