#!/usr/bin/env bash
set -euo pipefail

# A3: supervisor-authority / risk-owned-yield architecture experiment.
#
# This is not a replacement for the frozen v12 shared baseline. It deliberately
# reduces nominal deterministic yield takeover while keeping emergency braking
# distance and footprint-clearance guards active, so fixed/adaptive risk policies
# can be evaluated with less supervisor masking.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_init01_v13_A3_risk_owned_yield}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INIT_ID="${INIT_ID:-01}"
TARGET_START_OFFSETS="${TARGET_START_OFFSETS:--3.0 0.0 3.0}"
TARGET_SPEED="${TARGET_SPEED:-9.0}"
BASE_TUNING_CONFIG="${BASE_TUNING_CONFIG:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json}"
RESUME="${RESUME:-0}"

if [[ "${INIT_ID}" != "01" ]]; then
  cat >&2 <<EOF
ERROR: this focused A3 risk-owned-yield experiment must run init01 only.
  got INIT_ID=${INIT_ID}
EOF
  exit 2
fi

if [[ ! -f "${BASE_TUNING_CONFIG}" ]]; then
  cat >&2 <<EOF
ERROR: A3 risk-owned-yield tuning config not found:
  ${BASE_TUNING_CONFIG}
EOF
  exit 2
fi

mkdir -p "${RESULTS_DIR}/tuning_configs"

cat > "${RESULTS_DIR}/ablation_manifest.jsonl" <<EOF
{"event":"ablation_start","script":"$(basename "$0")","init_id":"${INIT_ID}","target_start_offsets":"${TARGET_START_OFFSETS}","target_speed":${TARGET_SPEED},"base_tuning_config":"${BASE_TUNING_CONFIG}","authority_regime":"risk_owned_yield","fixed_shared_baseline":"v12_current_best_reference_only","architecture_change":"nominal supervisor yield takeover reduced; emergency/footprint guards retained","arms":["smpc_fixed_aggressive","smpc_fixed_medium","smpc_fixed_conservative","smpc_adaptive_floor_weak"],"resume":${RESUME}}
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
config["config_name"] = f"give_way_v13_a3_risk_owned_yield_offset_{label}"
config["description"] = (
    "Generated from v13 risk-owned-yield A3 baseline. "
    "Only priority target start_longitudinal_offset and speed are varied; "
    "ego keeps yield_risk_owned_yield_enabled=true."
)
ego = config.setdefault("vehicle_role_overrides", {}).setdefault("ego", {})
ego["yield_risk_owned_yield_enabled"] = True
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
  for arm in \
    smpc_fixed_aggressive \
    smpc_fixed_medium \
    smpc_fixed_conservative \
    smpc_adaptive_floor_weak; do
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
    echo "Skipping completed A3 risk-owned-yield point: ${label}"
    printf '{"event":"ablation_skipped_completed","label":"%s","target_start_longitudinal_offset":%s,"results_dir":"%s"}\n' \
      "${label}" "${offset}" "${difficulty_dir}" >> "${RESULTS_DIR}/ablation_manifest.jsonl"
    continue
  fi

  printf '{"event":"ablation_difficulty_start","label":"%s","target_start_longitudinal_offset":%s,"tuning_config":"%s"}\n' \
    "${label}" "${offset}" "${tuning_config}" >> "${RESULTS_DIR}/ablation_manifest.jsonl"

  echo "Running A3 risk-owned-yield point: ${label}"
  RESULTS_DIR="${difficulty_dir}" \
  FROZEN_REDUCED_TUNING_CONFIG="${tuning_config}" \
  INIT_ID="${INIT_ID}" \
  INCLUDE_ADAPTIVE_ABLATIONS=0 \
  SKIP_COMPLETED_SUBRUNS="${RESUME}" \
  "${SCRIPT_DIR}/experimental/run_give_way_init01_fixed_frontier_vs_adaptive.sh"

  printf '{"event":"ablation_difficulty_end","label":"%s","target_start_longitudinal_offset":%s,"results_dir":"%s"}\n' \
    "${label}" "${offset}" "${difficulty_dir}" >> "${RESULTS_DIR}/ablation_manifest.jsonl"
done

cat > "${RESULTS_DIR}/README.md" <<EOF
# A3 Init01 v13 Risk-Owned-Yield Supervisor-Authority Experiment

This architecture experiment keeps the v12 close-stop / approach-braking
baseline as reference, but enables \`yield_risk_owned_yield_enabled=true\`.
The reduced supervisor no longer takes over for nominal overlap/hold conditions;
emergency braking-distance and footprint-clearance guards remain active.

Requested target start offsets:

\`\`\`text
${TARGET_START_OFFSETS}
\`\`\`

Target speed is fixed at \`${TARGET_SPEED}m/s\`.
EOF

echo "A3 v13 risk-owned-yield experiment complete: ${RESULTS_DIR}"
