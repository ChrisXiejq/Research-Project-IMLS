#!/usr/bin/env python3
"""Audit the complete 50-init x four-cell Day 6 formal collection."""

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
import json
import os
from pathlib import Path

import numpy as np

from audit_prediction_dataset_v2_day5 import (
    EXPECTED_CELLS,
    canonical_hash,
    freeze_reactive_parameters,
    paired_separation,
    read_jsonl,
    step_metrics,
)
from interaction_sequence import assert_logged_feature_equivalence
from prediction_input_contract import load_logged_raster, raster_array_sha256
from verify_prediction_input_contract import REQUIRED_V2_FIELDS


EXPECTED_INITS = set(range(1, 51))


def split_name(init_id):
    if init_id <= 40:
        return "train"
    if init_id <= 45:
        return "validation"
    return "test"


def atomic_write_json(path, value):
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--frozen-config-json", required=True)
    parser.add_argument("--preflight-report-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--expected-git-commit", default="6b71ccc")
    args = parser.parse_args()

    root = Path(args.results_dir).resolve()
    frozen = json.loads(
        Path(args.frozen_config_json).resolve().read_text(encoding="utf-8")
    )
    preflight = json.loads(
        Path(args.preflight_report_json).resolve().read_text(encoding="utf-8")
    )
    expected_contract = frozen["collection_configuration"]["prediction_contract"]
    manifests = sorted(
        root.glob("**/prediction_dataset/prediction_dataset_manifest.json")
    )
    errors = []
    contract_error_count = 0
    duplicate_sample_count = 0
    sample_keys = set()
    rollouts = {}
    parameter_hashes = set()
    observed_contracts = {}
    samples_per_cell = collections.Counter()
    samples_per_split = collections.Counter()
    rollouts_per_cell = collections.Counter()
    rollouts_per_split = collections.Counter()
    collision_per_cell = collections.Counter()

    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            metadata = manifest.get("dataset_metadata", {})
            cell = str(metadata.get("cell_id"))
            init_id = int(metadata.get("ego_init_id"))
        except Exception as exc:
            errors.append(f"{manifest_path}: invalid manifest: {exc}")
            continue
        key = (cell, init_id)
        if key in rollouts:
            errors.append(f"duplicate rollout manifest: {key}")
            continue
        if cell not in EXPECTED_CELLS or init_id not in EXPECTED_INITS:
            errors.append(f"{manifest_path}: unexpected cell/init {key}")
            continue
        expected_target, expected_ego = EXPECTED_CELLS[cell]
        metadata_checks = {
            "dataset_version": expected_contract["dataset_version"],
            "protocol_id": expected_contract["protocol_id"],
            "git_commit": args.expected_git_commit,
            "feature_schema_id": expected_contract["feature_schema_id"],
            "target_style": expected_target,
            "ego_policy": expected_ego,
        }
        for name, expected in metadata_checks.items():
            actual = metadata.get(name)
            if actual != expected:
                errors.append(
                    f"{manifest_path}: {name}={actual!r}, expected {expected!r}"
                )
        observed_contract = {
            "dataset_version": metadata.get("dataset_version"),
            "protocol_id": metadata.get("protocol_id"),
            "git_commit": metadata.get("git_commit"),
            "feature_schema_id": manifest.get("feature_schema_id"),
            "model_weights": manifest.get("model_weights"),
            "model_anchors": manifest.get("model_anchors"),
            "prediction_logging_stride": manifest.get("stride"),
            "prediction_logging_horizon": manifest.get("horizon"),
            "prediction_logging_save_raster": manifest.get("save_raster"),
            "dt_s": manifest.get("dt"),
        }
        observed_contracts[canonical_hash(observed_contract)] = observed_contract

        dataset_dir = manifest_path.parent
        labeled_path = dataset_dir / manifest["labeled_jsonl"]
        try:
            samples = list(read_jsonl(labeled_path))
        except Exception as exc:
            errors.append(f"{labeled_path}: cannot read samples: {exc}")
            samples = []
        if not samples:
            errors.append(f"{labeled_path}: no labeled samples")
        for sample in samples:
            missing = sorted(REQUIRED_V2_FIELDS - set(sample))
            if missing:
                contract_error_count += 1
                errors.append(
                    f"{labeled_path}: sample {sample.get('sample_id')} missing {missing}"
                )
                continue
            sample_key = (cell, init_id, int(sample["sample_id"]))
            if sample_key in sample_keys:
                duplicate_sample_count += 1
                errors.append(f"duplicate sample key: {sample_key}")
            sample_keys.add(sample_key)
            try:
                raster = load_logged_raster(dataset_dir / sample["raster_relpath"])
                if raster_array_sha256(raster) != sample["raster_uint8_sha256"]:
                    raise ValueError("raster hash mismatch")
                assert_logged_feature_equivalence(sample)
            except Exception as exc:
                contract_error_count += 1
                errors.append(
                    f"{labeled_path}: sample {sample.get('sample_id')}: {exc}"
                )
        if cell.startswith("S1") and samples:
            parameters = freeze_reactive_parameters(
                samples[0].get("target_style_parameters", {})
            )
            if parameters:
                parameter_hashes.add(canonical_hash(parameters))

        subrun_dir = dataset_dir.parent
        summary_path = subrun_dir / "scenario_run_summary.json"
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception as exc:
            summary = {}
            errors.append(f"{summary_path}: cannot read summary: {exc}")
        summary_extra = summary.get("extra", {})
        collision_count = summary_extra.get("collision_event_count")
        if collision_count is None:
            errors.append(f"{summary_path}: collision evidence missing")
        else:
            collision_per_cell[cell] += int(collision_count)
        try:
            metrics = step_metrics(subrun_dir / "scenario_steps.csv")
        except Exception as exc:
            metrics = {}
            errors.append(f"{subrun_dir}: step metrics failed: {exc}")
        metrics.update(
            {
                "ran_successfully": summary.get("ran_successfully") is True,
                "collision_event_count": collision_count,
                "sample_count": len(samples),
            }
        )
        rollouts[key] = metrics
        split = split_name(init_id)
        rollouts_per_cell[cell] += 1
        rollouts_per_split[split] += 1
        samples_per_cell[cell] += len(samples)
        samples_per_split[split] += len(samples)

    expected_keys = {
        (cell, init_id) for cell in EXPECTED_CELLS for init_id in EXPECTED_INITS
    }
    missing_rollouts = sorted(expected_keys - set(rollouts))
    if missing_rollouts:
        errors.append(f"missing rollout count: {len(missing_rollouts)}")

    reactive = [
        value for (cell, _), value in rollouts.items() if cell.startswith("S1")
    ]
    trigger_coverage = (
        sum(item.get("trigger_count", 0) > 0 for item in reactive) / len(reactive)
        if reactive
        else None
    )
    active_fractions = [
        item["active_fraction"] for item in reactive if "active_fraction" in item
    ]
    trigger_onsets = [
        item["trigger_onset_s"]
        for item in reactive
        if item.get("trigger_onset_s") is not None
    ]
    minimum_speeds = [
        item["minimum_speed_mps"]
        for item in reactive
        if item.get("minimum_speed_mps") is not None
    ]

    paired = []
    for suffix in ("FIXED", "ADAPTIVE"):
        for init_id in sorted(EXPECTED_INITS):
            s0 = rollouts.get((f"S0_{suffix}", init_id))
            s1 = rollouts.get((f"S1_{suffix}", init_id))
            if not s0 or not s1 or not all(name in s0 and name in s1 for name in ("time", "speed", "xy")):
                continue
            result = paired_separation(s0, s1)
            result.update({"ego_policy": suffix.lower(), "ego_init_id": init_id})
            paired.append(result)

    expected_observed_contract = dict(expected_contract)
    observed_contract_matches = (
        len(observed_contracts) == 1
        and next(iter(observed_contracts.values())) == expected_observed_contract
    )
    gates = {
        "complete_200_rollout_matrix": len(rollouts) == 200
        and not missing_rollouts,
        "exactly_50_rollouts_per_cell": all(
            rollouts_per_cell[cell] == 50 for cell in EXPECTED_CELLS
        ),
        "all_rollouts_ran_successfully": len(rollouts) == 200
        and all(item.get("ran_successfully") is True for item in rollouts.values()),
        "all_200_prediction_manifests_present": len(manifests) == 200,
        "all_rollouts_have_labeled_samples": len(rollouts) == 200
        and all(item.get("sample_count", 0) > 0 for item in rollouts.values()),
        "all_logged_inputs_equivalent": contract_error_count == 0,
        "sample_keys_unique_within_rollout": duplicate_sample_count == 0,
        "one_observed_collection_contract_matching_freeze": observed_contract_matches,
        "reactive_parameters_match_freeze": parameter_hashes
        == {frozen["reactive_parameters_sha256"]},
        "native_collision_evidence_present_for_all_rollouts": len(rollouts) == 200
        and all(item.get("collision_event_count") is not None for item in rollouts.values()),
        "grouped_split_rollout_counts_160_20_20": dict(rollouts_per_split)
        == {"train": 160, "validation": 20, "test": 20},
        "preflight_contract_passed": preflight.get("status") == "pass"
        and all(preflight.get("checks", {}).values()),
    }
    status = "pass" if all(gates.values()) and not errors else "fail"
    report = {
        "audit_schema_version": "prediction_dataset_v2_day6_audit_v1",
        "status": status,
        "results_dir": str(root),
        "frozen_collection_config_sha256": frozen["collection_config_sha256"],
        "resume_invariant_sha256": preflight.get("resume_invariant_sha256"),
        "rollout_count": len(rollouts),
        "manifest_count": len(manifests),
        "sample_count": len(sample_keys),
        "rollouts_per_cell": dict(rollouts_per_cell),
        "samples_per_cell": dict(samples_per_cell),
        "rollouts_per_split": dict(rollouts_per_split),
        "samples_per_split": dict(samples_per_split),
        "reactive_summary": {
            "trigger_rollout_coverage": trigger_coverage,
            "mean_active_fraction": (
                float(np.mean(active_fractions)) if active_fractions else None
            ),
            "minimum_target_speed_mps": (
                min(minimum_speeds) if minimum_speeds else None
            ),
            "trigger_onset_min_s": min(trigger_onsets) if trigger_onsets else None,
            "trigger_onset_max_s": max(trigger_onsets) if trigger_onsets else None,
        },
        "safety_summary": {
            "native_carla_collision_event_count": sum(collision_per_cell.values()),
            "collision_events_per_cell": dict(collision_per_cell),
            "note": (
                "Collision evidence is mandatory, but non-zero observed outcomes are "
                "reported rather than filtered or rerun."
            ),
        },
        "paired_s1_s0_summary": {
            "pair_count": len(paired),
            "median_max_target_position_separation_m": (
                float(
                    np.median(
                        [item["max_target_position_separation_m"] for item in paired]
                    )
                )
                if paired
                else None
            ),
            "pairs": paired,
        },
        "observed_collection_contracts": list(observed_contracts.values()),
        "reactive_parameter_hashes": sorted(parameter_hashes),
        "gates": gates,
        "error_count": len(errors),
        "errors": errors[:200],
    }
    atomic_write_json(args.output_json, report)
    print(json.dumps({key: report[key] for key in ("status", "rollout_count", "manifest_count", "sample_count", "gates", "error_count")}, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
