#!/usr/bin/env bash
set -euo pipefail

# A1: arrival-gap / interaction-timing sweep for the frozen v12 baseline.
#
# This keeps the v12 shared planner/supervisor settings fixed and varies only
# the priority target start_longitudinal_offset. The goal is to stress the
# give-way timing boundary more directly than target-speed-only sweeps.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_init01_v12_arrival_gap_sweep}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INIT_ID="${INIT_ID:-01}"
TARGET_START_OFFSETS="${TARGET_START_OFFSETS:--3.0 -1.5 0.0 1.5 3.0}"
TARGET_SPEED="${TARGET_SPEED:-9.0}"
BASE_TUNING_CONFIG="${BASE_TUNING_CONFIG:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v12_current_best.json}"
RESUME="${RESUME:-0}"

if [[ "${INIT_ID}" != "01" ]]; then
  cat >&2 <<EOF
ERROR: this focused arrival-gap sweep must run init01 only.
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

cat > "${RESULTS_DIR}/sweep_manifest.jsonl" <<EOF
{"event":"sweep_start","script":"$(basename "$0")","init_id":"${INIT_ID}","target_start_offsets":"${TARGET_START_OFFSETS}","target_speed":${TARGET_SPEED},"base_tuning_config":"${BASE_TUNING_CONFIG}","fixed_shared_baseline":"v12_current_best","varied_parameter":"target.start_longitudinal_offset","resume":${RESUME}}
EOF

make_gap_tuning() {
  local offset="$1"
  local out_path="$2"
  "${PYTHON_BIN}" -c '
import json
import sys

offset = float(sys.argv[1])
speed = float(sys.argv[2])
base_path = sys.argv[3]
out_path = sys.argv[4]

with open(base_path, "r", encoding="utf-8") as f:
    config = json.load(f)

label = f"{offset:+.1f}".replace("+", "p").replace("-", "m").replace(".", "p")
config["config_name"] = f"give_way_v12_arrival_gap_offset_{label}"
config["description"] = (
    "Generated from v12 current-best baseline for A1 arrival-gap sweep. "
    "Only priority target start_longitudinal_offset is changed; target speed, "
    "ego planner, supervisor, stop-clearance, and adaptive-risk settings are unchanged."
)
target = config.setdefault("vehicle_role_overrides", {}).setdefault("target", {})
target["start_longitudinal_offset"] = offset
target["nominal_speed"] = speed
target["init_speed"] = speed

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
' "${offset}" "${TARGET_SPEED}" "${BASE_TUNING_CONFIG}" "${out_path}"
}

format_label() {
  local offset="$1"
  local label="${offset/-/m}"
  label="${label//./p}"
  if [[ "${offset}" != -* ]]; then
    label="p${label}"
  fi
  printf "arrival_offset_%s" "${label}"
}

difficulty_complete() {
  local difficulty_dir="$1"
  local arm
  for arm in smpc_fixed_aggressive smpc_fixed_medium smpc_fixed_conservative smpc_adaptive_floor_weak; do
    if [[ ! -f "${difficulty_dir}/${arm}/postcarla_trajectory_gate.json" ]]; then
      return 1
    fi
    if [[ ! -f "${difficulty_dir}/${arm}/paper_metrics_summary.csv" ]]; then
      return 1
    fi
  done
  return 0
}

for offset in ${TARGET_START_OFFSETS}; do
  label="$(format_label "${offset}")"
  difficulty_dir="${RESULTS_DIR}/${label}"
  tuning_config="${RESULTS_DIR}/tuning_configs/${label}.json"

  make_gap_tuning "${offset}" "${tuning_config}"

  if [[ "${RESUME}" == "1" ]] && difficulty_complete "${difficulty_dir}"; then
    echo "Skipping completed arrival-gap point: ${label}"
    printf '{"event":"difficulty_skipped_completed","label":"%s","target_start_longitudinal_offset":%s,"results_dir":"%s"}\n' \
      "${label}" "${offset}" "${difficulty_dir}" >> "${RESULTS_DIR}/sweep_manifest.jsonl"
    continue
  fi

  printf '{"event":"difficulty_start","label":"%s","target_start_longitudinal_offset":%s,"tuning_config":"%s"}\n' \
    "${label}" "${offset}" "${tuning_config}" >> "${RESULTS_DIR}/sweep_manifest.jsonl"

  echo "Running v12 init01 arrival-gap sweep point: ${label}"
  RESULTS_DIR="${difficulty_dir}" \
  FROZEN_REDUCED_TUNING_CONFIG="${tuning_config}" \
  INIT_ID="${INIT_ID}" \
  SKIP_COMPLETED_SUBRUNS="${RESUME}" \
  "${SCRIPT_DIR}/run_give_way_init01_fixed_frontier_vs_adaptive.sh"

  printf '{"event":"difficulty_end","label":"%s","target_start_longitudinal_offset":%s,"results_dir":"%s"}\n' \
    "${label}" "${offset}" "${difficulty_dir}" >> "${RESULTS_DIR}/sweep_manifest.jsonl"
done

if [[ -f "${REPO_DIR}/docs/paper/generate_v12_claim_sweep_report.py" ]]; then
  "${PYTHON_BIN}" "${REPO_DIR}/docs/paper/generate_v12_claim_sweep_report.py" \
    "${RESULTS_DIR}" \
    --title "A1 v12 Arrival-Gap / Interaction-Timing Sweep"
fi

cat > "${RESULTS_DIR}/README.md" <<EOF
# A1 Init01 v12 Arrival-Gap / Interaction-Timing Sweep

This sweep freezes the current-best v12 shared planner/supervisor baseline and
varies only the priority target \`start_longitudinal_offset\`:

\`\`\`text
${TARGET_START_OFFSETS}
\`\`\`

Target speed is fixed at \`${TARGET_SPEED}m/s\`.

Each difficulty point runs the fixed-risk frontier plus \`adaptive_floor_weak\`.
Use this to find a hard interaction subset before mechanism ablations.
EOF

echo "A1 v12 arrival-gap sweep complete: ${RESULTS_DIR}"
