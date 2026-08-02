#!/usr/bin/env python3
"""Prepare restart-safe Day 12 dataset/model/result bundles for off-site copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path
from typing import Any, Iterable


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_hash(path: Path) -> dict[str, Any]:
    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total = 0
    for item in files:
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(item).encode("ascii"))
        total += item.stat().st_size
    return {
        "path": str(path),
        "files": len(files),
        "bytes": total,
        "sha256_tree": digest.hexdigest(),
    }


def file_record(path: Path) -> dict[str, Any]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def valid_existing(path: Path) -> bool:
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not checksum_path.is_file():
        return False
    expected = checksum_path.read_text(encoding="utf-8").strip().split()[0]
    return expected == sha256(path)


def write_checksum(path: Path) -> None:
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum_path.write_text(f"{sha256(path)}  {path.name}\n", encoding="utf-8")


def atomic_tar(path: Path, members: Iterable[tuple[Path, str]]) -> None:
    if valid_existing(path):
        return
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists():
        temporary.unlink()
    with tarfile.open(temporary, mode="w:gz", compresslevel=1) as archive:
        for source, arcname in members:
            if not source.exists():
                raise FileNotFoundError(source)
            archive.add(source, arcname=arcname, recursive=True)
    os.replace(temporary, path)
    write_checksum(path)


def atomic_copy(source: Path, destination: Path) -> None:
    if valid_existing(destination):
        return
    if not source.is_file():
        raise FileNotFoundError(source)
    temporary = destination.with_name(destination.name + ".partial")
    if temporary.exists():
        temporary.unlink()
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)
    write_checksum(destination)


def dataset_members(day6: Path) -> list[tuple[Path, str]]:
    members: list[tuple[Path, str]] = []
    for name in (
        "DAY6_COMPLETE.json",
        "day6_collection_audit.json",
        "day6_run_contract.json",
        "day6_analysis_manifest.json",
        "protocol_snapshot",
    ):
        path = day6 / name
        if path.exists():
            members.append((path, f"day6/{name}"))
    prediction_dirs = sorted(day6.glob("S*/scenario_*/prediction_dataset"))
    if len(prediction_dirs) != 200:
        raise ValueError(f"Expected 200 prediction_dataset directories, found {len(prediction_dirs)}")
    for prediction_dir in prediction_dirs:
        relative = prediction_dir.relative_to(day6)
        members.append((prediction_dir, f"day6/{relative}"))
    return members


def verify_completion(path: Path, expected_status: str = "pass") -> None:
    payload = read_json(path)
    if payload.get("status") != expected_status:
        raise ValueError(f"Completion marker is not {expected_status}: {path}")


def package(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    day6 = args.day6_results.resolve()
    day7 = args.day7_results.resolve()
    day8 = args.day8_results.resolve()
    day10 = args.day10_results.resolve()
    day11 = args.day11_results.resolve()
    selection_path = args.selection_freeze.resolve()
    preflight_path = args.day9_preflight.resolve()
    b0_model = args.b0_model.resolve()

    verify_completion(day6 / "DAY6_COMPLETE.json")
    verify_completion(day7 / "DAY7_COMPLETE.json")
    verify_completion(day10 / "DAY10_COMPLETE.json")
    verify_completion(day11 / "DAY11_COMPLETE.json")
    selection = read_json(selection_path)
    preflight = read_json(preflight_path)
    if selection.get("status") != "pass" or preflight.get("status") != "pass":
        raise ValueError("Day8 selection or Day9 deployment preflight is not pass")

    representatives = selection["representatives_for_single_test_pass"]
    model_members: list[tuple[Path, str]] = [(selection_path, "models/DAY8_MODEL_SELECTION_FROZEN.json")]
    model_records: dict[str, Any] = {}
    for variant, frozen in sorted(representatives.items()):
        seed = int(frozen["seed"])
        run_dir = day8 / "runs" / variant / f"seed_{seed}"
        model_dir = run_dir / "best_model"
        observed = artifact_hash(model_dir)
        expected = frozen["model"]["sha256_tree"]
        if observed["sha256_tree"] != expected:
            raise ValueError(f"{variant}: model tree hash mismatch")
        model_records[variant] = {**observed, "expected_sha256_tree": expected, "seed": seed}
        model_members.append((model_dir, f"models/{variant}/seed_{seed}/best_model"))
        for name in ("calibration.json", "run_config.json", "history.csv", "TRAINING_COMPLETE.json", "FIT_COMPLETE.json"):
            path = run_dir / name
            if path.exists():
                model_members.append((path, f"models/{variant}/seed_{seed}/{name}"))

    b0_expected = preflight["b0"]["deployment"]["model_artifact"]["sha256_tree"]
    b0_observed = artifact_hash(b0_model)
    if b0_observed["sha256_tree"] != b0_expected:
        raise ValueError("B0 model tree hash mismatch")
    model_records["B0"] = {**b0_observed, "expected_sha256_tree": b0_expected}
    model_members.append((b0_model, "models/B0/pretrained_model"))
    for path, arcname in (
        (day7 / "interaction_normalization_train.json", "models/shared/interaction_normalization_train.json"),
        (args.anchors.resolve(), "models/shared/l5kit_clusters_16.npy"),
        (preflight_path, "models/day9_deployment_preflight.json"),
    ):
        model_members.append((path, arcname))

    dataset_archive = output / "day12_v2_prediction_dataset_bundle.tar.gz"
    models_archive = output / "day12_frozen_model_packages.tar.gz"
    atomic_tar(dataset_archive, dataset_members(day6))
    atomic_tar(models_archive, model_members)

    day10_copy = output / "day10_formal_snapshot.tar.gz"
    day11_copy = output / "day11_timing_shift_snapshot.tar.gz"
    atomic_copy(args.day10_snapshot.resolve(), day10_copy)
    atomic_copy(args.day11_snapshot.resolve(), day11_copy)

    bundles = {
        "dataset": file_record(dataset_archive),
        "frozen_models": file_record(models_archive),
        "day10_full_results": file_record(day10_copy),
        "day11_full_results": file_record(day11_copy),
    }
    payload = {
        "schema_version": "day12_critical_asset_backup_manifest_v1",
        "status": "prepared_for_offsite_copy",
        "offsite_copy_verified": False,
        "bundles": bundles,
        "model_artifacts": model_records,
        "source_markers": {
            "day6_complete": file_record(day6 / "DAY6_COMPLETE.json"),
            "day7_complete": file_record(day7 / "DAY7_COMPLETE.json"),
            "day8_selection_freeze": file_record(selection_path),
            "day10_complete": file_record(day10 / "DAY10_COMPLETE.json"),
            "day11_complete": file_record(day11 / "DAY11_COMPLETE.json"),
        },
        "resume_semantics": "Each completed bundle is skipped only when its sidecar SHA-256 matches; partial bundles are rebuilt atomically.",
    }
    manifest_path = output / "day12_critical_asset_backup_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    complete = {
        "schema_version": "day12_asset_backup_server_stage_v1",
        "status": "pass",
        "offsite_copy_pending": True,
        "manifest_sha256": sha256(manifest_path),
        "bundles": {name: record["sha256"] for name, record in bundles.items()},
    }
    (output / "DAY12_ASSET_BACKUP_SERVER_STAGE_COMPLETE.json").write_text(
        json.dumps(complete, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day6-results", required=True, type=Path)
    parser.add_argument("--day7-results", required=True, type=Path)
    parser.add_argument("--day8-results", required=True, type=Path)
    parser.add_argument("--selection-freeze", required=True, type=Path)
    parser.add_argument("--day9-preflight", required=True, type=Path)
    parser.add_argument("--b0-model", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--day10-results", required=True, type=Path)
    parser.add_argument("--day11-results", required=True, type=Path)
    parser.add_argument("--day10-snapshot", required=True, type=Path)
    parser.add_argument("--day11-snapshot", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    payload = package(parse_args())
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
