#!/usr/bin/env python3
"""Generate result tables and figures following the reference paper style.

The reference is:
Predictive Control for Autonomous Driving With Uncertain Multimodal Predictions,
IEEE TCST 2025, Table I and Section IV-B.

This script intentionally separates:
1. direct paper-style metrics computed from this repository's CARLA logs;
2. same-project improvement from the frozen result to the fine-tuned milestone;
3. non-direct comparison against the original paper's published Table I.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


ORIGINAL_TABLE_I = [
    {
        "scenario": "Original paper: Unprotected left",
        "policy": "OL",
        "T_episode_norm": 1.53,
        "Delta_tau_m": 1.96,
        "A_lat_norm": 1.31,
        "J_long": 8.09,
        "J_lat": 6.62,
        "F_percent": 81.14,
        "dmin_m": 3.88,
        "P_percent": 0.10,
        "T_solve_ms": 13.6,
    },
    {
        "scenario": "Original paper: Unprotected left",
        "policy": "Fixed risk",
        "T_episode_norm": 1.10,
        "Delta_tau_m": 3.09,
        "A_lat_norm": 1.41,
        "J_long": 4.23,
        "J_lat": 9.04,
        "F_percent": 98.37,
        "dmin_m": 3.09,
        "P_percent": 0.44,
        "T_solve_ms": 31.5,
    },
    {
        "scenario": "Original paper: Unprotected left",
        "policy": "Proposed",
        "T_episode_norm": 1.09,
        "Delta_tau_m": 3.07,
        "A_lat_norm": 1.21,
        "J_long": 3.67,
        "J_lat": 8.58,
        "F_percent": 99.88,
        "dmin_m": 3.07,
        "P_percent": 1.63,
        "T_solve_ms": 39.9,
    },
    {
        "scenario": "Original paper: Lane change",
        "policy": "OL",
        "T_episode_norm": 1.32,
        "Delta_tau_m": 7.71,
        "A_lat_norm": 8.16,
        "J_long": 4.41,
        "J_lat": 6.45,
        "F_percent": 82.55,
        "dmin_m": 3.42,
        "P_percent": 0.88,
        "T_solve_ms": 35.6,
    },
    {
        "scenario": "Original paper: Lane change",
        "policy": "Fixed risk",
        "T_episode_norm": 1.07,
        "Delta_tau_m": 3.03,
        "A_lat_norm": 5.71,
        "J_long": 3.80,
        "J_lat": 4.93,
        "F_percent": 96.08,
        "dmin_m": 3.21,
        "P_percent": 1.31,
        "T_solve_ms": 325.20,
    },
    {
        "scenario": "Original paper: Lane change",
        "policy": "Proposed",
        "T_episode_norm": 1.06,
        "Delta_tau_m": 2.92,
        "A_lat_norm": 4.17,
        "J_long": 3.25,
        "J_lat": 3.27,
        "F_percent": 98.76,
        "dmin_m": 3.19,
        "P_percent": 1.84,
        "T_solve_ms": 397.19,
    },
]


def read_csv_dict(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def as_float(row: Dict[str, str], key: str, default: float = float("nan")) -> float:
    value = row.get(key, "")
    if value in ("", None):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def policy_label(policy: str) -> str:
    return {
        "smpc_fixed_risk": "Fixed risk + Supervisor",
        "smpc_var_risk": "Adaptive risk + Supervisor",
    }.get(policy, policy)


def load_gate_summary(path: Path) -> Dict[str, Dict[str, float]]:
    gate = json.loads(path.read_text())
    by_policy: Dict[str, List[Dict[str, float]]] = {}
    for item in gate.get("evaluations", []):
        policy = item["policy"]
        pair = item.get("pair_safety", [{}])[0]
        by_policy.setdefault(policy, []).append(
            {
                "pass": 1.0 if item.get("status") == "PASS" else 0.0,
                "center": float(pair.get("min_center_distance_m", float("nan"))),
                "footprint": float(pair.get("min_footprint_separation_m", float("nan"))),
                "solver_failure": float(item.get("solver_failure_frac", float("nan"))),
            }
        )

    summary: Dict[str, Dict[str, float]] = {}
    for policy, rows in by_policy.items():
        center = [r["center"] for r in rows if math.isfinite(r["center"])]
        footprint = [r["footprint"] for r in rows if math.isfinite(r["footprint"])]
        solver_failure = [r["solver_failure"] for r in rows if math.isfinite(r["solver_failure"])]
        summary[policy] = {
            "gate_pass_count": sum(r["pass"] for r in rows),
            "gate_total": len(rows),
            "gate_pass_percent": 100.0 * sum(r["pass"] for r in rows) / max(len(rows), 1),
            "center_min": min(center) if center else float("nan"),
            "center_mean": sum(center) / len(center) if center else float("nan"),
            "footprint_min": min(footprint) if footprint else float("nan"),
            "footprint_mean": sum(footprint) / len(footprint) if footprint else float("nan"),
            "solver_failure_max": max(solver_failure) if solver_failure else float("nan"),
            "solver_failure_mean": sum(solver_failure) / len(solver_failure) if solver_failure else float("nan"),
        }
    return summary


def load_project_metrics(results_dir: Path) -> Dict[str, Dict[str, float]]:
    metrics_rows = read_csv_dict(results_dir / "paper_metrics_summary.csv")
    gate = load_gate_summary(results_dir / "postcarla_trajectory_gate.json")
    by_policy: Dict[str, Dict[str, float]] = {}
    for row in metrics_rows:
        policy = row["policy"]
        by_policy[policy] = {
            "completion_time_s": as_float(row, "completion_time"),
            "feasibility_percent": 100.0 * as_float(row, "feasibility_percent"),
            "average_solve_time_ms": 1000.0 * as_float(row, "average_solve_time"),
            "dmin_center_mean_m": as_float(row, "dmin_TV"),
            "max_lateral_acceleration": as_float(row, "max_lateral_acceleration"),
            "avg_longitudinal_jerk": as_float(row, "avg_longitudinal_jerk"),
            "avg_lateral_jerk": as_float(row, "avg_lateral_jerk"),
            "completion_valid_percent": 100.0 * as_float(row, "completion_valid"),
            "solver_failure_frac": as_float(row, "solver_failure_frac"),
        }
        by_policy[policy].update(gate.get(policy, {}))
    return by_policy


def load_prediction_metrics(prediction_dir: Path) -> Tuple[Dict[str, float], Dict[str, float]]:
    pretrained = json.loads((prediction_dir / "pretrained_model_metrics_test.json").read_text())
    finetuned = json.loads((prediction_dir / "finetuned_best_metrics_test.json").read_text())
    return pretrained, finetuned


def pct_change(old: float, new: float, lower_is_better: bool = True) -> float:
    if old == 0:
        return float("nan")
    raw = 100.0 * (new - old) / abs(old)
    return -raw if lower_is_better else raw


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    if not rows:
        return
    keys: List[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def svg_escape(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_bar_svg(
    path: Path,
    title: str,
    labels: List[str],
    series: List[Tuple[str, List[float], str]],
    ylabel: str,
    width: int = 980,
    height: int = 520,
) -> None:
    margin_l, margin_r, margin_t, margin_b = 92, 36, 74, 110
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    max_val = max([0.0] + [v for _, values, _ in series for v in values if math.isfinite(v)])
    max_val = max_val * 1.18 if max_val > 0 else 1.0
    group_w = plot_w / max(len(labels), 1)
    bar_w = min(42, group_w / (len(series) + 1.4))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="32" text-anchor="middle" font-family="Arial" font-size="22" font-weight="700">{svg_escape(title)}</text>',
        f'<text x="22" y="{margin_t + plot_h/2:.1f}" transform="rotate(-90 22 {margin_t + plot_h/2:.1f})" text-anchor="middle" font-family="Arial" font-size="14">{svg_escape(ylabel)}</text>',
    ]

    for i in range(6):
        y = margin_t + plot_h - (plot_h * i / 5)
        val = max_val * i / 5
        parts.append(f'<line x1="{margin_l}" y1="{y:.1f}" x2="{width-margin_r}" y2="{y:.1f}" stroke="#e7eaf0" stroke-width="1"/>')
        parts.append(f'<text x="{margin_l-10}" y="{y+4:.1f}" text-anchor="end" font-family="Arial" font-size="12" fill="#596070">{val:.1f}</text>')

    parts.append(f'<line x1="{margin_l}" y1="{margin_t + plot_h}" x2="{width-margin_r}" y2="{margin_t + plot_h}" stroke="#1f2933" stroke-width="1.2"/>')
    parts.append(f'<line x1="{margin_l}" y1="{margin_t}" x2="{margin_l}" y2="{margin_t + plot_h}" stroke="#1f2933" stroke-width="1.2"/>')

    for i, label in enumerate(labels):
        base_x = margin_l + i * group_w + group_w / 2
        start_x = base_x - (len(series) * bar_w) / 2
        for j, (name, values, color) in enumerate(series):
            value = values[i]
            if not math.isfinite(value):
                continue
            h = plot_h * value / max_val
            x = start_x + j * bar_w
            y = margin_t + plot_h - h
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*0.84:.1f}" height="{h:.1f}" rx="4" fill="{color}"/>')
            parts.append(f'<text x="{x + bar_w*0.42:.1f}" y="{y-6:.1f}" text-anchor="middle" font-family="Arial" font-size="11" fill="#111827">{value:.2f}</text>')
        parts.append(f'<text x="{base_x:.1f}" y="{margin_t + plot_h + 28}" text-anchor="middle" font-family="Arial" font-size="12" fill="#111827">{svg_escape(label)}</text>')

    legend_x = margin_l
    legend_y = height - 34
    for name, _, color in series:
        parts.append(f'<rect x="{legend_x}" y="{legend_y-12}" width="14" height="14" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{legend_x+20}" y="{legend_y}" font-family="Arial" font-size="13" fill="#111827">{svg_escape(name)}</text>')
        legend_x += 220

    parts.append("</svg>")
    path.write_text("\n".join(parts))


def make_markdown_report(
    path: Path,
    project: Dict[str, Dict[str, float]],
    frozen: Dict[str, Dict[str, float]],
    pretrained: Dict[str, float],
    finetuned: Dict[str, float],
) -> None:
    var = project["smpc_var_risk"]
    fixed = project["smpc_fixed_risk"]
    frozen_var = frozen["smpc_var_risk"]
    original_unprotected_proposed = next(
        r for r in ORIGINAL_TABLE_I if r["scenario"].endswith("Unprotected left") and r["policy"] == "Proposed"
    )

    lines = [
        "# Original-Paper-Style Result Analysis",
        "",
        "This report follows the result structure of the reference paper, especially Section IV-B and Table I. The reference paper evaluates Mobility, Comfort, Safety, and Solver Performance over 50 CARLA initial conditions.",
        "",
        "Important comparability note: the original paper's absolute numbers are not a strict benchmark for this dissertation because the scenario, vehicle model details, reference normalization, policies, and safety supervisor are different. The fair comparison is therefore two-layered:",
        "",
        "1. **Same-project comparison**: previous frozen SMPC+Supervisor result versus the current fine-tuned-predictor integrated milestone.",
        "2. **Reference-paper-style comparison**: our results are presented using the same metric categories as the original paper, with explicit notes where a column is not directly comparable.",
        "",
        "## 1. Paper-Style Closed-Loop Metrics",
        "",
        "| Policy | Completion time | Feasibility | Mean centre dmin | Min footprint separation | Avg solve time | Max lat. acc. | Avg long. jerk | Avg lat. jerk | Gate pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for policy, row in [("Fixed risk + Supervisor", fixed), ("Adaptive risk + Supervisor", var)]:
        lines.append(
            f"| {policy} | {row['completion_time_s']:.3f} s | {row['feasibility_percent']:.2f}% | "
            f"{row['dmin_center_mean_m']:.3f} m | {row['footprint_min']:.3f} m | "
            f"{row['average_solve_time_ms']:.1f} ms | {row['max_lateral_acceleration']:.3f} | "
            f"{row['avg_longitudinal_jerk']:.3f} | {row['avg_lateral_jerk']:.3f} | "
            f"{int(row['gate_pass_count'])}/{int(row['gate_total'])} |"
        )

    lines += [
        "",
        "## 2. Same-Project Improvement",
        "",
        "| Metric | Previous frozen var-risk | Current fine-tuned var-risk | Direction |",
        "|---|---:|---:|---|",
        f"| Worst-case footprint separation | {frozen_var['footprint_min']:.4f} m | {var['footprint_min']:.4f} m | +{var['footprint_min'] - frozen_var['footprint_min']:.4f} m |",
        f"| Worst-case centre distance | {frozen_var['center_min']:.4f} m | {var['center_min']:.4f} m | +{var['center_min'] - frozen_var['center_min']:.4f} m |",
        f"| Mean centre dmin | {frozen_var['dmin_center_mean_m']:.4f} m | {var['dmin_center_mean_m']:.4f} m | {var['dmin_center_mean_m'] - frozen_var['dmin_center_mean_m']:+.4f} m |",
        f"| Feasibility | {frozen_var['feasibility_percent']:.2f}% | {var['feasibility_percent']:.2f}% | {var['feasibility_percent'] - frozen_var['feasibility_percent']:+.2f} pp |",
        f"| Avg solve time | {frozen_var['average_solve_time_ms']:.1f} ms | {var['average_solve_time_ms']:.1f} ms | {var['average_solve_time_ms'] - frozen_var['average_solve_time_ms']:+.1f} ms |",
        "",
        "Interpretation: the current integrated milestone gives a small positive improvement in the worst-case safety margin while preserving the full 50-init pass result. It is not a dramatic closed-loop improvement because the previous SMPC+Supervisor pipeline was already strongly safe.",
        "",
        "## 3. Model-Side Improvement",
        "",
        "| Predictor | Top-1 ADE | MinADE | Top-1 FDE | MinFDE | Top-probability mode is best |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Pretrained MultiPath | {pretrained['top1_ADE_mean']:.4f} m | {pretrained['minADE_mean']:.4f} m | {pretrained['top1_FDE_mean']:.4f} m | {pretrained['minFDE_mean']:.4f} m | {100*pretrained['top_prob_mode_is_best_frac']:.2f}% |",
        f"| Fine-tuned MultiPath | {finetuned['top1_ADE_mean']:.4f} m | {finetuned['minADE_mean']:.4f} m | {finetuned['top1_FDE_mean']:.4f} m | {finetuned['minFDE_mean']:.4f} m | {100*finetuned['top_prob_mode_is_best_frac']:.2f}% |",
        "",
        f"Top-1 ADE improves by {pct_change(pretrained['top1_ADE_mean'], finetuned['top1_ADE_mean']):.2f}%, and top-1 FDE improves by {pct_change(pretrained['top1_FDE_mean'], finetuned['top1_FDE_mean']):.2f}%. The probability assigned to the best mode becomes reliable: {100*pretrained['top_prob_mode_is_best_frac']:.2f}% -> {100*finetuned['top_prob_mode_is_best_frac']:.2f}%.",
        "",
        "## 4. Comparison with the Original Paper",
        "",
        "| Metric | Original paper Proposed, unprotected left | Current adaptive-risk milestone | Readout |",
        "|---|---:|---:|---|",
        f"| Feasibility | {original_unprotected_proposed['F_percent']:.2f}% | {var['feasibility_percent']:.2f}% | Similar, original is higher by {original_unprotected_proposed['F_percent'] - var['feasibility_percent']:.2f} pp. |",
        f"| Centre distance / dmin | {original_unprotected_proposed['dmin_m']:.2f} m | {var['dmin_center_mean_m']:.2f} m | Ours is larger, but scenario geometry differs. |",
        f"| Avg long. jerk | {original_unprotected_proposed['J_long']:.2f} | {var['avg_longitudinal_jerk']:.2f} | Ours is slightly higher. |",
        f"| Avg lat. jerk | {original_unprotected_proposed['J_lat']:.2f} | {var['avg_lateral_jerk']:.2f} | Ours is lower. |",
        f"| Avg solve time | {original_unprotected_proposed['T_solve_ms']:.1f} ms | {var['average_solve_time_ms']:.1f} ms | Ours is slower. |",
        "",
        "Conclusion: it is not defensible to claim that this dissertation directly outperforms the original paper overall. The scenario and architecture are different, and the original paper reports normalized reference-tracking metrics that this project does not compute in the same way. A defensible claim is that this project reproduces the paper-style evaluation categories, achieves competitive closed-loop feasibility and safety-distance behaviour, adds a rule-aware supervisor for give-way compliance, and improves the deployed predictor through CARLA-domain fine-tuning.",
        "",
        "## 5. Recommended Thesis Statement",
        "",
        "> Following the evaluation structure of the reference SMPC-with-multimodal-predictions paper, the final system is evaluated in terms of mobility, comfort, safety, and solver performance. The current best integrated milestone preserves a full 50-init safety pass rate, slightly improves the worst-case safety margin over the previous frozen control-side result, and substantially improves the prediction model's top-probability trajectory accuracy after fine-tuning. Compared with the original paper, the absolute performance numbers should be treated as reference-style rather than directly comparable benchmarks; the main improvement of this dissertation is the cumulative control-side and model-side enhancement within the same CARLA give-way pipeline.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fine-results", default="core/results/20260718_104740_50init_finetuned_predictor_validation")
    parser.add_argument("--frozen-results", default="core/results/20260710_164024_50init_phase_floor_final_dissertation")
    parser.add_argument("--prediction-dir", default="core/results/20260717_232553_prediction_dataset_collection/prediction_dataset_merged")
    parser.add_argument("--output-dir", default="docs/paper/original_paper_style_results")
    args = parser.parse_args()

    fine_results = Path(args.fine_results)
    frozen_results = Path(args.frozen_results)
    prediction_dir = Path(args.prediction_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    project = load_project_metrics(fine_results)
    frozen = load_project_metrics(frozen_results)
    pretrained, finetuned = load_prediction_metrics(prediction_dir)

    paper_style_rows: List[Dict[str, object]] = []
    for policy, row in project.items():
        paper_style_rows.append(
            {
                "scenario": "This dissertation: give-way intersection",
                "policy": policy_label(policy),
                "completion_time_s": row["completion_time_s"],
                "feasibility_percent": row["feasibility_percent"],
                "dmin_center_mean_m": row["dmin_center_mean_m"],
                "dmin_footprint_min_m": row["footprint_min"],
                "max_lateral_acceleration": row["max_lateral_acceleration"],
                "avg_longitudinal_jerk": row["avg_longitudinal_jerk"],
                "avg_lateral_jerk": row["avg_lateral_jerk"],
                "average_solve_time_ms": row["average_solve_time_ms"],
                "gate_pass": f"{int(row['gate_pass_count'])}/{int(row['gate_total'])}",
                "note": "Paper-style categories; not all columns are normalized exactly like the original paper.",
            }
        )
    write_csv(out / "table_dissertation_paper_style_metrics.csv", paper_style_rows)

    write_csv(out / "table_original_paper_i_values.csv", ORIGINAL_TABLE_I)

    var = project["smpc_var_risk"]
    frozen_var = frozen["smpc_var_risk"]
    improvement_rows = [
        {
            "metric": "worst_case_footprint_separation_m",
            "previous_frozen": frozen_var["footprint_min"],
            "current_finetuned": var["footprint_min"],
            "delta": var["footprint_min"] - frozen_var["footprint_min"],
            "higher_is_better": True,
        },
        {
            "metric": "worst_case_center_distance_m",
            "previous_frozen": frozen_var["center_min"],
            "current_finetuned": var["center_min"],
            "delta": var["center_min"] - frozen_var["center_min"],
            "higher_is_better": True,
        },
        {
            "metric": "top1_ADE_mean_m",
            "previous_pretrained": pretrained["top1_ADE_mean"],
            "current_finetuned": finetuned["top1_ADE_mean"],
            "relative_improvement_percent": pct_change(pretrained["top1_ADE_mean"], finetuned["top1_ADE_mean"]),
            "lower_is_better": True,
        },
        {
            "metric": "top1_FDE_mean_m",
            "previous_pretrained": pretrained["top1_FDE_mean"],
            "current_finetuned": finetuned["top1_FDE_mean"],
            "relative_improvement_percent": pct_change(pretrained["top1_FDE_mean"], finetuned["top1_FDE_mean"]),
            "lower_is_better": True,
        },
        {
            "metric": "top_prob_mode_is_best_percent",
            "previous_pretrained": 100.0 * pretrained["top_prob_mode_is_best_frac"],
            "current_finetuned": 100.0 * finetuned["top_prob_mode_is_best_frac"],
            "delta_pp": 100.0 * (finetuned["top_prob_mode_is_best_frac"] - pretrained["top_prob_mode_is_best_frac"]),
            "higher_is_better": True,
        },
    ]
    write_csv(out / "table_current_milestone_improvement.csv", improvement_rows)

    labels = ["Feasibility (%)", "Mean dmin (m)", "Solve time (ms)"]
    make_bar_svg(
        out / "fig_01_paper_style_closed_loop_metrics.svg",
        "Closed-Loop 50-Init Validation",
        labels,
        [
            (
                "Fixed risk + Supervisor",
                [
                    project["smpc_fixed_risk"]["feasibility_percent"],
                    project["smpc_fixed_risk"]["dmin_center_mean_m"],
                    project["smpc_fixed_risk"]["average_solve_time_ms"],
                ],
                "#4f7cff",
            ),
            (
                "Adaptive risk + Supervisor",
                [
                    var["feasibility_percent"],
                    var["dmin_center_mean_m"],
                    var["average_solve_time_ms"],
                ],
                "#ff8a3d",
            ),
        ],
        "Value",
    )

    make_bar_svg(
        out / "fig_02_prediction_model_improvement.svg",
        "Model-Side Improvement After Fine-Tuning",
        ["Top-1 ADE (m)", "Top-1 FDE (m)", "Best mode top (%)"],
        [
            (
                "Pretrained",
                [
                    pretrained["top1_ADE_mean"],
                    pretrained["top1_FDE_mean"],
                    100.0 * pretrained["top_prob_mode_is_best_frac"],
                ],
                "#7c8798",
            ),
            (
                "Fine-tuned",
                [
                    finetuned["top1_ADE_mean"],
                    finetuned["top1_FDE_mean"],
                    100.0 * finetuned["top_prob_mode_is_best_frac"],
                ],
                "#29a36a",
            ),
        ],
        "Value",
    )

    original_unprotected_proposed = next(
        r for r in ORIGINAL_TABLE_I if r["scenario"].endswith("Unprotected left") and r["policy"] == "Proposed"
    )
    make_bar_svg(
        out / "fig_03_reference_paper_comparison.svg",
        "Comparison with Reference Paper",
        ["Feasibility (%)", "dmin (m)", "Solve time (ms)"],
        [
            (
                "Original Proposed",
                [
                    original_unprotected_proposed["F_percent"],
                    original_unprotected_proposed["dmin_m"],
                    original_unprotected_proposed["T_solve_ms"],
                ],
                "#6b7280",
            ),
            (
                "Current milestone",
                [
                    var["feasibility_percent"],
                    var["dmin_center_mean_m"],
                    var["average_solve_time_ms"],
                ],
                "#d1495b",
            ),
        ],
        "Value",
    )

    make_bar_svg(
        out / "fig_04_current_vs_frozen_safety_margin.svg",
        "Current Milestone vs Previous Frozen Result",
        ["Worst footprint (m)", "Worst center (m)", "Mean center (m)"],
        [
            (
                "Previous frozen var-risk",
                [frozen_var["footprint_min"], frozen_var["center_min"], frozen_var["dmin_center_mean_m"]],
                "#8b9bb4",
            ),
            (
                "Fine-tuned var-risk",
                [var["footprint_min"], var["center_min"], var["dmin_center_mean_m"]],
                "#2f9e44",
            ),
        ],
        "Distance (m)",
    )

    make_markdown_report(
        out / "original_paper_style_result_analysis.md",
        project=project,
        frozen=frozen,
        pretrained=pretrained,
        finetuned=finetuned,
    )

    print(f"Wrote original-paper-style results to {out}")


if __name__ == "__main__":
    main()
