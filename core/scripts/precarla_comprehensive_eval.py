#!/usr/bin/env python3
"""Comprehensive local pre-CARLA evaluation for the UK give-way scenario.

This is a stricter test battery than ``precarla_validate_uk_give_way.py``.  It
does not replace CARLA, MultiPath, or SMPC, but it catches scenario-design
problems before an expensive CARLA run.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

from precarla_validate_uk_give_way import (
    ConflictReport,
    load_intersection,
    run_gymnasium_check,
    validate_scenario,
)


@dataclass(frozen=True)
class TestOutcome:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class SweepCase:
    ego_speed: float
    target_speed: float
    safety_gap: float
    ego_ttc: float
    target_ttc: float
    time_gap: float
    no_yield_min_distance: float
    give_way_min_distance: float
    status: str


def default_scenario_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "carla",
        "scenarios",
        "scenario_uk_give_way.json",
    )


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def moving_vehicles(scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [v for v in scenario["vehicle_params"] if v.get("role") in {"ego", "target"}]


def get_vehicle(scenario: Dict[str, Any], role: str) -> Dict[str, Any]:
    return next(v for v in scenario["vehicle_params"] if v.get("role") == role)


def modified_scenario_path(base_scenario_path: str, scenario: Dict[str, Any]) -> str:
    scenario_dir = os.path.dirname(os.path.abspath(base_scenario_path))
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="precarla_eval_",
        dir=scenario_dir,
        delete=False,
        encoding="utf-8",
    )
    try:
        json.dump(scenario, tmp)
        tmp.flush()
        return tmp.name
    finally:
        tmp.close()


def run_modified_validation(
    base_scenario_path: str,
    scenario: Dict[str, Any],
    safety_gap: float,
) -> Tuple[List[str], List[str], ConflictReport]:
    tmp_path = modified_scenario_path(base_scenario_path, scenario)
    try:
        return validate_scenario(tmp_path, safety_gap)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def add_outcome(outcomes: List[TestOutcome], condition: bool, name: str, pass_detail: str, fail_detail: str) -> None:
    outcomes.append(TestOutcome(name=name, status="PASS" if condition else "FAIL", detail=pass_detail if condition else fail_detail))


def add_warning(outcomes: List[TestOutcome], condition: bool, name: str, pass_detail: str, warn_detail: str) -> None:
    outcomes.append(TestOutcome(name=name, status="PASS" if condition else "WARN", detail=pass_detail if condition else warn_detail))


def semantic_and_geometry_tests(scenario_path: str, scenario: Dict[str, Any]) -> List[TestOutcome]:
    outcomes: List[TestOutcome] = []
    carla_params = scenario.get("carla_params", {})
    pred_params = scenario.get("prediction_params", {})
    ego = get_vehicle(scenario, "ego")
    target = get_vehicle(scenario, "target")

    intersection_path = os.path.join(
        os.path.dirname(os.path.abspath(scenario_path)),
        carla_params["intersection_csv_loc"],
    )
    intersection = load_intersection(intersection_path)

    add_outcome(
        outcomes,
        str(carla_params.get("traffic_control", "")).lower() == "unsignalised",
        "traffic control",
        "Scenario is explicitly unsignalised.",
        "Scenario is not explicitly unsignalised.",
    )
    add_outcome(
        outcomes,
        str(carla_params.get("side_of_road", "")).lower() == "left",
        "UK left-hand declaration",
        "Scenario declares left-hand traffic.",
        "Scenario does not declare left-hand traffic.",
    )
    add_outcome(
        outcomes,
        not bool(pred_params.get("render_traffic_lights", False)),
        "traffic-light rasterisation",
        "Default predictor input does not include traffic lights.",
        "Default predictor input includes traffic lights.",
    )
    add_outcome(
        outcomes,
        not bool(ego.get("obey_traffic_lights", False)) and not bool(target.get("obey_traffic_lights", False)),
        "traffic-light override",
        "Ego and target do not obey traffic-light overrides in this scenario.",
        "At least one moving vehicle obeys traffic-light overrides.",
    )
    add_outcome(
        outcomes,
        ego.get("traffic_role") == "turning_give_way_vehicle",
        "ego priority role",
        "Ego is marked as the turning give-way vehicle.",
        "Ego is not marked as the turning give-way vehicle.",
    )
    add_outcome(
        outcomes,
        target.get("traffic_role") == "priority_oncoming_straight",
        "target priority role",
        "Target is marked as the priority oncoming straight vehicle.",
        "Target is not marked as the priority oncoming straight vehicle.",
    )
    add_outcome(
        outcomes,
        int(ego["intersection_start_node_idx"]) != int(ego["intersection_goal_node_idx"]),
        "ego turning route",
        "Ego route changes road arm, so it is a turning movement.",
        "Ego route does not change road arm.",
    )
    add_outcome(
        outcomes,
        int(target["intersection_start_node_idx"]) == int(target["intersection_goal_node_idx"]),
        "target straight route",
        "Target route keeps the same road arm, so it is straight-going.",
        "Target route is not straight-going.",
    )

    moving = moving_vehicles(scenario)
    same_left_offsets = all(
        abs(float(v.get("start_left_offset", 0.0)) - float(v.get("goal_left_offset", 0.0))) < 1e-6
        for v in moving
    )
    positive_left_offsets = all(float(v.get("start_left_offset", 0.0)) > 0.0 for v in moving)
    add_outcome(
        outcomes,
        same_left_offsets and positive_left_offsets,
        "left-lane offsets",
        "Moving vehicles use consistent positive local-left lane offsets.",
        "Moving vehicles do not use consistent positive local-left lane offsets.",
    )
    add_warning(
        outcomes,
        len(intersection) == 4,
        "intersection arm count",
        "Intersection file has four directed arms.",
        f"Intersection file has {len(intersection)} arms; expected four for this test.",
    )
    return outcomes


def nominal_timing_tests(report: ConflictReport) -> List[TestOutcome]:
    outcomes: List[TestOutcome] = []
    add_outcome(
        outcomes,
        report.target_arrives_first,
        "nominal right-of-way timing",
        f"Target arrives first: target_ttc={report.target_ttc_s:.2f}s, ego_ttc={report.ego_ttc_s:.2f}s.",
        f"Target does not arrive first: target_ttc={report.target_ttc_s:.2f}s, ego_ttc={report.ego_ttc_s:.2f}s.",
    )
    add_outcome(
        outcomes,
        0.0 < report.time_gap_s < 2.0,
        "nominal interaction strength",
        f"Nominal time gap is meaningful for give-way: {report.time_gap_s:.2f}s.",
        f"Nominal time gap is outside the desired range: {report.time_gap_s:.2f}s.",
    )
    add_outcome(
        outcomes,
        report.give_way_min_distance_m > report.no_yield_min_distance_m,
        "nominal give-way benefit",
        f"Give-way improves min distance from {report.no_yield_min_distance_m:.2f}m to {report.give_way_min_distance_m:.2f}m.",
        f"Give-way does not improve min distance: {report.no_yield_min_distance_m:.2f}m -> {report.give_way_min_distance_m:.2f}m.",
    )
    add_warning(
        outcomes,
        report.no_yield_min_distance_m < 2.5,
        "nominal conflict is non-trivial",
        f"No-yield min distance is tight enough to be a useful test: {report.no_yield_min_distance_m:.2f}m.",
        f"No-yield min distance may be too large to stress SMPC: {report.no_yield_min_distance_m:.2f}m.",
    )
    return outcomes


def gymnasium_tests(scenario_path: str, safety_gap: float) -> List[TestOutcome]:
    ok, messages = run_gymnasium_check(scenario_path, safety_gap)
    detail = " | ".join(messages)
    return [
        TestOutcome(
            name="Gymnasium API and rollout",
            status="PASS" if ok else "FAIL",
            detail=detail,
        )
    ]


def speed_sweep_tests(
    scenario_path: str,
    scenario: Dict[str, Any],
    ego_speeds: Iterable[float],
    target_speeds: Iterable[float],
    safety_gap: float,
) -> Tuple[List[TestOutcome], List[SweepCase]]:
    cases: List[SweepCase] = []
    risky_cases = 0
    risky_improved = 0
    target_first_count = 0

    for ego_speed in ego_speeds:
        for target_speed in target_speeds:
            test_scenario = copy.deepcopy(scenario)
            ego = get_vehicle(test_scenario, "ego")
            target = get_vehicle(test_scenario, "target")
            ego["nominal_speed"] = float(ego_speed)
            target["nominal_speed"] = float(target_speed)
            target["init_speed"] = float(target_speed)
            _, _, report = run_modified_validation(scenario_path, test_scenario, safety_gap)
            target_first_count += int(report.target_arrives_first)
            is_risky = report.target_arrives_first and 0.0 < report.time_gap_s < safety_gap
            improved = report.give_way_min_distance_m > report.no_yield_min_distance_m
            risky_cases += int(is_risky)
            risky_improved += int(is_risky and improved)
            cases.append(
                SweepCase(
                    ego_speed=ego_speed,
                    target_speed=target_speed,
                    safety_gap=safety_gap,
                    ego_ttc=report.ego_ttc_s,
                    target_ttc=report.target_ttc_s,
                    time_gap=report.time_gap_s,
                    no_yield_min_distance=report.no_yield_min_distance_m,
                    give_way_min_distance=report.give_way_min_distance_m,
                    status="PASS" if (not is_risky or improved) else "FAIL",
                )
            )

    outcomes = [
        TestOutcome(
            name="speed sweep target priority",
            status="PASS" if target_first_count >= int(0.8 * len(cases)) else "WARN",
            detail=f"Target arrives first in {target_first_count}/{len(cases)} speed-sweep cases.",
        ),
        TestOutcome(
            name="speed sweep give-way benefit",
            status="PASS" if risky_cases > 0 and risky_improved == risky_cases else "FAIL",
            detail=f"Give-way improves min distance in {risky_improved}/{risky_cases} risky speed-sweep cases.",
        ),
    ]
    return outcomes, cases


def safety_gap_tests(
    scenario_path: str,
    scenario: Dict[str, Any],
    safety_gaps: Iterable[float],
) -> Tuple[List[TestOutcome], List[SweepCase]]:
    cases: List[SweepCase] = []
    previous_min = None
    monotonic = True
    for safety_gap in safety_gaps:
        _, _, report = run_modified_validation(scenario_path, copy.deepcopy(scenario), safety_gap)
        if previous_min is not None and report.give_way_min_distance_m + 1e-6 < previous_min:
            monotonic = False
        previous_min = report.give_way_min_distance_m
        cases.append(
            SweepCase(
                ego_speed=get_vehicle(scenario, "ego")["nominal_speed"],
                target_speed=get_vehicle(scenario, "target")["nominal_speed"],
                safety_gap=safety_gap,
                ego_ttc=report.ego_ttc_s,
                target_ttc=report.target_ttc_s,
                time_gap=report.time_gap_s,
                no_yield_min_distance=report.no_yield_min_distance_m,
                give_way_min_distance=report.give_way_min_distance_m,
                status="PASS",
            )
        )
    return [
        TestOutcome(
            name="safety-gap monotonicity",
            status="PASS" if monotonic else "FAIL",
            detail="Give-way minimum distance is non-decreasing as desired safety gap increases.",
        )
    ], cases


def write_reports(
    output_dir: str,
    scenario_path: str,
    base_passed: List[str],
    base_failed: List[str],
    nominal_report: ConflictReport,
    outcomes: List[TestOutcome],
    speed_cases: List[SweepCase],
    gap_cases: List[SweepCase],
) -> Tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    payload = {
        "scenario_path": scenario_path,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_passed": base_passed,
        "base_failed": base_failed,
        "nominal_report": asdict(nominal_report),
        "outcomes": [asdict(o) for o in outcomes],
        "speed_sweep_cases": [asdict(c) for c in speed_cases],
        "safety_gap_cases": [asdict(c) for c in gap_cases],
    }
    json_path = os.path.join(output_dir, "precarla_comprehensive_eval.json")
    md_path = os.path.join(output_dir, "precarla_comprehensive_eval.md")
    write_json(json_path, payload)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Pre-CARLA Comprehensive Evaluation\n\n")
        f.write(f"- Scenario: `{scenario_path}`\n")
        f.write(f"- Generated: `{payload['generated_at']}`\n\n")
        f.write("## Gate Outcomes\n\n")
        f.write("| Status | Test | Detail |\n|---|---|---|\n")
        for outcome in outcomes:
            f.write(f"| {outcome.status} | {outcome.name} | {outcome.detail} |\n")
        f.write("\n## Nominal Timing\n\n")
        f.write(f"- Conflict point: `{nominal_report.conflict_point}`\n")
        f.write(f"- Ego TTC: `{nominal_report.ego_ttc_s:.2f}s`\n")
        f.write(f"- Target TTC: `{nominal_report.target_ttc_s:.2f}s`\n")
        f.write(f"- Ego minus target TTC: `{nominal_report.time_gap_s:.2f}s`\n")
        f.write(f"- No-yield min distance: `{nominal_report.no_yield_min_distance_m:.2f}m`\n")
        f.write(f"- Give-way min distance: `{nominal_report.give_way_min_distance_m:.2f}m`\n\n")
        f.write("## Speed Sweep\n\n")
        f.write("| Ego Speed | Target Speed | Time Gap | No-Yield Min Dist | Give-Way Min Dist | Status |\n")
        f.write("|---:|---:|---:|---:|---:|---|\n")
        for case in speed_cases:
            f.write(
                f"| {case.ego_speed:.1f} | {case.target_speed:.1f} | {case.time_gap:.2f} | "
                f"{case.no_yield_min_distance:.2f} | {case.give_way_min_distance:.2f} | {case.status} |\n"
            )
        f.write("\n## Safety Gap Sweep\n\n")
        f.write("| Safety Gap | No-Yield Min Dist | Give-Way Min Dist |\n|---:|---:|---:|\n")
        for case in gap_cases:
            f.write(f"| {case.safety_gap:.1f} | {case.no_yield_min_distance:.2f} | {case.give_way_min_distance:.2f} |\n")
    return json_path, md_path


def print_summary(outcomes: List[TestOutcome], report_paths: Tuple[str, str]) -> None:
    fail_count = sum(1 for o in outcomes if o.status == "FAIL")
    warn_count = sum(1 for o in outcomes if o.status == "WARN")
    pass_count = sum(1 for o in outcomes if o.status == "PASS")
    print("Pre-CARLA comprehensive evaluation")
    print("=" * 42)
    for outcome in outcomes:
        print(f"{outcome.status}: {outcome.name} - {outcome.detail}")
    print("\nSummary")
    print(f"- PASS: {pass_count}")
    print(f"- WARN: {warn_count}")
    print(f"- FAIL: {fail_count}")
    print(f"- JSON report: {report_paths[0]}")
    print(f"- Markdown report: {report_paths[1]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=default_scenario_path(), help="Path to scenario JSON.")
    parser.add_argument(
        "--output_dir",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "results",
            "precarla_comprehensive_eval",
        ),
        help="Directory where JSON and Markdown reports are written.",
    )
    parser.add_argument("--safety_gap_s", type=float, default=2.0)
    args = parser.parse_args()

    scenario = load_json(args.scenario)
    base_passed, base_failed, nominal_report = validate_scenario(args.scenario, args.safety_gap_s)

    outcomes: List[TestOutcome] = []
    outcomes.extend(semantic_and_geometry_tests(args.scenario, scenario))
    outcomes.extend(nominal_timing_tests(nominal_report))
    outcomes.extend(gymnasium_tests(args.scenario, args.safety_gap_s))

    speed_outcomes, speed_cases = speed_sweep_tests(
        args.scenario,
        scenario,
        ego_speeds=[5.0, 6.0, 7.0, 8.0, 9.0],
        target_speeds=[9.0, 10.0, 11.0, 12.0, 13.0],
        safety_gap=args.safety_gap_s,
    )
    outcomes.extend(speed_outcomes)

    gap_outcomes, gap_cases = safety_gap_tests(
        args.scenario,
        scenario,
        safety_gaps=[1.0, 1.5, 2.0, 2.5, 3.0],
    )
    outcomes.extend(gap_outcomes)

    if base_failed:
        outcomes.append(
            TestOutcome(
                name="base validator",
                status="FAIL",
                detail="Base validator failures: " + "; ".join(base_failed),
            )
        )
    else:
        outcomes.append(
            TestOutcome(
                name="base validator",
                status="PASS",
                detail=f"Base validator passed {len(base_passed)} checks.",
            )
        )

    report_paths = write_reports(
        args.output_dir,
        args.scenario,
        base_passed,
        base_failed,
        nominal_report,
        outcomes,
        speed_cases,
        gap_cases,
    )
    print_summary(outcomes, report_paths)
    return 1 if any(o.status == "FAIL" for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
