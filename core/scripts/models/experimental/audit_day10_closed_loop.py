#!/usr/bin/env python3
"""Audit the frozen Day 10 predictor × risk × target-style CARLA matrix."""

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
from pathlib import Path

import numpy as np

from audit_day9_smoke import atomic_json, finite_summary, read_json, read_jsonl, sha256
from audit_day9_smoke import solver_failed, warmup_passed


def preflight_semantics(preflight: dict) -> dict:
    """Return deployment invariants, excluding nondeterministic GPU float diagnostics."""
    return {
        "status": preflight.get("status"),
        "selected_variant": preflight.get("selected_variant"),
        "selected_seed": preflight.get("selected_seed"),
        "selection_freeze_sha256": preflight.get("selection_freeze_sha256"),
        "anchors": preflight.get("anchors"),
        "normalization": preflight.get("normalization"),
        "warmup_input": preflight.get("warmup_input"),
        "b1_deployment": (preflight.get("b1") or {}).get("deployment"),
        "b1_numerical_status": ((preflight.get("b1") or {}).get("numerical_smoke") or {}).get("status"),
        "b1_numerical_checks": ((preflight.get("b1") or {}).get("numerical_smoke") or {}).get("checks"),
        "b0_deployment": (preflight.get("b0") or {}).get("deployment"),
        "b0_numerical_status": ((preflight.get("b0") or {}).get("numerical_smoke") or {}).get("status"),
        "b0_numerical_checks": ((preflight.get("b0") or {}).get("numerical_smoke") or {}).get("checks"),
    }


def semantic_sha256(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def deployment_failures(deployment: dict, predictor: str, contract: dict) -> list[str]:
    failures = []
    expected = contract["predictors"][predictor]
    if deployment.get("status") != "pass" or not warmup_passed(
        deployment.get("warmup_passed")
    ):
        failures.append("deployment_warmup")
    if (deployment.get("model_artifact") or {}).get("sha256_tree") != expected[
        "model_sha256_tree"
    ]:
        failures.append("model_hash")
    if (deployment.get("anchors_artifact") or {}).get("sha256") != contract[
        "anchors_sha256"
    ]:
        failures.append("anchors_hash")
    if deployment.get("normalization") != contract["normalization"]:
        failures.append("normalization")
    if predictor == "B1":
        if (deployment.get("calibration_artifact") or {}).get("sha256") != expected[
            "calibration_sha256"
        ]:
            failures.append("calibration_hash")
        if deployment.get("calibration_fit_split") != "val":
            failures.append("calibration_split")
        if deployment.get("calibration_parameters") != expected["calibration_parameters"]:
            failures.append("calibration_parameters")
    else:
        if deployment.get("calibration_source") is not None:
            failures.append("baseline_calibration_not_identity")
        if deployment.get("calibration_parameters") != {
            "temperature": 1.0,
            "covariance_scale": 1.0,
        }:
            failures.append("baseline_identity_parameters")
    return failures


def prediction_failures(rows: list[dict], cell: dict, contract: dict) -> tuple[list[str], dict]:
    failures = []
    invalid_probabilities = 0
    invalid_covariances = 0
    reactive_active_samples = 0
    observed_inits = set()
    expected_style = (
        "defensive_reactive" if cell["target_style"] == "reactive" else "assertive_constant_speed"
    )
    for row in rows:
        observed_inits.add(int(row.get("ego_init_id", -1)))
        if row.get("cell_id") != cell["cell_id"]:
            failures.append("cell_identity")
        if row.get("ego_policy") != cell["risk_policy"]:
            failures.append("risk_policy_label")
        if row.get("protocol_id") != contract.get(
            "prediction_protocol_id", "day10_a3_heldout_closed_loop_v1"
        ):
            failures.append("protocol_id")
        allowed_commits = contract.get("execution_git_commits") or [contract["git_commit"]]
        if row.get("git_commit") not in allowed_commits:
            failures.append("git_commit")
        if row.get("target_style") != expected_style:
            failures.append("target_style")
        if not math.isclose(
            float(row.get("target_start_offset_m", math.nan)),
            float(cell.get("target_offset_m", contract.get("target_offset_m", 0.0))),
            abs_tol=1e-12,
        ):
            failures.append("target_offset")
        if not math.isclose(
            float(row.get("target_speed_mps", math.nan)),
            float(contract["target_speed_mps"]),
            abs_tol=1e-12,
        ):
            failures.append("target_nominal_speed")
        style_parameters = row.get("target_style_parameters") or {}
        if cell["target_style"] == "reactive":
            for key, expected in contract["reactive_parameters"].items():
                if key not in style_parameters or not math.isclose(
                    float(style_parameters[key]), float(expected), abs_tol=1e-12
                ):
                    failures.append("reactive_parameters")
                    break
        elif not math.isclose(
            float(style_parameters.get("nominal_speed_mps", math.nan)),
            float(contract["target_speed_mps"]),
            abs_tol=1e-12,
        ):
            failures.append("assertive_parameters")
        probabilities = np.asarray(row.get("mode_probabilities"), dtype=float)
        covariances = np.asarray(row.get("pred_sigmas_world"), dtype=float)
        if (
            probabilities.size == 0
            or not np.isfinite(probabilities).all()
            or (probabilities < 0.0).any()
            or not math.isclose(float(probabilities.sum()), 1.0, abs_tol=1e-6)
        ):
            invalid_probabilities += 1
        if covariances.size == 0 or not np.isfinite(covariances).all():
            invalid_covariances += 1
        else:
            symmetric = np.allclose(
                covariances, np.swapaxes(covariances, -1, -2), atol=1e-6
            )
            positive = bool((np.linalg.eigvalsh(covariances) > 0.0).all())
            if not symmetric or not positive:
                invalid_covariances += 1
        reactive_active_samples += int(
            bool((row.get("target_reactive_diagnostics") or {}).get("active"))
        )
    if not rows:
        failures.append("no_prediction_samples")
    if invalid_probabilities:
        failures.append("invalid_probability")
    if invalid_covariances:
        failures.append("invalid_covariance")
    if cell["target_style"] == "assertive" and reactive_active_samples:
        failures.append("assertive_has_reactive_activity")
    return sorted(set(failures)), {
        "prediction_samples": len(rows),
        "invalid_probabilities": invalid_probabilities,
        "invalid_covariances": invalid_covariances,
        "reactive_active_samples": reactive_active_samples,
        "observed_inits": sorted(observed_inits),
    }


def debug_failures(rows: list[dict], cell: dict) -> tuple[list[str], dict]:
    failures = []
    valid = []
    solver_failures = 0
    risk_mode_matches = 0
    supervisor_rows = 0
    expected_mode = "adaptive_variable" if cell["risk_policy"] == "adaptive" else "fixed_static"
    for row in rows:
        solver = row.get("solver") or {}
        solver_failures += int(solver_failed(solver))
        if not any(bool(item) for item in (row.get("prediction_valid") or [])):
            continue
        valid.append(row)
        prediction = row.get("prediction") or {}
        if not all(
            finite_summary(prediction.get(field) or {})
            for field in ("mode_probs", "mus", "sigmas")
        ):
            failures.append("nonfinite_prediction_debug")
        if (row.get("risk") or {}).get("solver_risk_mode") == expected_mode:
            risk_mode_matches += 1
        supervisor_rows += int("yield_stop_supervisor" in row)
    if not valid:
        failures.append("no_valid_prediction_debug")
    if risk_mode_matches != len(valid):
        failures.append("risk_mode_chain")
    if supervisor_rows != len(valid):
        failures.append("supervisor_chain")
    return sorted(set(failures)), {
        "debug_steps": len(rows),
        "valid_prediction_debug_steps": len(valid),
        "solver_failure_steps": solver_failures,
        "solver_failure_fraction": solver_failures / len(rows) if rows else None,
    }


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
        raise ValueError("Day 10 run contract is not frozen")
    day11_timing_shift = str(contract.get("schema_version", "")).startswith("day11_")

    failures = []
    tuning_by_offset = contract.get("tuning_sha256_by_offset")
    if tuning_by_offset:
        for entry in tuning_by_offset.values():
            tuning_path = root / entry["path"]
            if not tuning_path.is_file() or sha256(tuning_path) != entry["sha256"]:
                failures.append(f"matrix:tuning_sha256:{entry['path']}")
    else:
        tuning_path = root / contract.get("tuning_filename", "tuning_day10_frozen.json")
        if not tuning_path.is_file() or sha256(tuning_path) != contract.get("tuning_sha256"):
            failures.append("matrix:tuning_sha256")
    preflight_path = root / contract.get(
        "deployment_preflight_filename", "day10_deployment_preflight.json"
    )
    if (
        not preflight_path.is_file()
        or semantic_sha256(preflight_semantics(read_json(preflight_path)))
        != contract.get("preflight_semantic_sha256")
    ):
        failures.append("matrix:preflight_semantics")
    allowed_commits = contract.get("execution_git_commits") or [contract.get("git_commit")]
    if len(allowed_commits) > 1:
        provenance_name = (
            "day11_contract_resume_provenance.json"
            if str(contract.get("schema_version", "")).startswith("day11_")
            else "day10_contract_resume_provenance.json"
        )
        provenance_path = root / provenance_name
        if not provenance_path.is_file():
            failures.append("matrix:resume_provenance")
        else:
            provenance = read_json(provenance_path)
            if (
                provenance.get("status") != "pass"
                or provenance.get("allowed_execution_git_commits") != allowed_commits
            ):
                failures.append("matrix:resume_provenance")
    evaluations = []
    observed_rollouts = 0
    for cell in contract["cells"]:
        cell_dir = root / cell["cell_id"]
        gate_path = cell_dir / "postcarla_trajectory_gate.json"
        gate = read_json(gate_path)
        cell_failures = []
        if gate.get("overall_status") != "PASS":
            cell_failures.append("postcarla_gate")
        gate_by_scenario = {
            Path(item["scenario_dir"]).name: item for item in (gate.get("evaluations") or [])
        }
        summaries = sorted(cell_dir.glob("**/scenario_run_summary.json"))
        if len(summaries) != len(contract["ego_init_ids"]):
            cell_failures.append("rollout_count")
        rollout_evaluations = []
        cell_reactive_active = 0
        observed_cell_inits = set()
        for summary_path in summaries:
            scenario_dir = summary_path.parent
            summary = read_json(summary_path)
            deployment_path = scenario_dir / "prediction_deployment_manifest.json"
            setup_path = scenario_dir / "smpc_debug_setup.json"
            debug_path = scenario_dir / "smpc_debug_steps.jsonl"
            prediction_path = scenario_dir / "prediction_dataset" / "prediction_dataset_raw.jsonl"
            rollout_failures = []
            if summary.get("ran_successfully") is not True:
                rollout_failures.append("scenario_run")
            deployment = read_json(deployment_path)
            rollout_failures.extend(
                deployment_failures(deployment, cell["predictor"], contract)
            )
            setup = read_json(setup_path)
            expected_profile = {
                "fixed_aggressive": "fixed_frontier_aggressive",
                "fixed_medium": "fixed_frontier_medium",
                "fixed_conservative": "fixed_frontier_conservative",
                "adaptive": "adaptive_interaction_severity",
            }[cell["risk_policy"]]
            if setup.get("risk_profile") != expected_profile:
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
            prediction_rows = read_jsonl(prediction_path)
            prediction_issues, prediction_stats = prediction_failures(
                prediction_rows, cell, contract
            )
            rollout_failures.extend(prediction_issues)
            debug_rows = read_jsonl(debug_path)
            debug_issues, debug_stats = debug_failures(debug_rows, cell)
            rollout_failures.extend(debug_issues)
            observed_inits = prediction_stats.pop("observed_inits")
            if len(observed_inits) != 1:
                rollout_failures.append("ego_init_identity")
                ego_init_id = None
            else:
                ego_init_id = observed_inits[0]
                observed_cell_inits.add(ego_init_id)
            gate_evaluation = gate_by_scenario.get(scenario_dir.name)
            if gate_evaluation is None or gate_evaluation.get("status") != "PASS":
                rollout_failures.append("postcarla_rollout")
                gate_solver_fraction = None
            else:
                gate_solver_fraction = gate_evaluation.get("solver_failure_frac")
            debug_solver_fraction = debug_stats["solver_failure_fraction"]
            if (
                gate_solver_fraction is None
                or debug_solver_fraction is None
                or not math.isclose(
                    float(gate_solver_fraction), float(debug_solver_fraction), abs_tol=1e-12
                )
            ):
                rollout_failures.append("solver_failure_accounting")
            cell_reactive_active += prediction_stats["reactive_active_samples"]
            observed_rollouts += 1
            rollout_evaluation = {
                "scenario": scenario_dir.name,
                "ego_init_id": ego_init_id,
                "status": "pass" if not rollout_failures else "fail",
                "failures": sorted(set(rollout_failures)),
                **prediction_stats,
                **debug_stats,
                "postcarla_solver_failure_fraction": gate_solver_fraction,
                "artifacts": {
                    "scenario_summary_sha256": sha256(summary_path),
                    "deployment_manifest_sha256": sha256(deployment_path),
                    "debug_setup_sha256": sha256(setup_path),
                    "debug_steps_sha256": sha256(debug_path),
                    "prediction_raw_sha256": sha256(prediction_path),
                },
            }
            rollout_evaluations.append(rollout_evaluation)
            cell_failures.extend(
                f"{scenario_dir.name}:{item}" for item in rollout_evaluation["failures"]
            )
        if observed_cell_inits != set(contract["ego_init_ids"]):
            cell_failures.append("ego_init_coverage")
        if (
            cell["target_style"] == "reactive"
            and cell_reactive_active == 0
            and not day11_timing_shift
        ):
            cell_failures.append("reactive_tail_not_exercised")
        evaluation = {
            **cell,
            "status": "pass" if not cell_failures else "fail",
            "failures": sorted(set(cell_failures)),
            "observed_rollouts": len(summaries),
            "reactive_active_samples": cell_reactive_active,
            "reactive_tail_exercised": bool(cell_reactive_active),
            "postcarla_status": gate.get("overall_status"),
            "postcarla_gate_sha256": sha256(gate_path),
            "rollouts": rollout_evaluations,
        }
        evaluations.append(evaluation)
        failures.extend(f"{cell['cell_id']}:{item}" for item in evaluation["failures"])

    reactive_activity_gate = {
        "scope": "per_reactive_cell",
        "groups": {},
    }
    if day11_timing_shift:
        reactive_activity_gate["scope"] = "across_offsets_within_predictor_x_policy"
        for predictor in sorted({item["predictor"] for item in evaluations}):
            for policy in sorted({item["risk_policy"] for item in evaluations}):
                group = [
                    item
                    for item in evaluations
                    if item["predictor"] == predictor
                    and item["risk_policy"] == policy
                    and item["target_style"] == "reactive"
                ]
                active_samples = sum(int(item["reactive_active_samples"]) for item in group)
                key = f"{predictor}::{policy}"
                reactive_activity_gate["groups"][key] = {
                    "cells": [item["cell_id"] for item in group],
                    "active_samples": active_samples,
                    "status": "pass" if active_samples else "fail",
                }
                if not group or not active_samples:
                    failures.append(f"matrix:reactive_activity:{key}")

    if observed_rollouts != int(contract["expected_rollouts"]):
        failures.append("matrix:rollout_count")
    payload = {
        "schema_version": contract.get("audit_schema_version", "day10_closed_loop_audit_v1"),
        "status": "pass" if not failures else "fail",
        "formal_evidence": True,
        "expected_cells": len(contract["cells"]),
        "observed_cells": len(evaluations),
        "expected_rollouts": int(contract["expected_rollouts"]),
        "observed_rollouts": observed_rollouts,
        "failures": failures,
        "contract_sha256": sha256(contract_path),
        "reactive_activity_gate": reactive_activity_gate,
        "evaluations": evaluations,
    }
    output = Path(args.output_json).resolve()
    atomic_json(output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "observed_cells": payload["observed_cells"],
                "observed_rollouts": observed_rollouts,
                "failures": failures,
            },
            indent=2,
        )
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
