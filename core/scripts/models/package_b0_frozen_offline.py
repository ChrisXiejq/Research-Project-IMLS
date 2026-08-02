#!/usr/bin/env python3
"""Package the small B0 offline bridge evidence without model weights or rasters."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
from pathlib import Path


INCLUDE = {
    "b0_validation_calibration.json",
    "b0_validation_evaluation.json",
    "b0_test_all.json",
    "b0_test_assertive.json",
    "b0_test_reactive.json",
    "b0_test_pre_response.json",
    "b0_test_response_active.json",
    "b0_frozen_offline_summary.json",
    "B0_OFFLINE_COMPLETE.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.results_dir.resolve()
    output = args.output.resolve()
    files = [root / name for name in sorted(INCLUDE)]
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing B0 offline evidence: {missing}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with tarfile.open(temporary, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=path.name)
    os.replace(temporary, output)
    manifest = {
        "schema_version": "b0_frozen_offline_snapshot_v1",
        "status": "pass",
        "archive": str(output),
        "archive_sha256": sha256(output),
        "files": len(files),
        "excludes_model_weights_and_rasters": True,
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
