#!/usr/bin/env python3
"""Audit and analyse the probability-weighted supervisor-authority experiment.

The evidence set contains 40 supervisor-on rollouts and 20 supervisor-off
rollouts.  Initialisation ids 126--130 form the paired authority comparison;
ids 131--135 are retained only as additional supervisor-on replications for
the predictor--risk transfer analysis.  Statistical resampling treats an
initialisation id, not a controller step or a factorial cell, as the
independent unit.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


OBJECTIVE_ID = "multipath_joint_probability_expected_cost_v2"
IMPLEMENTATION_ID = "corrected_joint_modes_shared_amin_probability_weighted_v2"
CONTRACT_SHA256 = "5190b9cb3af946ebeb9dfc48ff18cc4bcb362156bfb809efde0f3b707a303fdb"
ARCHIVE_SHA256 = "7bc5d0550ffbe5183b3d09f4cef145d4c5f077622a874f0d7faf93fb583c6285"
PREDICTORS = ("B1", "P_star")
RISKS = ("fixed_medium", "adaptive")
AUTHORITIES = ("on", "off")
PAIRED_INIT_IDS = tuple(range(126, 131))
ON_EXTRA_INIT_IDS = tuple(range(131, 136))
PREDICTOR_LABELS = {
    "B1": "Retrained MultiPath",
    "P_star": "Transformer-adapted MultiPath",
}
RISK_LABELS = {"fixed_medium": "Fixed medium", "adaptive": "Adaptive"}
AUTHORITY_LABELS = {"on": "Authority on", "off": "Authority off"}

BLUE = "#0072B2"
ORANGE = "#D55E00"
GREY = "#7A8491"
DARK = "#1F2937"
LIGHT_GREY = "#D9DEE5"


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
        raise ValueError(f"Cannot write an empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def only_path(root: Path, name: str) -> Path:
    paths = list(root.rglob(name))
    if len(paths) != 1:
        raise ValueError(f"Expected one {name} below {root}, found {len(paths)}")
    return paths[0]


def bootstrap_mean(
    values: Iterable[float], seed: int, draws: int = 50_000
) -> tuple[float, float, float]:
    array = np.asarray(list(values), dtype=float)
    if array.size < 2:
        raise ValueError("Bootstrap requires at least two independent groups")
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


def audit_protocols(input_root: Path) -> tuple[Path, Path, dict[str, Any]]:
    on_root = input_root / "formal_supervisor_on_assertive_40_v2_reference_integrity"
    off_root = input_root / "formal_supervisor_off_assertive_20_v2_reference_integrity"
    joint = read_json(input_root / "JOINT60_INTEGRITY_AUDIT.json")
    on_protocol = read_json(on_root / "FROZEN_PROTOCOL.json")
    off_protocol = read_json(off_root / "FROZEN_PROTOCOL.json")
    on_complete = read_json(on_root / "FORMAL_COMPLETE.json")
    off_complete = read_json(off_root / "FORMAL_COMPLETE.json")
    on_audit = read_json(on_root / "ON40_INTEGRITY_AUDIT.json")
    off_audit = read_json(off_root / "OFF20_INTEGRITY_AUDIT.json")
    archive_path = input_root / "weighted_smpc_joint60_compact.tar.gz"

    on_core, off_core = on_protocol["core"], off_protocol["core"]
    common_hash_keys = (
        "B1_model",
        "B1_calibration",
        "P_star_model",
        "P_star_calibration",
        "anchors",
        "adaptive_config",
        "scenario",
        "scenario_runner",
        "smpc_agent",
        "smpc_model",
        "mode_probability_contract",
    )
    common_hashes_match = all(
        on_core["file_sha256"][key] == off_core["file_sha256"][key]
        for key in common_hash_keys
    )
    checks = {
        "joint_integrity_pass": joint["status"] == "pass" and not joint["failures"],
        "rollout_counts": joint["on_rollouts"] == 40 and joint["off_rollouts"] == 20,
        "paired_initialisations": tuple(joint["paired_init_ids"]) == PAIRED_INIT_IDS,
        "on_extra_initialisations": tuple(joint["on_extra_init_ids"]) == ON_EXTRA_INIT_IDS,
        "protocol_schema": on_protocol["schema_version"] == off_protocol["schema_version"]
        == "probability_weighted_smpc_recovery_protocol_v2",
        "assertive_only": on_core["target_style"] == off_core["target_style"]
        == "assertive_constant_speed",
        "town05": on_core["town"] == off_core["town"] == "Town05",
        "authority_treatment": on_core["supervisor_authority"] == "on"
        and off_core["supervisor_authority"] == "off"
        and off_core["matched_authority_only_tuning"] is True,
        "weighted_objective": on_core["objective_id"] == off_core["objective_id"]
        == OBJECTIVE_ID,
        "no_unweighted_option": on_core["objective_unweighted_option_available"] is False
        and off_core["objective_unweighted_option_available"] is False,
        "common_artifact_hashes": common_hashes_match,
        "on_complete": on_complete["all_passed"] is True
        and on_complete["completed_rollouts"] == 40,
        "off_execution_complete": off_complete["matrix_execution_complete"] is True
        and off_complete["completed_rollouts"] == 20,
        "server_integrity_audits": on_audit["status"] == off_audit["status"] == "pass"
        and on_audit["rollouts"] == 40
        and off_audit["rollouts"] == 20,
        "weighted_solver_row_audit": on_audit["solver_rows"] == 5890
        and off_audit["solver_rows"] == 2888
        and off_audit["probability_weighted_solver_rows"] == 2888,
        "objective_contract": on_audit["objective_weighting_contract_sha256"]
        == off_audit["objective_weighting_contract_sha256"]
        == [CONTRACT_SHA256],
        "downloaded_archive_sha256": archive_path.is_file()
        and sha256_file(archive_path) == ARCHIVE_SHA256,
    }
    if not all(checks.values()):
        raise ValueError(f"Joint protocol audit failed: {checks}")
    audit = {
        "checks": checks,
        "joint_integrity_sha256": sha256_file(input_root / "JOINT60_INTEGRITY_AUDIT.json"),
        "on_protocol_core_sha256": on_protocol["core_sha256"],
        "off_protocol_core_sha256": off_protocol["core_sha256"],
        "on_integrity_sha256": sha256_file(on_root / "ON40_INTEGRITY_AUDIT.json"),
        "off_integrity_sha256": sha256_file(off_root / "OFF20_INTEGRITY_AUDIT.json"),
        "server_archive_sha256": sha256_file(archive_path),
    }
    return on_root, off_root, audit


def load_initialisations(path: Path) -> dict[int, dict[str, float]]:
    manifest = read_json(path)
    records = {
        int(row["ego_init_id"]): {
            "init_speed_mps": float(row["init_speed"]),
            "start_longitudinal_offset_m": float(row["start_longitudinal_offset"]),
        }
        for row in manifest["records"]
    }
    if not set(PAIRED_INIT_IDS + ON_EXTRA_INIT_IDS).issubset(records):
        raise ValueError("Initialisation manifest does not cover the formal matrix")
    return records


def parse_rollouts(
    root: Path,
    authority: str,
    init_records: dict[int, dict[str, float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    expected_ids = PAIRED_INIT_IDS + (ON_EXTRA_INIT_IDS if authority == "on" else ())
    expected_cells = {
        f"{predictor}__{risk}__assertive__supervisor_{authority}"
        for predictor in PREDICTORS
        for risk in RISKS
    }
    cell_paths = [path for path in root.iterdir() if path.is_dir()]
    if {path.name for path in cell_paths} != expected_cells:
        raise ValueError(f"Unexpected {authority} cell directories")

    for cell in sorted(cell_paths):
        predictor, risk = cell.name.split("__")[:2]
        for init_id in expected_ids:
            init_root = cell / f"ego_init_{init_id}"
            receipt = read_json(init_root / "FORMAL_ROLLOUT_COMPLETE.json")
            if not receipt["execution_complete"]:
                raise ValueError(f"Incomplete formal rollout: {init_root}")

            gate = read_json(init_root / "rollout" / "postcarla_trajectory_gate.json")
            if len(gate["evaluations"]) != 1:
                raise ValueError(f"Unexpected post-CARLA evaluations: {init_root}")
            evaluation = gate["evaluations"][0]
            if len(evaluation["pair_safety"]) != 1 or len(
                evaluation["fixed_geometry_yield_rules"]
            ) != 1:
                raise ValueError(f"Unexpected target count: {init_root}")
            safety = evaluation["pair_safety"][0]
            fixed_yield = evaluation["fixed_geometry_yield_rules"][0]
            if not math.isclose(float(safety["footprint_margin_m"]), 0.25, abs_tol=1e-12):
                raise ValueError(f"Unexpected footprint margin: {init_root}")

            with (init_root / "rollout" / "paper_metrics_summary.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                metric_rows = list(csv.DictReader(handle))
            if len(metric_rows) != 1:
                raise ValueError(f"Expected one metric row: {init_root}")
            metrics = metric_rows[0]

            setup = read_json(only_path(init_root, "smpc_debug_setup.json"))
            implementation = setup["control_implementation"]
            if not (
                implementation["objective_weighting"] == OBJECTIVE_ID
                and implementation["version"] == IMPLEMENTATION_ID
                and implementation["objective_weighting_contract_sha256"] == CONTRACT_SHA256
                and implementation["objective_unweighted_option_available"] is False
            ):
                raise ValueError(f"Invalid weighted-objective setup: {init_root}")

            outcome_reason = str(fixed_yield["outcome_reason"])
            rows.append(
                {
                    "authority": authority,
                    "authority_label": AUTHORITY_LABELS[authority],
                    "predictor": predictor,
                    "predictor_label": PREDICTOR_LABELS[predictor],
                    "risk": risk,
                    "risk_label": RISK_LABELS[risk],
                    "init_id": init_id,
                    **init_records[init_id],
                    "execution_complete": int(bool(receipt["execution_complete"])),
                    "competence_gate_pass": int(bool(receipt["competence_pass"])),
                    "formal_rollout_pass": int(bool(receipt["passed"])),
                    "legacy_target_first_yield": int(bool(receipt["target_first_yield"])),
                    "completion_valid": int(bool(evaluation["completion_valid"])),
                    "fixed_geometry_outcome": outcome_reason,
                    "early_conflict_entry": int(
                        outcome_reason == "ego_entered_before_target_clearance"
                    ),
                    "target_cleared_before_entry": int(
                        outcome_reason == "target_cleared_before_ego_entry"
                    ),
                    "never_entered_fixed_zone": int(
                        outcome_reason == "ego_never_entered_conflict_zone"
                    ),
                    "footprint_collision": int(bool(safety["footprint_collision"])),
                    "completion_time_s": float(metrics["completion_time"]),
                    "min_footprint_separation_m": float(safety["min_footprint_separation_m"]),
                    "min_center_distance_m": float(safety["min_center_distance_m"]),
                    "solver_failure_fraction": float(metrics["solver_failure_frac"]),
                    "average_solve_time_s": float(metrics["average_solve_time"]),
                    "max_abs_lateral_error_m": float(metrics["max_abs_ey_debug"]),
                    "completion_lateral_error_m": float(metrics["completion_ey"]),
                    "postcarla_status": str(evaluation["status"]),
                    "postcarla_errors": " | ".join(evaluation["errors"]),
                }
            )
    return rows


def join_command_path(input_root: Path, rows: list[dict[str, Any]]) -> None:
    with (input_root / "JOINT60_COMMAND_PATH_BY_ROLLOUT.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        command_rows = list(csv.DictReader(handle))
    lookup = {
        (row["authority"], row["predictor"], row["risk"], int(row["init_id"])): row
        for row in command_rows
    }
    if len(lookup) != 60 or len(rows) != 60:
        raise ValueError("Expected 60 unique rollout command-path records")
    integer_fields = (
        "rows",
        "any_request_rows",
        "post_request_rows",
        "post_applied_rows",
        "bypass_request_rows",
        "bypass_applied_rows",
        "solver_attempt_rows",
        "solver_optimal_rows",
        "actual_command_diff_rows",
    )
    fraction_fields = (
        "any_request_frac",
        "post_applied_frac",
        "bypass_applied_frac",
        "solver_optimal_frac",
        "actual_command_diff_frac",
    )
    for row in rows:
        key = (row["authority"], row["predictor"], row["risk"], row["init_id"])
        command = lookup[key]
        for field in integer_fields:
            row[field] = int(command[field])
        for field in fraction_fields:
            row[field] = float(command[field])


def authority_cell_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paired = [row for row in rows if row["init_id"] in PAIRED_INIT_IDS]
    output: list[dict[str, Any]] = []
    continuous = (
        "completion_time_s",
        "min_footprint_separation_m",
        "solver_failure_fraction",
        "average_solve_time_s",
        "max_abs_lateral_error_m",
        "any_request_frac",
        "post_applied_frac",
        "bypass_applied_frac",
        "solver_optimal_frac",
    )
    for authority in AUTHORITIES:
        for predictor in PREDICTORS:
            for risk in RISKS:
                subset = [
                    row
                    for row in paired
                    if row["authority"] == authority
                    and row["predictor"] == predictor
                    and row["risk"] == risk
                ]
                record: dict[str, Any] = {
                    "authority": authority,
                    "authority_label": AUTHORITY_LABELS[authority],
                    "predictor": predictor,
                    "predictor_label": PREDICTOR_LABELS[predictor],
                    "risk": risk,
                    "risk_label": RISK_LABELS[risk],
                    "initialisation_groups": len(subset),
                    "competence_gate_passes": sum(x["competence_gate_pass"] for x in subset),
                    "valid_completions": sum(x["completion_valid"] for x in subset),
                    "early_conflict_entries": sum(x["early_conflict_entry"] for x in subset),
                    "footprint_collisions": sum(x["footprint_collision"] for x in subset),
                }
                for field in continuous:
                    record[f"{field}_mean"] = float(np.mean([x[field] for x in subset]))
                output.append(record)
    return output


AUTHORITY_METRICS = (
    "competence_gate_pass",
    "completion_valid",
    "early_conflict_entry",
    "footprint_collision",
    "completion_time_s",
    "min_footprint_separation_m",
    "solver_failure_fraction",
    "average_solve_time_s",
    "max_abs_lateral_error_m",
    "any_request_frac",
    "post_applied_frac",
    "bypass_applied_frac",
    "solver_optimal_frac",
)


def authority_effects(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (row["authority"], row["predictor"], row["risk"], row["init_id"]): row
        for row in rows
        if row["init_id"] in PAIRED_INIT_IDS
    }
    output: list[dict[str, Any]] = []
    for metric_index, metric in enumerate(AUTHORITY_METRICS):
        group_differences = []
        for init_id in PAIRED_INIT_IDS:
            on_mean = float(
                np.mean(
                    [
                        lookup[("on", predictor, risk, init_id)][metric]
                        for predictor in PREDICTORS
                        for risk in RISKS
                    ]
                )
            )
            off_mean = float(
                np.mean(
                    [
                        lookup[("off", predictor, risk, init_id)][metric]
                        for predictor in PREDICTORS
                        for risk in RISKS
                    ]
                )
            )
            group_differences.append(on_mean - off_mean)
        effect, low, high = bootstrap_mean(group_differences, 2026082700 + metric_index)
        output.append(
            {
                "metric": metric,
                "contrast": "Supervisor authority on minus off",
                "effect": effect,
                "ci_low": low,
                "ci_high": high,
                "exact_two_sided_sign_flip_p": exact_sign_flip_p(group_differences),
                "independent_initialisation_groups": len(PAIRED_INIT_IDS),
                "group_differences": json.dumps(group_differences),
            }
        )
    return output


def off_factor_effects(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (row["predictor"], row["risk"], row["init_id"]): row
        for row in rows
        if row["authority"] == "off"
    }
    metrics = (
        "competence_gate_pass",
        "early_conflict_entry",
        "footprint_collision",
        "completion_time_s",
        "min_footprint_separation_m",
        "solver_failure_fraction",
        "average_solve_time_s",
        "max_abs_lateral_error_m",
    )
    output: list[dict[str, Any]] = []
    index = 0
    for metric in metrics:
        for risk in RISKS:
            values = [
                lookup[("P_star", risk, init_id)][metric]
                - lookup[("B1", risk, init_id)][metric]
                for init_id in PAIRED_INIT_IDS
            ]
            effect, low, high = bootstrap_mean(values, 2026082800 + index)
            output.append(
                {
                    "metric": metric,
                    "contrast_type": "predictor",
                    "contrast": f"Transformer-adapted minus retrained MultiPath | {RISK_LABELS[risk]}",
                    "effect": effect,
                    "ci_low": low,
                    "ci_high": high,
                    "exact_two_sided_sign_flip_p": exact_sign_flip_p(values),
                    "paired_initialisation_groups": len(PAIRED_INIT_IDS),
                }
            )
            index += 1
        for predictor in PREDICTORS:
            values = [
                lookup[(predictor, "adaptive", init_id)][metric]
                - lookup[(predictor, "fixed_medium", init_id)][metric]
                for init_id in PAIRED_INIT_IDS
            ]
            effect, low, high = bootstrap_mean(values, 2026082800 + index)
            output.append(
                {
                    "metric": metric,
                    "contrast_type": "risk",
                    "contrast": f"Adaptive minus fixed medium | {PREDICTOR_LABELS[predictor]}",
                    "effect": effect,
                    "ci_low": low,
                    "ci_high": high,
                    "exact_two_sided_sign_flip_p": exact_sign_flip_p(values),
                    "paired_initialisation_groups": len(PAIRED_INIT_IDS),
                }
            )
            index += 1
    return output


def pooled_authority_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paired = [row for row in rows if row["init_id"] in PAIRED_INIT_IDS]
    output = []
    for authority in AUTHORITIES:
        subset = [row for row in paired if row["authority"] == authority]
        total_steps = sum(row["rows"] for row in subset)
        solver_attempts = sum(row["solver_attempt_rows"] for row in subset)
        output.append(
            {
                "authority": authority,
                "authority_label": AUTHORITY_LABELS[authority],
                "rollouts": len(subset),
                "independent_initialisation_groups": len(PAIRED_INIT_IDS),
                "valid_completions": sum(row["completion_valid"] for row in subset),
                "competence_gate_passes": sum(row["competence_gate_pass"] for row in subset),
                "early_conflict_entries": sum(row["early_conflict_entry"] for row in subset),
                "footprint_collisions": sum(row["footprint_collision"] for row in subset),
                "fixed_zone_never_entered": sum(row["never_entered_fixed_zone"] for row in subset),
                "mean_completion_time_s": float(np.mean([row["completion_time_s"] for row in subset])),
                "mean_min_footprint_separation_m": float(
                    np.mean([row["min_footprint_separation_m"] for row in subset])
                ),
                "mean_solver_failure_fraction": float(
                    np.mean([row["solver_failure_fraction"] for row in subset])
                ),
                "mean_max_abs_lateral_error_m": float(
                    np.mean([row["max_abs_lateral_error_m"] for row in subset])
                ),
                "min_max_abs_lateral_error_m": min(
                    row["max_abs_lateral_error_m"] for row in subset
                ),
                "max_max_abs_lateral_error_m": max(
                    row["max_abs_lateral_error_m"] for row in subset
                ),
                "total_control_steps": total_steps,
                "any_request_rows": sum(row["any_request_rows"] for row in subset),
                "any_request_fraction": sum(row["any_request_rows"] for row in subset)
                / total_steps,
                "post_action_request_rows": sum(row["post_request_rows"] for row in subset),
                "post_action_request_fraction": sum(row["post_request_rows"] for row in subset)
                / total_steps,
                "post_action_applied_rows": sum(row["post_applied_rows"] for row in subset),
                "post_action_applied_fraction": sum(row["post_applied_rows"] for row in subset)
                / total_steps,
                "bypass_request_rows": sum(row["bypass_request_rows"] for row in subset),
                "bypass_request_fraction": sum(row["bypass_request_rows"] for row in subset)
                / total_steps,
                "bypass_applied_rows": sum(row["bypass_applied_rows"] for row in subset),
                "bypass_applied_fraction": sum(row["bypass_applied_rows"] for row in subset)
                / total_steps,
                "solver_attempts": solver_attempts,
                "solver_optimal_rows": sum(row["solver_optimal_rows"] for row in subset),
                "solver_optimal_fraction": sum(row["solver_optimal_rows"] for row in subset)
                / solver_attempts,
                "actual_command_difference_rows": sum(
                    row["actual_command_diff_rows"] for row in subset
                ),
                "actual_command_difference_fraction": sum(
                    row["actual_command_diff_rows"] for row in subset
                )
                / total_steps,
            }
        )
    return output


def posthoc_initialisation_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    off = [row for row in rows if row["authority"] == "off"]
    output = []
    for init_id in PAIRED_INIT_IDS:
        subset = [row for row in off if row["init_id"] == init_id]
        output.append(
            {
                "init_id": init_id,
                "init_speed_mps": subset[0]["init_speed_mps"],
                "start_longitudinal_offset_m": subset[0]["start_longitudinal_offset_m"],
                "factorial_cells": len(subset),
                "early_conflict_entries": sum(row["early_conflict_entry"] for row in subset),
                "footprint_collisions": sum(row["footprint_collision"] for row in subset),
                "competence_gate_passes": sum(row["competence_gate_pass"] for row in subset),
                "mean_solver_failure_fraction": float(
                    np.mean([row["solver_failure_fraction"] for row in subset])
                ),
                "outcome_pattern": (
                    "collision"
                    if any(row["footprint_collision"] for row in subset)
                    else "early_entry"
                    if any(row["early_conflict_entry"] for row in subset)
                    else "no_early_entry"
                ),
            }
        )
    return output


def plot_results(
    pooled: list[dict[str, Any]], initialisations: list[dict[str, Any]], output_dir: Path
) -> list[Path]:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.2,
            "axes.titlesize": 8.4,
            "axes.labelsize": 7.4,
            "xtick.labelsize": 6.8,
            "ytick.labelsize": 6.8,
            "legend.fontsize": 6.6,
            "axes.edgecolor": DARK,
            "axes.linewidth": 0.7,
            "axes.grid": True,
            "grid.color": LIGHT_GREY,
            "grid.linewidth": 0.55,
            "grid.alpha": 0.7,
        }
    )
    by_authority = {row["authority"]: row for row in pooled}
    fig, axes = plt.subplots(1, 2, figsize=(6.85, 2.55), constrained_layout=True)

    ax = axes[0]
    labels = ["Endpoint\ncompletion", "Early conflict\nentry", "Footprint\ncollision"]
    off_values = np.array(
        [
            by_authority["off"]["valid_completions"] / 20,
            by_authority["off"]["early_conflict_entries"] / 20,
            by_authority["off"]["footprint_collisions"] / 20,
        ]
    )
    on_values = np.array(
        [
            by_authority["on"]["valid_completions"] / 20,
            by_authority["on"]["early_conflict_entries"] / 20,
            by_authority["on"]["footprint_collisions"] / 20,
        ]
    )
    x = np.arange(len(labels))
    width = 0.34
    bars_off = ax.bar(x - width / 2, off_values, width, color=GREY, label="Authority off")
    bars_on = ax.bar(x + width / 2, on_values, width, color=BLUE, label="Authority on")
    ax.text(x[0], 1.035, "100%", ha="center", va="bottom", fontsize=6.2)
    for bars, values in ((bars_off, off_values), (bars_on, on_values)):
        for index, (bar, value) in enumerate(zip(bars, values)):
            if index == 0:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.035,
                f"{value:.0%}",
                ha="center",
                va="bottom",
                fontsize=6.2,
            )
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.16)
    ax.set_ylabel("Fraction of paired rollouts")
    ax.set_title("a  Physical outcomes")
    ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.0, 0.96), ncol=1)

    ax = axes[1]
    pattern_style = {
        "collision": (ORANGE, "X", "Footprint collision"),
        "early_entry": (ORANGE, "o", "Early entry, no collision"),
        "no_early_entry": (BLUE, "o", "No early entry"),
    }
    for pattern in ("collision", "early_entry", "no_early_entry"):
        subset = [row for row in initialisations if row["outcome_pattern"] == pattern]
        if not subset:
            continue
        colour, marker, label = pattern_style[pattern]
        ax.scatter(
            [row["start_longitudinal_offset_m"] for row in subset],
            [row["init_speed_mps"] for row in subset],
            s=38,
            marker=marker,
            color=colour,
            edgecolors=DARK if marker == "o" else colour,
            linewidths=0.6,
            label=label,
            zorder=3,
        )
        for row in subset:
            ax.annotate(
                str(row["init_id"]),
                (row["start_longitudinal_offset_m"], row["init_speed_mps"]),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=6.1,
            )
    ax.set_xlabel("Start longitudinal offset (m)")
    ax.set_ylabel("Initial ego speed (m s$^{-1}$)")
    ax.set_title("b  Authority-off initial conditions")
    ax.legend(frameon=False, loc="best", handletextpad=0.4)

    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="x", visible=False)

    outputs = []
    for suffix in ("pdf", "png"):
        path = output_dir / f"figure04_weighted_supervisor_authority.{suffix}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        outputs.append(path)
    plt.close(fig)
    return outputs


def build_report(
    rows: list[dict[str, Any]],
    pooled: list[dict[str, Any]],
    effects: list[dict[str, Any]],
    off_effects: list[dict[str, Any]],
    initialisations: list[dict[str, Any]],
) -> str:
    pooled_by = {row["authority"]: row for row in pooled}
    effect_by = {row["metric"]: row for row in effects}
    off_binary_zero = all(
        math.isclose(row["effect"], 0.0, abs_tol=1e-12)
        for row in off_effects
        if row["metric"] in {"competence_gate_pass", "early_conflict_entry", "footprint_collision"}
    )
    failed_reasons = Counter(
        row["fixed_geometry_outcome"] for row in rows if row["authority"] == "off"
    )
    lines = [
        "# Probability-weighted supervisor-authority analysis",
        "",
        "## Protocol and units",
        "",
        "- 60 unique formal rollouts: 40 authority-on and 20 authority-off.",
        "- The authority contrast uses five paired initialisation groups (126--130) across two predictors and two risk policies.",
        "- Initialisation groups, not control steps or factorial cells, are the independent resampling units.",
        "- Every rollout uses Town05, an assertive target and the same probability-weighted SMPC objective contract.",
        "",
        "## Main authority result",
        "",
        f"- The endpoint completion criterion is reached in {pooled_by['on']['valid_completions']}/20 rollouts with authority on and {pooled_by['off']['valid_completions']}/20 with authority off.",
        f"- The stricter competence gate passes {pooled_by['on']['competence_gate_passes']}/20 versus {pooled_by['off']['competence_gate_passes']}/20.",
        f"- Explicit fixed-geometry early entry occurs in {pooled_by['on']['early_conflict_entries']}/20 versus {pooled_by['off']['early_conflict_entries']}/20.",
        f"- Footprint collision occurs in {pooled_by['on']['footprint_collisions']}/20 versus {pooled_by['off']['footprint_collisions']}/20.",
        f"- Mean raw completion is {pooled_by['on']['mean_completion_time_s']:.4f} s versus {pooled_by['off']['mean_completion_time_s']:.4f} s. The faster off-arm value is not an efficiency gain because 12/20 rollouts enter before target clearance.",
        f"- Mean solver-failure fraction falls from {pooled_by['off']['mean_solver_failure_fraction']:.4f} to {pooled_by['on']['mean_solver_failure_fraction']:.4f}; paired group effect {effect_by['solver_failure_fraction']['effect']:+.4f} (95% cluster bootstrap [{effect_by['solver_failure_fraction']['ci_low']:+.4f}, {effect_by['solver_failure_fraction']['ci_high']:+.4f}]).",
        f"- Mean maximum absolute lateral route error falls from {pooled_by['off']['mean_max_abs_lateral_error_m']:.3f} m (range {pooled_by['off']['min_max_abs_lateral_error_m']:.3f}--{pooled_by['off']['max_max_abs_lateral_error_m']:.3f}) to {pooled_by['on']['mean_max_abs_lateral_error_m']:.3f} m (range {pooled_by['on']['min_max_abs_lateral_error_m']:.3f}--{pooled_by['on']['max_max_abs_lateral_error_m']:.3f}).",
        "",
        "## Mechanism",
        "",
        f"- Authority-on applies post-solver action replacement on {100*pooled_by['on']['post_action_applied_fraction']:.1f}% of control steps and SMPC bypass on {100*pooled_by['on']['bypass_applied_fraction']:.1f}%.",
        f"- Authority-off logs shadow requests on {100*pooled_by['off']['any_request_fraction']:.1f}% of steps, including action requests on {100*pooled_by['off']['post_action_request_fraction']:.1f}%, but applies none by construction.",
        f"- Solver acceptance is {100*pooled_by['on']['solver_optimal_fraction']:.1f}% with authority on and {100*pooled_by['off']['solver_optimal_fraction']:.1f}% with authority off.",
        "",
        "## Moderation and failure pattern",
        "",
        f"- Predictor and risk changes do not alter any binary off-arm outcome within an initialisation group: {off_binary_zero}.",
        "- Initialisations 126 and 128 have the highest initial speeds (9.83 and 9.71 m/s) and show early entry in all four predictor-risk cells without collision.",
        "- Initialisation 127 starts approximately 2.0 m further forward and produces early entry plus footprint collision in all four cells.",
        "- Initialisations 129 and 130 combine moderate speeds with approximately -1.9 m offsets; neither shows early entry or collision, and all four cells pass the competence gate.",
        f"- Fixed-geometry outcomes: {dict(failed_reasons)}.",
        "- This initial-condition pattern is post hoc and descriptive because only five independent groups were run with authority off.",
        "",
        "## Interpretation boundary",
        "",
        "The experiment disables the complete behavioural-authority bundle. It identifies the bundle's causal effect under these five paired initialisations, not the effect of any individual supervisor rule. The off arm still reaches the endpoint completion criterion in every rollout, so the supported claim is improved conflict handling, route retention and solver stability, not that driving is impossible without the supervisor.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--init-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    on_root, off_root, protocol_audit = audit_protocols(args.input_root)
    init_records = load_initialisations(args.init_manifest)
    rows = parse_rollouts(on_root, "on", init_records) + parse_rollouts(
        off_root, "off", init_records
    )
    join_command_path(args.input_root, rows)

    unique_keys = {
        (row["authority"], row["predictor"], row["risk"], row["init_id"])
        for row in rows
    }
    if len(rows) != len(unique_keys) or len(rows) != 60:
        raise ValueError("Missing or duplicate rollout keys")

    cell_rows = authority_cell_summaries(rows)
    effect_rows = authority_effects(rows)
    off_effect_rows = off_factor_effects(rows)
    pooled_rows = pooled_authority_summary(rows)
    initialisation_rows = posthoc_initialisation_summary(rows)
    figures = plot_results(pooled_rows, initialisation_rows, args.output_dir)

    write_csv(args.output_dir / "joint60_rollout_outcomes.csv", rows)
    write_csv(args.output_dir / "paired_authority_cell_summary.csv", cell_rows)
    write_csv(args.output_dir / "paired_authority_effects.csv", effect_rows)
    write_csv(args.output_dir / "authority_off_predictor_risk_effects.csv", off_effect_rows)
    write_csv(args.output_dir / "pooled_authority_summary.csv", pooled_rows)
    write_csv(args.output_dir / "authority_off_initialisation_patterns.csv", initialisation_rows)

    report = build_report(rows, pooled_rows, effect_rows, off_effect_rows, initialisation_rows)
    (args.output_dir / "SUPERVISOR_AUTHORITY_ANALYSIS.md").write_text(report, encoding="utf-8")
    audit = {
        **protocol_audit,
        "status": "pass",
        "rollouts": len(rows),
        "paired_authority_rollouts": sum(row["init_id"] in PAIRED_INIT_IDS for row in rows),
        "unique_rollout_keys": len(unique_keys),
        "figures": [str(path) for path in figures],
        "output_sha256": {
            path.name: sha256_file(path)
            for path in sorted(args.output_dir.iterdir())
            if path.is_file() and path.name != "ANALYSIS_AUDIT.json"
        },
    }
    write_json(args.output_dir / "ANALYSIS_AUDIT.json", audit)
    print(report)


if __name__ == "__main__":
    main()
