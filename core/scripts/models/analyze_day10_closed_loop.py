#!/usr/bin/env python3
"""Create reproducible paired statistics from the Day 10 closed-loop matrix.

The script intentionally uses a rollout/condition as the analysis unit.  It
never treats 20 Hz simulator steps as independent observations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any, Iterable


ROLLOUT_METRICS = (
    "completion_time_s",
    "min_footprint_separation_m",
    "min_center_distance_m",
    "clearance_s",
    "feasibility_fraction",
    "solver_failure_fraction",
    "average_solve_time_s",
    "max_lateral_acceleration_mps2",
    "avg_longitudinal_jerk_mps3",
    "avg_lateral_jerk_mps3",
    "supervisor_active_fraction",
    "risk_tightening_mean",
)

PRIMARY_METRICS = (
    "completion_time_s",
    "min_footprint_separation_m",
    "solver_failure_fraction",
    "supervisor_active_fraction",
)


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_float(value: Any) -> float:
    if value in (None, ""):
        return math.nan
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return float(value.lower() == "true")
    return float(value)


def finite(values: Iterable[float]) -> list[float]:
    return [value for value in values if math.isfinite(value)]


def mean(values: Iterable[float]) -> float:
    clean = finite(values)
    return statistics.fmean(clean) if clean else math.nan


def weighted_mean(rows: list[dict[str, str]], key: str) -> float:
    pairs = []
    for row in rows:
        value = as_float(row.get(key))
        weight = as_float(row.get("n_steps"))
        if math.isfinite(value) and math.isfinite(weight) and weight > 0:
            pairs.append((value, weight))
    total = sum(weight for _, weight in pairs)
    return sum(value * weight for value, weight in pairs) / total if total else math.nan


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        return math.nan
    position = probability * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def bootstrap_mean_ci(values: list[float], label: str, repetitions: int = 20000) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan
    seed = int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    estimates = sorted(
        statistics.fmean(rng.choice(values) for _ in values)
        for _ in range(repetitions)
    )
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def exact_sign_flip_p(values: list[float]) -> float:
    """Two-sided paired randomization p-value for the mean difference."""
    nonzero = [value for value in values if not math.isclose(value, 0.0, abs_tol=1e-15)]
    if not nonzero:
        return 1.0
    observed = abs(statistics.fmean(nonzero))
    extreme = 0
    total = 1 << len(nonzero)
    for signs in itertools.product((-1.0, 1.0), repeat=len(nonzero)):
        permuted = abs(statistics.fmean(sign * value for sign, value in zip(signs, nonzero)))
        if permuted >= observed - 1e-12:
            extreme += 1
    return extreme / total


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty table: {path}")
    fields = fields or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def load_rollouts(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    complete = read_json(root / "DAY10_COMPLETE.json")
    audit = read_json(root / "day10_closed_loop_audit.json")
    contract = read_json(root / "day10_run_contract.json")
    if complete.get("status") != "pass" or audit.get("status") != "pass":
        raise ValueError("Day 10 completion/audit status is not pass")

    audit_cells = {item["cell_id"]: item for item in audit["evaluations"]}
    expected_inits = set(int(value) for value in contract["ego_init_ids"])
    rollouts: list[dict[str, Any]] = []

    for cell in contract["cells"]:
        cell_id = cell["cell_id"]
        cell_dir = root / cell_id
        metrics_rows = read_csv(cell_dir / "df_full.csv")
        metrics_by_init = {int(row["initial"]): row for row in metrics_rows}
        gate = read_json(cell_dir / "postcarla_trajectory_gate.json")
        gate_by_init = {
            int(Path(item["scenario_dir"]).name.split("_ego_init_")[1].split("_")[0]): item
            for item in gate["evaluations"]
        }
        mechanism_rows = read_csv(cell_dir / "risk_by_conflict_distance_summary.csv")
        mechanism_by_init: dict[int, list[dict[str, str]]] = {}
        for row in mechanism_rows:
            mechanism_by_init.setdefault(int(row["initial"]), []).append(row)
        audit_by_init = {int(item["ego_init_id"]): item for item in audit_cells[cell_id]["rollouts"]}

        observed = set(metrics_by_init) & set(gate_by_init) & set(mechanism_by_init) & set(audit_by_init)
        if observed != expected_inits:
            raise ValueError(f"{cell_id}: expected inits {sorted(expected_inits)}, observed {sorted(observed)}")

        for init_id in sorted(expected_inits):
            metric = metrics_by_init[init_id]
            gate_item = gate_by_init[init_id]
            safety = gate_item["pair_safety"][0]
            yield_rule = gate_item["yield_rules"][0]
            audit_item = audit_by_init[init_id]
            mechanism = mechanism_by_init[init_id]
            rollout = {
                "cell_id": cell_id,
                "predictor": cell["predictor"],
                "risk_policy": cell["risk_policy"],
                "target_style": cell["target_style"],
                "ego_init_id": init_id,
                "completion_time_s": as_float(metric["completion_time"]),
                "completion_valid": as_float(metric["completion_valid"]),
                "min_footprint_separation_m": as_float(safety["min_footprint_separation_m"]),
                "min_center_distance_m": as_float(safety["min_center_distance_m"]),
                "footprint_collision": as_float(safety["footprint_collision"]),
                "yield_order_valid": as_float(yield_rule["target_clears_before_ego_enters"]),
                "clearance_s": as_float(yield_rule["ego_enter_time_s"]) - as_float(yield_rule["target_exit_time_s"]),
                "feasibility_fraction": as_float(metric["feasibility_percent"]),
                "solver_failure_fraction": as_float(metric["solver_failure_frac"]),
                "average_solve_time_s": as_float(metric["average_solve_time"]),
                "max_lateral_acceleration_mps2": as_float(metric["max_lateral_acceleration"]),
                "avg_longitudinal_jerk_mps3": as_float(metric["avg_longitudinal_jerk"]),
                "avg_lateral_jerk_mps3": as_float(metric["avg_lateral_jerk"]),
                "supervisor_active_fraction": weighted_mean(mechanism, "supervisor_active_frac"),
                "hard_stop_override_fraction": weighted_mean(mechanism, "hard_stop_override_frac"),
                "risk_tightening_mean": weighted_mean(mechanism, "risk_tightening_mean"),
                "adaptive_risk_solver_fraction": weighted_mean(mechanism, "solver_uses_adaptive_risk_frac"),
                "reactive_active_samples": int(audit_item["reactive_active_samples"]),
                "invalid_probabilities": int(audit_item["invalid_probabilities"]),
                "invalid_covariances": int(audit_item["invalid_covariances"]),
            }
            rollouts.append(rollout)

    expected_rollouts = int(contract["expected_rollouts"])
    if len(rollouts) != expected_rollouts:
        raise ValueError(f"Expected {expected_rollouts} rollouts, observed {len(rollouts)}")
    return rollouts, {"complete": complete, "audit": audit, "contract": contract}


def build_cell_summaries(rollouts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for rollout in rollouts:
        key = (rollout["predictor"], rollout["risk_policy"], rollout["target_style"])
        groups.setdefault(key, []).append(rollout)
    summaries = []
    for (predictor, risk_policy, target_style), rows in sorted(groups.items()):
        summary: dict[str, Any] = {
            "predictor": predictor,
            "risk_policy": risk_policy,
            "target_style": target_style,
            "n_rollouts": len(rows),
            "completion_rate": mean(row["completion_valid"] for row in rows),
            "collision_rate": mean(row["footprint_collision"] for row in rows),
            "yield_success_rate": mean(row["yield_order_valid"] for row in rows),
            "reactive_active_samples": sum(row["reactive_active_samples"] for row in rows),
        }
        for metric in ROLLOUT_METRICS:
            values = finite(row[metric] for row in rows)
            summary[f"{metric}_mean"] = mean(values)
            summary[f"{metric}_sd"] = statistics.stdev(values) if len(values) > 1 else 0.0
        summaries.append(summary)
    return summaries


def describe_contrast(
    family: str,
    inference_scope: str,
    name: str,
    metric: str,
    deltas: list[float],
    a_label: str,
    b_label: str,
) -> dict[str, Any]:
    clean = finite(deltas)
    low, high = bootstrap_mean_ci(clean, f"{family}|{name}|{metric}")
    return {
        "contrast_family": family,
        "inference_scope": inference_scope,
        "contrast": name,
        "metric": metric,
        "a_label": a_label,
        "b_label": b_label,
        "n_pairs": len(clean),
        "mean_delta_a_minus_b": mean(clean),
        "median_delta_a_minus_b": statistics.median(clean),
        "sd_delta": statistics.stdev(clean) if len(clean) > 1 else 0.0,
        "bootstrap_95ci_low": low,
        "bootstrap_95ci_high": high,
        "exact_sign_flip_p_two_sided": exact_sign_flip_p(clean),
        "positive_pairs": sum(value > 0 for value in clean),
        "negative_pairs": sum(value < 0 for value in clean),
        "zero_pairs": sum(math.isclose(value, 0.0, abs_tol=1e-15) for value in clean),
    }


def add_holm_adjustment(contrasts: list[dict[str, Any]]) -> None:
    """Add Holm family-wise adjusted p-values within declared scopes."""
    scopes: dict[str, list[dict[str, Any]]] = {}
    for contrast in contrasts:
        scopes.setdefault(contrast["inference_scope"], []).append(contrast)
    for rows in scopes.values():
        ordered = sorted(rows, key=lambda row: row["exact_sign_flip_p_two_sided"])
        running = 0.0
        total = len(ordered)
        for rank, row in enumerate(ordered):
            adjusted = min(1.0, (total - rank) * row["exact_sign_flip_p_two_sided"])
            running = max(running, adjusted)
            row["holm_adjusted_p_within_scope"] = running


def build_contrasts(rollouts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = {
        (row["predictor"], row["risk_policy"], row["target_style"], row["ego_init_id"]): row
        for row in rollouts
    }
    risks = ("fixed_aggressive", "fixed_medium", "fixed_conservative", "adaptive")
    fixed = risks[:3]
    styles = ("assertive", "reactive")
    inits = sorted({row["ego_init_id"] for row in rollouts})
    contrasts: list[dict[str, Any]] = []

    for risk in risks:
        for style_group, selected_styles in [("pooled", styles), *[(style, (style,)) for style in styles]]:
            for metric in PRIMARY_METRICS:
                deltas = [
                    index[("B1", risk, style, init_id)][metric]
                    - index[("B0", risk, style, init_id)][metric]
                    for style in selected_styles
                    for init_id in inits
                ]
                contrasts.append(describe_contrast(
                    "predictor_within_risk",
                    "predictor_within_risk_pooled_primary" if style_group == "pooled" else "predictor_within_risk_style_descriptive",
                    f"B1_minus_B0__{risk}__{style_group}",
                    metric,
                    deltas,
                    "B1",
                    "B0",
                ))

    for predictor in ("B0", "B1"):
        for fixed_policy in fixed:
            for style_group, selected_styles in [("pooled", styles), *[(style, (style,)) for style in styles]]:
                for metric in PRIMARY_METRICS:
                    deltas = [
                        index[(predictor, "adaptive", style, init_id)][metric]
                        - index[(predictor, fixed_policy, style, init_id)][metric]
                        for style in selected_styles
                        for init_id in inits
                    ]
                    contrasts.append(describe_contrast(
                        "adaptive_vs_fixed",
                        "adaptive_vs_fixed_pooled_primary" if style_group == "pooled" else "adaptive_vs_fixed_style_descriptive",
                        f"adaptive_minus_{fixed_policy}__{predictor}__{style_group}",
                        metric,
                        deltas,
                        "adaptive",
                        fixed_policy,
                    ))

    for fixed_policy in fixed:
        for metric in PRIMARY_METRICS:
            deltas = []
            for style in styles:
                for init_id in inits:
                    adaptive_predictor_delta = (
                        index[("B1", "adaptive", style, init_id)][metric]
                        - index[("B0", "adaptive", style, init_id)][metric]
                    )
                    fixed_predictor_delta = (
                        index[("B1", fixed_policy, style, init_id)][metric]
                        - index[("B0", fixed_policy, style, init_id)][metric]
                    )
                    deltas.append(adaptive_predictor_delta - fixed_predictor_delta)
            contrasts.append(describe_contrast(
                "predictor_x_risk_interaction",
                "predictor_x_risk_primary",
                f"B1_B0_effect__adaptive_minus_{fixed_policy}",
                metric,
                deltas,
                "B1-B0 under adaptive",
                f"B1-B0 under {fixed_policy}",
            ))

    for metric in PRIMARY_METRICS:
        deltas = []
        for init_id in inits:
            reactive_effect = mean(
                index[("B1", risk, "reactive", init_id)][metric]
                - index[("B0", risk, "reactive", init_id)][metric]
                for risk in risks
            )
            assertive_effect = mean(
                index[("B1", risk, "assertive", init_id)][metric]
                - index[("B0", risk, "assertive", init_id)][metric]
                for risk in risks
            )
            deltas.append(reactive_effect - assertive_effect)
        contrasts.append(describe_contrast(
            "predictor_x_target_interaction",
            "predictor_x_target_primary",
            "B1_B0_effect__reactive_minus_assertive",
            metric,
            deltas,
            "B1-B0 under reactive",
            "B1-B0 under assertive",
        ))
    add_holm_adjustment(contrasts)
    return contrasts


def build_summary(
    root: Path,
    rollouts: list[dict[str, Any]],
    metadata: dict[str, Any],
    contrasts: list[dict[str, Any]],
) -> dict[str, Any]:
    by_style: dict[str, dict[str, float]] = {}
    index = {
        (row["predictor"], row["risk_policy"], row["target_style"], row["ego_init_id"]): row
        for row in rollouts
    }
    risks = ("fixed_aggressive", "fixed_medium", "fixed_conservative", "adaptive")
    inits = sorted({row["ego_init_id"] for row in rollouts})
    for style in ("assertive", "reactive"):
        by_style[style] = {}
        for metric in PRIMARY_METRICS:
            values = [
                abs(index[("B1", risk, style, init_id)][metric] - index[("B0", risk, style, init_id)][metric])
                for risk in risks
                for init_id in inits
            ]
            by_style[style][metric] = mean(values)

    return {
        "schema_version": "day10_paired_analysis_v1",
        "status": "pass",
        "analysis_unit": metadata["contract"]["analysis_unit"],
        "source": {
            "day10_complete_sha256": sha256(root / "DAY10_COMPLETE.json"),
            "closed_loop_audit_sha256": sha256(root / "day10_closed_loop_audit.json"),
            "run_contract_sha256": sha256(root / "day10_run_contract.json"),
            "execution_git_commits": metadata["contract"].get("execution_git_commits", []),
        },
        "counts": {
            "cells": len({row["cell_id"] for row in rollouts}),
            "rollouts": len(rollouts),
            "paired_contrasts": len(contrasts),
        },
        "reliability": {
            "completion_failures": sum(row["completion_valid"] < 0.5 for row in rollouts),
            "footprint_collisions": sum(row["footprint_collision"] > 0.5 for row in rollouts),
            "yield_order_failures": sum(row["yield_order_valid"] < 0.5 for row in rollouts),
            "solver_gate_failures": sum(row["solver_failure_fraction"] > 0.05 for row in rollouts),
            "invalid_probabilities": sum(row["invalid_probabilities"] for row in rollouts),
            "invalid_covariances": sum(row["invalid_covariances"] for row in rollouts),
            "max_solver_failure_fraction": max(row["solver_failure_fraction"] for row in rollouts),
            "min_footprint_separation_m": min(row["min_footprint_separation_m"] for row in rollouts),
        },
        "mean_absolute_predictor_delta_by_target_style": by_style,
        "statistical_notes": [
            "Paired rollouts, not simulator steps, are the analysis unit.",
            "Bootstrap intervals are deterministic percentile intervals over paired conditions.",
            "Exact p-values use all sign flips of paired deltas and are exploratory with n=5 or n=10.",
            "Holm adjustment controls family-wise error within each declared inference scope; style-specific contrasts are descriptive.",
            "Raw jerk is retained only as a secondary descriptive metric because it is sensitive to 20 Hz numerical differentiation.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.results_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    rollouts, metadata = load_rollouts(root)
    cells = build_cell_summaries(rollouts)
    contrasts = build_contrasts(rollouts)
    summary = build_summary(root, rollouts, metadata, contrasts)

    write_csv(output / "day10_rollout_metrics.csv", rollouts)
    write_csv(output / "day10_cell_summary.csv", cells)
    write_csv(output / "day10_paired_contrasts.csv", contrasts)
    (output / "day10_analysis_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
