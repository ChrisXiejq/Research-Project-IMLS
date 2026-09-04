#!/usr/bin/env python3
"""Package compact Day 8 evidence without duplicating model weights."""

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
import tarfile
from pathlib import Path


RUN_FILES = {
    "FIT_COMPLETE.json",
    "TRAINING_COMPLETE.json",
    "run_config.json",
    "history.csv",
    "calibration.json",
    "validation_all.json",
    "validation_assertive.json",
    "validation_reactive.json",
    "validation_pre_response.json",
    "validation_response_active.json",
}
OPTIONAL_RUN_FILES = {"RESUME_PROVENANCE.json"}
VARIANTS = ("B1", "B2-M", "B2-D", "T1", "T2")
SEEDS = (11, 23, 37)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.results_dir).resolve()
    output = Path(args.output).resolve()
    files = [root / "day8_validation_summary.json", root / "DAY8_VALIDATION_COMPLETE.json"]
    files.extend(
        root / "runs" / variant / f"seed_{seed}" / filename
        for variant in VARIANTS
        for seed in SEEDS
        for filename in sorted(RUN_FILES)
    )
    files.extend(
        path
        for path in sorted((root / "runs").glob("*/seed_*/*"))
        if path.name in OPTIONAL_RUN_FILES and path.is_file()
    )
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing compact Day 8 evidence: {missing[:5]}")
    temporary = output.with_suffix(output.suffix + ".tmp")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(temporary, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=str(path.relative_to(root)))
    os.replace(temporary, output)
    manifest = {
        "status": "pass",
        "archive": str(output),
        "archive_sha256": sha256(output),
        "files": len(files),
        "excludes_model_weights": True,
    }
    manifest_path = output.with_suffix(output.suffix + ".json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
