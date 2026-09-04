#!/usr/bin/env python3
"""Hard audit for the non-statistical R2 corrected CARLA pilot."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np


CORRECTED = "corrected_joint_modes_shared_amin_v1"
EXPECTED_ONE_TV_MAP = [[0], [1], [2]]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def finite_summary(summary: dict) -> bool:
    return (
        int(summary.get("nan_count", -1)) == 0
        and float(summary.get("finite_frac", 0.0)) == 1.0
    )


def finite_numeric(value) -> bool:
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return False
    return bool(array.size > 0 and np.isfinite(array).all())


def valid_hash(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--contract-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    root = args.results_dir.resolve()
    contract_path = args.contract_json.resolve()
    contract = read_json(contract_path)
    if contract.get("status") != "frozen" or contract.get("implementation_version") != CORRECTED:
        raise ValueError("R2 corrected pilot contract is not frozen or uses the wrong implementation")

    failures: list[str] = []
    retry_policy = contract.get("transient_retry_policy") or {}
    if (
        int(retry_policy.get("max_attempts", 0)) < 1
        or retry_policy.get("completed_rollouts_never_repeated") is not True
        or retry_policy.get("scientific_failures_not_accepted") is not True
    ):
        failures.append("global:invalid_transient_retry_policy")
    evaluations = []
    amin_pairs = set()
    total_native_collisions = 0
    total_valid_prediction_steps = 0
    for cell in contract["cells"]:
        cell_id = cell["cell_id"]
        cell_dir = root / cell_id
        cell_failures = []
        summaries = sorted(cell_dir.glob("**/scenario_run_summary.json"))
        if len(summaries) != 1:
            evaluations.append({**cell, "status": "fail", "failures": ["scenario_count"]})
            failures.append(f"{cell_id}:scenario_count")
            continue
        scenario_dir = summaries[0].parent
        summary = read_json(summaries[0])
        setup_path = scenario_dir / "smpc_debug_setup.json"
        debug_path = scenario_dir / "smpc_debug_steps.jsonl"
        deployment_path = scenario_dir / "prediction_deployment_manifest.json"
        prediction_path = scenario_dir / "prediction_dataset/prediction_dataset_raw.jsonl"
        gate_path = cell_dir / "postcarla_trajectory_gate.json"
        receipt_path = cell_dir / "R2_CELL_COMPLETE.json"
        for path, label in (
            (setup_path, "missing_setup"),
            (debug_path, "missing_debug"),
            (deployment_path, "missing_deployment"),
            (prediction_path, "missing_prediction_dataset"),
            (gate_path, "missing_postcarla_gate"),
            (receipt_path, "missing_cell_receipt"),
        ):
            if not path.is_file():
                cell_failures.append(label)
        if cell_failures:
            evaluations.append({**cell, "status": "fail", "failures": cell_failures})
            failures.extend(f"{cell_id}:{item}" for item in cell_failures)
            continue

        setup = read_json(setup_path)
        debug_rows = read_jsonl(debug_path)
        deployment = read_json(deployment_path)
        prediction_rows = read_jsonl(prediction_path)
        gate = read_json(gate_path)
        receipt = read_json(receipt_path)
        if summary.get("ran_successfully") is not True:
            cell_failures.append("scenario_not_successful")
        if gate.get("overall_status") != "PASS":
            cell_failures.append("postcarla_gate")
        if receipt.get("status") != "pass" or receipt.get("cell_id") != cell_id:
            cell_failures.append("cell_receipt")

        collision_count = int((summary.get("extra") or {}).get("collision_event_count", -1))
        collision_events = (summary.get("extra") or {}).get("collision_events") or []
        total_native_collisions += max(collision_count, 0)
        if collision_count != 0 or collision_events:
            cell_failures.append("native_collision")

        control = setup.get("control_implementation") or {}
        ref_amin = control.get("reference_A_MIN")
        solver_amin = control.get("solver_A_MIN")
        amin_pairs.add((ref_amin, solver_amin))
        if (
            control.get("version") != CORRECTED
            or control.get("legacy_explicitly_enabled") is not False
            or control.get("mode_consumption_map_at_n_tv_max") != EXPECTED_ONE_TV_MAP
        ):
            cell_failures.append("corrected_setup_contract")
        if ref_amin != -3.0 or solver_amin != -3.0:
            cell_failures.append("shared_amin")

        expected_predictor = contract["predictors"][cell["predictor"]]
        actual_model = (deployment.get("model_artifact") or {}).get("sha256_tree")
        if actual_model != expected_predictor["model_sha256_tree"]:
            cell_failures.append("model_hash")
        if cell["predictor"] == "B1":
            if (deployment.get("calibration_artifact") or {}).get("sha256") != expected_predictor[
                "calibration_sha256"
            ]:
                cell_failures.append("calibration_hash")
        elif deployment.get("calibration_parameters") != {
            "temperature": 1.0,
            "covariance_scale": 1.0,
        }:
            cell_failures.append("baseline_not_identity_calibrated")
        tuning_path = root / cell["tuning_path"]
        if not tuning_path.is_file() or sha256(tuning_path) != cell["tuning_sha256"]:
            cell_failures.append("tuning_hash")

        valid_rows = []
        mode_contract_rows = 0
        supervisor_rows = 0
        solver_rows = 0
        applied_rows = 0
        solve_times = []
        for row in debug_rows:
            valid_flags = row.get("prediction_valid") or []
            if not any(bool(item) for item in valid_flags):
                continue
            valid_rows.append(row)
            prediction = row.get("prediction") or {}
            if not all(
                finite_summary(prediction.get(field) or {})
                for field in ("mode_probs", "mus", "sigmas")
            ):
                cell_failures.append("nonfinite_prediction_debug")
                continue
            mode_contract = prediction.get("mode_consumption") or {}
            joint_modes = mode_contract.get("joint_modes") or []
            consumed_indices = []
            hashes_ok = True
            for joint in joint_modes:
                for consumed in joint.get("per_vehicle") or []:
                    consumed_indices.append(consumed.get("spatial_mode_index"))
                    hashes_ok = hashes_ok and valid_hash(consumed.get("mean_sha256"))
                    hashes_ok = hashes_ok and valid_hash(consumed.get("covariance_sha256"))
            if (
                mode_contract.get("implementation_version") == CORRECTED
                and mode_contract.get("mapping") == EXPECTED_ONE_TV_MAP
                and consumed_indices == [0, 1, 2]
                and hashes_ok
            ):
                mode_contract_rows += 1
            if "yield_stop_supervisor" in row:
                supervisor_rows += 1
            if "solver" in row and "solver_problem" in row:
                solver_rows += 1
            applied = row.get("applied") or {}
            if all(
                finite_numeric(applied.get(field))
                for field in ("u0", "u_control", "v_des", "control_prev_after")
            ):
                applied_rows += 1
            solve_time = applied.get("solve_time")
            if solve_time is not None and math.isfinite(float(solve_time)):
                solve_times.append(float(solve_time))

        total_valid_prediction_steps += len(valid_rows)
        if not valid_rows:
            cell_failures.append("no_valid_prediction_steps")
        if mode_contract_rows != len(valid_rows):
            cell_failures.append("mode_consumption_telemetry")
        if supervisor_rows != len(valid_rows):
            cell_failures.append("supervisor_telemetry")
        if solver_rows != len(valid_rows):
            cell_failures.append("solver_telemetry")
        if applied_rows != len(valid_rows):
            cell_failures.append("nonfinite_or_missing_applied_control")
        p95_solve_time = float(np.quantile(solve_times, 0.95)) if solve_times else None
        if p95_solve_time is None or p95_solve_time > float(contract["runtime_gate"]["max_p95_solve_time_s"]):
            cell_failures.append("runtime_gate")

        invalid_prediction_rows = 0
        for row in prediction_rows:
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
                or (probabilities < 0.0).any()
                or not math.isclose(float(probabilities.sum()), 1.0, abs_tol=1e-6)
            ):
                invalid_prediction_rows += 1
        if not prediction_rows or invalid_prediction_rows:
            cell_failures.append("raw_prediction_numerics")

        stats = (summary.get("stats") or {}).get("ego_3") or {}
        evaluation = {
            **cell,
            "status": "pass" if not cell_failures else "fail",
            "failures": sorted(set(cell_failures)),
            "scenario_dir": str(scenario_dir),
            "native_collision_count": collision_count,
            "debug_steps": len(debug_rows),
            "valid_prediction_steps": len(valid_rows),
            "mode_contract_steps": mode_contract_rows,
            "prediction_samples": len(prediction_rows),
            "invalid_prediction_rows": invalid_prediction_rows,
            "p95_solve_time_s": p95_solve_time,
            "ego_steps": stats.get("n_steps"),
            "ego_feasible_fraction": stats.get("feasible_frac"),
            "reference_A_MIN": ref_amin,
            "solver_A_MIN": solver_amin,
            "artifacts": {
                "scenario_summary_sha256": sha256(summaries[0]),
                "setup_sha256": sha256(setup_path),
                "debug_sha256": sha256(debug_path),
                "deployment_sha256": sha256(deployment_path),
                "prediction_sha256": sha256(prediction_path),
                "gate_sha256": sha256(gate_path),
                "receipt_sha256": sha256(receipt_path),
            },
        }
        evaluations.append(evaluation)
        failures.extend(f"{cell_id}:{item}" for item in evaluation["failures"])

    if amin_pairs != {(-3.0, -3.0)}:
        failures.append("global:fixed_adaptive_amin_not_identical")
    if len(evaluations) != int(contract["expected_rollouts"]):
        failures.append("global:rollout_count")
    payload = {
        "schema_version": "r2_corrected_pilot_audit_v1",
        "status": "pass" if not failures else "fail",
        "stage": "R2",
        "non_statistical_pilot": True,
        "implementation_version": CORRECTED,
        "expected_rollouts": int(contract["expected_rollouts"]),
        "observed_rollouts": len(evaluations),
        "passing_rollouts": sum(item["status"] == "pass" for item in evaluations),
        "total_native_collisions": total_native_collisions,
        "total_valid_prediction_steps": total_valid_prediction_steps,
        "transient_retry_policy": retry_policy,
        "observed_amin_pairs": [list(pair) for pair in sorted(amin_pairs, key=str)],
        "contract_sha256": sha256(contract_path),
        "failures": sorted(set(failures)),
        "evaluations": evaluations,
    }
    atomic_json(args.output_json.resolve(), payload)
    print(json.dumps({key: payload[key] for key in (
        "status", "observed_rollouts", "passing_rollouts", "total_native_collisions", "failures"
    )}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
