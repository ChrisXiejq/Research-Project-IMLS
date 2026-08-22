#!/usr/bin/env python3
"""End-to-end validation, extension, calibration, freeze, and fresh-test orchestration."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Mapping

from capacity_study_v3_freeze import (
    build_selection_freeze,
    calibration_jobs,
    freeze_to_path,
    fresh_evaluation_jobs,
)
from capacity_study_v3_protocol import (
    atomic_json,
    sha256_file,
    sha256_payload,
    write_immutable_manifest,
)
from capacity_study_v3_runs import (
    convergence_extension_plan,
    core_runs,
    fraction_convergence_extension_plan,
    fraction_runs,
    run_payload,
    select_fraction_learning_rates,
    select_learning_rates,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_valid_training_completion(path: str | Path) -> dict[str, Any]:
    from capacity_study_v3_execute import completion_is_valid

    completion_path = Path(path)
    completion = _load_json(completion_path)
    config = _load_json(completion_path.parent / "run_config.json")
    if not completion_is_valid(completion_path, config["run_spec"]):
        raise ValueError(f"Training completion failed the formal integrity gate: {path}")
    return completion


def validation_rows_from_training(
    training_root: str | Path,
    *,
    extension_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    root = Path(training_root)
    from capacity_study_v3_execute import completion_is_valid

    extension_by_base = {}
    if extension_root is not None and Path(extension_root).exists():
        for path in Path(extension_root).glob("*/TRAINING_COMPLETE.json"):
            if not path.parent.name.endswith("__extended120"):
                continue
            payload = _load_json(path)
            run_config = _load_json(path.parent / "run_config.json")
            spec = run_config["run_spec"]
            base_id = spec.get("extends_run_id")
            if completion_is_valid(path, spec) and base_id:
                if base_id in extension_by_base:
                    raise ValueError(f"Duplicate extension completion: {base_id}")
                extension_by_base[base_id] = payload
    rows = []
    for spec in core_runs():
        base_path = root / spec.run_id / "TRAINING_COMPLETE.json"
        if not base_path.is_file():
            raise ValueError(f"Missing core completion: {spec.run_id}")
        base = _load_json(base_path)
        if not completion_is_valid(base_path, run_payload(spec)):
            raise ValueError(f"Invalid core completion: {spec.run_id}")
        effective = extension_by_base.get(spec.run_id, base)
        row = {
            "run_id": spec.run_id,
            "checkpoint_run_id": effective["run_id"],
            "model_cell_id": spec.model_cell_id,
            "learning_rate": spec.learning_rate,
            "seed": spec.seed,
            "split": "validation",
            "status": "pass",
            "rollout_macro_nll": effective["rollout_macro_nll"],
            "best_epoch": effective["best_epoch"],
            "epochs_allowed": effective["epochs_allowed"],
            "checkpoint_selection_metric": effective.get(
                "checkpoint_selection_metric"
            ),
        }
        if row["checkpoint_selection_metric"] != (
            "validation_rollout_macro_trajectory_mixture_NLL_per_step"
        ):
            raise ValueError(f"Wrong checkpoint metric: {effective['run_id']}")
        rows.append(row)
    if len(rows) != 189:
        raise ValueError("Validation selection requires exactly 189 core results")
    return rows


def select_and_audit_convergence(
    training_root: str | Path,
    *,
    extension_root: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    rows = validation_rows_from_training(
        training_root, extension_root=extension_root
    )
    selection = select_learning_rates(rows)
    convergence = convergence_extension_plan(selection, rows)
    return selection, convergence, rows


def fraction_validation_rows_from_training(
    training_root: str | Path,
    *,
    extension_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    root = Path(training_root)
    from capacity_study_v3_execute import completion_is_valid

    extension_by_base = {}
    if extension_root is not None and Path(extension_root).exists():
        for path in Path(extension_root).glob("*/TRAINING_COMPLETE.json"):
            if not path.parent.name.endswith("__extended120"):
                continue
            run_config = _load_json(path.parent / "run_config.json")
            extension_spec = run_config["run_spec"]
            base_id = extension_spec.get("extends_run_id")
            if base_id and completion_is_valid(path, extension_spec):
                extension_by_base[base_id] = _load_json(path)
    rows = []
    for spec in fraction_runs():
        path = root / spec.run_id / "TRAINING_COMPLETE.json"
        if not path.is_file():
            raise ValueError(f"Missing data-fraction completion: {spec.run_id}")
        completion = _load_json(path)
        if not completion_is_valid(path, run_payload(spec)):
            raise ValueError(f"Invalid data-fraction completion: {spec.run_id}")
        effective = extension_by_base.get(spec.run_id, completion)
        rows.append(
            {
                "run_id": spec.run_id,
                "checkpoint_run_id": effective["run_id"],
                "model_cell_id": spec.model_cell_id,
                "learning_rate": spec.learning_rate,
                "data_fraction": spec.data_fraction,
                "seed": spec.seed,
                "split": "validation",
                "status": "pass",
                "rollout_macro_nll": effective["rollout_macro_nll"],
                "best_epoch": effective["best_epoch"],
                "epochs_allowed": effective["epochs_allowed"],
            }
        )
    if len(rows) != 108:
        raise ValueError("Fraction validation requires all 108 manifest entries")
    return rows


def select_and_audit_fraction_convergence(
    training_root: str | Path,
    *,
    extension_root: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    rows = fraction_validation_rows_from_training(
        training_root, extension_root=extension_root
    )
    selection = select_fraction_learning_rates(rows)
    convergence = fraction_convergence_extension_plan(selection, rows)
    return selection, convergence, rows


def extension_execution_plan(
    convergence: Mapping[str, Any],
    *,
    convergence_path: str | Path,
    merged_dir: str | Path,
    base_model: str | Path,
    anchors: str | Path,
    output_root: str | Path,
    python_bin: str,
) -> dict[str, Any]:
    if convergence.get("status") not in {"pass", "requires_extension"}:
        raise ValueError("Convergence result cannot authorize extension execution")
    jobs = []
    for spec in convergence["extension_runs"]:
        completion = Path(output_root) / spec["run_id"] / "TRAINING_COMPLETE.json"
        from capacity_study_v3_execute import completion_is_valid

        complete = completion_is_valid(completion, spec)
        argv = [
            python_bin,
            str(SCRIPT_DIR / "train_prediction_model_v3.py"),
            "--run-manifest",
            str(convergence_path),
            "--run-id",
            spec["run_id"],
            "--merged-dir",
            str(merged_dir),
            "--base-model",
            str(base_model),
            "--anchors",
            str(anchors),
            "--output-dir",
            str(Path(output_root) / spec["run_id"]),
            "--epochs",
            "120",
        ]
        jobs.append(
            {
                "run_id": spec["run_id"],
                "extends_run_id": spec["extends_run_id"],
                "status": "complete" if complete else "pending",
                "command_argv": argv,
                "command": shlex.join(argv),
            }
        )
    return {
        "schema_version": "capacity_history_extension_execution_v3",
        "status": "pass",
        "jobs": jobs,
        "planned": len(jobs),
        "pending": sum(row["status"] == "pending" for row in jobs),
    }


def _command_jobs_for_calibration(
    selection: Mapping[str, Any], args: argparse.Namespace
) -> list[dict[str, Any]]:
    jobs = calibration_jobs(
        selection,
        training_root=args.training_root,
        output_root=args.calibration_root,
        merged_dir=args.merged_dir,
        anchors=args.anchors,
    )
    for job in jobs:
        argv = [
            args.python_bin,
            str(SCRIPT_DIR / "evaluate_multipath_model_on_dataset.py"),
            "--merged_dir",
            job["merged_dir"],
            "--split",
            "val",
            "--model",
            job["model"],
            "--anchors",
            job["anchors"],
            "--fit-calibration",
            "--calibration-output-json",
            job["calibration_output"],
            "--output_json",
            job["evaluation_output"],
            "--require-complete-interaction-history",
        ]
        job["command_argv"] = argv
        job["command"] = shlex.join(argv)
        job["status"] = (
            "complete"
            if Path(job["calibration_output"]).is_file()
            and Path(job["evaluation_output"]).is_file()
            else "pending"
        )
    if getattr(args, "fraction_selection", None):
        fraction_selection = _load_json(args.fraction_selection)
        core_ids = {job["run_id"] for job in jobs}
        additional_ids = sorted(
            {
                run_id
                for row in fraction_selection["selected_fraction_cells"]
                for run_id in row["retained_run_ids"]
            }
            - core_ids
        )
        if len(additional_ids) != 27:
            raise ValueError("Calibration plan requires 27 additional fraction checkpoints")
        for run_id in additional_ids:
            output_dir = Path(args.calibration_root) / run_id
            argv = [
                args.python_bin,
                str(SCRIPT_DIR / "evaluate_multipath_model_on_dataset.py"),
                "--merged_dir", str(args.merged_dir),
                "--split", "val",
                "--model", str(Path(args.training_root) / run_id / "best_model"),
                "--anchors", str(args.anchors),
                "--fit-calibration",
                "--calibration-output-json", str(output_dir / "calibration.json"),
                "--output_json", str(output_dir / "validation_metrics.json"),
                "--require-complete-interaction-history",
            ]
            jobs.append(
                {
                    "job_id": f"calibrate__{run_id}",
                    "run_id": run_id,
                    "split": "val",
                    "calibration_output": str(output_dir / "calibration.json"),
                    "evaluation_output": str(output_dir / "validation_metrics.json"),
                    "status": (
                        "complete"
                        if (output_dir / "calibration.json").is_file()
                        and (output_dir / "validation_metrics.json").is_file()
                        else "pending"
                    ),
                    "command_argv": argv,
                    "command": shlex.join(argv),
                }
            )
    if len(jobs) not in {63, 90}:
        raise ValueError("Calibration plan must contain 63 core or 90 core+fraction jobs")
    return jobs


def _latency_jobs(selection: Mapping[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    completion_by_run = {
        run_id: _load_json(Path(args.training_root) / run_id / "TRAINING_COMPLETE.json")
        for cell in selection["selected_cells"]
        for run_id in cell["retained_run_ids"]
    }
    jobs = []
    for run_id, completion in sorted(completion_by_run.items()):
        output = Path(args.latency_root) / run_id / "latency.json"
        argv = [
            args.python_bin,
            str(SCRIPT_DIR / "measure_capacity_model_latency_v3.py"),
            "--model",
            str(Path(args.training_root) / run_id / "best_model"),
            "--merged-dir",
            str(args.merged_dir),
            "--run-id",
            run_id,
            "--trainable-parameters",
            str(completion["parameters"]["trainable_parameters"]),
            "--output-json",
            str(output),
        ]
        jobs.append(
            {
                "run_id": run_id,
                "status": "complete" if output.is_file() else "pending",
                "output": str(output),
                "command_argv": argv,
                "command": shlex.join(argv),
            }
        )
    if len(jobs) != 63:
        raise ValueError("Latency plan requires 63 selected seed checkpoints")
    return jobs


def _execute_pending(jobs: list[dict[str, Any]]) -> None:
    for job in jobs:
        if job["status"] == "pending":
            subprocess.run(job["command_argv"], check=True)


def _fresh_jobs(freeze: Mapping[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    jobs = fresh_evaluation_jobs(
        freeze,
        training_root=args.training_root,
        calibration_root=args.calibration_root,
        dataset_roots={
            "general_test": args.general_test,
            "interaction_challenge": args.interaction_challenge,
        },
        output_root=args.output_root,
        anchors=args.anchors,
    )
    for job in jobs:
        argv = [
            args.python_bin,
            str(SCRIPT_DIR / "evaluate_multipath_model_on_dataset.py"),
            "--merged_dir",
            job["merged_dir"],
            "--split",
            "test",
            "--model",
            job["model"],
            "--anchors",
            job["anchors"],
            "--calibration-json",
            job["calibration"],
            "--output_json",
            job["output"],
            "--require-complete-interaction-history",
        ]
        job["command_argv"] = argv
        job["command"] = shlex.join(argv)
        job["status"] = "complete" if Path(job["output"]).is_file() else "pending"
    data_efficiency = freeze.get("data_efficiency") or {}
    additional = data_efficiency.get("additional_retained_records", [])
    fraction_by_run = {
        run_id: row
        for row in data_efficiency.get("selected_fraction_cells", [])
        for run_id in row["retained_run_ids"]
    }
    for retained in additional:
        run_id = retained["run_id"]
        cell = fraction_by_run[run_id]
        for dataset, merged_dir in (
            ("general_test", args.general_test),
            ("interaction_challenge", args.interaction_challenge),
        ):
            output = Path(args.output_root) / "data_efficiency" / dataset / f"{run_id}.json"
            argv = [
                args.python_bin,
                str(SCRIPT_DIR / "evaluate_multipath_model_on_dataset.py"),
                "--merged_dir", str(merged_dir),
                "--split", "test",
                "--model", str(Path(args.training_root) / run_id / "best_model"),
                "--anchors", str(args.anchors),
                "--calibration-json", str(Path(args.calibration_root) / run_id / "calibration.json"),
                "--output_json", str(output),
                "--require-complete-interaction-history",
            ]
            jobs.append(
                {
                    "job_id": f"evaluate__data_efficiency__{dataset}__{run_id}",
                    "dataset": dataset,
                    "run_id": run_id,
                    "model_cell_id": cell["model_cell_id"],
                    "data_fraction": cell["data_fraction"],
                    "output": str(output),
                    "status": "complete" if output.is_file() else "pending",
                    "command_argv": argv,
                    "command": shlex.join(argv),
                }
            )
    if len(jobs) != 126 + 2 * len(additional):
        raise ValueError("Fresh evaluation plan count drift")
    return jobs


def audit_fresh_evaluations(jobs: list[Mapping[str, Any]]) -> dict[str, Any]:
    failures = []
    membership_by_dataset: dict[str, set[str]] = {}
    supports: dict[str, dict[str, int]] = {}
    artifacts = []
    expected_groups = {"general_test": 10, "interaction_challenge": 20}
    for job in jobs:
        path = Path(job["output"])
        if not path.is_file():
            failures.append(f"missing:{job['job_id']}")
            continue
        value = _load_json(path)
        if value.get("status") != "pass" or value.get("split") != "test":
            failures.append(f"status_or_split:{job['job_id']}")
        if value.get("calibration_fit_uses_test") is not False:
            failures.append(f"test_fitted_calibration:{job['job_id']}")
        if value.get("requires_complete_interaction_history") is not True:
            failures.append(f"incomplete_history_eligibility:{job['job_id']}")
        dataset = str(job["dataset"])
        if int(value.get("independent_init_groups", -1)) != expected_groups[dataset]:
            failures.append(f"group_count:{job['job_id']}")
        membership_by_dataset.setdefault(dataset, set()).add(
            str(value.get("sample_membership_sha256"))
        )
        horizon = value.get("trained_history_horizon_s")
        cell_id = str(job["model_cell_id"])
        expected_horizon = None
        if "-h0p0-" in cell_id:
            expected_horizon = 0.0
        elif "-h0p4-" in cell_id:
            expected_horizon = 0.4
        elif "-h1p0-" in cell_id:
            expected_horizon = 1.0
        if horizon != expected_horizon:
            failures.append(f"history_horizon:{job['job_id']}")
        if dataset not in supports:
            supports[dataset] = {
                name: int((value.get("calibrated") or {}).get("response_strata_v3", {}).get(name, {}).get("windows", 0))
                for name in (
                    "assertive",
                    "reactive_pre_response",
                    "response_onset",
                    "response_active",
                )
            }
        artifacts.append({"job_id": job["job_id"], "sha256": sha256_file(path)})
    for dataset, hashes in membership_by_dataset.items():
        if len(hashes) != 1:
            failures.append(f"sample_membership_mismatch:{dataset}")
    report = {
        "schema_version": "capacity_history_fresh_evaluation_audit_v3",
        "status": "pass" if not failures and len(artifacts) == len(jobs) else "fail",
        "planned_jobs": len(jobs),
        "completed_jobs": len(artifacts),
        "failures": failures,
        "sample_membership_sha256_by_dataset": {
            key: sorted(value) for key, value in membership_by_dataset.items()
        },
        "response_stratum_window_support": supports,
        "artifacts": artifacts,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    selection = sub.add_parser("select")
    selection.add_argument("--training-root", required=True, type=Path)
    selection.add_argument("--extension-root", type=Path)
    selection.add_argument("--selection-output", required=True, type=Path)
    selection.add_argument("--convergence-output", required=True, type=Path)
    selection.add_argument("--validation-rows-output", required=True, type=Path)
    selection.add_argument("--fraction-selection-output", required=True, type=Path)
    selection.add_argument("--fraction-convergence-output", required=True, type=Path)
    selection.add_argument("--fraction-validation-rows-output", required=True, type=Path)
    extension = sub.add_parser("extensions")
    extension.add_argument("--convergence", required=True, type=Path)
    extension.add_argument("--merged-dir", required=True, type=Path)
    extension.add_argument("--base-model", required=True, type=Path)
    extension.add_argument("--anchors", required=True, type=Path)
    extension.add_argument("--output-root", required=True, type=Path)
    extension.add_argument("--python-bin", default="python")
    extension.add_argument("--plan-output", required=True, type=Path)
    extension.add_argument("--execute", action="store_true")
    calibration = sub.add_parser("calibrate")
    calibration.add_argument("--selection", required=True, type=Path)
    calibration.add_argument("--fraction-selection", required=True, type=Path)
    calibration.add_argument("--training-root", required=True, type=Path)
    calibration.add_argument("--calibration-root", required=True, type=Path)
    calibration.add_argument("--latency-root", required=True, type=Path)
    calibration.add_argument("--merged-dir", required=True, type=Path)
    calibration.add_argument("--anchors", required=True, type=Path)
    calibration.add_argument("--python-bin", default="python")
    calibration.add_argument("--plan-output", required=True, type=Path)
    calibration.add_argument("--execute", action="store_true")
    freeze_parser = sub.add_parser("freeze")
    for name in ("selection", "fraction_selection", "fraction_convergence", "convergence", "training_root", "calibration_root", "latency_root", "data_provenance"):
        freeze_parser.add_argument("--" + name.replace("_", "-"), required=True, type=Path)
    freeze_parser.add_argument("--source-revision", required=True)
    freeze_parser.add_argument("--output", required=True, type=Path)
    fresh = sub.add_parser("fresh-evaluate")
    fresh.add_argument("--freeze", required=True, type=Path)
    fresh.add_argument("--training-root", required=True, type=Path)
    fresh.add_argument("--calibration-root", required=True, type=Path)
    fresh.add_argument("--general-test", required=True, type=Path)
    fresh.add_argument("--interaction-challenge", required=True, type=Path)
    fresh.add_argument("--output-root", required=True, type=Path)
    fresh.add_argument("--anchors", required=True, type=Path)
    fresh.add_argument("--python-bin", default="python")
    fresh.add_argument("--plan-output", required=True, type=Path)
    fresh.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.command == "select":
        selected, convergence, rows = select_and_audit_convergence(
            args.training_root, extension_root=args.extension_root
        )
        atomic_json(args.selection_output, selected)
        atomic_json(args.convergence_output, convergence)
        atomic_json(args.validation_rows_output, rows)
        fraction_selection, fraction_convergence, fraction_rows = (
            select_and_audit_fraction_convergence(
                args.training_root, extension_root=args.extension_root
            )
        )
        atomic_json(args.fraction_selection_output, fraction_selection)
        atomic_json(args.fraction_convergence_output, fraction_convergence)
        atomic_json(args.fraction_validation_rows_output, fraction_rows)
        report = {
            "status": convergence["status"],
            "selected_cells": 21,
            "selected_fraction_cells": 12,
            "fraction_convergence_status": fraction_convergence["status"],
        }
    elif args.command == "extensions":
        convergence = _load_json(args.convergence)
        plan = extension_execution_plan(
            convergence,
            convergence_path=args.convergence,
            merged_dir=args.merged_dir,
            base_model=args.base_model,
            anchors=args.anchors,
            output_root=args.output_root,
            python_bin=args.python_bin,
        )
        atomic_json(args.plan_output, plan)
        if args.execute:
            _execute_pending(plan["jobs"])
        report = plan
    elif args.command == "calibrate":
        selected = _load_json(args.selection)
        calibration_jobs_with_commands = _command_jobs_for_calibration(selected, args)
        latency_jobs = _latency_jobs(selected, args)
        report = {
            "schema_version": "capacity_history_calibration_latency_plan_v3",
            "status": "pass",
            "calibration_jobs": calibration_jobs_with_commands,
            "latency_jobs": latency_jobs,
        }
        atomic_json(args.plan_output, report)
        if args.execute:
            _execute_pending(calibration_jobs_with_commands)
            _execute_pending(latency_jobs)
    elif args.command == "freeze":
        selected, convergence = _load_json(args.selection), _load_json(args.convergence)
        run_ids = [run_id for cell in selected["selected_cells"] for run_id in cell["retained_run_ids"]]
        training = {
            run_id: _load_valid_training_completion(
                args.training_root / run_id / "TRAINING_COMPLETE.json"
            )
            for run_id in run_ids
        }
        calibrations = {
            run_id: _load_json(args.calibration_root / run_id / "calibration.json")
            for run_id in run_ids
        }
        latencies = {
            run_id: _load_json(args.latency_root / run_id / "latency.json")
            for run_id in run_ids
        }
        payload = build_selection_freeze(
            selection=selected,
            convergence=convergence,
            training_completions=training,
            calibration_records=calibrations,
            latency_records=latencies,
            data_provenance=_load_json(args.data_provenance),
            source_revision=args.source_revision,
            data_efficiency_selection=_load_json(args.fraction_selection),
            data_efficiency_convergence=_load_json(args.fraction_convergence),
            data_efficiency_training_completions={
                run_id: _load_valid_training_completion(
                    args.training_root / run_id / "TRAINING_COMPLETE.json"
                )
                for run_id in {
                    run_id
                    for row in _load_json(args.fraction_selection)["selected_fraction_cells"]
                    for run_id in row["retained_run_ids"]
                }
                - set(run_ids)
            },
            data_efficiency_calibration_records={
                run_id: _load_json(args.calibration_root / run_id / "calibration.json")
                for run_id in {
                    run_id
                    for row in _load_json(args.fraction_selection)["selected_fraction_cells"]
                    for run_id in row["retained_run_ids"]
                }
                - set(run_ids)
            },
        )
        report = freeze_to_path(args.output, payload)
    else:
        freeze = _load_json(args.freeze)
        jobs = _fresh_jobs(freeze, args)
        report = {
            "schema_version": "capacity_history_fresh_evaluation_plan_v3",
            "status": "pass",
            "jobs": jobs,
            "planned": len(jobs),
            "pending": sum(row["status"] == "pending" for row in jobs),
        }
        atomic_json(args.plan_output, report)
        if args.execute:
            _execute_pending(jobs)
            report = audit_fresh_evaluations(jobs)
            if report["status"] != "pass":
                raise ValueError(f"Fresh evaluation audit failed: {report['failures']}")
            write_immutable_manifest(
                Path(args.output_root) / "FRESH_EVALUATION_COMPLETE.json", report
            )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
