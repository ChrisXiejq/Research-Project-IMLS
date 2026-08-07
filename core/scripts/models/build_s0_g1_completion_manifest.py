#!/usr/bin/env python3
"""Verify and freeze the complete S0-G1 distinction evidence batch."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from distinction_analysis_utils import atomic_write_json, sha256_file


MARKERS = {
    "S0": "00_baseline/S0_COMPLETE.json",
    "S1": "00_regression_gates/S1_COMPLETE.json",
    "E1": "01_physical_baselines/E1_COMPLETE.json",
    "E2": "02_input_ablations/E2_COMPLETE.json",
    "E3": "03_training_budget/E3_COMPLETE.json",
    "E4": "04_in_loop_prediction/E4_COMPLETE.json",
    "E5": "05_collision_and_geometry/E5_COMPLETE.json",
    "E6": "06_split_balance/E6_COMPLETE.json",
    "G1": "07_ml_claim_gate/G1_ML_CONTRIBUTION_FROZEN.json",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence_dir.resolve()
    stage_records = {}
    failures = []
    for stage, relative in MARKERS.items():
        path = root / relative
        if not path.exists():
            failures.append(f"missing:{relative}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        status = str(payload.get("status"))
        if not (status == "pass" or status.startswith("pass_with_")):
            failures.append(f"bad_status:{stage}:{status}")
        stage_records[stage] = {"path": relative, "status": status, "sha256": sha256_file(path)}

    checklist = {
        "schema_version": "distinction_remediation_checklist_after_g1_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "items": [
            {"id": "C1", "status": "open_for_R1_G2", "resolution": "mode collapse detected and isolated; corrected evidence not yet run"},
            {"id": "C2", "status": "open_for_R1_G2", "resolution": "A_MIN policy-stack confound detected; H4 pure-risk attribution prohibited"},
            {"id": "C3", "status": "bounded", "resolution": "formal deployment scope explicitly limited to B0/B1"},
            {"id": "C4", "status": "resolved_by_disclosure", "resolution": "all parameter counts and 15 histories audited; architecture causality prohibited"},
            {"id": "C5", "status": "resolved_by_inference_boundary", "resolution": "five-init minimum p=0.0625 disclosed; descriptive direction counts used"},
            {"id": "C6", "status": "resolved", "resolution": "91 callbacks attributed to 20 frames/2 target-light episodes; init50 sensitivity complete"},
            {"id": "C7", "status": "open_for_M1", "resolution": "42/66 invalid legacy JSON pointers reproduced; replacement value-resolving manifest required"},
            {"id": "C8", "status": "resolved_by_metric_semantics", "resolution": "centre distance separated from oriented-footprint separation; margin sensitivity complete"},
            {"id": "C9", "status": "resolved", "resolution": "CV/CA/train-mean and three-seed B1 input diagnostics complete"},
        ],
    }
    atomic_write_json(root / "00_baseline/remediation_checklist_after_G1.json", checklist)

    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "S0_G1_COMPLETE.json":
            files.append(
                {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            )
    manifest = {
        "schema_version": "distinction_s0_g1_completion_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass" if not failures else "fail",
        "result_generation": "distinction_v1",
        "completed_stages": list(MARKERS),
        "stage_markers": stage_records,
        "verification_failures": failures,
        "artifact_file_count": len(files),
        "artifact_total_bytes": sum(item["bytes"] for item in files),
        "artifact_inventory": files,
        "remaining_scientific_gates": [
            "R1/G2 corrected mode mapping and unified A_MIN decision",
            "fixed route-defined conflict-zone replay if raw scenario_result.pkl is retained",
            "M1 replacement for invalid legacy evidence locators",
        ],
        "git_note": "No commit or push was performed as part of S0-G1 completion.",
    }
    atomic_write_json(root / "S0_G1_COMPLETE.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("status", "completed_stages", "artifact_file_count", "artifact_total_bytes", "remaining_scientific_gates")}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
