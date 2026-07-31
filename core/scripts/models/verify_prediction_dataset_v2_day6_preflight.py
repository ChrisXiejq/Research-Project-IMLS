#!/usr/bin/env python3
"""Verify the frozen Day 6 collection contract and guard resume invariants."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_MODEL_WEIGHTS_TREE_SHA256 = (
    "bc4c18b39fe8a7adcaa9119a31231d3e0e2226cb44b10f63492a8386f61aa0ed"
)
EXPECTED_MODEL_ANCHORS_SHA256 = (
    "52ab777b9bf695ed56f069b96cbce337014a47f457ed19c638abfb1cde6aa982"
)


def canonical_hash(value):
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_manifest(path):
    root = Path(path).resolve()
    files = []
    for item in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        files.append(
            {
                "relative_path": item.relative_to(root).as_posix(),
                "size_bytes": item.stat().st_size,
                "sha256": file_sha256(item),
            }
        )
    return {
        "path": str(root),
        "file_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
        "tree_sha256": canonical_hash(files),
    }


def source_paths(repo_dir):
    scripts = Path(repo_dir).resolve() / "core" / "scripts"
    carla = scripts / "carla"
    scenario = carla / "scenarios"
    return {
        "collection_runner": carla / "run_give_way_prediction_dataset_v2.sh",
        "batch_runner": carla / "run_all_scenarios.py",
        "scenario_runner": scenario / "run_intersection_scenario.py",
        "scenario": scenario / "scenario_uk_give_way.json",
        "intersection_geometry": scenario / "intersection_01.csv",
        "tuning_config": scenario
        / "tuning_configs"
        / "give_way_reduced_clear_path_release_v12_current_best.json",
        "reactive_target_agent": carla
        / "policies"
        / "defensive_reactive_agent.py",
        "straight_line_target_agent": carla / "policies" / "straight_line_agent.py",
        "agent_history_rasterizer": carla / "rasterizer" / "agent_history.py",
        "prediction_deployment": scripts / "models" / "deploy_multipath_model.py",
        "interaction_sequence": scripts / "models" / "interaction_sequence.py",
        "prediction_input_contract": scripts
        / "models"
        / "prediction_input_contract.py",
        "gmm_prediction": scripts / "evaluation" / "gmm_prediction.py",
    }


def formal_init_manifest(repo_dir):
    init_dir = (
        Path(repo_dir).resolve()
        / "core"
        / "scripts"
        / "carla"
        / "scenarios"
        / "inits"
        / "paper_intersection_50"
    )
    paths = sorted(init_dir.glob("ego_init_*.json"))
    return [
        {"filename": path.name, "sha256": file_sha256(path)} for path in paths
    ]


def atomic_write_json(path, value):
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)


def build_report(repo_dir, frozen_path, model_weights, model_anchors):
    repo_dir = Path(repo_dir).resolve()
    frozen_path = Path(frozen_path).resolve()
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    collection = frozen["collection_configuration"]
    expected_sources = collection["source_artifact_sha256"]
    paths = source_paths(repo_dir)
    actual_sources = {name: file_sha256(path) for name, path in paths.items()}
    init_manifest = formal_init_manifest(repo_dir)
    weights_path = repo_dir / "core" / "scripts" / "models" / model_weights
    anchors_path = repo_dir / "core" / "scripts" / "models" / model_anchors
    model_snapshot = {
        "weights": tree_manifest(weights_path),
        "anchors": {
            "path": str(anchors_path),
            "size_bytes": anchors_path.stat().st_size,
            "sha256": file_sha256(anchors_path),
        },
    }
    day6_wrapper = (
        repo_dir
        / "core"
        / "scripts"
        / "carla"
        / "run_day6_formal_prediction_dataset_v2.sh"
    )
    checks = {
        "frozen_collection_hash": canonical_hash(collection)
        == frozen["collection_config_sha256"],
        "reactive_parameter_hash": canonical_hash(frozen["reactive_parameters"])
        == frozen["reactive_parameters_sha256"],
        "all_13_source_artifacts_present": set(paths) == set(expected_sources),
        "all_source_artifact_hashes_match": actual_sources == expected_sources,
        "exactly_50_formal_inits": len(init_manifest) == 50,
        "formal_init_set_hash_matches": canonical_hash(init_manifest)
        == collection["formal_init_set_sha256"],
        "model_weights_name_matches": model_weights
        == collection["prediction_contract"]["model_weights"],
        "model_anchors_name_matches": model_anchors
        == collection["prediction_contract"]["model_anchors"],
        "model_artifacts_nonempty": model_snapshot["weights"]["file_count"] > 0
        and model_snapshot["anchors"]["size_bytes"] > 0,
        "model_weights_tree_hash_matches_day5": model_snapshot["weights"][
            "tree_sha256"
        ]
        == EXPECTED_MODEL_WEIGHTS_TREE_SHA256,
        "model_anchors_hash_matches_day5": model_snapshot["anchors"]["sha256"]
        == EXPECTED_MODEL_ANCHORS_SHA256,
        "day6_wrapper_present": day6_wrapper.is_file(),
    }
    invariant = {
        "collection_config_sha256": frozen["collection_config_sha256"],
        "reactive_parameters_sha256": frozen["reactive_parameters_sha256"],
        "source_artifact_sha256": actual_sources,
        "formal_init_set_sha256": canonical_hash(init_manifest),
        "model_weights_tree_sha256": model_snapshot["weights"]["tree_sha256"],
        "model_anchors_sha256": model_snapshot["anchors"]["sha256"],
        "day6_wrapper_sha256": file_sha256(day6_wrapper),
        "runtime": {
            "init_start": 1,
            "init_end": 50,
            "cells": list(collection["cells"]),
            "expected_rollouts": 200,
            "prediction_logging_stride": collection["prediction_contract"][
                "prediction_logging_stride"
            ],
            "prediction_logging_horizon": collection["prediction_contract"][
                "prediction_logging_horizon"
            ],
            "prediction_logging_save_raster": collection["prediction_contract"][
                "prediction_logging_save_raster"
            ],
            "prediction_git_commit": collection["prediction_contract"]["git_commit"],
        },
    }
    return {
        "schema_version": "day6_preflight_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all(checks.values()) else "fail",
        "repo_dir": str(repo_dir),
        "frozen_config": str(frozen_path),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "checks": checks,
        "resume_invariant": invariant,
        "resume_invariant_sha256": canonical_hash(invariant),
        "model_artifacts": model_snapshot,
        "source_artifact_paths": {name: str(path) for name, path in paths.items()},
        "formal_init_manifest": init_manifest,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", required=True)
    parser.add_argument("--frozen-config", required=True)
    parser.add_argument("--contract-json", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--model-weights", required=True)
    parser.add_argument("--model-anchors", required=True)
    args = parser.parse_args()

    report = build_report(
        args.repo_dir, args.frozen_config, args.model_weights, args.model_anchors
    )
    contract_path = Path(args.contract_json).resolve()
    if contract_path.exists():
        existing = json.loads(contract_path.read_text(encoding="utf-8"))
        matches = existing.get("resume_invariant_sha256") == report.get(
            "resume_invariant_sha256"
        )
        report["checks"]["resume_invariant_matches_existing_contract"] = matches
        if not matches:
            report["status"] = "fail"
    else:
        report["checks"]["resume_invariant_matches_existing_contract"] = True
        atomic_write_json(contract_path, report)
        report["contract_created"] = True

    atomic_write_json(args.report_json, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "resume_invariant_sha256": report["resume_invariant_sha256"],
                "checks": report["checks"],
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "pass" and all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
