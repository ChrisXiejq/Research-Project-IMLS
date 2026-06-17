#!/usr/bin/env python3
"""Pre-CARLA sanity check for the UK give-way intersection scenario.

This script intentionally avoids CARLA, TensorFlow, Gurobi, and NumPy.  It reads
the same scenario JSON and intersection CSV used by the CARLA runner, then checks
whether the simplified geometry is consistent with:

1. unsignalised traffic control,
2. UK left-hand lane offsets,
3. a turning ego vehicle yielding to an oncoming straight target vehicle.

If gymnasium is installed, the same logic is also exposed through a small
Gymnasium-compatible environment class.  The command-line validation does not
require gymnasium.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import gymnasium as gym
    from gymnasium import spaces
except Exception:  # pragma: no cover - optional dependency
    gym = None
    spaces = None


Point = Tuple[float, float]


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    yaw_deg: float


@dataclass(frozen=True)
class RouteGeometry:
    role: str
    traffic_role: str
    path: List[Point]
    nominal_speed: float
    obey_traffic_lights: bool


@dataclass(frozen=True)
class ConflictReport:
    conflict_point: Point
    ego_distance_to_conflict: float
    target_distance_to_conflict: float
    ego_ttc_s: float
    target_ttc_s: float
    target_arrives_first: bool
    time_gap_s: float
    no_yield_min_distance_m: float
    give_way_min_distance_m: float


def load_intersection(intersection_csv: str) -> List[Tuple[Pose, Pose]]:
    routes: List[Tuple[Pose, Pose]] = []
    with open(intersection_csv, "r", encoding="utf-8") as f:
        for line in f:
            if "#" in line or not line.strip():
                continue
            data = [part.strip() for part in line.split(",")]
            routes.append(
                (
                    Pose(float(data[0]), float(data[1]), float(data[2])),
                    Pose(float(data[3]), float(data[4]), float(data[5])),
                )
            )
    return routes


def transform_pose(raw_pose: Pose, left_offset: float, longitudinal_offset: float) -> Point:
    """Replicate run_intersection_scenario.get_intersection_transform XY logic."""
    yaw_rad = math.radians(raw_pose.yaw_deg)
    x = raw_pose.x + longitudinal_offset * math.cos(yaw_rad)
    y = raw_pose.y + longitudinal_offset * math.sin(yaw_rad)

    left_dir_yaw = yaw_rad - math.pi / 2.0
    x += left_offset * math.cos(left_dir_yaw)
    y += left_offset * math.sin(left_dir_yaw)
    return (x, y)


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def polyline_length(path: Sequence[Point]) -> float:
    return sum(distance(a, b) for a, b in zip(path[:-1], path[1:]))


def path_point_at_distance(path: Sequence[Point], s: float) -> Point:
    if s <= 0.0:
        return path[0]

    remaining = s
    for a, b in zip(path[:-1], path[1:]):
        seg_len = distance(a, b)
        if seg_len <= 1e-9:
            continue
        if remaining <= seg_len:
            alpha = remaining / seg_len
            return (a[0] + alpha * (b[0] - a[0]), a[1] + alpha * (b[1] - a[1]))
        remaining -= seg_len
    return path[-1]


def distance_along_path_to_point(path: Sequence[Point], point: Point) -> float:
    best_s = 0.0
    best_dist = float("inf")
    s_prefix = 0.0

    for a, b in zip(path[:-1], path[1:]):
        ab = (b[0] - a[0], b[1] - a[1])
        seg_len_sq = ab[0] * ab[0] + ab[1] * ab[1]
        if seg_len_sq <= 1e-12:
            continue
        ap = (point[0] - a[0], point[1] - a[1])
        alpha = max(0.0, min(1.0, (ap[0] * ab[0] + ap[1] * ab[1]) / seg_len_sq))
        proj = (a[0] + alpha * ab[0], a[1] + alpha * ab[1])
        d = distance(proj, point)
        if d < best_dist:
            best_dist = d
            best_s = s_prefix + alpha * math.sqrt(seg_len_sq)
        s_prefix += math.sqrt(seg_len_sq)
    return best_s


def segment_intersection(a: Point, b: Point, c: Point, d: Point) -> Optional[Point]:
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    r = (bx - ax, by - ay)
    s = (dx - cx, dy - cy)
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) < 1e-9:
        return None
    qmp = (cx - ax, cy - ay)
    t = (qmp[0] * s[1] - qmp[1] * s[0]) / denom
    u = (qmp[0] * r[1] - qmp[1] * r[0]) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (ax + t * r[0], ay + t * r[1])
    return None


def first_polyline_intersection(path_a: Sequence[Point], path_b: Sequence[Point]) -> Optional[Point]:
    for a0, a1 in zip(path_a[:-1], path_a[1:]):
        for b0, b1 in zip(path_b[:-1], path_b[1:]):
            point = segment_intersection(a0, a1, b0, b1)
            if point is not None:
                return point
    return None


def nearest_polyline_midpoint(path_a: Sequence[Point], path_b: Sequence[Point]) -> Point:
    best_pair = (path_a[0], path_b[0])
    best_dist = float("inf")
    samples = 80
    len_a = polyline_length(path_a)
    len_b = polyline_length(path_b)
    for i in range(samples + 1):
        pa = path_point_at_distance(path_a, len_a * i / samples)
        for j in range(samples + 1):
            pb = path_point_at_distance(path_b, len_b * j / samples)
            d = distance(pa, pb)
            if d < best_dist:
                best_dist = d
                best_pair = (pa, pb)
    return ((best_pair[0][0] + best_pair[1][0]) / 2.0, (best_pair[0][1] + best_pair[1][1]) / 2.0)


def intersection_center(intersection: Sequence[Tuple[Pose, Pose]]) -> Point:
    xs: List[float] = []
    ys: List[float] = []
    for start, goal in intersection:
        xs.extend([start.x, goal.x])
        ys.extend([start.y, goal.y])
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def build_route_geometry(scenario: Dict, intersection: Sequence[Tuple[Pose, Pose]], vehicle: Dict) -> RouteGeometry:
    start_idx = int(vehicle["intersection_start_node_idx"])
    goal_idx = int(vehicle["intersection_goal_node_idx"])
    raw_start = intersection[start_idx][0]
    raw_goal = intersection[goal_idx][1]

    start = transform_pose(
        raw_start,
        float(vehicle.get("start_left_offset", 0.0)),
        float(vehicle.get("start_longitudinal_offset", 0.0)),
    )
    goal = transform_pose(
        raw_goal,
        float(vehicle.get("goal_left_offset", 0.0)),
        float(vehicle.get("goal_longitudinal_offset", 0.0)),
    )

    if start_idx == goal_idx:
        path = [start, goal]
    else:
        path = [start, intersection_center(intersection), goal]

    return RouteGeometry(
        role=str(vehicle.get("role", "")),
        traffic_role=str(vehicle.get("traffic_role", "")),
        path=path,
        nominal_speed=float(vehicle.get("nominal_speed", vehicle.get("init_speed", 0.0))),
        obey_traffic_lights=bool(vehicle.get("obey_traffic_lights", False)),
    )


def simulate_min_distance(
    ego_path: Sequence[Point],
    target_path: Sequence[Point],
    ego_speed: float,
    target_speed: float,
    ego_wait_s: float = 0.0,
    dt: float = 0.05,
    horizon_s: float = 8.0,
) -> float:
    min_dist = float("inf")
    for k in range(int(horizon_s / dt) + 1):
        t = k * dt
        ego_s = max(0.0, t - ego_wait_s) * ego_speed
        target_s = t * target_speed
        ego_pos = path_point_at_distance(ego_path, ego_s)
        target_pos = path_point_at_distance(target_path, target_s)
        min_dist = min(min_dist, distance(ego_pos, target_pos))
    return min_dist


def validate_scenario(scenario_path: str, safety_time_gap_s: float = 2.0) -> Tuple[List[str], List[str], ConflictReport]:
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario = json.load(f)

    scenario_dir = os.path.dirname(os.path.abspath(scenario_path))
    intersection_path = os.path.join(scenario_dir, scenario["carla_params"]["intersection_csv_loc"])
    intersection = load_intersection(intersection_path)

    vehicles = scenario["vehicle_params"]
    ego_vehicle = next(v for v in vehicles if v.get("role") == "ego")
    target_vehicle = next(v for v in vehicles if v.get("role") == "target")

    ego = build_route_geometry(scenario, intersection, ego_vehicle)
    target = build_route_geometry(scenario, intersection, target_vehicle)

    conflict = first_polyline_intersection(ego.path, target.path)
    if conflict is None:
        conflict = nearest_polyline_midpoint(ego.path, target.path)

    ego_s_conflict = distance_along_path_to_point(ego.path, conflict)
    target_s_conflict = distance_along_path_to_point(target.path, conflict)
    ego_ttc = ego_s_conflict / max(ego.nominal_speed, 1e-6)
    target_ttc = target_s_conflict / max(target.nominal_speed, 1e-6)
    time_gap = ego_ttc - target_ttc
    target_arrives_first = target_ttc < ego_ttc

    no_yield_min_dist = simulate_min_distance(
        ego.path,
        target.path,
        ego.nominal_speed,
        target.nominal_speed,
        ego_wait_s=0.0,
    )
    ego_wait_s = max(0.0, safety_time_gap_s - time_gap)
    give_way_min_dist = simulate_min_distance(
        ego.path,
        target.path,
        ego.nominal_speed,
        target.nominal_speed,
        ego_wait_s=ego_wait_s,
    )

    report = ConflictReport(
        conflict_point=conflict,
        ego_distance_to_conflict=ego_s_conflict,
        target_distance_to_conflict=target_s_conflict,
        ego_ttc_s=ego_ttc,
        target_ttc_s=target_ttc,
        target_arrives_first=target_arrives_first,
        time_gap_s=time_gap,
        no_yield_min_distance_m=no_yield_min_dist,
        give_way_min_distance_m=give_way_min_dist,
    )

    passed: List[str] = []
    failed: List[str] = []

    def check(condition: bool, label: str) -> None:
        if condition:
            passed.append(label)
        else:
            failed.append(label)

    carla_params = scenario.get("carla_params", {})
    pred_params = scenario.get("prediction_params", {})
    check(str(carla_params.get("traffic_control", "")).lower() == "unsignalised", "scenario declares unsignalised traffic control")
    check(str(carla_params.get("side_of_road", "")).lower() == "left", "scenario declares UK left-hand traffic")
    check(not bool(pred_params.get("render_traffic_lights", False)), "traffic lights are not rendered for the default predictor input")
    check(not ego.obey_traffic_lights and not target.obey_traffic_lights, "ego and target do not obey traffic-light overrides in this scenario")
    check(ego.traffic_role == "turning_give_way_vehicle", "ego is marked as the turning give-way vehicle")
    check(target.traffic_role == "priority_oncoming_straight", "target is marked as the priority oncoming straight vehicle")
    check(target_arrives_first, "target reaches the conflict point before ego under nominal speeds")
    check(0.0 < time_gap < safety_time_gap_s, "nominal timing creates a meaningful give-way interaction")
    check(give_way_min_dist > no_yield_min_dist, "simple give-way delay increases the minimum separation")

    return passed, failed, report


if gym is not None:

    class UKGiveWayKinematicEnv(gym.Env):
        """Tiny Gymnasium wrapper for pre-CARLA UK give-way timing checks."""

        metadata = {"render_modes": []}

        def __init__(self, scenario_path: str, safety_time_gap_s: float = 2.0):
            super().__init__()
            self.scenario_path = scenario_path
            self.safety_time_gap_s = safety_time_gap_s
            self.action_space = spaces.Discrete(2)  # 0: no yield, 1: give-way delay
            self.observation_space = spaces.Box(low=-1000.0, high=1000.0, shape=(4,), dtype=float)
            self._report: Optional[ConflictReport] = None

        def reset(self, *, seed: Optional[int] = None, options: Optional[Dict] = None):
            super().reset(seed=seed)
            _, _, self._report = validate_scenario(self.scenario_path, self.safety_time_gap_s)
            obs = [
                self._report.ego_ttc_s,
                self._report.target_ttc_s,
                self._report.time_gap_s,
                self._report.no_yield_min_distance_m,
            ]
            return obs, {}

        def step(self, action: int):
            if self._report is None:
                _, _, self._report = validate_scenario(self.scenario_path, self.safety_time_gap_s)
            min_dist = (
                self._report.no_yield_min_distance_m
                if action == 0
                else self._report.give_way_min_distance_m
            )
            reward = min_dist
            obs = [
                self._report.ego_ttc_s,
                self._report.target_ttc_s,
                self._report.time_gap_s,
                min_dist,
            ]
            return obs, reward, True, False, {"min_distance_m": min_dist}


def print_report(passed: Iterable[str], failed: Iterable[str], report: ConflictReport) -> None:
    print("Pre-CARLA UK give-way validation")
    print("=" * 38)
    for item in passed:
        print(f"PASS: {item}")
    for item in failed:
        print(f"FAIL: {item}")

    print("\nConflict timing")
    print(f"- conflict_point: ({report.conflict_point[0]:.2f}, {report.conflict_point[1]:.2f}) m")
    print(f"- ego_distance_to_conflict: {report.ego_distance_to_conflict:.2f} m")
    print(f"- target_distance_to_conflict: {report.target_distance_to_conflict:.2f} m")
    print(f"- ego_ttc: {report.ego_ttc_s:.2f} s")
    print(f"- target_ttc: {report.target_ttc_s:.2f} s")
    print(f"- ego_minus_target_ttc: {report.time_gap_s:.2f} s")
    print(f"- no_yield_min_distance: {report.no_yield_min_distance_m:.2f} m")
    print(f"- give_way_min_distance: {report.give_way_min_distance_m:.2f} m")


def main() -> int:
    default_scenario = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "carla",
        "scenarios",
        "scenario_uk_give_way.json",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=default_scenario, help="Path to scenario JSON.")
    parser.add_argument("--safety_time_gap_s", type=float, default=2.0, help="Desired minimum time gap after the target clears the conflict point.")
    args = parser.parse_args()

    passed, failed, report = validate_scenario(args.scenario, args.safety_time_gap_s)
    print_report(passed, failed, report)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
