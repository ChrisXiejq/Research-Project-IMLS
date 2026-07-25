#!/usr/bin/env python3
"""Summarise the v12 target-speed difficulty sweep."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ARMS = (
    "smpc_fixed_aggressive",
    "smpc_fixed_medium",
    "smpc_fixed_conservative",
    "smpc_adaptive_floor_weak",
)


def _read_first_csv(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else {}


def _read_gate(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    out = {"gate_status": data.get("overall_status")}
    evaluations = data.get("evaluations") or []
    if evaluations:
        ev = evaluations[0]
        out["solver_failure_frac_gate"] = ev.get("solver_failure_frac")
        pair = (ev.get("pair_safety") or [{}])[0]
        out["min_center_distance_m"] = pair.get("min_center_distance_m")
        out["min_footprint_separation_m"] = pair.get("min_footprint_separation_m")
        out["footprint_collision"] = pair.get("footprint_collision")
        yield_rules = ev.get("yield_rules") or []
        if yield_rules:
            out["target_clears_before_ego_enters"] = yield_rules[0].get(
                "target_clears_before_ego_enters"
            )
    return out


def _risk_metric(path: Path, bucket: str, phase: str, key: str) -> str:
    if not path.exists():
        return ""
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("bucket") == bucket and row.get("clearance_phase") == phase:
                return row.get(key, "")
    return ""


def _speed_from_label(label: str) -> str:
    prefix = "target_speed_"
    if label.startswith(prefix):
        return label[len(prefix) :].replace("p", ".")
    return ""


def collect(results_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for speed_dir in sorted(results_dir.glob("target_speed_*")):
        if not speed_dir.is_dir():
            continue
        for arm in ARMS:
            arm_dir = speed_dir / arm
            if not arm_dir.exists():
                continue
            metrics = _read_first_csv(arm_dir / "paper_metrics_summary.csv")
            rollout = _read_first_csv(
                arm_dir / "diagnostics_after_supervisor_feedback" / "rollout_diagnostics.csv"
            )
            gate = _read_gate(arm_dir / "postcarla_trajectory_gate.json")
            risk_path = arm_dir / "risk_by_conflict_distance_summary.csv"
            row = {
                "difficulty": speed_dir.name,
                "target_speed": _speed_from_label(speed_dir.name),
                "arm": arm,
                "policy": metrics.get("policy", ""),
                "gate_status": gate.get("gate_status", ""),
                "footprint_collision": gate.get("footprint_collision", ""),
                "target_clears_before_ego_enters": gate.get(
                    "target_clears_before_ego_enters", ""
                ),
                "completion_time": metrics.get("completion_time", ""),
                "completion_valid": metrics.get("completion_valid", ""),
                "dmin_TV": metrics.get("dmin_TV", ""),
                "min_center_distance_m": gate.get("min_center_distance_m", ""),
                "min_footprint_separation_m": gate.get(
                    "min_footprint_separation_m", ""
                ),
                "first_stop_distance_to_conflict_m": rollout.get(
                    "first_stop_distance_to_conflict_m", ""
                ),
                "waiting_time_after_first_stop_s": rollout.get(
                    "waiting_time_after_first_stop_s", ""
                ),
                "delay_after_target_clearance_s": rollout.get(
                    "delay_after_target_clearance_s", ""
                ),
                "supervisor_active_fraction": rollout.get(
                    "supervisor_active_fraction", ""
                ),
                "solver_bypass_fraction": rollout.get("solver_bypass_fraction", ""),
                "infeasible_fraction": rollout.get("infeasible_fraction", ""),
                "mean_abs_final_minus_nominal_accel": rollout.get(
                    "mean_abs_final_minus_nominal_accel", ""
                ),
                "critical_pre_tightening": _risk_metric(
                    risk_path, "critical", "pre_clearance", "risk_tightening_mean"
                ),
                "near_pre_tightening": _risk_metric(
                    risk_path, "near", "pre_clearance", "risk_tightening_mean"
                ),
                "near_post_tightening": _risk_metric(
                    risk_path, "near", "post_clearance", "risk_tightening_mean"
                ),
            }
            rows.append(row)
    return rows


def write_outputs(results_dir: Path, rows: list[dict]) -> None:
    csv_path = results_dir / "v12_target_speed_sweep_summary.csv"
    md_path = results_dir / "v12_target_speed_sweep_report.md"
    if not rows:
        raise RuntimeError(f"No sweep rows found under {results_dir}")

    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# v12 Target-Speed Difficulty Sweep Report\n\n")
        f.write(
            "This report keeps the v12 shared planner/supervisor baseline fixed "
            "and varies only target speed.\n\n"
        )
        f.write(
            "| Target speed | Arm | Gate | First stop | Completion | dmin | "
            "Footprint sep | Supervisor | Infeasible | Critical pre tight | Near post tight |\n"
        )
        f.write("| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n")
        for row in rows:
            f.write(
                "| {target_speed} | {arm} | {gate_status} | "
                "{first_stop_distance_to_conflict_m} | {completion_time} | "
                "{dmin_TV} | {min_footprint_separation_m} | "
                "{supervisor_active_fraction} | {infeasible_fraction} | "
                "{critical_pre_tightening} | {near_post_tightening} |\n".format(**row)
            )
        f.write("\n## Interpretation Checklist\n\n")
        f.write("- Does fixed aggressive fail safety or increase supervisor burden first?\n")
        f.write("- Does fixed conservative remain safe but become slower or delayed?\n")
        f.write(
            "- Does adaptive/floor_weak combine conservative-like safety with "
            "medium/aggressive-like efficiency?\n"
        )
        f.write(
            "- Does adaptive keep pre-clearance tightening and post-clearance relaxation "
            "across the difficulty range?\n"
        )

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    args = parser.parse_args()
    write_outputs(args.results_dir, collect(args.results_dir))


if __name__ == "__main__":
    main()
