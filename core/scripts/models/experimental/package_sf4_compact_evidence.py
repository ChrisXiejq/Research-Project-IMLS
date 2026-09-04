#!/usr/bin/env python3
"""Create and verify a deterministic compact SF4 evidence package.

The archive retains all analysis products, formal receipts, attempt provenance,
post-CARLA gates and the debug/control manifests needed to audit the causal
intervention. Heavy prediction JSONL, pickle trajectories and per-step CSV are
left in the canonical server result directory and remain hash-bound by each
rollout receipt.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import gzip
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from r3_attempt_manager import valid_receipt


SCHEMA = "sf4_supervisor_behavioural_authority_compact_evidence_package_v1"
ARCHIVE_ROOT = "sf4_supervisor_behavioural_authority_compact_evidence"
TOP_LEVEL = (
    "SF4_COMPLETE.json",
    "SF4_FULL_RAW_SNAPSHOT_COMPLETE.json",
    "SF4_PREFLIGHT_COMPLETE.json",
    "sf4_supervisor_behavioural_authority_run_contract.json",
    "sf4_town05_spawn_preflight.json",
    "sf4_b1_deployment_preflight.json",
    "sf4_source_validation.json",
    "sf4_init_generation_revalidation.json",
    "sf4_prepare_report.json",
    "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.json",
    "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.files.json",
)
SCENARIO_FILES = (
    "scenario_run_summary.json",
    "scenario_rollout_config.json",
    "smpc_debug_setup.json",
    "smpc_debug_steps.jsonl",
    "smpc_completion.json",
    "prediction_deployment_manifest.json",
    "prediction_dataset/prediction_dataset_config.json",
    "prediction_dataset/prediction_dataset_manifest.json",
)
EXCLUDED_HEAVY = (
    "prediction_dataset/prediction_dataset_raw.jsonl",
    "prediction_dataset/prediction_dataset_labeled.jsonl",
    "scenario_result.pkl",
    "scenario_steps.csv",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object: %s" % path)
    return value


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def sidecar_path(output: Path) -> Path:
    return Path(str(output) + ".json")


def files_manifest_path(output: Path) -> Path:
    return Path(str(output) + ".files.json")


def collect(root: Path) -> List[Path]:
    complete = read_json(root / "SF4_COMPLETE.json")
    analysis = read_json(root / "analysis/SF4_ANALYSIS_COMPLETE.json")
    if (
        complete.get("status") != "pass"
        or complete.get("observed_rollouts") != 80
        or analysis.get("status") != "pass"
        or analysis.get("observed_rollouts") != 80
        or (analysis.get("implementation_manipulation_gate") or {}).get("status")
        != "pass"
    ):
        raise ValueError("SF4 completion/analysis gate is incomplete")
    paths = []
    for relative in TOP_LEVEL:
        path = root / relative
        if not path.is_file():
            raise ValueError("Missing compact-package artifact: %s" % path)
        paths.append(path)
    paths.extend(sorted(path for path in (root / "_frozen_tuning").glob("*.json") if path.is_file()))
    paths.extend(sorted(path for path in (root / "analysis").rglob("*") if path.is_file()))
    receipts = sorted(root.glob("SF4_*/SF4_ROLLOUT_*_COMPLETE.json"))
    if len(receipts) != 80:
        raise ValueError("Expected 80 SF4 receipts, found %d" % len(receipts))
    for receipt_path in receipts:
        receipt = read_json(receipt_path)
        cell = receipt_path.parent
        init_id = int(receipt.get("ego_init_id", -1))
        if not valid_receipt(cell, cell.name, init_id, "SF4"):
            raise ValueError("Invalid receipt/attempt provenance: %s" % receipt_path)
        scenario = cell / str(receipt["scenario_dir"])
        paths.append(receipt_path)
        gate = cell / "postcarla_trajectory_gate.json"
        if not gate.is_file():
            raise ValueError("Missing post-CARLA gate: %s" % gate)
        paths.append(gate)
        for key in ("attempt_record", "attempt_ledger"):
            path = cell / str(receipt.get(key, ""))
            if not path.is_file():
                raise ValueError("Missing receipt provenance %s: %s" % (key, path))
            paths.append(path)
        attempt_root = cell / "_attempts" / ("init_%d" % init_id)
        paths.extend(
            sorted(path for path in attempt_root.rglob("*.json") if path.is_file())
        )
        for relative in SCENARIO_FILES:
            path = scenario / relative
            if path.is_file():
                paths.append(path)
            elif relative != "smpc_completion.json":
                raise ValueError("Missing compact scenario artifact: %s" % path)
    unique = {path.resolve(): path for path in paths}
    resolved_root = root.resolve()
    for path in unique:
        if resolved_root not in path.parents:
            raise ValueError("Archive input escapes SF4 root: %s" % path)
    return sorted(unique, key=lambda path: path.relative_to(resolved_root).as_posix())


def manifest(root: Path, paths: Iterable[Path]) -> Dict[str, Any]:
    records = []
    for path in paths:
        records.append(
            {
                "path": path.resolve().relative_to(root.resolve()).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return {
        "schema_version": "sf4_compact_files_manifest_v1",
        "status": "pass",
        "files": records,
        "excluded_heavy_raw_files": list(EXCLUDED_HEAVY),
        "exclusion_contract": (
            "Heavy raw files remain in the canonical SF4_RESULTS tree and are "
            "individually plus aggregately hash-bound by the included receipts."
        ),
    }


def tar_member(name: str, value: bytes) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.size = len(value)
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def create(root: Path, output: Path) -> Dict[str, Any]:
    paths = collect(root)
    files_manifest = manifest(root, paths)
    rendered_manifest = (json.dumps(files_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
            archive.addfile(
                tar_member(ARCHIVE_ROOT + "/SF4_COMPACT_FILES_MANIFEST.json", rendered_manifest),
                io.BytesIO(rendered_manifest),
            )
            for path in paths:
                value = path.read_bytes()
                relative = path.resolve().relative_to(root.resolve()).as_posix()
                archive.addfile(
                    tar_member(ARCHIVE_ROOT + "/" + relative, value),
                    io.BytesIO(value),
                )
    atomic_bytes(output, buffer.getvalue())
    atomic_bytes(files_manifest_path(output), rendered_manifest)
    payload = {
        "schema_version": SCHEMA,
        "status": "pass",
        "archive": str(output.resolve()),
        "archive_bytes": output.stat().st_size,
        "archive_sha256": sha256(output),
        "files_manifest": str(files_manifest_path(output).resolve()),
        "files_manifest_sha256": sha256_bytes(rendered_manifest),
        "included_files": len(files_manifest["files"]),
        "raw_evidence_location": str(root.resolve()),
        "heavy_raw_files_excluded_but_receipt_bound": True,
    }
    atomic_json(sidecar_path(output), payload)
    return payload


def verify(output: Path) -> Dict[str, Any]:
    sidecar = read_json(sidecar_path(output))
    files_manifest = read_json(files_manifest_path(output))
    if (
        sidecar.get("schema_version") != SCHEMA
        or sidecar.get("status") != "pass"
        or sidecar.get("archive_sha256") != sha256(output)
        or sidecar.get("files_manifest_sha256") != sha256(files_manifest_path(output))
    ):
        raise ValueError("SF4 compact package sidecar/hash verification failed")
    expected = {item["path"]: item for item in files_manifest.get("files", [])}
    with tarfile.open(output, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        embedded_name = ARCHIVE_ROOT + "/SF4_COMPACT_FILES_MANIFEST.json"
        embedded = archive.extractfile(members[embedded_name])
        if embedded is None or sha256_bytes(embedded.read()) != sidecar["files_manifest_sha256"]:
            raise ValueError("Embedded SF4 files manifest drift")
        for relative, record in expected.items():
            name = ARCHIVE_ROOT + "/" + relative
            member = members.get(name)
            if member is None or int(member.size) != int(record["bytes"]):
                raise ValueError("Missing/size-drift archive member: %s" % name)
            handle = archive.extractfile(member)
            if handle is None or sha256_bytes(handle.read()) != record["sha256"]:
                raise ValueError("Hash-drift archive member: %s" % name)
        if len(members) != len(expected) + 1:
            raise ValueError("Unexpected member in SF4 compact archive")
    return {
        "schema_version": SCHEMA,
        "status": "pass",
        "archive_sha256": sidecar["archive_sha256"],
        "included_files": len(expected),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        payload = verify(args.output.resolve())
    else:
        if args.results_dir is None:
            parser.error("--results-dir is required unless --verify-only is used")
        payload = create(args.results_dir.resolve(), args.output.resolve())
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
