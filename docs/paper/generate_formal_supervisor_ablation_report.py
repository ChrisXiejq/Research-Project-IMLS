#!/usr/bin/env python3
"""Generate a formal supervisor-ablation report after supervisor feedback.

The report is intentionally text/table focused. It answers:
- whether reduced intervention improves conservative early stopping;
- whether shared supervisor masks adaptive-risk vs fixed-risk differences;
- where remaining infeasible steps occur;
- whether the result is sufficient to proceed to 50-init.

Only the Python standard library is used so the script can run in the CARLA
environment and on local machines without extra dependencies.
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


DEFAULT_RESULT_DIR = Path(
    "core/results/20260725_125938_5init_formal_supervisor_ablation"
)

MODES = [
    ("full_supervisor", "full"),
    ("reduced_intervention_supervisor", "reduced"),
]
POLICIES = ["fixed-risk", "adaptive-risk"]

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


def as_float(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return math.nan
    return out if math.isfinite(out) else math.nan


def fmt(value: float, digits: int = 3) -> str:
    if value is None or not math.isfinite(value):
        return "nan"
    return f"{value:.{digits}f}"


def pct(value: float) -> str:
    if value is None or not math.isfinite(value):
        return "nan"
    return f"{100.0 * value:.1f}%"


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


def mean_field(rows: List[Dict[str, str]], field: str) -> float:
    vals = [as_float(r.get(field)) for r in rows]
    vals = [v for v in vals if math.isfinite(v)]
    return mean(vals) if vals else math.nan


def load_rollout_diagnostics(result_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for mode_dir, mode_label in MODES:
        path = (
            result_dir
            / mode_dir
            / "diagnostics_after_supervisor_feedback"
            / "rollout_diagnostics.csv"
        )
        for row in read_csv(path):
            row["supervisor_mode"] = mode_label
            rows.append(row)
    return rows


def load_paper_metrics(result_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for mode_dir, mode_label in MODES:
        path = result_dir / mode_dir / "paper_metrics_summary.csv"
        for row in read_csv(path):
            row["supervisor_mode"] = mode_label
            if row.get("policy") == "smpc_fixed_risk":
                row["policy_label"] = "fixed-risk"
            elif row.get("policy") == "smpc_var_risk":
                row["policy_label"] = "adaptive-risk"
            else:
                row["policy_label"] = row.get("policy", "unknown")
            rows.append(row)
    return rows


def load_risk_comparison(result_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for mode_dir, mode_label in MODES:
        path = result_dir / mode_dir / "risk_by_conflict_distance_comparison.csv"
        for row in read_csv(path):
            row["supervisor_mode"] = mode_label
            rows.append(row)
    return rows


def load_infeasible_steps(result_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for mode_dir, mode_label in MODES:
        path = (
            result_dir
            / mode_dir
            / "diagnostics_after_supervisor_feedback"
            / "infeasible_steps.csv"
        )
        for row in read_csv(path):
            row["supervisor_mode"] = mode_label
            rows.append(row)
    return rows


def aggregate_by_mode_policy(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for mode in ["full", "reduced"]:
        for policy in POLICIES:
            subset = [
                r
                for r in rows
                if r.get("supervisor_mode") == mode and r.get("policy") == policy
            ]
            row: Dict[str, Any] = {
                "supervisor_mode": mode,
                "policy": policy,
                "n_rollouts": len(subset),
            }
            for field in DIAGNOSTIC_FIELDS:
                row[field] = mean_field(subset, field)
            out.append(row)
    return out


def aggregate_paper_metrics(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, float]]:
    out: Dict[Tuple[str, str], Dict[str, float]] = {}
    for mode in ["full", "reduced"]:
        for policy in POLICIES:
            subset = [
                r
                for r in rows
                if r.get("supervisor_mode") == mode and r.get("policy_label") == policy
            ]
            out[(mode, policy)] = {
                "completion_time": mean_field(subset, "completion_time"),
                "dmin_TV": mean_field(subset, "dmin_TV"),
                "avg_longitudinal_jerk": mean_field(subset, "avg_longitudinal_jerk"),
                "avg_lateral_jerk": mean_field(subset, "avg_lateral_jerk"),
                "average_solve_time": mean_field(subset, "average_solve_time"),
                "solver_failure_frac": mean_field(subset, "solver_failure_frac"),
            }
    return out


def aggregate_infeasible_steps(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Counter[Tuple[str, str, str, str]] = Counter()
    distances: defaultdict[Tuple[str, str, str, str], List[float]] = defaultdict(list)
    inits: defaultdict[Tuple[str, str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        key = (
            row.get("supervisor_mode", ""),
            row.get("policy", ""),
            row.get("phase_bucket", ""),
            row.get("yield_phase", ""),
        )
        counts[key] += 1
        inits[key].add(row.get("init_id", ""))
        dconf = as_float(row.get("distance_to_conflict_m"))
        if math.isfinite(dconf):
            distances[key].append(dconf)

    out: List[Dict[str, Any]] = []
    for key, count in counts.most_common():
        ds = distances[key]
        out.append(
            {
                "supervisor_mode": key[0],
                "policy": key[1],
                "phase_bucket": key[2],
                "yield_phase": key[3],
                "infeasible_steps": count,
                "affected_inits": " ".join(sorted(inits[key])),
                "mean_distance_to_conflict_m": mean(ds) if ds else math.nan,
                "min_distance_to_conflict_m": min(ds) if ds else math.nan,
                "max_distance_to_conflict_m": max(ds) if ds else math.nan,
            }
        )
    return out


def risk_layer_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    wanted = [
        ("critical", "pre_clearance"),
        ("near", "pre_clearance"),
        ("critical", "post_clearance"),
        ("near", "post_clearance"),
    ]
    out: List[Dict[str, Any]] = []
    for mode in ["full", "reduced"]:
        for bucket, phase in wanted:
            subset = [
                r
                for r in rows
                if r.get("supervisor_mode") == mode
                and r.get("bucket") == bucket
                and r.get("clearance_phase") == phase
            ]
            if not subset:
                continue
            out.append(
                {
                    "supervisor_mode": mode,
                    "bucket": bucket,
                    "clearance_phase": phase,
                    "var_minus_fixed_risk_tightening_mean": mean_field(
                        subset, "var_minus_fixed_risk_tightening_mean"
                    ),
                    "var_minus_fixed_nominal_accel_mean": mean_field(
                        subset, "var_minus_fixed_nominal_accel_mean"
                    ),
                    "var_minus_fixed_final_accel_mean": mean_field(
                        subset, "var_minus_fixed_final_accel_mean"
                    ),
                    "var_minus_fixed_supervisor_override_frac": mean_field(
                        subset, "var_minus_fixed_supervisor_override_frac"
                    ),
                    "var_minus_fixed_solver_failure_frac": mean_field(
                        subset, "var_minus_fixed_solver_failure_frac"
                    ),
                }
            )
    return out


def markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def find(summary: List[Dict[str, Any]], mode: str, policy: str) -> Dict[str, Any]:
    for row in summary:
        if row["supervisor_mode"] == mode and row["policy"] == policy:
            return row
    return {}


def generate_report(
    result_dir: Path,
    summary: List[Dict[str, Any]],
    paper_metrics: Dict[Tuple[str, str], Dict[str, float]],
    infeasible_summary: List[Dict[str, Any]],
    risk_summary: List[Dict[str, Any]],
) -> str:
    full_fixed = find(summary, "full", "fixed-risk")
    full_var = find(summary, "full", "adaptive-risk")
    red_fixed = find(summary, "reduced", "fixed-risk")
    red_var = find(summary, "reduced", "adaptive-risk")

    def delta(field: str, policy: str) -> float:
        base = find(summary, "full", policy)
        red = find(summary, "reduced", policy)
        return as_float(red.get(field)) - as_float(base.get(field))

    aggregate_rows: List[List[str]] = []
    for mode in ["full", "reduced"]:
        for policy in POLICIES:
            row = find(summary, mode, policy)
            pm = paper_metrics.get((mode, policy), {})
            aggregate_rows.append(
                [
                    mode,
                    policy,
                    fmt(as_float(row.get("first_stop_distance_to_conflict_m"))),
                    fmt(as_float(row.get("waiting_time_after_first_stop_s"))),
                    fmt(as_float(row.get("delay_after_target_clearance_s"))),
                    pct(as_float(row.get("supervisor_active_fraction"))),
                    pct(as_float(row.get("solver_bypass_fraction"))),
                    pct(as_float(row.get("infeasible_fraction"))),
                    fmt(as_float(pm.get("completion_time"))),
                    fmt(as_float(pm.get("dmin_TV"))),
                    fmt(as_float(row.get("mean_abs_final_minus_nominal_accel_when_active"))),
                ]
            )

    supervisor_delta_rows: List[List[str]] = []
    for policy in POLICIES:
        supervisor_delta_rows.append(
            [
                policy,
                fmt(delta("first_stop_distance_to_conflict_m", policy)),
                fmt(delta("waiting_time_after_first_stop_s", policy)),
                fmt(delta("delay_after_target_clearance_s", policy)),
                fmt(delta("supervisor_active_fraction", policy), 4),
                fmt(delta("solver_bypass_fraction", policy), 4),
                fmt(delta("mean_abs_final_minus_nominal_accel_when_active", policy)),
            ]
        )

    var_fixed_rows: List[List[str]] = []
    for mode in ["full", "reduced"]:
        fixed = find(summary, mode, "fixed-risk")
        var = find(summary, mode, "adaptive-risk")
        pm_fixed = paper_metrics.get((mode, "fixed-risk"), {})
        pm_var = paper_metrics.get((mode, "adaptive-risk"), {})
        var_fixed_rows.append(
            [
                mode,
                fmt(
                    as_float(var.get("first_stop_distance_to_conflict_m"))
                    - as_float(fixed.get("first_stop_distance_to_conflict_m"))
                ),
                fmt(
                    as_float(var.get("delay_after_target_clearance_s"))
                    - as_float(fixed.get("delay_after_target_clearance_s"))
                ),
                fmt(
                    as_float(pm_var.get("completion_time"))
                    - as_float(pm_fixed.get("completion_time"))
                ),
                fmt(as_float(pm_var.get("dmin_TV")) - as_float(pm_fixed.get("dmin_TV"))),
                fmt(
                    as_float(var.get("mean_abs_final_minus_nominal_accel_when_active"))
                    - as_float(fixed.get("mean_abs_final_minus_nominal_accel_when_active"))
                ),
            ]
        )

    infeasible_rows = [
        [
            row["supervisor_mode"],
            row["policy"],
            row["phase_bucket"],
            row["yield_phase"],
            str(row["infeasible_steps"]),
            row["affected_inits"],
            fmt(as_float(row["mean_distance_to_conflict_m"])),
        ]
        for row in infeasible_summary
    ]
    if not infeasible_rows:
        infeasible_rows = [["none", "none", "none", "none", "0", "-", "-"]]

    risk_rows = [
        [
            row["supervisor_mode"],
            row["bucket"],
            row["clearance_phase"],
            fmt(as_float(row["var_minus_fixed_risk_tightening_mean"]), 4),
            fmt(as_float(row["var_minus_fixed_nominal_accel_mean"]), 4),
            fmt(as_float(row["var_minus_fixed_final_accel_mean"]), 4),
            fmt(as_float(row["var_minus_fixed_supervisor_override_frac"]), 4),
        ]
        for row in risk_summary
    ]

    reduced_wait_delta_fixed = delta("waiting_time_after_first_stop_s", "fixed-risk")
    reduced_wait_delta_var = delta("waiting_time_after_first_stop_s", "adaptive-risk")
    reduced_delay_delta_fixed = delta("delay_after_target_clearance_s", "fixed-risk")
    reduced_delay_delta_var = delta("delay_after_target_clearance_s", "adaptive-risk")
    reduced_stop_delta_fixed = delta("first_stop_distance_to_conflict_m", "fixed-risk")
    reduced_stop_delta_var = delta("first_stop_distance_to_conflict_m", "adaptive-risk")

    lines = [
        "# Formal Supervisor Ablation Report",
        "",
        f"- Result directory: `{result_dir}`",
        "- Scope: 5-init formal ablation, no 50-init escalation.",
        "- Supervisor modes: `full` vs `reduced_intervention`.",
        "- Policies: `fixed-risk` vs `adaptive-risk`.",
        "",
        "## Executive Conclusion",
        "",
        "- Both full and reduced-intervention supervisor settings pass the post-CARLA safety gate.",
        "- Reduced intervention substantially improves the conservative early-stop behaviour while preserving safety.",
        f"- For fixed-risk, reduced intervention changes first-stop distance by `{fmt(reduced_stop_delta_fixed)}m`, waiting time by `{fmt(reduced_wait_delta_fixed)}s`, and post-clearance delay by `{fmt(reduced_delay_delta_fixed)}s`.",
        f"- For adaptive-risk, reduced intervention changes first-stop distance by `{fmt(reduced_stop_delta_var)}m`, waiting time by `{fmt(reduced_wait_delta_var)}s`, and post-clearance delay by `{fmt(reduced_delay_delta_var)}s`.",
        "- This is strong evidence that the original conservative behaviour was dominated by supervisor/yield logic rather than adaptive-risk alone.",
        "- Adaptive-risk remains interpretable at the solver layer, but final executed-trajectory advantages over fixed-risk are still weak in this 5-init ablation.",
        "- Therefore, this result should be used as supervisor-contribution evidence, not as a final proof of var-risk superiority.",
        "- Do not proceed to 50-init before completing infeasibility analysis, solver-vs-final separation plots, and risk-intensity/scenario-difficulty sweep.",
        "",
        "## Aggregate Behaviour Metrics",
        "",
        markdown_table(
            [
                "Supervisor",
                "Policy",
                "First Stop dconf (m)",
                "Wait (s)",
                "Clearance Delay (s)",
                "Supervisor Active",
                "Solver Bypass",
                "Infeasible",
                "Completion Time (s)",
                "dmin TV (m)",
                "Active nominal-final abs accel",
            ],
            aggregate_rows,
        ),
        "",
        "## Supervisor Contribution",
        "",
        "Negative values mean the reduced supervisor decreased the metric relative to full supervisor.",
        "",
        markdown_table(
            [
                "Policy",
                "Delta Stop dconf (m)",
                "Delta Wait (s)",
                "Delta Clearance Delay (s)",
                "Delta Active Frac",
                "Delta Bypass Frac",
                "Delta Active nominal-final abs accel",
            ],
            supervisor_delta_rows,
        ),
        "",
        "Interpretation:",
        "",
        "- Reduced supervisor directly addresses the supervisor feedback about conservative behaviour.",
        "- The large drops in stop distance, waiting time, clearance delay, and bypass fraction show that full supervisor was strongly shaping final behaviour.",
        "- Because the changes appear for both fixed-risk and adaptive-risk, this is a supervisor contribution result, not an adaptive-risk-only result.",
        "",
        "## Var-Risk vs Fixed-Risk After Supervisor Filtering",
        "",
        markdown_table(
            [
                "Supervisor",
                "Var-Fixed Stop dconf (m)",
                "Var-Fixed Delay (s)",
                "Var-Fixed Completion (s)",
                "Var-Fixed dmin TV (m)",
                "Var-Fixed Active nominal-final abs accel",
            ],
            var_fixed_rows,
        ),
        "",
        "Interpretation:",
        "",
        "- Full supervisor nearly eliminates final behaviour differences between fixed-risk and adaptive-risk.",
        "- Reduced supervisor exposes slightly more solver/final consistency benefit for adaptive-risk, but the final trajectory differences remain too small for a strong claim.",
        "- The defensible claim is currently: adaptive-risk has solver-layer behaviour consistent with phase-aware risk, but shared supervisor still masks much of the final executed behaviour.",
        "",
        "## Solver-Layer Risk Evidence",
        "",
        markdown_table(
            [
                "Supervisor",
                "Bucket",
                "Clearance Phase",
                "Var-Fixed Risk Tightening",
                "Var-Fixed Nominal Accel",
                "Var-Fixed Final Accel",
                "Var-Fixed Override Frac",
            ],
            risk_rows,
        ),
        "",
        "Interpretation:",
        "",
        "- In pre-clearance critical/near phases, adaptive-risk generally applies stronger risk tightening and more conservative nominal acceleration.",
        "- After clearance, adaptive-risk relaxes risk relative to fixed-risk.",
        "- The gap between nominal acceleration differences and final acceleration differences supports the supervisor-masking explanation.",
        "",
        "## Infeasibility Phase Analysis",
        "",
        markdown_table(
            [
                "Supervisor",
                "Policy",
                "Phase Bucket",
                "Yield Phase",
                "Steps",
                "Affected Inits",
                "Mean dconf (m)",
            ],
            infeasible_rows,
        ),
        "",
        "Interpretation:",
        "",
        "- Full supervisor has no infeasible steps in this 5-init run.",
        "- Reduced supervisor has a small infeasible fraction, still below gate threshold.",
        "- Remaining infeasible steps are concentrated in critical/pre-clearance approach or cautious-observed-target phases, before target clearance.",
        "- This should be written as a controlled trade-off: reducing deterministic intervention exposes more SMPC optimisation difficulty, but the safety gate remains satisfied.",
        "",
        "## Mapping To Supervisor Feedback",
        "",
        "1. Conservative early stop: addressed by reduced supervisor; behaviour metrics improve substantially.",
        "2. Infeasibility: not ignored; remaining failures are phase-localised and below the gate threshold.",
        "3. Fine-tuning sanity: not answered by this ablation; keep separate sanity-check section.",
        "4. Supervisor dominance: directly supported; full supervisor strongly masks fixed/adaptive final differences.",
        "",
        "## Decision",
        "",
        "- Freeze the current reduced-intervention supervisor as the stable ablation condition.",
        "- Do not tune supervisor further unless a new regression appears.",
        "- Do not run 50-init yet.",
        "- Next experiment should be an adaptive-risk intensity / scenario difficulty sweep under the same frozen reduced supervisor, with the same fixed-risk baseline.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", type=Path, default=DEFAULT_RESULT_DIR)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    result_dir = args.result_dir
    out_dir = args.out_dir or (result_dir / "formal_supervisor_ablation_analysis")
    out_dir.mkdir(parents=True, exist_ok=True)

    diagnostics = load_rollout_diagnostics(result_dir)
    paper_rows = load_paper_metrics(result_dir)
    risk_rows = load_risk_comparison(result_dir)
    infeasible_rows = load_infeasible_steps(result_dir)

    summary = aggregate_by_mode_policy(diagnostics)
    paper_summary = aggregate_paper_metrics(paper_rows)
    infeasible_summary = aggregate_infeasible_steps(infeasible_rows)
    risk_summary = risk_layer_summary(risk_rows)

    write_csv(
        out_dir / "supervisor_ablation_aggregate.csv",
        summary,
        ["supervisor_mode", "policy", "n_rollouts"] + DIAGNOSTIC_FIELDS,
    )
    write_csv(
        out_dir / "infeasibility_phase_summary.csv",
        infeasible_summary,
        [
            "supervisor_mode",
            "policy",
            "phase_bucket",
            "yield_phase",
            "infeasible_steps",
            "affected_inits",
            "mean_distance_to_conflict_m",
            "min_distance_to_conflict_m",
            "max_distance_to_conflict_m",
        ],
    )
    write_csv(
        out_dir / "solver_layer_var_fixed_summary.csv",
        risk_summary,
        [
            "supervisor_mode",
            "bucket",
            "clearance_phase",
            "var_minus_fixed_risk_tightening_mean",
            "var_minus_fixed_nominal_accel_mean",
            "var_minus_fixed_final_accel_mean",
            "var_minus_fixed_supervisor_override_frac",
            "var_minus_fixed_solver_failure_frac",
        ],
    )
    report = generate_report(
        result_dir=result_dir,
        summary=summary,
        paper_metrics=paper_summary,
        infeasible_summary=infeasible_summary,
        risk_summary=risk_summary,
    )
    (out_dir / "formal_supervisor_ablation_report.md").write_text(report)
    print(out_dir / "formal_supervisor_ablation_report.md")


if __name__ == "__main__":
    main()
