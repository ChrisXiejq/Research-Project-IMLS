#!/usr/bin/env python3
"""Build a Day 13 training-only collision-rollout sensitivity dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any, Iterable


FEATURE_SCHEMA_ID = "give_way_interaction_sequence_v2"
FEATURE_NAMES = (
    "time_offset_s",
    "ego_rel_x_m",
    "ego_rel_y_m",
    "target_rel_x_m",
    "target_rel_y_m",
    "ego_speed_mps",
    "target_speed_mps",
    "relative_longitudinal_speed_mps",
    "relative_lateral_speed_mps",
    "sin_relative_yaw",
    "cos_relative_yaw",
    "ego_target_distance_m",
)
HISTORY_TIMES_S = (-1.0, -0.8, -0.6, -0.4, -0.2, 0.0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSON") from exc


class Normalization:
    def __init__(self) -> None:
        self.count = [0] * len(FEATURE_NAMES)
        self.total = [0.0] * len(FEATURE_NAMES)
        self.total_sq = [0.0] * len(FEATURE_NAMES)

    def update(self, sample: dict[str, Any]) -> None:
        sequence = sample.get("interaction_sequence") or []
        mask = sample.get("interaction_sequence_mask") or []
        if len(sequence) != 6 or len(mask) != 6 or any(len(row) != 12 for row in sequence):
            raise ValueError(f"Invalid interaction sequence: {sample.get('source_subrun')}")
        for row, valid in zip(sequence, mask):
            if not bool(valid):
                continue
            for index, raw in enumerate(row):
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError("Non-finite interaction feature")
                self.count[index] += 1
                self.total[index] += value
                self.total_sq[index] += value * value

    def payload(self) -> dict[str, Any]:
        if any(count == 0 for count in self.count):
            raise ValueError(f"Missing normalization observations: {self.count}")
        mean = [total / count for total, count in zip(self.total, self.count)]
        variance = [
            max(total_sq / count - value * value, 0.0)
            for total_sq, count, value in zip(self.total_sq, self.count, mean)
        ]
        return {
            "schema_id": FEATURE_SCHEMA_ID,
            "fit_split": "train",
            "fit_init_ids": list(range(1, 41)),
            "masked_tokens_excluded": True,
            "minimum_std": 1.0e-6,
            "feature_names": list(FEATURE_NAMES),
            "history_times_s": list(HISTORY_TIMES_S),
            "count_per_feature": self.count,
            "mean": mean,
            "std": [max(math.sqrt(value), 1.0e-6) for value in variance],
        }


def sample_key(sample: dict[str, Any]) -> tuple[str, str]:
    return str(sample.get("source_cell", sample.get("cell_id"))), str(sample["source_subrun"])


def collision_rollouts(path: Path) -> set[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selected = {
        (str(row["cell"]), str(row["scenario_dir"]))
        for row in rows
        if int(row["collision_callbacks"]) > 0
    }
    selected_rows = [row for row in rows if int(row["collision_callbacks"]) > 0]
    if len(selected) != 6 or len(selected_rows) != 6:
        raise ValueError(f"Expected six unique callback-containing rollouts, found {len(selected)}")
    if any(row["split"] != "train" or not row["cell"].startswith("S1_") for row in selected_rows):
        raise ValueError("Collision filter must be restricted to reactive training rollouts")
    return selected


def write_filtered(
    source: Path,
    destination: Path,
    excluded: set[tuple[str, str]],
    normalization: Normalization | None = None,
) -> tuple[int, int, set[tuple[str, str]]]:
    retained = removed = 0
    observed: set[tuple[str, str]] = set()
    with destination.open("w", encoding="utf-8") as handle:
        for sample in read_jsonl(source):
            key = sample_key(sample)
            if key in excluded:
                removed += 1
                observed.add(key)
                continue
            handle.write(json.dumps(sample, separators=(",", ":")) + "\n")
            retained += 1
            if normalization is not None:
                normalization.update(sample)
    return retained, removed, observed


def build(day7: Path, collision_audit_path: Path, rollout_path: Path, output: Path) -> dict[str, Any]:
    source_complete_path = day7 / "DAY7_COMPLETE.json"
    model_gate_path = day7 / "DAY7_MODEL_IMPLEMENTATION_COMPLETE.json"
    source_complete = read_json(source_complete_path)
    model_gate = read_json(model_gate_path)
    collision_audit = read_json(collision_audit_path)
    if source_complete.get("status") != "pass" or model_gate.get("status") != "pass":
        raise ValueError("Original Day7 completion gates must pass")
    if collision_audit.get("status") != "pass":
        raise ValueError("Day12 collision audit must pass")
    if collision_audit.get("sensitivity_decision", {}).get("decision") != "material_reactive_train_overlap_full_filtered_matrix_review":
        raise ValueError("Collision audit does not trigger the full filtered-matrix review")

    source_hashes = {
        "day7_complete": sha256(source_complete_path),
        "collision_audit": sha256(collision_audit_path),
        "collision_rollouts": sha256(rollout_path),
    }
    completion_path = output / "DAY7_COMPLETE.json"
    if completion_path.is_file():
        existing = read_json(completion_path)
        if existing.get("status") == "pass" and existing.get("source_hashes") == source_hashes:
            return existing
        raise ValueError(f"Existing filtered dataset has provenance drift: {output}")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite incomplete output: {output}")

    excluded = collision_rollouts(rollout_path)
    stage = output.with_name(f".{output.name}.building.{os.getpid()}")
    stage.mkdir(parents=True)
    normalization = Normalization()
    try:
        train_retained, train_removed, train_observed = write_filtered(
            day7 / "train.jsonl", stage / "train.jsonl", excluded, normalization
        )
        all_retained, all_removed, all_observed = write_filtered(
            day7 / "all.jsonl", stage / "all.jsonl", excluded
        )
        if train_observed != excluded or all_observed != excluded:
            raise ValueError("Not every declared collision rollout was observed in train/all JSONL")
        expected_removed = int(collision_audit["totals"]["affected_usable_windows"])
        if train_removed != expected_removed or all_removed != expected_removed:
            raise ValueError(
                f"Excluded sample mismatch: train={train_removed}, all={all_removed}, expected={expected_removed}"
            )
        for split in ("val", "test"):
            shutil.copyfile(day7 / f"{split}.jsonl", stage / f"{split}.jsonl")
            if sha256(stage / f"{split}.jsonl") != sha256(day7 / f"{split}.jsonl"):
                raise ValueError(f"{split} split changed during training-only sensitivity build")

        atomic_json(stage / "interaction_normalization_train.json", normalization.payload())
        shutil.copyfile(model_gate_path, stage / model_gate_path.name)
        files = {
            split: {
                "path": f"{split}.jsonl",
                "bytes": (stage / f"{split}.jsonl").stat().st_size,
                "sha256": sha256(stage / f"{split}.jsonl"),
            }
            for split in ("all", "train", "val", "test")
        }
        audit = {
            "schema_version": "day13_collision_filtered_dataset_audit_v1",
            "status": "pass",
            "analysis_role": "training-only sensitivity; original Day7 and Day8 remain primary",
            "filter_rule": "exclude every usable training sample from the six rollout directories with native CARLA callbacks",
            "excluded_rollouts": [
                {"cell": cell, "source_subrun": subrun} for cell, subrun in sorted(excluded)
            ],
            "counts": {
                "original_train_usable": train_retained + train_removed,
                "retained_train_usable": train_retained,
                "excluded_train_usable": train_removed,
                "excluded_train_fraction": train_removed / (train_retained + train_removed),
                "retained_all_usable": all_retained,
                "excluded_all_usable": all_removed,
            },
            "holdout_invariance": {
                split: {
                    "byte_identical": True,
                    "sha256": files[split]["sha256"],
                }
                for split in ("val", "test")
            },
            "test_accessed_for_selection": False,
            "source_hashes": source_hashes,
        }
        atomic_json(stage / "day13_filter_audit.json", audit)
        manifest = {
            "schema_version": "day13_collision_filtered_merged_dataset_v1",
            "status": "pass",
            "training_filter": audit["filter_rule"],
            "original_day7_results": str(day7),
            "files": files,
            "normalization": {
                "path": "interaction_normalization_train.json",
                "sha256": sha256(stage / "interaction_normalization_train.json"),
            },
            "audit": "day13_filter_audit.json",
            "test_accessed": False,
        }
        atomic_json(stage / "manifest.json", manifest)
        completion = {
            "schema_version": "day13_filtered_day7_compatibility_gate_v1",
            "status": "pass",
            "rollout_count": 194,
            "usable_sample_count": all_retained,
            "full_horizon_sample_count": None,
            "manifest_sha256": sha256(stage / "manifest.json"),
            "normalization_sha256": sha256(stage / "interaction_normalization_train.json"),
            "split_audit_sha256": sha256(stage / "day13_filter_audit.json"),
            "source_hashes": source_hashes,
        }
        atomic_json(stage / "DAY7_COMPLETE.json", completion)
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage, output)
        return completion
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day7-results", required=True, type=Path)
    parser.add_argument("--collision-audit", required=True, type=Path)
    parser.add_argument("--collision-rollouts", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = build(
        args.day7_results.resolve(),
        args.collision_audit.resolve(),
        args.collision_rollouts.resolve(),
        args.output_dir.resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
