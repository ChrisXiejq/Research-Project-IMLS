#!/usr/bin/env python3
"""Package the frozen Day 8 test evidence without model weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
from pathlib import Path


VARIANTS = ("B1", "B2-M", "B2-D", "T1", "T2")
SUBSETS = ("all", "assertive", "reactive", "pre_response", "response_active")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.test_dir).resolve()
    output = Path(args.output).resolve()
    selection_path = root / "DAY8_MODEL_SELECTION_FROZEN.json"
    selection = json.loads(selection_path.read_text())
    files = [
        selection_path,
        root / "day8_frozen_test_summary.json",
        root / "DAY8_TEST_COMPLETE.json",
    ]
    for variant in VARIANTS:
        seed = int(selection["representatives_for_single_test_pass"][variant]["seed"])
        files.extend(root / variant / f"seed_{seed}" / f"test_{subset}.json" for subset in SUBSETS)
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing Day 8 test evidence: {missing[:5]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
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
        "contains_all_five_frozen_representatives": True,
    }
    manifest_path = output.with_suffix(output.suffix + ".json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
