#!/usr/bin/env python3
"""Train one manifest-defined V3 capacity/history model without test access."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import csv
import hashlib
import json
import math
import os
import random
import shutil
import time
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

try:  # Pure contract tests run on machines without the server TensorFlow image.
    import tensorflow as tf
except ModuleNotFoundError:  # pragma: no cover - exercised on the training server.
    tf = None

from capacity_study_v3_protocol import (
    CORE_EPOCHS,
    COLLECTION_CELLS,
    EARLY_STOPPING_PATIENCE,
    ENCODER_DROPOUT,
    EXTENDED_EPOCHS,
    GRADIENT_CLIP_NORM,
    PROTOCOL_PATH,
    TRAIN_GROUPS,
    VALIDATION_GROUPS,
    WEIGHT_DECAY,
    atomic_json,
    load_protocol,
    sha256_file,
    sha256_payload,
    validate_protocol,
)
from capacity_study_v3_runs import validate_run_manifest
from interaction_sequence_v3 import apply_history_horizon, has_complete_interaction_history
from prediction_dataset_utils import read_jsonl, resolve_raster_path


SCRIPT_DIR = Path(__file__).resolve().parent
MODELS_DIR = SCRIPT_DIR.parent
SOURCE_FILES = (
    SCRIPT_DIR / "train_prediction_model_v3.py",
    SCRIPT_DIR / "interaction_adapter_v2.py",
    SCRIPT_DIR / "interaction_adapter_v3.py",
    SCRIPT_DIR / "interaction_sequence_v3.py",
    SCRIPT_DIR / "capacity_model_config_v3.py",
    SCRIPT_DIR / "capacity_study_v3_protocol.py",
    SCRIPT_DIR / "capacity_study_v3_runs.py",
    MODELS_DIR / "training" / "evaluate_multipath_model_on_dataset.py",
    MODELS_DIR / "modeling" / "multipath_gmm_utils.py",
    MODELS_DIR / "data" / "prediction_dataset_utils.py",
    MODELS_DIR / "modeling" / "prediction_input_contract.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-manifest", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--merged-dir", required=True, type=Path)
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--epochs", type=int, choices=(CORE_EPOCHS, EXTENDED_EPOCHS))
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--label-horizon", type=int, default=10)
    parser.add_argument("--shuffle-buffer", type=int, default=1024)
    parser.add_argument("--max-train-samples", type=int)
    parser.add_argument("--max-val-samples", type=int)
    return parser.parse_args()


def load_run_spec(manifest_path: Path, identifier: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") in {
        "capacity_history_convergence_plan_v3",
        "capacity_history_fraction_convergence_plan_v3",
    }:
        value = dict(manifest)
        recorded = value.pop("plan_sha256", None)
        value.pop("payload_sha256", None)
        if recorded != sha256_payload(value):
            raise ValueError("Convergence extension manifest hash mismatch")
        if manifest.get("status") != "requires_extension":
            raise ValueError("Convergence plan does not authorize extension training")
        matches = [
            row for row in manifest.get("extension_runs", []) if row["run_id"] == identifier
        ]
        if len(matches) != 1:
            raise ValueError(f"Run id must resolve to one extension spec: {identifier}")
        return matches[0], manifest
    validate_run_manifest(manifest)
    core_matches = [row for row in manifest["core_runs"] if row["run_id"] == identifier]
    if len(core_matches) == 1:
        return core_matches[0], manifest
    fraction_matches = [
        row for row in manifest["fraction_runs"] if row["run_id"] == identifier
    ]
    if len(fraction_matches) != 1:
        raise ValueError(f"Run id must resolve to one semantic spec: {identifier}")
    return fraction_matches[0], manifest


def source_hashes() -> dict[str, str]:
    return {path.name: sha256_file(path) for path in SOURCE_FILES}


def semantic_run_config(
    *,
    spec: Mapping[str, Any],
    manifest_path: Path,
    merged_dir: Path,
    base_model: Path,
    anchors: Path,
    epochs: int,
    batch_size: int,
    label_horizon: int,
    shuffle_buffer: int,
    max_train_samples: int | None,
    max_val_samples: int | None,
) -> dict[str, Any]:
    if epochs not in (CORE_EPOCHS, EXTENDED_EPOCHS):
        raise ValueError("V3 epochs must use the frozen 80/120 budget")
    return {
        "schema_version": "capacity_history_training_config_v3",
        "run_spec": dict(spec),
        "run_manifest": str(manifest_path.resolve()),
        "run_manifest_sha256": sha256_file(manifest_path),
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "merged_dir": str(merged_dir.resolve()),
        "base_model": str(base_model.resolve()),
        "anchors": str(anchors.resolve()),
        "base_model_artifact": artifact_hash(base_model),
        "anchors_sha256": sha256_file(anchors),
        "dataset_artifact_sha256": {
            "train_jsonl": sha256_file(merged_dir / "train.jsonl"),
            "val_jsonl": sha256_file(merged_dir / "val.jsonl"),
            "day7_complete": sha256_file(merged_dir / "DAY7_COMPLETE.json"),
            "model_implementation_complete": sha256_file(
                merged_dir / "DAY7_MODEL_IMPLEMENTATION_COMPLETE.json"
            ),
            "interaction_normalization_train": (
                sha256_file(merged_dir / "interaction_normalization_train.json")
                if (merged_dir / "interaction_normalization_train.json").is_file()
                else None
            ),
        },
        "epochs": epochs,
        "batch_size": batch_size,
        "label_horizon": label_horizon,
        "shuffle_buffer": shuffle_buffer,
        "max_train_samples": max_train_samples,
        "max_val_samples": max_val_samples,
        "optimization": {
            "optimizer": "adamw",
            "weight_decay": WEIGHT_DECAY,
            "gradient_clip_norm": GRADIENT_CLIP_NORM,
            "encoder_dropout": ENCODER_DROPOUT,
            "early_stopping_patience": EARLY_STOPPING_PATIENCE,
            "checkpoint_metric": "validation_rollout_macro_trajectory_mixture_NLL_per_step",
        },
        "source_sha256": source_hashes(),
    }


def assert_resume_compatible(existing: Mapping[str, Any], requested: Mapping[str, Any]) -> None:
    if existing != requested:
        changed = sorted(
            key
            for key in set(existing) | set(requested)
            if existing.get(key) != requested.get(key)
        )
        raise ValueError(f"Resume semantic config drift detected: {changed}")


def masked_local_label(sample: Mapping[str, Any], horizon: int) -> np.ndarray:
    label = np.zeros((horizon, 3), dtype=np.float32)
    rotation = np.asarray(sample["target_to_world_R"], dtype=np.float32)
    translation = np.asarray(sample["target_to_world_t"], dtype=np.float32)
    future = sample.get("future_xy_world") or []
    mask = sample.get("future_valid_mask") or []
    for index in range(min(horizon, len(mask), len(future))):
        if mask[index] and future[index] and future[index][0] is not None:
            label[index, :2] = (
                np.asarray(future[index], dtype=np.float32) - translation
            ) @ rotation
            label[index, 2] = 1.0
    return label


def sample_generator(
    jsonl: Path,
    *,
    family: str,
    history_horizon_s: float | None,
    label_horizon: int,
    allowed_train_groups: set[int] | None,
    maximum: int | None,
) -> Iterator[tuple[bytes, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    emitted = 0
    for sample in read_jsonl(str(jsonl)):
        if allowed_train_groups is not None and int(sample["ego_init_id"]) not in allowed_train_groups:
            continue
        original_mask = sample.get("interaction_sequence_mask") or []
        if not has_complete_interaction_history(original_mask):
            continue
        label = masked_local_label(sample, label_horizon)
        if not np.any(label[:, 2]):
            continue
        raster_path = resolve_raster_path(sample)
        if not raster_path or not os.path.exists(raster_path):
            continue
        sequence = np.asarray(sample["interaction_sequence"], dtype=np.float32)
        mask = np.asarray(original_mask, dtype=np.float32)
        past = np.asarray(sample["past_states_local"], dtype=np.float32)
        if not (
            np.all(np.isfinite(sequence))
            and np.all(np.isfinite(mask))
            and np.all(np.isfinite(past))
            and np.all(np.isfinite(label))
        ):
            raise ValueError(
                f"Non-finite model input or label: {_sample_key(sample)}"
            )
        if family != "head":
            if history_horizon_s is None:
                raise ValueError("Encoder run requires history_horizon_s")
            sequence, mask = apply_history_horizon(sequence, mask, history_horizon_s)
        yield (
            raster_path.encode("utf-8"),
            past,
            sequence,
            mask,
            label,
        )
        emitted += 1
        if maximum is not None and emitted >= maximum:
            return


def validation_sample_metadata(
    jsonl: Path,
    *,
    label_horizon: int,
    maximum: int | None,
) -> list[dict[str, Any]]:
    """Return metadata in exactly the deterministic validation generator order."""

    rows = []
    for sample in read_jsonl(str(jsonl)):
        if not has_complete_interaction_history(
            sample.get("interaction_sequence_mask") or []
        ):
            continue
        label = masked_local_label(sample, label_horizon)
        raster_path = resolve_raster_path(sample)
        if not np.any(label[:, 2]) or not raster_path or not os.path.exists(raster_path):
            continue
        rows.append(dict(sample))
        if maximum is not None and len(rows) >= maximum:
            break
    return rows


def count_samples(**kwargs) -> int:
    return sum(1 for _ in sample_generator(**kwargs))


def _sample_key(sample: Mapping[str, Any]) -> str:
    required = ("ego_init_id", "sample_id")
    if any(name not in sample for name in required):
        raise ValueError(f"Dataset sample is missing identity fields: {required}")
    return "|".join(
        (
            str(sample["ego_init_id"]),
            str(sample.get("cell_id", sample.get("source_cell", ""))),
            str(sample["sample_id"]),
        )
    )


def audit_training_data(
    train_jsonl: Path,
    val_jsonl: Path,
    *,
    train_groups: Sequence[int],
    label_horizon: int,
    strict_formal: bool,
) -> dict[str, Any]:
    """Fail closed on leakage or silent sample loss before expensive fitting."""

    expected_train = {int(value) for value in train_groups}
    expected_validation = set(VALIDATION_GROUPS)
    allowed_source_train = set(TRAIN_GROUPS)
    expected_cells = set(COLLECTION_CELLS)
    split_records: dict[str, dict[str, Any]] = {}
    hard_failures: list[str] = []

    for split, path, expected, allowed in (
        ("train", train_jsonl, expected_train, allowed_source_train),
        ("validation", val_jsonl, expected_validation, expected_validation),
    ):
        raw_groups: set[int] = set()
        eligible_groups: set[int] = set()
        eligible_keys: set[str] = set()
        duplicate_keys: list[str] = []
        support_by_group: Counter[int] = Counter()
        cells_by_group: dict[int, set[str]] = defaultdict(set)
        exclusions: Counter[str] = Counter()
        raw_count = 0
        for sample in read_jsonl(str(path)):
            raw_count += 1
            group = int(sample["ego_init_id"])
            raw_groups.add(group)
            if group not in allowed:
                hard_failures.append(f"{split}:unexpected_group:{group}")
            if group not in expected:
                continue
            key = _sample_key(sample)
            if key in eligible_keys:
                duplicate_keys.append(key)
                continue
            if not has_complete_interaction_history(
                sample.get("interaction_sequence_mask") or []
            ):
                exclusions["incomplete_history"] += 1
                continue
            label = masked_local_label(sample, label_horizon)
            if not np.any(label[:, 2]):
                exclusions["no_valid_future"] += 1
                continue
            raster_path = resolve_raster_path(sample)
            if not raster_path or not os.path.exists(raster_path):
                exclusions["missing_raster"] += 1
                continue
            arrays = (
                np.asarray(sample["past_states_local"], dtype=np.float32),
                np.asarray(sample["interaction_sequence"], dtype=np.float32),
                np.asarray(sample["interaction_sequence_mask"], dtype=np.float32),
                label,
            )
            if not all(np.all(np.isfinite(value)) for value in arrays):
                exclusions["non_finite_input_or_label"] += 1
                continue
            eligible_keys.add(key)
            eligible_groups.add(group)
            support_by_group[group] += 1
            cells_by_group[group].add(
                str(sample.get("cell_id", sample.get("source_cell", "")))
            )

        if duplicate_keys:
            hard_failures.append(f"{split}:duplicate_sample_keys:{len(duplicate_keys)}")
        if exclusions["missing_raster"]:
            hard_failures.append(
                f"{split}:missing_rasters:{exclusions['missing_raster']}"
            )
        if exclusions["non_finite_input_or_label"]:
            hard_failures.append(
                f"{split}:non_finite_inputs_or_labels:"
                f"{exclusions['non_finite_input_or_label']}"
            )
        if strict_formal:
            missing_groups = expected - eligible_groups
            if missing_groups:
                hard_failures.append(
                    f"{split}:missing_eligible_groups:{sorted(missing_groups)}"
                )
            for group in sorted(expected & eligible_groups):
                if cells_by_group[group] != expected_cells:
                    hard_failures.append(
                        f"{split}:group_{group}_cell_support:"
                        f"{sorted(cells_by_group[group])}"
                    )
        split_records[split] = {
            "path": str(path.resolve()),
            "raw_samples": raw_count,
            "raw_groups": sorted(raw_groups),
            "expected_eligible_groups": sorted(expected),
            "eligible_groups": sorted(eligible_groups),
            "eligible_samples": len(eligible_keys),
            "eligible_sample_keys": eligible_keys,
            "support_by_group": {
                str(group): support_by_group[group] for group in sorted(support_by_group)
            },
            "cells_by_group": {
                str(group): sorted(cells_by_group[group]) for group in sorted(cells_by_group)
            },
            "exclusions": dict(sorted(exclusions.items())),
        }

    overlap_groups = set(split_records["train"]["eligible_groups"]) & set(
        split_records["validation"]["eligible_groups"]
    )
    overlap_keys = split_records["train"].pop("eligible_sample_keys") & split_records[
        "validation"
    ].pop("eligible_sample_keys")
    if overlap_groups:
        hard_failures.append(f"train_validation_group_overlap:{sorted(overlap_groups)}")
    if overlap_keys:
        hard_failures.append(f"train_validation_sample_overlap:{len(overlap_keys)}")
    payload = {
        "schema_version": "capacity_history_training_data_integrity_v3",
        "status": "pass" if not hard_failures else "fail",
        "formal_mode": strict_formal,
        "hard_failures": sorted(set(hard_failures)),
        "train_validation_group_overlap": sorted(overlap_groups),
        "train_validation_sample_overlap_count": len(overlap_keys),
        "splits": split_records,
    }
    payload["audit_sha256"] = sha256_payload(payload)
    if hard_failures:
        raise ValueError("Training data integrity audit failed: " + "; ".join(payload["hard_failures"]))
    return payload


def load_image(path_value: np.ndarray) -> np.ndarray:
    from prediction_input_contract import load_logged_raster, preprocess_resnet_raster

    value = path_value.item() if hasattr(path_value, "item") else path_value
    path = value.decode("utf-8") if isinstance(value, bytes) else str(value)
    raster = load_logged_raster(path)
    if tuple(raster.shape[:2]) != (500, 500):
        import cv2

        raster = cv2.resize(raster, (500, 500), interpolation=cv2.INTER_LINEAR)
    return preprocess_resnet_raster(raster)[0].astype(np.float32)


def make_dataset(
    jsonl: Path,
    *,
    spec: Mapping[str, Any],
    label_horizon: int,
    batch_size: int,
    shuffle: bool,
    shuffle_buffer: int,
    maximum: int | None,
    expected_samples: int | None = None,
):
    if tf is None:
        raise RuntimeError("TensorFlow is required for V3 training")
    signature = (
        tf.TensorSpec((), tf.string),
        tf.TensorSpec((None, 4), tf.float32),
        tf.TensorSpec((6, 12), tf.float32),
        tf.TensorSpec((6,), tf.float32),
        tf.TensorSpec((label_horizon, 3), tf.float32),
    )
    allowed = set(spec["train_groups"]) if jsonl.name == "train.jsonl" else None
    dataset = tf.data.Dataset.from_generator(
        lambda: sample_generator(
            jsonl,
            family=spec["family"],
            history_horizon_s=spec["history_horizon_s"],
            label_horizon=label_horizon,
            allowed_train_groups=allowed,
            maximum=maximum,
        ),
        output_signature=signature,
    )
    if shuffle:
        dataset = dataset.shuffle(
            shuffle_buffer,
            seed=int(spec["seed"]),
            reshuffle_each_iteration=True,
        )

    def prepare(path, past, sequence, mask, label):
        image = tf.numpy_function(load_image, [path], tf.float32)
        image.set_shape((500, 500, 3))
        inputs = (image, past) if spec["family"] == "head" else (image, past, sequence, mask)
        return inputs, label

    options = tf.data.Options()
    options.experimental_deterministic = True
    prepared = (
        dataset.with_options(options)
        .map(prepare, num_parallel_calls=tf.data.AUTOTUNE, deterministic=True)
        .batch(batch_size, drop_remainder=False)
    )
    if expected_samples is not None:
        if expected_samples < 1:
            raise ValueError("Expected dataset sample count must be positive")
        prepared = prepared.apply(
            tf.data.experimental.assert_cardinality(
                int(math.ceil(expected_samples / batch_size))
            )
        )
    return prepared.prefetch(tf.data.AUTOTUNE)


def build_model(spec: Mapping[str, Any], merged: Path, base_path: Path, anchors: np.ndarray):
    if tf is None:
        raise RuntimeError("TensorFlow is required for V3 training")
    from interaction_adapter_v2 import load_normalization
    from interaction_adapter_v3 import (
        build_capacity_head_adapter,
        build_capacity_interaction_adapter,
    )

    base = tf.keras.models.load_model(base_path, compile=False)
    if spec["family"] == "head":
        return build_capacity_head_adapter(base, spec["capacity_tier"])
    normalization = load_normalization(merged / "interaction_normalization_train.json")
    return build_capacity_interaction_adapter(
        base,
        anchors,
        normalization,
        spec["family"],
        spec["capacity_tier"],
        float(spec["history_horizon_s"]),
        dropout=ENCODER_DROPOUT,
    )


def read_history(path: Path) -> dict[str, list[float]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[str, list[float]] = {}
    for row in rows:
        for key, value in row.items():
            if key == "epoch" or value in (None, ""):
                continue
            result.setdefault(key, []).append(float(value))
    return result


def make_optimizer(learning_rate: float):
    if tf is None:
        raise RuntimeError("TensorFlow is required for V3 training")
    return tf.keras.optimizers.AdamW(
        learning_rate=float(learning_rate),
        weight_decay=WEIGHT_DECAY,
        clipnorm=GRADIENT_CLIP_NORM,
    )


def make_finite_weights_callback():
    if tf is None:
        raise RuntimeError("TensorFlow is required for V3 training")

    class FiniteWeights(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            for variable in self.model.trainable_variables:
                if not bool(tf.reduce_all(tf.math.is_finite(variable)).numpy()):
                    raise RuntimeError(
                        f"Non-finite trainable weight after epoch {epoch + 1}: "
                        f"{variable.name}"
                    )

    return FiniteWeights()


def evaluate_rollout_macro_nll(
    model,
    validation_dataset,
    validation_samples: list[dict[str, Any]],
    anchors: np.ndarray,
    label_horizon: int,
) -> float:
    from evaluate_multipath_model_on_dataset import evaluate_decoded
    from multipath_gmm_utils import decode_multipath_raw

    raw_batches = []
    label_batches = []
    for inputs, labels in validation_dataset:
        raw_batches.append(np.asarray(model.predict_on_batch(inputs)))
        label_batches.append(np.asarray(labels))
    if not raw_batches:
        raise RuntimeError("Validation dataset emitted no batches")
    raw = np.concatenate(raw_batches, axis=0)
    labels = np.concatenate(label_batches, axis=0)
    if len(raw) != len(validation_samples):
        raise RuntimeError("Validation metadata/prediction order mismatch")
    decoded = decode_multipath_raw(raw, anchors)
    metrics = evaluate_decoded(
        decoded,
        labels,
        validation_samples,
        label_horizon,
        temperature=1.0,
        covariance_scale=1.0,
    )
    score = float(
        metrics["rollout_aggregation"]["macro_mean"]
        ["trajectory_mixture_NLL_per_step_mean"]
    )
    if not np.isfinite(score):
        raise RuntimeError("Non-finite validation rollout-macro NLL")
    return score


def make_rollout_macro_checkpoint(
    *,
    validation_dataset,
    validation_samples: list[dict[str, Any]],
    anchors: np.ndarray,
    label_horizon: int,
    best_weights: Path,
    existing_history: Mapping[str, list[float]],
):
    """Checkpoint on the preregistered rollout-macro mixture NLL.

    The ordinary Keras validation loss weights every logged window equally.
    That is useful for optimisation diagnostics but is not the experimental
    unit, so it must not choose the retained checkpoint.
    """

    if tf is None:
        raise RuntimeError("TensorFlow is required for checkpoint validation")
    previous = existing_history.get("val_rollout_macro_nll", [])
    if best_weights.exists() != bool(previous):
        raise ValueError(
            "Resume checkpoint/history mismatch for rollout-macro selection; "
            "refusing to silently reset the best score"
        )

    class RolloutMacroCheckpoint(tf.keras.callbacks.Callback):
        def __init__(self):
            super().__init__()
            self.best = min(previous) if previous else float("inf")

        def on_epoch_end(self, epoch, logs=None):
            score = evaluate_rollout_macro_nll(
                self.model,
                validation_dataset,
                validation_samples,
                anchors,
                label_horizon,
            )
            if logs is not None:
                logs["val_rollout_macro_nll"] = score
            if score < self.best:
                self.best = score
                self.model.save_weights(str(best_weights), overwrite=True)

    return RolloutMacroCheckpoint()


def artifact_hash(path: Path) -> dict[str, Any]:
    if path.is_file():
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total_bytes = 0
    for item in files:
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        total_bytes += item.stat().st_size
    return {
        "path": str(path),
        "files": len(files),
        "bytes": total_bytes,
        "sha256_tree": digest.hexdigest(),
    }


def main() -> None:  # pragma: no cover - full execution belongs on the GPU server.
    args = parse_args()
    if tf is None:
        raise RuntimeError("TensorFlow is not installed; run this trainer in the project server image")
    if args.batch_size < 1 or args.label_horizon < 1 or args.shuffle_buffer < 1:
        raise ValueError("Batch size, label horizon, and shuffle buffer must be positive")
    protocol_report = validate_protocol(load_protocol())
    spec, _ = load_run_spec(args.run_manifest.resolve(), args.run_id)
    epochs = int(args.epochs or spec["epochs"])
    random.seed(int(spec["seed"]))
    np.random.seed(int(spec["seed"]))
    tf.keras.utils.set_random_seed(int(spec["seed"]))
    tf.config.experimental.enable_op_determinism()

    merged = args.merged_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    completion_path = output / "TRAINING_COMPLETE.json"

    for gate_name in ("DAY7_COMPLETE.json", "DAY7_MODEL_IMPLEMENTATION_COMPLETE.json"):
        gate = json.loads((merged / gate_name).read_text(encoding="utf-8"))
        if gate.get("status") != "pass":
            raise ValueError(f"Required dataset gate failed: {gate_name}")
    anchors = np.load(args.anchors.resolve()).astype(np.float32)
    if anchors.shape[1] < args.label_horizon:
        raise ValueError("Anchor horizon is shorter than label horizon")

    config = semantic_run_config(
        spec=spec,
        manifest_path=args.run_manifest,
        merged_dir=merged,
        base_model=args.base_model,
        anchors=args.anchors,
        epochs=epochs,
        batch_size=args.batch_size,
        label_horizon=args.label_horizon,
        shuffle_buffer=args.shuffle_buffer,
        max_train_samples=args.max_train_samples,
        max_val_samples=args.max_val_samples,
    )
    config["protocol_validation"] = protocol_report
    config_path = output / "run_config.json"
    if config_path.exists():
        assert_resume_compatible(
            json.loads(config_path.read_text(encoding="utf-8")), config
        )
    else:
        atomic_json(config_path, config)
    if completion_path.exists():
        from capacity_study_v3_execute import completion_is_valid

        if completion_is_valid(completion_path, spec):
            print(json.dumps({"status": "skip_complete", "run_id": args.run_id}))
            return
        raise ValueError(
            "Existing training completion is stale or invalid; refusing to resume into "
            "a completed output directory. Preserve it for audit and use a clean run directory."
        )

    generator_common = {
        "family": spec["family"],
        "history_horizon_s": spec["history_horizon_s"],
        "label_horizon": args.label_horizon,
    }
    train_jsonl, val_jsonl = merged / "train.jsonl", merged / "val.jsonl"
    formal_run = args.max_train_samples is None and args.max_val_samples is None
    data_integrity = audit_training_data(
        train_jsonl,
        val_jsonl,
        train_groups=spec["train_groups"],
        label_horizon=args.label_horizon,
        strict_formal=formal_run,
    )
    data_integrity_path = output / "training_data_integrity.json"
    atomic_json(data_integrity_path, data_integrity)
    train_count = count_samples(
        jsonl=train_jsonl,
        allowed_train_groups=set(spec["train_groups"]),
        maximum=args.max_train_samples,
        **generator_common,
    )
    val_count = count_samples(
        jsonl=val_jsonl,
        allowed_train_groups=None,
        maximum=args.max_val_samples,
        **generator_common,
    )
    if train_count == 0 or val_count == 0:
        raise ValueError(f"No usable complete-history samples: train={train_count}, val={val_count}")

    model, capacity_config = build_model(spec, merged, args.base_model.resolve(), anchors)
    from interaction_adapter_v2 import masked_multipath_loss, masked_top_mode_ade, parameter_report

    parameters = parameter_report(model)
    if parameters["trainable_parameters"] != capacity_config.trainable_parameters:
        raise ValueError(
            "Keras trainable count disagrees with frozen capacity configuration: "
            f"{parameters['trainable_parameters']} != {capacity_config.trainable_parameters}"
        )
    model.compile(
        optimizer=make_optimizer(float(spec["learning_rate"])),
        loss=masked_multipath_loss(anchors, args.label_horizon),
        metrics=[masked_top_mode_ade(anchors, args.label_horizon)],
    )
    train_ds = make_dataset(
        train_jsonl,
        spec=spec,
        label_horizon=args.label_horizon,
        batch_size=args.batch_size,
        shuffle=True,
        shuffle_buffer=args.shuffle_buffer,
        maximum=args.max_train_samples,
        expected_samples=train_count,
    )
    val_ds = make_dataset(
        val_jsonl,
        spec=spec,
        label_horizon=args.label_horizon,
        batch_size=args.batch_size,
        shuffle=False,
        shuffle_buffer=args.shuffle_buffer,
        maximum=args.max_val_samples,
        expected_samples=val_count,
    )
    best_weights = output / "best.weights.h5"
    history_csv = output / "history.csv"
    backup_dir = output / "resume_backup"
    history_before_resume = read_history(history_csv)
    validation_samples = validation_sample_metadata(
        val_jsonl,
        label_horizon=args.label_horizon,
        maximum=args.max_val_samples,
    )
    initial_weights = [np.asarray(value.numpy()).copy() for value in model.trainable_weights]
    initial_rollout_macro_nll = evaluate_rollout_macro_nll(
        model,
        val_ds,
        validation_samples,
        anchors,
        args.label_horizon,
    )
    initial_trainable_l2 = float(
        np.sqrt(sum(float(np.sum(np.square(value))) for value in initial_weights))
    )
    training_start = {
        "schema_version": "capacity_history_training_start_v3",
        "run_id": args.run_id,
        "run_config_sha256": sha256_file(config_path),
        "initial_validation_rollout_macro_nll": initial_rollout_macro_nll,
        "initial_trainable_l2": initial_trainable_l2,
    }
    training_start["record_sha256"] = sha256_payload(training_start)
    training_start_path = output / "training_start.json"
    if training_start_path.exists():
        existing_start = json.loads(training_start_path.read_text(encoding="utf-8"))
        comparable_existing = dict(existing_start)
        comparable_requested = dict(training_start)
        old_score = float(comparable_existing.pop("initial_validation_rollout_macro_nll"))
        new_score = float(comparable_requested.pop("initial_validation_rollout_macro_nll"))
        comparable_existing.pop("record_sha256", None)
        comparable_requested.pop("record_sha256", None)
        if comparable_existing != comparable_requested or not np.isclose(
            old_score, new_score, rtol=1.0e-7, atol=1.0e-7
        ):
            raise ValueError("Resume initial-model health record drift detected")
    else:
        atomic_json(training_start_path, training_start)
    rollout_macro_checkpoint = make_rollout_macro_checkpoint(
        validation_dataset=val_ds,
        validation_samples=validation_samples,
        anchors=anchors,
        label_horizon=args.label_horizon,
        best_weights=best_weights,
        existing_history=history_before_resume,
    )
    callbacks = [
        tf.keras.callbacks.BackupAndRestore(
            backup_dir=str(backup_dir), save_freq="epoch", delete_checkpoint=False
        ),
        make_finite_weights_callback(),
        rollout_macro_checkpoint,
        tf.keras.callbacks.EarlyStopping(
            monitor="val_rollout_macro_nll",
            mode="min",
            patience=EARLY_STOPPING_PATIENCE,
            verbose=1,
        ),
        tf.keras.callbacks.CSVLogger(str(history_csv), append=history_csv.exists()),
        tf.keras.callbacks.TerminateOnNaN(),
    ]
    started = time.perf_counter()
    model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=epochs,
        callbacks=callbacks,
        verbose=2,
    )
    elapsed = time.perf_counter() - started
    if not best_weights.exists():
        raise RuntimeError("Training ended without a best validation checkpoint")
    model.load_weights(str(best_weights))
    for variable in model.trainable_variables:
        if not bool(tf.reduce_all(tf.math.is_finite(variable)).numpy()):
            raise RuntimeError(f"Best checkpoint contains non-finite weight: {variable.name}")
    best_model = output / "best_model"
    staging = output / "best_model.staging"
    if staging.exists():
        shutil.rmtree(staging)
    model.save(staging)
    if best_model.exists():
        shutil.rmtree(best_model)
    os.replace(staging, best_model)
    history = read_history(history_csv)
    val_losses = history.get("val_rollout_macro_nll", [])
    if not val_losses or not np.all(np.isfinite(val_losses)):
        raise RuntimeError("Validation history is missing or non-finite")
    best_epoch = int(np.argmin(val_losses)) + 1
    train_losses = history.get("loss", [])
    keras_val_losses = history.get("val_loss", [])
    if len(train_losses) != len(val_losses) or len(keras_val_losses) != len(val_losses):
        raise RuntimeError("Training/validation histories are incomplete or misaligned")
    if not np.all(np.isfinite(train_losses)) or not np.all(np.isfinite(keras_val_losses)):
        raise RuntimeError("Training history contains non-finite optimisation losses")
    update_squared = 0.0
    for initial, trained in zip(initial_weights, model.trainable_weights):
        update_squared += float(np.sum(np.square(np.asarray(trained.numpy()) - initial)))
    update_l2 = float(np.sqrt(update_squared))
    relative_update_l2 = update_l2 / max(initial_trainable_l2, 1.0e-12)
    best_score = float(val_losses[best_epoch - 1])
    warnings = []
    if best_score >= initial_rollout_macro_nll - 1.0e-6:
        warnings.append("no_validation_improvement_over_zero_residual_initialization")
    if relative_update_l2 <= 1.0e-8:
        warnings.append("negligible_trainable_weight_update")
    if best_epoch > epochs - 5:
        warnings.append("best_checkpoint_at_preregistered_convergence_boundary")
    training_health = {
        "schema_version": "capacity_history_training_health_v3",
        "status": "pass",
        "hard_checks_pass": True,
        "formal_run": formal_run,
        "optimizer": {
            "name": "adamw",
            "learning_rate": float(spec["learning_rate"]),
            "weight_decay": WEIGHT_DECAY,
            "gradient_clip_norm": GRADIENT_CLIP_NORM,
            "encoder_dropout": ENCODER_DROPOUT if spec["family"] != "head" else None,
        },
        "initial_validation_rollout_macro_nll": initial_rollout_macro_nll,
        "best_validation_rollout_macro_nll": best_score,
        "validation_improvement": initial_rollout_macro_nll - best_score,
        "best_epoch": best_epoch,
        "epochs_completed": len(val_losses),
        "epochs_allowed": epochs,
        "post_best_epochs_observed": len(val_losses) - best_epoch,
        "best_epoch_train_loss": float(train_losses[best_epoch - 1]),
        "best_epoch_window_weighted_val_loss": float(
            keras_val_losses[best_epoch - 1]
        ),
        "best_epoch_window_weighted_generalization_gap": float(
            keras_val_losses[best_epoch - 1] - train_losses[best_epoch - 1]
        ),
        "initial_trainable_l2": initial_trainable_l2,
        "best_checkpoint_update_l2": update_l2,
        "relative_trainable_update_l2": relative_update_l2,
        "warnings": warnings,
        "warning_policy": (
            "Warnings remain visible and do not delete adverse/null scientific results; "
            "formal selection is blocked only by hard integrity, numerical, or convergence gates."
        ),
    }
    training_health["health_sha256"] = sha256_payload(training_health)
    training_health_path = output / "training_health.json"
    atomic_json(training_health_path, training_health)
    completion = {
        "status": "pass" if formal_run else "smoke_only",
        "formal_run": formal_run,
        "run_id": args.run_id,
        "model_cell_id": spec["model_cell_id"],
        "family": spec["family"],
        "capacity_tier": spec["capacity_tier"],
        "history_horizon_s": spec["history_horizon_s"],
        "learning_rate": spec["learning_rate"],
        "seed": spec["seed"],
        "data_fraction": spec["data_fraction"],
        "train_groups": spec["train_groups"],
        "train_samples": train_count,
        "validation_samples": val_count,
        "epochs_allowed": epochs,
        "epochs_completed": len(val_losses),
        "best_epoch": best_epoch,
        "rollout_macro_nll": best_score,
        "checkpoint_selection_metric": "validation_rollout_macro_trajectory_mixture_NLL_per_step",
        "training_wall_time_s": elapsed,
        "tensorflow_version": tf.__version__,
        "visible_devices": [device.name for device in tf.config.list_physical_devices()],
        "parameters": parameters,
        "capacity_config": capacity_config.__dict__,
        "best_model": artifact_hash(best_model),
        "best_weights": artifact_hash(best_weights),
        "history_csv": artifact_hash(history_csv),
        "run_config": artifact_hash(config_path),
        "training_start": artifact_hash(training_start_path),
        "training_data_integrity": artifact_hash(data_integrity_path),
        "training_health": artifact_hash(training_health_path),
        "dataset_artifact_sha256": config["dataset_artifact_sha256"],
    }
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    atomic_json(completion_path, completion)
    print(json.dumps(completion, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
