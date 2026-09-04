#!/usr/bin/env python3
"""Package compact T1/T2 interaction-context ablation evidence."""

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
    files = [root / "interaction_context_ablation_summary.json", root / "CONTEXT_ABLATION_COMPLETE.json"]
    files.extend(
        root / variant / mode / f"test_{subset}.json"
        for variant in ("T1", "T2")
        for mode in ("zero", "shuffle")
        for subset in ("all", "assertive", "reactive", "pre_response", "response_active")
    )
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing context-ablation evidence: {missing}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with tarfile.open(temporary, "w:gz") as archive:
        for path in sorted(files):
            archive.add(path, arcname=str(path.relative_to(root)))
    os.replace(temporary, output)
    manifest = {
        "schema_version": "interaction_context_ablation_snapshot_v1",
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
