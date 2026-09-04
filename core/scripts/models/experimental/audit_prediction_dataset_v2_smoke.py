#!/usr/bin/env python3
"""Audit a Day 4/5 V2 collection smoke without merging the dataset."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import collections
import csv
import json
from pathlib import Path

import numpy as np

from interaction_sequence import assert_logged_feature_equivalence
from prediction_input_contract import load_logged_raster, raster_array_sha256
from verify_prediction_input_contract import REQUIRED_V2_FIELDS


EXPECTED_CELLS = {
    "S0_FIXED": ("assertive_constant_speed", "fixed_medium"),
    "S0_ADAPTIVE": ("assertive_constant_speed", "adaptive_floor_weak"),
    "S1_FIXED": ("defensive_reactive", "fixed_medium"),
    "S1_ADAPTIVE": ("defensive_reactive", "adaptive_floor_weak"),
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output-json", required=True)
    return parser.parse_args()


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def as_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes"}


def main():
    args = parse_args()
    root = Path(args.results_dir).expanduser().resolve()
    manifests = sorted(root.glob("**/prediction_dataset/prediction_dataset_manifest.json"))
    errors = []
    cell_counts = collections.Counter()
    samples_per_cell = collections.Counter()
    valid_tokens = collections.Counter()
    trigger_counts = collections.Counter()
    release_counts = collections.Counter()
    active_steps = collections.Counter()
    minimum_active_speed = {}

    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        dataset_dir = manifest_path.parent
        labeled_path = dataset_dir / manifest["labeled_jsonl"]
        rows = list(read_jsonl(labeled_path))
        metadata = manifest.get("dataset_metadata", {})
        cell = metadata.get("cell_id")
        if cell not in EXPECTED_CELLS:
            errors.append(f"{manifest_path}: invalid cell_id={cell!r}")
            continue
        cell_counts[cell] += 1
        expected_target, expected_ego = EXPECTED_CELLS[cell]
        if metadata.get("target_style") != expected_target:
            errors.append(f"{manifest_path}: target style mismatch")
        if metadata.get("ego_policy") != expected_ego:
            errors.append(f"{manifest_path}: ego policy mismatch")
        if not rows:
            errors.append(f"{labeled_path}: no samples")
        for sample in rows:
            samples_per_cell[cell] += 1
            missing = sorted(REQUIRED_V2_FIELDS - set(sample))
            if missing:
                errors.append(f"{labeled_path}: missing fields {missing}")
                continue
            try:
                equivalence = assert_logged_feature_equivalence(sample)
                if any(value != 0.0 for value in equivalence.values()):
                    errors.append(f"{labeled_path}: interaction mismatch")
                mask = np.asarray(sample["interaction_sequence_mask"], dtype=np.float32)
                valid_tokens[cell] += int(np.sum(mask))
                raster_path = dataset_dir / sample["raster_relpath"]
                observed_hash = raster_array_sha256(load_logged_raster(str(raster_path)))
                if observed_hash != sample.get("raster_uint8_sha256"):
                    errors.append(f"{raster_path}: raster hash mismatch")
            except Exception as exc:
                errors.append(f"{labeled_path}: {exc}")

        step_csv = manifest_path.parent.parent / "scenario_steps.csv"
        if step_csv.is_file():
            with step_csv.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if as_bool(row.get("target0_reactive_triggered_this_step")):
                        trigger_counts[cell] += 1
                    if as_bool(row.get("target0_reactive_released_this_step")):
                        release_counts[cell] += 1
                    if as_bool(row.get("target0_reactive_active")):
                        active_steps[cell] += 1
                        try:
                            speed = float(row["target0_speed"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        old = minimum_active_speed.get(cell)
                        minimum_active_speed[cell] = speed if old is None else min(old, speed)

    missing_cells = sorted(set(EXPECTED_CELLS) - set(cell_counts))
    if missing_cells:
        errors.append(f"missing cells: {missing_cells}")
    report = {
        "audit_schema_version": "prediction_dataset_v2_smoke_audit_v1",
        "status": "pass" if not errors else "fail",
        "results_dir": str(root),
        "manifests": len(manifests),
        "cell_rollouts": dict(sorted(cell_counts.items())),
        "samples_per_cell": dict(sorted(samples_per_cell.items())),
        "valid_interaction_tokens_per_cell": dict(sorted(valid_tokens.items())),
        "reactive_diagnostics": {
            "trigger_counts": dict(sorted(trigger_counts.items())),
            "release_counts": dict(sorted(release_counts.items())),
            "active_steps": dict(sorted(active_steps.items())),
            "minimum_active_target_speed_mps": dict(sorted(minimum_active_speed.items())),
            "note": "Trigger coverage is diagnostic on Day 4 and becomes a freeze gate on Day 5.",
        },
        "errors": errors[:100],
    }
    output = Path(args.output_json).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
