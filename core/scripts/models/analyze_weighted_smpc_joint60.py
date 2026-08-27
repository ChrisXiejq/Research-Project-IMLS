#!/usr/bin/env python3
"""Audit and analyse the matched 60-rollout probability-weighted SMPC study.

The analysis unit is the ego initialisation group.  The script intentionally
reads only frozen rollout artefacts and writes new analysis products; it never
modifies the dissertation source or its existing figures.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


BOOTSTRAP_SEED = 20260827
BOOTSTRAP_REPLICATES = 10_000
FAILURE_PENALTY_S = 30.0
PREDICTORS = ("B1", "P_star")
RISKS = ("fixed_medium", "adaptive")
AUTHORITIES = ("off", "on")
COMMON_INITS = tuple(range(126, 131))
ON_INITS = tuple(range(126, 136))

METRICS = {
    "completion_time_s": {
        "label": "Observed completion time (s)", "direction": "lower_is_better"
    },
    "failure_penalized_completion_time_s": {
        "label": "Failure-penalised completion (s)",
        "direction": "lower_is_better",
    },
    "minimum_margin_adjusted_bbox_separation_m": {
        "label": "Minimum footprint separation (m)\n(0.25 m margin per actor)",
        "direction": "higher_is_better",
    },
    "solver_failure_frac": {
        "label": "Solver failure fraction", "direction": "lower_is_better"
    },
    "formal_gate_pass": {"label": "PostCARLA technical-gate pass rate", "direction": "higher_is_better"},
    "fixed_geometry_yield_success": {
        "label": "Fixed-geometry yield rate", "direction": "higher_is_better"
    },
    "native_collision_any": {"label": "Native collision rate", "direction": "lower_is_better"},
    "margin_adjusted_bbox_violation_any": {
        "label": "0.25 m margin-violation rate", "direction": "lower_is_better"
    },
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def first_mapping(values: Any) -> Mapping[str, Any]:
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], Mapping):
        raise ValueError("Expected one mapping in trajectory-gate field")
    return values[0]


def load_rollout(marker_path: Path) -> dict[str, Any]:
    marker = read_json(marker_path)
    rollout_dir = marker_path.parent / "rollout"
    gate = read_json(rollout_dir / "postcarla_trajectory_gate.json")
    evaluations = gate.get("evaluations")
    evaluation = first_mapping(evaluations)
    with (rollout_dir / "paper_metrics_summary.csv").open(newline="", encoding="utf-8") as handle:
        metric_rows = list(csv.DictReader(handle))
    if len(metric_rows) != 1:
        raise ValueError(f"Expected one metrics row: {rollout_dir}")
    metrics = metric_rows[0]

    cell_tokens = marker["cell_id"].split("__")
    predictor, risk, target_style, authority_token = cell_tokens
    authority = authority_token.removeprefix("supervisor_")
    init_id = int(marker["init_id"])

    primary_margin = first_mapping(evaluation.get("pair_safety"))
    sensitivity = evaluation.get("footprint_margin_sensitivity") or {}
    native = first_mapping(sensitivity.get("0"))
    fixed_yield = first_mapping(evaluation.get("fixed_geometry_yield_rules"))

    completion_valid = bool(evaluation.get("completion_valid"))
    native_collision = bool(native.get("footprint_collision"))
    fixed_yield_success = fixed_yield.get("target_clears_before_ego_enters") is True
    actual_completion = finite(metrics.get("completion_time"))
    if actual_completion is None:
        raise ValueError(f"Missing completion time: {rollout_dir}")
    scientific_failure = (not completion_valid) or native_collision or (not fixed_yield_success)

    return {
        "authority": authority,
        "predictor": predictor,
        "risk": risk,
        "target_style": target_style,
        "init_id": init_id,
        "cell_id": marker["cell_id"],
        "source_dir": str(marker_path.parent),
        "execution_complete": int(bool(marker.get("execution_complete"))),
        # Off markers carry the per-rollout check; on authority is certified by
        # the campaign-level ON40_INTEGRITY_AUDIT.json.
        "authority_integrity_pass": int(bool(marker.get("authority_integrity_pass", True))),
        "formal_gate_pass": int(gate.get("overall_status") == "PASS" and marker.get("passed") is True),
        "completion_valid": int(completion_valid),
        "completion_time_s": actual_completion,
        "failure_penalized_completion_time_s": (
            FAILURE_PENALTY_S if scientific_failure else actual_completion
        ),
        "scientific_failure": int(scientific_failure),
        "fixed_geometry_yield_success": int(fixed_yield_success),
        "trajectory_inferred_yield_success": int(
            first_mapping(evaluation.get("yield_rules")).get("target_clears_before_ego_enters") is True
        ),
        "native_collision_any": int(native_collision),
        "margin_adjusted_bbox_violation_any": int(bool(primary_margin.get("footprint_collision"))),
        "minimum_native_bbox_separation_m": finite(native.get("min_footprint_separation_m")),
        "minimum_margin_adjusted_bbox_separation_m": finite(
            primary_margin.get("min_footprint_separation_m")
        ),
        "solver_failure_frac": finite(evaluation.get("solver_failure_frac")),
        "average_solve_time_s": finite(metrics.get("average_solve_time")),
        "dmin_center_m": finite(metrics.get("dmin_TV")),
    }


def percentile(sorted_values: Sequence[float], probability: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = probability * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def bootstrap_ci(values: Sequence[float], *, salt: int = 0) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan
    rng = random.Random(BOOTSTRAP_SEED + salt)
    samples = [
        statistics.fmean(values[rng.randrange(len(values))] for _ in values)
        for _ in range(BOOTSTRAP_REPLICATES)
    ]
    samples.sort()
    return percentile(samples, 0.025), percentile(samples, 0.975)


def exact_sign_flip(values: Sequence[float]) -> float:
    if not values:
        return math.nan
    observed = abs(statistics.fmean(values))
    count = 0
    total = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(values)):
        statistic = abs(statistics.fmean(sign * value for sign, value in zip(signs, values)))
        count += int(statistic >= observed - 1.0e-15)
        total += 1
    return count / total


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def command_path_summary(command: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in command.get("rollouts") or []:
        authority = str(row["authority"])
        for field in (
            "rows", "any_request_rows", "post_applied_rows", "bypass_applied_rows",
            "solver_attempt_rows", "solver_optimal_rows", "actual_command_diff_rows",
        ):
            grouped[authority][field] += int(row[field])
        grouped[authority]["rollouts"] += 1
    output = []
    for authority in AUTHORITIES:
        counts = grouped[authority]
        rows = counts["rows"]
        attempts = counts["solver_attempt_rows"]
        output.append({
            "authority": authority,
            "rollouts": counts["rollouts"],
            "eligible_rows": rows,
            "any_request_rows": counts["any_request_rows"],
            "any_request_frac": counts["any_request_rows"] / rows,
            "post_applied_rows": counts["post_applied_rows"],
            "post_applied_frac": counts["post_applied_rows"] / rows,
            "bypass_applied_rows": counts["bypass_applied_rows"],
            "bypass_applied_frac": counts["bypass_applied_rows"] / rows,
            "actual_command_diff_rows": counts["actual_command_diff_rows"],
            "actual_command_diff_frac": counts["actual_command_diff_rows"] / rows,
            "solver_attempt_rows": attempts,
            "solver_optimal_rows": counts["solver_optimal_rows"],
            "solver_optimal_frac": counts["solver_optimal_rows"] / attempts,
        })
    return output


def cell_summaries(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["authority"]), str(row["predictor"]), str(row["risk"]))].append(row)
    output: list[dict[str, Any]] = []
    for group_index, (key, items) in enumerate(sorted(grouped.items())):
        record: dict[str, Any] = {
            "authority": key[0], "predictor": key[1], "risk": key[2], "n_init": len(items)
        }
        for metric in METRICS:
            values = [float(item[metric]) for item in items]
            low, high = bootstrap_ci(values, salt=1000 * group_index + len(output))
            record[f"{metric}__mean"] = statistics.fmean(values)
            record[f"{metric}__ci95_low"] = low
            record[f"{metric}__ci95_high"] = high
        output.append(record)
    return output


def lookup(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[int, str, str, str], Mapping[str, Any]]:
    index: dict[tuple[int, str, str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (int(row["init_id"]), str(row["authority"]), str(row["predictor"]), str(row["risk"]))
        if key in index:
            raise ValueError(f"Duplicate matched rollout: {key}")
        index[key] = row
    return index


def summarise_effect(
    *, effect_id: str, family: str, metric: str, estimand: str,
    cluster_values: Sequence[float], scope: str,
) -> dict[str, Any]:
    low, high = bootstrap_ci(cluster_values, salt=sum(ord(char) for char in effect_id + metric))
    return {
        "effect_id": effect_id,
        "family": family,
        "scope": scope,
        "metric": metric,
        "metric_direction": METRICS[metric]["direction"],
        "estimand": estimand,
        "independent_init_groups": len(cluster_values),
        "mean_effect": statistics.fmean(cluster_values),
        "cluster_bootstrap_95ci_low": low,
        "cluster_bootstrap_95ci_high": high,
        "exact_two_sided_sign_flip_sensitivity_value": exact_sign_flip(cluster_values),
        "sign_flip_assumption": "symmetric distribution of init-cluster effects; not randomisation inference",
    }


def effects(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    idx = lookup(rows)
    output: list[dict[str, Any]] = []
    analysed_metrics = tuple(METRICS)

    # Direct authority effect on the matched five-group block. This establishes
    # what physical control changed; interactions below ask whether authority
    # also changed predictor- or risk-policy contrasts.
    for predictor in PREDICTORS:
        for risk in RISKS:
            for metric in analysed_metrics:
                values = [
                    float(idx[(init_id, "on", predictor, risk)][metric])
                    - float(idx[(init_id, "off", predictor, risk)][metric])
                    for init_id in COMMON_INITS
                ]
                output.append(summarise_effect(
                    effect_id=f"authority_on_minus_off__{predictor}__{risk}",
                    family="direct_authority_effect", metric=metric,
                    estimand="supervisor_on - supervisor_off", cluster_values=values,
                    scope=f"{predictor}__{risk}__matched_init126_130",
                ))
    for metric in analysed_metrics:
        values = []
        for init_id in COMMON_INITS:
            within_init = [
                float(idx[(init_id, "on", predictor, risk)][metric])
                - float(idx[(init_id, "off", predictor, risk)][metric])
                for predictor in PREDICTORS for risk in RISKS
            ]
            values.append(statistics.fmean(within_init))
        output.append(summarise_effect(
            effect_id="authority_on_minus_off__pooled_upper_layer",
            family="direct_authority_effect", metric=metric,
            estimand="mean_predictor_risk[supervisor_on - supervisor_off]",
            cluster_values=values, scope="upper_layer_pooled__matched_init126_130",
        ))

    # H2a: predictor effect with supervisor on, using all ten paired init groups.
    for risk in RISKS:
        for metric in analysed_metrics:
            values = [
                float(idx[(init_id, "on", "P_star", risk)][metric])
                - float(idx[(init_id, "on", "B1", risk)][metric])
                for init_id in ON_INITS
            ]
            output.append(summarise_effect(
                effect_id=f"h2_on_predictor__{risk}", family="H2_predictor_transfer",
                metric=metric, estimand="P_star - B1", cluster_values=values,
                scope=f"supervisor_on__{risk}__init126_135",
            ))

    # H2b: predictor x authority interaction on the five shared init groups.
    for risk in RISKS:
        for metric in analysed_metrics:
            values = []
            for init_id in COMMON_INITS:
                off_delta = (
                    float(idx[(init_id, "off", "P_star", risk)][metric])
                    - float(idx[(init_id, "off", "B1", risk)][metric])
                )
                on_delta = (
                    float(idx[(init_id, "on", "P_star", risk)][metric])
                    - float(idx[(init_id, "on", "B1", risk)][metric])
                )
                values.append(off_delta - on_delta)
            output.append(summarise_effect(
                effect_id=f"h2_predictor_x_authority__{risk}", family="H2_predictor_by_authority",
                metric=metric, estimand="(P_star-B1)_off - (P_star-B1)_on",
                cluster_values=values, scope=f"{risk}__matched_init126_130",
            ))
        # end metric

    for metric in analysed_metrics:
        values = []
        for init_id in COMMON_INITS:
            risk_values = []
            for risk in RISKS:
                off_delta = float(idx[(init_id, "off", "P_star", risk)][metric]) - float(
                    idx[(init_id, "off", "B1", risk)][metric]
                )
                on_delta = float(idx[(init_id, "on", "P_star", risk)][metric]) - float(
                    idx[(init_id, "on", "B1", risk)][metric]
                )
                risk_values.append(off_delta - on_delta)
            values.append(statistics.fmean(risk_values))
        output.append(summarise_effect(
            effect_id="h2_predictor_x_authority__pooled_risk", family="H2_predictor_by_authority",
            metric=metric, estimand="mean_risk[(P_star-B1)_off - (P_star-B1)_on]",
            cluster_values=values, scope="risk_pooled__matched_init126_130",
        ))

    # H3: risk x authority interaction, by predictor and pooled.
    for predictor in PREDICTORS:
        for metric in analysed_metrics:
            values = []
            for init_id in COMMON_INITS:
                off_delta = float(idx[(init_id, "off", predictor, "adaptive")][metric]) - float(
                    idx[(init_id, "off", predictor, "fixed_medium")][metric]
                )
                on_delta = float(idx[(init_id, "on", predictor, "adaptive")][metric]) - float(
                    idx[(init_id, "on", predictor, "fixed_medium")][metric]
                )
                values.append(off_delta - on_delta)
            output.append(summarise_effect(
                effect_id=f"h3_risk_x_authority__{predictor}", family="H3_risk_by_authority",
                metric=metric, estimand="(adaptive-fixed)_off - (adaptive-fixed)_on",
                cluster_values=values, scope=f"{predictor}__matched_init126_130",
            ))

    for metric in analysed_metrics:
        values = []
        for init_id in COMMON_INITS:
            predictor_values = []
            for predictor in PREDICTORS:
                off_delta = float(idx[(init_id, "off", predictor, "adaptive")][metric]) - float(
                    idx[(init_id, "off", predictor, "fixed_medium")][metric]
                )
                on_delta = float(idx[(init_id, "on", predictor, "adaptive")][metric]) - float(
                    idx[(init_id, "on", predictor, "fixed_medium")][metric]
                )
                predictor_values.append(off_delta - on_delta)
            values.append(statistics.fmean(predictor_values))
        output.append(summarise_effect(
            effect_id="h3_risk_x_authority__pooled_predictor", family="H3_risk_by_authority",
            metric=metric, estimand="mean_predictor[(adaptive-fixed)_off - (adaptive-fixed)_on]",
            cluster_values=values, scope="predictor_pooled__matched_init126_130",
        ))

    # Exploratory three-way interaction, explicitly labelled as such.
    for metric in analysed_metrics:
        values = []
        for init_id in COMMON_INITS:
            def risk_authority(predictor: str) -> float:
                off_risk = float(idx[(init_id, "off", predictor, "adaptive")][metric]) - float(
                    idx[(init_id, "off", predictor, "fixed_medium")][metric]
                )
                on_risk = float(idx[(init_id, "on", predictor, "adaptive")][metric]) - float(
                    idx[(init_id, "on", predictor, "fixed_medium")][metric]
                )
                return off_risk - on_risk
            values.append(risk_authority("P_star") - risk_authority("B1"))
        output.append(summarise_effect(
            effect_id="exploratory_predictor_x_risk_x_authority", family="exploratory_three_way",
            metric=metric,
            estimand="[(adaptive-fixed)_off-(adaptive-fixed)_on]_P_star - same_B1",
            cluster_values=values, scope="matched_init126_130__exploratory",
        ))
    return output


def set_plot_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9.0, "axes.titlesize": 10.0,
        "axes.labelsize": 9.0, "legend.fontsize": 7.6, "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5, "axes.linewidth": 0.7, "lines.linewidth": 1.7,
        "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.transparent": False,
    })


def cell_record(cells: Sequence[Mapping[str, Any]], authority: str, predictor: str, risk: str) -> Mapping[str, Any]:
    matches = [
        row for row in cells
        if row["authority"] == authority and row["predictor"] == predictor and row["risk"] == risk
    ]
    if len(matches) != 1:
        raise ValueError(f"Missing or duplicate cell summary: {authority}, {predictor}, {risk}")
    return matches[0]


def add_error_line(
    ax: Any, x: Sequence[float], records: Sequence[Mapping[str, Any]], metric: str,
    *, label: str, color: str, marker: str, linestyle: str,
) -> None:
    means = np.array([float(record[f"{metric}__mean"]) for record in records])
    lows = np.array([float(record[f"{metric}__ci95_low"]) for record in records])
    highs = np.array([float(record[f"{metric}__ci95_high"]) for record in records])
    ax.errorbar(
        x, means, yerr=np.vstack([means - lows, highs - means]), label=label,
        color=color, marker=marker, linestyle=linestyle, markersize=4.8,
        capsize=2.7, elinewidth=1.0, zorder=3,
    )


def finish_panel(ax: Any, title: str, ylabel: str, panel_letter: str) -> None:
    ax.set_title(title, loc="left", pad=6, fontweight="semibold")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#d9dde2", linewidth=0.65, alpha=0.9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(-0.13, 1.06, panel_letter, transform=ax.transAxes, fontweight="bold", fontsize=11)


def plot_predictor_transfer(cells: Sequence[Mapping[str, Any]], output_dir: Path) -> None:
    set_plot_style()
    fig, axes = plt.subplots(2, 2, figsize=(7.15, 5.5), constrained_layout=True)
    panel_metrics = (
        "failure_penalized_completion_time_s",
        "minimum_margin_adjusted_bbox_separation_m",
        "solver_failure_frac",
        "formal_gate_pass",
    )
    styles = [
        ("on", "fixed_medium", "Supervisor on · fixed", "#2f5d8a", "o", "-"),
        ("on", "adaptive", "Supervisor on · adaptive", "#2c7a6b", "s", "-"),
        ("off", "fixed_medium", "Supervisor off · fixed", "#b05a3c", "o", "--"),
        ("off", "adaptive", "Supervisor off · adaptive", "#8d5aa6", "s", "--"),
    ]
    for index, (ax, metric) in enumerate(zip(axes.flat, panel_metrics)):
        for authority, risk, label, color, marker, linestyle in styles:
            records = [cell_record(cells, authority, predictor, risk) for predictor in PREDICTORS]
            add_error_line(ax, (0, 1), records, metric, label=label, color=color, marker=marker, linestyle=linestyle)
        ax.set_xticks((0, 1), ("B1", r"P$^{*}$"))
        ax.set_xlabel("Predictor")
        finish_panel(ax, METRICS[metric]["label"].split("\n")[0], METRICS[metric]["label"], chr(65 + index))
        if metric in {"formal_gate_pass", "solver_failure_frac"}:
            ax.set_ylim(-0.04, 1.04)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=2, frameon=False)
    fig.suptitle("Predictor outcomes under matched risk and supervisor authority", fontsize=11.5, fontweight="semibold")
    for suffix in ("pdf", "png"):
        fig.savefig(output_dir / f"figure03_joint60_predictor_authority_transfer.{suffix}", dpi=320, bbox_inches="tight")
    plt.close(fig)


def plot_supervisor_authority(cells: Sequence[Mapping[str, Any]], output_dir: Path) -> None:
    set_plot_style()
    fig, axes = plt.subplots(2, 2, figsize=(7.15, 5.5), constrained_layout=True)
    panel_metrics = (
        "failure_penalized_completion_time_s",
        "minimum_margin_adjusted_bbox_separation_m",
        "solver_failure_frac",
        "fixed_geometry_yield_success",
    )
    styles = [
        ("B1", "fixed_medium", "B1 · fixed", "#2f5d8a", "o", "-"),
        ("B1", "adaptive", "B1 · adaptive", "#2c7a6b", "s", "-"),
        ("P_star", "fixed_medium", r"P$^{*}$ · fixed", "#b05a3c", "o", "--"),
        ("P_star", "adaptive", r"P$^{*}$ · adaptive", "#8d5aa6", "s", "--"),
    ]
    for index, (ax, metric) in enumerate(zip(axes.flat, panel_metrics)):
        for predictor, risk, label, color, marker, linestyle in styles:
            records = [cell_record(cells, authority, predictor, risk) for authority in AUTHORITIES]
            add_error_line(ax, (0, 1), records, metric, label=label, color=color, marker=marker, linestyle=linestyle)
        ax.set_xticks((0, 1), ("Off", "On"))
        ax.set_xlabel("Supervisor behavioural authority")
        finish_panel(ax, METRICS[metric]["label"].split("\n")[0], METRICS[metric]["label"], chr(65 + index))
        if metric in {"fixed_geometry_yield_success", "solver_failure_frac"}:
            ax.set_ylim(-0.04, 1.04)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=2, frameon=False)
    fig.suptitle("Behavioural authority changes physical outcomes across all upper-layer cells", fontsize=11.5, fontweight="semibold")
    for suffix in ("pdf", "png"):
        fig.savefig(output_dir / f"figure04_joint60_supervisor_authority.{suffix}", dpi=320, bbox_inches="tight")
    plt.close(fig)


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def select_effect(effect_rows: Sequence[Mapping[str, Any]], effect_id: str, metric: str) -> Mapping[str, Any]:
    matches = [row for row in effect_rows if row["effect_id"] == effect_id and row["metric"] == metric]
    if len(matches) != 1:
        raise ValueError(f"Missing effect {effect_id}/{metric}")
    return matches[0]


def paper_update_markdown(
    rows: Sequence[Mapping[str, Any]], cells: Sequence[Mapping[str, Any]],
    effect_rows: Sequence[Mapping[str, Any]], command_summary_path: Path,
) -> str:
    on_pass = sum(int(row["formal_gate_pass"]) for row in rows if row["authority"] == "on")
    off_pass = sum(int(row["formal_gate_pass"]) for row in rows if row["authority"] == "off")
    on_fixed_yield = sum(int(row["fixed_geometry_yield_success"]) for row in rows if row["authority"] == "on")
    off_fixed_yield = sum(int(row["fixed_geometry_yield_success"]) for row in rows if row["authority"] == "off")
    h2_fixed = select_effect(effect_rows, "h2_on_predictor__fixed_medium", "failure_penalized_completion_time_s")
    h2_adaptive = select_effect(effect_rows, "h2_on_predictor__adaptive", "failure_penalized_completion_time_s")
    h2_interaction = select_effect(effect_rows, "h2_predictor_x_authority__pooled_risk", "failure_penalized_completion_time_s")
    h3_interaction = select_effect(effect_rows, "h3_risk_x_authority__pooled_predictor", "failure_penalized_completion_time_s")
    direct_authority = select_effect(
        effect_rows, "authority_on_minus_off__pooled_upper_layer",
        "failure_penalized_completion_time_s",
    )
    direct_authority_raw_time = select_effect(
        effect_rows, "authority_on_minus_off__pooled_upper_layer", "completion_time_s"
    )
    direct_authority_separation = select_effect(
        effect_rows, "authority_on_minus_off__pooled_upper_layer",
        "minimum_margin_adjusted_bbox_separation_m",
    )
    command = read_json(command_summary_path)
    command_cells = {row["authority"]: row for row in command_path_summary(command)}
    on_command = command_cells.get("on", {})
    off_command = command_cells.get("off", {})

    def effect_text(row: Mapping[str, Any], unit: str = "s") -> str:
        return (
            f"{fmt(float(row['mean_effect']))} {unit} "
            f"(95% cluster-bootstrap CI {fmt(float(row['cluster_bootstrap_95ci_low']))} to "
            f"{fmt(float(row['cluster_bootstrap_95ci_high']))}; exact sign-flip sensitivity "
            f"p={fmt(float(row['exact_two_sided_sign_flip_sensitivity_value']), 4)})"
        )

    lines = [
        "# Joint60 H2/H3 paper replacement brief",
        "",
        "## Frozen evidence scope",
        "",
        "The corrected probability-weighted SMPC evidence comprises 60 unique assertive-target rollouts: 40 supervisor-on rollouts (B1/P* × fixed/adaptive × ten init groups) and 20 matched supervisor-off rollouts (the same four upper-layer cells × five shared init groups). All integrity audits passed. The supervisor-off scientific failures are retained in the estimates; none was dropped as an execution failure.",
        "",
        "The 30 s failure penalty follows the existing dissertation contract: it applies to noncompletion, native/zero-margin physical overlap, or failure of the fixed-route-geometry yield ordering. A 0.25 m expanded-footprint violation remains a diagnostic rather than a penalty trigger.",
        "",
        "## Result text to replace",
        "",
        "### 1. Update subsection `Better in-loop prediction does not consistently improve driving` (`main.tex` lines 849–884 in SHA e8c2c09)",
        "",
        "Lines 851–860 contain an in-loop ADE claim that cannot be recomputed from the compact Joint60 archive. Retain it only if its separate prediction-deployment evidence remains archived and correctly scoped; Joint60 supports the physical/controller paragraphs, not that ADE paragraph.",
        "",
        f"Suggested numerical core: with behavioural authority on, the paired P*−B1 effect on failure-penalised completion time was {effect_text(h2_fixed)} under fixed risk and {effect_text(h2_adaptive)} under adaptive risk. Across the five init groups shared by both authority conditions, the pooled predictor×authority interaction was {effect_text(h2_interaction)}. Because this interaction is estimated from only five groups and its interval must be interpreted directly, do not claim that the supervisor is the unique cause of predictor masking unless the interval and sign support that statement.",
        "",
        "Replace lines 862–874 and Figure `fig:closed_factorial` at lines 876–884 with `figure03_joint60_predictor_authority_transfer.pdf`. Its four panels report failure-penalised completion, 0.25 m margin-adjusted footprint separation, solver failure fraction, and formal gate pass rate for all eight predictor×risk×authority cells.",
        "",
        "### 2. Replace subsection `Adaptive risk provides a condition-specific efficiency gain` (`main.tex` lines 890–924)",
        "",
        f"Suggested numerical core: the pooled risk×authority interaction on failure-penalised completion time was {effect_text(h3_interaction)}. Report predictor-specific interactions from `joint60_effects.csv`; if their intervals include zero, describe adaptive-vs-fixed differences as unresolved in this assertive scenario rather than as masked.",
        "",
        "### 3. Replace subsection `Supervisor authority is selective but decisive` (`main.tex` from line 926 through the end of the current authority result)",
        "",
        f"Suggested numerical core: fixed-route yield ordering succeeded in {on_fixed_yield}/40 supervisor-on and {off_fixed_yield}/20 supervisor-off rollouts. This compliance comes with delay: switching authority on changed observed completion time by {effect_text(direct_authority_raw_time)} (on−off; positive is slower), but improved the declared failure-penalised outcome by {effect_text(direct_authority)}. Minimum margin-adjusted separation changed by {effect_text(direct_authority_separation, 'm')}; therefore do not claim that authority increased separation. There were no native collisions in either arm, while 4/20 off rollouts and 0/40 on rollouts violated the 0.25 m-per-actor diagnostic margin. The technical PostCARLA gate passed in {on_pass}/40 on and {off_pass}/20 off rollouts; unlike the scientific penalty, that gate did not require fixed-route yield ordering. Telemetry verifies that the off condition was a factual authority ablation: actual command differences occurred in {100.0 * float(on_command.get('actual_command_diff_frac', 0.0)):.1f}% of on rows and {100.0 * float(off_command.get('actual_command_diff_frac', 0.0)):.1f}% of off rows; post-solver actions were applied in {100.0 * float(on_command.get('post_applied_frac', 0.0)):.1f}% versus {100.0 * float(off_command.get('post_applied_frac', 0.0)):.1f}% of rows.",
        "",
        "Replace Figure `fig:supervisor_authority` at lines 928–939 with `figure04_joint60_supervisor_authority.pdf`, including its caption. The figure keeps all four predictor×risk lines and shows their transition from authority off to on. Replace the old 40-off statements at lines 952–965; they are not part of the corrected weighted-controller evidence.",
        "",
        "## Appendix table replacements",
        "",
        "- `tab:closed_cells` at lines 1143–1159: replace old behaviour-averaged rows with the eight assertive predictor×risk×authority cell summaries in `joint60_cell_summary.csv` (ready LaTeX: `joint60_appendix_cell_table.tex`). Do not include an ADE column unless sourced from its separate archive.",
        "- `tab:supervisor` at lines 1161–1180: replace the old authority ablation with matched init126–130 estimates from `joint60_effects.csv`, especially `authority_on_minus_off__*`, `h2_predictor_x_authority__*`, and `h3_risk_x_authority__*`.",
        "- `tab:appendix_supervisor_path` at lines 1182–1207: replace old denominators with `joint60_command_path_summary.csv`; per-rollout detail remains in `JOINT60_COMMAND_PATH_BY_ROLLOUT.csv`.",
        "",
        "### 4. Propagate the corrected scope to `Limitations` and `Conclusion`",
        "",
        "- Update `Limitations` at lines 985–1000: the corrected closed-loop authority evidence is bounded to one assertive constant-speed target behaviour, not two behaviours; the common authority interaction block contains five init groups.",
        "- Update `Conclusion` at lines 1013–1032: remove the broad claim that adaptive risk usually changes the efficiency–separation operating point. In Joint60, fixed versus adaptive risk changes completion by only hundredths of a second and does not change the 0/20 versus 40/40 fixed-geometry yield result. Retain the existing line that authority ablation does not isolate the supervisor as the sole cause of limited predictor transfer; the new predictor×authority interaction directly supports that caution.",
        "",
        "## Claim boundary",
        "",
        "The matched 2×2×2 design identifies predictor×authority and risk×authority interactions for the assertive constant-speed target on init126–130. It does not establish generality to reactive targets or other junction geometries, and five shared init groups give a minimum attainable two-sided exact sign-flip sensitivity value of 0.0625. A null or near-zero interaction is evidence that masking was not resolved by this experiment, not evidence that the two upstream methods are universally equivalent.",
        "",
    ]
    return "\n".join(lines)


def latex_cell_table(cells: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        r"\begin{tabular}{lllrrrr}",
        r"\toprule",
        r"Authority & Predictor & Risk & $n$ & Penalty time (s) & Separation (m) & Gate pass \\",
        r"\midrule",
    ]
    for row in sorted(cells, key=lambda item: (item["authority"], item["predictor"], item["risk"])):
        predictor = r"P$^{*}$" if row["predictor"] == "P_star" else "B1"
        risk = "fixed" if row["risk"] == "fixed_medium" else "adaptive"
        lines.append(
            f"{row['authority']} & {predictor} & {risk} & {row['n_init']} & "
            f"{float(row['failure_penalized_completion_time_s__mean']):.2f} & "
            f"{float(row['minimum_margin_adjusted_bbox_separation_m__mean']):.2f} & "
            f"{float(row['formal_gate_pass__mean']):.2f} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def latex_effect_table(effect_rows: Sequence[Mapping[str, Any]]) -> str:
    selections = (
        ("Authority, observed completion", "authority_on_minus_off__pooled_upper_layer", "completion_time_s"),
        ("Authority, pooled completion", "authority_on_minus_off__pooled_upper_layer", "failure_penalized_completion_time_s"),
        ("Authority, pooled separation", "authority_on_minus_off__pooled_upper_layer", "minimum_margin_adjusted_bbox_separation_m"),
        (r"Predictor $\times$ authority, completion", "h2_predictor_x_authority__pooled_risk", "failure_penalized_completion_time_s"),
        (r"Predictor $\times$ authority, separation", "h2_predictor_x_authority__pooled_risk", "minimum_margin_adjusted_bbox_separation_m"),
        (r"Risk $\times$ authority, completion", "h3_risk_x_authority__pooled_predictor", "failure_penalized_completion_time_s"),
        (r"Risk $\times$ authority, separation", "h3_risk_x_authority__pooled_predictor", "minimum_margin_adjusted_bbox_separation_m"),
    )
    lines = [
        r"\begin{tabular}{lrrr}", r"\toprule",
        r"Contrast & Effect & 95\% cluster-bootstrap CI & Sign-flip sensitivity \\",
        r"\midrule",
    ]
    for label, effect_id, metric in selections:
        row = select_effect(effect_rows, effect_id, metric)
        lines.append(
            f"{label} & {float(row['mean_effect']):+.3f} & "
            f"[{float(row['cluster_bootstrap_95ci_low']):+.3f}, "
            f"{float(row['cluster_bootstrap_95ci_high']):+.3f}] & "
            f"{float(row['exact_two_sided_sign_flip_sensitivity_value']):.4f} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def latex_command_table(command_cells: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        r"\begin{tabular}{lrr}", r"\toprule", r"Diagnostic & Off & On \\", r"\midrule",
    ]
    by_authority = {row["authority"]: row for row in command_cells}
    diagnostics = (
        ("Any-channel request rate", "any_request_frac"),
        ("Post-action applied rate", "post_applied_frac"),
        ("Effective bypass rate", "bypass_applied_frac"),
        ("Actual command-difference rate", "actual_command_diff_frac"),
        ("Solver-optimal fraction", "solver_optimal_frac"),
    )
    for label, key in diagnostics:
        lines.append(
            f"{label} & {float(by_authority['off'][key]):.3f} & "
            f"{float(by_authority['on'][key]):.3f} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    return "\n".join(lines)


def run(args: argparse.Namespace) -> None:
    input_root = args.input_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    on_root = input_root / "formal_supervisor_on_assertive_40_v2_reference_integrity"
    off_root = input_root / "formal_supervisor_off_assertive_20_v2_reference_integrity"
    on_audit = read_json(on_root / "ON40_INTEGRITY_AUDIT.json")
    off_audit = read_json(off_root / "OFF20_INTEGRITY_AUDIT.json")
    if on_audit.get("status") != "pass" or int(on_audit.get("rollouts", -1)) != 40:
        raise ValueError("ON40 campaign integrity audit is not a 40-rollout pass")
    if off_audit.get("status") != "pass" or int(off_audit.get("rollouts", -1)) != 20:
        raise ValueError("OFF20 campaign integrity audit is not a 20-rollout pass")
    if on_audit.get("objective_weighting_contract_sha256") != off_audit.get(
        "objective_weighting_contract_sha256"
    ):
        raise ValueError("On/off objective-weighting contract hashes differ")
    marker_paths = sorted(on_root.glob("*/ego_init_*/FORMAL_ROLLOUT_COMPLETE.json")) + sorted(
        off_root.glob("*/ego_init_*/FORMAL_ROLLOUT_COMPLETE.json")
    )
    rows = [load_rollout(path) for path in marker_paths]
    if len(rows) != 60:
        raise ValueError(f"Expected 60 formal rollouts, found {len(rows)}")
    if Counter(row["authority"] for row in rows) != Counter({"on": 40, "off": 20}):
        raise ValueError("Authority counts differ from frozen 40+20 design")
    if any(row["target_style"] != "assertive" for row in rows):
        raise ValueError("Non-assertive rollout found")
    if any(not row["execution_complete"] or not row["authority_integrity_pass"] for row in rows):
        raise ValueError("Execution or authority integrity failure in frozen results")
    expected_keys = {
        (init_id, authority, predictor, risk)
        for authority in AUTHORITIES
        for predictor in PREDICTORS
        for risk in RISKS
        for init_id in (ON_INITS if authority == "on" else COMMON_INITS)
    }
    if set(lookup(rows)) != expected_keys:
        raise ValueError("Frozen result matrix has missing or unexpected cells")

    cells = cell_summaries(rows)
    effect_rows = effects(rows)
    command_summary_path = input_root / "JOINT60_COMMAND_PATH_SUMMARY.json"
    if not command_summary_path.is_file():
        raise ValueError(f"Missing command-path audit: {command_summary_path}")
    command_cells = command_path_summary(read_json(command_summary_path))

    write_csv(output_dir / "joint60_rollout_outcomes.csv", rows)
    write_csv(output_dir / "joint60_cell_summary.csv", cells)
    write_csv(output_dir / "joint60_effects.csv", effect_rows)
    write_csv(output_dir / "joint60_command_path_summary.csv", command_cells)
    plot_predictor_transfer(cells, output_dir)
    plot_supervisor_authority(cells, output_dir)
    (output_dir / "joint60_appendix_cell_table.tex").write_text(latex_cell_table(cells), encoding="utf-8")
    (output_dir / "joint60_effect_table.tex").write_text(
        latex_effect_table(effect_rows), encoding="utf-8"
    )
    (output_dir / "joint60_command_path_table.tex").write_text(
        latex_command_table(command_cells), encoding="utf-8"
    )
    update_text = paper_update_markdown(rows, cells, effect_rows, command_summary_path)
    (output_dir / "joint60_paper_update.md").write_text(update_text, encoding="utf-8")

    payload = {
        "schema_version": "weighted_smpc_joint60_analysis_v1",
        "status": "pass",
        "input_root": str(input_root),
        "output_dir": str(output_dir),
        "design": {
            "unique_rollouts": 60,
            "supervisor_on_rollouts": 40,
            "supervisor_off_rollouts": 20,
            "target_style": "assertive_constant_speed",
            "on_init_groups": list(ON_INITS),
            "cross_authority_matched_init_groups": list(COMMON_INITS),
        },
        "integrity": {
            "all_execution_complete": True,
            "all_authority_integrity_pass": True,
            "cell_counts": {
                f"{row['authority']}__{row['predictor']}__{row['risk']}": row["n_init"]
                for row in cells
            },
        },
        "outcomes": {
            "formal_gate_pass": {
                authority: {
                    "passed": sum(int(row["formal_gate_pass"]) for row in rows if row["authority"] == authority),
                    "total": sum(1 for row in rows if row["authority"] == authority),
                }
                for authority in AUTHORITIES
            },
            "scientific_failures_retained": sum(int(row["scientific_failure"]) for row in rows),
            "fixed_geometry_yield_success": {
                authority: {
                    "successes": sum(
                        int(row["fixed_geometry_yield_success"])
                        for row in rows if row["authority"] == authority
                    ),
                    "total": sum(1 for row in rows if row["authority"] == authority),
                }
                for authority in AUTHORITIES
            },
        },
        "command_path_by_authority": command_cells,
        "inference": {
            "unit": "ego_init_id",
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "sign_flip": "exact two-sided sensitivity under symmetric init-effect assumption; not randomisation inference",
            "effect_rows": len(effect_rows),
        },
        "claim_boundary": (
            "The five-group matched authority experiment identifies interactions only in the "
            "assertive constant-speed scenario. It cannot establish generality to reactive targets "
            "or other junction geometries; null interactions do not prove universal equivalence."
        ),
    }
    (output_dir / "joint60_analysis.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload["outcomes"], indent=2, sort_keys=True))
    print(output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
