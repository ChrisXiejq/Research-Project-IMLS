#!/usr/bin/env python3
"""E2 resumable B1 raster/history neutralisation and shuffle diagnostics.

This is intentionally a frozen diagnostic: the model, labels and split do not
change.  Train-only means are used for neutral inputs, and shuffle donors are
forced to come from a different ego-init group.
"""

from __future__ import annotations

import argparse

import json
import os
import time
from pathlib import Path

import numpy as np
import tensorflow as tf

import evaluate_multipath_model_on_dataset as evaluator
from distinction_analysis_utils import atomic_write_json, sha256_file
from prediction_input_contract import load_logged_raster, preprocess_resnet_raster


CONDITIONS = ("original", "raster_mean", "raster_shuffle", "past_mean", "past_shuffle")


def load_image(path: str) -> np.ndarray:
    image = load_logged_raster(path)
    if tuple(image.shape[:2]) != (500, 500):
        import cv2

        image = cv2.resize(image, (500, 500), interpolation=cv2.INTER_LINEAR)
    return preprocess_resnet_raster(image)[0].astype(np.float32)


def init_id(item) -> int:
    return int(item[0]["ego_init_id"])


def cross_init_donor_indices(items: list, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    groups = {}
    for index, item in enumerate(items):
        groups.setdefault(init_id(item), []).append(index)
    init_ids = sorted(groups)
    shuffled_ids = init_ids.copy()
    while True:
        rng.shuffle(shuffled_ids)
        if all(left != right for left, right in zip(init_ids, shuffled_ids)):
            break
    donors = np.zeros(len(items), dtype=np.int64)
    for receiver_init, donor_init in zip(init_ids, shuffled_ids):
        receiver_indices = groups[receiver_init]
        donor_indices = groups[donor_init].copy()
        rng.shuffle(donor_indices)
        for position, receiver_index in enumerate(receiver_indices):
            donors[receiver_index] = donor_indices[position % len(donor_indices)]
    if any(init_id(items[index]) == init_id(items[int(donors[index])]) for index in range(len(items))):
        raise RuntimeError("Cross-init shuffle construction failed")
    return donors


def train_means(train_items: list, cache_path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    if cache_path.exists():
        cache = np.load(cache_path)
        return cache["raster_channel_mean"], cache["past_mean"], json.loads(str(cache["metadata"]))
    channel_sum = np.zeros(3, dtype=np.float64)
    pixel_count = 0
    past_sum = np.zeros_like(np.asarray(train_items[0][2], dtype=np.float64))
    for index, item in enumerate(train_items):
        image = load_image(item[1])
        channel_sum += image.sum(axis=(0, 1), dtype=np.float64)
        pixel_count += image.shape[0] * image.shape[1]
        past_sum += np.asarray(item[2], dtype=np.float64)
        if (index + 1) % 250 == 0:
            print(json.dumps({"event": "train_mean_progress", "processed": index + 1, "total": len(train_items)}), flush=True)
    raster_mean = (channel_sum / pixel_count).astype(np.float32)
    past_mean = (past_sum / len(train_items)).astype(np.float32)
    metadata = {"train_full_horizon_samples": len(train_items), "pixel_count": pixel_count}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache_path, raster_channel_mean=raster_mean, past_mean=past_mean, metadata=json.dumps(metadata))
    return raster_mean, past_mean, metadata


def predict_condition(
    model,
    items: list,
    condition: str,
    raster_mean: np.ndarray,
    past_mean: np.ndarray,
    donors: np.ndarray,
    batch_size: int,
) -> tuple[list, np.ndarray, np.ndarray, dict]:
    samples, predictions, labels = [], [], []
    started = time.perf_counter()
    for start in range(0, len(items), batch_size):
        indices = list(range(start, min(start + batch_size, len(items))))
        images, pasts, batch_labels = [], [], []
        for index in indices:
            sample, raster_path, past, label = items[index]
            raster_source = items[int(donors[index])][1] if condition == "raster_shuffle" else raster_path
            image = load_image(raster_source)
            if condition == "raster_mean":
                image = np.broadcast_to(raster_mean, image.shape).copy()
            past_value = np.asarray(past, dtype=np.float32)
            if condition == "past_mean":
                past_value = past_mean.copy()
            elif condition == "past_shuffle":
                past_value = np.asarray(items[int(donors[index])][2], dtype=np.float32)
            images.append(image)
            pasts.append(past_value)
            batch_labels.append(label)
            samples.append(sample)
        predictions.append(np.asarray(model.predict_on_batch([np.asarray(images), np.asarray(pasts)])))
        labels.append(np.asarray(batch_labels, dtype=np.float32))
        print(json.dumps({"event": "condition_progress", "condition": condition, "processed": len(samples), "total": len(items)}), flush=True)
    elapsed = time.perf_counter() - started
    return samples, np.concatenate(predictions), np.concatenate(labels), {
        "seconds": elapsed,
        "mean_ms_per_sample_including_input_io": 1000.0 * elapsed / len(items),
    }


def evaluate_subset(raw: np.ndarray, labels: np.ndarray, samples: list, anchors: np.ndarray, calibration: dict) -> dict:
    uncalibrated = evaluator.evaluate_decoded(
        evaluator.decode_raw_predictions(raw, anchors), labels, samples, 10, temperature=1.0, covariance_scale=1.0
    )
    parameters = calibration["parameters"]
    calibrated = evaluator.evaluate_decoded(
        evaluator.decode_raw_predictions(
            raw,
            anchors,
            temperature=float(parameters["temperature"]),
            covariance_scale=float(parameters["covariance_scale"]),
        ),
        labels,
        samples,
        10,
        temperature=float(parameters["temperature"]),
        covariance_scale=float(parameters["covariance_scale"]),
    )
    return {"uncalibrated": uncalibrated, "calibrated": calibrated}


def compact(condition: str, result: dict) -> dict:
    output = {"condition": condition}
    for subset in ("all", "response_active"):
        value = result.get(subset)
        if not value:
            output[f"{subset}_samples"] = 0
            continue
        uncal, cal = value["uncalibrated"], value["calibrated"]
        output.update(
            {
                f"{subset}_samples": uncal["samples"],
                f"{subset}_top1_ADE_m": uncal["top1_ADE_mean"],
                f"{subset}_top1_FDE_m": uncal["top1_FDE_mean"],
                f"{subset}_uncalibrated_rollout_macro_NLL": uncal["rollout_aggregation"]["macro_mean"]["trajectory_mixture_NLL_per_step_mean"],
                f"{subset}_calibrated_rollout_macro_NLL": cal["rollout_aggregation"]["macro_mean"]["trajectory_mixture_NLL_per_step_mean"],
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--anchors", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260808)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_dir = str(args.merged_dir.resolve().parent)
    train_items = list(evaluator.load_samples(str(args.merged_dir / "train.jsonl"), result_dir, 10, subset="all"))
    test_items = list(evaluator.load_samples(str(args.merged_dir / "test.jsonl"), result_dir, 10, subset="all"))
    raster_mean, past_mean, mean_metadata = train_means(train_items, args.output_dir / "train_input_means.npz")
    donors = cross_init_donor_indices(test_items, args.seed)
    model = tf.keras.models.load_model(args.model, compile=False)
    if len(model.inputs) != 2:
        raise ValueError(f"B1 diagnostic requires a two-input model, found {len(model.inputs)}")
    anchors = np.load(args.anchors).astype(np.float32)
    calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    summaries = []
    for condition in CONDITIONS:
        destination = args.output_dir / f"condition_{condition}.json"
        if destination.exists():
            result = json.loads(destination.read_text(encoding="utf-8"))
            summaries.append(compact(condition, result))
            print(json.dumps({"event": "resume_skip", "condition": condition}), flush=True)
            continue
        samples, raw, labels, timing = predict_condition(
            model, test_items, condition, raster_mean, past_mean, donors, args.batch_size
        )
        result = {"condition": condition, "timing": timing, "all": evaluate_subset(raw, labels, samples, anchors, calibration)}
        active_indices = [
            index
            for index, sample in enumerate(samples)
            if sample.get("target_style") == "defensive_reactive"
            and bool((sample.get("target_reactive_diagnostics") or {}).get("active"))
        ]
        if active_indices:
            result["response_active"] = evaluate_subset(
                raw[active_indices], labels[active_indices], [samples[index] for index in active_indices], anchors, calibration
            )
        atomic_write_json(destination, result)
        summaries.append(compact(condition, result))

    original = next(row for row in summaries if row["condition"] == "original")
    for row in summaries:
        for key, value in list(row.items()):
            if key in {"condition"} or key.endswith("samples") or value is None:
                continue
            row[f"delta_vs_original__{key}"] = float(value) - float(original[key])
    final = {
        "schema_version": "distinction_b1_base_input_diagnostics_v1",
        "status": "pass",
        "result_generation": "distinction_v1",
        "model": str(args.model.resolve()),
        "model_artifact": evaluator.artifact_hash(args.model.resolve()),
        "anchors_sha256": sha256_file(args.anchors),
        "calibration_sha256": sha256_file(args.calibration),
        "train_input_mean_metadata": mean_metadata,
        "raster_channel_mean_after_caffe_preprocessing": raster_mean.tolist(),
        "past_state_train_mean": past_mean.tolist(),
        "shuffle_rule": "deterministic donor from a different ego_init_id; receiver labels remain unchanged",
        "test_samples": len(test_items),
        "conditions": summaries,
        "claim_boundary": "Neutralisation is an out-of-distribution sensitivity diagnostic; shuffle is the stronger input-use check and is not proof of semantic causal understanding.",
    }
    atomic_write_json(args.output_dir / "b1_base_input_diagnostics.json", final)
    atomic_write_json(args.output_dir / "E2_COMPLETE.json", {"stage": "E2", "status": "pass", "artifact": "b1_base_input_diagnostics.json"})
    print(json.dumps(final, indent=2), flush=True)


if __name__ == "__main__":
    main()
