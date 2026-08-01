#!/usr/bin/env python3
"""Train one frozen-contract Day 8 prediction variant with crash-safe resume.

The script deliberately performs no test-set evaluation.  It trains on the
fixed Day 7 train split, selects a checkpoint using validation masked NLL, and
writes its completion marker last.  ``BackupAndRestore`` preserves optimizer,
epoch and model state if the server dies between epochs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterator, Tuple

import numpy as np
import tensorflow as tf

from interaction_adapter_v2 import (
    VARIANTS,
    build_interaction_adapter,
    configure_v2_b1_head,
    load_normalization,
    masked_multipath_loss,
    masked_top_mode_ade,
    parameter_report,
)
from prediction_dataset_utils import read_jsonl, resolve_raster_path
from prediction_input_contract import load_logged_raster, preprocess_resnet_raster


ALL_VARIANTS = ("B1", *VARIANTS)
REPO_ROOT = Path(__file__).resolve().parents[3]
TRAINER_RELPATH = "core/scripts/models/train_prediction_model_v2_day8.py"
ADAPTER_RELPATH = "core/scripts/models/interaction_adapter_v2.py"
LEGACY_RESUME_TRAINER_SHA256 = (
    "946fc09e3c7e4839fd20998c8182180ee23b30e63549e8932b8b35de99018d2f"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-dir", required=True)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--variant", required=True, choices=ALL_VARIANTS)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1.0e-4)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--shuffle-buffer", type=int, default=1024)
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--max-val-samples", type=int, default=None)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_hash(path: Path) -> Dict:
    if path.is_file():
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    total = 0
    for item in files:
        relative = str(item.relative_to(path)).encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        total += item.stat().st_size
    return {"path": str(path), "files": len(files), "bytes": total, "sha256_tree": digest.hexdigest()}


def atomic_json(path: Path, payload: Dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def masked_local_label(sample: Dict, horizon: int) -> np.ndarray:
    label = np.zeros((horizon, 3), dtype=np.float32)
    rotation = np.asarray(sample["target_to_world_R"], dtype=np.float32)
    translation = np.asarray(sample["target_to_world_t"], dtype=np.float32)
    future = sample.get("future_xy_world") or []
    mask = sample.get("future_valid_mask") or []
    for index in range(min(horizon, len(mask), len(future))):
        if mask[index] and future[index] and future[index][0] is not None:
            label[index, :2] = (np.asarray(future[index], dtype=np.float32) - translation) @ rotation
            label[index, 2] = 1.0
    return label


def sample_generator(
    jsonl: Path,
    horizon: int,
    maximum: int | None,
) -> Iterator[Tuple[bytes, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    emitted = 0
    for sample in read_jsonl(str(jsonl)):
        label = masked_local_label(sample, horizon)
        if not np.any(label[:, 2]):
            continue
        raster_path = resolve_raster_path(sample)
        if not raster_path or not os.path.exists(raster_path):
            continue
        sequence = np.asarray(sample.get("interaction_sequence"), dtype=np.float32)
        mask = np.asarray(sample.get("interaction_sequence_mask"), dtype=np.float32)
        if sequence.shape != (6, 12) or mask.shape != (6,):
            raise ValueError(f"Invalid V2 interaction shape in {sample.get('source_subrun')}")
        yield (
            raster_path.encode("utf-8"),
            np.asarray(sample["past_states_local"], dtype=np.float32),
            sequence,
            mask,
            label,
        )
        emitted += 1
        if maximum is not None and emitted >= maximum:
            return


def count_samples(jsonl: Path, horizon: int, maximum: int | None) -> int:
    return sum(1 for _ in sample_generator(jsonl, horizon, maximum))


def load_image(path_value: np.ndarray) -> np.ndarray:
    value = path_value.item() if hasattr(path_value, "item") else path_value
    path = value.decode("utf-8") if isinstance(value, bytes) else str(value)
    raster = load_logged_raster(path)
    if tuple(raster.shape[:2]) != (500, 500):
        import cv2

        raster = cv2.resize(raster, (500, 500), interpolation=cv2.INTER_LINEAR)
    return preprocess_resnet_raster(raster)[0].astype(np.float32)


def make_dataset(
    jsonl: Path,
    variant: str,
    horizon: int,
    batch_size: int,
    shuffle: bool,
    shuffle_buffer: int,
    seed: int,
    maximum: int | None,
) -> tf.data.Dataset:
    signature = (
        tf.TensorSpec((), tf.string),
        tf.TensorSpec((None, 4), tf.float32),
        tf.TensorSpec((6, 12), tf.float32),
        tf.TensorSpec((6,), tf.float32),
        tf.TensorSpec((horizon, 3), tf.float32),
    )
    dataset = tf.data.Dataset.from_generator(
        lambda: sample_generator(jsonl, horizon, maximum), output_signature=signature
    )
    if shuffle:
        dataset = dataset.shuffle(
            shuffle_buffer, seed=seed, reshuffle_each_iteration=True
        )

    def prepare(path, past, sequence, mask, label):
        image = tf.numpy_function(load_image, [path], tf.float32)
        image.set_shape((500, 500, 3))
        inputs = (image, past) if variant == "B1" else (image, past, sequence, mask)
        return inputs, label

    options = tf.data.Options()
    options.experimental_deterministic = not shuffle
    dataset = dataset.with_options(options)
    return (
        dataset.map(prepare, num_parallel_calls=tf.data.AUTOTUNE)
        .batch(batch_size, drop_remainder=False)
        .prefetch(tf.data.AUTOTUNE)
    )


def git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def git_blob_sha256(revision: str, relative_path: str) -> str:
    try:
        content = subprocess.check_output(
            ["git", "show", f"{revision}:{relative_path}"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(
            f"Cannot audit resume source {revision}:{relative_path}"
        ) from error
    return hashlib.sha256(content).hexdigest()


def audit_compatible_git_only_resume(
    existing: Dict, requested: Dict, output: Path
) -> None:
    existing_semantics = {
        key: value for key, value in existing.items() if key != "git_head"
    }
    requested_semantics = {
        key: value for key, value in requested.items() if key != "git_head"
    }
    if existing_semantics != requested_semantics:
        changed = sorted(
            key
            for key in set(existing_semantics) | set(requested_semantics)
            if existing_semantics.get(key) != requested_semantics.get(key)
        )
        raise ValueError(f"Resume semantic config drift detected: {changed}")
    previous_head = existing.get("git_head")
    requested_head = requested.get("git_head")
    if not previous_head or not requested_head:
        raise ValueError("Cannot audit resume across missing Git provenance")
    previous_trainer_sha = git_blob_sha256(previous_head, TRAINER_RELPATH)
    previous_adapter_sha = git_blob_sha256(previous_head, ADAPTER_RELPATH)
    current_adapter_sha = sha256_file(REPO_ROOT / ADAPTER_RELPATH)
    if previous_trainer_sha != LEGACY_RESUME_TRAINER_SHA256:
        raise ValueError(
            "Resume rejected: previous trainer is not the audited legacy implementation"
        )
    if previous_adapter_sha != current_adapter_sha:
        raise ValueError("Resume rejected: interaction adapter implementation changed")
    atomic_json(
        output / "RESUME_PROVENANCE.json",
        {
            "status": "pass",
            "reason": "git_head_only_change_with_identical_training_semantics",
            "allowed_changed_config_fields": ["git_head"],
            "previous_git_head": previous_head,
            "resume_git_head": requested_head,
            "previous_trainer_sha256": previous_trainer_sha,
            "audited_legacy_trainer_sha256": LEGACY_RESUME_TRAINER_SHA256,
            "previous_interaction_adapter_sha256": previous_adapter_sha,
            "resume_interaction_adapter_sha256": current_adapter_sha,
        },
    )


def read_history(path: Path) -> Dict[str, list]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result: Dict[str, list] = {}
    for row in rows:
        for key, value in row.items():
            if key == "epoch" or value in (None, ""):
                continue
            result.setdefault(key, []).append(float(value))
    return result


def build_model(args: argparse.Namespace, anchors: np.ndarray) -> tf.keras.Model:
    base = tf.keras.models.load_model(args.base_model, compile=False)
    if args.variant == "B1":
        return configure_v2_b1_head(base)
    normalization = load_normalization(
        Path(args.merged_dir) / "interaction_normalization_train.json"
    )
    return build_interaction_adapter(base, anchors, normalization, args.variant)


def main() -> None:
    args = parse_args()
    if args.epochs < 1 or args.batch_size < 1 or args.patience < 1:
        raise ValueError("epochs, batch-size and patience must be positive")
    random.seed(args.seed)
    np.random.seed(args.seed)
    tf.keras.utils.set_random_seed(args.seed)

    merged = Path(args.merged_dir).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    completion_path = output / "TRAINING_COMPLETE.json"
    if completion_path.exists():
        completion = json.loads(completion_path.read_text())
        if completion.get("status") == "pass":
            print(json.dumps({"status": "skip_complete", "completion": str(completion_path)}))
            return

    day7 = json.loads((merged / "DAY7_COMPLETE.json").read_text())
    model_gate = json.loads((merged / "DAY7_MODEL_IMPLEMENTATION_COMPLETE.json").read_text())
    if day7.get("status") != "pass" or model_gate.get("status") != "pass":
        raise ValueError("Both Day 7 completion gates must pass before Day 8 training")
    anchors_path = Path(args.anchors).resolve()
    base_path = Path(args.base_model).resolve()
    anchors = np.load(anchors_path).astype(np.float32)
    if anchors.shape[1] < args.horizon:
        raise ValueError("Anchor horizon is shorter than label horizon")

    config = {
        "schema_version": "day8_training_config_v1",
        "variant": args.variant,
        "seed": args.seed,
        "merged_dir": str(merged),
        "base_model": str(base_path),
        "anchors": str(anchors_path),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "patience": args.patience,
        "horizon": args.horizon,
        "shuffle_buffer": args.shuffle_buffer,
        "max_train_samples": args.max_train_samples,
        "max_val_samples": args.max_val_samples,
        "day7_manifest_sha256": day7["manifest_sha256"],
        "day7_model_smoke_sha256": model_gate["model_smoke_report_sha256"],
        "git_head": git_head(),
    }
    config_path = output / "run_config.json"
    if config_path.exists():
        existing_config = json.loads(config_path.read_text())
        if existing_config != config:
            audit_compatible_git_only_resume(existing_config, config, output)
    atomic_json(config_path, config)

    train_jsonl, val_jsonl = merged / "train.jsonl", merged / "val.jsonl"
    train_count = count_samples(train_jsonl, args.horizon, args.max_train_samples)
    val_count = count_samples(val_jsonl, args.horizon, args.max_val_samples)
    if train_count == 0 or val_count == 0:
        raise ValueError(f"No usable samples: train={train_count}, val={val_count}")

    model = build_model(args, anchors)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(args.learning_rate, clipnorm=10.0),
        loss=masked_multipath_loss(anchors, args.horizon),
        metrics=[masked_top_mode_ade(anchors, args.horizon)],
    )
    params = parameter_report(model)
    train_ds = make_dataset(
        train_jsonl, args.variant, args.horizon, args.batch_size, True,
        args.shuffle_buffer, args.seed, args.max_train_samples,
    )
    val_ds = make_dataset(
        val_jsonl, args.variant, args.horizon, args.batch_size, False,
        args.shuffle_buffer, args.seed, args.max_val_samples,
    )
    best_weights = output / "best.weights.h5"
    history_csv = output / "history.csv"
    fit_complete = output / "FIT_COMPLETE.json"
    backup_dir = output / "resume_backup"
    callbacks = [
        tf.keras.callbacks.BackupAndRestore(
            backup_dir=str(backup_dir), save_freq="epoch", delete_checkpoint=False
        ),
        tf.keras.callbacks.ModelCheckpoint(
            str(best_weights), monitor="val_loss", mode="min", save_best_only=True,
            save_weights_only=True, verbose=1,
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", mode="min", patience=args.patience, verbose=1
        ),
        tf.keras.callbacks.CSVLogger(str(history_csv), append=history_csv.exists()),
        tf.keras.callbacks.TerminateOnNaN(),
    ]
    if fit_complete.exists() and best_weights.exists():
        fit_gate = json.loads(fit_complete.read_text())
        if fit_gate.get("status") != "pass":
            raise ValueError(f"Invalid fit completion marker: {fit_complete}")
        print(json.dumps({"status": "skip_completed_fit", "fit_completion": str(fit_complete)}))
    else:
        model.fit(
            train_ds,
            validation_data=val_ds,
            epochs=args.epochs,
            callbacks=callbacks,
            verbose=2,
        )
        if not best_weights.exists():
            raise RuntimeError("Training ended without a best validation checkpoint")
        atomic_json(
            fit_complete,
            {
                "status": "pass",
                "best_weights_sha256": sha256_file(best_weights),
                "history_rows": len(read_history(history_csv).get("val_loss", [])),
            },
        )
    if not best_weights.exists():
        raise RuntimeError("Training ended without a best validation checkpoint")
    model.load_weights(str(best_weights))
    best_model = output / "best_model"
    staging = output / "best_model.staging"
    if staging.exists():
        shutil.rmtree(staging)
    model.save(staging)
    if best_model.exists():
        shutil.rmtree(best_model)
    os.replace(staging, best_model)

    history = read_history(history_csv)
    val_losses = history.get("val_loss", [])
    if not val_losses or not np.all(np.isfinite(val_losses)):
        raise RuntimeError("Validation history is missing or non-finite")
    best_epoch = int(np.argmin(val_losses)) + 1
    completion = {
        "status": "pass",
        "variant": args.variant,
        "seed": args.seed,
        "train_samples": train_count,
        "validation_samples": val_count,
        "epochs_completed": len(val_losses),
        "best_epoch": best_epoch,
        "best_val_masked_nll": float(val_losses[best_epoch - 1]),
        "parameters": params,
        "best_model": artifact_hash(best_model),
        "best_weights": artifact_hash(best_weights),
        "history_csv": artifact_hash(history_csv),
        "run_config": artifact_hash(config_path),
    }
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    atomic_json(completion_path, completion)
    print(json.dumps(completion, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
