#!/usr/bin/env python3
"""Verify frozen Day 8 B1 and optional B0 can be deployed online for Day 9."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from deploy_multipath_model import DeployMultiPath
from prediction_dataset_utils import read_jsonl, resolve_raster_path
from prediction_input_contract import load_logged_raster


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def smoke(model: DeployMultiPath, image: np.ndarray, past: np.ndarray) -> dict:
    prediction = model.predict_instance(image, past)
    probabilities = np.asarray(prediction.mode_probabilities, dtype=float)
    means = np.asarray(prediction.mus, dtype=float)
    covariances = np.asarray(prediction.sigmas, dtype=float)
    eigenvalues = np.linalg.eigvalsh(covariances)
    checks = {
        "probabilities_finite": bool(np.isfinite(probabilities).all()),
        "probabilities_nonnegative": bool((probabilities >= 0.0).all()),
        "probabilities_sum_to_one": bool(np.isclose(probabilities.sum(), 1.0, atol=1e-6)),
        "means_finite": bool(np.isfinite(means).all()),
        "covariances_finite": bool(np.isfinite(covariances).all()),
        "covariances_symmetric": bool(
            np.allclose(covariances, np.swapaxes(covariances, -1, -2), atol=1e-6)
        ),
        "covariances_positive_definite": bool((eigenvalues > 0.0).all()),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "probability_sum": float(probabilities.sum()),
        "minimum_covariance_eigenvalue": float(eigenvalues.min()),
        "probability_shape": list(probabilities.shape),
        "mean_shape": list(means.shape),
        "covariance_shape": list(covariances.shape),
    }


def load_frozen_train_input(day7_results: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    jsonl_path = day7_results / "train.jsonl"
    result_dir = str(day7_results.parent)
    for sample in read_jsonl(str(jsonl_path)):
        raster_path = resolve_raster_path(sample, result_dir=result_dir)
        if raster_path and Path(raster_path).is_file():
            image = load_logged_raster(raster_path)
            past = np.asarray(sample["past_states_local"], dtype=np.float32)
            if tuple(image.shape[:2]) == (500, 500) and past.shape == (5, 4):
                return image, past, {
                    "split": "train",
                    "jsonl": str(jsonl_path),
                    "jsonl_sha256": sha256(jsonl_path),
                    "raster": str(Path(raster_path).resolve()),
                    "raster_sha256": sha256(Path(raster_path)),
                    "cell_id": sample.get("cell_id"),
                    "ego_init_id": sample.get("ego_init_id"),
                    "source_subrun": sample.get("source_subrun"),
                    "sample_id": sample.get("sample_id"),
                    "image_shape": list(image.shape),
                    "past_states_shape": list(past.shape),
                }
    raise ValueError(f"No deployment-compatible frozen train sample in {jsonl_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day7-results", required=True)
    parser.add_argument("--day8-results", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--baseline-model", default=None)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    day7 = Path(args.day7_results).resolve()
    day8 = Path(args.day8_results).resolve()
    model_path = Path(args.model).resolve()
    calibration_path = Path(args.calibration).resolve()
    anchors_path = Path(args.anchors).resolve()
    completion = json.loads((day8 / "DAY8_COMPLETE.json").read_text())
    freeze_path = day8 / "final_test_v1" / "DAY8_MODEL_SELECTION_FROZEN.json"
    freeze = json.loads(freeze_path.read_text())
    if completion.get("status") != "pass" or not completion.get("frozen_test_complete"):
        raise ValueError("Day 8 is not complete")
    if completion.get("test_used_for_selection") is not False:
        raise ValueError("Day 8 selection leakage gate failed")
    if (
        freeze.get("closed_loop_selected_variant") != "B1"
        or int(freeze.get("closed_loop_selected_seed", -1)) != 37
    ):
        raise ValueError("Day 9 requires frozen B1/seed 37")
    expected = freeze["representatives_for_single_test_pass"]["B1"]

    anchors = np.load(anchors_path).astype(np.float32)
    deployed = DeployMultiPath(model_path, anchors, calibration=calibration_path)
    metadata = deployed.deployment_metadata()
    if metadata["model_artifact"].get("sha256_tree") != expected["model"]["sha256_tree"]:
        raise ValueError("B1 model tree hash differs from the Day 8 freeze")
    if metadata["calibration_artifact"].get("sha256") != expected["calibration"]["sha256"]:
        raise ValueError("B1 calibration hash differs from the Day 8 freeze")
    if metadata["calibration_parameters"] != {
        "temperature": expected["calibration_parameters"]["temperature"],
        "covariance_scale": expected["calibration_parameters"]["covariance_scale"],
    }:
        raise ValueError("B1 calibration parameters differ from the Day 8 freeze")
    calibration = json.loads(calibration_path.read_text())
    expected_anchors = calibration.get("anchors_artifact") or {}
    if expected_anchors.get("sha256") and expected_anchors["sha256"] != sha256(anchors_path):
        raise ValueError("Anchor hash differs from the validation calibration artifact")
    image, past, warmup_input = load_frozen_train_input(day7)
    b1_smoke = smoke(deployed, image, past)
    if b1_smoke["status"] != "pass":
        raise ValueError(f"B1 numerical deployment smoke failed: {b1_smoke}")

    baseline = None
    if args.baseline_model:
        baseline_model = DeployMultiPath(Path(args.baseline_model).resolve(), anchors)
        baseline_smoke = smoke(baseline_model, image, past)
        if baseline_smoke["status"] != "pass":
            raise ValueError(f"B0 numerical deployment smoke failed: {baseline_smoke}")
        baseline = {
            "deployment": baseline_model.deployment_metadata(),
            "numerical_smoke": baseline_smoke,
        }

    payload = {
        "schema_version": "day9_deployment_preflight_v1",
        "status": "pass",
        "day8_complete": True,
        "selection_freeze_sha256": sha256(freeze_path),
        "selected_variant": "B1",
        "selected_seed": 37,
        "normalization": {
            "interaction_normalization": "not_applicable_for_two_input_B1",
            "raster": "shared ResNet preprocess_input contract",
            "past_states": "no explicit normalization",
        },
        "warmup_input": warmup_input,
        "b1": {"deployment": metadata, "numerical_smoke": b1_smoke},
        "b0": baseline,
        "anchors": DeployMultiPath._artifact_hash(anchors_path),
    }
    output = Path(args.output_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output, payload)
    print(json.dumps({"status": "pass", "selected_variant": "B1", "selected_seed": 37}))


if __name__ == "__main__":
    main()
