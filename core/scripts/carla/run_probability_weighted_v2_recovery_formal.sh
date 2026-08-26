#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/autodl-tmp/Research-Project-IMLS-shadow-v2}"
RESULTS_ROOT="${RESULTS_ROOT:-/root/autodl-tmp/results/weighted_smpc_v2_recovery/formal_supervisor_on_80_v1}"
PYTHON_BIN="${PYTHON_BIN:-/root/miniconda3/envs/carla_modern/bin/python}"
CARLA_ROOT="${CARLA_ROOT:-/root/autodl-tmp/carla_0.9.14}"
GUROBI_LOADER="${GUROBI_LOADER:-/root/autodl-tmp/load_gurobi11.sh}"

SCENARIO="${REPO_DIR}/core/scripts/carla/scenarios/scenario_uk_give_way.json"
INIT_DIR="${REPO_DIR}/core/scripts/carla/scenarios/inits/supervisor_masking_shadow_v2"
ANCHORS="${REPO_DIR}/core/scripts/models/l5kit_clusters_16.npy"
ON_TUNING="${REPO_DIR}/core/scripts/carla/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json"
ADAPTIVE_CONFIG="${REPO_DIR}/core/scripts/carla/scenarios/tuning_configs/adaptive_floor_weak_v1.json"
TRAINING_ROOT="/root/autodl-tmp/results/capacity_history_thesis_core_v3/training"
CALIBRATION_ROOT="/root/autodl-tmp/results/capacity_history_thesis_core_v3/postprocess/calibration"
B1_RUN="v3__head-large__lr1e-4__s23__data100"
PSTAR_RUN="v3__transformer-h1p0-large__lr1e-4__s37__data100"

export CARLA_ROOT
export PYTHONPATH="${REPO_DIR}/core/scripts/models:${REPO_DIR}/core/scripts/carla:${PYTHONPATH:-}"
source "${GUROBI_LOADER}" >/dev/null 2>&1

test -x "${PYTHON_BIN}"
test -f "${SCENARIO}"
test -f "${ON_TUNING}"
test -f "${ADAPTIVE_CONFIG}"
test -f "${ANCHORS}"
pgrep -f 'CarlaUE4-Linux-Shipping.*world-port=2000' >/dev/null
mkdir -p "${RESULTS_ROOT}"

"${PYTHON_BIN}" - "${RESULTS_ROOT}" "${REPO_DIR}" "${TRAINING_ROOT}" "${CALIBRATION_ROOT}" <<'PY'
import datetime
import hashlib
import json
import pathlib
import sys

results_root = pathlib.Path(sys.argv[1])
repo = pathlib.Path(sys.argv[2])
training = pathlib.Path(sys.argv[3])
calibration = pathlib.Path(sys.argv[4])
b1 = "v3__head-large__lr1e-4__s23__data100"
pstar = "v3__transformer-h1p0-large__lr1e-4__s37__data100"

def digest(path):
    path = pathlib.Path(path)
    h = hashlib.sha256()
    if path.is_dir():
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            h.update(str(child.relative_to(path)).encode())
            h.update(b"\0")
            h.update(child.read_bytes())
    else:
        h.update(path.read_bytes())
    return h.hexdigest()

tracked = {
    "mode_probability_contract": repo / "core/scripts/carla/utils/mode_probability_contract.py",
    "smpc_model": repo / "core/scripts/carla/policies/smpc.py",
    "smpc_agent": repo / "core/scripts/carla/policies/smpc_agent.py",
    "scenario_runner": repo / "core/scripts/carla/scenarios/run_intersection_scenario.py",
    "batch_runner": repo / "core/scripts/carla/run_all_scenarios.py",
    "formal_runner": repo / "core/scripts/carla/run_probability_weighted_v2_recovery_formal.sh",
    "scenario": repo / "core/scripts/carla/scenarios/scenario_uk_give_way.json",
    "on_tuning": repo / "core/scripts/carla/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json",
    "adaptive_config": repo / "core/scripts/carla/scenarios/tuning_configs/adaptive_floor_weak_v1.json",
    "anchors": repo / "core/scripts/models/l5kit_clusters_16.npy",
    "B1_model": training / b1 / "best_model",
    "B1_calibration": calibration / b1 / "calibration.json",
    "P_star_model": training / pstar / "best_model",
    "P_star_calibration": calibration / pstar / "calibration.json",
}
for init_id in range(126, 136):
    tracked[f"init_{init_id}"] = repo / f"core/scripts/carla/scenarios/inits/supervisor_masking_shadow_v2/ego_init_{init_id}.json"
missing = [name for name, path in tracked.items() if not path.exists()]
if missing:
    raise SystemExit(f"Missing frozen protocol assets: {missing}")

cells = [
    {"cell_id": "B1__fixed_medium__assertive__supervisor_on", "predictor": "B1", "risk": "fixed_medium", "target_style": "assertive_constant_speed"},
    {"cell_id": "B1__fixed_medium__reactive__supervisor_on", "predictor": "B1", "risk": "fixed_medium", "target_style": "defensive_reactive"},
    {"cell_id": "B1__adaptive__assertive__supervisor_on", "predictor": "B1", "risk": "adaptive", "target_style": "assertive_constant_speed"},
    {"cell_id": "B1__adaptive__reactive__supervisor_on", "predictor": "B1", "risk": "adaptive", "target_style": "defensive_reactive"},
    {"cell_id": "P_star__fixed_medium__assertive__supervisor_on", "predictor": "P_star", "risk": "fixed_medium", "target_style": "assertive_constant_speed"},
    {"cell_id": "P_star__fixed_medium__reactive__supervisor_on", "predictor": "P_star", "risk": "fixed_medium", "target_style": "defensive_reactive"},
    {"cell_id": "P_star__adaptive__assertive__supervisor_on", "predictor": "P_star", "risk": "adaptive", "target_style": "assertive_constant_speed"},
    {"cell_id": "P_star__adaptive__reactive__supervisor_on", "predictor": "P_star", "risk": "adaptive", "target_style": "defensive_reactive"},
]
core = {
    "protocol_id": "probability_weighted_joint_mode_smpc_supervisor_on_80_v1",
    "objective_id": "multipath_joint_probability_expected_cost_v2",
    "objective_unweighted_option_available": False,
    "carla_version": "0.9.14",
    "town": "Town05",
    "target_styles": ["assertive_constant_speed", "defensive_reactive"],
    "camera_enabled": False,
    "formal_init_ids": list(range(126, 136)),
    "excluded_smoke_init_ids": list(range(116, 126)),
    "cells": cells,
    "supervisor_authority": "on",
    "risk_policies": ["fixed_medium", "adaptive"],
    "expected_unique_rollouts": 80,
    "file_sha256": {name: digest(path) for name, path in tracked.items()},
}
encoded = json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
payload = {
    "schema_version": "probability_weighted_smpc_recovery_protocol_v1",
    "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "core": core,
    "core_sha256": hashlib.sha256(encoded).hexdigest(),
}
path = results_root / "FROZEN_PROTOCOL.json"
if path.exists():
    existing = json.loads(path.read_text())
    if existing.get("core_sha256") != payload["core_sha256"]:
        raise SystemExit("Frozen protocol mismatch; refusing to mix experiment versions")
else:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(payload["core_sha256"])
PY

run_rollout() {
  local cell_id="$1" predictor="$2" risk="$3" target_style="$4" init_id="$5"
  local run_id policy risk_profile tuning run_dir scenario_dir
  local model calibration
  local adaptive_args=()

  if [[ "${predictor}" == "B1" ]]; then run_id="${B1_RUN}"; else run_id="${PSTAR_RUN}"; fi
  model="${TRAINING_ROOT}/${run_id}/best_model"
  calibration="${CALIBRATION_ROOT}/${run_id}/calibration.json"
  case "${risk}" in
    fixed_medium)
      policy="smpc_fixed_risk"
      risk_profile="fixed_frontier_medium"
      ;;
    adaptive)
      policy="smpc_var_risk"
      risk_profile="adaptive_interaction_severity"
      adaptive_args=(--adaptive_risk_config_file "${ADAPTIVE_CONFIG}")
      ;;
    *)
      echo "Unknown frozen risk policy: ${risk}" >&2
      return 4
      ;;
  esac
  tuning="${ON_TUNING}"

  run_dir="${RESULTS_ROOT}/${cell_id}/ego_init_${init_id}"
  scenario_dir="${run_dir}/rollout/scenario_uk_give_way_ego_init_${init_id}_${policy}"
  if [[ -s "${run_dir}/FORMAL_ROLLOUT_COMPLETE.json" ]]; then
    return 0
  fi
  mkdir -p "${run_dir}"
  "${PYTHON_BIN}" "${REPO_DIR}/core/scripts/carla/run_all_scenarios.py" \
    --scenario_glob "${SCENARIO}" \
    --init_glob "${INIT_DIR}/ego_init_${init_id}.json" \
    --results_dir "${run_dir}/rollout" \
    --policies "${policy}" \
    --risk_profile "${risk_profile}" \
    "${adaptive_args[@]}" \
    --tuning_config "${tuning}" \
    --prediction_model_weights "${model}" \
    --prediction_model_anchors "${ANCHORS}" \
    --prediction_model_calibration "${calibration}" \
    --target_style "${target_style}" \
    --disable_camera_viz --skip_postprocess --no_console_log \
    >"${run_dir}/runner.log" 2>&1

  test -s "${scenario_dir}/scenario_result.pkl"
  "${PYTHON_BIN}" "${REPO_DIR}/core/scripts/postcarla_trajectory_gate.py" \
    "${run_dir}/rollout" --required-policies "${policy}" \
    --footprint-margin-m 0.25 --footprint-margins-m 0.0,0.25,0.35,0.50 \
    >"${run_dir}/postprocess.log" 2>&1
  "${PYTHON_BIN}" "${REPO_DIR}/core/scripts/compute_scenario_results.py" \
    --results_dir "${run_dir}/rollout" --compute_metrics \
    >>"${run_dir}/postprocess.log" 2>&1

  "${PYTHON_BIN}" - "${run_dir}" "${cell_id}" "${init_id}" <<'PY'
import datetime
import json
import pathlib
import sys

run_dir = pathlib.Path(sys.argv[1])
cell_id = sys.argv[2]
init_id = int(sys.argv[3])
gate = json.loads((run_dir / "rollout/postcarla_trajectory_gate.json").read_text())
evaluation = gate["evaluations"][0]
pairs = evaluation.get("pair_safety") or []
competence = (
    evaluation.get("completion_valid") is True
    and evaluation.get("collision_envelope_logged") is True
    and all(not pair.get("footprint_collision") for pair in pairs)
    and float(evaluation.get("solver_failure_frac") or 0.0) <= 0.05
)
target_first = all(
    item.get("target_clears_before_ego_enters") is True
    for item in (evaluation.get("yield_rules") or [])
)
passed = competence and target_first
payload = {
    "schema_version": "probability_weighted_smpc_formal_rollout_gate_v1",
    "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "cell_id": cell_id,
    "init_id": init_id,
    "supervisor_authority": "on",
    "competence_pass": competence,
    "target_first_yield": target_first,
    "solver_failure_frac": evaluation.get("solver_failure_frac"),
    "postcarla_status": evaluation.get("status"),
    "passed": passed,
}
(run_dir / "FORMAL_ROLLOUT_COMPLETE.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
if not passed:
    raise SystemExit(f"Formal rollout gate failed: {payload}")
PY
}

while read -r cell predictor risk target_style; do
  for init_id in {126..135}; do
    run_rollout "${cell}" "${predictor}" "${risk}" "${target_style}" "${init_id}"
  done
done <<'CELLS'
B1__fixed_medium__assertive__supervisor_on B1 fixed_medium assertive_constant_speed
B1__fixed_medium__reactive__supervisor_on B1 fixed_medium defensive_reactive
B1__adaptive__assertive__supervisor_on B1 adaptive assertive_constant_speed
B1__adaptive__reactive__supervisor_on B1 adaptive defensive_reactive
P_star__fixed_medium__assertive__supervisor_on P_star fixed_medium assertive_constant_speed
P_star__fixed_medium__reactive__supervisor_on P_star fixed_medium defensive_reactive
P_star__adaptive__assertive__supervisor_on P_star adaptive assertive_constant_speed
P_star__adaptive__reactive__supervisor_on P_star adaptive defensive_reactive
CELLS

"${PYTHON_BIN}" - "${RESULTS_ROOT}" <<'PY'
import datetime
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
records = [json.loads(path.read_text()) for path in sorted(root.glob("*/ego_init_*/FORMAL_ROLLOUT_COMPLETE.json"))]
expected = 80
payload = {
    "schema_version": "probability_weighted_smpc_recovery_complete_v1",
    "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "expected_rollouts": expected,
    "completed_rollouts": len(records),
    "passed_rollouts": sum(bool(row.get("passed")) for row in records),
    "all_passed": len(records) == expected and all(bool(row.get("passed")) for row in records),
    "records": records,
}
(root / "FORMAL_COMPLETE.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
if not payload["all_passed"]:
    raise SystemExit("Formal recovery matrix incomplete or failed")
PY

echo "Weighted SMPC recovery formal matrix complete: ${RESULTS_ROOT}"
