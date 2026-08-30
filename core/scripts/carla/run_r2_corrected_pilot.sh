#!/usr/bin/env bash
set -Eeuo pipefail

# R2 is a non-statistical, resumable 10-rollout deployment gate for the R1
# corrected control implementation.  It never contributes effect estimates.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
DAY7_RESULTS="${DAY7_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day8/day8_validation_v1}"
R2_RESULTS="${R2_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/distinction_v1/r2_corrected_pilot_v1}"
R2_MAX_ATTEMPTS="${R2_MAX_ATTEMPTS:-3}"
B1_MODEL="${B1_MODEL:-${DAY8_RESULTS}/runs/B1/seed_37/best_model}"
B1_CALIBRATION="${B1_CALIBRATION:-${DAY8_RESULTS}/runs/B1/seed_37/calibration.json}"
B0_MODEL="${B0_MODEL:-${MODELS_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/l5kit_clusters_16.npy}"
TUNING_SOURCE="${TUNING_SOURCE:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json}"
FROZEN_COLLECTION="${FROZEN_COLLECTION:-${REPO_DIR}/docs/paper/generated/day5/day5_final_6b71ccc_frozen_config.json}"
R1_CONTRACT="${R1_CONTRACT:-${REPO_DIR}/docs/paper/generated/distinction_v1/08_corrected_closed_loop/r1/R1_CORRECTED_CONTROL_CONTRACT.json}"

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
if [[ ! "${R2_MAX_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "R2_MAX_ATTEMPTS must be a positive integer, got ${R2_MAX_ATTEMPTS}" >&2
  exit 2
fi
for required in \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" "${DAY7_RESULTS}/train.jsonl" \
  "${DAY8_RESULTS}/DAY8_COMPLETE.json" "${DAY8_RESULTS}/final_test_v1/DAY8_MODEL_SELECTION_FROZEN.json" \
  "${B1_MODEL}/saved_model.pb" "${B1_CALIBRATION}" "${B0_MODEL}/saved_model.pb" \
  "${ANCHORS}" "${TUNING_SOURCE}" "${FROZEN_COLLECTION}" "${R1_CONTRACT}" \
  "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_45.json" \
  "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_50.json" \
  "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py"; do
  test -e "${required}" || { echo "Missing R2 asset: ${required}" >&2; exit 2; }
done

mkdir -p "${R2_RESULTS}"
exec > >(tee -a "${R2_RESULTS}/r2_runner.log") 2>&1
if "${PYTHON_BIN}" - "${R2_RESULTS}/R2_COMPLETE.json" <<'PY'
import json,sys
try: payload=json.load(open(sys.argv[1]))
except Exception: raise SystemExit(1)
raise SystemExit(0 if payload.get("status")=="pass" else 1)
PY
then
  echo "R2 already complete"
  cat "${R2_RESULTS}/R2_COMPLETE.json"
  exit 0
fi

LOCK="${R2_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another R2 runner is active: PID $(cat "${LOCK}/pid")" >&2
    exit 3
  fi
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}"
  mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() { rm -f "${LOCK}/pid"; rmdir "${LOCK}" 2>/dev/null || true; }
trap cleanup EXIT

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${MODELS_DIR}:${PYTHONPATH:-}"
GUROBI_BUNDLE_ROOT="${GUROBI_BUNDLE_ROOT:-${IMLS_REPO:-/path/to/Research-Project-IMLS}/gurobi}"
if [[ -z "${GUROBI_HOME:-}" ]]; then
  for candidate in "${REPO_DIR}/gurobi/gurobi1103/linux64" "${GUROBI_BUNDLE_ROOT}/gurobi1103/linux64"; do
    if [[ -d "${candidate}" ]]; then
      export GUROBI_HOME="${candidate}"
      break
    fi
  done
fi
export GUROBI_VERSION="${GUROBI_VERSION:-110}"
if [[ -z "${GRB_LICENSE_FILE:-}" ]]; then
  for candidate in "${REPO_DIR}/gurobi/gurobi.lic" "${GUROBI_BUNDLE_ROOT}/gurobi.lic"; do
    if [[ -f "${candidate}" ]]; then
      export GRB_LICENSE_FILE="${candidate}"
      break
    fi
  done
fi
if [[ -n "${GUROBI_HOME:-}" ]]; then
  export LD_LIBRARY_PATH="${GUROBI_HOME}/lib:${LD_LIBRARY_PATH:-}"
fi

"${PYTHON_BIN}" -c 'import casadi as ca,sys; print("CasADi/Gurobi:",ca.__version__,ca.has_conic("gurobi")); sys.exit(0 if ca.has_conic("gurobi") else 2)'
"${PYTHON_BIN}" -c 'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(10.0); print("CARLA map:",c.get_world().get_map().name)'
"${PYTHON_BIN}" -c 'import tensorflow as tf,sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'

PREFLIGHT="${R2_RESULTS}/r2_deployment_preflight.json"
"${PYTHON_BIN}" "${MODELS_DIR}/verify_day9_deployment.py" \
  --day7-results "${DAY7_RESULTS}" --day8-results "${DAY8_RESULTS}" \
  --model "${B1_MODEL}" --calibration "${B1_CALIBRATION}" \
  --anchors "${ANCHORS}" --baseline-model "${B0_MODEL}" --output-json "${PREFLIGHT}"

REACTIVE_CONFIG_JSON="$("${PYTHON_BIN}" -c '
import json,sys
p=json.load(open(sys.argv[1]))["reactive_parameters"]
keys=("caution_speed_mps","minimum_speed_mps","activation_distance_m","release_clearance_m","arrival_time_gap_s","closest_approach_time_s","closest_approach_distance_m","release_hold_s")
print(json.dumps({k:p[k] for k in keys},separators=(",",":")))
' "${FROZEN_COLLECTION}")"

INIT_DIR="${R2_RESULTS}/_inits"
mkdir -p "${INIT_DIR}"
ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_45.json" "${INIT_DIR}/ego_init_45.json"
ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_50.json" "${INIT_DIR}/ego_init_50.json"

TUNING_DIR="${R2_RESULTS}/tuning_configs"
mkdir -p "${TUNING_DIR}"
for spec in "dev_offset_0:0.0" "probe_offset_m3:-3.0"; do
  label="${spec%%:*}"
  offset="${spec#*:}"
  output="${TUNING_DIR}/${label}.json"
  "${PYTHON_BIN}" - "${TUNING_SOURCE}" "${output}" "${label}" "${offset}" <<'PY'
import json,os,sys
from pathlib import Path
source,output=map(Path,sys.argv[1:3]); label=sys.argv[3]; offset=float(sys.argv[4])
p=json.loads(source.read_text())
p["config_name"]=f"r2_corrected_pilot_{label}"
p["description"]="R2 corrected-v1 non-statistical deployment pilot; frozen before rollout outcomes."
roles=p.setdefault("vehicle_role_overrides",{})
roles.setdefault("ego",{})["control_implementation_version"]="corrected_joint_modes_shared_amin_v1"
target=roles.setdefault("target",{})
target["start_longitudinal_offset"]=offset; target["nominal_speed"]=9.0; target["init_speed"]=9.0
rendered=json.dumps(p,indent=2,sort_keys=True)+"\n"
if output.exists() and output.read_text()!=rendered: raise SystemExit(f"Frozen R2 tuning drift: {output}")
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(rendered); os.replace(tmp,output)
PY
done

CONTRACT="${R2_RESULTS}/r2_run_contract.json"
"${PYTHON_BIN}" - "${PREFLIGHT}" "${R1_CONTRACT}" "${CONTRACT}" "${REACTIVE_CONFIG_JSON}" "${INIT_DIR}" "${TUNING_DIR}" "${REPO_DIR}" <<'PY'
import hashlib,json,os,subprocess,sys
from pathlib import Path
preflight_path,r1_path,output,init_dir,tuning_dir,repo=map(Path,[sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[5],sys.argv[6],sys.argv[7]])
reactive=json.loads(sys.argv[4]); pre=json.loads(preflight_path.read_text()); r1=json.loads(r1_path.read_text())
if pre.get("status")!="pass" or r1.get("status")!="pass": raise SystemExit("R1/preflight gate failed")
def h(path): return hashlib.sha256(path.read_bytes()).hexdigest()
cells=[]
for predictor in ("B1","B0"):
 for policy in ("fixed_medium","adaptive"):
  for style in ("assertive","reactive"):
   cells.append({"cell_id":f"dev_{predictor}_{policy}_{style}_init45","predictor":predictor,"risk_policy":policy,"target_style":style,"ego_init_id":45,"target_offset_m":0.0,"tuning_path":"tuning_configs/dev_offset_0.json","tuning_sha256":h(tuning_dir/"dev_offset_0.json"),"probe":False})
for predictor in ("B1","B0"):
 cells.append({"cell_id":f"probe_{predictor}_adaptive_reactive_offset_m3_init50","predictor":predictor,"risk_policy":"adaptive","target_style":"reactive","ego_init_id":50,"target_offset_m":-3.0,"tuning_path":"tuning_configs/probe_offset_m3.json","tuning_sha256":h(tuning_dir/"probe_offset_m3.json"),"probe":True})
payload={"schema_version":"r2_corrected_pilot_contract_v1","status":"frozen","stage":"R2","non_statistical_pilot":True,"formal_evidence":False,"implementation_version":"corrected_joint_modes_shared_amin_v1","result_generation":"distinction_corrected_v1","expected_rollouts":10,"cells":cells,"authority_regime":"A3_risk_owned_yield","target_speed_mps":9.0,"n_modes":3,"shared_A_MIN_mps2":-3.0,"runtime_gate":{"max_p95_solve_time_s":0.5,"max_scenario_iters":600},"transient_retry_policy":{"max_attempts":int(os.environ.get("R2_MAX_ATTEMPTS","3")),"backoff_seconds":"5 * failed_attempt_index","completed_rollouts_never_repeated":True,"scientific_failures_not_accepted":True},"predictors":{"B1":{"seed":37,"model_sha256_tree":pre["b1"]["deployment"]["model_artifact"]["sha256_tree"],"calibration_sha256":pre["b1"]["deployment"]["calibration_artifact"]["sha256"],"calibration_parameters":pre["b1"]["deployment"]["calibration_parameters"]},"B0":{"model_sha256_tree":pre["b0"]["deployment"]["model_artifact"]["sha256_tree"],"calibration":"identity_no_calibration_artifact"}},"anchors_sha256":pre["anchors"]["sha256"],"reactive_parameters":reactive,"init_sha256":{"45":h(init_dir/"ego_init_45.json"),"50":h(init_dir/"ego_init_50.json")},"preflight_sha256":h(preflight_path),"r1_contract_sha256":h(r1_path),"r1_source_sha256":r1["source_sha256"],"git_commit":subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip(),"no_post_result_tuning":True}
rendered=json.dumps(payload,indent=2,sort_keys=True)+"\n"
if output.exists() and output.read_text()!=rendered: raise SystemExit(f"Frozen R2 contract drift: {output}")
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(rendered); os.replace(tmp,output)
PY

postprocess_cell() {
  local cell_dir="$1" required_policy="$2"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${cell_dir}" --required-policies "${required_policy}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" --results_dir "${cell_dir}" --compute_metrics
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${cell_dir}"
}

cell_is_complete() {
  "${PYTHON_BIN}" - "$1/R2_CELL_COMPLETE.json" <<'PY'
import json,sys
try: payload=json.load(open(sys.argv[1]))
except Exception: raise SystemExit(1)
raise SystemExit(0 if payload.get("status")=="pass" else 1)
PY
}

run_cell() {
  local cell_id="$1" predictor="$2" policy="$3" style="$4" init_id="$5" tuning_label="$6"
  local cell_dir="${R2_RESULTS}/${cell_id}"
  local model policy_name risk_profile target_style tuning="${TUNING_DIR}/${tuning_label}.json"
  local calibration_arg=() adaptive_arg=()
  mkdir -p "${cell_dir}"
  if cell_is_complete "${cell_dir}"; then
    echo "[$(date --iso-8601=seconds)] R2 skip completed cell=${cell_id}"
    return
  fi
  if [[ "${predictor}" == "B1" ]]; then
    model="${B1_MODEL}"; calibration_arg=(--prediction_model_calibration "${B1_CALIBRATION}")
  else
    model="${B0_MODEL}"
  fi
  if [[ "${policy}" == "fixed_medium" ]]; then
    policy_name="smpc_fixed_risk"; risk_profile="fixed_frontier_medium"
  else
    policy_name="smpc_var_risk"; risk_profile="adaptive_interaction_severity"
    adaptive_arg=(--adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}')
  fi
  if [[ "${style}" == "reactive" ]]; then target_style="defensive_reactive"; else target_style="assertive_constant_speed"; fi
  local attempt scenario_status=1
  for ((attempt=1; attempt<=R2_MAX_ATTEMPTS; attempt++)); do
    echo "[$(date --iso-8601=seconds)] R2 cell=${cell_id} attempt=${attempt}/${R2_MAX_ATTEMPTS}"
    if "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
      --scenario_glob scenario_uk_give_way.json \
      --init_glob "${INIT_DIR}/ego_init_${init_id}.json" \
      --results_dir "${cell_dir}" --policies "${policy_name}" --risk_profile "${risk_profile}" \
      --tuning_config "${tuning}" --prediction_model_weights "${model}" \
      --prediction_model_anchors "${ANCHORS}" "${calibration_arg[@]}" \
      --target_style "${target_style}" --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
      --enable_prediction_logging --prediction_logging_stride 1 --prediction_logging_horizon 10 \
      --prediction_protocol_id r2_corrected_pilot_v1 --prediction_cell_id "${cell_id}" \
      --prediction_ego_policy_label "${policy}" --prediction_git_commit "$(git -C "${REPO_DIR}" rev-parse HEAD)" \
      --disable_camera_viz --skip_completed_subruns --postprocess_no_plots "${adaptive_arg[@]}"; then
      scenario_status=0
      break
    else
      scenario_status=$?
    fi
    if (( attempt < R2_MAX_ATTEMPTS )); then
      echo "[$(date --iso-8601=seconds)] transient cell failure; retrying after $((5 * attempt))s"
      sleep $((5 * attempt))
    fi
  done
  if (( scenario_status != 0 )); then
    echo "R2 cell failed after ${R2_MAX_ATTEMPTS} attempts: ${cell_id}" >&2
    return "${scenario_status}"
  fi
  postprocess_cell "${cell_dir}" "${policy_name}"
  "${PYTHON_BIN}" - "${cell_id}" "${cell_dir}" "${tuning}" "${policy_name}" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
cell_id,cell_dir,tuning,policy=sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4]
summaries=list(cell_dir.glob("**/scenario_run_summary.json"))
if len(summaries)!=1 or json.loads(summaries[0].read_text()).get("ran_successfully") is not True: raise SystemExit("R2 cell scenario incomplete")
gate=json.loads((cell_dir/"postcarla_trajectory_gate.json").read_text())
if gate.get("overall_status")!="PASS": raise SystemExit("R2 cell post-CARLA gate failed")
p={"schema_version":"r2_cell_complete_v1","status":"pass","cell_id":cell_id,"required_policy":policy,"scenario_summary":str(summaries[0]),"scenario_summary_sha256":hashlib.sha256(summaries[0].read_bytes()).hexdigest(),"tuning_sha256":hashlib.sha256(tuning.read_bytes()).hexdigest()}
out=cell_dir/"R2_CELL_COMPLETE.json"; tmp=out.with_suffix(out.suffix+".tmp"); tmp.write_text(json.dumps(p,indent=2,sort_keys=True)+"\n"); os.replace(tmp,out)
PY
}

for predictor in B1 B0; do
  for policy in fixed_medium adaptive; do
    for style in assertive reactive; do
      run_cell "dev_${predictor}_${policy}_${style}_init45" "${predictor}" "${policy}" "${style}" 45 dev_offset_0
    done
  done
done
for predictor in B1 B0; do
  run_cell "probe_${predictor}_adaptive_reactive_offset_m3_init50" "${predictor}" adaptive reactive 50 probe_offset_m3
done

AUDIT="${R2_RESULTS}/r2_corrected_pilot_audit.json"
"${PYTHON_BIN}" "${MODELS_DIR}/audit_r2_corrected_pilot.py" \
  --results-dir "${R2_RESULTS}" --contract-json "${CONTRACT}" --output-json "${AUDIT}"
"${PYTHON_BIN}" - "${AUDIT}" "${PREFLIGHT}" "${R2_RESULTS}/R2_COMPLETE.json" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
audit_path,preflight_path,output=map(Path,sys.argv[1:]); audit=json.loads(audit_path.read_text()); pre=json.loads(preflight_path.read_text())
if audit.get("status")!="pass" or audit.get("observed_rollouts")!=10 or audit.get("passing_rollouts")!=10 or pre.get("status")!="pass": raise SystemExit("R2 completion gate failed")
p={"schema_version":"r2_complete_v1","status":"pass","stage":"R2","non_statistical_pilot":True,"formal_evidence":False,"implementation_version":"corrected_joint_modes_shared_amin_v1","observed_rollouts":10,"passing_rollouts":10,"native_collisions":audit["total_native_collisions"],"valid_prediction_steps":audit["total_valid_prediction_steps"],"deployment_preflight_sha256":hashlib.sha256(preflight_path.read_bytes()).hexdigest(),"pilot_audit_sha256":hashlib.sha256(audit_path.read_bytes()).hexdigest()}
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(json.dumps(p,indent=2,sort_keys=True)+"\n"); os.replace(tmp,output)
PY
"${PYTHON_BIN}" "${MODELS_DIR}/package_closed_loop_snapshot.py" \
  --results-dir "${R2_RESULTS}" --contract r2_run_contract.json \
  --audit r2_corrected_pilot_audit.json --complete R2_COMPLETE.json \
  --output "${R2_RESULTS}/r2_corrected_pilot_snapshot.tar.gz"
echo "[$(date --iso-8601=seconds)] R2 complete"
cat "${R2_RESULTS}/R2_COMPLETE.json"
