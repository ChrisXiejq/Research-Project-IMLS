#!/usr/bin/env python3
"""Create and verify immutable closed-loop evidence archives.

The default profile preserves the historical compact package.  ``r3-final``
adds raw trajectory pickles, frozen inputs, attempt provenance, environment
metadata and analysis outputs so every registered R3 result can be recomputed
without launching CARLA again.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
from typing import Any, Iterable


INCLUDE_NAMES = {
    "scenario_run_summary.json",
    "scenario_rollout_config.json",
    "prediction_deployment_manifest.json",
    "smpc_debug_setup.json",
    "smpc_debug_steps.jsonl",
    "smpc_completion.json",
    "scenario_steps.csv",
    "prediction_dataset_config.json",
    "prediction_dataset_manifest.json",
    "prediction_dataset_raw.jsonl",
    "prediction_dataset_labeled.jsonl",
    "postcarla_trajectory_gate.json",
    "risk_by_conflict_distance_summary.json",
    "risk_by_conflict_distance_summary.csv",
    "risk_by_conflict_distance_comparison.csv",
    "df_full.csv",
    "paper_metrics_summary.csv",
    "comparison_manifest.jsonl",
    "day11_analysis_summary.json",
    "day11_rollout_metrics.csv",
    "day11_cell_summary.csv",
    "day11_paired_contrasts.csv",
    "day11_contract_resume_provenance.json",
    "day11_audit_repair_provenance.json",
}

R3_REQUIRED_ROOT_FILES = {
    "r3_run_contract.json",
    "r3_corrected_matrix_audit.json",
    "R3_DATA_COMPLETE.json",
    "R3_PREFLIGHT_COMPLETE.json",
    "r3_deployment_preflight.json",
    "tuning_r3_frozen.json",
    "r3_environment.json",
    "r3_execution_source_manifest.json",
    "r3_runner_frozen.log",
    "analysis/R3_ANALYSIS_COMPLETE.json",
    "analysis/R3_STUDY_STOP_GATE.json",
}
R3_REQUIRED_FROZEN_CONTRACTS = {
    "DAY7_COMPLETE.json",
    "DAY8_COMPLETE.json",
    "DAY8_MODEL_SELECTION_FROZEN.json",
    "R1_CORRECTED_CONTROL_CONTRACT.json",
    "R2_COMPLETE.json",
    "G2_ROUTE_DECISION.json",
    "M0_R3_ANALYSIS_CONTRACT.json",
    "M0_R3_ANALYSIS_CONTRACT_v2.json",
    "M0_R3_ANALYSIS_CONTRACT_v2.md",
    "M0_AMENDMENT_COMPLETE.json",
    "R3_INIT_GENERATION_MANIFEST.json",
    "scenario_uk_give_way.json",
    "day5_frozen_collection.json",
}
R3_EXCLUDED_SUFFIXES = {
    ".avi",
    ".gif",
    ".h5",
    ".jpeg",
    ".jpg",
    ".mp4",
    ".pb",
    ".png",
    ".tif",
    ".tiff",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def ensure_inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"Evidence path escapes results directory: {path}") from error
    return resolved


def compact_files(root: Path, output: Path, explicit: set[Path]) -> list[Path]:
    return sorted(
        {
            path.resolve()
            for path in root.rglob("*")
            if path.is_file() and path.name in INCLUDE_NAMES and path.resolve() != output
        }
        | explicit
    )


def r3_files(root: Path, output: Path, explicit: set[Path], contract: dict[str, Any]) -> list[Path]:
    missing = [relative for relative in sorted(R3_REQUIRED_ROOT_FILES) if not (root / relative).is_file()]
    frozen = root / "_frozen_contracts"
    missing.extend(
        str(Path("_frozen_contracts") / name)
        for name in sorted(R3_REQUIRED_FROZEN_CONTRACTS)
        if not (frozen / name).is_file()
    )
    expected_inits = {int(value) for value in contract.get("ego_init_ids", [])}
    missing.extend(
        str(Path("_frozen_inits_101_105") / f"ego_init_{init_id}.json")
        for init_id in sorted(expected_inits)
        if not (root / "_frozen_inits_101_105" / f"ego_init_{init_id}.json").is_file()
    )
    expected = int(contract.get("expected_rollouts", 0))
    receipts = sorted(root.glob("*/R3_ROLLOUT_*_COMPLETE.json"))
    trajectories = sorted(root.glob("*/scenario_*/scenario_result.pkl"))
    ledgers = sorted(root.glob("*/_attempts/init_*/attempt_ledger.json"))
    if len(receipts) != expected:
        missing.append(f"rollout receipts: expected {expected}, found {len(receipts)}")
    if len(trajectories) != expected:
        missing.append(f"scenario_result.pkl: expected {expected}, found {len(trajectories)}")
    if len(ledgers) != expected:
        missing.append(f"attempt ledgers: expected {expected}, found {len(ledgers)}")
    if missing:
        raise FileNotFoundError(f"Missing R3 final evidence: {missing}")

    self_artifacts = {
        output,
        Path(str(output) + ".json"),
        Path(str(output) + ".files.json"),
        output.with_suffix(output.suffix + ".tmp"),
    }
    files: set[Path] = set(explicit)
    files.discard((root / "R3_COMPLETE.json").resolve())
    for path in root.rglob("*"):
        if not path.is_file() or path.resolve() in self_artifacts or path.name.endswith(".tmp"):
            continue
        if path == root / "r3_runner.log":
            # The live tee target changes when the packager prints.  Its
            # immutable pre-package copy is r3_runner_frozen.log.
            continue
        if path == root / "R3_COMPLETE.json":
            # The final marker is written only after this archive has passed
            # full member/hash verification.  A stale marker from a prior
            # interrupted rebuild must never become archive evidence.
            continue
        relative = path.relative_to(root)
        parts = relative.parts
        include = (
            path.name in INCLUDE_NAMES
            or path.name == "scenario_result.pkl"
            or path.name.startswith("R3_ROLLOUT_")
            or relative.as_posix() in R3_REQUIRED_ROOT_FILES
            or (parts and parts[0] in {"_attempts", "_frozen_contracts", "_frozen_inits_101_105", "analysis"})
            or (len(parts) > 1 and parts[1] == "_attempts")
            or (len(parts) == 1 and (path.name.startswith("r3_") or path.name.startswith("R3_")))
        )
        if include and path.suffix.lower() not in R3_EXCLUDED_SUFFIXES:
            if path.is_symlink():
                raise ValueError(f"R3 final evidence must be a byte-for-byte copy, not a symlink: {path}")
            files.add(ensure_inside(root, path))
    return sorted(files)


def file_manifest(root: Path, files: Iterable[Path], profile: str) -> dict[str, Any]:
    entries = []
    for path in files:
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return {
        "schema_version": "closed_loop_snapshot_files_v2",
        "status": "pass",
        "profile": profile,
        "files": entries,
        "file_count": len(entries),
        "total_uncompressed_bytes": sum(item["bytes"] for item in entries),
    }


def render_manifest(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def normalized_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.mode = 0o644
    return info


def verify_archive(archive_path: Path, manifest_payload: dict[str, Any]) -> dict[str, Any]:
    expected = {item["path"]: item for item in manifest_payload["files"]}
    with tarfile.open(archive_path, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        if "SNAPSHOT_FILES_MANIFEST.json" not in members:
            raise RuntimeError("Archive is missing SNAPSHOT_FILES_MANIFEST.json")
        embedded_handle = archive.extractfile(members["SNAPSHOT_FILES_MANIFEST.json"])
        if embedded_handle is None:
            raise RuntimeError("Unable to read embedded snapshot manifest")
        embedded = json.loads(embedded_handle.read())
        if embedded != manifest_payload:
            raise RuntimeError("Embedded snapshot manifest differs from sidecar manifest")
        actual_names = set(members) - {"SNAPSHOT_FILES_MANIFEST.json"}
        if actual_names != set(expected):
            raise RuntimeError(
                f"Archive membership mismatch: missing={sorted(set(expected)-actual_names)}, "
                f"extra={sorted(actual_names-set(expected))}"
            )
        for name, item in expected.items():
            handle = archive.extractfile(members[name])
            if handle is None:
                raise RuntimeError(f"Unable to read archive member: {name}")
            data = handle.read()
            if len(data) != item["bytes"] or bytes_sha256(data) != item["sha256"]:
                raise RuntimeError(f"Archive member verification failed: {name}")
    return {
        "status": "pass",
        "verified_members": len(expected),
        "embedded_manifest_sha256": bytes_sha256(render_manifest(manifest_payload)),
    }


def build_snapshot(
    *,
    root: Path,
    contract_name: str,
    audit_name: str,
    complete_name: str,
    output: Path,
    profile: str,
    evidence: list[str],
) -> dict[str, Any]:
    root = root.resolve()
    output = output.resolve()
    required = {contract_name, audit_name, complete_name}
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing closed-loop evidence: {missing}")
    contract = json.loads((root / contract_name).read_text(encoding="utf-8"))
    explicit = {ensure_inside(root, root / name) for name in required | set(evidence)}
    preflight = contract.get("deployment_preflight_filename")
    if preflight:
        explicit.add(ensure_inside(root, root / preflight))
    for entry in (contract.get("tuning_sha256_by_offset") or {}).values():
        explicit.add(ensure_inside(root, root / entry["path"]))
    missing_explicit = [str(path) for path in explicit if not path.is_file()]
    if missing_explicit:
        raise FileNotFoundError(f"Missing contract-bound evidence: {missing_explicit}")
    files = (
        r3_files(root, output, explicit, contract)
        if profile == "r3-final"
        else compact_files(root, output, explicit)
    )
    manifest_payload = file_manifest(root, files, profile)
    manifest_bytes = render_manifest(manifest_payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in files:
                    archive.add(
                        path,
                        arcname=path.relative_to(root).as_posix(),
                        recursive=False,
                        filter=normalized_tarinfo,
                    )
                info = tarfile.TarInfo("SNAPSHOT_FILES_MANIFEST.json")
                info.size = len(manifest_bytes)
                info.mode = 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(manifest_bytes))
    os.replace(temporary, output)
    verification = verify_archive(output, manifest_payload)
    files_manifest_path = Path(str(output) + ".files.json")
    atomic_json(files_manifest_path, manifest_payload)
    snapshot_manifest = {
        "schema_version": "closed_loop_snapshot_v2",
        "status": "pass",
        "profile": profile,
        "archive": str(output),
        "archive_sha256": sha256(output),
        "archive_bytes": output.stat().st_size,
        "files_manifest": str(files_manifest_path),
        "files_manifest_sha256": sha256(files_manifest_path),
        "files": len(files),
        "total_uncompressed_bytes": manifest_payload["total_uncompressed_bytes"],
        "archive_verification": verification,
        "excludes_model_weights_rasters_and_video": True,
        "includes_raw_scenario_trajectories": profile == "r3-final",
    }
    sidecar = Path(str(output) + ".json")
    atomic_json(sidecar, snapshot_manifest)
    print(json.dumps(snapshot_manifest, indent=2, sort_keys=True))
    return snapshot_manifest


def verify_snapshot(output: Path) -> dict[str, Any]:
    output = output.resolve()
    sidecar = Path(str(output) + ".json")
    files_sidecar = Path(str(output) + ".files.json")
    if not output.is_file() or not sidecar.is_file() or not files_sidecar.is_file():
        raise FileNotFoundError("Snapshot archive or sidecars are missing")
    snapshot = json.loads(sidecar.read_text(encoding="utf-8"))
    manifest = json.loads(files_sidecar.read_text(encoding="utf-8"))
    if sha256(output) != snapshot.get("archive_sha256"):
        raise RuntimeError("Snapshot archive hash differs from sidecar")
    if sha256(files_sidecar) != snapshot.get("files_manifest_sha256"):
        raise RuntimeError("Snapshot files-manifest hash differs from sidecar")
    verification = verify_archive(output, manifest)
    result = {
        "status": "pass",
        "archive": str(output),
        "archive_sha256": sha256(output),
        "files_manifest_sha256": sha256(files_sidecar),
        **verification,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--contract")
    parser.add_argument("--audit")
    parser.add_argument("--complete")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile", choices=("compact", "r3-final"), default="compact")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        verify_snapshot(args.output)
        return
    missing = [name for name in ("results_dir", "contract", "audit", "complete") if getattr(args, name) is None]
    if missing:
        parser.error(f"required when creating an archive: {', '.join('--' + name.replace('_', '-') for name in missing)}")
    build_snapshot(
        root=args.results_dir,
        contract_name=args.contract,
        audit_name=args.audit,
        complete_name=args.complete,
        output=args.output,
        profile=args.profile,
        evidence=args.evidence,
    )


if __name__ == "__main__":
    main()
