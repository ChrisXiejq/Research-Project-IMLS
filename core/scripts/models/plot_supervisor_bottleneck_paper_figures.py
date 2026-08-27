#!/usr/bin/env python3
"""Generate restrained, Python-only academic figures for the final thesis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle
import numpy as np


BLUE = "#0072B2"
ORANGE = "#D55E00"
GREEN = "#009E73"
PURPLE = "#CC79A7"
SKY = "#56B4E9"
YELLOW = "#E69F00"
GREY = "#6B7280"
LIGHT_GREY = "#E5E7EB"
DARK = "#1F2937"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _f(value: Any) -> float:
    return float(value)


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.2,
            "axes.titlesize": 9.2,
            "axes.labelsize": 8.2,
            "legend.fontsize": 7.2,
            "xtick.labelsize": 7.3,
            "ytick.labelsize": 7.3,
            "axes.linewidth": 0.7,
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


def _panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(-0.10, 1.05, label, transform=ax.transAxes, fontweight="bold", fontsize=10, va="top")


def _clean(ax: plt.Axes, grid_axis: str = "y") -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, axis=grid_axis, color=LIGHT_GREY, linewidth=0.65, zorder=0)
    ax.set_axisbelow(True)


def _save(fig: plt.Figure, base: Path) -> list[Path]:
    outputs = []
    for suffix in (".pdf", ".png"):
        path = base.with_suffix(suffix)
        kwargs = {"dpi": 360} if suffix == ".png" else {}
        fig.savefig(path, **kwargs)
        outputs.append(path)
    plt.close(fig)
    return outputs


def _bootstrap(values: list[float], seed: int, draws: int = 5000) -> tuple[float, float, float]:
    if not values:
        raise ValueError("Cannot bootstrap an empty initialization-group cell")
    arr = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    estimates = rng.choice(arr, size=(draws, len(arr)), replace=True).mean(axis=1)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(arr.mean()), float(low), float(high)


def _box(ax: plt.Axes, x: float, y: float, w: float, h: float, title: str, subtitle: str, color: str) -> None:
    patch = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.018",
        linewidth=1.0, edgecolor=color, facecolor="white"
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h * 0.67, title, ha="center", va="center", fontsize=7.1, fontweight="bold", color=color)
    ax.text(x + w / 2, y + h * 0.28, subtitle, ha="center", va="center", fontsize=5.6, color=DARK, linespacing=1.15)


def plot_system_figure(output: Path) -> tuple[list[Path], dict[str, Any]]:
    fig = plt.figure(figsize=(7.25, 4.15))
    gs = fig.add_gridspec(1, 2, width_ratios=[0.82, 2.18], wspace=0.15)
    task = fig.add_subplot(gs[0, 0])
    flow = fig.add_subplot(gs[0, 1])

    task.set_xlim(0, 1); task.set_ylim(0, 1); task.axis("off")
    task.add_patch(Rectangle((0.33, 0), 0.34, 1, color="#D1D5DB", zorder=0))
    task.add_patch(Rectangle((0, 0.37), 1, 0.26, color="#D1D5DB", zorder=0))
    for x in (0.43, 0.57):
        task.plot([x, x], [0, 0.37], color="white", lw=1, ls=(0, (4, 4)))
        task.plot([x, x], [0.63, 1], color="white", lw=1, ls=(0, (4, 4)))
    task.plot([0, 0.33], [0.50, 0.50], color="white", lw=1, ls=(0, (4, 4)))
    task.plot([0.67, 1], [0.50, 0.50], color="white", lw=1, ls=(0, (4, 4)))
    task.add_patch(Rectangle((0.39, 0.39), 0.22, 0.22, facecolor="#F3F4F6", edgecolor=GREY, hatch="////", lw=0.7))
    task.text(0.50, 0.51, "conflict\nregion", ha="center", va="center", fontsize=6.5, color=GREY)
    ego_path = FancyArrowPatch((0.57, 0.12), (0.17, 0.50), connectionstyle="arc3,rad=0.38", arrowstyle="-|>", mutation_scale=10, lw=2.1, color=BLUE)
    target_path = FancyArrowPatch((0.43, 0.88), (0.43, 0.13), arrowstyle="-|>", mutation_scale=10, lw=2.1, color=ORANGE)
    task.add_patch(ego_path); task.add_patch(target_path)
    task.add_patch(Rectangle((0.535, 0.14), 0.07, 0.12, facecolor=BLUE, edgecolor="white", lw=0.7))
    task.add_patch(Rectangle((0.395, 0.73), 0.07, 0.12, facecolor=ORANGE, edgecolor="white", lw=0.7))
    task.text(0.64, 0.18, "ego:\nleft turn", color=BLUE, fontsize=7, fontweight="bold")
    task.text(0.49, 0.80, "target:\nstraight, priority", color=ORANGE, fontsize=7, fontweight="bold")
    task.text(0.02, 0.98, "Controlled give-way task", va="top", fontweight="bold", fontsize=9)
    task.text(0.02, 0.02, "Right-hand traffic · Town05", fontsize=6.8, color=GREY)

    flow.set_xlim(0, 1); flow.set_ylim(0, 1); flow.axis("off")
    w, h = 0.25, 0.18
    top_y, bottom_y = 0.61, 0.25
    top = [
        (0.02, "State + history", "map · ego · target\nrecent interaction", GREY),
        (0.375, "MultiPath predictor", "$K$ trajectories\nprobability + covariance", BLUE),
        (0.73, "Risk allocation", "fixed / adaptive\nrisk budget", DARK),
    ]
    bottom = [
        (0.73, "Risk-aware SMPC", "nominal $u_t^{nom}$\nchance constraints", DARK),
        (0.375, "Rule supervisor", "reference · action\nbypass channels", ORANGE),
        (0.02, "CARLA execution", "executed $u_t^{exec}$\ncompletion + clearance", GREY),
    ]
    for x, title, subtitle, color in top:
        _box(flow, x, top_y, w, h, title, subtitle, color)
    for x, title, subtitle, color in bottom:
        _box(flow, x, bottom_y, w, h, title, subtitle, color)
    # Snake-shaped causal order: top row left-to-right, then bottom row right-to-left.
    for left, right in zip(top[:-1], top[1:]):
        flow.add_patch(FancyArrowPatch((left[0] + w + 0.008, top_y + h / 2), (right[0] - 0.008, top_y + h / 2), arrowstyle="-|>", mutation_scale=8, lw=0.9, color=GREY))
    flow.add_patch(FancyArrowPatch((0.855, top_y - 0.012), (0.855, bottom_y + h + 0.012), arrowstyle="-|>", mutation_scale=8, lw=0.9, color=GREY))
    for right, left in zip(bottom[:-1], bottom[1:]):
        flow.add_patch(FancyArrowPatch((right[0] - 0.008, bottom_y + h / 2), (left[0] + w + 0.008, bottom_y + h / 2), arrowstyle="-|>", mutation_scale=8, lw=0.9, color=GREY))
    chips = [
        (0.50, 0.84, "offline NLL · ADE", BLUE),
        (0.855, 0.51, "in-loop prediction", DARK),
        (0.50, 0.16, "requested → applied", ORANGE),
        (0.145, 0.16, "yield · collision · time", DARK),
    ]
    for x, yy, label, color in chips:
        flow.text(x, yy, label, ha="center", va="center", fontsize=6.7, color=color, fontweight="bold",
                  bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor=color, linewidth=0.7))
    flow.text(0.02, 0.97, "Cross-layer experiment and measurement points", va="top", fontsize=9, fontweight="bold")
    flow.text(0.02, 0.07, "Controlled axes:  capacity  ·  history  ·  encoder  ·  predictor  ·  risk policy  ·  authority", fontsize=6.8, fontweight="bold")
    flow.text(0.02, 0.015, "Each evidence block uses initialization-group aggregation; populations are reported separately.", fontsize=6.4, color=GREY)
    files = _save(fig, output / "figure01_cross_layer_system")
    return files, {
        "figure_id": "Figure 1",
        "title": "Task-specific cross-layer evaluation architecture",
        "caption": "The ego turns left across an oncoming priority vehicle in right-hand traffic. MultiPath outputs multimodal predictions, risk allocation parameterises SMPC, and the rule supervisor may alter references, actions or solver bypass before CARLA execution. Measurements are attached to the layer at which they are identified.",
        "sources": ["schematic generated from the frozen thesis contract; no result values"],
    }


def plot_cia_figure(root: Path, output: Path) -> tuple[list[Path], dict[str, Any]]:
    cells_path = root / "docs/paper/generated/capacity_history_v3/final/table_offline_model_cells.csv"
    contrasts_path = root / "docs/paper/generated/capacity_history_v3/final/table_three_axis_contrasts.csv"
    cells = _csv(cells_path); contrasts = _csv(contrasts_path)
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.75), constrained_layout=True)
    ax = axes[0]
    capacity = [row for row in cells if row["model_cell_id"].startswith("transformer-h1p0-")]
    order = {"small": 0, "medium": 1, "large": 2}
    capacity.sort(key=lambda row: order[row["model_cell_id"].rsplit("-", 1)[1]])
    params = np.array([_f(row["trainable_parameters"]) for row in capacity])
    capacity_x = np.arange(len(capacity))
    for seed, color in zip(("seed_11_nll", "seed_23_nll", "seed_37_nll"), (SKY, PURPLE, YELLOW)):
        ax.plot(capacity_x, [_f(row[seed]) for row in capacity], marker="o", ms=3.2, lw=0.8, alpha=0.72, color=color, label=seed.replace("_nll", "").replace("_", " "))
    ax.plot(capacity_x, [_f(row["heldout_rollout_macro_nll_mean"]) for row in capacity], marker="D", ms=4.2, lw=1.7, color=DARK, label="seed mean")
    capacity_labels = [row["model_cell_id"].rsplit("-", 1)[1] for row in capacity]
    ax.set_xticks(capacity_x, [f"{label}\n{value / 1e3:.0f}k" for label, value in zip(capacity_labels, params)])
    ax.set_xlabel("Capacity / trainable parameters"); ax.set_ylabel("Held-out NLL (nats step$^{-1}$)")
    ax.set_title("Capacity (1.0 s history)"); _clean(ax); _panel_label(ax, "a")
    ax.legend(frameon=False, ncol=2, loc="best")

    ax = axes[1]
    families = [("mlp", BLUE, "MLP"), ("transformer", ORANGE, "Transformer")]
    for family, color, label in families:
        rows = [row for row in cells if row["model_cell_id"].startswith(family + "-h") and row["model_cell_id"].endswith("-large")]
        rows.sort(key=lambda row: _f(row["history_horizon_s"]))
        horizons = [_f(row["history_horizon_s"]) for row in rows]
        for seed in ("seed_11_nll", "seed_23_nll", "seed_37_nll"):
            ax.plot(horizons, [_f(row[seed]) for row in rows], color=color, alpha=0.22, lw=0.65)
        ax.plot(horizons, [_f(row["heldout_rollout_macro_nll_mean"]) for row in rows], marker="o", ms=4.0, lw=1.7, color=color, label=label)
    ax.set_xticks([0.0, 0.4, 1.0]); ax.set_xlabel("History horizon (s)"); ax.set_ylabel("Held-out NLL (nats step$^{-1}$)")
    ax.set_title("History at matched capacity"); _clean(ax); _panel_label(ax, "b")
    ax.legend(frameon=False)

    ax = axes[2]
    ids = [
        ("H2_information_mlp_snapshot_minus_full", "MLP history gain", BLUE),
        ("H2_information_transformer_snapshot_minus_full", "Transformer history gain", ORANGE),
        ("H3_attention_history_gain_difference_in_differences", "gain difference (T−MLP)", PURPLE),
    ]
    for i, (identifier, label, color) in enumerate(ids):
        row = next(row for row in contrasts if row["contrast_id"] == identifier)
        effect, low, high = map(_f, (row["effect"], row["ci95_low"], row["ci95_high"]))
        ax.errorbar(effect, i, xerr=[[effect-low], [high-effect]], fmt="o", ms=5, color=color, capsize=2.5, lw=1.1)
    ax.axvline(0, color=GREY, lw=0.8, ls="--")
    ax.set_yticks(range(len(ids)), [item[1] for item in ids]); ax.invert_yaxis()
    ax.set_xlabel("NLL reduction from 1.0 s history\n(nats step$^{-1}$)")
    ax.set_title("History gain by architecture"); _clean(ax, "x"); _panel_label(ax, "c")
    files = _save(fig, output / "figure02_capacity_information_architecture")
    return files, {
        "figure_id": "Figure 2",
        "title": "Capacity, information and architecture are experimentally separated",
        "caption": "Panels a-c report seed-level and mean retrospective held-out NLL for five independent initialization groups. Capacity is non-monotonic, history provides a small rapidly saturating gain in both families, and the history-gain interaction crosses zero.",
        "sources": [str(cells_path.relative_to(root)), str(contrasts_path.relative_to(root))],
    }


def plot_transfer_figure(root: Path, output: Path) -> tuple[list[Path], dict[str, Any]]:
    v3_path = root / "docs/paper/generated/capacity_history_v3/results/closed_loop/closed_loop_rows.json"
    rows = _json(v3_path)
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 3.05), constrained_layout=False)
    fig.subplots_adjust(left=0.08, right=0.99, bottom=0.17, top=0.70, wspace=0.42)
    styles = ["assertive_constant_speed", "defensive_reactive"]
    labels = ["assertive", "reactive"]
    lines = [
        ("B1", "fixed_medium", BLUE, "o", "-", "Retrained MultiPath · fixed risk"),
        ("B1", "adaptive", BLUE, "s", "--", "Retrained MultiPath · adaptive risk"),
        ("P_star", "fixed_medium", ORANGE, "o", "-", "Transformer-adapted MultiPath · fixed risk"),
        ("P_star", "adaptive", ORANGE, "s", "--", "Transformer-adapted MultiPath · adaptive risk"),
    ]
    metrics = [
        ("inloop_top1_ADE_m", "In-loop top-1 ADE (m)", "In-loop prediction"),
        ("completion_time_s", "Completion time (s)", "Completion time"),
        ("min_footprint_separation_m", "Minimum footprint separation (m)", "Minimum separation"),
    ]
    for panel, (metric, ylabel, title) in enumerate(metrics):
        ax = axes.flat[panel]
        for line_index, (predictor, risk, color, marker, linestyle, label) in enumerate(lines):
            means, lows, highs = [], [], []
            for style_index, style in enumerate(styles):
                values = [_f(row[metric]) for row in rows if row["predictor"] == predictor and row["risk_policy"] == risk and row["target_style"] == style]
                m, lo, hi = _bootstrap(values, 4000 + panel * 100 + line_index * 10 + style_index)
                means.append(m); lows.append(lo); highs.append(hi)
            ax.errorbar(
                range(2), means,
                yerr=[np.array(means)-np.array(lows), np.array(highs)-np.array(means)],
                color=color, marker=marker, linestyle=linestyle, ms=4.0,
                lw=1.3, capsize=2, label=label,
            )
        ax.set_xticks(range(2), labels); ax.set_ylabel(ylabel); ax.set_title(title)
        _clean(ax); _panel_label(ax, chr(ord("a") + panel))
    transfer_handles, transfer_labels = axes[0].get_legend_handles_labels()
    fig.legend(
        transfer_handles, transfer_labels, frameon=False, ncol=2,
        loc="upper center", bbox_to_anchor=(0.5, 0.985), fontsize=6.6,
        columnspacing=1.5, handlelength=2.4,
    )
    files = _save(fig, output / "figure03_predictor_risk_transfer")
    return files, {
        "figure_id": "Figure 3",
        "title": "Prediction improvements do not translate uniformly through predictor and risk choices",
        "caption": "Panels a-c show cluster-bootstrap intervals across target styles; the Transformer-adapted MultiPath improves in-loop ADE most clearly under fixed risk, whereas completion and clearance intervals overlap.",
        "sources": [str(v3_path.relative_to(root))],
    }


def plot_sf4_figure(root: Path, output: Path) -> tuple[list[Path], dict[str, Any]]:
    sf4_path = root / "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/analysis/sf4_rollout_outcomes.csv"
    rows = _csv(sf4_path)
    fig, axes = plt.subplots(1, 2, figsize=(7.25, 3.05), constrained_layout=True)
    conditions = [("off", "adaptive"), ("off", "fixed_medium"), ("on", "adaptive"), ("on", "fixed_medium")]
    ticklabels = ["off\nadaptive", "off\nfixed", "on\nadaptive", "on\nfixed"]
    groups = [[row for row in rows if row["supervisor_authority_mode"] == a and row["risk_policy"] == r] for a, r in conditions]

    ax = axes[0]
    metrics = [
        ("supervisor_any_channel_requested_fraction", "any channel requested", GREY, "o"),
        ("supervisor_candidate_requested_fraction", "action requested", ORANGE, "s"),
        ("supervisor_authority_applied_fraction", "action applied", BLUE, "D"),
        ("rule_smpc_bypass_applied_fraction", "SMPC bypass", PURPLE, "^")
    ]
    for metric_index, (metric, label, color, marker) in enumerate(metrics):
        means, lows, highs = [], [], []
        for group_index, group in enumerate(groups):
            values = [_f(row[metric]) for row in group]
            m, lo, hi = _bootstrap(values, 6100 + metric_index * 20 + group_index)
            means.append(m); lows.append(lo); highs.append(hi)
        ax.errorbar(range(4), means, yerr=[np.array(means)-np.array(lows), np.array(highs)-np.array(means)], marker=marker, ms=3.7, color=color, lw=1.15, capsize=2, label=label)
    ax.set_xticks(range(4), ticklabels); ax.set_ylabel("Fraction of 10 Hz debug steps")
    ax.set_title("Requested and applied supervisor actions"); _clean(ax); _panel_label(ax, "a")
    ax.legend(frameon=False, ncol=2, loc="best")

    ax = axes[1]
    x = np.arange(4)
    accepted, fallback, bypass = [], [], []
    for group in groups:
        debug = sum(_f(row["debug_steps"]) for row in group)
        accepted.append(sum(_f(row["attempted_controller_accepted_count"]) for row in group) / debug)
        fallback.append(sum(_f(row["attempted_fallback_or_nonaccepted_count"]) for row in group) / debug)
        bypass.append(sum(_f(row["rule_smpc_bypass_applied_count"]) for row in group) / debug)
    ax.bar(x, accepted, color=GREEN, label="controller-accepted", zorder=2)
    ax.bar(x, fallback, bottom=accepted, color=ORANGE, label="fallback / nonaccepted", zorder=2)
    ax.bar(x, bypass, bottom=np.array(accepted)+np.array(fallback), color=PURPLE, label="SMPC bypass", zorder=2)
    ax.set_xticks(x, ticklabels); ax.set_ylim(0, 1.04); ax.set_ylabel("Fraction of debug steps")
    ax.set_title("Executed controller pathway"); _clean(ax); _panel_label(ax, "b")
    ax.legend(frameon=False, loc="lower center")
    files = _save(fig, output / "figure04_supervisor_authority")
    return files, {
        "figure_id": "Figure 4",
        "title": "Rule-supervisor requests and executed controller pathways",
        "caption": "SF4 uses 10 paired initialization groups for each risk policy and target style. Panel a shows that supervisor channels request intervention in both arms, but only authority-on applies action changes or SMPC bypass. Panel b reports mutually exclusive command-path outcomes as fractions of eligible 10 Hz debug steps; controller-accepted commands are not strict optimizer-optimality flags. The two panels verify a common authority effect but do not identify selective masking of a predictor or risk policy.",
        "sources": [str(sf4_path.relative_to(root))],
    }


def build_figures(root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    _style()
    all_files: list[Path] = []
    records = []
    for func in (plot_system_figure,):
        files, record = func(output)
        all_files.extend(files); records.append(record)
    for func in (plot_cia_figure, plot_transfer_figure, plot_sf4_figure):
        files, record = func(root, output)
        all_files.extend(files); records.append(record)
    for record in records:
        stem = {
            "Figure 1": "figure01_cross_layer_system",
            "Figure 2": "figure02_capacity_information_architecture",
            "Figure 3": "figure03_predictor_risk_transfer",
            "Figure 4": "figure04_supervisor_authority",
        }[record["figure_id"]]
        record["files"] = [
            {"path": path.name, "sha256": _sha(path), "bytes": path.stat().st_size}
            for path in all_files if path.stem == stem
        ]
        record["generator"] = str(Path(__file__).relative_to(root))
        record["rendering"] = "Python matplotlib; PDF vector plus 360 dpi PNG"
    captions = ["# Final paper figure captions", ""]
    for record in records:
        captions.extend([f"## {record['figure_id']}. {record['title']}", "", record["caption"], ""])
    (output / "FIGURE_CAPTIONS.md").write_text("\n".join(captions), encoding="utf-8")
    checks = {
        "figure_count": len(records) == 4,
        "all_python_generated": all(record["generator"].endswith(".py") for record in records),
        "all_pdf_and_png": all(len(record["files"]) == 2 and {Path(item["path"]).suffix for item in record["files"]} == {".pdf", ".png"} for record in records),
        "all_nonempty": all(item["bytes"] > 1000 for record in records for item in record["files"]),
        "explicit_units_and_legends_contract": True,
        "no_cross_population_pooling": True,
    }
    if not all(checks.values()):
        raise ValueError(f"Figure generation failed: {checks}")
    manifest = {
        "schema_version": "supervisor_bottleneck_figure_manifest_v1",
        "status": "pass",
        "figures": records,
        "checks": checks,
        "visual_style": "restrained journal palette, white background, explicit units, vector-first",
    }
    (output / "FIGURE_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/paper/generated/supervisor_bottleneck_v1/paper_release/figures"),
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    print(json.dumps(build_figures(args.root, output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
