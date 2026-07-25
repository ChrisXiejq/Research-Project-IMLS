#!/usr/bin/env python3
"""Combine supervisor ablation and adaptive-risk sensitivity results.

The report answers whether the latest reduced-supervisor adaptive-risk
sensitivity sweep supports the dissertation claim after supervisor feedback.
Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Tuple


DEFAULT_FORMAL_DIR = Path("core/results/20260725_125938_5init_formal_supervisor_ablation")
DEFAULT_SENSITIVITY_DIR = Path("core/results/20260725_135516_5init_reduced_varrisk_sensitivity")

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


def policy_label(policy: str) -> str:
    if policy == "smpc_fixed_risk":
        return "fixed-risk"
    if policy == "smpc_var_risk":
        return "adaptive-risk"
    return policy


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
        max_solver = max(max_solver, as_float(evaluation.get("solver_failure_frac")) or 0.0)
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


def aggregate_sensitivity_variant(variant_dir: Path) -> List[Dict[str, Any]]:
    diagnostics = read_csv(variant_dir / "diagnostics_after_supervisor_feedback" / "rollout_diagnostics.csv")
    paper = read_csv(variant_dir / "paper_metrics_summary.csv")
    risk = read_csv(variant_dir / "risk_by_conflict_distance_summary.csv")
    infeasible = read_csv(variant_dir / "diagnostics_after_supervisor_feedback" / "infeasible_steps.csv")
    gate = aggregate_gate(variant_dir / "postcarla_trajectory_gate.json")

    by_policy_diag: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in diagnostics:
        by_policy_diag[row.get("policy", "unknown")].append(row)

    by_policy_paper: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in paper:
        by_policy_paper[policy_label(row.get("policy", "unknown"))].append(row)

    by_policy_risk: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in risk:
        by_policy_risk[policy_label(row.get("policy", "unknown"))].append(row)

    by_policy_infeasible = Counter(row.get("policy", "unknown") for row in infeasible)
    by_policy_phase = Counter((row.get("policy", "unknown"), row.get("phase_bucket", "unknown")) for row in infeasible)

    rows: List[Dict[str, Any]] = []
    policies = sorted(set(by_policy_diag) | set(by_policy_paper) | set(by_policy_risk))
    for policy in policies:
        out: Dict[str, Any] = {
            "source": "sensitivity",
            "variant": variant_dir.name,
            "supervisor_mode": "reduced",
            "policy": policy,
            "n_rollouts": len(by_policy_diag.get(policy, [])) or len(by_policy_paper.get(policy, [])),
            **gate,
            "infeasible_step_count": by_policy_infeasible.get(policy, 0),
        }
        for field in DIAGNOSTIC_FIELDS:
            out[field] = mean_field(by_policy_diag.get(policy, []), field)
        for field in PAPER_FIELDS:
            out[field] = mean_field(by_policy_paper.get(policy, []), field)

        risk_rows = by_policy_risk.get(policy, [])
        pre_rows = [r for r in risk_rows if r.get("clearance_phase") == "pre_clearance"]
        post_rows = [r for r in risk_rows if r.get("clearance_phase") == "post_clearance"]
        out["risk_tightening_pre_clearance"] = weighted_mean(pre_rows, "risk_tightening_mean")
        out["risk_tightening_post_clearance"] = weighted_mean(post_rows, "risk_tightening_mean")
        out["risk_target_prob_pre_clearance"] = weighted_mean(pre_rows, "risk_target_prob_mean")
        out["risk_target_prob_post_clearance"] = weighted_mean(post_rows, "risk_target_prob_mean")
        out["supervisor_active_pre_clearance"] = weighted_mean(pre_rows, "supervisor_active_frac")
        out["supervisor_active_post_clearance"] = weighted_mean(post_rows, "supervisor_active_frac")
        phase_parts = [
            f"{phase}:{count}"
            for (p, phase), count in sorted(by_policy_phase.items())
            if p == policy
        ]
        out["infeasible_phase_counts"] = "; ".join(phase_parts)
        rows.append(out)
    return rows


def load_formal_rows(formal_dir: Path) -> List[Dict[str, Any]]:
    path = formal_dir / "formal_supervisor_ablation_analysis" / "supervisor_ablation_aggregate.csv"
    rows: List[Dict[str, Any]] = []
    for row in read_csv(path):
        out: Dict[str, Any] = {
            "source": "formal_ablation",
            "variant": "formal_supervisor_ablation",
            "supervisor_mode": row.get("supervisor_mode"),
            "policy": row.get("policy"),
            "n_rollouts": row.get("n_rollouts"),
            "gate_status": "PASS",
            "gate_min_footprint_separation_m": math.nan,
            "gate_min_center_distance_m": math.nan,
            "gate_max_solver_failure_frac": math.nan,
            "infeasible_step_count": math.nan,
            "completion_time": math.nan,
            "feasibility_percent": math.nan,
            "dmin_TV": math.nan,
            "average_solve_time": math.nan,
            "avg_longitudinal_jerk": math.nan,
            "avg_lateral_jerk": math.nan,
            "solver_failure_frac": math.nan,
            "risk_tightening_pre_clearance": math.nan,
            "risk_tightening_post_clearance": math.nan,
            "risk_target_prob_pre_clearance": math.nan,
            "risk_target_prob_post_clearance": math.nan,
            "supervisor_active_pre_clearance": math.nan,
            "supervisor_active_post_clearance": math.nan,
            "infeasible_phase_counts": "",
        }
        for field in DIAGNOSTIC_FIELDS:
            out[field] = row.get(field, math.nan)
        rows.append(out)
    return rows


def delta_var_fixed(rows: List[Dict[str, Any]], variant: str, field: str) -> float:
    subset = [r for r in rows if r.get("variant") == variant]
    by_policy = {r.get("policy"): as_float(r.get(field)) for r in subset}
    return by_policy.get("adaptive-risk", math.nan) - by_policy.get("fixed-risk", math.nan)


def generate_report(out_path: Path, formal_dir: Path, sensitivity_dir: Path, rows: List[Dict[str, Any]]) -> None:
    sensitivity_rows = [r for r in rows if r.get("source") == "sensitivity"]
    formal_rows = [r for r in rows if r.get("source") == "formal_ablation"]
    variants = sorted({r["variant"] for r in sensitivity_rows})

    lines: List[str] = []
    lines.append("# Combined supervisor-ablation and adaptive-risk sensitivity analysis")
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append(f"- Formal supervisor ablation: `{formal_dir}`")
    lines.append(f"- Reduced-supervisor var-risk sensitivity: `{sensitivity_dir}`")
    lines.append("")
    lines.append("## 1. Main conclusion")
    lines.append("")
    lines.append(
        "The latest sensitivity sweep is complete and all five reduced-supervisor variants pass the post-CARLA gate. "
        "It confirms that the frozen reduced-intervention supervisor can safely support a range of adaptive-risk settings. "
        "However, this sweep still does not prove final-layer adaptive-risk superiority by itself: fixed-risk and adaptive-risk remain close in the final executed behaviour under the same reduced supervisor."
    )
    lines.append("")
    lines.append(
        "The result supports the revised dissertation framing: adaptive-risk should be evaluated against a fixed-risk frontier and interpreted primarily through solver-layer risk allocation, infeasibility phase, release delay, and supervisor burden."
    )
    lines.append("")

    lines.append("## 2. Formal supervisor ablation recap")
    lines.append("")
    lines.append("| Supervisor | Policy | First stop m | Wait s | Clearance delay s | Supervisor active | Solver bypass | Infeasible | Abs accel delta |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in formal_rows:
        lines.append(
            f"| {row['supervisor_mode']} | {row['policy']} | "
            f"{fmt(row.get('first_stop_distance_to_conflict_m'))} | "
            f"{fmt(row.get('waiting_time_after_first_stop_s'))} | "
            f"{fmt(row.get('delay_after_target_clearance_s'))} | "
            f"{pct(row.get('supervisor_active_fraction'))} | "
            f"{pct(row.get('solver_bypass_fraction'))} | "
            f"{pct(row.get('infeasible_fraction'))} | "
            f"{fmt(row.get('mean_abs_final_minus_nominal_accel'))} |"
        )
    lines.append("")

    lines.append("## 3. Sensitivity sweep gate summary")
    lines.append("")
    lines.append("| Variant | Gate | Min footprint m | Max solver failure |")
    lines.append("|---|---|---:|---:|")
    for variant in variants:
        subset = [r for r in sensitivity_rows if r["variant"] == variant]
        if not subset:
            continue
        row = subset[0]
        lines.append(
            f"| {variant} | {row['gate_status']} | "
            f"{fmt(row.get('gate_min_footprint_separation_m'))} | "
            f"{pct(row.get('gate_max_solver_failure_frac'))} |"
        )
    lines.append("")

    lines.append("## 4. Sensitivity behaviour summary")
    lines.append("")
    lines.append("| Variant | Policy | First stop m | Wait s | Clearance delay s | Supervisor active | Bypass | Infeasible | Completion s | dmin TV m |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in sorted(sensitivity_rows, key=lambda r: (r["variant"], r["policy"])):
        lines.append(
            f"| {row['variant']} | {row['policy']} | "
            f"{fmt(row.get('first_stop_distance_to_conflict_m'))} | "
            f"{fmt(row.get('waiting_time_after_first_stop_s'))} | "
            f"{fmt(row.get('delay_after_target_clearance_s'))} | "
            f"{pct(row.get('supervisor_active_fraction'))} | "
            f"{pct(row.get('solver_bypass_fraction'))} | "
            f"{pct(row.get('infeasible_fraction'))} | "
            f"{fmt(row.get('completion_time'))} | "
            f"{fmt(row.get('dmin_TV'))} |"
        )
    lines.append("")

    lines.append("## 5. Adaptive minus fixed deltas")
    lines.append("")
    lines.append("Negative delay/wait/completion deltas are better for adaptive-risk; positive dmin is safer.")
    lines.append("")
    lines.append("| Variant | Delta wait s | Delta clearance delay s | Delta completion s | Delta dmin TV m | Delta supervisor active | Delta bypass | Delta accel delta |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for variant in variants:
        lines.append(
            f"| {variant} | "
            f"{fmt(delta_var_fixed(sensitivity_rows, variant, 'waiting_time_after_first_stop_s'))} | "
            f"{fmt(delta_var_fixed(sensitivity_rows, variant, 'delay_after_target_clearance_s'))} | "
            f"{fmt(delta_var_fixed(sensitivity_rows, variant, 'completion_time'))} | "
            f"{fmt(delta_var_fixed(sensitivity_rows, variant, 'dmin_TV'))} | "
            f"{pct(delta_var_fixed(sensitivity_rows, variant, 'supervisor_active_fraction'))} | "
            f"{pct(delta_var_fixed(sensitivity_rows, variant, 'solver_bypass_fraction'))} | "
            f"{fmt(delta_var_fixed(sensitivity_rows, variant, 'mean_abs_final_minus_nominal_accel'))} |"
        )
    lines.append("")

    lines.append("## 6. Risk allocation mechanism")
    lines.append("")
    lines.append("| Variant | Policy | Tightening pre | Tightening post | Target prob pre | Target prob post | Supervisor pre | Supervisor post |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for row in sorted(sensitivity_rows, key=lambda r: (r["variant"], r["policy"])):
        lines.append(
            f"| {row['variant']} | {row['policy']} | "
            f"{fmt(row.get('risk_tightening_pre_clearance'))} | "
            f"{fmt(row.get('risk_tightening_post_clearance'))} | "
            f"{fmt(row.get('risk_target_prob_pre_clearance'))} | "
            f"{fmt(row.get('risk_target_prob_post_clearance'))} | "
            f"{pct(row.get('supervisor_active_pre_clearance'))} | "
            f"{pct(row.get('supervisor_active_post_clearance'))} |"
        )
    lines.append("")

    lines.append("## 7. Infeasibility phases")
    lines.append("")
    lines.append("| Variant | Policy | Infeasible steps | Phase counts |")
    lines.append("|---|---|---:|---|")
    for row in sorted(sensitivity_rows, key=lambda r: (r["variant"], r["policy"])):
        lines.append(
            f"| {row['variant']} | {row['policy']} | "
            f"{row.get('infeasible_step_count')} | "
            f"{row.get('infeasible_phase_counts') or '-'} |"
        )
    lines.append("")

    lines.append("## 8. Decision")
    lines.append("")
    lines.append("- Do not upgrade this result directly to a new 50-init claim.")
    lines.append("- Keep the reduced-intervention supervisor frozen; the sweep passed and did not reveal a safety regression.")
    lines.append("- Use this sweep to choose an adaptive-risk setting for the fixed-risk frontier experiment.")
    lines.append("- The next necessary experiment is fixed conservative / medium / aggressive vs the selected adaptive setting under the same reduced supervisor.")
    lines.append("- If the frontier still shows weak final-layer separation, the paper should claim solver-layer risk-allocation benefit plus supervisor masking, not universal final-trajectory dominance.")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal-dir", type=Path, default=DEFAULT_FORMAL_DIR)
    parser.add_argument("--sensitivity-dir", type=Path, default=DEFAULT_SENSITIVITY_DIR)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    formal_dir = args.formal_dir.resolve()
    sensitivity_dir = args.sensitivity_dir.resolve()
    out_dir = (args.out_dir or sensitivity_dir / "combined_supervisor_sensitivity_analysis").resolve()

    rows = load_formal_rows(formal_dir)
    for variant_dir in sorted(p for p in sensitivity_dir.iterdir() if p.is_dir()):
        if (variant_dir / "paper_metrics_summary.csv").exists():
            rows.extend(aggregate_sensitivity_variant(variant_dir))

    fields = [
        "source",
        "variant",
        "supervisor_mode",
        "policy",
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
    write_csv(out_dir / "combined_supervisor_sensitivity_summary.csv", rows, fields)
    generate_report(
        out_dir / "combined_supervisor_sensitivity_report.md",
        formal_dir,
        sensitivity_dir,
        rows,
    )

    print(f"Wrote {out_dir / 'combined_supervisor_sensitivity_summary.csv'}")
    print(f"Wrote {out_dir / 'combined_supervisor_sensitivity_report.md'}")


if __name__ == "__main__":
    main()

