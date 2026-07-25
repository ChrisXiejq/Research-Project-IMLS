#!/usr/bin/env python3
"""Generate a fixed-risk frontier report for the give-way experiment.

The frontier run stores each arm in its own subdirectory:
- fixed_aggressive
- fixed_medium
- fixed_conservative
- adaptive_floor_weak

This script aggregates the post-CARLA gate, paper metrics, supervisor
diagnostics, risk-by-phase summaries, and infeasibility phases into a single
Markdown/CSV report.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List


DEFAULT_RESULT_DIR = Path("core/results/20260725_000000_5init_fixed_risk_frontier")

VARIANT_ORDER = [
    "fixed_aggressive",
    "fixed_medium",
    "fixed_conservative",
    "adaptive_floor_weak",
    "adaptive_severity_high_gain",
]

DIAGNOSTIC_FIELDS = [
    "first_stop_distance_to_conflict_m",
    "waiting_time_after_first_stop_s",
    "delay_after_target_clearance_s",
    "supervisor_active_fraction",
    "solver_bypass_fraction",
    "infeasible_fraction",
    "mean_abs_final_minus_nominal_accel",
    "mean_abs_final_minus_nominal_accel_when_active",
]

PAPER_FIELDS = [
    "completion_time",
    "feasibility_percent",
    "dmin_TV",
    "average_solve_time",
    "avg_longitudinal_jerk",
    "avg_lateral_jerk",
    "solver_failure_frac",
]


def as_float(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return math.nan
    return out if math.isfinite(out) else math.nan


def fmt(value: Any, digits: int = 3) -> str:
    num = as_float(value)
    if not math.isfinite(num):
        return "nan"
    return f"{num:.{digits}f}"


def pct(value: Any) -> str:
    num = as_float(value)
    if not math.isfinite(num):
        return "nan"
    return f"{100.0 * num:.1f}%"


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def mean_field(rows: List[Dict[str, Any]], field: str) -> float:
    vals = [as_float(row.get(field)) for row in rows]
    vals = [v for v in vals if math.isfinite(v)]
    return mean(vals) if vals else math.nan


def weighted_mean(rows: List[Dict[str, str]], field: str, weight_field: str = "n_steps") -> float:
    total = 0.0
    weight = 0.0
    for row in rows:
        value = as_float(row.get(field))
        w = as_float(row.get(weight_field))
        if math.isfinite(value) and math.isfinite(w) and w > 0:
            total += value * w
            weight += w
    return total / weight if weight else math.nan


def variant_label(name: str) -> str:
    return {
        "fixed_aggressive": "fixed-risk aggressive",
        "fixed_medium": "fixed-risk medium",
        "fixed_conservative": "fixed-risk conservative",
        "adaptive_floor_weak": "adaptive-risk floor_weak",
        "adaptive_severity_high_gain": "adaptive-risk severity_high_gain",
    }.get(name, name)


def method_group(name: str) -> str:
    return "adaptive-risk" if name.startswith("adaptive_") else "fixed-risk"


def aggregate_gate(gate_path: Path) -> Dict[str, Any]:
    if not gate_path.exists():
        return {
            "gate_status": "missing",
            "gate_min_footprint_separation_m": math.nan,
            "gate_min_center_distance_m": math.nan,
            "gate_max_solver_failure_frac": math.nan,
        }
    data = json.loads(gate_path.read_text())
    min_foot = math.inf
    min_center = math.inf
    max_solver = 0.0
    for evaluation in data.get("evaluations", []):
        solver_failure = as_float(evaluation.get("solver_failure_frac"))
        if math.isfinite(solver_failure):
            max_solver = max(max_solver, solver_failure)
        for pair in evaluation.get("pair_safety", []):
            foot = as_float(pair.get("min_footprint_separation_m"))
            center = as_float(pair.get("min_center_distance_m"))
            if math.isfinite(foot):
                min_foot = min(min_foot, foot)
            if math.isfinite(center):
                min_center = min(min_center, center)
    return {
        "gate_status": data.get("overall_status", "unknown"),
        "gate_min_footprint_separation_m": min_foot if math.isfinite(min_foot) else math.nan,
        "gate_min_center_distance_m": min_center if math.isfinite(min_center) else math.nan,
        "gate_max_solver_failure_frac": max_solver,
    }


def aggregate_variant(variant_dir: Path) -> Dict[str, Any]:
    name = variant_dir.name
    diagnostics = read_csv(variant_dir / "diagnostics_after_supervisor_feedback" / "rollout_diagnostics.csv")
    paper = read_csv(variant_dir / "paper_metrics_summary.csv")
    risk = read_csv(variant_dir / "risk_by_conflict_distance_summary.csv")
    infeasible = read_csv(variant_dir / "diagnostics_after_supervisor_feedback" / "infeasible_steps.csv")

    out: Dict[str, Any] = {
        "variant": name,
        "method": variant_label(name),
        "method_group": method_group(name),
        "n_rollouts": len(diagnostics) or len(paper),
        **aggregate_gate(variant_dir / "postcarla_trajectory_gate.json"),
        "infeasible_step_count": len(infeasible),
    }
    for field in DIAGNOSTIC_FIELDS:
        out[field] = mean_field(diagnostics, field)
    for field in PAPER_FIELDS:
        out[field] = mean_field(paper, field)

    pre_rows = [r for r in risk if r.get("clearance_phase") == "pre_clearance"]
    post_rows = [r for r in risk if r.get("clearance_phase") == "post_clearance"]
    out["risk_tightening_pre_clearance"] = weighted_mean(pre_rows, "risk_tightening_mean")
    out["risk_tightening_post_clearance"] = weighted_mean(post_rows, "risk_tightening_mean")
    out["risk_target_prob_pre_clearance"] = weighted_mean(pre_rows, "risk_target_prob_mean")
    out["risk_target_prob_post_clearance"] = weighted_mean(post_rows, "risk_target_prob_mean")
    out["supervisor_active_pre_clearance"] = weighted_mean(pre_rows, "supervisor_active_frac")
    out["supervisor_active_post_clearance"] = weighted_mean(post_rows, "supervisor_active_frac")

    phases = Counter(row.get("phase_bucket", "unknown") for row in infeasible)
    out["infeasible_phase_counts"] = "; ".join(f"{k}:{v}" for k, v in sorted(phases.items()))
    return out


def dominates(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Conservative Pareto dominance check for fixed vs adaptive.

    Lower is better for delay/completion/infeasibility/supervisor burden;
    higher is better for footprint separation and dmin.
    """
    lower_better = [
        "completion_time",
        "waiting_time_after_first_stop_s",
        "delay_after_target_clearance_s",
        "infeasible_fraction",
        "supervisor_active_fraction",
        "solver_bypass_fraction",
        "mean_abs_final_minus_nominal_accel",
    ]
    higher_better = [
        "gate_min_footprint_separation_m",
        "dmin_TV",
        "feasibility_percent",
    ]

    comparisons = []
    for field in lower_better:
        av = as_float(a.get(field))
        bv = as_float(b.get(field))
        if math.isfinite(av) and math.isfinite(bv):
            comparisons.append((av <= bv + 1.0e-9, av < bv - 1.0e-9))
    for field in higher_better:
        av = as_float(a.get(field))
        bv = as_float(b.get(field))
        if math.isfinite(av) and math.isfinite(bv):
            comparisons.append((av + 1.0e-9 >= bv, av > bv + 1.0e-9))

    return bool(comparisons) and all(ok for ok, _ in comparisons) and any(strict for _, strict in comparisons)


def generate_report(out_path: Path, result_dir: Path, rows: List[Dict[str, Any]]) -> None:
    adaptive_rows = [r for r in rows if r["method_group"] == "adaptive-risk"]
    fixed_rows = [r for r in rows if r["method_group"] == "fixed-risk"]

    lines: List[str] = []
    lines.append("# Fixed-risk frontier analysis")
    lines.append("")
    lines.append(f"Input: `{result_dir}`")
    lines.append("")
    lines.append("## 1. Gate summary")
    lines.append("")
    lines.append("| Variant | Gate | Min footprint m | Max solver failure |")
    lines.append("|---|---|---:|---:|")
    for row in rows:
        lines.append(
            f"| {row['method']} | {row['gate_status']} | "
            f"{fmt(row.get('gate_min_footprint_separation_m'))} | "
            f"{pct(row.get('gate_max_solver_failure_frac'))} |"
        )
    lines.append("")

    lines.append("## 2. Behaviour and supervisor burden")
    lines.append("")
    lines.append("| Variant | First stop m | Wait s | Clearance delay s | Completion s | dmin TV m | Supervisor active | Bypass | Infeasible | Abs accel delta |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        lines.append(
            f"| {row['method']} | "
            f"{fmt(row.get('first_stop_distance_to_conflict_m'))} | "
            f"{fmt(row.get('waiting_time_after_first_stop_s'))} | "
            f"{fmt(row.get('delay_after_target_clearance_s'))} | "
            f"{fmt(row.get('completion_time'))} | "
            f"{fmt(row.get('dmin_TV'))} | "
            f"{pct(row.get('supervisor_active_fraction'))} | "
            f"{pct(row.get('solver_bypass_fraction'))} | "
            f"{pct(row.get('infeasible_fraction'))} | "
            f"{fmt(row.get('mean_abs_final_minus_nominal_accel'))} |"
        )
    lines.append("")

    lines.append("## 3. Risk allocation by clearance phase")
    lines.append("")
    lines.append("| Variant | Tightening pre | Tightening post | Target prob pre | Target prob post | Supervisor pre | Supervisor post |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        lines.append(
            f"| {row['method']} | "
            f"{fmt(row.get('risk_tightening_pre_clearance'))} | "
            f"{fmt(row.get('risk_tightening_post_clearance'))} | "
            f"{fmt(row.get('risk_target_prob_pre_clearance'))} | "
            f"{fmt(row.get('risk_target_prob_post_clearance'))} | "
            f"{pct(row.get('supervisor_active_pre_clearance'))} | "
            f"{pct(row.get('supervisor_active_post_clearance'))} |"
        )
    lines.append("")

    lines.append("## 4. Infeasibility phases")
    lines.append("")
    lines.append("| Variant | Infeasible steps | Phase counts |")
    lines.append("|---|---:|---|")
    for row in rows:
        lines.append(
            f"| {row['method']} | {row.get('infeasible_step_count')} | "
            f"{row.get('infeasible_phase_counts') or '-'} |"
        )
    lines.append("")

    lines.append("## 5. Frontier decision")
    lines.append("")
    if not adaptive_rows or not fixed_rows:
        lines.append("Frontier decision unavailable because adaptive or fixed rows are missing.")
    else:
        for adaptive in adaptive_rows:
            dominating = [fixed for fixed in fixed_rows if dominates(fixed, adaptive)]
            dominated_fixed = [fixed for fixed in fixed_rows if dominates(adaptive, fixed)]
            if dominating:
                lines.append(
                    f"- `{adaptive['method']}` is Pareto-dominated by: "
                    + ", ".join(f"`{row['method']}`" for row in dominating)
                    + ". Do not claim final-layer superiority from this setting."
                )
            else:
                lines.append(
                    f"- `{adaptive['method']}` is not Pareto-dominated by the fixed-risk frontier under the measured metrics."
                )
            if dominated_fixed:
                lines.append(
                    f"  It Pareto-dominates: "
                    + ", ".join(f"`{row['method']}`" for row in dominated_fixed)
                    + "."
                )
            else:
                lines.append(
                    "  It does not strictly dominate a fixed-risk baseline across all tracked metrics; interpret any advantage as a trade-off, not universal dominance."
                )
    lines.append("")
    lines.append("Paper-safe interpretation:")
    lines.append("")
    lines.append(
        "Use this frontier to decide whether adaptive-risk provides a favourable safety-performance trade-off. "
        "If adaptive-risk is not dominated and has a clear mechanism-level phase-aware risk allocation, it supports the revised dissertation claim. "
        "If it is dominated or final-layer differences remain weak, keep the claim at solver-layer contribution plus supervisor masking."
    )
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", type=Path, default=DEFAULT_RESULT_DIR)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    result_dir = args.result_dir.resolve()
    out_dir = (args.out_dir or result_dir / "fixed_risk_frontier_analysis").resolve()

    rows: List[Dict[str, Any]] = []
    for name in VARIANT_ORDER:
        variant_dir = result_dir / name
        if variant_dir.is_dir():
            rows.append(aggregate_variant(variant_dir))

    if not rows:
        raise SystemExit(f"No fixed-risk frontier variant directories found under {result_dir}")

    fields = [
        "variant",
        "method",
        "method_group",
        "n_rollouts",
        "gate_status",
        "gate_min_footprint_separation_m",
        "gate_min_center_distance_m",
        "gate_max_solver_failure_frac",
        *DIAGNOSTIC_FIELDS,
        *PAPER_FIELDS,
        "risk_tightening_pre_clearance",
        "risk_tightening_post_clearance",
        "risk_target_prob_pre_clearance",
        "risk_target_prob_post_clearance",
        "supervisor_active_pre_clearance",
        "supervisor_active_post_clearance",
        "infeasible_step_count",
        "infeasible_phase_counts",
    ]
    write_csv(out_dir / "fixed_risk_frontier_summary.csv", rows, fields)
    generate_report(out_dir / "fixed_risk_frontier_report.md", result_dir, rows)
    print(f"Wrote {out_dir / 'fixed_risk_frontier_summary.csv'}")
    print(f"Wrote {out_dir / 'fixed_risk_frontier_report.md'}")


if __name__ == "__main__":
    main()

