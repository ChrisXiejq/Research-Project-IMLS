#!/usr/bin/env python3
"""Fast selection calibration and gated retrospective held-out evaluation."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import numpy as np
import tensorflow as tf

from build_thesis_core_feature_cache_v3 import validate_cache
from capacity_study_v3_protocol import (
    THESIS_HELDOUT_GROUPS,
    THESIS_SELECTION_GROUPS,
    atomic_json,
    sha256_payload,
)
from evaluate_multipath_model_on_dataset import (
    artifact_hash,
    decode_raw_predictions,
    evaluate_decoded,
    fit_validation_calibration,
)
from prediction_dataset_utils import read_jsonl
from prepare_thesis_core_v3_dataset import load_thesis_normalization, sample_key
from thesis_core_v3_execute import completion_valid
from thesis_core_v3_runs import validate_thesis_core_manifest
from train_thesis_core_cached_v3 import build_cached_model, cached_inputs


CALIBRATION_SCHEMA = "multipath_posthoc_calibration_v4_masked"
SELECTION_EVALUATION_SCHEMA = "capacity_history_thesis_core_selection_evaluation_v4_masked"
HELDOUT_EVALUATION_SCHEMA = "capacity_history_thesis_core_heldout_evaluation_v4_masked"
FULL_HORIZON_EVALUATION_SCHEMA = (
    "capacity_history_thesis_core_full_horizon_sensitivity_v4_masked"
)
SELECTION_FREEZE_SCHEMA = "capacity_history_thesis_core_selection_freeze_v4_masked"
FUTURE_VALIDITY_CONTRACT = "future_valid_mask_fail_closed_v4"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as handle:
        return {name: np.asarray(handle[name]) for name in handle.files}


def _validated_freeze(path: Path, run_id: str) -> dict[str, Any]:
    payload = _load(path)
    value = dict(payload)
    recorded = value.pop("freeze_sha256", None)
    if (
        recorded != sha256_payload(value)
        or payload.get("schema_version") != SELECTION_FREEZE_SCHEMA
        or payload.get("status") != "pass"
        or payload.get("future_validity_contract") != FUTURE_VALIDITY_CONTRACT
    ):
        raise ValueError("Held-out access blocked by invalid selection freeze")
    if payload.get("heldout_access_authorized") is not True:
        raise ValueError("Selection freeze does not authorize held-out access")
    required = {
        run
        for cell in payload.get("cells", [])
        for run in cell.get("retained_run_ids", [])
    }
    if run_id not in required:
        raise ValueError(f"Run is absent from selection freeze: {run_id}")
    return payload


def _spec_and_completion(
    manifest_path: Path, training_root: Path, run_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load(manifest_path)
    validate_thesis_core_manifest(manifest)
    matches = [row for row in manifest["runs"] if row["run_id"] == run_id]
    if len(matches) != 1:
        raise ValueError(f"Run id does not resolve exactly once: {run_id}")
    spec = matches[0]
    completion_path = training_root / run_id / "TRAINING_COMPLETE.json"
    if not completion_valid(completion_path, spec):
        raise ValueError(f"Training completion failed integrity gate: {run_id}")
    return spec, _load(completion_path)


def _validate_frozen_training_binding(
    freeze: Mapping[str, Any],
    run_id: str,
    spec: Mapping[str, Any],
    completion: Mapping[str, Any],
) -> Mapping[str, Any]:
    matches = [row for row in freeze.get("runs", []) if row.get("run_id") == run_id]
    if len(matches) != 1:
        raise ValueError(f"Frozen training run does not resolve exactly once: {run_id}")
    frozen = matches[0]
    model_identity = completion["best_model"].get("sha256_tree") or completion[
        "best_model"
    ].get("sha256")
    if (
        frozen.get("model_cell_id") != spec.get("model_cell_id")
        or int(frozen.get("seed", -1)) != int(spec.get("seed", -2))
        or frozen.get("training_completion_sha256")
        != completion.get("completion_sha256")
        or frozen.get("model_identity") != model_identity
        or frozen.get("cached_weights_sha256")
        != completion.get("cached_weights", {}).get("sha256")
        or freeze.get("cache_complete_sha256")
        != completion.get("cache_complete_sha256")
        or freeze.get("dataset_complete_sha256")
        != completion.get("dataset_complete_sha256")
    ):
        raise ValueError(f"Selection freeze/training identity mismatch: {run_id}")
    return frozen


def _predict_cached(
    spec: Mapping[str, Any],
    arrays: Mapping[str, np.ndarray],
    base_model: Path,
    anchors_path: Path,
    normalization_path: Path,
    weights_path: Path,
    batch_size: int,
) -> np.ndarray:
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(int(spec["seed"]))
    tf.config.experimental.enable_op_determinism()
    anchors = np.load(anchors_path)
    normalization = load_thesis_normalization(normalization_path)
    base = tf.keras.models.load_model(base_model, compile=False)
    base.trainable = False
    model, _ = build_cached_model(spec, base, arrays, anchors, normalization)
    model.load_weights(weights_path)
    return np.asarray(
        model.predict(cached_inputs(spec, arrays), batch_size=batch_size, verbose=0)
    )


def _aligned_rows(jsonl_path: Path, arrays: Mapping[str, np.ndarray]) -> list[dict[str, Any]]:
    rows = list(read_jsonl(str(jsonl_path)))
    expected = [sample_key(row) for row in rows]
    actual = [str(value) for value in arrays["sample_ids"].tolist()]
    if expected != actual:
        raise ValueError("Cached sample order or membership differs from sealed JSONL")
    return rows


def calibrate(args: argparse.Namespace) -> dict[str, Any]:
    spec, completion = _spec_and_completion(
        args.manifest, args.training_root, args.run_id
    )
    validate_cache(args.cache_dir, args.dataset_dir, args.base_model)
    arrays = _load_npz(args.cache_dir / "selection.npz")
    rows = _aligned_rows(args.dataset_dir / "selection.jsonl", arrays)
    if {int(row["ego_init_id"]) for row in rows} != set(THESIS_SELECTION_GROUPS):
        raise ValueError("Calibration sample groups are not exactly 36--40")
    predictions = _predict_cached(
        spec,
        arrays,
        args.base_model,
        args.anchors,
        args.dataset_dir / "interaction_normalization_fit.json",
        args.training_root / args.run_id / "cached_best.weights.h5",
        args.batch_size,
    )
    anchors = np.load(args.anchors)
    labels = arrays["labels"]
    grid = SimpleNamespace(
        temperature_min=0.25,
        temperature_max=4.0,
        temperature_count=25,
        covariance_scale_min=1.0e-4,
        covariance_scale_max=4.0,
        covariance_scale_count=49,
    )
    calibration = fit_validation_calibration(
        predictions, anchors, labels, rows, 10, grid
    )
    calibration["calibration_schema_version"] = CALIBRATION_SCHEMA
    calibration.update(
        {
            "fit_split": "validation",
            "fit_role": "groups_36_40_selection",
            "fit_groups": list(THESIS_SELECTION_GROUPS),
            "calibration_fit_uses_test": False,
            "run_id": args.run_id,
            "model_cell_id": spec["model_cell_id"],
            "seed": int(spec["seed"]),
            "model_artifact": completion["best_model"],
            "cached_weights_artifact": completion["cached_weights"],
            "cache_complete_sha256": completion["cache_complete_sha256"],
            "dataset_complete_sha256": completion["dataset_complete_sha256"],
            "selection_jsonl": artifact_hash(args.dataset_dir / "selection.jsonl"),
            "anchors_artifact": artifact_hash(args.anchors),
            "samples": len(rows),
            "sample_membership_sha256": sha256_payload(
                [sample_key(row) for row in rows]
            ),
            "horizon": 10,
        }
    )
    uncalibrated = evaluate_decoded(
        decode_raw_predictions(predictions, anchors),
        labels,
        rows,
        10,
        temperature=1.0,
        covariance_scale=1.0,
    )
    parameters = calibration["parameters"]
    calibrated = evaluate_decoded(
        decode_raw_predictions(
            predictions,
            anchors,
            temperature=float(parameters["temperature"]),
            covariance_scale=float(parameters["covariance_scale"]),
        ),
        labels,
        rows,
        10,
        temperature=float(parameters["temperature"]),
        covariance_scale=float(parameters["covariance_scale"]),
    )
    calibration["calibration_sha256"] = sha256_payload(calibration)
    report = {
        "schema_version": SELECTION_EVALUATION_SCHEMA,
        "status": "pass",
        "split_role": "groups_36_40_selection",
        "run_id": args.run_id,
        "model_cell_id": spec["model_cell_id"],
        "seed": int(spec["seed"]),
        "samples": len(rows),
        "independent_init_groups": len(THESIS_SELECTION_GROUPS),
        "sample_membership_sha256": sha256_payload([sample_key(row) for row in rows]),
        "training_completion_sha256": completion["completion_sha256"],
        "cache_complete_sha256": completion["cache_complete_sha256"],
        "dataset_complete_sha256": completion["dataset_complete_sha256"],
        "model_artifact": completion["best_model"],
        "cached_weights_artifact": completion["cached_weights"],
        "future_validity_contract": FUTURE_VALIDITY_CONTRACT,
        "uncalibrated": uncalibrated,
        "calibrated": calibrated,
        "calibration_sha256": calibration["calibration_sha256"],
    }
    report["evaluation_sha256"] = sha256_payload(report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output_dir / "calibration.json", calibration)
    atomic_json(args.output_dir / "selection_metrics.json", report)
    return report


def evaluate_heldout(args: argparse.Namespace) -> dict[str, Any]:
    freeze = _validated_freeze(args.selection_freeze, args.run_id)
    spec, completion = _spec_and_completion(
        args.manifest, args.training_root, args.run_id
    )
    validate_cache(args.cache_dir, args.dataset_dir, args.base_model)
    calibration_path = args.calibration_root / args.run_id / "calibration.json"
    calibration = _load(calibration_path)
    calibration_value = dict(calibration)
    recorded = calibration_value.pop("calibration_sha256", None)
    if recorded != sha256_payload(calibration_value):
        raise ValueError("Calibration hash mismatch")
    if (
        calibration.get("calibration_schema_version") != CALIBRATION_SCHEMA
        or calibration.get("future_validity", {}).get("contract")
        != FUTURE_VALIDITY_CONTRACT
        or calibration.get("run_id") != args.run_id
        or calibration.get("fit_role") != "groups_36_40_selection"
        or calibration.get("calibration_fit_uses_test") is not False
        or calibration.get("model_artifact") != completion["best_model"]
        or calibration.get("cached_weights_artifact") != completion["cached_weights"]
    ):
        raise ValueError("Calibration is not bound to this frozen training run")
    frozen_record = _validate_frozen_training_binding(
        freeze, args.run_id, spec, completion
    )
    if (
        frozen_record["calibration_sha256"] != recorded
    ):
        raise ValueError("Selection freeze/training/calibration provenance binding mismatch")

    # Held-out tensors and rows are intentionally opened only after every gate above.
    arrays = _load_npz(args.cache_dir / "heldout.npz")
    rows = _aligned_rows(args.dataset_dir / "heldout.jsonl", arrays)
    if {int(row["ego_init_id"]) for row in rows} != set(THESIS_HELDOUT_GROUPS):
        raise ValueError("Held-out sample groups are not exactly 41--45")
    predictions = _predict_cached(
        spec,
        arrays,
        args.base_model,
        args.anchors,
        args.dataset_dir / "interaction_normalization_fit.json",
        args.training_root / args.run_id / "cached_best.weights.h5",
        args.batch_size,
    )
    anchors = np.load(args.anchors)
    labels = arrays["labels"]
    uncalibrated = evaluate_decoded(
        decode_raw_predictions(predictions, anchors), labels, rows, 10,
        temperature=1.0, covariance_scale=1.0,
    )
    parameters = calibration["parameters"]
    calibrated = evaluate_decoded(
        decode_raw_predictions(
            predictions, anchors,
            temperature=float(parameters["temperature"]),
            covariance_scale=float(parameters["covariance_scale"]),
        ),
        labels, rows, 10,
        temperature=float(parameters["temperature"]),
        covariance_scale=float(parameters["covariance_scale"]),
    )
    report = {
        "schema_version": HELDOUT_EVALUATION_SCHEMA,
        "status": "pass",
        "evidence_status": "retrospective_held_out",
        "split_role": "groups_41_45_retrospective_heldout",
        "heldout_access_was_gated": True,
        "selection_freeze_sha256": freeze["freeze_sha256"],
        "training_completion_sha256": completion["completion_sha256"],
        "cache_complete_sha256": completion["cache_complete_sha256"],
        "dataset_complete_sha256": completion["dataset_complete_sha256"],
        "future_validity_contract": FUTURE_VALIDITY_CONTRACT,
        "run_id": args.run_id,
        "model_cell_id": spec["model_cell_id"],
        "family": spec["family"],
        "capacity_tier": spec["capacity_tier"],
        "history_horizon_s": spec["history_horizon_s"],
        "seed": int(spec["seed"]),
        "samples": len(rows),
        "independent_init_groups": len(THESIS_HELDOUT_GROUPS),
        "sample_membership_sha256": sha256_payload([sample_key(row) for row in rows]),
        "model_artifact": completion["best_model"],
        "cached_weights_artifact": completion["cached_weights"],
        "calibration_sha256": recorded,
        "uncalibrated": uncalibrated,
        "calibrated": calibrated,
    }
    report["evaluation_sha256"] = sha256_payload(report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output_dir / "heldout_metrics.json", report)
    return report


def evaluate_full_horizon_sensitivity(args: argparse.Namespace) -> dict[str, Any]:
    freeze = _validated_freeze(args.selection_freeze, args.run_id)
    spec, completion = _spec_and_completion(args.manifest, args.training_root, args.run_id)
    validate_cache(args.cache_dir, args.dataset_dir, args.base_model)
    _validate_frozen_training_binding(freeze, args.run_id, spec, completion)
    anchors = np.load(args.anchors)

    selection_arrays = _load_npz(args.cache_dir / "selection.npz")
    selection_rows = _aligned_rows(
        args.dataset_dir / "selection.jsonl", selection_arrays
    )
    if {int(row["ego_init_id"]) for row in selection_rows} != set(
        THESIS_SELECTION_GROUPS
    ):
        raise ValueError("Full-horizon calibration groups are not exactly 36--40")
    selection_mask = np.asarray(selection_arrays["labels"][..., 2], dtype=bool)
    selection_indices = np.flatnonzero(np.all(selection_mask, axis=1))
    if len(selection_indices) != 330:
        raise ValueError(
            f"Expected 330 full-horizon selection windows, found {len(selection_indices)}"
        )
    selection_subset = {
        key: np.asarray(value)[selection_indices] for key, value in selection_arrays.items()
    }
    selection_rows_subset = [selection_rows[index] for index in selection_indices]
    selection_predictions = _predict_cached(
        spec,
        selection_subset,
        args.base_model,
        args.anchors,
        args.dataset_dir / "interaction_normalization_fit.json",
        args.training_root / args.run_id / "cached_best.weights.h5",
        args.batch_size,
    )
    grid = SimpleNamespace(
        temperature_min=0.25,
        temperature_max=4.0,
        temperature_count=25,
        covariance_scale_min=1.0e-4,
        covariance_scale_max=4.0,
        covariance_scale_count=49,
    )
    calibration = fit_validation_calibration(
        selection_predictions,
        anchors,
        selection_subset["labels"],
        selection_rows_subset,
        10,
        grid,
    )
    calibration.update(
        {
            "calibration_schema_version": (
                "multipath_posthoc_calibration_v4_full_horizon_sensitivity"
            ),
            "fit_split": "validation",
            "fit_role": "groups_36_40_full_horizon_only_sensitivity",
            "fit_groups": list(THESIS_SELECTION_GROUPS),
            "calibration_fit_uses_test": False,
            "run_id": args.run_id,
            "model_cell_id": spec["model_cell_id"],
            "seed": int(spec["seed"]),
            "training_completion_sha256": completion["completion_sha256"],
            "model_artifact": completion["best_model"],
            "cached_weights_artifact": completion["cached_weights"],
            "cache_complete_sha256": completion["cache_complete_sha256"],
            "dataset_complete_sha256": completion["dataset_complete_sha256"],
            "selection_samples": len(selection_rows_subset),
            "selection_membership_sha256": sha256_payload(
                [sample_key(row) for row in selection_rows_subset]
            ),
        }
    )
    calibration["calibration_sha256"] = sha256_payload(calibration)

    # All freeze/training/cache/dataset gates above pass before any held-out I/O.
    heldout_arrays = _load_npz(args.cache_dir / "heldout.npz")
    heldout_rows = _aligned_rows(args.dataset_dir / "heldout.jsonl", heldout_arrays)
    if {int(row["ego_init_id"]) for row in heldout_rows} != set(
        THESIS_HELDOUT_GROUPS
    ):
        raise ValueError("Full-horizon held-out groups are not exactly 41--45")
    heldout_mask = np.asarray(heldout_arrays["labels"][..., 2], dtype=bool)
    heldout_indices = np.flatnonzero(np.all(heldout_mask, axis=1))
    if len(heldout_indices) != 326:
        raise ValueError(
            f"Expected 326 full-horizon held-out windows, found {len(heldout_indices)}"
        )
    heldout_subset = {
        key: np.asarray(value)[heldout_indices] for key, value in heldout_arrays.items()
    }
    heldout_rows_subset = [heldout_rows[index] for index in heldout_indices]
    predictions = _predict_cached(
        spec,
        heldout_subset,
        args.base_model,
        args.anchors,
        args.dataset_dir / "interaction_normalization_fit.json",
        args.training_root / args.run_id / "cached_best.weights.h5",
        args.batch_size,
    )
    parameters = calibration["parameters"]
    uncalibrated = evaluate_decoded(
        decode_raw_predictions(predictions, anchors),
        heldout_subset["labels"],
        heldout_rows_subset,
        10,
        temperature=1.0,
        covariance_scale=1.0,
    )
    calibrated = evaluate_decoded(
        decode_raw_predictions(
            predictions,
            anchors,
            temperature=float(parameters["temperature"]),
            covariance_scale=float(parameters["covariance_scale"]),
        ),
        heldout_subset["labels"],
        heldout_rows_subset,
        10,
        temperature=float(parameters["temperature"]),
        covariance_scale=float(parameters["covariance_scale"]),
    )
    report = {
        "schema_version": FULL_HORIZON_EVALUATION_SCHEMA,
        "status": "pass",
        "evidence_status": "retrospective_heldout_full_horizon_sensitivity",
        "split_role": "groups_41_45_full_horizon_only_sensitivity",
        "selection_freeze_sha256": freeze["freeze_sha256"],
        "future_validity_contract": FUTURE_VALIDITY_CONTRACT,
        "run_id": args.run_id,
        "model_cell_id": spec["model_cell_id"],
        "seed": int(spec["seed"]),
        "selection_full_horizon_samples": len(selection_rows_subset),
        "heldout_full_horizon_samples": len(heldout_rows_subset),
        "heldout_membership_sha256": sha256_payload(
            [sample_key(row) for row in heldout_rows_subset]
        ),
        "training_completion_sha256": completion["completion_sha256"],
        "model_artifact": completion["best_model"],
        "cached_weights_artifact": completion["cached_weights"],
        "cache_complete_sha256": completion["cache_complete_sha256"],
        "dataset_complete_sha256": completion["dataset_complete_sha256"],
        "calibration": calibration,
        "uncalibrated": uncalibrated,
        "calibrated": calibrated,
        "claim_boundary": (
            "Sensitivity analysis only: calibration was refitted on full-horizon "
            "selection windows and evaluated on full-horizon held-out windows."
        ),
    }
    report["evaluation_sha256"] = sha256_payload(report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output_dir / "full_horizon_metrics.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("calibrate", "heldout", "full-horizon-sensitivity")
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--training-root", required=True, type=Path)
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--calibration-root", type=Path)
    parser.add_argument("--selection-freeze", type=Path)
    args = parser.parse_args()
    if args.mode == "calibrate":
        report = calibrate(args)
    elif args.mode == "heldout":
        if args.calibration_root is None or args.selection_freeze is None:
            raise ValueError("heldout mode requires calibration root and selection freeze")
        report = evaluate_heldout(args)
    else:
        if args.selection_freeze is None:
            raise ValueError("full-horizon sensitivity requires selection freeze")
        report = evaluate_full_horizon_sensitivity(args)
    print(json.dumps({
        "status": report["status"],
        "run_id": report["run_id"],
        "split_role": report["split_role"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
