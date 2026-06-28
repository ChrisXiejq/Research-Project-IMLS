#!/usr/bin/env bash
set -euo pipefail

# Controlled target-speed sweep for the dissertation give-way experiment.
#
# Purpose:
#   Expand the validated single give-way case into a small controlled experiment
#   by varying only the priority target vehicle speed. The final geometry,
#   rule-aware supervisor, yield tuning, deterministic yield bypass, and bounded
#   recovery handoff are kept unchanged.
#
# Default sweep:
#   target init/nominal speed = 4.5, 6.0, 7.5 m/s
#
# For each speed:
#   1. Full method: risk_profile=adaptive_interaction_severity
#      policies: smpc_var_risk smpc_fixed_risk smpc_open_loop
#   2. No-adaptive-risk ablation: risk_profile=rule_aware_static_risk
#      policies: smpc_var_risk smpc_fixed_risk
#
# Optional environment overrides:
#   TARGET_SPEEDS="4.5 6.0 7.5"
#   RESULTS_DIR=/path/to/results_dir
#   PYTHON_BIN=python
#   ENABLE_CAMERA_VIZ=0          # default: 0 for quantitative sweeps
#   INCLUDE_NOTV=1               # required by compute_scenario_results metrics
#   POSTPROCESS_NO_PLOTS=1       # default: 1 for faster sweep metrics

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SCENARIO_DIR="${SCRIPT_DIR}/scenarios"
BASE_SCENARIO="${SCENARIO_DIR}/scenario_uk_give_way.json"
TUNING_CONFIG="${SCENARIO_DIR}/tuning_configs/give_way_smpc_tuning.json"

PYTHON_BIN="${PYTHON_BIN:-python}"
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/${RUN_STAMP}_target_speed_sweep}"
GENERATED_DIR="${SCENARIO_DIR}/generated/${RUN_STAMP}_target_speed_sweep"
TARGET_SPEEDS="${TARGET_SPEEDS:-4.5 6.0 7.5}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"
INCLUDE_NOTV="${INCLUDE_NOTV:-1}"
POSTPROCESS_NO_PLOTS="${POSTPROCESS_NO_PLOTS:-1}"

mkdir -p "${RESULTS_DIR}" "${GENERATED_DIR}"

MANIFEST="${RESULTS_DIR}/target_speed_sweep_manifest.csv"
SUMMARY_CSV="${RESULTS_DIR}/target_speed_sweep_summary.csv"
SUMMARY_MD="${RESULTS_DIR}/target_speed_sweep_summary.md"

echo "speed_mps,profile,scenario_glob,results_dir" > "${MANIFEST}"

camera_args=()
if [[ "${ENABLE_CAMERA_VIZ}" == "1" ]]; then
  camera_args+=(--enable_camera_viz)
else
  camera_args+=(--disable_camera_viz)
fi

notv_args=()
if [[ "${INCLUDE_NOTV}" == "1" ]]; then
  notv_args+=(--with_notv --with_notv_cl)
fi

postprocess_args=()
if [[ "${POSTPROCESS_NO_PLOTS}" == "1" ]]; then
  postprocess_args+=(--postprocess_no_plots)
fi

cd "${SCRIPT_DIR}"

make_speed_tag() {
  local speed="$1"
  printf 'target_%sms' "${speed//./p}"
}

generate_scenario() {
  local speed="$1"
  local tag="$2"
  local out_file="${GENERATED_DIR}/scenario_uk_give_way_${tag}.json"

  "${PYTHON_BIN}" - "${BASE_SCENARIO}" "${out_file}" "${speed}" "${TUNING_CONFIG}" <<'PY'
import json
import os
import sys

base_path, out_path, speed_text, tuning_path = sys.argv[1:5]
speed = float(speed_text)

with open(base_path, "r", encoding="utf-8") as f:
    scenario = json.load(f)

scenario["tuning_config"] = os.path.abspath(tuning_path)

desc = dict(scenario.get("scenario_description", {}))
desc["name"] = f"{desc.get('name', 'give-way target-speed sweep')} target_speed={speed:g}mps"
desc["controlled_sweep"] = {
    "sweep_variable": "priority target init_speed and nominal_speed",
    "target_speed_mps": speed,
    "fixed_controls": [
        "right-hand traffic give-way geometry",
        "ego start_left_offset=+2.75",
        "yield_stop_buffer_distance=8.0",
        "yield_release_clearance_margin=1.0",
        "rule-aware supervisor and bounded deterministic bypass",
    ],
}
scenario["scenario_description"] = desc

for vehicle in scenario.get("vehicle_params", []):
    if vehicle.get("role") == "target":
        vehicle["init_speed"] = speed
        vehicle["nominal_speed"] = speed

os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(scenario, f, indent=2)
    f.write("\n")
PY

  printf '%s\n' "${out_file}"
}

run_batch() {
  local speed="$1"
  local tag="$2"
  local profile="$3"
  local profile_label="$4"
  local scenario_glob="$5"
  shift 5
  local policies=("$@")
  local run_dir="${RESULTS_DIR}/${tag}_${profile_label}"
  local scenario_name="scenario_uk_give_way_${tag}"

  echo
  echo "============================================================"
  echo "Running target-speed sweep: speed=${speed}m/s profile=${profile}"
  echo "Results: ${run_dir}"
  echo "Policies: ${policies[*]}"
  echo "============================================================"

  "${PYTHON_BIN}" run_all_scenarios.py \
    --scenario_glob "${scenario_glob}" \
    --init_glob "ego_init_01.json" \
    --results_dir "${run_dir}" \
    --policies "${policies[@]}" \
    --solver_backend gurobi \
    --risk_profile "${profile}" \
    "${camera_args[@]}" \
    "${notv_args[@]}" \
    "${postprocess_args[@]}" \
    --postprocess_plot_scenario "${scenario_name}" \
    --postprocess_plot_init 1

  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${run_dir}"

  echo "${speed},${profile_label},${scenario_glob},${run_dir}" >> "${MANIFEST}"
}

for speed in ${TARGET_SPEEDS}; do
  tag="$(make_speed_tag "${speed}")"
  scenario_file="$(generate_scenario "${speed}" "${tag}")"
  scenario_glob="generated/${RUN_STAMP}_target_speed_sweep/$(basename "${scenario_file}")"

  run_batch \
    "${speed}" \
    "${tag}" \
    "adaptive_interaction_severity" \
    "adaptive" \
    "${scenario_glob}" \
    smpc_var_risk smpc_fixed_risk smpc_open_loop

  run_batch \
    "${speed}" \
    "${tag}" \
    "rule_aware_static_risk" \
    "static_risk" \
    "${scenario_glob}" \
    smpc_var_risk smpc_fixed_risk
done

"${PYTHON_BIN}" - "${MANIFEST}" "${SUMMARY_CSV}" "${SUMMARY_MD}" <<'PY'
import csv
import json
import math
import os
import sys

manifest_path, summary_csv, summary_md = sys.argv[1:4]

def fmt(value):
    if value in (None, ""):
        return ""
    try:
        value = float(value)
        if not math.isfinite(value):
            return ""
        return f"{value:.4g}"
    except Exception:
        return str(value)

def gate_by_policy(results_dir):
    path = os.path.join(results_dir, "postcarla_trajectory_gate.json")
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    out = {}
    for row in payload.get("evaluations", []):
        policy = row.get("policy", "")
        pair = (row.get("pair_safety") or [{}])[0]
        yield_rule = (row.get("yield_rules") or [{}])[0]
        out[policy] = {
            "gate_status": row.get("status", ""),
            "required": row.get("is_required_policy", ""),
            "completion_valid": row.get("completion_valid", ""),
            "gate_solver_failure_frac": row.get("solver_failure_frac", ""),
            "center_dmin_gate": pair.get("min_center_distance_m", ""),
            "footprint_collision": pair.get("footprint_collision", ""),
            "yield_ok": yield_rule.get("target_clears_before_ego_enters", ""),
        }
    return out

fields = [
    "speed_mps",
    "profile",
    "policy",
    "gate_status",
    "completion_valid",
    "yield_ok",
    "footprint_collision",
    "completion_time",
    "dmin_TV",
    "solver_failure_frac",
    "average_solve_time",
    "max_lateral_acceleration",
    "avg_longitudinal_jerk",
    "avg_lateral_jerk",
    "forced_reference_linearization_frac",
    "max_abs_ey_debug",
    "results_dir",
]

rows = []
with open(manifest_path, "r", encoding="utf-8") as f:
    for manifest in csv.DictReader(f):
        results_dir = manifest["results_dir"]
        gate = gate_by_policy(results_dir)
        df_path = os.path.join(results_dir, "df_final.csv")
        if not os.path.isfile(df_path):
            continue
        with open(df_path, "r", encoding="utf-8") as df:
            for metric in csv.DictReader(df):
                policy = metric.get("policy", "")
                if not policy.startswith("smpc"):
                    continue
                grow = gate.get(policy, {})
                row = {
                    "speed_mps": manifest["speed_mps"],
                    "profile": manifest["profile"],
                    "policy": policy,
                    "gate_status": grow.get("gate_status", ""),
                    "completion_valid": grow.get("completion_valid", ""),
                    "yield_ok": grow.get("yield_ok", ""),
                    "footprint_collision": grow.get("footprint_collision", ""),
                    "completion_time": metric.get("completion_time", ""),
                    "dmin_TV": metric.get("dmin_TV", ""),
                    "solver_failure_frac": metric.get("solver_failure_frac", grow.get("gate_solver_failure_frac", "")),
                    "average_solve_time": metric.get("average_solve_time", ""),
                    "max_lateral_acceleration": metric.get("max_lateral_acceleration", ""),
                    "avg_longitudinal_jerk": metric.get("avg_longitudinal_jerk", ""),
                    "avg_lateral_jerk": metric.get("avg_lateral_jerk", ""),
                    "forced_reference_linearization_frac": metric.get("forced_reference_linearization_frac", ""),
                    "max_abs_ey_debug": metric.get("max_abs_ey_debug", ""),
                    "results_dir": results_dir,
                }
                rows.append(row)

os.makedirs(os.path.dirname(summary_csv), exist_ok=True)
with open(summary_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

with open(summary_md, "w", encoding="utf-8") as f:
    f.write("# Target-Speed Sweep Summary\n\n")
    f.write(f"- Manifest: `{manifest_path}`\n")
    f.write(f"- CSV: `{summary_csv}`\n\n")
    f.write("| " + " | ".join(fields[:-1]) + " |\n")
    f.write("|" + "|".join(["---"] * (len(fields) - 1)) + "|\n")
    for row in rows:
        f.write("| " + " | ".join(fmt(row.get(k, "")) for k in fields[:-1]) + " |\n")

print(f"Wrote {summary_csv}")
print(f"Wrote {summary_md}")
PY

echo
echo "Target-speed sweep complete."
echo "Results root: ${RESULTS_DIR}"
echo "Manifest: ${MANIFEST}"
echo "Summary CSV: ${SUMMARY_CSV}"
echo "Summary Markdown: ${SUMMARY_MD}"
