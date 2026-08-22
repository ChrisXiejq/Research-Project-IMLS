#!/usr/bin/env python3
"""Materialise hash-bound frozen-B0 outputs for fast thesis-core training."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload
from prediction_dataset_utils import read_jsonl, resolve_raster_path
from prepare_thesis_core_v3_dataset import sample_key
from train_prediction_model_v3 import artifact_hash, load_image, masked_local_label


SPLITS = ("fit", "selection", "heldout")
CACHE_EXTRACTION_SEED = 20260822
CACHE_SOURCE_FILES = (
    "build_thesis_core_feature_cache_v3.py",
    "capacity_study_v3_protocol.py",
    "prediction_dataset_utils.py",
    "prepare_thesis_core_v3_dataset.py",
    "train_prediction_model_v3.py",
)


def cache_source_sha256() -> dict[str, str]:
    directory = Path(__file__).resolve().parent
    return {name: sha256_file(directory / name) for name in CACHE_SOURCE_FILES}


def _final_dense(model: tf.keras.Model) -> tf.keras.layers.Dense:
    layer = next(
        (item for item in reversed(model.layers) if isinstance(item, tf.keras.layers.Dense)),
        None,
    )
    if layer is None:
        raise ValueError("Base model has no Dense prediction head")
    return layer


def extract_split(
    feature_model: tf.keras.Model,
    split_jsonl: Path,
    output_npz: Path,
    *,
    batch_size: int,
    label_horizon: int,
) -> dict[str, Any]:
    rows = list(read_jsonl(str(split_jsonl)))
    base_chunks: list[np.ndarray] = []
    feature_chunks: list[np.ndarray] = []
    sequences: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    identifiers: list[str] = []
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        images = np.stack(
            [load_image(np.asarray(str(resolve_raster_path(row)).encode("utf-8"))) for row in batch]
        )
        past = np.stack([np.asarray(row["past_states_local"], dtype=np.float32) for row in batch])
        base_raw, head_features = feature_model.predict_on_batch([images, past])
        base_chunks.append(np.asarray(base_raw, dtype=np.float32))
        feature_chunks.append(np.asarray(head_features, dtype=np.float32))
        for row in batch:
            identifiers.append(sample_key(row))
            sequences.append(np.asarray(row["interaction_sequence"], dtype=np.float32))
            masks.append(np.asarray(row["interaction_sequence_mask"], dtype=np.float32))
            labels.append(masked_local_label(row, label_horizon))
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"Duplicate cache identifiers in {split_jsonl}")
    arrays = {
        "sample_ids": np.asarray(identifiers),
        "base_raw": np.concatenate(base_chunks, axis=0),
        "head_features": np.concatenate(feature_chunks, axis=0),
        "sequence": np.stack(sequences),
        "mask": np.stack(masks),
        "labels": np.stack(labels),
    }
    if any(not np.all(np.isfinite(value)) for key, value in arrays.items() if key != "sample_ids"):
        raise ValueError(f"Non-finite cached tensor in {split_jsonl}")
    temporary = output_npz.with_suffix(output_npz.suffix + ".tmp")
    with temporary.open("wb") as handle:
        np.savez(handle, **arrays)
    os.replace(temporary, output_npz)
    return {
        "path": str(output_npz.resolve()),
        "sha256": sha256_file(output_npz),
        "samples": len(identifiers),
        "base_output_dim": int(arrays["base_raw"].shape[1]),
        "head_feature_dim": int(arrays["head_features"].shape[1]),
        "label_shape": list(arrays["labels"].shape[1:]),
    }


def build_cache(
    dataset_dir: Path,
    base_model_path: Path,
    output_dir: Path,
    *,
    batch_size: int = 32,
    label_horizon: int = 10,
) -> dict[str, Any]:
    tf.keras.utils.set_random_seed(CACHE_EXTRACTION_SEED)
    tf.config.experimental.enable_op_determinism()
    dataset_complete = dataset_dir / "THESIS_CORE_DATASET_COMPLETE.json"
    dataset_manifest = json.loads(dataset_complete.read_text(encoding="utf-8"))
    dataset_copy = dict(dataset_manifest)
    recorded = dataset_copy.pop("manifest_sha256", None)
    if recorded != sha256_payload(dataset_copy):
        raise ValueError("Thesis-core dataset manifest hash mismatch")
    base = tf.keras.models.load_model(base_model_path, compile=False)
    base.trainable = False
    final_dense = _final_dense(base)
    feature_model = tf.keras.Model(base.inputs, [base.output, final_dense.input])
    output_dir.mkdir(parents=True, exist_ok=True)
    split_records = {
        split: extract_split(
            feature_model,
            dataset_dir / f"{split}.jsonl",
            output_dir / f"{split}.npz",
            batch_size=batch_size,
            label_horizon=label_horizon,
        )
        for split in SPLITS
    }
    manifest = {
        "schema_version": "capacity_history_thesis_core_feature_cache_v3",
        "status": "pass",
        "dataset_manifest": str(dataset_complete.resolve()),
        "dataset_manifest_sha256": sha256_file(dataset_complete),
        "base_model": str(base_model_path.resolve()),
        "base_model_artifact": artifact_hash(base_model_path),
        "batch_size": batch_size,
        "deterministic_extraction": True,
        "extraction_seed": CACHE_EXTRACTION_SEED,
        "label_horizon": label_horizon,
        "source_sha256": cache_source_sha256(),
        "splits": split_records,
    }
    manifest["cache_manifest_sha256"] = sha256_payload(manifest)
    atomic_json(output_dir / "CACHE_COMPLETE.json", manifest)
    return manifest


def validate_cache(cache_dir: Path, dataset_dir: Path, base_model_path: Path) -> dict[str, Any]:
    path = cache_dir / "CACHE_COMPLETE.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = dict(payload)
    recorded = value.pop("cache_manifest_sha256", None)
    if recorded != sha256_payload(value):
        raise ValueError("Feature-cache manifest hash mismatch")
    if payload["dataset_manifest_sha256"] != sha256_file(dataset_dir / "THESIS_CORE_DATASET_COMPLETE.json"):
        raise ValueError("Feature-cache dataset provenance drift")
    if payload["base_model_artifact"] != artifact_hash(base_model_path):
        raise ValueError("Feature-cache base-model provenance drift")
    if payload.get("deterministic_extraction") is not True:
        raise ValueError("Feature cache was not extracted deterministically")
    if payload.get("extraction_seed") != CACHE_EXTRACTION_SEED:
        raise ValueError("Feature-cache extraction seed drift")
    if payload.get("source_sha256") != cache_source_sha256():
        raise ValueError("Feature-cache implementation provenance drift")
    for record in payload["splits"].values():
        path_value = Path(record["path"])
        if not path_value.is_file() or sha256_file(path_value) != record["sha256"]:
            raise ValueError("Feature-cache split hash drift")
    return {
        "status": "pass",
        "cache_manifest_sha256": recorded,
        "batch_size": int(payload["batch_size"]),
        "splits": payload["splits"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--label-horizon", type=int, default=10)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        report = validate_cache(args.output_dir, args.dataset_dir, args.base_model)
    else:
        report = build_cache(
            args.dataset_dir,
            args.base_model,
            args.output_dir,
            batch_size=args.batch_size,
            label_horizon=args.label_horizon,
        )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
