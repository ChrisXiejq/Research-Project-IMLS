#!/usr/bin/env python3
"""Verify copied Day 12 critical-asset bundles against the server manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.backup_dir.resolve()
    manifest_path = root / "day12_critical_asset_backup_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = []
    for name, expected in manifest["bundles"].items():
        path = root / Path(expected["path"]).name
        if not path.is_file():
            raise FileNotFoundError(path)
        observed = sha256(path)
        if observed != expected["sha256"] or path.stat().st_size != int(expected["bytes"]):
            raise ValueError(f"{name}: copied bundle does not match manifest")
        if path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                member_count = sum(1 for _ in archive)
            if member_count == 0:
                raise ValueError(f"{name}: empty tar archive")
        else:
            member_count = None
        records.append({"bundle": name, "file": path.name, "sha256": observed, "members": member_count})
    result = {
        "schema_version": "day12_offsite_backup_verification_v1",
        "status": "pass",
        "manifest_sha256": sha256(manifest_path),
        "bundles": records,
    }
    output = root / "DAY12_OFFSITE_BACKUP_VERIFIED.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
