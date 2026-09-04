#!/usr/bin/env python3
"""Copy only allowlisted compact evidence into the publication tree."""

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
import shutil
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


PUBLICATION_EVIDENCE_MANIFEST = "PUBLICATION_EVIDENCE_MANIFEST.json"
FORBIDDEN_EVIDENCE_SUFFIXES = (
    ".log",
    ".jsonl",
    ".mp4",
    ".avi",
    ".ckpt",
    ".h5",
    ".pb",
    ".pt",
    ".pth",
    ".zip",
    ".tar",
    ".tar.gz",
    ".tar.xz",
    ".tar.bz2",
)

FUTURE_MASK_PATHS = (
    "OFFLINE_AUDIT_COMPLETE.json",
    "audits/",
    "figures/",
    "paper_outputs/",
    "postprocess/offline_cells.csv",
    "postprocess/offline_synthesis.json",
    "postprocess/selection_freeze.json",
    "postprocess/training_audit.json",
    "postprocess/training_curve_audit_final.json",
    "protocol/EXTENSION_PROTOCOL.json",
    "protocol/PIPELINE_STAGE_COMPLETE.json",
)

JOINT60_PATHS = (
    "JOINT60_INTEGRITY_AUDIT.json",
    "JOINT60_COMMAND_PATH_BY_ROLLOUT.csv",
    "JOINT60_COMMAND_PATH_SUMMARY.json",
    "formal_supervisor_on_assertive_40_v2_reference_integrity/FROZEN_PROTOCOL.json",
    "formal_supervisor_on_assertive_40_v2_reference_integrity/FORMAL_COMPLETE.json",
    "formal_supervisor_on_assertive_40_v2_reference_integrity/ON40_INTEGRITY_AUDIT.json",
    "formal_supervisor_off_assertive_20_v2_reference_integrity/FROZEN_PROTOCOL.json",
    "formal_supervisor_off_assertive_20_v2_reference_integrity/FORMAL_COMPLETE.json",
    "formal_supervisor_off_assertive_20_v2_reference_integrity/OFF20_INTEGRITY_AUDIT.json",
)


def _safe_relative(value: str) -> PurePosixPath:
    relative = PurePosixPath(value.rstrip("/"))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"Allowlist path is not repository-relative: {value}")
    return relative


def _forbidden_suffix(path: Path) -> bool:
    lower = path.name.lower()
    return any(lower.endswith(suffix) for suffix in FORBIDDEN_EVIDENCE_SUFFIXES)


def _selected_files(source_root: Path, allowlist: Sequence[str]) -> list[Path]:
    selected: set[Path] = set()
    resolved_root = source_root.resolve()
    for entry in allowlist:
        relative = _safe_relative(entry)
        candidate = source_root.joinpath(*relative.parts)
        if not candidate.exists() and not candidate.is_symlink():
            raise FileNotFoundError(f"Missing required evidence path: {relative}")
        if candidate.is_symlink():
            raise ValueError(f"Symlink evidence is forbidden: {relative}")
        if candidate.is_dir():
            directory_files = sorted(path for path in candidate.rglob("*") if path.is_file())
            if not directory_files:
                raise ValueError(f"Allowlisted evidence directory is empty: {relative}")
            selected.update(directory_files)
        elif candidate.is_file():
            selected.add(candidate)
        else:
            raise ValueError(f"Unsupported evidence path type: {relative}")

    for path in sorted(selected):
        relative = path.relative_to(source_root)
        internal_parent = path.parent
        internal_symlink = False
        while internal_parent != source_root:
            if internal_parent.is_symlink():
                internal_symlink = True
                break
            internal_parent = internal_parent.parent
        if path.is_symlink() or internal_symlink:
            raise ValueError(f"Symlink evidence is forbidden: {relative}")
        if _forbidden_suffix(path):
            raise ValueError(f"Forbidden evidence suffix: {relative}")
        try:
            path.resolve().relative_to(resolved_root)
        except ValueError as error:
            raise ValueError(f"Evidence escapes source root: {relative}") from error
    return sorted(selected)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize_collection(
    source_root: Path,
    output_root: Path,
    *,
    allowlist: Sequence[str],
    collection_id: str,
) -> dict[str, object]:
    """Copy one evidence collection and write a deterministic hash manifest."""

    if not source_root.is_dir() or source_root.is_symlink():
        raise ValueError(f"Evidence source must be a real directory: {source_root}")
    selected = _selected_files(source_root, allowlist)
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for source in selected:
        relative = source.relative_to(source_root)
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.is_symlink():
            raise ValueError(f"Refusing to overwrite target symlink: {relative}")
        shutil.copy2(source, target)
        records.append(
            {
                "source_path": relative.as_posix(),
                "target_path": relative.as_posix(),
                "bytes": target.stat().st_size,
                "sha256": _sha256(target),
            }
        )

    report: dict[str, object] = {
        "schema_version": "publication_evidence_manifest_v1",
        "status": "pass",
        "collection_id": collection_id,
        "source_root_policy": "caller_supplied_external_path_not_recorded",
        "allowlist": list(allowlist),
        "file_count": len(records),
        "total_bytes": sum(int(record["bytes"]) for record in records),
        "files": records,
        "excluded_by_default": [
            "raw rollout trajectories",
            "training logs",
            "model checkpoints",
            "videos",
            "archives",
            "credentials and licence files",
        ],
    }
    manifest = output_root / PUBLICATION_EVIDENCE_MANIFEST
    manifest.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def materialize_all(
    future_mask_root: Path, joint60_root: Path, output_root: Path
) -> dict[str, object]:
    future = materialize_collection(
        future_mask_root,
        output_root / "future_mask_v4e_120",
        allowlist=FUTURE_MASK_PATHS,
        collection_id="future_mask_v4e_120",
    )
    joint = materialize_collection(
        joint60_root,
        output_root / "weighted_smpc_v2_recovery" / "provenance",
        allowlist=JOINT60_PATHS,
        collection_id="weighted_smpc_joint60_provenance",
    )
    return {
        "schema_version": "publication_evidence_materialization_v1",
        "status": "pass",
        "collections": {
            "future_mask_v4e_120": future,
            "weighted_smpc_joint60_provenance": joint,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--future-mask-root", required=True, type=Path)
    parser.add_argument("--joint60-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    payload = materialize_all(
        args.future_mask_root, args.joint60_root, args.output_root
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
