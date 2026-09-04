#!/usr/bin/env bash
set -Eeuo pipefail

# Frozen Day 10 formal matrix:
# B1 fine-tuned vs B0 pretrained × fixed frontier/adaptive ×
# assertive/reactive × held-out init46--50 = 80 rollouts.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
DAY7_RESULTS="${DAY7_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day8/day8_validation_v1}"
DAY9_RESULTS="${DAY9_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day9/day9_smoke_v1}"
DAY10_RESULTS="${DAY10_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day10/day10_formal_v1}"
B1_MODEL="${B1_MODEL:-${DAY8_RESULTS}/runs/B1/seed_37/best_model}"
B1_CALIBRATION="${B1_CALIBRATION:-${DAY8_RESULTS}/runs/B1/seed_37/calibration.json}"
B0_MODEL="${B0_MODEL:-${MODELS_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/assets/l5kit_clusters_16.npy}"
TUNING_SOURCE="${TUNING_SOURCE:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json}"
FROZEN_COLLECTION="${FROZEN_COLLECTION:-${REPO_DIR}/docs/paper/generated/day5/day5_final_6b71ccc_frozen_config.json}"

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
for required in \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" \
  "${DAY7_RESULTS}/train.jsonl" \
  "${DAY8_RESULTS}/DAY8_COMPLETE.json" \
  "${DAY8_RESULTS}/final_test_v1/DAY8_MODEL_SELECTION_FROZEN.json" \
  "${DAY9_RESULTS}/DAY9_COMPLETE.json" \
  "${B1_MODEL}/saved_model.pb" \
  "${B1_CALIBRATION}" \
  "${B0_MODEL}/saved_model.pb" \
  "${ANCHORS}" \
  "${TUNING_SOURCE}" \
  "${FROZEN_COLLECTION}" \
  "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py"; do
  test -e "${required}" || { echo "Missing required Day 10 asset: ${required}" >&2; exit 2; }
done
for init_id in 46 47 48 49 50; do
  test -f "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${init_id}.json" || exit 2
done

mkdir -p "${DAY10_RESULTS}"
exec > >(tee -a "${DAY10_RESULTS}/day10_runner.log") 2>&1
if "${PYTHON_BIN}" - "${DAY10_RESULTS}/DAY10_COMPLETE.json" <<'PY'
import json, sys
try:
    payload=json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if payload.get("status") == "pass" else 1)
PY
then
  echo "Day 10 already completed"
  cat "${DAY10_RESULTS}/DAY10_COMPLETE.json"
  exit 0
fi

LOCK="${DAY10_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another Day 10 runner is active: PID $(cat "${LOCK}/pid")" >&2
    exit 3
  fi
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}"
  mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() {
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}" 2>/dev/null || true
}
trap cleanup EXIT

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${MODELS_DIR}:${PYTHONPATH:-}"
if [[ -z "${GUROBI_HOME:-}" && -d "${REPO_DIR}/gurobi/gurobi1103/linux64" ]]; then
  export GUROBI_HOME="${REPO_DIR}/gurobi/gurobi1103/linux64"
fi
export GUROBI_VERSION="${GUROBI_VERSION:-110}"
if [[ -z "${GRB_LICENSE_FILE:-}" && -f "${REPO_DIR}/gurobi/gurobi.lic" ]]; then
  export GRB_LICENSE_FILE="${REPO_DIR}/gurobi/gurobi.lic"
fi
if [[ -n "${GUROBI_HOME:-}" ]]; then
  export LD_LIBRARY_PATH="${GUROBI_HOME}/lib:${LD_LIBRARY_PATH:-}"
fi

"${PYTHON_BIN}" -c 'import casadi as ca,sys; print("CasADi/Gurobi:",ca.__version__,ca.has_conic("gurobi")); sys.exit(0 if ca.has_conic("gurobi") else 2)'
"${PYTHON_BIN}" -c 'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(10.0); print("CARLA map:",c.get_world().get_map().name)'
"${PYTHON_BIN}" -c 'import tensorflow as tf,sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'

PREFLIGHT="${DAY10_RESULTS}/day10_deployment_preflight.json"
"${PYTHON_BIN}" "${MODELS_DIR}/experimental/verify_day9_deployment.py" \
  --day7-results "${DAY7_RESULTS}" \
  --day8-results "${DAY8_RESULTS}" \
  --model "${B1_MODEL}" \
  --calibration "${B1_CALIBRATION}" \
  --anchors "${ANCHORS}" \
  --baseline-model "${B0_MODEL}" \
  --output-json "${PREFLIGHT}"

TUNING_CONFIG="${DAY10_RESULTS}/tuning_day10_frozen.json"
if [[ -f "${TUNING_CONFIG}" ]]; then
  cmp --silent "${TUNING_SOURCE}" "${TUNING_CONFIG}" || {
    echo "Frozen Day 10 tuning config drift" >&2
    exit 4
  }
else
  cp "${TUNING_SOURCE}" "${TUNING_CONFIG}"
fi

REACTIVE_CONFIG_JSON="$("${PYTHON_BIN}" -c '
import json,sys
frozen=json.load(open(sys.argv[1]))["reactive_parameters"]
keys=("caution_speed_mps","minimum_speed_mps","activation_distance_m","release_clearance_m","arrival_time_gap_s","closest_approach_time_s","closest_approach_distance_m","release_hold_s")
print(json.dumps({key:frozen[key] for key in keys},separators=(",",":")))
' "${FROZEN_COLLECTION}")"

INIT_DIR="${DAY10_RESULTS}/_heldout_inits_46_50"
mkdir -p "${INIT_DIR}"
for init_id in 46 47 48 49 50; do
  ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${init_id}.json" \
    "${INIT_DIR}/ego_init_${init_id}.json"
done

CONTRACT="${DAY10_RESULTS}/day10_run_contract.json"
"${PYTHON_BIN}" - \
  "${PREFLIGHT}" "${CONTRACT}" "${TUNING_CONFIG}" "${REACTIVE_CONFIG_JSON}" \
  "${DAY9_RESULTS}/DAY9_COMPLETE.json" "${INIT_DIR}" "${REPO_DIR}" <<'PY'
import hashlib,json,os,subprocess,sys
from pathlib import Path
preflight_path,output,tuning_path,day9_complete,init_dir,repo_dir=map(Path,[sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[5],sys.argv[6],sys.argv[7]])
reactive=json.loads(sys.argv[4]); preflight=json.loads(preflight_path.read_text())
if json.loads(day9_complete.read_text()).get("status") != "pass": raise SystemExit("Day 9 is not complete")
def preflight_semantics(value):
    return {
      "status":value.get("status"),"selected_variant":value.get("selected_variant"),"selected_seed":value.get("selected_seed"),
      "selection_freeze_sha256":value.get("selection_freeze_sha256"),"anchors":value.get("anchors"),
      "normalization":value.get("normalization"),"warmup_input":value.get("warmup_input"),
      "b1_deployment":(value.get("b1") or {}).get("deployment"),
      "b1_numerical_status":((value.get("b1") or {}).get("numerical_smoke") or {}).get("status"),
      "b1_numerical_checks":((value.get("b1") or {}).get("numerical_smoke") or {}).get("checks"),
      "b0_deployment":(value.get("b0") or {}).get("deployment"),
      "b0_numerical_status":((value.get("b0") or {}).get("numerical_smoke") or {}).get("status"),
      "b0_numerical_checks":((value.get("b0") or {}).get("numerical_smoke") or {}).get("checks"),
    }
def semantic_sha256(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def atomic_json(path,value):
    temporary=path.with_suffix(path.suffix+".tmp"); temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n"); os.replace(temporary,path)
current_git=subprocess.check_output(["git","-C",str(repo_dir),"rev-parse","HEAD"],text=True).strip()
cells=[]
for predictor in ("B1","B0"):
    for policy in ("fixed_aggressive","fixed_medium","fixed_conservative","adaptive"):
        for style in ("assertive","reactive"):
            cells.append({"cell_id":f"{predictor}_{policy}_{style}","predictor":predictor,"risk_policy":policy,"target_style":style})
init_hashes={str(i):hashlib.sha256((init_dir/f"ego_init_{i}.json").read_bytes()).hexdigest() for i in range(46,51)}
payload={
 "schema_version":"day10_formal_closed_loop_contract_v2","status":"frozen","formal_evidence":True,
 "research_comparison":"B1_finetuned_vs_B0_pretrained_x_fixed_frontier_vs_adaptive_x_target_style",
 "ego_init_ids":list(range(46,51)),"target_offset_m":0.0,"target_speed_mps":9.0,
 "authority_regime":"A3_risk_owned_yield","expected_rollouts":80,"cells":cells,
 "predictors":{
  "B1":{"seed":37,"model_sha256_tree":preflight["b1"]["deployment"]["model_artifact"]["sha256_tree"],"calibration_sha256":preflight["b1"]["deployment"]["calibration_artifact"]["sha256"],"calibration_parameters":preflight["b1"]["deployment"]["calibration_parameters"]},
  "B0":{"model_sha256_tree":preflight["b0"]["deployment"]["model_artifact"]["sha256_tree"],"calibration":"identity_no_calibration_artifact"}},
 "anchors_sha256":preflight["anchors"]["sha256"],
 "normalization":{"interaction":"not_applicable_for_two_input_B1","past_states_local":"no explicit normalization","raster":"tensorflow.keras.applications.resnet.preprocess_input"},
 "risk_policies":["fixed_aggressive","fixed_medium","fixed_conservative","adaptive"],
 "adaptive_parameters":{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78},
 "reactive_parameters":reactive,"init_sha256":init_hashes,
 "tuning_sha256":hashlib.sha256(tuning_path.read_bytes()).hexdigest(),
 "preflight_semantic_sha256":semantic_sha256(preflight_semantics(preflight)),
 "day9_complete_sha256":hashlib.sha256(day9_complete.read_bytes()).hexdigest(),
 "git_commit":current_git,"execution_git_commits":[current_git],
 "analysis_unit":"paired rollout condition (ego_init_id,target_style)",
 "primary_factors":["predictor","risk_policy","target_style"],
 "no_post_result_tuning":True,
}
if output.exists():
    existing=json.loads(output.read_text())
    if existing.get("schema_version")=="day10_formal_closed_loop_contract_v2":
        payload["execution_git_commits"]=existing.get("execution_git_commits") or [existing.get("git_commit")]
        if existing != payload: raise SystemExit(f"Day 10 contract drift: {output}")
    elif existing.get("schema_version")=="day10_formal_closed_loop_contract_v1":
        ignored={"schema_version","preflight_sha256","git_commit"}
        drift=[key for key,value in existing.items() if key not in ignored and payload.get(key)!=value]
        if drift: raise SystemExit(f"Day 10 legacy contract semantic drift keys: {drift}")
        old_git=existing.get("git_commit")
        if not old_git: raise SystemExit("Day 10 legacy contract has no git commit")
        ancestor=subprocess.run(["git","-C",str(repo_dir),"merge-base","--is-ancestor",old_git,current_git]).returncode==0
        if not ancestor: raise SystemExit("Day 10 contract migration is not a fast-forward descendant")
        changed=subprocess.check_output(
          ["git","-C",str(repo_dir),"-c","core.quotepath=false","diff","--name-only",old_git,current_git],
          text=True,
        ).splitlines()
        allowed_exact={
          "core/scripts/carla/experimental/run_day10_formal_closed_loop.sh",
          "core/scripts/models/experimental/audit_day10_closed_loop.py",
          "core/scripts/models/experimental/package_day10_snapshot.py",
          "core/scripts/models/tests/test_day10_closed_loop_audit.py",
        }
        disallowed=[path for path in changed if path not in allowed_exact and not path.startswith("docs/")]
        if disallowed: raise SystemExit(f"Unsafe Day 10 contract migration changed runtime files: {disallowed}")
        payload["execution_git_commits"]=list(dict.fromkeys([old_git,current_git]))
        provenance={
          "schema_version":"day10_contract_resume_provenance_v1","status":"pass",
          "reason":"replace nondeterministic full preflight hash with stable deployment semantics",
          "old_contract_schema":existing.get("schema_version"),"new_contract_schema":payload["schema_version"],
          "old_git_commit":old_git,"new_git_commit":current_git,
          "allowed_execution_git_commits":payload["execution_git_commits"],"changed_files":changed,
          "old_preflight_observed_sha256":existing.get("preflight_sha256"),
          "new_preflight_observed_sha256":hashlib.sha256(preflight_path.read_bytes()).hexdigest(),
          "preflight_semantic_sha256":payload["preflight_semantic_sha256"],
          "raw_rollouts_preserved":True,
        }
        atomic_json(output.parent/"day10_contract_resume_provenance.json",provenance)
    else:
        raise SystemExit(f"Unsupported Day 10 contract schema: {existing.get('schema_version')}")
atomic_json(output,payload)
PY

postprocess_cell() {
  local cell_dir="$1"
  local required_policy="$2"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" \
    "${cell_dir}" --required-policies "${required_policy}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" \
    --results_dir "${cell_dir}" --compute_metrics
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${cell_dir}"
}

run_cell() {
  local predictor="$1" policy="$2" style="$3"
  local cell_id="${predictor}_${policy}_${style}"
  local cell_dir="${DAY10_RESULTS}/${cell_id}"
  local model policy_name risk_profile target_style
  local calibration_arg=() adaptive_arg=()
  if [[ "${predictor}" == "B1" ]]; then
    model="${B1_MODEL}"
    calibration_arg=(--prediction_model_calibration "${B1_CALIBRATION}")
  else
    model="${B0_MODEL}"
  fi
  case "${policy}" in
    fixed_aggressive) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_aggressive ;;
    fixed_medium) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_medium ;;
    fixed_conservative) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_conservative ;;
    adaptive)
      policy_name=smpc_var_risk; risk_profile=adaptive_interaction_severity
      adaptive_arg=(--adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}')
      ;;
    *) echo "Unknown risk policy: ${policy}" >&2; exit 5 ;;
  esac
  if [[ "${style}" == "reactive" ]]; then target_style=defensive_reactive; else target_style=assertive_constant_speed; fi
  mkdir -p "${cell_dir}"
  echo "[$(date --iso-8601=seconds)] Day10 cell=${cell_id}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
    --scenario_glob scenario_uk_give_way.json \
    --init_glob "${INIT_DIR}/ego_init_*.json" \
    --results_dir "${cell_dir}" \
    --policies "${policy_name}" \
    --risk_profile "${risk_profile}" \
    --tuning_config "${TUNING_CONFIG}" \
    --prediction_model_weights "${model}" \
    --prediction_model_anchors "${ANCHORS}" \
    "${calibration_arg[@]}" \
    --target_style "${target_style}" \
    --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
    --enable_prediction_logging \
    --prediction_logging_stride 1 \
    --prediction_logging_horizon 10 \
    --prediction_protocol_id day10_a3_heldout_closed_loop_v1 \
    --prediction_cell_id "${cell_id}" \
    --prediction_ego_policy_label "${policy}" \
    --prediction_git_commit "$(git -C "${REPO_DIR}" rev-parse HEAD)" \
    --disable_camera_viz \
    --skip_completed_subruns \
    --postprocess_no_plots \
    "${adaptive_arg[@]}"
  postprocess_cell "${cell_dir}" "${policy_name}"
}

for predictor in B1 B0; do
  for policy in fixed_aggressive fixed_medium fixed_conservative adaptive; do
    for style in assertive reactive; do
      run_cell "${predictor}" "${policy}" "${style}"
    done
  done
done

AUDIT="${DAY10_RESULTS}/day10_closed_loop_audit.json"
"${PYTHON_BIN}" "${MODELS_DIR}/experimental/audit_day10_closed_loop.py" \
  --results-dir "${DAY10_RESULTS}" \
  --contract-json "${CONTRACT}" \
  --output-json "${AUDIT}"

"${PYTHON_BIN}" - "${AUDIT}" "${PREFLIGHT}" "${DAY10_RESULTS}/DAY10_COMPLETE.json" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
audit_path,preflight_path,output=map(Path,sys.argv[1:])
audit=json.loads(audit_path.read_text()); preflight=json.loads(preflight_path.read_text())
if audit.get("status")!="pass" or preflight.get("status")!="pass" or audit.get("observed_rollouts")!=80:
    raise SystemExit("Day 10 completion gate failed")
payload={"schema_version":"day10_complete_v1","status":"pass","formal_evidence":True,"predictors":["B1","B0"],"selected_seed":37,"observed_cells":audit["observed_cells"],"observed_rollouts":audit["observed_rollouts"],"deployment_preflight_sha256":hashlib.sha256(preflight_path.read_bytes()).hexdigest(),"closed_loop_audit_sha256":hashlib.sha256(audit_path.read_bytes()).hexdigest()}
temporary=output.with_suffix(output.suffix+".tmp"); temporary.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n"); os.replace(temporary,output)
PY

"${PYTHON_BIN}" "${MODELS_DIR}/experimental/package_day10_snapshot.py" \
  --results-dir "${DAY10_RESULTS}" \
  --output "${DAY10_RESULTS}/day10_formal_snapshot.tar.gz"

echo "[$(date --iso-8601=seconds)] Day 10 complete"
cat "${DAY10_RESULTS}/DAY10_COMPLETE.json"
