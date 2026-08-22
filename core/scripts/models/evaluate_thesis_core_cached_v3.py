#!/usr/bin/env python3
"""Fast selection calibration and gated retrospective held-out evaluation."""

from __future__ import annotations

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


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as handle:
        return {name: np.asarray(handle[name]) for name in handle.files}


def _validated_freeze(path: Path, run_id: str) -> dict[str, Any]:
    payload = _load(path)
    value = dict(payload)
    recorded = value.pop("freeze_sha256", None)
    if recorded != sha256_payload(value) or payload.get("status") != "pass":
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
    labels = arrays["labels"][..., :2]
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
        "schema_version": "capacity_history_thesis_core_selection_evaluation_v3",
        "status": "pass",
        "split_role": "groups_36_40_selection",
        "run_id": args.run_id,
        "model_cell_id": spec["model_cell_id"],
        "seed": int(spec["seed"]),
        "samples": len(rows),
        "independent_init_groups": len(THESIS_SELECTION_GROUPS),
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
        calibration.get("run_id") != args.run_id
        or calibration.get("fit_role") != "groups_36_40_selection"
        or calibration.get("calibration_fit_uses_test") is not False
        or calibration.get("model_artifact") != completion["best_model"]
        or calibration.get("cached_weights_artifact") != completion["cached_weights"]
    ):
        raise ValueError("Calibration is not bound to this frozen training run")
    frozen_record = next(
        row for row in freeze["runs"] if row["run_id"] == args.run_id
    )
    if frozen_record["calibration_sha256"] != recorded:
        raise ValueError("Selection freeze/calibration binding mismatch")

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
    labels = arrays["labels"][..., :2]
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
        "schema_version": "capacity_history_thesis_core_heldout_evaluation_v3",
        "status": "pass",
        "evidence_status": "retrospective_held_out",
        "split_role": "groups_41_45_retrospective_heldout",
        "heldout_access_was_gated": True,
        "selection_freeze_sha256": freeze["freeze_sha256"],
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("calibrate", "heldout"))
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
    else:
        if args.calibration_root is None or args.selection_freeze is None:
            raise ValueError("heldout mode requires calibration root and selection freeze")
        report = evaluate_heldout(args)
    print(json.dumps({
        "status": report["status"],
        "run_id": report["run_id"],
        "split_role": report["split_role"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
