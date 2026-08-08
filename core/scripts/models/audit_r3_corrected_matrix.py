#!/usr/bin/env python3
"""Integrity audit for the prospective corrected R3 closed-loop matrix.

Adverse scientific outcomes (collision, yield failure or completion failure)
are counted, never converted into missing data.  Only provenance, numerical,
coverage and telemetry defects make this audit fail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np


CORRECTED = "corrected_joint_modes_shared_amin_v1"
MODE_MAP = [[0], [1], [2]]
RISK_PROFILES = {
    "fixed_aggressive": "fixed_frontier_aggressive",
    "fixed_medium": "fixed_frontier_medium",
    "fixed_conservative": "fixed_frontier_conservative",
    "adaptive": "adaptive_interaction_severity",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def preflight_semantics(value: dict) -> dict:
    """Exclude nondeterministic GPU float diagnostics from the resume contract."""

    return {
        "status": value.get("status"),
        "selected_variant": value.get("selected_variant"),
        "selected_seed": value.get("selected_seed"),
        "selection_freeze_sha256": value.get("selection_freeze_sha256"),
        "anchors": value.get("anchors"),
        "normalization": value.get("normalization"),
        "warmup_input": value.get("warmup_input"),
        "b1_deployment": (value.get("b1") or {}).get("deployment"),
        "b0_deployment": (value.get("b0") or {}).get("deployment"),
    }


def semantic_sha256(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def valid_hash(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def finite_summary(value: dict) -> bool:
    return int(value.get("nan_count", -1)) == 0 and float(value.get("finite_frac", 0.0)) == 1.0


def finite_numeric(value: object) -> bool:
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return False
    return bool(array.size and np.isfinite(array).all())


def scenario_init_id(name: str) -> int:
    match = re.search(r"_ego_init_(\d+)_", name)
    if not match:
        raise ValueError(f"Cannot parse init ID: {name}")
    return int(match.group(1))


def deployment_failures(deployment: dict, predictor: str, contract: dict) -> list[str]:
    failures = []
    expected = contract["predictors"][predictor]
    if deployment.get("status") != "pass" or deployment.get("warmup_passed") not in (True, 1, "true", "True"):
        failures.append("deployment_warmup")
    if (deployment.get("model_artifact") or {}).get("sha256_tree") != expected["model_sha256_tree"]:
        failures.append("model_hash")
    if (deployment.get("anchors_artifact") or {}).get("sha256") != contract["anchors_sha256"]:
        failures.append("anchors_hash")
    if predictor == "B1":
        if (deployment.get("calibration_artifact") or {}).get("sha256") != expected["calibration_sha256"]:
            failures.append("calibration_hash")
        if deployment.get("calibration_parameters") != expected["calibration_parameters"]:
            failures.append("calibration_parameters")
        if deployment.get("calibration_fit_split") != "val":
            failures.append("calibration_split")
    elif deployment.get("calibration_parameters") != {"temperature": 1.0, "covariance_scale": 1.0}:
        failures.append("b0_not_identity_calibrated")
    return failures


def debug_audit(rows: list[dict], runtime_limit: float) -> tuple[list[str], dict]:
    failures: list[str] = []
    valid_rows = []
    solve_times = []
    distinct_mode_rows = 0
    for row in rows:
        if not any(bool(value) for value in (row.get("prediction_valid") or [])):
            continue
        valid_rows.append(row)
        prediction = row.get("prediction") or {}
        if not all(finite_summary(prediction.get(field) or {}) for field in ("mode_probs", "mus", "sigmas")):
            failures.append("nonfinite_prediction_debug")
        mode = prediction.get("mode_consumption") or {}
        joint = mode.get("joint_modes") or []
        indices = []
        means = []
        covariances = []
        hashes_ok = True
        for joint_mode in joint:
            for consumed in joint_mode.get("per_vehicle") or []:
                indices.append(consumed.get("spatial_mode_index"))
                means.append(consumed.get("mean_sha256"))
                covariances.append(consumed.get("covariance_sha256"))
                hashes_ok = hashes_ok and valid_hash(means[-1]) and valid_hash(covariances[-1])
        if (
            mode.get("implementation_version") != CORRECTED
            or mode.get("mapping") != MODE_MAP
            or indices != [0, 1, 2]
            or not hashes_ok
        ):
            failures.append("mode_consumption")
        elif len(set(means)) == 3 and len(set(covariances)) == 3:
            distinct_mode_rows += 1
        else:
            failures.append("collapsed_consumed_modes")
        if "yield_stop_supervisor" not in row:
            failures.append("supervisor_telemetry")
        if "solver" not in row or "solver_problem" not in row:
            failures.append("solver_telemetry")
        applied = row.get("applied") or {}
        if not all(finite_numeric(applied.get(field)) for field in ("u0", "u_control", "v_des", "control_prev_after")):
            failures.append("applied_control_numerics")
        solve_time = applied.get("solve_time")
        if solve_time is not None and math.isfinite(float(solve_time)):
            solve_times.append(float(solve_time))
    if not valid_rows:
        failures.append("no_valid_prediction_steps")
    p95 = float(np.quantile(solve_times, 0.95)) if solve_times else None
    if p95 is None or p95 > runtime_limit:
        failures.append("runtime_gate")
    return sorted(set(failures)), {
        "debug_steps": len(rows),
        "valid_prediction_steps": len(valid_rows),
        "distinct_consumed_mode_steps": distinct_mode_rows,
        "p95_solve_time_s": p95,
    }


def prediction_audit(rows: list[dict], cell: dict, init_id: int, contract: dict) -> tuple[list[str], dict]:
    failures: list[str] = []
    reactive_active = 0
    expected_style = "defensive_reactive" if cell["target_style"] == "reactive" else "assertive_constant_speed"
    for row in rows:
        if int(row.get("ego_init_id", -1)) != init_id:
            failures.append("prediction_init_id")
        if row.get("cell_id") != cell["cell_id"] or row.get("ego_policy") != cell["risk_policy"]:
            failures.append("prediction_treatment_identity")
        if row.get("protocol_id") != contract["prediction_protocol_id"]:
            failures.append("prediction_protocol")
        if row.get("git_commit") != contract["git_commit"]:
            failures.append("prediction_git_commit")
        if row.get("target_style") != expected_style:
            failures.append("prediction_target_style")
        if not math.isclose(
            float(row.get("target_start_offset_m", math.nan)),
            float(contract["target_offset_m"]),
            abs_tol=1e-12,
        ):
            failures.append("prediction_target_offset")
        if not math.isclose(
            float(row.get("target_speed_mps", math.nan)),
            float(contract["target_speed_mps"]),
            abs_tol=1e-12,
        ):
            failures.append("prediction_target_speed")
        style_parameters = row.get("target_style_parameters") or {}
        if cell["target_style"] == "reactive":
            for key, expected in contract["reactive_parameters"].items():
                if key not in style_parameters or not math.isclose(
                    float(style_parameters[key]), float(expected), abs_tol=1e-12
                ):
                    failures.append("prediction_reactive_parameters")
                    break
        elif not math.isclose(
            float(style_parameters.get("nominal_speed_mps", math.nan)),
            float(contract["target_speed_mps"]),
            abs_tol=1e-12,
        ):
            failures.append("prediction_assertive_parameters")
        probabilities = np.asarray(row.get("mode_probabilities"), dtype=float)
        means = np.asarray(row.get("pred_mus_world"), dtype=float)
        covariances = np.asarray(row.get("pred_sigmas_world"), dtype=float)
        if (
            probabilities.size == 0
            or means.size == 0
            or covariances.size == 0
            or not np.isfinite(probabilities).all()
            or not np.isfinite(means).all()
            or not np.isfinite(covariances).all()
            or (probabilities < 0).any()
            or not math.isclose(float(probabilities.sum()), 1.0, abs_tol=1e-6)
        ):
            failures.append("prediction_numerics")
        else:
            if not np.allclose(covariances, np.swapaxes(covariances, -1, -2), atol=1e-6):
                failures.append("covariance_symmetry")
            elif not bool((np.linalg.eigvalsh(covariances) > 0).all()):
                failures.append("covariance_positive_definite")
        reactive_active += int(bool((row.get("target_reactive_diagnostics") or {}).get("active")))
    if not rows:
        failures.append("no_prediction_samples")
    if cell["target_style"] == "assertive" and reactive_active:
        failures.append("assertive_reactive_activity")
    return sorted(set(failures)), {
        "prediction_samples": len(rows),
        "reactive_active_samples": reactive_active,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--contract-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    root = args.results_dir.resolve()
    contract_path = args.contract_json.resolve()
    contract = read_json(contract_path)
    if contract.get("status") != "frozen" or contract.get("implementation_version") != CORRECTED:
        raise ValueError("R3 contract is not a frozen corrected-v1 contract")

    failures: list[str] = []
    expected_inits = set(int(value) for value in contract["ego_init_ids"])
    expected_keys = {
        (cell["predictor"], cell["risk_policy"], cell["target_style"], init_id)
        for cell in contract["cells"]
        for init_id in expected_inits
    }
    order = contract.get("execution_order") or []
    order_keys = {
        (item["predictor"], item["risk_policy"], item["target_style"], int(item["ego_init_id"]))
        for item in order
    }
    if len(order) != len(order_keys) or order_keys != expected_keys:
        failures.append("matrix:execution_order_coverage_or_duplicates")
    block_size = len(contract["cells"])
    for block_index in range(len(expected_inits)):
        block = order[block_index * block_size : (block_index + 1) * block_size]
        block_inits = {int(item["ego_init_id"]) for item in block}
        block_cells = {(item["predictor"], item["risk_policy"], item["target_style"]) for item in block}
        expected_cells = {(item["predictor"], item["risk_policy"], item["target_style"]) for item in contract["cells"]}
        if len(block_inits) != 1 or block_cells != expected_cells:
            failures.append(f"matrix:block_randomisation:{block_index}")
    if len(expected_keys) != int(contract["expected_rollouts"]):
        failures.append("matrix:contract_rollout_count")

    for source_key, relative in (contract.get("frozen_source_files") or {}).items():
        path = root / relative["path"] if relative.get("scope") == "results" else Path(relative["path"])
        if not path.is_file() or sha256(path) != relative["sha256"]:
            failures.append(f"matrix:frozen_source:{source_key}")
    for init_id in expected_inits:
        init_path = root / "_frozen_inits_101_105" / f"ego_init_{init_id}.json"
        if not init_path.is_file() or sha256(init_path) != contract["init_sha256"].get(str(init_id)):
            failures.append(f"matrix:init_sha256:{init_id}")
    preflight_path = root / "r3_deployment_preflight.json"
    if (
        not preflight_path.is_file()
        or semantic_sha256(preflight_semantics(read_json(preflight_path)))
        != contract.get("preflight_semantic_sha256")
    ):
        failures.append("matrix:preflight_semantics")

    evaluations = []
    observed_keys = set()
    geometry_by_init: dict[int, list[np.ndarray]] = defaultdict(list)
    total_native_collisions = 0
    total_footprint_collisions = 0
    total_yield_failures = 0
    total_completion_failures = 0
    total_valid_prediction_steps = 0
    max_p95 = 0.0

    for cell in contract["cells"]:
        cell_dir = root / cell["cell_id"]
        gate_path = cell_dir / "postcarla_trajectory_gate.json"
        cell_failures: list[str] = []
        if not gate_path.is_file():
            evaluations.append({**cell, "status": "fail", "failures": ["missing_postcarla_gate"]})
            failures.append(f"{cell['cell_id']}:missing_postcarla_gate")
            continue
        gate = read_json(gate_path)
        gate_by_name = {Path(item["scenario_dir"]).name: item for item in gate.get("evaluations", [])}
        summaries = sorted(cell_dir.glob("scenario_*/scenario_run_summary.json"))
        if len(summaries) != len(expected_inits):
            cell_failures.append("rollout_count")
        rollout_evaluations = []
        cell_reactive_active = 0
        for summary_path in summaries:
            scenario_dir = summary_path.parent
            init_id = scenario_init_id(scenario_dir.name)
            key = (cell["predictor"], cell["risk_policy"], cell["target_style"], init_id)
            observed_keys.add(key)
            rollout_failures: list[str] = []
            summary = read_json(summary_path)
            if summary.get("ran_successfully") is not True:
                rollout_failures.append("scenario_not_successful")
            extra = summary.get("extra") or {}
            if "collision_event_count" not in extra or "collision_events" not in extra:
                rollout_failures.append("native_collision_telemetry")
                native_count = 0
                native_events = []
            else:
                native_count = int(extra["collision_event_count"])
                native_events = extra["collision_events"] or []
                if native_count != len(native_events):
                    rollout_failures.append("native_collision_count_mismatch")
            total_native_collisions += native_count

            setup_path = scenario_dir / "smpc_debug_setup.json"
            debug_path = scenario_dir / "smpc_debug_steps.jsonl"
            deployment_path = scenario_dir / "prediction_deployment_manifest.json"
            prediction_path = scenario_dir / "prediction_dataset/prediction_dataset_raw.jsonl"
            for path, label in (
                (setup_path, "missing_setup"),
                (debug_path, "missing_debug"),
                (deployment_path, "missing_deployment"),
                (prediction_path, "missing_prediction"),
            ):
                if not path.is_file():
                    rollout_failures.append(label)
            gate_item = gate_by_name.get(scenario_dir.name)
            if gate_item is None:
                rollout_failures.append("missing_postcarla_rollout")
            if rollout_failures and any(item.startswith("missing_") for item in rollout_failures):
                rollout_evaluations.append({"scenario": scenario_dir.name, "ego_init_id": init_id, "status": "fail", "failures": sorted(set(rollout_failures))})
                cell_failures.extend(f"{scenario_dir.name}:{item}" for item in rollout_failures)
                continue

            setup = read_json(setup_path)
            control = setup.get("control_implementation") or {}
            if (
                control.get("version") != CORRECTED
                or control.get("legacy_explicitly_enabled") is not False
                or control.get("mode_consumption_map_at_n_tv_max") != MODE_MAP
                or control.get("reference_A_MIN") != -3.0
                or control.get("solver_A_MIN") != -3.0
            ):
                rollout_failures.append("corrected_control_contract")
            if setup.get("risk_profile") != RISK_PROFILES[cell["risk_policy"]]:
                rollout_failures.append("risk_profile")
            if bool(setup.get("fixed_risk")) != (cell["risk_policy"] != "adaptive"):
                rollout_failures.append("fixed_risk_flag")
            supervisor = setup.get("yield_stop_supervisor") or {}
            if (
                supervisor.get("risk_owned_yield_enabled") != 1
                or supervisor.get("planner_ownership_stress_enabled") != 1
                or supervisor.get("mode") != "reduced_intervention"
            ):
                rollout_failures.append("authority_regime")
            if "collision_envelope" not in setup:
                rollout_failures.append("collision_envelope_telemetry")

            rollout_failures.extend(deployment_failures(read_json(deployment_path), cell["predictor"], contract))
            debug_failures, debug_stats = debug_audit(read_jsonl(debug_path), float(contract["runtime_gate"]["max_p95_solve_time_s"]))
            rollout_failures.extend(debug_failures)
            prediction_failures, prediction_stats = prediction_audit(read_jsonl(prediction_path), cell, init_id, contract)
            rollout_failures.extend(prediction_failures)
            total_valid_prediction_steps += debug_stats["valid_prediction_steps"]
            if debug_stats["p95_solve_time_s"] is not None:
                max_p95 = max(max_p95, float(debug_stats["p95_solve_time_s"]))
            cell_reactive_active += prediction_stats["reactive_active_samples"]

            if gate_item is not None:
                completion = gate_item.get("completion_valid")
                if not isinstance(completion, bool):
                    rollout_failures.append("completion_outcome_missing")
                else:
                    total_completion_failures += int(not completion)
                pairs = gate_item.get("pair_safety") or []
                if len(pairs) != 1 or not isinstance(pairs[0].get("footprint_collision") if pairs else None, bool):
                    rollout_failures.append("footprint_outcome_missing")
                else:
                    total_footprint_collisions += int(pairs[0]["footprint_collision"])
                fixed_rules = gate_item.get("fixed_geometry_yield_rules") or []
                if len(fixed_rules) != 1:
                    rollout_failures.append("fixed_geometry_outcome_missing")
                else:
                    rule = fixed_rules[0]
                    outcome = rule.get("target_clears_before_ego_enters")
                    if not isinstance(outcome, bool):
                        rollout_failures.append("fixed_geometry_yield_outcome_missing")
                    else:
                        total_yield_failures += int(not outcome)
                    points = np.asarray([rule.get("ego_conflict_point_xy"), rule.get("target_conflict_point_xy")], dtype=float)
                    if points.shape != (2, 2) or not np.isfinite(points).all() or rule.get("geometry_source") != "controller_route_projection":
                        rollout_failures.append("fixed_geometry_invalid")
                    else:
                        geometry_by_init[init_id].append(points)

            rollout = {
                "scenario": scenario_dir.name,
                "ego_init_id": init_id,
                "status": "pass" if not rollout_failures else "fail",
                "failures": sorted(set(rollout_failures)),
                "native_collision_count": native_count,
                "native_collision_events": native_events,
                **debug_stats,
                **prediction_stats,
                "artifacts": {
                    "scenario_summary_sha256": sha256(summary_path),
                    "setup_sha256": sha256(setup_path),
                    "debug_sha256": sha256(debug_path),
                    "deployment_sha256": sha256(deployment_path),
                    "prediction_sha256": sha256(prediction_path),
                },
            }
            rollout_evaluations.append(rollout)
            cell_failures.extend(f"{scenario_dir.name}:{item}" for item in rollout["failures"])
        if cell["target_style"] == "reactive" and cell_reactive_active == 0:
            cell_failures.append("reactive_tail_not_exercised")
        evaluation = {
            **cell,
            "status": "pass" if not cell_failures else "fail",
            "failures": sorted(set(cell_failures)),
            "observed_rollouts": len(summaries),
            "reactive_active_samples": cell_reactive_active,
            "postcarla_overall_status_is_scientific_not_integrity": gate.get("overall_status"),
            "rollouts": rollout_evaluations,
        }
        evaluations.append(evaluation)
        failures.extend(f"{cell['cell_id']}:{item}" for item in evaluation["failures"])

    if observed_keys != expected_keys:
        failures.append("matrix:observed_treatment_keys")
    geometry_consistency = {}
    for init_id in sorted(expected_inits):
        points = geometry_by_init.get(init_id, [])
        consistent = len(points) == len(contract["cells"]) and all(
            np.allclose(points[0], value, atol=1e-3) for value in points[1:]
        )
        geometry_consistency[str(init_id)] = {
            "observations": len(points),
            "expected": len(contract["cells"]),
            "consistent_across_treatments": bool(consistent),
            "points": points[0].tolist() if points else None,
        }
        if not consistent:
            failures.append(f"matrix:fixed_geometry_consistency:init{init_id}")

    payload = {
        "schema_version": "r3_corrected_matrix_audit_v1",
        "status": "pass" if not failures else "fail",
        "stage": "R3",
        "formal_evidence": True,
        "implementation_version": CORRECTED,
        "expected_rollouts": int(contract["expected_rollouts"]),
        "observed_rollouts": len(observed_keys),
        "unique_treatment_keys": len(observed_keys),
        "passing_integrity_rollouts": sum(
            rollout.get("status") == "pass"
            for evaluation in evaluations
            for rollout in evaluation.get("rollouts", [])
        ),
        "scientific_outcome_taxonomy": {
            "native_collision_events": total_native_collisions,
            "footprint_collision_rollouts": total_footprint_collisions,
            "fixed_geometry_yield_failure_rollouts": total_yield_failures,
            "completion_failure_rollouts": total_completion_failures,
            "adverse_outcomes_are_retained_not_excluded": True,
        },
        "total_valid_prediction_steps": total_valid_prediction_steps,
        "maximum_rollout_p95_solve_time_s": max_p95,
        "fixed_geometry_consistency": geometry_consistency,
        "contract_sha256": sha256(contract_path),
        "failures": sorted(set(failures)),
        "evaluations": evaluations,
    }
    atomic_json(args.output_json.resolve(), payload)
    print(json.dumps({key: payload[key] for key in ("status", "observed_rollouts", "passing_integrity_rollouts", "scientific_outcome_taxonomy", "failures")}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
