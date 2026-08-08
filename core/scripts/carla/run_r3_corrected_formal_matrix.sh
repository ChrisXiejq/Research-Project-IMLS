#!/usr/bin/env bash
set -Eeuo pipefail

# Prospective corrected R3 matrix:
# B0/B1 x 3 fixed + adaptive x assertive/reactive x 5 new init groups = 80.
# Scientific adverse outcomes are retained; only infrastructure/integrity
# failures stop the final R3 completion gate.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-/root/miniconda3/envs/carla_modern/bin/python}"
DAY7_RESULTS="${DAY7_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1}"
R2_RESULTS="${R2_RESULTS:-/root/autodl-tmp/results/give_way_transformer/distinction_v1/r2_corrected_pilot_v4}"
R3_RESULTS="${R3_RESULTS:-/root/autodl-tmp/results/give_way_transformer/distinction_v1/r3_corrected_formal_v1}"
R3_MAX_ATTEMPTS="${R3_MAX_ATTEMPTS:-3}"
B1_MODEL="${B1_MODEL:-${DAY8_RESULTS}/runs/B1/seed_37/best_model}"
B1_CALIBRATION="${B1_CALIBRATION:-${DAY8_RESULTS}/runs/B1/seed_37/calibration.json}"
B0_MODEL="${B0_MODEL:-${MODELS_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/l5kit_clusters_16.npy}"
TUNING_SOURCE="${TUNING_SOURCE:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json}"
FROZEN_COLLECTION="${FROZEN_COLLECTION:-${REPO_DIR}/docs/paper/generated/day5/day5_final_6b71ccc_frozen_config.json}"
R1_CONTRACT="${R1_CONTRACT:-${REPO_DIR}/docs/paper/generated/distinction_v1/08_corrected_closed_loop/r1/R1_CORRECTED_CONTROL_CONTRACT.json}"
G2_DECISION="${G2_DECISION:-${REPO_DIR}/docs/paper/generated/distinction_v1/08_corrected_closed_loop/g2/G2_ROUTE_DECISION.json}"
M0_CONTRACT="${M0_CONTRACT:-${REPO_DIR}/docs/paper/generated/distinction_v1/09_analysis_contract/M0_R3_ANALYSIS_CONTRACT.json}"
R3_INIT_SOURCE="${R3_INIT_SOURCE:-${SCRIPT_DIR}/scenarios/inits/distinction_r3_new}"

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
if [[ ! "${R3_MAX_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "R3_MAX_ATTEMPTS must be a positive integer, got ${R3_MAX_ATTEMPTS}" >&2
  exit 2
fi
for required in \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" "${DAY7_RESULTS}/train.jsonl" \
  "${DAY8_RESULTS}/DAY8_COMPLETE.json" "${DAY8_RESULTS}/final_test_v1/DAY8_MODEL_SELECTION_FROZEN.json" \
  "${R2_RESULTS}/R2_COMPLETE.json" "${R2_RESULTS}/r2_corrected_pilot_audit.json" \
  "${B1_MODEL}/saved_model.pb" "${B1_CALIBRATION}" "${B0_MODEL}/saved_model.pb" \
  "${ANCHORS}" "${TUNING_SOURCE}" "${FROZEN_COLLECTION}" "${R1_CONTRACT}" \
  "${G2_DECISION}" "${M0_CONTRACT}" "${R3_INIT_SOURCE}/R3_INIT_GENERATION_MANIFEST.json" \
  "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py"; do
  test -e "${required}" || { echo "Missing R3 asset: ${required}" >&2; exit 2; }
done
for init_id in 101 102 103 104 105; do
  test -f "${R3_INIT_SOURCE}/ego_init_${init_id}.json" || exit 2
done

"${PYTHON_BIN}" - "${R2_RESULTS}/R2_COMPLETE.json" "${G2_DECISION}" "${M0_CONTRACT}" <<'PY'
import json,sys
r2,g2,m0=(json.load(open(path)) for path in sys.argv[1:])
if r2.get("status")!="pass": raise SystemExit("R2 is not complete")
if g2.get("status")!="frozen" or g2.get("decision")!="Route_R_corrected_prospective_core": raise SystemExit("G2 does not freeze Route R")
if m0.get("status")!="frozen_before_r3_outcomes": raise SystemExit("M0 was not frozen before R3")
PY

mkdir -p "${R3_RESULTS}"
exec > >(tee -a "${R3_RESULTS}/r3_runner.log") 2>&1
if "${PYTHON_BIN}" - "${R3_RESULTS}/R3_COMPLETE.json" <<'PY'
import json,sys
try: payload=json.load(open(sys.argv[1]))
except Exception: raise SystemExit(1)
raise SystemExit(0 if payload.get("status")=="pass" else 1)
PY
then
  echo "R3 already complete"
  cat "${R3_RESULTS}/R3_COMPLETE.json"
  exit 0
fi

LOCK="${R3_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another R3 runner is active: PID $(cat "${LOCK}/pid")" >&2
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
GUROBI_BUNDLE_ROOT="${GUROBI_BUNDLE_ROOT:-/root/autodl-tmp/Research-Project-IMLS/gurobi}"
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
"${PYTHON_BIN}" -c 'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(10.0); print("CARLA map:",c.get_world().get_map().name)'
"${PYTHON_BIN}" -c 'import tensorflow as tf,sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'

PREFLIGHT="${R3_RESULTS}/r3_deployment_preflight.json"
"${PYTHON_BIN}" "${MODELS_DIR}/verify_day9_deployment.py" \
  --day7-results "${DAY7_RESULTS}" --day8-results "${DAY8_RESULTS}" \
  --model "${B1_MODEL}" --calibration "${B1_CALIBRATION}" \
  --anchors "${ANCHORS}" --baseline-model "${B0_MODEL}" --output-json "${PREFLIGHT}"

TUNING_CONFIG="${R3_RESULTS}/tuning_r3_frozen.json"
if [[ -f "${TUNING_CONFIG}" ]]; then
  cmp --silent "${TUNING_SOURCE}" "${TUNING_CONFIG}" || { echo "Frozen R3 tuning drift" >&2; exit 4; }
else
  cp "${TUNING_SOURCE}" "${TUNING_CONFIG}"
fi

REACTIVE_CONFIG_JSON="$("${PYTHON_BIN}" -c '
import json,sys
p=json.load(open(sys.argv[1]))["reactive_parameters"]
keys=("caution_speed_mps","minimum_speed_mps","activation_distance_m","release_clearance_m","arrival_time_gap_s","closest_approach_time_s","closest_approach_distance_m","release_hold_s")
print(json.dumps({k:p[k] for k in keys},separators=(",",":")))
' "${FROZEN_COLLECTION}")"

INIT_DIR="${R3_RESULTS}/_frozen_inits_101_105"
mkdir -p "${INIT_DIR}"
for init_id in 101 102 103 104 105; do
  ln -sfn "${R3_INIT_SOURCE}/ego_init_${init_id}.json" "${INIT_DIR}/ego_init_${init_id}.json"
done

CONTRACT="${R3_RESULTS}/r3_run_contract.json"
"${PYTHON_BIN}" - "${PREFLIGHT}" "${CONTRACT}" "${TUNING_CONFIG}" "${REACTIVE_CONFIG_JSON}" \
  "${INIT_DIR}" "${REPO_DIR}" "${R1_CONTRACT}" "${R2_RESULTS}/R2_COMPLETE.json" \
  "${G2_DECISION}" "${M0_CONTRACT}" "${R3_INIT_SOURCE}/R3_INIT_GENERATION_MANIFEST.json" <<'PY'
import hashlib,json,os,random,subprocess,sys
from pathlib import Path
preflight_path,output,tuning_path=map(Path,sys.argv[1:4]); reactive=json.loads(sys.argv[4])
init_dir,repo,r1,r2,g2,m0,init_manifest=map(Path,sys.argv[5:12])
pre=json.loads(preflight_path.read_text())
if pre.get("status")!="pass": raise SystemExit("R3 deployment preflight failed")
def h(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def semantic(value):
 return {"status":value.get("status"),"selected_variant":value.get("selected_variant"),"selected_seed":value.get("selected_seed"),"selection_freeze_sha256":value.get("selection_freeze_sha256"),"anchors":value.get("anchors"),"normalization":value.get("normalization"),"warmup_input":value.get("warmup_input"),"b1_deployment":(value.get("b1") or {}).get("deployment"),"b0_deployment":(value.get("b0") or {}).get("deployment")}
def semantic_hash(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
cells=[]
for predictor in ("B1","B0"):
 for policy in ("fixed_aggressive","fixed_medium","fixed_conservative","adaptive"):
  for style in ("assertive","reactive"):
   cells.append({"cell_id":f"{predictor}_{policy}_{style}","predictor":predictor,"risk_policy":policy,"target_style":style})
rng=random.Random(20260808); order=[]
for init_id in (101,102,103,104,105):
 block=[dict(cell,ego_init_id=init_id) for cell in cells]; rng.shuffle(block); order.extend(block)
payload={
 "schema_version":"r3_corrected_formal_contract_v1","status":"frozen","stage":"R3","formal_evidence":True,
 "result_generation":"distinction_corrected_v1","implementation_version":"corrected_joint_modes_shared_amin_v1",
 "research_comparison":"B1_vs_B0_predictor_stack_x_fixed_frontier_vs_adaptive_x_target_style",
 "ego_init_ids":[101,102,103,104,105],"expected_rollouts":80,"cells":cells,
 "execution_order_seed":20260808,"execution_order_method":"complete treatment block shuffled independently within each init","execution_order":order,
 "target_offset_m":0.0,"target_speed_mps":9.0,"authority_regime":"A3_risk_owned_yield","shared_A_MIN_mps2":-3.0,"n_modes":3,
 "risk_policies":["fixed_aggressive","fixed_medium","fixed_conservative","adaptive"],
 "adaptive_parameters":{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78},
 "reactive_parameters":reactive,"runtime_gate":{"max_p95_solve_time_s":0.5,"max_scenario_iters":600},
 "transient_retry_policy":{"max_attempts":int(os.environ.get("R3_MAX_ATTEMPTS","3")),"backoff_seconds":"5 * failed_attempt_index","completed_rollouts_never_repeated":True,"scientific_outcomes_never_retried_or_excluded":True},
 "predictors":{"B1":{"seed":37,"model_sha256_tree":pre["b1"]["deployment"]["model_artifact"]["sha256_tree"],"calibration_sha256":pre["b1"]["deployment"]["calibration_artifact"]["sha256"],"calibration_parameters":pre["b1"]["deployment"]["calibration_parameters"]},"B0":{"model_sha256_tree":pre["b0"]["deployment"]["model_artifact"]["sha256_tree"],"calibration":"identity_no_calibration_artifact"}},
 "anchors_sha256":pre["anchors"]["sha256"],"init_sha256":{str(i):h(init_dir/f"ego_init_{i}.json") for i in range(101,106)},
 "init_generation_manifest_sha256":h(init_manifest),"tuning_sha256":h(tuning_path),"preflight_semantic_sha256":semantic_hash(semantic(pre)),
 "r1_contract_sha256":h(r1),"r2_complete_sha256":h(r2),"g2_decision_sha256":h(g2),"m0_analysis_contract_sha256":h(m0),
 "frozen_source_files":{"tuning":{"scope":"results","path":"tuning_r3_frozen.json","sha256":h(tuning_path)}},
 "prediction_protocol_id":"r3_corrected_formal_v1","git_commit":subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip(),
 "analysis_unit":"ego_init_cluster","fixed_geometry_metric_required":True,"pilot_rollouts_excluded":True,"legacy_corrected_pooling_prohibited":True,"no_post_result_tuning":True,
}
rendered=json.dumps(payload,indent=2,sort_keys=True)+"\n"
if output.exists() and output.read_text()!=rendered: raise SystemExit(f"Frozen R3 contract drift: {output}")
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(rendered); os.replace(tmp,output)
PY

rollout_is_complete() {
  "${PYTHON_BIN}" - "$1" <<'PY'
import json,sys
try: payload=json.load(open(sys.argv[1]))
except Exception: raise SystemExit(1)
raise SystemExit(0 if payload.get("status")=="pass" else 1)
PY
}

run_rollout() {
  local predictor="$1" policy="$2" style="$3" init_id="$4"
  local cell_id="${predictor}_${policy}_${style}" cell_dir="${R3_RESULTS}/${cell_id}"
  local receipt="${cell_dir}/R3_ROLLOUT_${init_id}_COMPLETE.json"
  local model policy_name risk_profile target_style attempt scenario_status=1
  local calibration_arg=() adaptive_arg=()
  mkdir -p "${cell_dir}"
  if rollout_is_complete "${receipt}"; then
    echo "[$(date --iso-8601=seconds)] R3 skip completed ${cell_id}/init${init_id}"
    return
  fi
  if [[ "${predictor}" == "B1" ]]; then model="${B1_MODEL}"; calibration_arg=(--prediction_model_calibration "${B1_CALIBRATION}"); else model="${B0_MODEL}"; fi
  case "${policy}" in
    fixed_aggressive) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_aggressive ;;
    fixed_medium) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_medium ;;
    fixed_conservative) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_conservative ;;
    adaptive) policy_name=smpc_var_risk; risk_profile=adaptive_interaction_severity; adaptive_arg=(--adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}') ;;
    *) echo "Unknown risk policy: ${policy}" >&2; exit 5 ;;
  esac
  if [[ "${style}" == "reactive" ]]; then target_style=defensive_reactive; else target_style=assertive_constant_speed; fi
  for ((attempt=1; attempt<=R3_MAX_ATTEMPTS; attempt++)); do
    echo "[$(date --iso-8601=seconds)] R3 ${cell_id}/init${init_id} attempt=${attempt}/${R3_MAX_ATTEMPTS}"
    if "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
      --scenario_glob scenario_uk_give_way.json --init_glob "${INIT_DIR}/ego_init_${init_id}.json" \
      --results_dir "${cell_dir}" --policies "${policy_name}" --risk_profile "${risk_profile}" \
      --tuning_config "${TUNING_CONFIG}" --prediction_model_weights "${model}" --prediction_model_anchors "${ANCHORS}" \
      "${calibration_arg[@]}" --target_style "${target_style}" --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
      --enable_prediction_logging --prediction_logging_stride 1 --prediction_logging_horizon 10 \
      --prediction_protocol_id r3_corrected_formal_v1 --prediction_cell_id "${cell_id}" \
      --prediction_ego_policy_label "${policy}" --prediction_git_commit "$(git -C "${REPO_DIR}" rev-parse HEAD)" \
      --disable_camera_viz --skip_completed_subruns --postprocess_no_plots "${adaptive_arg[@]}"; then
      scenario_status=0; break
    else
      scenario_status=$?
    fi
    if (( attempt < R3_MAX_ATTEMPTS )); then echo "[$(date --iso-8601=seconds)] transient failure; retry after $((5 * attempt))s"; sleep $((5 * attempt)); fi
  done
  if (( scenario_status != 0 )); then echo "R3 infrastructure failure after ${R3_MAX_ATTEMPTS} attempts: ${cell_id}/init${init_id}" >&2; return "${scenario_status}"; fi
  "${PYTHON_BIN}" - "${cell_id}" "${init_id}" "${cell_dir}" "${receipt}" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
cell_id,init_id,cell_dir,output=sys.argv[1],int(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4])
summaries=list(cell_dir.glob(f"scenario_*_ego_init_{init_id}_*/scenario_run_summary.json"))
if len(summaries)!=1 or json.loads(summaries[0].read_text()).get("ran_successfully") is not True: raise SystemExit("R3 rollout scenario incomplete")
p={"schema_version":"r3_rollout_complete_v1","status":"pass","cell_id":cell_id,"ego_init_id":init_id,"scenario_summary":str(summaries[0]),"scenario_summary_sha256":hashlib.sha256(summaries[0].read_bytes()).hexdigest()}
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(json.dumps(p,indent=2,sort_keys=True)+"\n"); os.replace(tmp,output)
PY
}

while IFS=$'\t' read -r predictor policy style init_id; do
  run_rollout "${predictor}" "${policy}" "${style}" "${init_id}"
done < <("${PYTHON_BIN}" - "${CONTRACT}" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1]))["execution_order"]: print(item["predictor"],item["risk_policy"],item["target_style"],item["ego_init_id"],sep="\t")
PY
)

for predictor in B1 B0; do
  for policy in fixed_aggressive fixed_medium fixed_conservative adaptive; do
    for style in assertive reactive; do
      cell_dir="${R3_RESULTS}/${predictor}_${policy}_${style}"
      if [[ "${policy}" == adaptive ]]; then required_policy=smpc_var_risk; else required_policy=smpc_fixed_risk; fi
      gate_status=0
      "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${cell_dir}" \
        --required-policies "${required_policy}" --require-fixed-geometry-yield || gate_status=$?
      echo "[$(date --iso-8601=seconds)] R3 scientific outcome gate status=${gate_status} cell=$(basename "${cell_dir}")"
      "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" --results_dir "${cell_dir}" --compute_metrics
      "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${cell_dir}"
    done
  done
done

AUDIT="${R3_RESULTS}/r3_corrected_matrix_audit.json"
"${PYTHON_BIN}" "${MODELS_DIR}/audit_r3_corrected_matrix.py" --results-dir "${R3_RESULTS}" --contract-json "${CONTRACT}" --output-json "${AUDIT}"
"${PYTHON_BIN}" - "${AUDIT}" "${PREFLIGHT}" "${R3_RESULTS}/R3_COMPLETE.json" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
audit_path,preflight_path,output=map(Path,sys.argv[1:]); audit=json.loads(audit_path.read_text()); pre=json.loads(preflight_path.read_text())
if audit.get("status")!="pass" or audit.get("observed_rollouts")!=80 or audit.get("passing_integrity_rollouts")!=80 or pre.get("status")!="pass": raise SystemExit("R3 integrity completion gate failed")
p={"schema_version":"r3_complete_v1","status":"pass","stage":"R3","formal_evidence":True,"result_generation":"distinction_corrected_v1","implementation_version":"corrected_joint_modes_shared_amin_v1","observed_rollouts":80,"unique_treatment_keys":80,"scientific_outcome_taxonomy":audit["scientific_outcome_taxonomy"],"deployment_preflight_sha256":hashlib.sha256(preflight_path.read_bytes()).hexdigest(),"matrix_audit_sha256":hashlib.sha256(audit_path.read_bytes()).hexdigest()}
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(json.dumps(p,indent=2,sort_keys=True)+"\n"); os.replace(tmp,output)
PY
"${PYTHON_BIN}" "${MODELS_DIR}/package_closed_loop_snapshot.py" --results-dir "${R3_RESULTS}" \
  --contract r3_run_contract.json --audit r3_corrected_matrix_audit.json --complete R3_COMPLETE.json \
  --output "${R3_RESULTS}/r3_corrected_formal_snapshot.tar.gz"
echo "[$(date --iso-8601=seconds)] R3 complete"
cat "${R3_RESULTS}/R3_COMPLETE.json"
