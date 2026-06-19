#!/usr/bin/env python3
"""Post-CARLA trajectory safety gate.

This script checks what the pre-CARLA gate cannot check: the actual closed-loop
CARLA trajectories produced by each policy.  It replays ``scenario_result.pkl``
with conservative oriented-rectangle vehicle footprints and fails if required
SMPC policies collide with any target vehicle.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from precarla_validate_uk_give_way import (
    FOOTPRINT_SAFETY_MARGIN_M,
    polygon_distance,
    rectangle_corners,
    vehicle_dimensions,
)


Point = Tuple[float, float]


@dataclass(frozen=True)
class PairSafety:
    target_key: str
    min_center_distance_m: float
    min_center_time_s: float
    min_center_step: int
    min_footprint_separation_m: float
    min_footprint_time_s: float
    min_footprint_step: int
    footprint_collision: bool
    collision_first_time_s: Optional[float]
    collision_last_time_s: Optional[float]
    collision_duration_s: float
    collision_steps: int


@dataclass(frozen=True)
class YieldRule:
    target_key: str
    conflict_point_xy: Point
    conflict_radius_m: float
    ego_enter_time_s: Optional[float]
    ego_exit_time_s: Optional[float]
    target_enter_time_s: Optional[float]
    target_exit_time_s: Optional[float]
    target_clears_before_ego_enters: Optional[bool]


@dataclass(frozen=True)
class PolicySafety:
    scenario_dir: str
    policy: str
    status: str
    is_required_policy: bool
    completion_valid: Optional[bool]
    solver_failure_frac: Optional[float]
    collision_envelope_logged: Optional[bool]
    ego_key: Optional[str]
    target_keys: List[str]
    pair_safety: List[PairSafety]
    yield_rules: List[YieldRule]
    errors: List[str]
    warnings: List[str]


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_policy(dirname: str) -> str:
    base = os.path.basename(dirname.rstrip("/"))
    if "_ego_init_" not in base:
        return base
    tail = base.split("_ego_init_", 1)[1]
    return tail.split("_", 1)[1]


def _actor_index(actor_key: str) -> Optional[int]:
    try:
        return int(actor_key.rsplit("_", 1)[1])
    except Exception:
        return None


def _vehicle_type_for_key(actor_key: str, rollout_config: Optional[Dict[str, Any]]) -> str:
    idx = _actor_index(actor_key)
    if idx is None or not rollout_config:
        return ""
    vehicles = rollout_config.get("vehicle_params") or []
    if 0 <= idx < len(vehicles):
        return str(vehicles[idx].get("vehicle_type", ""))
    return ""


def _completion_valid(scenario_dir: str) -> Optional[bool]:
    payload = _load_json(os.path.join(scenario_dir, "smpc_completion.json"))
    if not payload:
        return None
    comp = payload.get("completion") or {}
    lateral_ok = bool(comp.get("lateral_ok", False))
    by_s = bool(comp.get("completed_by_s_margin", False))
    by_goal = bool(comp.get("completed_by_goal_dist", False))
    return bool(lateral_ok and (by_s or by_goal))


def _solver_failure_frac(scenario_dir: str) -> Optional[float]:
    path = os.path.join(scenario_dir, "smpc_debug_steps.jsonl")
    if not os.path.isfile(path):
        return None
    total = 0
    failed = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            optimal = (row.get("solver") or {}).get("optimal")
            if optimal is not None and not bool(optimal):
                failed += 1
    return None if total == 0 else failed / total


def _collision_envelope_logged(scenario_dir: str) -> Optional[bool]:
    payload = _load_json(os.path.join(scenario_dir, "smpc_debug_setup.json"))
    if not payload:
        return None
    return "collision_envelope" in payload


def _interp_state(traj: np.ndarray, times: np.ndarray) -> np.ndarray:
    out = np.zeros((len(times), traj.shape[1]), dtype=float)
    out[:, 0] = times
    for col in range(1, traj.shape[1]):
        out[:, col] = np.interp(times, traj[:, 0], traj[:, col])
    return out


def _angle_lerp_unwrapped(traj: np.ndarray, times: np.ndarray) -> np.ndarray:
    yaw = np.unwrap(traj[:, 3])
    return np.interp(times, traj[:, 0], yaw)


def _common_time_grid(ego: np.ndarray, target: np.ndarray, default_dt: float = 0.05) -> np.ndarray:
    start = max(float(ego[0, 0]), float(target[0, 0]))
    end = min(float(ego[-1, 0]), float(target[-1, 0]))
    if end < start:
        return np.array([], dtype=float)
    dts = []
    for traj in (ego, target):
        if len(traj) > 1:
            diffs = np.diff(traj[:, 0])
            diffs = diffs[diffs > 1e-9]
            if len(diffs):
                dts.append(float(np.median(diffs)))
    dt = min(dts) if dts else default_dt
    dt = max(1e-3, min(dt, default_dt))
    return np.arange(start, end + 0.5 * dt, dt)


def _trajectory_conflict_point(ego: np.ndarray, target: np.ndarray) -> Point:
    ego_xy = ego[:, 1:3]
    target_xy = target[:, 1:3]
    # Trajectories are short in this gate, so the direct pairwise distance matrix
    # is clearer than a dependency on scipy/k-d trees.
    diffs = ego_xy[:, None, :] - target_xy[None, :, :]
    dist2 = np.sum(diffs * diffs, axis=2)
    ego_idx, target_idx = np.unravel_index(int(np.argmin(dist2)), dist2.shape)
    point = 0.5 * (ego_xy[ego_idx] + target_xy[target_idx])
    return float(point[0]), float(point[1])


def _zone_interval(traj: np.ndarray, center: Point, radius_m: float) -> Tuple[Optional[float], Optional[float]]:
    center_xy = np.asarray(center, dtype=float)
    dist = np.linalg.norm(traj[:, 1:3] - center_xy, axis=1)
    inside = np.flatnonzero(dist <= radius_m)
    if len(inside) == 0:
        return None, None
    return float(traj[inside[0], 0]), float(traj[inside[-1], 0])


def _yield_rule(
    target_key: str,
    ego_payload: Dict[str, Any],
    target_payload: Dict[str, Any],
    conflict_radius_m: float,
    clearance_tolerance_s: float,
) -> YieldRule:
    ego = np.asarray(ego_payload["state_trajectory"], dtype=float)
    target = np.asarray(target_payload["state_trajectory"], dtype=float)
    conflict_point = _trajectory_conflict_point(ego, target)
    ego_enter, ego_exit = _zone_interval(ego, conflict_point, conflict_radius_m)
    target_enter, target_exit = _zone_interval(target, conflict_point, conflict_radius_m)
    if ego_enter is None or target_exit is None:
        target_first = None
    else:
        target_first = bool(target_exit <= ego_enter + clearance_tolerance_s)
    return YieldRule(
        target_key=target_key,
        conflict_point_xy=conflict_point,
        conflict_radius_m=float(conflict_radius_m),
        ego_enter_time_s=ego_enter,
        ego_exit_time_s=ego_exit,
        target_enter_time_s=target_enter,
        target_exit_time_s=target_exit,
        target_clears_before_ego_enters=target_first,
    )


def _pair_safety(
    ego_key: str,
    ego_payload: Dict[str, Any],
    target_key: str,
    target_payload: Dict[str, Any],
    rollout_config: Optional[Dict[str, Any]],
    footprint_margin_m: float,
) -> PairSafety:
    ego = np.asarray(ego_payload["state_trajectory"], dtype=float)
    target = np.asarray(target_payload["state_trajectory"], dtype=float)
    times = _common_time_grid(ego, target)
    if len(times) == 0:
        raise ValueError(f"No overlapping trajectory time range for {ego_key} and {target_key}")

    ego_i = _interp_state(ego, times)
    target_i = _interp_state(target, times)
    ego_i[:, 3] = _angle_lerp_unwrapped(ego, times)
    target_i[:, 3] = _angle_lerp_unwrapped(target, times)

    center_dist = np.linalg.norm(ego_i[:, 1:3] - target_i[:, 1:3], axis=1)
    min_center_idx = int(np.argmin(center_dist))

    ego_length, ego_width = vehicle_dimensions(_vehicle_type_for_key(ego_key, rollout_config))
    target_length, target_width = vehicle_dimensions(_vehicle_type_for_key(target_key, rollout_config))

    footprint_seps: List[float] = []
    collision_idxs: List[int] = []
    for i, (ego_state, target_state) in enumerate(zip(ego_i, target_i)):
        ego_poly = rectangle_corners(
            (float(ego_state[1]), float(ego_state[2])),
            float(ego_state[3]),
            ego_length,
            ego_width,
            footprint_margin_m,
        )
        target_poly = rectangle_corners(
            (float(target_state[1]), float(target_state[2])),
            float(target_state[3]),
            target_length,
            target_width,
            footprint_margin_m,
        )
        sep = float(polygon_distance(ego_poly, target_poly))
        footprint_seps.append(sep)
        if sep <= 1e-9:
            collision_idxs.append(i)

    footprint_arr = np.asarray(footprint_seps, dtype=float)
    min_footprint_idx = int(np.argmin(footprint_arr))
    if collision_idxs:
        first = collision_idxs[0]
        last = collision_idxs[-1]
        collision_first_time = float(times[first])
        collision_last_time = float(times[last])
        if len(times) > 1:
            dt = float(np.median(np.diff(times)))
        else:
            dt = 0.0
        collision_duration = float((last - first + 1) * dt)
    else:
        collision_first_time = None
        collision_last_time = None
        collision_duration = 0.0

    return PairSafety(
        target_key=target_key,
        min_center_distance_m=float(center_dist[min_center_idx]),
        min_center_time_s=float(times[min_center_idx]),
        min_center_step=min_center_idx,
        min_footprint_separation_m=float(footprint_arr[min_footprint_idx]),
        min_footprint_time_s=float(times[min_footprint_idx]),
        min_footprint_step=min_footprint_idx,
        footprint_collision=bool(collision_idxs),
        collision_first_time_s=collision_first_time,
        collision_last_time_s=collision_last_time,
        collision_duration_s=collision_duration,
        collision_steps=len(collision_idxs),
    )


def _list_scenario_dirs(results_dir: str) -> List[str]:
    out = []
    for name in sorted(os.listdir(results_dir)):
        path = os.path.join(results_dir, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "scenario_result.pkl")):
            out.append(path)
    return out


def _load_postcarla_gate_config(results_dir: str) -> Dict[str, Any]:
    root_configs = _load_json(os.path.join(results_dir, "applied_tuning_configs.json")) or {}
    for metadata in root_configs.values():
        config = metadata.get("config") if isinstance(metadata, dict) else None
        if isinstance(config, dict) and isinstance(config.get("postcarla_gate"), dict):
            return dict(config["postcarla_gate"])

    for scenario_dir in _list_scenario_dirs(results_dir):
        metadata = _load_json(os.path.join(scenario_dir, "fine_tune_config.json")) or {}
        config = metadata.get("config") if isinstance(metadata, dict) else None
        if isinstance(config, dict) and isinstance(config.get("postcarla_gate"), dict):
            return dict(config["postcarla_gate"])
    return {}


def evaluate_scenario_dir(
    scenario_dir: str,
    required_policies: Sequence[str],
    footprint_margin_m: float,
    conflict_radius_m: float,
    clearance_tolerance_s: float,
    require_collision_envelope: bool,
    max_solver_failure_frac: float,
) -> PolicySafety:
    policy = _parse_policy(scenario_dir)
    is_required = policy in set(required_policies)
    errors: List[str] = []
    warnings: List[str] = []
    pair_results: List[PairSafety] = []
    yield_rules: List[YieldRule] = []

    rollout_config = _load_json(os.path.join(scenario_dir, "scenario_rollout_config.json"))
    completion_valid = _completion_valid(scenario_dir)
    solver_failure = _solver_failure_frac(scenario_dir)
    envelope_logged = _collision_envelope_logged(scenario_dir)

    with open(os.path.join(scenario_dir, "scenario_result.pkl"), "rb") as f:
        result = pickle.load(f)

    ego_keys = [key for key in result if key.startswith("ego_")]
    target_keys = [key for key in result if key.startswith("target_")]
    ego_key = ego_keys[0] if ego_keys else None

    if not ego_key:
        warnings.append("No ego trajectory found; likely a non-standard baseline.")
    if not target_keys:
        warnings.append("No target trajectories found; skipping collision replay.")

    if ego_key and target_keys:
        for target_key in target_keys:
            pair = _pair_safety(
                ego_key,
                result[ego_key],
                target_key,
                result[target_key],
                rollout_config,
                footprint_margin_m,
            )
            pair_results.append(pair)
            if pair.footprint_collision:
                message = (
                    f"Footprint collision with {target_key}: "
                    f"{pair.collision_duration_s:.2f}s, "
                    f"center dmin={pair.min_center_distance_m:.3f}m"
                )
                if is_required:
                    errors.append(message)
                else:
                    warnings.append(message)
            yield_rule = _yield_rule(
                target_key,
                result[ego_key],
                result[target_key],
                conflict_radius_m,
                clearance_tolerance_s,
            )
            yield_rules.append(yield_rule)
            if yield_rule.target_clears_before_ego_enters is False:
                message = (
                    f"Turning vehicle did not give way to {target_key}: "
                    f"target_exit={yield_rule.target_exit_time_s:.2f}s, "
                    f"ego_enter={yield_rule.ego_enter_time_s:.2f}s"
                )
                if is_required:
                    errors.append(message)
                else:
                    warnings.append(message)

    if is_required:
        if completion_valid is not True:
            errors.append(f"Required policy did not complete validly: completion_valid={completion_valid}")
        if solver_failure is not None and solver_failure > max_solver_failure_frac:
            errors.append(
                f"Required policy solver_failure_frac={solver_failure:.3f} exceeds "
                f"{max_solver_failure_frac:.3f}"
            )
        if require_collision_envelope and envelope_logged is not True:
            errors.append("Required policy did not log collision_envelope; server may be running stale code/config.")
    else:
        if completion_valid is False:
            warnings.append("Policy did not complete validly.")
        if solver_failure is not None and solver_failure > max_solver_failure_frac:
            warnings.append(
                f"solver_failure_frac={solver_failure:.3f} exceeds {max_solver_failure_frac:.3f}"
            )

    status = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return PolicySafety(
        scenario_dir=scenario_dir,
        policy=policy,
        status=status,
        is_required_policy=is_required,
        completion_valid=completion_valid,
        solver_failure_frac=solver_failure,
        collision_envelope_logged=envelope_logged,
        ego_key=ego_key,
        target_keys=target_keys,
        pair_safety=pair_results,
        yield_rules=yield_rules,
        errors=errors,
        warnings=warnings,
    )


def write_reports(results_dir: str, evaluations: List[PolicySafety], gate_settings: Dict[str, Any]) -> Tuple[str, str]:
    json_path = os.path.join(results_dir, "postcarla_trajectory_gate.json")
    md_path = os.path.join(results_dir, "postcarla_trajectory_gate.md")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results_dir": results_dir,
        "overall_status": "FAIL" if any(e.status == "FAIL" for e in evaluations) else (
            "WARN" if any(e.status == "WARN" for e in evaluations) else "PASS"
        ),
        "gate_settings": gate_settings,
        "evaluations": [asdict(e) for e in evaluations],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Post-CARLA Trajectory Gate\n\n")
        f.write(f"- Generated: `{payload['generated_at']}`\n")
        f.write(f"- Results dir: `{results_dir}`\n")
        f.write(f"- Overall status: `{payload['overall_status']}`\n\n")
        f.write("## Gate Settings\n\n")
        for key, value in sorted(gate_settings.items()):
            f.write(f"- `{key}`: `{value}`\n")
        f.write("\n## Policy Results\n\n")
        f.write("| Status | Policy | Required | Completion | Solver Failure | Collision Envelope | Target | Center dmin | Footprint collision | Yield OK | Collision duration | Notes |\n")
        f.write("|---|---|---:|---|---:|---|---|---:|---|---|---:|---|\n")
        for evaluation in evaluations:
            if evaluation.pair_safety:
                pairs = evaluation.pair_safety
            else:
                pairs = [None]
            yield_by_target = {rule.target_key: rule for rule in evaluation.yield_rules}
            notes = "; ".join(evaluation.errors + evaluation.warnings)
            for pair in pairs:
                yield_ok = ""
                if pair is not None and pair.target_key in yield_by_target:
                    yield_ok = str(yield_by_target[pair.target_key].target_clears_before_ego_enters)
                f.write(
                    f"| {evaluation.status} | {evaluation.policy} | {evaluation.is_required_policy} | "
                    f"{evaluation.completion_valid} | "
                    f"{'' if evaluation.solver_failure_frac is None else f'{evaluation.solver_failure_frac:.3f}'} | "
                    f"{evaluation.collision_envelope_logged} | "
                    f"{'' if pair is None else pair.target_key} | "
                    f"{'' if pair is None else f'{pair.min_center_distance_m:.3f}'} | "
                    f"{'' if pair is None else pair.footprint_collision} | "
                    f"{yield_ok} | "
                    f"{'' if pair is None else f'{pair.collision_duration_s:.2f}'} | "
                    f"{notes} |\n"
                )
    return json_path, md_path


def print_summary(evaluations: List[PolicySafety], report_paths: Tuple[str, str]) -> None:
    overall = "FAIL" if any(e.status == "FAIL" for e in evaluations) else (
        "WARN" if any(e.status == "WARN" for e in evaluations) else "PASS"
    )
    print("Post-CARLA trajectory gate")
    print("=" * 32)
    for evaluation in evaluations:
        print(
            f"{evaluation.status}: {os.path.basename(evaluation.scenario_dir)} "
            f"(policy={evaluation.policy}, required={evaluation.is_required_policy})"
        )
        for pair in evaluation.pair_safety:
            print(
                f"  target={pair.target_key} center_dmin={pair.min_center_distance_m:.3f}m "
                f"footprint_collision={pair.footprint_collision} "
                f"collision_duration={pair.collision_duration_s:.2f}s"
            )
        for rule in evaluation.yield_rules:
            print(
                f"  yield target={rule.target_key} "
                f"target_exit={rule.target_exit_time_s} ego_enter={rule.ego_enter_time_s} "
                f"target_first={rule.target_clears_before_ego_enters}"
            )
        for error in evaluation.errors:
            print(f"  ERROR: {error}")
        for warning in evaluation.warnings:
            print(f"  WARN: {warning}")
    print()
    print(f"Overall: {overall}")
    print(f"JSON report: {report_paths[0]}")
    print(f"Markdown report: {report_paths[1]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", help="CARLA timestamp results directory.")
    parser.add_argument(
        "--required-policies",
        default=None,
        help="Comma-separated policies that must complete and avoid footprint collision.",
    )
    parser.add_argument("--footprint-margin-m", type=float, default=None)
    parser.add_argument(
        "--conflict-radius-m",
        type=float,
        default=None,
        help="Radius around the inferred conflict point used for turning-gives-way checks.",
    )
    parser.add_argument(
        "--clearance-tolerance-s",
        type=float,
        default=None,
        help="Allowed timing tolerance for target clearing the conflict zone before ego enters.",
    )
    parser.add_argument("--max-solver-failure-frac", type=float, default=None)
    parser.add_argument(
        "--allow-missing-collision-envelope",
        action="store_true",
        help="Do not fail required policies when smpc_debug_setup.json lacks collision_envelope.",
    )
    args = parser.parse_args()

    results_dir = os.path.abspath(args.results_dir)
    gate_config = _load_postcarla_gate_config(results_dir)
    required_policy_value = args.required_policies
    if required_policy_value is None:
        required_policy_value = ",".join(gate_config.get("required_policies", ["smpc_var_risk", "smpc_fixed_risk"]))
    required_policies = [p.strip() for p in required_policy_value.split(",") if p.strip()]
    footprint_margin_m = (
        args.footprint_margin_m
        if args.footprint_margin_m is not None
        else float(gate_config.get("footprint_margin_m", FOOTPRINT_SAFETY_MARGIN_M))
    )
    conflict_radius_m = (
        args.conflict_radius_m
        if args.conflict_radius_m is not None
        else float(gate_config.get("conflict_radius_m", 4.0))
    )
    clearance_tolerance_s = (
        args.clearance_tolerance_s
        if args.clearance_tolerance_s is not None
        else float(gate_config.get("clearance_tolerance_s", 0.2))
    )
    max_solver_failure_frac = (
        args.max_solver_failure_frac
        if args.max_solver_failure_frac is not None
        else float(gate_config.get("max_solver_failure_frac", 0.05))
    )
    require_collision_envelope = (
        bool(gate_config.get("require_collision_envelope_log", True))
        and not args.allow_missing_collision_envelope
    )
    gate_settings = {
        "required_policies": required_policies,
        "footprint_margin_m": footprint_margin_m,
        "conflict_radius_m": conflict_radius_m,
        "clearance_tolerance_s": clearance_tolerance_s,
        "max_solver_failure_frac": max_solver_failure_frac,
        "require_collision_envelope_log": require_collision_envelope,
        "source": "fine_tune_config" if gate_config else "script_defaults",
    }
    scenario_dirs = _list_scenario_dirs(results_dir)
    evaluations = [
        evaluate_scenario_dir(
            scenario_dir,
            required_policies=required_policies,
            footprint_margin_m=footprint_margin_m,
            conflict_radius_m=conflict_radius_m,
            clearance_tolerance_s=clearance_tolerance_s,
            require_collision_envelope=require_collision_envelope,
            max_solver_failure_frac=max_solver_failure_frac,
        )
        for scenario_dir in scenario_dirs
    ]
    report_paths = write_reports(results_dir, evaluations, gate_settings)
    print_summary(evaluations, report_paths)
    return 1 if any(e.status == "FAIL" for e in evaluations) else 0


if __name__ == "__main__":
    raise SystemExit(main())
