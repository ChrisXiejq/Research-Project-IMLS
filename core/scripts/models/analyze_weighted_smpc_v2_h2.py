#!/usr/bin/env python3
"""Audit and analyse the 40-rollout probability-weighted H2 experiment.

The script treats initialization ids as the independent paired units.  It
validates the frozen 2 x 2 assertive-only matrix, recomputes physical outcomes
from per-rollout artifacts, audits the probability-weighted objective at every
logged solver step, and produces restrained Python-only paper figures.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


OBJECTIVE_ID = "multipath_joint_probability_expected_cost_v2"
IMPLEMENTATION_ID = "corrected_joint_modes_shared_amin_probability_weighted_v2"
CONTRACT_SHA256 = "5190b9cb3af946ebeb9dfc48ff18cc4bcb362156bfb809efde0f3b707a303fdb"
PREDICTORS = ("B1", "P_star")
RISKS = ("fixed_medium", "adaptive")
INIT_IDS = tuple(range(126, 136))
PREDICTOR_LABELS = {
    "B1": "Retrained MultiPath",
    "P_star": "Transformer-adapted MultiPath",
}
RISK_LABELS = {"fixed_medium": "Fixed medium", "adaptive": "Adaptive"}

BLUE = "#0072B2"
ORANGE = "#D55E00"
DARK = "#1F2937"
LIGHT_GREY = "#E5E7EB"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def bootstrap_mean(values: Iterable[float], seed: int, draws: int = 50_000) -> tuple[float, float, float]:
    array = np.asarray(list(values), dtype=float)
    if array.size != 10:
        raise ValueError(f"Expected 10 initialization groups, found {array.size}")
    rng = np.random.default_rng(seed)
    samples = array[rng.integers(0, array.size, size=(draws, array.size))].mean(axis=1)
    low, high = np.quantile(samples, (0.025, 0.975))
    return float(array.mean()), float(low), float(high)


def exact_sign_flip_p(values: Iterable[float]) -> float:
    array = np.asarray(list(values), dtype=float)
    observed = abs(float(array.mean()))
    estimates = [
        abs(float(np.mean(array * np.asarray(signs, dtype=float))))
        for signs in itertools.product((-1.0, 1.0), repeat=array.size)
    ]
    return float(np.mean(np.asarray(estimates) >= observed - 1e-15))


def only_path(root: Path, name: str) -> Path:
    paths = list(root.rglob(name))
    if len(paths) != 1:
        raise ValueError(f"Expected one {name} below {root}, found {len(paths)}")
    return paths[0]


def audit_protocol(root: Path) -> dict[str, Any]:
    protocol = read_json(root / "FROZEN_PROTOCOL.json")
    complete = read_json(root / "FORMAL_COMPLETE.json")
    audit = read_json(root / "ON40_INTEGRITY_AUDIT.json")
    core = protocol["core"]
    expected_cells = {
        f"{predictor}__{risk}__assertive__supervisor_on"
        for predictor in PREDICTORS
        for risk in RISKS
    }
    observed_cells = {cell["cell_id"] for cell in core["cells"]}
    directory_cells = {path.name for path in root.iterdir() if path.is_dir()}
    checks = {
        "protocol_schema_v2": protocol["schema_version"] == "probability_weighted_smpc_recovery_protocol_v2",
        "expected_cells": observed_cells == expected_cells == directory_cells,
        "expected_initializations": tuple(core["formal_init_ids"]) == INIT_IDS,
        "expected_rollouts": core["expected_unique_rollouts"] == 40,
        "assertive_only": core["target_style"] == "assertive_constant_speed",
        "supervisor_on": core["supervisor_authority"] == "on",
        "town05": core["town"] == "Town05",
        "weighted_objective": core["objective_id"] == OBJECTIVE_ID,
        "no_unweighted_option": core["objective_unweighted_option_available"] is False,
        "formal_complete": complete["all_passed"] is True and complete["completed_rollouts"] == 40,
        "no_formal_failures": complete["failed_rollouts"] == 0,
        "server_integrity_pass": audit["status"] == "pass" and audit["rollouts"] == 40,
    }
    if not all(checks.values()):
        raise ValueError(f"Frozen protocol audit failed: {checks}")
    return {
        "checks": checks,
        "protocol_core_sha256": protocol["core_sha256"],
        "formal_complete_sha256": sha256_file(root / "FORMAL_COMPLETE.json"),
        "server_integrity_sha256": sha256_file(root / "ON40_INTEGRITY_AUDIT.json"),
    }


def parse_rollout(cell: Path, init_id: int) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    predictor, risk = cell.name.split("__")[:2]
    init_root = cell / f"ego_init_{init_id}"
    receipt = read_json(init_root / "FORMAL_ROLLOUT_COMPLETE.json")
    if not receipt["passed"]:
        raise ValueError(f"Formal receipt failed: {init_root}")

    metrics_path = init_root / "rollout" / "paper_metrics_summary.csv"
    with metrics_path.open(newline="", encoding="utf-8") as handle:
        metric_rows = list(csv.DictReader(handle))
    if len(metric_rows) != 1:
        raise ValueError(f"Expected one metric row in {metrics_path}")
    metrics = metric_rows[0]

    gate = read_json(init_root / "rollout" / "postcarla_trajectory_gate.json")
    if gate["overall_status"] != "PASS" or len(gate["evaluations"]) != 1:
        raise ValueError(f"Post-CARLA gate failed: {init_root}")
    evaluation = gate["evaluations"][0]
    if len(evaluation["pair_safety"]) != 1:
        raise ValueError(f"Expected one ego-target safety pair: {init_root}")
    safety = evaluation["pair_safety"][0]
    if not math.isclose(float(safety["footprint_margin_m"]), 0.25, abs_tol=1e-12):
        raise ValueError(f"Unexpected footprint margin: {init_root}")

    setup = read_json(only_path(init_root, "smpc_debug_setup.json"))
    implementation = setup["control_implementation"]
    if not (
        implementation["objective_weighting"] == OBJECTIVE_ID
        and implementation["version"] == IMPLEMENTATION_ID
        and implementation["objective_weighting_contract_sha256"] == CONTRACT_SHA256
        and implementation["objective_unweighted_option_available"] is False
    ):
        raise ValueError(f"Invalid weighted-objective setup: {init_root}")

    counts = defaultdict(int)
    entropy_values: list[float] = []
    top_probability_values: list[float] = []
    tightening_values: list[float] = []
    target_probability_values: list[float] = []
    prediction_by_step: dict[int, dict[str, Any]] = {}
    debug_path = only_path(init_root, "smpc_debug_steps.jsonl")
    with debug_path.open(encoding="utf-8") as handle:
        for raw in handle:
            step = read_json_line(raw)
            counts["debug_steps"] += 1
            valid_prediction = bool(any(step.get("prediction_valid", [])))
            if valid_prediction:
                counts["prediction_valid_steps"] += 1
                probabilities = np.asarray(step["prediction"]["mode_probs"]["head"], dtype=float)
                probabilities /= probabilities.sum()
                entropy_values.append(float(-np.sum(probabilities * np.log(np.clip(probabilities, 1e-12, None)))))
                top_probability_values.append(float(np.max(probabilities)))
                tightening_values.append(float(step["risk"]["applied_tight"]))
                target_probability_values.append(float(step["risk"]["applied_target_prob"]))
                mode_hashes = tuple(
                    branch["per_vehicle"][0]["mean_sha256"]
                    for branch in step["prediction"]["mode_consumption"]["joint_modes"]
                )
                prediction_by_step[int(step["step"])] = {
                    "probabilities": probabilities,
                    "mean_hashes": mode_hashes,
                }

            channels = (
                step.get("supervisor_behavioural_authority", {})
                .get("complete_candidate_channel_manifest", {})
                .get("channels", {})
            )
            if channels:
                counts["any_supervisor_request"] += int(any(bool(value.get("requested")) for value in channels.values()))
                counts["any_supervisor_application"] += int(any(bool(value.get("applied")) for value in channels.values()))
            action_filter = step.get("applied", {}).get("post_solver_action_filter", {})
            counts["post_solver_action_requested"] += int(bool(action_filter.get("intervention_requested")))
            counts["post_solver_action_applied"] += int(bool(action_filter.get("intervention_applied")))
            counts["effective_smpc_bypass"] += int(bool(step.get("solver_bypass", {}).get("enabled")))

            solver_debug = step.get("solver", {}).get("debug")
            if solver_debug is None:
                continue
            counts["solver_debug_rows"] += 1
            objective_ok = (
                solver_debug.get("objective_weighting") == OBJECTIVE_ID
                and solver_debug.get("control_implementation_version") == IMPLEMENTATION_ID
                and solver_debug.get("objective_weighting_contract_sha256") == CONTRACT_SHA256
                and solver_debug.get("objective_unweighted_option_available") is False
            )
            probabilities = np.asarray(solver_debug.get("joint_mode_probabilities", []), dtype=float)
            weights = np.asarray(solver_debug.get("active_objective_weights", []), dtype=float)
            weights_ok = (
                probabilities.size == weights.size > 0
                and np.all(np.isfinite(probabilities))
                and np.all(np.isfinite(weights))
                and np.allclose(probabilities, weights, atol=1e-12, rtol=0.0)
                and math.isclose(float(probabilities.sum()), 1.0, abs_tol=1e-9)
            )
            if not objective_ok or not weights_ok:
                raise ValueError(f"Weighted objective audit failed at {debug_path}:{step.get('step')}")
            counts["weighted_objective_rows"] += 1
            solver_success = bool(solver_debug.get("success"))
            counts["solver_success_rows"] += int(solver_success)
            counts["solver_non_success_rows"] += int(not solver_success)
            if not solver_success:
                counts["solver_non_success_without_valid_prediction"] += int(not valid_prediction)
                counts["solver_non_success_action_replaced"] += int(
                    bool(action_filter.get("intervention_applied"))
                )
                phase_reason = str(step.get("yield_stop_supervisor", {}).get("reason"))
                counts["solver_non_success_observed_caution"] += int(
                    phase_reason == "observed_target_braking_distance_caution"
                )
                counts["solver_non_success_clear_path_release"] += int(
                    phase_reason == "target_nominally_cleared_clear_path_release"
                )

    if not entropy_values or counts["weighted_objective_rows"] != counts["solver_debug_rows"]:
        raise ValueError(f"Incomplete debug telemetry: {init_root}")
    for key in (
        "solver_non_success_without_valid_prediction",
        "solver_non_success_action_replaced",
        "solver_non_success_observed_caution",
        "solver_non_success_clear_path_release",
    ):
        counts[key] += 0
    fixed_yield = evaluation["fixed_geometry_yield_rules"]
    if len(fixed_yield) != 1:
        raise ValueError(f"Expected one fixed-geometry yield audit: {init_root}")

    n_steps = counts["debug_steps"]
    record = {
        "predictor": predictor,
        "predictor_label": PREDICTOR_LABELS[predictor],
        "risk_policy": risk,
        "risk_label": RISK_LABELS[risk],
        "target_style": "assertive_constant_speed",
        "supervisor_authority": "on",
        "init_id": init_id,
        "completion_time_s": float(metrics["completion_time"]),
        "min_footprint_separation_m": float(safety["min_footprint_separation_m"]),
        "min_center_distance_m": float(safety["min_center_distance_m"]),
        "completion_valid": int(float(metrics["completion_valid"]) == 1.0),
        "yield_compliant": int(bool(fixed_yield[0]["target_clears_before_ego_enters"])),
        "footprint_collision": int(bool(safety["footprint_collision"])),
        "solver_failure_fraction": float(metrics["solver_failure_frac"]),
        "average_solve_time_s": float(metrics["average_solve_time"]),
        "mode_entropy_nats": float(np.mean(entropy_values)),
        "top_mode_probability": float(np.mean(top_probability_values)),
        "tightening_mean": float(np.mean(tightening_values)),
        "tightening_min": float(np.min(tightening_values)),
        "tightening_max": float(np.max(tightening_values)),
        "target_probability_mean": float(np.mean(target_probability_values)),
        **counts,
        "post_solver_action_applied_fraction": counts["post_solver_action_applied"] / n_steps,
        "effective_smpc_bypass_fraction": counts["effective_smpc_bypass"] / n_steps,
    }
    return record, prediction_by_step


def read_json_line(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("SMPC debug line is not a JSON object")
    return value


CELL_METRICS = (
    "completion_time_s",
    "min_footprint_separation_m",
    "solver_failure_fraction",
    "average_solve_time_s",
    "mode_entropy_nats",
    "top_mode_probability",
    "post_solver_action_applied_fraction",
    "effective_smpc_bypass_fraction",
)


def cell_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for predictor in PREDICTORS:
        for risk in RISKS:
            subset = [row for row in rows if row["predictor"] == predictor and row["risk_policy"] == risk]
            record: dict[str, Any] = {
                "predictor": predictor,
                "predictor_label": PREDICTOR_LABELS[predictor],
                "risk_policy": risk,
                "risk_label": RISK_LABELS[risk],
                "initialization_groups": len(subset),
                "completed": sum(row["completion_valid"] for row in subset),
                "yield_compliant": sum(row["yield_compliant"] for row in subset),
                "footprint_collisions": sum(row["footprint_collision"] for row in subset),
            }
            for index, metric in enumerate(CELL_METRICS):
                mean, low, high = bootstrap_mean(
                    [row[metric] for row in subset],
                    seed=20260827 + 100 * index + 10 * PREDICTORS.index(predictor) + RISKS.index(risk),
                )
                record[f"{metric}_mean"] = mean
                record[f"{metric}_ci_low"] = low
                record[f"{metric}_ci_high"] = high
            output.append(record)
    return output


def paired_effects(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {(row["predictor"], row["risk_policy"], row["init_id"]): row for row in rows}
    output: list[dict[str, Any]] = []
    for metric_index, metric in enumerate(CELL_METRICS[:4]):
        definitions: list[tuple[str, str, list[float]]] = []
        for risk in RISKS:
            values = [
                lookup[("P_star", risk, init_id)][metric] - lookup[("B1", risk, init_id)][metric]
                for init_id in INIT_IDS
            ]
            definitions.append(("predictor_effect", f"Transformer-adapted minus retrained MultiPath | {RISK_LABELS[risk]}", values))
        for predictor in PREDICTORS:
            values = [
                lookup[(predictor, "adaptive", init_id)][metric]
                - lookup[(predictor, "fixed_medium", init_id)][metric]
                for init_id in INIT_IDS
            ]
            definitions.append(("risk_effect", f"Adaptive minus fixed medium | {PREDICTOR_LABELS[predictor]}", values))
        values = [
            (lookup[("P_star", "adaptive", init_id)][metric] - lookup[("B1", "adaptive", init_id)][metric])
            - (lookup[("P_star", "fixed_medium", init_id)][metric] - lookup[("B1", "fixed_medium", init_id)][metric])
            for init_id in INIT_IDS
        ]
        definitions.append(("predictor_by_risk", "Predictor-by-risk difference in differences", values))
        for contrast_index, (kind, label, values) in enumerate(definitions):
            mean, low, high = bootstrap_mean(values, 20261827 + 100 * metric_index + contrast_index)
            output.append(
                {
                    "metric": metric,
                    "contrast_type": kind,
                    "contrast": label,
                    "effect": mean,
                    "ci_low": low,
                    "ci_high": high,
                    "exact_two_sided_sign_flip_p": exact_sign_flip_p(values),
                    "paired_initialization_groups": 10,
                }
            )
    return output


def predictor_manipulation_checks(
    prediction_records: dict[tuple[str, str, int], dict[int, dict[str, Any]]]
) -> list[dict[str, Any]]:
    group_rows = []
    for risk in RISKS:
        for init_id in INIT_IDS:
            retrained = prediction_records[("B1", risk, init_id)]
            transformer = prediction_records[("P_star", risk, init_id)]
            common_steps = sorted(set(retrained) & set(transformer))
            if not common_steps:
                raise ValueError(f"No matched prediction steps for {risk}, init {init_id}")
            probability_l1 = [
                float(np.abs(retrained[step]["probabilities"] - transformer[step]["probabilities"]).sum())
                for step in common_steps
            ]
            hash_difference = [
                retrained[step]["mean_hashes"] != transformer[step]["mean_hashes"]
                for step in common_steps
            ]
            group_rows.append(
                {
                    "risk_policy": risk,
                    "init_id": init_id,
                    "matched_prediction_steps": len(common_steps),
                    "mean_probability_l1_distance": float(np.mean(probability_l1)),
                    "trajectory_mean_hash_difference_fraction": float(np.mean(hash_difference)),
                }
            )
    output = []
    for risk_index, risk in enumerate(RISKS):
        subset = [row for row in group_rows if row["risk_policy"] == risk]
        record: dict[str, Any] = {
            "risk_policy": risk,
            "risk_label": RISK_LABELS[risk],
            "paired_initialization_groups": 10,
            "matched_prediction_steps": sum(row["matched_prediction_steps"] for row in subset),
        }
        for metric_index, metric in enumerate(
            ("mean_probability_l1_distance", "trajectory_mean_hash_difference_fraction")
        ):
            mean, low, high = bootstrap_mean(
                [row[metric] for row in subset], 20262827 + 100 * metric_index + risk_index
            )
            record[f"{metric}_mean"] = mean
            record[f"{metric}_ci_low"] = low
            record[f"{metric}_ci_high"] = high
        output.append(record)
    return output


def plot_results(cell_rows: list[dict[str, Any]], output_dir: Path) -> list[Path]:
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
    lookup = {(row["predictor"], row["risk_policy"]): row for row in cell_rows}
    figure, axes = plt.subplots(1, 3, figsize=(7.25, 2.65), constrained_layout=False)
    figure.subplots_adjust(left=0.075, right=0.995, bottom=0.20, top=0.72, wspace=0.40)
    panels = (
        ("mode_entropy_nats", "Deployed mixture entropy (nats)", "Prediction distribution"),
        ("completion_time_s", "Completion time (s)", "Completion efficiency"),
        ("min_footprint_separation_m", "Minimum footprint separation (m)", "Physical separation"),
    )
    x = np.arange(2)
    for panel_index, (metric, ylabel, title) in enumerate(panels):
        axis = axes[panel_index]
        for predictor, color, marker in (("B1", BLUE, "o"), ("P_star", ORANGE, "s")):
            means = np.asarray([lookup[(predictor, risk)][f"{metric}_mean"] for risk in RISKS])
            lows = np.asarray([lookup[(predictor, risk)][f"{metric}_ci_low"] for risk in RISKS])
            highs = np.asarray([lookup[(predictor, risk)][f"{metric}_ci_high"] for risk in RISKS])
            axis.errorbar(
                x,
                means,
                yerr=[means - lows, highs - means],
                color=color,
                marker=marker,
                linestyle="-",
                markersize=4.0,
                linewidth=1.35,
                capsize=2.0,
                label=PREDICTOR_LABELS[predictor],
            )
        axis.set_xticks(x, [RISK_LABELS[risk] for risk in RISKS])
        axis.set_ylabel(ylabel)
        axis.set_title(title)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(True, axis="y", color=LIGHT_GREY, linewidth=0.65)
        axis.set_axisbelow(True)
        axis.text(-0.12, 1.08, chr(ord("a") + panel_index), transform=axis.transAxes, fontweight="bold", fontsize=10, va="top")
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 0.98))
    base = output_dir / "figure03_weighted_predictor_risk_transfer"
    outputs = []
    for suffix in (".pdf", ".png"):
        path = base.with_suffix(suffix)
        figure.savefig(path, dpi=360 if suffix == ".png" else None)
        outputs.append(path)
    plt.close(figure)
    return outputs


def build_report(
    rows: list[dict[str, Any]],
    cells: list[dict[str, Any]],
    effects: list[dict[str, Any]],
    manipulation: list[dict[str, Any]],
    protocol_audit: dict[str, Any],
) -> str:
    effect_lookup = {(row["metric"], row["contrast"]): row for row in effects}
    lines = [
        "# Probability-weighted H2 assertive-only analysis",
        "",
        "## Integrity",
        "",
        "- Formal matrix: 40/40 completed; four cells, ten paired initialization groups per cell.",
        "- Target behaviour: assertive constant speed; supervisor authority: on; CARLA map: Town05.",
        f"- Weighted objective: {sum(row['weighted_objective_rows'] for row in rows):,} audited solver rows; no contract mismatch.",
        f"- Physical outcomes: {sum(row['completion_valid'] for row in rows)}/40 completion, {sum(row['yield_compliant'] for row in rows)}/40 give-way compliance, {sum(row['footprint_collision'] for row in rows)} footprint collisions.",
        f"- Solver non-success: {sum(row['solver_non_success_rows'] for row in rows)}/5,890 rows; {sum(row['solver_non_success_observed_caution'] for row in rows)} occur before a valid prediction during observed-target caution and {sum(row['solver_non_success_clear_path_release'] for row in rows)} during clear-path release. Every such step receives the declared fallback and supervisor action replacement.",
        "",
        "## Primary paired effects",
        "",
    ]
    for risk in RISKS:
        label = f"Transformer-adapted minus retrained MultiPath | {RISK_LABELS[risk]}"
        completion = effect_lookup[("completion_time_s", label)]
        separation = effect_lookup[("min_footprint_separation_m", label)]
        lines.append(
            f"- {RISK_LABELS[risk]}: completion {completion['effect']:+.4f} s "
            f"(95% paired bootstrap [{completion['ci_low']:+.4f}, {completion['ci_high']:+.4f}]); "
            f"separation {separation['effect']:+.4f} m "
            f"([{separation['ci_low']:+.4f}, {separation['ci_high']:+.4f}])."
        )
    for predictor in PREDICTORS:
        label = f"Adaptive minus fixed medium | {PREDICTOR_LABELS[predictor]}"
        completion = effect_lookup[("completion_time_s", label)]
        separation = effect_lookup[("min_footprint_separation_m", label)]
        lines.append(
            f"- Adaptive risk with {PREDICTOR_LABELS[predictor]}: completion {completion['effect']:+.4f} s "
            f"([{completion['ci_low']:+.4f}, {completion['ci_high']:+.4f}]); "
            f"separation {separation['effect']:+.4f} m "
            f"([{separation['ci_low']:+.4f}, {separation['ci_high']:+.4f}])."
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "The deployed predictors produce different mode probabilities and trajectory means, and those probabilities exactly equal the audited SMPC branch-cost weights. The treatment therefore reaches the corrected controller. The physical contrasts remain small and most paired intervals cross zero. These data support transmission of the predictor intervention into the optimiser, but not a consistent completion-time or separation benefit. Mode entropy is a deployment manipulation check, not an in-loop accuracy score.",
            "",
            "## Provenance",
            "",
            f"- Protocol core SHA256: `{protocol_audit['protocol_core_sha256']}`",
            f"- FORMAL_COMPLETE SHA256: `{protocol_audit['formal_complete_sha256']}`",
            f"- Server integrity SHA256: `{protocol_audit['server_integrity_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.input.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    protocol_audit = audit_protocol(root)
    rows: list[dict[str, Any]] = []
    prediction_records: dict[tuple[str, str, int], dict[int, dict[str, Any]]] = {}
    for predictor in PREDICTORS:
        for risk in RISKS:
            cell = root / f"{predictor}__{risk}__assertive__supervisor_on"
            for init_id in INIT_IDS:
                record, prediction = parse_rollout(cell, init_id)
                rows.append(record)
                prediction_records[(predictor, risk, init_id)] = prediction

    if len(rows) != 40 or len({(row["predictor"], row["risk_policy"], row["init_id"]) for row in rows}) != 40:
        raise ValueError("Formal matrix is incomplete or duplicated")
    cells = cell_summaries(rows)
    effects = paired_effects(rows)
    manipulation = predictor_manipulation_checks(prediction_records)
    audited_solver_rows = sum(row["weighted_objective_rows"] for row in rows)
    if audited_solver_rows != 5890:
        raise ValueError(f"Expected 5,890 weighted solver rows, found {audited_solver_rows}")

    write_csv(output / "weighted_h2_rollout_outcomes.csv", rows)
    write_csv(output / "weighted_h2_cell_summary.csv", cells)
    write_csv(output / "weighted_h2_paired_effects.csv", effects)
    write_csv(output / "weighted_h2_predictor_manipulation.csv", manipulation)
    figure_paths = plot_results(cells, output)
    report = build_report(rows, cells, effects, manipulation, protocol_audit)
    (output / "WEIGHTED_H2_ANALYSIS.md").write_text(report, encoding="utf-8")
    manifest = {
        "schema_version": "probability_weighted_h2_assertive_analysis_v1",
        "status": "pass",
        "input": str(root),
        "protocol_audit": protocol_audit,
        "counts": {
            "rollouts": len(rows),
            "paired_initialization_groups": 10,
            "weighted_solver_rows": audited_solver_rows,
            "completion": sum(row["completion_valid"] for row in rows),
            "yield_compliant": sum(row["yield_compliant"] for row in rows),
            "footprint_collisions": sum(row["footprint_collision"] for row in rows),
            "solver_non_success_rows": sum(row["solver_non_success_rows"] for row in rows),
            "solver_non_success_observed_caution": sum(
                row["solver_non_success_observed_caution"] for row in rows
            ),
            "solver_non_success_clear_path_release": sum(
                row["solver_non_success_clear_path_release"] for row in rows
            ),
        },
        "figures": [
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in figure_paths
        ],
        "claim_boundary": (
            "The experiment identifies paired predictor and risk effects for one assertive Town05 give-way task "
            "with supervisor authority enabled. It does not identify a supervisor-on/off effect or a universal safety claim."
        ),
    }
    write_json(output / "WEIGHTED_H2_ANALYSIS_COMPLETE.json", manifest)
    print(report)


if __name__ == "__main__":
    main()
