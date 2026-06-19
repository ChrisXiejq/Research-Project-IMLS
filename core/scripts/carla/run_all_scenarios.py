import os
import sys
import glob
import json
import argparse
import time
import traceback
import importlib.util
import subprocess
from datetime import datetime

from utils import experiment_logging as exp_log

script_root = os.path.abspath(__file__).split("carla")[0]
if script_root not in sys.path:
    sys.path.append(script_root)
from experiment_tuning import apply_tuning_config, load_scenario_with_tuning, tuning_snapshot_payload



def _prepare_drone_viz_params(scenario_dict, enable_camera_viz=False):
    drone_viz_dict = dict(scenario_dict["drone_viz_params"])
    if not enable_camera_viz:
        # Headless AutoDL runs are more stable without RGB camera sensors.
        drone_viz_dict["visualize_opencv"] = False
        drone_viz_dict["save_avi"] = False
    return drone_viz_dict


def _policy_output_name(policy_name, solver_backend):
    if solver_backend == "gurobi":
        return policy_name
    return f"{policy_name}_{solver_backend}"


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


def _prepare_prediction_params(scenario_dict):
    pred_dict = dict(scenario_dict.get("prediction_params", {}))
    traffic_control = (
        scenario_dict.get("carla_params", {}).get("traffic_control")
        or scenario_dict.get("scenario_description", {}).get("traffic_control", "")
    )
    traffic_control_norm = str(traffic_control).lower().strip()
    if traffic_control_norm.startswith("signalised"):
        pred_dict.setdefault("render_traffic_lights", True)
    return pred_dict


def _maybe_render_topdown_mp4(savedir, scenario_dict, log, args):
    """Offline top-down MP4 from ``scenario_result.pkl`` (no CARLA)."""
    if not getattr(args, "render_topdown_mp4", False):
        return
    pkl = os.path.join(savedir, "scenario_result.pkl")
    if not os.path.isfile(pkl):
        log.warning("Skip top-down render: missing %s", pkl)
        return
    csv_rel = scenario_dict.get("carla_params", {}).get("intersection_csv_loc")
    carla_dir = os.path.dirname(os.path.abspath(__file__))
    scenarios_dir = os.path.join(carla_dir, "scenarios")
    csv_path = os.path.join(scenarios_dir, csv_rel) if csv_rel else None
    if csv_path and not os.path.isfile(csv_path):
        log.warning("Intersection CSV not found (%s); video will omit road polylines.", csv_path)
        csv_path = None
    outv = os.path.join(savedir, "rollout_topdown.mp4")
    mod_path = os.path.join(os.path.dirname(carla_dir), "render_rollout_video.py")
    try:
        spec = importlib.util.spec_from_file_location("render_rollout_video", mod_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.render_topdown_mp4(
            pkl,
            csv_path,
            outv,
            fps=float(args.render_topdown_fps),
            width=int(args.render_topdown_width),
            height=int(args.render_topdown_height),
        )
        log.info("Wrote top-down rollout video: %s", outv)
    except Exception:
        log.warning("Top-down video render failed; see traceback.", exc_info=True)


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
        return "scenario_01"
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


def run_without_tvs(scene, scenario_dict, ego_init_dict, savedir, get_cl=False, enable_camera_viz=False):
    if scene =="intersection":
        from scenarios.run_intersection_scenario import CarlaParams, DroneVizParams, VehicleParams, PredictionParams, RunIntersectionScenario
    else:
        from scenarios.run_lk_scenario import CarlaParams, DroneVizParams, VehicleParams, PredictionParams, RunLKScenario


    carla_params     = CarlaParams(**scenario_dict["carla_params"])
    drone_viz_params = DroneVizParams(**_prepare_drone_viz_params(scenario_dict, enable_camera_viz))
    pred_params      = PredictionParams(**_prepare_prediction_params(scenario_dict))

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

    if scene =="intersection":
        runner = RunIntersectionScenario(carla_params,
                                        drone_viz_params,
                                        vehicles_params_list,
                                        pred_params,
                                        savedir)
    else:
        runner = RunLKScenario(carla_params,
                                        drone_viz_params,
                                        vehicles_params_list,
                                        pred_params,
                                        savedir)
    
    return runner.run_scenario()

def run_with_tvs(scene, scenario_dict, ego_init_dict, ego_policy_config, savedir,
                 enable_camera_viz=False, solver_backend="gurobi",
                 risk_profile="upstream_code"):
    if scene =="intersection":
        from scenarios.run_intersection_scenario import CarlaParams, DroneVizParams, VehicleParams, PredictionParams, RunIntersectionScenario
    else:
        from scenarios.run_lk_scenario import CarlaParams, DroneVizParams, VehicleParams, PredictionParams, RunLKScenario
    
    
    carla_params     = CarlaParams(**scenario_dict["carla_params"])
    drone_viz_params = DroneVizParams(**_prepare_drone_viz_params(scenario_dict, enable_camera_viz))
    pred_params      = PredictionParams(**_prepare_prediction_params(scenario_dict))

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
            vehicles_params_list.append( VehicleParams(**vp_dict) )
        elif vp_dict["role"] == "ego":
         
            vp_dict.update(ego_init_dict)
            vp_dict["policy_type"] = policy_type
            vp_dict["smpc_config"] = policy_config
            vp_dict["solver_backend"] = solver_backend
            vp_dict["risk_profile"] = risk_profile
            vehicles_params_list.append( VehicleParams(**vp_dict) )
        else:

            raise ValueError(f"Invalid vehicle role: {vp_dict['role']}")

    if scene == "intersection":
        runner = RunIntersectionScenario(carla_params,
                                        drone_viz_params,
                                        vehicles_params_list,
                                        pred_params,
                                        savedir)
    else:
        runner = RunLKScenario(carla_params,
                                     drone_viz_params,
                                     vehicles_params_list,
                                     pred_params,
                                     savedir)
    return runner.run_scenario()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run SMPC experiments in CARLA.")
    parser.add_argument("--scenario_glob", default="scenario_01.json",
                        help="Glob pattern under scenarios/. Default is the paper's intersection scenario; use scenario_0*.json for all local variants.")
    parser.add_argument("--init_glob", default="ego_init_*.json",
                        help="Glob pattern under scenarios/inits/. Example: ego_init_0*.json")
    parser.add_argument("--results_dir", default=None,
                        help="Optional absolute/relative output directory. Default: <core>/results")
    parser.add_argument("--policies", nargs="+",
                        default=["smpc_var_risk", "smpc_open_loop", "smpc_fixed_risk"],
                        help="Policies to run.")
    parser.add_argument("--with_notv", action="store_true",
                        help="Also run no-TV reference rollout.")
    parser.add_argument("--with_notv_cl", action="store_true",
                        help="Also run no-TV centerline rollout.")
    parser.add_argument("--enable_camera_viz", action="store_true",
                        help="Enable CARLA RGB camera sensor and avi/opencv visualization. Disabled by default for AutoDL stability.")
    parser.add_argument(
        "--render_topdown_mp4",
        action="store_true",
        help="After each successful subrun, write rollout_topdown.mp4 from scenario_result.pkl (OpenCV; no extra CARLA load).",
    )
    parser.add_argument("--render_topdown_fps", type=float, default=15.0, help="FPS for offline top-down MP4.")
    parser.add_argument("--render_topdown_width", type=int, default=1280, help="Width in pixels for offline top-down MP4.")
    parser.add_argument("--render_topdown_height", type=int, default=720, help="Height in pixels for offline top-down MP4.")
    parser.add_argument("--solver_backend", choices=["gurobi", "ipopt_approx"], default="gurobi",
                        help="Solver backend for SMPC policies. Use ipopt_approx when Gurobi is unavailable.")
    parser.add_argument("--risk_profile", choices=["upstream_code", "paper_eps_002"], default="upstream_code",
                        help="Gurobi SMPC risk profile: upstream_code matches SMPC_MMPreds numerical settings; paper_eps_002 uses epsilon=0.02.")
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
    parser.add_argument("--no_console_log", action="store_true",
                        help="Do not duplicate experiment logs to stdout (file + jsonl still written).")
    args = parser.parse_args()

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
            "solver_backend": args.solver_backend,
            "risk_profile": args.risk_profile,
            "tuning_config": args.tuning_config,
            "no_tuning_config": args.no_tuning_config,
            "with_notv": args.with_notv,
            "with_notv_cl": args.with_notv_cl,
            "enable_camera_viz": args.enable_camera_viz,
            "render_topdown_mp4": args.render_topdown_mp4,
            "render_topdown_fps": args.render_topdown_fps,
            "render_topdown_width": args.render_topdown_width,
            "render_topdown_height": args.render_topdown_height,
            "skip_postprocess": args.skip_postprocess,
            "postprocess_no_plots": args.postprocess_no_plots,
            "postprocess_plot_scenario": args.postprocess_plot_scenario,
            "postprocess_plot_init": args.postprocess_plot_init,
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
        if "lk" in scenario_name:
            scene = "highway"
        else:
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
                    scenario_ok = run_without_tvs(scene, scenario_dict, ego_init_dict, savedir, enable_camera_viz=args.enable_camera_viz)
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
                        _maybe_render_topdown_mp4(savedir, scenario_dict, log, args)

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
                    scenario_ok = run_without_tvs(scene, scenario_dict, ego_init_dict, savedir, get_cl=True, enable_camera_viz=args.enable_camera_viz)
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
                        _maybe_render_topdown_mp4(savedir, scenario_dict, log, args)

            for ego_policy_config in args.policies:
                output_policy_name = _policy_output_name(ego_policy_config, args.solver_backend)
                savedir = os.path.join(results_folder, f"{scenario_name}_{ego_init_name}_{output_policy_name}")
                print(f"Running {scenario_name} {ego_init_name} {ego_policy_config} ({args.solver_backend})")
                label = f"{scenario_name}_{ego_init_name}_{ego_policy_config}"
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
                            "solver_backend": args.solver_backend,
                        },
                    )
                    scenario_ok = run_with_tvs(scene, scenario_dict, ego_init_dict, ego_policy_config, savedir,
                                               enable_camera_viz=args.enable_camera_viz,
                                               solver_backend=args.solver_backend,
                                               risk_profile=args.risk_profile)
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
                        _maybe_render_topdown_mp4(savedir, scenario_dict, log, args)

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
