#!/usr/bin/env python3
"""Integrity-first analysis for the SF4 behavioural-authority ablation.

The independent unit is the ego-initialisation block, never a simulation
step.  Raw evidence is hash-checked before any outcome is read.  Scientific
adverse outcomes (collision, controller fallback/non-acceptance, yield failure
and noncompletion)
remain observations; they are not treated as infrastructure failures.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import random
import statistics
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from r3_attempt_manager import validate_receipt_attempt_provenance


SCHEMA = "sf4_supervisor_behavioural_authority_analysis_v1"
EXPECTED_INITS = tuple(range(106, 116))
EXPECTED_ROLLOUTS = 80
FPS = 20.0
HORIZON_S = 30.0
STOP_SPEED_MPS = 0.15
RESUME_SPEED_MPS = 0.8
SUSTAINED_STEPS = 3
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_SEED = 20260814
COMMAND_TOLERANCE = 1.0e-8
WALL_TIME_THRESHOLDS_S = (0.050, 0.200, 0.500)
PRE_SOLVER_CANDIDATE_CHANNELS = frozenset({
    "reference_states",
    "reference_inputs",
    "linearization_states",
    "linearization_inputs",
    "heading_cost_weights",
    "yield_reference_active",
    "recovery_reference_active",
    "supervisor_forced_reference_linearization",
})
COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS = frozenset({
    "reference_shaping",
    "supervisor_forced_reference_linearization",
    "lane_entry_heading_cost",
    "rule_smpc_bypass",
    "post_solver_action_and_desired_speed",
    "release_recovery_state",
    "next_control_history",
})
RAW_REQUIRED = (
    "scenario_run_summary.json",
    "scenario_rollout_config.json",
    "smpc_debug_setup.json",
    "prediction_deployment_manifest.json",
    "prediction_dataset/prediction_dataset_config.json",
    "prediction_dataset/prediction_dataset_manifest.json",
    "smpc_debug_steps.jsonl",
    "prediction_dataset/prediction_dataset_raw.jsonl",
    "prediction_dataset/prediction_dataset_labeled.jsonl",
    "scenario_result.pkl",
    "scenario_steps.csv",
)
RAW_OPTIONAL = ("smpc_completion.json",)
OUTCOME_COLUMNS = (
    "failure_penalized_completion_time_s",
    "completion_success",
    "yield_rule_failure",
    "trajectory_inferred_yield_rule_failure",
    "minimum_margin_adjusted_bbox_separation_m",
    "native_collision_any",
    "physical_bbox_overlap_any",
    "margin_adjusted_bbox_violation_any",
    "adverse_collision_any",
    "attempted_fallback_or_nonaccepted_fraction",
    "ego_policy_wall_time_p50_ms",
    "ego_policy_wall_time_p95_ms",
    "ego_policy_wall_time_p99_ms",
    "ego_policy_wall_time_over_50ms_fraction",
    "ego_policy_wall_time_over_200ms_fraction",
    "ego_policy_wall_time_over_500ms_fraction",
    "prediction_wall_time_p50_ms",
    "prediction_wall_time_p95_ms",
    "prediction_wall_time_p99_ms",
    "supervisor_candidate_requested_fraction",
    "supervisor_authority_applied_fraction",
    "candidate_minus_nominal_accel_mean_mps2",
    "candidate_minus_nominal_accel_abs_mean_mps2",
    "actual_minus_nominal_accel_mean_mps2",
    "actual_minus_nominal_accel_abs_mean_mps2",
    "cautious_approach_progress_m",
    "first_stop_distance_to_conflict_m",
    "first_stop_distance_to_designed_stop_m",
    "stopped_duration_s",
    "nominal_conflict_clear_to_actual_path_release_s",
    "actual_path_release_to_sustained_resume_s",
    "buffered_conflict_clear_to_sustained_resume_s",
)
ACTIVE_YIELD_PHASES = {
    "cautious_approach_observed_target",
    "approach_yield_line",
    "hold_yield_line",
}


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object: %s" % path)
    return value


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("%s:%d is not a JSON object" % (path, line_number))
        rows.append(value)
    if not rows:
        raise ValueError("No JSONL rows: %s" % path)
    return rows


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV header is missing: %s" % path)
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError("No CSV data rows: %s" % path)
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def truthy(value: Any) -> bool:
    return value is True or value in (1, "1", "true", "True")


def validated_solver_execution(
    row: Mapping[str, Any], *, effective_bypass: bool
) -> Dict[str, Any]:
    """Fail closed on the factual no-solve/attempt boundary for one debug row."""

    solver = row.get("solver")
    problem = row.get("solver_problem")
    applied = row.get("applied")
    if not isinstance(solver, Mapping) or not solver:
        raise ValueError("solver telemetry is absent or empty")
    if (
        not isinstance(problem, Mapping)
        or not problem
        or problem.get("problem_id") in (None, "")
    ):
        raise ValueError("solver_problem telemetry is absent or lacks problem_id")
    if not isinstance(applied, Mapping) or type(applied.get("is_opt")) is not bool:
        raise ValueError("applied.is_opt must be a factual boolean")
    if type(solver.get("optimal")) is not bool:
        raise ValueError("solver.optimal must be a factual controller-acceptance boolean")
    if solver["optimal"] != applied["is_opt"]:
        raise ValueError("solver.optimal disagrees with applied.is_opt")
    # Presence is required to establish the execution record.  Finiteness is
    # deliberately not an acceptance criterion: non-finite timings remain
    # adverse/missing computational observations and are never allowed to
    # erase a scientifically valid rollout.
    if "solve_time" not in solver:
        raise ValueError("solver.solve_time telemetry is absent")

    solver_bypassed = solver.get("bypassed") is True
    problem_bypassed = problem.get("bypassed") is True
    if effective_bypass:
        solve_time = finite(solver.get("solve_time"))
        if (
            not solver_bypassed
            or not problem_bypassed
            or solve_time is None
            or not math.isclose(solve_time, 0.0, abs_tol=1.0e-12)
        ):
            raise ValueError(
                "effective rule bypass must carry matched solver/problem bypass "
                "markers and a zero-time no-solve record"
            )
        return {
            "classification": "rule_bypass_no_solve",
            "controller_accepted": None,
            "raw_return_status": None,
        }

    if solver_bypassed or problem_bypassed:
        raise ValueError("factual SMPC attempt is marked as bypassed")
    solver_debug = solver.get("debug")
    return_status = (
        solver_debug.get("return_status")
        if isinstance(solver_debug, Mapping)
        else None
    )
    return {
        "classification": (
            "attempted_controller_accepted"
            if applied["is_opt"]
            else "attempted_fallback_or_nonaccepted"
        ),
        "controller_accepted": bool(applied["is_opt"]),
        "raw_return_status": (
            str(return_status).strip()
            if return_status is not None and str(return_status).strip()
            else None
        ),
    }


def supervisor(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("yield_stop_supervisor")
    return value if isinstance(value, Mapping) else {}


def authority_record(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("supervisor_behavioural_authority")
    if isinstance(value, Mapping):
        return value
    nested = supervisor(row).get("supervisor_behavioural_authority")
    return nested if isinstance(nested, Mapping) else {}


def audit_channels_pass(
    audit: Mapping[str, Any], *, mode: str, require_equal_when_off: bool = True
) -> bool:
    if audit.get("status") != "pass" or audit.get("mode") != mode:
        return False
    channels = audit.get("channels")
    if not isinstance(channels, Mapping) or not channels:
        return False
    if mode == "off" and require_equal_when_off:
        for value in channels.values():
            if not isinstance(value, Mapping):
                return False
            if not truthy(value.get("equal")) and not truthy(
                value.get("adaptive_risk_only_exception")
            ):
                return False
    return True


def debug_step(row: Mapping[str, Any]) -> int:
    value = finite(row.get("step"))
    if value is None or not value.is_integer():
        raise ValueError("Debug step is missing or non-integral")
    return int(value)


def debug_speed(row: Mapping[str, Any]) -> Optional[float]:
    state = row.get("vehicle_state")
    return finite(state.get("speed")) if isinstance(state, Mapping) else None


def first_index(
    rows: Sequence[Mapping[str, Any]],
    predicate: Callable[[Mapping[str, Any]], bool],
    start: int = 0,
) -> Optional[int]:
    for index in range(max(0, start), len(rows)):
        if predicate(rows[index]):
            return index
    return None


def first_sustained_index(
    rows: Sequence[Mapping[str, Any]],
    predicate: Callable[[Mapping[str, Any]], bool],
    start: int,
    consecutive: int = SUSTAINED_STEPS,
    end: Optional[int] = None,
) -> Optional[int]:
    run_start = None
    run_length = 0
    stop = len(rows) if end is None else min(len(rows), max(0, end))
    for index in range(max(0, start), stop):
        if predicate(rows[index]):
            if run_start is None:
                run_start = index
            run_length += 1
            if run_length >= consecutive:
                return run_start
        else:
            run_start = None
            run_length = 0
    return None


def elapsed(rows: Sequence[Mapping[str, Any]], left: Optional[int], right: Optional[int]) -> Optional[float]:
    if left is None or right is None:
        return None
    delta = debug_step(rows[right]) - debug_step(rows[left])
    return delta / FPS if delta >= 0 else None


def command(record: Mapping[str, Any], key: str) -> Tuple[float, float, float]:
    value = record.get(key)
    if not isinstance(value, Mapping):
        raise ValueError("Action-filter record lacks %s" % key)
    numbers = tuple(finite(value.get(name)) for name in ("a_des", "df_des", "v_des"))
    if any(number is None for number in numbers):
        raise ValueError("Non-finite command in %s" % key)
    return (float(numbers[0]), float(numbers[1]), float(numbers[2]))


def commands_equal(left: Sequence[float], right: Sequence[float]) -> bool:
    return all(abs(a - b) <= COMMAND_TOLERANCE for a, b in zip(left, right))


def close(left: Any, right: Any, tolerance: float = 1.0e-9) -> bool:
    left_value = finite(left)
    right_value = finite(right)
    return (
        left_value is not None
        and right_value is not None
        and abs(left_value - right_value) <= tolerance
    )


def validate_contract_matrix(contract: Mapping[str, Any]) -> None:
    expected_cells = {
        ("B1", policy, style, mode)
        for policy in ("adaptive", "fixed_medium")
        for style in ("assertive", "reactive")
        for mode in ("on", "off")
    }
    cells = contract.get("cells") or []
    observed_cells = {
        (
            item.get("predictor"), item.get("risk_policy"),
            item.get("target_style"), item.get("supervisor_authority_mode"),
        )
        for item in cells if isinstance(item, Mapping)
    }
    if len(cells) != 8 or observed_cells != expected_cells:
        raise ValueError("SF4 contract does not contain the exact eight-cell factorial")
    expected_keys = {
        (init_id, predictor, policy, style, mode)
        for init_id in EXPECTED_INITS
        for predictor, policy, style, mode in expected_cells
    }
    order = contract.get("execution_order") or []
    observed_keys = {
        (
            int(item.get("ego_init_id", -1)), item.get("predictor"),
            item.get("risk_policy"), item.get("target_style"),
            item.get("supervisor_authority_mode"),
        )
        for item in order if isinstance(item, Mapping)
    }
    if len(order) != EXPECTED_ROLLOUTS or observed_keys != expected_keys:
        raise ValueError("SF4 execution order is not the complete 8-cell x 10-init Cartesian product")
    cell_identity = {
        (item.get("predictor"), item.get("risk_policy"), item.get("target_style"), item.get("supervisor_authority_mode")): item.get("cell_id")
        for item in cells
    }
    for item in order:
        key = (
            item.get("predictor"), item.get("risk_policy"),
            item.get("target_style"), item.get("supervisor_authority_mode"),
        )
        if item.get("cell_id") != cell_identity.get(key):
            raise ValueError("SF4 execution-order cell identity drift")


def validate_rollout_controls(
    item: Mapping[str, Any],
    scenario_dir: Path,
    summary: Mapping[str, Any],
    setup: Mapping[str, Any],
    rollout: Mapping[str, Any],
    deployment: Mapping[str, Any],
    dataset_config: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    failures = []
    init_id = int(item["ego_init_id"])
    policy = str(item["risk_policy"])
    style = str(item["target_style"])
    mode = str(item["supervisor_authority_mode"])
    expected_profile = contract["risk_profiles"][policy]
    expected_style = contract["target_styles_runtime"][style]
    scenario_contract = contract["scenario"]
    if (
        not str((summary.get("extra") or {}).get("map", "")).endswith("Town05")
        or not close(summary.get("carla_fps"), scenario_contract["fps"])
        or int(summary.get("max_iters", -1)) != int(scenario_contract["max_iters"])
    ):
        failures.append("summary_map_fps_or_horizon")
    if rollout.get("schema_version") != "scenario_rollout_config_v2":
        failures.append("rollout_config_schema")
    carla = rollout.get("carla_params") or {}
    if (
        carla.get("map_str") != "Town05"
        or not close(carla.get("fps"), 20)
        or carla.get("side_of_road") != "right"
        or carla.get("traffic_control") != "unsignalised"
        or carla.get("priority_rule") != "turning_gives_way_to_oncoming_straight"
        or carla.get("terminate_on_collision") is not True
    ):
        failures.append("effective_carla_conditions")

    provenance = rollout.get("execution_provenance") or {}
    init_source = provenance.get("ego_init_source") or {}
    scenario_source = provenance.get("scenario_source") or {}
    tuning_source = provenance.get("tuning_source") or {}
    expected_init = contract["init_values"][str(init_id)]
    expected_init_hash = contract["hashes"]["init_files"][str(init_id)]
    expected_tuning_hash = contract["hashes"]["supervisor_authority_tuning"][mode]
    if (
        provenance.get("schema_version") != "carla_rollout_execution_provenance_v1"
        or init_source.get("sha256") != expected_init_hash
        or init_source.get("parsed_values") != expected_init
        or scenario_source.get("sha256") != scenario_contract["source_sha256"]
        or provenance.get("tuning_applied") is not True
        or tuning_source.get("sha256") != expected_tuning_hash
    ):
        failures.append("source_or_init_provenance")
    expected_policy_config = "smpc_var_risk" if policy == "adaptive" else "smpc_fixed_risk"
    expected_adaptive = contract["adaptive_parameters"] if policy == "adaptive" else {}
    if (
        provenance.get("ego_policy_config") != expected_policy_config
        or provenance.get("risk_profile") != expected_profile
        or provenance.get("target_style") != expected_style
        or (provenance.get("adaptive_risk_config") or {}) != expected_adaptive
        or (provenance.get("reactive_config") or {}) != contract["reactive_parameters"]
    ):
        failures.append("treatment_provenance")
    prediction = provenance.get("prediction") or {}
    if (
        prediction.get("protocol_id") != contract["prediction_protocol_id"]
        or prediction.get("cell_id") != item["cell_id"]
        or prediction.get("ego_policy_label") != policy
        or prediction.get("git_commit") != contract["git_commit"]
        or prediction.get("logging_enabled") is not True
        or int(prediction.get("logging_stride", -1)) != 1
        or int(prediction.get("logging_horizon", -1)) != 10
        or not prediction.get("model_weights_argument")
        or not prediction.get("model_anchors_argument")
        or not prediction.get("model_calibration_argument")
    ):
        failures.append("prediction_execution_provenance")

    effective = rollout.get("effective_runtime_vehicle_params")
    if not isinstance(effective, list):
        failures.append("effective_vehicle_params_missing")
        effective = []
    by_role = {
        value.get("role"): value
        for value in effective
        if isinstance(value, Mapping) and value.get("role") in ("ego", "target")
    }
    ego = by_role.get("ego") or {}
    target = by_role.get("target") or {}
    if (
        not close(ego.get("init_speed"), expected_init["init_speed"])
        or not close(ego.get("start_longitudinal_offset"), expected_init["start_longitudinal_offset"])
        or ego.get("risk_profile") != expected_profile
        or ego.get("smpc_config") != ("var_risk" if policy == "adaptive" else "fixed_risk")
        or (ego.get("adaptive_risk_config") or {}) != expected_adaptive
        or ego.get("yield_supervisor_behavioural_authority_mode") != mode
        or ego.get("yield_post_solver_action_filter_mode") != "apply"
        or ego.get("yield_rule_smpc_bypass_enabled") is not True
        or ego.get("yield_supervisor_mode") != "reduced_intervention"
    ):
        failures.append("effective_ego_treatment")
    target_conditions = contract["target_conditions"]
    if (
        target.get("target_style") != expected_style
        or target.get("policy_type") != ("defensive_reactive" if style == "reactive" else "straight")
        or not close(target.get("init_speed"), target_conditions["init_speed_mps"])
        or not close(target.get("nominal_speed"), target_conditions["nominal_speed_mps"])
        or not close(target.get("start_longitudinal_offset"), target_conditions["start_longitudinal_offset_m"])
    ):
        failures.append("effective_target_treatment")

    if (
        setup.get("risk_profile") != expected_profile
        or bool(setup.get("fixed_risk")) != (policy != "adaptive")
    ):
        failures.append("debug_setup_risk")
    setup_supervisor = setup.get("yield_stop_supervisor") or {}
    setup_filter = setup_supervisor.get("post_solver_action_filter") or {}
    setup_authority = setup_supervisor.get("behavioural_authority") or {}
    expected_effective_filter = "apply" if mode == "on" else "monitor_only"
    if (
        setup_supervisor.get("mode") != "reduced_intervention"
        or setup_supervisor.get("rule_smpc_bypass_enabled") is not True
        or setup_authority.get("mode") != mode
        or bool(setup_authority.get("authority_enabled")) != (mode == "on")
        or setup_filter.get("configured_mode") != "apply"
        or setup_filter.get("mode") != expected_effective_filter
        or bool(setup_filter.get("authority_enabled")) != (mode == "on")
    ):
        failures.append("debug_setup_behavioural_authority")

    model_artifact = deployment.get("model_artifact") or {}
    calibration_artifact = deployment.get("calibration_artifact") or {}
    anchors_artifact = deployment.get("anchors_artifact") or {}
    if (
        deployment.get("status") != "pass"
        or deployment.get("warmup_passed") not in (True, 1, "true", "True")
        or model_artifact.get("sha256_tree") != contract["hashes"]["b1_model_tree"]
        or calibration_artifact.get("sha256") != contract["hashes"]["b1_calibration"]
        or anchors_artifact.get("sha256") != contract["hashes"]["anchors"]
    ):
        failures.append("b1_deployment_identity")
    metadata = dataset_config.get("dataset_metadata") or {}
    if (
        int(metadata.get("ego_init_id", -1)) != init_id
        or metadata.get("protocol_id") != contract["prediction_protocol_id"]
        or metadata.get("cell_id") != item["cell_id"]
        or metadata.get("ego_policy") != policy
        or metadata.get("target_style") != expected_style
        or metadata.get("map") != "Town05"
        or int(dataset_config.get("stride", -1)) != 1
        or int(dataset_config.get("horizon", -1)) != 10
    ):
        failures.append("prediction_dataset_identity")
    if failures:
        raise ValueError(
            "SF4 control-variable gate failed for %s: %s"
            % (scenario_dir, sorted(set(failures)))
        )


def raw_evidence_hash(scenario_dir: Path) -> str:
    digest = hashlib.sha256()
    for relative in RAW_REQUIRED + RAW_OPTIONAL:
        path = scenario_dir / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(path).encode("ascii") if path.is_file() else b"ABSENT_BY_DESIGN")
        digest.update(b"\n")
    return digest.hexdigest()


def verify_receipt(
    results_dir: Path, item: Mapping[str, Any]
) -> Tuple[Path, Path, Dict[str, Any]]:
    cell = str(item["cell_id"])
    init_id = int(item["ego_init_id"])
    cell_dir = results_dir / cell
    receipt_path = cell_dir / ("SF4_ROLLOUT_%d_COMPLETE.json" % init_id)
    receipt = read_json(receipt_path)
    if (
        receipt.get("schema_version") != "formal_rollout_complete_v1"
        or receipt.get("status") != "pass"
        or receipt.get("stage") != "SF4"
        or receipt.get("cell_id") != cell
        or int(receipt.get("ego_init_id", -1)) != init_id
    ):
        raise ValueError("Invalid SF4 receipt identity: %s" % receipt_path)
    scenario_dir = (cell_dir / str(receipt["scenario_dir"])).resolve()
    if cell_dir.resolve() not in scenario_dir.parents:
        raise ValueError("Receipt scenario escapes its cell: %s" % receipt_path)
    for relative in RAW_REQUIRED:
        path = scenario_dir / relative
        artifact = (receipt.get("critical_artifacts") or {}).get(relative)
        if not path.is_file() or not isinstance(artifact, Mapping):
            raise ValueError("Missing receipt-bound raw artifact: %s" % path)
        if sha256(path) != artifact.get("sha256") or path.stat().st_size != int(artifact.get("bytes", -1)):
            raise ValueError("Raw artifact hash/size drift: %s" % path)
    for relative, artifact in (receipt.get("critical_artifacts") or {}).items():
        path = scenario_dir / relative
        if not path.is_file() or sha256(path) != artifact.get("sha256"):
            raise ValueError("Critical artifact drift: %s" % path)
    if raw_evidence_hash(scenario_dir) != receipt.get("raw_evidence_sha256"):
        raise ValueError("Raw evidence aggregate hash drift: %s" % receipt_path)
    if sha256(scenario_dir / "scenario_run_summary.json") != receipt.get("scenario_summary_sha256"):
        raise ValueError("Scenario summary hash drift: %s" % receipt_path)
    provenance = validate_receipt_attempt_provenance(
        cell_dir=cell_dir,
        cell_id=cell,
        init_id=init_id,
        receipt=receipt,
    )
    receipt["_verified_attempt_provenance"] = {
        "accepted_attempt": provenance["accepted_attempt"],
        "attempts_started": provenance["attempts_started"],
        "infrastructure_retries": provenance["infrastructure_retries"],
    }
    return receipt_path, scenario_dir, receipt


def gate_evaluation(cell_dir: Path, scenario_dir: Path) -> Dict[str, Any]:
    gate_path = cell_dir / "postcarla_trajectory_gate.json"
    gate = read_json(gate_path)
    matches = [
        item for item in (gate.get("evaluations") or [])
        if Path(str(item.get("scenario_dir", ""))).name == scenario_dir.name
    ]
    if len(matches) != 1:
        raise ValueError("Expected one post-CARLA evaluation for %s, got %d" % (scenario_dir, len(matches)))
    value = matches[0]
    if not isinstance(value.get("completion_valid"), bool):
        raise ValueError("Post-CARLA completion outcome is unavailable: %s" % scenario_dir)
    return value


def footprint_margin_pair(
    gate: Mapping[str, Any], margin_m_per_actor: float
) -> Mapping[str, Any]:
    """Return the single ego--target replay record at one frozen margin."""

    sensitivity = gate.get("footprint_margin_sensitivity")
    if not isinstance(sensitivity, Mapping):
        raise ValueError("Post-CARLA footprint-margin sensitivity is unavailable")
    matches = [
        pairs
        for key, pairs in sensitivity.items()
        if finite(key) is not None
        and math.isclose(float(key), margin_m_per_actor, abs_tol=1.0e-12)
    ]
    if len(matches) != 1 or not isinstance(matches[0], list) or len(matches[0]) != 1:
        raise ValueError(
            "Expected one footprint replay pair at %.3f m/actor" % margin_m_per_actor
        )
    pair = matches[0][0]
    if not isinstance(pair, Mapping):
        raise ValueError("Footprint replay pair is not an object")
    observed_margin = finite(pair.get("footprint_margin_m"))
    if observed_margin is None or not math.isclose(
        observed_margin, margin_m_per_actor, abs_tol=1.0e-12
    ):
        raise ValueError("Footprint replay pair has a mismatched per-actor margin")
    return pair


def behavior_metrics(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    entry = first_index(
        rows,
        lambda row: truthy(supervisor(row).get("active"))
        or str(supervisor(row).get("phase") or "") in ACTIVE_YIELD_PHASES,
    )
    # Every downstream clock is conditional on observing a genuine give-way
    # episode.  Searching from rollout step zero when entry is absent can turn
    # an unrelated terminal/goal stop into a fictitious give-way stop and can
    # likewise invent clearance/release clocks from stale status fields.
    if entry is None:
        return {
            "yield_entry_step": None,
            "first_sustained_stop_step": None,
            "nominal_conflict_clear_step": None,
            "actual_path_release_step": None,
            "buffered_conflict_clear_step": None,
            "sustained_resume_step": None,
            "cautious_approach_progress_m": None,
            "first_stop_distance_to_conflict_m": None,
            "first_stop_distance_to_designed_stop_m": None,
            "stopped_duration_s": None,
            "nominal_conflict_clear_to_actual_path_release_s": None,
            "actual_path_release_to_sustained_resume_s": None,
            "buffered_conflict_clear_to_sustained_resume_s": None,
        }
    start = entry
    nominal = first_index(
        rows,
        lambda row: truthy(supervisor(row).get("target_nominally_cleared_conflict")),
        start,
    )

    def released(row: Mapping[str, Any]) -> bool:
        state = supervisor(row)
        recovery = state.get("recovery") if isinstance(state.get("recovery"), Mapping) else {}
        return (
            truthy(state.get("raw_reduced_clear_path_release"))
            or truthy(state.get("reduced_clear_path_release"))
            or truthy(recovery.get("clear_path_release_start"))
            or str(state.get("phase") or "") == "released_recovery"
        )

    release = first_index(rows, released, start)
    # A later goal/terminal stop is not a give-way stop.  The stop clock is
    # therefore defined only on the closed-open interval [entry, release).
    # Without an observed release there is no bounded give-way episode and the
    # stop clock is censored rather than searched to the end of the rollout.
    stop = None
    if release is not None:
        stop = first_sustained_index(
            rows,
            lambda row: debug_speed(row) is not None
            and float(debug_speed(row)) <= STOP_SPEED_MPS,
            start,
            end=release,
        )
    buffered = first_index(
        rows,
        lambda row: truthy(supervisor(row).get("target_cleared_conflict")),
        start,
    )
    resume = None
    if release is not None:
        resume = first_sustained_index(
            rows,
            lambda row: debug_speed(row) is not None and float(debug_speed(row)) >= RESUME_SPEED_MPS,
            release,
        )
    first_stop_distance = None
    stop_line_error = None
    approach_progress = None
    if stop is not None:
        entry_state = supervisor(rows[entry])
        stop_state = supervisor(rows[stop])
        first_stop_distance = finite(stop_state.get("ego_distance_to_conflict"))
        stop_line_error = finite(stop_state.get("ego_distance_to_stop"))
        designed_clearance = finite(stop_state.get("stop_clearance"))
        if designed_clearance is None:
            designed_clearance = finite(stop_state.get("dynamic_stop_clearance"))
        if (
            stop_line_error is None
            and first_stop_distance is not None
            and designed_clearance is not None
        ):
            stop_line_error = first_stop_distance - designed_clearance
        entry_route_s = finite(entry_state.get("ego_route_s"))
        stop_route_s = finite(stop_state.get("ego_route_s"))
        if entry_route_s is not None and stop_route_s is not None:
            approach_progress = stop_route_s - entry_route_s
        else:
            entry_distance = finite(entry_state.get("ego_distance_to_conflict"))
            if entry_distance is not None and first_stop_distance is not None:
                approach_progress = entry_distance - first_stop_distance
    return {
        "yield_entry_step": debug_step(rows[entry]) if entry is not None else None,
        "first_sustained_stop_step": debug_step(rows[stop]) if stop is not None else None,
        "nominal_conflict_clear_step": debug_step(rows[nominal]) if nominal is not None else None,
        "actual_path_release_step": debug_step(rows[release]) if release is not None else None,
        "buffered_conflict_clear_step": debug_step(rows[buffered]) if buffered is not None else None,
        "sustained_resume_step": debug_step(rows[resume]) if resume is not None else None,
        "cautious_approach_progress_m": approach_progress,
        "first_stop_distance_to_conflict_m": first_stop_distance,
        "first_stop_distance_to_designed_stop_m": stop_line_error,
        "stopped_duration_s": elapsed(rows, stop, resume),
        "nominal_conflict_clear_to_actual_path_release_s": elapsed(rows, nominal, release),
        "actual_path_release_to_sustained_resume_s": elapsed(rows, release, resume),
        "buffered_conflict_clear_to_sustained_resume_s": elapsed(rows, buffered, resume),
    }


def wall_time_metrics(
    scenario_steps_path: Path, summary: Mapping[str, Any]
) -> Dict[str, Any]:
    """Validate raw wall-time telemetry and return active-planning diagnostics.

    Every invocation remains in ``scenario_steps.csv``.  The inferential
    summaries use rows for which the ego policy was still active after the
    call, excluding the cheap completion-tail calls that do not execute the
    risk/update/solve/supervisor pipeline.
    """

    rows = read_csv_rows(scenario_steps_path)
    required = {
        "step",
        "ego_policy_run_step_wall_time_s",
        "ego_policy_done_after_step",
        "prediction_pipeline_wall_time_s",
    }
    missing = required - set(rows[0])
    if missing:
        raise ValueError(
            "SF4 server wall-time columns are missing from %s: %s"
            % (scenario_steps_path, sorted(missing))
        )
    steps = []
    active_mask = []
    for row in rows:
        try:
            steps.append(int(row["step"]))
        except (TypeError, ValueError):
            raise ValueError("Invalid scenario step in %s" % scenario_steps_path)
        done_text = str(row.get("ego_policy_done_after_step", "")).strip().lower()
        if done_text not in {"true", "false", "1", "0"}:
            raise ValueError(
                "Invalid ego_policy_done_after_step in %s" % scenario_steps_path
            )
        active_mask.append(done_text in {"false", "0"})
    if any(right <= left for left, right in zip(steps, steps[1:])):
        raise ValueError("Scenario timing steps are not strictly increasing")

    def values(column: str, mask: Sequence[bool]) -> Tuple[List[float], int]:
        finite_values = []
        nonfinite = 0
        for include, row in zip(mask, rows):
            if not include:
                continue
            try:
                value = float(row.get(column, ""))
            except (TypeError, ValueError):
                nonfinite += 1
                continue
            if not math.isfinite(value) or value < 0.0:
                nonfinite += 1
            else:
                finite_values.append(value)
        return finite_values, nonfinite

    all_mask = [True] * len(rows)
    policy_all, policy_all_nonfinite = values(
        "ego_policy_run_step_wall_time_s", all_mask
    )
    policy_active, policy_active_nonfinite = values(
        "ego_policy_run_step_wall_time_s", active_mask
    )
    prediction_all, prediction_all_nonfinite = values(
        "prediction_pipeline_wall_time_s", all_mask
    )
    prediction_active, prediction_active_nonfinite = values(
        "prediction_pipeline_wall_time_s", active_mask
    )
    diagnostics = (summary.get("extra") or {}).get(
        "server_wall_time_diagnostics"
    ) or {}
    if (
        diagnostics.get("schema_version") != "server_wall_time_diagnostics_v1"
        or diagnostics.get("clock") != "time.perf_counter"
        or diagnostics.get("server_side_diagnostic_only") is not True
        or diagnostics.get("deployment_or_real_time_guarantee") is not False
        or diagnostics.get("active_planning_definition")
        != "ego policy.done() is false immediately after run_step"
    ):
        raise ValueError("SF4 server wall-time scope/provenance is invalid")

    def raw_summary(values_s: Sequence[float], nonfinite: int) -> Dict[str, Any]:
        ordered = sorted(values_s)
        result: Dict[str, Any] = {
            "observed_sample_count": len(ordered) + nonfinite,
            "finite_sample_count": len(ordered),
            "nonfinite_sample_count": nonfinite,
        }
        if ordered:
            result.update({
                "mean_s": statistics.fmean(ordered),
                "p50_s": percentile(ordered, 0.50),
                "p95_s": percentile(ordered, 0.95),
                "p99_s": percentile(ordered, 0.99),
                "max_s": max(ordered),
                "over_50ms_fraction": statistics.fmean(
                    float(value > 0.050) for value in ordered
                ),
                "over_200ms_fraction": statistics.fmean(
                    float(value > 0.200) for value in ordered
                ),
                "over_500ms_fraction": statistics.fmean(
                    float(value > 0.500) for value in ordered
                ),
            })
        else:
            for key in (
                "mean_s", "p50_s", "p95_s", "p99_s", "max_s",
                "over_50ms_fraction", "over_200ms_fraction",
                "over_500ms_fraction",
            ):
                result[key] = None
        return result

    blocks = {
        "ego_policy_all_invocations": (policy_all, policy_all_nonfinite),
        "ego_policy_active_planning_invocations": (
            policy_active, policy_active_nonfinite
        ),
        "prediction_all_invocations": (
            prediction_all, prediction_all_nonfinite
        ),
        "prediction_during_ego_active_planning": (
            prediction_active, prediction_active_nonfinite
        ),
    }
    for name, (block_values, block_nonfinite) in blocks.items():
        observed = diagnostics.get(name) or {}
        expected = raw_summary(block_values, block_nonfinite)
        if observed.get("thresholds_ms") != [50.0, 200.0, 500.0]:
            raise ValueError("Wall-time threshold contract drift: %s" % name)
        if int(observed.get("exception_count", -1)) != 0:
            raise ValueError(
                "Accepted SF4 rollout reports a wall-time exception: %s" % name
            )
        for key, expected_value in expected.items():
            observed_value = observed.get(key)
            if expected_value is None:
                if observed_value is not None:
                    raise ValueError("Wall-time summary drift: %s.%s" % (name, key))
            elif key.endswith("count"):
                if int(observed_value) != int(expected_value):
                    raise ValueError("Wall-time summary drift: %s.%s" % (name, key))
            elif not math.isclose(
                float(observed_value), float(expected_value), rel_tol=1.0e-9,
                abs_tol=1.0e-12,
            ):
                raise ValueError("Wall-time summary drift: %s.%s" % (name, key))

    policy_defined = bool(policy_active) and policy_active_nonfinite == 0
    prediction_defined = (
        bool(prediction_active) and prediction_active_nonfinite == 0
    )
    policy_summary = raw_summary(policy_active, policy_active_nonfinite)
    prediction_summary = raw_summary(
        prediction_active, prediction_active_nonfinite
    )
    return {
        "schema_version": "sf4_server_wall_time_rollout_v1",
        "status": (
            "pass" if policy_defined and prediction_defined
            else "partial_nonfinite_or_missing_secondary"
        ),
        "server_side_diagnostic_only": True,
        "deployment_or_real_time_guarantee": False,
        "ego_policy_active_sample_count": (
            len(policy_active) + policy_active_nonfinite
        ),
        "ego_policy_all_invocation_count": (
            len(policy_all) + policy_all_nonfinite
        ),
        "ego_policy_wall_time_nonfinite_count": policy_active_nonfinite,
        "ego_policy_wall_time_exception_count": 0,
        "prediction_active_sample_count": (
            len(prediction_active) + prediction_active_nonfinite
        ),
        "prediction_all_invocation_count": (
            len(prediction_all) + prediction_all_nonfinite
        ),
        "prediction_wall_time_nonfinite_count": prediction_active_nonfinite,
        "prediction_wall_time_exception_count": 0,
        "ego_policy_wall_time_p50_ms": (
            1000.0 * policy_summary["p50_s"] if policy_defined else None
        ),
        "ego_policy_wall_time_p95_ms": (
            1000.0 * policy_summary["p95_s"] if policy_defined else None
        ),
        "ego_policy_wall_time_p99_ms": (
            1000.0 * policy_summary["p99_s"] if policy_defined else None
        ),
        "ego_policy_wall_time_over_50ms_fraction": (
            policy_summary["over_50ms_fraction"] if policy_defined else None
        ),
        "ego_policy_wall_time_over_200ms_fraction": (
            policy_summary["over_200ms_fraction"] if policy_defined else None
        ),
        "ego_policy_wall_time_over_500ms_fraction": (
            policy_summary["over_500ms_fraction"] if policy_defined else None
        ),
        "prediction_wall_time_p50_ms": (
            1000.0 * prediction_summary["p50_s"]
            if prediction_defined else None
        ),
        "prediction_wall_time_p95_ms": (
            1000.0 * prediction_summary["p95_s"]
            if prediction_defined else None
        ),
        "prediction_wall_time_p99_ms": (
            1000.0 * prediction_summary["p99_s"]
            if prediction_defined else None
        ),
    }


def analyze_rollout(
    results_dir: Path, item: Mapping[str, Any], contract: Mapping[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    receipt_path, scenario_dir, receipt = verify_receipt(results_dir, item)
    summary = read_json(scenario_dir / "scenario_run_summary.json")
    setup = read_json(scenario_dir / "smpc_debug_setup.json")
    rollout = read_json(scenario_dir / "scenario_rollout_config.json")
    deployment = read_json(scenario_dir / "prediction_deployment_manifest.json")
    dataset_config = read_json(
        scenario_dir / "prediction_dataset/prediction_dataset_config.json"
    )
    if summary.get("ran_successfully") is not True:
        raise ValueError("Accepted receipt has unsuccessful summary: %s" % scenario_dir)
    validate_rollout_controls(
        item, scenario_dir, summary, setup, rollout, deployment,
        dataset_config, contract,
    )
    rows = read_jsonl(scenario_dir / "smpc_debug_steps.jsonl")
    wall_time = wall_time_metrics(
        scenario_dir / "scenario_steps.csv", summary
    )
    steps = [debug_step(row) for row in rows]
    if any(right <= left for left, right in zip(steps, steps[1:])):
        raise ValueError("Debug steps are not strictly increasing: %s" % scenario_dir)

    requested: List[float] = []
    applied: List[float] = []
    candidate_delta: List[float] = []
    actual_delta: List[float] = []
    attempted_controller_accepted: List[float] = []
    factual_solver_return_status_counts: Dict[str, int] = {}
    factual_solver_return_status_missing_count = 0
    upstream_reference_requested: List[float] = []
    upstream_heading_requested: List[float] = []
    upstream_linearization_requested: List[float] = []
    bypass_requested: List[float] = []
    bypass_applied: List[float] = []
    factual_solver_attempted: List[float] = []
    any_authority_requested: List[float] = []
    reference_state_delta: List[float] = []
    reference_input_delta: List[float] = []
    heading_weight_intensity: List[float] = []
    linearization_state_delta: List[float] = []
    mode = str(item["supervisor_authority_mode"])
    manipulation_failures = []
    for row in rows:
        bypass = row.get("solver_bypass")
        shadow_bypass = False
        effective_bypass = False
        if not isinstance(bypass, Mapping):
            manipulation_failures.append("solver_bypass_record_missing")
        else:
            shadow_bypass = truthy(bypass.get("shadow_requested"))
            effective_bypass = truthy(bypass.get("enabled"))
            if (
                not truthy(bypass.get("configuration_enabled"))
                or bypass.get("authority_mode") != mode
                or not truthy(bypass.get("authority_gated"))
                or not truthy(bypass.get("off_always_executes_solver"))
                or (mode == "on" and effective_bypass != shadow_bypass)
                or (mode == "off" and effective_bypass)
            ):
                manipulation_failures.append("solver_bypass_authority_semantics")
            bypass_requested.append(float(shadow_bypass))
            bypass_applied.append(float(effective_bypass))
            factual_solver_attempted.append(float(not effective_bypass))
        state = supervisor(row)
        record = state.get("post_solver_action_filter")
        if not isinstance(record, Mapping):
            applied_record = row.get("applied")
            record = applied_record.get("post_solver_action_filter") if isinstance(applied_record, Mapping) else None
        if not isinstance(record, Mapping):
            manipulation_failures.append("action_filter_record_missing")
            continue
        expected_filter_mode = "apply" if mode == "on" else "monitor_only"
        if record.get("mode") != expected_filter_mode:
            manipulation_failures.append("action_filter_mode_mismatch")
        nominal = command(record, "nominal_solver_command")
        candidate = command(record, "supervisor_candidate_command")
        actual = command(record, "actual_command")
        should_apply = mode == "on"
        if truthy(record.get("authority_enabled")) != should_apply:
            manipulation_failures.append("authority_flag_mismatch")
        if should_apply and not commands_equal(actual, candidate):
            manipulation_failures.append("authority_on_actual_not_candidate")
        if not should_apply and not commands_equal(actual, nominal):
            manipulation_failures.append("authority_off_actual_not_nominal")
        is_requested = truthy(record.get("intervention_requested"))
        is_applied = truthy(record.get("intervention_applied"))
        if is_requested != (not commands_equal(candidate, nominal)):
            manipulation_failures.append("intervention_requested_flag_mismatch")
        if is_applied != (should_apply and is_requested):
            manipulation_failures.append("intervention_applied_flag_mismatch")
        requested.append(float(is_requested))
        applied.append(float(is_applied))
        candidate_delta.append(candidate[0] - nominal[0])
        actual_delta.append(actual[0] - nominal[0])
        authority = authority_record(row)
        if not authority:
            manipulation_failures.append("behavioural_authority_record_missing")
            continue
        if (
            authority.get("schema_version")
            != "supervisor_behavioural_authority_step_v1"
            or authority.get("mode") != mode
            or truthy(authority.get("authority_enabled")) != (mode == "on")
            or not truthy(authority.get("interaction_estimator_computed"))
            or authority.get("rule_smpc_bypass_configured") is not True
            or authority.get("allowed_solver_influence_when_off")
            != ["adaptive_risk_allocation"]
            or not truthy(authority.get("shadow_state_isolated"))
        ):
            manipulation_failures.append("behavioural_authority_semantics")
        implementation = authority.get("implementation_manipulation_gate") or {}
        estimator_state = authority.get("interaction_risk_estimator_state") or {}
        bypass_channel = authority.get("rule_smpc_bypass_channel") or {}
        if (
            implementation.get("status") != "pass"
            or not truthy(implementation.get("shadow_state_isolated"))
            or set(implementation.get("candidate_channels_computed") or [])
            != COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS
            or estimator_state.get("permitted_factual_use_when_authority_off")
            != ["adaptive_risk_allocation"]
            or estimator_state.get("nonrisk_solver_or_control_use_when_authority_off")
            is not False
            or not truthy(estimator_state.get("separate_from_shadow_behaviour_state"))
            or not truthy(bypass_channel.get("configured"))
            or truthy(bypass_channel.get("shadow_requested"))
            != truthy(bypass.get("shadow_requested"))
            or truthy(bypass_channel.get("effective"))
            != truthy(bypass.get("enabled"))
            or not truthy(bypass_channel.get("authority_gated"))
            or not truthy(bypass_channel.get("off_always_executes_solver"))
        ):
            manipulation_failures.append("implementation_manipulation_gate")
        reference_audit = authority.get("reference_and_solver_input_audit") or {}
        solver_input_audit = reference_audit.get("solver_input_authority") or {}
        candidate_application_audit = (
            reference_audit.get("candidate_application_authority") or {}
        )
        post_audit = authority.get("post_action_and_next_state_audit") or {}
        if (
            not audit_channels_pass(reference_audit, mode=mode)
            or not audit_channels_pass(solver_input_audit, mode=mode)
            or not audit_channels_pass(post_audit, mode=mode)
        ):
            manipulation_failures.append("authority_channel_audit")
        candidate_channels = candidate_application_audit.get("channels") or {}
        candidate_channel_records = [
            value
            for value in candidate_channels.values()
            if isinstance(value, Mapping)
        ]
        if (
            candidate_application_audit.get("schema_version")
            != "supervisor_candidate_application_channels_v1"
            or candidate_application_audit.get("mode") != mode
            or candidate_application_audit.get("status") != "pass"
            or truthy(
                candidate_application_audit.get("candidate_equality_required")
            )
            != (mode == "on")
            or len(candidate_channel_records) != len(candidate_channels)
            or set(candidate_channels) != PRE_SOLVER_CANDIDATE_CHANNELS
            or (
                mode == "on"
                and (
                    not candidate_channel_records
                    or not all(
                        truthy(value.get("equal"))
                        for value in candidate_channel_records
                    )
                )
            )
        ):
            manipulation_failures.append("authority_on_candidate_application")
        complete_manifest = (
            authority.get("complete_candidate_channel_manifest") or {}
        )
        complete_channels = complete_manifest.get("channels") or {}
        if (
            complete_manifest.get("schema_version")
            != "complete_supervisor_behavioural_authority_manifest_v1"
            or complete_manifest.get("mode") != mode
            or complete_manifest.get("status") != "pass"
            or set(complete_manifest.get("expected_channels") or [])
            != COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS
            or set(complete_channels)
            != COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS
            or any(
                not isinstance(value, Mapping)
                or value.get("candidate_computed") is not True
                or value.get("authority_assignment_consistent") is not True
                or (
                    mode == "on"
                    and truthy(value.get("applied"))
                    != truthy(value.get("requested"))
                )
                or (
                    mode == "off"
                    and (
                        truthy(value.get("applied"))
                        or value.get("factual_neutral_when_off") is not True
                    )
                )
                for value in complete_channels.values()
            )
        ):
            manipulation_failures.append(
                "complete_behavioural_authority_channel_manifest"
            )
        factual_before = authority.get("factual_behaviour_state_before_solve")
        factual_after = authority.get("factual_behaviour_state_after_action")
        neutral = {
            "yield_stop_seen": False,
            "yield_stop_active_prev": False,
            "yield_recovery_steps_remaining": 0,
            "yield_last_applied_accel": None,
        }
        if mode == "off" and (factual_before != neutral or factual_after != neutral):
            manipulation_failures.append("authority_off_factual_state_not_neutral")
        observed = authority.get("observed_first_stage_activity") or {}
        upstream = authority.get("upstream_shadow_requests") or {}
        post_request = authority.get("post_solver_shadow_request") or {}
        expected_upstream_any = any(
            truthy(upstream.get(key))
            for key in (
                "reference_requested",
                "heading_cost_requested",
                "reference_linearization_requested",
                "rule_smpc_bypass_requested",
            )
        )
        if (
            not truthy(observed.get("scientific_outcome_not_integrity_gate"))
            or truthy(post_request.get("requested")) != is_requested
            or truthy(upstream.get("any_requested")) != expected_upstream_any
            or truthy(observed.get("any_requested"))
            != (expected_upstream_any or is_requested)
        ):
            manipulation_failures.append("first_stage_diagnostic_semantics")
        upstream_reference_requested.append(
            float(truthy(upstream.get("reference_requested")))
        )
        upstream_heading_requested.append(
            float(truthy(upstream.get("heading_cost_requested")))
        )
        upstream_linearization_requested.append(
            float(truthy(upstream.get("reference_linearization_requested")))
        )
        any_authority_requested.append(float(truthy(observed.get("any_requested"))))
        intensity = authority.get("upstream_shadow_intensity") or {}
        reference_state_delta.append(
            float(finite(intensity.get("reference_states_max_abs_delta")) or 0.0)
        )
        reference_input_delta.append(
            float(finite(intensity.get("reference_inputs_max_abs_delta")) or 0.0)
        )
        heading_weight_intensity.append(
            float(finite(intensity.get("heading_cost_max_abs_weight")) or 0.0)
        )
        linearization_state_delta.append(
            float(finite(intensity.get("linearization_states_max_abs_delta")) or 0.0)
        )
        try:
            execution = validated_solver_execution(
                row, effective_bypass=effective_bypass
            )
        except ValueError as exc:
            manipulation_failures.append("solver_execution_boundary:%s" % exc)
            execution = None
        if execution is not None and execution["controller_accepted"] is not None:
            attempted_controller_accepted.append(
                float(bool(execution["controller_accepted"]))
            )
            return_status = execution["raw_return_status"]
            if return_status is None:
                factual_solver_return_status_missing_count += 1
            else:
                label = str(return_status)
                factual_solver_return_status_counts[label] = (
                    factual_solver_return_status_counts.get(label, 0) + 1
                )
    if len(requested) != len(rows):
        manipulation_failures.append("post_action_record_not_on_every_debug_step")
    if len(any_authority_requested) != len(rows):
        manipulation_failures.append("authority_record_not_on_every_debug_step")
    if len(bypass_requested) != len(rows):
        manipulation_failures.append("bypass_record_not_on_every_debug_step")
    if manipulation_failures:
        raise ValueError(
            "SF4 manipulation gate failed for %s: %s"
            % (scenario_dir, sorted(set(manipulation_failures)))
        )

    cell_dir = results_dir / str(item["cell_id"])
    gate = gate_evaluation(cell_dir, scenario_dir)
    summary_extra = summary.get("extra") or {}
    collision_events = summary_extra.get("collision_events")
    if (
        summary_extra.get("collision_telemetry_schema_version")
        != "carla_collision_identity_v2"
        or not isinstance(collision_events, list)
        or int(summary_extra.get("collision_event_count", -1))
        != len(collision_events)
    ):
        raise ValueError("Native CARLA collision telemetry is incomplete: %s" % scenario_dir)
    collision_any = int(bool(collision_events))
    if truthy(summary_extra.get("collision_terminated")) and not collision_any:
        raise ValueError("Native collision termination marker lacks a factual event: %s" % scenario_dir)
    pair_separations = [
        finite(pair.get("min_footprint_separation_m"))
        for pair in (gate.get("pair_safety") or [])
        if isinstance(pair, Mapping)
    ]
    pair_separations = [value for value in pair_separations if value is not None]
    if not pair_separations:
        raise ValueError("No actual-bbox separation outcome: %s" % scenario_dir)
    zero_margin_pair = footprint_margin_pair(gate, 0.0)
    primary_margin_pair = footprint_margin_pair(gate, 0.25)
    physical_bbox_overlap_any = int(truthy(zero_margin_pair.get("footprint_collision")))
    margin_adjusted_bbox_violation_any = int(
        truthy(primary_margin_pair.get("footprint_collision"))
    )
    primary_margin_separation = finite(
        primary_margin_pair.get("min_footprint_separation_m")
    )
    if primary_margin_separation is None or not math.isclose(
        min(pair_separations), primary_margin_separation, abs_tol=1.0e-9
    ):
        raise ValueError("Primary 0.25-m footprint outcome disagrees with pair_safety")
    adverse_collision_any = int(bool(collision_any or physical_bbox_overlap_any))
    completion_path = scenario_dir / "smpc_completion.json"
    completion_step = None
    if completion_path.is_file():
        completion_step = finite(read_json(completion_path).get("step"))
    yield_rules = [
        value for value in (gate.get("yield_rules") or [])
        if isinstance(value, Mapping)
    ]
    fixed_geometry_yield_rules = [
        value for value in (gate.get("fixed_geometry_yield_rules") or [])
        if isinstance(value, Mapping)
    ]
    if len(fixed_geometry_yield_rules) != 1:
        raise ValueError(
            "Expected exactly one route-defined fixed-geometry yield outcome: %s"
            % scenario_dir
        )
    yield_rule_failure = int(
        fixed_geometry_yield_rules[0].get("target_clears_before_ego_enters")
        is not True
    )
    trajectory_inferred_yield_rule_failure = int(
        len(yield_rules) != 1
        or yield_rules[0].get("target_clears_before_ego_enters") is not True
    )
    completion_success = bool(
        gate["completion_valid"] and not adverse_collision_any
        and not yield_rule_failure and completion_step is not None
    )
    completion_time = min(HORIZON_S, float(completion_step) / FPS) if completion_success else HORIZON_S
    behavior = behavior_metrics(rows)
    row = {
        "cell_id": item["cell_id"],
        "predictor": item["predictor"],
        "risk_policy": item["risk_policy"],
        "target_style": item["target_style"],
        "supervisor_authority_mode": mode,
        "ego_init_id": int(item["ego_init_id"]),
        "scenario_dir": str(scenario_dir),
        "debug_steps": len(rows),
        "failure_penalized_completion_time_s": completion_time,
        "completion_success": int(completion_success),
        "yield_rule_failure": yield_rule_failure,
        "trajectory_inferred_yield_rule_failure": (
            trajectory_inferred_yield_rule_failure
        ),
        "minimum_margin_adjusted_bbox_separation_m": primary_margin_separation,
        "native_collision_any": collision_any,
        "physical_bbox_overlap_any": physical_bbox_overlap_any,
        "margin_adjusted_bbox_violation_any": margin_adjusted_bbox_violation_any,
        "adverse_collision_any": adverse_collision_any,
        "factual_solver_attempt_count": len(attempted_controller_accepted),
        "attempted_controller_accepted_count": int(
            sum(attempted_controller_accepted)
        ),
        "attempted_fallback_or_nonaccepted_count": int(
            len(attempted_controller_accepted)
            - sum(attempted_controller_accepted)
        ),
        "attempted_controller_accepted_fraction": (
            statistics.fmean(attempted_controller_accepted)
            if attempted_controller_accepted
            else None
        ),
        "attempted_fallback_or_nonaccepted_fraction": (
            1.0 - statistics.fmean(attempted_controller_accepted)
            if attempted_controller_accepted
            else None
        ),
        "factual_solver_return_status_missing_count": (
            factual_solver_return_status_missing_count
        ),
        "factual_solver_return_status_counts_json": json.dumps(
            factual_solver_return_status_counts,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "ego_policy_active_sample_count": wall_time[
            "ego_policy_active_sample_count"
        ],
        "ego_policy_all_invocation_count": wall_time[
            "ego_policy_all_invocation_count"
        ],
        "ego_policy_wall_time_nonfinite_count": wall_time[
            "ego_policy_wall_time_nonfinite_count"
        ],
        "ego_policy_wall_time_exception_count": wall_time[
            "ego_policy_wall_time_exception_count"
        ],
        "prediction_active_sample_count": wall_time[
            "prediction_active_sample_count"
        ],
        "prediction_all_invocation_count": wall_time[
            "prediction_all_invocation_count"
        ],
        "prediction_wall_time_nonfinite_count": wall_time[
            "prediction_wall_time_nonfinite_count"
        ],
        "prediction_wall_time_exception_count": wall_time[
            "prediction_wall_time_exception_count"
        ],
        **{
            key: wall_time[key]
            for key in OUTCOME_COLUMNS
            if key.startswith("ego_policy_wall_time_")
            or key.startswith("prediction_wall_time_")
        },
        "supervisor_candidate_requested_fraction": statistics.fmean(requested),
        "supervisor_authority_applied_fraction": statistics.fmean(applied),
        "supervisor_any_channel_requested_fraction": statistics.fmean(
            any_authority_requested
        ),
        "upstream_reference_requested_fraction": statistics.fmean(
            upstream_reference_requested
        ),
        "upstream_heading_cost_requested_fraction": statistics.fmean(
            upstream_heading_requested
        ),
        "upstream_reference_linearization_requested_fraction": statistics.fmean(
            upstream_linearization_requested
        ),
        "rule_smpc_bypass_requested_fraction": statistics.fmean(
            bypass_requested
        ),
        "rule_smpc_bypass_applied_fraction": statistics.fmean(bypass_applied),
        "rule_smpc_bypass_requested_count": int(sum(bypass_requested)),
        "rule_smpc_bypass_applied_count": int(sum(bypass_applied)),
        "factual_solver_attempted_fraction": statistics.fmean(
            factual_solver_attempted
        ),
        "upstream_reference_states_max_abs_delta_mean": statistics.fmean(
            reference_state_delta
        ),
        "upstream_reference_inputs_max_abs_delta_mean": statistics.fmean(
            reference_input_delta
        ),
        "upstream_heading_cost_max_abs_weight_mean": statistics.fmean(
            heading_weight_intensity
        ),
        "upstream_linearization_states_max_abs_delta_mean": statistics.fmean(
            linearization_state_delta
        ),
        "candidate_minus_nominal_accel_mean_mps2": statistics.fmean(candidate_delta),
        "candidate_minus_nominal_accel_abs_mean_mps2": statistics.fmean(abs(value) for value in candidate_delta),
        "actual_minus_nominal_accel_mean_mps2": statistics.fmean(actual_delta),
        "actual_minus_nominal_accel_abs_mean_mps2": statistics.fmean(abs(value) for value in actual_delta),
        **behavior,
    }
    evidence = {
        "cell_id": item["cell_id"],
        "ego_init_id": int(item["ego_init_id"]),
        "receipt": str(receipt_path),
        "receipt_sha256": sha256(receipt_path),
        "raw_evidence_sha256": receipt["raw_evidence_sha256"],
        "accepted_attempt": receipt["_verified_attempt_provenance"]["accepted_attempt"],
        "attempts_started": receipt["_verified_attempt_provenance"]["attempts_started"],
        "infrastructure_retries": receipt["_verified_attempt_provenance"]["infrastructure_retries"],
        "attempt_record_sha256": receipt["attempt_record_sha256"],
        "attempt_ledger_sha256": receipt["attempt_ledger_sha256_at_receipt"],
        "postcarla_gate": str(cell_dir / "postcarla_trajectory_gate.json"),
        "postcarla_gate_sha256": sha256(cell_dir / "postcarla_trajectory_gate.json"),
        "server_wall_time_status": wall_time["status"],
    }
    return row, evidence


def mean_defined(values: Iterable[Any]) -> Optional[float]:
    numbers = [finite(value) for value in values]
    if any(value is None for value in numbers) or not numbers:
        return None
    return statistics.fmean(float(value) for value in numbers)


def cluster_dids(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    index = {
        (int(row["ego_init_id"]), str(row["risk_policy"]), str(row["supervisor_authority_mode"]), str(row["target_style"])): row
        for row in rows
    }
    output = []
    for init_id in EXPECTED_INITS:
        record: Dict[str, Any] = {"ego_init_id": init_id}
        for outcome in OUTCOME_COLUMNS:
            means = {}
            for policy in ("adaptive", "fixed_medium"):
                for mode in ("on", "off"):
                    values = [index[(init_id, policy, mode, style)][outcome] for style in ("assertive", "reactive")]
                    means[(policy, mode)] = mean_defined(values)
            if any(value is None for value in means.values()):
                record["did__" + outcome] = None
                record["risk_on__" + outcome] = None
                record["risk_off__" + outcome] = None
                record["authority_adaptive__" + outcome] = None
                record["authority_fixed_medium__" + outcome] = None
            else:
                record["did__" + outcome] = (
                    float(means[("adaptive", "on")])
                    - float(means[("fixed_medium", "on")])
                    - float(means[("adaptive", "off")])
                    + float(means[("fixed_medium", "off")])
                )
                record["risk_on__" + outcome] = (
                    float(means[("adaptive", "on")])
                    - float(means[("fixed_medium", "on")])
                )
                record["risk_off__" + outcome] = (
                    float(means[("adaptive", "off")])
                    - float(means[("fixed_medium", "off")])
                )
                record["authority_adaptive__" + outcome] = (
                    float(means[("adaptive", "on")])
                    - float(means[("adaptive", "off")])
                )
                record["authority_fixed_medium__" + outcome] = (
                    float(means[("fixed_medium", "on")])
                    - float(means[("fixed_medium", "off")])
                )
        output.append(record)
    return output


def exact_sign_flip(values: Sequence[float]) -> float:
    observed = abs(statistics.fmean(values))
    count = 0
    total = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(values)):
        statistic = abs(statistics.fmean(sign * value for sign, value in zip(signs, values)))
        count += int(statistic >= observed - 1.0e-15)
        total += 1
    return count / total


def percentile(sorted_values: Sequence[float], probability: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = probability * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def bootstrap_ci(values: Sequence[float]) -> Tuple[float, float]:
    rng = random.Random(BOOTSTRAP_SEED)
    samples = []
    for _ in range(BOOTSTRAP_REPLICATES):
        samples.append(statistics.fmean(values[rng.randrange(len(values))] for _ in values))
    samples.sort()
    return percentile(samples, 0.025), percentile(samples, 0.975)


def effect_summary(
    cluster_rows: Sequence[Mapping[str, Any]], key: str
) -> Dict[str, Any]:
    values = [finite(row.get(key)) for row in cluster_rows]
    defined = [float(value) for value in values if value is not None]
    entry: Dict[str, Any] = {
        "defined_init_clusters": len(defined),
        "total_init_clusters": len(values),
    }
    if len(defined) == len(EXPECTED_INITS):
        low, high = bootstrap_ci(defined)
        entry.update({
            "mean_effect": statistics.fmean(defined),
            "cluster_bootstrap_95ci": [low, high],
            "exact_two_sided_sign_flip_sensitivity_value": exact_sign_flip(defined),
            "sign_flip_assumption": "symmetric distribution of init-cluster effects",
            "randomisation_inference": False,
        })
    else:
        entry["status"] = "descriptive_only_missing_event_clock"
    return entry


def inference(cluster_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    estimates: Dict[str, Any] = {}
    direct: Dict[str, Any] = {}
    contrasts = {
        "risk_effect_authority_on": "risk_on__",
        "risk_effect_authority_off": "risk_off__",
        "authority_effect_adaptive": "authority_adaptive__",
        "authority_effect_fixed_medium": "authority_fixed_medium__",
    }
    for outcome in OUTCOME_COLUMNS:
        estimates[outcome] = effect_summary(cluster_rows, "did__" + outcome)
        direct[outcome] = {
            label: effect_summary(cluster_rows, prefix + outcome)
            for label, prefix in contrasts.items()
        }
    primary = estimates["failure_penalized_completion_time_s"]
    if primary.get("defined_init_clusters") != 10:
        raise ValueError("Primary DID is not defined for all ten init clusters")
    return {
        "schema_version": "sf4_supervisor_behavioural_authority_cluster_inference_v1",
        "status": "pass",
        "independent_unit": "ego_init_id",
        "primary_estimand": "(adaptive-fixed_medium)_on - (adaptive-fixed_medium)_off",
        "primary_outcome": "failure_penalized_completion_time_s",
        "exact_sensitivity_analysis": (
            "all 2^10 two-sided sign flips of init-cluster effects under a "
            "symmetric cluster-effect assumption; not randomisation inference"
        ),
        "bootstrap": {
            "unit": "complete ego-init block",
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
        },
        "outcomes": estimates,
        "direct_paired_effects": direct,
    }


def activity_cell(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not rows:
        raise ValueError("Cannot summarise an empty SF4 first-stage cell")
    mean = lambda key: statistics.fmean(float(row[key]) for row in rows)
    return {
        "rollouts": len(rows),
        "any_channel_requested_fraction": mean(
            "supervisor_any_channel_requested_fraction"
        ),
        "post_action_requested_fraction": mean(
            "supervisor_candidate_requested_fraction"
        ),
        "authority_applied_fraction": mean(
            "supervisor_authority_applied_fraction"
        ),
        "reference_requested_fraction": mean(
            "upstream_reference_requested_fraction"
        ),
        "heading_cost_requested_fraction": mean(
            "upstream_heading_cost_requested_fraction"
        ),
        "reference_linearization_requested_fraction": mean(
            "upstream_reference_linearization_requested_fraction"
        ),
        "rule_smpc_bypass_requested_fraction": mean(
            "rule_smpc_bypass_requested_fraction"
        ),
        "rule_smpc_bypass_applied_fraction": mean(
            "rule_smpc_bypass_applied_fraction"
        ),
        "factual_solver_attempted_fraction": mean(
            "factual_solver_attempted_fraction"
        ),
        "reference_states_max_abs_delta_mean": mean(
            "upstream_reference_states_max_abs_delta_mean"
        ),
        "reference_inputs_max_abs_delta_mean": mean(
            "upstream_reference_inputs_max_abs_delta_mean"
        ),
        "heading_cost_max_abs_weight_mean": mean(
            "upstream_heading_cost_max_abs_weight_mean"
        ),
        "linearization_states_max_abs_delta_mean": mean(
            "upstream_linearization_states_max_abs_delta_mean"
        ),
        "post_action_accel_abs_delta_mean_mps2": mean(
            "candidate_minus_nominal_accel_abs_mean_mps2"
        ),
        "actual_accel_abs_delta_mean_mps2": mean(
            "actual_minus_nominal_accel_abs_mean_mps2"
        ),
    }


def manipulation_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    by_authority = {
        mode: activity_cell(
            [row for row in rows if row["supervisor_authority_mode"] == mode]
        )
        for mode in ("on", "off")
    }
    by_risk = {
        risk: activity_cell([row for row in rows if row["risk_policy"] == risk])
        for risk in ("adaptive", "fixed_medium")
    }
    by_style = {
        style: activity_cell([row for row in rows if row["target_style"] == style])
        for style in ("assertive", "reactive")
    }
    by_risk_style = {
        "%s__%s" % (risk, style): activity_cell([
            row for row in rows
            if row["risk_policy"] == risk and row["target_style"] == style
        ])
        for risk in ("adaptive", "fixed_medium")
        for style in ("assertive", "reactive")
    }
    by_authority_risk_style = {
        "%s__%s__%s" % (mode, risk, style): activity_cell([
            row for row in rows
            if row["supervisor_authority_mode"] == mode
            and row["risk_policy"] == risk
            and row["target_style"] == style
        ])
        for mode in ("on", "off")
        for risk in ("adaptive", "fixed_medium")
        for style in ("assertive", "reactive")
    }
    full = activity_cell(rows)
    active = bool(full["any_channel_requested_fraction"] > 0.0)
    observed = {
        "status": "active" if active else "inactive_scientific_outcome",
        "full_matrix": full,
        "by_authority": by_authority,
        "by_risk": by_risk,
        "by_style": by_style,
        "by_risk_style": by_risk_style,
        "by_authority_risk_style": by_authority_risk_style,
        "zero_activity_is_integrity_failure": False,
        "zero_activity_triggers_extra_rollouts": False,
        "claim_limit_if_inactive": (
            "Authority assignment was implemented, but this distribution did not "
            "activate any measured supervisor behavioural channel; the data do not "
            "identify masking conditional on an activated intervention."
        ),
    }
    return {
        "schema_version": "sf4_supervisor_behavioural_authority_manipulation_v1",
        "status": "pass",
        "rollouts_checked": len(rows),
        "implementation_manipulation_gate": {
            "status": "pass",
            "rule_smpc_bypass_configured_identically": True,
            "authority_on_applies_eligible_rule_smpc_bypass": True,
            "authority_off_logs_shadow_bypass_but_always_solves": True,
            "authority_record_present_every_step": True,
            "all_upstream_and_downstream_candidates_computed": True,
            "authority_on_applies_candidate_channels": True,
            "authority_off_nonrisk_solver_control_and_next_state_neutral": True,
            "shadow_behaviour_state_isolated": True,
            "interaction_estimator_state_limited_to_adaptive_risk_when_off": True,
            "collision_outcomes_retained": True,
        },
        "observed_first_stage_activity": observed,
    }


def server_wall_time_summary(
    rows: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    metrics = (
        "ego_policy_wall_time_p50_ms",
        "ego_policy_wall_time_p95_ms",
        "ego_policy_wall_time_p99_ms",
        "ego_policy_wall_time_over_50ms_fraction",
        "ego_policy_wall_time_over_200ms_fraction",
        "ego_policy_wall_time_over_500ms_fraction",
        "prediction_wall_time_p50_ms",
        "prediction_wall_time_p95_ms",
        "prediction_wall_time_p99_ms",
    )

    def group(values: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        output: Dict[str, Any] = {"rollouts": len(values)}
        for metric in metrics:
            defined = [finite(row.get(metric)) for row in values]
            numbers = [float(value) for value in defined if value is not None]
            output[metric + "__defined_rollouts"] = len(numbers)
            output[metric + "__rollout_mean"] = (
                statistics.fmean(numbers) if numbers else None
            )
        return output

    by_authority = {
        mode: group([
            row for row in rows
            if row["supervisor_authority_mode"] == mode
        ])
        for mode in ("on", "off")
    }
    nonfinite = {
        "ego_policy_active_nonfinite_samples": int(sum(
            int(row["ego_policy_wall_time_nonfinite_count"]) for row in rows
        )),
        "prediction_active_nonfinite_samples": int(sum(
            int(row["prediction_wall_time_nonfinite_count"]) for row in rows
        )),
        "ego_policy_exceptions": int(sum(
            int(row["ego_policy_wall_time_exception_count"]) for row in rows
        )),
        "prediction_exceptions": int(sum(
            int(row["prediction_wall_time_exception_count"]) for row in rows
        )),
    }
    all_defined = all(
        int(by_authority[mode][metric + "__defined_rollouts"])
        == int(by_authority[mode]["rollouts"])
        for mode in ("on", "off")
        for metric in metrics
    )
    return {
        "schema_version": "sf4_server_wall_time_analysis_v1",
        "status": "pass" if all_defined else "partial_secondary",
        "formal_rollouts": len(rows),
        "clock": "time.perf_counter",
        "scope": (
            "Server-side wall time around ego policy.run_step while the ego "
            "policy remains active after the call; includes risk allocation, "
            "solver update/solve and supervisor, excludes the separately "
            "reported shared prediction pipeline and other-agent policies."
        ),
        "server_side_diagnostic_only": True,
        "deployment_or_real_time_guarantee": False,
        "inferential_unit": "ego_init_id paired cluster, never simulation step",
        "quantile_unit": "within-rollout active-planning invocations",
        "thresholds_ms": [50.0, 200.0, 500.0],
        "nonfinite_and_exception_accounting": nonfinite,
        "by_authority_rollout_means": by_authority,
        "missing_or_nonfinite_timing_never_invalidates_primary_science_or_allows_replacement": True,
    }


def controller_execution_summary(
    rows: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    def group(values: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        attempts = int(sum(int(row["factual_solver_attempt_count"]) for row in values))
        accepted = int(sum(
            int(row["attempted_controller_accepted_count"]) for row in values
        ))
        fallback = int(sum(
            int(row["attempted_fallback_or_nonaccepted_count"]) for row in values
        ))
        missing_status = int(sum(
            int(row["factual_solver_return_status_missing_count"]) for row in values
        ))
        statuses: Dict[str, int] = {}
        for row in values:
            for label, count in json.loads(
                str(row["factual_solver_return_status_counts_json"])
            ).items():
                statuses[str(label)] = statuses.get(str(label), 0) + int(count)
        if attempts != accepted + fallback:
            raise ValueError("Controller-acceptance accounting does not close")
        if attempts != missing_status + sum(statuses.values()):
            raise ValueError("Raw solver return-status accounting does not close")
        return {
            "rollouts": len(values),
            "factual_solver_attempts": attempts,
            "controller_accepted_attempts": accepted,
            "fallback_or_nonaccepted_attempts": fallback,
            "controller_accepted_fraction": (
                accepted / attempts if attempts else None
            ),
            "fallback_or_nonaccepted_fraction": (
                fallback / attempts if attempts else None
            ),
            "raw_solver_return_status_counts": dict(sorted(statuses.items())),
            "raw_solver_return_status_missing_count": missing_status,
        }

    by_cell = {
        "%s__%s__%s" % (mode, risk, style): group([
            row for row in rows
            if row["supervisor_authority_mode"] == mode
            and row["risk_policy"] == risk
            and row["target_style"] == style
        ])
        for mode in ("on", "off")
        for risk in ("adaptive", "fixed_medium")
        for style in ("assertive", "reactive")
    }
    return {
        "schema_version": "sf4_controller_acceptance_and_solver_status_v1",
        "status": "pass",
        "semantic_boundary": (
            "applied.is_opt and solver.optimal denote controller acceptance of "
            "the returned command, including accepted SUBOPTIMAL solutions; "
            "they are not strict optimizer-optimality or feasibility flags"
        ),
        "denominator": (
            "factual SMPC attempts only; effective supervisor rule-bypass "
            "steps are excluded"
        ),
        "raw_return_status_is_separately_reported": True,
        "full_matrix": group(rows),
        "by_authority_risk_style": by_cell,
    }


def direct_effect_rows(
    cluster_rows: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    labels = {
        "risk_effect_authority_on": "risk_on__",
        "risk_effect_authority_off": "risk_off__",
        "authority_effect_adaptive": "authority_adaptive__",
        "authority_effect_fixed_medium": "authority_fixed_medium__",
    }
    return [
        {
            "ego_init_id": int(row["ego_init_id"]),
            "outcome": outcome,
            "contrast": label,
            "effect": row.get(prefix + outcome),
        }
        for row in cluster_rows
        for outcome in OUTCOME_COLUMNS
        for label, prefix in labels.items()
    ]


def tex_escape(value: object) -> str:
    rendered = str(value)
    for old, new in (
        ("\\", r"\textbackslash{}"),
        ("_", r"\_"),
        ("%", r"\%"),
        ("&", r"\&"),
        ("#", r"\#"),
    ):
        rendered = rendered.replace(old, new)
    return rendered


def render_effects_tex(inference_payload: Mapping[str, Any]) -> str:
    outcome = "failure_penalized_completion_time_s"
    entries = [
        ("Primary DID: risk effect on minus risk effect off", inference_payload["outcomes"][outcome]),
        ("Adaptive minus fixed-medium, authority on", inference_payload["direct_paired_effects"][outcome]["risk_effect_authority_on"]),
        ("Adaptive minus fixed-medium, authority off", inference_payload["direct_paired_effects"][outcome]["risk_effect_authority_off"]),
        ("Authority on minus off, adaptive", inference_payload["direct_paired_effects"][outcome]["authority_effect_adaptive"]),
        ("Authority on minus off, fixed-medium", inference_payload["direct_paired_effects"][outcome]["authority_effect_fixed_medium"]),
    ]
    lines = [
        "% Auto-generated by analyze_sf4_supervisor_behavioural_authority.py; do not edit.",
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{SF4 failure-penalised completion-time interaction and direct paired effects. The 30-s penalty applies to a native CARLA collision or zero-margin physical bounding-box overlap, fixed-route-geometry yield failure, or noncompletion; 0.25-m-per-actor safety-margin violation remains a separate diagnostic. Lower is better. The final column is a two-sided exact sign-flip sensitivity value under a symmetric cluster-effect assumption, not randomisation inference.}",
        r"\label{tab:sf4-authority-effects}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Contrast & Effect (s) & 95\% cluster CI & Sign-flip sensitivity \\ ",
        r"\midrule",
    ]
    for label, entry in entries:
        if "mean_effect" not in entry:
            lines.append(r"%s & NA & NA & NA \\" % tex_escape(label))
            continue
        ci = entry["cluster_bootstrap_95ci"]
        lines.append(
            "%s & %.3f & [%.3f, %.3f] & %.4f \\\\" % (
                tex_escape(label),
                float(entry["mean_effect"]),
                float(ci[0]),
                float(ci[1]),
                float(entry["exact_two_sided_sign_flip_sensitivity_value"]),
            )
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    return "\n".join(lines)


def render_behavioural_authority_effects_tex(
    inference_payload: Mapping[str, Any]
) -> str:
    """Render all paper-facing safety/behaviour contrasts at the init-cluster level."""

    metrics = (
        (
            "minimum_margin_adjusted_bbox_separation_m",
            "Minimum 0.25-m/actor margin-adjusted bbox separation",
            "m",
        ),
        ("cautious_approach_progress_m", "Cautious approach progress after yield entry", "m"),
        ("first_stop_distance_to_conflict_m", "First sustained-stop distance to conflict", "m"),
        ("first_stop_distance_to_designed_stop_m", "Signed stop-line error", "m"),
        ("stopped_duration_s", "Stopped duration", "s"),
        (
            "nominal_conflict_clear_to_actual_path_release_s",
            "Nominal clear to actual-path release",
            "s",
        ),
        (
            "actual_path_release_to_sustained_resume_s",
            "Actual-path release to sustained resume",
            "s",
        ),
        (
            "buffered_conflict_clear_to_sustained_resume_s",
            "Buffered clear to sustained resume",
            "s",
        ),
    )
    contrasts = (
        ("DID: risk(on) minus risk(off)", None),
        ("Adaptive minus fixed-medium, authority on", "risk_effect_authority_on"),
        ("Adaptive minus fixed-medium, authority off", "risk_effect_authority_off"),
        ("Authority on minus off, adaptive", "authority_effect_adaptive"),
        ("Authority on minus off, fixed-medium", "authority_effect_fixed_medium"),
    )
    lines = [
        "% Auto-generated by analyze_sf4_supervisor_behavioural_authority.py; do not edit.",
        r"\begin{table*}[p]",
        r"\centering\scriptsize",
        (
            r"\caption{SF4 supervisor-authority effects on safety margin, approach, stopping and "
            r"release behaviour. Each effect is computed within ego initialisation after "
            r"averaging the two target styles; $n/10$ reports complete init clusters. "
            r"Missing event clocks remain censored and are never imputed. Positive values "
            r"mean a larger named endpoint (not universally a benefit); stop--conflict is "
            r"$s_{\mathrm{conflict}}-s_{\mathrm{ego}}$ from the actor/reference point, "
            r"not bumper clearance, and signed stop-line error is "
            r"$s_{\mathrm{stop}}-s_{\mathrm{ego}}$ (positive upstream/short, negative "
            r"after passing the configured stop point). Contrast signs are "
            r"exactly as labelled. Intervals are deterministic 10,000-replicate "
            r"init-cluster bootstrap intervals. Sign-flip values are small-$n$ "
            r"sensitivities under a symmetric cluster-effect assumption, not "
            r"randomisation inference.}"
        ),
        r"\label{tab:sf4-behavioural-authority-effects}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{@{}lllrrrr@{}}",
        r"\toprule",
        r"Endpoint & Contrast & Unit & $n/10$ & Mean effect & 95\% cluster CI & Sign-flip sensitivity \\ ",
        r"\midrule",
    ]
    for metric, metric_label, unit in metrics:
        for contrast_label, direct_key in contrasts:
            entry = (
                inference_payload["outcomes"][metric]
                if direct_key is None
                else inference_payload["direct_paired_effects"][metric][direct_key]
            )
            defined = int(entry["defined_init_clusters"])
            total = int(entry["total_init_clusters"])
            if total != len(EXPECTED_INITS):
                raise ValueError("SF4 behavioural table has an unexpected init denominator")
            prefix = "%s & %s & %s & %d/%d" % (
                tex_escape(metric_label),
                tex_escape(contrast_label),
                unit,
                defined,
                total,
            )
            if "mean_effect" not in entry:
                lines.append(prefix + r" & -- & -- & -- \\")
                continue
            ci = entry["cluster_bootstrap_95ci"]
            lines.append(
                prefix + " & %+.3f & [%+.3f, %+.3f] & %.4f \\\\" % (
                    float(entry["mean_effect"]),
                    float(ci[0]),
                    float(ci[1]),
                    float(entry["exact_two_sided_sign_flip_sensitivity_value"]),
                )
            )
        lines.append(r"\addlinespace")
    lines.extend([r"\bottomrule", r"\end{tabular}}", r"\end{table*}", ""])
    return "\n".join(lines)


def render_wall_time_tex(inference_payload: Mapping[str, Any]) -> str:
    metric_labels = (
        ("ego_policy_wall_time_p50_ms", "Ego policy P50 (ms)"),
        ("ego_policy_wall_time_p95_ms", "Ego policy P95 (ms)"),
        ("ego_policy_wall_time_p99_ms", "Ego policy P99 (ms)"),
        ("ego_policy_wall_time_over_50ms_fraction", "Ego policy >50 ms fraction"),
        ("ego_policy_wall_time_over_200ms_fraction", "Ego policy >200 ms fraction"),
        ("ego_policy_wall_time_over_500ms_fraction", "Ego policy >500 ms fraction"),
        ("prediction_wall_time_p50_ms", "Shared prediction P50 (ms)"),
        ("prediction_wall_time_p95_ms", "Shared prediction P95 (ms)"),
        ("prediction_wall_time_p99_ms", "Shared prediction P99 (ms)"),
    )
    contrasts = (
        ("DID", None),
        ("Risk, authority on", "risk_effect_authority_on"),
        ("Risk, authority off", "risk_effect_authority_off"),
        ("Authority, adaptive", "authority_effect_adaptive"),
        ("Authority, fixed-medium", "authority_effect_fixed_medium"),
    )
    lines = [
        "% Auto-generated by analyze_sf4_supervisor_behavioural_authority.py; do not edit.",
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{SF4 server-side ego-policy and separately timed shared-prediction-pipeline wall-time diagnostics. Each rollout is first reduced to active-planning invocation summaries; inference then uses paired ego-initialisation clusters, never simulation steps. These measurements are machine-specific diagnostics, not an end-to-end deployment or real-time guarantee. Sign-flip values are exploratory sensitivities under a symmetric cluster-effect assumption.}",
        r"\label{tab:sf4-wall-time}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"Metric & Contrast & Effect & 95\% cluster CI & Sign-flip sensitivity \\ ",
        r"\midrule",
    ]
    for metric, metric_label in metric_labels:
        for contrast_label, direct_key in contrasts:
            entry = (
                inference_payload["outcomes"][metric]
                if direct_key is None
                else inference_payload["direct_paired_effects"][metric][direct_key]
            )
            if "mean_effect" not in entry:
                lines.append(
                    "%s & %s & NA & NA & NA \\\\"
                    % (tex_escape(metric_label), tex_escape(contrast_label))
                )
                continue
            ci = entry["cluster_bootstrap_95ci"]
            lines.append(
                "%s & %s & %.6f & [%.6f, %.6f] & %.4f \\\\" % (
                    tex_escape(metric_label),
                    tex_escape(contrast_label),
                    float(entry["mean_effect"]),
                    float(ci[0]),
                    float(ci[1]),
                    float(entry["exact_two_sided_sign_flip_sensitivity_value"]),
                )
            )
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}}",
        r"\end{table*}",
        "",
    ])
    return "\n".join(lines)


def render_controller_execution_tex(summary: Mapping[str, Any]) -> str:
    lines = [
        "% Auto-generated by analyze_sf4_supervisor_behavioural_authority.py; do not edit.",
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{SF4 factual controller-acceptance and raw solver-status accounting. Effective rule-SMPC-bypass steps are excluded from the factual-attempt denominator. Controller accepted means the implementation used the returned command; it is not strict optimizer optimality or feasibility. Raw solver return statuses remain separately enumerated.}",
        r"\label{tab:sf4-controller-acceptance}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lllrrrrl}",
        r"\toprule",
        r"Authority & Risk & Style & Attempts & Accepted & Fallback/nonaccepted & Missing status & Raw return statuses \\ ",
        r"\midrule",
    ]
    cells = summary["by_authority_risk_style"]
    for mode in ("on", "off"):
        for risk in ("adaptive", "fixed_medium"):
            for style in ("assertive", "reactive"):
                value = cells["%s__%s__%s" % (mode, risk, style)]
                statuses = ", ".join(
                    "%s:%d" % (key, int(count))
                    for key, count in value[
                        "raw_solver_return_status_counts"
                    ].items()
                ) or "none"
                lines.append(
                    "%s & %s & %s & %d & %d & %d & %d & %s \\\\" % (
                        tex_escape(mode),
                        tex_escape(risk),
                        tex_escape(style),
                        int(value["factual_solver_attempts"]),
                        int(value["controller_accepted_attempts"]),
                        int(value["fallback_or_nonaccepted_attempts"]),
                        int(value["raw_solver_return_status_missing_count"]),
                        tex_escape(statuses),
                    )
                )
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}}",
        r"\end{table*}",
        "",
    ])
    return "\n".join(lines)


def render_manipulation_tex(manipulation: Mapping[str, Any]) -> str:
    observed = manipulation["observed_first_stage_activity"]
    lines = [
        "% Auto-generated by analyze_sf4_supervisor_behavioural_authority.py; do not edit.",
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{SF4 behavioural-authority implementation check and observed first-stage activity. Ref., head., lin., post and bypass-request are requested-step fractions; bypass-applied and solve are factual fractions. $\Delta r$, $\Delta \ell$ and $\Delta a$ are mean shadow intensities. Zero activity is a retained scientific outcome and never a rerun gate.}",
        r"\label{tab:sf4-authority-manipulation}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lllrrrrrrrrrrr}",
        r"\toprule",
        r"Authority & Risk & Style & Any & Ref. & Head. & Lin. & Post & Byp.-req. & Byp.-app. & Solve & $\Delta r$ & $\Delta \ell$ & $\Delta a$ \\ ",
        r"\midrule",
    ]
    cells = observed["by_authority_risk_style"]
    for mode in ("on", "off"):
        for risk in ("adaptive", "fixed_medium"):
            for style in ("assertive", "reactive"):
                value = cells["%s__%s__%s" % (mode, risk, style)]
                lines.append(
                    "%s & %s & %s & %.3f & %.3f & %.3f & %.3f & %.3f & %.3f & %.3f & %.3f & %.4f & %.4f & %.4f \\\\" % (
                        tex_escape(mode), tex_escape(risk), tex_escape(style),
                        value["any_channel_requested_fraction"],
                        value["reference_requested_fraction"],
                        value["heading_cost_requested_fraction"],
                        value["reference_linearization_requested_fraction"],
                        value["post_action_requested_fraction"],
                        value["rule_smpc_bypass_requested_fraction"],
                        value["rule_smpc_bypass_applied_fraction"],
                        value["factual_solver_attempted_fraction"],
                        value["reference_states_max_abs_delta_mean"],
                        value["linearization_states_max_abs_delta_mean"],
                        value["post_action_accel_abs_delta_mean_mps2"],
                    )
                )
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}}",
        r"\begin{minipage}{0.98\textwidth}\footnotesize",
        "Implementation/manipulation gate: \\textbf{%s}. Observed first-stage activity: \\textbf{%s}. %s" % (
            tex_escape(manipulation["implementation_manipulation_gate"]["status"]),
            tex_escape(observed["status"]),
            tex_escape(
                observed["claim_limit_if_inactive"]
                if observed["status"] == "inactive_scientific_outcome"
                else "At least one measured supervisor behavioural channel was requested; cell-level zeros remain reported."
            ),
        ),
        r"\end{minipage}",
        r"\end{table*}",
        "",
    ])
    return "\n".join(lines)


def report_markdown(
    inference_payload: Mapping[str, Any],
    manipulation: Mapping[str, Any],
    wall_time: Mapping[str, Any],
    controller_execution: Mapping[str, Any],
) -> str:
    primary = inference_payload["outcomes"]["failure_penalized_completion_time_s"]
    ci = primary["cluster_bootstrap_95ci"]
    observed = manipulation["observed_first_stage_activity"]
    by_mode = observed["by_authority"]
    timing_by_mode = wall_time["by_authority_rollout_means"]
    controller_full = controller_execution["full_matrix"]
    return "\n".join(
        [
            "# SF4 Complete Supervisor Behavioural-Authority Ablation",
            "",
            "Status: integrity and implementation/manipulation gates passed for all 80 prespecified rollouts.",
            "",
            "The primary DID is `(adaptive-fixed-medium)_on - (adaptive-fixed-medium)_off`.",
            "Its failure-penalised completion-time estimate is %.6f s (cluster-bootstrap 95%% CI %.6f to %.6f; exact two-sided sign-flip sensitivity value=%.9f under a symmetric cluster-effect assumption; this is not randomisation inference)."
            % (primary["mean_effect"], ci[0], ci[1], primary["exact_two_sided_sign_flip_sensitivity_value"]),
            "The 30 s penalty uses the union of native CARLA collision and zero-margin physical bounding-box overlap, the fixed-route-geometry yield outcome, and noncompletion. The stricter 0.25 m-per-actor margin violation and realised-trajectory yield rule are separate diagnostics and never silently redefine the primary endpoint.",
            "",
            "Authority-on any-channel/post-action/applied fractions: %.6f / %.6f / %.6f. Authority-off any-channel/post-action/applied fractions: %.6f / %.6f / %.6f."
            % (
                by_mode["on"]["any_channel_requested_fraction"],
                by_mode["on"]["post_action_requested_fraction"],
                by_mode["on"]["authority_applied_fraction"],
                by_mode["off"]["any_channel_requested_fraction"],
                by_mode["off"]["post_action_requested_fraction"],
                by_mode["off"]["authority_applied_fraction"],
            ),
            "",
            "Observed first-stage activity status: `%s`. Zero activity is retained as a scientific outcome and never triggers rerunning or replacement." % observed["status"],
            (
                observed["claim_limit_if_inactive"]
                if observed["status"] == "inactive_scientific_outcome"
                else "At least one measured behavioural channel was requested; all risk/style-specific request frequencies and intensities remain reported."
            ),
            "",
            "## Controller acceptance and raw solver status",
            "",
            "Across %d factual SMPC attempts, %d commands were controller-accepted and %d used the fallback/nonaccepted path; %d raw return statuses were unavailable. Effective rule-SMPC-bypass steps are excluded from this denominator. `is_opt` is treated only as controller acceptance (including accepted `SUBOPTIMAL` solutions), never as strict solver optimality or feasibility; raw return statuses are reported separately."
            % (
                controller_full["factual_solver_attempts"],
                controller_full["controller_accepted_attempts"],
                controller_full["fallback_or_nonaccepted_attempts"],
                controller_full["raw_solver_return_status_missing_count"],
            ),
            "",
            "## Server-side computational wall time",
            "",
            "Timing status: `%s`. Ego-policy `run_step` wall time is measured with `time.perf_counter` over active-planning invocations, includes risk allocation, solver update/solve and supervisor, and excludes the separately recorded shared prediction pipeline and other-agent policies." % wall_time["status"],
            "Authority-on/off rollout-mean ego-policy P50: %.6f / %.6f ms; P95: %.6f / %.6f ms; P99: %.6f / %.6f ms. These are server-specific diagnostics, not deployment or real-time guarantees. Paired effects and DID use ego-init clusters, never per-step pseudo-replication."
            % (
                timing_by_mode["on"]["ego_policy_wall_time_p50_ms__rollout_mean"],
                timing_by_mode["off"]["ego_policy_wall_time_p50_ms__rollout_mean"],
                timing_by_mode["on"]["ego_policy_wall_time_p95_ms__rollout_mean"],
                timing_by_mode["off"]["ego_policy_wall_time_p95_ms__rollout_mean"],
                timing_by_mode["on"]["ego_policy_wall_time_p99_ms__rollout_mean"],
                timing_by_mode["off"]["ego_policy_wall_time_p99_ms__rollout_mean"],
            )
            if wall_time["status"] == "pass"
            else "Some wall-time samples were non-finite or missing; counts are reported separately, no timing value is imputed, and the primary scientific outcome remains valid.",
            (
                "Authority-on/off rollout-mean shared-prediction P50: %.6f / %.6f ms; P95: %.6f / %.6f ms; P99: %.6f / %.6f ms. The prediction pipeline is common to both authority arms and is reported separately from `policy.run_step`; their sum is not relabelled as a measured end-to-end loop latency."
                % (
                    timing_by_mode["on"]["prediction_wall_time_p50_ms__rollout_mean"],
                    timing_by_mode["off"]["prediction_wall_time_p50_ms__rollout_mean"],
                    timing_by_mode["on"]["prediction_wall_time_p95_ms__rollout_mean"],
                    timing_by_mode["off"]["prediction_wall_time_p95_ms__rollout_mean"],
                    timing_by_mode["on"]["prediction_wall_time_p99_ms__rollout_mean"],
                    timing_by_mode["off"]["prediction_wall_time_p99_ms__rollout_mean"],
                )
                if wall_time["status"] == "pass"
                else "Shared-prediction wall-time non-finite/missing counts are reported separately and no value is imputed."
            ),
            "",
            "Nominal conflict clear, actual path release and footprint-buffered clear are distinct clocks. Missing exploratory event clocks remain missing; they are never substituted or imputed.",
            "",
            "Collision, controller fallback/non-acceptance, raw solver return status, yield failure and noncompletion remain scientific outcomes. The result concerns the complete application authority of the corrected reduced_intervention rule-aware supervisor inside the frozen B1/estimator/risk/SMPC stack, not the historical full supervisor configuration; prediction, the estimator, adaptive-risk allocation, collision monitoring and SMPC constraints remain present in both arms.",
            "",
        ]
    )


def run(args: argparse.Namespace) -> Dict[str, Any]:
    results_dir = args.results_dir.resolve()
    contract_path = args.contract.resolve()
    prereg_path = args.prereg.resolve()
    output_dir = args.output_dir.resolve()
    contract = read_json(contract_path)
    prereg = read_json(prereg_path)
    if contract.get("schema_version") != "sf4_supervisor_behavioural_authority_run_contract_v1":
        raise ValueError("Unexpected SF4 run-contract schema")
    if prereg.get("schema_version") != "sf4_supervisor_behavioural_authority_prereg_v1":
        raise ValueError("Unexpected SF4 preregistration schema")
    if int(contract.get("expected_rollouts", -1)) != EXPECTED_ROLLOUTS:
        raise ValueError("SF4 contract does not contain 80 rollouts")
    wall_contract = contract.get("server_wall_time_contract") or {}
    if (
        wall_contract.get("schema_version")
        != "server_wall_time_diagnostics_v1"
        or wall_contract.get("clock") != "time.perf_counter"
        or wall_contract.get("inferential_unit")
        != "ego_init_id paired cluster"
        or wall_contract.get("server_side_diagnostic_only") is not True
        or wall_contract.get("deployment_or_real_time_guarantee") is not False
    ):
        raise ValueError("SF4 prospective wall-time contract is absent or stale")
    if (contract.get("hashes") or {}).get("prereg_json") != sha256(prereg_path):
        raise ValueError("Run contract does not bind this preregistration")
    validate_contract_matrix(contract)
    order = contract.get("execution_order") or []

    rows = []
    evidence = []
    for item in order:
        row, item_evidence = analyze_rollout(results_dir, item, contract)
        rows.append(row)
        evidence.append(item_evidence)
    if sorted(int(row["ego_init_id"]) for row in rows)[::8] != list(EXPECTED_INITS):
        raise ValueError("SF4 init blocks are incomplete")

    cluster_rows = cluster_dids(rows)
    direct_rows = direct_effect_rows(cluster_rows)
    inference_payload = inference(cluster_rows)
    manipulation = manipulation_summary(rows)
    wall_time = server_wall_time_summary(rows)
    controller_execution = controller_execution_summary(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    rollout_csv = output_dir / "sf4_rollout_outcomes.csv"
    cluster_csv = output_dir / "sf4_per_init_did.csv"
    direct_csv = output_dir / "sf4_per_init_direct_effects.csv"
    inference_json = output_dir / "sf4_inference.json"
    manipulation_json = output_dir / "sf4_manipulation_checks.json"
    wall_time_json = output_dir / "sf4_server_wall_time_diagnostics.json"
    controller_execution_json = (
        output_dir / "sf4_controller_acceptance_and_solver_status.json"
    )
    input_manifest = output_dir / "sf4_input_manifest.json"
    report = output_dir / "SF4_ANALYSIS_REPORT.md"
    effects_tex = output_dir / "sf4_primary_and_direct_effects.tex"
    behavioural_effects_tex = output_dir / "sf4_behavioural_authority_effects.tex"
    manipulation_tex = (
        output_dir / "sf4_authority_manipulation_and_first_stage.tex"
    )
    wall_time_tex = output_dir / "sf4_computational_wall_time.tex"
    controller_execution_tex = (
        output_dir / "sf4_controller_acceptance_and_solver_status.tex"
    )
    receipt = output_dir / "SF4_ANALYSIS_COMPLETE.json"
    rollout_fields = list(rows[0].keys())
    cluster_fields = ["ego_init_id"] + [
        prefix + outcome
        for outcome in OUTCOME_COLUMNS
        for prefix in (
            "did__",
            "risk_on__",
            "risk_off__",
            "authority_adaptive__",
            "authority_fixed_medium__",
        )
    ]
    write_csv(rollout_csv, rows, rollout_fields)
    write_csv(cluster_csv, cluster_rows, cluster_fields)
    write_csv(
        direct_csv,
        direct_rows,
        ["ego_init_id", "outcome", "contrast", "effect"],
    )
    atomic_json(inference_json, inference_payload)
    atomic_json(manipulation_json, manipulation)
    atomic_json(wall_time_json, wall_time)
    atomic_json(controller_execution_json, controller_execution)
    atomic_json(
        input_manifest,
        {
            "schema_version": "sf4_supervisor_behavioural_authority_analysis_input_manifest_v1",
            "status": "pass",
            "contract": {"path": str(contract_path), "sha256": sha256(contract_path)},
            "preregistration": {"path": str(prereg_path), "sha256": sha256(prereg_path)},
            "rollouts": evidence,
        },
    )
    atomic_text(
        report,
        report_markdown(
            inference_payload, manipulation, wall_time, controller_execution
        ),
    )
    atomic_text(effects_tex, render_effects_tex(inference_payload))
    atomic_text(
        behavioural_effects_tex,
        render_behavioural_authority_effects_tex(inference_payload),
    )
    atomic_text(manipulation_tex, render_manipulation_tex(manipulation))
    atomic_text(wall_time_tex, render_wall_time_tex(inference_payload))
    atomic_text(
        controller_execution_tex,
        render_controller_execution_tex(controller_execution),
    )
    products = [
        rollout_csv,
        cluster_csv,
        direct_csv,
        inference_json,
        manipulation_json,
        wall_time_json,
        controller_execution_json,
        input_manifest,
        report,
        effects_tex,
        behavioural_effects_tex,
        manipulation_tex,
        wall_time_tex,
        controller_execution_tex,
    ]
    completion = {
        "schema_version": "sf4_supervisor_behavioural_authority_analysis_complete_v1",
        "status": "pass",
        "formal_evidence": True,
        "observed_rollouts": len(rows),
        "independent_init_clusters": len(cluster_rows),
        "primary_estimand": inference_payload["primary_estimand"],
        "primary_outcome": inference_payload["primary_outcome"],
        "primary_outcome_definition": {
            "failure_penalty_s": HORIZON_S,
            "collision": (
                "native CARLA collision OR zero-margin actual-bounding-box overlap"
            ),
            "yield": (
                "exactly one fixed route-projected geometry outcome; realised-trajectory "
                "yield rule is sensitivity only"
            ),
            "margin_adjusted_separation": (
                "actual CARLA bounding boxes inflated 0.25 m per actor; a margin "
                "violation alone is not relabelled as physical collision"
            ),
        },
        "integrity_gate": "pass",
        "implementation_manipulation_gate": manipulation[
            "implementation_manipulation_gate"
        ],
        "observed_first_stage_activity": manipulation[
            "observed_first_stage_activity"
        ],
        "solver_execution": {
            "debug_steps": int(sum(int(row["debug_steps"]) for row in rows)),
            "bypass_requested_steps": int(
                sum(int(row["rule_smpc_bypass_requested_count"]) for row in rows)
            ),
            "bypass_applied_steps": int(
                sum(int(row["rule_smpc_bypass_applied_count"]) for row in rows)
            ),
            "factual_solver_attempts": int(
                sum(int(row["factual_solver_attempt_count"]) for row in rows)
            ),
            "controller_accepted_attempts": int(
                sum(
                    int(row["attempted_controller_accepted_count"])
                    for row in rows
                )
            ),
            "fallback_or_nonaccepted_attempts": int(
                sum(
                    int(row["attempted_fallback_or_nonaccepted_count"])
                    for row in rows
                )
            ),
            "controller_acceptance_not_strict_optimizer_feasibility": True,
            "effective_bypass_excluded_from_controller_acceptance_denominator": True,
            "raw_solver_return_status_taxonomy": controller_execution,
        },
        "server_wall_time_diagnostics": wall_time,
        "scientific_direction_never_blocks_completion": True,
        "observed_activity_never_blocks_completion": True,
        "products": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in products
        },
    }
    atomic_json(receipt, completion)
    return completion


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--prereg", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> None:
    payload = run(build_parser().parse_args())
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
