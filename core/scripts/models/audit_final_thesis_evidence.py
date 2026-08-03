#!/usr/bin/env python3
"""Cross-check final thesis evidence gates and surface methodological boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(repo: Path, output: Path) -> dict[str, Any]:
    generated = repo / "docs/paper/generated"
    paths = {
        "day6": generated / "day6/day6_collection_audit.json",
        "day7": generated / "day7/day7_split_audit.json",
        "day8_validation": generated / "day8/final_validation/day8_validation_summary.json",
        "day8_test": generated / "day8/final_test/day8_frozen_test_summary.json",
        "day9": generated / "day9/day9_smoke_audit.json",
        "day10": generated / "day10/analysis/day10_analysis_summary.json",
        "day10_contract": generated / "day10/evidence/day10_run_contract.json",
        "day11": generated / "day11/analysis/day11_analysis_summary.json",
        "day11_contract": generated / "day11/evidence/day11_run_contract.json",
        "day12": generated / "day12/timing_synthesis/day12_timing_synthesis_summary.json",
        "collision": generated / "day12/server_stage/collision_attribution/day12_collision_window_audit.json",
        "day13": generated / "day13/analysis/day13_filtered_sensitivity_summary.json",
        "paper": generated / "paper_assets_v1/PAPER_EVIDENCE_PACKAGE_COMPLETE.json",
        "results_manifest": generated / "paper_assets_v1/paper_results_manifest.json",
    }
    data = {name: load(path) for name, path in paths.items()}
    checks: list[dict[str, Any]] = []

    def check(check_id: str, condition: bool, evidence: Any) -> None:
        checks.append({"check_id": check_id, "status": "pass" if condition else "fail", "evidence": evidence})

    check("day6_collection_complete", data["day6"].get("status") == "pass" and data["day6"].get("rollout_count") == 200, {"status": data["day6"].get("status"), "rollouts": data["day6"].get("rollout_count")})
    check("day6_day7_raw_count_match", data["day6"].get("sample_count") == data["day7"].get("raw_sample_counts", {}).get("all") == 11230, {"day6": data["day6"].get("sample_count"), "day7": data["day7"].get("raw_sample_counts", {}).get("all")})
    check("rollout_split_disjoint", all(data["day7"].get("leakage_checks", {}).values()), data["day7"].get("leakage_checks"))
    check("dataset_split_counts", data["day7"].get("rollouts_by_split") == {"train": 160, "val": 20, "test": 20}, data["day7"].get("rollouts_by_split"))
    check("day8_validation_complete", data["day8_validation"].get("status") == "pass" and data["day8_validation"].get("expected_runs") == data["day8_validation"].get("observed_runs") == 15, {"expected": data["day8_validation"].get("expected_runs"), "observed": data["day8_validation"].get("observed_runs")})
    check("selection_test_separation", data["day8_validation"].get("test_accessed") is False and data["day8_test"].get("test_used_for_selection") is False, {"validation_test_accessed": data["day8_validation"].get("test_accessed"), "test_used_for_selection": data["day8_test"].get("test_used_for_selection")})
    check("b1_frozen_selection", data["day8_validation"].get("provisional_selected_variant") == data["day8_test"].get("closed_loop_selected_variant") == "B1" and data["day8_test"].get("closed_loop_selected_seed") == 37, {"variant": data["day8_test"].get("closed_loop_selected_variant"), "seed": data["day8_test"].get("closed_loop_selected_seed")})
    check("day9_smoke_only_complete", data["day9"].get("status") == "pass" and data["day9"].get("expected_arms") == data["day9"].get("observed_arms") == 8 and data["day9"].get("smoke_only_not_formal_evidence") is True, {"arms": data["day9"].get("observed_arms"), "smoke_only": data["day9"].get("smoke_only_not_formal_evidence")})
    check("day10_formal_matrix", data["day10"].get("status") == "pass" and data["day10"].get("counts", {}).get("rollouts") == 80 and data["day10"].get("counts", {}).get("cells") == 16, data["day10"].get("counts"))
    check("day11_timing_matrix", data["day11"].get("status") == "pass" and data["day11"].get("rollouts") == 80 and data["day11"].get("cells") == 16, {"rollouts": data["day11"].get("rollouts"), "cells": data["day11"].get("cells")})
    check("day12_three_offset_synthesis", data["day12"].get("status") == "pass" and data["day12"].get("rollouts") == 120 and data["day12"].get("offsets_m") == [-3.0, 0.0, 3.0], {"rollouts": data["day12"].get("rollouts"), "offsets_m": data["day12"].get("offsets_m")})
    collision_totals = data["collision"].get("totals", {})
    check("collision_callbacks_test_clean", data["collision"].get("status") == "pass" and collision_totals.get("affected_usable_by_split") == {"train": 162, "val": 0, "test": 0}, collision_totals.get("affected_usable_by_split"))
    check("day13_filtered_sensitivity", data["day13"].get("status") == "pass" and data["day13"].get("matched_runs") == 15 and data["day13"].get("selected_architecture_stable") is True and data["day13"].get("test_accessed") is False, {"matched_runs": data["day13"].get("matched_runs"), "stable": data["day13"].get("selected_architecture_stable"), "test_accessed": data["day13"].get("test_accessed")})
    check("paper_package_integrity", data["paper"].get("status") == "pass" and data["paper"].get("source_integrity_failures") == 0 and data["paper"].get("unresolved_evidence_ids") == 0, data["paper"])

    test_inits = data["day7"].get("split_init_ids", {}).get("test")
    day10_inits = data["day10_contract"].get("ego_init_ids")
    day11_inits = data["day11_contract"].get("ego_init_ids")
    shared_held_out_inits = test_inits == day10_inits == day11_inits == [46, 47, 48, 49, 50]
    b0_calibration = data["day10_contract"].get("predictors", {}).get("B0", {}).get("calibration")
    b1_has_calibration = "calibration_parameters" in data["day10_contract"].get("predictors", {}).get("B1", {})

    warnings = [
        {
            "warning_id": "W1_five_init_groups",
            "severity": "high",
            "finding": "Validation, test and formal closed-loop inference use five ego-init clusters; the smallest attainable two-sided exact sign-flip p-value is 0.0625 before multiplicity correction.",
            "action": "Treat interval/effect patterns as descriptive and do not claim p<0.05 significance.",
        },
        {
            "warning_id": "W2_shared_held_out_inits",
            "severity": "medium",
            "finding": f"Offline frozen test and Day10/Day11 closed-loop experiments share held-out ego init IDs {test_inits}.",
            "verified": shared_held_out_inits,
            "action": "State that closed loop did not tune/select the model, but is not an independent external replication of the offline test population.",
        },
        {
            "warning_id": "W3_predictor_stack_treatment",
            "severity": "high",
            "finding": f"Closed-loop B0 uses {b0_calibration}; B1 includes frozen calibration parameters.",
            "verified": b0_calibration == "identity_no_calibration_artifact" and b1_has_calibration,
            "action": "Attribute closed-loop contrasts to the frozen predictor stack (model plus calibration), not network weights alone.",
        },
        {
            "warning_id": "W4_response_tail_size",
            "severity": "high",
            "finding": "The response-active frozen-test subset contains 15 windows from six rollouts and three init groups.",
            "action": "Report calibration failure as a diagnostic limitation, not a general tail-performance estimate.",
        },
        {
            "warning_id": "W5_single_map_distribution",
            "severity": "high",
            "finding": "All formal evidence is from a controlled Town05 give-way geometry and a 2.0 s prediction horizon (10 steps at 0.2 s).",
            "action": "Restrict claims to the tested in-distribution CARLA scenario; do not claim cross-map or real-world generalisation.",
        },
        {
            "warning_id": "W6_callback_alignment",
            "severity": "medium",
            "finding": "Old collection logs lack a per-rollout sample-clock/CARLA-frame anchor, so 162 affected train windows are a conservative whole-rollout upper bound.",
            "action": "Use Day13 only as post-hoc architecture sensitivity and retain the original Day8 experiment as primary.",
        },
        {
            "warning_id": "W7_batch_and_multiplicity",
            "severity": "medium",
            "finding": "Nominal and shifted timing conditions were executed in separate batches; all selected Day12 Holm-adjusted p-values are non-confirmatory.",
            "action": "Emphasise effect heterogeneity and mechanism trade-offs rather than statistical significance.",
        },
        {
            "warning_id": "W8_title_and_causality",
            "severity": "medium",
            "finding": "The final selected B1 model does not consume the explicit interaction sequence, although T1/T2 do; deployment arrows show implemented flow, not causal identification.",
            "action": "Prefer a task-adapted prediction/predictor-risk coupling title and avoid claiming a causal interaction model.",
        },
    ]

    failures = [item for item in checks if item["status"] != "pass"]
    payload = {
        "schema_version": "final_thesis_evidence_audit_v1",
        "status": "pass" if not failures else "fail",
        "completed_stage": "Day14 evidence package and Results draft",
        "checks": checks,
        "check_count": len(checks),
        "failure_count": len(failures),
        "warnings": warnings,
        "warning_count": len(warnings),
        "new_formal_experiment_required": False,
        "writing_blockers": [
            "Complete literature review with current primary sources.",
            "Write full Methods with sufficient implementation detail and frozen protocol references.",
            "Integrate canonical tables/figures into the university thesis template.",
            "Perform final citation, terminology and claim-boundary review.",
        ],
        "source_files": {str(path.relative_to(repo)): sha256(path) for path in paths.values()},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output or repo / "docs/paper/generated/final_audit/FINAL_THESIS_EVIDENCE_AUDIT.json").resolve()
    result = build(repo, output)
    print(json.dumps({"status": result["status"], "check_count": result["check_count"], "failure_count": result["failure_count"], "warning_count": result["warning_count"]}, indent=2))


if __name__ == "__main__":
    main()
