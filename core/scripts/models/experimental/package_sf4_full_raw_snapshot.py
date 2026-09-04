#!/usr/bin/env python3
"""Create a deterministic, receipt-verified full SF4 raw snapshot.

Unlike the compact transfer package, this archive contains every canonical
scenario artifact (including ``scenario_result.pkl`` and ``scenario_steps.csv``)
and every attempt-provenance file.  It is therefore sufficient to recompute
the footprint/bounding-box separation audit without access to the live server
tree.  Source files are never moved or deleted.
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
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from r3_attempt_manager import RAW_REQUIRED_FILES, read_json, valid_receipt


SCHEMA = "sf4_supervisor_behavioural_authority_full_raw_snapshot_v1"
MANIFEST_SCHEMA = "sf4_supervisor_behavioural_authority_full_raw_snapshot_files_manifest_v1"
ARCHIVE_ROOT = "sf4_supervisor_behavioural_authority_full_raw_snapshot"
MARKER_NAME = "SF4_FULL_RAW_SNAPSHOT_COMPLETE.json"
EXPECTED_ROLLOUTS = 80
TOP_LEVEL_REQUIRED = (
    "SF4_PREFLIGHT_COMPLETE.json",
    "sf4_supervisor_behavioural_authority_run_contract.json",
    "sf4_town05_spawn_preflight.json",
    "sf4_b1_deployment_preflight.json",
    "sf4_source_validation.json",
    "sf4_init_generation_revalidation.json",
    "sf4_prepare_report.json",
    "analysis/SF4_ANALYSIS_COMPLETE.json",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_bytes(
        path,
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def sidecar_path(output: Path) -> Path:
    return Path(str(output) + ".json")


def files_manifest_path(output: Path) -> Path:
    return Path(str(output) + ".files.json")


def _inside(root: Path, path: Path, label: str) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents:
        raise ValueError("%s escapes SF4_RESULTS: %s" % (label, path))
    return resolved


def _regular_files(root: Path, directory: Path) -> List[Path]:
    _inside(root, directory, "snapshot directory")
    paths = []
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("Full SF4 snapshot rejects symlinks: %s" % path)
        if path.is_file():
            paths.append(_inside(root, path, "snapshot input"))
    return sorted(paths)


def collect(
    root: Path, prereg: Path
) -> Tuple[List[Path], Dict[str, Any], bytes, str]:
    root = root.resolve()
    prereg = prereg.resolve()
    contract_path = root / "sf4_supervisor_behavioural_authority_run_contract.json"
    contract = read_json(contract_path)
    analysis = read_json(root / "analysis/SF4_ANALYSIS_COMPLETE.json")
    if (
        contract.get("schema_version")
        != "sf4_supervisor_behavioural_authority_run_contract_v1"
        or int(contract.get("expected_rollouts", -1)) != EXPECTED_ROLLOUTS
        or analysis.get("status") != "pass"
        or int(analysis.get("observed_rollouts", -1)) != EXPECTED_ROLLOUTS
        or (analysis.get("implementation_manipulation_gate") or {}).get("status")
        != "pass"
    ):
        raise ValueError("SF4 contract/analysis is incomplete")
    if not prereg.is_file() or sha256(prereg) != (contract.get("hashes") or {}).get("prereg_json"):
        raise ValueError("Full snapshot preregistration does not match run contract")

    paths: List[Path] = []
    for relative in TOP_LEVEL_REQUIRED:
        path = root / relative
        if not path.is_file():
            raise ValueError("Missing full-snapshot artifact: %s" % path)
        paths.append(path.resolve())
    for directory in (root / "_frozen_tuning", root / "analysis"):
        if not directory.is_dir():
            raise ValueError("Missing full-snapshot directory: %s" % directory)
        paths.extend(_regular_files(root, directory))

    execution_order = contract.get("execution_order")
    if not isinstance(execution_order, list) or len(execution_order) != EXPECTED_ROLLOUTS:
        raise ValueError("SF4 contract execution order is incomplete")
    expected_receipts = set()
    rollout_records = []
    for item in execution_order:
        if not isinstance(item, Mapping):
            raise ValueError("Invalid SF4 execution-order record")
        cell_id = str(item.get("cell_id"))
        init_id = int(item.get("ego_init_id", -1))
        cell = root / cell_id
        receipt_path = cell / ("SF4_ROLLOUT_%d_COMPLETE.json" % init_id)
        expected_receipts.add(receipt_path.resolve())
        if not valid_receipt(cell, cell_id, init_id, "SF4"):
            raise ValueError("Invalid receipt/raw/attempt provenance: %s" % receipt_path)
        receipt = read_json(receipt_path)
        scenario = _inside(root, cell / str(receipt["scenario_dir"]), "scenario")
        attempt_root = _inside(
            root, cell / "_attempts" / ("init_%d" % init_id), "attempt provenance"
        )
        for relative in RAW_REQUIRED_FILES:
            path = scenario / relative
            if not path.is_file():
                raise ValueError("Full snapshot lacks required raw evidence: %s" % path)
        paths.append(receipt_path.resolve())
        paths.extend(_regular_files(root, scenario))
        paths.extend(_regular_files(root, attempt_root))
        rollout_records.append(
            {
                "cell_id": cell_id,
                "ego_init_id": init_id,
                "receipt": receipt_path.relative_to(root).as_posix(),
                "receipt_sha256": sha256(receipt_path),
                "raw_evidence_sha256": receipt["raw_evidence_sha256"],
                "accepted_attempt": int(receipt["accepted_attempt"]),
                "attempt_record_sha256": receipt["attempt_record_sha256"],
                "attempt_ledger_sha256": receipt[
                    "attempt_ledger_sha256_at_receipt"
                ],
            }
        )

    observed_receipts = {
        path.resolve()
        for path in root.glob("SF4_*/SF4_ROLLOUT_*_COMPLETE.json")
    }
    if observed_receipts != expected_receipts:
        raise ValueError("SF4 receipt set differs from the frozen 80-rollout contract")
    for cell_id in sorted({str(item["cell_id"]) for item in execution_order}):
        cell = root / cell_id
        for path in sorted(cell.glob("postcarla_trajectory_gate.*")):
            if path.is_file():
                paths.append(path.resolve())
        if not (cell / "postcarla_trajectory_gate.json").is_file():
            raise ValueError("Missing footprint-separation gate for %s" % cell_id)

    unique = sorted(
        set(paths), key=lambda path: path.relative_to(root).as_posix()
    )
    file_records = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in unique
    ]
    prereg_bytes = prereg.read_bytes()
    prereg_archive_path = (
        "_external/SF4_SUPERVISOR_BEHAVIOURAL_AUTHORITY_PREREG.json"
    )
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "status": "pass",
        "source_files_deleted": False,
        "files": file_records,
        "external_files": [
            {
                "path": prereg_archive_path,
                "bytes": len(prereg_bytes),
                "sha256": sha256_bytes(prereg_bytes),
            }
        ],
        "rollouts": sorted(
            rollout_records,
            key=lambda item: (item["cell_id"], item["ego_init_id"]),
        ),
        "coverage": {
            "expected_rollouts": EXPECTED_ROLLOUTS,
            "receipt_raw_and_attempt_provenance_verified": True,
            "all_canonical_scenario_files_included": True,
            "all_attempt_provenance_files_included": True,
            "scenario_result_pickle_included_per_rollout": True,
            "scenario_steps_csv_included_per_rollout": True,
            "server_wall_time_recomputation_supported": True,
            "controller_acceptance_and_raw_status_recomputation_supported": True,
            "postcarla_bbox_separation_gate_included_per_cell": True,
            "bbox_and_separation_recomputation_supported": True,
        },
        "operational_exclusions": [
            "sf4_runner.log and transient PID/lock files",
            "the snapshot archive and its derived sidecars/marker",
        ],
    }
    return unique, manifest, prereg_bytes, prereg_archive_path


def tar_member(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.size = size
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _verify_archive(
    output: Path, manifest: Mapping[str, Any], manifest_bytes: bytes
) -> None:
    expected = {
        str(item["path"]): item
        for item in list(manifest.get("files", []))
        + list(manifest.get("external_files", []))
    }
    with tarfile.open(output, "r:gz") as archive:
        members = {item.name: item for item in archive.getmembers() if item.isfile()}
        embedded_name = ARCHIVE_ROOT + "/SF4_FULL_RAW_FILES_MANIFEST.json"
        embedded_member = members.get(embedded_name)
        if embedded_member is None:
            raise ValueError("Full snapshot lacks embedded files manifest")
        embedded = archive.extractfile(embedded_member)
        if embedded is None or embedded.read() != manifest_bytes:
            raise ValueError("Embedded full-snapshot manifest drift")
        for relative, record in expected.items():
            name = ARCHIVE_ROOT + "/" + relative
            member = members.get(name)
            if member is None or int(member.size) != int(record["bytes"]):
                raise ValueError("Missing/size-drift full-snapshot member: %s" % name)
            handle = archive.extractfile(member)
            if handle is None or sha256_stream(handle) != record["sha256"]:
                raise ValueError("Hash-drift full-snapshot member: %s" % name)
        if len(members) != len(expected) + 1:
            raise ValueError("Unexpected member in full SF4 raw snapshot")


def _write_derived_metadata(
    output: Path,
    manifest: Mapping[str, Any],
    manifest_bytes: bytes,
    *,
    reused: bool,
) -> Dict[str, Any]:
    atomic_bytes(files_manifest_path(output), manifest_bytes)
    payload = {
        "schema_version": SCHEMA,
        "status": "pass",
        "archive": output.name,
        "archive_bytes": output.stat().st_size,
        "archive_sha256": sha256(output),
        "files_manifest": files_manifest_path(output).name,
        "files_manifest_sha256": sha256_bytes(manifest_bytes),
        "included_source_files": len(manifest.get("files", [])),
        "included_external_files": len(manifest.get("external_files", [])),
        "observed_rollouts": len(manifest.get("rollouts", [])),
        "full_raw_evidence": True,
        "bbox_and_separation_recomputation_supported": True,
        "server_wall_time_recomputation_supported": True,
        "controller_acceptance_and_raw_status_recomputation_supported": True,
        "source_files_deleted": False,
    }
    atomic_json(sidecar_path(output), payload)
    marker = {
        "schema_version": "sf4_full_raw_snapshot_complete_v1",
        "status": "pass",
        "formal_evidence": True,
        "observed_rollouts": len(manifest.get("rollouts", [])),
        "archive": output.name,
        "archive_bytes": output.stat().st_size,
        "archive_sha256": payload["archive_sha256"],
        "archive_sidecar": sidecar_path(output).name,
        "archive_sidecar_sha256": sha256(sidecar_path(output)),
        "files_manifest": files_manifest_path(output).name,
        "files_manifest_sha256": payload["files_manifest_sha256"],
        "receipt_raw_and_attempt_provenance_verified": True,
        "bbox_and_separation_recomputation_supported": True,
        "server_wall_time_recomputation_supported": True,
        "controller_acceptance_and_raw_status_recomputation_supported": True,
        "source_files_deleted": False,
    }
    atomic_json(output.parent / MARKER_NAME, marker)
    returned = dict(payload)
    returned["reused_verified_archive"] = reused
    return returned


def create(root: Path, output: Path, prereg: Path) -> Dict[str, Any]:
    root = root.resolve()
    output = output.resolve()
    if output.parent != root:
        raise ValueError("Full SF4 snapshot must be written directly inside SF4_RESULTS")
    paths, manifest, prereg_bytes, prereg_archive_path = collect(root, prereg)
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if output.is_file():
        _verify_archive(output, manifest, manifest_bytes)
        return _write_derived_metadata(
            output, manifest, manifest_bytes, reused=True
        )

    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
            ) as archive:
                embedded_name = ARCHIVE_ROOT + "/SF4_FULL_RAW_FILES_MANIFEST.json"
                archive.addfile(
                    tar_member(embedded_name, len(manifest_bytes)),
                    io.BytesIO(manifest_bytes),
                )
                for path in paths:
                    relative = path.relative_to(root).as_posix()
                    with path.open("rb") as handle:
                        archive.addfile(
                            tar_member(
                                ARCHIVE_ROOT + "/" + relative,
                                path.stat().st_size,
                            ),
                            handle,
                        )
                archive.addfile(
                    tar_member(
                        ARCHIVE_ROOT + "/" + prereg_archive_path,
                        len(prereg_bytes),
                    ),
                    io.BytesIO(prereg_bytes),
                )
    os.replace(temporary, output)
    _verify_archive(output, manifest, manifest_bytes)
    return _write_derived_metadata(output, manifest, manifest_bytes, reused=False)


def verify(output: Path) -> Dict[str, Any]:
    output = output.resolve()
    sidecar = read_json(sidecar_path(output))
    manifest = read_json(files_manifest_path(output))
    manifest_bytes = files_manifest_path(output).read_bytes()
    marker = read_json(output.parent / MARKER_NAME)
    coverage = manifest.get("coverage") or {}
    if (
        sidecar.get("schema_version") != SCHEMA
        or sidecar.get("status") != "pass"
        or sidecar.get("archive") != output.name
        or int(sidecar.get("archive_bytes", -1)) != output.stat().st_size
        or int(sidecar.get("observed_rollouts", -1)) != EXPECTED_ROLLOUTS
        or sidecar.get("archive_sha256") != sha256(output)
        or sidecar.get("files_manifest_sha256") != sha256_bytes(manifest_bytes)
        or sidecar.get("server_wall_time_recomputation_supported") is not True
        or sidecar.get("controller_acceptance_and_raw_status_recomputation_supported") is not True
        or manifest.get("schema_version") != MANIFEST_SCHEMA
        or manifest.get("status") != "pass"
        or len(manifest.get("rollouts", [])) != EXPECTED_ROLLOUTS
        or coverage.get("bbox_and_separation_recomputation_supported") is not True
        or coverage.get("server_wall_time_recomputation_supported") is not True
        or coverage.get("controller_acceptance_and_raw_status_recomputation_supported") is not True
        or coverage.get("receipt_raw_and_attempt_provenance_verified") is not True
        or marker.get("schema_version") != "sf4_full_raw_snapshot_complete_v1"
        or marker.get("status") != "pass"
        or int(marker.get("observed_rollouts", -1)) != EXPECTED_ROLLOUTS
        or marker.get("archive") != output.name
        or int(marker.get("archive_bytes", -1)) != output.stat().st_size
        or marker.get("archive_sha256") != sidecar.get("archive_sha256")
        or marker.get("archive_sidecar_sha256") != sha256(sidecar_path(output))
        or marker.get("files_manifest_sha256")
        != sidecar.get("files_manifest_sha256")
        or marker.get("source_files_deleted") is not False
        or marker.get("bbox_and_separation_recomputation_supported") is not True
        or marker.get("server_wall_time_recomputation_supported") is not True
        or marker.get("controller_acceptance_and_raw_status_recomputation_supported") is not True
        or marker.get("receipt_raw_and_attempt_provenance_verified") is not True
    ):
        raise ValueError("Full SF4 snapshot sidecar/marker verification failed")
    _verify_archive(output, manifest, manifest_bytes)
    return {
        "schema_version": SCHEMA,
        "status": "pass",
        "archive_sha256": sidecar["archive_sha256"],
        "files_manifest_sha256": sidecar["files_manifest_sha256"],
        "observed_rollouts": sidecar["observed_rollouts"],
        "bbox_and_separation_recomputation_supported": True,
        "server_wall_time_recomputation_supported": True,
        "controller_acceptance_and_raw_status_recomputation_supported": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prereg", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        payload = verify(args.output)
    else:
        if args.results_dir is None or args.prereg is None:
            parser.error("--results-dir and --prereg are required when creating")
        payload = create(args.results_dir, args.output, args.prereg)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
