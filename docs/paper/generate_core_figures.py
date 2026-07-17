#!/usr/bin/env python3
"""Generate paper-facing core figures for the frozen phase-aware risk results.

This script intentionally uses only the Python standard library so that the
figures can be regenerated on a clean macOS/Python environment without pandas
or matplotlib.
"""

from __future__ import annotations

import csv
import html
import json
import math
import re
from pathlib import Path
from statistics import mean


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_RESULT = REPO_ROOT / "core/results/20260710_164024_50init_phase_floor_final_dissertation"
ABLATION_RESULT = REPO_ROOT / "core/results/20260711_120356_10init_adaptive_risk_ablation"
OUT_DIR = REPO_ROOT / "docs/paper/figures"

COLORS = {
    "fixed": "#4E79A7",
    "var": "#F28E2B",
    "delta": "#59A14F",
    "nominal": "#E15759",
    "final": "#76B7B2",
    "floor": "#B07AA1",
    "nofloor": "#9C755F",
    "grid": "#D8D8D8",
    "text": "#222222",
}

PHASES = [
    ("approach", "pre_clearance", "Approach\npre-clearance"),
    ("critical", "pre_clearance", "Critical\npre-clearance"),
    ("critical", "post_clearance", "Critical\npost-clearance"),
    ("near", "post_clearance", "Near\npost-clearance"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def fnum(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    if value in ("", "nan", "NaN", None):
        return math.nan
    return float(value)


def phase_rows(rows: list[dict[str, str]], bucket: str, clearance_phase: str) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("bucket") == bucket and row.get("clearance_phase") == clearance_phase
    ]


def phase_mean(rows: list[dict[str, str]], bucket: str, clearance_phase: str, key: str) -> float:
    values = [fnum(row, key) for row in phase_rows(rows, bucket, clearance_phase)]
    values = [v for v in values if not math.isnan(v)]
    return mean(values) if values else math.nan


def extract_init(scenario_dir: str) -> int | None:
    match = re.search(r"ego_init_(\d+)_", scenario_dir)
    return int(match.group(1)) if match else None


def safety_summary() -> dict[str, dict[str, float]]:
    gate_path = MAIN_RESULT / "postcarla_trajectory_gate.json"
    data = json.loads(gate_path.read_text())
    summary: dict[str, dict[str, list[float] | float]] = {}
    for item in data["evaluations"]:
        policy = item["policy"]
        bucket = summary.setdefault(
            policy,
            {
                "n": 0.0,
                "pass": 0.0,
                "solver_failure": [],
                "footprint": [],
                "center": [],
            },
        )
        bucket["n"] = float(bucket["n"]) + 1.0
        if item["status"] == "PASS":
            bucket["pass"] = float(bucket["pass"]) + 1.0
        bucket["solver_failure"].append(float(item.get("solver_failure_frac", 0.0)))  # type: ignore[union-attr]
        for pair in item.get("pair_safety", []):
            bucket["footprint"].append(float(pair["min_footprint_separation_m"]))  # type: ignore[union-attr]
            bucket["center"].append(float(pair["min_center_distance_m"]))  # type: ignore[union-attr]

    out: dict[str, dict[str, float]] = {}
    for policy, values in summary.items():
        solver = values["solver_failure"]  # type: ignore[assignment]
        footprint = values["footprint"]  # type: ignore[assignment]
        center = values["center"]  # type: ignore[assignment]
        out[policy] = {
            "pass": float(values["pass"]),
            "n": float(values["n"]),
            "solver_failure_max": max(solver),
            "solver_failure_mean": mean(solver),
            "footprint_min": min(footprint),
            "footprint_mean": mean(footprint),
            "center_min": min(center),
            "center_mean": mean(center),
        }
    return out


def svg_text(x: float, y: float, text: str, size: int = 12, anchor: str = "middle", weight: str = "normal") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{COLORS["text"]}" '
        f'text-anchor="{anchor}">{html.escape(text)}</text>'
    )


def multiline_label(x: float, y: float, text: str, size: int = 11) -> str:
    parts = text.split("\n")
    lines = []
    for idx, part in enumerate(parts):
        lines.append(svg_text(x, y + idx * (size + 2), part, size=size))
    return "\n".join(lines)


def nice_ticks(y_min: float, y_max: float, count: int = 5) -> list[float]:
    if y_min == y_max:
        y_min -= 1.0
        y_max += 1.0
    span = y_max - y_min
    raw = span / max(count - 1, 1)
    power = 10 ** math.floor(math.log10(abs(raw)))
    step = min([1, 2, 2.5, 5, 10], key=lambda m: abs(m * power - raw)) * power
    start = math.floor(y_min / step) * step
    end = math.ceil(y_max / step) * step
    ticks = []
    value = start
    while value <= end + step * 0.5:
        ticks.append(round(value, 10))
        value += step
    return ticks


def render_grouped_bar(
    path: Path,
    title: str,
    categories: list[str],
    series: list[tuple[str, list[float], str]],
    ylabel: str,
    y_min: float | None = None,
    y_max: float | None = None,
    note: str | None = None,
) -> None:
    width, height = 980, 560
    left, right, top, bottom = 95, 35, 70, 105
    plot_w, plot_h = width - left - right, height - top - bottom
    all_values = [v for _, values, _ in series for v in values if not math.isnan(v)]
    auto_min = min(0.0, min(all_values))
    auto_max = max(all_values)
    y_min = auto_min if y_min is None else y_min
    y_max = auto_max if y_max is None else y_max
    pad = (y_max - y_min) * 0.08 or 1.0
    y_min -= pad
    y_max += pad
    ticks = nice_ticks(y_min, y_max)
    y_min, y_max = min(ticks), max(ticks)

    def x_pos(group_idx: int, bar_idx: int) -> float:
        group_w = plot_w / len(categories)
        total_bar_w = group_w * 0.68
        bar_w = total_bar_w / len(series)
        start = left + group_idx * group_w + (group_w - total_bar_w) / 2
        return start + bar_idx * bar_w

    def y_pos(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    group_w = plot_w / len(categories)
    total_bar_w = group_w * 0.68
    bar_w = total_bar_w / len(series)
    if y_min <= 0.0 <= y_max:
        baseline_value = 0.0
    elif y_min > 0.0:
        baseline_value = y_min
    else:
        baseline_value = y_max
    baseline = y_pos(baseline_value)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        svg_text(width / 2, 32, title, size=18, weight="bold"),
        svg_text(24, top + plot_h / 2, ylabel, size=12, anchor="middle", weight="bold").replace(
            "<text ", '<text transform="rotate(-90 24 {:.1f})" '.format(top + plot_h / 2), 1
        ),
    ]

    for tick in ticks:
        y = y_pos(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="{COLORS["grid"]}" stroke-width="1"/>')
        parts.append(svg_text(left - 10, y + 4, f"{tick:.2f}", size=10, anchor="end"))
    parts.append(f'<line x1="{left}" y1="{baseline:.1f}" x2="{left + plot_w}" y2="{baseline:.1f}" stroke="#555" stroke-width="1.2"/>')

    for s_idx, (name, values, color) in enumerate(series):
        for c_idx, value in enumerate(values):
            x = x_pos(c_idx, s_idx)
            bar_top = y_pos(max(value, baseline_value))
            bar_bottom = y_pos(min(value, baseline_value))
            y = bar_top
            h = abs(bar_bottom - bar_top)
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w - 3:.1f}" height="{h:.1f}" fill="{color}"/>')
            label_y = y - 6 if value >= baseline_value else y + h + 14
            parts.append(svg_text(x + (bar_w - 3) / 2, label_y, f"{value:+.3f}" if y_min < 0 else f"{value:.3f}", size=9))

    for c_idx, category in enumerate(categories):
        x = left + c_idx * group_w + group_w / 2
        parts.append(multiline_label(x, top + plot_h + 27, category, size=11))

    legend_x = left + plot_w - 250
    legend_y = 48
    for idx, (name, _, color) in enumerate(series):
        y = legend_y + idx * 18
        parts.append(f'<rect x="{legend_x}" y="{y - 10}" width="12" height="12" fill="{color}"/>')
        parts.append(svg_text(legend_x + 18, y, name, size=11, anchor="start"))

    if note:
        parts.append(svg_text(left, height - 18, note, size=10, anchor="start"))
    parts.append("</svg>")
    path.write_text("\n".join(parts))


def render_table(path: Path, title: str, rows: list[list[str]], note: str | None = None) -> None:
    width = 980
    row_h = 42
    height = 110 + row_h * len(rows) + (35 if note else 0)
    col_x = [45, 235, 390, 575, 765]
    col_w = [190, 155, 185, 190, 170]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        svg_text(width / 2, 34, title, size=18, weight="bold"),
    ]
    y0 = 70
    for r_idx, row in enumerate(rows):
        y = y0 + r_idx * row_h
        fill = "#F5F7FA" if r_idx == 0 else ("#FFFFFF" if r_idx % 2 else "#FAFAFA")
        parts.append(f'<rect x="35" y="{y - 24}" width="{width - 70}" height="{row_h}" fill="{fill}" stroke="#E0E0E0"/>')
        for c_idx, cell in enumerate(row):
            weight = "bold" if r_idx == 0 else "normal"
            anchor = "start" if c_idx == 0 else "middle"
            x = col_x[c_idx] if c_idx == 0 else col_x[c_idx] + col_w[c_idx] / 2
            parts.append(svg_text(x, y + 2, cell, size=11, anchor=anchor, weight=weight))
    if note:
        parts.append(svg_text(45, height - 24, note, size=10, anchor="start"))
    parts.append("</svg>")
    path.write_text("\n".join(parts))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    main_rows = read_csv(MAIN_RESULT / "risk_by_conflict_distance_comparison.csv")
    phase_labels = [label for _, _, label in PHASES]

    fixed_tight = [phase_mean(main_rows, b, p, "fixed_risk_tightening_mean") for b, p, _ in PHASES]
    var_tight = [phase_mean(main_rows, b, p, "var_risk_tightening_mean") for b, p, _ in PHASES]
    delta_tight = [phase_mean(main_rows, b, p, "var_minus_fixed_risk_tightening_mean") for b, p, _ in PHASES]
    nominal_delta = [phase_mean(main_rows, b, p, "var_minus_fixed_nominal_accel_mean") for b, p, _ in PHASES]
    final_delta = [phase_mean(main_rows, b, p, "var_minus_fixed_final_accel_mean") for b, p, _ in PHASES]
    var_override = [phase_mean(main_rows, b, p, "var_supervisor_override_frac") for b, p, _ in PHASES]
    fixed_override = [phase_mean(main_rows, b, p, "fixed_supervisor_override_frac") for b, p, _ in PHASES]

    safety = safety_summary()
    safety_rows = [
        ["Policy", "PASS", "Solver failure max/mean", "Footprint sep. min/mean", "Center dmin min/mean"],
    ]
    for policy in ("smpc_fixed_risk", "smpc_var_risk"):
        s = safety[policy]
        safety_rows.append(
            [
                policy,
                f"{int(s['pass'])}/{int(s['n'])}",
                f"{s['solver_failure_max']:.4f} / {s['solver_failure_mean']:.4f}",
                f"{s['footprint_min']:.4f} / {s['footprint_mean']:.4f} m",
                f"{s['center_min']:.4f} / {s['center_mean']:.4f} m",
            ]
        )
    render_table(
        OUT_DIR / "fig_01_frozen_50init_safety_summary.svg",
        "Frozen 50-init Main Result: Safety Gate Summary",
        safety_rows,
        "Source: postcarla_trajectory_gate.json. Required SMPC rollouts: 100/100 PASS.",
    )

    render_grouped_bar(
        OUT_DIR / "fig_02_phase_aware_risk_tightening.svg",
        "Phase-Aware Risk Tightening in the Frozen 50-init Result",
        phase_labels,
        [
            ("Fixed-risk SMPC", fixed_tight, COLORS["fixed"]),
            ("Adaptive-risk SMPC", var_tight, COLORS["var"]),
        ],
        "Risk tightening",
        y_min=1.0,
        y_max=2.0,
        note="Adaptive risk is higher before target clearance and relaxed after clearance.",
    )

    render_grouped_bar(
        OUT_DIR / "fig_03_var_minus_fixed_tightening.svg",
        "Adaptive Minus Fixed Risk Tightening by Conflict Phase",
        phase_labels,
        [("Adaptive - Fixed", delta_tight, COLORS["delta"])],
        "Tightening difference",
        y_min=-0.45,
        y_max=0.25,
        note="Positive means adaptive risk is more conservative; negative means adaptive risk is more relaxed.",
    )

    render_grouped_bar(
        OUT_DIR / "fig_04_nominal_vs_final_acceleration_delta.svg",
        "Nominal vs Final Acceleration Difference",
        phase_labels,
        [
            ("Nominal accel delta", nominal_delta, COLORS["nominal"]),
            ("Final accel delta", final_delta, COLORS["final"]),
        ],
        "Var - fixed acceleration",
        y_min=-0.5,
        y_max=0.1,
        note="Critical pre-clearance shows solver-layer conservatism; final control is largely shaped by the supervisor.",
    )

    render_grouped_bar(
        OUT_DIR / "fig_05_supervisor_override_fraction.svg",
        "Supervisor Override Fraction by Conflict Phase",
        phase_labels,
        [
            ("Fixed-risk SMPC", fixed_override, COLORS["fixed"]),
            ("Adaptive-risk SMPC", var_override, COLORS["var"]),
        ],
        "Override fraction",
        y_min=0.0,
        y_max=1.05,
        note="High pre-clearance override fraction explains why final trajectory metrics remain close.",
    )

    ablation_values = []
    ablation_floor_frac = []
    for variant in ("phase_floor", "no_phase_floor"):
        rows = read_csv(ABLATION_RESULT / variant / "risk_by_conflict_distance_comparison.csv")
        ablation_values.append(phase_mean(rows, "critical", "pre_clearance", "var_minus_fixed_risk_tightening_mean"))
        ablation_floor_frac.append(phase_mean(rows, "critical", "pre_clearance", "var_floor_applied_frac"))
    render_grouped_bar(
        OUT_DIR / "fig_06_ablation_critical_preclearance_gap.svg",
        "Ablation: Critical Pre-Clearance Tightening Gap",
        ["Phase floor", "No phase floor"],
        [
            ("Var - fixed tightening gap", ablation_values, COLORS["floor"]),
            ("Floor applied fraction", ablation_floor_frac, COLORS["nofloor"]),
        ],
        "Value",
        y_min=0.0,
        y_max=1.05,
        note="Disabling the floor reduces the tightening gap from about +0.160 to about +0.060.",
    )

    summary_path = OUT_DIR / "core_figure_summary.md"
    summary_path.write_text(
        "\n".join(
            [
                "# Core Figure Summary",
                "",
                "Frozen main result: `core/results/20260710_164024_50init_phase_floor_final_dissertation`.",
                "",
                "Ablation result: `core/results/20260711_120356_10init_adaptive_risk_ablation`.",
                "",
                "Generated figures:",
                "",
                "- `fig_01_frozen_50init_safety_summary.svg`",
                "- `fig_02_phase_aware_risk_tightening.svg`",
                "- `fig_03_var_minus_fixed_tightening.svg`",
                "- `fig_04_nominal_vs_final_acceleration_delta.svg`",
                "- `fig_05_supervisor_override_fraction.svg`",
                "- `fig_06_ablation_critical_preclearance_gap.svg`",
                "",
                "Key values:",
                "",
                f"- Critical/pre-clearance tightening gap: `{delta_tight[1]:+.4f}`.",
                f"- Critical/post-clearance tightening gap: `{delta_tight[2]:+.4f}`.",
                f"- Ablation gap with floor: `{ablation_values[0]:+.4f}`.",
                f"- Ablation gap without floor: `{ablation_values[1]:+.4f}`.",
            ]
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
