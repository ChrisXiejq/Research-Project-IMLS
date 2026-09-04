#!/usr/bin/env python3
"""Measure warmed batch-one inference latency for one frozen V3 model."""

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

import numpy as np
import tensorflow as tf

import interaction_adapter_v2  # noqa: F401
import interaction_adapter_v3  # noqa: F401
from capacity_study_v3_analysis import measure_latency
from capacity_study_v3_protocol import atomic_json, sha256_file
from evaluate_multipath_model_on_dataset import load_samples, make_batch


def main() -> None:  # pragma: no cover - runs in the TensorFlow server image.
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--merged-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trainable-parameters", required=True, type=int)
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    model = tf.keras.models.load_model(args.model, compile=False)
    sample = next(
        load_samples(
            str(args.merged_dir / "val.jsonl"),
            str(args.merged_dir.parent),
            10,
            max_samples=1,
            require_complete_interaction_history=True,
        )
    )
    _, images, past, context, sequence, mask, _ = make_batch([sample])
    input_count = len(model.inputs)
    inputs = {
        2: [images, past],
        3: [images, past, context],
        4: [images, past, sequence, mask],
    }.get(input_count)
    if inputs is None:
        raise ValueError(f"Unsupported model input count: {input_count}")

    def predict():
        value = np.asarray(model.predict_on_batch(inputs))
        if not np.isfinite(value).all():
            raise ValueError("Latency run produced non-finite predictions")
        return value

    report = measure_latency(
        predict,
        warmup_count=20,
        measured_count=100,
        trainable_parameters=args.trainable_parameters,
    )
    report.update(
        {
            "schema_version": "capacity_history_latency_v3",
            "status": "pass",
            "run_id": args.run_id,
            "model_sha256_tree": __import__(
                "train_prediction_model_v3"
            ).artifact_hash(args.model)["sha256_tree"],
            "tensorflow_version": tf.__version__,
            "visible_devices": [device.name for device in tf.config.list_physical_devices()],
            "source_sha256": sha256_file(Path(__file__)),
        }
    )
    atomic_json(args.output_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
