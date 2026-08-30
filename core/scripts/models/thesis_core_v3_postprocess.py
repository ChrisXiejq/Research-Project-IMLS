#!/usr/bin/env python3
"""Orchestrate, freeze, and synthesize the thesis-core post-training study."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

import numpy as np

from audit_thesis_core_v3_training import audit as audit_training
from audit_future_mask_v4_offline import audit_training_curves
from capacity_study_v3_analysis import (
    crossed_seed_init_sensitivity,
    effect_summary,
    synthesize_three_axes,
)
from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload
from thesis_core_v3_runs import shard_runs, thesis_core_runs, validate_thesis_core_manifest


SCRIPT_DIR = Path(__file__).resolve().parent
TRAINING_AUDIT_SCHEMA = "capacity_history_thesis_core_training_audit_v4_masked"
CALIBRATION_SCHEMA = "multipath_posthoc_calibration_v4_masked"
SELECTION_EVALUATION_SCHEMA = "capacity_history_thesis_core_selection_evaluation_v4_masked"
HELDOUT_EVALUATION_SCHEMA = "capacity_history_thesis_core_heldout_evaluation_v4_masked"
FULL_HORIZON_EVALUATION_SCHEMA = (
    "capacity_history_thesis_core_full_horizon_sensitivity_v4_masked"
)
SELECTION_FREEZE_SCHEMA = "capacity_history_thesis_core_selection_freeze_v4_masked"
OFFLINE_SYNTHESIS_SCHEMA = "capacity_history_thesis_core_offline_synthesis_v4_masked"
FUTURE_VALIDITY_CONTRACT = "future_valid_mask_fail_closed_v4"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_valid(payload: Mapping[str, Any], field: str) -> bool:
    value = dict(payload)
    recorded = value.pop(field, None)
    return recorded == sha256_payload(value)


def _artifact_identity(record: Mapping[str, Any]) -> str:
    value = record.get("sha256_tree") or record.get("sha256")
    if not value:
        raise ValueError("Artifact record lacks identity")
    return str(value)


def _representative(cell: Mapping[str, Any]) -> str:
    scores = {int(seed): float(score) for seed, score in cell["seed_scores"].items()}
    target = median(scores.values())
    chosen = min(scores, key=lambda seed: (abs(scores[seed] - target), seed))
    matches = [run_id for run_id in cell["retained_run_ids"] if f"__s{chosen}__" in run_id]
    if len(matches) != 1:
        raise ValueError(f"Representative seed resolution failed: {cell['model_cell_id']}")
    return matches[0]


def _stage_complete(
    stage: str,
    run_id: str,
    output_root: Path,
    freeze: Mapping[str, Any] | None,
) -> bool:
    name, hash_field, schema_field, expected_schema = {
        "calibrate": (
            "calibration.json",
            "calibration_sha256",
            "calibration_schema_version",
            CALIBRATION_SCHEMA,
        ),
        "latency": (
            "latency.json",
            "latency_sha256",
            "schema_version",
            "capacity_history_thesis_core_latency_v3",
        ),
        "heldout": (
            "heldout_metrics.json",
            "evaluation_sha256",
            "schema_version",
            HELDOUT_EVALUATION_SCHEMA,
        ),
        "full_horizon": (
            "full_horizon_metrics.json",
            "evaluation_sha256",
            "schema_version",
            FULL_HORIZON_EVALUATION_SCHEMA,
        ),
    }[stage]
    path = output_root / run_id / name
    if not path.is_file():
        return False
    try:
        payload = _load(path)
        if (
            payload.get("status", "pass") != "pass"
            or payload.get(schema_field) != expected_schema
            or not _hash_valid(payload, hash_field)
        ):
            return False
        if payload.get("run_id") != run_id:
            return False
        if stage == "calibrate":
            selection_path = output_root / run_id / "selection_metrics.json"
            if not selection_path.is_file():
                return False
            selection = _load(selection_path)
            if (
                not _hash_valid(selection, "evaluation_sha256")
                or selection.get("schema_version") != SELECTION_EVALUATION_SCHEMA
                or selection.get("status") != "pass"
                or selection.get("run_id") != run_id
                or selection.get("future_validity_contract")
                != FUTURE_VALIDITY_CONTRACT
                or selection.get("calibration_sha256")
                != payload.get("calibration_sha256")
                or selection.get("model_cell_id") != payload.get("model_cell_id")
                or int(selection.get("seed", -1)) != int(payload.get("seed", -2))
                or selection.get("model_artifact") != payload.get("model_artifact")
                or selection.get("cached_weights_artifact")
                != payload.get("cached_weights_artifact")
                or selection.get("cache_complete_sha256")
                != payload.get("cache_complete_sha256")
                or selection.get("dataset_complete_sha256")
                != payload.get("dataset_complete_sha256")
            ):
                return False
        if stage in {"heldout", "full_horizon"} and (
            freeze is None
            or payload.get("selection_freeze_sha256") != freeze.get("freeze_sha256")
            or payload.get("future_validity_contract") != FUTURE_VALIDITY_CONTRACT
        ):
            return False
        if stage in {"heldout", "full_horizon"}:
            frozen_matches = [
                row for row in freeze.get("runs", []) if row.get("run_id") == run_id
            ]
            if len(frozen_matches) != 1:
                return False
            frozen = frozen_matches[0]
            model_identity = payload.get("model_artifact", {}).get(
                "sha256_tree"
            ) or payload.get("model_artifact", {}).get("sha256")
            if (
                payload.get("training_completion_sha256")
                != frozen.get("training_completion_sha256")
                or payload.get("model_cell_id") != frozen.get("model_cell_id")
                or int(payload.get("seed", -1)) != int(frozen.get("seed", -2))
                or model_identity != frozen.get("model_identity")
                or payload.get("cached_weights_artifact", {}).get("sha256")
                != frozen.get("cached_weights_sha256")
                or payload.get("cache_complete_sha256")
                != freeze.get("cache_complete_sha256")
                or payload.get("dataset_complete_sha256")
                != freeze.get("dataset_complete_sha256")
            ):
                return False
        if stage == "heldout" and payload.get("evidence_status") != "retrospective_held_out":
            return False
        if (
            stage == "full_horizon"
            and payload.get("evidence_status")
            != "retrospective_heldout_full_horizon_sensitivity"
        ):
            return False
        if stage == "full_horizon":
            calibration = payload.get("calibration", {})
            if (
                not _hash_valid(calibration, "calibration_sha256")
                or calibration.get("calibration_schema_version")
                != "multipath_posthoc_calibration_v4_full_horizon_sensitivity"
                or calibration.get("fit_role")
                != "groups_36_40_full_horizon_only_sensitivity"
                or calibration.get("calibration_fit_uses_test") is not False
                or int(payload.get("selection_full_horizon_samples", -1)) != 330
                or int(payload.get("heldout_full_horizon_samples", -1)) != 326
                or calibration.get("training_completion_sha256")
                != payload.get("training_completion_sha256")
                or calibration.get("model_artifact") != payload.get("model_artifact")
                or calibration.get("cached_weights_artifact")
                != payload.get("cached_weights_artifact")
                or calibration.get("cache_complete_sha256")
                != payload.get("cache_complete_sha256")
                or calibration.get("dataset_complete_sha256")
                != payload.get("dataset_complete_sha256")
            ):
                return False
        return True
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def stage_plan(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load(args.manifest)
    validate_thesis_core_manifest(manifest)
    assigned = {
        row.run_id for row in shard_runs(
            thesis_core_runs(), args.shard_index, args.shard_count
        )
    }
    freeze = None
    if args.stage in {"heldout", "full_horizon"}:
        if not args.selection_freeze or not args.selection_freeze.is_file():
            raise ValueError("Held-out stage is blocked until selection freeze exists")
        freeze = _load(args.selection_freeze)
        if (
            not _hash_valid(freeze, "freeze_sha256")
            or freeze.get("schema_version") != SELECTION_FREEZE_SCHEMA
            or freeze.get("status") != "pass"
            or freeze.get("future_validity_contract") != FUTURE_VALIDITY_CONTRACT
        ):
            raise ValueError("Held-out stage is blocked by invalid selection freeze")
    jobs = []
    for spec in manifest["runs"]:
        run_id = str(spec["run_id"])
        if run_id not in assigned:
            continue
        output_dir = args.output_root / run_id
        if args.stage in {"calibrate", "heldout", "full_horizon"}:
            evaluation_mode = (
                "full-horizon-sensitivity"
                if args.stage == "full_horizon"
                else args.stage
            )
            command = [
                args.python_bin,
                str(SCRIPT_DIR / "evaluate_thesis_core_cached_v3.py"),
                evaluation_mode,
                "--manifest", str(args.manifest),
                "--training-root", str(args.training_root),
                "--dataset-dir", str(args.dataset_dir),
                "--cache-dir", str(args.cache_dir),
                "--base-model", str(args.base_model),
                "--anchors", str(args.anchors),
                "--run-id", run_id,
                "--output-dir", str(output_dir),
            ]
            if args.stage == "heldout":
                command.extend(
                    [
                        "--calibration-root", str(args.calibration_root),
                        "--selection-freeze", str(args.selection_freeze),
                    ]
                )
            elif args.stage == "full_horizon":
                command.extend(
                    ["--selection-freeze", str(args.selection_freeze)]
                )
        else:
            command = [
                args.python_bin,
                str(SCRIPT_DIR / "measure_thesis_core_latency_v3.py"),
                "--manifest", str(args.manifest),
                "--training-root", str(args.training_root),
                "--dataset-dir", str(args.dataset_dir),
                "--run-id", run_id,
                "--output", str(output_dir / "latency.json"),
            ]
        jobs.append(
            {
                "run_id": run_id,
                "model_cell_id": spec["model_cell_id"],
                "status": "complete" if _stage_complete(
                    args.stage, run_id, args.output_root, freeze
                ) else "pending",
                "command_argv": command,
            }
        )
    return {
        "schema_version": f"capacity_history_thesis_core_{args.stage}_plan_v4_masked",
        "status": "pass",
        "stage": args.stage,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "assigned_runs": len(jobs),
        "complete_runs": sum(row["status"] == "complete" for row in jobs),
        "pending_runs": sum(row["status"] == "pending" for row in jobs),
        "jobs": jobs,
    }


def execute_stage(args: argparse.Namespace) -> dict[str, Any]:
    plan = stage_plan(args)
    if args.execute:
        for job in plan["jobs"]:
            if job["status"] == "pending":
                subprocess.run(job["command_argv"], check=True)
        plan = stage_plan(args)
        if plan["pending_runs"]:
            raise ValueError(f"Stage remains incomplete: {plan['pending_runs']}")
    if args.plan_output:
        atomic_json(args.plan_output, plan)
    return plan


def freeze_selection(args: argparse.Namespace) -> dict[str, Any]:
    audit = _load(args.training_audit)
    if (
        not _hash_valid(audit, "audit_sha256")
        or audit.get("schema_version") != TRAINING_AUDIT_SCHEMA
        or audit.get("status") != "pass"
        or audit.get("future_validity_contract") != FUTURE_VALIDITY_CONTRACT
    ):
        raise ValueError("Selection freeze blocked by invalid training audit")
    convergence = audit_training_curves(args.training_root, args.manifest)
    convergence["audit_sha256"] = sha256_payload(convergence)
    convergence_path = args.output.with_name("training_curve_audit_pre_freeze.json")
    atomic_json(convergence_path, convergence)
    if convergence.get("status") != "pass":
        raise ValueError(
            "Selection freeze blocked by unresolved boundary-underfit risk: "
            f"{convergence.get('unresolved_boundary_underfit_runs')}"
        )
    manifest = _load(args.manifest)
    validate_thesis_core_manifest(manifest)
    spec_by_run = {row["run_id"]: row for row in manifest["runs"]}
    cell_by_id = {row["model_cell_id"]: row for row in audit["cells"]}
    run_records = []
    latencies_by_cell: dict[str, list[float]] = {}
    for run_id, spec in spec_by_run.items():
        calibration = _load(args.calibration_root / run_id / "calibration.json")
        latency = _load(args.latency_root / run_id / "latency.json")
        completion = _load(args.training_root / run_id / "TRAINING_COMPLETE.json")
        if (
            not _hash_valid(calibration, "calibration_sha256")
            or calibration.get("calibration_schema_version") != CALIBRATION_SCHEMA
            or calibration.get("future_validity", {}).get("contract")
            != FUTURE_VALIDITY_CONTRACT
            or calibration.get("fit_role") != "groups_36_40_selection"
            or calibration.get("calibration_fit_uses_test") is not False
            or calibration.get("run_id") != run_id
            or calibration.get("model_artifact") != completion.get("best_model")
            or calibration.get("cached_weights_artifact")
            != completion.get("cached_weights")
            or calibration.get("cache_complete_sha256")
            != completion.get("cache_complete_sha256")
            or calibration.get("dataset_complete_sha256")
            != completion.get("dataset_complete_sha256")
        ):
            raise ValueError(f"Invalid selection calibration: {run_id}")
        if (
            not _hash_valid(latency, "latency_sha256")
            or latency.get("status") != "pass"
            or latency.get("run_id") != run_id
            or latency.get("model_artifact") != completion["best_model"]
        ):
            raise ValueError(f"Invalid latency record: {run_id}")
        latencies_by_cell.setdefault(spec["model_cell_id"], []).append(
            float(latency["mean_ms"])
        )
        run_records.append(
            {
                "run_id": run_id,
                "model_cell_id": spec["model_cell_id"],
                "seed": int(spec["seed"]),
                "training_completion_sha256": completion["completion_sha256"],
                "model_identity": _artifact_identity(completion["best_model"]),
                "cached_weights_sha256": completion["cached_weights"]["sha256"],
                "cache_complete_sha256": completion["cache_complete_sha256"],
                "dataset_complete_sha256": completion["dataset_complete_sha256"],
                "calibration_sha256": calibration["calibration_sha256"],
                "latency_sha256": latency["latency_sha256"],
                "warmed_batch_one_mean_ms": float(latency["mean_ms"]),
            }
        )

    cells = []
    candidates = []
    for cell_id, audited in sorted(cell_by_id.items()):
        median_latency = float(median(latencies_by_cell[cell_id]))
        representative = _representative(audited)
        record = {
            **audited,
            "selected_learning_rate": 1.0e-4,
            "representative_run_id": representative,
            "median_warmed_batch_one_latency_ms": median_latency,
            "latency_gate_pass": median_latency <= 50.0,
        }
        cells.append(record)
        if audited["model_cell_id"].startswith(("mlp-", "transformer-")) and record[
            "latency_gate_pass"
        ]:
            candidates.append(
                (
                    float(audited["median_validation_rollout_macro_nll"]),
                    int(audited["trainable_parameters"]),
                    median_latency,
                    cell_id,
                    record,
                )
            )
    if not candidates:
        raise ValueError("No sequence-model candidate passed the latency gate")
    selected = min(candidates, key=lambda value: value[:4])[4]
    p_star = {
        "role": "P_star",
        "model_cell_id": selected["model_cell_id"],
        "representative_run_id": selected["representative_run_id"],
        "retained_run_ids": selected["retained_run_ids"],
        "median_validation_rollout_macro_nll": selected[
            "median_validation_rollout_macro_nll"
        ],
        "trainable_parameters": selected["trainable_parameters"],
        "median_warmed_batch_one_latency_ms": selected[
            "median_warmed_batch_one_latency_ms"
        ],
        "selection_rule": [
            "median_validation_rollout_macro_nll",
            "trainable_parameters",
            "median_warmed_batch_one_latency_ms",
            "model_cell_id",
        ],
    }
    b1 = next(row for row in cells if row["model_cell_id"] == "head-large")
    payload = {
        "schema_version": SELECTION_FREEZE_SCHEMA,
        "status": "pass",
        "evidence_status": "retrospective_held_out",
        "selection_split": "groups_36_40",
        "heldout_split": "groups_41_45_retrospective",
        "heldout_access_authorized": True,
        "post_outcome_budget_extension_performed": False,
        "future_validity_contract": FUTURE_VALIDITY_CONTRACT,
        "training_audit": str(args.training_audit.resolve()),
        "training_audit_sha256": audit["audit_sha256"],
        "training_curve_audit": str(convergence_path.resolve()),
        "training_curve_audit_sha256": convergence["audit_sha256"],
        "manifest_sha256": sha256_file(args.manifest),
        "dataset_complete_sha256": next(iter(audit["dataset_identity_counts"])),
        "cache_complete_sha256": next(iter(audit["cache_identity_counts"])),
        "cells": cells,
        "runs": sorted(run_records, key=lambda row: row["run_id"]),
        "B1": {
            "role": "B1",
            "model_cell_id": "head-large",
            "representative_run_id": b1["representative_run_id"],
            "retained_run_ids": b1["retained_run_ids"],
        },
        "P_star": p_star,
        "claim_boundary": (
            "Selection used groups 36--40 only. Groups 41--45 are retrospective "
            "held-out evidence and do not constitute a fresh confirmatory test."
        ),
    }
    payload["freeze_sha256"] = sha256_payload(payload)
    if args.output.exists():
        existing = _load(args.output)
        if existing != payload:
            raise ValueError("Refusing to overwrite a different immutable selection freeze")
    else:
        atomic_json(args.output, payload)
    return payload


def _heldout_rows(freeze: Mapping[str, Any], heldout_root: Path) -> list[dict[str, Any]]:
    rows = []
    frozen_runs = {row["run_id"]: row for row in freeze["runs"]}
    for cell in freeze["cells"]:
        for run_id in cell["retained_run_ids"]:
            report = _load(heldout_root / run_id / "heldout_metrics.json")
            frozen = frozen_runs[run_id]
            if (
                not _hash_valid(report, "evaluation_sha256")
                or report.get("schema_version") != HELDOUT_EVALUATION_SCHEMA
                or report.get("status") != "pass"
                or report.get("selection_freeze_sha256") != freeze["freeze_sha256"]
                or report.get("future_validity_contract") != FUTURE_VALIDITY_CONTRACT
                or report.get("training_completion_sha256")
                != frozen["training_completion_sha256"]
                or report.get("cache_complete_sha256") != freeze["cache_complete_sha256"]
                or report.get("dataset_complete_sha256")
                != freeze["dataset_complete_sha256"]
                or report.get("model_cell_id") != cell["model_cell_id"]
                or int(report.get("seed", -1)) != int(frozen["seed"])
            ):
                raise ValueError(f"Invalid held-out evaluation: {run_id}")
            for group_key, metrics in report["calibrated"]["init_group_aggregation"][
                "per_init_group"
            ].items():
                rows.append(
                    {
                        "dataset": "retrospective_heldout",
                        "model_cell_id": cell["model_cell_id"],
                        "seed": int(report["seed"]),
                        "ego_init_id": int(group_key.rsplit("_", 1)[-1]),
                        "rollout_id": group_key,
                        "rollout_macro_nll": metrics[
                            "trajectory_mixture_NLL_per_step_mean"
                        ],
                        "top1_ADE": metrics["top1_ADE_mean"],
                        "top1_FDE": metrics["top1_FDE_mean"],
                        "source_artifact": str(
                            heldout_root / run_id / "heldout_metrics.json"
                        ),
                    }
                )
    return rows


def _branch(effect: Mapping[str, Any]) -> str:
    low, high = effect["cluster_interval_95"]
    value = float(effect["effect"])
    exact_p = effect.get("holm_adjusted_p")
    if exact_p is None:
        exact_p = effect.get("raw_sign_flip_p")
    exact_resolved = exact_p is not None and float(exact_p) <= 0.05
    if math.isfinite(low) and low > 0.0:
        return (
            "supports_preregistered_direction"
            if exact_resolved
            else "directional_descriptive_exact_test_resolution_limited"
        )
    if math.isfinite(high) and high < 0.0:
        return (
            "opposes_preregistered_direction"
            if exact_resolved
            else "opposing_descriptive_exact_test_resolution_limited"
        )
    return "inconclusive_or_mixed" if value != 0.0 else "null"


def synthesize(args: argparse.Namespace) -> dict[str, Any]:
    freeze = _load(args.selection_freeze)
    if (
        not _hash_valid(freeze, "freeze_sha256")
        or freeze.get("schema_version") != SELECTION_FREEZE_SCHEMA
        or freeze.get("future_validity_contract") != FUTURE_VALIDITY_CONTRACT
    ):
        raise ValueError("Invalid selection freeze")
    rows = _heldout_rows(freeze, args.heldout_root)
    three_axes = synthesize_three_axes(rows, dataset="retrospective_heldout")
    direct = []
    for horizon in ("h0p0", "h0p4", "h1p0"):
        direct.append(
            effect_summary(
                rows,
                contrast_id=f"architecture_direct_mlp_minus_transformer__{horizon}__large",
                terms=(
                    (f"mlp-{horizon}-large", 1.0),
                    (f"transformer-{horizon}-large", -1.0),
                ),
            )
        )
    supporting = [
        effect_summary(
            rows,
            contrast_id="capacity_transformer_full_medium_minus_large",
            terms=(("transformer-h1p0-medium", 1.0), ("transformer-h1p0-large", -1.0)),
        ),
        effect_summary(
            rows,
            contrast_id="capacity_transformer_full_small_minus_medium",
            terms=(("transformer-h1p0-small", 1.0), ("transformer-h1p0-medium", -1.0)),
        ),
        effect_summary(
            rows,
            contrast_id="B1_minus_mlp_full_large",
            terms=(("head-large", 1.0), ("mlp-h1p0-large", -1.0)),
        ),
        effect_summary(
            rows,
            contrast_id="B1_minus_transformer_full_large",
            terms=(("head-large", 1.0), ("transformer-h1p0-large", -1.0)),
        ),
    ]
    cell_seed: dict[tuple[str, int], list[float]] = {}
    for row in rows:
        cell_seed.setdefault((row["model_cell_id"], row["seed"]), []).append(
            float(row["rollout_macro_nll"])
        )
    cell_summaries = []
    for cell in freeze["cells"]:
        values = {
            seed: float(np.mean(members))
            for (cell_id, seed), members in cell_seed.items()
            if cell_id == cell["model_cell_id"]
        }
        cell_summaries.append(
            {
                "model_cell_id": cell["model_cell_id"],
                "trainable_parameters": cell["trainable_parameters"],
                "history_horizon_s": next(
                    row.get("history_horizon_s")
                    for row in _load(args.manifest)["runs"]
                    if row["model_cell_id"] == cell["model_cell_id"]
                ),
                "heldout_rollout_macro_nll_mean": float(np.mean(list(values.values()))),
                "heldout_rollout_macro_nll_seed_sd": float(
                    np.std(list(values.values()), ddof=1)
                ),
                "per_seed": {str(key): value for key, value in sorted(values.items())},
                "selection_median_rollout_macro_nll": cell[
                    "median_validation_rollout_macro_nll"
                ],
            }
        )
    primary = three_axes["primary_contrasts"]
    crossed = []
    for contrast in [*primary, *direct, *supporting]:
        crossed.append(
            crossed_seed_init_sensitivity(
                rows,
                contrast_id=contrast["contrast_id"],
                terms=tuple(
                    (term["model_cell_id"], float(term["coefficient"]))
                    for term in contrast["terms"]
                ),
            )
        )
    payload = {
        "schema_version": OFFLINE_SYNTHESIS_SCHEMA,
        "status": "pass",
        "evidence_status": "retrospective_held_out",
        "selection_freeze_sha256": freeze["freeze_sha256"],
        "evaluated_runs": 27,
        "independent_init_groups": 5,
        "future_validity_contract": FUTURE_VALIDITY_CONTRACT,
        "statistical_scope": (
            "Retrospective descriptive inference over five held-out init groups, "
            "conditional on the three fixed training seeds. Exact two-sided sign-flip "
            "tests cannot attain p<0.05 at n=5."
        ),
        "cell_summaries": cell_summaries,
        "three_axes": three_axes,
        "direct_architecture_contrasts": direct,
        "supporting_contrasts": supporting,
        "crossed_seed_init_sensitivity": crossed,
        "result_branches": {
            row["contrast_id"]: _branch(row) for row in primary
        },
        "B1": freeze["B1"],
        "P_star": freeze["P_star"],
        "claim_boundary": freeze["claim_boundary"],
    }
    payload["synthesis_sha256"] = sha256_payload(payload)
    atomic_json(args.output, payload)
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cell_summaries[0]))
        writer.writeheader()
        writer.writerows(cell_summaries)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--manifest", required=True, type=Path)
    audit_parser.add_argument("--training-root", required=True, type=Path)
    audit_parser.add_argument("--output", required=True, type=Path)

    stage = sub.add_parser("stage")
    stage.add_argument(
        "--stage",
        choices=("calibrate", "latency", "heldout", "full_horizon"),
        required=True,
    )
    stage.add_argument("--manifest", required=True, type=Path)
    stage.add_argument("--training-root", required=True, type=Path)
    stage.add_argument("--dataset-dir", required=True, type=Path)
    stage.add_argument("--cache-dir", required=True, type=Path)
    stage.add_argument("--base-model", required=True, type=Path)
    stage.add_argument("--anchors", required=True, type=Path)
    stage.add_argument("--output-root", required=True, type=Path)
    stage.add_argument("--calibration-root", type=Path)
    stage.add_argument("--selection-freeze", type=Path)
    stage.add_argument("--shard-index", required=True, type=int)
    stage.add_argument("--shard-count", type=int, default=6)
    stage.add_argument("--python-bin", default="python")
    stage.add_argument("--plan-output", type=Path)
    stage.add_argument("--execute", action="store_true")

    freeze = sub.add_parser("freeze")
    freeze.add_argument("--manifest", required=True, type=Path)
    freeze.add_argument("--training-root", required=True, type=Path)
    freeze.add_argument("--training-audit", required=True, type=Path)
    freeze.add_argument("--calibration-root", required=True, type=Path)
    freeze.add_argument("--latency-root", required=True, type=Path)
    freeze.add_argument("--output", required=True, type=Path)

    synthesis = sub.add_parser("synthesize")
    synthesis.add_argument("--manifest", required=True, type=Path)
    synthesis.add_argument("--selection-freeze", required=True, type=Path)
    synthesis.add_argument("--heldout-root", required=True, type=Path)
    synthesis.add_argument("--output", required=True, type=Path)
    synthesis.add_argument("--csv-output", required=True, type=Path)
    args = parser.parse_args()

    if args.command == "audit":
        report = audit_training(args.manifest, args.training_root)
        atomic_json(args.output, report)
    elif args.command == "stage":
        report = execute_stage(args)
    elif args.command == "freeze":
        report = freeze_selection(args)
    else:
        report = synthesize(args)
    print(json.dumps({
        "status": report["status"],
        "schema_version": report["schema_version"],
        **({"pending_runs": report["pending_runs"]} if "pending_runs" in report else {}),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
