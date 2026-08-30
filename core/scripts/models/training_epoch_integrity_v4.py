#!/usr/bin/env python3
"""Fail-closed continuity checks for per-epoch training evidence.

Counting CSV rows and checkpoint files is insufficient after an interrupted
Keras callback sequence: both populations can have the same size while one
epoch is absent from each.  This module makes the epoch identities explicit
and optionally verifies that every HDF5 checkpoint is structurally readable.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any


CHECKPOINT_PATTERN = re.compile(r"^epoch_(\d+)\.weights\.h5$")
BACKUP_PATTERN = re.compile(r"^ckpt-(\d+)\.index$")


def _history_epochs(path: Path) -> tuple[list[int], list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return [], ["history_missing"]
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "epoch" not in reader.fieldnames:
                return [], ["history_epoch_column_missing"]
            rows = list(reader)
    except (OSError, csv.Error):
        return [], ["history_unreadable"]

    epochs: list[int] = []
    for row_index, row in enumerate(rows):
        raw = row.get("epoch")
        try:
            numeric = float(str(raw))
            value = int(numeric)
            if not numeric.is_integer() or value < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"history_epoch_invalid:{row_index}")
            continue
        epochs.append(value)
    return epochs, errors


def _checkpoint_population(path: Path) -> tuple[list[int], list[Path], list[str]]:
    if not path.is_dir():
        return [], [], ["checkpoint_directory_missing"]
    indexed: list[tuple[int, Path]] = []
    errors: list[str] = []
    for checkpoint in sorted(path.glob("epoch_*.weights.h5")):
        match = CHECKPOINT_PATTERN.fullmatch(checkpoint.name)
        if match is None:
            errors.append(f"checkpoint_name_invalid:{checkpoint.name}")
            continue
        indexed.append((int(match.group(1)), checkpoint))
    indexed.sort(key=lambda item: item[0])
    return [item[0] for item in indexed], [item[1] for item in indexed], errors


def _backup_epoch(path: Path) -> tuple[int | None, list[str]]:
    chief = path / "chief"
    if not chief.is_dir():
        return None, ["optimizer_backup_missing"]
    epochs: list[int] = []
    errors: list[str] = []
    for item in sorted(chief.glob("ckpt-*.index")):
        match = BACKUP_PATTERN.fullmatch(item.name)
        if match is None:
            errors.append(f"optimizer_backup_name_invalid:{item.name}")
            continue
        if item.stat().st_size <= 0:
            errors.append(f"optimizer_backup_index_empty:{item.name}")
        data_files = list(chief.glob(f"ckpt-{match.group(1)}.data-*-of-*"))
        if not data_files or any(value.stat().st_size <= 0 for value in data_files):
            errors.append(f"optimizer_backup_data_missing_or_empty:ckpt-{match.group(1)}")
        epochs.append(int(match.group(1)))
    if not epochs:
        errors.append("optimizer_backup_checkpoint_missing")
        return None, errors
    return max(epochs), errors


def restored_early_stopping_state(
    scores: list[float], *, patience: int
) -> dict[str, Any]:
    """Reconstruct Keras min-mode EarlyStopping state from complete history."""

    if patience < 1:
        raise ValueError("Early-stopping patience must be positive")
    best = math.inf
    best_epoch: int | None = None
    wait = 0
    for index, raw_score in enumerate(scores):
        score = float(raw_score)
        if not math.isfinite(score):
            raise ValueError(f"Non-finite early-stopping score at index {index}")
        if score < best:
            best = score
            best_epoch = index + 1
            wait = 0
        else:
            wait += 1
    return {
        "observed_epochs": len(scores),
        "best": None if best_epoch is None else best,
        "best_epoch": best_epoch,
        "consecutive_non_improving_epochs": wait,
        "patience": patience,
        "stop_already_reached": bool(scores and wait >= patience),
    }


def inspect_epoch_artifacts(
    history_path: Path,
    checkpoint_dir: Path,
    *,
    backup_dir: Path | None = None,
    validate_hdf5: bool = False,
) -> dict[str, Any]:
    """Return a deterministic, fail-closed epoch continuity report."""

    history_epochs, errors = _history_epochs(history_path)
    checkpoint_epochs, checkpoint_paths, checkpoint_errors = _checkpoint_population(
        checkpoint_dir
    )
    errors.extend(checkpoint_errors)

    expected_history = list(range(len(history_epochs)))
    expected_checkpoints = list(range(1, len(history_epochs) + 1))
    if history_epochs != expected_history:
        errors.append("history_epoch_sequence_not_contiguous_from_zero")
    if checkpoint_epochs != expected_checkpoints:
        errors.append("checkpoint_epoch_sequence_not_contiguous_from_one")
    if checkpoint_epochs != [value + 1 for value in history_epochs]:
        errors.append("history_checkpoint_epoch_identity_mismatch")

    backup_epoch: int | None = None
    if backup_dir is not None:
        backup_epoch, backup_errors = _backup_epoch(backup_dir)
        errors.extend(backup_errors)
        if backup_epoch is not None and backup_epoch != len(history_epochs):
            errors.append("optimizer_backup_history_epoch_mismatch")

    unreadable: list[str] = []
    if validate_hdf5:
        try:
            import h5py
        except ImportError:
            errors.append("h5py_unavailable_for_checkpoint_validation")
        else:
            for checkpoint in checkpoint_paths:
                try:
                    with h5py.File(checkpoint, "r") as handle:
                        if not list(handle.keys()):
                            raise ValueError("empty HDF5 root")
                except (OSError, RuntimeError, ValueError):
                    unreadable.append(checkpoint.name)
            if unreadable:
                errors.append("checkpoint_hdf5_unreadable")

    errors = sorted(set(errors))
    return {
        "status": "pass" if not errors else "fail",
        "history_rows": len(history_epochs),
        "history_epoch_indices": history_epochs,
        "checkpoint_files": len(checkpoint_epochs),
        "checkpoint_epoch_indices": checkpoint_epochs,
        "optimizer_backup_epoch": backup_epoch,
        "unreadable_checkpoints": unreadable,
        "errors": errors,
    }
