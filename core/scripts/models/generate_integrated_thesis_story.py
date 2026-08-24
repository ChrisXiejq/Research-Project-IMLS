#!/usr/bin/env python3
"""Audit the full dissertation evidence chain and generate integrated figures.

This script deliberately keeps historical experiments separate from V3.  It
checks each study's own completion gate, records source hashes, and produces
figures whose panels preserve the correct independent units and protocols.
Historical and V3 scalar levels are never pooled into one estimator.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PALETTE = {
    # Restrained, colour-blind-safe palette suitable for journal figures.
    "navy": "#1B365D",
    "blue": "#0072B2",
    "cyan": "#56B4E9",
    "orange": "#D55E00",
    "red": "#A33A2B",
    "green": "#007F5F",
    "purple": "#6B5B95",
    "ink": "#202124",
    "muted": "#5F6368",
    "grid": "#D9D9D9",
    "panel": "#FFFFFF",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def mean(values: Iterable[float]) -> float:
    return statistics.fmean(float(value) for value in values)


def linear(value: float, low: float, high: float, start: float, end: float) -> float:
    if math.isclose(high, low):
        return (start + end) / 2
    return start + (value - low) / (high - low) * (end - start)


def svg_document(width: int, height: int, title: str, desc: str, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc>
<style>
text {{ font-family: Arial, Helvetica, sans-serif; fill: {PALETTE['ink']}; }}
.title {{ font-size: 18px; font-weight: 600; }}
.subtitle {{ font-size: 11.5px; fill: {PALETTE['muted']}; }}
.panel-title {{ font-size: 13px; font-weight: 600; }}
.label {{ font-size: 11px; }} .small {{ font-size: 9.5px; }}
.axis {{ stroke: {PALETTE['ink']}; stroke-width: 1.1; }}
.grid {{ stroke: {PALETTE['grid']}; stroke-width: .8; }}
.panel {{ fill: {PALETTE['panel']}; stroke: none; }}
</style><rect width="100%" height="100%" fill="#FFFFFF"/>{body}</svg>'''


def panel_frame(parts: list[str], x: float, y: float, w: float, h: float, tag: str, title: str) -> None:
    parts.append(f'<rect class="panel" x="{x}" y="{y}" width="{w}" height="{h}"/>')
    parts.append(f'<text class="panel-title" x="{x+18}" y="{y+28}">{escape(tag)}  {escape(title)}</text>')


def axes(
    parts: list[str], *, x0: float, x1: float, y0: float, y1: float,
    y_low: float, y_high: float, y_digits: int = 3, ticks: int = 4,
) -> None:
    parts.extend([
        f'<line class="axis" x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}"/>',
        f'<line class="axis" x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}"/>',
    ])
    for idx in range(ticks + 1):
        value = y_low + idx * (y_high - y_low) / ticks
        y = linear(value, y_low, y_high, y1, y0)
        parts.append(f'<line class="grid" x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}"/>')
        parts.append(f'<text class="small" x="{x0-8}" y="{y+3.5:.1f}" text-anchor="end">{value:.{y_digits}f}</text>')


def marker(parts: list[str], x: float, y: float, colour: str, shape: str, size: float = 4.0, opacity: float = 1.0) -> None:
    if shape == "square":
        parts.append(f'<rect x="{x-size}" y="{y-size}" width="{2*size}" height="{2*size}" rx="1" fill="{colour}" fill-opacity="{opacity}"/>')
    elif shape == "diamond":
        parts.append(f'<path d="M {x:.1f} {y-size:.1f} L {x+size:.1f} {y:.1f} L {x:.1f} {y+size:.1f} L {x-size:.1f} {y:.1f} Z" fill="{colour}" fill-opacity="{opacity}"/>')
    else:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size}" fill="{colour}" fill-opacity="{opacity}"/>')


def build_audit(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    p = lambda rel: repo / rel
    paths = {
        "foundation_gate": p("docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/SUPERVISOR_COMMENT_3_COMPLETE.json"),
        "foundation_cells": p("docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/frozen_test_same_aggregation.csv"),
        "foundation_pairs": p("docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/frozen_test_paired_summary.csv"),
        "r3_gate": p("docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/R3_COMPLETE.json"),
        "r3_analysis_gate": p("docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/R3_ANALYSIS_COMPLETE.json"),
        "r3_cells": p("docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_cell_outcome_summary.csv"),
        "r3_dominance": p("docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h4_dominance.csv"),
        "sf4_gate": p("docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/SF4_COMPLETE.json"),
        "sf4_analysis_gate": p("docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/analysis/SF4_ANALYSIS_COMPLETE.json"),
        "sf4_inference": p("docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/analysis/sf4_inference.json"),
        "v3_offline": p("docs/paper/generated/capacity_history_v3/results/postprocess/offline_synthesis.json"),
        "v3_training": p("docs/paper/generated/capacity_history_v3/results/postprocess/training_audit.json"),
        "v3_freeze": p("docs/paper/generated/capacity_history_v3/results/postprocess/selection_freeze.json"),
        "v3_closed_gate": p("docs/paper/generated/capacity_history_v3/results/closed_loop/CLOSED_LOOP_COMPLETE.json"),
        "v3_closed_audit": p("docs/paper/generated/capacity_history_v3/results/closed_loop/CLOSED_LOOP_AUDIT.json"),
        "v3_closed": p("docs/paper/generated/capacity_history_v3/results/closed_loop/PREDICTOR_BY_RISK_SYNTHESIS.json"),
        "v3_rows": p("docs/paper/generated/capacity_history_v3/results/closed_loop/closed_loop_rows.json"),
    }
    for name, path in paths.items():
        require(path.is_file(), f"Missing evidence file: {name}: {path}")

    foundation_gate = load_json(paths["foundation_gate"])
    foundation_cells = read_csv(paths["foundation_cells"])
    foundation_pairs = read_csv(paths["foundation_pairs"])
    require(foundation_gate.get("status") == "pass", "Foundation B0/B1 gate failed")
    require(int(foundation_gate["independent_paired_init_groups"]) == 5, "Foundation independent-unit count drifted")
    require(len(foundation_cells) == 4, "Foundation aggregation table must retain both aggregation levels")
    require(len(foundation_pairs) == 3, "Foundation paired table must retain NLL/ADE/FDE")

    r3_gate = load_json(paths["r3_gate"])
    r3_analysis_gate = load_json(paths["r3_analysis_gate"])
    r3_cells = read_csv(paths["r3_cells"])
    r3_dominance = read_csv(paths["r3_dominance"])
    require(r3_gate.get("status") == "pass" and r3_gate.get("formal_evidence") is True, "R3 completion gate failed")
    require(int(r3_gate["observed_rollouts"]) == 80, "R3 must retain 80 rollouts")
    require(r3_analysis_gate.get("status") == "pass" and int(r3_analysis_gate["observed_rollouts"]) == 80, "R3 analysis gate failed")
    require(len(r3_cells) == 16 and len(r3_dominance) == 12, "R3 factorial tables are incomplete")
    require(sum(row["dominance_status"] == "dominates" for row in r3_dominance) == 3, "R3 dominance count drifted")

    sf4_gate = load_json(paths["sf4_gate"])
    sf4_analysis_gate = load_json(paths["sf4_analysis_gate"])
    sf4 = load_json(paths["sf4_inference"])
    require(sf4_gate.get("status") == "pass" and sf4_gate.get("formal_evidence") is True, "SF4 gate failed")
    require(int(sf4_gate["observed_rollouts"]) == 80, "SF4 must retain 80 rollouts")
    require(sf4_analysis_gate.get("status") == "pass" and int(sf4_analysis_gate["observed_rollouts"]) == 80, "SF4 analysis gate failed")
    require(sf4.get("status") == "pass", "SF4 inference failed")

    offline = load_json(paths["v3_offline"])
    training = load_json(paths["v3_training"])
    freeze = load_json(paths["v3_freeze"])
    closed_gate = load_json(paths["v3_closed_gate"])
    closed_audit = load_json(paths["v3_closed_audit"])
    closed = load_json(paths["v3_closed"])
    v3_rows = load_json(paths["v3_rows"])
    require(offline.get("status") == "pass" and int(offline["evaluated_runs"]) == 27, "V3 offline synthesis failed")
    require(offline.get("evidence_status") == "retrospective_held_out", "V3 evidence label drifted")
    require(training.get("status") == "pass" and int(training["valid_runs"]) == 27, "V3 training audit failed")
    require(freeze.get("status") == "pass", "V3 selection freeze failed")
    require(closed_gate.get("status") == "pass" and closed_gate.get("formal_evidence") is True, "V3 closed-loop gate failed")
    require(int(closed_gate["observed_rollouts"]) == 80 and len(v3_rows) == 80, "V3 closed-loop matrix is incomplete")
    require(closed_audit.get("status") == "pass" and closed.get("status") == "pass", "V3 closed-loop audit/synthesis failed")

    b0 = next(row for row in foundation_cells if row["variant"] == "B0" and row["aggregation_level"] == "rollout_macro")
    b1 = next(row for row in foundation_cells if row["variant"] == "B1" and row["aggregation_level"] == "rollout_macro")
    sf_completion = sf4["direct_paired_effects"]["failure_penalized_completion_time_s"]
    sf_separation = sf4["direct_paired_effects"]["minimum_margin_adjusted_bbox_separation_m"]
    activity = sf4_analysis_gate["observed_first_stage_activity"]["by_authority"]
    audit = {
        "schema_version": "integrated_thesis_story_audit_v1",
        "status": "pass",
        "scientific_scope": "right-hand-traffic Town05 left-turn give-way; ego yields to an opposing straight-through target",
        "evidence_blocks": [
            {
                "id": "F1_foundation_adaptation",
                "role": "establishes the task-adapted B1 reference without using the withdrawn percentage accuracy",
                "design": "B0 versus B1; groups 46--50; 20 rollouts; 315 overlapping windows; 5 paired groups",
                "status": "pass",
                "key_results": {
                    "B0_NLL": float(b0["trajectory_mixture_NLL_nats_per_step"]),
                    "B1_NLL": float(b1["trajectory_mixture_NLL_nats_per_step"]),
                    "B0_ADE_m": float(b0["top1_ADE_m"]),
                    "B1_ADE_m": float(b1["top1_ADE_m"]),
                    "B0_FDE_m": float(b0["top1_FDE_m"]),
                    "B1_FDE_m": float(b1["top1_FDE_m"]),
                    "favourable_groups_each_metric": "5/5",
                },
                "claim_boundary": "one Town05 distribution; five independent groups; old 0.98%-to-100% mode-ranking headline withdrawn",
            },
            {
                "id": "F2_r3_broad_predictor_risk",
                "role": "broad closed-loop frontier and historical transfer boundary",
                "design": "B0/B1 x adaptive/fixed-aggressive/fixed-medium/fixed-conservative x two styles x groups 101--105",
                "status": "pass",
                "rollouts": 80,
                "key_results": {"B1_jointly_better_cells": "2/8", "adaptive_dominance_cells": "3/12"},
                "claim_boundary": "five paired groups; exact sign-flip sensitivity is coarse; no pooling with V3 groups 81--90",
            },
            {
                "id": "F3_sf4_supervisor_authority",
                "role": "mechanism ablation for shared supervisor authority",
                "design": "B1 x adaptive/fixed-medium x authority on/off x two styles x ten groups",
                "status": "pass",
                "rollouts": 80,
                "key_results": {
                    "completion_authority_effect_adaptive_s": sf_completion["authority_effect_adaptive"]["mean_effect"],
                    "completion_authority_effect_fixed_s": sf_completion["authority_effect_fixed_medium"]["mean_effect"],
                    "completion_risk_by_authority_DID_s": sf4["outcomes"]["failure_penalized_completion_time_s"]["mean_effect"],
                    "separation_risk_by_authority_DID_m": sf4["outcomes"]["minimum_margin_adjusted_bbox_separation_m"]["mean_effect"],
                    "authority_on_request_fraction": activity["on"]["any_channel_requested_fraction"],
                    "authority_on_applied_fraction": activity["on"]["authority_applied_fraction"],
                    "authority_off_request_fraction": activity["off"]["any_channel_requested_fraction"],
                    "authority_off_applied_fraction": activity["off"]["authority_applied_fraction"],
                    "separation_authority_effect_adaptive_m": sf_separation["authority_effect_adaptive"]["mean_effect"],
                    "separation_authority_effect_fixed_m": sf_separation["authority_effect_fixed_medium"]["mean_effect"],
                },
                "claim_boundary": "authority-off is a mechanism stress test, not a viable deployment recommendation; no selective risk-policy masking demonstrated",
            },
            {
                "id": "F4_v3_offline_three_axis",
                "role": "capacity, information and matched architecture decomposition",
                "design": "9 cells x 3 seeds; groups 1--35 fit, 36--40 selection/calibration, 41--45 retrospective held-out",
                "status": "pass",
                "runs": 27,
                "claim_boundary": "five retrospective held-out groups; H1--H3 scalar levels are not pooled with the older groups 46--50 foundation audit",
            },
            {
                "id": "F5_v3_selected_model_carla",
                "role": "prospective H4a/H4b test for frozen P* and risk",
                "design": "B1/P* x fixed-medium/adaptive x two styles x groups 81--90",
                "status": "pass",
                "rollouts": 80,
                "claim_boundary": "ten paired groups; prediction diagnostics differ, but physical interaction intervals cross zero; zero collisions are not safety proof",
            },
        ],
        "compatibility_rules": [
            "Do not pool historical groups 46--50, R3 groups 101--105, SF4 groups, V3 groups 41--45, or V3 CARLA groups 81--90 as a single independent sample.",
            "Use F1 to justify B1 as a strong task-adapted reference, not as a V3 H1 capacity result.",
            "Use F2 for the broad adaptive-versus-three-fixed frontier and F5 for the prospectively frozen best-model transfer test.",
            "Use F3 only to test supervisor mechanism; authority-off is not a recommended controller.",
            "All universal superiority, safety, equivalence and cross-map claims remain prohibited.",
        ],
        "integrated_hypotheses": {
            "H1": "At 1.0 s history, greater Transformer trainable capacity reduces held-out rollout-macro NLL with a coherent capacity trend.",
            "H2": "At matched large capacity, older explicit interaction tokens add predictive information beyond the current interaction state for both encoder families.",
            "H3": "At matched capacity and information, attention extracts more history value than an MLP, requiring a favourable history-gain interaction in addition to direct model gaps.",
            "H4": "Closed-loop utility: (a) validation-selected P* retains its prediction advantage and improves CARLA completion/separation relative to B1; (b) adaptive risk offers a better efficiency-separation operating point than fixed risk in the give-way task.",
        },
        "source_hashes": {name: sha256(path) for name, path in paths.items()},
    }
    data = {
        "offline": offline,
        "v3_rows": v3_rows,
        "r3_cells": r3_cells,
        "r3_dominance": r3_dominance,
        "foundation_cells": foundation_cells,
        "foundation_pairs": foundation_pairs,
        "sf4": sf4,
        "sf4_analysis_gate": sf4_analysis_gate,
        "audit": audit,
    }
    return audit, data


def figure_offline(path: Path, offline: Mapping[str, Any]) -> None:
    cells = {row["model_cell_id"]: row for row in offline["cell_summaries"]}
    width, height = 1260, 570
    parts = [
        '<text class="title" x="54" y="40">Controlled offline ablations</text>',
        '<text class="subtitle" x="54" y="62">Thin lines denote random seeds; bold lines denote means under matched evaluation units.</text>',
    ]
    panel_frame(parts, 42, 82, 736, 445, "A", "Information and architecture at matched large capacity")
    x0, x1, y0, y1 = 120, 744, 135, 430
    hist_ids = {
        "MLP": ["mlp-h0p0-large", "mlp-h0p4-large", "mlp-h1p0-large"],
        "Transformer": ["transformer-h0p0-large", "transformer-h0p4-large", "transformer-h1p0-large"],
    }
    vals = [float(cells[mid]["per_seed"][str(seed)]) for mids in hist_ids.values() for mid in mids for seed in (11, 23, 37)]
    b1 = float(cells["head-large"]["heldout_rollout_macro_nll_mean"])
    low, high = min(vals) - .0015, max(max(vals), b1) + .0015
    axes(parts, x0=x0, x1=x1, y0=y0, y1=y1, y_low=low, y_high=high, y_digits=3)
    horizons = [0.0, .4, 1.0]
    for horizon in horizons:
        x = linear(horizon, 0, 1, x0, x1)
        parts.append(f'<text class="label" x="{x:.1f}" y="{y1+22}" text-anchor="middle">{horizon:.1f}</text>')
    parts.append(f'<text class="label" x="{(x0+x1)/2}" y="{y1+45}" text-anchor="middle">Explicit interaction history (s)</text>')
    parts.append(f'<text class="small" transform="translate({x0-56} {(y0+y1)/2}) rotate(-90)" text-anchor="middle">Rollout-macro NLL (lower is better)</text>')
    styles = {"MLP": (PALETTE["orange"], "circle"), "Transformer": (PALETTE["blue"], "square")}
    for name, mids in hist_ids.items():
        colour, shape = styles[name]
        for seed_idx, seed in enumerate((11, 23, 37)):
            points = []
            for horizon, mid in zip(horizons, mids):
                x = linear(horizon, 0, 1, x0, x1)
                y = linear(float(cells[mid]["per_seed"][str(seed)]), low, high, y1, y0)
                points.append(f"{x:.1f},{y:.1f}")
                marker(parts, x, y, colour, shape, 3, .38)
            parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colour}" stroke-width="1.2" stroke-opacity=".38"/>')
        points = []
        for horizon, mid in zip(horizons, mids):
            x = linear(horizon, 0, 1, x0, x1)
            value = float(cells[mid]["heldout_rollout_macro_nll_mean"])
            y = linear(value, low, high, y1, y0)
            points.append(f"{x:.1f},{y:.1f}")
            marker(parts, x, y, colour, shape, 5.3)
            label_x = x + 8 if math.isclose(horizon, 0.0) else x
            label_anchor = "start" if math.isclose(horizon, 0.0) else "middle"
            parts.append(f'<text class="small" x="{label_x:.1f}" y="{y-10:.1f}" text-anchor="{label_anchor}">{value:.4f}</text>')
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colour}" stroke-width="3"/>')
    yb = linear(b1, low, high, y1, y0)
    parts.append(f'<line x1="{x0}" y1="{yb:.1f}" x2="{x1}" y2="{yb:.1f}" stroke="{PALETTE["muted"]}" stroke-width="1.4" stroke-dasharray="7 5"/>')
    parts.append(f'<text class="small" x="{x1-4}" y="{yb-7:.1f}" text-anchor="end">B1 allocation reference {b1:.4f}</text>')
    parts.extend([
        f'<line x1="160" y1="505" x2="194" y2="505" stroke="{PALETTE["orange"]}" stroke-width="3"/><circle cx="177" cy="505" r="4" fill="{PALETTE["orange"]}"/><text class="small" x="202" y="509">MLP mean + 3 seed paths</text>',
        f'<line x1="430" y1="505" x2="464" y2="505" stroke="{PALETTE["blue"]}" stroke-width="3"/><rect x="443" y="501" width="8" height="8" fill="{PALETTE["blue"]}"/><text class="small" x="472" y="509">Transformer mean + 3 seed paths</text>',
    ])

    panel_frame(parts, 798, 82, 420, 445, "B", "Capacity at 1.0 s history")
    cx0, cx1, cy0, cy1 = 860, 1185, 135, 430
    cap_ids = ["transformer-h1p0-small", "transformer-h1p0-medium", "transformer-h1p0-large"]
    cap_vals = [float(cells[mid]["per_seed"][str(seed)]) for mid in cap_ids for seed in (11, 23, 37)]
    clow, chigh = min(cap_vals) - .0008, max(cap_vals) + .0008
    axes(parts, x0=cx0, x1=cx1, y0=cy0, y1=cy1, y_low=clow, y_high=chigh, y_digits=4)
    labels = ["0.167M", "0.498M", "1.027M"]
    for idx, label in enumerate(labels):
        x = linear(idx, 0, 2, cx0, cx1)
        parts.append(f'<text class="label" x="{x:.1f}" y="{cy1+22}" text-anchor="middle">{label}</text>')
    parts.append(f'<text class="label" x="{(cx0+cx1)/2}" y="{cy1+45}" text-anchor="middle">Trainable parameters</text>')
    for seed in (11, 23, 37):
        points = []
        for idx, mid in enumerate(cap_ids):
            x = linear(idx, 0, 2, cx0, cx1)
            y = linear(float(cells[mid]["per_seed"][str(seed)]), clow, chigh, cy1, cy0)
            points.append(f"{x:.1f},{y:.1f}")
            marker(parts, x, y, PALETTE["blue"], "square", 3, .38)
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{PALETTE["blue"]}" stroke-width="1.2" stroke-opacity=".38"/>')
    points = []
    for idx, mid in enumerate(cap_ids):
        x = linear(idx, 0, 2, cx0, cx1)
        value = float(cells[mid]["heldout_rollout_macro_nll_mean"])
        y = linear(value, clow, chigh, cy1, cy0)
        points.append(f"{x:.1f},{y:.1f}")
        marker(parts, x, y, PALETTE["blue"], "square", 5.3)
        label_x = x + 9 if idx == 0 else x
        label_anchor = "start" if idx == 0 else "middle"
        parts.append(f'<text class="small" x="{label_x:.1f}" y="{y-11:.1f}" text-anchor="{label_anchor}">{value:.4f}</text>')
    parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{PALETTE["blue"]}" stroke-width="3"/>')
    parts.append(f'<text class="small" x="{(cx0+cx1)/2}" y="507" text-anchor="middle">Medium is numerically best: no monotonic scaling curve</text>')
    atomic_text(path, svg_document(width, height, "Offline factor landscape", "Seed-level and mean history and capacity curves for the V3 offline study.", "\n".join(parts)))


def aggregate_v3(rows: Sequence[Mapping[str, Any]], metric: str) -> dict[tuple[str, str, str], float]:
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["predictor"], row["risk_policy"], row["target_style"])].append(float(row[metric]))
    return {key: mean(values) for key, values in grouped.items()}


def figure_v3_closed(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    width, height = 1320, 530
    parts = [
        '<text class="title" x="48" y="38">Closed-loop predictor-risk response</text>',
        '<text class="subtitle" x="48" y="60">Task-adapted and validation-selected predictors across risk policy and target response.</text>',
    ]
    panels = [
        ("completion_time_s", "A", "Completion time", "s", 10.2, 12.55, 2),
        ("min_footprint_separation_m", "B", "Minimum separation", "m", 1.06, 1.18, 3),
        ("inloop_top1_ADE_m", "C", "In-loop top-1 ADE", "m", .05, .48, 2),
    ]
    risks = ["fixed_medium", "adaptive"]
    series = [
        ("B1", "assertive_constant_speed", "B1 / assertive", PALETTE["navy"], "circle", ""),
        ("B1", "defensive_reactive", "B1 / reactive", PALETTE["cyan"], "circle", "7 4"),
        ("P_star", "assertive_constant_speed", "P* / assertive", PALETTE["orange"], "square", ""),
        ("P_star", "defensive_reactive", "P* / reactive", PALETTE["red"], "square", "7 4"),
    ]
    for panel_idx, (metric, tag, title, unit, low, high, digits) in enumerate(panels):
        px = 38 + panel_idx * 427
        panel_frame(parts, px, 79, 405, 395, tag, title)
        x0, x1, y0, y1 = px + 64, px + 370, 132, 399
        axes(parts, x0=x0, x1=x1, y0=y0, y1=y1, y_low=low, y_high=high, y_digits=digits)
        agg = aggregate_v3(rows, metric)
        for ix, risk in enumerate(risks):
            x = linear(ix, 0, 1, x0, x1)
            label = "Fixed medium" if risk == "fixed_medium" else "Adaptive"
            parts.append(f'<text class="label" x="{x:.1f}" y="{y1+22}" text-anchor="middle">{label}</text>')
        for predictor, style, _, colour, shape, dash in series:
            points = []
            for ix, risk in enumerate(risks):
                x = linear(ix, 0, 1, x0, x1)
                value = agg[(predictor, risk, style)]
                y = linear(value, low, high, y1, y0)
                points.append(f"{x:.1f},{y:.1f}")
                marker(parts, x, y, colour, shape, 5)
                if metric == "inloop_top1_ADE_m" or style == "assertive_constant_speed":
                    label_y = y - 10
                    if metric == "min_footprint_separation_m" and predictor == "P_star":
                        label_y = y + 18
                    if metric == "inloop_top1_ADE_m" and style == "assertive_constant_speed" and predictor == "P_star":
                        label_y = y + 18
                    parts.append(f'<text class="small" x="{x:.1f}" y="{label_y:.1f}" text-anchor="middle">{value:.{digits+1}f}</text>')
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colour}" stroke-width="2.7"{dash_attr}/>')
        parts.append(f'<text class="small" transform="translate({px+18} {(y0+y1)/2}) rotate(-90)" text-anchor="middle">{escape(unit)} (preferred: {"lower" if metric != "min_footprint_separation_m" else "higher"})</text>')
    legend_y = 505
    for idx, (_, _, label, colour, shape, dash) in enumerate(series):
        x = 225 + idx * 245
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<line x1="{x}" y1="{legend_y-4}" x2="{x+34}" y2="{legend_y-4}" stroke="{colour}" stroke-width="2.7"{dash_attr}/>')
        marker(parts, x + 17, legend_y - 4, colour, shape, 4.5)
        parts.append(f'<text class="small" x="{x+43}" y="{legend_y}">{escape(label)}</text>')
    atomic_text(path, svg_document(width, height, "Closed-loop factorial response", "Three physical and predictive outcomes for four predictor-style series under fixed and adaptive risk.", "\n".join(parts)))


def figure_r3_frontier(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    width, height = 1260, 535
    parts = [
        '<text class="title" x="50" y="39">Risk-policy response across predictor and target behaviour</text>',
        '<text class="subtitle" x="50" y="61">Three fixed settings and adaptive risk; points are paired initialisation-group means.</text>',
    ]
    panels = [
        ("ego_route_completion_duration_s_mean", "A", "Completion time", 9.8, 11.35, 2, "s; lower is better"),
        ("minimum_footprint_separation_m_mean", "B", "Minimum footprint separation", 1.11, 1.24, 3, "m; higher is better"),
    ]
    policies = ["fixed_aggressive", "fixed_medium", "fixed_conservative", "adaptive"]
    series = [
        ("B0", "assertive", "B0 / assertive", PALETTE["navy"], "circle", ""),
        ("B0", "reactive", "B0 / reactive", PALETTE["cyan"], "circle", "7 4"),
        ("B1", "assertive", "B1 / assertive", PALETTE["orange"], "square", ""),
        ("B1", "reactive", "B1 / reactive", PALETTE["red"], "square", "7 4"),
    ]
    lookup = {(r["predictor"], r["risk_policy"], r["target_style"]): r for r in rows}
    for panel_idx, (metric, tag, title, low, high, digits, unit) in enumerate(panels):
        px = 38 + panel_idx * 610
        panel_frame(parts, px, 80, 585, 395, tag, title)
        x0, x1, y0, y1 = px + 72, px + 550, 132, 400
        axes(parts, x0=x0, x1=x1, y0=y0, y1=y1, y_low=low, y_high=high, y_digits=digits)
        for ix, policy in enumerate(policies):
            x = linear(ix, 0, 3, x0, x1)
            label = {"fixed_aggressive": "Fixed agg.", "fixed_medium": "Fixed med.", "fixed_conservative": "Fixed cons.", "adaptive": "Adaptive"}[policy]
            parts.append(f'<text class="small" x="{x:.1f}" y="{y1+22}" text-anchor="middle">{label}</text>')
        for predictor, style, _, colour, shape, dash in series:
            points = []
            for ix, policy in enumerate(policies):
                value = float(lookup[(predictor, policy, style)][metric])
                x = linear(ix, 0, 3, x0, x1)
                y = linear(value, low, high, y1, y0)
                points.append(f"{x:.1f},{y:.1f}")
                marker(parts, x, y, colour, shape, 4.7)
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colour}" stroke-width="2.6"{dash_attr}/>')
        parts.append(f'<text class="small" transform="translate({px+19} {(y0+y1)/2}) rotate(-90)" text-anchor="middle">{escape(unit)}</text>')
    legend_y = 508
    for idx, (_, _, label, colour, shape, dash) in enumerate(series):
        x = 200 + idx * 250
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<line x1="{x}" y1="{legend_y-4}" x2="{x+34}" y2="{legend_y-4}" stroke="{colour}" stroke-width="2.7"{dash_attr}/>')
        marker(parts, x + 17, legend_y - 4, colour, shape, 4.5)
        parts.append(f'<text class="small" x="{x+43}" y="{legend_y}">{escape(label)}</text>')
    atomic_text(path, svg_document(width, height, "Risk-policy response", "Four predictor-style lines across adaptive and three fixed risk policies.", "\n".join(parts)))


def figure_evidence_chain(path: Path, data: Mapping[str, Any]) -> None:
    width, height = 1280, 510
    parts = [
        '<text class="title" x="48" y="39">Prediction gain, closed-loop transfer and supervisory mechanism</text>',
        '<text class="subtitle" x="48" y="61">Panels retain their own estimands and scales; no cross-experiment pooling is applied.</text>',
    ]
    # Panel A: foundation B0 -> B1 ratios, three lines on a common relative scale.
    panel_frame(parts, 35, 82, 385, 380, "A", "Task adaptation")
    cells = {(r["variant"], r["aggregation_level"]): r for r in data["foundation_cells"]}
    b0 = cells[("B0", "rollout_macro")]
    b1 = cells[("B1", "rollout_macro")]
    metrics = [
        ("NLL", "trajectory_mixture_NLL_nats_per_step", PALETTE["purple"]),
        ("ADE", "top1_ADE_m", PALETTE["orange"]),
        ("FDE", "top1_FDE_m", PALETTE["blue"]),
    ]
    x0, x1, y0, y1 = 105, 385, 140, 380
    axes(parts, x0=x0, x1=x1, y0=y0, y1=y1, y_low=0, y_high=1.05, y_digits=2)
    for x, label in ((x0, "B0"), (x1, "B1")):
        parts.append(f'<text class="label" x="{x}" y="{y1+21}" text-anchor="middle">{label}</text>')
    for idx, (label, field, colour) in enumerate(metrics):
        ratio = float(b1[field]) / float(b0[field])
        y_start = linear(1.0, 0, 1.05, y1, y0)
        y_end = linear(ratio, 0, 1.05, y1, y0)
        offset = (idx - 1) * 5
        parts.append(f'<line x1="{x0}" y1="{y_start+offset:.1f}" x2="{x1}" y2="{y_end:.1f}" stroke="{colour}" stroke-width="3"/>')
        marker(parts, x0, y_start + offset, colour, "circle", 4.8)
        marker(parts, x1, y_end, colour, "circle", 4.8)
        label_y = y_end - 8 if label == "NLL" else y_end - 11 if label == "ADE" else y_end + 17
        parts.append(f'<text class="small" x="{x1-8}" y="{label_y:.1f}" text-anchor="end">{label}: {ratio:.3f}x</text>')
    parts.append('<text class="small" x="245" y="435" text-anchor="middle">Relative error (B0 = 1.0); all metrics favour B1 in 5/5 groups</text>')

    # Panel B: R3 transfer counts.
    panel_frame(parts, 444, 82, 385, 380, "B", "Closed-loop transfer")
    bars = [("B1 jointly better", 2, 8, PALETTE["blue"]), ("Adaptive dominates", 3, 12, PALETTE["green"])]
    bx0, bx1 = 520, 790
    for idx, (label, count, total, colour) in enumerate(bars):
        y = 190 + idx * 120
        parts.append(f'<text class="label" x="{bx0}" y="{y-16}">{escape(label)}</text>')
        parts.append(f'<rect x="{bx0}" y="{y}" width="{bx1-bx0}" height="28" rx="7" fill="#E5EBF0"/>')
        parts.append(f'<rect x="{bx0}" y="{y}" width="{(bx1-bx0)*count/total:.1f}" height="28" rx="7" fill="{colour}"/>')
        parts.append(f'<text x="{bx1-4}" y="{y+20}" text-anchor="end" class="label">{count}/{total}</text>')
    parts.append('<text class="small" x="636" y="434" text-anchor="middle">Strong in-loop prediction difference; physical utility remains condition-specific</text>')

    # Panel C: supervisor common effects and near-zero interaction.
    panel_frame(parts, 852, 82, 393, 380, "C", "Supervisor mechanism")
    sf = data["sf4"]
    records = [
        ("Authority, adaptive", sf["direct_paired_effects"]["failure_penalized_completion_time_s"]["authority_effect_adaptive"], PALETTE["orange"]),
        ("Authority, fixed", sf["direct_paired_effects"]["failure_penalized_completion_time_s"]["authority_effect_fixed_medium"], PALETTE["blue"]),
        ("Risk-policy interaction", sf["outcomes"]["failure_penalized_completion_time_s"], PALETTE["green"]),
    ]
    fx0, fx1, fy0, fy1 = 975, 1210, 140, 375
    low, high = -20.5, 2.0
    zero = linear(0, low, high, fx0, fx1)
    parts.append(f'<line class="grid" x1="{zero:.1f}" y1="{fy0}" x2="{zero:.1f}" y2="{fy1}" stroke-width="1.5"/>')
    parts.append(f'<line class="axis" x1="{fx0}" y1="{fy1}" x2="{fx1}" y2="{fy1}"/>')
    for idx, (label, rec, colour) in enumerate(records):
        y = 180 + idx * 77
        effect = float(rec["mean_effect"])
        lo, hi = [float(v) for v in rec["cluster_bootstrap_95ci"]]
        xe, xl, xh = [linear(v, low, high, fx0, fx1) for v in (effect, lo, hi)]
        parts.append(f'<text class="small" x="{fx0-8}" y="{y+4}" text-anchor="end">{escape(label)}</text>')
        parts.append(f'<line x1="{xl:.1f}" y1="{y}" x2="{xh:.1f}" y2="{y}" stroke="{colour}" stroke-width="2.6"/>')
        parts.append(f'<line x1="{xl:.1f}" y1="{y-5}" x2="{xl:.1f}" y2="{y+5}" stroke="{colour}"/><line x1="{xh:.1f}" y1="{y-5}" x2="{xh:.1f}" y2="{y+5}" stroke="{colour}"/>')
        marker(parts, xe, y, colour, "diamond", 5)
        parts.append(f'<text class="small" x="{xe:.1f}" y="{y-11}" text-anchor="middle">{effect:+.2f} s</text>')
    for value in (-20, -10, 0):
        x = linear(value, low, high, fx0, fx1)
        parts.append(f'<text class="small" x="{x:.1f}" y="{fy1+20}" text-anchor="middle">{value}</text>')
    parts.append('<text class="small" x="1092" y="424" text-anchor="middle">Large common authority benefit;</text>')
    parts.append('<text class="small" x="1092" y="440" text-anchor="middle">no selective adaptive-risk masking</text>')
    atomic_text(path, svg_document(width, height, "Integrated evidence chain", "Foundation task adaptation, broad closed-loop transfer, and supervisor mechanism evidence.", "\n".join(parts)))


def render_png(svg_path: Path) -> Path:
    png_path = svg_path.with_suffix(".png")
    subprocess.run(
        ["rsvg-convert", "--width", "2400", "--keep-aspect-ratio", "--output", str(png_path), str(svg_path)],
        check=True,
    )
    return png_path


def audit_markdown(audit: Mapping[str, Any]) -> str:
    blocks = {row["id"]: row for row in audit["evidence_blocks"]}
    return f"""# Integrated dissertation experiment and story audit

**Status:** PASS. The complete story uses five separately gated evidence blocks. Their scalar levels and independent units are not pooled.

## Scenario fixed in the paper

The task is a Town05 unsignalised give-way interaction under right-hand traffic. The ego vehicle turns left across the path of an opposing target that proceeds straight. The ego must yield before the conflict zone and resume after clearance.

## Evidence blocks

1. **F1 foundation adaptation:** {blocks['F1_foundation_adaptation']['design']}. This establishes B1 as a strong task-adapted reference. The old 0.98%-to-100% number is withdrawn because it was a mode-ranking hit rate, not trajectory accuracy.
2. **F2 broad predictor-risk matrix:** {blocks['F2_r3_broad_predictor_risk']['design']}. B1 is jointly faster and no worse in separation in 2/8 cells; adaptive risk dominates a fixed comparator in 3/12 cells.
3. **F3 supervisor authority:** {blocks['F3_sf4_supervisor_authority']['design']}. Authority produces a large common benefit but does not demonstrate selective masking of the adaptive-minus-fixed contrast.
4. **F4 V3 offline decomposition:** {blocks['F4_v3_offline_three_axis']['design']}. This is the authoritative Capacity, Information and Architecture ablation.
5. **F5 V3 selected-model deployment:** {blocks['F5_v3_selected_model_carla']['design']}. This prospectively tests transfer of validation-selected P* and its interaction with risk.

## Integrated H1--H4

- **H1 Capacity:** {audit['integrated_hypotheses']['H1']}
- **H2 Information:** {audit['integrated_hypotheses']['H2']}
- **H3 Architecture:** {audit['integrated_hypotheses']['H3']}
- **H4 Closed-loop utility:** {audit['integrated_hypotheses']['H4']}

## Licensed story

The pretrained foundation is substantially misaligned with the bounded give-way distribution, and task-specific adaptation corrects that mismatch. Within the task-trained sequence family, explicit recent interaction history adds a small, saturating gain; capacity is not the persuasive explanation and the direct Transformer advantage is not attention-specific. The validation-frozen best sequence model remains predictively distinguishable in CARLA, but neither it nor adaptive risk is uniformly superior on physical outcomes. Risk, SMPC and the active supervisor compress, reverse or preserve model differences according to the decision context.

## Non-negotiable evidence boundaries

""" + "\n".join(f"- {rule}" for rule in audit["compatibility_rules"]) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    output = (args.output_dir or repo / "docs/paper/generated/integrated_thesis_story_v1").resolve()
    audit, data = build_audit(repo)
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / "INTEGRATED_STORY_AUDIT.json", audit)
    atomic_text(output / "INTEGRATED_STORY_AUDIT.md", audit_markdown(audit))
    figures = {
        "offline_factor_landscape": output / "figure_offline_factor_landscape.svg",
        "v3_closed_loop_factorial": output / "figure_v3_closed_loop_factorial.svg",
        "r3_risk_frontier": output / "figure_r3_risk_frontier.svg",
        "integrated_evidence_chain": output / "figure_integrated_evidence_chain.svg",
    }
    figure_offline(figures["offline_factor_landscape"], data["offline"])
    figure_v3_closed(figures["v3_closed_loop_factorial"], data["v3_rows"])
    figure_r3_frontier(figures["r3_risk_frontier"], data["r3_cells"])
    figure_evidence_chain(figures["integrated_evidence_chain"], data)
    pngs = {name: render_png(path) for name, path in figures.items()}
    manifest = {
        "schema_version": "integrated_thesis_story_products_v1",
        "status": "pass",
        "audit_sha256": sha256(output / "INTEGRATED_STORY_AUDIT.json"),
        "products": {
            **{path.name: sha256(path) for path in figures.values()},
            **{path.name: sha256(path) for path in pngs.values()},
        },
    }
    atomic_json(output / "INTEGRATED_PRODUCTS.json", manifest)
    print(json.dumps({"status": "pass", "output": str(output), "products": sorted(manifest["products"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
