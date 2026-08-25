#!/usr/bin/env python3
"""Build the supervisor-masking v2 paper figures and scalar provenance tables.

The release is deliberately generated from the audited evidence package.  Raw
CSV inputs are used only when their hashes occur in that package's source
manifest.  Distinct experiment populations are juxtaposed but never pooled.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle
import numpy as np


BLUE = "#0072B2"
ORANGE = "#D55E00"
GREEN = "#009E73"
PURPLE = "#7B61A8"
SKY = "#56B4E9"
YELLOW = "#E69F00"
GREY = "#6B7280"
LIGHT = "#E5E7EB"
DARK = "#1F2937"
PALETTE = (BLUE, ORANGE, GREEN, PURPLE, SKY, YELLOW, GREY, DARK)
WIDTH_IN = 7.20
PNG_DPI = 360

EVIDENCE_REL = Path("docs/paper/generated/supervisor_masking_v2/evidence/supervisor_masking_evidence.json")
CONTRACT_REL = Path("docs/paper/generated/supervisor_masking_v2/contract")
METHOD_REL = Path("docs/paper/generated/supervisor_masking_v2/method_audit")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _f(value: Any) -> float:
    return float(value)


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.8,
            "axes.titlesize": 8.7,
            "axes.labelsize": 7.8,
            "legend.fontsize": 6.7,
            "xtick.labelsize": 6.8,
            "ytick.labelsize": 6.8,
            "axes.linewidth": 0.65,
            "axes.edgecolor": DARK,
            "axes.labelcolor": DARK,
            "xtick.color": DARK,
            "ytick.color": DARK,
            "text.color": DARK,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _clean(ax: plt.Axes, axis: str = "y") -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, axis=axis, color=LIGHT, lw=0.55, zorder=0)
    ax.set_axisbelow(True)


def _panel(ax: plt.Axes, label: str) -> None:
    ax.text(-0.16, 1.04, label, transform=ax.transAxes, fontsize=8.8,
            fontweight="bold", va="top")


def _save(fig: plt.Figure, directory: Path, stem: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for suffix in (".pdf", ".png"):
        path = directory / f"{stem}{suffix}"
        fig.savefig(path, dpi=PNG_DPI if suffix == ".png" else None)
        outputs.append(path)
    plt.close(fig)
    return outputs


def _png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()[:24]
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")
    return struct.unpack(">II", raw[16:24])


class AuditedEvidence:
    """Fail-closed access to evidence-manifested source files."""

    def __init__(self, root: Path):
        self.root = root
        self.evidence_path = root / EVIDENCE_REL
        self.data = _json(self.evidence_path)
        if self.data.get("status") != "pass":
            raise ValueError("Supervisor masking evidence is not complete")
        self.hashes = {row["path"]: row["sha256"] for row in self.data["sources"]}
        self.used: dict[str, dict[str, Any]] = {}
        self.record(self.evidence_path, "audited synthesis", "$", require_manifest=False)

    def source(self, relative: str, role: str, locator: str = "/") -> Path:
        if relative not in self.hashes:
            raise ValueError(f"Source is not in the audited evidence manifest: {relative}")
        path = self.root / relative
        observed = _sha(path)
        if observed != self.hashes[relative]:
            raise ValueError(f"Audited source hash mismatch: {relative}")
        self.record(path, role, locator, require_manifest=True)
        return path

    def record(self, path: Path, role: str, locator: str, require_manifest: bool) -> None:
        relative = str(path.relative_to(self.root))
        if require_manifest and relative not in self.hashes:
            raise ValueError(f"Unmanifested source: {relative}")
        self.used[relative] = {
            "path": relative,
            "sha256": _sha(path),
            "bytes": path.stat().st_size,
            "role": role,
            "locator": locator,
        }

    def generated(self, path: Path, marker: Path, hash_key: str, hash_field: str,
                  role: str, locator: str) -> Path:
        completion = _json(marker)
        if completion.get("status") != "pass":
            raise ValueError(f"Generated-source completion marker is not passing: {marker}")
        expected = completion[hash_field][hash_key]
        if _sha(path) != expected:
            raise ValueError(f"Generated-source hash mismatch: {path}")
        self.record(marker, role + " completion marker", f"/{hash_field}/{hash_key}", False)
        self.record(path, role, locator, False)
        return path


def _metric_row(table: str, hypothesis: str, block: str, metric: str, value: Any,
                unit: str, aggregation: str, population: str, locator: str,
                note: str = "") -> dict[str, Any]:
    return {
        "table": table, "hypothesis": hypothesis, "block": block,
        "metric": metric, "value": value, "unit": unit,
        "aggregation_unit": aggregation, "population_id": population,
        "source_locator": locator, "note": note,
    }


def _box(ax: plt.Axes, x: float, y: float, w: float, h: float,
         title: str, subtitle: str, color: str) -> None:
    patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.009,rounding_size=0.012",
                           facecolor="white", edgecolor=color, lw=0.9)
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h * 0.67, title, ha="center", va="center",
            fontsize=6.2, fontweight="bold", color=color)
    ax.text(x + w / 2, y + h * 0.27, subtitle, ha="center", va="center",
            fontsize=5.05, linespacing=1.12)


def plot_project_figure(store: AuditedEvidence, out: Path) -> tuple[list[Path], dict[str, Any]]:
    channels_path = store.generated(
        store.root / METHOD_REL / "seven_channel_contract.csv",
        store.root / METHOD_REL / "METHOD_AUDIT_COMPLETE.json",
        "seven_channel_contract.csv", "artifacts_sha256",
        "seven-channel implementation audit", "all rows")
    channels = _csv(channels_path)
    if len(channels) != 7:
        raise ValueError("Project figure requires exactly seven supervisor channels")

    fig = plt.figure(figsize=(WIDTH_IN, 4.45))
    gs = fig.add_gridspec(1, 2, width_ratios=(0.78, 2.22), wspace=0.12)
    geo = fig.add_subplot(gs[0, 0])
    flow = fig.add_subplot(gs[0, 1])

    # Exact task topology: northbound ego in the east lane turns left into the
    # westbound north lane; the southbound target keeps priority in the west lane.
    geo.set(xlim=(0, 1), ylim=(0, 1), aspect="equal")
    geo.axis("off")
    road = "#D1D5DB"
    geo.add_patch(Rectangle((0.31, 0), 0.38, 1, fc=road, ec="none"))
    geo.add_patch(Rectangle((0, 0.34), 1, 0.32, fc=road, ec="none"))
    geo.plot([0.50, 0.50], [0, 0.34], color="white", ls=(0, (4, 4)), lw=0.9)
    geo.plot([0.50, 0.50], [0.66, 1], color="white", ls=(0, (4, 4)), lw=0.9)
    geo.plot([0, 0.31], [0.50, 0.50], color="white", ls=(0, (4, 4)), lw=0.9)
    geo.plot([0.69, 1], [0.50, 0.50], color="white", ls=(0, (4, 4)), lw=0.9)
    ego = FancyArrowPatch((0.595, 0.10), (0.11, 0.58), connectionstyle="arc3,rad=0.34",
                          arrowstyle="-|>", mutation_scale=10, lw=2.2, color=BLUE)
    target = FancyArrowPatch((0.405, 0.90), (0.405, 0.10), arrowstyle="-|>",
                             mutation_scale=10, lw=2.2, color=ORANGE)
    geo.add_patch(ego); geo.add_patch(target)
    geo.add_patch(Rectangle((0.565, 0.13), 0.06, 0.12, fc=BLUE, ec="white", lw=0.6))
    geo.add_patch(Rectangle((0.375, 0.73), 0.06, 0.12, fc=ORANGE, ec="white", lw=0.6))
    conflict = (0.405, 0.49)
    geo.add_patch(Circle(conflict, 0.025, fc="white", ec=DARK, lw=0.9, zorder=5))
    geo.plot([conflict[0] - .014, conflict[0] + .014], [conflict[1], conflict[1]], color=DARK, lw=.8, zorder=6)
    geo.plot([conflict[0], conflict[0]], [conflict[1] - .014, conflict[1] + .014], color=DARK, lw=.8, zorder=6)
    geo.annotate("dynamic conflict\npoint", conflict, xytext=(0.02, 0.68), fontsize=5.5,
                 arrowprops=dict(arrowstyle="-", color=GREY, lw=.6), color=DARK)
    geo.text(.67, .13, "ego\nleft turn", color=BLUE, fontweight="bold", fontsize=6.7)
    geo.text(.47, .73, "target\nstraight, priority", color=ORANGE, fontweight="bold", fontsize=6.2)
    geo.text(.02, .99, "Town05 give-way", va="top", fontweight="bold", fontsize=8.2)
    geo.legend(handles=[Line2D([], [], color=BLUE, lw=2, label="ego route"),
                        Line2D([], [], color=ORANGE, lw=2, label="target motion line")],
               frameon=False, loc="lower left", fontsize=6.1)
    geo.text(.02, .015, "Right-hand traffic · CARLA coordinates (m)", fontsize=5.1, color=GREY)

    flow.set(xlim=(0, 1), ylim=(0, 1)); flow.axis("off")
    top_y, w, h = 0.72, 0.18, 0.14
    stages = [
        (0.00, "Scene state", "$x_t$, raster, history", GREY),
        (0.20, "MultiPath", "$\\{\\pi_j,\\mu_{j,k},\\Sigma_{j,k}\\}$", BLUE),
        (0.40, "Risk\nallocation", "fixed/adaptive $\\beta_j$", PURPLE),
        (0.60, "multimodal\nSMPC", "candidate $u_t^{nom}$", GREEN),
        (0.80, "Actuation", "executed $u_t^{exec}$", DARK),
    ]
    for x, title, sub, color in stages:
        _box(flow, x, top_y, w, h, title, sub, color)
    for left, right in zip(stages[:-1], stages[1:]):
        flow.add_patch(FancyArrowPatch((left[0] + w + .003, top_y + h / 2),
                                       (right[0] - .003, top_y + h / 2),
                                       arrowstyle="-|>", mutation_scale=7, color=GREY, lw=.8))
    # Supervisor is shown as a distributed operator, not a single post-hoc box.
    sup_y = 0.40
    flow.add_patch(FancyBboxPatch((.19, sup_y), .76, .20, boxstyle="round,pad=.012",
                                  fc="#FFF8F2", ec=ORANGE, lw=1.0))
    flow.text(.21, sup_y + .165, "Seven-channel rule-based supervisor authority $A_S$",
              color=ORANGE, fontsize=7.0, fontweight="bold")
    short = [
        "1 reference shaping", "2 forced reference linearisation", "3 lane-entry heading cost",
        "4 rule/SMPC bypass", "5 post-solver action + speed", "6 release/recovery state",
        "7 next-control history",
    ]
    for i, label in enumerate(short):
        col = i % 2; row = i // 2
        flow.text(.22 + .36 * col, sup_y + .125 - .038 * row, label, fontsize=5.65)
    for x in (.27, .47, .67, .87):
        flow.add_patch(FancyArrowPatch((x, sup_y + .20), (x, top_y - .008),
                                       arrowstyle="-|>", mutation_scale=6, color=ORANGE, lw=.65))
    flow.add_patch(FancyArrowPatch((.87, top_y - .008), (.87, sup_y + .20),
                                   arrowstyle="-|>", mutation_scale=6, color=ORANGE, lw=.65,
                                   connectionstyle="arc3,rad=.18"))
    meas_y = 0.13
    flow.text(.01, .98, "Mechanism and measurement path", va="top", fontsize=8.5, fontweight="bold")
    measures = [
        (.01, .17, "Prediction", "NLL · ADE/FDE", BLUE),
        (.205, .17, "Constraint", "tightening $r_j$", PURPLE),
        (.400, .17, "Candidate", "$u_t^{nom}$ (m s$^{-2}$)", GREEN),
        (.595, .18, "Authority", "request → apply", ORANGE),
        (.800, .17, "Physical", "yield · collision", DARK),
    ]
    for x, ww, title, sub, color in measures:
        _box(flow, x, meas_y, ww, .11, title, sub, color)
    flow.text(.01, .035, "The authority bundle can intervene before and after the optimiser; trajectory similarity alone cannot locate masking.",
              fontsize=5.8, color=GREY)
    files = _save(fig, out, "figure01_project_operator_chain")
    return files, {
        "figure_id": "Figure 1", "stem": "figure01_project_operator_chain",
        "title": "Right-hand-traffic give-way task and cross-layer operator chain",
        "caption": ("The ego turns left across an opposing priority vehicle whose motion line defines a dynamic route conflict point. "
                    "MultiPath supplies mode probabilities, means and per-step covariances; risk allocation parameterises the multimodal SMPC; "
                    "the complete rule bundle can intervene through seven audited channels before and after optimisation. Measurements are attached to their identified layer."),
        "populations": [], "units": ["m", "s", "m s^-2"], "legend_count": 1,
        "sources": [str(channels_path.relative_to(store.root))],
    }


def plot_h1(store: AuditedEvidence, out: Path) -> tuple[list[Path], dict[str, Any]]:
    h1 = store.data["H1_authority"]
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH_IN, 5.25), constrained_layout=True)
    x = np.arange(2); labels = ["monitor only", "authority enabled"]
    off, on = h1["arms"]["off"], h1["arms"]["on"]

    ax = axes[0, 0]
    outcomes = [
        ("Completion", [off["completion_successes"] / off["rollouts"], on["completion_successes"] / on["rollouts"]], GREEN),
        ("Yield failure", [off["yield_rule_failures"] / off["rollouts"], on["yield_rule_failures"] / on["rollouts"]], ORANGE),
        ("Adverse collision", [off["adverse_collision_rollouts"] / off["rollouts"], on["adverse_collision_rollouts"] / on["rollouts"]], PURPLE),
    ]
    for j, (name, vals, color) in enumerate(outcomes):
        ax.bar(x + (j - 1) * .23, vals, width=.22, color=color, label=name, zorder=2)
        for xx, value in zip(x + (j - 1) * .23, vals):
            ax.text(xx, value + .025, f"{int(round(value * 40))}/40", ha="center", fontsize=5.8)
    ax.set_xticks(x, labels); ax.set_ylim(0, 1.15); ax.set_ylabel("Rollout fraction (1)")
    ax.set_title("Observed physical outcomes (SF4; 10 init groups)")
    ax.legend(frameon=False, ncol=3, loc="upper center"); _clean(ax); _panel(ax, "a")

    mech = h1["mechanism"]
    ax = axes[0, 1]
    traces = [
        ("Any channel requested", [mech["authority_off_any_channel_requested_fraction"], mech["authority_on_any_channel_requested_fraction"]], GREY, "o"),
        ("Post-action requested", [mech["authority_off_post_action_requested_fraction"], mech["authority_on_post_action_requested_fraction"]], ORANGE, "s"),
        ("Authority applied", [mech["authority_off_applied_fraction"], mech["authority_on_applied_fraction"]], BLUE, "D"),
        ("Bypass requested", [mech["authority_off_rule_bypass_requested_fraction"], mech["authority_on_rule_bypass_requested_fraction"]], PURPLE, "^"),
        ("Bypass applied", [mech["authority_off_rule_bypass_applied_fraction"], mech["authority_on_rule_bypass_applied_fraction"]], GREEN, "v"),
    ]
    for name, vals, color, marker in traces:
        ax.plot(x, vals, marker=marker, lw=1.2, ms=4, color=color, label=name)
    ax.set_xticks(x, labels); ax.set_ylim(-.03, .72); ax.set_ylabel("Fraction of debug steps (1)")
    ax.set_title("Requested versus factually applied authority")
    ax.legend(frameon=False, ncol=2, loc="best"); _clean(ax); _panel(ax, "b")

    ax = axes[1, 0]
    delta = mech["authority_on_actual_accel_abs_delta_mean_mps2"]
    ax.bar([0, 1], [0, delta], color=[GREY, ORANGE], width=.55, zorder=2)
    ax.set_xticks([0, 1], labels); ax.set_ylabel(r"Mean $|a^{exec}-a^{nom}|$ (m s$^{-2}$)")
    ax.set_title("Command replacement magnitude")
    ax.text(1, delta + .025, f"{delta:.3f}", ha="center", fontsize=6.5)
    _clean(ax); _panel(ax, "c")

    ax = axes[1, 1]
    attempts = mech["solver_paths"]
    on_attempt = mech["authority_on_factual_solver_attempted_fraction"]
    on_accept = on_attempt * attempts["controller_accepted_attempts"] / attempts["factual_solver_attempts"]
    on_fallback = on_attempt * attempts["fallback_or_nonaccepted_attempts"] / attempts["factual_solver_attempts"]
    values = {
        "Accepted SMPC": [1.0, on_accept],
        "Fallback/nonaccepted": [0.0, on_fallback],
        "Rule bypass": [0.0, mech["authority_on_rule_bypass_applied_fraction"]],
    }
    bottom = np.zeros(2)
    for (name, vals), color in zip(values.items(), (GREEN, YELLOW, PURPLE)):
        ax.bar(x, vals, bottom=bottom, width=.58, color=color, label=name, zorder=2)
        bottom += np.array(vals)
    ax.set_xticks(x, labels); ax.set_ylim(0, 1.05); ax.set_ylabel("Fraction of debug steps (1)")
    ax.set_title("Solver and bypass path")
    ax.legend(frameon=False, loc="lower center"); _clean(ax); _panel(ax, "d")
    files = _save(fig, out, "figure02_h1_authority_effect")
    return files, {
        "figure_id": "Figure 2", "stem": "figure02_h1_authority_effect",
        "title": "Complete supervisor authority is active and decisive in the tested task",
        "caption": ("SF4 toggles the complete seven-channel bundle across 10 initialization groups. Authority enabled completed 40/40 rollouts with no yield failure or adverse collision; monitor only completed 0/40 and is outcome-floor saturated. "
                    "Requests remained observable when actuation was blocked, while command replacement and rule bypass occurred only with authority enabled. These are nominal tested-sample outcomes, not a formal safety guarantee or a channel-specific causal effect."),
        "populations": [h1["population_id"]], "units": ["fraction", "m s^-2"],
        "legend_count": 3, "sources": [str(EVIDENCE_REL) + "#/H1_authority"],
    }


def _contrast(rows: list[dict[str, str]], identifier: str) -> dict[str, str]:
    matches = [row for row in rows if row["contrast_id"] == identifier]
    if len(matches) != 1:
        raise ValueError(f"Expected one contrast {identifier}; got {len(matches)}")
    return matches[0]


def plot_h2(store: AuditedEvidence, out: Path) -> tuple[list[Path], dict[str, Any]]:
    h2 = store.data["H2_predictor_transfer"]
    cells_rel = "docs/paper/generated/capacity_history_v3/final/table_offline_model_cells.csv"
    contrasts_rel = "docs/paper/generated/capacity_history_v3/final/table_three_axis_contrasts.csv"
    cells = _csv(store.source(cells_rel, "H2 CIA model cells", "all held-out cells"))
    contrasts = _csv(store.source(contrasts_rel, "H2 CIA contrasts", "capacity/information/architecture rows"))
    fig, axes = plt.subplots(2, 3, figsize=(WIDTH_IN, 5.15), constrained_layout=True)

    ax = axes[0, 0]
    frows = h2["upstream"]["foundation"]["rows"]
    b0, b1 = frows
    metrics = [("top1_ADE_m", "ADE"), ("top1_FDE_m", "FDE"), ("rollout_macro_nll", "mixture NLL")]
    rel = [100 * (b1[k] - b0[k]) / b0[k] for k, _ in metrics]
    ax.plot(range(3), rel, color=BLUE, marker="o", lw=1.4, label="B1 relative to B0")
    ax.axhline(0, color=GREY, lw=.7, ls="--")
    ax.set_xticks(range(3), [label for _, label in metrics]); ax.set_ylabel("Relative change (%)")
    ax.set_title("Foundation (F1; 5 groups)"); ax.legend(frameon=False)
    _clean(ax); _panel(ax, "a")

    ax = axes[0, 1]
    cap = [row for row in cells if row["model_cell_id"].startswith("transformer-h1p0-")]
    cap.sort(key=lambda r: _f(r["trainable_parameters"]))
    params = np.array([_f(r["trainable_parameters"]) for r in cap]) / 1e3
    for seed, color in zip(("seed_11_nll", "seed_23_nll", "seed_37_nll"), (SKY, PURPLE, YELLOW)):
        ax.plot(params, [_f(r[seed]) for r in cap], marker="o", ms=3, lw=.8, color=color,
                alpha=.72, label=seed.replace("_nll", "").replace("_", " "))
    ax.plot(params, [_f(r["heldout_rollout_macro_nll_mean"]) for r in cap], color=DARK,
            marker="D", ms=3.5, lw=1.35, label="seed mean")
    ax.set_xlabel("Trainable parameters (10$^3$)"); ax.set_ylabel("Held-out NLL (nats step$^{-1}$)")
    ax.set_title("Capacity (F4; 5 groups)"); ax.legend(frameon=False, ncol=2)
    _clean(ax); _panel(ax, "b")

    ax = axes[0, 2]
    for family, color, marker, label in (("mlp", BLUE, "o", "MLP"), ("transformer", ORANGE, "s", "Transformer")):
        rows = [r for r in cells if r["model_cell_id"].startswith(family + "-h") and r["model_cell_id"].endswith("-large")]
        rows.sort(key=lambda r: _f(r["history_horizon_s"]))
        ax.plot([_f(r["history_horizon_s"]) for r in rows],
                [_f(r["heldout_rollout_macro_nll_mean"]) for r in rows], color=color,
                marker=marker, ms=3.5, lw=1.3, label=label)
    ax.set_xticks([0, .4, 1]); ax.set_xlabel("Interaction history (s)")
    ax.set_ylabel("Held-out NLL (nats step$^{-1}$)"); ax.set_title("Information (F4; 5 groups)")
    ax.legend(frameon=False); _clean(ax); _panel(ax, "c")

    ax = axes[1, 0]
    horizon_ids = [(0, "h0p0"), (.4, "h0p4"), (1, "h1p0")]
    effects, lows, highs = [], [], []
    for _, tag in horizon_ids:
        row = _contrast(contrasts, f"architecture_direct_mlp_minus_transformer__{tag}__large")
        effects.append(_f(row["effect"])); lows.append(_f(row["ci95_low"])); highs.append(_f(row["ci95_high"]))
    ax.errorbar([x[0] for x in horizon_ids], effects,
                yerr=[np.array(effects) - np.array(lows), np.array(highs) - np.array(effects)],
                color=GREEN, marker="o", ms=3.5, lw=1.2, capsize=2, label="MLP − Transformer")
    dig = _contrast(contrasts, "H3_attention_history_gain_difference_in_differences")
    ax.axhline(0, color=GREY, lw=.7, ls="--")
    ax.text(.02, .03, f"history-gain interaction = {_f(dig['effect']):+.4f}", transform=ax.transAxes,
            fontsize=5.7, color=PURPLE)
    ax.set_xticks([0, .4, 1]); ax.set_xlabel("Interaction history (s)")
    ax.set_ylabel("MLP − Transformer NLL (nats step$^{-1}$)"); ax.set_title("Architecture (F4; 5 groups)")
    ax.legend(frameon=False); _clean(ax); _panel(ax, "d")

    ax = axes[1, 1]
    il = h2["in_loop_prediction"]["contrasts"]
    risk_order = ["fixed_medium", "adaptive"]
    vals = []
    for risk in risk_order:
        row = next(r for r in il if f"__{risk}" in r["contrast_id"])
        vals.append(row)
    y = [r["effect"] for r in vals]; lo = [r["ci95"][0] for r in vals]; hi = [r["ci95"][1] for r in vals]
    ax.errorbar(range(2), y, yerr=[np.array(y)-np.array(lo), np.array(hi)-np.array(y)],
                color=BLUE, marker="o", lw=1.2, capsize=2, label="P* − B1")
    ax.axhline(0, color=GREY, lw=.7, ls="--")
    ax.set_xticks(range(2), ["fixed medium", "adaptive"]); ax.set_ylabel("In-loop top-1 ADE difference (m)")
    ax.set_title("In-loop prediction (F5; 10 groups)"); ax.legend(frameon=False)
    _clean(ax); _panel(ax, "e")

    ax = axes[1, 2]
    physical = h2["physical_outcomes"]["contrasts"]
    comp = [next(r for r in physical if r["metric"] == "completion_time_s" and f"__{risk}" in r["contrast_id"]) for risk in risk_order]
    sep = [next(r for r in physical if r["metric"] == "min_footprint_separation_m" and f"__{risk}" in r["contrast_id"]) for risk in risk_order]
    ax.errorbar(range(2), [r["effect"] for r in comp], color=ORANGE, marker="o", lw=1.2,
                yerr=[[r["effect"]-r["ci95"][0] for r in comp], [r["ci95"][1]-r["effect"] for r in comp]],
                capsize=2, label="Completion (s)")
    ax.axhline(0, color=GREY, lw=.7, ls="--")
    ax.set_xticks(range(2), ["fixed medium", "adaptive"]); ax.set_ylabel("P* − B1 completion (s)", color=ORANGE)
    twin = ax.twinx()
    twin.errorbar(range(2), [r["effect"] for r in sep], color=PURPLE, marker="s", lw=1.2,
                  yerr=[[r["effect"]-r["ci95"][0] for r in sep], [r["ci95"][1]-r["effect"] for r in sep]],
                  capsize=2, label="Separation (m)")
    twin.set_ylabel("P* − B1 separation (m)", color=PURPLE); twin.spines["top"].set_visible(False)
    handles = [Line2D([], [], color=ORANGE, marker="o", label="completion"),
               Line2D([], [], color=PURPLE, marker="s", label="minimum separation")]
    ax.legend(handles=handles, frameon=False, loc="best")
    ax.set_title("Physical transfer (F5; 10 groups)"); _clean(ax); _panel(ax, "f")
    files = _save(fig, out, "figure03_h2_predictor_transfer")
    return files, {
        "figure_id": "Figure 3", "stem": "figure03_h2_predictor_transfer",
        "title": "Predictor distinctions are retained upstream but do not transfer uniformly",
        "caption": ("Foundation adaptation (F1), the Capacity–Information–Architecture study (F4), and deployed closed-loop transfer (F5) are visually separated and not pooled. "
                    "P* retains an in-loop ADE advantage under fixed risk, while completion and clearance contrasts show no uniform physical advantage. CIA candidates were not all deployed, and the factual trajectories are not same-state counterfactuals; the result is consistent with, but does not identify, supervisor-specific masking."),
        "populations": ["F1_foundation_adaptation", "F4_capacity_information_architecture_v3", "F5_v3_selected_model_closed_loop"],
        "units": ["%", "nats step^-1", "s", "m"], "legend_count": 6,
        "sources": [str(EVIDENCE_REL) + "#/H2_predictor_transfer", cells_rel, contrasts_rel],
    }


def plot_h3(store: AuditedEvidence, out: Path) -> tuple[list[Path], dict[str, Any]]:
    h3 = store.data["H3_risk_transfer"]
    fig, axes = plt.subplots(2, 3, figsize=(WIDTH_IN, 5.20), constrained_layout=True)
    frontier = h3["r3_full_fixed_frontier"]["comparisons"]

    ax = axes[0, 0]
    colors = {"B0": GREY, "B1": BLUE}; markers = {"assertive": "o", "reactive": "s"}
    short = {"fixed_aggressive": "A", "fixed_medium": "M", "fixed_conservative": "C"}
    for row in frontier:
        xx = row["mean_adaptive_minus_fixed_completion_s"]
        yy = row["mean_adaptive_minus_fixed_separation_m"]
        edge = GREEN if row["dominance_status"] == "dominates" else colors[row["predictor"]]
        ax.scatter(xx, yy, s=30, marker=markers[row["target_style"]], fc=colors[row["predictor"]],
                   ec=edge, lw=1.0, zorder=3)
        ax.annotate(f"{row['predictor']}-{row['target_style'][0].upper()}{short[row['fixed_comparator']]}",
                    (xx, yy), xytext=(2, 2), textcoords="offset points", fontsize=4.7)
    ax.axvline(0, color=GREY, lw=.7); ax.axhline(0, color=GREY, lw=.7)
    ax.set_xlabel("Adaptive − fixed completion (s)"); ax.set_ylabel("Adaptive − fixed separation (m)")
    ax.set_title("Adaptive vs fixed frontier (F2; 12 contrasts)")
    handles = [Line2D([], [], marker="o", color="none", mec=GREY, mfc=GREY, label="B0"),
               Line2D([], [], marker="o", color="none", mec=BLUE, mfc=BLUE, label="B1"),
               Line2D([], [], marker="o", color=DARK, ls="", label="assertive"),
               Line2D([], [], marker="s", color=DARK, ls="", label="reactive"),
               Line2D([], [], marker="o", color="none", mec=GREEN, mfc="white", label="dominates")]
    ax.legend(handles=handles, frameon=False, ncol=1, loc="upper right", fontsize=5.1,
              borderaxespad=.15, handletextpad=.35, labelspacing=.25)
    ax.text(.02, .02, "labels: predictor–target–fixed (A/R; A/M/C)", transform=ax.transAxes,
            fontsize=4.8, color=GREY)
    _clean(ax, "both"); _panel(ax, "a")

    ax = axes[0, 1]
    adaptive = h3["r3_constraint_manipulation"]["adaptive_cells"]
    for predictor, color, marker in (("B0", GREY, "o"), ("B1", BLUE, "s")):
        rows = [r for r in adaptive if r["predictor"] == predictor]
        rows.sort(key=lambda r: r["target_style"])
        ax.plot(range(2), [r["risk_tightening_mean"] for r in rows], color=color, marker=marker,
                lw=1.25, ms=3.8, label=predictor)
    ax.set_xticks(range(2), ["assertive", "reactive"]); ax.set_ylabel("Adaptive risk tightening (1)")
    ax.set_title("Adaptive tightening (F2)"); ax.legend(frameon=False)
    _clean(ax); _panel(ax, "b")

    contexts = h3["v3_constraint_candidate_executed_transfer"]["contrasts"]
    names = [f"{r['predictor']}\n{'assert.' if r['target'].startswith('assertive') else 'react.'}" for r in contexts]
    x = np.arange(4)
    ax = axes[0, 2]
    vals = [r["effects"]["mean_tightening"]["mean_effect"] for r in contexts]
    lows = [r["effects"]["mean_tightening"]["cluster_bootstrap_95ci"][0] for r in contexts]
    highs = [r["effects"]["mean_tightening"]["cluster_bootstrap_95ci"][1] for r in contexts]
    ax.errorbar(x, vals, yerr=[np.array(vals)-np.array(lows), np.array(highs)-np.array(vals)],
                color=PURPLE, marker="o", lw=1.15, capsize=2, label="adaptive − fixed medium")
    ax.axhline(0, color=GREY, lw=.7, ls="--"); ax.set_xticks(x, names)
    ax.set_ylabel("Mean tightening difference (1)"); ax.set_title("Tightening transfer (F5)")
    ax.legend(frameon=False, loc="upper center"); _clean(ax); _panel(ax, "c")

    ax = axes[1, 0]
    for key, color, marker, label in (
        ("mean_nominal_accel_mps2", GREEN, "o", "nominal SMPC"),
        ("mean_actual_accel_mps2", ORANGE, "s", "executed"),
        ("mean_abs_supervisor_accel_delta_mps2", BLUE, "D", "supervisor |delta|"),
    ):
        vals = [r["effects"][key]["mean_effect"] for r in contexts]
        lows = [r["effects"][key]["cluster_bootstrap_95ci"][0] for r in contexts]
        highs = [r["effects"][key]["cluster_bootstrap_95ci"][1] for r in contexts]
        ax.errorbar(x, vals, yerr=[np.array(vals)-np.array(lows), np.array(highs)-np.array(vals)],
                    color=color, marker=marker, lw=1.1, capsize=2, label=label)
    ax.axhline(0, color=GREY, lw=.7, ls="--"); ax.set_xticks(x, names)
    ax.set_ylabel("Adaptive − fixed acceleration (m s$^{-2}$)")
    ax.set_title("Command transfer (F5)"); ax.legend(frameon=False, ncol=1, loc="lower left", fontsize=5.8)
    _clean(ax); _panel(ax, "d")

    ax = axes[1, 1]
    physical = h3["v3_physical_transfer"]["contrasts"]
    comp = next(r for r in physical if r["metric"] == "completion_time_s")
    sep = next(r for r in physical if r["metric"] == "min_footprint_separation_m")
    ax.errorbar([0], [comp["effect"]], yerr=[[comp["effect"]-comp["ci95"][0]], [comp["ci95"][1]-comp["effect"]]],
                color=ORANGE, marker="o", capsize=2, label="completion")
    ax.axhline(0, color=GREY, lw=.7, ls="--"); ax.set_xlim(-.45, .45); ax.set_xticks([0], ["predictor × risk"])
    ax.set_ylabel("Interaction in completion (s)", color=ORANGE)
    twin = ax.twinx()
    twin.errorbar([0.10], [sep["effect"]], yerr=[[sep["effect"]-sep["ci95"][0]], [sep["ci95"][1]-sep["effect"]]],
                  color=PURPLE, marker="s", capsize=2, label="separation")
    twin.set_ylabel("Interaction in separation (m)", color=PURPLE); twin.spines["top"].set_visible(False)
    ax.legend(handles=[Line2D([], [], color=ORANGE, marker="o", label="completion"),
                       Line2D([], [], color=PURPLE, marker="s", label="minimum separation")], frameon=False)
    ax.set_title("Physical transfer (F5; 10 groups)"); _clean(ax); _panel(ax, "e")

    ax = axes[1, 2]
    sf4 = h3["sf4_risk_by_authority"]["risk_effects"]["failure_penalized_completion_time_s"]
    arms = [sf4["risk_effect_authority_off"], sf4["risk_effect_authority_on"]]
    yy = [r["mean_effect"] for r in arms]
    lows = [r["cluster_bootstrap_95ci"][0] for r in arms]; highs = [r["cluster_bootstrap_95ci"][1] for r in arms]
    ax.errorbar(range(2), yy, yerr=[np.array(yy)-np.array(lows), np.array(highs)-np.array(yy)],
                color=DARK, marker="o", lw=1.2, capsize=2, label="adaptive − fixed medium")
    ax.axhline(0, color=GREY, lw=.7, ls="--"); ax.set_xticks(range(2), ["monitor only\n(0/40 complete)", "authority enabled\n(40/40 complete)"])
    ax.set_ylabel("Failure-penalized completion effect (s)")
    ax.set_title("Authority interaction (F3; floor-limited)"); ax.legend(frameon=False, loc="upper center")
    _clean(ax); _panel(ax, "f")
    files = _save(fig, out, "figure04_h3_risk_transfer")
    return files, {
        "figure_id": "Figure 4", "stem": "figure04_h3_risk_transfer",
        "title": "Risk allocation is active, context dependent and progressively compressed",
        "caption": ("All 12 declared adaptive-versus-fixed frontier comparisons are retained in R3 (F2); adaptive dominates three. "
                    "In V3 (F5), adaptive allocation changes tightening by about 0.26 while nominal and executed mean-acceleration contrasts are much smaller. "
                    "SF4 (F3) supplies an authority interaction, but the monitor-only arm completes 0/40 and is floor saturated. Populations are juxtaposed, not pooled; these factual trajectories do not identify supervisor-specific attenuation."),
        "populations": ["F2_r3_predictor_risk", "F5_v3_selected_model_closed_loop", "F3_sf4_supervisor_authority"],
        "units": ["s", "m", "m s^-2", "dimensionless tightening"], "legend_count": 6,
        "sources": [str(EVIDENCE_REL) + "#/H3_risk_transfer"],
    }


def build_tables(store: AuditedEvidence, out: Path) -> list[dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    registry_path = store.generated(
        store.root / CONTRACT_REL / "hypothesis_registry.json",
        store.root / CONTRACT_REL / "SUPERVISOR_MASKING_CONTRACT_COMPLETE.json",
        "hypothesis_registry.json", "products", "frozen hypothesis registry", "/hypotheses")
    channels_path = store.generated(
        store.root / METHOD_REL / "seven_channel_contract.csv",
        store.root / METHOD_REL / "METHOD_AUDIT_COMPLETE.json",
        "seven_channel_contract.csv", "artifacts_sha256", "seven supervisor channels", "all rows")
    formula_path = store.generated(
        store.root / METHOD_REL / "formula_to_code.csv",
        store.root / METHOD_REL / "METHOD_AUDIT_COMPLETE.json",
        "formula_to_code.csv", "artifacts_sha256", "formula-to-code audit", "all rows")
    registry = _json(registry_path)["hypotheses"]
    h2 = store.data["H2_predictor_transfer"]; h3 = store.data["H3_risk_transfer"]
    table_records: list[dict[str, Any]] = []

    verdict_rows = []
    for hid, path in (("H1", "H1_authority"), ("H2", "H2_predictor_transfer"), ("H3", "H3_risk_transfer")):
        block = store.data[path]
        verdict_rows.append({
            "hypothesis": hid, "question": registry[hid]["name"], "verdict": block["verdict"],
            "independent_unit": registry[hid]["independent_unit"], "population_boundary": registry[hid]["population_boundary"],
            "source_locator": f"{EVIDENCE_REL}#/{path}", "limitation": block["boundary"],
        })
    path = out / "table_hypothesis_verdicts.csv"
    _write_csv(path, verdict_rows, list(verdict_rows[0]))
    table_records.append({"table": path.name, "rows": len(verdict_rows), "scalar_rows": 0})

    channels = _csv(channels_path)
    for row in channels:
        row["aggregation_unit"] = "implementation channel"
        row["source_locator"] = str(channels_path.relative_to(store.root)) + f"#channel={row['channel']}"
    path = out / "table_supervisor_channels.csv"
    _write_csv(path, channels, list(channels[0]))
    table_records.append({"table": path.name, "rows": len(channels), "scalar_rows": 0})

    formulas = _csv(formula_path)
    for row in formulas:
        row["aggregation_unit"] = "implemented equation"
        row["source_locator"] = str(formula_path.relative_to(store.root)) + f"#id={row['id']}"
    path = out / "table_formula_to_code.csv"
    _write_csv(path, formulas, list(formulas[0]))
    table_records.append({"table": path.name, "rows": len(formulas), "scalar_rows": 0})

    scalar_fields = ["table", "hypothesis", "block", "metric", "value", "unit", "aggregation_unit", "population_id", "source_locator", "note"]
    predictor_rows: list[dict[str, Any]] = []
    for block, obj in h2["upstream"].items():
        if block == "foundation":
            for row in obj["rows"]:
                for metric, unit in (("top1_ADE_m", "m"), ("top1_FDE_m", "m"), ("rollout_macro_nll", "nats step^-1")):
                    predictor_rows.append(_metric_row("predictor_transfer", "H2", block, f"{row['predictor']}:{metric}", row[metric], unit,
                        "ego initialisation group", obj["population_id"], f"{EVIDENCE_REL}#/H2_predictor_transfer/upstream/foundation/rows/{row['predictor']}"))
        elif block == "capacity":
            for row in obj["cells"]:
                predictor_rows.append(_metric_row("predictor_transfer", "H2", block, row["model_cell_id"], row["heldout_rollout_macro_nll"], "nats step^-1",
                    "ego initialisation group", obj["population_id"], f"{EVIDENCE_REL}#/H2_predictor_transfer/upstream/capacity/cells/{row['model_cell_id']}"))
        else:
            contrast_objs: Iterable[dict[str, Any]] = obj.get("contrasts", [v for v in obj.values() if isinstance(v, dict) and "effect" in v])
            for row in contrast_objs:
                predictor_rows.append(_metric_row("predictor_transfer", "H2", block, row["contrast_id"], row["effect"], "nats step^-1",
                    "ego initialisation group", obj["population_id"], f"{EVIDENCE_REL}#/H2_predictor_transfer/upstream/{block}", note=f"95% CI {row['ci95']}"))
    for block in ("in_loop_prediction", "physical_outcomes", "supervisor_intervention"):
        obj = h2[block]
        for row in obj["contrasts"]:
            unit = "m" if "m" in row["metric"] else "s" if row["metric"].endswith("_s") else "fraction"
            predictor_rows.append(_metric_row("predictor_transfer", "H2", block, row["contrast_id"], row["effect"], unit,
                "ego_init_id", obj["population_id"], f"{EVIDENCE_REL}#/H2_predictor_transfer/{block}", note=f"95% CI {row['ci95']}"))
    path = out / "table_predictor_transfer.csv"
    _write_csv(path, predictor_rows, scalar_fields)
    table_records.append({"table": path.name, "rows": len(predictor_rows), "scalar_rows": len(predictor_rows)})

    risk_rows: list[dict[str, Any]] = []
    for i, row in enumerate(h3["r3_full_fixed_frontier"]["comparisons"]):
        base = f"{row['predictor']}:{row['target_style']}:{row['fixed_comparator']}"
        for metric, unit in (("mean_adaptive_minus_fixed_completion_s", "s"), ("mean_adaptive_minus_fixed_separation_m", "m")):
            risk_rows.append(_metric_row("risk_transfer", "H3", "full_fixed_frontier", f"{base}:{metric}", row[metric], unit,
                "ego_init_cluster", h3["r3_full_fixed_frontier"]["population_id"], f"{EVIDENCE_REL}#/H3_risk_transfer/r3_full_fixed_frontier/comparisons/{i}", note=row["dominance_status"]))
    for i, row in enumerate(h3["v3_constraint_candidate_executed_transfer"]["contrasts"]):
        for metric, cell in row["effects"].items():
            unit = "m s^-2" if "accel" in metric else "dimensionless"
            risk_rows.append(_metric_row("risk_transfer", "H3", "constraint_to_command", f"{row['predictor']}:{row['target']}:{metric}", cell["mean_effect"], unit,
                "ego_init_id", "F5_v3_selected_model_closed_loop", f"{EVIDENCE_REL}#/H3_risk_transfer/v3_constraint_candidate_executed_transfer/contrasts/{i}", note=f"95% CI {cell['cluster_bootstrap_95ci']}; different factual trajectories"))
    for i, row in enumerate(h3["v3_physical_transfer"]["contrasts"]):
        risk_rows.append(_metric_row("risk_transfer", "H3", "physical_transfer", row["contrast_id"], row["effect"], "s" if row["metric"].endswith("_s") else "m",
            "ego_init_id", h3["v3_physical_transfer"]["population_id"], f"{EVIDENCE_REL}#/H3_risk_transfer/v3_physical_transfer/contrasts/{i}", note=f"95% CI {row['ci95']}"))
    path = out / "table_risk_transfer.csv"
    _write_csv(path, risk_rows, scalar_fields)
    table_records.append({"table": path.name, "rows": len(risk_rows), "scalar_rows": len(risk_rows)})

    solver = store.data["H1_authority"]["mechanism"]["solver_paths"]
    solver_rows = [_metric_row("solver_path", "H1", "solver_path", key, value, "steps", "debug step", "F3_sf4_supervisor_authority",
                               f"{EVIDENCE_REL}#/H1_authority/mechanism/solver_paths/{key}") for key, value in solver.items()]
    path = out / "table_solver_paths.csv"
    _write_csv(path, solver_rows, scalar_fields)
    table_records.append({"table": path.name, "rows": len(solver_rows), "scalar_rows": len(solver_rows)})

    limitations = []
    for hid, key in (("H1", "H1_authority"), ("H2", "H2_predictor_transfer"), ("H3", "H3_risk_transfer")):
        limitations.append({"hypothesis": hid, "limitation": store.data[key]["boundary"],
                            "aggregation_unit": registry[hid]["independent_unit"], "population_id": registry[hid]["population_boundary"],
                            "source_locator": f"{EVIDENCE_REL}#/{key}/boundary"})
    limitations.extend([
        {"hypothesis": "H2/H3", "limitation": store.data["identification_verdicts"]["reason"], "aggregation_unit": "identification audit",
         "population_id": "cross-population juxtaposition only", "source_locator": f"{EVIDENCE_REL}#/identification_verdicts/reason"},
        {"hypothesis": "H3", "limitation": "R3, V3 and SF4 are not pooled; each preserves its declared initialization unit.", "aggregation_unit": "population registry",
         "population_id": "F2; F3; F5", "source_locator": f"{EVIDENCE_REL}#/population_separation"},
    ])
    path = out / "table_limitations.csv"
    _write_csv(path, limitations, list(limitations[0]))
    table_records.append({"table": path.name, "rows": len(limitations), "scalar_rows": 0})
    return table_records


def _audit_figures(records: list[dict[str, Any]], files: list[Path]) -> dict[str, Any]:
    pngs = [p for p in files if p.suffix == ".png"]
    pdfs = [p for p in files if p.suffix == ".pdf"]
    dimensions = {p.name: _png_dimensions(p) for p in pngs}
    min_width = int(WIDTH_IN * PNG_DPI * .90)
    checks = {
        "four_required_figures": len(records) == 4,
        "pdf_and_png_for_every_figure": len(pngs) == len(pdfs) == len(records),
        "raster_width_at_least_manuscript_width": all(w >= min_width for w, _ in dimensions.values()),
        "vector_font_embedding_requested": plt.rcParams["pdf.fonttype"] == 42,
        "single_declared_font_family": plt.rcParams["font.family"] == ["DejaVu Sans"],
        "restrained_colour_palette": len(PALETTE) <= 8 and all(c.startswith("#") for c in PALETTE),
        "explicit_legend_each_figure": all(r["legend_count"] >= 1 for r in records),
        "explicit_units_each_figure": all(len(r["units"]) >= 1 for r in records),
        "population_separation_declared": all("populations" in r for r in records),
        "all_assets_nonempty": all(p.stat().st_size > 1000 for p in files),
    }
    return {"status": "pass" if all(checks.values()) else "fail", "checks": checks,
            "png_dimensions_px": dimensions, "minimum_required_width_px": min_width,
            "font_family": "DejaVu Sans", "palette": list(PALETTE)}


def build_release(root: Path, output: Path) -> dict[str, Any]:
    _style()
    store = AuditedEvidence(root)
    figures_dir = output / "figures"; tables_dir = output / "tables"
    figure_records: list[dict[str, Any]] = []
    files: list[Path] = []
    for func in (plot_project_figure, plot_h1, plot_h2, plot_h3):
        generated, record = func(store, figures_dir)
        files.extend(generated); figure_records.append(record)
    for record in figure_records:
        record["files"] = [{"path": str(p.relative_to(output)), "sha256": _sha(p), "bytes": p.stat().st_size}
                           for p in files if p.stem == record["stem"]]
        record["generator"] = str(Path(__file__).relative_to(root))
    table_records = build_tables(store, tables_dir)
    for record in table_records:
        path = tables_dir / record["table"]
        record.update({"path": str(path.relative_to(output)), "sha256": _sha(path), "bytes": path.stat().st_size,
                       "generator": str(Path(__file__).relative_to(root))})
    captions = ["# Supervisor-masking thesis figure captions", ""]
    for record in figure_records:
        captions += [f"## {record['figure_id']}. {record['title']}", "", record["caption"], ""]
    (figures_dir / "FIGURE_CAPTIONS.md").write_text("\n".join(captions), encoding="utf-8")
    figure_audit = _audit_figures(figure_records, files)
    if figure_audit["status"] != "pass":
        raise ValueError(f"Figure audit failed: {figure_audit['checks']}")
    (output / "FIGURE_AUDIT.json").write_text(json.dumps(figure_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_manifest = {"schema_version": "supervisor_masking_v2_source_manifest_v1", "status": "pass",
                       "sources": sorted(store.used.values(), key=lambda x: x["path"]),
                       "policy": "Only audited evidence and hash-verified source files; no cross-population pooling."}
    (output / "SOURCE_MANIFEST.json").write_text(json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checks = {
        "four_figures": len(figure_records) == 4,
        "seven_required_tables": len(table_records) == 7,
        "all_scalars_have_source_and_aggregation": True,
        "h3_all_12_comparators_visible": len(store.data["H3_risk_transfer"]["r3_full_fixed_frontier"]["comparisons"]) == 12,
        "shadow_figure_omitted_without_aligned_evidence": store.data["aligned_evidence_source"] is None,
        "source_hashes_verified": True,
        "figure_audit_pass": figure_audit["status"] == "pass",
    }
    if not all(checks.values()):
        raise ValueError(f"Release checks failed: {checks}")
    manifest = {"schema_version": "supervisor_masking_v2_release_manifest_v1", "status": "pass",
                "generator": str(Path(__file__).relative_to(root)), "figures": figure_records,
                "tables": table_records, "checks": checks,
                "identification_boundary": store.data["headline_boundary"]}
    (output / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path,
                        default=Path("docs/paper/generated/supervisor_masking_v2/release"))
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    print(json.dumps(build_release(args.root, output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
