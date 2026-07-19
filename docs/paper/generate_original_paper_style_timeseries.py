#!/usr/bin/env python3
"""Generate original-paper-style closed-loop time-series figures.

The reference paper uses multi-panel line plots for closed-loop behaviour
such as lateral error, heading error, speed, steering, and acceleration.
This script creates comparable figures from this repository's
``smpc_debug_steps.jsonl`` logs without requiring matplotlib.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


COLORS = {
    "fixed": "#4f7cff",
    "adaptive": "#ff8a3d",
    "risk": "#d1495b",
    "distance": "#2f9e44",
    "supervisor": "#6f42c1",
    "grid": "#e7eaf0",
    "axis": "#1f2933",
    "text": "#111827",
}


def finite(v: object) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def get_nested(obj: Dict, keys: Iterable[str], default=None):
    cur = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def read_debug_series(path: Path) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            step = int(obj.get("step", len(rows)))
            t = 0.05 * step
            vehicle = obj.get("vehicle_state", {})
            applied = obj.get("applied", {})
            risk = obj.get("risk", {})
            risk_adaptive = risk.get("adaptive", {}) if isinstance(risk.get("adaptive"), dict) else {}
            yielder = obj.get("rule_aware_yield", {}) or obj.get("yield_stop_supervisor", {}) or {}
            pred = obj.get("prediction", {})
            mode_probs = pred.get("mode_probs", [])
            if isinstance(mode_probs, dict):
                mode_probs = mode_probs.get("head", [])
            if mode_probs and isinstance(mode_probs[0], list):
                mode_probs = mode_probs[0]

            u0 = applied.get("u0", [None, None])
            if not isinstance(u0, list) or len(u0) < 2:
                u0 = [None, None]
            u_control = applied.get("u_control", [None, None])
            if not isinstance(u_control, list) or len(u_control) < 2:
                u_control = [None, None]

            supervisor_active = 1.0 if yielder.get("active") else 0.0
            target_cleared = 1.0 if risk_adaptive.get("target_cleared_conflict") else 0.0

            row = {
                "t": t,
                "step": float(step),
                "ey": finite(vehicle.get("ey")),
                "epsi_deg": None,
                "speed": finite(vehicle.get("speed")),
                "vehicle_accel": finite(vehicle.get("accel")),
                "cmd_accel": finite(u0[0]),
                "cmd_yaw_or_steer": finite(u0[1]),
                "final_accel_delta": None,
                "solve_time_ms": None,
                "risk_tightening": finite(risk.get("solver_current_tight", risk.get("tight"))),
                "target_prob": finite(risk.get("solver_current_target_prob", risk.get("target_prob"))),
                "ego_distance_to_conflict": finite(risk_adaptive.get("ego_distance_to_conflict")),
                "supervisor_active": supervisor_active,
                "target_cleared": target_cleared,
                "top_mode_probability": max([float(x) for x in mode_probs if finite(x) is not None], default=float("nan")),
            }
            epsi = finite(vehicle.get("epsi"))
            if epsi is not None:
                row["epsi_deg"] = 180.0 * epsi / math.pi
            solve_time = finite(applied.get("solve_time", get_nested(obj, ["solver", "solve_time"])))
            if solve_time is not None:
                row["solve_time_ms"] = 1000.0 * solve_time
            if finite(u0[0]) is not None and finite(u_control[0]) is not None:
                row["final_accel_delta"] = float(u_control[0]) - float(u0[0])
            rows.append(row)
    return rows


def extent(series: List[List[Dict[str, float]]], key: str) -> Tuple[float, float]:
    vals = []
    for rows in series:
        for r in rows:
            v = r.get(key)
            if v is not None and math.isfinite(v):
                vals.append(v)
    if not vals:
        return 0.0, 1.0
    lo, hi = min(vals), max(vals)
    if abs(hi - lo) < 1e-9:
        pad = max(abs(hi) * 0.1, 1.0)
        return lo - pad, hi + pad
    pad = 0.08 * (hi - lo)
    return lo - pad, hi + pad


def points(rows: List[Dict[str, float]], x_key: str, y_key: str, x0: float, y0: float, w: float, h: float, x_min: float, x_max: float, y_min: float, y_max: float) -> str:
    pts = []
    for r in rows:
        x, y = r.get(x_key), r.get(y_key)
        if x is None or y is None or not (math.isfinite(x) and math.isfinite(y)):
            continue
        px = x0 + (x - x_min) / (x_max - x_min) * w
        py = y0 + h - (y - y_min) / (y_max - y_min) * h
        pts.append(f"{px:.1f},{py:.1f}")
    return " ".join(pts)


def svg_text(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draw_multi_panel(
    out: Path,
    title: str,
    panels: List[Tuple[str, str]],
    series: List[Tuple[str, List[Dict[str, float]], str]],
    height_per_panel: int = 170,
) -> None:
    width = 1120
    margin_l, margin_r, margin_t, margin_b = 96, 42, 72, 72
    panel_gap = 28
    plot_w = width - margin_l - margin_r
    plot_h = height_per_panel
    height = margin_t + margin_b + len(panels) * plot_h + (len(panels) - 1) * panel_gap
    x_min, x_max = extent([rows for _, rows, _ in series], "t")

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="34" text-anchor="middle" font-family="Arial" font-size="22" font-weight="700">{svg_text(title)}</text>',
    ]

    legend_x = margin_l
    for label, _, color in series:
        parts.append(f'<rect x="{legend_x}" y="50" width="14" height="14" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{legend_x+20}" y="62" font-family="Arial" font-size="13" fill="{COLORS["text"]}">{svg_text(label)}</text>')
        legend_x += 230

    for idx, (key, ylabel) in enumerate(panels):
        y_top = margin_t + idx * (plot_h + panel_gap)
        y_min, y_max = extent([rows for _, rows, _ in series], key)
        parts.append(f'<text x="22" y="{y_top + plot_h/2:.1f}" transform="rotate(-90 22 {y_top + plot_h/2:.1f})" text-anchor="middle" font-family="Arial" font-size="13">{svg_text(ylabel)}</text>')
        for i in range(5):
            y = y_top + plot_h - i * plot_h / 4
            val = y_min + i * (y_max - y_min) / 4
            parts.append(f'<line x1="{margin_l}" y1="{y:.1f}" x2="{width-margin_r}" y2="{y:.1f}" stroke="{COLORS["grid"]}" stroke-width="1"/>')
            parts.append(f'<text x="{margin_l-10}" y="{y+4:.1f}" text-anchor="end" font-family="Arial" font-size="11" fill="#596070">{val:.2f}</text>')
        parts.append(f'<line x1="{margin_l}" y1="{y_top+plot_h:.1f}" x2="{width-margin_r}" y2="{y_top+plot_h:.1f}" stroke="{COLORS["axis"]}" stroke-width="1.2"/>')
        parts.append(f'<line x1="{margin_l}" y1="{y_top:.1f}" x2="{margin_l}" y2="{y_top+plot_h:.1f}" stroke="{COLORS["axis"]}" stroke-width="1.2"/>')
        for label, rows, color in series:
            pts = points(rows, "t", key, margin_l, y_top, plot_w, plot_h, x_min, x_max, y_min, y_max)
            if pts:
                parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"/>')
        if idx == len(panels) - 1:
            for i in range(6):
                x = margin_l + i * plot_w / 5
                val = x_min + i * (x_max - x_min) / 5
                parts.append(f'<text x="{x:.1f}" y="{y_top+plot_h+24}" text-anchor="middle" font-family="Arial" font-size="12" fill="#596070">{val:.1f}</text>')
            parts.append(f'<text x="{margin_l+plot_w/2:.1f}" y="{y_top+plot_h+50}" text-anchor="middle" font-family="Arial" font-size="13">Time (s)</text>')

    parts.append("</svg>")
    out.write_text("\n".join(parts) + "\n")


def write_csv(out: Path, rows: List[Dict[str, float]]) -> None:
    keys = ["t", "step", "ey", "epsi_deg", "speed", "vehicle_accel", "cmd_accel", "cmd_yaw_or_steer", "final_accel_delta", "solve_time_ms", "risk_tightening", "target_prob", "ego_distance_to_conflict", "supervisor_active", "target_cleared", "top_mode_probability"]
    with out.open("w") as f:
        f.write(",".join(keys) + "\n")
        for r in rows:
            vals = []
            for k in keys:
                v = r.get(k)
                vals.append("" if v is None or not math.isfinite(v) else f"{v:.10g}")
            f.write(",".join(vals) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="core/results/20260718_104740_50init_finetuned_predictor_validation")
    parser.add_argument("--init", default="41")
    parser.add_argument("--output-dir", default="docs/paper/original_paper_style_results")
    args = parser.parse_args()

    results = Path(args.results_dir)
    init = str(args.init).zfill(2)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixed_path = results / f"scenario_uk_give_way_ego_init_{init}_smpc_fixed_risk" / "smpc_debug_steps.jsonl"
    adaptive_path = results / f"scenario_uk_give_way_ego_init_{init}_smpc_var_risk" / "smpc_debug_steps.jsonl"
    if not fixed_path.exists() or not adaptive_path.exists():
        raise FileNotFoundError(f"Missing paired debug logs for init {init}: {fixed_path}, {adaptive_path}")

    fixed = read_debug_series(fixed_path)
    adaptive = read_debug_series(adaptive_path)
    write_csv(out / f"timeseries_init_{init}_fixed_risk.csv", fixed)
    write_csv(out / f"timeseries_init_{init}_adaptive_risk.csv", adaptive)

    draw_multi_panel(
        out / f"fig_05_timeseries_init_{init}_closed_loop_behaviour.svg",
        f"Closed-Loop Behaviour Time Series, ego_init_{init}",
        [
            ("ey", "Lateral error ey (m)"),
            ("epsi_deg", "Heading error (deg)"),
            ("speed", "Speed (m/s)"),
            ("cmd_yaw_or_steer", "Steering / yaw cmd"),
            ("cmd_accel", "Longitudinal accel cmd"),
        ],
        [
            ("Fixed risk + Supervisor", fixed, COLORS["fixed"]),
            ("Adaptive risk + Supervisor", adaptive, COLORS["adaptive"]),
        ],
    )

    draw_multi_panel(
        out / f"fig_06_timeseries_init_{init}_risk_supervisor.svg",
        f"Risk and Supervisor Diagnostics, ego_init_{init}",
        [
            ("risk_tightening", "Risk tightening"),
            ("ego_distance_to_conflict", "Ego-conflict distance (m)"),
            ("supervisor_active", "Supervisor active"),
            ("target_cleared", "Target cleared"),
            ("solve_time_ms", "Solve time (ms)"),
        ],
        [
            ("Fixed risk + Supervisor", fixed, COLORS["fixed"]),
            ("Adaptive risk + Supervisor", adaptive, COLORS["adaptive"]),
        ],
    )

    draw_multi_panel(
        out / f"fig_07_timeseries_init_{init}_prediction_and_execution.svg",
        f"Prediction and Execution Diagnostics, ego_init_{init}",
        [
            ("top_mode_probability", "Top mode probability"),
            ("target_prob", "Applied target probability"),
            ("final_accel_delta", "Final - nominal accel"),
            ("vehicle_accel", "Measured accel"),
        ],
        [
            ("Fixed risk + Supervisor", fixed, COLORS["fixed"]),
            ("Adaptive risk + Supervisor", adaptive, COLORS["adaptive"]),
        ],
    )

    print(f"Wrote time-series figures for ego_init_{init} to {out}")


if __name__ == "__main__":
    main()
