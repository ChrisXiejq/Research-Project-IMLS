#!/usr/bin/env python3
"""Numerical and solver preflight for frozen B1 and validation-selected P*."""

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
import math
from pathlib import Path

import numpy as np

from capacity_study_v3_analysis import measure_latency
from capacity_study_v3_closed_loop import validate_dual_predictor_preflight
from capacity_study_v3_freeze import validate_selection_freeze
from deploy_multipath_model import DeployMultiPath
from evaluate_multipath_model_on_dataset import (
    decode_raw_predictions,
    load_samples,
    make_batch,
)
from prediction_input_contract import load_logged_raster


def _frozen_model_identity(freeze: dict, run_id: str) -> str:
    if "runs" in freeze:
        matches = [
            seed["model_identity"] for seed in freeze["runs"] if seed["run_id"] == run_id
        ]
    else:
        matches = [
            seed["model_identity"]
            for cell in freeze["cells"]
            for seed in cell["retained_seeds"]
            if seed["run_id"] == run_id
        ]
    if len(matches) != 1:
        raise ValueError(f"Representative run is not uniquely hash-bound: {run_id}")
    return str(matches[0])


def _array_contract(prediction) -> tuple[bool, bool, bool]:
    probabilities = np.asarray(prediction.mode_probabilities, dtype=np.float64)
    means = np.asarray(prediction.mus, dtype=np.float64)
    covariances = np.asarray(prediction.sigmas, dtype=np.float64)
    probabilities_valid = bool(
        probabilities.ndim == 1
        and np.isfinite(probabilities).all()
        and (probabilities >= 0.0).all()
        and np.isclose(probabilities.sum(), 1.0, atol=1.0e-6)
    )
    output_shape_valid = bool(
        means.ndim == 3
        and means.shape[-1] == 2
        and covariances.shape == means.shape[:-1] + (2, 2)
        and len(probabilities) == means.shape[0]
    )
    covariance_valid = bool(
        np.isfinite(covariances).all()
        and np.allclose(covariances, np.swapaxes(covariances, -1, -2), atol=1.0e-6)
        and (np.linalg.eigvalsh(covariances) > 0.0).all()
    )
    return output_shape_valid, probabilities_valid, covariance_valid


def verify_one(
    *,
    predictor_id: str,
    run_id: str,
    model_path: Path,
    calibration_path: Path,
    frozen_identity: str,
    anchors: np.ndarray,
    sample_item,
    solver_record: dict,
) -> dict:
    deployed = DeployMultiPath(model_path, anchors, calibration=calibration_path)
    metadata = deployed.deployment_metadata()
    actual_identity = metadata["model_artifact"].get("sha256_tree") or metadata[
        "model_artifact"
    ].get("sha256")
    if actual_identity != frozen_identity:
        raise ValueError(f"{predictor_id} model differs from selection freeze")
    (
        _,
        images,
        past_batch,
        context_batch,
        sequence_batch,
        sequence_mask_batch,
        _,
    ) = make_batch([sample_item])
    sample, raster_path, past, _ = sample_item
    if deployed.model_input_count == 4:
        model_inputs = [images, past_batch, sequence_batch, sequence_mask_batch]
        online_context = (sequence_batch[0], sequence_mask_batch[0])
    elif deployed.model_input_count == 3:
        model_inputs = [images, past_batch, context_batch]
        online_context = context_batch[0]
    elif deployed.model_input_count == 2:
        model_inputs = [images, past_batch]
        online_context = None
    else:
        raise ValueError(f"Unsupported predictor input count: {deployed.model_input_count}")
    raw = np.asarray(deployed.model.predict_on_batch(model_inputs))
    offline = decode_raw_predictions(
        raw,
        anchors,
        temperature=deployed.calibration["temperature"],
        covariance_scale=deployed.calibration["covariance_scale"],
    )
    raw_image = load_logged_raster(raster_path)

    def online_call():
        return deployed.predict_instance(
            raw_image, past, interaction_context=online_context
        )

    online = online_call()
    differences = {
        "probabilities": float(
            np.max(np.abs(offline.probabilities[0] - online.mode_probabilities))
        ),
        "means": float(np.max(np.abs(offline.means[0] - online.mus))),
        "covariances": float(
            np.max(np.abs(offline.covariances[0] - online.sigmas))
        ),
    }
    max_difference = max(differences.values())
    shape_valid, probability_valid, covariance_valid = _array_contract(online)
    latency = measure_latency(
        online_call,
        warmup_count=20,
        measured_count=100,
        trainable_parameters=None,
    )
    return {
        "predictor_id": predictor_id,
        "representative_run_id": run_id,
        "model_identity": actual_identity,
        "calibration_model_identity": actual_identity,
        "calibration_identity": metadata["calibration_artifact"]["sha256"],
        "calibration_fit_split": metadata["calibration_fit_split"],
        "model_input_count": deployed.model_input_count,
        "sequence_model_family": deployed.sequence_model_family,
        "output_shape_valid": shape_valid,
        "probabilities_valid": probability_valid,
        "covariances_valid": covariance_valid,
        "joint_mode_mapping_valid": bool(shape_valid and len(online.mode_probabilities) == len(anchors)),
        "solver_smoke_valid": bool(
            solver_record.get("status") == "pass" and solver_record.get("gurobi") is True
        ),
        "offline_online_differences": differences,
        "offline_online_max_abs_diff": max_difference,
        "warmed_batch_one_latency_ms": latency["mean_ms"],
        "latency_limit_ms": 50.0,
        "latency": latency,
        "sample_id": sample.get("sample_id"),
    }


def main() -> None:  # pragma: no cover - requires the server TensorFlow/CARLA stack.
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-freeze", required=True, type=Path)
    parser.add_argument("--closed-loop-manifest", required=True, type=Path)
    parser.add_argument("--training-root", required=True, type=Path)
    parser.add_argument("--calibration-root", required=True, type=Path)
    parser.add_argument("--merged-dir", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--solver-preflight-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    freeze = json.loads(args.selection_freeze.read_text(encoding="utf-8"))
    manifest = json.loads(args.closed_loop_manifest.read_text(encoding="utf-8"))
    solver = json.loads(args.solver_preflight_json.read_text(encoding="utf-8"))
    validate_selection_freeze(freeze)
    anchors = np.load(args.anchors).astype(np.float32)
    sample_jsonl = args.merged_dir / "train.jsonl"
    if not sample_jsonl.is_file():
        sample_jsonl = args.merged_dir / "fit.jsonl"
    iterator = load_samples(
        str(sample_jsonl),
        str(args.merged_dir.parent),
        10,
        max_samples=1,
        require_complete_interaction_history=True,
    )
    sample_item = next(iterator)
    records = {}
    for predictor_id in ("B1", "P_star"):
        run_id = freeze[predictor_id]["representative_run_id"]
        records[predictor_id] = verify_one(
            predictor_id=predictor_id,
            run_id=run_id,
            model_path=args.training_root / run_id / "best_model",
            calibration_path=args.calibration_root / run_id / "calibration.json",
            frozen_identity=_frozen_model_identity(freeze, run_id),
            anchors=anchors,
            sample_item=sample_item,
            solver_record=solver,
        )
    report = validate_dual_predictor_preflight(manifest, freeze, records, solver)
    report["predictor_records"] = records
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "pass", "predictors": list(records)}))


if __name__ == "__main__":
    main()
