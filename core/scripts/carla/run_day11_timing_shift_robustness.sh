#!/usr/bin/env bash
set -Eeuo pipefail

# Day 11: local robustness extension of Day 10, not a new model-selection stage.
# B1/B0 x fixed-medium/adaptive x assertive/reactive x target offset {-3,+3} m x init46--50.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-/root/miniconda3/envs/carla_modern/bin/python}"
DAY7_RESULTS="${DAY7_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1}"
DAY9_RESULTS="${DAY9_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day9/day9_smoke_v1}"
DAY10_RESULTS="${DAY10_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day10/day10_formal_v1}"
DAY11_RESULTS="${DAY11_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day11/day11_timing_shift_v1}"
B1_MODEL="${B1_MODEL:-${DAY8_RESULTS}/runs/B1/seed_37/best_model}"
B1_CALIBRATION="${B1_CALIBRATION:-${DAY8_RESULTS}/runs/B1/seed_37/calibration.json}"
B0_MODEL="${B0_MODEL:-${MODELS_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/l5kit_clusters_16.npy}"
TUNING_SOURCE="${TUNING_SOURCE:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json}"
FROZEN_COLLECTION="${FROZEN_COLLECTION:-${REPO_DIR}/docs/paper/generated/day5/day5_final_6b71ccc_frozen_config.json}"

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
for required in \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" "${DAY8_RESULTS}/DAY8_COMPLETE.json" \
  "${DAY9_RESULTS}/DAY9_COMPLETE.json" "${DAY10_RESULTS}/DAY10_COMPLETE.json" \
  "${DAY10_RESULTS}/day10_run_contract.json" "${B1_MODEL}/saved_model.pb" \
  "${B1_CALIBRATION}" "${B0_MODEL}/saved_model.pb" "${ANCHORS}" \
  "${TUNING_SOURCE}" "${FROZEN_COLLECTION}" \
  "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py"; do
  test -e "${required}" || { echo "Missing Day 11 asset: ${required}" >&2; exit 2; }
done
for init_id in 46 47 48 49 50; do
  test -f "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${init_id}.json" || exit 2
done

mkdir -p "${DAY11_RESULTS}"
exec > >(tee -a "${DAY11_RESULTS}/day11_runner.log") 2>&1
if "${PYTHON_BIN}" - "${DAY11_RESULTS}/DAY11_COMPLETE.json" <<'PY'
import json,sys
try: p=json.load(open(sys.argv[1]))
except Exception: raise SystemExit(1)
raise SystemExit(0 if p.get("status")=="pass" else 1)
PY
then
  echo "Day 11 already complete"; cat "${DAY11_RESULTS}/DAY11_COMPLETE.json"; exit 0
fi

LOCK="${DAY11_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another Day 11 runner is active: PID $(cat "${LOCK}/pid")" >&2; exit 3
  fi
  rm -f "${LOCK}/pid"; rmdir "${LOCK}"; mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() { rm -f "${LOCK}/pid"; rmdir "${LOCK}" 2>/dev/null || true; }
trap cleanup EXIT

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${MODELS_DIR}:${PYTHONPATH:-}"
if [[ -z "${GUROBI_HOME:-}" && -d "${REPO_DIR}/gurobi/gurobi1103/linux64" ]]; then export GUROBI_HOME="${REPO_DIR}/gurobi/gurobi1103/linux64"; fi
export GUROBI_VERSION="${GUROBI_VERSION:-110}"
if [[ -z "${GRB_LICENSE_FILE:-}" && -f "${REPO_DIR}/gurobi/gurobi.lic" ]]; then export GRB_LICENSE_FILE="${REPO_DIR}/gurobi/gurobi.lic"; fi
if [[ -n "${GUROBI_HOME:-}" ]]; then export LD_LIBRARY_PATH="${GUROBI_HOME}/lib:${LD_LIBRARY_PATH:-}"; fi

"${PYTHON_BIN}" -c 'import casadi as ca,sys; print("CasADi/Gurobi:",ca.__version__,ca.has_conic("gurobi")); sys.exit(0 if ca.has_conic("gurobi") else 2)'
"${PYTHON_BIN}" -c 'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(10.0); print("CARLA map:",c.get_world().get_map().name)'
"${PYTHON_BIN}" -c 'import tensorflow as tf,sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'

PREFLIGHT="${DAY11_RESULTS}/day11_deployment_preflight.json"
"${PYTHON_BIN}" "${MODELS_DIR}/verify_day9_deployment.py" \
  --day7-results "${DAY7_RESULTS}" --day8-results "${DAY8_RESULTS}" \
  --model "${B1_MODEL}" --calibration "${B1_CALIBRATION}" --anchors "${ANCHORS}" \
  --baseline-model "${B0_MODEL}" --output-json "${PREFLIGHT}"

REACTIVE_CONFIG_JSON="$("${PYTHON_BIN}" -c '
import json,sys
p=json.load(open(sys.argv[1]))["reactive_parameters"]
keys=("caution_speed_mps","minimum_speed_mps","activation_distance_m","release_clearance_m","arrival_time_gap_s","closest_approach_time_s","closest_approach_distance_m","release_hold_s")
print(json.dumps({k:p[k] for k in keys},separators=(",",":")))
' "${FROZEN_COLLECTION}")"

INIT_DIR="${DAY11_RESULTS}/_heldout_inits_46_50"; mkdir -p "${INIT_DIR}"
for init_id in 46 47 48 49 50; do
  ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${init_id}.json" "${INIT_DIR}/ego_init_${init_id}.json"
done

mkdir -p "${DAY11_RESULTS}/tuning_configs"
for spec in "m3:-3.0" "p3:3.0"; do
  label="${spec%%:*}"; offset="${spec#*:}"; output="${DAY11_RESULTS}/tuning_configs/offset_${label}.json"
  "${PYTHON_BIN}" - "${TUNING_SOURCE}" "${output}" "${offset}" <<'PY'
import json,os,sys
from pathlib import Path
source,output,offset=Path(sys.argv[1]),Path(sys.argv[2]),float(sys.argv[3])
p=json.loads(source.read_text()); p["config_name"]=f"day11_timing_shift_offset_{offset:+.1f}m"
p["description"]="Day 11 frozen timing-shift robustness config; only target longitudinal start offset differs from Day 10."
target=p.setdefault("vehicle_role_overrides",{}).setdefault("target",{})
target["start_longitudinal_offset"]=offset; target["nominal_speed"]=9.0; target["init_speed"]=9.0
rendered=json.dumps(p,indent=2,sort_keys=True)+"\n"
if output.exists() and output.read_text()!=rendered: raise SystemExit(f"Frozen tuning drift: {output}")
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(rendered); os.replace(tmp,output)
PY
done

CONTRACT="${DAY11_RESULTS}/day11_run_contract.json"
"${PYTHON_BIN}" - "${PREFLIGHT}" "${CONTRACT}" "${REACTIVE_CONFIG_JSON}" "${DAY10_RESULTS}/day10_run_contract.json" "${INIT_DIR}" "${DAY11_RESULTS}" "${REPO_DIR}" <<'PY'
import hashlib,json,os,subprocess,sys
from pathlib import Path
preflight_path,output,day10_contract,init_dir,root,repo=map(Path,[sys.argv[1],sys.argv[2],sys.argv[4],sys.argv[5],sys.argv[6],sys.argv[7]])
reactive=json.loads(sys.argv[3]); pre=json.loads(preflight_path.read_text()); day10=json.loads(day10_contract.read_text())
if day10.get("status")!="frozen" or not day10.get("no_post_result_tuning"): raise SystemExit("Invalid Day 10 provenance")
def tree_semantics(p):
 return {"status":p.get("status"),"selected_variant":p.get("selected_variant"),"selected_seed":p.get("selected_seed"),"selection_freeze_sha256":p.get("selection_freeze_sha256"),"anchors":p.get("anchors"),"normalization":p.get("normalization"),"warmup_input":p.get("warmup_input"),"b1_deployment":(p.get("b1") or {}).get("deployment"),"b1_numerical_status":((p.get("b1") or {}).get("numerical_smoke") or {}).get("status"),"b1_numerical_checks":((p.get("b1") or {}).get("numerical_smoke") or {}).get("checks"),"b0_deployment":(p.get("b0") or {}).get("deployment"),"b0_numerical_status":((p.get("b0") or {}).get("numerical_smoke") or {}).get("status"),"b0_numerical_checks":((p.get("b0") or {}).get("numerical_smoke") or {}).get("checks")}
def h(path): return hashlib.sha256(path.read_bytes()).hexdigest()
cells=[]
for predictor in ("B1","B0"):
 for policy in ("fixed_medium","adaptive"):
  for style in ("assertive","reactive"):
   for label,offset in (("m3",-3.0),("p3",3.0)):
    cells.append({"cell_id":f"{predictor}_{policy}_{style}_offset_{label}","predictor":predictor,"risk_policy":policy,"target_style":style,"offset_label":label,"target_offset_m":offset})
payload={"schema_version":"day11_timing_shift_contract_v1","status":"frozen","formal_evidence":True,
 "research_comparison":"Day10 local timing-shift robustness: B1/B0 x fixed-medium/adaptive x style x target offset",
 "ego_init_ids":list(range(46,51)),"target_speed_mps":9.0,"target_offsets_m":[-3.0,3.0],
 "authority_regime":"A3_risk_owned_yield","expected_rollouts":80,"cells":cells,
 "predictors":{"B1":{"seed":37,"model_sha256_tree":pre["b1"]["deployment"]["model_artifact"]["sha256_tree"],"calibration_sha256":pre["b1"]["deployment"]["calibration_artifact"]["sha256"],"calibration_parameters":pre["b1"]["deployment"]["calibration_parameters"]},"B0":{"model_sha256_tree":pre["b0"]["deployment"]["model_artifact"]["sha256_tree"],"calibration":"identity_no_calibration_artifact"}},
 "anchors_sha256":pre["anchors"]["sha256"],"normalization":day10["normalization"],"risk_policies":["fixed_medium","adaptive"],
 "adaptive_parameters":day10["adaptive_parameters"],"reactive_parameters":reactive,
 "init_sha256":{str(i):h(init_dir/f"ego_init_{i}.json") for i in range(46,51)},
 "tuning_sha256_by_offset":{label:{"path":f"tuning_configs/offset_{label}.json","sha256":h(root/f"tuning_configs/offset_{label}.json")} for label in ("m3","p3")},
 "preflight_semantic_sha256":hashlib.sha256(json.dumps(tree_semantics(pre),sort_keys=True,separators=(",",":")).encode()).hexdigest(),
 "day10_contract_sha256":h(day10_contract),"git_commit":subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip(),
 "execution_git_commits":[subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip()],
 "analysis_unit":"paired rollout condition (ego_init_id,target_style,target_offset_m)",
 "primary_factors":["predictor","risk_policy","target_style","target_offset_m"],
 "prediction_protocol_id":"day11_a3_timing_shift_closed_loop_v1","audit_schema_version":"day11_closed_loop_audit_v1",
 "deployment_preflight_filename":"day11_deployment_preflight.json",
 "pre_registered_primary_contrasts":["B1_minus_B0 within each policy pooled over offsets/styles","adaptive_minus_fixed_medium within each predictor pooled over offsets/styles","predictor_x_offset and policy_x_offset interactions"],
 "no_post_result_tuning":True,"test_used_for_model_selection":False}
if output.exists():
 old=json.loads(output.read_text())
 old_compare={k:v for k,v in old.items() if k not in ("git_commit","execution_git_commits")}
 new_compare={k:v for k,v in payload.items() if k not in ("git_commit","execution_git_commits")}
 if old_compare!=new_compare: raise SystemExit(f"Day 11 contract semantic drift: {output}")
 old_git=old.get("git_commit"); new_git=payload["git_commit"]
 if old_git!=new_git:
  if list(root.glob("**/scenario_run_summary.json")): raise SystemExit("Cannot migrate Day 11 contract after rollout execution began")
  ancestor=subprocess.run(["git","-C",str(repo),"merge-base","--is-ancestor",old_git,new_git]).returncode==0
  if not ancestor: raise SystemExit("Day 11 repair commit is not a fast-forward descendant")
  changed=subprocess.check_output(["git","-C",str(repo),"diff","--name-only",old_git,new_git],text=True).splitlines()
  allowed={"core/scripts/carla/run_day11_timing_shift_robustness.sh","core/scripts/models/audit_day10_closed_loop.py","core/scripts/models/package_closed_loop_snapshot.py"}
  disallowed=[path for path in changed if path not in allowed and not path.startswith("docs/")]
  if disallowed: raise SystemExit(f"Unsafe pre-rollout Day 11 migration changed runtime files: {disallowed}")
  payload["execution_git_commits"]=list(dict.fromkeys((old.get("execution_git_commits") or [old_git])+[new_git]))
  provenance={"schema_version":"day11_contract_pre_rollout_repair_v1","status":"pass","reason":"fix same-command local variable expansion before first rollout","old_git_commit":old_git,"new_git_commit":new_git,"changed_files":changed,"rollouts_preserved":0,"allowed_execution_git_commits":payload["execution_git_commits"]}
  prov=root/"day11_contract_resume_provenance.json"; tmp=prov.with_suffix(prov.suffix+".tmp"); tmp.write_text(json.dumps(provenance,indent=2,sort_keys=True)+"\n"); os.replace(tmp,prov)
rendered=json.dumps(payload,indent=2,sort_keys=True)+"\n"
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(rendered); os.replace(tmp,output)
PY

postprocess_cell() {
  local cell_dir="$1" required_policy="$2"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${cell_dir}" --required-policies "${required_policy}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" --results_dir "${cell_dir}" --compute_metrics
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${cell_dir}"
}

run_cell() {
  local predictor="$1" policy="$2" style="$3" label="$4" offset="$5"
  local cell_id="${predictor}_${policy}_${style}_offset_${label}"
  local cell_dir="${DAY11_RESULTS}/${cell_id}"
  local model policy_name risk_profile target_style tuning="${DAY11_RESULTS}/tuning_configs/offset_${label}.json"
  local calibration_arg=() adaptive_arg=()
  if [[ "${predictor}" == "B1" ]]; then model="${B1_MODEL}"; calibration_arg=(--prediction_model_calibration "${B1_CALIBRATION}"); else model="${B0_MODEL}"; fi
  if [[ "${policy}" == "fixed_medium" ]]; then policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_medium; else
    policy_name=smpc_var_risk; risk_profile=adaptive_interaction_severity
    adaptive_arg=(--adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}')
  fi
  if [[ "${style}" == "reactive" ]]; then target_style=defensive_reactive; else target_style=assertive_constant_speed; fi
  mkdir -p "${cell_dir}"; echo "[$(date --iso-8601=seconds)] Day11 cell=${cell_id} offset=${offset}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
    --scenario_glob scenario_uk_give_way.json --init_glob "${INIT_DIR}/ego_init_*.json" \
    --results_dir "${cell_dir}" --policies "${policy_name}" --risk_profile "${risk_profile}" \
    --tuning_config "${tuning}" --prediction_model_weights "${model}" --prediction_model_anchors "${ANCHORS}" \
    "${calibration_arg[@]}" --target_style "${target_style}" --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
    --enable_prediction_logging --prediction_logging_stride 1 --prediction_logging_horizon 10 \
    --prediction_protocol_id day11_a3_timing_shift_closed_loop_v1 --prediction_cell_id "${cell_id}" \
    --prediction_ego_policy_label "${policy}" --prediction_git_commit "$(git -C "${REPO_DIR}" rev-parse HEAD)" \
    --disable_camera_viz --skip_completed_subruns --postprocess_no_plots "${adaptive_arg[@]}"
  postprocess_cell "${cell_dir}" "${policy_name}"
}

for predictor in B1 B0; do
  for policy in fixed_medium adaptive; do
    for style in assertive reactive; do
      run_cell "${predictor}" "${policy}" "${style}" m3 -3.0
      run_cell "${predictor}" "${policy}" "${style}" p3 3.0
    done
  done
done

AUDIT="${DAY11_RESULTS}/day11_closed_loop_audit.json"
"${PYTHON_BIN}" "${MODELS_DIR}/audit_day10_closed_loop.py" --results-dir "${DAY11_RESULTS}" --contract-json "${CONTRACT}" --output-json "${AUDIT}"
"${PYTHON_BIN}" - "${AUDIT}" "${PREFLIGHT}" "${DAY11_RESULTS}/DAY11_COMPLETE.json" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
audit_path,preflight_path,output=map(Path,sys.argv[1:]); audit=json.loads(audit_path.read_text()); pre=json.loads(preflight_path.read_text())
if audit.get("status")!="pass" or pre.get("status")!="pass" or audit.get("observed_rollouts")!=80: raise SystemExit("Day 11 completion gate failed")
p={"schema_version":"day11_complete_v1","status":"pass","formal_evidence":True,"observed_cells":audit["observed_cells"],"observed_rollouts":audit["observed_rollouts"],"deployment_preflight_sha256":hashlib.sha256(preflight_path.read_bytes()).hexdigest(),"closed_loop_audit_sha256":hashlib.sha256(audit_path.read_bytes()).hexdigest()}
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(json.dumps(p,indent=2,sort_keys=True)+"\n"); os.replace(tmp,output)
PY
"${PYTHON_BIN}" "${MODELS_DIR}/analyze_day11_timing_shift.py" \
  --results-dir "${DAY11_RESULTS}" --output-dir "${DAY11_RESULTS}/analysis"
"${PYTHON_BIN}" "${MODELS_DIR}/package_closed_loop_snapshot.py" --results-dir "${DAY11_RESULTS}" --contract day11_run_contract.json --audit day11_closed_loop_audit.json --complete DAY11_COMPLETE.json --output "${DAY11_RESULTS}/day11_timing_shift_snapshot.tar.gz"
echo "[$(date --iso-8601=seconds)] Day 11 complete"; cat "${DAY11_RESULTS}/DAY11_COMPLETE.json"
