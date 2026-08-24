#!/usr/bin/env python3
"""Evaluate the three behavioural phases of the implicit-SMPC experiment."""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

import numpy as np


DEFAULT_SETTINGS = {
    "target_arrival_radius_m": 12.0,
    "conflict_radius_m": 4.0,
    "clearance_tolerance_s": 0.2,
    "minimum_pre_arrival_duration_s": 0.5,
    "minimum_pre_arrival_progress_m": 1.0,
    "minimum_interaction_speed_drop_mps": 1.0,
    "minimum_post_clear_progress_m": 5.0,
    "minimum_resume_speed_gain_mps": 1.0,
    "maximum_absolute_lateral_error_m": None,
    "max_solver_failure_fraction": 0.0,
    "require_valid_completion": True,
    "require_no_native_collision": True,
}


def _trajectory(value: Any, label: str) -> np.ndarray:
    trajectory = np.asarray(value, dtype=float)
    if trajectory.ndim != 2 or trajectory.shape[0] < 2 or trajectory.shape[1] < 5:
        raise ValueError(f"{label} trajectory must have shape [N>=2, >=5]")
    if not np.isfinite(trajectory[:, :5]).all():
        raise ValueError(f"{label} trajectory contains non-finite state values")
    if np.any(np.diff(trajectory[:, 0]) <= 0.0):
        raise ValueError(f"{label} trajectory timestamps must be strictly increasing")
    return trajectory


def _zone_interval(
    trajectory: np.ndarray,
    point_xy: Iterable[float],
    radius_m: float,
) -> Tuple[Optional[float], Optional[float]]:
    distance = np.linalg.norm(
        trajectory[:, 1:3] - np.asarray(point_xy, dtype=float),
        axis=1,
    )
    inside_mask = distance <= float(radius_m)
    indices = np.flatnonzero(inside_mask)
    if len(indices) == 0:
        return None, None
    first = int(indices[0])
    enter_time = float(trajectory[first, 0])
    if first > 0 and distance[first - 1] > float(radius_m):
        outside_distance = float(distance[first - 1])
        inside_distance = float(distance[first])
        denominator = max(outside_distance - inside_distance, 1.0e-12)
        fraction = (outside_distance - float(radius_m)) / denominator
        enter_time = float(
            trajectory[first - 1, 0]
            + fraction * (trajectory[first, 0] - trajectory[first - 1, 0])
        )
    outside_after_entry = np.flatnonzero(~inside_mask[first + 1 :])
    clear_time = None
    if len(outside_after_entry):
        clear_index = first + 1 + int(outside_after_entry[0])
        inside_index = clear_index - 1
        inside_distance = float(distance[inside_index])
        outside_distance = float(distance[clear_index])
        denominator = max(outside_distance - inside_distance, 1.0e-12)
        fraction = (float(radius_m) - inside_distance) / denominator
        clear_time = float(
            trajectory[inside_index, 0]
            + fraction
            * (trajectory[clear_index, 0] - trajectory[inside_index, 0])
        )
    return (
        enter_time,
        clear_time,
    )


def _cumulative_distance(trajectory: np.ndarray) -> np.ndarray:
    segment_lengths = np.linalg.norm(np.diff(trajectory[:, 1:3], axis=0), axis=1)
    return np.concatenate(([0.0], np.cumsum(segment_lengths)))


def _interp(times: np.ndarray, values: np.ndarray, query_time: float) -> float:
    return float(np.interp(float(query_time), times, values))


def _interval_values(
    trajectory: np.ndarray,
    column: int,
    start_time: float,
    end_time: float,
) -> np.ndarray:
    times = trajectory[:, 0]
    mask = (times >= start_time) & (times <= end_time)
    values = list(trajectory[mask, column])
    values.extend(
        [
            _interp(times, trajectory[:, column], start_time),
            _interp(times, trajectory[:, column], end_time),
        ]
    )
    return np.asarray(values, dtype=float)


def _target_line_max_deviation(
    target: np.ndarray,
    target_conflict_point_xy: Iterable[float],
    target_tangent_xy: Iterable[float],
) -> float:
    point = np.asarray(target_conflict_point_xy, dtype=float)
    tangent = np.asarray(target_tangent_xy, dtype=float)
    tangent /= max(float(np.linalg.norm(tangent)), 1.0e-12)
    normal = np.array([-tangent[1], tangent[0]], dtype=float)
    return float(np.max(np.abs((target[:, 1:3] - point) @ normal)))


def evaluate_three_phase_behavior(
    ego_trajectory: Any,
    target_trajectory: Any,
    geometry: Dict[str, Any],
    *,
    settings: Optional[Dict[str, Any]] = None,
    completion_valid: Optional[bool],
    native_collision: bool,
    footprint_collision: Optional[bool],
    solver_failure_fraction: Optional[float],
    contract_valid: bool,
    observed_max_abs_lateral_error_m: Optional[float] = None,
) -> Dict[str, Any]:
    """Return a fail-closed verdict for proceed, yield and resume phases."""

    config = {**DEFAULT_SETTINGS, **dict(settings or {})}
    ego = _trajectory(ego_trajectory, "ego")
    target = _trajectory(target_trajectory, "target")
    ego_point = np.asarray(geometry["ego_conflict_point_xy"], dtype=float)
    target_point = np.asarray(geometry["target_conflict_point_xy"], dtype=float)

    target_arrival, _ = _zone_interval(
        target,
        target_point,
        float(config["target_arrival_radius_m"]),
    )
    target_enter, target_exit = _zone_interval(
        target,
        target_point,
        float(config["conflict_radius_m"]),
    )
    ego_enter, ego_exit = _zone_interval(
        ego,
        ego_point,
        float(config["conflict_radius_m"]),
    )

    errors = []
    if target_arrival is None:
        errors.append("target_never_reached_arrival_zone")
    if target_enter is None or target_exit is None:
        errors.append("target_never_traversed_conflict_zone")

    ego_times = ego[:, 0]
    cumulative = _cumulative_distance(ego)
    start_time = float(ego_times[0])
    end_time = float(ego_times[-1])

    phase1_duration = None
    phase1_progress = None
    pre_arrival_peak_speed = None
    phase1_pass = False
    if target_arrival is not None:
        phase1_end = min(float(target_arrival), end_time)
        phase1_duration = max(0.0, phase1_end - start_time)
        phase1_progress = _interp(ego_times, cumulative, phase1_end)
        pre_arrival_peak_speed = float(
            np.max(_interval_values(ego, 4, start_time, phase1_end))
        )
        phase1_pass = bool(
            phase1_duration
            >= float(config["minimum_pre_arrival_duration_s"])
            and phase1_progress
            >= float(config["minimum_pre_arrival_progress_m"])
            and pre_arrival_peak_speed > 0.5
        )
    if not phase1_pass:
        errors.append("phase1_ego_did_not_continue_before_target_arrival")

    interaction_min_speed = None
    interaction_speed_drop = None
    yield_order_pass = False
    phase2_pass = False
    if (
        target_arrival is not None
        and target_exit is not None
        and pre_arrival_peak_speed is not None
    ):
        interaction_end = min(float(target_exit), end_time)
        interaction_min_speed = float(
            np.min(
                _interval_values(
                    ego,
                    4,
                    min(float(target_arrival), interaction_end),
                    interaction_end,
                )
            )
        )
        interaction_speed_drop = float(
            pre_arrival_peak_speed - interaction_min_speed
        )
        yield_order_pass = bool(
            ego_enter is not None
            and float(target_exit)
            <= float(ego_enter) + float(config["clearance_tolerance_s"])
        )
        phase2_pass = bool(
            interaction_speed_drop
            >= float(config["minimum_interaction_speed_drop_mps"])
            and yield_order_pass
        )
    if not phase2_pass:
        errors.append("phase2_ego_did_not_slow_and_yield_to_target")

    post_clear_progress = None
    resume_speed_gain = None
    phase3_pass = False
    if target_exit is not None and interaction_min_speed is not None:
        post_start = min(float(target_exit), end_time)
        post_clear_progress = float(
            cumulative[-1] - _interp(ego_times, cumulative, post_start)
        )
        post_peak_speed = float(
            np.max(_interval_values(ego, 4, post_start, end_time))
        )
        resume_speed_gain = float(post_peak_speed - interaction_min_speed)
        completion_pass = (
            completion_valid is True
            if bool(config["require_valid_completion"])
            else completion_valid is not False
        )
        phase3_pass = bool(
            post_clear_progress
            >= float(config["minimum_post_clear_progress_m"])
            and resume_speed_gain
            >= float(config["minimum_resume_speed_gain_mps"])
            and completion_pass
        )
    if not phase3_pass:
        errors.append("phase3_ego_did_not_resume_and_complete_after_target_clearance")

    collision_pass = bool(
        (not native_collision or not bool(config["require_no_native_collision"]))
        and footprint_collision is False
    )
    if footprint_collision is None:
        errors.append("offline_footprint_collision_evidence_missing")
    elif footprint_collision:
        errors.append("offline_footprint_collision_detected")
    if native_collision and bool(config["require_no_native_collision"]):
        errors.append("native_carla_collision_detected")

    solver_pass = bool(
        solver_failure_fraction is not None
        and math.isfinite(float(solver_failure_fraction))
        and float(solver_failure_fraction)
        <= float(config["max_solver_failure_fraction"])
    )
    if not solver_pass:
        errors.append("solver_failure_fraction_missing_or_above_limit")
    if not contract_valid:
        errors.append("implicit_filter_control_contract_invalid")

    target_line_deviation = _target_line_max_deviation(
        target,
        target_point,
        geometry["target_tangent_xy"],
    )
    target_straight_pass = bool(target_line_deviation <= 0.75)
    if not target_straight_pass:
        errors.append("target_deviated_from_fixed_straight_route")

    lateral_error_limit = config.get("maximum_absolute_lateral_error_m")
    route_adherence_pass = True
    if lateral_error_limit is not None:
        route_adherence_pass = bool(
            observed_max_abs_lateral_error_m is not None
            and math.isfinite(float(observed_max_abs_lateral_error_m))
            and float(observed_max_abs_lateral_error_m)
            <= float(lateral_error_limit)
        )
        if not route_adherence_pass:
            errors.append("ego_exceeded_maximum_lateral_route_error")

    overall_pass = bool(
        phase1_pass
        and phase2_pass
        and phase3_pass
        and collision_pass
        and solver_pass
        and contract_valid
        and target_straight_pass
        and route_adherence_pass
    )
    return {
        "status": "PASS" if overall_pass else "FAIL",
        "phase1_proceed_before_target": {
            "pass": phase1_pass,
            "target_arrival_time_s": target_arrival,
            "duration_s": phase1_duration,
            "ego_progress_m": phase1_progress,
            "ego_peak_speed_mps": pre_arrival_peak_speed,
        },
        "phase2_slow_and_yield": {
            "pass": phase2_pass,
            "target_conflict_enter_time_s": target_enter,
            "target_conflict_exit_time_s": target_exit,
            "ego_conflict_enter_time_s": ego_enter,
            "ego_conflict_exit_time_s": ego_exit,
            "interaction_min_speed_mps": interaction_min_speed,
            "speed_drop_mps": interaction_speed_drop,
            "target_cleared_before_ego_entry": yield_order_pass,
        },
        "phase3_resume_after_target": {
            "pass": phase3_pass,
            "post_clear_progress_m": post_clear_progress,
            "resume_speed_gain_mps": resume_speed_gain,
            "completion_valid": completion_valid,
        },
        "safety_and_integrity": {
            "pass": bool(
                collision_pass
                and solver_pass
                and contract_valid
                and target_straight_pass
                and route_adherence_pass
            ),
            "native_collision": bool(native_collision),
            "footprint_collision": footprint_collision,
            "solver_failure_fraction": solver_failure_fraction,
            "contract_valid": bool(contract_valid),
            "target_straight_line_max_deviation_m": target_line_deviation,
            "target_straight_pass": target_straight_pass,
            "ego_max_absolute_lateral_error_m": observed_max_abs_lateral_error_m,
            "ego_lateral_error_limit_m": lateral_error_limit,
            "ego_route_adherence_pass": route_adherence_pass,
        },
        "settings": config,
        "errors": errors,
    }


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _completion_valid(scenario_dir: str) -> Optional[bool]:
    payload = _load_json(os.path.join(scenario_dir, "smpc_completion.json"))
    if not payload:
        return False
    completion = payload.get("completion") or {}
    return bool(
        completion.get("completed_by_lane_entry", False)
        or completion.get("completed_by_exit_alignment", False)
        or (
            completion.get("lateral_ok", False)
            and completion.get("heading_ok", True)
            and (
                completion.get("completed_by_s_margin", False)
                or completion.get("completed_by_goal_dist", False)
            )
        )
    )


def _solver_failure_fraction(scenario_dir: str) -> Optional[float]:
    path = os.path.join(scenario_dir, "smpc_debug_steps.jsonl")
    if not os.path.isfile(path):
        return None
    total = 0
    failed = 0
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            optimal = (row.get("solver") or {}).get("optimal")
            if optimal is None:
                continue
            total += 1
            failed += int(not bool(optimal))
    return None if total == 0 else failed / total


def _max_absolute_lateral_error(scenario_dir: str) -> Optional[float]:
    path = os.path.join(scenario_dir, "smpc_debug_steps.jsonl")
    if not os.path.isfile(path):
        return None
    values = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            state = (json.loads(line).get("vehicle_state") or {})
            value = state.get("ey")
            if value is not None and math.isfinite(float(value)):
                values.append(abs(float(value)))
    return max(values) if values else None


def _runtime_control_integrity(scenario_dir: str) -> Dict[str, Any]:
    """Verify that every applied ego command is the raw SMPC command.

    Configuration flags are insufficient evidence on their own: this audit
    reads the step log and fails if a solver bypass, a post-solver replacement,
    or any mismatch between the solver command and the applied command occurs.
    """

    path = os.path.join(scenario_dir, "smpc_debug_steps.jsonl")
    if not os.path.isfile(path):
        return {
            "pass": False,
            "step_count": 0,
            "errors": ["smpc_debug_steps_missing"],
        }

    errors = []
    step_count = 0
    intervention_norms = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            applied = row.get("applied") or {}
            if "u0" not in applied:
                continue
            step_count += 1
            prefix = f"line_{line_number}"
            if bool((row.get("solver_bypass") or {}).get("enabled", False)):
                errors.append(f"{prefix}:solver_bypass_enabled")
            action_filter = applied.get("post_solver_action_filter") or {}
            if bool(action_filter.get("intervention_applied", False)):
                errors.append(f"{prefix}:post_solver_intervention_applied")
            actual = np.asarray(applied.get("u0"), dtype=float).reshape(-1)
            solver = np.asarray(
                applied.get("nominal_solver_u0"), dtype=float
            ).reshape(-1)
            if actual.shape != solver.shape or not np.allclose(
                actual, solver, rtol=0.0, atol=1.0e-9
            ):
                errors.append(f"{prefix}:applied_command_differs_from_solver")
            manifest = (
                (row.get("supervisor_behavioural_authority") or {}).get(
                    "complete_candidate_channel_manifest"
                )
                or {}
            )
            if manifest.get("schema_version") != "implicit_smpc_no_supervisor_manifest_v1":
                errors.append(f"{prefix}:no_supervisor_manifest_missing")
            if manifest.get("authority_enabled") is not False:
                errors.append(f"{prefix}:supervisor_authority_not_false")
            value = applied.get("implicit_filter_intervention_norm")
            if value is not None and math.isfinite(float(value)):
                intervention_norms.append(float(value))

    if step_count == 0:
        errors.append("no_applied_smpc_steps")
    return {
        "pass": bool(step_count > 0 and not errors),
        "step_count": int(step_count),
        "intervention_norm_mean": (
            float(np.mean(intervention_norms)) if intervention_norms else None
        ),
        "intervention_norm_max": (
            float(np.max(intervention_norms)) if intervention_norms else None
        ),
        "errors": errors,
    }


def _contract_valid(contract: Dict[str, Any], setup: Dict[str, Any]) -> bool:
    supervisor = contract.get("supervisor_authority") or {}
    implicit = setup.get("implicit_safety_filter") or {}
    setup_supervisor = setup.get("yield_stop_supervisor") or {}
    authority = setup_supervisor.get("behavioural_authority") or {}
    action_filter = setup_supervisor.get("post_solver_action_filter") or {}
    common_valid = bool(
        contract.get("evaluation_only") is True
        and contract.get("evaluation_thresholds_are_controller_input") is False
        and (contract.get("target_controller") or {}).get("uses_ego_state") is False
        and (contract.get("target_predictor") or {}).get("uses_ego_state") is False
        and supervisor.get("yield_state_machine") is False
        and supervisor.get("rule_solver_bypass") is False
        and supervisor.get("post_solver_action_filter") is False
        and supervisor.get("behavioural_authority_mode") == "off"
        and implicit.get("supervisor_free_smpc_enabled") is True
        and setup_supervisor.get("enabled") is False
        and authority.get("authority_enabled") is False
        and action_filter.get("authority_enabled") is False
    )
    arm = contract.get("experimental_arm")
    if arm == "paper_equivalent_baseline":
        ego_policy = contract.get("ego_policy") or {}
        return bool(
            common_valid
            and contract.get("evaluation_geometry_is_controller_input") is False
            and implicit.get("enabled") is False
            and implicit.get("terminal_collision_constraint") is False
            and setup.get("risk_profile") == "upstream_code"
            and ego_policy.get("horizon_steps") == 10
            and math.isclose(float(ego_policy.get("dt_s", 0.0)), 0.2)
        )
    if arm == "implicit_safety_filter":
        conflict_filter = implicit.get("conflict_zone_filter") or {}
        return bool(
            common_valid
            and implicit.get("enabled") is True
            and implicit.get("terminal_collision_constraint") is True
            and setup.get("risk_profile") == "paper_eps_002"
            and contract.get("evaluation_geometry_is_controller_input")
            is bool(conflict_filter.get("enabled"))
            and conflict_filter.get("state_machine") is False
            and conflict_filter.get("post_solver_action_override") is False
            and conflict_filter.get("distance_trigger_m") is None
        )
    return False


def _settings(scenario_dir: str) -> Dict[str, Any]:
    fine_tune = _load_json(os.path.join(scenario_dir, "fine_tune_config.json")) or {}
    config = fine_tune.get("config") or {}
    return {**DEFAULT_SETTINGS, **(config.get("implicit_filter_evaluation") or {})}


def _footprint_collision_by_dir(results_dir: str) -> Dict[str, Optional[bool]]:
    payload = _load_json(os.path.join(results_dir, "postcarla_trajectory_gate.json"))
    if not payload:
        return {}
    output = {}
    for evaluation in payload.get("evaluations", []):
        scenario_dir = os.path.realpath(str(evaluation.get("scenario_dir", "")))
        pairs = evaluation.get("pair_safety") or []
        output[scenario_dir] = (
            any(bool(pair.get("footprint_collision")) for pair in pairs)
            if pairs
            else None
        )
    return output


def _scenario_dirs(results_dir: str):
    for root, _, files in os.walk(results_dir):
        if {
            "scenario_result.pkl",
            "implicit_safety_filter_contract.json",
        }.issubset(files):
            yield root


def evaluate_scenario_dir(
    scenario_dir: str,
    footprint_collision: Optional[bool],
) -> Dict[str, Any]:
    contract = _load_json(
        os.path.join(scenario_dir, "implicit_safety_filter_contract.json")
    ) or {}
    setup = _load_json(os.path.join(scenario_dir, "smpc_debug_setup.json")) or {}
    summary = _load_json(os.path.join(scenario_dir, "scenario_run_summary.json")) or {}
    with open(os.path.join(scenario_dir, "scenario_result.pkl"), "rb") as handle:
        result = pickle.load(handle)
    ego_keys = [key for key in result if str(key).startswith("ego_")]
    target_keys = [key for key in result if str(key).startswith("target_")]
    if len(ego_keys) != 1 or len(target_keys) != 1:
        raise ValueError(
            f"Expected exactly one ego and target trajectory in {scenario_dir}"
        )
    runtime_integrity = _runtime_control_integrity(scenario_dir)
    verdict = evaluate_three_phase_behavior(
        result[ego_keys[0]]["state_trajectory"],
        result[target_keys[0]]["state_trajectory"],
        contract["evaluation_geometry"],
        settings=_settings(scenario_dir),
        completion_valid=_completion_valid(scenario_dir),
        native_collision=bool(
            ((summary.get("extra") or {}).get("collision_event_count") or 0) > 0
        ),
        footprint_collision=footprint_collision,
        solver_failure_fraction=_solver_failure_fraction(scenario_dir),
        contract_valid=bool(
            _contract_valid(contract, setup) and runtime_integrity["pass"]
        ),
        observed_max_abs_lateral_error_m=(
            _max_absolute_lateral_error(scenario_dir)
        ),
    )
    verdict["safety_and_integrity"]["runtime_control_integrity"] = (
        runtime_integrity
    )
    return {
        "scenario_dir": os.path.abspath(scenario_dir),
        "ego_key": ego_keys[0],
        "target_key": target_keys[0],
        **verdict,
    }


def _write_reports(results_dir: str, evaluations: list) -> Tuple[str, str]:
    overall = "PASS" if evaluations and all(
        item["status"] == "PASS" for item in evaluations
    ) else "FAIL"
    payload = {
        "schema_version": "implicit_smpc_three_phase_report_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results_dir": os.path.abspath(results_dir),
        "overall_status": overall,
        "evaluations": evaluations,
    }
    json_path = os.path.join(results_dir, "implicit_smpc_three_phase_report.json")
    md_path = os.path.join(results_dir, "implicit_smpc_three_phase_report.md")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("# Implicit-SMPC Three-Phase Report\n\n")
        handle.write(f"Overall status: **{overall}**\n\n")
        handle.write("| Run | Proceed before arrival | Slow and yield | Resume after clear | Integrity | Status |\n")
        handle.write("|---|---:|---:|---:|---:|---:|\n")
        for item in evaluations:
            handle.write(
                f"| `{os.path.basename(item['scenario_dir'])}` | "
                f"{item['phase1_proceed_before_target']['pass']} | "
                f"{item['phase2_slow_and_yield']['pass']} | "
                f"{item['phase3_resume_after_target']['pass']} | "
                f"{item['safety_and_integrity']['pass']} | {item['status']} |\n"
            )
            if item["errors"]:
                handle.write(
                    f"\nErrors for `{os.path.basename(item['scenario_dir'])}`: "
                    + "; ".join(item["errors"])
                    + "\n"
                )
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", help="Root directory produced by run_all_scenarios.py")
    args = parser.parse_args()
    results_dir = os.path.abspath(args.results_dir)
    footprint_by_dir = _footprint_collision_by_dir(results_dir)
    scenario_dirs = sorted(_scenario_dirs(results_dir))
    evaluations = [
        evaluate_scenario_dir(
            scenario_dir,
            footprint_by_dir.get(os.path.realpath(scenario_dir)),
        )
        for scenario_dir in scenario_dirs
    ]
    paths = _write_reports(results_dir, evaluations)
    overall = "PASS" if evaluations and all(
        item["status"] == "PASS" for item in evaluations
    ) else "FAIL"
    print(f"Implicit-SMPC three-phase evaluation: {overall}")
    print(f"JSON report: {paths[0]}")
    print(f"Markdown report: {paths[1]}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
