#!/usr/bin/env python3
"""Summarise v12 claim-driven sweep / ablation result directories."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


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


def collect(results_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for difficulty_dir in sorted(p for p in results_dir.iterdir() if p.is_dir()):
        if difficulty_dir.name in {"tuning_configs", "_ego_init_01"}:
            continue
        for arm_dir in sorted(p for p in difficulty_dir.iterdir() if p.is_dir()):
            metrics_path = arm_dir / "paper_metrics_summary.csv"
            gate_path = arm_dir / "postcarla_trajectory_gate.json"
            if not metrics_path.exists() and not gate_path.exists():
                continue
            metrics = _read_first_csv(metrics_path)
            rollout = _read_first_csv(
                arm_dir / "diagnostics_after_supervisor_feedback" / "rollout_diagnostics.csv"
            )
            gate = _read_gate(gate_path)
            risk_path = arm_dir / "risk_by_conflict_distance_summary.csv"
            rows.append(
                {
                    "difficulty": difficulty_dir.name,
                    "arm": arm_dir.name,
                    "policy": metrics.get("policy", ""),
                    "gate_status": gate.get("gate_status", ""),
                    "footprint_collision": gate.get("footprint_collision", ""),
                    "target_clears_before_ego_enters": gate.get(
                        "target_clears_before_ego_enters", ""
                    ),
                    "completion_time": metrics.get("completion_time", ""),
                    "completion_valid": metrics.get("completion_valid", ""),
                    "solver_failure_frac": metrics.get(
                        "solver_failure_frac", gate.get("solver_failure_frac_gate", "")
                    ),
                    "feasibility_percent": metrics.get("feasibility_percent", ""),
                    "forced_reference_linearization_frac": metrics.get(
                        "forced_reference_linearization_frac", ""
                    ),
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
            )
    return rows


def write_outputs(results_dir: Path, rows: list[dict], title: str) -> None:
    if not rows:
        raise RuntimeError(f"No claim-sweep rows found under {results_dir}")

    csv_path = results_dir / "v12_claim_sweep_summary.csv"
    md_path = results_dir / "v12_claim_sweep_report.md"
    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write("| Difficulty | Arm | Gate | Completion | Solver fail | dmin | ")
        f.write("Footprint sep | Supervisor | Infeasible | Critical pre | Near post |\n")
        f.write("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n")
        for row in rows:
            f.write(
                "| {difficulty} | {arm} | {gate_status} | {completion_time} | "
                "{solver_failure_frac} | {min_center_distance_m} | "
                "{min_footprint_separation_m} | {supervisor_active_fraction} | "
                "{infeasible_fraction} | {critical_pre_tightening} | "
                "{near_post_tightening} |\n".format(**row)
            )
        f.write("\n## Interpretation Checklist\n\n")
        f.write("- Does the fixed-risk frontier show a safety/feasibility/efficiency trade-off?\n")
        f.write("- Does full adaptive beat phase-blind / no-pre / no-post variants on the intended mechanism?\n")
        f.write("- Are any differences still explainable by shared supervisor activity?\n")

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--title", default="v12 Claim-Driven Sweep Report")
    args = parser.parse_args()
    write_outputs(args.results_dir, collect(args.results_dir), args.title)


if __name__ == "__main__":
    main()
