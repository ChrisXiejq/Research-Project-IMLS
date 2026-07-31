import os
import sys
import glob
import json
import argparse
import time
import traceback
import subprocess
from datetime import datetime

from utils import experiment_logging as exp_log

script_root = os.path.abspath(__file__).split("carla")[0]
if script_root not in sys.path:
    sys.path.append(script_root)
from experiment_tuning import apply_tuning_config, load_scenario_with_tuning, tuning_snapshot_payload



def _prepare_drone_viz_params(scenario_dict, enable_camera_viz=True):
    drone_viz_dict = dict(scenario_dict["drone_viz_params"])
    if not enable_camera_viz:
        # Headless AutoDL runs are more stable without RGB camera sensors.
        drone_viz_dict["visualize_opencv"] = False
        drone_viz_dict["save_avi"] = False
    return drone_viz_dict


def _policy_output_name(policy_name):
    return policy_name


def _current_git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _write_fine_tune_config_snapshot(savedir: str, scenario_dict: dict) -> None:
    os.makedirs(savedir, exist_ok=True)
    exp_log.write_json(
        os.path.join(savedir, "fine_tune_config.json"),
        tuning_snapshot_payload(scenario_dict),
    )


def _write_scenario_rollout_config(savedir: str, scenario_dict: dict) -> None:
    """Snapshot carla + top-down viz params next to ``scenario_result.pkl`` for reproducible rendering."""
    default_viz = {
        "road_half_width_m": 4.0,
        "dash_len_m": 4.0,
        "dash_gap_m": 3.5,
        "road_arm_extend_m": 14.0,
    }
    user_viz = scenario_dict.get("viz_topdown") or {}
    merged_viz = {**default_viz}
    for k in ("road_half_width_m", "dash_len_m", "dash_gap_m", "road_arm_extend_m"):
        if k in user_viz:
            merged_viz[k] = float(user_viz[k])
    exp_log.write_json(
        os.path.join(savedir, "scenario_rollout_config.json"),
        {
            "scenario_description": scenario_dict.get("scenario_description", {}),
            "carla_params": scenario_dict.get("carla_params", {}),
            "prediction_params": scenario_dict.get("prediction_params", {}),
            "viz_topdown": merged_viz,
            "vehicle_params": scenario_dict.get("vehicle_params", []),
            "fine_tune_config": tuning_snapshot_payload(scenario_dict),
        },
    )


def _savedir_completed_successfully(savedir: str) -> bool:
    """Return True only for a completed rollout that is safe to skip on resume."""
    pkl_path = os.path.join(savedir, "scenario_result.pkl")
    summary_path = os.path.join(savedir, "scenario_run_summary.json")
    if not (os.path.isfile(pkl_path) and os.path.isfile(summary_path)):
        return False
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except Exception:
        return False
    return bool(summary.get("ran_successfully", False))


def _prepare_prediction_params(scenario_dict, args=None, dataset_metadata=None):
    pred_dict = dict(scenario_dict.get("prediction_params", {}))
    traffic_control = (
        scenario_dict.get("carla_params", {}).get("traffic_control")
        or scenario_dict.get("scenario_description", {}).get("traffic_control", "")
    )
    traffic_control_norm = str(traffic_control).lower().strip()
    if traffic_control_norm.startswith("signalised"):
        pred_dict.setdefault("render_traffic_lights", True)
    if args is not None:
        if getattr(args, "prediction_model_weights", None):
            pred_dict["model_weights"] = args.prediction_model_weights
        if getattr(args, "prediction_model_anchors", None):
            pred_dict["model_anchors"] = args.prediction_model_anchors
        if getattr(args, "enable_prediction_logging", False):
            pred_dict["prediction_logging_enabled"] = True
        if getattr(args, "prediction_logging_stride", None) is not None:
            pred_dict["prediction_logging_stride"] = int(args.prediction_logging_stride)
        if getattr(args, "prediction_logging_horizon", None) is not None:
            pred_dict["prediction_logging_horizon"] = int(args.prediction_logging_horizon)
        if getattr(args, "prediction_logging_save_raster", False):
            pred_dict["prediction_logging_save_raster"] = True
    if dataset_metadata is not None:
        pred_dict["prediction_dataset_metadata"] = dict(dataset_metadata)
    return pred_dict


def _infer_plot_init(init_glob):
    matches = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios/inits/", init_glob))
    if not matches:
        return 1
    name = os.path.basename(sorted(matches)[0])
    try:
        return int(name.split("ego_init_")[-1].split(".json")[0])
    except Exception:
        return 1


def _infer_plot_scenario(scenario_glob):
    matches = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios/", scenario_glob))
    if not matches:
        return "scenario_uk_give_way"
    return os.path.basename(sorted(matches)[0]).replace(".json", "")


def _run_postprocess(results_folder, args, log):
    """Run paper-oriented metrics and plots after the batch without masking rollout results."""
    if getattr(args, "skip_postprocess", False):
        return {"status": "skipped", "reason": "skip_postprocess"}

    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "compute_scenario_results.py")
    script_path = os.path.abspath(script_path)
    plot_init = args.postprocess_plot_init or _infer_plot_init(args.init_glob)
    plot_scenario = args.postprocess_plot_scenario or _infer_plot_scenario(args.scenario_glob)
    cmd = [
        sys.executable,
        script_path,
        "--results_dir",
        os.path.abspath(results_folder),
        "--compute_metrics",
    ]
    if not args.postprocess_no_plots:
        cmd.extend([
            "--make_traj_map",
            "--make_paper_panel",
            "--plot_scenario",
            plot_scenario,
            "--plot_init",
            str(plot_init),
        ])

    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=os.path.dirname(script_path), env=env, text=True, capture_output=True)
    payload = {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "duration_s": time.perf_counter() - started,
        "command": cmd,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-8000:],
        "plot_scenario": plot_scenario,
        "plot_init": plot_init,
    }
    exp_log.write_json(os.path.join(results_folder, "batch_postprocess.json"), payload)
    if proc.returncode == 0:
        log.info("Postprocess metrics/plots completed; see paper_metrics_summary.md and df_*.csv")
    else:
        log.warning("Postprocess metrics/plots failed; see batch_postprocess.json")
    return payload


def _load_adaptive_risk_config(args):
    """Load optional adaptive-risk mapping overrides for ablation runs."""
    if args.adaptive_risk_config_json and args.adaptive_risk_config_file:
        raise ValueError(
            "Use only one of --adaptive_risk_config_json or --adaptive_risk_config_file"
        )
    if args.adaptive_risk_config_file:
        with open(args.adaptive_risk_config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    elif args.adaptive_risk_config_json:
        config = json.loads(args.adaptive_risk_config_json)
    else:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("adaptive risk config must decode to a JSON object")
    return config


def run_without_tvs(scene, scenario_dict, ego_init_dict, savedir, get_cl=False, enable_camera_viz=True, args=None):
    if scene != "intersection":
        raise ValueError(f"Unsupported scene type after cleanup: {scene}")
    from scenarios.run_intersection_scenario import CarlaParams, DroneVizParams, VehicleParams, PredictionParams, RunIntersectionScenario


    carla_params     = CarlaParams(**scenario_dict["carla_params"])
    drone_viz_params = DroneVizParams(**_prepare_drone_viz_params(scenario_dict, enable_camera_viz))
    pred_params      = PredictionParams(**_prepare_prediction_params(scenario_dict, args))

    vehicles_params_list = []

    for vp_src in scenario_dict["vehicle_params"]:
        vp_dict = dict(vp_src)
        if vp_dict["role"] == "static":
            continue
            # vehicles_params_list.append( VehicleParams(**vp_dict) )
        elif "target" in vp_dict["role"]:
            pass
        elif vp_dict["role"] == "ego":
            if get_cl:
                vp_dict['goal_left_offset']=0.0
            vp_dict.update(ego_init_dict)
            vp_dict["policy_type"] = "blsmpc"
            vp_dict["smpc_config"] = ""
            vehicles_params_list.append( VehicleParams(**vp_dict) )
        else:

            raise ValueError(f"Invalid vehicle role: {vp_dict['role']}")

    runner = RunIntersectionScenario(carla_params,
                                    drone_viz_params,
                                    vehicles_params_list,
                                    pred_params,
                                    savedir)
    
    return runner.run_scenario()

def run_with_tvs(scene, scenario_dict, ego_init_dict, ego_policy_config, savedir,
                 enable_camera_viz=True, risk_profile="upstream_code",
                 adaptive_risk_config=None, args=None, prediction_dataset_metadata=None):
    if scene != "intersection":
        raise ValueError(f"Unsupported scene type after cleanup: {scene}")
    from scenarios.run_intersection_scenario import CarlaParams, DroneVizParams, VehicleParams, PredictionParams, RunIntersectionScenario
    
    
    carla_params     = CarlaParams(**scenario_dict["carla_params"])
    drone_viz_params = DroneVizParams(**_prepare_drone_viz_params(scenario_dict, enable_camera_viz))
    pred_params      = PredictionParams(
        **_prepare_prediction_params(
            scenario_dict,
            args,
            dataset_metadata=prediction_dataset_metadata,
        )
    )

    vehicles_params_list = []

    if ego_policy_config == "blsmpc":
        policy_type   = "blsmpc"
        policy_config = ""
    elif ego_policy_config.startswith("smpc"):
        policy_type = "smpc"
        policy_config = ego_policy_config.split("smpc_")[-1]
    elif ego_policy_config == "mpc":
        policy_type = "mpc"
        policy_config = ""
    else:
        raise ValueError(f"Invalid ego policy config: {ego_policy_config}")

    for vp_src in scenario_dict["vehicle_params"]:
        vp_dict = dict(vp_src)
        if vp_dict["role"] == "static":
            # Not generating static vehicles
            vehicles_params_list.append( VehicleParams(**vp_dict) )
            # continue
        elif "target" in vp_dict["role"]:
            target_style = getattr(args, "target_style", "assertive_constant_speed")
            vp_dict["target_style"] = target_style
            vp_dict["policy_type"] = (
                "defensive_reactive"
                if target_style == "defensive_reactive"
                else "straight"
            )
            vehicles_params_list.append( VehicleParams(**vp_dict) )
        elif vp_dict["role"] == "ego":
         
            vp_dict.update(ego_init_dict)
            vp_dict["policy_type"] = policy_type
            vp_dict["smpc_config"] = policy_config
            vp_dict["risk_profile"] = risk_profile
            if adaptive_risk_config:
                vp_dict["adaptive_risk_config"] = dict(adaptive_risk_config)
            vehicles_params_list.append( VehicleParams(**vp_dict) )
        else:

            raise ValueError(f"Invalid vehicle role: {vp_dict['role']}")

    runner = RunIntersectionScenario(carla_params,
                                    drone_viz_params,
                                    vehicles_params_list,
                                    pred_params,
                                    savedir)
    return runner.run_scenario()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run SMPC experiments in CARLA.")
    parser.add_argument("--scenario_glob", default="scenario_uk_give_way.json",
                        help="Glob pattern under scenarios/. Default is the dissertation give-way intersection scenario.")
    parser.add_argument("--init_glob", default="ego_init_01.json",
                        help="Glob pattern under scenarios/inits/. Use paper_intersection_50/ego_init_*.json for the full 50-init batch.")
    parser.add_argument("--results_dir", default=None,
                        help="Optional absolute/relative output directory. Default: <core>/results")
    parser.add_argument("--policies", nargs="+",
                        default=["smpc_var_risk", "smpc_open_loop", "smpc_fixed_risk"],
                        help="Policies to run.")
    parser.add_argument("--with_notv", action="store_true",
                        help="Also run no-TV reference rollout.")
    parser.add_argument("--with_notv_cl", action="store_true",
                        help="Also run no-TV centerline rollout.")
    parser.add_argument("--enable_camera_viz", dest="enable_camera_viz", action="store_true",
                        help="Enable CARLA RGB camera sensor and avi/opencv visualization. This is the default when the scenario requests save_avi=true.")
    parser.add_argument("--disable_camera_viz", dest="enable_camera_viz", action="store_false",
                        help="Disable CARLA RGB camera sensor and carla_sim.avi generation for faster/headless runs.")
    parser.set_defaults(enable_camera_viz=True)
    parser.add_argument(
        "--risk_profile",
        choices=[
            "upstream_code",
            "paper_eps_002",
            "adaptive_interaction_severity",
            "adaptive_interaction_severity_no_floor",
            "adaptive_interaction_severity_no_relax",
            "adaptive_interaction_severity_no_phase_awareness",
            "rule_aware_static_risk",
            "fixed_frontier_aggressive",
            "fixed_frontier_medium",
            "fixed_frontier_conservative",
        ],
        default="upstream_code",
        help=(
            "Gurobi SMPC risk profile. Adaptive variants share the same solver "
            "backend but differ in pre-clearance floor and post-clearance "
            "relaxation settings for ablation."
        ),
    )
    parser.add_argument(
        "--adaptive_risk_config_json",
        default=None,
        help="Optional JSON object overriding adaptive risk mapping values for ablation runs.",
    )
    parser.add_argument(
        "--adaptive_risk_config_file",
        default=None,
        help="Optional JSON file overriding adaptive risk mapping values for ablation runs.",
    )
    parser.add_argument(
        "--tuning_config",
        default=None,
        help=(
            "Optional fine-tuning config JSON. If omitted, each scenario may provide "
            "its own tuning_config path relative to the scenario file."
        ),
    )
    parser.add_argument(
        "--no_tuning_config",
        action="store_true",
        help="Ignore scenario-level tuning_config and run only with values in the scenario JSON.",
    )
    parser.add_argument("--skip_postprocess", action="store_true",
                        help="Skip automatic paper metrics/plots generation at the end of the batch.")
    parser.add_argument("--postprocess_no_plots", action="store_true",
                        help="Only generate df_*.csv and paper_metrics_summary; skip trajectory figures.")
    parser.add_argument("--postprocess_plot_scenario", default=None,
                        help="Scenario name for automatic trajectory figures. Default: first matched scenario.")
    parser.add_argument("--postprocess_plot_init", type=int, default=None,
                        help="ego_init index for automatic trajectory figures. Default: first matched init.")
    parser.add_argument("--skip_completed_subruns", action="store_true",
                        help="Resume mode: skip rollout directories with scenario_result.pkl and ran_successfully=true.")
    parser.add_argument("--prediction_model_weights", default=None,
                        help="Override PredictionParams.model_weights, relative to core/scripts/models unless absolute.")
    parser.add_argument("--prediction_model_anchors", default=None,
                        help="Override PredictionParams.model_anchors, relative to core/scripts/models unless absolute.")
    parser.add_argument("--enable_prediction_logging", action="store_true",
                        help="Write per-rollout prediction dataset JSONL files for model calibration/fine-tuning.")
    parser.add_argument("--prediction_logging_stride", type=int, default=None,
                        help="Record one prediction sample every N simulator steps when prediction logging is enabled.")
    parser.add_argument("--prediction_logging_horizon", type=int, default=None,
                        help="Number of future target steps to label in prediction_dataset_labeled.jsonl.")
    parser.add_argument("--prediction_logging_save_raster", action="store_true",
                        help="Also save rasterized prediction input images as PNG files for future fine-tuning.")
    parser.add_argument(
        "--target_style",
        choices=["assertive_constant_speed", "defensive_reactive"],
        default="assertive_constant_speed",
        help="V2 target behavior treatment.",
    )
    parser.add_argument(
        "--prediction_dataset_version",
        default="give_way_interaction_prediction_v2.0",
    )
    parser.add_argument(
        "--prediction_protocol_id",
        default="town05_give_way_2x2_200_rollouts_v1",
    )
    parser.add_argument(
        "--prediction_feature_schema_id",
        default="give_way_interaction_sequence_v2",
    )
    parser.add_argument("--prediction_cell_id", default=None)
    parser.add_argument("--prediction_ego_policy_label", default=None)
    parser.add_argument("--prediction_git_commit", default=None)
    parser.add_argument("--no_console_log", action="store_true",
                        help="Do not duplicate experiment logs to stdout (file + jsonl still written).")
    args = parser.parse_args()
    if args.prediction_git_commit is None:
        args.prediction_git_commit = _current_git_commit()
    adaptive_risk_config = _load_adaptive_risk_config(args)

    scenario_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios/")
    scenarios_list = sorted(glob.glob(os.path.join(scenario_folder, args.scenario_glob)))
    if not scenarios_list:
        raise RuntimeError(f"No scenarios matched: {args.scenario_glob}")

    if args.results_dir is None:
        results_root = os.path.join(os.path.abspath(__file__).split("scripts")[0], "results")
        run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_folder = os.path.join(results_root, run_stamp)
    else:
        results_folder = os.path.abspath(args.results_dir)
    os.makedirs(results_folder, exist_ok=True)
    print(f"Saving experiment outputs under: {results_folder}")

    log = exp_log.configure_batch_logging(
        results_folder,
        console=not args.no_console_log,
    )
    exp_log.write_json(
        os.path.join(results_folder, "batch_config.json"),
        {
            "argv": sys.argv,
            "scenario_glob": args.scenario_glob,
            "init_glob": args.init_glob,
            "policies": list(args.policies),
            "solver_backend": "gurobi",
            "risk_profile": args.risk_profile,
            "adaptive_risk_config": adaptive_risk_config,
            "tuning_config": args.tuning_config,
            "no_tuning_config": args.no_tuning_config,
            "with_notv": args.with_notv,
            "with_notv_cl": args.with_notv_cl,
            "enable_camera_viz": args.enable_camera_viz,
            "skip_postprocess": args.skip_postprocess,
            "postprocess_no_plots": args.postprocess_no_plots,
            "postprocess_plot_scenario": args.postprocess_plot_scenario,
            "postprocess_plot_init": args.postprocess_plot_init,
            "prediction_model_weights": args.prediction_model_weights,
            "prediction_model_anchors": args.prediction_model_anchors,
            "enable_prediction_logging": args.enable_prediction_logging,
            "prediction_logging_stride": args.prediction_logging_stride,
            "prediction_logging_horizon": args.prediction_logging_horizon,
            "prediction_logging_save_raster": args.prediction_logging_save_raster,
            "target_style": args.target_style,
            "prediction_dataset_version": args.prediction_dataset_version,
            "prediction_protocol_id": args.prediction_protocol_id,
            "prediction_feature_schema_id": args.prediction_feature_schema_id,
            "prediction_cell_id": args.prediction_cell_id,
            "prediction_ego_policy_label": args.prediction_ego_policy_label,
            "prediction_git_commit": args.prediction_git_commit,
            "results_folder": os.path.abspath(results_folder),
        },
    )
    exp_log.append_jsonl(
        results_folder,
        {"event": "batch_start", "n_scenario_files": len(scenarios_list)},
    )
    log.info("Matched %d scenario JSON files", len(scenarios_list))

    subrun_status: list = []
    applied_tuning_configs = {}

    for scenario in scenarios_list:
        # Load the scenario and generate parameters.
        if args.no_tuning_config:
            scenario_dict = json.load(open(scenario, "r"))
            scenario_dict.pop("tuning_config", None)
            scenario_dict, tuning_metadata = apply_tuning_config(scenario_dict, scenario_path=scenario, tuning_config_path=None)
        else:
            scenario_dict, tuning_metadata = load_scenario_with_tuning(scenario, args.tuning_config)
        scenario_name = scenario.split("/")[-1].split('.json')[0]
        applied_tuning_configs[scenario_name] = tuning_metadata
        exp_log.write_json(
            os.path.join(results_folder, "applied_tuning_configs.json"),
            applied_tuning_configs,
        )
        log.info(
            "Scenario %s tuning config: %s",
            scenario_name,
            tuning_metadata.get("source_path") if tuning_metadata.get("applied") else "none",
        )
        scene = "intersection"
        inits_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios/inits/")
        ego_init_list = sorted(glob.glob(os.path.join(inits_folder, args.init_glob)))
        if not ego_init_list:
            raise RuntimeError(f"No init files matched: {args.init_glob}")

        log.info("Scenario %s: %d init files", scenario_name, len(ego_init_list))

        for ego_init in ego_init_list:
            # Load the ego vehicle parameters.
            ego_init_dict = json.load(open(ego_init, "r"))
            ego_init_name = os.path.basename(ego_init).replace(".json", "")

            if args.with_notv:
                savedir = os.path.join(results_folder, f"{scenario_name}_{ego_init_name}_notv")
                print(f"Running {scenario_name} {ego_init_name} notv")
                label = f"{scenario_name}_{ego_init_name}_notv"
                t0 = time.perf_counter()
                err = None
                ok = False
                scenario_ok = None
                try:
                    _write_fine_tune_config_snapshot(savedir, scenario_dict)
                    exp_log.append_jsonl(
                        results_folder,
                        {"event": "subrun_start", "label": label, "savedir": savedir},
                    )
                    scenario_ok = run_without_tvs(scene, scenario_dict, ego_init_dict, savedir, enable_camera_viz=args.enable_camera_viz, args=args)
                    ok = bool(scenario_ok)
                except Exception:
                    err = traceback.format_exc()
                    log.exception("Subrun failed: %s", label)
                    raise
                finally:
                    duration_s = time.perf_counter() - t0
                    metrics = exp_log.collect_savedir_metrics(savedir)
                    exp_log.log_batch_subrun(
                        label,
                        phase="notv",
                        duration_s=duration_s,
                        ok=ok,
                        error=err,
                        savedir=savedir,
                        metrics=metrics,
                    )
                    subrun_status.append(
                        {
                            "label": label,
                            "ok": ok,
                            "savedir": savedir,
                            "scenario_completed": scenario_ok,
                            "duration_s": duration_s,
                            "metrics": metrics,
                        }
                    )
                    if ok and scenario_ok:
                        _write_scenario_rollout_config(savedir, scenario_dict)

            if args.with_notv_cl:
                savedir = os.path.join(results_folder, f"{scenario_name}_{ego_init_name}_notv_cl")
                print(f"Running {scenario_name} {ego_init_name} notv_cl")
                label = f"{scenario_name}_{ego_init_name}_notv_cl"
                t0 = time.perf_counter()
                err = None
                ok = False
                scenario_ok = None
                try:
                    _write_fine_tune_config_snapshot(savedir, scenario_dict)
                    exp_log.append_jsonl(
                        results_folder,
                        {"event": "subrun_start", "label": label, "savedir": savedir},
                    )
                    scenario_ok = run_without_tvs(scene, scenario_dict, ego_init_dict, savedir, get_cl=True, enable_camera_viz=args.enable_camera_viz, args=args)
                    ok = bool(scenario_ok)
                except Exception:
                    err = traceback.format_exc()
                    log.exception("Subrun failed: %s", label)
                    raise
                finally:
                    duration_s = time.perf_counter() - t0
                    metrics = exp_log.collect_savedir_metrics(savedir)
                    exp_log.log_batch_subrun(
                        label,
                        phase="notv_cl",
                        duration_s=duration_s,
                        ok=ok,
                        error=err,
                        savedir=savedir,
                        metrics=metrics,
                    )
                    subrun_status.append(
                        {
                            "label": label,
                            "ok": ok,
                            "savedir": savedir,
                            "scenario_completed": scenario_ok,
                            "duration_s": duration_s,
                            "metrics": metrics,
                        }
                    )
                    if ok and scenario_ok:
                        _write_scenario_rollout_config(savedir, scenario_dict)

            for ego_policy_config in args.policies:
                output_policy_name = _policy_output_name(ego_policy_config)
                savedir = os.path.join(results_folder, f"{scenario_name}_{ego_init_name}_{output_policy_name}")
                print(f"Running {scenario_name} {ego_init_name} {ego_policy_config}")
                label = f"{scenario_name}_{ego_init_name}_{ego_policy_config}"
                if args.skip_completed_subruns and _savedir_completed_successfully(savedir):
                    metrics = exp_log.collect_savedir_metrics(savedir)
                    log.info("Skipping completed subrun: %s", label)
                    exp_log.append_jsonl(
                        results_folder,
                        {
                            "event": "subrun_skipped_completed",
                            "label": label,
                            "savedir": os.path.abspath(savedir),
                            "policy": ego_policy_config,
                            "metrics": metrics,
                        },
                    )
                    subrun_status.append(
                        {
                            "label": label,
                            "ok": True,
                            "savedir": savedir,
                            "policy": ego_policy_config,
                            "scenario_completed": True,
                            "duration_s": 0.0,
                            "metrics": metrics,
                            "skipped_completed": True,
                        }
                    )
                    continue
                t0 = time.perf_counter()
                err = None
                ok = False
                scenario_ok = None
                try:
                    _write_fine_tune_config_snapshot(savedir, scenario_dict)
                    exp_log.append_jsonl(
                        results_folder,
                        {
                            "event": "subrun_start",
                            "label": label,
                            "savedir": savedir,
                            "policy": ego_policy_config,
                            "solver_backend": "gurobi",
                        },
                    )
                    try:
                        ego_init_id = int(ego_init_name.rsplit("_", 1)[-1])
                    except ValueError:
                        ego_init_id = None
                    prediction_dataset_metadata = {
                        "dataset_version": args.prediction_dataset_version,
                        "protocol_id": args.prediction_protocol_id,
                        "git_commit": args.prediction_git_commit,
                        "scenario": scenario_name,
                        "map": scenario_dict.get("carla_params", {}).get("map_str"),
                        "ego_init_id": ego_init_id,
                        "ego_policy": (
                            args.prediction_ego_policy_label or ego_policy_config
                        ),
                        "target_style": args.target_style,
                        "cell_id": args.prediction_cell_id,
                        "feature_schema_id": args.prediction_feature_schema_id,
                        "source_subrun": label,
                    }
                    scenario_ok = run_with_tvs(scene, scenario_dict, ego_init_dict, ego_policy_config, savedir,
                                               enable_camera_viz=args.enable_camera_viz,
                                               risk_profile=args.risk_profile,
                                               adaptive_risk_config=adaptive_risk_config,
                                               args=args,
                                               prediction_dataset_metadata=prediction_dataset_metadata)
                    ok = bool(scenario_ok)
                except Exception:
                    err = traceback.format_exc()
                    log.exception("Subrun failed: %s", label)
                    raise
                finally:
                    duration_s = time.perf_counter() - t0
                    metrics = exp_log.collect_savedir_metrics(savedir)
                    exp_log.log_batch_subrun(
                        label,
                        phase="smpc",
                        duration_s=duration_s,
                        ok=ok,
                        error=err,
                        savedir=savedir,
                        metrics=metrics,
                    )
                    subrun_status.append(
                        {
                            "label": label,
                            "ok": ok,
                            "savedir": savedir,
                            "policy": ego_policy_config,
                            "scenario_completed": scenario_ok,
                            "duration_s": duration_s,
                            "metrics": metrics,
                        }
                    )
                    if ok and scenario_ok:
                        _write_scenario_rollout_config(savedir, scenario_dict)

    exp_log.append_jsonl(
        results_folder,
        {
            "event": "batch_end",
            "n_subruns": len(subrun_status),
            "all_scenario_flags_true": (
                len(subrun_status) > 0
                and all(s.get("scenario_completed") is True for s in subrun_status)
            ),
        },
    )
    exp_log.write_json(os.path.join(results_folder, "batch_subruns.json"), {"subruns": subrun_status})
    exp_log.write_batch_summary_txt(results_folder, subrun_status)
    log.info(
        "Batch finished; logged %d subruns to batch_subruns.json and batch_summary.txt",
        len(subrun_status),
    )
    _run_postprocess(results_folder, args, log)
