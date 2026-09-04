#!/usr/bin/env bash
set -Eeuo pipefail

# Prospective SF4 behavioural-authority matrix:
# B1 x {adaptive, original fixed-medium} x {supervisor authority on, off}
# x {assertive, reactive} x ten new init clusters = 80 formal rollouts.
# Only infrastructure failures are retried. All adverse scientific outcomes
# are retained and passed to the preregistered failure-penalised analysis.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
DAY7_RESULTS="${DAY7_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day8/day8_validation_v1}"
SF4_RESULTS="${SF4_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/distinction_v1/sf4_supervisor_behavioural_authority_v1}"
SF4_MAX_ATTEMPTS="${SF4_MAX_ATTEMPTS:-10}"
B1_MODEL="${B1_MODEL:-${DAY8_RESULTS}/runs/B1/seed_37/best_model}"
B1_CALIBRATION="${B1_CALIBRATION:-${DAY8_RESULTS}/runs/B1/seed_37/calibration.json}"
B0_MODEL="${B0_MODEL:-${MODELS_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/assets/l5kit_clusters_16.npy}"
SCENARIO_SOURCE="${SCENARIO_SOURCE:-${SCRIPT_DIR}/scenarios/scenario_uk_give_way.json}"
BASE_TUNING="${BASE_TUNING:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_v15_supervisor_behavioural_authority_ablation.json}"
INIT_SOURCE="${INIT_SOURCE:-${SCRIPT_DIR}/scenarios/inits/distinction_sf4_supervisor_authority_ablation}"
INIT_MANIFEST="${INIT_MANIFEST:-${INIT_SOURCE}/SF4_INIT_CANDIDATE_MANIFEST.json}"
R3_INIT_MANIFEST="${R3_INIT_MANIFEST:-${SCRIPT_DIR}/scenarios/inits/distinction_r3_new/R3_INIT_GENERATION_MANIFEST.json}"
SMOKE_INIT="${SMOKE_INIT:-${SCRIPT_DIR}/scenarios/inits/distinction_r3_new/ego_init_105.json}"
PREREG_DIR="${PREREG_DIR:-${REPO_DIR}/core/scripts/models/protocols}"
PREREG_JSON="${PREREG_JSON:-${PREREG_DIR}/sf4_supervisor_behavioural_authority_prereg.json}"
PREREG_MD="${PREREG_MD:-${PREREG_DIR}/sf4_supervisor_behavioural_authority_prereg.md}"
FROZEN_COLLECTION="${FROZEN_COLLECTION:-${REPO_DIR}/docs/paper/generated/day5/day5_final_6b71ccc_frozen_config.json}"
ATTEMPT_MANAGER="${MODELS_DIR}/experimental/r3_attempt_manager.py"
PREPARE="${MODELS_DIR}/experimental/prepare_sf4_supervisor_behavioural_authority.py"
SPAWN_PREFLIGHTER="${MODELS_DIR}/experimental/preflight_sf4_supervisor_authority_inits.py"
ANALYZER="${MODELS_DIR}/experimental/analyze_sf4_supervisor_behavioural_authority.py"
PACKAGER="${MODELS_DIR}/experimental/package_sf4_compact_evidence.py"
FULL_PACKAGER="${MODELS_DIR}/experimental/package_sf4_full_raw_snapshot.py"
SMOKE_VALIDATOR="${MODELS_DIR}/experimental/validate_sf4_supervisor_authority_smoke.py"
PROTOCOL_ID="sf4_supervisor_behavioural_authority_v1"
SF4_PREFLIGHT_ONLY=0
SF4_SMOKE_ONLY=0
SF4_LIST_PENDING=0

usage() {
  cat <<'EOF'
Usage: run_sf4_supervisor_behavioural_authority_ablation.sh [--preflight-only | --smoke-only | --list-pending]

  --preflight-only  Verify the frozen design, clean Git state, Town05 spawn
                    eligibility, B1 deployment, GPU and Gurobi without a rollout.
  --smoke-only      Run and freeze four excluded init105 full-stack runtime
                    checks spanning the complete risk-by-authority factorial;
                    no formal outcome is read or retained as evidence.
  --list-pending    Verify accepted receipts and print resumable progress only.

Use one dedicated CARLA 0.9.14 Town05 server on 127.0.0.1:2000. No other
experiment may share that server while SF4 is active.
EOF
}

while (($#)); do
  case "$1" in
    --preflight-only) SF4_PREFLIGHT_ONLY=1 ;;
    --smoke-only) SF4_SMOKE_ONLY=1 ;;
    --list-pending) SF4_LIST_PENDING=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
if ((SF4_PREFLIGHT_ONLY + SF4_SMOKE_ONLY + SF4_LIST_PENDING > 1)); then
  echo "Choose only one of --preflight-only, --smoke-only or --list-pending" >&2
  exit 2
fi
if ((SF4_LIST_PENDING)); then
  exec "${PYTHON_BIN}" "${PREPARE}" progress --results-dir "${SF4_RESULTS}"
fi

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
if [[ ! "${SF4_MAX_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "SF4_MAX_ATTEMPTS must be a positive integer" >&2
  exit 2
fi
for required in \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" "${DAY7_RESULTS}/train.jsonl" \
  "${DAY8_RESULTS}/DAY8_COMPLETE.json" "${DAY8_RESULTS}/final_test_v1/DAY8_MODEL_SELECTION_FROZEN.json" \
  "${B1_MODEL}/saved_model.pb" "${B1_CALIBRATION}" "${B0_MODEL}/saved_model.pb" "${ANCHORS}" \
  "${SCENARIO_SOURCE}" "${BASE_TUNING}" "${INIT_MANIFEST}" "${R3_INIT_MANIFEST}" "${SMOKE_INIT}" \
  "${PREREG_JSON}" "${PREREG_MD}" "${FROZEN_COLLECTION}" \
  "${ATTEMPT_MANAGER}" "${PREPARE}" "${SPAWN_PREFLIGHTER}" "${ANALYZER}" "${PACKAGER}" "${FULL_PACKAGER}" "${SMOKE_VALIDATOR}" \
  "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py"; do
  test -e "${required}" || { echo "Missing SF4 asset: ${required}" >&2; exit 2; }
done
for init_id in $(seq 106 115); do
  test -f "${INIT_SOURCE}/ego_init_${init_id}.json" || { echo "Missing init${init_id}" >&2; exit 2; }
done

mkdir -p "${SF4_RESULTS}"
exec > >(tee -a "${SF4_RESULTS}/sf4_runner.log") 2>&1
LOCK="${SF4_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another SF4 runner is active: PID $(cat "${LOCK}/pid")" >&2
    exit 3
  fi
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}"
  mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() { rm -f "${LOCK}/pid"; rmdir "${LOCK}" 2>/dev/null || true; }
trap cleanup EXIT

if [[ -n "$(git -C "${REPO_DIR}" status --porcelain --untracked-files=no)" ]]; then
  echo "SF4 requires a clean tracked Git worktree. Commit/stash tracked changes first." >&2
  git -C "${REPO_DIR}" status --short --untracked-files=no >&2
  exit 4
fi

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${MODELS_DIR}:${PYTHONPATH:-}"
GUROBI_BUNDLE_ROOT="${GUROBI_BUNDLE_ROOT:-${IMLS_REPO:-/path/to/Research-Project-IMLS}/gurobi}"
if [[ -z "${GUROBI_HOME:-}" ]]; then
  for candidate in "${REPO_DIR}/gurobi/gurobi1103/linux64" "${GUROBI_BUNDLE_ROOT}/gurobi1103/linux64"; do
    if [[ -d "${candidate}" ]]; then export GUROBI_HOME="${candidate}"; break; fi
  done
fi
export GUROBI_VERSION="${GUROBI_VERSION:-110}"
if [[ -z "${GRB_LICENSE_FILE:-}" ]]; then
  for candidate in "${REPO_DIR}/gurobi/gurobi.lic" "${GUROBI_BUNDLE_ROOT}/gurobi.lic"; do
    if [[ -f "${candidate}" ]]; then export GRB_LICENSE_FILE="${candidate}"; break; fi
  done
fi
if [[ -n "${GUROBI_HOME:-}" ]]; then export LD_LIBRARY_PATH="${GUROBI_HOME}/lib:${LD_LIBRARY_PATH:-}"; fi

"${PYTHON_BIN}" -c 'import casadi as ca,sys; print("CasADi/Gurobi:",ca.__version__,ca.has_conic("gurobi")); sys.exit(0 if ca.has_conic("gurobi") else 2)'
"${PYTHON_BIN}" -c 'import carla,sys; c=carla.Client("127.0.0.1",2000); c.set_timeout(10); w=c.get_world(); m=w.get_map().name; actors=[a for a in w.get_actors() if a.type_id.startswith(("vehicle.","sensor."))]; print("CARLA:",m,"experiment actors:",len(actors)); sys.exit(0 if m.endswith("Town05") else 4)'
"${PYTHON_BIN}" -c 'import tensorflow as tf,sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'

# Independently reproduce the strict PCG64 continuation. Existing candidate
# files must be byte-identical or generation fails closed.
"${PYTHON_BIN}" "${MODELS_DIR}/experimental/generate_sf4_supervisor_authority_inits.py" \
  --output-dir "${INIT_SOURCE}" --r3-manifest "${R3_INIT_MANIFEST}" \
  > "${SF4_RESULTS}/sf4_init_generation_revalidation.json"

"${PYTHON_BIN}" "${PREPARE}" validate-sources \
  --scenario "${SCENARIO_SOURCE}" --base-tuning "${BASE_TUNING}" \
  --init-dir "${INIT_SOURCE}" --init-manifest "${INIT_MANIFEST}" \
  --prereg "${PREREG_JSON}" \
  > "${SF4_RESULTS}/sf4_source_validation.json"

SPAWN_PREFLIGHT="${SF4_RESULTS}/sf4_town05_spawn_preflight.json"
if [[ ! -f "${SPAWN_PREFLIGHT}" ]]; then
  if compgen -G "${SF4_RESULTS}/*/SF4_ROLLOUT_*_COMPLETE.json" > /dev/null; then
    echo "Cannot create prospective spawn preflight after SF4 receipts exist" >&2
    exit 4
  fi
  "${PYTHON_BIN}" "${SPAWN_PREFLIGHTER}" \
    --carla-root "${CARLA_ROOT}" --scenario "${SCENARIO_SOURCE}" \
    --tuning "${BASE_TUNING}" --init-dir "${INIT_SOURCE}" \
    --init-manifest "${INIT_MANIFEST}" --output "${SPAWN_PREFLIGHT}"
else
  "${PYTHON_BIN}" - "${SPAWN_PREFLIGHT}" "${SCENARIO_SOURCE}" "${BASE_TUNING}" "${INIT_MANIFEST}" <<'PY'
import hashlib,json,sys
from pathlib import Path
pre,scenario,tuning,manifest=map(Path,sys.argv[1:])
v=json.loads(pre.read_text()); h=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
ok=(v.get("status")=="pass" and v.get("formal_rollouts_launched")==0
 and v.get("treatment_executed") is False and str(v.get("map","")).endswith("Town05")
 and v.get("scenario_sha256")==h(scenario) and v.get("tuning_sha256")==h(tuning)
 and v.get("init_manifest_sha256")==h(manifest)
 and [r.get("ego_init_id") for r in v.get("records",[])]==list(range(106,116))
 and all(r.get("status")=="pass" for r in v.get("records",[])))
raise SystemExit(0 if ok else "Frozen SF4 spawn preflight drift")
PY
fi

DEPLOYMENT_PREFLIGHT="${SF4_RESULTS}/sf4_b1_deployment_preflight.json"
DEPLOYMENT_CANDIDATE="${SF4_RESULTS}/sf4_b1_deployment_preflight.candidate.tmp.json"
"${PYTHON_BIN}" "${MODELS_DIR}/experimental/verify_day9_deployment.py" \
  --day7-results "${DAY7_RESULTS}" --day8-results "${DAY8_RESULTS}" \
  --model "${B1_MODEL}" --calibration "${B1_CALIBRATION}" \
  --anchors "${ANCHORS}" --baseline-model "${B0_MODEL}" \
  --output-json "${DEPLOYMENT_CANDIDATE}"
"${PYTHON_BIN}" - "${DEPLOYMENT_CANDIDATE}" "${DEPLOYMENT_PREFLIGHT}" <<'PY'
import json,os,sys
from pathlib import Path
candidate,output=map(Path,sys.argv[1:]); value=json.loads(candidate.read_text())
def semantic(v):
 return {"status":v.get("status"),"selected_variant":v.get("selected_variant"),"selected_seed":v.get("selected_seed"),"selection_freeze_sha256":v.get("selection_freeze_sha256"),"anchors":v.get("anchors"),"normalization":v.get("normalization"),"warmup_input":v.get("warmup_input"),"b1_deployment":(v.get("b1") or {}).get("deployment")}
if value.get("status")!="pass": raise SystemExit("SF4 B1 deployment preflight failed")
if output.is_file():
 if semantic(json.loads(output.read_text()))!=semantic(value): raise SystemExit("Frozen SF4 B1 deployment semantic drift")
 candidate.unlink()
else: os.replace(candidate,output)
PY

REACTIVE_CONFIG_JSON="$("${PYTHON_BIN}" -c '
import json,sys
p=json.load(open(sys.argv[1]))["reactive_parameters"]
keys=("caution_speed_mps","minimum_speed_mps","activation_distance_m","release_clearance_m","arrival_time_gap_s","closest_approach_time_s","closest_approach_distance_m","release_hold_s")
print(json.dumps({k:p[k] for k in keys},separators=(",",":")))
' "${FROZEN_COLLECTION}")"

CONTRACT="${SF4_RESULTS}/sf4_supervisor_behavioural_authority_run_contract.json"
"${PYTHON_BIN}" "${PREPARE}" prepare \
  --scenario "${SCENARIO_SOURCE}" --base-tuning "${BASE_TUNING}" \
  --init-dir "${INIT_SOURCE}" --init-manifest "${INIT_MANIFEST}" \
  --prereg "${PREREG_JSON}" --prereg-md "${PREREG_MD}" \
  --results-dir "${SF4_RESULTS}" --spawn-preflight "${SPAWN_PREFLIGHT}" \
  --deployment-preflight "${DEPLOYMENT_PREFLIGHT}" --repo "${REPO_DIR}" \
  --b1-model "${B1_MODEL}" --b1-calibration "${B1_CALIBRATION}" \
  --anchors "${ANCHORS}" --max-attempts "${SF4_MAX_ATTEMPTS}" \
  --prediction-protocol-id "${PROTOCOL_ID}" \
  --reactive-config-json "${REACTIVE_CONFIG_JSON}" \
  --execution-source "${SCRIPT_DIR}/experimental/run_sf4_supervisor_behavioural_authority_ablation.sh" \
  --execution-source "${SCRIPT_DIR}/run_all_scenarios.py" \
  --execution-source "${SCRIPT_DIR}/policies/smpc_agent.py" \
  --execution-source "${SCRIPT_DIR}/policies/supervisor_action_filter.py" \
  --execution-source "${SCRIPT_DIR}/scenarios/run_intersection_scenario.py" \
  --execution-source "${MODELS_DIR}/experimental/generate_sf4_supervisor_authority_inits.py" \
  --execution-source "${SPAWN_PREFLIGHTER}" \
  --execution-source "${PREPARE}" \
  --execution-source "${MODELS_DIR}/experimental/verify_day9_deployment.py" \
  --execution-source "${ATTEMPT_MANAGER}" \
  --execution-source "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" \
  --execution-source "${ANALYZER}" \
  --execution-source "${PACKAGER}" \
  --execution-source "${FULL_PACKAGER}" \
  --execution-source "${SMOKE_VALIDATOR}" \
  > "${SF4_RESULTS}/sf4_prepare_report.json"

(
  cd "${REPO_DIR}"
  "${PYTHON_BIN}" -m unittest -v \
    core.scripts.models.tests.test_sf4_supervisor_behavioural_authority \
    core.scripts.models.tests.test_r3_runner_hardening
)

PREFLIGHT_MARKER="${SF4_RESULTS}/SF4_PREFLIGHT_COMPLETE.json"
"${PYTHON_BIN}" - "${CONTRACT}" "${SPAWN_PREFLIGHT}" "${DEPLOYMENT_PREFLIGHT}" \
  "${PREREG_JSON}" "${PREFLIGHT_MARKER}" "${SF4_RESULTS}" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
contract,spawn,deployment,prereg,output,root=map(Path,sys.argv[1:])
h=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
p={"schema_version":"sf4_preflight_complete_v1","status":"pass","formal_rollouts_launched":0,
 "contract_sha256":h(contract),"spawn_preflight_sha256":h(spawn),
 "deployment_preflight_sha256":h(deployment),"preregistration_sha256":h(prereg)}
rendered=json.dumps(p,indent=2,sort_keys=True)+"\n"
if output.is_file():
 if output.read_text()!=rendered: raise SystemExit("Frozen SF4 preflight marker drift")
else:
 if list(root.glob("*/SF4_ROLLOUT_*_COMPLETE.json")): raise SystemExit("Cannot freeze SF4 preflight after outcomes")
 tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(rendered); os.replace(tmp,output)
PY

if ((SF4_PREFLIGHT_ONLY)); then
  echo "[$(date --iso-8601=seconds)] SF4 preflight PASS; no treatment rollout launched"
  "${PYTHON_BIN}" "${PREPARE}" progress --results-dir "${SF4_RESULTS}"
  exit 0
fi

run_smoke_case() {
  local label="$1" policy="$2" mode="$3"
  local smoke_root="${SF4_RESULTS}/_smoke/${label}"
  local tuning="${SF4_RESULTS}/_frozen_tuning/supervisor_authority_${mode}.json"
  local policy_name risk_profile
  local adaptive_arg=()
  case "${policy}" in
    fixed_medium)
      policy_name=smpc_fixed_risk
      risk_profile=fixed_frontier_medium
      ;;
    adaptive)
      policy_name=smpc_var_risk
      risk_profile=adaptive_interaction_severity
      adaptive_arg=(--adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}')
      ;;
    *) echo "Unknown SF4 smoke risk policy: ${policy}" >&2; return 5 ;;
  esac
  mkdir -p "${smoke_root}"
  "${PYTHON_BIN}" "${ATTEMPT_MANAGER}" hygiene --attempt-dir "${smoke_root}" \
    --host 127.0.0.1 --port 2000 --timeout 10
  "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
    --scenario_glob scenario_uk_give_way.json \
    --init_glob "${SMOKE_INIT}" \
    --results_dir "${smoke_root}" --policies "${policy_name}" \
    --risk_profile "${risk_profile}" --tuning_config "${tuning}" \
    --prediction_model_weights "${B1_MODEL}" --prediction_model_anchors "${ANCHORS}" \
    --prediction_model_calibration "${B1_CALIBRATION}" \
    --target_style assertive_constant_speed --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
    --enable_prediction_logging --prediction_logging_stride 1 --prediction_logging_horizon 10 \
    --prediction_dataset_version distinction_sf4_supervisor_authority_smoke_excluded \
    --prediction_protocol_id "${PROTOCOL_ID}_smoke_excluded" \
    --prediction_cell_id "SF4_SMOKE_${label}" \
    --prediction_ego_policy_label "${policy}" \
    --prediction_git_commit "$(git -C "${REPO_DIR}" rev-parse HEAD)" \
    --disable_camera_viz --postprocess_no_plots --skip_completed_subruns \
    "${adaptive_arg[@]}" \
    2>&1 | tee -a "${smoke_root}/smoke_runner.log"
}

SMOKE_MARKER="${SF4_RESULTS}/SF4_SMOKE_COMPLETE.json"
if ((SF4_SMOKE_ONLY)); then
  if compgen -G "${SF4_RESULTS}/SF4_B1_*/SF4_ROLLOUT_*_COMPLETE.json" > /dev/null; then
    echo "SF4 excluded smoke must complete before the first formal receipt" >&2
    exit 4
  fi
  run_smoke_case fixed_on fixed_medium on
  run_smoke_case fixed_off fixed_medium off
  run_smoke_case adaptive_on adaptive on
  run_smoke_case adaptive_off adaptive off
  "${PYTHON_BIN}" "${SMOKE_VALIDATOR}" \
    --results-dir "${SF4_RESULTS}" --contract "${CONTRACT}" \
    --output "${SMOKE_MARKER}"
  echo "[$(date --iso-8601=seconds)] SF4 excluded full-stack smoke PASS; no formal rollout launched"
  exit 0
fi

test -f "${SMOKE_MARKER}" || {
  echo "Missing SF4_SMOKE_COMPLETE.json; run this script once with --smoke-only before formal collection" >&2
  exit 4
}
"${PYTHON_BIN}" - "${SMOKE_MARKER}" "${CONTRACT}" <<'PY'
import hashlib,json,sys
from pathlib import Path
marker,contract=map(Path,sys.argv[1:])
h=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
v=json.loads(marker.read_text())
ok=(v.get("schema_version")=="sf4_supervisor_behavioural_authority_smoke_v1"
 and v.get("status")=="pass" and v.get("formal_rollouts_observed")==0
 and v.get("excluded_init_id")==105 and v.get("excluded_from_80_rollout_analysis") is True
 and v.get("scientific_outcomes_read_or_used_for_tuning") is False
 and v.get("contract_sha256")==h(contract)
 and len(v.get("records",[]))==4
 and {r.get("label") for r in v.get("records",[])}
     == {"fixed_on","fixed_off","adaptive_on","adaptive_off"}
 and all(r.get("status")=="pass" for r in v.get("records",[])))
raise SystemExit(0 if ok else "SF4 excluded smoke marker is missing, stale or invalid")
PY

run_rollout() {
  local cell_id="$1" policy="$2" style="$3" mode="$4" init_id="$5"
  local cell_dir="${SF4_RESULTS}/${cell_id}"
  local tuning="${SF4_RESULTS}/_frozen_tuning/supervisor_authority_${mode}.json"
  local policy_name risk_profile target_style attempt_dir attempt_log prepare_json prepare_status
  local finalize_json finalize_status scenario_status=1 attempt=0 retry_allowed=0
  local adaptive_arg=()
  mkdir -p "${cell_dir}"
  case "${policy}" in
    fixed_medium) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_medium ;;
    adaptive)
      policy_name=smpc_var_risk; risk_profile=adaptive_interaction_severity
      adaptive_arg=(--adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}')
      ;;
    *) echo "Unknown SF4 risk policy: ${policy}" >&2; return 5 ;;
  esac
  if [[ "${style}" == "reactive" ]]; then target_style=defensive_reactive; else target_style=assertive_constant_speed; fi
  while true; do
    prepare_status=0
    prepare_json="$("${PYTHON_BIN}" "${ATTEMPT_MANAGER}" prepare \
      --cell-dir "${cell_dir}" --cell-id "${cell_id}" --init-id "${init_id}" \
      --max-attempts "${SF4_MAX_ATTEMPTS}" --receipt-prefix SF4)" || prepare_status=$?
    echo "${prepare_json}"
    if [[ "${prepare_json}" == *'"status": "complete"'* ]]; then
      echo "[$(date --iso-8601=seconds)] SF4 skip verified ${cell_id}/init${init_id}"
      return 0
    fi
    if ((prepare_status != 0)); then return "${prepare_status}"; fi
    read -r attempt attempt_dir attempt_log < <("${PYTHON_BIN}" -c \
      'import json,sys; p=json.loads(sys.stdin.read()); print(p["attempt"],p["attempt_dir"],p["attempt_log"])' \
      <<<"${prepare_json}")
    echo "[$(date --iso-8601=seconds)] SF4 ${cell_id}/init${init_id} attempt=${attempt}/${SF4_MAX_ATTEMPTS}"
    if (
      set -Eeuo pipefail
      "${PYTHON_BIN}" "${ATTEMPT_MANAGER}" hygiene --attempt-dir "${attempt_dir}" \
        --host 127.0.0.1 --port 2000 --timeout 10
      "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
        --scenario_glob scenario_uk_give_way.json \
        --init_glob "${INIT_SOURCE}/ego_init_${init_id}.json" \
        --results_dir "${attempt_dir}" --policies "${policy_name}" \
        --risk_profile "${risk_profile}" --tuning_config "${tuning}" \
        --prediction_model_weights "${B1_MODEL}" --prediction_model_anchors "${ANCHORS}" \
        --prediction_model_calibration "${B1_CALIBRATION}" \
        --target_style "${target_style}" --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
        --enable_prediction_logging --prediction_logging_stride 1 --prediction_logging_horizon 10 \
        --prediction_dataset_version distinction_sf4_supervisor_behavioural_authority \
        --prediction_protocol_id "${PROTOCOL_ID}" --prediction_cell_id "${cell_id}" \
        --prediction_ego_policy_label "${policy}" \
        --prediction_git_commit "$(git -C "${REPO_DIR}" rev-parse HEAD)" \
        --disable_camera_viz --postprocess_no_plots "${adaptive_arg[@]}"
    ) 2>&1 | tee "${attempt_log}"; then scenario_status=0; else scenario_status=$?; fi
    finalize_status=0
    finalize_json="$("${PYTHON_BIN}" "${ATTEMPT_MANAGER}" finalize \
      --cell-dir "${cell_dir}" --cell-id "${cell_id}" --init-id "${init_id}" \
      --max-attempts "${SF4_MAX_ATTEMPTS}" --receipt-prefix SF4 \
      --attempt-dir "${attempt_dir}" --exit-code "${scenario_status}")" || finalize_status=$?
    echo "${finalize_json}"
    if [[ "${finalize_json}" == *'"status": "accepted"'* ]]; then return 0; fi
    retry_allowed="$("${PYTHON_BIN}" -c 'import json,sys; print(1 if json.loads(sys.stdin.read()).get("retry_allowed") else 0)' <<<"${finalize_json}")"
    if ((finalize_status != 0 || retry_allowed != 1)); then
      echo "SF4 non-retryable execution failure: ${cell_id}/init${init_id}; inspect ${attempt_log}" >&2
      if ((finalize_status != 0)); then return "${finalize_status}"; else return 5; fi
    fi
    if ((attempt >= SF4_MAX_ATTEMPTS)); then return 4; fi
    sleep $((5 * attempt))
  done
}

while IFS=$'\t' read -r cell_id policy style mode init_id; do
  run_rollout "${cell_id}" "${policy}" "${style}" "${mode}" "${init_id}"
done < <("${PYTHON_BIN}" - "${CONTRACT}" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1]))["execution_order"]:
 print(item["cell_id"],item["risk_policy"],item["target_style"],item["supervisor_authority_mode"],item["ego_init_id"],sep="\t")
PY
)

for policy in adaptive fixed_medium; do
  for style in assertive reactive; do
    for mode in on off; do
      cell_id="SF4_B1_${policy}_${style}_supervisor_${mode}"
      cell_dir="${SF4_RESULTS}/${cell_id}"
      if [[ "${policy}" == "adaptive" ]]; then required_policy=smpc_var_risk; else required_policy=smpc_fixed_risk; fi
      gate_status=0
      "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${cell_dir}" \
        --required-policies "${required_policy}" --require-fixed-geometry-yield \
        --footprint-margin-m 0.25 --footprint-margins-m 0.0,0.25,0.35,0.50 \
        --conflict-radius-m 4.0 --clearance-tolerance-s 0.2 || gate_status=$?
      echo "[$(date --iso-8601=seconds)] SF4 scientific outcome gate status=${gate_status} cell=${cell_id}"
      test -s "${cell_dir}/postcarla_trajectory_gate.json" || { echo "Missing SF4 gate artifact" >&2; exit 5; }
      for init_id in $(seq 106 115); do
        "${PYTHON_BIN}" "${ATTEMPT_MANAGER}" verify \
          --cell-dir "${cell_dir}" --cell-id "${cell_id}" --init-id "${init_id}" \
          --max-attempts "${SF4_MAX_ATTEMPTS}" --receipt-prefix SF4
      done
    done
  done
done

"${PYTHON_BIN}" "${ANALYZER}" --results-dir "${SF4_RESULTS}" \
  --contract "${CONTRACT}" --prereg "${PREREG_JSON}" \
  --output-dir "${SF4_RESULTS}/analysis"

FULL_RAW_SNAPSHOT="${SF4_RESULTS}/sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz"
"${PYTHON_BIN}" "${FULL_PACKAGER}" --results-dir "${SF4_RESULTS}" \
  --prereg "${PREREG_JSON}" --output "${FULL_RAW_SNAPSHOT}"
"${PYTHON_BIN}" "${FULL_PACKAGER}" --verify-only --output "${FULL_RAW_SNAPSHOT}"
FULL_RAW_MARKER="${SF4_RESULTS}/SF4_FULL_RAW_SNAPSHOT_COMPLETE.json"

SF4_COMPLETE="${SF4_RESULTS}/SF4_COMPLETE.json"
"${PYTHON_BIN}" - "${CONTRACT}" "${PREREG_JSON}" "${SPAWN_PREFLIGHT}" \
  "${DEPLOYMENT_PREFLIGHT}" "${SF4_RESULTS}/analysis/SF4_ANALYSIS_COMPLETE.json" \
  "${FULL_RAW_SNAPSHOT}" "${FULL_RAW_SNAPSHOT}.json" \
  "${FULL_RAW_SNAPSHOT}.files.json" "${FULL_RAW_MARKER}" "${SF4_COMPLETE}" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
contract,prereg,spawn,deployment,analysis,archive,sidecar,manifest,full_marker,output=map(Path,sys.argv[1:])
h=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
a=json.loads(analysis.read_text())
if a.get("status")!="pass" or a.get("observed_rollouts")!=80 or a.get("independent_init_clusters")!=10:
 raise SystemExit("SF4 formal analysis is incomplete")
if (a.get("implementation_manipulation_gate") or {}).get("status")!="pass":
 raise SystemExit("SF4 behavioural-authority implementation gate failed")
if (a.get("observed_first_stage_activity") or {}).get("status") not in {"active","inactive_scientific_outcome"}:
 raise SystemExit("SF4 first-stage activity result is missing")
m=json.loads(full_marker.read_text()); s=json.loads(sidecar.read_text())
if (m.get("status")!="pass" or m.get("observed_rollouts")!=80
 or m.get("archive_sha256")!=h(archive) or s.get("archive_sha256")!=h(archive)
 or m.get("files_manifest_sha256")!=h(manifest)
 or s.get("files_manifest_sha256")!=h(manifest)
 or m.get("archive_sidecar_sha256")!=h(sidecar)
 or m.get("bbox_and_separation_recomputation_supported") is not True
 or m.get("server_wall_time_recomputation_supported") is not True
 or m.get("controller_acceptance_and_raw_status_recomputation_supported") is not True
 or m.get("receipt_raw_and_attempt_provenance_verified") is not True
 or m.get("source_files_deleted") is not False):
 raise SystemExit("SF4 full raw snapshot is incomplete or hash-drifted")
p={"schema_version":"sf4_supervisor_behavioural_authority_complete_v1","status":"pass","formal_evidence":True,
 "observed_rollouts":80,"independent_init_clusters":10,
 "scientific_direction_never_blocks_completion":True,
 "observed_activity_never_triggers_extra_rollouts":True,
 "primary_estimand":"(adaptive-fixed_medium)_on - (adaptive-fixed_medium)_off",
 "implementation_manipulation_gate":a.get("implementation_manipulation_gate"),
 "observed_first_stage_activity_status":(a.get("observed_first_stage_activity") or {}).get("status"),
 "solver_execution":a.get("solver_execution"),
 "server_wall_time_diagnostics":a.get("server_wall_time_diagnostics"),
 "additional_sf4_carla_rollouts_required":False,
 "contract_sha256":h(contract),"preregistration_sha256":h(prereg),
 "spawn_preflight_sha256":h(spawn),"deployment_preflight_sha256":h(deployment),
 "analysis_complete_sha256":h(analysis),
 "full_raw_snapshot":archive.name,"full_raw_snapshot_sha256":h(archive),
 "full_raw_snapshot_sidecar_sha256":h(sidecar),
 "full_raw_snapshot_files_manifest_sha256":h(manifest),
 "full_raw_snapshot_complete_sha256":h(full_marker),
 "bbox_and_separation_recomputation_supported":True,
 "server_wall_time_recomputation_supported":True,
 "controller_acceptance_and_raw_status_recomputation_supported":True,
 "source_raw_evidence_deleted":False}
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(json.dumps(p,indent=2,sort_keys=True)+"\n"); os.replace(tmp,output)
PY
COMPACT_PACKAGE="${SF4_RESULTS}/sf4_supervisor_behavioural_authority_compact_evidence.tar.gz"
"${PYTHON_BIN}" "${PACKAGER}" --results-dir "${SF4_RESULTS}" --output "${COMPACT_PACKAGE}"
"${PYTHON_BIN}" "${PACKAGER}" --verify-only --output "${COMPACT_PACKAGE}"
echo "[$(date --iso-8601=seconds)] SF4 complete"
cat "${SF4_COMPLETE}"
echo "SF4 full raw snapshot: ${FULL_RAW_SNAPSHOT}"
echo "SF4 compact evidence package: ${COMPACT_PACKAGE}"
