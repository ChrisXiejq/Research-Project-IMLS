#!/usr/bin/env python3
"""Freeze validation-only Day 8 representatives before any test access."""

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
from pathlib import Path


VARIANTS = ("B1", "B2-M", "B2-D", "T1", "T2")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_hash(path: Path) -> dict:
    if path.is_file():
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total = 0
    for item in files:
        digest.update(str(item.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(sha256_file(item).encode())
        total += item.stat().st_size
    return {"path": str(path), "files": len(files), "bytes": total, "sha256_tree": digest.hexdigest()}


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    root = Path(args.results_dir).resolve()
    summary_path = root / "day8_validation_summary.json"
    completion_path = root / "DAY8_VALIDATION_COMPLETE.json"
    summary = json.loads(summary_path.read_text())
    completion = json.loads(completion_path.read_text())
    test_dir = root / "final_test_v1"
    existing_test_outputs = sorted(test_dir.glob("**/test_*.json")) if test_dir.exists() else []
    output = Path(args.output_json).resolve()
    if existing_test_outputs and not output.exists():
        raise ValueError(
            "Test outputs already exist but no prior selection freeze is present; "
            "refusing to create a post-test freeze"
        )
    if summary.get("status") != "pass" or completion.get("status") != "pass":
        raise ValueError("Day 8 validation gate has not passed")
    if summary.get("observed_runs") != 15 or summary.get("test_accessed") is not False:
        raise ValueError("Selection freeze requires 15 runs and untouched test")
    if completion.get("validation_summary_sha256") != sha256_file(summary_path):
        raise ValueError("Validation summary hash does not match completion marker")

    ranked = {item["variant"]: item for item in summary["variant_ranking"]}
    runs = {(item["variant"], int(item["seed"])): item for item in summary["runs"]}
    representatives = {}
    for variant in VARIANTS:
        seed = int(ranked[variant]["representative_seed"])
        run_summary = runs[(variant, seed)]
        run_dir = root / "runs" / variant / f"seed_{seed}"
        model = artifact_hash(run_dir / "best_model")
        expected_model = run_summary["training"]["model_artifact"]
        if model.get("sha256_tree") != expected_model.get("sha256_tree"):
            raise ValueError(f"Model artifact drift for {variant}/seed_{seed}")
        calibration_path = run_dir / "calibration.json"
        calibration = json.loads(calibration_path.read_text())
        if calibration.get("fit_split") != "val":
            raise ValueError(f"Calibration is not validation-only: {calibration_path}")
        representatives[variant] = {
            "seed": seed,
            "selection_rule": ranked[variant]["representative_rule"],
            "validation_rank": 1
            + next(index for index, item in enumerate(summary["variant_ranking"]) if item["variant"] == variant),
            "model": model,
            "calibration": artifact_hash(calibration_path),
            "calibration_parameters": calibration["parameters"],
            "training_completion": artifact_hash(run_dir / "TRAINING_COMPLETE.json"),
        }

    selected_variant = str(summary["provisional_selected_variant"])
    selected_seed = int(summary["provisional_representative_seed"])
    if representatives[selected_variant]["seed"] != selected_seed:
        raise ValueError("Selected representative is inconsistent with validation summary")
    payload = {
        "schema_version": "day8_model_selection_freeze_v1",
        "status": "pass",
        "selection_basis": "validation_only",
        "test_accessed_at_freeze": False,
        "validation_summary": artifact_hash(summary_path),
        "validation_completion": artifact_hash(completion_path),
        "representatives_for_single_test_pass": representatives,
        "closed_loop_selected_variant": selected_variant,
        "closed_loop_selected_seed": selected_seed,
        "closed_loop_selection_locked_before_test": True,
        "test_policy": "evaluate all five frozen representatives once; test cannot change selection or training",
    }
    if output.exists():
        existing = json.loads(output.read_text())
        if existing != payload:
            raise ValueError(f"Existing selection freeze differs: {output}")
        print(json.dumps({"status": "skip_identical_freeze", "output": str(output)}))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
