#!/usr/bin/env python3
"""Freeze, materialise, and audit V3 fresh-data collection manifests."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from capacity_study_v3_protocol import (
    CHALLENGE_TEST_GROUPS,
    COLLECTION_CELLS,
    GENERAL_TEST_GROUPS,
    build_group_registry,
    atomic_json,
    classify_response_stratum,
    sha256_file,
    sha256_payload,
    validate_group_registry,
    write_immutable_manifest,
)
from prediction_dataset_utils import read_jsonl


CELL_DETAILS = {
    "S0_FIXED": ("assertive_constant_speed", "fixed_medium"),
    "S0_ADAPTIVE": ("assertive_constant_speed", "adaptive_floor_weak"),
    "S1_FIXED": ("defensive_reactive", "fixed_medium"),
    "S1_ADAPTIVE": ("defensive_reactive", "adaptive_floor_weak"),
}


def build_collection_manifest(
    registry: Mapping[str, Any], collection_set: str
) -> dict[str, Any]:
    validate_group_registry(registry)
    expected_groups = {
        "general_test": GENERAL_TEST_GROUPS,
        "interaction_challenge": CHALLENGE_TEST_GROUPS,
    }
    if collection_set not in expected_groups:
        raise ValueError(f"Unknown fresh collection set: {collection_set}")
    groups = expected_groups[collection_set]
    registry_by_id = {int(row["ego_init_id"]): row for row in registry["records"]}
    rollouts = []
    for group_id in groups:
        if registry_by_id[group_id]["group_set"] != collection_set:
            raise ValueError(f"Registry set mismatch for group {group_id}")
        for cell_id in COLLECTION_CELLS:
            target_style, ego_policy = CELL_DETAILS[cell_id]
            rollouts.append(
                {
                    "rollout_id": f"v3_{collection_set}_init_{group_id:02d}_{cell_id.lower()}",
                    "ego_init_id": group_id,
                    "cell_id": cell_id,
                    "target_style": target_style,
                    "ego_policy": ego_policy,
                    "status": "planned",
                }
            )
    expected_count = 40 if collection_set == "general_test" else 80
    payload = {
        "schema_version": "capacity_history_fresh_collection_v3",
        "status": "frozen",
        "collection_set": collection_set,
        "dataset_version": "give_way_capacity_history_prediction_v3.0",
        "protocol_id": f"town05_capacity_history_{collection_set}_v3",
        "feature_schema_id": "give_way_interaction_sequence_v2",
        "generated_without_candidate_model_outputs": True,
        "admission_rule": {
            "basis": "prospective initial geometry only",
            "candidate_model_outputs_forbidden": True,
            "posthoc_response_filtering_forbidden": True,
            "interaction_challenge_intent": (
                "cover the frozen -2.50..-0.25 and +0.25..+2.50 m offset "
                "strata to increase the chance of observing reactive onset/active windows"
            ),
            "response_trigger_is_guaranteed": False,
        },
        "group_registry_sha256": registry["registry_sha256"],
        "ego_init_ids": list(groups),
        "collection_cells": list(COLLECTION_CELLS),
        "expected_rollouts": expected_count,
        "rollouts": rollouts,
    }
    if collection_set == "interaction_challenge":
        offsets = [
            float(registry_by_id[group_id]["start_longitudinal_offset_m"])
            for group_id in groups
        ]
        payload["offset_strata"] = {
            "negative": sum(value < 0.0 for value in offsets),
            "positive": sum(value > 0.0 for value in offsets),
            "minimum_m": min(offsets),
            "maximum_m": max(offsets),
            "zero_excluded": all(value != 0.0 for value in offsets),
        }
    payload["manifest_sha256"] = sha256_payload(payload)
    return payload


def validate_collection_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    recorded = value.pop("manifest_sha256", None)
    value.pop("payload_sha256", None)
    if recorded != sha256_payload(value):
        raise ValueError("Fresh collection manifest hash mismatch")
    collection_set = str(payload["collection_set"])
    registry = build_group_registry()
    expected = build_collection_manifest(registry, collection_set)
    expected.pop("manifest_sha256")
    if value != expected:
        raise ValueError("Fresh collection manifest differs from frozen registry")
    pairs = {(row["ego_init_id"], row["cell_id"]) for row in payload["rollouts"]}
    expected_pairs = {
        (group_id, cell_id)
        for group_id in payload["ego_init_ids"]
        for cell_id in COLLECTION_CELLS
    }
    if pairs != expected_pairs or len(pairs) != payload["expected_rollouts"]:
        raise ValueError("Fresh collection does not contain exact four-cell pairing")
    return {
        "status": "pass",
        "collection_set": collection_set,
        "rollouts": len(pairs),
        "independent_groups": len(payload["ego_init_ids"]),
        "manifest_sha256": recorded,
    }


def materialize_init_files(
    registry: Mapping[str, Any], output_dir: str | Path
) -> dict[str, Any]:
    validate_group_registry(registry)
    root = Path(output_dir)
    records = []
    for row in registry["records"]:
        group_id = int(row["ego_init_id"])
        payload = {
            "start_longitudinal_offset": float(row["start_longitudinal_offset_m"]),
            "init_speed": float(row["init_speed_mps"]),
        }
        rendered = json.dumps(payload, sort_keys=True) + "\n"
        path = root / row["group_set"] / f"ego_init_{group_id:02d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"Frozen init drift: {path}")
        if not path.exists():
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(rendered, encoding="utf-8")
            os.replace(temporary, path)
        records.append(
            {
                "ego_init_id": group_id,
                "group_set": row["group_set"],
                "path": str(path),
                "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            }
        )
    return {"status": "pass", "init_files": len(records), "records": records}


def _infer_observed_cell(path: Path, payload: Mapping[str, Any]) -> str | None:
    for key in ("cell_id", "prediction_cell_id"):
        value = payload.get(key)
        if value in COLLECTION_CELLS:
            return str(value)
    for part in path.parts:
        if part in COLLECTION_CELLS:
            return part
    return None


def _infer_observed_init(path: Path, payload: Mapping[str, Any]) -> int | None:
    value = payload.get("ego_init_id")
    if value is not None:
        return int(value)
    match = re.search(r"ego_init_(\d+)", str(path))
    return int(match.group(1)) if match else None


def audit_collection_outputs(
    manifest: Mapping[str, Any], results_dir: str | Path
) -> dict[str, Any]:
    validate_collection_manifest(manifest)
    observed = []
    for path in sorted(Path(results_dir).rglob("prediction_dataset_manifest.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        observed.append(
            {
                "cell_id": _infer_observed_cell(path, payload),
                "ego_init_id": _infer_observed_init(path, payload),
                "path": str(path),
                "sha256": sha256_file(path),
            }
        )
    pairs = [(row["ego_init_id"], row["cell_id"]) for row in observed]
    expected = {(row["ego_init_id"], row["cell_id"]) for row in manifest["rollouts"]}
    counts = Counter(pairs)
    duplicates = sorted(pair for pair, count in counts.items() if count != 1)
    missing = sorted(expected - set(pairs))
    extra = sorted(set(pairs) - expected)
    status = "pass" if not duplicates and not missing and not extra and len(pairs) == len(expected) else "fail"
    return {
        "schema_version": "capacity_history_collection_audit_v3",
        "status": status,
        "collection_set": manifest["collection_set"],
        "expected_rollouts": len(expected),
        "observed_rollouts": len(pairs),
        "independent_groups": len({pair[0] for pair in pairs if pair[0] is not None}),
        "duplicates": duplicates,
        "missing": missing,
        "extra": extra,
        "observed": observed,
    }


def _sample_stratum(sample: Mapping[str, Any]) -> str:
    style = str(sample.get("target_style", ""))
    diagnostics = sample.get("target_reactive_diagnostics") or {}
    sample_time = sample.get(
        "sim_time_s",
        sample.get("simulation_time_s", sample.get("timestamp_s", 0.0)),
    )
    trigger_time = diagnostics.get("trigger_time_s")
    if trigger_time is None and diagnostics.get("triggered_this_step"):
        trigger_time = sample_time
    if trigger_time is None:
        if style == "defensive_reactive" and diagnostics.get("active"):
            return "response_active"
        return classify_response_stratum(
            target_style=style,
            sample_time_s=float(sample_time),
            trigger_time_s=None,
            reactive_active=bool(diagnostics.get("active")),
        )
    return classify_response_stratum(
        target_style=style,
        sample_time_s=float(sample_time),
        trigger_time_s=float(trigger_time),
        reactive_active=bool(diagnostics.get("active")),
    )


def seal_fresh_dataset(
    manifest: Mapping[str, Any], results_dir: str | Path, output_dir: str | Path
) -> dict[str, Any]:
    audit = audit_collection_outputs(manifest, results_dir)
    if audit["status"] != "pass":
        raise ValueError("Cannot seal an incomplete fresh collection")
    expected_pairs = {(row["ego_init_id"], row["cell_id"]) for row in manifest["rollouts"]}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "test.jsonl"
    temporary = destination.with_suffix(".jsonl.tmp")
    samples = 0
    support = Counter(
        {
            "assertive": 0,
            "reactive_pre_response": 0,
            "response_onset": 0,
            "response_active": 0,
        }
    )
    rollout_pairs = set()
    with temporary.open("w", encoding="utf-8") as handle:
        for jsonl_path in sorted(Path(results_dir).rglob("prediction_dataset_labeled.jsonl")):
            for sample in read_jsonl(str(jsonl_path)):
                pair = (int(sample["ego_init_id"]), str(sample["cell_id"]))
                if pair not in expected_pairs:
                    continue
                result = dict(sample)
                result["source_prediction_dataset_dir"] = str(jsonl_path.parent.resolve())
                result["fresh_collection_set"] = manifest["collection_set"]
                result["response_stratum_v3"] = _sample_stratum(result)
                handle.write(json.dumps(result, separators=(",", ":")) + "\n")
                samples += 1
                support[result["response_stratum_v3"]] += 1
                rollout_pairs.add(pair)
    os.replace(temporary, destination)
    if rollout_pairs != expected_pairs:
        raise ValueError("Sealed sample set lacks one or more planned rollouts")
    completion = {
        "schema_version": "capacity_history_fresh_dataset_v3",
        "status": "pass",
        "collection_set": manifest["collection_set"],
        "manifest_sha256": manifest["manifest_sha256"],
        "dataset_jsonl": {"path": str(destination), "sha256": sha256_file(destination)},
        "samples": samples,
        "rollouts": len(rollout_pairs),
        "independent_groups": len({pair[0] for pair in rollout_pairs}),
        "response_stratum_windows": dict(sorted(support.items())),
        "historical_group_overlap": sorted(
            {pair[0] for pair in rollout_pairs}.intersection(range(1, 51))
        ),
    }
    if completion["historical_group_overlap"]:
        raise ValueError("Fresh dataset overlaps historical groups")
    return write_immutable_manifest(output / "FRESH_DATASET_COMPLETE.json", completion)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--output-root", required=True, type=Path)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--manifest", required=True, type=Path)
    audit.add_argument("--results-dir", required=True, type=Path)
    audit.add_argument("--output", required=True, type=Path)
    seal = subparsers.add_parser("seal")
    seal.add_argument("--manifest", required=True, type=Path)
    seal.add_argument("--results-dir", required=True, type=Path)
    seal.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        registry = build_group_registry()
        validate_group_registry(registry)
        write_immutable_manifest(args.output_root / "group_registry.json", registry)
        materialize_init_files(registry, args.output_root / "inits")
        for collection_set in ("general_test", "interaction_challenge"):
            manifest = build_collection_manifest(registry, collection_set)
            validate_collection_manifest(manifest)
            write_immutable_manifest(
                args.output_root / f"{collection_set}_manifest.json", manifest
            )
        report = {"status": "pass", "output_root": str(args.output_root)}
    elif args.command == "audit":
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = audit_collection_outputs(manifest, args.results_dir)
        # An audit may legitimately fail while a resumable collection is only
        # partially complete.  Only the sealed completion gate is immutable.
        atomic_json(args.output, report)
    else:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = seal_fresh_dataset(manifest, args.results_dir, args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
