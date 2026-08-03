#!/usr/bin/env python3
"""Generate the eight canonical thesis figures as deterministic SVG files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import textwrap
from pathlib import Path
from typing import Any, Iterable


INK = "#17212B"
MUTED = "#5B6773"
GRID = "#D7DEE5"
LIGHT = "#F3F6F8"
BLUE = "#2474B5"
ORANGE = "#D97706"
GREEN = "#17845B"
PURPLE = "#8A55A3"
RED = "#C44E52"
GREY = "#7A8793"
WHITE = "#FFFFFF"

MODEL_COLORS = {"B0": GREY, "B1": BLUE, "B2-M": ORANGE, "B2-D": GREEN, "T1": PURPLE, "T2": RED}
POLICY_COLORS = {
    "adaptive": BLUE,
    "fixed_aggressive": ORANGE,
    "fixed_medium": GREEN,
    "fixed_conservative": PURPLE,
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class SVG:
    def __init__(self, width: int = 1200, height: int = 700, title: str = "") -> None:
        self.width = width
        self.height = height
        self.items = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f"<title id=\"title\">{esc(title)}</title>",
            '<desc id="desc">Thesis figure generated from the frozen paper results manifest.</desc>',
            "<defs>",
            '<marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#5B6773"/></marker>',
            '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#17212B} .title{font-size:24px;font-weight:700}.subtitle{font-size:14px;fill:#5B6773}.panel{font-size:17px;font-weight:700}.label{font-size:14px}.small{font-size:12px;fill:#5B6773}.tiny{font-size:10.5px;fill:#5B6773}.axis{stroke:#5B6773;stroke-width:1.2}.grid{stroke:#D7DEE5;stroke-width:1}.box{fill:#F3F6F8;stroke:#AAB4BE;stroke-width:1.2}</style>',
            "</defs>",
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="{WHITE}"/>',
        ]

    def add(self, value: str) -> None:
        self.items.append(value)

    def text(self, x: float, y: float, value: Any, cls: str = "label", anchor: str = "start", rotate: float | None = None, fill: str | None = None) -> None:
        transform = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
        color = f' fill="{fill}"' if fill else ""
        self.add(f'<text x="{x:.2f}" y="{y:.2f}" class="{cls}" text-anchor="{anchor}"{transform}{color}>{esc(value)}</text>')

    def multiline(self, x: float, y: float, value: str, width: int, cls: str = "small", line_height: int = 18, anchor: str = "start") -> None:
        lines = textwrap.wrap(value, width=width, break_long_words=False) or [""]
        self.add(f'<text x="{x:.2f}" y="{y:.2f}" class="{cls}" text-anchor="{anchor}">')
        for index, line in enumerate(lines):
            dy = 0 if index == 0 else line_height
            self.add(f'<tspan x="{x:.2f}" dy="{dy}">{esc(line)}</tspan>')
        self.add("</text>")

    def line(self, x1: float, y1: float, x2: float, y2: float, stroke: str = MUTED, width: float = 1.2, dash: str | None = None, arrow: bool = False) -> None:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        marker = ' marker-end="url(#arrow)"' if arrow else ""
        self.add(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-width="{width}"{dash_attr}{marker}/>')

    def rect(self, x: float, y: float, width: float, height: float, fill: str = LIGHT, stroke: str = GRID, radius: float = 10, stroke_width: float = 1.2) -> None:
        self.add(f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>')

    def circle(self, x: float, y: float, radius: float, fill: str, stroke: str = WHITE, stroke_width: float = 1.5) -> None:
        self.add(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>')

    def triangle(self, x: float, y: float, size: float, fill: str, stroke: str = INK) -> None:
        points = f"{x:.2f},{y-size:.2f} {x-size:.2f},{y+size:.2f} {x+size:.2f},{y+size:.2f}"
        self.add(f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')

    def polyline(self, points: Iterable[tuple[float, float]], stroke: str, width: float = 2.0, fill: str = "none") -> None:
        value = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.add(f'<polyline points="{value}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')

    def save(self, path: Path) -> None:
        path.write_text("\n".join(self.items + ["</svg>"]) + "\n", encoding="utf-8")


def title(svg: SVG, name: str, subtitle: str) -> None:
    svg.text(60, 42, name, "title")
    svg.text(60, 66, subtitle, "subtitle")


def scale(value: float, low: float, high: float, out_low: float, out_high: float) -> float:
    if math.isclose(low, high):
        return (out_low + out_high) / 2
    return out_low + (value - low) / (high - low) * (out_high - out_low)


def axes(svg: SVG, x: float, y: float, width: float, height: float, x_low: float, x_high: float, y_low: float, y_high: float, x_label: str, y_label: str, x_ticks: int = 5, y_ticks: int = 5) -> tuple[Any, Any]:
    sx = lambda value: scale(value, x_low, x_high, x, x + width)
    sy = lambda value: scale(value, y_low, y_high, y + height, y)
    for index in range(y_ticks + 1):
        value = y_low + (y_high - y_low) * index / y_ticks
        yy = sy(value)
        svg.line(x, yy, x + width, yy, GRID, 1)
        svg.text(x - 9, yy + 4, f"{value:.2g}", "tiny", "end")
    for index in range(x_ticks + 1):
        value = x_low + (x_high - x_low) * index / x_ticks
        xx = sx(value)
        svg.line(xx, y, xx, y + height, GRID, 1)
        svg.text(xx, y + height + 19, f"{value:.2g}", "tiny", "middle")
    svg.line(x, y + height, x + width, y + height, MUTED, 1.2)
    svg.line(x, y, x, y + height, MUTED, 1.2)
    svg.text(x + width / 2, y + height + 43, x_label, "small", "middle")
    svg.text(x - 48, y + height / 2, y_label, "small", "middle", -90)
    return sx, sy


def figure01_workflow(output: Path) -> list[str]:
    svg = SVG(title="Research workflow and evidence gates")
    title(svg, "Research workflow and evidence gates", "The initial adaptive-risk question is retained, but model evidence is moved to the centre of the thesis.")
    stages = [
        ("1  Planning motivation", "Adaptive vs fixed risk under a shared supervisor", "Negative/mixed pilot", ORANGE),
        ("2  Controlled interaction data", "200 CARLA rollouts; rollout-level train/val/test split", "Integrity + collision audit", GREEN),
        ("3  Matched model comparison", "B0, B1, B2-M, B2-D, T1 and T2; 3 seeds", "Validation-only selection", BLUE),
        ("4  Frozen closed loop", "Predictor × risk × style × timing", "120 formal rollouts", PURPLE),
    ]
    x_positions = [55, 335, 615, 895]
    for index, ((heading, body, gate, color), x) in enumerate(zip(stages, x_positions)):
        svg.rect(x, 150, 245, 250, WHITE, color, 14, 2)
        svg.rect(x, 150, 245, 47, color, color, 14, 0)
        svg.text(x + 16, 181, heading, "panel", fill=WHITE)
        svg.multiline(x + 18, 235, body, 27, "label", 22)
        svg.line(x + 18, 325, x + 227, 325, GRID, 1)
        svg.text(x + 18, 352, "Evidence gate", "small")
        svg.multiline(x + 18, 376, gate, 26, "label", 20)
        if index < len(stages) - 1:
            svg.line(x + 250, 275, x_positions[index + 1] - 8, 275, MUTED, 2, arrow=True)
    svg.rect(130, 485, 940, 125, LIGHT, GRID, 12)
    svg.text(155, 518, "Final evidence-led claim", "panel")
    svg.multiline(155, 550, "Task adaptation strongly improves in-distribution prediction, but closed-loop benefit is conditional on risk policy, arrival timing, solver feasibility and supervisor intervention. Tested Transformers use sequence context but do not beat simple B1 adaptation.", 120, "label", 22)
    svg.text(600, 665, "Primary evidence: Day8 frozen test + Day10 nominal + Day11/12 timing synthesis | Day13 is sensitivity only", "small", "middle")
    svg.save(output / "figure01_research_workflow.svg")
    return ["R_DATA_TRAIN_ROLLOUTS", "R_TEST_B1_MINUS_B0_ADE", "R_SENS_SELECTED_ARCHITECTURE_STABLE"]


def figure02_architecture(output: Path) -> list[str]:
    svg = SVG(title="Matched model architecture and controls")
    title(svg, "Matched model architecture and controls", "All variants share the same frozen MultiPath base, data split, loss, anchors and evaluation contract.")
    svg.rect(55, 140, 230, 190, WHITE, BLUE, 12, 2)
    svg.text(170, 177, "Frozen MultiPath base", "panel", "middle")
    svg.text(170, 214, "Raster + target history", "label", "middle")
    svg.text(170, 245, "10 modes × 20 steps", "small", "middle")
    svg.text(170, 278, "Base means / covariance / logits", "small", "middle")
    svg.rect(55, 390, 230, 145, WHITE, GREEN, 12, 2)
    svg.text(170, 425, "Interaction sequence", "panel", "middle")
    svg.text(170, 460, "6 tokens × 12 features + mask", "label", "middle")
    svg.text(170, 493, "Train-only normalization", "small", "middle")

    branches = [
        ("B1", "No sequence branch", "Fine-tune final base head", BLUE),
        ("B2-M / B2-D", "Flatten + matched MLP", "Mean-only / distributional", ORANGE),
        ("T1 / T2", "Masked self-attention", "Mean-only / distributional", PURPLE),
    ]
    ys = [125, 315, 505]
    for (name, encoder, head, color), y in zip(branches, ys):
        svg.rect(420, y, 300, 130, WHITE, color, 12, 2)
        svg.text(445, y + 34, name, "panel")
        svg.text(445, y + 68, encoder, "label")
        svg.text(445, y + 98, head, "small")
        if name == "B1":
            svg.line(285, 230, 410, y + 65, MUTED, 1.8, arrow=True)
        else:
            svg.line(285, 455, 410, y + 65, MUTED, 1.8, arrow=True)
            svg.line(285, 230, 410, y + 65, MUTED, 1.2, arrow=True)
        svg.line(720, y + 65, 805, y + 65, MUTED, 1.8, arrow=True)

    svg.rect(820, 215, 325, 255, WHITE, GREY, 12, 2)
    svg.text(982, 254, "Structured residual merge", "panel", "middle")
    svg.text(850, 296, "Mean-only: B2-M ↔ T1", "label")
    svg.text(850, 330, "Distributional: B2-D ↔ T2", "label")
    svg.line(850, 350, 1115, 350, GRID, 1)
    svg.text(850, 382, "Matched comparisons isolate", "small")
    svg.text(850, 407, "temporal inductive bias from capacity.", "small")
    svg.text(850, 444, "B1 remains the simple-adaptation control.", "small")
    svg.text(600, 655, "Frozen test is opened once after validation-only ranking; context ablation is post-selection reporting only.", "small", "middle")
    svg.save(output / "figure02_model_architecture.svg")
    return ["R_VAL_B1_S11_MACRO_NLL", "R_ABLATION_T1_SHUFFLE_MACRO_NLL", "R_ABLATION_T2_SHUFFLE_MACRO_NLL"]


def figure03_model_comparison(tables: Path, output: Path) -> list[str]:
    validation = read_csv(tables / "table02_validation_5models_3seeds.csv")
    test = read_csv(tables / "table03_frozen_test_and_b0_control.csv")
    order = ["B1", "B2-D", "T2", "T1", "B2-M"]
    svg = SVG(title="Offline model comparison")
    title(svg, "Offline model comparison", "Validation uses three seeds; frozen test uses one validation-selected checkpoint per architecture.")

    x0, y0, w, h = 95, 135, 480, 430
    nll_values = [float(row["validation_macro_nll"]) for row in validation]
    sy = lambda value: scale(value, 1.82, 2.06, y0 + h, y0)
    for tick in [1.85, 1.90, 1.95, 2.00, 2.05]:
        yy = sy(tick)
        svg.line(x0, yy, x0 + w, yy, GRID, 1)
        svg.text(x0 - 12, yy + 4, fmt(tick, 2), "tiny", "end")
    svg.line(x0, y0 + h, x0 + w, y0 + h, MUTED, 1.2)
    svg.text(x0 - 56, y0 + h / 2, "Validation macro NLL (nats/step) ↓", "small", "middle", -90)
    for index, model in enumerate(order):
        xx = x0 + (index + 0.5) * w / len(order)
        values = sorted(float(r["validation_macro_nll"]) for r in validation if r["variant"] == model)
        for offset, value in zip((-10, 0, 10), values):
            svg.circle(xx + offset, sy(value), 6, MODEL_COLORS[model])
        svg.line(xx - 22, sy(values[1]), xx + 22, sy(values[1]), INK, 2)
        svg.text(xx, y0 + h + 27, model, "label", "middle")
    svg.text(x0 + w / 2, 112, "(a) Validation-only model selection", "panel", "middle")

    x1, y1, w1, h1 = 700, 135, 420, 430
    test_map = {r["variant"].replace(" pretrained control", ""): r for r in test}
    test_order = ["B0", "B1", "B2-D", "T2", "T1", "B2-M"]
    sx = lambda value: scale(value, 0, 2.9, x1, x1 + w1)
    for tick in [0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        xx = sx(tick)
        svg.line(xx, y1, xx, y1 + h1, GRID, 1)
        svg.text(xx, y1 + h1 + 20, fmt(tick, 1), "tiny", "middle")
    for index, model in enumerate(test_order):
        yy = y1 + 40 + index * 63
        ade = float(test_map[model]["test_top1_ade_m"])
        fde = float(test_map[model]["test_top1_fde_m"])
        svg.line(sx(ade), yy, sx(fde), yy, MODEL_COLORS[model], 3)
        svg.circle(sx(ade), yy, 6, MODEL_COLORS[model])
        svg.triangle(sx(fde), yy, 6, MODEL_COLORS[model])
        svg.text(x1 - 18, yy + 4, model, "label", "end")
        svg.text(sx(fde) + 10, yy + 4, f"{ade:.2f}/{fde:.2f}", "tiny")
    svg.text(x1 + w1 / 2, 112, "(b) Frozen-test ADE ● and FDE ▲", "panel", "middle")
    svg.text(x1 + w1 / 2, y1 + h1 + 48, "Error (m) ↓", "small", "middle")
    svg.text(600, 655, "B1 ranks first on validation NLL and frozen-test displacement error; complexity alone does not determine performance.", "small", "middle")
    svg.save(output / "figure03_offline_model_comparison.svg")
    return ["R_TEST_B1_MACRO_NLL", "R_TEST_B1_TOP1_ADE_M", "R_TEST_B1_MINUS_B0_ADE", "R_TEST_B1_MINUS_B0_FDE"]


def figure04_calibration(tables: Path, output: Path) -> list[str]:
    rows = read_csv(tables / "table04_calibration_aggregate_vs_response_tail.csv")
    svg = SVG(title="Aggregate and response-active calibration")
    title(svg, "Aggregate and response-active calibration", "The validation-frozen global calibrator improves aggregate B1 NLL but fails in the interaction tail.")
    panels = [("all", "All test windows", -3.0, 3.5), ("response_active", "Response-active tail (15 windows)", 0.0, 10.0)]
    for panel_index, (subset, label, ymin, ymax) in enumerate(panels):
        x = 115 + panel_index * 585
        y, w, h = 145, 435, 390
        sy = lambda value, y=y, h=h, ymin=ymin, ymax=ymax: scale(value, ymin, ymax, y + h, y)
        for tick_index in range(6):
            value = ymin + (ymax - ymin) * tick_index / 5
            yy = sy(value)
            svg.line(x, yy, x + w, yy, GRID, 1)
            svg.text(x - 10, yy + 4, fmt(value, 1), "tiny", "end")
        if ymin < 0:
            svg.line(x, sy(0), x + w, sy(0), MUTED, 1.2)
        selected = [r for r in rows if r["subset"] == subset]
        for model_index, row in enumerate(selected):
            color = MODEL_COLORS[row["variant"]]
            left = x + 110 + model_index * 205
            right = left + 90
            uncal = float(row["uncalibrated_macro_nll"])
            cal = float(row["calibrated_macro_nll"])
            svg.line(left, sy(uncal), right, sy(cal), color, 3)
            svg.circle(left, sy(uncal), 7, color)
            svg.circle(right, sy(cal), 7, color)
            svg.text((left + right) / 2, min(sy(uncal), sy(cal)) - 12, row["variant"], "label", "middle")
            svg.text(left, y + h + 24, "raw", "small", "middle")
            svg.text(right, y + h + 24, "cal", "small", "middle")
            svg.text(right + 10, sy(cal) + 4, fmt(cal, 2), "tiny")
        svg.text(x + w / 2, 118, f"({chr(97 + panel_index)}) {label}", "panel", "middle")
        svg.text(x - 58, y + h / 2, "Rollout-macro NLL (nats/step) ↓", "small", "middle", -90)
    svg.text(600, 650, "Tail estimates use only 15 windows / 6 rollouts / 3 init groups and are reported as a limitation, not a new selection criterion.", "small", "middle")
    svg.save(output / "figure04_calibration_tail.svg")
    return ["R_CAL_B1_RESPONSE_ACTIVE_MINUS_B0_CAL_NLL"]


def figure05_frontier(tables: Path, output: Path) -> list[str]:
    rows = read_csv(tables / "table05_day10_predictor_risk_frontier.csv")
    svg = SVG(title="Nominal closed-loop safety-efficiency frontier")
    title(svg, "Nominal closed-loop safety–efficiency frontier", "Each point is a five-rollout cell mean; lower delay and higher separation are preferred.")
    for panel_index, style in enumerate(("assertive", "reactive")):
        x = 105 + panel_index * 575
        y, w, h = 150, 430, 390
        sx, sy = axes(svg, x, y, w, h, 8.0, 9.25, 1.05, 1.36, "Adjusted completion delay (s) ↓", "Footprint separation (m) ↑", 5, 5)
        for row in rows:
            if row["target_style"] != style:
                continue
            xx, yy = sx(float(row["adjusted_delay_s"])), sy(float(row["footprint_margin_m"]))
            color = POLICY_COLORS[row["risk_policy"]]
            if row["predictor"] == "B1":
                svg.triangle(xx, yy, 8, color)
            else:
                svg.circle(xx, yy, 7, color, INK, 1)
        svg.text(x + w / 2, 120, f"({chr(97 + panel_index)}) {style.capitalize()} target", "panel", "middle")
        svg.text(x + w - 3, y + 18, "preferred ↗", "tiny", "end")
    legend_y = 615
    legend = [("adaptive", BLUE), ("fixed aggressive", ORANGE), ("fixed medium", GREEN), ("fixed conservative", PURPLE)]
    for index, (name, color) in enumerate(legend):
        xx = 155 + index * 190
        svg.circle(xx, legend_y, 6, color)
        svg.text(xx + 12, legend_y + 4, name, "small")
    svg.circle(920, legend_y, 6, WHITE, INK, 1.5)
    svg.text(935, legend_y + 4, "B0 ○", "small")
    svg.triangle(1010, legend_y, 6, WHITE)
    svg.text(1025, legend_y + 4, "B1 △", "small")
    svg.save(output / "figure05_day10_frontier.svg")
    return [
        "R_DAY10_RELIABILITY_FOOTPRINT_COLLISIONS",
        "R_DAY10_RELIABILITY_YIELD_ORDER_FAILURES",
        "R_DAY10_RELIABILITY_MIN_FOOTPRINT_SEPARATION_M",
        "R_DAY10_B1_REACTIVE_ADAPTIVE_ADJUSTED_DELAY_S",
        "R_DAY10_B1_REACTIVE_FIXED_AGGRESSIVE_ADJUSTED_DELAY_S",
        "R_DAY10_B1_REACTIVE_ADAPTIVE_FOOTPRINT_MARGIN_M",
        "R_DAY10_B1_REACTIVE_FIXED_AGGRESSIVE_FOOTPRINT_MARGIN_M",
    ]


def find_contrast(rows: list[dict[str, str]], contrast: str, metric: str) -> dict[str, str]:
    return next(row for row in rows if row["contrast"] == contrast and row["metric"] == metric)


def forest_panel(svg: SVG, rows: list[dict[str, str]], x: float, y: float, width: float, height: float, metric: str, metric_label: str, low: float, high: float) -> None:
    sx = lambda value: scale(value, low, high, x, x + width)
    offsets = [("offset_m3", "−3 m"), ("offset_0", "0 m"), ("offset_p3", "+3 m")]
    for tick_index in range(5):
        value = low + (high - low) * tick_index / 4
        xx = sx(value)
        svg.line(xx, y, xx, y + height, GRID, 1)
        svg.text(xx, y + height + 20, fmt(value, 2), "tiny", "middle")
    if low < 0 < high:
        svg.line(sx(0), y, sx(0), y + height, MUTED, 1.3)
    for offset_index, (token, label) in enumerate(offsets):
        base_y = y + 52 + offset_index * 92
        svg.text(x - 14, base_y + 7, label, "small", "end")
        for policy_index, (policy, color) in enumerate((("fixed_medium", GREEN), ("adaptive", BLUE))):
            row = find_contrast(rows, f"B1_minus_B0__{policy}__{token}", metric)
            yy = base_y + (-8 if policy_index == 0 else 10)
            effect, ci_low, ci_high = (float(row[k]) for k in ("effect", "ci95_low", "ci95_high"))
            svg.line(sx(ci_low), yy, sx(ci_high), yy, color, 3)
            svg.line(sx(ci_low), yy - 5, sx(ci_low), yy + 5, color, 1.5)
            svg.line(sx(ci_high), yy - 5, sx(ci_high), yy + 5, color, 1.5)
            svg.circle(sx(effect), yy, 6, color)
    svg.text(x + width / 2, y - 18, metric_label, "panel", "middle")
    svg.text(x + width / 2, y + height + 44, "B1 − B0 effect", "small", "middle")


def figure06_predictor_effect(tables: Path, output: Path) -> list[str]:
    rows = read_csv(tables / "table06_timing_robustness_key_contrasts.csv")
    svg = SVG(title="Predictor effect by risk policy and arrival timing")
    title(svg, "Predictor effect varies with risk policy and arrival timing", "Five-init cluster intervals; negative delay favours B1, positive separation favours B1.")
    forest_panel(svg, rows, 130, 170, 390, 320, "target_clearance_adjusted_completion_delay_s", "(a) Adjusted completion delay (s)", -1.7, 1.0)
    forest_panel(svg, rows, 730, 170, 390, 320, "min_footprint_separation_m", "(b) Minimum footprint separation (m)", -0.5, 0.3)
    svg.circle(315, 600, 6, GREEN)
    svg.text(329, 604, "fixed medium", "small")
    svg.circle(455, 600, 6, BLUE)
    svg.text(469, 604, "adaptive", "small")
    svg.text(600, 655, "Intervals crossing zero and sign changes across conditions reject a claim of uniform closed-loop gain.", "small", "middle")
    svg.save(output / "figure06_predictor_effect_moderation.svg")
    return [
        "R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_M3_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S",
        "R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_0_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S",
        "R_TIMING_B1_MINUS_B0_ADAPTIVE_OFFSET_P3_MIN_FOOTPRINT_SEPARATION_M",
    ]


def figure07_mechanism(tables: Path, output: Path) -> list[str]:
    rows = read_csv(tables / "table06_timing_robustness_key_contrasts.csv")
    svg = SVG(title="Arrival timing mechanism effects")
    title(svg, "Arrival timing changes safety margin, solver feasibility and supervisor activity", "+3 m minus −3 m effects for B1; five-init cluster intervals.")
    specs = [
        ("min_footprint_separation_m", "Separation (m)", 0.2, 1.45, 1),
        ("solver_failure_fraction", "Solver failures (pp)", 1.0, 3.2, 100),
        ("supervisor_active_fraction", "Supervisor activity (pp)", -10.5, -3.0, 100),
    ]
    for index, (metric, label, low, high, multiplier) in enumerate(specs):
        x = 85 + index * 390
        y, w, h = 180, 300, 300
        sx = lambda value, x=x, w=w, low=low, high=high: scale(value, low, high, x, x + w)
        for tick_index in range(5):
            value = low + (high - low) * tick_index / 4
            xx = sx(value)
            svg.line(xx, y, xx, y + h, GRID, 1)
            svg.text(xx, y + h + 20, fmt(value, 1 if multiplier == 100 else 2), "tiny", "middle")
        for policy_index, (policy, policy_label, color) in enumerate((("fixed_medium", "fixed medium", GREEN), ("adaptive", "adaptive", BLUE))):
            row = find_contrast(rows, f"offset_p3_minus_m3__B1__{policy}", metric)
            effect, ci_low, ci_high = (float(row[k]) * multiplier for k in ("effect", "ci95_low", "ci95_high"))
            yy = y + 100 + policy_index * 95
            svg.line(sx(ci_low), yy, sx(ci_high), yy, color, 4)
            svg.line(sx(ci_low), yy - 7, sx(ci_low), yy + 7, color, 1.5)
            svg.line(sx(ci_high), yy - 7, sx(ci_high), yy + 7, color, 1.5)
            svg.circle(sx(effect), yy, 7, color)
            svg.text(x, yy - 18, policy_label, "small")
            svg.text(sx(effect), yy + 28, fmt(effect, 2), "tiny", "middle")
        svg.text(x + w / 2, 145, f"({chr(97 + index)}) {label}", "panel", "middle")
    svg.rect(125, 565, 950, 65, LIGHT, GRID, 10)
    svg.text(600, 592, "+3 m increases physical separation and solver failure while reducing supervisor activity.", "label", "middle")
    svg.text(600, 616, "This is a coupled mechanism trade-off, not evidence that any single controller component is the sole cause.", "small", "middle")
    svg.save(output / "figure07_arrival_timing_mechanisms.svg")
    return [
        "R_TIMING_OFFSET_P3_MINUS_M3_B1_FIXED_MEDIUM_MIN_FOOTPRINT_SEPARATION_M",
        "R_TIMING_OFFSET_P3_MINUS_M3_B1_ADAPTIVE_SOLVER_FAILURE_FRACTION",
        "R_TIMING_OFFSET_P3_MINUS_M3_B1_ADAPTIVE_SUPERVISOR_ACTIVE_FRACTION",
    ]


def figure08_chain(output: Path) -> list[str]:
    svg = SVG(title="Deployment chain and measurement boundaries")
    title(svg, "Deployment chain and measurement boundaries", "The closed-loop result is a property of the coupled stack; each stage has a separately reported mechanism metric.")
    nodes = [
        ("Prediction", "Mixture trajectories\nNLL, ADE/FDE", BLUE),
        ("Risk allocation", "Fixed frontier or\nadaptive policy", ORANGE),
        ("Trajectory solver", "Feasibility and\nfailure fraction", GREEN),
        ("Supervisor", "Safety override and\nactive fraction", PURPLE),
        ("Executed motion", "Delay, separation,\nyield and collisions", RED),
    ]
    xs = [45, 285, 525, 765, 1005]
    for index, ((heading, body, color), x) in enumerate(zip(nodes, xs)):
        svg.rect(x, 190, 165, 180, WHITE, color, 12, 2)
        svg.rect(x, 190, 165, 42, color, color, 12, 0)
        svg.text(x + 82.5, 218, heading, "panel", "middle", fill=WHITE)
        for line_index, line in enumerate(body.split("\n")):
            svg.text(x + 82.5, 278 + line_index * 28, line, "label", "middle")
        if index < len(nodes) - 1:
            svg.line(x + 170, 280, xs[index + 1] - 8, 280, MUTED, 2, arrow=True)
    svg.line(1085, 375, 1085, 465, MUTED, 1.8)
    svg.line(1085, 465, 130, 465, MUTED, 1.8)
    svg.line(130, 465, 130, 380, MUTED, 1.8, arrow=True)
    svg.text(600, 487, "Closed-loop feedback: observed motion changes the next raster, state history and interaction sequence", "small", "middle")

    moderators = [("Arrival timing", 170), ("Target style", 410), ("Data regime", 650), ("Calibration", 890)]
    for label, x in moderators:
        svg.rect(x, 555, 150, 50, LIGHT, GRID, 10)
        svg.text(x + 75, 586, label, "label", "middle")
        svg.line(x + 75, 555, x + 75, 500, GRID, 1.5, arrow=True)
    svg.text(600, 660, "Arrows show implemented information/control flow, not identification of a single causal main effect.", "small", "middle")
    svg.save(output / "figure08_deployment_chain.svg")
    return ["R_DAY10_RELIABILITY_MAX_SOLVER_FAILURE_FRACTION", "R_TIMING_OBSERVED_COLLISIONS"]


def build(repo: Path, output: Path) -> dict[str, Any]:
    tables = repo / "docs/paper/generated/paper_assets_v1"
    completion_path = tables / "PAPER_TABLES_COMPLETE.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    manifest = json.loads((tables / "paper_results_manifest.json").read_text(encoding="utf-8"))
    if completion.get("status") != "pass" or manifest.get("status") != "pass":
        raise ValueError("Paper table/manifest gate did not pass")
    output.mkdir(parents=True, exist_ok=True)
    figure_evidence = {
        "figure01_research_workflow.svg": figure01_workflow(output),
        "figure02_model_architecture.svg": figure02_architecture(output),
        "figure03_offline_model_comparison.svg": figure03_model_comparison(tables, output),
        "figure04_calibration_tail.svg": figure04_calibration(tables, output),
        "figure05_day10_frontier.svg": figure05_frontier(tables, output),
        "figure06_predictor_effect_moderation.svg": figure06_predictor_effect(tables, output),
        "figure07_arrival_timing_mechanisms.svg": figure07_mechanism(tables, output),
        "figure08_deployment_chain.svg": figure08_chain(output),
    }
    for filename, ids in figure_evidence.items():
        if not (output / filename).is_file():
            raise FileNotFoundError(output / filename)
        missing = [result_id for result_id in ids if result_id not in manifest["results"]]
        if missing:
            raise ValueError(f"{filename} has unknown evidence IDs: {missing}")
    captions = [
        "# Canonical thesis figure captions",
        "",
        "> Generated alongside the figures. Figure numbers are stable; edit prose only by changing the generator.",
        "",
        "1. **Research workflow and evidence gates.** The project progresses from the initial adaptive-risk planning question through controlled interaction data, matched offline model comparison and a frozen predictor–controller evaluation. Negative and mixed findings are retained as evidence gates rather than hidden.",
        "2. **Matched model architecture and controls.** B2-M/T1 and B2-D/T2 isolate temporal attention from approximate parameter capacity while sharing the frozen MultiPath base and evaluation contract. B1 is the simple task-adaptation control.",
        "3. **Offline model comparison.** Points in panel (a) are the three validation seeds and horizontal segments are medians. Panel (b) reports ADE/FDE from each validation-selected frozen-test checkpoint plus pretrained B0. B1 is best under the registered selection metric and displacement errors.",
        "4. **Aggregate and response-active calibration.** Validation-frozen global calibration improves aggregate B1 NLL but substantially worsens its response-active-tail NLL. The tail contains only 15 windows from 6 rollouts and 3 init groups.",
        "5. **Nominal closed-loop safety–efficiency frontier.** Each mark is a five-rollout Day10 cell mean. No predictor–risk combination uniformly occupies the preferred upper-left region across target styles; zero observed collisions are an event count, not an estimated zero risk.",
        "6. **Predictor-effect moderation.** B1−B0 closed-loop effects and five-init cluster intervals vary by risk policy and arrival offset. Sign changes and intervals crossing zero reject a uniform closed-loop-gain claim despite strong offline B1 improvement.",
        "7. **Arrival-timing mechanisms.** Moving the target from −3 m to +3 m increases separation and solver failures while reducing supervisor activity. These simultaneous changes demonstrate a coupled trade-off rather than a single-component explanation.",
        "8. **Deployment chain and measurement boundaries.** Prediction, risk allocation, trajectory optimization, supervisor intervention and executed motion form a feedback system. Arrows describe implemented flow and do not by themselves identify causal effects.",
        "",
    ]
    captions_path = output / "figure_captions.md"
    captions_path.write_text("\n".join(captions), encoding="utf-8")
    figure_records = {}
    for filename, ids in figure_evidence.items():
        path = output / filename
        figure_records[filename] = {
            "sha256": sha256(path),
            "evidence_ids": ids,
            "source_files": sorted({manifest["results"][result_id]["source_file"] for result_id in ids}),
        }
    payload = {
        "schema_version": "ucl_thesis_paper_figures_v1",
        "status": "pass",
        "figure_count": len(figure_records),
        "source_results_manifest_sha256": sha256(tables / "paper_results_manifest.json"),
        "figures": figure_records,
        "captions_sha256": sha256(captions_path),
        "rules": [
            "Data figures use canonical paper tables generated from the frozen result manifest.",
            "Intervals use five ego-init clusters, never simulator steps.",
            "Zero observed collision counts are not population-risk estimates.",
            "Schematic arrows show implemented flow, not causal identification.",
        ],
    }
    atomic_json(output / "paper_figures_manifest.json", payload)
    atomic_json(
        output / "PAPER_FIGURES_COMPLETE.json",
        {
            "schema_version": "paper_figures_complete_v1",
            "status": "pass",
            "figure_count": len(figure_records),
            "figures_manifest_sha256": sha256(output / "paper_figures_manifest.json"),
            "source_results_manifest_sha256": payload["source_results_manifest_sha256"],
        },
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output_dir or repo / "docs/paper/generated/paper_assets_v1/figures").resolve()
    payload = build(repo, output)
    print(json.dumps({"status": payload["status"], "figure_count": payload["figure_count"]}, indent=2))


if __name__ == "__main__":
    main()
