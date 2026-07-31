#!/usr/bin/env python3
"""Verify evaluator/deployment equivalence on one real logged raster sample."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf
from tensorflow.keras.applications.resnet import preprocess_input

from deploy_multipath_model import DeployMultiPath
from evaluate_multipath_model_on_dataset import (
    decode_raw_predictions,
    load_samples,
    make_batch,
)
from prediction_dataset_utils import interaction_context_from_sample


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-dir", required=True)
    parser.add_argument("--split", default="val", choices=["train", "val", "test"])
    parser.add_argument("--model", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--calibration-json", default=None)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--output-json", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    merged_dir = os.path.abspath(args.merged_dir)
    result_dir = os.path.abspath(os.path.join(merged_dir, os.pardir))
    anchors = np.load(args.anchors).astype(np.float32)
    deploy = DeployMultiPath(args.model, anchors, calibration=args.calibration_json)
    iterator = load_samples(
        os.path.join(merged_dir, f"{args.split}.jsonl"),
        result_dir,
        args.horizon,
        max_samples=1,
    )
    item = next(iterator)
    sample, raster_path, past, _ = item
    samples, evaluator_images, past_batch, context_batch, _ = make_batch([item])

    raw_image = cv2.imread(raster_path, cv2.IMREAD_COLOR)
    if raw_image is None:
        raise ValueError(f"Unable to decode raster: {raster_path}")
    deployment_preprocessed = preprocess_input(
        tf.cast(raw_image[None, ...], tf.float32)
    ).numpy()
    input_difference = float(
        np.max(np.abs(evaluator_images - deployment_preprocessed))
    )

    model_inputs = (
        [evaluator_images, past_batch, context_batch]
        if deploy.uses_interaction_context
        else [evaluator_images, past_batch]
    )
    raw_prediction = np.asarray(deploy.model.predict_on_batch(model_inputs))
    offline = decode_raw_predictions(
        raw_prediction,
        anchors,
        temperature=deploy.calibration["temperature"],
        covariance_scale=deploy.calibration["covariance_scale"],
    )
    online = deploy.predict_instance(
        raw_image,
        past,
        interaction_context=interaction_context_from_sample(sample),
    )

    differences = {
        "preprocessed_input_max_abs": input_difference,
        "probability_max_abs": float(
            np.max(np.abs(offline.probabilities[0] - online.mode_probabilities))
        ),
        "mean_max_abs": float(np.max(np.abs(offline.means[0] - online.mus))),
        "covariance_max_abs": float(
            np.max(np.abs(offline.covariances[0] - online.sigmas))
        ),
    }
    passed = (
        differences["preprocessed_input_max_abs"] == 0.0
        and differences["probability_max_abs"] <= 1.0e-7
        and differences["mean_max_abs"] <= 1.0e-6
        and differences["covariance_max_abs"] <= 1.0e-5
    )
    report = {
        "sample_equivalence_schema_version": "multipath_real_sample_equivalence_v1",
        "status": "pass" if passed else "fail",
        "split": args.split,
        "source_subrun": sample.get("source_subrun"),
        "sample_id": sample.get("sample_id"),
        "raster_path": raster_path,
        "uses_interaction_context": deploy.uses_interaction_context,
        "calibration": deploy.calibration,
        "differences": differences,
        "channel_contract": (
            "cv2.imread restores the byte order written by cv2.imwrite and "
            "matches the online in-memory semantic raster before ResNet preprocessing"
        ),
    }
    output_path = Path(args.output_json).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
