#!/usr/bin/env python3
"""Reproducible solver-timing and controller-acceptance audit.

The canonical R3 aggregate treated rule-yield SMPC bypass rows (``optimal=true``,
``solve_time=0``) as successful solves even though the optimizer was not called.
Those frozen numbers are retained only as preliminary legacy evidence.  Final
timing and acceptance claims in this audit are reconstructed from raw JSONL
and use actual attempted solves as their denominator.  The historical
``optimal`` flag means that the controller accepted a CasADi result; it may
include ``SUBOPTIMAL`` and is not interpreted as mathematical optimality or a
proof of optimisation-problem feasibility.

Raw logs are optional for reproducing the preliminary aggregate package.  In
their absence every corrected attempted-solve result is ``not_evaluated`` and
the receipt is non-final.
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
import os
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_R3_ROOT = (
    REPO_ROOT
    / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final"
    / "server_runs/r3_corrected_formal_v3"
)
DEFAULT_MATRIX_AUDIT = DEFAULT_R3_ROOT / "r3_corrected_matrix_audit.json"
DEFAULT_ROLLOUT_OUTCOMES = DEFAULT_R3_ROOT / "analysis/r3_rollout_outcomes.csv"
DEFAULT_SNAPSHOT_FILES_MANIFEST = (
    DEFAULT_R3_ROOT / "r3_corrected_formal_snapshot.tar.gz.files.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT / "docs/paper/generated/supervisor_feedback_v1/02_cost_feasibility"
)

POLICY_ORDER = (
    "adaptive",
    "fixed_aggressive",
    "fixed_medium",
    "fixed_conservative",
)
FIXED_POLICIES = POLICY_ORDER[1:]

DEADLINE_SOURCES = {
    "simulator_control_period_s": (
        "derived as 1 / the unique carla_fps value in r3_rollout_outcomes.csv"
    ),
    "smpc_planning_interval_s": (
        "validated unique ego_effective_vehicle_params_json.dt value across all R3 rollouts"
    ),
    "frozen_runtime_gate_s": (
        "validated unique runtime_gate_limit_s value in r3_corrected_matrix_audit.json"
    ),
}

NONOPTIMAL_ROLLOUT_FIELDS = (
    "legacy_aggregate_status",
    "cell_id",
    "predictor",
    "risk_policy",
    "target_style",
    "ego_init_id",
    "debug_steps",
    "legacy_nonoptimal_steps",
    "legacy_solver_failure_fraction_all_debug_rows",
    "rollout_affected",
    "legacy_conflated_per_rollout_p95_solve_time_s",
    "runtime_gate_limit_s",
    "runtime_gate_passed",
    "raw_validation_status",
)

STEP_CLASSIFICATIONS = (
    "no_solver_telemetry_context",
    "rule_bypass_no_solve",
    "attempted_accepted",
    "attempted_fallback_or_nonaccepted",
)

RAW_STEP_CLASSIFICATION_FIELDS = (
    "cell_id",
    "predictor",
    "risk_policy",
    "target_style",
    "ego_init_id",
    "debug_row_index",
    "step",
    "prediction_valid_any",
    "classification",
    "solver_attempted",
    "solver_logger_accepted",
    "solver_bypass_enabled",
    "solver_bypassed",
    "solver_problem_bypassed",
    "applied_logger_accepted",
    "attempted_solve_time_state",
    "attempted_solve_time_s",
    "return_status",
    "return_status_source",
    "exception_type",
    "exception_repr",
    "solver_risk_mode",
    "solver_risk_mode_source",
    "fallback_present",
    "fallback_schema",
    "fallback_mode",
    "supervisor_action_source",
    "supervisor_action_mode",
)

RAW_SOLVER_SUMMARY_FIELDS = (
    "risk_policy",
    "ego_init_id",
    "rollouts",
    "debug_rows",
    "prediction_valid_context_steps",
    "prediction_invalid_context_steps",
    "no_solver_telemetry_context_steps",
    "rule_bypass_no_solve_steps",
    "attempted_solve_steps",
    "prediction_valid_attempted_solve_steps",
    "prediction_invalid_attempted_solve_steps",
    "prediction_valid_bypass_no_solve_steps",
    "prediction_invalid_bypass_no_solve_steps",
    "attempted_accepted_steps",
    "attempted_fallback_or_nonaccepted_steps",
    "controller_acceptance_rate_attempted_solve",
    "solver_execution_decisions",
    "bypass_fraction_of_solver_execution_decisions",
    "finite_attempted_latency_steps",
    "nonfinite_attempted_latency_steps",
    "attempted_latency_p50_s",
    "attempted_latency_p95_s",
    "attempted_latency_p99_s",
    "independent_unit_warning",
)

RAW_POLICY_SOLVER_SUMMARY_FIELDS = (
    *RAW_SOLVER_SUMMARY_FIELDS,
    "rollouts_with_finite_attempted_latency",
    "mean_per_rollout_attempted_p95_s",
    "median_per_rollout_attempted_p95_s",
)

RAW_ROLLOUT_VALIDATION_FIELDS = (
    "cell_id",
    "predictor",
    "risk_policy",
    "target_style",
    "ego_init_id",
    "debug_steps",
    "prediction_valid_context_steps",
    "prediction_invalid_context_steps",
    "no_solver_telemetry_context_steps",
    "rule_bypass_no_solve_steps",
    "attempted_solve_steps",
    "prediction_valid_attempted_solve_steps",
    "prediction_invalid_attempted_solve_steps",
    "prediction_valid_bypass_no_solve_steps",
    "prediction_invalid_bypass_no_solve_steps",
    "attempted_accepted_steps",
    "attempted_fallback_or_nonaccepted_steps",
    "attempted_controller_acceptance_rate",
    "finite_attempted_solve_times",
    "nonfinite_attempted_solve_times",
    "attempted_latency_p50_s",
    "attempted_latency_p95_s",
    "attempted_latency_p99_s",
    "legacy_nonoptimal_steps_all_debug_rows",
    "legacy_minus_corrected_fallback_or_nonaccepted_steps",
    "legacy_valid_prediction_steps",
    "legacy_finite_valid_prediction_times",
    "legacy_nonfinite_valid_prediction_times",
    "legacy_raw_p95_solve_time_s",
    "legacy_aggregate_p95_solve_time_s",
    "legacy_aggregate_validation_status",
    "classification_validation_status",
)

CORRECTED_COST_PAIR_FIELDS = (
    "contrast",
    "predictor",
    "target_style",
    "ego_init_id",
    "adaptive_attempted_p95_solve_time_s",
    "control_attempted_p95_solve_time_s",
    "adaptive_minus_control_attempted_p95_solve_time_s",
    "adaptive_over_control_ratio",
)

CORRECTED_FAILURE_PAIR_FIELDS = (
    "contrast",
    "predictor",
    "target_style",
    "ego_init_id",
    "adaptive_attempted_fallback_or_nonaccepted_fraction",
    "control_attempted_fallback_or_nonaccepted_fraction",
    "adaptive_minus_control_attempted_fallback_or_nonaccepted_fraction",
    "adaptive_over_control_ratio",
)

FAILURE_EVENT_FIELDS = (
    "cell_id",
    "predictor",
    "risk_policy",
    "target_style",
    "ego_init_id",
    "debug_row_index",
    "step",
    "prediction_valid_any",
    "prediction_valid_json",
    "return_status",
    "return_status_source",
    "exception_type",
    "solver_success_stat",
    "solver_iter_count",
    "yield_phase",
    "supervisor_active",
    "supervisor_action_present",
    "supervisor_action_source",
    "supervisor_action_mode",
    "supervisor_action_json",
    "final_control_telemetry_source",
    "applied_logger_accepted",
    "applied_u0_json",
    "applied_solver_u_control_json",
    "reference_regenerated",
    "reference_restored_global",
    "reference_forced_linearization",
    "reference_skip_reason",
    "solver_risk_mode",
    "solver_risk_mode_source",
    "solver_control_source",
    "fallback_present",
    "fallback_schema",
    "fallback_mode",
    "fallback_mode_source",
    "fallback_v_curr",
    "fallback_v_next_ref",
    "fallback_a_brake",
    "fallback_u_control_json",
    "fallback_v_tp1",
    "applied_solve_time_state",
    "applied_solve_time_s",
    "rollout_completion_valid",
    "rollout_completion_failure",
    "rollout_completion_reason",
    "rollout_completion_duration_s",
    "rollout_yield_outcome_observed",
    "rollout_yield_failure",
    "rollout_yield_outcome_reason",
    "rollout_minimum_footprint_separation_m",
    "rollout_footprint_collision",
    "rollout_native_collision_any",
    "rollout_native_collision_episode_count",
)

AFFECTED_ROLLOUT_OUTCOME_FIELDS = (
    "cell_id",
    "predictor",
    "risk_policy",
    "target_style",
    "ego_init_id",
    "attempted_solve_steps",
    "attempted_fallback_or_nonaccepted_steps",
    "attempted_fallback_or_nonaccepted_fraction",
    "completion_valid",
    "completion_failure",
    "completion_reason",
    "completion_duration_s",
    "yield_outcome_observed",
    "yield_failure",
    "yield_outcome_reason",
    "minimum_footprint_separation_m",
    "footprint_collision",
    "native_collision_any",
    "native_collision_episode_count",
    "interpretation_boundary",
)

FAILURE_TAXONOMY_KEYS = (
    "risk_policy",
    "return_status",
    "return_status_source",
    "exception_type",
    "prediction_valid_any",
    "yield_phase",
    "reference_regenerated",
    "reference_restored_global",
    "reference_forced_linearization",
    "reference_skip_reason",
    "solver_risk_mode",
    "solver_risk_mode_source",
    "solver_control_source",
    "fallback_present",
    "fallback_schema",
    "fallback_mode",
    "fallback_mode_source",
    "supervisor_action_source",
    "supervisor_action_mode",
    "supervisor_active",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def atomic_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def finite_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected numeric {label}, got {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"Expected finite {label}, got {value!r}")
    return number


def integer(value: Any, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected integer {label}, got {value!r}") from exc
    return number


def binary_integer(value: Any, label: str) -> int:
    number = integer(value, label)
    if number not in (0, 1):
        raise ValueError(f"Expected binary {label}, got {value!r}")
    return number


def stable_float(value: float | None) -> str:
    if value is None:
        return ""
    return format(float(value), ".17g")


def quantile(values: Sequence[float], probability: float) -> float:
    """NumPy-default-compatible linear quantile for finite values."""

    if not values:
        raise ValueError("Cannot take a quantile of an empty sequence")
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"Invalid quantile probability: {probability}")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def exact_sign_flip_p(values: Sequence[float]) -> float | None:
    """Exact sign-flip sensitivity value under paired-effect symmetry."""

    clean = [float(value) for value in values if math.isfinite(float(value))]
    if not clean:
        return None
    observed = abs(statistics.mean(clean))
    total = 2 ** len(clean)
    extreme = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(clean)):
        candidate = abs(statistics.mean(sign * value for sign, value in zip(signs, clean)))
        if candidate >= observed - 1e-15:
            extreme += 1
    return extreme / total


def scalar_category(value: Any, missing: str = "__missing__") -> str:
    if value is None:
        return missing
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        return "__nonfinite__"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def prediction_valid_category(value: Any) -> str:
    if value is None:
        return "__missing__"
    if not isinstance(value, list):
        return "__invalid_type__"
    return "true" if any(bool(item) for item in value) else "false"


def rollout_key(row: Mapping[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(row["predictor"]),
        str(row["risk_policy"]),
        str(row["target_style"]),
        integer(row["ego_init_id"], "ego_init_id"),
    )


def load_frozen_rows(
    matrix_audit_path: Path,
    rollout_outcomes_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, float]]:
    matrix = read_json(matrix_audit_path)
    if matrix.get("status") != "pass" or matrix.get("integrity_status") not in (None, "pass"):
        raise ValueError("R3 matrix audit is not integrity-valid")
    evaluations = matrix.get("evaluations")
    if not isinstance(evaluations, list) or not evaluations:
        raise ValueError("R3 matrix audit has no evaluations")

    audit_rows: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for evaluation in evaluations:
        for required in ("cell_id", "predictor", "risk_policy", "target_style", "rollouts"):
            if required not in evaluation:
                raise ValueError(f"Matrix evaluation missing {required}")
        if evaluation["risk_policy"] not in POLICY_ORDER:
            raise ValueError(f"Unknown R3 risk policy: {evaluation['risk_policy']}")
        if not isinstance(evaluation["rollouts"], list):
            raise ValueError(f"Matrix evaluation rollouts are malformed: {evaluation['cell_id']}")
        for raw in evaluation["rollouts"]:
            row = {
                "cell_id": str(evaluation["cell_id"]),
                "predictor": str(evaluation["predictor"]),
                "risk_policy": str(evaluation["risk_policy"]),
                "target_style": str(evaluation["target_style"]),
                "ego_init_id": integer(raw.get("ego_init_id"), "matrix ego_init_id"),
                "debug_steps": integer(raw.get("debug_steps"), "debug_steps"),
                "valid_prediction_steps": integer(
                    raw.get("valid_prediction_steps"), "valid_prediction_steps"
                ),
                "p95_solve_time_s": finite_float(
                    raw.get("p95_solve_time_s"), "p95_solve_time_s"
                ),
                "runtime_gate_limit_s": finite_float(
                    raw.get("runtime_gate_limit_s"), "runtime_gate_limit_s"
                ),
                "runtime_gate_passed": bool(raw.get("runtime_gate_passed")),
            }
            key = rollout_key(row)
            if key in audit_rows:
                raise ValueError(f"Duplicate matrix rollout key: {key}")
            audit_rows[key] = row

    expected = integer(matrix.get("observed_rollouts"), "matrix observed_rollouts")
    if len(audit_rows) != expected:
        raise ValueError(f"Matrix rows {len(audit_rows)} != observed_rollouts {expected}")

    # Reuse the canonical R3 analysis receipt when this is the frozen repository
    # package.  Synthetic/unit-test inputs need not fabricate a sidecar, but a
    # present sidecar is always authoritative and must validate exactly.
    analysis_receipt_path = rollout_outcomes_path.parent / "R3_ANALYSIS_COMPLETE.json"
    if analysis_receipt_path.is_file():
        analysis_receipt = read_json(analysis_receipt_path)
        if analysis_receipt.get("status") != "pass":
            raise ValueError("R3 analysis receipt is not pass")
        expected_rows = (analysis_receipt.get("formal_table_row_counts") or {}).get(
            rollout_outcomes_path.name
        )
        expected_hash = (analysis_receipt.get("formal_table_sha256") or {}).get(
            rollout_outcomes_path.name
        )
        if expected_rows != expected:
            raise ValueError(
                f"R3 analysis receipt row count {expected_rows} != matrix count {expected}"
            )
        if expected_hash != sha256(rollout_outcomes_path):
            raise ValueError("R3 rollout-outcomes hash does not match analysis receipt")

    data_receipt_path = matrix_audit_path.parent / "R3_DATA_COMPLETE.json"
    if data_receipt_path.is_file():
        data_receipt = read_json(data_receipt_path)
        if data_receipt.get("status") != "pass":
            raise ValueError("R3 data-complete receipt is not pass")
        if data_receipt.get("matrix_audit_sha256") != sha256(matrix_audit_path):
            raise ValueError("R3 matrix-audit hash does not match data-complete receipt")
        if analysis_receipt_path.is_file() and data_receipt.get(
            "analysis_complete_sha256"
        ) != sha256(analysis_receipt_path):
            raise ValueError("R3 analysis-receipt hash does not match data-complete receipt")

    outcome_rows = read_csv(rollout_outcomes_path)
    outcomes: dict[tuple[str, str, str, int], dict[str, str]] = {}
    for row in outcome_rows:
        for required in (
            "cell_id",
            "predictor",
            "risk_policy",
            "target_style",
            "ego_init_id",
            "solver_failure_fraction",
            "carla_fps",
            "ego_effective_vehicle_params_json",
            "completion_valid",
            "completion_failure",
            "ego_route_completion_duration_s",
            "fixed_geometry_yield_outcome_observed",
            "fixed_geometry_yield_failure",
            "minimum_footprint_separation_m",
            "footprint_collision",
            "native_collision_any",
            "native_collision_episode_count",
            "audit_scientific_outcomes_json",
        ):
            if required not in row:
                raise ValueError(f"R3 rollout outcome missing {required}")
        key = rollout_key(row)
        if key in outcomes:
            raise ValueError(f"Duplicate rollout outcome key: {key}")
        outcomes[key] = row
    if set(outcomes) != set(audit_rows):
        missing = sorted(set(audit_rows) - set(outcomes))
        extra = sorted(set(outcomes) - set(audit_rows))
        raise ValueError(f"Matrix/outcome rollout-key mismatch: missing={missing}, extra={extra}")

    joined: list[dict[str, Any]] = []
    for key in sorted(
        audit_rows,
        key=lambda item: (
            POLICY_ORDER.index(item[1]),
            item[0],
            item[2],
            item[3],
        ),
    ):
        audit = audit_rows[key]
        outcome = outcomes[key]
        if outcome["cell_id"] != audit["cell_id"]:
            raise ValueError(f"Cell ID mismatch for {key}")
        fraction = finite_float(outcome["solver_failure_fraction"], "solver_failure_fraction")
        if not 0.0 <= fraction <= 1.0:
            raise ValueError(f"Invalid solver_failure_fraction for {key}: {fraction}")
        inferred_count = int(round(fraction * audit["debug_steps"]))
        reconstructed = inferred_count / audit["debug_steps"] if audit["debug_steps"] else 0.0
        if not math.isclose(fraction, reconstructed, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(
                f"Cannot reconstruct integer non-optimal count for {key}: "
                f"fraction={fraction}, debug_steps={audit['debug_steps']}"
            )
        try:
            ego_parameters = json.loads(outcome["ego_effective_vehicle_params_json"])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid ego_effective_vehicle_params_json for {key}") from exc
        if not isinstance(ego_parameters, dict) or "dt" not in ego_parameters:
            raise ValueError(f"Missing frozen ego SMPC dt for {key}")
        smpc_dt = finite_float(ego_parameters["dt"], "ego effective SMPC dt")
        if smpc_dt <= 0.0:
            raise ValueError(f"Non-positive frozen ego SMPC dt for {key}: {smpc_dt}")
        completion_valid = binary_integer(
            outcome["completion_valid"], "completion_valid"
        )
        completion_failure = binary_integer(
            outcome["completion_failure"], "completion_failure"
        )
        completion_duration = optional_finite_float(
            outcome["ego_route_completion_duration_s"]
        )
        if completion_valid and completion_duration is None:
            raise ValueError(f"Valid completion lacks a finite duration for {key}")
        yield_outcome_observed = binary_integer(
            outcome["fixed_geometry_yield_outcome_observed"],
            "fixed_geometry_yield_outcome_observed",
        )
        yield_failure = binary_integer(
            outcome["fixed_geometry_yield_failure"],
            "fixed_geometry_yield_failure",
        )
        minimum_separation = finite_float(
            outcome["minimum_footprint_separation_m"],
            "minimum_footprint_separation_m",
        )
        footprint_collision = binary_integer(
            outcome["footprint_collision"], "footprint_collision"
        )
        native_collision_any = binary_integer(
            outcome["native_collision_any"], "native_collision_any"
        )
        native_collision_episode_count = integer(
            outcome["native_collision_episode_count"],
            "native_collision_episode_count",
        )
        if native_collision_episode_count < 0:
            raise ValueError(f"Negative native collision episode count for {key}")
        if native_collision_any != int(native_collision_episode_count > 0):
            raise ValueError(f"Native collision flag/count disagree for {key}")
        try:
            scientific_outcomes = json.loads(outcome["audit_scientific_outcomes_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid audit_scientific_outcomes_json for {key}") from exc
        if not isinstance(scientific_outcomes, dict):
            raise ValueError(f"Scientific outcomes are not an object for {key}")
        for required in (
            "completion_reason",
            "completion_success",
            "fixed_geometry_yield_outcome_reason",
            "fixed_geometry_yield_success",
            "footprint_collision",
            "native_collision_contact_episodes",
        ):
            if required not in scientific_outcomes:
                raise ValueError(f"Scientific outcomes missing {required} for {key}")
        if bool(scientific_outcomes["completion_success"]) != bool(
            completion_valid and not completion_failure
        ):
            raise ValueError(f"Completion outcome telemetry disagrees for {key}")
        if yield_outcome_observed and bool(
            scientific_outcomes["fixed_geometry_yield_success"]
        ) != bool(not yield_failure):
            raise ValueError(f"Yield outcome telemetry disagrees for {key}")
        if bool(scientific_outcomes["footprint_collision"]) != bool(
            footprint_collision
        ):
            raise ValueError(f"Footprint collision telemetry disagrees for {key}")
        if integer(
            scientific_outcomes["native_collision_contact_episodes"],
            "native_collision_contact_episodes",
        ) != native_collision_episode_count:
            raise ValueError(f"Native collision telemetry disagrees for {key}")
        joined.append(
            {
                **audit,
                "solver_failure_fraction": fraction,
                "nonoptimal_steps": inferred_count,
                "carla_fps": finite_float(outcome["carla_fps"], "carla_fps"),
                "smpc_dt": smpc_dt,
                "completion_valid": completion_valid,
                "completion_failure": completion_failure,
                "completion_reason": str(scientific_outcomes["completion_reason"]),
                "completion_duration_s": completion_duration,
                "yield_outcome_observed": yield_outcome_observed,
                "yield_failure": yield_failure,
                "yield_outcome_reason": str(
                    scientific_outcomes["fixed_geometry_yield_outcome_reason"]
                ),
                "minimum_footprint_separation_m": minimum_separation,
                "footprint_collision": footprint_collision,
                "native_collision_any": native_collision_any,
                "native_collision_episode_count": native_collision_episode_count,
            }
        )

    fps_values = {row["carla_fps"] for row in joined}
    smpc_dt_values = {row["smpc_dt"] for row in joined}
    gate_values = {row["runtime_gate_limit_s"] for row in joined}
    if len(fps_values) != 1:
        raise ValueError(f"Expected one CARLA FPS, got {sorted(fps_values)}")
    if len(gate_values) != 1:
        raise ValueError(f"Expected one runtime gate, got {sorted(gate_values)}")
    if len(smpc_dt_values) != 1:
        raise ValueError(f"Expected one frozen ego SMPC dt, got {sorted(smpc_dt_values)}")
    deadlines = {
        "simulator_control_period_s": 1.0 / next(iter(fps_values)),
        "smpc_planning_interval_s": next(iter(smpc_dt_values)),
        "frozen_runtime_gate_s": next(iter(gate_values)),
    }
    return matrix, joined, deadlines


def validate_pairing(rows: Sequence[Mapping[str, Any]]) -> None:
    lookup = {rollout_key(row): row for row in rows}
    base_keys = {
        (str(row["predictor"]), str(row["target_style"]), int(row["ego_init_id"]))
        for row in rows
    }
    for predictor, style, init_id in sorted(base_keys):
        missing = [
            policy
            for policy in POLICY_ORDER
            if (predictor, policy, style, init_id) not in lookup
        ]
        if missing:
            raise ValueError(
                f"Incomplete adaptive/fixed pairing for {(predictor, style, init_id)}: {missing}"
            )


def summarize_policy_costs(
    rows: Sequence[dict[str, Any]],
    deadlines: Mapping[str, float],
    raw_policy: Mapping[str, Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for policy in POLICY_ORDER:
        policy_rows = [row for row in rows if row["risk_policy"] == policy]
        if not policy_rows:
            raise ValueError(f"No R3 rows for {policy}")
        p95s = [float(row["p95_solve_time_s"]) for row in policy_rows]
        raw = raw_policy.get(policy) if raw_policy is not None else None
        output.append(
            {
                "risk_policy": policy,
                "rollouts": len(policy_rows),
                "legacy_aggregate_status": "preliminary_legacy_conflated",
                "legacy_conflated_per_rollout_p95_s_mean": stable_float(
                    statistics.mean(p95s)
                ),
                "legacy_conflated_per_rollout_p95_s_median": stable_float(
                    statistics.median(p95s)
                ),
                "legacy_conflated_per_rollout_p95_s_min": stable_float(min(p95s)),
                "legacy_conflated_per_rollout_p95_s_max": stable_float(max(p95s)),
                "legacy_metric_scope": (
                    "valid-prediction finite applied.solve_time, including 0-second "
                    "rule-bypass no-solve markers"
                ),
                "simulator_control_period_s": stable_float(
                    deadlines["simulator_control_period_s"]
                ),
                "legacy_rollouts_p95_above_control_period": sum(
                    value > deadlines["simulator_control_period_s"] for value in p95s
                ),
                "smpc_planning_interval_s": stable_float(
                    deadlines["smpc_planning_interval_s"]
                ),
                "legacy_rollouts_p95_above_smpc_planning_interval": sum(
                    value > deadlines["smpc_planning_interval_s"] for value in p95s
                ),
                "frozen_runtime_gate_s": stable_float(deadlines["frozen_runtime_gate_s"]),
                "legacy_rollouts_p95_above_frozen_gate": sum(
                    value > deadlines["frozen_runtime_gate_s"] for value in p95s
                ),
                "corrected_attempted_solve_status": (
                    "pass" if raw is not None else "not_evaluated"
                ),
                "attempted_solve_steps": (
                    raw["attempted_solve_steps"] if raw is not None else ""
                ),
                "attempted_accepted_steps": (
                    raw["attempted_accepted_steps"] if raw is not None else ""
                ),
                "attempted_fallback_or_nonaccepted_steps": (
                    raw["attempted_fallback_or_nonaccepted_steps"] if raw is not None else ""
                ),
                "attempted_controller_acceptance_rate": (
                    raw["controller_acceptance_rate_attempted_solve"] if raw is not None else ""
                ),
                "rule_bypass_no_solve_steps": (
                    raw["rule_bypass_no_solve_steps"] if raw is not None else ""
                ),
                "solver_execution_decisions": (
                    raw["solver_execution_decisions"] if raw is not None else ""
                ),
                "bypass_fraction_of_solver_execution_decisions": (
                    raw["bypass_fraction_of_solver_execution_decisions"]
                    if raw is not None
                    else ""
                ),
                "finite_attempted_latency_steps": (
                    raw["finite_attempted_latency_steps"] if raw is not None else ""
                ),
                "nonfinite_attempted_latency_steps": (
                    raw["nonfinite_attempted_latency_steps"] if raw is not None else ""
                ),
                "attempted_latency_p50_s": (
                    raw["attempted_latency_p50_s"] if raw is not None else ""
                ),
                "attempted_latency_p95_s": (
                    raw["attempted_latency_p95_s"] if raw is not None else ""
                ),
                "attempted_latency_p99_s": (
                    raw["attempted_latency_p99_s"] if raw is not None else ""
                ),
                "mean_per_rollout_attempted_p95_s": (
                    raw["mean_per_rollout_attempted_p95_s"]
                    if raw is not None
                    else ""
                ),
            }
        )
    return output


def build_pair_rows(
    rows: Sequence[dict[str, Any]],
    value_field: str,
    treatment_label: str,
) -> list[dict[str, Any]]:
    lookup = {rollout_key(row): row for row in rows}
    pair_rows: list[dict[str, Any]] = []
    bases = sorted(
        {
            (row["predictor"], row["target_style"], int(row["ego_init_id"]))
            for row in rows
        }
    )
    for control in FIXED_POLICIES:
        for predictor, style, init_id in bases:
            adaptive = lookup[(predictor, "adaptive", style, init_id)]
            fixed = lookup[(predictor, control, style, init_id)]
            treatment = float(adaptive[value_field])
            comparator = float(fixed[value_field])
            pair_rows.append(
                {
                    "contrast": f"adaptive_minus_{control}",
                    "predictor": predictor,
                    "target_style": style,
                    "ego_init_id": init_id,
                    f"adaptive_{treatment_label}": stable_float(treatment),
                    f"control_{treatment_label}": stable_float(comparator),
                    f"adaptive_minus_control_{treatment_label}": stable_float(
                        treatment - comparator
                    ),
                    "adaptive_over_control_ratio": (
                        stable_float(treatment / comparator) if comparator != 0.0 else ""
                    ),
                }
            )
    return pair_rows


def summarize_pair_rows(
    pair_rows: Sequence[Mapping[str, Any]],
    effect_field: str,
    effect_unit: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for control in FIXED_POLICIES:
        contrast = f"adaptive_minus_{control}"
        selected = [row for row in pair_rows if row["contrast"] == contrast]
        effects = [finite_float(row[effect_field], effect_field) for row in selected]
        by_init: dict[int, list[float]] = defaultdict(list)
        for row, effect in zip(selected, effects):
            by_init[integer(row["ego_init_id"], "paired ego_init_id")].append(effect)
        cluster_effects = [statistics.mean(by_init[key]) for key in sorted(by_init)]
        output.append(
            {
                "contrast": contrast,
                "metric": effect_field,
                "unit": effect_unit,
                "paired_rollouts": len(effects),
                "mean_effect": stable_float(statistics.mean(effects)),
                "median_effect": stable_float(statistics.median(effects)),
                "minimum_effect": stable_float(min(effects)),
                "maximum_effect": stable_float(max(effects)),
                "positive_pairs": sum(value > 0.0 for value in effects),
                "zero_pairs": sum(value == 0.0 for value in effects),
                "negative_pairs": sum(value < 0.0 for value in effects),
                "independent_init_clusters": len(cluster_effects),
                "cluster_mean_effect": stable_float(statistics.mean(cluster_effects)),
                "cluster_minimum_effect": stable_float(min(cluster_effects)),
                "cluster_maximum_effect": stable_float(max(cluster_effects)),
                "cluster_positive": sum(value > 0.0 for value in cluster_effects),
                "cluster_zero": sum(value == 0.0 for value in cluster_effects),
                "cluster_negative": sum(value < 0.0 for value in cluster_effects),
                "cluster_effects_json": json.dumps(
                    {str(key): by_init[key] and statistics.mean(by_init[key]) for key in sorted(by_init)},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "two_sided_exact_sign_flip_p_descriptive": stable_float(
                    exact_sign_flip_p(cluster_effects)
                ),
                "inference_scope": "descriptive post-hoc supervisor-feedback audit",
            }
        )
    return output


def summarize_nonoptimal_policy(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for policy in POLICY_ORDER:
        selected = [row for row in rows if row["risk_policy"] == policy]
        fractions = [float(row["solver_failure_fraction"]) for row in selected]
        debug_steps = sum(int(row["debug_steps"]) for row in selected)
        failures = sum(int(row["nonoptimal_steps"]) for row in selected)
        output.append(
            {
                "risk_policy": policy,
                "legacy_aggregate_status": "preliminary_legacy_conflated",
                "rollouts": len(selected),
                "affected_rollouts": sum(int(row["nonoptimal_steps"]) > 0 for row in selected),
                "debug_steps": debug_steps,
                "nonoptimal_steps": failures,
                "pooled_step_fraction_descriptive": stable_float(
                    failures / debug_steps if debug_steps else 0.0
                ),
                "mean_per_rollout_failure_fraction": stable_float(statistics.mean(fractions)),
                "median_per_rollout_failure_fraction": stable_float(
                    statistics.median(fractions)
                ),
                "independent_unit_warning": (
                    "legacy fraction divides by all debug rows and includes bypass/no-solve "
                    "rows in the denominator; use factual attempted-solve timing and "
                    "controller acceptance/fallback for final claims"
                ),
            }
        )
    return output


def manifest_hash_lookup(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = read_json(path)
    if payload.get("status") != "pass" or not isinstance(payload.get("files"), list):
        raise ValueError(f"Raw snapshot files manifest is not valid: {path}")
    lookup: dict[str, str] = {}
    for row in payload["files"]:
        if not isinstance(row, dict) or "path" not in row or "sha256" not in row:
            raise ValueError(f"Malformed raw snapshot manifest row: {row!r}")
        lookup[str(row["path"])] = str(row["sha256"])
    return lookup


def find_raw_debug_files(
    raw_root: Path,
    rows: Sequence[dict[str, Any]],
) -> tuple[dict[tuple[str, int], tuple[Path, str]], int]:
    expected_cells = {str(row["cell_id"]) for row in rows}
    discovered: dict[tuple[str, int], tuple[Path, str]] = {}
    ignored = 0
    init_pattern = re.compile(r"_ego_init_(\d+)_")
    for path in sorted(raw_root.rglob("smpc_debug_steps.jsonl")):
        matching_parts = [part for part in path.parts if part in expected_cells]
        if len(matching_parts) != 1:
            ignored += 1
            continue
        cell_id = matching_parts[0]
        match = init_pattern.search(str(path.parent))
        if match is None:
            raise ValueError(f"Cannot identify ego init from raw debug path: {path}")
        init_id = int(match.group(1))
        key = (cell_id, init_id)
        cell_index = path.parts.index(cell_id)
        canonical_relative = Path(*path.parts[cell_index:]).as_posix()
        if key in discovered:
            raise ValueError(f"Duplicate canonical raw debug file for {key}")
        discovered[key] = (path, canonical_relative)

    expected = {(str(row["cell_id"]), int(row["ego_init_id"])) for row in rows}
    missing = sorted(expected - set(discovered))
    extra = sorted(set(discovered) - expected)
    if missing or extra:
        raise ValueError(
            f"Extracted raw snapshot is incomplete or has unexpected canonical logs: "
            f"missing={missing}, extra={extra}"
        )
    return discovered, ignored


def solver_return_status(debug: Mapping[str, Any]) -> tuple[Any, str]:
    if debug.get("return_status") is not None:
        return debug.get("return_status"), "solver.debug.return_status"
    stats = debug.get("stats")
    if isinstance(stats, dict) and stats.get("return_status") is not None:
        return stats.get("return_status"), "solver.debug.stats.return_status"
    return None, "__missing__"


def first_non_null_with_source(
    candidates: Sequence[tuple[str, Any]],
) -> tuple[Any, str]:
    """Return the first recorded value and its literal JSON telemetry path."""

    for source, value in candidates:
        if value is not None:
            return value, source
    return None, "__missing__"


def solver_risk_mode_record(
    debug_row: Mapping[str, Any],
    solver: Mapping[str, Any],
    solver_debug: Mapping[str, Any],
) -> tuple[Any, str]:
    """Read the R3 risk-mode telemetry without assuming a convenience field.

    The corrected R3 implementation records this primarily under ``risk``.  A
    solver-level value exists on bypassed rows, while older/debug variants may
    retain it inside ``solver.debug``.  Keeping the source path prevents these
    schemas from being silently conflated.
    """

    risk = debug_row.get("risk")
    risk = risk if isinstance(risk, dict) else {}
    adaptive = risk.get("adaptive")
    adaptive = adaptive if isinstance(adaptive, dict) else {}
    return first_non_null_with_source(
        (
            ("risk.solver_risk_mode", risk.get("solver_risk_mode")),
            ("solver.solver_risk_mode", solver.get("solver_risk_mode")),
            ("solver.debug.solver_risk_mode", solver_debug.get("solver_risk_mode")),
            ("risk.adaptive.solver_risk_mode", adaptive.get("solver_risk_mode")),
        )
    )


def fallback_record(
    solver_debug: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, str, Any, str]:
    """Return exact fallback telemetry plus a schema label.

    Closed-loop R3 fallback records do *not* contain a ``mode`` convenience
    field.  They contain the brake/hold branch inputs and output explicitly.
    We therefore preserve ``mode`` as missing and label only the observed field
    schema; no unavailable branch decision is reconstructed post hoc.
    """

    fallback = solver_debug.get("fallback")
    if not isinstance(fallback, dict):
        return None, "__not_applicable__", None, "__not_applicable__"
    mode = fallback.get("mode")
    if mode is not None:
        return fallback, "explicit_mode_field", mode, "solver.debug.fallback.mode"
    closed_loop_fields = {
        "v_curr",
        "v_next_ref",
        "u_ref_val",
        "a_brake",
        "u_control",
        "v_tp1",
    }
    schema = (
        "closed_loop_brake_or_hold_fields"
        if closed_loop_fields.issubset(fallback)
        else "unclassified_recorded_fields"
    )
    return fallback, schema, None, "__not_recorded__"


def supervisor_action_record(
    yield_status: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, str, Any]:
    """Resolve the literal supervisor action record used by corrected R3."""

    direct = yield_status.get("applied")
    direct = direct if isinstance(direct, dict) else None
    recovery = yield_status.get("recovery")
    recovery = recovery if isinstance(recovery, dict) else {}
    recovery_applied = recovery.get("applied")
    recovery_applied = recovery_applied if isinstance(recovery_applied, dict) else None
    if direct is not None and recovery_applied is not None:
        raise ValueError(
            "Ambiguous supervisor telemetry: both yield_stop_supervisor.applied "
            "and yield_stop_supervisor.recovery.applied are populated"
        )
    if direct is not None:
        return direct, "yield_stop_supervisor.applied", direct.get("mode")
    if recovery_applied is not None:
        return (
            recovery_applied,
            "yield_stop_supervisor.recovery.applied",
            recovery_applied.get("mode"),
        )
    return None, "__none_recorded__", None


def optional_finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def classify_solver_step(
    debug_row: Mapping[str, Any],
    *,
    key: tuple[str, int],
    row_index: int,
) -> dict[str, Any]:
    """Classify one raw decision without equating bypass with a solve attempt."""

    prediction_state = prediction_valid_category(debug_row.get("prediction_valid"))
    if prediction_state not in {"true", "false"}:
        raise ValueError(
            f"Malformed prediction_valid telemetry for {key}, row {row_index}: "
            f"{prediction_state}"
        )
    solver_value = debug_row.get("solver")
    applied_value = debug_row.get("applied")
    solver_problem_value = debug_row.get("solver_problem")
    solver_bypass_value = debug_row.get("solver_bypass")
    explicit_no_attempt = (
        solver_value in (None, {})
        and applied_value in (None, {})
        and solver_problem_value in (None, {})
        and solver_bypass_value in (None, {})
    )
    if explicit_no_attempt:
        solver_bypass = (
            solver_bypass_value if isinstance(solver_bypass_value, dict) else {}
        )
        return {
            # This row is outside the solver-execution denominator.  Its
            # prediction-validity flag is context, not the reason we infer that
            # no solve occurred; the absence of solver/problem/applied telemetry
            # is the decisive evidence.
            "classification": "no_solver_telemetry_context",
            "prediction_state": prediction_state,
            "attempted": False,
            "accepted": None,
            "solve_time": None,
            "solver": {},
            "solver_debug": {},
            "applied": {},
            "solver_bypass": solver_bypass,
            "solver_problem": {},
        }

    solver = solver_value
    if not isinstance(solver, dict):
        raise ValueError(f"Raw solver telemetry missing for {key}, row {row_index}")
    solver_bypass = debug_row.get("solver_bypass")
    if not isinstance(solver_bypass, dict) or not isinstance(
        solver_bypass.get("enabled"), bool
    ):
        raise ValueError(
            f"solver_bypass.enabled must be a recorded boolean for {key}, row {row_index}"
        )
    solver_problem = debug_row.get("solver_problem")
    solver_problem = solver_problem if isinstance(solver_problem, dict) else {}
    applied = debug_row.get("applied")
    applied = applied if isinstance(applied, dict) else {}
    solver_debug = solver.get("debug")
    solver_debug = solver_debug if isinstance(solver_debug, dict) else {}

    if solver_bypass["enabled"]:
        required = {
            "solver.bypassed": solver.get("bypassed"),
            "solver_problem.bypassed": solver_problem.get("bypassed"),
            "solver.optimal": solver.get("optimal"),
            "applied.is_opt": applied.get("is_opt"),
        }
        if any(value is not True for value in required.values()):
            raise ValueError(
                f"Inconsistent rule-bypass telemetry for {key}, row {row_index}: {required}"
            )
        solver_time = optional_finite_float(solver.get("solve_time"))
        applied_time = optional_finite_float(applied.get("solve_time"))
        if solver_time != 0.0 or applied_time != 0.0:
            raise ValueError(
                f"Rule bypass must retain its recorded zero-time no-solve marker for "
                f"{key}, row {row_index}"
            )
        return {
            "classification": "rule_bypass_no_solve",
            "prediction_state": prediction_state,
            "attempted": False,
            "accepted": None,
            "solve_time": None,
            "solver": solver,
            "solver_debug": solver_debug,
            "applied": applied,
            "solver_bypass": solver_bypass,
            "solver_problem": solver_problem,
        }

    if solver.get("bypassed") is True or solver_problem.get("bypassed") is True:
        raise ValueError(
            f"Bypass markers disagree with solver_bypass.enabled for {key}, row {row_index}"
        )
    if not solver_problem:
        raise ValueError(f"solver_problem missing for attempted solve {key}, row {row_index}")

    top_exception = solver.get("exception")
    debug_exception = solver_debug.get("exception")
    has_exception = top_exception is not None or debug_exception is not None
    # ``solver.optimal`` is a historical logger name.  The controller wrapper
    # sets it to true for a normal solve *and* for CasADi ``SUBOPTIMAL`` when it
    # elects to execute the debug solution, so the scientifically valid label
    # here is controller-accepted rather than mathematically optimal/feasible.
    accepted_value = solver.get("optimal")
    if has_exception:
        if accepted_value not in (None, False):
            raise ValueError(
                f"Exception attempt cannot be controller-accepted for {key}, row {row_index}"
            )
        accepted = False
    else:
        if not isinstance(accepted_value, bool):
            raise ValueError(
                f"historical solver.optimal acceptance flag must be boolean for "
                f"attempted solve {key}, row {row_index}"
            )
        if not solver_debug:
            raise ValueError(
                f"solver.debug missing for attempted solve {key}, row {row_index}"
            )
        accepted = accepted_value

    if applied:
        applied_accepted = applied.get("is_opt")
        if not isinstance(applied_accepted, bool) or applied_accepted != accepted:
            raise ValueError(
                f"historical applied.is_opt acceptance flag mismatch for attempted "
                f"solve {key}, row {row_index}"
            )
    elif not has_exception:
        raise ValueError(f"applied telemetry missing for attempted solve {key}, row {row_index}")

    solver_time = optional_finite_float(solver.get("solve_time"))
    applied_time = optional_finite_float(applied.get("solve_time"))
    if solver_time is not None and applied_time is not None and not math.isclose(
        solver_time, applied_time, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ValueError(f"solver/applied solve-time mismatch for {key}, row {row_index}")
    solve_time = applied_time if applied_time is not None else solver_time
    return {
        "classification": (
            "attempted_accepted"
            if accepted
            else "attempted_fallback_or_nonaccepted"
        ),
        "prediction_state": prediction_state,
        "attempted": True,
        "accepted": accepted,
        "solve_time": solve_time,
        "solver": solver,
        "solver_debug": solver_debug,
        "applied": applied,
        "solver_bypass": solver_bypass,
        "solver_problem": solver_problem,
    }


def raw_step_context(
    debug_row: Mapping[str, Any], classified: Mapping[str, Any]
) -> dict[str, Any]:
    solver = classified["solver"]
    solver_debug = classified["solver_debug"]
    applied = classified["applied"]
    return_status, return_status_source = solver_return_status(solver_debug)
    yield_status = debug_row.get("yield_stop_supervisor")
    yield_status = yield_status if isinstance(yield_status, dict) else {}
    reference = debug_row.get("reference")
    reference = reference if isinstance(reference, dict) else {}
    reference_status = reference.get("status")
    reference_status = reference_status if isinstance(reference_status, dict) else {}
    fallback, fallback_schema, fallback_mode, fallback_mode_source = fallback_record(
        solver_debug
    )
    solver_risk_mode, solver_risk_mode_source = solver_risk_mode_record(
        debug_row, solver, solver_debug
    )
    supervisor_action, supervisor_action_source, supervisor_action_mode = (
        supervisor_action_record(yield_status)
    )
    stats = solver_debug.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    solver_control_source = (
        "solver.debug.fallback.u_control"
        if fallback is not None and fallback.get("u_control") is not None
        else (
            "solver.u_control"
            if solver.get("u_control") is not None
            else (
                "applied.u_control"
                if applied.get("u_control") is not None
                else "__missing__"
            )
        )
    )
    exception_repr, exception_source = first_non_null_with_source(
        (
            ("solver.debug.exception", solver_debug.get("exception")),
            ("solver.exception", solver.get("exception")),
        )
    )
    exception_type = solver_debug.get("exception_type")
    if exception_type is None and exception_repr is not None:
        exception_type = "__top_level_solver_exception_type_not_recorded__"
    return {
        "return_status": return_status,
        "return_status_source": return_status_source,
        "exception_type": exception_type,
        "exception_repr": exception_repr,
        "exception_source": exception_source,
        "yield_status": yield_status,
        "reference_status": reference_status,
        "fallback": fallback,
        "fallback_schema": fallback_schema,
        "fallback_mode": fallback_mode,
        "fallback_mode_source": fallback_mode_source,
        "solver_risk_mode": solver_risk_mode,
        "solver_risk_mode_source": solver_risk_mode_source,
        "supervisor_action": supervisor_action,
        "supervisor_action_source": supervisor_action_source,
        "supervisor_action_mode": supervisor_action_mode,
        "solver_control_source": solver_control_source,
        "solver_stats": stats,
    }


def raw_solver_group_row(
    policy: str,
    init_id: int | str,
    stats: Mapping[str, Any],
) -> dict[str, Any]:
    counts = stats["counts"]
    times = stats["latencies"]
    attempted = counts["attempted_accepted"] + counts["attempted_fallback_or_nonaccepted"]
    bypass = counts["rule_bypass_no_solve"]
    execution_decisions = attempted + bypass
    prediction_context = stats["prediction_context"]
    execution_by_prediction = stats["execution_by_prediction"]
    return {
        "risk_policy": policy,
        "ego_init_id": init_id,
        "rollouts": len(stats["rollouts"]),
        "debug_rows": sum(counts[name] for name in STEP_CLASSIFICATIONS),
        "prediction_valid_context_steps": prediction_context["true"],
        "prediction_invalid_context_steps": prediction_context["false"],
        "no_solver_telemetry_context_steps": counts[
            "no_solver_telemetry_context"
        ],
        "rule_bypass_no_solve_steps": bypass,
        "attempted_solve_steps": attempted,
        "prediction_valid_attempted_solve_steps": execution_by_prediction["true"][
            "attempted"
        ],
        "prediction_invalid_attempted_solve_steps": execution_by_prediction[
            "false"
        ]["attempted"],
        "prediction_valid_bypass_no_solve_steps": execution_by_prediction["true"][
            "bypass"
        ],
        "prediction_invalid_bypass_no_solve_steps": execution_by_prediction[
            "false"
        ]["bypass"],
        "attempted_accepted_steps": counts["attempted_accepted"],
        "attempted_fallback_or_nonaccepted_steps": counts["attempted_fallback_or_nonaccepted"],
        "controller_acceptance_rate_attempted_solve": stable_float(
            counts["attempted_accepted"] / attempted if attempted else None
        ),
        "solver_execution_decisions": execution_decisions,
        "bypass_fraction_of_solver_execution_decisions": stable_float(
            bypass / execution_decisions if execution_decisions else None
        ),
        "finite_attempted_latency_steps": len(times),
        "nonfinite_attempted_latency_steps": stats["nonfinite_attempted"],
        "attempted_latency_p50_s": stable_float(quantile(times, 0.50) if times else None),
        "attempted_latency_p95_s": stable_float(quantile(times, 0.95) if times else None),
        "attempted_latency_p99_s": stable_float(quantile(times, 0.99) if times else None),
        "independent_unit_warning": (
            "step counts are diagnostic; five ego-initialisation clusters are the "
            "independent units"
        ),
    }


def analyze_raw(
    raw_root: Path,
    rows: Sequence[dict[str, Any]],
    deadlines: Mapping[str, float],
    snapshot_files_manifest: Path | None,
) -> dict[str, Any]:
    if snapshot_files_manifest is None:
        raise ValueError(
            "A snapshot files manifest is required for a final raw audit; "
            "unhashed raw logs cannot produce a pass receipt"
        )
    files, ignored_files = find_raw_debug_files(raw_root, rows)
    hash_lookup = manifest_hash_lookup(snapshot_files_manifest)
    if not hash_lookup:
        raise ValueError("Raw snapshot files manifest contains no hash records")
    expected_by_cell_init = {
        (str(row["cell_id"]), int(row["ego_init_id"])): row for row in rows
    }
    events: list[dict[str, Any]] = []
    affected_rollout_outcomes: list[dict[str, Any]] = []
    step_records: list[dict[str, Any]] = []
    rollout_summaries: list[dict[str, Any]] = []
    corrected_rollout_rows: list[dict[str, Any]] = []
    deadline_counts: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"finite": 0, "exceeded": 0, "nonfinite": 0}
    )
    group_stats: dict[tuple[str, int | str], dict[str, Any]] = defaultdict(
        lambda: {
            "counts": {name: 0 for name in STEP_CLASSIFICATIONS},
            "latencies": [],
            "nonfinite_attempted": 0,
            "prediction_context": {"true": 0, "false": 0},
            "execution_by_prediction": {
                "true": {"attempted": 0, "bypass": 0},
                "false": {"attempted": 0, "bypass": 0},
            },
            "rollouts": set(),
        }
    )
    validated_hashes: list[dict[str, str]] = []

    for key in sorted(files):
        path, canonical_relative = files[key]
        aggregate = expected_by_cell_init[key]
        expected_hash = hash_lookup.get(canonical_relative)
        if expected_hash is None:
            raise ValueError(
                f"Raw debug path absent from snapshot files manifest: {canonical_relative}"
            )
        observed_hash = sha256(path)
        if observed_hash != expected_hash:
            raise ValueError(f"Raw debug hash mismatch: {canonical_relative}")
        validated_hashes.append({"path": canonical_relative, "sha256": observed_hash})

        debug_rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"Expected object at {path}:{line_number}")
                debug_rows.append(value)
        if len(debug_rows) != int(aggregate["debug_steps"]):
            raise ValueError(
                f"Raw debug-step count mismatch for {key}: "
                f"{len(debug_rows)} != {aggregate['debug_steps']}"
            )
        step_ids = [
            integer(debug_row.get("step"), f"raw step for {key}")
            for debug_row in debug_rows
        ]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError(f"Duplicate raw step IDs within canonical log for {key}")
        if any(current <= previous for previous, current in zip(step_ids, step_ids[1:])):
            raise ValueError(
                f"Raw step IDs are not strictly increasing within canonical log for {key}"
            )

        counts = {name: 0 for name in STEP_CLASSIFICATIONS}
        legacy_nonoptimal_steps = 0
        legacy_valid_prediction_steps = 0
        legacy_finite_times: list[float] = []
        legacy_nonfinite_times = 0
        attempted_finite_times: list[float] = []
        attempted_nonfinite_times = 0
        rollout_prediction_context = {"true": 0, "false": 0}
        rollout_execution_by_prediction = {
            "true": {"attempted": 0, "bypass": 0},
            "false": {"attempted": 0, "bypass": 0},
        }
        policy = str(aggregate["risk_policy"])
        init_id = int(aggregate["ego_init_id"])
        rollout_identity = (str(aggregate["cell_id"]), init_id)

        for row_index, debug_row in enumerate(debug_rows):
            legacy_solver = debug_row.get("solver")
            legacy_solver = legacy_solver if isinstance(legacy_solver, dict) else {}
            legacy_optimal = legacy_solver.get("optimal")
            legacy_nonoptimal_steps += int(
                legacy_optimal is not None and not bool(legacy_optimal)
            )
            classified = classify_solver_step(
                debug_row,
                key=key,
                row_index=row_index,
            )
            classification = str(classified["classification"])
            if classification not in STEP_CLASSIFICATIONS:
                raise AssertionError(f"Unexpected step classification: {classification}")
            counts[classification] += 1
            context = raw_step_context(debug_row, classified)
            prediction_state = str(classified["prediction_state"])
            valid_prediction = prediction_state == "true"
            rollout_prediction_context[prediction_state] += 1
            if valid_prediction:
                legacy_valid_prediction_steps += 1

            applied = classified["applied"]
            legacy_solve_time = optional_finite_float(applied.get("solve_time"))
            if valid_prediction:
                if legacy_solve_time is None:
                    legacy_nonfinite_times += 1
                else:
                    legacy_finite_times.append(legacy_solve_time)

            attempted = bool(classified["attempted"])
            attempted_solve_time = classified["solve_time"]
            if attempted:
                rollout_execution_by_prediction[prediction_state]["attempted"] += 1
                if attempted_solve_time is None:
                    attempted_nonfinite_times += 1
                else:
                    attempted_finite_times.append(float(attempted_solve_time))
                for deadline_name, deadline in deadlines.items():
                    deadline_count = deadline_counts[(policy, deadline_name)]
                    if attempted_solve_time is None:
                        deadline_count["nonfinite"] += 1
                    else:
                        deadline_count["finite"] += 1
                        deadline_count["exceeded"] += int(
                            float(attempted_solve_time) > deadline
                        )
            elif classification == "rule_bypass_no_solve":
                rollout_execution_by_prediction[prediction_state]["bypass"] += 1

            for group_key in ((policy, init_id), (policy, "ALL")):
                stats = group_stats[group_key]
                stats["counts"][classification] += 1
                stats["rollouts"].add(rollout_identity)
                stats["prediction_context"][prediction_state] += 1
                if attempted:
                    stats["execution_by_prediction"][prediction_state]["attempted"] += 1
                elif classification == "rule_bypass_no_solve":
                    stats["execution_by_prediction"][prediction_state]["bypass"] += 1
                if attempted:
                    if attempted_solve_time is None:
                        stats["nonfinite_attempted"] += 1
                    else:
                        stats["latencies"].append(float(attempted_solve_time))

            solver = classified["solver"]
            solver_debug = classified["solver_debug"]
            solver_bypass = classified["solver_bypass"]
            solver_problem = classified["solver_problem"]
            fallback = context["fallback"]
            yield_status = context["yield_status"]
            supervisor_action = context["supervisor_action"]
            step_records.append(
                {
                    "cell_id": aggregate["cell_id"],
                    "predictor": aggregate["predictor"],
                    "risk_policy": policy,
                    "target_style": aggregate["target_style"],
                    "ego_init_id": init_id,
                    "debug_row_index": row_index,
                    "step": scalar_category(debug_row.get("step")),
                    "prediction_valid_any": prediction_state,
                    "classification": classification,
                    "solver_attempted": int(attempted),
                    "solver_logger_accepted": scalar_category(classified["accepted"]),
                    "solver_bypass_enabled": scalar_category(
                        solver_bypass.get("enabled")
                    ),
                    "solver_bypassed": scalar_category(solver.get("bypassed")),
                    "solver_problem_bypassed": scalar_category(
                        solver_problem.get("bypassed")
                    ),
                    "applied_logger_accepted": scalar_category(applied.get("is_opt")),
                    "attempted_solve_time_state": (
                        "finite"
                        if attempted and attempted_solve_time is not None
                        else (
                            "missing_or_nonfinite"
                            if attempted
                            else "__not_applicable__"
                        )
                    ),
                    "attempted_solve_time_s": stable_float(attempted_solve_time),
                    "return_status": scalar_category(context["return_status"]),
                    "return_status_source": context["return_status_source"],
                    "exception_type": scalar_category(context["exception_type"]),
                    "exception_repr": scalar_category(context["exception_repr"]),
                    "solver_risk_mode": scalar_category(context["solver_risk_mode"]),
                    "solver_risk_mode_source": context["solver_risk_mode_source"],
                    "fallback_present": "true" if fallback is not None else "false",
                    "fallback_schema": context["fallback_schema"],
                    "fallback_mode": scalar_category(
                        context["fallback_mode"],
                        missing=(
                            "__not_recorded__"
                            if fallback is not None
                            else "__not_applicable__"
                        ),
                    ),
                    "supervisor_action_source": context[
                        "supervisor_action_source"
                    ],
                    "supervisor_action_mode": scalar_category(
                        context["supervisor_action_mode"]
                    ),
                }
            )

            if classification != "attempted_fallback_or_nonaccepted":
                continue
            stats = context["solver_stats"]
            solver_control_source = context["solver_control_source"]
            event = {
                "cell_id": aggregate["cell_id"],
                "predictor": aggregate["predictor"],
                "risk_policy": policy,
                "target_style": aggregate["target_style"],
                "ego_init_id": init_id,
                "debug_row_index": row_index,
                "step": scalar_category(debug_row.get("step")),
                "prediction_valid_any": prediction_state,
                "prediction_valid_json": json.dumps(
                    debug_row.get("prediction_valid"),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "return_status": scalar_category(context["return_status"]),
                "return_status_source": context["return_status_source"],
                "exception_type": scalar_category(context["exception_type"]),
                "solver_success_stat": scalar_category(
                    solver_debug.get("success", stats.get("success"))
                ),
                "solver_iter_count": scalar_category(
                    solver_debug.get("iter_count", stats.get("iter_count"))
                ),
                "yield_phase": scalar_category(yield_status.get("phase")),
                "supervisor_active": scalar_category(yield_status.get("active")),
                "supervisor_action_present": (
                    "true" if supervisor_action is not None else "false"
                ),
                "supervisor_action_source": context["supervisor_action_source"],
                "supervisor_action_mode": scalar_category(
                    context["supervisor_action_mode"]
                ),
                "supervisor_action_json": (
                    json.dumps(
                        supervisor_action,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if supervisor_action is not None
                    else ""
                ),
                "final_control_telemetry_source": (
                    "applied.u0" if applied.get("u0") is not None else "__missing__"
                ),
                "applied_logger_accepted": scalar_category(applied.get("is_opt")),
                "applied_u0_json": json.dumps(
                    applied.get("u0"), sort_keys=True, separators=(",", ":")
                ),
                "applied_solver_u_control_json": json.dumps(
                    applied.get("u_control"), sort_keys=True, separators=(",", ":")
                ),
                "reference_regenerated": scalar_category(
                    context["reference_status"].get("regenerated")
                ),
                "reference_restored_global": scalar_category(
                    context["reference_status"].get("restored_global_reference")
                ),
                "reference_forced_linearization": scalar_category(
                    context["reference_status"].get("forced_reference_linearization")
                ),
                "reference_skip_reason": scalar_category(
                    context["reference_status"].get("skip_reason")
                ),
                "solver_risk_mode": scalar_category(context["solver_risk_mode"]),
                "solver_risk_mode_source": context["solver_risk_mode_source"],
                "solver_control_source": solver_control_source,
                "fallback_present": "true" if fallback is not None else "false",
                "fallback_schema": context["fallback_schema"],
                "fallback_mode": scalar_category(
                    context["fallback_mode"],
                    missing=(
                        "__not_recorded__"
                        if fallback is not None
                        else "__not_applicable__"
                    ),
                ),
                "fallback_mode_source": context["fallback_mode_source"],
                "fallback_v_curr": scalar_category(
                    fallback.get("v_curr") if fallback is not None else None,
                    missing="",
                ),
                "fallback_v_next_ref": scalar_category(
                    fallback.get("v_next_ref") if fallback is not None else None,
                    missing="",
                ),
                "fallback_a_brake": scalar_category(
                    fallback.get("a_brake") if fallback is not None else None,
                    missing="",
                ),
                "fallback_u_control_json": (
                    json.dumps(
                        fallback.get("u_control"),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if fallback is not None
                    else ""
                ),
                "fallback_v_tp1": scalar_category(
                    fallback.get("v_tp1") if fallback is not None else None,
                    missing="",
                ),
                "applied_solve_time_state": (
                    "finite"
                    if attempted_solve_time is not None
                    else "missing_or_nonfinite"
                ),
                "applied_solve_time_s": stable_float(attempted_solve_time),
                "rollout_completion_valid": aggregate["completion_valid"],
                "rollout_completion_failure": aggregate["completion_failure"],
                "rollout_completion_reason": aggregate["completion_reason"],
                "rollout_completion_duration_s": stable_float(
                    aggregate["completion_duration_s"]
                ),
                "rollout_yield_outcome_observed": aggregate[
                    "yield_outcome_observed"
                ],
                "rollout_yield_failure": aggregate["yield_failure"],
                "rollout_yield_outcome_reason": aggregate[
                    "yield_outcome_reason"
                ],
                "rollout_minimum_footprint_separation_m": stable_float(
                    aggregate["minimum_footprint_separation_m"]
                ),
                "rollout_footprint_collision": aggregate["footprint_collision"],
                "rollout_native_collision_any": aggregate["native_collision_any"],
                "rollout_native_collision_episode_count": aggregate[
                    "native_collision_episode_count"
                ],
            }
            events.append(event)

        if sum(counts.values()) != len(debug_rows):
            raise AssertionError(f"Classification did not partition raw rows for {key}")
        attempted_steps = counts["attempted_accepted"] + counts["attempted_fallback_or_nonaccepted"]
        if legacy_nonoptimal_steps != int(aggregate["nonoptimal_steps"]):
            raise ValueError(
                f"Legacy raw non-optimal count mismatch for {key}: "
                f"{legacy_nonoptimal_steps} != {aggregate['nonoptimal_steps']}"
            )
        if legacy_valid_prediction_steps != int(aggregate["valid_prediction_steps"]):
            raise ValueError(
                f"Raw valid-prediction count mismatch for {key}: "
                f"{legacy_valid_prediction_steps} != {aggregate['valid_prediction_steps']}"
            )
        if not legacy_finite_times:
            raise ValueError(f"No legacy finite valid-prediction times for {key}")
        legacy_observed_p95 = quantile(legacy_finite_times, 0.95)
        if not math.isclose(
            legacy_observed_p95,
            float(aggregate["p95_solve_time_s"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                f"Legacy raw P95 mismatch for {key}: {legacy_observed_p95} != "
                f"{aggregate['p95_solve_time_s']}"
            )
        attempted_acceptance = (
            counts["attempted_accepted"] / attempted_steps if attempted_steps else None
        )
        attempted_p50 = (
            quantile(attempted_finite_times, 0.50)
            if attempted_finite_times
            else None
        )
        attempted_p95 = (
            quantile(attempted_finite_times, 0.95)
            if attempted_finite_times
            else None
        )
        attempted_p99 = (
            quantile(attempted_finite_times, 0.99)
            if attempted_finite_times
            else None
        )
        rollout_summary = {
            "cell_id": aggregate["cell_id"],
            "predictor": aggregate["predictor"],
            "risk_policy": policy,
            "target_style": aggregate["target_style"],
            "ego_init_id": init_id,
            "debug_steps": len(debug_rows),
            "prediction_valid_context_steps": rollout_prediction_context["true"],
            "prediction_invalid_context_steps": rollout_prediction_context["false"],
            "no_solver_telemetry_context_steps": counts[
                "no_solver_telemetry_context"
            ],
            "rule_bypass_no_solve_steps": counts["rule_bypass_no_solve"],
            "attempted_solve_steps": attempted_steps,
            "prediction_valid_attempted_solve_steps": (
                rollout_execution_by_prediction["true"]["attempted"]
            ),
            "prediction_invalid_attempted_solve_steps": (
                rollout_execution_by_prediction["false"]["attempted"]
            ),
            "prediction_valid_bypass_no_solve_steps": (
                rollout_execution_by_prediction["true"]["bypass"]
            ),
            "prediction_invalid_bypass_no_solve_steps": (
                rollout_execution_by_prediction["false"]["bypass"]
            ),
            "attempted_accepted_steps": counts["attempted_accepted"],
            "attempted_fallback_or_nonaccepted_steps": counts["attempted_fallback_or_nonaccepted"],
            "attempted_controller_acceptance_rate": stable_float(
                attempted_acceptance
            ),
            "finite_attempted_solve_times": len(attempted_finite_times),
            "nonfinite_attempted_solve_times": attempted_nonfinite_times,
            "attempted_latency_p50_s": stable_float(attempted_p50),
            "attempted_latency_p95_s": stable_float(attempted_p95),
            "attempted_latency_p99_s": stable_float(attempted_p99),
            "legacy_nonoptimal_steps_all_debug_rows": legacy_nonoptimal_steps,
            "legacy_minus_corrected_fallback_or_nonaccepted_steps": (
                legacy_nonoptimal_steps - counts["attempted_fallback_or_nonaccepted"]
            ),
            "legacy_valid_prediction_steps": legacy_valid_prediction_steps,
            "legacy_finite_valid_prediction_times": len(legacy_finite_times),
            "legacy_nonfinite_valid_prediction_times": legacy_nonfinite_times,
            "legacy_raw_p95_solve_time_s": stable_float(legacy_observed_p95),
            "legacy_aggregate_p95_solve_time_s": stable_float(
                float(aggregate["p95_solve_time_s"])
            ),
            "legacy_aggregate_validation_status": "pass_reproduced_but_conflated",
            "classification_validation_status": "pass",
        }
        rollout_summaries.append(rollout_summary)
        if counts["attempted_fallback_or_nonaccepted"] > 0:
            affected_rollout_outcomes.append(
                {
                    "cell_id": aggregate["cell_id"],
                    "predictor": aggregate["predictor"],
                    "risk_policy": policy,
                    "target_style": aggregate["target_style"],
                    "ego_init_id": init_id,
                    "attempted_solve_steps": attempted_steps,
                    "attempted_fallback_or_nonaccepted_steps": counts[
                        "attempted_fallback_or_nonaccepted"
                    ],
                    "attempted_fallback_or_nonaccepted_fraction": stable_float(
                        counts["attempted_fallback_or_nonaccepted"] / attempted_steps
                    ),
                    "completion_valid": aggregate["completion_valid"],
                    "completion_failure": aggregate["completion_failure"],
                    "completion_reason": aggregate["completion_reason"],
                    "completion_duration_s": stable_float(
                        aggregate["completion_duration_s"]
                    ),
                    "yield_outcome_observed": aggregate[
                        "yield_outcome_observed"
                    ],
                    "yield_failure": aggregate["yield_failure"],
                    "yield_outcome_reason": aggregate["yield_outcome_reason"],
                    "minimum_footprint_separation_m": stable_float(
                        aggregate["minimum_footprint_separation_m"]
                    ),
                    "footprint_collision": aggregate["footprint_collision"],
                    "native_collision_any": aggregate["native_collision_any"],
                    "native_collision_episode_count": aggregate[
                        "native_collision_episode_count"
                    ],
                    "interpretation_boundary": (
                        "rollout outcome after one or more fallback/nonaccepted attempts; "
                        "descriptive association, not a causal effect of controller "
                        "nonacceptance or a mathematical feasibility diagnosis"
                    ),
                }
            )
        corrected_rollout_rows.append(
            {
                "cell_id": aggregate["cell_id"],
                "predictor": aggregate["predictor"],
                "risk_policy": policy,
                "target_style": aggregate["target_style"],
                "ego_init_id": init_id,
                "p95_solve_time_s": attempted_p95,
                "solver_failure_fraction": (
                    counts["attempted_fallback_or_nonaccepted"] / attempted_steps
                    if attempted_steps
                    else None
                ),
            }
        )

    taxonomy_groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        taxonomy_groups[
            tuple(str(event[field]) for field in FAILURE_TAXONOMY_KEYS)
        ].append(event)
    taxonomy: list[dict[str, Any]] = []
    for group_key in sorted(taxonomy_groups):
        selected = taxonomy_groups[group_key]
        row = dict(zip(FAILURE_TAXONOMY_KEYS, group_key))
        rollout_ids = {
            (event["cell_id"], int(event["ego_init_id"])) for event in selected
        }
        row.update(
            {
                "failure_events": len(selected),
                "affected_rollouts": len(rollout_ids),
                "affected_init_ids": ";".join(
                    str(value) for value in sorted({item[1] for item in rollout_ids})
                ),
                "interpretation_boundary": (
                    "descriptive downstream outcome/fallback category; not a causal label"
                ),
            }
        )
        taxonomy.append(row)

    raw_policy: dict[str, dict[str, Any]] = {}
    for policy in POLICY_ORDER:
        group = group_stats[(policy, "ALL")]
        row = raw_solver_group_row(policy, "ALL", group)
        if not group["latencies"]:
            raise ValueError(f"No finite attempted-solve latency rows for policy {policy}")
        rollout_p95s = [
            finite_float(item["attempted_latency_p95_s"], "attempted rollout P95")
            for item in rollout_summaries
            if item["risk_policy"] == policy and item["attempted_latency_p95_s"] != ""
        ]
        row.update(
            {
                "rollouts_with_finite_attempted_latency": len(rollout_p95s),
                "mean_per_rollout_attempted_p95_s": stable_float(
                    statistics.mean(rollout_p95s) if rollout_p95s else None
                ),
                "median_per_rollout_attempted_p95_s": stable_float(
                    statistics.median(rollout_p95s) if rollout_p95s else None
                ),
            }
        )
        raw_policy[policy] = row
    raw_policy_init = [
        raw_solver_group_row(policy, init_id, group_stats[(policy, init_id)])
        for policy in POLICY_ORDER
        for init_id in sorted(
            {
                int(row["ego_init_id"])
                for row in rows
                if row["risk_policy"] == policy
            }
        )
    ]
    no_solver_telemetry_context_steps = sum(
        int(raw_policy[policy]["no_solver_telemetry_context_steps"])
        for policy in POLICY_ORDER
    )
    telemetry_integrity_status = (
        "pass"
        if no_solver_telemetry_context_steps == 0
        else "fail_nonzero_no_solver_telemetry_context"
    )

    deadline_rows: list[dict[str, Any]] = []
    for policy in POLICY_ORDER:
        for deadline_name, deadline in deadlines.items():
            deadline_count = deadline_counts[(policy, deadline_name)]
            deadline_rows.append(
                {
                    "risk_policy": policy,
                    "deadline_name": deadline_name,
                    "deadline_s": stable_float(deadline),
                    "deadline_source": DEADLINE_SOURCES[deadline_name],
                    "evaluation_status": "evaluated",
                    "finite_attempted_solve_steps": deadline_count["finite"],
                    "deadline_exceedance_steps": deadline_count["exceeded"],
                    "deadline_exceedance_fraction_of_finite_attempts": stable_float(
                        deadline_count["exceeded"] / deadline_count["finite"]
                        if deadline_count["finite"]
                        else None
                    ),
                    "nonfinite_attempted_solve_steps_excluded": deadline_count[
                        "nonfinite"
                    ],
                    "scope": (
                        "actual attempted solves only; finite recorded solve time; "
                        "strict greater-than deadline; bypass zero markers excluded"
                    ),
                    "reason_not_evaluated": "",
                }
            )

    return {
        "status": (
            "pass"
            if telemetry_integrity_status == "pass"
            else "fail_raw_telemetry_integrity"
        ),
        "reason": (
            "all canonical raw logs hash-validated; every step strictly classified; "
            "canonical R3 contains no telemetry-absent context rows; legacy aggregate "
            "reproduced; corrected attempted-solve audit complete"
            if telemetry_integrity_status == "pass"
            else (
                "raw logs contain control-context rows without solver/problem/applied/"
                "bypass execution telemetry; canonical R3 logger should emit complete "
                "execution telemetry for every debug row"
            )
        ),
        "classification_status": "pass",
        "raw_step_identity_status": "pass",
        "telemetry_integrity_status": telemetry_integrity_status,
        "no_solver_telemetry_context_steps": no_solver_telemetry_context_steps,
        "corrected_latency_status": "pass",
        "corrected_acceptance_status": "pass",
        "legacy_aggregate_status": "preliminary_legacy_conflated",
        "ignored_noncanonical_debug_files": ignored_files,
        "canonical_debug_files": len(files),
        "hash_validation_status": "pass",
        "validated_hashes": validated_hashes,
        "step_records": step_records,
        "failure_events": events,
        "failure_taxonomy": taxonomy,
        "affected_rollout_outcomes": affected_rollout_outcomes,
        "failure_downstream_outcome_join_status": "pass",
        "rollout_summaries": rollout_summaries,
        "corrected_rollout_rows": corrected_rollout_rows,
        "raw_policy": raw_policy,
        "raw_policy_init": raw_policy_init,
        "deadline_rows": deadline_rows,
    }


def not_evaluated_raw(
    rows: Sequence[dict[str, Any]], deadlines: Mapping[str, float]
) -> dict[str, Any]:
    deadline_rows = []
    for policy in POLICY_ORDER:
        for deadline_name, deadline in deadlines.items():
            deadline_rows.append(
                {
                    "risk_policy": policy,
                    "deadline_name": deadline_name,
                    "deadline_s": stable_float(deadline),
                    "deadline_source": DEADLINE_SOURCES[deadline_name],
                    "evaluation_status": "not_evaluated",
                    "finite_attempted_solve_steps": "",
                    "deadline_exceedance_steps": "",
                    "deadline_exceedance_fraction_of_finite_attempts": "",
                    "nonfinite_attempted_solve_steps_excluded": "",
                    "scope": "requires raw classification of actual attempted solves",
                    "reason_not_evaluated": "extracted raw snapshot directory was not provided",
                }
            )
    return {
        "status": "not_evaluated",
        "reason": "extracted raw snapshot directory was not provided",
        "expected_canonical_debug_files": len(rows),
        "failure_events": [],
        "failure_taxonomy": [],
        "affected_rollout_outcomes": [],
        "step_records": [],
        "rollout_summaries": [],
        "corrected_rollout_rows": [],
        "deadline_rows": deadline_rows,
        "raw_policy": {},
        "raw_policy_init": [],
        "classification_status": "not_evaluated",
        "raw_step_identity_status": "not_evaluated",
        "failure_downstream_outcome_join_status": "not_evaluated",
        "telemetry_integrity_status": "not_evaluated",
        "no_solver_telemetry_context_steps": None,
        "corrected_latency_status": "not_evaluated",
        "corrected_acceptance_status": "not_evaluated",
        "legacy_aggregate_status": "preliminary_legacy_conflated",
    }


def report_markdown(summary: Mapping[str, Any]) -> str:
    costs = {row["risk_policy"]: row for row in summary["policy_cost_summary"]}
    legacy_failures = {
        row["risk_policy"]: row
        for row in summary["legacy_nonoptimal_policy_summary"]
    }
    legacy_medium = next(
        row
        for row in summary["legacy_paired_cost_contrasts"]
        if row["contrast"] == "adaptive_minus_fixed_medium"
    )
    raw_status = summary["raw_taxonomy_status"]
    raw_policy = (
        {
            row["risk_policy"]: row
            for row in summary["raw_policy_solver_summary"]
        }
        if raw_status["status"] == "pass"
        else {}
    )
    lines = [
        "# Supervisor feedback 2 — solver timing, controller acceptance and fallback",
        "",
        f"Evidence status: **{summary['status']}**.",
        "",
        "## Preliminary legacy aggregate — not a final solver result",
        "",
        (
            "The frozen aggregate counted rule-yield bypass decisions as successful "
            "zero-second solves. It is retained only to reproduce the previous report and "
            "must not be used for final timing or controller-acceptance claims."
        ),
        "",
        (
            f"Under that legacy conflated definition, adaptive mean rollout P95 was "
            f"{1000 * float(costs['adaptive']['legacy_conflated_per_rollout_p95_s_mean']):.2f} ms "
            f"and fixed-medium was "
            f"{1000 * float(costs['fixed_medium']['legacy_conflated_per_rollout_p95_s_mean']):.2f} ms; "
            f"the legacy paired difference was "
            f"{1000 * float(legacy_medium['mean_effect']):+.2f} ms."
        ),
        (
            f"The legacy logger diagnostic was "
            f"{summary['legacy_total_nonoptimal_steps']}/"
            f"{summary['legacy_total_debug_steps']} non-optimal/debug rows. Its denominator "
            "contains all logged control contexts, including bypass/no-solve and rows "
            "without solver telemetry, and is therefore not an attempted-solve "
            "controller-acceptance rate."
        ),
        "",
        "## Corrected attempted-solve audit",
        "",
    ]
    if raw_policy:
        lines.extend(
            (
                "| Policy | Attempts | Controller accepted / attempted | Bypass no-solve, n (% execution) | "
                "Finite / non-finite latency | P50 / P95 / P99 (ms) |",
                "|---|---:|---:|---:|---:|---:|",
            )
        )
        for policy in POLICY_ORDER:
            row = raw_policy[policy]
            lines.append(
                f"| {policy} | {row['attempted_solve_steps']} | "
                f"{row['attempted_accepted_steps']}/{row['attempted_solve_steps']} "
                f"({100 * float(row['controller_acceptance_rate_attempted_solve']):.2f}%) | "
                f"{row['rule_bypass_no_solve_steps']} "
                f"({100 * float(row['bypass_fraction_of_solver_execution_decisions']):.2f}%) | "
                f"{row['finite_attempted_latency_steps']}/"
                f"{row['nonfinite_attempted_latency_steps']} | "
                f"{1000 * float(row['attempted_latency_p50_s']):.2f} / "
                f"{1000 * float(row['attempted_latency_p95_s']):.2f} / "
                f"{1000 * float(row['attempted_latency_p99_s']):.2f} |"
            )
        lines.extend(
            (
                "",
                "All latency quantiles and 50/200/500 ms deadline counts use only actual "
                "attempted solves with finite recorded latency. Non-finite attempts are "
                "reported separately and are never imputed. Bypass/no-solve rows are "
                "reported separately and enter neither timing nor the acceptance denominator. "
                "The historical accepted flag includes CasADi SUBOPTIMAL solutions selected "
                "for execution; it is not proof of mathematical optimality or feasibility.",
            )
        )
    else:
        if raw_status["status"] == "fail_raw_telemetry_integrity":
            lines.append(
                "**Raw telemetry integrity failed.** The canonical R3 logger is expected "
                "to emit solver/bypass execution telemetry for every debug row, but "
                f"{raw_status['no_solver_telemetry_context_steps']} telemetry-absent "
                "control-context rows were observed. They are never silently removed "
                "from a final claim; the final gate remains closed."
            )
        else:
            lines.append(
                "**Not evaluated.** The hash-validated raw R3 snapshot is required to "
                "separate solver execution decisions into rule-bypass/no-solve, "
                "attempted-accepted and attempted-fallback/nonaccepted rows. Prediction validity "
                "remains a context stratifier. The legacy numbers above remain "
                "preliminary."
            )
    lines.extend(
        (
            "",
            "## Statistical unit and taxonomy boundary",
            "",
            "Step counts diagnose execution. The five ego-initialisation clusters, not "
            "individual steps, are the independent units for paired summaries.",
            "",
            f"Raw taxonomy status: **{raw_status['status']}**. {raw_status['reason']}",
        )
    )
    if raw_status["status"] == "pass":
        lines.append(
            f"The audit hash-validated {raw_status['canonical_debug_files']} logs and "
            f"retained {raw_status['failure_event_count']} attempted-fallback/nonaccepted downstream "
            "outcome/fallback events. Every event is joined to the corresponding canonical "
            "completion, yield, physical-separation and collision outcomes. Those "
            "categories are descriptive associations, not causal labels."
        )
    else:
        lines.append(
            "Return status, exception, fallback, supervisor action and exact deadline "
            "outcomes are not inferred from aggregate tables."
        )
    return "\n".join(lines).rstrip() + "\n"


def tex_escape(value: Any) -> str:
    text = str(value)
    replacements = (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def policy_tex_label(policy: str) -> str:
    labels = {
        "adaptive": "Adaptive",
        "fixed_aggressive": "Fixed aggressive",
        "fixed_medium": "Fixed medium",
        "fixed_conservative": "Fixed conservative",
    }
    if policy not in labels:
        raise ValueError(f"Unknown policy for TeX table: {policy}")
    return labels[policy]


def policy_cost_tex(
    policy_costs: Sequence[Mapping[str, Any]],
    deadlines: Mapping[str, float],
) -> str:
    by_policy = {str(row["risk_policy"]): row for row in policy_costs}
    corrected = all(
        row["corrected_attempted_solve_status"] == "pass"
        for row in policy_costs
    )
    lines = [r"\begin{table}[t]", r"\centering\small"]
    if corrected:
        lines.extend(
            (
                (
                    r"\caption{Corrected-R3 recorded optimiser solve-stage timing on actual "
                    r"SMPC attempts. The logged value is CasADi solver wall time, not "
                    r"end-to-end prediction, controller or deployment latency. Rule-yield "
                    r"bypass/no-solve zero markers are excluded; non-finite attempted "
                    r"latency is counted but not imputed.}"
                ),
                r"\label{tab:supervisor-feedback-policy-cost}",
                r"\resizebox{\linewidth}{!}{%",
                r"\begin{tabular}{@{}lrrrrrrr@{}}",
                r"\toprule",
                (
                    r"Policy & Attempts & Finite & Non-finite & Bypass & "
                    r"P50 (ms) & P95 (ms) & P99 (ms) \\"
                ),
                r"\midrule",
            )
        )
        for policy in POLICY_ORDER:
            row = by_policy[policy]
            lines.append(
                f"{policy_tex_label(policy)} & {row['attempted_solve_steps']} & "
                f"{row['finite_attempted_latency_steps']} & "
                f"{row['nonfinite_attempted_latency_steps']} & "
                f"{row['rule_bypass_no_solve_steps']} & "
                f"{1000 * float(row['attempted_latency_p50_s']):.2f} & "
                f"{1000 * float(row['attempted_latency_p95_s']):.2f} & "
                f"{1000 * float(row['attempted_latency_p99_s']):.2f} \\\\"
            )
        lines.extend((r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table}"))
    else:
        lines.extend(
            (
                (
                    r"\caption{Preliminary legacy aggregate (not a final solver-latency "
                    r"result). These rollout P95 values include rule-yield bypass/no-solve "
                    r"rows recorded as zero-second successful solves. Final reporting must "
                    r"use the raw attempted-solve-only audit.}"
                ),
                r"\label{tab:supervisor-feedback-policy-cost}",
                r"\begin{tabular}{@{}lrrr@{}}",
                r"\toprule",
                r"Policy & $n$ & Legacy mean P95 (ms) & Legacy median P95 (ms) \\",
                r"\midrule",
            )
        )
        for policy in POLICY_ORDER:
            row = by_policy[policy]
            lines.append(
                f"{policy_tex_label(policy)} & {row['rollouts']} & "
                f"{1000 * float(row['legacy_conflated_per_rollout_p95_s_mean']):.2f} & "
                f"{1000 * float(row['legacy_conflated_per_rollout_p95_s_median']):.2f} \\\\"
            )
        lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return "\n".join(lines) + "\n"


def solver_nonoptimal_tex(
    legacy_policy_rows: Sequence[Mapping[str, Any]],
    raw_policy: Mapping[str, Mapping[str, Any]] | None,
) -> str:
    lines = [r"\begin{table}[t]", r"\centering\small"]
    if raw_policy:
        lines.extend(
            (
                (
                    r"\caption{Corrected-R3 controller acceptance and fallback audit. "
                    r"The historical logger's accepted flag includes CasADi SUBOPTIMAL "
                    r"solutions selected for execution and therefore is not mathematical "
                    r"optimality or a proof of optimisation-problem feasibility. The "
                    r"denominator is actual solve attempts; bypass/no-solve decisions are "
                    r"shown separately. Step counts are descriptive; five ego-"
                    r"initialisation clusters are the independent units.}"
                ),
                r"\label{tab:supervisor-feedback-solver-nonoptimal}",
                r"\begin{tabular}{@{}lrrrr@{}}",
                r"\toprule",
                r"Policy & Accepted & Fallback/nonaccepted & Attempts & Bypass/no-solve \\",
                r"\midrule",
            )
        )
        for policy in POLICY_ORDER:
            row = raw_policy[policy]
            lines.append(
                f"{policy_tex_label(policy)} & {row['attempted_accepted_steps']} & "
                f"{row['attempted_fallback_or_nonaccepted_steps']} & "
                f"{row['attempted_solve_steps']} & "
                f"{row['rule_bypass_no_solve_steps']} \\\\"
            )
    else:
        by_policy = {
            str(row["risk_policy"]): row for row in legacy_policy_rows
        }
        lines.extend(
            (
                (
                    r"\caption{Preliminary legacy non-optimal/debug-row diagnostic "
                    r"(not final controller acceptance). Its denominator includes "
                    r"all logged control contexts, including bypass/no-solve and rows "
                    r"without solver telemetry. Final reporting must divide by actual "
                    r"solve attempts and report bypass separately.}"
                ),
                r"\label{tab:supervisor-feedback-solver-nonoptimal}",
                r"\begin{tabular}{@{}lrrr@{}}",
                r"\toprule",
                r"Policy & Legacy non-optimal & All debug rows & Legacy fraction (\%) \\",
                r"\midrule",
            )
        )
        for policy in POLICY_ORDER:
            row = by_policy[policy]
            lines.append(
                f"{policy_tex_label(policy)} & {row['nonoptimal_steps']} & "
                f"{row['debug_steps']} & "
                f"{100 * float(row['pooled_step_fraction_descriptive']):.3f} \\\\"
            )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return "\n".join(lines) + "\n"


def corrected_paired_cost_acceptance_tex(
    cost_contrasts: Sequence[Mapping[str, Any]],
    acceptance_contrasts: Sequence[Mapping[str, Any]],
    raw_status: Mapping[str, Any],
) -> str:
    """Render the examiner-visible, init-cluster paired SF2 effects.

    Simulator steps remain useful diagnostics, but they are repeated observations
    within a rollout.  This table therefore reports effects after averaging the
    balanced predictor/style cells within each ego-initialisation cluster.
    """

    lines = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        (
            r"\caption{Corrected adaptive-minus-fixed contrasts for recorded CasADi "
            r"solve-stage P95 and attempted-solve fallback/nonacceptance. Effects are "
            r"first paired by predictor, target style and ego initialisation, then "
            r"averaged within each ego-initialisation cluster. Timing excludes "
            r"bypass/no-solve markers and is not end-to-end latency. Acceptance is the "
            r"historical controller decision (including accepted SUBOPTIMAL results), "
            r"not a feasibility certificate. The exact sign-flip value is a "
            r"small-$n$ sensitivity analysis, not confirmatory inference.}"
        ),
        r"\label{tab:supervisor-feedback-paired-cost-acceptance}",
    ]
    if raw_status.get("status") != "pass":
        lines.extend(
            (
                r"\begin{tabular}{@{}l@{}}",
                r"\toprule",
                (
                    r"Not evaluated: hash-validated raw execution logs are required "
                    r"for attempted-solve-only paired effects. \\"
                ),
                r"\bottomrule",
                r"\end{tabular}",
                r"\end{table}",
            )
        )
        return "\n".join(lines) + "\n"

    def indexed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
        return {str(row["contrast"]): row for row in rows}

    cost_by_contrast = indexed(cost_contrasts)
    acceptance_by_contrast = indexed(acceptance_contrasts)
    expected = {f"adaptive_minus_{policy}" for policy in FIXED_POLICIES}
    if set(cost_by_contrast) != expected or set(acceptance_by_contrast) != expected:
        raise ValueError("Corrected paired SF2 table requires all three fixed-policy contrasts")

    lines.extend(
        (
            r"\resizebox{\linewidth}{!}{%",
            r"\begin{tabular}{@{}lllrrrr@{}}",
            r"\toprule",
            (
                r"Comparator & Endpoint & Init $n$ & Mean $\Delta$ & Init range "
                r"& Init signs ($-/0/+$) & $p_{\mathrm{sens}}$ \\"
            ),
            r"\midrule",
        )
    )
    for policy in FIXED_POLICIES:
        contrast = f"adaptive_minus_{policy}"
        for endpoint, row, scale, unit in (
            ("Recorded solve P95", cost_by_contrast[contrast], 1000.0, "ms"),
            (
                "Fallback/nonacceptance",
                acceptance_by_contrast[contrast],
                100.0,
                "pp",
            ),
        ):
            n = int(row["independent_init_clusters"])
            negative = int(row["cluster_negative"])
            zero = int(row["cluster_zero"])
            positive = int(row["cluster_positive"])
            if negative + zero + positive != n:
                raise ValueError("SF2 cluster sign counts do not sum to init n")
            mean = scale * finite_float(row["cluster_mean_effect"], "cluster mean")
            low = scale * finite_float(row["cluster_minimum_effect"], "cluster minimum")
            high = scale * finite_float(row["cluster_maximum_effect"], "cluster maximum")
            p_value = finite_float(
                row["two_sided_exact_sign_flip_p_descriptive"],
                "descriptive exact sign-flip sensitivity",
            )
            lines.append(
                f"{policy_tex_label(policy)} & {endpoint} ({unit}) & {n} & "
                f"{mean:+.2f} & [{low:+.2f}, {high:+.2f}] & "
                f"{negative}/{zero}/{positive} & {p_value:.4f} \\\\"
            )
    lines.extend((r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table}"))
    return "\n".join(lines) + "\n"


def compact_failure_taxonomy(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "return_status",
        "prediction_valid_any",
        "yield_phase",
        "fallback_schema",
        "supervisor_action_source",
        "supervisor_action_mode",
    )
    grouped: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[tuple(str(event[key]) for key in keys)].append(event)
    rows: list[dict[str, Any]] = []
    for group_key, selected in grouped.items():
        rollouts = {
            (str(event["cell_id"]), int(event["ego_init_id"])) for event in selected
        }
        rows.append(
            {
                **dict(zip(keys, group_key)),
                "failure_events": len(selected),
                "affected_rollouts": len(rollouts),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -int(row["failure_events"]),
            str(row["return_status"]),
            str(row["prediction_valid_any"]),
            str(row["yield_phase"]),
            str(row["fallback_schema"]),
            str(row["supervisor_action_source"]),
            str(row["supervisor_action_mode"]),
        ),
    )


def failure_taxonomy_tex(
    events: Sequence[Mapping[str, Any]], raw_status: Mapping[str, Any]
) -> str:
    lines = [
        r"\begin{table}[p]",
        r"\centering\scriptsize",
        (
            r"\caption{Exact descriptive taxonomy of corrected-R3 attempted-"
            r"fallback/nonaccepted solver events. Raw return status is retained because "
            r"the historical accepted flag is not mathematical optimality or a feasibility "
            r"certificate. Categories transcribe telemetry and are not causal labels.}"
        ),
        r"\label{tab:supervisor-feedback-failure-taxonomy}",
    ]
    if raw_status.get("status") != "pass":
        lines.extend(
            (
                r"\begin{tabular}{@{}l@{}}",
                r"\toprule",
                (
                    r"Not evaluated: the extracted raw R3 snapshot was not supplied; "
                    r"no return status, phase or fallback cause was inferred. \\"
                ),
                r"\bottomrule",
                r"\end{tabular}",
                r"\end{table}",
            )
        )
        return "\n".join(lines) + "\n"

    compact = compact_failure_taxonomy(events)
    if not compact:
        lines.extend(
            (
                r"\begin{tabular}{@{}l@{}}",
                r"\toprule",
                r"No attempted-fallback/nonaccepted solver events were observed. \\",
                r"\bottomrule",
                r"\end{tabular}",
                r"\end{table}",
            )
        )
        return "\n".join(lines) + "\n"
    lines.extend(
        (
            r"\resizebox{\linewidth}{!}{%",
            r"\begin{tabular}{@{}llllllrr@{}}",
            r"\toprule",
            (
                r"Return status & Prediction valid & Yield phase & Fallback schema & "
                r"Supervisor source & Supervisor mode & Events & Rollouts \\"
            ),
            r"\midrule",
        )
    )
    for row in compact:
        lines.append(
            f"{tex_escape(row['return_status'])} & "
            f"{tex_escape(row['prediction_valid_any'])} & "
            f"{tex_escape(row['yield_phase'])} & "
            f"{tex_escape(row['fallback_schema'])} & "
            f"{tex_escape(row['supervisor_action_source'])} & "
            f"{tex_escape(row['supervisor_action_mode'])} & "
            f"{row['failure_events']} & {row['affected_rollouts']} \\\\"
        )
    lines.extend(
        (
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\end{table}",
        )
    )
    return "\n".join(lines) + "\n"


def failure_downstream_tex(
    affected_rollouts: Sequence[Mapping[str, Any]],
    raw_status: Mapping[str, Any],
) -> str:
    lines = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        (
            r"\caption{Canonical downstream outcomes for rollouts containing at least one "
            r"attempted-fallback/nonaccepted solve. Completion and yield entries show failures over "
            r"observed outcomes; separation is the minimum 0.25-m-buffered actual-bounding-"
            r"box distance among affected rollouts. This is a descriptive association, "
            r"not the causal effect of controller nonacceptance.}"
        ),
        r"\label{tab:supervisor-feedback-failure-downstream}",
    ]
    if raw_status.get("status") != "pass":
        lines.extend(
            (
                r"\begin{tabular}{@{}l@{}}",
                r"\toprule",
                r"Not evaluated: hash-validated raw execution logs were not supplied. \\",
                r"\bottomrule",
                r"\end{tabular}",
                r"\end{table}",
            )
        )
        return "\n".join(lines) + "\n"

    lines.extend(
        (
            r"\resizebox{\linewidth}{!}{%",
            r"\begin{tabular}{@{}lrrrrrrrr@{}}",
            r"\toprule",
            (
                r"Policy & Affected & Events & Completion fail/valid & Yield fail/observed "
                r"& Footprint coll. & Native coll. & Min sep. (m) \\"
            ),
            r"\midrule",
        )
    )
    for policy in POLICY_ORDER:
        selected = [
            row for row in affected_rollouts if row["risk_policy"] == policy
        ]
        events = sum(int(row["attempted_fallback_or_nonaccepted_steps"]) for row in selected)
        valid_completion = sum(int(row["completion_valid"]) for row in selected)
        completion_failures = sum(
            int(row["completion_failure"]) for row in selected
        )
        observed_yield = sum(int(row["yield_outcome_observed"]) for row in selected)
        yield_failures = sum(int(row["yield_failure"]) for row in selected)
        footprint_collisions = sum(int(row["footprint_collision"]) for row in selected)
        native_collisions = sum(int(row["native_collision_any"]) for row in selected)
        separations = [
            finite_float(
                row["minimum_footprint_separation_m"],
                "affected-rollout minimum separation",
            )
            for row in selected
        ]
        minimum_separation = min(separations) if separations else None
        lines.append(
            f"{policy_tex_label(policy)} & {len(selected)} & {events} & "
            f"{completion_failures}/{valid_completion} & "
            f"{yield_failures}/{observed_yield} & {footprint_collisions} & "
            f"{native_collisions} & "
            f"{minimum_separation:.3f} \\\\" if minimum_separation is not None else
            f"{policy_tex_label(policy)} & 0 & 0 & 0/0 & 0/0 & 0 & 0 & -- \\\\"
        )
    lines.extend(
        (r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table}")
    )
    return "\n".join(lines) + "\n"


def build(
    matrix_audit_path: Path,
    rollout_outcomes_path: Path,
    output: Path,
    raw_root: Path | None = None,
    snapshot_files_manifest: Path | None = None,
) -> dict[str, Any]:
    matrix, rows, deadlines = load_frozen_rows(
        matrix_audit_path, rollout_outcomes_path
    )
    validate_pairing(rows)

    raw = (
        analyze_raw(
            raw_root,
            rows,
            deadlines,
            snapshot_files_manifest,
        )
        if raw_root is not None
        else not_evaluated_raw(rows, deadlines)
    )
    raw_policy = raw["raw_policy"] if raw["status"] == "pass" else None

    policy_costs = summarize_policy_costs(rows, deadlines, raw_policy)
    cost_pairs = build_pair_rows(
        rows,
        "p95_solve_time_s",
        "legacy_conflated_p95_solve_time_s",
    )
    cost_contrasts = summarize_pair_rows(
        cost_pairs,
        "adaptive_minus_control_legacy_conflated_p95_solve_time_s",
        "s",
    )
    failure_pairs = build_pair_rows(
        rows,
        "solver_failure_fraction",
        "solver_failure_fraction",
    )
    failure_contrasts = summarize_pair_rows(
        failure_pairs,
        "adaptive_minus_control_solver_failure_fraction",
        "fraction",
    )
    nonoptimal_policy = summarize_nonoptimal_policy(rows)
    corrected_cost_pairs: list[dict[str, Any]] = []
    corrected_cost_contrasts: list[dict[str, Any]] = []
    corrected_failure_pairs: list[dict[str, Any]] = []
    corrected_failure_contrasts: list[dict[str, Any]] = []
    if raw["status"] == "pass":
        corrected_rows = raw["corrected_rollout_rows"]
        if any(row["p95_solve_time_s"] is None for row in corrected_rows):
            raise ValueError(
                "Final corrected pairing requires a finite attempted-solve P95 per rollout"
            )
        if any(row["solver_failure_fraction"] is None for row in corrected_rows):
            raise ValueError(
                "Final corrected pairing requires at least one attempted solve per rollout"
            )
        corrected_cost_pairs = build_pair_rows(
            corrected_rows,
            "p95_solve_time_s",
            "attempted_p95_solve_time_s",
        )
        corrected_cost_contrasts = summarize_pair_rows(
            corrected_cost_pairs,
            "adaptive_minus_control_attempted_p95_solve_time_s",
            "s",
        )
        corrected_failure_pairs = build_pair_rows(
            corrected_rows,
            "solver_failure_fraction",
            "attempted_fallback_or_nonaccepted_fraction",
        )
        corrected_failure_contrasts = summarize_pair_rows(
            corrected_failure_pairs,
            "adaptive_minus_control_attempted_fallback_or_nonaccepted_fraction",
            "fraction",
        )

    for row in rows:
        row["raw_validation_status"] = (
            "pass" if raw["status"] == "pass" else "not_evaluated"
        )
    nonoptimal_rollouts = [
        {
            "legacy_aggregate_status": "preliminary_legacy_conflated",
            "cell_id": row["cell_id"],
            "predictor": row["predictor"],
            "risk_policy": row["risk_policy"],
            "target_style": row["target_style"],
            "ego_init_id": row["ego_init_id"],
            "debug_steps": row["debug_steps"],
            "legacy_nonoptimal_steps": row["nonoptimal_steps"],
            "legacy_solver_failure_fraction_all_debug_rows": stable_float(
                row["solver_failure_fraction"]
            ),
            "rollout_affected": int(row["nonoptimal_steps"] > 0),
            "legacy_conflated_per_rollout_p95_solve_time_s": stable_float(
                row["p95_solve_time_s"]
            ),
            "runtime_gate_limit_s": stable_float(row["runtime_gate_limit_s"]),
            "runtime_gate_passed": int(row["runtime_gate_passed"]),
            "raw_validation_status": row["raw_validation_status"],
        }
        for row in rows
    ]

    total_debug = sum(int(row["debug_steps"]) for row in rows)
    total_nonoptimal = sum(int(row["nonoptimal_steps"]) for row in rows)
    deadline_evaluation_status = (
        "evaluated" if raw["status"] == "pass" else "not_evaluated"
    )
    final_evidence_ready = bool(
        raw["status"] == "pass"
        and raw.get("hash_validation_status") == "pass"
        and raw.get("classification_status") == "pass"
        and raw.get("raw_step_identity_status") == "pass"
        and raw.get("telemetry_integrity_status") == "pass"
        and raw.get("no_solver_telemetry_context_steps") == 0
        and raw.get("corrected_latency_status") == "pass"
        and raw.get("corrected_acceptance_status") == "pass"
        and raw.get("failure_downstream_outcome_join_status") == "pass"
        and deadline_evaluation_status == "evaluated"
        and raw["deadline_rows"]
        and all(
            row.get("evaluation_status") == "evaluated"
            for row in raw["deadline_rows"]
        )
    )
    evidence_status = (
        "pass"
        if final_evidence_ready
        else (
            "fail_raw_telemetry_integrity"
            if raw.get("telemetry_integrity_status", "not_evaluated").startswith(
                "fail_"
            )
            else "partial_raw_required"
        )
    )
    raw_taxonomy_status = {
        "status": raw["status"],
        "reason": raw["reason"],
        "expected_canonical_debug_files": len(rows),
        "canonical_debug_files": raw.get("canonical_debug_files"),
        "ignored_noncanonical_debug_files": raw.get("ignored_noncanonical_debug_files"),
        "hash_validation_status": raw.get("hash_validation_status", "not_evaluated"),
        "failure_event_count": len(raw["failure_events"]),
        "failure_taxonomy_rows": len(raw["failure_taxonomy"]),
        "step_classification_status": raw.get(
            "classification_status", "not_evaluated"
        ),
        "raw_step_identity_status": raw.get(
            "raw_step_identity_status", "not_evaluated"
        ),
        "telemetry_integrity_status": raw.get(
            "telemetry_integrity_status", "not_evaluated"
        ),
        "no_solver_telemetry_context_steps": raw.get(
            "no_solver_telemetry_context_steps"
        ),
        "corrected_latency_status": raw.get(
            "corrected_latency_status", "not_evaluated"
        ),
        "corrected_acceptance_status": raw.get(
            "corrected_acceptance_status", "not_evaluated"
        ),
        "failure_downstream_outcome_join_status": raw.get(
            "failure_downstream_outcome_join_status", "not_evaluated"
        ),
        "affected_rollout_outcome_rows": len(raw["affected_rollout_outcomes"]),
        "deadline_evaluation_status": deadline_evaluation_status,
        "deadline_claim_status": "pass" if final_evidence_ready else "not_evaluated",
        "no_cause_inference_without_raw": True,
    }
    summary: dict[str, Any] = {
        "schema_version": "supervisor_feedback_cost_feasibility_v3",
        "status": evidence_status,
        "legacy_aggregate_evidence_status": "preliminary_legacy_conflated",
        "raw_step_classification_status": raw.get(
            "classification_status", "not_evaluated"
        ),
        "raw_step_identity_status": raw.get(
            "raw_step_identity_status", "not_evaluated"
        ),
        "raw_telemetry_integrity_status": raw.get(
            "telemetry_integrity_status", "not_evaluated"
        ),
        "raw_no_solver_telemetry_context_steps": raw.get(
            "no_solver_telemetry_context_steps"
        ),
        "corrected_attempted_latency_status": raw.get(
            "corrected_latency_status", "not_evaluated"
        ),
        "corrected_attempted_acceptance_status": raw.get(
            "corrected_acceptance_status", "not_evaluated"
        ),
        "failure_downstream_outcome_join_status": raw.get(
            "failure_downstream_outcome_join_status", "not_evaluated"
        ),
        "final_evidence_ready": final_evidence_ready,
        "missing_final_requirements": (
            []
            if final_evidence_ready
            else [
                "hash-validated raw execution classification with telemetry-absent contexts separated",
                "unique, strictly increasing step identity within every canonical raw log",
                "finite recorded optimizer-internal attempted-solve timing and deadline evaluation",
                "attempted-solve controller acceptance and bypass accounting",
                "every fallback/nonaccepted event joined to exactly one canonical rollout outcome, with multiple events allowed per rollout",
            ]
        ),
        "source_matrix_schema_version": matrix.get("schema_version"),
        "implementation_version": matrix.get("implementation_version"),
        "observed_rollouts": len(rows),
        "independent_init_clusters": len({int(row["ego_init_id"]) for row in rows}),
        "simulator_control_period_s": deadlines["simulator_control_period_s"],
        "smpc_planning_interval_s": deadlines["smpc_planning_interval_s"],
        "frozen_runtime_gate_s": deadlines["frozen_runtime_gate_s"],
        "deadline_sources": dict(DEADLINE_SOURCES),
        "legacy_total_nonoptimal_steps": total_nonoptimal,
        "legacy_total_debug_steps": total_debug,
        "legacy_pooled_nonoptimal_fraction_descriptive": (
            total_nonoptimal / total_debug if total_debug else 0.0
        ),
        "legacy_affected_rollouts": sum(
            int(row["nonoptimal_steps"]) > 0 for row in rows
        ),
        "policy_cost_summary": policy_costs,
        "legacy_paired_cost_contrasts": cost_contrasts,
        "legacy_nonoptimal_policy_summary": nonoptimal_policy,
        "legacy_paired_solver_failure_contrasts": failure_contrasts,
        "corrected_paired_cost_contrasts": corrected_cost_contrasts,
        "corrected_paired_controller_nonacceptance_contrasts": corrected_failure_contrasts,
        "raw_policy_solver_summary": list(raw["raw_policy"].values()),
        "raw_policy_init_solver_summary": raw["raw_policy_init"],
        "raw_taxonomy_status": raw_taxonomy_status,
        "claim_boundaries": [
            "Frozen 104.24/90.23 ms and +14.01 ms values are preliminary legacy aggregates that conflate rule-bypass zero markers with solves.",
            "Final P50/P95/P99 and deadline counts use actual attempts with finite recorded CasADi solver wall time only; this excludes prediction, controller preprocessing, supervisor logic and CARLA-loop overhead.",
            "The historical optimal flag is reported as controller acceptance because it includes CasADi SUBOPTIMAL solutions selected for execution; it is not mathematical optimality or a feasibility certificate.",
            "Rule bypass is reported separately and enters neither timing nor controller-acceptance denominators.",
            "Non-finite attempted timing is counted separately and never imputed; finite-only exceedance fractions must be read together with non-finite counts.",
            "Simulator steps are diagnostic counts; ego-initialisation clusters are the independent units.",
            "Deadline exceedance and failure-cause taxonomy are not inferred when raw debug logs are absent.",
            "Every fallback/nonaccepted event is joined to canonical completion, yield, physical-separation and collision outcomes; the association is descriptive and does not establish a causal root cause.",
        ],
    }

    output.mkdir(parents=True, exist_ok=True)
    table_specs: list[tuple[str, Sequence[str], Sequence[Mapping[str, Any]]]] = [
        (
            "policy_cost_summary.csv",
            tuple(policy_costs[0]),
            policy_costs,
        ),
        (
            "paired_cost_effects.csv",
            tuple(cost_pairs[0]),
            cost_pairs,
        ),
        (
            "paired_cost_contrasts.csv",
            tuple(cost_contrasts[0]),
            cost_contrasts,
        ),
        (
            "corrected_attempted_cost_effects.csv",
            CORRECTED_COST_PAIR_FIELDS,
            corrected_cost_pairs,
        ),
        (
            "corrected_attempted_cost_contrasts.csv",
            tuple(cost_contrasts[0]),
            corrected_cost_contrasts,
        ),
        (
            "solver_nonoptimal_rollouts.csv",
            NONOPTIMAL_ROLLOUT_FIELDS,
            nonoptimal_rollouts,
        ),
        (
            "solver_nonoptimal_policy_summary.csv",
            tuple(nonoptimal_policy[0]),
            nonoptimal_policy,
        ),
        (
            "paired_solver_failure_effects.csv",
            tuple(failure_pairs[0]),
            failure_pairs,
        ),
        (
            "paired_solver_failure_contrasts.csv",
            tuple(failure_contrasts[0]),
            failure_contrasts,
        ),
        (
            "corrected_attempted_acceptance_effects.csv",
            CORRECTED_FAILURE_PAIR_FIELDS,
            corrected_failure_pairs,
        ),
        (
            "corrected_attempted_acceptance_contrasts.csv",
            tuple(failure_contrasts[0]),
            corrected_failure_contrasts,
        ),
        (
            "raw_step_classification.csv",
            RAW_STEP_CLASSIFICATION_FIELDS,
            raw["step_records"],
        ),
        (
            "raw_policy_solver_summary.csv",
            RAW_POLICY_SOLVER_SUMMARY_FIELDS,
            list(raw["raw_policy"].values()),
        ),
        (
            "raw_policy_init_solver_summary.csv",
            RAW_SOLVER_SUMMARY_FIELDS,
            raw["raw_policy_init"],
        ),
        (
            "deadline_exceedance.csv",
            tuple(raw["deadline_rows"][0]),
            raw["deadline_rows"],
        ),
        (
            "solver_failure_events.csv",
            FAILURE_EVENT_FIELDS,
            raw["failure_events"],
        ),
        (
            "solver_failure_affected_rollout_outcomes.csv",
            AFFECTED_ROLLOUT_OUTCOME_FIELDS,
            raw["affected_rollout_outcomes"],
        ),
        (
            "solver_failure_taxonomy.csv",
            (*FAILURE_TAXONOMY_KEYS, "failure_events", "affected_rollouts", "affected_init_ids", "interpretation_boundary"),
            raw["failure_taxonomy"],
        ),
        (
            "raw_rollout_validation.csv",
            RAW_ROLLOUT_VALIDATION_FIELDS,
            raw["rollout_summaries"],
        ),
    ]
    for filename, fieldnames, table_rows in table_specs:
        atomic_csv(output / filename, fieldnames, table_rows)

    atomic_json(output / "raw_taxonomy_status.json", raw_taxonomy_status)
    atomic_json(output / "analysis_summary.json", summary)
    atomic_text(output / "SUPERVISOR_FEEDBACK_02_REPORT.md", report_markdown(summary))
    latex_artifacts = {
        "supervisor_feedback_02_policy_cost.tex": policy_cost_tex(
            policy_costs, deadlines
        ),
        "supervisor_feedback_02_solver_nonoptimal.tex": solver_nonoptimal_tex(
            nonoptimal_policy,
            raw_policy,
        ),
        "supervisor_feedback_02_failure_taxonomy.tex": failure_taxonomy_tex(
            raw["failure_events"], raw_taxonomy_status
        ),
        "supervisor_feedback_02_failure_downstream.tex": failure_downstream_tex(
            raw["affected_rollout_outcomes"], raw_taxonomy_status
        ),
        "supervisor_feedback_02_paired_cost_acceptance.tex": corrected_paired_cost_acceptance_tex(
            corrected_cost_contrasts,
            corrected_failure_contrasts,
            raw_taxonomy_status,
        ),
    }
    for filename, contents in latex_artifacts.items():
        atomic_text(output / filename, contents)

    source_files = {
        "r3_corrected_matrix_audit": matrix_audit_path,
        "r3_rollout_outcomes": rollout_outcomes_path,
        "analysis_script": Path(__file__).resolve(),
    }
    analysis_receipt_path = rollout_outcomes_path.parent / "R3_ANALYSIS_COMPLETE.json"
    if analysis_receipt_path.is_file():
        source_files["r3_analysis_complete"] = analysis_receipt_path
    data_receipt_path = matrix_audit_path.parent / "R3_DATA_COMPLETE.json"
    if data_receipt_path.is_file():
        source_files["r3_data_complete"] = data_receipt_path
    if raw_root is not None and snapshot_files_manifest is not None:
        source_files["r3_snapshot_files_manifest"] = snapshot_files_manifest
    artifact_names = [
        *(filename for filename, _, _ in table_specs),
        "raw_taxonomy_status.json",
        "analysis_summary.json",
        "SUPERVISOR_FEEDBACK_02_REPORT.md",
        *latex_artifacts,
    ]
    manifest = {
        "schema_version": "supervisor_feedback_cost_feasibility_manifest_v3",
        "status": evidence_status,
        "legacy_aggregate_artifact_status": "preliminary_legacy_conflated",
        "final_evidence_ready": final_evidence_ready,
        "raw_telemetry_integrity": {
            "status": raw_taxonomy_status["telemetry_integrity_status"],
            "no_solver_telemetry_context_steps": raw_taxonomy_status[
                "no_solver_telemetry_context_steps"
            ],
            "required_context_steps_for_final": 0,
        },
        "sources": {
            name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for name, path in sorted(source_files.items())
        },
        "raw_debug_hash_validation": {
            "status": raw_taxonomy_status["hash_validation_status"],
            "validated_files": len(raw.get("validated_hashes", [])),
            "validated_file_set_sha256": (
                hashlib.sha256(
                    json.dumps(
                        raw.get("validated_hashes", []),
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                if raw.get("validated_hashes")
                else None
            ),
        },
        "artifacts": {
            name: {"bytes": (output / name).stat().st_size, "sha256": sha256(output / name)}
            for name in artifact_names
        },
    }
    atomic_json(output / "artifact_manifest.json", manifest)

    receipt = {
        "schema_version": "supervisor_feedback_02_complete_v3",
        "status": evidence_status,
        "legacy_aggregate_evidence_status": "preliminary_legacy_conflated",
        "final_evidence_ready": final_evidence_ready,
        "observed_rollouts": len(rows),
        "legacy_total_nonoptimal_steps": total_nonoptimal,
        "legacy_total_debug_steps": total_debug,
        "legacy_affected_rollouts": summary["legacy_affected_rollouts"],
        "raw_step_classification_status": raw.get(
            "classification_status", "not_evaluated"
        ),
        "raw_step_identity_status": raw.get(
            "raw_step_identity_status", "not_evaluated"
        ),
        "raw_telemetry_integrity_status": raw.get(
            "telemetry_integrity_status", "not_evaluated"
        ),
        "raw_no_solver_telemetry_context_steps": raw.get(
            "no_solver_telemetry_context_steps"
        ),
        "corrected_attempted_latency_status": raw.get(
            "corrected_latency_status", "not_evaluated"
        ),
        "corrected_attempted_acceptance_status": raw.get(
            "corrected_acceptance_status", "not_evaluated"
        ),
        "failure_downstream_outcome_join_status": raw.get(
            "failure_downstream_outcome_join_status", "not_evaluated"
        ),
        "corrected_attempted_solve_steps": (
            sum(
                int(row["attempted_solve_steps"])
                for row in raw_policy.values()
            )
            if raw_policy
            else None
        ),
        "corrected_rule_bypass_no_solve_steps": (
            sum(
                int(row["rule_bypass_no_solve_steps"])
                for row in raw_policy.values()
            )
            if raw_policy
            else None
        ),
        "corrected_attempted_fallback_or_nonaccepted_steps": (
            sum(
                int(row["attempted_fallback_or_nonaccepted_steps"])
                for row in raw_policy.values()
            )
            if raw_policy
            else None
        ),
        "legacy_minus_corrected_fallback_or_nonaccepted_steps": (
            total_nonoptimal
            - sum(
                int(row["attempted_fallback_or_nonaccepted_steps"])
                for row in raw_policy.values()
            )
            if raw_policy
            else None
        ),
        "raw_taxonomy_status": raw_taxonomy_status["status"],
        "deadline_evaluation_status": raw_taxonomy_status["deadline_evaluation_status"],
        "deadline_claim_status": raw_taxonomy_status["deadline_claim_status"],
        "artifact_manifest": "artifact_manifest.json",
        "artifact_manifest_sha256": sha256(output / "artifact_manifest.json"),
        "artifacts": [*artifact_names, "artifact_manifest.json"],
        "claim_boundary": (
            "legacy 104.24/90.23 ms, +14.01 ms and 264/17230 are preliminary "
            "bypass-conflated aggregates; final claims require hash-validated execution "
            "classification with telemetry-absent contexts separated, unique monotonic "
            "step IDs, finite recorded optimizer-internal timing, controller acceptance "
            "and downstream-outcome joins. The historical optimal flag includes "
            "controller-accepted SUBOPTIMAL results and is not a feasibility certificate."
        ),
    }
    atomic_json(output / "SUPERVISOR_FEEDBACK_02_COMPLETE.json", receipt)
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-audit", type=Path, default=DEFAULT_MATRIX_AUDIT)
    parser.add_argument("--rollout-outcomes", type=Path, default=DEFAULT_ROLLOUT_OUTCOMES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=None,
        help="Optional directory containing the extracted R3 final snapshot.",
    )
    parser.add_argument(
        "--snapshot-files-manifest",
        type=Path,
        default=None,
        help=(
            "Optional closed-loop snapshot files manifest used to hash-validate raw logs. "
            "When --raw-root is supplied and this option is omitted, the canonical local "
            "R3 files manifest is used."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.raw_root is not None and not args.raw_root.is_dir():
        raise SystemExit(f"--raw-root is not a directory: {args.raw_root}")
    files_manifest = args.snapshot_files_manifest
    if args.raw_root is not None and files_manifest is None:
        files_manifest = DEFAULT_SNAPSHOT_FILES_MANIFEST
    receipt = build(
        args.matrix_audit,
        args.rollout_outcomes,
        args.output_dir,
        raw_root=args.raw_root,
        snapshot_files_manifest=files_manifest,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
