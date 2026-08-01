#!/usr/bin/env python3
"""Merge, group-split and audit the completed Day 6 V2 dataset for Day 7."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable

import numpy as np

from interaction_sequence import FEATURE_NAMES, FEATURE_SCHEMA_ID, HISTORY_TIMES_S
from prediction_dataset_utils import infer_init_id, read_jsonl, split_for_init


CELLS = ("S0_FIXED", "S0_ADAPTIVE", "S1_FIXED", "S1_ADAPTIVE")
EXPECTED_ROLLOUTS = {"train": 160, "val": 20, "test": 20}
DATASET_VERSION = "give_way_interaction_prediction_v2.0"
PROTOCOL_ID = "town05_give_way_2x2_200_rollouts_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day6-results", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


class TrainNormalization:
    def __init__(self) -> None:
        self.count = np.zeros(len(FEATURE_NAMES), dtype=np.int64)
        self.total = np.zeros(len(FEATURE_NAMES), dtype=np.float64)
        self.total_sq = np.zeros(len(FEATURE_NAMES), dtype=np.float64)

    def update(self, sequence: np.ndarray, mask: np.ndarray) -> None:
        valid = mask.astype(bool)
        if np.any(valid):
            values = sequence[valid].astype(np.float64)
            self.count += values.shape[0]
            self.total += np.sum(values, axis=0)
            self.total_sq += np.sum(np.square(values), axis=0)

    def payload(self) -> Dict[str, Any]:
        if np.any(self.count == 0):
            raise ValueError(f"No train observations for features: {self.count.tolist()}")
        mean = self.total / self.count
        variance = np.maximum(self.total_sq / self.count - np.square(mean), 0.0)
        std = np.maximum(np.sqrt(variance), 1.0e-6)
        return {
            "schema_id": FEATURE_SCHEMA_ID,
            "fit_split": "train",
            "fit_init_ids": list(range(1, 41)),
            "masked_tokens_excluded": True,
            "minimum_std": 1.0e-6,
            "feature_names": list(FEATURE_NAMES),
            "history_times_s": list(HISTORY_TIMES_S),
            "count_per_feature": self.count.tolist(),
            "mean": mean.tolist(),
            "std": std.tolist(),
        }


def validate_sequence(sample: Dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    sequence = np.asarray(sample.get("interaction_sequence"), dtype=np.float32)
    mask = np.asarray(sample.get("interaction_sequence_mask"), dtype=np.float32)
    if sequence.shape != (6, 12) or mask.shape != (6,):
        raise ValueError(f"Invalid interaction shapes: {sequence.shape}, {mask.shape}")
    if not np.all(np.isfinite(sequence)) or not np.all(np.isin(mask, (0.0, 1.0))):
        raise ValueError("Interaction sequence contains non-finite values or invalid mask")
    if np.any(sequence[mask == 0.0] != 0.0):
        raise ValueError("Masked interaction tokens are not zero-filled")
    return sequence, mask


def expected_cell_metadata(cell: str) -> tuple[str, str]:
    target_style = "assertive_constant_speed" if cell.startswith("S0_") else "defensive_reactive"
    ego_policy = "fixed_medium" if cell.endswith("FIXED") else "adaptive_floor_weak"
    return target_style, ego_policy


def main() -> None:
    args = parse_args()
    day6 = Path(args.day6_results).resolve()
    output = Path(args.output_dir).resolve()
    if output == day6 or day6 in output.parents:
        raise ValueError("Day 7 output must be outside the immutable Day 6 result directory")
    complete = json.loads((day6 / "DAY6_COMPLETE.json").read_text())
    if complete.get("status") != "pass" or complete.get("rollout_count") != 200:
        raise ValueError("Day 6 completion marker is not a passing 200-rollout contract")
    if output.exists():
        if (output / "DAY7_COMPLETE.json").is_file():
            print((output / "DAY7_COMPLETE.json").read_text())
            return
        raise FileExistsError(f"Refusing to overwrite incomplete output directory: {output}")

    stage = output.with_name(f".{output.name}.building.{os.getpid()}")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    handles = {name: (stage / f"{name}.jsonl").open("w") for name in ("all", "train", "val", "test")}
    raw_counts = Counter()
    usable_counts = Counter()
    full_counts = Counter()
    partial_counts = Counter()
    zero_counts = Counter()
    usable_by_cell_split: Counter[tuple[str, str]] = Counter()
    rollout_by_split: Counter[str] = Counter()
    rollouts_by_init: defaultdict[int, set[str]] = defaultdict(set)
    sample_keys: set[tuple[str, int, int]] = set()
    normalization = TrainNormalization()
    source_files = []

    try:
        for cell in CELLS:
            target_style, ego_policy = expected_cell_metadata(cell)
            labeled_files = sorted(day6.glob(f"{cell}/scenario_*/prediction_dataset/prediction_dataset_labeled.jsonl"))
            if len(labeled_files) != 50:
                raise ValueError(f"{cell}: expected 50 labeled files, found {len(labeled_files)}")
            for labeled_path in labeled_files:
                subrun = labeled_path.parents[1].name
                init_id = infer_init_id(subrun)
                if init_id is None:
                    raise ValueError(f"Cannot infer init id: {subrun}")
                split = split_for_init(init_id)
                rollout_key = (cell, init_id)
                if cell in rollouts_by_init[init_id]:
                    raise ValueError(f"Duplicate rollout: {rollout_key}")
                rollouts_by_init[init_id].add(cell)
                rollout_by_split[split] += 1
                prediction_dir = labeled_path.parent
                source_files.append(str(labeled_path))
                for sample in read_jsonl(str(labeled_path)):
                    raw_counts[split] += 1
                    raw_counts["all"] += 1
                    if sample.get("dataset_version") != DATASET_VERSION or sample.get("protocol_id") != PROTOCOL_ID:
                        raise ValueError(f"Protocol mismatch in {labeled_path}")
                    if sample.get("cell_id") != cell or int(sample.get("ego_init_id")) != init_id:
                        raise ValueError(f"Cell/init metadata mismatch in {labeled_path}")
                    if sample.get("target_style") != target_style or sample.get("ego_policy") != ego_policy:
                        raise ValueError(f"Factor metadata mismatch in {labeled_path}")
                    sequence, sequence_mask = validate_sequence(sample)
                    future_mask = np.asarray(sample.get("future_valid_mask") or [], dtype=np.float32)
                    valid_future = int(np.count_nonzero(future_mask[:10]))
                    if valid_future == 0:
                        zero_counts[split] += 1
                        zero_counts["all"] += 1
                        continue
                    sample_id = int(sample["sample_id"])
                    key = (cell, init_id, sample_id)
                    if key in sample_keys:
                        raise ValueError(f"Duplicate sample key: {key}")
                    sample_keys.add(key)
                    if valid_future == 10:
                        full_counts[split] += 1
                        full_counts["all"] += 1
                    else:
                        partial_counts[split] += 1
                        partial_counts["all"] += 1
                    usable_counts[split] += 1
                    usable_counts["all"] += 1
                    usable_by_cell_split[(cell, split)] += 1
                    sample["source_subrun"] = subrun
                    sample["source_cell"] = cell
                    sample["day7_split"] = split
                    sample["source_prediction_dataset_dir"] = str(prediction_dir)
                    raster_relpath = sample.get("raster_relpath")
                    if raster_relpath:
                        raster_path = prediction_dir / raster_relpath
                        if not raster_path.is_file():
                            raise FileNotFoundError(raster_path)
                        sample["raster_abspath"] = str(raster_path)
                        sample["raster_relpath_from_day6"] = str(raster_path.relative_to(day6))
                    line = json.dumps(sample, separators=(",", ":")) + "\n"
                    handles["all"].write(line)
                    handles[split].write(line)
                    if split == "train":
                        normalization.update(sequence, sequence_mask)
        for init_id in range(1, 51):
            if rollouts_by_init[init_id] != set(CELLS):
                raise ValueError(f"Init {init_id} lacks all four cells: {sorted(rollouts_by_init[init_id])}")
        if dict(rollout_by_split) != EXPECTED_ROLLOUTS:
            raise ValueError(f"Grouped rollout count mismatch: {dict(rollout_by_split)}")
    finally:
        for handle in handles.values():
            handle.close()

    normalization_payload = normalization.payload()
    atomic_json(stage / "interaction_normalization_train.json", normalization_payload)
    files = {}
    for name in ("all", "train", "val", "test"):
        path = stage / f"{name}.jsonl"
        files[name] = {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
    normalization_sha = sha256_file(stage / "interaction_normalization_train.json")
    audit = {
        "status": "pass",
        "dataset_version": DATASET_VERSION,
        "protocol_id": PROTOCOL_ID,
        "source_day6_complete_sha256": sha256_file(day6 / "DAY6_COMPLETE.json"),
        "source_rollouts": 200,
        "rollouts_by_split": dict(rollout_by_split),
        "rollouts_per_init": 4,
        "split_init_ids": {
            "train": list(range(1, 41)),
            "val": list(range(41, 46)),
            "test": list(range(46, 51)),
        },
        "raw_sample_counts": dict(raw_counts),
        "usable_any_label_counts": dict(usable_counts),
        "full_horizon_counts": dict(full_counts),
        "partial_horizon_counts": dict(partial_counts),
        "zero_label_excluded_counts": dict(zero_counts),
        "usable_by_cell_split": {
            cell: {split: usable_by_cell_split[(cell, split)] for split in ("train", "val", "test")}
            for cell in CELLS
        },
        "unique_sample_keys": len(sample_keys),
        "leakage_checks": {
            "init_groups_disjoint": True,
            "four_cells_colocated_per_init": True,
            "normalization_train_only": True,
            "zero_label_samples_excluded": True,
            "partial_horizon_samples_retained_for_masked_loss": True,
        },
        "files": files,
        "normalization": {
            "path": "interaction_normalization_train.json",
            "sha256": normalization_sha,
        },
        "source_labeled_files": source_files,
    }
    atomic_json(stage / "day7_split_audit.json", audit)
    manifest = {
        "status": "pass",
        "day": 7,
        "day6_results": str(day6),
        "merged_dir": str(output),
        "training_filter": "at least one valid future step; masked loss required",
        "audit": "day7_split_audit.json",
        "normalization": "interaction_normalization_train.json",
        "files": files,
    }
    atomic_json(stage / "manifest.json", manifest)
    completion = {
        "status": "pass",
        "rollout_count": 200,
        "usable_sample_count": usable_counts["all"],
        "full_horizon_sample_count": full_counts["all"],
        "split_audit_sha256": sha256_file(stage / "day7_split_audit.json"),
        "normalization_sha256": normalization_sha,
        "manifest_sha256": sha256_file(stage / "manifest.json"),
    }
    atomic_json(stage / "DAY7_COMPLETE.json", completion)
    output.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, output)
    print(json.dumps(completion, indent=2))


if __name__ == "__main__":
    main()
