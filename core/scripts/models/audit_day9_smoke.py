#!/usr/bin/env python3
"""Audit Day 9 CARLA deployment smoke and its prediction-to-control chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def finite_summary(summary: dict) -> bool:
    return (
        int(summary.get("nan_count", -1)) == 0
        and float(summary.get("finite_frac", 0.0)) == 1.0
    )


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--contract-json", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    root = Path(args.results_dir).resolve()
    contract_path = Path(args.contract_json).resolve()
    contract = read_json(contract_path)
    if contract.get("status") != "frozen":
        raise ValueError("Day 9 run contract is not frozen")

    evaluations = []
    failures = []
    for arm in contract["arms"]:
        arm_dir = root / arm["arm_id"]
        gate_path = arm_dir / "postcarla_trajectory_gate.json"
        gate = read_json(gate_path)
        scenario_summaries = sorted(arm_dir.glob("**/scenario_run_summary.json"))
        if len(scenario_summaries) != 1:
            raise ValueError(f"Expected one scenario in {arm_dir}, found {len(scenario_summaries)}")
        scenario_dir = scenario_summaries[0].parent
        scenario_summary = read_json(scenario_summaries[0])
        deployment_path = scenario_dir / "prediction_deployment_manifest.json"
        deployment = read_json(deployment_path)
        debug_path = scenario_dir / "smpc_debug_steps.jsonl"
        debug_rows = read_jsonl(debug_path)
        prediction_path = scenario_dir / "prediction_dataset" / "prediction_dataset_raw.jsonl"
        prediction_rows = read_jsonl(prediction_path)

        expected_predictor = contract["predictors"][arm["predictor"]]
        arm_failures = []
        if gate.get("overall_status") != "PASS":
            arm_failures.append("postcarla_gate")
        if scenario_summary.get("ran_successfully") is not True:
            arm_failures.append("scenario_run")
        if deployment.get("status") != "pass" or deployment.get("warmup_passed") is not True:
            arm_failures.append("deployment_warmup")
        actual_model_hash = (deployment.get("model_artifact") or {}).get("sha256_tree")
        if actual_model_hash != expected_predictor["model_sha256_tree"]:
            arm_failures.append("model_hash")
        if arm["predictor"] == "B1":
            if (deployment.get("calibration_artifact") or {}).get("sha256") != expected_predictor[
                "calibration_sha256"
            ]:
                arm_failures.append("calibration_hash")
            if deployment.get("calibration_fit_split") != "val":
                arm_failures.append("calibration_split")
            if deployment.get("calibration_parameters") != expected_predictor[
                "calibration_parameters"
            ]:
                arm_failures.append("calibration_parameters")
        else:
            if deployment.get("calibration_source") is not None:
                arm_failures.append("baseline_calibration_not_identity")
            if deployment.get("calibration_parameters") != {
                "temperature": 1.0,
                "covariance_scale": 1.0,
            }:
                arm_failures.append("baseline_identity_parameters")

        valid_debug = []
        solver_failures = 0
        risk_mode_matches = 0
        supervisor_rows = 0
        for row in debug_rows:
            solver = row.get("solver") or {}
            if "exception" in solver or solver.get("optimal") is False:
                solver_failures += 1
            valid_flags = row.get("prediction_valid") or []
            if not any(bool(item) for item in valid_flags):
                continue
            valid_debug.append(row)
            prediction = row.get("prediction") or {}
            if not all(
                finite_summary(prediction.get(field) or {})
                for field in ("mode_probs", "mus", "sigmas")
            ):
                arm_failures.append("nonfinite_prediction_debug")
                break
            risk = row.get("risk") or {}
            expected_mode = "adaptive_variable" if arm["risk_policy"] == "adaptive" else "fixed_static"
            if risk.get("solver_risk_mode") == expected_mode:
                risk_mode_matches += 1
            if "yield_stop_supervisor" in row:
                supervisor_rows += 1

        if not valid_debug:
            arm_failures.append("no_valid_prediction_debug")
        if risk_mode_matches != len(valid_debug):
            arm_failures.append("risk_mode_chain")
        if supervisor_rows != len(valid_debug):
            arm_failures.append("supervisor_chain")

        invalid_covariances = 0
        invalid_probabilities = 0
        active_samples = 0
        for row in prediction_rows:
            probs = np.asarray(row.get("mode_probabilities"), dtype=float)
            covariances = np.asarray(row.get("pred_sigmas_world"), dtype=float)
            if (
                probs.size == 0
                or not np.isfinite(probs).all()
                or (probs < 0.0).any()
                or not math.isclose(float(probs.sum()), 1.0, abs_tol=1e-6)
            ):
                invalid_probabilities += 1
            if covariances.size == 0 or not np.isfinite(covariances).all():
                invalid_covariances += 1
            else:
                symmetric = np.allclose(covariances, np.swapaxes(covariances, -1, -2), atol=1e-6)
                positive = bool((np.linalg.eigvalsh(covariances) > 0.0).all())
                if not symmetric or not positive:
                    invalid_covariances += 1
            diagnostics = row.get("target_reactive_diagnostics") or {}
            active_samples += int(bool(diagnostics.get("active")))
        if not prediction_rows:
            arm_failures.append("no_prediction_samples")
        if invalid_covariances:
            arm_failures.append("invalid_covariance")
        if invalid_probabilities:
            arm_failures.append("invalid_probability")
        if arm["target_style"] == "reactive" and active_samples == 0:
            arm_failures.append("reactive_tail_not_exercised")

        evaluation = {
            **arm,
            "status": "pass" if not arm_failures else "fail",
            "failures": sorted(set(arm_failures)),
            "scenario_dir": str(scenario_dir),
            "postcarla_status": gate.get("overall_status"),
            "debug_steps": len(debug_rows),
            "valid_prediction_debug_steps": len(valid_debug),
            "prediction_samples": len(prediction_rows),
            "reactive_active_samples": active_samples,
            "solver_failure_steps": solver_failures,
            "invalid_probabilities": invalid_probabilities,
            "invalid_covariances": invalid_covariances,
            "artifacts": {
                "scenario_summary_sha256": sha256(scenario_summaries[0]),
                "deployment_manifest_sha256": sha256(deployment_path),
                "debug_steps_sha256": sha256(debug_path),
                "prediction_raw_sha256": sha256(prediction_path),
                "postcarla_gate_sha256": sha256(gate_path),
            },
        }
        evaluations.append(evaluation)
        failures.extend(f"{arm['arm_id']}:{item}" for item in evaluation["failures"])

    payload = {
        "schema_version": "day9_carla_smoke_audit_v1",
        "status": "pass" if not failures else "fail",
        "smoke_only_not_formal_evidence": True,
        "expected_arms": len(contract["arms"]),
        "observed_arms": len(evaluations),
        "failures": failures,
        "contract_sha256": sha256(contract_path),
        "evaluations": evaluations,
    }
    output = Path(args.output_json).resolve()
    atomic_json(output, payload)
    print(json.dumps({
        "status": payload["status"],
        "observed_arms": payload["observed_arms"],
        "failures": failures,
    }, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
