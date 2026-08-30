#!/usr/bin/env python3
"""Audit the corrected future-mask V4 offline predictor evidence.

This script is deliberately read-only with respect to experiment products.  It
compares the sealed V3 and V4 feature caches, quantifies the effect of rescoring
the historical 27 checkpoints, and derives a full-horizon-only sensitivity
analysis from the corrected held-out reports.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

import numpy as np

from capacity_study_v3_analysis import (
    crossed_seed_init_sensitivity,
    synthesize_three_axes,
)
from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload
from prediction_dataset_utils import read_jsonl
from prepare_thesis_core_v3_dataset import sample_key
from thesis_core_v3_execute import completion_valid


METRICS = (
    "trajectory_mixture_NLL_per_step_mean",
    "pointwise_mixture_NLL_mean",
    "top1_ADE_mean",
    "top1_FDE_mean",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_valid(payload: Mapping[str, Any], field: str) -> bool:
    value = dict(payload)
    recorded = value.pop(field, None)
    return recorded == sha256_payload(value)


def _discover(root: Path, filename: str) -> dict[str, Path]:
    reports = {path.parent.name: path for path in sorted(root.glob(f"*/{filename}"))}
    if len(reports) != 27:
        raise ValueError(f"Expected 27 {filename} files under {root}, found {len(reports)}")
    return reports


def _mask_summary(labels: np.ndarray, horizon: int = 10) -> dict[str, Any]:
    if labels.ndim != 3 or labels.shape[1:] != (horizon, 3):
        raise ValueError(f"Unexpected cached label shape: {labels.shape}")
    mask = np.asarray(labels[..., 2], dtype=np.float64)
    if not np.all(np.isfinite(mask)) or not np.all(np.isin(mask, (0.0, 1.0))):
        raise ValueError("Cached future mask is not finite binary data")
    valid = mask.astype(bool)
    lengths = np.sum(valid, axis=1)
    if np.any(lengths < 1):
        raise ValueError("Zero-valid-future sample detected")
    expected = np.arange(horizon)[None, :] < lengths[:, None]
    if not np.array_equal(valid, expected):
        raise ValueError("Future mask is not a contiguous valid prefix")
    return {
        "samples": int(len(labels)),
        "horizon_steps": horizon,
        "valid_future_steps": int(np.sum(valid)),
        "invalid_future_steps": int(np.size(valid) - np.sum(valid)),
        "full_horizon_samples": int(np.sum(lengths == horizon)),
        "partial_horizon_samples": int(np.sum(lengths < horizon)),
        "valid_length_histogram": {
            str(key): int(value) for key, value in sorted(Counter(lengths.tolist()).items())
        },
        "mask_sha256": sha256_payload(valid.astype(np.uint8).tolist()),
    }


def audit_cache(old_cache: Path, corrected_cache: Path) -> dict[str, Any]:
    old_manifest = _load(old_cache / "CACHE_COMPLETE.json")
    corrected_manifest = _load(corrected_cache / "CACHE_COMPLETE.json")
    if not _hash_valid(old_manifest, "cache_manifest_sha256") or not _hash_valid(
        corrected_manifest, "cache_manifest_sha256"
    ):
        raise ValueError("Old or corrected cache manifest hash is invalid")
    split_reports = {}
    mask_reports = {}
    for split in ("fit", "selection", "heldout"):
        old_path = old_cache / f"{split}.npz"
        corrected_path = corrected_cache / f"{split}.npz"
        with np.load(old_path, allow_pickle=False) as old, np.load(
            corrected_path, allow_pickle=False
        ) as corrected:
            if set(old.files) != set(corrected.files):
                raise ValueError(f"Cache key drift in {split}")
            arrays = {}
            for key in old.files:
                left = np.asarray(old[key])
                right = np.asarray(corrected[key])
                arrays[key] = {
                    "shape": list(left.shape),
                    "dtype": str(left.dtype),
                    "exactly_equal": bool(
                        left.shape == right.shape
                        and left.dtype == right.dtype
                        and np.array_equal(left, right)
                    ),
                }
                if not arrays[key]["exactly_equal"]:
                    raise ValueError(f"V3/V4 cache tensor drift: {split}/{key}")
            mask_reports[split] = _mask_summary(np.asarray(corrected["labels"]))
        split_reports[split] = {
            "old_sha256": sha256_file(old_path),
            "corrected_sha256": sha256_file(corrected_path),
            "file_sha256_equal": sha256_file(old_path) == sha256_file(corrected_path),
            "arrays": arrays,
        }
    changed_sources = {
        key: {
            "old": old_manifest.get("source_sha256", {}).get(key),
            "corrected": corrected_manifest.get("source_sha256", {}).get(key),
        }
        for key in sorted(
            set(old_manifest.get("source_sha256", {}))
            | set(corrected_manifest.get("source_sha256", {}))
        )
        if old_manifest.get("source_sha256", {}).get(key)
        != corrected_manifest.get("source_sha256", {}).get(key)
    }
    return {
        "status": "pass",
        "interpretation": (
            "All cached tensors are byte-for-byte and array-for-array identical; "
            "V4 changes future-mask consumption, not dataset membership or features."
        ),
        "old_manifest_sha256": sha256_file(old_cache / "CACHE_COMPLETE.json"),
        "corrected_manifest_sha256": sha256_file(corrected_cache / "CACHE_COMPLETE.json"),
        "changed_source_files": changed_sources,
        "splits": split_reports,
        "future_masks": mask_reports,
    }


def audit_dataset_mask_strata(dataset_dir: Path, corrected_cache: Path) -> dict[str, Any]:
    split_reports = {}
    for split in ("fit", "selection", "heldout"):
        rows = list(read_jsonl(str(dataset_dir / f"{split}.jsonl")))
        with np.load(corrected_cache / f"{split}.npz", allow_pickle=False) as arrays:
            labels = np.asarray(arrays["labels"])
            cached_ids = [str(value) for value in arrays["sample_ids"].tolist()]
        expected_ids = [sample_key(row) for row in rows]
        if cached_ids != expected_ids or len(rows) != len(labels):
            raise ValueError(f"Dataset/cache membership or order drift in {split}")
        masks = labels[..., 2].astype(bool)
        metadata_masks = np.asarray(
            [row["future_valid_mask"][: masks.shape[1]] for row in rows], dtype=bool
        )
        if not np.array_equal(masks, metadata_masks):
            raise ValueError(f"Dataset/cache future-mask mismatch in {split}")
        strata: dict[str, dict[str, Any]] = {}
        timing_errors = []
        spacing_errors = []
        for index, (row, mask) in enumerate(zip(rows, masks)):
            key = f"ego_init_{int(row['ego_init_id'])}::{row['cell_id']}"
            record = strata.setdefault(
                key,
                {
                    "ego_init_id": int(row["ego_init_id"]),
                    "cell_id": str(row["cell_id"]),
                    "samples": 0,
                    "full_horizon_samples": 0,
                    "partial_horizon_samples": 0,
                    "valid_future_steps": 0,
                    "invalid_future_steps": 0,
                    "source_subruns": set(),
                },
            )
            valid_count = int(np.sum(mask))
            record["samples"] += 1
            record["full_horizon_samples"] += int(valid_count == len(mask))
            record["partial_horizon_samples"] += int(valid_count < len(mask))
            record["valid_future_steps"] += valid_count
            record["invalid_future_steps"] += int(len(mask) - valid_count)
            record["source_subruns"].add(str(row["source_subrun"]))
            times = np.asarray(row["future_times_s"][: len(mask)], dtype=np.float64)
            if len(times) != len(mask) or not np.all(np.isfinite(times)):
                raise ValueError(f"Invalid future time grid in {split} row {index}")
            expected_dt = float(row.get("dt_s", row.get("dt", 0.2)))
            spacing_errors.extend((np.diff(times) - expected_dt).tolist())
            if valid_count == len(mask):
                timing_errors.append(float(times[-1] - float(row["sim_time_s"]) - 2.0))
        serializable_strata = []
        for key, record in sorted(strata.items()):
            record = dict(record)
            record["stratum"] = key
            record["source_subruns"] = sorted(record["source_subruns"])
            serializable_strata.append(record)
        maximum_terminal_error = max((abs(value) for value in timing_errors), default=math.inf)
        maximum_spacing_error = max((abs(value) for value in spacing_errors), default=math.inf)
        if maximum_terminal_error > 1.0e-6 or maximum_spacing_error > 1.0e-6:
            raise ValueError(
                f"FDE time-grid audit failed in {split}: terminal={maximum_terminal_error}, "
                f"spacing={maximum_spacing_error}"
            )
        split_reports[split] = {
            "sample_membership_sha256": sha256_payload(expected_ids),
            "full_horizon_membership_sha256": sha256_payload(
                [
                    expected_ids[index]
                    for index, mask in enumerate(masks)
                    if bool(np.all(mask))
                ]
            ),
            "future_validity": _mask_summary(labels),
            "strata": serializable_strata,
            "strata_count": len(serializable_strata),
            "full_horizon_terminal_time_s": 2.0,
            "maximum_full_horizon_terminal_time_error_s": maximum_terminal_error,
            "maximum_time_step_error_s": maximum_spacing_error,
        }
    return {
        "status": "pass",
        "future_valid_prefix_and_time_grid_verified": True,
        "splits": split_reports,
    }


def audit_formal_report_contracts(
    selection_root: Path,
    heldout_root: Path,
    dataset_contract: Mapping[str, Any],
    training_root: Path,
    manifest_path: Path,
    selection_freeze_path: Path,
) -> dict[str, Any]:
    selections = _discover(selection_root, "selection_metrics.json")
    heldouts = _discover(heldout_root, "heldout_metrics.json")
    if set(selections) != set(heldouts):
        raise ValueError("Corrected selection/held-out run membership differs")
    manifest = _load(manifest_path)
    specs = {str(row["run_id"]): row for row in manifest["runs"]}
    if set(selections) != set(specs):
        raise ValueError("Corrected reports do not cover the frozen 27-run manifest")
    freeze = _load(selection_freeze_path)
    if (
        not _hash_valid(freeze, "freeze_sha256")
        or freeze.get("schema_version")
        != "capacity_history_thesis_core_selection_freeze_v4_masked"
        or freeze.get("status") != "pass"
        or freeze.get("future_validity_contract")
        != "future_valid_mask_fail_closed_v4"
    ):
        raise ValueError("Corrected selection freeze is invalid")
    frozen_runs = {str(row["run_id"]): row for row in freeze["runs"]}
    if set(frozen_runs) != set(specs):
        raise ValueError("Selection freeze does not cover the frozen 27-run manifest")
    expected = {
        "selection": dataset_contract["splits"]["selection"],
        "heldout": dataset_contract["splits"]["heldout"],
    }
    rows = []
    for run_id in sorted(selections):
        selection = _load(selections[run_id])
        heldout = _load(heldouts[run_id])
        spec = specs[run_id]
        completion_path = training_root / run_id / "TRAINING_COMPLETE.json"
        if not completion_valid(completion_path, spec):
            raise ValueError(f"Corrected training receipt is invalid: {run_id}")
        completion = _load(completion_path)
        calibration = _load(selection_root / run_id / "calibration.json")
        frozen = frozen_runs[run_id]
        model_identity = completion["best_model"].get("sha256_tree") or completion[
            "best_model"
        ].get("sha256")
        if (
            not _hash_valid(selection, "evaluation_sha256")
            or selection.get("schema_version")
            != "capacity_history_thesis_core_selection_evaluation_v4_masked"
            or not _hash_valid(heldout, "evaluation_sha256")
            or heldout.get("schema_version")
            != "capacity_history_thesis_core_heldout_evaluation_v4_masked"
            or not _hash_valid(calibration, "calibration_sha256")
            or calibration.get("calibration_schema_version")
            != "multipath_posthoc_calibration_v4_masked"
        ):
            raise ValueError(f"Corrected report schema/hash mismatch: {run_id}")
        if (
            selection.get("training_completion_sha256")
            != completion.get("completion_sha256")
            or heldout.get("training_completion_sha256")
            != completion.get("completion_sha256")
            or selection.get("model_artifact") != completion.get("best_model")
            or heldout.get("model_artifact") != completion.get("best_model")
            or selection.get("cached_weights_artifact")
            != completion.get("cached_weights")
            or heldout.get("cached_weights_artifact")
            != completion.get("cached_weights")
            or selection.get("cache_complete_sha256")
            != completion.get("cache_complete_sha256")
            or heldout.get("cache_complete_sha256")
            != completion.get("cache_complete_sha256")
            or selection.get("dataset_complete_sha256")
            != completion.get("dataset_complete_sha256")
            or heldout.get("dataset_complete_sha256")
            != completion.get("dataset_complete_sha256")
            or selection.get("calibration_sha256")
            != calibration.get("calibration_sha256")
            or heldout.get("calibration_sha256")
            != calibration.get("calibration_sha256")
            or heldout.get("selection_freeze_sha256") != freeze.get("freeze_sha256")
            or frozen.get("training_completion_sha256")
            != completion.get("completion_sha256")
            or frozen.get("model_identity") != model_identity
            or frozen.get("cached_weights_sha256")
            != completion.get("cached_weights", {}).get("sha256")
            or frozen.get("calibration_sha256")
            != calibration.get("calibration_sha256")
            or frozen.get("model_cell_id") != spec.get("model_cell_id")
            or int(frozen.get("seed", -1)) != int(spec.get("seed", -2))
        ):
            raise ValueError(f"Corrected cross-report provenance mismatch: {run_id}")
        for split, report in (("selection", selection), ("heldout", heldout)):
            expected_split = expected[split]
            if report.get("sample_membership_sha256") != expected_split[
                "sample_membership_sha256"
            ]:
                raise ValueError(f"Corrected report membership mismatch: {run_id}/{split}")
            for calibration_state in ("uncalibrated", "calibrated"):
                validity = report[calibration_state]["future_validity"]
                expected_validity = expected_split["future_validity"]
                for field in (
                    "samples",
                    "valid_future_steps",
                    "invalid_future_steps",
                    "full_horizon_samples",
                    "partial_horizon_samples",
                    "mask_sha256",
                ):
                    if validity.get(field) != expected_validity.get(field):
                        raise ValueError(
                            f"Corrected report mask denominator mismatch: "
                            f"{run_id}/{split}/{calibration_state}/{field}"
                        )
                if report[calibration_state].get("FDE_full_horizon_samples") != expected_validity[
                    "full_horizon_samples"
                ]:
                    raise ValueError(f"Corrected FDE denominator mismatch: {run_id}/{split}")
        rows.append(
            {
                "run_id": run_id,
                "model_cell_id": heldout["model_cell_id"],
                "seed": int(heldout["seed"]),
                "training_completion_sha256": heldout["training_completion_sha256"],
                "selection_evaluation_sha256": selection["evaluation_sha256"],
                "heldout_evaluation_sha256": heldout["evaluation_sha256"],
                "selection_freeze_sha256": heldout["selection_freeze_sha256"],
                "model_identity": model_identity,
                "cached_weights_sha256": completion["cached_weights"]["sha256"],
                "calibration_sha256": calibration["calibration_sha256"],
                "cache_complete_sha256": completion["cache_complete_sha256"],
                "dataset_complete_sha256": completion["dataset_complete_sha256"],
                "selection_membership_sha256": selection["sample_membership_sha256"],
                "heldout_membership_sha256": heldout["sample_membership_sha256"],
                "selection_mask_sha256": selection["calibrated"]["future_validity"][
                    "mask_sha256"
                ],
                "heldout_mask_sha256": heldout["calibrated"]["future_validity"][
                    "mask_sha256"
                ],
            }
        )
    return {
        "status": "pass",
        "runs": len(rows),
        "selection_and_heldout_membership_mask_denominators_uniform": True,
        "training_freeze_selection_heldout_identity_chain_verified": True,
        "selection_freeze_sha256": freeze["freeze_sha256"],
        "rows": rows,
    }


def _macro(metrics: Mapping[str, Any], key: str) -> float:
    aggregation = metrics.get("rollout_aggregation", {}).get("macro_mean", {})
    return float(aggregation.get(key, metrics[key]))


def _finite_summary(values: Iterable[float]) -> dict[str, float]:
    array = np.asarray(list(values), dtype=np.float64)
    array = array[np.isfinite(array)]
    if not len(array):
        return {"mean": math.nan, "median": math.nan, "minimum": math.nan, "maximum": math.nan}
    return {
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
    }


def audit_historical_checkpoints(old_root: Path, corrected_root: Path) -> dict[str, Any]:
    old = _discover(old_root, "selection_metrics.json")
    corrected = _discover(corrected_root, "selection_metrics.json")
    if set(old) != set(corrected):
        raise ValueError("Historical/corrected run membership differs")
    rows = []
    for run_id in sorted(old):
        before = _load(old[run_id])
        after = _load(corrected[run_id])
        if not _hash_valid(before, "evaluation_sha256") or not _hash_valid(
            after, "evaluation_sha256"
        ):
            raise ValueError(f"Selection evaluation hash mismatch: {run_id}")
        if before["model_cell_id"] != after["model_cell_id"] or before["seed"] != after["seed"]:
            raise ValueError(f"Run identity drift: {run_id}")
        old_calibration = _load(old[run_id].with_name("calibration.json"))
        new_calibration = _load(corrected[run_id].with_name("calibration.json"))
        if not _hash_valid(old_calibration, "calibration_sha256") or not _hash_valid(
            new_calibration, "calibration_sha256"
        ):
            raise ValueError(f"Calibration hash mismatch: {run_id}")
        if (
            old_calibration.get("model_artifact")
            != new_calibration.get("model_artifact")
            or old_calibration.get("cached_weights_artifact")
            != new_calibration.get("cached_weights_artifact")
        ):
            raise ValueError(
                f"Historical rescore did not use the identical checkpoint artifacts: {run_id}"
            )
        row = {
            "run_id": run_id,
            "model_cell_id": after["model_cell_id"],
            "seed": int(after["seed"]),
            "old_temperature": float(old_calibration["parameters"]["temperature"]),
            "corrected_temperature": float(new_calibration["parameters"]["temperature"]),
            "old_covariance_scale": float(old_calibration["parameters"]["covariance_scale"]),
            "corrected_covariance_scale": float(
                new_calibration["parameters"]["covariance_scale"]
            ),
            "model_artifact_identity": (
                new_calibration["model_artifact"].get("sha256_tree")
                or new_calibration["model_artifact"].get("sha256")
            ),
            "cached_weights_sha256": new_calibration["cached_weights_artifact"][
                "sha256"
            ],
            "corrected_validity": after["uncalibrated"]["future_validity"],
        }
        for state, report in (("old", before), ("corrected", after)):
            for calibration_state in ("uncalibrated", "calibrated"):
                for metric in METRICS:
                    row[f"{state}_{calibration_state}_{metric}"] = _macro(
                        report[calibration_state], metric
                    )
        rows.append(row)
    differences = {}
    for calibration_state in ("uncalibrated", "calibrated"):
        for metric in METRICS:
            key = f"{calibration_state}_{metric}"
            differences[key] = _finite_summary(
                row[f"corrected_{key}"] - row[f"old_{key}"] for row in rows
            )
    cell_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        for state in ("old", "corrected"):
            cell_values[row["model_cell_id"]][state].append(
                row[f"{state}_uncalibrated_trajectory_mixture_NLL_per_step_mean"]
            )
    rankings = {}
    for state in ("old", "corrected"):
        rankings[state] = sorted(
            (
                {
                    "model_cell_id": cell,
                    "median_seed_rollout_macro_nll": float(median(values[state])),
                }
                for cell, values in cell_values.items()
            ),
            key=lambda row: (row["median_seed_rollout_macro_nll"], row["model_cell_id"]),
        )
    return {
        "status": "pass",
        "evidence_role": "diagnostic_rescore_of_historical_wrongly_selected_checkpoints",
        "runs": len(rows),
        "run_membership_sha256": sha256_payload(sorted(old)),
        "differences_corrected_minus_old": differences,
        "old_checkpoint_rankings": rankings,
        "rows": rows,
        "claim_boundary": (
            "These scores quantify metric corruption at the historical selected weights. "
            "They do not repair checkpoint selection or replace the corrected 27-run retraining."
        ),
    }


def _full_horizon_summary(
    reports: Mapping[str, Path],
    *,
    report_filename: str,
    filter_partial: bool,
    dataset_name: str,
) -> dict[str, Any]:
    rows = []
    cell_seed: dict[tuple[str, int], list[float]] = defaultdict(list)
    for run_id, path in reports.items():
        report = _load(path)
        if not _hash_valid(report, "evaluation_sha256"):
            raise ValueError(f"Full-horizon source evaluation hash mismatch: {run_id}")
        samples = report["calibrated"]["sample_metrics_v3"]
        horizon = int(report["calibrated"]["FDE_horizon_steps"])
        eligible_samples = [
            sample
            for sample in samples
            if not filter_partial or int(sample["valid_future_steps"]) == horizon
        ]
        if (
            len(eligible_samples) != 326
            or any(int(sample["valid_future_steps"]) != horizon for sample in eligible_samples)
            or any(sample.get("fixed_horizon_FDE_eligible") is not True for sample in eligible_samples)
            or any(sample.get("top1_FDE") is None for sample in eligible_samples)
        ):
            raise ValueError(
                f"Full-horizon internal sample contract failed: {run_id} "
                f"eligible={len(eligible_samples)}"
            )
        if not filter_partial and len(samples) != 326:
            raise ValueError(
                f"Recalibrated full-horizon report contains non-full or extra rows: {run_id}"
            )
        grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
        for sample in eligible_samples:
            grouped[int(sample["ego_init_id"])].append(sample)
        if set(grouped) != {41, 42, 43, 44, 45}:
            raise ValueError(f"Unexpected full-horizon held-out groups: {run_id}")
        if sum(len(members) for members in grouped.values()) != 326:
            raise ValueError(f"Full-horizon init strata do not sum to 326: {run_id}")
        for ego_init_id, members in sorted(grouped.items()):
            nll = float(np.mean([row["trajectory_mixture_NLL_per_step"] for row in members]))
            rows.append(
                {
                    "dataset": dataset_name,
                    "model_cell_id": report["model_cell_id"],
                    "seed": int(report["seed"]),
                    "ego_init_id": ego_init_id,
                    "rollout_id": f"ego_init_{ego_init_id}",
                    "rollout_macro_nll": nll,
                    "top1_ADE": float(np.mean([row["top1_ADE"] for row in members])),
                    "top1_FDE": float(np.mean([row["top1_FDE"] for row in members])),
                    "full_horizon_samples": len(members),
                    "source_artifact": str(path),
                }
            )
            cell_seed[(report["model_cell_id"], int(report["seed"]))].append(nll)
    axes = synthesize_three_axes(rows, dataset=dataset_name)
    crossed = [
        crossed_seed_init_sensitivity(
            rows,
            contrast_id=contrast["contrast_id"],
            terms=tuple(
                (term["model_cell_id"], float(term["coefficient"]))
                for term in contrast["terms"]
            ),
        )
        for contrast in [
            *axes["primary_contrasts"],
            *axes["supporting_contrasts"],
        ]
    ]
    cells = []
    for cell in sorted({key[0] for key in cell_seed}):
        per_seed = {
            str(seed): float(np.mean(values))
            for (candidate, seed), values in cell_seed.items()
            if candidate == cell
        }
        cells.append(
            {
                "model_cell_id": cell,
                "full_horizon_rollout_macro_nll_mean": float(np.mean(list(per_seed.values()))),
                "full_horizon_rollout_macro_nll_seed_sd": float(
                    np.std(list(per_seed.values()), ddof=1)
                ),
                "per_seed": per_seed,
            }
        )
    return {
        "source_report_filename": report_filename,
        "evaluated_runs": len(reports),
        "rows": rows,
        "cell_summaries": cells,
        "three_axes": axes,
        "crossed_seed_init_sensitivity": crossed,
    }


def full_horizon_sensitivity(
    heldout_root: Path,
    full_horizon_root: Path,
    offline_synthesis_path: Path,
    training_root: Path,
    manifest_path: Path,
    selection_freeze_path: Path,
    dataset_contract: Mapping[str, Any],
) -> dict[str, Any]:
    primary_reports = _discover(heldout_root, "heldout_metrics.json")
    recalibrated_reports = _discover(full_horizon_root, "full_horizon_metrics.json")
    if set(primary_reports) != set(recalibrated_reports):
        raise ValueError("Primary/recalibrated full-horizon run membership differs")
    manifest = _load(manifest_path)
    specs = {str(row["run_id"]): row for row in manifest["runs"]}
    freeze = _load(selection_freeze_path)
    if (
        set(primary_reports) != set(specs)
        or not _hash_valid(freeze, "freeze_sha256")
        or freeze.get("schema_version")
        != "capacity_history_thesis_core_selection_freeze_v4_masked"
    ):
        raise ValueError("Full-horizon sensitivity manifest/freeze gate failed")
    frozen_runs = {str(row["run_id"]): row for row in freeze["runs"]}
    primary = _full_horizon_summary(
        primary_reports,
        report_filename="heldout_metrics.json",
        filter_partial=True,
        dataset_name="retrospective_heldout_full_horizon_primary_calibration",
    )
    recalibrated = _full_horizon_summary(
        recalibrated_reports,
        report_filename="full_horizon_metrics.json",
        filter_partial=False,
        dataset_name="retrospective_heldout_full_horizon_recalibrated",
    )
    calibration_differences = []
    for run_id in sorted(primary_reports):
        primary_report = _load(primary_reports[run_id])
        recalibrated_report = _load(recalibrated_reports[run_id])
        calibration = recalibrated_report.get("calibration", {})
        spec = specs[run_id]
        completion_path = training_root / run_id / "TRAINING_COMPLETE.json"
        if not completion_valid(completion_path, spec):
            raise ValueError(f"Invalid training receipt in full-horizon audit: {run_id}")
        completion = _load(completion_path)
        frozen = frozen_runs.get(run_id, {})
        model_identity = completion["best_model"].get("sha256_tree") or completion[
            "best_model"
        ].get("sha256")
        if (
            recalibrated_report.get("schema_version")
            != "capacity_history_thesis_core_full_horizon_sensitivity_v4_masked"
            or recalibrated_report.get("selection_freeze_sha256")
            != freeze.get("freeze_sha256")
            or primary_report.get("selection_freeze_sha256")
            != freeze.get("freeze_sha256")
            or not _hash_valid(calibration, "calibration_sha256")
            or calibration.get("calibration_schema_version")
            != "multipath_posthoc_calibration_v4_full_horizon_sensitivity"
            or calibration.get("fit_role")
            != "groups_36_40_full_horizon_only_sensitivity"
            or calibration.get("calibration_fit_uses_test") is not False
            or int(recalibrated_report.get("selection_full_horizon_samples", -1)) != 330
            or int(recalibrated_report.get("heldout_full_horizon_samples", -1)) != 326
            or recalibrated_report.get("heldout_membership_sha256")
            != dataset_contract["splits"]["heldout"][
                "full_horizon_membership_sha256"
            ]
            or calibration.get("selection_membership_sha256")
            != dataset_contract["splits"]["selection"][
                "full_horizon_membership_sha256"
            ]
            or recalibrated_report.get("training_completion_sha256")
            != completion.get("completion_sha256")
            or recalibrated_report.get("model_artifact") != completion.get("best_model")
            or recalibrated_report.get("cached_weights_artifact")
            != completion.get("cached_weights")
            or recalibrated_report.get("cache_complete_sha256")
            != completion.get("cache_complete_sha256")
            or recalibrated_report.get("dataset_complete_sha256")
            != completion.get("dataset_complete_sha256")
            or frozen.get("training_completion_sha256")
            != completion.get("completion_sha256")
            or frozen.get("model_identity") != model_identity
            or frozen.get("cached_weights_sha256")
            != completion.get("cached_weights", {}).get("sha256")
        ):
            raise ValueError(f"Invalid full-horizon sensitivity provenance: {run_id}")
        primary_parameters = primary_report["calibrated"]["calibration_parameters"]
        recalibrated_parameters = recalibrated_report["calibration"]["parameters"]
        calibration_differences.append(
            {
                "run_id": run_id,
                "model_cell_id": recalibrated_report["model_cell_id"],
                "seed": int(recalibrated_report["seed"]),
                "primary_temperature": float(primary_parameters["temperature"]),
                "full_horizon_temperature": float(recalibrated_parameters["temperature"]),
                "primary_covariance_scale": float(primary_parameters["covariance_scale"]),
                "full_horizon_covariance_scale": float(
                    recalibrated_parameters["covariance_scale"]
                ),
            }
        )
    official = _load(offline_synthesis_path)
    if (
        not _hash_valid(official, "synthesis_sha256")
        or official.get("schema_version")
        != "capacity_history_thesis_core_offline_synthesis_v4_masked"
        or official.get("selection_freeze_sha256") != freeze.get("freeze_sha256")
    ):
        raise ValueError("Corrected offline synthesis hash is invalid")
    return {
        "status": "pass",
        "evidence_status": "retrospective_heldout_full_horizon_only_sensitivity",
        "evaluated_runs": len(recalibrated_reports),
        "independent_init_groups": 5,
        "rows": recalibrated["rows"],
        "cell_summaries": recalibrated["cell_summaries"],
        "three_axes": recalibrated["three_axes"],
        "primary_mixed_horizon_calibration_filtered_to_full_horizon": primary,
        "full_horizon_selection_recalibrated": recalibrated,
        "calibration_parameter_comparison": calibration_differences,
        "official_all_valid_step_synthesis_sha256": official["synthesis_sha256"],
        "selection_freeze_sha256": freeze["freeze_sha256"],
        "training_freeze_heldout_full_horizon_identity_chain_verified": True,
        "claim_boundary": (
            "This sensitivity excludes partial windows and refits calibration using only "
            "full-horizon selection windows. It complements, rather than replaces, the "
            "primary valid-step analysis. FDE@2.0 s is always supported only here."
        ),
    }


def audit_training_curves(
    training_root: Path,
    manifest_path: Path,
    *,
    tail_epochs: int = 10,
    material_tail_improvement: float = 1.0e-3,
) -> dict[str, Any]:
    manifest = _load(manifest_path)
    rows = []
    unresolved = []
    for spec in manifest["runs"]:
        run_id = str(spec["run_id"])
        run_dir = training_root / run_id
        completion_path = run_dir / "TRAINING_COMPLETE.json"
        if not completion_valid(completion_path, spec):
            raise ValueError(f"Invalid corrected training completion: {run_id}")
        completion = _load(completion_path)
        health = _load(run_dir / "training_health.json")
        with (run_dir / "history.csv").open(newline="", encoding="utf-8") as handle:
            history = list(csv.DictReader(handle))
        scores = np.asarray(
            [float(row["val_rollout_macro_nll"]) for row in history], dtype=np.float64
        )
        train_loss = np.asarray([float(row["loss"]) for row in history], dtype=np.float64)
        val_loss = np.asarray([float(row["val_loss"]) for row in history], dtype=np.float64)
        if not (
            len(scores)
            and np.all(np.isfinite(scores))
            and np.all(np.isfinite(train_loss))
            and np.all(np.isfinite(val_loss))
        ):
            raise ValueError(f"Non-finite or empty corrected training history: {run_id}")
        best_epoch = int(np.argmin(scores)) + 1
        if best_epoch != int(health["best_epoch"]) or best_epoch != int(
            completion["best_epoch"]
        ):
            raise ValueError(f"Best-epoch receipt mismatch: {run_id}")
        epoch_files = sorted((run_dir / "epoch_checkpoints").glob("epoch_*.weights.h5"))
        if len(epoch_files) != len(history):
            raise ValueError(f"Per-epoch recovery checkpoint mismatch: {run_id}")
        start_index = max(0, len(scores) - tail_epochs - 1)
        tail_improvement = float(scores[start_index] - np.min(scores[start_index:]))
        tail_slope = float(
            np.polyfit(
                np.arange(start_index, len(scores), dtype=np.float64),
                scores[start_index:],
                1,
            )[0]
        )
        boundary = best_epoch > len(scores) - 5
        unresolved_boundary = bool(
            boundary and tail_improvement > material_tail_improvement
        )
        if unresolved_boundary:
            unresolved.append(run_id)
        rows.append(
            {
                "run_id": run_id,
                "model_cell_id": spec["model_cell_id"],
                "seed": int(spec["seed"]),
                "epochs_completed": len(scores),
                "best_epoch": best_epoch,
                "best_validation_rollout_macro_nll": float(np.min(scores)),
                "last_validation_rollout_macro_nll": float(scores[-1]),
                "tail_window_epochs": min(tail_epochs + 1, len(scores)),
                "tail_best_improvement": tail_improvement,
                "tail_slope_per_epoch": tail_slope,
                "boundary_best": boundary,
                "unresolved_boundary_underfit_risk": unresolved_boundary,
                "last_train_loss": float(train_loss[-1]),
                "last_validation_loss": float(val_loss[-1]),
                "last_validation_minus_train_loss": float(val_loss[-1] - train_loss[-1]),
                "per_epoch_checkpoints": len(epoch_files),
                "epoch_recovery_preserved": bool(health["epoch_recovery_preserved"]),
                "maximum_trainable_weight_change": float(
                    health["maximum_trainable_weight_change"]
                ),
                "completion_sha256": completion["completion_sha256"],
            }
        )
    if len(rows) != 27:
        raise ValueError(f"Expected 27 corrected training histories, found {len(rows)}")
    return {
        "status": "pass" if not unresolved else "fail",
        "runs": len(rows),
        "tail_epochs": tail_epochs,
        "material_tail_improvement_threshold": material_tail_improvement,
        "boundary_best_runs": sum(row["boundary_best"] for row in rows),
        "unresolved_boundary_underfit_runs": unresolved,
        "finite_histories": True,
        "all_epoch_checkpoints_present": True,
        "rows": rows,
        "interpretation": (
            "A best epoch near the hard limit is accepted only when improvement over the "
            "final tail window is below the frozen materiality threshold."
        ),
    }


def _write_rows(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _cell_means(synthesis: Mapping[str, Any]) -> dict[str, float]:
    return {
        str(row["model_cell_id"]): float(row["heldout_rollout_macro_nll_mean"])
        for row in synthesis["cell_summaries"]
    }


def _contrast_map(synthesis: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = [
        *synthesis["three_axes"]["primary_contrasts"],
        *synthesis.get("direct_architecture_contrasts", []),
        *synthesis.get("supporting_contrasts", []),
    ]
    return {str(row["contrast_id"]): row for row in rows}


def _history_predicate(cells: Mapping[str, float], family: str) -> dict[str, Any]:
    values = [cells[f"{family}-h{horizon}-large"] for horizon in ("0p0", "0p4", "1p0")]
    recent_gain = values[0] - values[1]
    later_gain = values[1] - values[2]
    total_gain = values[0] - values[2]
    retained_fraction = recent_gain / total_gain if total_gain > 0.0 else math.nan
    predicate = bool(
        recent_gain > 0.0
        and total_gain >= 0.0
        and (later_gain <= 0.0 or retained_fraction >= 0.75)
    )
    return {
        "nll_h0p0": values[0],
        "nll_h0p4": values[1],
        "nll_h1p0": values[2],
        "recent_gain_0p0_minus_0p4": recent_gain,
        "later_gain_0p4_minus_1p0": later_gain,
        "total_gain_0p0_minus_1p0": total_gain,
        "recent_gain_fraction": retained_fraction,
        "recent_history_captures_most_predicate": predicate,
    }


def build_claim_and_deployment_decisions(
    old_synthesis_path: Path,
    corrected_synthesis_path: Path,
    old_freeze_path: Path,
    corrected_freeze_path: Path,
    cache_audit: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    old = _load(old_synthesis_path)
    corrected = _load(corrected_synthesis_path)
    old_freeze = _load(old_freeze_path)
    corrected_freeze = _load(corrected_freeze_path)
    if (
        not _hash_valid(old, "synthesis_sha256")
        or not _hash_valid(corrected, "synthesis_sha256")
        or not _hash_valid(old_freeze, "freeze_sha256")
        or not _hash_valid(corrected_freeze, "freeze_sha256")
        or corrected.get("schema_version")
        != "capacity_history_thesis_core_offline_synthesis_v4_masked"
        or corrected_freeze.get("schema_version")
        != "capacity_history_thesis_core_selection_freeze_v4_masked"
    ):
        raise ValueError("Old/new synthesis or selection-freeze identity is invalid")
    old_cells = _cell_means(old)
    new_cells = _cell_means(corrected)
    new_cell_records = {
        str(row["model_cell_id"]): row for row in corrected["cell_summaries"]
    }
    if set(old_cells) != set(new_cells) or len(new_cells) != 9:
        raise ValueError("Old/new CIA model-cell membership differs")

    capacity_cells = {
        tier: f"transformer-h1p0-{tier}" for tier in ("small", "medium", "large")
    }
    old_capacity = {tier: old_cells[cell] for tier, cell in capacity_cells.items()}
    new_capacity = {tier: new_cells[cell] for tier, cell in capacity_cells.items()}
    old_best = min(old_capacity, key=lambda tier: (old_capacity[tier], tier))
    new_best = min(new_capacity, key=lambda tier: (new_capacity[tier], tier))
    capacity_seed_best = {}
    for seed in (11, 23, 37):
        values = {
            tier: float(new_cell_records[cell]["per_seed"][str(seed)])
            for tier, cell in capacity_cells.items()
        }
        capacity_seed_best[str(seed)] = min(values, key=lambda tier: (values[tier], tier))
    if new_best == old_best == "medium" and set(capacity_seed_best.values()) == {"medium"}:
        capacity_status = "same"
    elif new_best == "medium":
        capacity_status = "weakened"
    elif len(set(capacity_seed_best.values())) == 1:
        capacity_status = "reversed"
    else:
        capacity_status = "not_identifiable"

    history_details = {}
    history_predicates = []
    for family in ("mlp", "transformer"):
        old_history = _history_predicate(old_cells, family)
        new_history = _history_predicate(new_cells, family)
        history_details[family] = {"old": old_history, "corrected": new_history}
        history_predicates.append(new_history["recent_history_captures_most_predicate"])
    if all(history_predicates):
        history_status = "same"
    elif all(history_details[family]["corrected"]["total_gain_0p0_minus_1p0"] > 0.0 for family in ("mlp", "transformer")):
        history_status = "weakened"
    elif all(history_details[family]["corrected"]["total_gain_0p0_minus_1p0"] <= 0.0 for family in ("mlp", "transformer")):
        history_status = "reversed"
    else:
        history_status = "not_identifiable"

    horizons = ("h0p0", "h0p4", "h1p0")
    old_arch = {
        horizon: old_cells[f"mlp-{horizon}-large"]
        - old_cells[f"transformer-{horizon}-large"]
        for horizon in horizons
    }
    new_arch = {
        horizon: new_cells[f"mlp-{horizon}-large"]
        - new_cells[f"transformer-{horizon}-large"]
        for horizon in horizons
    }
    positive_arch = sum(value > 0.0 for value in new_arch.values())
    architecture_status = (
        "same" if positive_arch == 3 else "weakened" if positive_arch == 2
        else "reversed" if positive_arch == 0 else "not_identifiable"
    )

    old_contrasts = _contrast_map(old)
    new_contrasts = _contrast_map(corrected)
    new_crossed = {
        str(row["contrast_id"]): row
        for row in corrected.get("crossed_seed_init_sensitivity", [])
    }
    attention_id = "H3_attention_history_gain_difference_in_differences"
    old_attention = old_contrasts[attention_id]
    new_attention = new_contrasts[attention_id]
    new_low, new_high = [float(value) for value in new_attention["cluster_interval_95"]]
    crossed_low, crossed_high = [
        float(value)
        for value in new_crossed[attention_id]["crossed_bootstrap_interval_95"]
    ]
    if new_low > 0.0 and crossed_low > 0.0:
        attention_status = "reversed"
    elif new_high < 0.0 and crossed_high < 0.0:
        attention_status = "weakened"
    else:
        attention_status = "not_identifiable"

    claim_rows = [
        {
            "claim_id": "capacity_medium_observed_optimum",
            "old": {"means": old_capacity, "best": old_best},
            "corrected": {
                "means": new_capacity,
                "best": new_best,
                "best_by_training_seed": capacity_seed_best,
            },
            "conclusion_status": capacity_status,
            "evidence_role": "retrospective_descriptive_observed_ranking",
        },
        {
            "claim_id": "recent_history_captures_most_gain",
            "old_and_corrected": history_details,
            "conclusion_status": history_status,
            "evidence_role": "retrospective_descriptive_observed_gain",
        },
        {
            "claim_id": "transformer_direct_offset_across_horizons",
            "old_mlp_minus_transformer": old_arch,
            "corrected_mlp_minus_transformer": new_arch,
            "conclusion_status": architecture_status,
            "evidence_role": "retrospective_descriptive_observed_offset",
        },
        {
            "claim_id": "no_attention_specific_history_gain",
            "old_effect": old_attention,
            "corrected_effect": new_attention,
            "crossed_seed_init_sensitivity": new_crossed[attention_id],
            "conclusion_status": attention_status,
            "evidence_role": "retrospective_descriptive_interaction_unresolved_at_n5",
            "interpretive_rule": (
                "A confidence interval spanning zero is not evidence of no effect; "
                "it is classified as not identifiable at the available resolution."
            ),
        },
    ]
    status_order = {"same": 0, "weakened": 1, "reversed": 2, "not_identifiable": 3}
    overall_offline = max(
        (row["conclusion_status"] for row in claim_rows),
        key=lambda value: status_order[value],
    )

    old_runs = {row["run_id"]: row for row in old_freeze["runs"]}
    new_runs = {row["run_id"]: row for row in corrected_freeze["runs"]}
    role_identities = {}
    for role in ("B1", "P_star"):
        old_role = old_freeze[role]
        new_role = corrected_freeze[role]
        old_run = old_runs[old_role["representative_run_id"]]
        new_run = new_runs[new_role["representative_run_id"]]
        same_representative = (
            old_role["representative_run_id"] == new_role["representative_run_id"]
        )
        role_identities[role] = {
            "old": old_role,
            "corrected": new_role,
            "same_configuration": (
                old_role["model_cell_id"] == new_role["model_cell_id"]
            ),
            "same_representative_run": same_representative,
            "same_model_weights": (
                same_representative
                and old_run.get("model_identity") == new_run.get("model_identity")
            ),
            "same_calibration": (
                same_representative
                and old_run.get("calibration_sha256")
                == new_run.get("calibration_sha256")
            ),
        }
    same_dataset = old_freeze.get("dataset_complete_sha256") == corrected_freeze.get(
        "dataset_complete_sha256"
    )
    cache_tensors_equal = bool(
        cache_audit.get("status") == "pass"
        and all(
            all(field["exactly_equal"] for field in split["arrays"].values())
            for split in cache_audit["splits"].values()
        )
    )
    offline_role_identity_exact = all(
        value
        for identity in role_identities.values()
        for key, value in identity.items()
        if key.startswith("same_")
    )
    offline_bundle_exact = bool(
        offline_role_identity_exact and same_dataset and cache_tensors_equal
    )
    # Historical CARLA receipts do not carry a complete canonical B1/P* bundle
    # signature, so offline identity alone cannot license reuse.
    actual_carla_predictor_bundle_identity_verified = False
    decision = (
        "rerun_required" if not offline_bundle_exact else "not_verifiable"
    )
    deployment = {
        "schema_version": "capacity_history_future_mask_v4_carla_deployment_decision",
        "status": "pass",
        "decision": decision,
        "carla_execution_authorized": False,
        "corrected_offline_to_closed_loop_claim_allowed": False,
        "historical_v3_carla_claim_allowed": True,
        "old_p_star": old_freeze["P_star"],
        "corrected_p_star": corrected_freeze["P_star"],
        "old_B1": old_freeze["B1"],
        "corrected_B1": corrected_freeze["B1"],
        "identity": {
            "roles": role_identities,
            "offline_B1_and_P_star_bundle_exact": offline_bundle_exact,
            "same_dataset": same_dataset,
            "feature_cache_tensors_exactly_equal": cache_tensors_equal,
            "actual_carla_predictor_bundle_identity_verified": (
                actual_carla_predictor_bundle_identity_verified
            ),
        },
        "required_next_action": (
            "Rerun corrected B1/P* CARLA before claiming corrected V4 "
            "offline-to-closed-loop transfer."
        ),
        "claim_boundary": (
            "A rerun-required decision does not invalidate historical physical rollouts; "
            "it limits them to the historical V3 deployed stack."
        ),
        "old_selection_freeze_sha256": old_freeze["freeze_sha256"],
        "corrected_selection_freeze_sha256": corrected_freeze["freeze_sha256"],
        "old_synthesis_sha256": old["synthesis_sha256"],
        "corrected_synthesis_sha256": corrected["synthesis_sha256"],
    }
    deployment["decision_sha256"] = sha256_payload(deployment)
    consistency = {
        "schema_version": "capacity_history_future_mask_v4_claim_consistency_audit",
        "status": "pass",
        "old_metric_contract": "diagnostic_invalid_future_mask_v3",
        "corrected_metric_contract": "future_valid_mask_fail_closed_v4",
        "claims": claim_rows,
        "overall_offline_conclusion_status": overall_offline,
        "corrected_offline_to_closed_loop_status": (
            "not_identifiable_without_carla_rerun"
        ),
        "statistical_boundary": (
            "Five held-out init groups provide retrospective descriptive evidence; "
            "exact two-sided sign-flip tests cannot attain p<0.05 at n=5."
        ),
        "deployment_decision_sha256": deployment["decision_sha256"],
    }
    consistency["audit_sha256"] = sha256_payload(consistency)
    return consistency, deployment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-cache", required=True, type=Path)
    parser.add_argument("--corrected-cache", required=True, type=Path)
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--old-selection-root", required=True, type=Path)
    parser.add_argument("--corrected-old-selection-root", required=True, type=Path)
    parser.add_argument("--corrected-heldout-root", type=Path)
    parser.add_argument("--corrected-selection-root", type=Path)
    parser.add_argument("--full-horizon-root", type=Path)
    parser.add_argument("--offline-synthesis", type=Path)
    parser.add_argument("--old-offline-synthesis", type=Path)
    parser.add_argument("--selection-freeze", type=Path)
    parser.add_argument("--old-selection-freeze", type=Path)
    parser.add_argument("--pipeline-receipt", type=Path)
    parser.add_argument("--pipeline-stage-receipt", type=Path)
    parser.add_argument("--extension-protocol", type=Path)
    parser.add_argument("--training-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pipeline_receipt = None
    pipeline_stage_receipt = None
    extension_protocol = None
    if args.pipeline_receipt:
        pipeline_receipt = _load(args.pipeline_receipt)
        if (
            not _hash_valid(pipeline_receipt, "receipt_sha256")
            or pipeline_receipt.get("schema_version")
            != "capacity_history_future_mask_v4_running_pipeline_receipt"
            or pipeline_receipt.get("status") != "pass"
        ):
            raise ValueError("V4 pipeline launch receipt is invalid")
        expected_sources = pipeline_receipt.get("training_source_sha256", {})
        for name, recorded_hash in expected_sources.items():
            if sha256_file(Path(__file__).with_name(name)) != recorded_hash:
                raise ValueError(f"Training source changed after launch receipt: {name}")
        if (
            not args.manifest
            or pipeline_receipt.get("manifest", {}).get("sha256")
            != sha256_file(args.manifest)
            or pipeline_receipt.get("dataset_complete", {}).get("sha256")
            != sha256_file(args.dataset_dir / "THESIS_CORE_DATASET_COMPLETE.json")
            or pipeline_receipt.get("cache_complete", {}).get("sha256")
            != sha256_file(args.corrected_cache / "CACHE_COMPLETE.json")
        ):
            raise ValueError("Pipeline receipt immutable-input identity mismatch")
        if pipeline_receipt.get("protocol_variant") == "uniform_v4e_120_epoch_amendment":
            if not args.extension_protocol:
                raise ValueError("V4e pipeline receipt requires the extension protocol")
            extension_protocol = _load(args.extension_protocol)
            if (
                not _hash_valid(extension_protocol, "protocol_sha256")
                or extension_protocol.get("status") != "pass"
                or extension_protocol.get("all_27_runs_extended_uniformly") is not True
                or extension_protocol.get("single_run_or_cell_selective_extension")
                is not False
                or extension_protocol.get("heldout_accessed_before_amendment") is not False
                or pipeline_receipt.get("extension_protocol", {}).get("sha256")
                != sha256_file(args.extension_protocol)
                or pipeline_receipt.get("extension_protocol", {}).get(
                    "protocol_sha256"
                )
                != extension_protocol.get("protocol_sha256")
            ):
                raise ValueError("Uniform V4e extension protocol is invalid")
        elif args.extension_protocol:
            raise ValueError("Extension protocol supplied to a non-extension pipeline")
    if args.pipeline_stage_receipt:
        pipeline_stage_receipt = _load(args.pipeline_stage_receipt)
        if (
            not _hash_valid(pipeline_stage_receipt, "stage_receipt_sha256")
            or pipeline_stage_receipt.get("schema_version")
            != "capacity_history_future_mask_v4_pipeline_stage_complete"
            or pipeline_stage_receipt.get("status") != "pass"
            or int(pipeline_stage_receipt.get("corrected_runs", -1)) != 27
            or int(pipeline_stage_receipt.get("calibrations", -1)) != 27
            or int(pipeline_stage_receipt.get("heldout_reports", -1)) != 27
            or pipeline_receipt is None
            or pipeline_stage_receipt.get("pipeline_receipt_sha256")
            != pipeline_receipt.get("receipt_sha256")
        ):
            raise ValueError("V4 pipeline stage-complete receipt is invalid")
    cache = audit_cache(args.old_cache, args.corrected_cache)
    dataset_contract = audit_dataset_mask_strata(args.dataset_dir, args.corrected_cache)
    historical = audit_historical_checkpoints(
        args.old_selection_root, args.corrected_old_selection_root
    )
    source_sha256 = sha256_file(Path(__file__))
    evaluator_sha256 = sha256_file(
        Path(__file__).with_name("evaluate_multipath_model_on_dataset.py")
    )
    cache["analysis_source_sha256"] = source_sha256
    cache["evaluation_source_sha256"] = evaluator_sha256
    cache["dataset_mask_strata"] = dataset_contract
    historical["analysis_source_sha256"] = source_sha256
    historical["evaluation_source_sha256"] = evaluator_sha256
    cache["audit_sha256"] = sha256_payload(cache)
    historical["audit_sha256"] = sha256_payload(historical)
    atomic_json(args.output_dir / "CACHE_AND_MASK_AUDIT.json", cache)
    atomic_json(args.output_dir / "HISTORICAL_CHECKPOINT_IMPACT_AUDIT.json", historical)
    _write_rows(args.output_dir / "historical_checkpoint_impact_rows.csv", historical["rows"])
    result = {
        "status": "pass",
        "cache_and_mask_audit": str(args.output_dir / "CACHE_AND_MASK_AUDIT.json"),
        "historical_checkpoint_impact_audit": str(
            args.output_dir / "HISTORICAL_CHECKPOINT_IMPACT_AUDIT.json"
        ),
    }
    if args.training_root or args.manifest:
        if not args.training_root or not args.manifest:
            raise ValueError("Training-curve audit requires both training root and manifest")
        training = audit_training_curves(args.training_root, args.manifest)
        training["analysis_source_sha256"] = source_sha256
        training["evaluation_source_sha256"] = evaluator_sha256
        training["audit_sha256"] = sha256_payload(training)
        atomic_json(args.output_dir / "TRAINING_CURVE_AUDIT.json", training)
        _write_rows(args.output_dir / "training_curve_rows.csv", training["rows"])
        result["training_curve_audit"] = str(
            args.output_dir / "TRAINING_CURVE_AUDIT.json"
        )
        if training["status"] != "pass":
            raise ValueError(
                "Corrected training retains material boundary-underfit risk: "
                f"{training['unresolved_boundary_underfit_runs']}"
            )
    if args.corrected_heldout_root or args.full_horizon_root or args.offline_synthesis:
        if (
            not args.corrected_heldout_root
            or not args.full_horizon_root
            or not args.offline_synthesis
            or not args.training_root
            or not args.manifest
            or not args.selection_freeze
        ):
            raise ValueError(
                "Full-horizon sensitivity requires held-out/full-horizon/synthesis, "
                "training, manifest, and selection-freeze inputs"
            )
        sensitivity = full_horizon_sensitivity(
            args.corrected_heldout_root,
            args.full_horizon_root,
            args.offline_synthesis,
            args.training_root,
            args.manifest,
            args.selection_freeze,
            dataset_contract,
        )
        sensitivity["analysis_source_sha256"] = source_sha256
        sensitivity["evaluation_source_sha256"] = evaluator_sha256
        sensitivity["sensitivity_sha256"] = sha256_payload(sensitivity)
        atomic_json(args.output_dir / "FULL_HORIZON_SENSITIVITY.json", sensitivity)
        _write_rows(args.output_dir / "full_horizon_rows.csv", sensitivity["rows"])
        result["full_horizon_sensitivity"] = str(
            args.output_dir / "FULL_HORIZON_SENSITIVITY.json"
        )
    if args.corrected_selection_root or args.corrected_heldout_root:
        if (
            not args.corrected_selection_root
            or not args.corrected_heldout_root
            or not args.training_root
            or not args.manifest
            or not args.selection_freeze
        ):
            raise ValueError(
                "Formal report audit requires selection/held-out, training, manifest, "
                "and selection-freeze inputs"
            )
        reports = audit_formal_report_contracts(
            args.corrected_selection_root,
            args.corrected_heldout_root,
            dataset_contract,
            args.training_root,
            args.manifest,
            args.selection_freeze,
        )
        reports["analysis_source_sha256"] = source_sha256
        if pipeline_receipt is not None:
            expected_cache = pipeline_receipt["cache_complete"]["sha256"]
            expected_dataset = pipeline_receipt["dataset_complete"]["sha256"]
            if any(
                row["cache_complete_sha256"] != expected_cache
                or row["dataset_complete_sha256"] != expected_dataset
                for row in reports["rows"]
            ):
                raise ValueError(
                    "Training/evaluation artifacts are not bound to pipeline receipt inputs"
                )
            freeze_for_receipt = _load(args.selection_freeze)
            if (
                freeze_for_receipt.get("cache_complete_sha256") != expected_cache
                or freeze_for_receipt.get("dataset_complete_sha256") != expected_dataset
            ):
                raise ValueError("Selection freeze is not bound to pipeline receipt inputs")
            reports["pipeline_receipt_sha256"] = pipeline_receipt["receipt_sha256"]
        reports["audit_sha256"] = sha256_payload(reports)
        atomic_json(args.output_dir / "FORMAL_REPORT_CONTRACT_AUDIT.json", reports)
        _write_rows(args.output_dir / "formal_report_contract_rows.csv", reports["rows"])
        result["formal_report_contract_audit"] = str(
            args.output_dir / "FORMAL_REPORT_CONTRACT_AUDIT.json"
        )
    decision_inputs = (
        args.old_offline_synthesis,
        args.offline_synthesis,
        args.old_selection_freeze,
        args.selection_freeze,
    )
    if any(decision_inputs):
        if not all(decision_inputs):
            raise ValueError(
                "Claim/deployment decision requires old/new synthesis and old/new freeze"
            )
        consistency, deployment = build_claim_and_deployment_decisions(
            args.old_offline_synthesis,
            args.offline_synthesis,
            args.old_selection_freeze,
            args.selection_freeze,
            cache,
        )
        gate_artifacts = {
            "cache_and_mask_audit_sha256": cache["audit_sha256"],
            "historical_impact_audit_sha256": historical["audit_sha256"],
            "training_curve_audit_sha256": training["audit_sha256"],
            "full_horizon_sensitivity_sha256": sensitivity["sensitivity_sha256"],
            "formal_report_contract_audit_sha256": reports["audit_sha256"],
            "pipeline_receipt_sha256": (
                pipeline_receipt["receipt_sha256"] if pipeline_receipt else None
            ),
            "pipeline_stage_receipt_sha256": (
                pipeline_stage_receipt["stage_receipt_sha256"]
                if pipeline_stage_receipt
                else None
            ),
            "selection_freeze_sha256": _load(args.selection_freeze)["freeze_sha256"],
            "corrected_synthesis_sha256": _load(args.offline_synthesis)[
                "synthesis_sha256"
            ],
            "extension_protocol_sha256": (
                extension_protocol["protocol_sha256"]
                if extension_protocol is not None
                else None
            ),
        }
        if pipeline_receipt is None or pipeline_stage_receipt is None:
            raise ValueError(
                "Final offline release requires running and stage-complete pipeline receipts"
            )
        deployment.pop("decision_sha256", None)
        deployment["gate_artifacts"] = gate_artifacts
        deployment["decision_sha256"] = sha256_payload(deployment)
        consistency.pop("audit_sha256", None)
        consistency["deployment_decision_sha256"] = deployment["decision_sha256"]
        consistency["gate_artifacts"] = gate_artifacts
        consistency["audit_sha256"] = sha256_payload(consistency)
        atomic_json(args.output_dir / "CLAIM_CONSISTENCY_AUDIT.json", consistency)
        atomic_json(args.output_dir / "CARLA_DEPLOYMENT_DECISION.json", deployment)
        release = {
            "schema_version": "capacity_history_future_mask_v4_offline_evidence_release",
            "status": "pass",
            "corrected_runs": 27,
            "future_validity_contract": "future_valid_mask_fail_closed_v4",
            "gate_artifacts": gate_artifacts,
            "claim_consistency_audit_sha256": consistency["audit_sha256"],
            "carla_deployment_decision_sha256": deployment["decision_sha256"],
            "carla_was_launched": False,
        }
        release["release_sha256"] = sha256_payload(release)
        atomic_json(args.output_dir / "OFFLINE_EVIDENCE_RELEASE.json", release)
        result["claim_consistency_audit"] = str(
            args.output_dir / "CLAIM_CONSISTENCY_AUDIT.json"
        )
        result["carla_deployment_decision"] = str(
            args.output_dir / "CARLA_DEPLOYMENT_DECISION.json"
        )
        result["offline_evidence_release"] = str(
            args.output_dir / "OFFLINE_EVIDENCE_RELEASE.json"
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
