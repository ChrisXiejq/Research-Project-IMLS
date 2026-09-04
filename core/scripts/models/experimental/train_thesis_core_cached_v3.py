#!/usr/bin/env python3
"""Train one thesis-core cell from hash-bound frozen-backbone features."""

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
import json
import os
import random
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import tensorflow as tf

from build_thesis_core_feature_cache_v3 import validate_cache
from capacity_study_v3_protocol import (
    CORE_EPOCHS,
    EARLY_STOPPING_PATIENCE,
    ENCODER_DROPOUT,
    GRADIENT_CLIP_NORM,
    THESIS_CORE_LEARNING_RATE,
    WEIGHT_DECAY,
    atomic_json,
    sha256_file,
    sha256_payload,
)
from interaction_adapter_v2 import (
    masked_multipath_loss,
    masked_top_mode_ade,
    parameter_report,
)
from interaction_adapter_v3 import (
    build_cached_capacity_interaction_adapter,
)
from prediction_dataset_utils import read_jsonl, resolve_raster_path
from prepare_thesis_core_v3_dataset import load_thesis_normalization
from thesis_core_v3_runs import thesis_core_manifest, validate_thesis_core_manifest
from training_epoch_integrity_v4 import (
    inspect_epoch_artifacts,
    restored_early_stopping_state,
)
from train_prediction_model_v3 import (
    artifact_hash,
    load_image,
    make_finite_weights_callback,
    make_optimizer,
    make_rollout_macro_checkpoint,
    read_history,
    validation_sample_metadata,
)


TRAINING_SOURCE_FILES = (
    "build_thesis_core_feature_cache_v3.py",
    "capacity_study_v3_protocol.py",
    "evaluate_multipath_model_on_dataset.py",
    "interaction_adapter_v2.py",
    "interaction_adapter_v3.py",
    "prediction_dataset_utils.py",
    "prepare_thesis_core_v3_dataset.py",
    "thesis_core_v3_runs.py",
    "train_prediction_model_v3.py",
    "train_thesis_core_cached_v3.py",
    "training_epoch_integrity_v4.py",
)


class HistoryRestoredEarlyStopping(tf.keras.callbacks.EarlyStopping):
    """EarlyStopping whose best/wait state survives process boundaries."""

    def __init__(self, prior_scores: list[float]) -> None:
        super().__init__(
            monitor="val_rollout_macro_nll",
            mode="min",
            patience=EARLY_STOPPING_PATIENCE,
        )
        self.restored_state = restored_early_stopping_state(
            prior_scores, patience=EARLY_STOPPING_PATIENCE
        )

    def on_train_begin(self, logs=None) -> None:
        super().on_train_begin(logs)
        if self.restored_state["best_epoch"] is None:
            return
        self.best = float(self.restored_state["best"])
        self.wait = int(self.restored_state["consecutive_non_improving_epochs"])
        self.best_epoch = int(self.restored_state["best_epoch"]) - 1


def training_source_sha256() -> dict[str, str]:
    directory = Path(__file__).resolve().parent
    return {name: sha256_file(directory / name) for name in TRAINING_SOURCE_FILES}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-manifest", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=64)
    return parser.parse_args()


def _run_spec(manifest_path: Path, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_thesis_core_manifest(payload)
    matches = [row for row in payload["runs"] if row["run_id"] == run_id]
    if len(matches) != 1:
        raise ValueError(f"Run id must resolve exactly once: {run_id}")
    return matches[0], payload


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as handle:
        return {name: np.asarray(handle[name]) for name in handle.files}


def _cached_head_model(base: tf.keras.Model, feature_dim: int) -> tuple[tf.keras.Model, str]:
    final = next(
        (layer for layer in reversed(base.layers) if isinstance(layer, tf.keras.layers.Dense)),
        None,
    )
    if final is None:
        raise ValueError("Base model has no final Dense layer")
    feature = tf.keras.Input((feature_dim,), name="cached_head_features")
    cloned = tf.keras.layers.Dense.from_config(final.get_config())
    # ``base.trainable = False`` propagates to its final Dense and therefore to
    # the serialized config.  B1 is specifically the task-adapted final head.
    cloned.trainable = True
    output = cloned(feature)
    model = tf.keras.Model(feature, output, name="cached_multipath_head_large_v3")
    cloned.set_weights(final.get_weights())
    return model, final.name


def build_cached_model(
    spec: Mapping[str, Any],
    base: tf.keras.Model,
    cache: Mapping[str, np.ndarray],
    anchors: np.ndarray,
    normalization: Mapping[str, Any],
) -> tuple[tf.keras.Model, str | None]:
    if spec["family"] == "head":
        if spec["capacity_tier"] != "large":
            raise ValueError("Thesis-core head execution permits large B1 only")
        return _cached_head_model(base, int(cache["head_features"].shape[1]))
    model, _ = build_cached_capacity_interaction_adapter(
        int(cache["base_raw"].shape[1]),
        anchors,
        normalization,
        spec["family"],
        spec["capacity_tier"],
        float(spec["history_horizon_s"]),
        dropout=ENCODER_DROPOUT,
    )
    return model, None


def cached_inputs(spec: Mapping[str, Any], arrays: Mapping[str, np.ndarray]):
    if spec["family"] == "head":
        return arrays["head_features"]
    return (arrays["base_raw"], arrays["sequence"], arrays["mask"])


def make_dataset(
    spec: Mapping[str, Any], arrays: Mapping[str, np.ndarray], batch_size: int, *, shuffle: bool
):
    inputs = cached_inputs(spec, arrays)
    dataset = tf.data.Dataset.from_tensor_slices((inputs, arrays["labels"]))
    if shuffle:
        dataset = dataset.shuffle(
            len(arrays["labels"]), seed=int(spec["seed"]), reshuffle_each_iteration=True
        )
    options = tf.data.Options()
    options.experimental_deterministic = True
    return dataset.with_options(options).batch(batch_size).prefetch(tf.data.AUTOTUNE)


def gradient_audit(
    model: tf.keras.Model,
    inputs: Any,
    labels: np.ndarray,
    loss_function,
) -> dict[str, Any]:
    variables = list(model.trainable_variables)
    if not variables:
        raise ValueError("Model has no trainable variables")
    with tf.GradientTape() as tape:
        predictions = model(inputs, training=True)
        loss = tf.reduce_mean(loss_function(labels, predictions))
    gradients = tape.gradient(loss, variables)
    present = [value for value in gradients if value is not None]
    if len(present) != len(variables):
        raise ValueError("Disconnected trainable variable detected by gradient audit")
    if not all(bool(tf.reduce_all(tf.math.is_finite(value)).numpy()) for value in present):
        raise ValueError("Non-finite gradient detected before training")
    global_norm = float(tf.linalg.global_norm(present).numpy())
    if not np.isfinite(global_norm) or global_norm <= 1.0e-12:
        raise ValueError(f"Zero or invalid pre-training gradient norm: {global_norm}")
    return {
        "status": "pass",
        "trainable_tensors": len(variables),
        "gradient_global_norm": global_norm,
    }


def reconstruct_full_model(
    spec: Mapping[str, Any],
    base_model_path: Path,
    anchors: np.ndarray,
    normalization: Mapping[str, Any],
    cached: tf.keras.Model,
) -> tf.keras.Model:
    base = tf.keras.models.load_model(base_model_path, compile=False)
    base.trainable = False
    if spec["family"] == "head":
        final = next(
            (layer for layer in reversed(base.layers) if isinstance(layer, tf.keras.layers.Dense)),
            None,
        )
        if final is None:
            raise ValueError("Base model has no final Dense layer")
        output = cached(final.input)
        full = tf.keras.Model(base.inputs, output, name="thesis_core_full_head_v3")
    else:
        sequence = tf.keras.Input((6, 12), name="interaction_sequence")
        mask = tf.keras.Input((6,), name="interaction_sequence_mask")
        output = cached((base.output, sequence, mask))
        full = tf.keras.Model(
            [*base.inputs, sequence, mask],
            output,
            name=f"thesis_core_full_{spec['family']}_v3",
        )
    return full


def parity_audit(
    spec: Mapping[str, Any],
    cached: tf.keras.Model,
    full: tf.keras.Model,
    arrays: Mapping[str, np.ndarray],
    selection_jsonl: Path,
    *,
    count: int = 32,
) -> dict[str, Any]:
    rows = list(read_jsonl(str(selection_jsonl)))[:count]
    count = min(count, len(rows), len(arrays["labels"]))
    images = np.stack(
        [load_image(np.asarray(str(resolve_raster_path(row)).encode("utf-8"))) for row in rows[:count]]
    )
    past = np.stack([np.asarray(row["past_states_local"], dtype=np.float32) for row in rows[:count]])
    if spec["family"] == "head":
        full_inputs = [images, past]
        cache_inputs = arrays["head_features"][:count]
    else:
        full_inputs = [images, past, arrays["sequence"][:count], arrays["mask"][:count]]
        cache_inputs = [
            arrays["base_raw"][:count], arrays["sequence"][:count], arrays["mask"][:count]
        ]
    expected = np.asarray(cached.predict_on_batch(cache_inputs))
    actual = np.asarray(full.predict_on_batch(full_inputs))
    difference = np.abs(expected - actual)
    report = {
        "schema_version": "capacity_history_cached_full_parity_v3",
        "status": "pass" if np.allclose(expected, actual, rtol=1.0e-5, atol=1.0e-5) else "fail",
        "samples": count,
        "rtol": 1.0e-5,
        "atol": 1.0e-5,
        "maximum_absolute_error": float(np.max(difference)),
        "mean_absolute_error": float(np.mean(difference)),
    }
    report["parity_sha256"] = sha256_payload(report)
    if report["status"] != "pass":
        raise ValueError(f"Cached/full parity failed: {report}")
    return report


def main() -> None:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("Batch size must be positive")
    spec, manifest = _run_spec(args.run_manifest, args.run_id)
    if float(spec["learning_rate"]) != THESIS_CORE_LEARNING_RATE:
        raise ValueError("Thesis-core learning rate drift")
    cache_audit = validate_cache(args.cache_dir, args.dataset_dir, args.base_model)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    config = {
        "schema_version": "capacity_history_thesis_core_training_config_v4_masked",
        "run_spec": spec,
        "run_manifest": str(args.run_manifest.resolve()),
        "run_manifest_sha256": sha256_file(args.run_manifest),
        "dataset_complete_sha256": sha256_file(args.dataset_dir / "THESIS_CORE_DATASET_COMPLETE.json"),
        "cache_complete_sha256": sha256_file(args.cache_dir / "CACHE_COMPLETE.json"),
        "base_model_artifact": artifact_hash(args.base_model),
        "anchors_sha256": sha256_file(args.anchors),
        "source_sha256": training_source_sha256(),
        "batch_size": args.batch_size,
        "epochs": CORE_EPOCHS,
        "patience": EARLY_STOPPING_PATIENCE,
        "early_stopping_state_restoration": (
            "validation_history_global_best_and_consecutive_wait_v4"
        ),
        "future_validity_contract": "future_valid_mask_fail_closed_v4",
        "checkpoint_selection_metric": (
            "validation_rollout_macro_masked_trajectory_mixture_NLL_per_valid_step"
        ),
        "optimization": {
            "optimizer": "adamw",
            "learning_rate": THESIS_CORE_LEARNING_RATE,
            "weight_decay": WEIGHT_DECAY,
            "gradient_clip_norm": GRADIENT_CLIP_NORM,
            "encoder_dropout": ENCODER_DROPOUT,
        },
    }
    config_path = output / "run_config.json"
    if config_path.exists():
        if json.loads(config_path.read_text(encoding="utf-8")) != config:
            raise ValueError("Cached trainer resume semantic config drift")
    else:
        atomic_json(config_path, config)
    os.environ["PYTHONHASHSEED"] = str(spec["seed"])
    random.seed(int(spec["seed"]))
    np.random.seed(int(spec["seed"]))
    tf.keras.utils.set_random_seed(int(spec["seed"]))
    tf.config.experimental.enable_op_determinism()

    fit = _load_npz(args.cache_dir / "fit.npz")
    selection = _load_npz(args.cache_dir / "selection.npz")
    anchors = np.load(args.anchors)
    normalization = load_thesis_normalization(
        args.dataset_dir / "interaction_normalization_fit.json"
    )
    base = tf.keras.models.load_model(args.base_model, compile=False)
    base.trainable = False
    model, _ = build_cached_model(spec, base, fit, anchors, normalization)
    parameters = parameter_report(model)
    loss_function = masked_multipath_loss(anchors, 10)
    model.compile(
        optimizer=make_optimizer(THESIS_CORE_LEARNING_RATE),
        loss=loss_function,
        metrics=[masked_top_mode_ade(anchors, 10)],
    )
    audit_count = min(args.batch_size, len(fit["labels"]))
    audit_inputs = cached_inputs(spec, fit)
    if isinstance(audit_inputs, (list, tuple)):
        audit_inputs = tuple(value[:audit_count] for value in audit_inputs)
    else:
        audit_inputs = audit_inputs[:audit_count]
    gradients = gradient_audit(
        model, audit_inputs, fit["labels"][:audit_count], loss_function
    )
    initial_trainable_weights = [np.asarray(value.numpy()).copy() for value in model.trainable_weights]
    fit_ds = make_dataset(spec, fit, args.batch_size, shuffle=True)
    selection_ds = make_dataset(spec, selection, args.batch_size, shuffle=False)
    metadata = validation_sample_metadata(
        args.dataset_dir / "selection.jsonl", label_horizon=10, maximum=None
    )
    cached_weights = output / "cached_best.weights.h5"
    history_csv = output / "history.csv"
    backup_dir = output / "resume_backup"
    epoch_checkpoint_dir = output / "epoch_checkpoints"
    epoch_checkpoint_dir.mkdir(parents=True, exist_ok=True)
    existing_history = read_history(history_csv)
    if history_csv.exists() or any(epoch_checkpoint_dir.glob("epoch_*.weights.h5")):
        epoch_integrity_before = inspect_epoch_artifacts(
            history_csv,
            epoch_checkpoint_dir,
            backup_dir=backup_dir,
            validate_hdf5=True,
        )
        if epoch_integrity_before["status"] != "pass":
            raise ValueError(
                "Pre-training epoch recovery integrity failed: "
                f"{epoch_integrity_before['errors']}"
            )
    prior_scores = list(existing_history.get("val_rollout_macro_nll", []))
    early_stopping_state = restored_early_stopping_state(
        prior_scores, patience=EARLY_STOPPING_PATIENCE
    )
    rollout_callback = make_rollout_macro_checkpoint(
        validation_dataset=selection_ds,
        validation_samples=metadata,
        anchors=anchors,
        label_horizon=10,
        best_weights=cached_weights,
        existing_history=existing_history,
    )
    callbacks = [
        tf.keras.callbacks.BackupAndRestore(
            backup_dir=str(backup_dir), save_freq="epoch", delete_checkpoint=False
        ),
        make_finite_weights_callback(),
        rollout_callback,
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(epoch_checkpoint_dir / "epoch_{epoch:03d}.weights.h5"),
            save_weights_only=True,
            save_freq="epoch",
            verbose=0,
        ),
        HistoryRestoredEarlyStopping(prior_scores),
        tf.keras.callbacks.CSVLogger(str(history_csv), append=history_csv.exists()),
        tf.keras.callbacks.TerminateOnNaN(),
    ]
    started = time.perf_counter()
    if early_stopping_state["stop_already_reached"]:
        model.load_weights(cached_weights)
    else:
        model.fit(
            fit_ds,
            validation_data=selection_ds,
            epochs=CORE_EPOCHS,
            callbacks=callbacks,
            verbose=2,
        )
    wall_time = time.perf_counter() - started
    model.load_weights(cached_weights)
    maximum_weight_change = max(
        float(np.max(np.abs(np.asarray(value.numpy()) - initial)))
        for value, initial in zip(model.trainable_weights, initial_trainable_weights)
    )
    if not np.isfinite(maximum_weight_change) or maximum_weight_change <= 1.0e-10:
        raise ValueError(f"Training did not update any trainable weight: {maximum_weight_change}")
    history = read_history(history_csv)
    scores = history.get("val_rollout_macro_nll", [])
    if not scores or not np.all(np.isfinite(scores)):
        raise ValueError("Missing or non-finite selection history")
    epoch_checkpoints = sorted(epoch_checkpoint_dir.glob("epoch_*.weights.h5"))
    epoch_integrity_after = inspect_epoch_artifacts(
        history_csv,
        epoch_checkpoint_dir,
        backup_dir=backup_dir,
        validate_hdf5=True,
    )
    if epoch_integrity_after["status"] != "pass":
        raise ValueError(
            "Post-training epoch recovery integrity failed: "
            f"{epoch_integrity_after['errors']}"
        )
    if not backup_dir.exists():
        raise ValueError("Epoch recovery checkpoint is missing after training")
    best_epoch = int(np.argmin(scores)) + 1
    # Rebuild a clean inference graph from the selected checkpoint.  Reusing a
    # model that has been compiled/traced for training can change Transformer
    # graph fusion when it is nested inside the full model, despite identical
    # weights.  The deployment artifact must be validated in its actual fresh
    # inference form.
    inference_cached, _ = build_cached_model(spec, base, selection, anchors, normalization)
    inference_cached.load_weights(cached_weights)
    full = reconstruct_full_model(
        spec, args.base_model, anchors, normalization, inference_cached
    )
    parity = parity_audit(
        spec,
        inference_cached,
        full,
        selection,
        args.dataset_dir / "selection.jsonl",
        count=int(cache_audit["batch_size"]),
    )
    parity_path = output / "cached_full_parity.json"
    atomic_json(parity_path, parity)
    full_weights = output / "best.weights.h5"
    full.save_weights(full_weights)
    best_model = output / "best_model"
    staging = output / "best_model.staging"
    if staging.exists():
        shutil.rmtree(staging)
    full.save(staging)
    if best_model.exists():
        shutil.rmtree(best_model)
    os.replace(staging, best_model)
    parameter_path = output / "parameters.json"
    atomic_json(
        parameter_path,
        {"cached_trainable": parameters, "reconstructed_full": parameter_report(full)},
    )
    health = {
        "schema_version": "capacity_history_thesis_core_training_health_v4_masked",
        "status": "pass",
        "hard_checks_pass": True,
        "run_id": args.run_id,
        "epochs_completed": len(scores),
        "epochs_allowed": CORE_EPOCHS,
        "best_epoch": best_epoch,
        "boundary_limited": best_epoch > CORE_EPOCHS - 5,
        "training_wall_time_s": wall_time,
        "optimizer": config["optimization"],
        "gradient_audit": gradients,
        "maximum_trainable_weight_change": maximum_weight_change,
        "fit_samples": int(len(fit["labels"])),
        "selection_samples": int(len(selection["labels"])),
        "future_validity_contract": "future_valid_mask_fail_closed_v4",
        "per_epoch_checkpoints": len(epoch_checkpoints),
        "epoch_recovery_preserved": True,
        "epoch_artifact_integrity": epoch_integrity_after,
        "early_stopping_resume": early_stopping_state,
        "epochs_added_in_this_invocation": len(scores) - len(prior_scores),
    }
    health["health_sha256"] = sha256_payload(health)
    health_path = output / "training_health.json"
    atomic_json(health_path, health)
    completion = {
        "schema_version": "capacity_history_thesis_core_training_complete_v4_masked",
        "status": "pass",
        "formal_run": True,
        "evidence_status": "retrospective_held_out",
        "run_id": args.run_id,
        "model_cell_id": spec["model_cell_id"],
        "family": spec["family"],
        "capacity_tier": spec["capacity_tier"],
        "history_horizon_s": spec["history_horizon_s"],
        "learning_rate": spec["learning_rate"],
        "seed": spec["seed"],
        "best_epoch": best_epoch,
        "checkpoint_selection_metric": (
            "validation_rollout_macro_masked_trajectory_mixture_NLL_per_valid_step"
        ),
        "future_validity_contract": "future_valid_mask_fail_closed_v4",
        "best_model": artifact_hash(best_model),
        "best_weights": artifact_hash(full_weights),
        "cached_weights": artifact_hash(cached_weights),
        "history_csv": artifact_hash(history_csv),
        "run_config": artifact_hash(config_path),
        "training_health": artifact_hash(health_path),
        "parameters": artifact_hash(parameter_path),
        "parity": artifact_hash(parity_path),
        "epoch_checkpoints": artifact_hash(epoch_checkpoint_dir),
        "resume_backup": artifact_hash(backup_dir),
        "cache_complete_sha256": config["cache_complete_sha256"],
        "dataset_complete_sha256": config["dataset_complete_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
    }
    completion["completion_sha256"] = sha256_payload(completion)
    atomic_json(output / "TRAINING_COMPLETE.json", completion)
    print(json.dumps(completion, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
