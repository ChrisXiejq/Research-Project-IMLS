#!/usr/bin/env python3
"""Convert the external pipeline readiness signal into a hash-bound stage receipt."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload
from thesis_core_v3_execute import completion_valid
from thesis_core_v3_postprocess import (
    FUTURE_VALIDITY_CONTRACT,
    HELDOUT_EVALUATION_SCHEMA,
    OFFLINE_SYNTHESIS_SCHEMA,
    SELECTION_FREEZE_SCHEMA,
    _hash_valid,
    _stage_complete,
)
from thesis_core_v3_runs import validate_thesis_core_manifest


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--training-root", required=True, type=Path)
    parser.add_argument("--calibration-root", required=True, type=Path)
    parser.add_argument("--latency-root", required=True, type=Path)
    parser.add_argument("--heldout-root", required=True, type=Path)
    parser.add_argument("--selection-freeze", required=True, type=Path)
    parser.add_argument("--synthesis", required=True, type=Path)
    parser.add_argument("--pipeline-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    manifest = load(args.manifest)
    validate_thesis_core_manifest(manifest)
    receipt = load(args.pipeline_receipt)
    if (
        not _hash_valid(receipt, "receipt_sha256")
        or receipt.get("schema_version")
        != "capacity_history_future_mask_v4_running_pipeline_receipt"
    ):
        raise ValueError("Invalid running-pipeline receipt")
    freeze = load(args.selection_freeze)
    if (
        not _hash_valid(freeze, "freeze_sha256")
        or freeze.get("schema_version") != SELECTION_FREEZE_SCHEMA
        or freeze.get("status") != "pass"
        or freeze.get("future_validity_contract") != FUTURE_VALIDITY_CONTRACT
        or len(freeze.get("runs", [])) != 27
    ):
        raise ValueError("Invalid V4 selection freeze")
    synthesis = load(args.synthesis)
    if (
        not _hash_valid(synthesis, "synthesis_sha256")
        or synthesis.get("schema_version") != OFFLINE_SYNTHESIS_SCHEMA
        or synthesis.get("status") != "pass"
        or synthesis.get("selection_freeze_sha256") != freeze.get("freeze_sha256")
        or int(synthesis.get("evaluated_runs", -1)) != 27
    ):
        raise ValueError("Invalid V4 offline synthesis")

    runs = []
    for spec in manifest["runs"]:
        run_id = str(spec["run_id"])
        completion_path = args.training_root / run_id / "TRAINING_COMPLETE.json"
        if (
            not completion_valid(completion_path, spec)
            or not _stage_complete("calibrate", run_id, args.calibration_root, None)
            or not _stage_complete("latency", run_id, args.latency_root, None)
            or not _stage_complete("heldout", run_id, args.heldout_root, freeze)
        ):
            raise ValueError(f"Incomplete or invalid pipeline stage: {run_id}")
        completion = load(completion_path)
        runs.append(
            {
                "run_id": run_id,
                "completion_sha256": completion["completion_sha256"],
                "model_cell_id": spec["model_cell_id"],
                "seed": int(spec["seed"]),
            }
        )
    payload = {
        "schema_version": "capacity_history_future_mask_v4_pipeline_stage_complete",
        "status": "pass",
        "corrected_runs": len(runs),
        "calibrations": 27,
        "latency_reports": 27,
        "heldout_reports": 27,
        "future_validity_contract": FUTURE_VALIDITY_CONTRACT,
        "heldout_schema": HELDOUT_EVALUATION_SCHEMA,
        "pipeline_receipt_sha256": receipt["receipt_sha256"],
        "manifest_sha256": sha256_file(args.manifest),
        "selection_freeze_sha256": freeze["freeze_sha256"],
        "synthesis_sha256": synthesis["synthesis_sha256"],
        "runs": runs,
        "source_sha256": {
            name: sha256_file(Path(__file__).with_name(name))
            for name in (
                "thesis_core_v3_postprocess.py",
                "evaluate_thesis_core_cached_v3.py",
                "capacity_study_v3_analysis.py",
            )
        },
    }
    payload["stage_receipt_sha256"] = sha256_payload(payload)
    atomic_json(args.output, payload)
    print(json.dumps({"status": "pass", "runs": len(runs)}))


if __name__ == "__main__":
    main()
