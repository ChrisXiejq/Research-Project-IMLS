#!/usr/bin/env python3
"""Create restrained academic figures for the corrected mask-V4 study.

All plotted values are read from hash-bound JSON evidence.  The script uses
Matplotlib only; no generative image tooling is involved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload


CELL_ORDER = (
    "head-large",
    "mlp-h0p0-large",
    "transformer-h0p0-large",
    "mlp-h0p4-large",
    "transformer-h0p4-large",
    "mlp-h1p0-large",
    "transformer-h1p0-small",
    "transformer-h1p0-medium",
    "transformer-h1p0-large",
)
CELL_LABELS = (
    "B1",
    "MLP\n0.0 s",
    "Trans.\n0.0 s",
    "MLP\n0.4 s",
    "Trans.\n0.4 s",
    "MLP\n1.0 s",
    "Trans.\nsmall",
    "Trans.\nmedium",
    "Trans.\nlarge",
)
CELL_LABEL_BY_ID = dict(zip(CELL_ORDER, CELL_LABELS))
SEEDS = (11, 23, 37)
BLUE = "#2864A8"
ORANGE = "#D27623"
GREEN = "#2E7D5A"
PURPLE = "#7953A3"
GREY = "#7B7B7B"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_valid(payload: Mapping[str, Any], field: str) -> bool:
    value = dict(payload)
    recorded = value.pop(field, None)
    return recorded == sha256_payload(value)


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": "#D8D8D8",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.65,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _save(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(output_dir / f"{stem}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_mask_impact(impact: Mapping[str, Any], output_dir: Path) -> None:
    rows = impact["rows"]
    by_key = {(row["model_cell_id"], int(row["seed"])): row for row in rows}
    if set(by_key) != {(cell, seed) for cell in CELL_ORDER for seed in SEEDS}:
        raise ValueError("Historical impact figure has incomplete cell/seed membership")
    x = np.arange(len(CELL_ORDER))
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 3.65), constrained_layout=True)

    for seed_index, seed in enumerate(SEEDS):
        old = [
            by_key[(cell, seed)][
                "old_uncalibrated_trajectory_mixture_NLL_per_step_mean"
            ]
            for cell in CELL_ORDER
        ]
        corrected = [
            by_key[(cell, seed)][
                "corrected_uncalibrated_trajectory_mixture_NLL_per_step_mean"
            ]
            for cell in CELL_ORDER
        ]
        axes[0].plot(
            x,
            old,
            color=GREY,
            linestyle="--",
            marker="o",
            markersize=3,
            linewidth=0.9,
            alpha=0.55,
            label="Legacy V3 seeds (diagnostic)" if seed_index == 0 else None,
        )
        axes[0].plot(
            x,
            corrected,
            color=BLUE,
            linestyle="-",
            marker="o",
            markersize=3,
            linewidth=1.05,
            alpha=0.65,
            label="Corrected V4 seeds" if seed_index == 0 else None,
        )
    old_mean = np.mean(
        [
            [
                by_key[(cell, seed)][
                    "old_uncalibrated_trajectory_mixture_NLL_per_step_mean"
                ]
                for cell in CELL_ORDER
            ]
            for seed in SEEDS
        ],
        axis=0,
    )
    corrected_mean = np.mean(
        [
            [
                by_key[(cell, seed)][
                    "corrected_uncalibrated_trajectory_mixture_NLL_per_step_mean"
                ]
                for cell in CELL_ORDER
            ]
            for seed in SEEDS
        ],
        axis=0,
    )
    axes[0].plot(
        x, old_mean, color="#3F3F3F", linewidth=2.0,
        label="Legacy V3 mean (diagnostic)",
    )
    axes[0].plot(x, corrected_mean, color=BLUE, linewidth=2.1, label="Corrected V4 mean")
    axes[0].set_title("a  Historical checkpoints: scoring impact", loc="left", fontweight="bold")
    axes[0].set_ylabel("NLL (nats per scoring step)")
    axes[0].set_xticks(x, CELL_LABELS)
    axes[0].legend(frameon=False, ncol=2, loc="center", bbox_to_anchor=(0.62, 0.54))

    metric_specs = (
        (
            "top1_ADE_mean",
            "legacy ADE-like",
            "valid-step top-1 ADE",
            ORANGE,
            "o",
        ),
        (
            "top1_FDE_mean",
            "legacy terminal-slot displacement",
            "full-support top-1 FDE@2.0 s",
            GREEN,
            "s",
        ),
    )
    for metric, old_label, corrected_label, color, marker in metric_specs:
        old_values = np.mean(
            [
                [
                    by_key[(cell, seed)][f"old_uncalibrated_{metric}"]
                    for cell in CELL_ORDER
                ]
                for seed in SEEDS
            ],
            axis=0,
        )
        corrected_values = np.mean(
            [
                [
                    by_key[(cell, seed)][f"corrected_uncalibrated_{metric}"]
                    for cell in CELL_ORDER
                ]
                for seed in SEEDS
            ],
            axis=0,
        )
        axes[1].plot(
            x,
            old_values,
            color=color,
            linestyle="--",
            marker=marker,
            markersize=4,
            linewidth=1.3,
            alpha=0.65,
            label=f"V3 {old_label} (diagnostic)",
        )
        axes[1].plot(
            x,
            corrected_values,
            color=color,
            linestyle="-",
            marker=marker,
            markersize=4,
            linewidth=2.0,
            label=f"V4 {corrected_label}",
        )
    axes[1].set_title("b  Accuracy distortion from invalid tails", loc="left", fontweight="bold")
    axes[1].set_ylabel("Displacement error (m)")
    axes[1].set_xticks(x, CELL_LABELS)
    axes[1].legend(frameon=False, ncol=2, loc="center", bbox_to_anchor=(0.62, 0.55))
    fig.text(
        0.5,
        -0.035,
        "Impact diagnosis only: legacy V3 scores are superseded; all formal inference uses the V4 valid-step contract.",
        ha="center",
        va="top",
        fontsize=8,
        color="#4A4A4A",
    )
    _save(fig, output_dir, "figure_mask_correction_impact")


def _cells_by_id(payload: Mapping[str, Any], *, full: bool = False) -> dict[str, Any]:
    rows = payload["cell_summaries"]
    return {row["model_cell_id"]: row for row in rows}


def _seed_value(row: Mapping[str, Any], seed: int) -> float:
    return float(row["per_seed"][str(seed)])


def plot_corrected_cia(
    offline: Mapping[str, Any], sensitivity: Mapping[str, Any], output_dir: Path
) -> None:
    cells = _cells_by_id(offline)
    full = _cells_by_id(sensitivity, full=True)
    if set(cells) != set(CELL_ORDER) or set(full) != set(CELL_ORDER):
        raise ValueError("Corrected CIA figure has incomplete model-cell membership")
    fig, axes_grid = plt.subplots(2, 2, figsize=(10.8, 7.0), constrained_layout=True)
    axes = axes_grid.ravel()

    capacity_cells = (
        "transformer-h1p0-small",
        "transformer-h1p0-medium",
        "transformer-h1p0-large",
    )
    capacity_x = np.arange(3)
    for seed_index, seed in enumerate(SEEDS):
        axes[0].plot(
            capacity_x,
            [_seed_value(cells[cell], seed) for cell in capacity_cells],
            color=BLUE,
            alpha=0.35,
            linewidth=0.9,
            marker="o",
            markersize=3,
            label="valid-step seeds" if seed_index == 0 else None,
        )
        axes[0].plot(
            capacity_x,
            [_seed_value(full[cell], seed) for cell in capacity_cells],
            color=PURPLE,
            alpha=0.28,
            linewidth=0.8,
            linestyle="--",
            marker="s",
            markersize=2.7,
            label="full-horizon seeds" if seed_index == 0 else None,
        )
    axes[0].plot(
        capacity_x,
        [cells[cell]["heldout_rollout_macro_nll_mean"] for cell in capacity_cells],
        color=BLUE,
        linewidth=2.2,
        marker="o",
        label="valid-step mean",
    )
    axes[0].plot(
        capacity_x,
        [full[cell]["full_horizon_rollout_macro_nll_mean"] for cell in capacity_cells],
        color=PURPLE,
        linewidth=1.8,
        linestyle="--",
        marker="s",
        label="full-horizon sensitivity",
    )
    axes[0].set_xticks(capacity_x, ("small", "medium", "large"))
    axes[0].set_xlabel("Transformer capacity")
    axes[0].set_ylabel("Held-out NLL (nats per valid step)")
    axes[0].set_title("a  Capacity", loc="left", fontweight="bold")
    axes[0].legend(frameon=False)

    horizons = (0.0, 0.4, 1.0)
    information = {
        "MLP valid-step": (
            ("mlp-h0p0-large", "mlp-h0p4-large", "mlp-h1p0-large"),
            BLUE,
            "-",
            "o",
            cells,
            "heldout_rollout_macro_nll_mean",
        ),
        "Transformer valid-step": (
            (
                "transformer-h0p0-large",
                "transformer-h0p4-large",
                "transformer-h1p0-large",
            ),
            ORANGE,
            "-",
            "s",
            cells,
            "heldout_rollout_macro_nll_mean",
        ),
        "MLP full horizon": (
            ("mlp-h0p0-large", "mlp-h0p4-large", "mlp-h1p0-large"),
            BLUE,
            "--",
            "o",
            full,
            "full_horizon_rollout_macro_nll_mean",
        ),
        "Transformer full horizon": (
            (
                "transformer-h0p0-large",
                "transformer-h0p4-large",
                "transformer-h1p0-large",
            ),
            ORANGE,
            "--",
            "s",
            full,
            "full_horizon_rollout_macro_nll_mean",
        ),
    }
    for seed_index, seed in enumerate(SEEDS):
        for family, model_ids, color, marker in (
            (
                "MLP",
                ("mlp-h0p0-large", "mlp-h0p4-large", "mlp-h1p0-large"),
                BLUE,
                "o",
            ),
            (
                "Transformer",
                (
                    "transformer-h0p0-large",
                    "transformer-h0p4-large",
                    "transformer-h1p0-large",
                ),
                ORANGE,
                "s",
            ),
        ):
            axes[1].plot(
                horizons,
                [_seed_value(cells[cell], seed) for cell in model_ids],
                color=color,
                alpha=0.24,
                linewidth=0.75,
                marker=marker,
                markersize=2.5,
                label=f"{family} seeds" if seed_index == 0 else None,
            )
    for label, (model_ids, color, linestyle, marker, source, field) in information.items():
        axes[1].plot(
            horizons,
            [source[cell][field] for cell in model_ids],
            color=color,
            linestyle=linestyle,
            marker=marker,
            linewidth=2.0 if linestyle == "-" else 1.45,
            label=label,
        )
    axes[1].set_xticks(horizons, ("0.0", "0.4", "1.0"))
    axes[1].set_xlabel("Interaction-history horizon (s)")
    axes[1].set_ylabel("Held-out NLL (nats per valid step)")
    axes[1].set_title("b  Information", loc="left", fontweight="bold")
    axes[1].legend(frameon=False, ncol=2)

    architecture_cells = (
        ("mlp-h0p0-large", "transformer-h0p0-large"),
        ("mlp-h0p4-large", "transformer-h0p4-large"),
        ("mlp-h1p0-large", "transformer-h1p0-large"),
    )
    for seed_index, seed in enumerate(SEEDS):
        axes[2].plot(
            horizons,
            [
                _seed_value(cells[mlp], seed) - _seed_value(cells[transformer], seed)
                for mlp, transformer in architecture_cells
            ],
            color=GREY,
            alpha=0.5,
            linewidth=0.9,
            marker="o",
            markersize=3,
            label="valid-step seeds" if seed_index == 0 else None,
        )
        axes[2].plot(
            horizons,
            [
                _seed_value(full[mlp], seed) - _seed_value(full[transformer], seed)
                for mlp, transformer in architecture_cells
            ],
            color=PURPLE,
            alpha=0.28,
            linewidth=0.8,
            linestyle="--",
            marker="s",
            markersize=2.7,
            label="full-horizon seeds" if seed_index == 0 else None,
        )
    axes[2].plot(
        horizons,
        [
            cells[mlp]["heldout_rollout_macro_nll_mean"]
            - cells[transformer]["heldout_rollout_macro_nll_mean"]
            for mlp, transformer in architecture_cells
        ],
        color=GREEN,
        linewidth=2.2,
        marker="o",
        label="valid-step mean",
    )
    axes[2].plot(
        horizons,
        [
            full[mlp]["full_horizon_rollout_macro_nll_mean"]
            - full[transformer]["full_horizon_rollout_macro_nll_mean"]
            for mlp, transformer in architecture_cells
        ],
        color=PURPLE,
        linewidth=1.8,
        linestyle="--",
        marker="s",
        label="full-horizon sensitivity",
    )
    axes[2].axhline(0.0, color="#333333", linewidth=0.8)
    axes[2].set_xticks(horizons, ("0.0", "0.4", "1.0"))
    axes[2].set_xlabel("Matched history horizon (s)")
    axes[2].set_ylabel("MLP minus Transformer NLL\n(nats per valid step)")
    axes[2].set_title("c  Architecture", loc="left", fontweight="bold")
    axes[2].legend(frameon=False)

    primary = {
        row["contrast_id"]: row
        for row in offline["three_axes"]["primary_contrasts"]
    }
    full_primary = {
        row["contrast_id"]: row
        for row in sensitivity["full_horizon_selection_recalibrated"]["three_axes"][
            "primary_contrasts"
        ]
    }
    contrast_ids = (
        "H1_capacity_transformer_full_small_minus_large",
        "H2_information_mlp_snapshot_minus_full",
        "H2_information_transformer_snapshot_minus_full",
        "H3_attention_history_gain_difference_in_differences",
    )
    contrast_labels = (
        "Capacity:\nsmall − large",
        "Information:\nMLP 0.0 − 1.0 s",
        "Information:\nTrans. 0.0 − 1.0 s",
        "Attention:\nhistory-gain interaction",
    )
    y = np.arange(len(contrast_ids), dtype=np.float64)
    for offset, source, color, marker, label in (
        (-0.10, primary, GREEN, "o", "valid-step primary"),
        (0.10, full_primary, PURPLE, "s", "full-horizon sensitivity"),
    ):
        group_offsets = np.linspace(-0.045, 0.045, 5)
        group_label_used = False
        for row_index, key in enumerate(contrast_ids):
            group_values = [
                float(value)
                for _, value in sorted(
                    source[key].get("paired_init_effects", {}).items(),
                    key=lambda item: int(item[0]),
                )
            ]
            if group_values:
                if len(group_values) != 5:
                    raise ValueError(
                        f"Controlled-effect plot requires five init-group effects: {key}"
                    )
                axes[3].scatter(
                    group_values,
                    y[row_index] + offset + group_offsets,
                    facecolors="none",
                    edgecolors=color,
                    marker=marker,
                    s=18,
                    linewidths=0.7,
                    alpha=0.62,
                    label=f"{label}: init groups" if not group_label_used else None,
                    zorder=2,
                )
                group_label_used = True
        values = np.asarray([float(source[key]["effect"]) for key in contrast_ids])
        lows = np.asarray(
            [float(source[key]["cluster_interval_95"][0]) for key in contrast_ids]
        )
        highs = np.asarray(
            [float(source[key]["cluster_interval_95"][1]) for key in contrast_ids]
        )
        axes[3].errorbar(
            values,
            y + offset,
            xerr=np.vstack((values - lows, highs - values)),
            color=color,
            marker=marker,
            linestyle="none",
            markersize=5,
            capsize=2.5,
            linewidth=1.2,
            label=f"{label}: mean and 95% CI",
            zorder=3,
        )
    axes[3].axvline(0.0, color="#333333", linewidth=0.8)
    axes[3].set_yticks(y, contrast_labels)
    axes[3].invert_yaxis()
    axes[3].set_xlabel("NLL contrast (nats per valid step; positive follows named direction)")
    axes[3].set_title("d  Controlled effects", loc="left", fontweight="bold")
    handles, labels = axes[3].get_legend_handles_labels()
    labels = [
        label.replace("valid-step primary", "V4").replace(
            "full-horizon sensitivity", "Full horizon"
        )
        for label in labels
    ]
    axes[3].legend(
        handles,
        labels,
        frameon=False,
        ncol=2,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.42),
    )
    _save(fig, output_dir, "figure_corrected_capacity_information_architecture")


def _selection_candidates(
    offline: Mapping[str, Any], freeze: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], str]:
    if (
        freeze.get("status") != "pass"
        or freeze.get("selection_split") != "groups_36_40"
        or freeze.get("heldout_split") != "groups_41_45_retrospective"
        or freeze.get("heldout_access_authorized") is not True
    ):
        raise ValueError("Selection-stability figure requires the frozen validation-only split")
    if offline.get("selection_freeze_sha256") != freeze.get("freeze_sha256"):
        raise ValueError("Selection-stability source is not bound to the supplied freeze")
    selected = str(freeze.get("P_star", {}).get("model_cell_id", ""))
    if not selected.startswith(("mlp-", "transformer-")):
        raise ValueError("Selection freeze does not contain a sequence-model P_star")

    heldout_by_cell = _cells_by_id(offline)
    candidates = []
    for cell in freeze.get("cells", []):
        cell_id = str(cell.get("model_cell_id", ""))
        if not cell_id.startswith(("mlp-", "transformer-")):
            continue
        if cell_id not in heldout_by_cell:
            raise ValueError(f"Selection candidate is missing held-out audit evidence: {cell_id}")
        seed_scores = cell.get("seed_scores", {})
        if set(seed_scores) != {str(seed) for seed in SEEDS}:
            raise ValueError(f"Selection candidate lacks three validation seeds: {cell_id}")
        candidates.append(
            {
                "model_cell_id": cell_id,
                "validation_median": float(cell["median_validation_rollout_macro_nll"]),
                "latency_gate_pass": cell.get("latency_gate_pass") is True,
                "validation_seed_scores": {
                    int(seed): float(seed_scores[str(seed)]) for seed in SEEDS
                },
                "heldout_mean": float(
                    heldout_by_cell[cell_id]["heldout_rollout_macro_nll_mean"]
                ),
            }
        )
    if len(candidates) != 8:
        raise ValueError(f"Selection-stability figure requires eight candidates, found {len(candidates)}")
    eligible = [row for row in candidates if row["latency_gate_pass"]]
    if not eligible:
        raise ValueError("Selection-stability figure found no latency-eligible candidate")
    recomputed = min(
        eligible,
        key=lambda row: (
            row["validation_median"],
            next(
                int(cell["trainable_parameters"])
                for cell in freeze["cells"]
                if cell["model_cell_id"] == row["model_cell_id"]
            ),
            next(
                float(cell["median_warmed_batch_one_latency_ms"])
                for cell in freeze["cells"]
                if cell["model_cell_id"] == row["model_cell_id"]
            ),
            row["model_cell_id"],
        ),
    )["model_cell_id"]
    if recomputed != selected:
        raise ValueError("P_star does not match the frozen validation-only selection rule")
    return sorted(candidates, key=lambda row: row["validation_median"]), selected


def plot_selection_stability(
    offline: Mapping[str, Any], freeze: Mapping[str, Any], output_dir: Path
) -> None:
    candidates, selected = _selection_candidates(offline, freeze)
    x = np.arange(len(candidates), dtype=np.float64)
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 3.8), constrained_layout=True)

    for seed_index, seed in enumerate(SEEDS):
        axes[0].plot(
            x,
            [row["validation_seed_scores"][seed] for row in candidates],
            color=GREY,
            alpha=0.45,
            linewidth=0.85,
            marker="o",
            markersize=2.8,
            label="validation seeds" if seed_index == 0 else None,
        )
    validation = [row["validation_median"] for row in candidates]
    axes[0].plot(
        x,
        validation,
        color=BLUE,
        linewidth=2.0,
        marker="o",
        markersize=4,
        label="validation median",
    )
    selected_index = next(
        index for index, row in enumerate(candidates) if row["model_cell_id"] == selected
    )
    axes[0].scatter(
        [selected_index],
        [validation[selected_index]],
        color=GREEN,
        marker="D",
        s=38,
        zorder=4,
        label="validation-selected P* (<=50 ms)",
    )
    axes[0].set_xticks(
        x,
        [CELL_LABEL_BY_ID[row["model_cell_id"]] for row in candidates],
    )
    axes[0].set_ylabel("Validation NLL (nats per valid step)")
    axes[0].set_xlabel("Candidate ordered by validation median")
    axes[0].set_title("a  Validation-only selection", loc="left", fontweight="bold")
    axes[0].legend(frameon=False)

    validation_rank = {
        row["model_cell_id"]: rank
        for rank, row in enumerate(candidates, start=1)
    }
    heldout_order = sorted(candidates, key=lambda row: row["heldout_mean"])
    heldout_rank = {
        row["model_cell_id"]: rank
        for rank, row in enumerate(heldout_order, start=1)
    }
    for row in candidates:
        cell_id = row["model_cell_id"]
        family_color = BLUE if cell_id.startswith("mlp-") else ORANGE
        is_selected = cell_id == selected
        axes[1].plot(
            (0.0, 1.0),
            (validation_rank[cell_id], heldout_rank[cell_id]),
            color=GREEN if is_selected else family_color,
            linewidth=2.2 if is_selected else 1.0,
            marker="D" if is_selected else "o",
            markersize=4.2 if is_selected else 3.2,
            alpha=1.0 if is_selected else 0.72,
        )
        axes[1].text(
            1.04,
            heldout_rank[cell_id],
            CELL_LABEL_BY_ID[cell_id].replace("\n", " "),
            va="center",
            fontsize=7.5,
            color="#333333",
        )
    axes[1].set_xlim(-0.08, 1.52)
    axes[1].set_ylim(len(candidates) + 0.5, 0.5)
    axes[1].set_xticks((0.0, 1.0), ("Validation freeze", "Held-out audit"))
    axes[1].set_yticks(range(1, len(candidates) + 1))
    axes[1].set_ylabel("Rank (1 = lower NLL)")
    axes[1].set_title("b  Retrospective rank stability", loc="left", fontweight="bold")
    axes[1].legend(
        handles=(
            Line2D([0], [0], color=BLUE, marker="o", linewidth=1.2, label="MLP"),
            Line2D([0], [0], color=ORANGE, marker="o", linewidth=1.2, label="Transformer"),
            Line2D([0], [0], color=GREEN, marker="D", linewidth=2.2, label="Frozen P*"),
        ),
        frameon=False,
        loc="lower left",
    )
    fig.text(
        0.5,
        -0.035,
        "P* minimises validation NLL among candidates passing the frozen 50 ms latency gate; "
        "held-out ranks are retrospective and never alter selection.",
        ha="center",
        va="top",
        fontsize=8,
        color="#4A4A4A",
    )
    _save(fig, output_dir, "figure_selection_stability_v4_validation_frozen")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--impact-audit", required=True, type=Path)
    parser.add_argument("--offline-synthesis", type=Path)
    parser.add_argument("--full-horizon-sensitivity", type=Path)
    parser.add_argument("--selection-freeze", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    impact = _load(args.impact_audit)
    if not _hash_valid(impact, "audit_sha256") or impact.get("status") != "pass":
        raise ValueError("Historical impact audit is invalid")
    _style()
    plot_mask_impact(impact, args.output_dir)
    generated = ["figure_mask_correction_impact.pdf", "figure_mask_correction_impact.png"]
    if args.offline_synthesis or args.full_horizon_sensitivity or args.selection_freeze:
        if not all(
            (args.offline_synthesis, args.full_horizon_sensitivity, args.selection_freeze)
        ):
            raise ValueError(
                "Corrected CIA and selection plots require synthesis, sensitivity, and freeze together"
            )
        offline = _load(args.offline_synthesis)
        sensitivity = _load(args.full_horizon_sensitivity)
        freeze = _load(args.selection_freeze)
        if not _hash_valid(offline, "synthesis_sha256") or not _hash_valid(
            sensitivity, "sensitivity_sha256"
        ) or not _hash_valid(freeze, "freeze_sha256"):
            raise ValueError("Corrected synthesis, sensitivity, or selection freeze hash is invalid")
        plot_corrected_cia(offline, sensitivity, args.output_dir)
        plot_selection_stability(offline, freeze, args.output_dir)
        generated.extend(
            [
                "figure_corrected_capacity_information_architecture.pdf",
                "figure_corrected_capacity_information_architecture.png",
                "figure_selection_stability_v4_validation_frozen.pdf",
                "figure_selection_stability_v4_validation_frozen.png",
            ]
        )
    manifest = {
        "schema_version": "capacity_history_future_mask_v4_figure_manifest",
        "status": "pass",
        "generation_method": "Python/Matplotlib",
        "files": {
            name: sha256_file(args.output_dir / name) for name in generated
        },
        "source_artifacts": {
            "impact_audit_sha256": impact["audit_sha256"],
            **(
                {
                    "offline_synthesis_sha256": offline["synthesis_sha256"],
                    "full_horizon_sensitivity_sha256": sensitivity[
                        "sensitivity_sha256"
                    ],
                    "selection_freeze_sha256": freeze["freeze_sha256"],
                }
                if args.offline_synthesis
                else {}
            ),
        },
    }
    manifest["manifest_sha256"] = sha256_payload(manifest)
    atomic_json(args.output_dir / "FIGURE_MANIFEST.json", manifest)
    generated.append("FIGURE_MANIFEST.json")
    print(json.dumps({"status": "pass", "generated": generated}, indent=2))


if __name__ == "__main__":
    main()
