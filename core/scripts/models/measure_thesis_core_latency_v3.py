#!/usr/bin/env python3
"""Measure deployment-equivalent warmed batch-one latency for one thesis-core run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

import interaction_adapter_v2  # noqa: F401
import interaction_adapter_v3  # noqa: F401
from capacity_study_v3_analysis import measure_latency
from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload
from evaluate_multipath_model_on_dataset import artifact_hash, load_samples, make_batch
from thesis_core_v3_execute import completion_valid
from thesis_core_v3_runs import validate_thesis_core_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--training-root", required=True, type=Path)
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_thesis_core_manifest(manifest)
    spec = next(row for row in manifest["runs"] if row["run_id"] == args.run_id)
    run_dir = args.training_root / args.run_id
    completion_path = run_dir / "TRAINING_COMPLETE.json"
    if not completion_valid(completion_path, spec):
        raise ValueError("Latency blocked by invalid training completion")
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    parameter_report = json.loads((run_dir / "parameters.json").read_text(encoding="utf-8"))
    trainable_parameters = int(
        parameter_report["cached_trainable"]["trainable_parameters"]
    )
    model = tf.keras.models.load_model(run_dir / "best_model", compile=False)
    sample = next(
        load_samples(
            str(args.dataset_dir / "selection.jsonl"),
            str(args.dataset_dir.parent),
            10,
            max_samples=1,
            require_complete_interaction_history=True,
        )
    )
    _, images, past, context, sequence, mask, _ = make_batch([sample])
    inputs = {
        2: [images, past],
        3: [images, past, context],
        4: [images, past, sequence, mask],
    }.get(len(model.inputs))
    if inputs is None:
        raise ValueError(f"Unsupported model input count: {len(model.inputs)}")

    def predict():
        output = np.asarray(model.predict_on_batch(inputs))
        if not np.all(np.isfinite(output)):
            raise ValueError("Latency prediction contains non-finite output")
        return output

    report = measure_latency(
        predict,
        warmup_count=20,
        measured_count=100,
        trainable_parameters=trainable_parameters,
    )
    report.update(
        {
            "schema_version": "capacity_history_thesis_core_latency_v3",
            "status": "pass",
            "run_id": args.run_id,
            "model_cell_id": spec["model_cell_id"],
            "seed": int(spec["seed"]),
            "selection_groups": [36, 37, 38, 39, 40],
            "model_artifact": completion["best_model"],
            "training_completion_sha256": completion["completion_sha256"],
            "selection_jsonl_sha256": sha256_file(args.dataset_dir / "selection.jsonl"),
            "tensorflow_version": tf.__version__,
            "visible_devices": [device.name for device in tf.config.list_physical_devices()],
            "source_sha256": sha256_file(Path(__file__)),
        }
    )
    report["latency_sha256"] = sha256_payload(report)
    atomic_json(args.output, report)
    print(json.dumps({
        "status": "pass",
        "run_id": args.run_id,
        "mean_ms": report["mean_ms"],
        "p90_ms": report.get("p90_ms"),
    }, sort_keys=True))


if __name__ == "__main__":
    tf.keras.utils.set_random_seed(20260822)
    tf.config.experimental.enable_op_determinism()
    main()
