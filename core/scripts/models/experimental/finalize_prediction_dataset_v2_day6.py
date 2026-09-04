#!/usr/bin/env python3
"""Create the Day 6 analysis manifest and success marker after a passing audit."""

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
from datetime import datetime, timezone
from pathlib import Path


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--audit-json", required=True)
    parser.add_argument("--contract-json", required=True)
    parser.add_argument("--preflight-json", required=True)
    args = parser.parse_args()

    root = Path(args.results_dir).resolve()
    audit_path = Path(args.audit_json).resolve()
    contract_path = Path(args.contract_json).resolve()
    preflight_path = Path(args.preflight_json).resolve()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if audit.get("status") != "pass" or not all(audit.get("gates", {}).values()):
        raise ValueError("Day 6 audit is not passing; refusing completion marker")
    if preflight.get("status") != "pass" or not all(preflight.get("checks", {}).values()):
        raise ValueError("Day 6 preflight is not passing; refusing completion marker")

    patterns = (
        "day6_*",
        "protocol_snapshot/*",
        "prediction_dataset_manifests.txt",
        "*/batch_summary.txt",
        "*/batch_subruns.json",
        "*/batch_events.jsonl",
        "*/environment.json",
        "*/applied_tuning_configs.json",
        "*/scenario_*/scenario_run_summary.json",
        "*/scenario_*/scenario_steps.csv",
        "*/scenario_*/prediction_dataset/prediction_dataset_manifest.json",
    )
    selected = set()
    for pattern in patterns:
        selected.update(path for path in root.glob(pattern) if path.is_file())
    selected.discard(root / "DAY6_COMPLETE.json")
    selected.discard(root / "day6_analysis_manifest.json")
    # Runner/nohup logs are still being appended while this finalizer prints.
    # They remain in the result directory but cannot receive a stable hash here.
    selected = {path for path in selected if path.suffix != ".log"}
    files = [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(selected)
    ]
    analysis_manifest = {
        "schema_version": "day6_analysis_manifest_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "results_dir": str(root),
        "file_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
        "note": (
            "This compact manifest covers audit/control metadata, every rollout "
            "summary and step CSV, and every prediction manifest. Raw rasters, "
            "pickles and labeled JSONL remain under their rollout directories."
        ),
    }
    analysis_path = root / "day6_analysis_manifest.json"
    atomic_write(analysis_path, analysis_manifest)
    completion = {
        "schema_version": "day6_complete_v1",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "results_dir": str(root),
        "rollout_count": audit["rollout_count"],
        "manifest_count": audit["manifest_count"],
        "sample_count": audit["sample_count"],
        "frozen_collection_config_sha256": audit[
            "frozen_collection_config_sha256"
        ],
        "resume_invariant_sha256": contract["resume_invariant_sha256"],
        "audit_sha256": file_sha256(audit_path),
        "preflight_sha256": file_sha256(preflight_path),
        "analysis_manifest_sha256": file_sha256(analysis_path),
    }
    atomic_write(root / "DAY6_COMPLETE.json", completion)
    print(json.dumps(completion, indent=2))


if __name__ == "__main__":
    main()
