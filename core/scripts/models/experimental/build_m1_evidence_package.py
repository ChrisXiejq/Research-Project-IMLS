#!/usr/bin/env python3
"""Build and value-audit the final four-hypothesis M1 evidence package."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import csv
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

try:
    from .frozen_prediction_evidence import (
        frozen_test_evaluation_paths,
        frozen_test_rollout_records,
    )
except ImportError:  # direct script execution
    from frozen_prediction_evidence import (
        frozen_test_evaluation_paths,
        frozen_test_rollout_records,
    )


CLOSURE_FINAL = "final"
CLOSURE_PRE_SF4 = "pre-sf4"
CLOSURE_MODES = (CLOSURE_FINAL, CLOSURE_PRE_SF4)
SUPERVISOR_CONTENT_EVIDENCE_IDS = (
    "SF1_BEHAVIOUR_APPROACH_STOP",
    "SF1_BEHAVIOUR_RELEASE_LATENCY",
    "SF1_BEHAVIOUR_PAIRED_RISK_CONTRASTS",
    "SF2_ATTEMPTED_SOLVE_COST_QUANTILES",
    "SF2_ATTEMPTED_SOLVE_ACCEPTANCE",
    "SF2_PAIRED_COST_ACCEPTANCE_CONTRASTS",
    "SF2_RAW_SOLVER_FAILURE_TAXONOMY",
    "SF2_FAILURE_AFFECTED_ROLLOUT_OUTCOMES",
    "SF2_DEADLINE_EXCEEDANCE",
    "SF4_PRIMARY_DID_COMPLETION",
    "SF4_BEHAVIOURAL_AUTHORITY_EFFECTS",
    "SF4_MANIPULATION_AUTHORITY",
    "SF4_COMPUTATIONAL_WALL_TIME",
    "SF4_CONTROLLER_ACCEPTANCE_AND_SOLVER_STATUS",
)
SF4_REQUIRED_RAW_FILES = (
    "scenario_run_summary.json",
    "scenario_rollout_config.json",
    "smpc_debug_setup.json",
    "prediction_deployment_manifest.json",
    "prediction_dataset/prediction_dataset_config.json",
    "prediction_dataset/prediction_dataset_manifest.json",
    "smpc_debug_steps.jsonl",
    "prediction_dataset/prediction_dataset_raw.jsonl",
    "prediction_dataset/prediction_dataset_labeled.jsonl",
    "scenario_result.pkl",
    "scenario_steps.csv",
)
SF4_REQUIRED_ANALYSIS_PRODUCTS = (
    "sf4_rollout_outcomes.csv",
    "sf4_per_init_did.csv",
    "sf4_per_init_direct_effects.csv",
    "sf4_inference.json",
    "sf4_manipulation_checks.json",
    "sf4_server_wall_time_diagnostics.json",
    "sf4_controller_acceptance_and_solver_status.json",
    "sf4_input_manifest.json",
    "SF4_ANALYSIS_REPORT.md",
    "sf4_primary_and_direct_effects.tex",
    "sf4_behavioural_authority_effects.tex",
    "sf4_authority_manipulation_and_first_stage.tex",
    "sf4_computational_wall_time.tex",
    "sf4_controller_acceptance_and_solver_status.tex",
)
SF4_BEHAVIOURAL_OUTCOMES = (
    "minimum_margin_adjusted_bbox_separation_m",
    "cautious_approach_progress_m",
    "first_stop_distance_to_conflict_m",
    "first_stop_distance_to_designed_stop_m",
    "stopped_duration_s",
    "nominal_conflict_clear_to_actual_path_release_s",
    "actual_path_release_to_sustained_resume_s",
    "buffered_conflict_clear_to_sustained_resume_s",
)
SF4_REQUIRED_EXECUTION_SOURCES = (
    "core/scripts/carla/experimental/run_sf4_supervisor_behavioural_authority_ablation.sh",
    "core/scripts/carla/run_all_scenarios.py",
    "core/scripts/carla/policies/smpc_agent.py",
    "core/scripts/carla/policies/supervisor_action_filter.py",
    "core/scripts/carla/scenarios/run_intersection_scenario.py",
    "core/scripts/models/experimental/generate_sf4_supervisor_authority_inits.py",
    "core/scripts/models/experimental/preflight_sf4_supervisor_authority_inits.py",
    "core/scripts/models/experimental/prepare_sf4_supervisor_behavioural_authority.py",
    "core/scripts/models/experimental/verify_day9_deployment.py",
    "core/scripts/models/experimental/r3_attempt_manager.py",
    "core/scripts/postcarla_trajectory_gate.py",
    "core/scripts/models/experimental/analyze_sf4_supervisor_behavioural_authority.py",
    "core/scripts/models/experimental/package_sf4_compact_evidence.py",
    "core/scripts/models/experimental/package_sf4_full_raw_snapshot.py",
    "core/scripts/models/experimental/validate_sf4_supervisor_authority_smoke.py",
)
SF2_EXECUTION_CLASSES = (
    "rule_bypass_no_solve",
    "attempted_accepted",
    "attempted_fallback_or_nonaccepted",
)
SF2_REQUIRED_FINAL_ARTIFACTS = (
    "policy_cost_summary.csv",
    "corrected_attempted_cost_effects.csv",
    "corrected_attempted_cost_contrasts.csv",
    "corrected_attempted_acceptance_effects.csv",
    "corrected_attempted_acceptance_contrasts.csv",
    "raw_step_classification.csv",
    "raw_policy_solver_summary.csv",
    "raw_policy_init_solver_summary.csv",
    "deadline_exceedance.csv",
    "solver_failure_events.csv",
    "solver_failure_affected_rollout_outcomes.csv",
    "solver_failure_taxonomy.csv",
    "raw_rollout_validation.csv",
    "raw_taxonomy_status.json",
    "analysis_summary.json",
    "supervisor_feedback_02_policy_cost.tex",
    "supervisor_feedback_02_solver_nonoptimal.tex",
    "supervisor_feedback_02_failure_taxonomy.tex",
    "supervisor_feedback_02_failure_downstream.tex",
    "supervisor_feedback_02_paired_cost_acceptance.tex",
)
SF3_REQUIRED_ARTIFACTS = (
    "SUPERVISOR_COMMENT_3_AUDIT.md",
    "finetune_audit.json",
    "finetune_b0_b1_paired_init_effects.tex",
    "finetune_b0_b1_rollout_macro.tex",
    "frozen_test_paired_by_init.csv",
    "frozen_test_paired_summary.csv",
    "frozen_test_population_contract.json",
    "frozen_test_same_aggregation.csv",
    "frozen_test_same_aggregation_contrasts.csv",
    "percentage_accuracy_scan.json",
    "physical_baselines_paired_by_init.csv",
    "physical_baselines_same_aggregation.csv",
)
SF3_EXPECTED_TEST_JSONL_SHA256 = (
    "29291fe2a172047267c3a0c4c3d5693519f550881010a965fb60166a5013d770"
)
SF3_EXPECTED_ANCHORS_SHA256 = (
    "52ab777b9bf695ed56f069b96cbce337014a47f457ed19c638abfb1cde6aa982"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256_token(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower()
    )


def _record_check(
    checks: dict[str, bool], failures: list[str], name: str, condition: bool, detail: str
) -> None:
    checks[name] = bool(condition)
    if not condition:
        failures.append(f"{name}:{detail}")


def _verified_artifact_hashes(
    directory: Path, artifacts: Any, *, nested: bool
) -> tuple[bool, int]:
    if not isinstance(artifacts, dict) or not artifacts:
        return False, 0
    verified = 0
    for relative, record in artifacts.items():
        expected = record.get("sha256") if nested and isinstance(record, dict) else record
        path = directory / str(relative)
        if not _sha256_token(expected) or not path.is_file() or sha256(path) != expected:
            return False, verified
        verified += 1
    return True, verified


def _manifest_file_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = payload.get("files")
    if not isinstance(records, list):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            return {}
        path = str(record["path"]).lstrip("./")
        if path in output:
            return {}
        output[path] = record
    return output


def _manifest_record(
    records: dict[str, dict[str, Any]], relative: str
) -> dict[str, Any] | None:
    normalized = relative.lstrip("./")
    exact = records.get(normalized)
    if exact is not None:
        return exact
    matches = [record for path, record in records.items() if path.endswith("/" + normalized)]
    return matches[0] if len(matches) == 1 else None


def _find_existing(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.is_file() or candidate.is_dir():
            return candidate
    return candidates[0]


def stage_aware_status(
    *, base_ready: bool, closure_status: str, closure_mode: str
) -> str:
    """Return a publication status without allowing a pre-SF4 false positive."""

    if closure_mode not in CLOSURE_MODES:
        raise ValueError(f"Unknown supervisor-feedback closure mode: {closure_mode}")
    if not base_ready:
        return "fail"
    if closure_mode == CLOSURE_PRE_SF4:
        return "partial_pre_sf4"
    return "pass" if closure_status == "pass" else "fail"


def audit_supervisor_feedback_closure(
    repo: Path,
    *,
    supervisor_feedback_root: Path | None = None,
    sf4_results_root: Path | None = None,
) -> dict[str, Any]:
    """Fail-closed audit of the four externally requested evidence closures.

    The heavy R3/SF4 archives do not need to be committed, but their verified
    sidecars and complete file manifests do.  The manifests bind every formal
    rollout receipt and every required raw file; if an archive is present in
    the checkout its digest is re-computed as an additional check.
    """

    repo = repo.resolve()
    feedback_root = (
        supervisor_feedback_root.resolve()
        if supervisor_feedback_root is not None
        else repo / "docs/paper/generated/supervisor_feedback_v1"
    )
    sf4_root = (
        sf4_results_root.resolve()
        if sf4_results_root is not None
        else repo
        / "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs"
        / "sf4_supervisor_behavioural_authority_v1"
    )
    offline_root = _find_existing(
        [feedback_root / "r3_offline", feedback_root]
    )
    behaviour_dir = _find_existing(
        [offline_root / "01_behaviour", feedback_root / "01_behaviour"]
    )
    cost_dir = _find_existing(
        [offline_root / "02_cost_feasibility", feedback_root / "02_cost_feasibility"]
    )
    sf3_dir = feedback_root / "03_finetune_audit"
    combined_path = _find_existing(
        [
            offline_root / "SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json",
            feedback_root / "SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json",
        ]
    )
    r3_snapshot_root = (
        repo
        / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final"
        / "server_runs/r3_corrected_formal_v3"
    )
    r3_snapshot_receipt_path = r3_snapshot_root / "r3_corrected_formal_snapshot.tar.gz.json"
    r3_snapshot_manifest_path = r3_snapshot_root / "r3_corrected_formal_snapshot.tar.gz.files.json"

    checks: dict[str, bool] = {}
    failures: list[str] = []
    verified_files: dict[str, str] = {}

    def display(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(repo))
        except ValueError:
            return str(path.resolve())

    def bind(path: Path) -> None:
        if path.is_file():
            try:
                verified_files[str(path.relative_to(repo))] = sha256(path)
            except ValueError:
                verified_files[str(path)] = sha256(path)

    behaviour_receipt_path = behaviour_dir / "SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json"
    sf1_ok = False
    try:
        behaviour_receipt = load_json(behaviour_receipt_path)
        summary_path = behaviour_dir / str(behaviour_receipt["summary"])
        summary = load_json(summary_path)
        contract_path = behaviour_dir / str(behaviour_receipt["contract"])
        contract = load_json(contract_path)
        rollout_path = behaviour_dir / "behaviour_rollouts.csv"
        sensitivity_path = behaviour_dir / "behaviour_threshold_sensitivity.csv"
        policy_macro_path = behaviour_dir / "behaviour_policy_cluster_macro.csv"
        paired_contrasts_path = (
            behaviour_dir / "behaviour_policy_paired_contrasts.csv"
        )
        paired_contrasts_tex_path = (
            behaviour_dir / "behaviour_policy_paired_contrasts.tex"
        )
        rollout_rows = load_csv(rollout_path)
        sensitivity_rows = load_csv(sensitivity_path)
        policy_macro_rows = load_csv(policy_macro_path)
        paired_contrast_rows = load_csv(paired_contrasts_path)
        artifact_ok, artifact_count = _verified_artifact_hashes(
            behaviour_dir, behaviour_receipt.get("artifacts"), nested=False
        )
        rollout_keys = {
            (row.get("cell_id"), row.get("ego_init_id")) for row in rollout_rows
        }
        raw_hash_rows = sum(_sha256_token(row.get("debug_sha256")) for row in rollout_rows)
        source_hashes = behaviour_receipt.get("source_sha256") or {}
        expected_sf1_sources = {
            "core/scripts/models/analysis/analyze_supervisor_feedback_behaviour.py": (
                repo / "core/scripts/models/analysis/analyze_supervisor_feedback_behaviour.py"
            ),
            "core/scripts/models/experimental/run_supervisor_feedback_r3_offline_audits.sh": (
                repo / "core/scripts/models/experimental/run_supervisor_feedback_r3_offline_audits.sh"
            ),
            "matrix_audit": r3_snapshot_root / "r3_corrected_matrix_audit.json",
        }
        source_hashes_ok = all(
            path.is_file() and source_hashes.get(name) == sha256(path)
            for name, path in expected_sf1_sources.items()
        ) and summary.get("source_sha256") == source_hashes
        sensitivity_definitions = {
            (
                float(row["stop_speed_mps"]),
                float(row["resume_speed_mps"]),
                int(row["consecutive_steps"]),
                row["risk_policy"],
            )
            for row in sensitivity_rows
        }
        expected_sensitivity_definitions = {
            (stop, resume, sustained, policy)
            for stop in (0.10, 0.15, 0.20)
            for resume in (0.5, 0.8, 1.0)
            for sustained in (2, 3, 5)
            for policy in (
                "adaptive",
                "fixed_aggressive",
                "fixed_medium",
                "fixed_conservative",
            )
        }
        baseline = contract.get("baseline_definition") or {}
        sensitivity_grid = contract.get("threshold_sensitivity_grid") or {}
        sf1_metrics = {
            "first_stop_distance_to_conflict_m",
            "first_stop_distance_to_designed_stop_m",
            "cautious_approach_progress_m",
            "pre_clearance_stopped_duration_s",
            "nominal_clear_to_release_latency_s",
            "buffered_clear_to_resume_latency_s",
            "release_to_resume_latency_s",
        }
        expected_sf1_contrasts = {
            "adaptive_minus_fixed_aggressive",
            "adaptive_minus_fixed_medium",
            "adaptive_minus_fixed_conservative",
        }
        def optional_finite_number(value: Any) -> float | None:
            if value in (None, "", "NA", "--"):
                return None
            number = float(value)
            return number if math.isfinite(number) else None

        paired_cells_ok = True
        for row in paired_contrast_rows:
            observed = int(row["independent_init_groups"])
            expected = int(row["expected_init_groups"])
            per_init = json.loads(row["per_init_effects_json"])
            finite_effects = [
                optional_finite_number(value) for value in per_init.values()
            ]
            finite_effects = [value for value in finite_effects if value is not None]
            summaries = {
                field: optional_finite_number(row.get(field))
                for field in (
                    "cluster_mean_effect",
                    "cluster_median_effect",
                    "minimum_effect",
                    "maximum_effect",
                    "two_sided_exact_sign_flip_p_descriptive",
                )
            }
            signs = [
                int(row.get(field) or 0)
                for field in ("negative_groups", "zero_groups", "positive_groups")
            ]
            paired_cells_ok = paired_cells_ok and all(
                (
                    expected == 5,
                    0 <= observed <= expected,
                    set(per_init) == {"101", "102", "103", "104", "105"},
                    len(finite_effects) == observed,
                    sum(signs) == observed,
                    row.get("analysis_role")
                    == "post_hoc_paired_mechanism_contrast",
                    (
                        all(value is None for value in summaries.values())
                        if observed == 0
                        else all(value is not None for value in summaries.values())
                        and 0.0
                        <= float(
                            summaries[
                                "two_sided_exact_sign_flip_p_descriptive"
                            ]
                        )
                        <= 1.0
                    ),
                )
            )
        sf1_artifact_names = set(behaviour_receipt.get("artifacts") or {})
        required_sf1_artifacts = {
            "behaviour_analysis_contract.json",
            "behaviour_rollouts.csv",
            "behaviour_cell_summary.csv",
            "behaviour_policy_cluster_macro.csv",
            "behaviour_policy_paired_contrasts.csv",
            "behaviour_threshold_sensitivity.csv",
            "behaviour_approach_stop.tex",
            "behaviour_release.tex",
            "behaviour_policy_paired_contrasts.tex",
        }
        paired_contrasts_ok = all(
            (
                len(paired_contrast_rows) == 21,
                {
                    (row.get("contrast"), row.get("metric"))
                    for row in paired_contrast_rows
                }
                == {
                    (contrast, metric)
                    for contrast in expected_sf1_contrasts
                    for metric in sf1_metrics
                },
                paired_cells_ok,
                required_sf1_artifacts <= sf1_artifact_names,
                paired_contrasts_tex_path.is_file(),
                paired_contrasts_tex_path.is_file()
                and "adaptive-minus-fixed behavioural contrasts"
                in paired_contrasts_tex_path.read_text(encoding="utf-8"),
                paired_contrasts_tex_path.is_file()
                and "missing mechanism events are censored rather than imputed"
                in paired_contrasts_tex_path.read_text(encoding="utf-8"),
            )
        )
        policy_macro_ok = all(
            (
                len(policy_macro_rows) == 4,
                {row.get("risk_policy") for row in policy_macro_rows}
                == {
                    "adaptive",
                    "fixed_aggressive",
                    "fixed_medium",
                    "fixed_conservative",
                },
                all(
                    int(row["rollouts"]) == 20
                    and int(row["independent_init_groups"]) == 5
                    and int(row["conditions_per_init"]) == 4
                    for row in policy_macro_rows
                ),
            )
        )

        def csv_truth(value: Any) -> bool:
            return str(value).lower() in {"1", "true"}

        stop_window_ok = True
        for row in rollout_rows:
            status = row.get("stop_window_status")
            censored = csv_truth(row.get("stop_window_censored_missing_release"))
            release_observed = csv_truth(row.get("path_release_observed"))
            stop_observed = csv_truth(row.get("sustained_stop_observed"))
            if status not in {
                "evaluated",
                "censored_missing_release",
                "not_applicable_missing_yield_entry",
            }:
                stop_window_ok = False
                break
            if censored != (status == "censored_missing_release"):
                stop_window_ok = False
                break
            if status == "evaluated" and not release_observed:
                stop_window_ok = False
                break
            if status != "evaluated" and any(
                (
                    stop_observed,
                    bool(row.get("first_sustained_stop_step")),
                    bool(row.get("first_stop_distance_to_conflict_m")),
                    bool(row.get("first_stop_distance_to_designed_stop_m")),
                    bool(row.get("cautious_approach_progress_m")),
                    bool(row.get("cautious_approach_duration_s")),
                    bool(row.get("pre_clearance_stopped_duration_s")),
                )
            ):
                stop_window_ok = False
                break
        sf1_ok = all(
            (
                str(behaviour_receipt.get("status", "")).startswith("pass"),
                behaviour_receipt.get("summary_sha256") == sha256(summary_path),
                behaviour_receipt.get("contract_sha256") == sha256(contract_path),
                summary.get("contract_sha256") == sha256(contract_path),
                summary.get("formal_integrity_status") == "pass",
                summary.get("observed_rollouts") == 80,
                summary.get("expected_rollouts") == 80,
                summary.get("formal_cells") == 16,
                len(summary.get("independent_init_groups", [])) == 5,
                len(rollout_rows) == len(rollout_keys) == raw_hash_rows == 80,
                contract.get("fps") == 20.0,
                contract.get("independent_unit") == "ego_initialisation_group",
                contract.get("step_rows_are_not_independent_samples") is True,
                baseline
                == {
                    "stop_speed_mps": 0.15,
                    "resume_speed_mps": 0.8,
                    "minimum_consecutive_steps": 3,
                },
                sensitivity_grid.get("stop_speed_mps") == [0.1, 0.15, 0.2],
                sensitivity_grid.get("resume_speed_mps") == [0.5, 0.8, 1.0],
                sensitivity_grid.get("minimum_consecutive_steps") == [2, 3, 5],
                sensitivity_grid.get("definitions") == 27,
                sensitivity_grid.get("rows") == 108,
                len(sensitivity_rows) == 108,
                sensitivity_definitions == expected_sensitivity_definitions,
                all(row.get("independent_unit") == "ego_initialisation_group" for row in sensitivity_rows),
                all(row.get("step_rows_are_not_independent_samples") == "True" for row in sensitivity_rows),
                policy_macro_ok,
                paired_contrasts_ok,
                stop_window_ok,
                source_hashes_ok,
                artifact_ok,
                artifact_count >= len(required_sf1_artifacts),
            )
        )
        for path in (
            behaviour_receipt_path,
            summary_path,
            contract_path,
            rollout_path,
            sensitivity_path,
            policy_macro_path,
            paired_contrasts_path,
            paired_contrasts_tex_path,
            *expected_sf1_sources.values(),
        ):
            bind(path)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(f"sf1_behaviour_exception:{type(exc).__name__}")
    _record_check(
        checks,
        failures,
        "sf1_behaviour_80_raw_hash_bound",
        sf1_ok,
        display(behaviour_receipt_path),
    )

    cost_receipt_path = cost_dir / "SUPERVISOR_FEEDBACK_02_COMPLETE.json"
    sf2_ok = False
    try:
        cost_receipt = load_json(cost_receipt_path)
        cost_manifest_path = cost_dir / str(cost_receipt["artifact_manifest"])
        cost_manifest = load_json(cost_manifest_path)
        raw_status_path = cost_dir / "raw_taxonomy_status.json"
        raw_status = load_json(raw_status_path)
        analysis_summary_path = cost_dir / "analysis_summary.json"
        analysis_summary = load_json(analysis_summary_path)
        artifact_ok, artifact_count = _verified_artifact_hashes(
            cost_dir, cost_manifest.get("artifacts"), nested=True
        )
        manifest_artifacts = cost_manifest.get("artifacts") or {}
        required_artifacts_ok = set(SF2_REQUIRED_FINAL_ARTIFACTS).issubset(
            set(manifest_artifacts)
        ) and set(cost_receipt.get("artifacts") or ()) == {
            *manifest_artifacts,
            cost_manifest_path.name,
        }
        raw_validation = cost_manifest.get("raw_debug_hash_validation") or {}
        raw_telemetry_integrity = cost_manifest.get("raw_telemetry_integrity") or {}
        cost_sources = cost_manifest.get("sources") or {}
        expected_cost_sources = {
            "analysis_script": repo
            / "core/scripts/models/analysis/analyze_supervisor_feedback_cost_feasibility.py",
            "r3_corrected_matrix_audit": r3_snapshot_root
            / "r3_corrected_matrix_audit.json",
            "r3_rollout_outcomes": r3_snapshot_root
            / "analysis/r3_rollout_outcomes.csv",
            "r3_analysis_complete": r3_snapshot_root
            / "analysis/R3_ANALYSIS_COMPLETE.json",
            "r3_data_complete": r3_snapshot_root / "R3_DATA_COMPLETE.json",
            "r3_snapshot_files_manifest": r3_snapshot_manifest_path,
        }
        cost_sources_ok = all(
            path.is_file()
            and isinstance(cost_sources.get(name), dict)
            and cost_sources[name].get("sha256") == sha256(path)
            and cost_sources[name].get("bytes") == path.stat().st_size
            for name, path in expected_cost_sources.items()
        )

        step_rows = load_csv(cost_dir / "raw_step_classification.csv")
        raw_policy_rows = load_csv(cost_dir / "raw_policy_solver_summary.csv")
        raw_policy_init_rows = load_csv(
            cost_dir / "raw_policy_init_solver_summary.csv"
        )
        policy_cost_rows = load_csv(cost_dir / "policy_cost_summary.csv")
        corrected_cost_contrast_rows = load_csv(
            cost_dir / "corrected_attempted_cost_contrasts.csv"
        )
        corrected_acceptance_contrast_rows = load_csv(
            cost_dir / "corrected_attempted_acceptance_contrasts.csv"
        )
        deadline_rows = load_csv(cost_dir / "deadline_exceedance.csv")
        failure_events = load_csv(cost_dir / "solver_failure_events.csv")
        affected_outcomes = load_csv(
            cost_dir / "solver_failure_affected_rollout_outcomes.csv"
        )
        failure_taxonomy = load_csv(cost_dir / "solver_failure_taxonomy.csv")
        rollout_validation_rows = load_csv(cost_dir / "raw_rollout_validation.csv")

        execution_classes = {row.get("classification") for row in step_rows}
        class_counts = {
            name: sum(row.get("classification") == name for row in step_rows)
            for name in SF2_EXECUTION_CLASSES
        }
        no_context_rows = sum(
            row.get("classification") == "no_solver_telemetry_context"
            for row in step_rows
        )
        unknown_class_rows = sum(
            row.get("classification")
            not in {*SF2_EXECUTION_CLASSES, "no_solver_telemetry_context"}
            for row in step_rows
        )
        attempted_total = (
            class_counts["attempted_accepted"]
            + class_counts["attempted_fallback_or_nonaccepted"]
        )
        bypass_total = class_counts["rule_bypass_no_solve"]
        receipt_counts_ok = all(
            (
                attempted_total > 0,
                no_context_rows == 0,
                unknown_class_rows == 0,
                len(step_rows) == attempted_total + bypass_total,
                cost_receipt.get("raw_no_solver_telemetry_context_steps") == 0,
                cost_receipt.get("corrected_attempted_solve_steps")
                == attempted_total,
                cost_receipt.get("corrected_rule_bypass_no_solve_steps")
                == bypass_total,
                cost_receipt.get(
                    "corrected_attempted_fallback_or_nonaccepted_steps"
                )
                == class_counts["attempted_fallback_or_nonaccepted"],
                cost_receipt.get("legacy_total_debug_steps") == len(step_rows),
                cost_receipt.get(
                    "legacy_minus_corrected_fallback_or_nonaccepted_steps"
                )
                == cost_receipt.get("legacy_total_nonoptimal_steps")
                - class_counts["attempted_fallback_or_nonaccepted"],
            )
        )

        # Recompute the step-identity gate from the exported table instead of
        # trusting the receipt.  A debug-row count is not enough: duplicated or
        # reordered step IDs could otherwise silently double-count one control
        # decision in the paper-facing statistics.
        step_groups: dict[tuple[str, str, str, str, int], list[dict[str, str]]] = {}
        for row in step_rows:
            key = (
                row["cell_id"],
                row["predictor"],
                row["risk_policy"],
                row["target_style"],
                int(row["ego_init_id"]),
            )
            step_groups.setdefault(key, []).append(row)
        step_identity_ok = len(step_groups) == 80
        for rows in step_groups.values():
            row_indices = [int(row["debug_row_index"]) for row in rows]
            step_ids = [int(row["step"]) for row in rows]
            step_identity_ok = step_identity_ok and all(
                (
                    row_indices == list(range(len(rows))),
                    len(step_ids) == len(set(step_ids)),
                    all(
                        current > previous
                        for previous, current in zip(step_ids, step_ids[1:])
                    ),
                )
            )

        rollout_key_fields = (
            "cell_id",
            "predictor",
            "risk_policy",
            "target_style",
            "ego_init_id",
        )

        def exported_rollout_key(row: dict[str, str]) -> tuple[str, ...]:
            return tuple(row[field] for field in rollout_key_fields)

        event_keys = {exported_rollout_key(row) for row in failure_events}
        affected_by_key = {
            exported_rollout_key(row): row for row in affected_outcomes
        }
        rollout_validation_keys = {
            exported_rollout_key(row) for row in rollout_validation_rows
        }
        downstream_binary_pairs = (
            ("rollout_completion_valid", "completion_valid"),
            ("rollout_completion_failure", "completion_failure"),
            ("rollout_yield_outcome_observed", "yield_outcome_observed"),
            ("rollout_yield_failure", "yield_failure"),
            ("rollout_footprint_collision", "footprint_collision"),
            ("rollout_native_collision_any", "native_collision_any"),
        )
        downstream_scalar_pairs = (
            ("rollout_completion_reason", "completion_reason"),
            ("rollout_completion_duration_s", "completion_duration_s"),
            ("rollout_yield_outcome_reason", "yield_outcome_reason"),
            (
                "rollout_minimum_footprint_separation_m",
                "minimum_footprint_separation_m",
            ),
            (
                "rollout_native_collision_episode_count",
                "native_collision_episode_count",
            ),
        )
        downstream_join_ok = all(
            (
                len(affected_by_key) == len(affected_outcomes),
                event_keys == set(affected_by_key),
                event_keys.issubset(rollout_validation_keys),
                sum(
                    int(row["attempted_fallback_or_nonaccepted_steps"])
                    for row in affected_outcomes
                )
                == len(failure_events),
            )
        )
        for affected in affected_outcomes:
            attempted = int(affected["attempted_solve_steps"])
            failures_for_rollout = int(
                affected["attempted_fallback_or_nonaccepted_steps"]
            )
            downstream_join_ok = downstream_join_ok and all(
                (
                    attempted > 0,
                    0 < failures_for_rollout <= attempted,
                    math.isclose(
                        float(
                            affected[
                                "attempted_fallback_or_nonaccepted_fraction"
                            ]
                        ),
                        failures_for_rollout / attempted,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    ),
                    all(
                        int(affected[field]) in (0, 1)
                        for _, field in downstream_binary_pairs
                    ),
                    math.isfinite(
                        float(affected["minimum_footprint_separation_m"])
                    ),
                    int(affected["native_collision_episode_count"]) >= 0,
                    int(affected["native_collision_any"])
                    == int(int(affected["native_collision_episode_count"]) > 0),
                    (
                        int(affected["completion_valid"]) == 0
                        or math.isfinite(float(affected["completion_duration_s"]))
                    ),
                    bool(affected["completion_reason"]),
                    bool(affected["yield_outcome_reason"]),
                    "descriptive" in affected["interpretation_boundary"].lower(),
                    "mathematical feasibility"
                    in affected["interpretation_boundary"].lower(),
                    "not a causal" in affected["interpretation_boundary"].lower(),
                )
            )
        for event in failure_events:
            affected = affected_by_key.get(exported_rollout_key(event))
            if affected is None:
                downstream_join_ok = False
                continue
            downstream_join_ok = downstream_join_ok and all(
                (
                    all(
                        int(event[event_field]) in (0, 1)
                        and event[event_field] == affected[affected_field]
                        for event_field, affected_field in downstream_binary_pairs
                    ),
                    all(
                        event[event_field] == affected[affected_field]
                        for event_field, affected_field in downstream_scalar_pairs
                    ),
                    math.isfinite(
                        float(event["rollout_minimum_footprint_separation_m"])
                    ),
                )
            )

        expected_policies = {
            "adaptive",
            "fixed_aggressive",
            "fixed_medium",
            "fixed_conservative",
        }

        def solver_summary_rows_ok(rows: list[dict[str, str]], *, by_init: bool) -> bool:
            if len(rows) != (20 if by_init else 4):
                return False
            if {row.get("risk_policy") for row in rows} != expected_policies:
                return False
            if by_init and {int(row["ego_init_id"]) for row in rows} != set(
                range(101, 106)
            ):
                return False
            for row in rows:
                debug_rows = int(row["debug_rows"])
                prediction_valid_context = int(
                    row["prediction_valid_context_steps"]
                )
                prediction_invalid_context = int(
                    row["prediction_invalid_context_steps"]
                )
                attempted = int(row["attempted_solve_steps"])
                accepted = int(row["attempted_accepted_steps"])
                fallback_or_nonaccepted = int(
                    row["attempted_fallback_or_nonaccepted_steps"]
                )
                bypass = int(row["rule_bypass_no_solve_steps"])
                decisions = int(row["solver_execution_decisions"])
                finite = int(row["finite_attempted_latency_steps"])
                nonfinite = int(row["nonfinite_attempted_latency_steps"])
                if not all(
                    (
                        int(row["no_solver_telemetry_context_steps"]) == 0,
                        debug_rows
                        == prediction_valid_context + prediction_invalid_context,
                        attempted
                        == int(row["prediction_valid_attempted_solve_steps"])
                        + int(row["prediction_invalid_attempted_solve_steps"]),
                        bypass
                        == int(row["prediction_valid_bypass_no_solve_steps"])
                        + int(row["prediction_invalid_bypass_no_solve_steps"]),
                        attempted == accepted + fallback_or_nonaccepted,
                        decisions == attempted + bypass,
                        attempted == finite + nonfinite,
                        attempted > 0,
                        math.isclose(
                            float(
                                row[
                                    "controller_acceptance_rate_attempted_solve"
                                ]
                            ),
                            accepted / attempted,
                            rel_tol=0.0,
                            abs_tol=1e-12,
                        ),
                        math.isclose(
                            float(
                                row[
                                    "bypass_fraction_of_solver_execution_decisions"
                                ]
                            ),
                            bypass / decisions,
                            rel_tol=0.0,
                            abs_tol=1e-12,
                        ),
                    )
                ):
                    return False
            return True

        policy_rows_ok = solver_summary_rows_ok(raw_policy_rows, by_init=False)
        policy_init_rows_ok = solver_summary_rows_ok(
            raw_policy_init_rows, by_init=True
        )
        policy_sums_ok = all(
            (
                sum(int(row["attempted_solve_steps"]) for row in raw_policy_rows)
                == attempted_total,
                sum(
                    int(row["attempted_fallback_or_nonaccepted_steps"])
                    for row in raw_policy_rows
                )
                == class_counts["attempted_fallback_or_nonaccepted"],
                sum(
                    int(row["rule_bypass_no_solve_steps"])
                    for row in raw_policy_rows
                )
                == bypass_total,
            )
        )
        policy_cost_ok = all(
            (
                len(policy_cost_rows) == 4,
                {row.get("risk_policy") for row in policy_cost_rows}
                == expected_policies,
                all(
                    row.get("corrected_attempted_solve_status") == "pass"
                    and int(row["attempted_solve_steps"]) > 0
                    and int(row["attempted_solve_steps"])
                    == int(row["attempted_accepted_steps"])
                    + int(row["attempted_fallback_or_nonaccepted_steps"])
                    and all(
                        math.isfinite(float(row[field]))
                        for field in (
                            "attempted_latency_p50_s",
                            "attempted_latency_p95_s",
                            "attempted_latency_p99_s",
                        )
                    )
                    for row in policy_cost_rows
                ),
            )
        )

        def corrected_contrasts_ok(
            rows: list[dict[str, str]], *, metric: str, unit: str
        ) -> bool:
            expected_contrasts = {
                "adaptive_minus_fixed_aggressive",
                "adaptive_minus_fixed_medium",
                "adaptive_minus_fixed_conservative",
            }
            if (
                len(rows) != 3
                or {row.get("contrast") for row in rows} != expected_contrasts
            ):
                return False
            for row in rows:
                effects = json.loads(row["cluster_effects_json"])
                mean = float(row["cluster_mean_effect"])
                low = float(row["cluster_minimum_effect"])
                high = float(row["cluster_maximum_effect"])
                p_value = float(row["two_sided_exact_sign_flip_p_descriptive"])
                if not all(
                    (
                        row.get("metric") == metric,
                        row.get("unit") == unit,
                        int(row["paired_rollouts"]) == 20,
                        int(row["independent_init_clusters"]) == 5,
                        set(effects) == {"101", "102", "103", "104", "105"},
                        all(math.isfinite(float(value)) for value in effects.values()),
                        all(math.isfinite(value) for value in (mean, low, high, p_value)),
                        low <= mean <= high,
                        int(row["cluster_negative"])
                        + int(row["cluster_zero"])
                        + int(row["cluster_positive"])
                        == 5,
                        int(row["negative_pairs"])
                        + int(row["zero_pairs"])
                        + int(row["positive_pairs"])
                        == 20,
                        0.0 <= p_value <= 1.0,
                        row.get("inference_scope")
                        == "descriptive post-hoc supervisor-feedback audit",
                    )
                ):
                    return False
            return True

        paired_sf2_ok = all(
            (
                corrected_contrasts_ok(
                    corrected_cost_contrast_rows,
                    metric="adaptive_minus_control_attempted_p95_solve_time_s",
                    unit="s",
                ),
                corrected_contrasts_ok(
                    corrected_acceptance_contrast_rows,
                    metric=(
                        "adaptive_minus_control_attempted_fallback_or_nonaccepted_fraction"
                    ),
                    unit="fraction",
                ),
            )
        )
        deadline_names = {
            "simulator_control_period_s",
            "smpc_planning_interval_s",
            "frozen_runtime_gate_s",
        }
        policy_attempts = {
            row["risk_policy"]: int(row["attempted_solve_steps"])
            for row in raw_policy_rows
        }
        deadlines_ok = all(
            (
                len(deadline_rows) == 12,
                {row.get("risk_policy") for row in deadline_rows}
                == expected_policies,
                {row.get("deadline_name") for row in deadline_rows}
                == deadline_names,
                all(
                    row.get("evaluation_status") == "evaluated"
                    and int(row["finite_attempted_solve_steps"])
                    + int(row["nonfinite_attempted_solve_steps_excluded"])
                    == policy_attempts[row["risk_policy"]]
                    and 0 <= int(row["deadline_exceedance_steps"])
                    <= int(row["finite_attempted_solve_steps"])
                    for row in deadline_rows
                ),
            )
        )
        final_tex_ok = all(
            (
                "actual SMPC solve attempts only"
                in (cost_dir / "supervisor_feedback_02_policy_cost.tex").read_text(
                    encoding="utf-8"
                ),
                all(
                    phrase
                    in (
                        cost_dir / "supervisor_feedback_02_solver_nonoptimal.tex"
                    ).read_text(encoding="utf-8")
                    for phrase in (
                        "controller acceptance and fallback audit",
                        "not mathematical",
                        "actual solve attempts",
                        "bypass/no-solve decisions",
                    )
                ),
                "Not evaluated"
                not in (cost_dir / "supervisor_feedback_02_failure_taxonomy.tex").read_text(
                    encoding="utf-8"
                ),
                all(
                    phrase
                    in (
                        cost_dir / "supervisor_feedback_02_failure_downstream.tex"
                    ).read_text(encoding="utf-8")
                    for phrase in (
                        "Canonical downstream outcomes",
                        "fallback/nonaccepted",
                        "descriptive association",
                    )
                ),
                all(
                    phrase
                    in (
                        cost_dir / "supervisor_feedback_02_paired_cost_acceptance.tex"
                    ).read_text(encoding="utf-8")
                    for phrase in (
                        "Recorded solve P95",
                        "Fallback/nonacceptance",
                        "Fixed aggressive",
                        "Fixed medium",
                        "Fixed conservative",
                        "Init $n$",
                        "not a feasibility certificate",
                    )
                ),
            )
        )
        sf2_ok = all(
            (
                cost_receipt.get("schema_version")
                == "supervisor_feedback_02_complete_v3",
                cost_receipt.get("status") == "pass",
                cost_receipt.get("final_evidence_ready") is True,
                cost_receipt.get("legacy_aggregate_evidence_status")
                == "preliminary_legacy_conflated",
                cost_receipt.get("observed_rollouts") == 80,
                cost_receipt.get("raw_step_classification_status") == "pass",
                cost_receipt.get("raw_step_identity_status") == "pass",
                cost_receipt.get("raw_telemetry_integrity_status") == "pass",
                cost_receipt.get("raw_no_solver_telemetry_context_steps") == 0,
                cost_receipt.get("corrected_attempted_latency_status") == "pass",
                cost_receipt.get("corrected_attempted_acceptance_status") == "pass",
                cost_receipt.get("failure_downstream_outcome_join_status")
                == "pass",
                cost_receipt.get("raw_taxonomy_status") == "pass",
                cost_receipt.get("deadline_evaluation_status") == "evaluated",
                cost_receipt.get("deadline_claim_status") == "pass",
                cost_receipt.get("artifact_manifest_sha256") == sha256(cost_manifest_path),
                cost_manifest.get("schema_version")
                == "supervisor_feedback_cost_feasibility_manifest_v3",
                cost_manifest.get("status") == "pass",
                cost_manifest.get("final_evidence_ready") is True,
                cost_manifest.get("legacy_aggregate_artifact_status")
                == "preliminary_legacy_conflated",
                raw_validation.get("status") == "pass",
                raw_validation.get("validated_files") == 80,
                _sha256_token(raw_validation.get("validated_file_set_sha256")),
                raw_telemetry_integrity.get("status") == "pass",
                raw_telemetry_integrity.get("no_solver_telemetry_context_steps")
                == 0,
                raw_telemetry_integrity.get("required_context_steps_for_final")
                == 0,
                raw_status.get("status") == "pass",
                raw_status.get("hash_validation_status") == "pass",
                raw_status.get("canonical_debug_files") == 80,
                raw_status.get("expected_canonical_debug_files") == 80,
                raw_status.get("step_classification_status") == "pass",
                raw_status.get("raw_step_identity_status") == "pass",
                raw_status.get("telemetry_integrity_status") == "pass",
                raw_status.get("no_solver_telemetry_context_steps") == 0,
                raw_status.get("corrected_latency_status") == "pass",
                raw_status.get("corrected_acceptance_status") == "pass",
                raw_status.get("failure_downstream_outcome_join_status")
                == "pass",
                raw_status.get("affected_rollout_outcome_rows")
                == len(affected_outcomes),
                raw_status.get("deadline_evaluation_status") == "evaluated",
                raw_status.get("deadline_claim_status") == "pass",
                raw_status.get("failure_event_count") == len(failure_events),
                raw_status.get("failure_taxonomy_rows") == len(failure_taxonomy),
                analysis_summary.get("schema_version")
                == "supervisor_feedback_cost_feasibility_v3",
                analysis_summary.get("status") == "pass",
                analysis_summary.get("final_evidence_ready") is True,
                analysis_summary.get("raw_step_classification_status") == "pass",
                analysis_summary.get("raw_step_identity_status") == "pass",
                analysis_summary.get("raw_telemetry_integrity_status") == "pass",
                analysis_summary.get("raw_no_solver_telemetry_context_steps") == 0,
                analysis_summary.get("corrected_attempted_latency_status") == "pass",
                analysis_summary.get("corrected_attempted_acceptance_status")
                == "pass",
                analysis_summary.get("failure_downstream_outcome_join_status")
                == "pass",
                artifact_ok,
                artifact_count >= len(SF2_REQUIRED_FINAL_ARTIFACTS),
                required_artifacts_ok,
                cost_sources_ok,
                execution_classes.issubset(set(SF2_EXECUTION_CLASSES)),
                step_identity_ok,
                receipt_counts_ok,
                policy_rows_ok,
                policy_init_rows_ok,
                policy_sums_ok,
                policy_cost_ok,
                paired_sf2_ok,
                deadlines_ok,
                len(rollout_validation_rows) == 80,
                len(failure_events)
                == class_counts["attempted_fallback_or_nonaccepted"],
                downstream_join_ok,
                bool(failure_taxonomy) == bool(failure_events),
                final_tex_ok,
            )
        )
        for path in (
            cost_receipt_path,
            cost_manifest_path,
            raw_status_path,
            analysis_summary_path,
            *(cost_dir / name for name in SF2_REQUIRED_FINAL_ARTIFACTS),
            *expected_cost_sources.values(),
        ):
            bind(path)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(f"sf2_cost_exception:{type(exc).__name__}")
    _record_check(
        checks,
        failures,
        "sf2_raw_taxonomy_and_deadlines_final",
        sf2_ok,
        display(cost_receipt_path),
    )

    r3_binding_ok = False
    try:
        combined = load_json(combined_path)
        r3_snapshot_receipt = load_json(r3_snapshot_receipt_path)
        combined_receipts = combined.get("receipts") or {}
        bound_hashes = set(combined_receipts.values())
        combined_sources = combined.get("source_sha256") or {}
        expected_combined_sources = {
            "core/scripts/models/analysis/analyze_supervisor_feedback_behaviour.py": repo
            / "core/scripts/models/analysis/analyze_supervisor_feedback_behaviour.py",
            "core/scripts/models/analysis/analyze_supervisor_feedback_cost_feasibility.py": repo
            / "core/scripts/models/analysis/analyze_supervisor_feedback_cost_feasibility.py",
            "core/scripts/models/experimental/run_supervisor_feedback_r3_offline_audits.sh": repo
            / "core/scripts/models/experimental/run_supervisor_feedback_r3_offline_audits.sh",
            "r3_corrected_matrix_audit.json": r3_snapshot_root
            / "r3_corrected_matrix_audit.json",
        }
        combined_sources_ok = all(
            path.is_file() and combined_sources.get(name) == sha256(path)
            for name, path in expected_combined_sources.items()
        )
        r3_binding_ok = all(
            (
                str(combined.get("status", "")).startswith("pass"),
                sha256(behaviour_receipt_path) in bound_hashes,
                sha256(cost_receipt_path) in bound_hashes,
                r3_snapshot_receipt.get("status") == "pass",
                (r3_snapshot_receipt.get("archive_verification") or {}).get("status")
                == "pass",
                combined.get("source_r3_archive_sha256")
                == r3_snapshot_receipt.get("archive_sha256"),
                r3_snapshot_receipt.get("files_manifest_sha256")
                == sha256(r3_snapshot_manifest_path),
                r3_snapshot_receipt.get("files") == 2325,
                combined_sources_ok,
            )
        )
        for path in (
            combined_path,
            r3_snapshot_receipt_path,
            r3_snapshot_manifest_path,
            *expected_combined_sources.values(),
        ):
            bind(path)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(
            f"sf1_sf2_r3_snapshot_binding_exception:{type(exc).__name__}"
        )
    _record_check(
        checks,
        failures,
        "sf1_sf2_source_r3_snapshot_hash_bound",
        r3_binding_ok,
        display(combined_path),
    )

    sf3_receipt_path = sf3_dir / "SUPERVISOR_COMMENT_3_COMPLETE.json"
    sf3_ok = False
    try:
        sf3_receipt = load_json(sf3_receipt_path)
        sf3_manifest_path = sf3_dir / str(sf3_receipt["manifest"])
        sf3_manifest = load_json(sf3_manifest_path)
        artifacts_ok, artifact_count = _verified_artifact_hashes(
            sf3_dir, sf3_receipt.get("artifacts"), nested=False
        )
        receipt_artifacts = sf3_receipt.get("artifacts") or {}
        manifest_artifacts = sf3_manifest.get("artifacts") or {}
        exact_artifacts_ok = all(
            (
                receipt_artifacts == manifest_artifacts,
                set(receipt_artifacts) == set(SF3_REQUIRED_ARTIFACTS),
            )
        )
        receipt_sources = sf3_receipt.get("source_sha256") or {}
        manifest_sources = sf3_manifest.get("source_sha256") or {}
        sources_ok = bool(receipt_sources) and receipt_sources == manifest_sources
        for relative, expected in receipt_sources.items():
            source = repo / relative
            if not source.is_file() or sha256(source) != expected:
                sources_ok = False
                break
        finetune_audit_path = sf3_dir / "finetune_audit.json"
        finetune_audit = load_json(finetune_audit_path)
        percentage_scan_path = sf3_dir / "percentage_accuracy_scan.json"
        percentage_scan = load_json(percentage_scan_path)
        population_contract_path = sf3_dir / "frozen_test_population_contract.json"
        population_contract = load_json(population_contract_path)
        same_aggregation_rows = load_csv(
            sf3_dir / "frozen_test_same_aggregation.csv"
        )
        contrast_rows = load_csv(
            sf3_dir / "frozen_test_same_aggregation_contrasts.csv"
        )
        paired_rows = load_csv(sf3_dir / "frozen_test_paired_by_init.csv")
        paired_summary_rows = load_csv(
            sf3_dir / "frozen_test_paired_summary.csv"
        )
        aggregation_ok = all(
            (
                len(same_aggregation_rows) == 4,
                {
                    (row.get("variant"), row.get("aggregation_level"))
                    for row in same_aggregation_rows
                }
                == {
                    ("B0", "rollout_macro"),
                    ("B1", "rollout_macro"),
                    ("B0", "held_out_init_group_macro"),
                    ("B1", "held_out_init_group_macro"),
                },
                len(contrast_rows) == 2,
                all(
                    row.get("contrast") == "B1_minus_B0"
                    and int(row["held_out_init_groups"]) == 5
                    and int(row["rollouts"]) == 20
                    and int(row["full_horizon_windows"]) == 315
                    and all(
                        float(row[field]) < 0.0
                        for field in (
                            "delta_top1_ADE_m",
                            "delta_top1_FDE_m",
                            "delta_trajectory_mixture_NLL_nats_per_step",
                        )
                    )
                    for row in contrast_rows
                ),
                len(paired_rows) == 5,
                {int(row["ego_init_id"]) for row in paired_rows}
                == set(range(46, 51)),
                all(
                    all(
                        int(row[field]) == 1
                        for field in (
                            "B1_better_top1_ADE_m",
                            "B1_better_top1_FDE_m",
                            "B1_better_trajectory_mixture_NLL_nats_per_step",
                        )
                    )
                    for row in paired_rows
                ),
                len(paired_summary_rows) == 3,
                all(
                    int(row["independent_paired_init_groups"]) == 5
                    and int(row["favourable_init_count"]) == 5
                    and "sensitivity analysis"
                    in row.get("inference_note", "").lower()
                    and "not treatment-randomisation inference"
                    in row.get("inference_note", "").lower()
                    for row in paired_summary_rows
                ),
            )
        )
        corrected_table = sf3_dir / "finetune_b0_b1_rollout_macro.tex"
        corrected_table_ok = all(
            (
                corrected_table.is_file(),
                corrected_table.is_file()
                and "\\begin{table}" in corrected_table.read_text(encoding="utf-8"),
                corrected_table.is_file()
                and len(corrected_table.read_text(encoding="utf-8").strip()) >= 100,
            )
        )
        sf3_ok = all(
            (
                sf3_receipt.get("schema_version")
                == "supervisor_comment_3_complete_v2",
                sf3_receipt.get("stage")
                == "supervisor_feedback_item_3_finetune_audit",
                sf3_receipt.get("status") == "pass",
                sf3_receipt.get("manifest_sha256") == sha256(sf3_manifest_path),
                sf3_receipt.get("failure_count") == 0,
                sf3_receipt.get("old_percentage_accuracy_hit_count") == 0,
                sf3_receipt.get("overlapping_windows_treated_as_independent") is False,
                sf3_receipt.get("independent_paired_init_groups") == 5,
                sf3_receipt.get("frozen_test_population_contract_status") == "pass",
                sf3_receipt.get("frozen_test_population_contract_sha256")
                == sha256(population_contract_path),
                sf3_receipt.get("test_jsonl_sha256")
                == SF3_EXPECTED_TEST_JSONL_SHA256,
                sf3_receipt.get("anchors_sha256")
                == SF3_EXPECTED_ANCHORS_SHA256,
                sf3_manifest.get("status") == "pass",
                sf3_manifest.get("schema_version")
                == "supervisor_finetune_feedback_manifest_v2",
                sf3_manifest.get("checks_failed") == 0,
                sf3_manifest.get("checks_passed") == 9,
                sf3_manifest.get("independent_paired_init_groups") == 5,
                sf3_manifest.get("analysis_requires_carla") is False,
                sf3_manifest.get("analysis_requires_training") is False,
                sf3_manifest.get("frozen_test_population_contract_status")
                == "pass",
                sf3_manifest.get("frozen_test_population_contract_sha256")
                == sha256(population_contract_path),
                sf3_manifest.get("test_jsonl_sha256")
                == SF3_EXPECTED_TEST_JSONL_SHA256,
                sf3_manifest.get("anchors_sha256")
                == SF3_EXPECTED_ANCHORS_SHA256,
                finetune_audit.get("schema_version")
                == "supervisor_finetune_feedback_audit_v2",
                finetune_audit.get("status") == "pass",
                (finetune_audit.get("metric_policy") or {}).get(
                    "overlapping_windows_are_independent"
                )
                is False,
                (finetune_audit.get("metric_policy") or {}).get(
                    "superseded_percentage_accuracy_is_current_evidence"
                )
                is False,
                percentage_scan.get("status") == "pass",
                percentage_scan.get("hit_count") == 0,
                percentage_scan.get("hits") == [],
                population_contract.get("schema_version")
                == "frozen_test_population_contract_v1",
                population_contract.get("status") == "pass",
                bool(population_contract.get("checks"))
                and all((population_contract.get("checks") or {}).values()),
                (population_contract.get("test_jsonl") or {}).get("sha256")
                == SF3_EXPECTED_TEST_JSONL_SHA256,
                (population_contract.get("test_jsonl") or {}).get("bytes")
                == 5_673_913,
                (population_contract.get("anchors") or {}).get("sha256")
                == SF3_EXPECTED_ANCHORS_SHA256,
                (population_contract.get("anchors") or {}).get("bytes") == 6_528,
                artifacts_ok,
                artifact_count == len(SF3_REQUIRED_ARTIFACTS),
                exact_artifacts_ok,
                sources_ok,
                aggregation_ok,
                corrected_table_ok,
            )
        )
        for path in (
            sf3_receipt_path,
            sf3_manifest_path,
            *(sf3_dir / name for name in SF3_REQUIRED_ARTIFACTS),
            *(repo / relative for relative in receipt_sources),
        ):
            bind(path)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(f"sf3_finetune_exception:{type(exc).__name__}")
    _record_check(
        checks,
        failures,
        "sf3_finetune_receipt_and_hashes",
        sf3_ok,
        display(sf3_receipt_path),
    )

    sf4_complete_path = sf4_root / "SF4_COMPLETE.json"
    sf4_analysis_path = sf4_root / "analysis/SF4_ANALYSIS_COMPLETE.json"
    sf4_contract_path = (
        sf4_root / "sf4_supervisor_behavioural_authority_run_contract.json"
    )
    sf4_prereg_path = (
        repo
        / "core/scripts/models/protocols/"
        "sf4_supervisor_behavioural_authority_prereg.json"
    )
    sf4_receipts = sorted(sf4_root.glob("SF4_*/SF4_ROLLOUT_*_COMPLETE.json"))
    sf4_core_ok = False
    sf4_complete: dict[str, Any] = {}
    receipt_records: list[tuple[Path, dict[str, Any]]] = []
    try:
        sf4_complete = load_json(sf4_complete_path)
        sf4_analysis = load_json(sf4_analysis_path)
        sf4_contract = load_json(sf4_contract_path)
        sf4_prereg = load_json(sf4_prereg_path)
        sf4_inference_path = sf4_analysis_path.parent / "sf4_inference.json"
        sf4_manipulation_path = (
            sf4_analysis_path.parent / "sf4_manipulation_checks.json"
        )
        sf4_wall_time_path = (
            sf4_analysis_path.parent / "sf4_server_wall_time_diagnostics.json"
        )
        sf4_controller_path = (
            sf4_analysis_path.parent
            / "sf4_controller_acceptance_and_solver_status.json"
        )
        sf4_input_manifest_path = (
            sf4_analysis_path.parent / "sf4_input_manifest.json"
        )
        sf4_inference = load_json(sf4_inference_path)
        sf4_manipulation = load_json(sf4_manipulation_path)
        sf4_wall_time = load_json(sf4_wall_time_path)
        sf4_controller = load_json(sf4_controller_path)
        sf4_input_manifest = load_json(sf4_input_manifest_path)
        products_ok, product_count = _verified_artifact_hashes(
            sf4_analysis_path.parent, sf4_analysis.get("products"), nested=True
        )
        products_exact = set(sf4_analysis.get("products") or {}) == set(
            SF4_REQUIRED_ANALYSIS_PRODUCTS
        )

        expected_cells = {
            (
                f"SF4_B1_{risk}_{style}_supervisor_{mode}",
                risk,
                style,
                mode,
            )
            for risk in ("adaptive", "fixed_medium")
            for style in ("assertive", "reactive")
            for mode in ("on", "off")
        }
        contract_cells = {
            (
                str(item["cell_id"]),
                str(item["risk_policy"]),
                str(item["target_style"]),
                str(item["supervisor_authority_mode"]),
            )
            for item in sf4_contract.get("cells") or []
        }
        execution_order = sf4_contract.get("execution_order") or []
        execution_keys = {
            (str(item["cell_id"]), int(item["ego_init_id"]))
            for item in execution_order
        }
        execution_blocks_ok = all(
            {
                (
                    str(item["cell_id"]),
                    str(item["risk_policy"]),
                    str(item["target_style"]),
                    str(item["supervisor_authority_mode"]),
                )
                for item in execution_order
                if int(item["ego_init_id"]) == init_id
            }
            == expected_cells
            for init_id in range(106, 116)
        )
        common_controller = sf4_contract.get("common_controller_contract") or {}
        wall_contract = sf4_contract.get("server_wall_time_contract") or {}
        contract_hashes = sf4_contract.get("hashes") or {}
        execution_source_hashes = contract_hashes.get("execution_sources") or {}
        execution_sources_ok = set(SF4_REQUIRED_EXECUTION_SOURCES).issubset(
            execution_source_hashes
        ) and all(
            (repo / relative).is_file()
            and execution_source_hashes.get(relative) == sha256(repo / relative)
            for relative in SF4_REQUIRED_EXECUTION_SOURCES
        )
        frozen_tuning_hashes = contract_hashes.get(
            "supervisor_authority_tuning"
        ) or {}
        frozen_tuning_paths = (
            (sf4_contract.get("paths_relative_to_results") or {}).get(
                "supervisor_authority_tuning"
            )
            or {}
        )
        frozen_tuning_ok = set(frozen_tuning_hashes) == set(frozen_tuning_paths) == {
            "on",
            "off",
        } and all(
            (sf4_root / frozen_tuning_paths[mode]).is_file()
            and frozen_tuning_hashes[mode]
            == sha256(sf4_root / frozen_tuning_paths[mode])
            for mode in ("on", "off")
        )
        prereg_secondary_outcomes = set(
            ((sf4_prereg.get("secondary_estimands") or {}).get(
                "same_did_and_direct_effects"
            ) or [])
        )
        contract_ok = all(
            (
                sf4_contract.get("schema_version")
                == "sf4_supervisor_behavioural_authority_run_contract_v1",
                sf4_contract.get("status") == "frozen_before_outcomes",
                sf4_contract.get("formal_evidence") is True,
                sf4_contract.get("expected_rollouts") == 80,
                sf4_contract.get("independent_unit") == "ego_init_id",
                sf4_contract.get("ego_init_ids") == list(range(106, 116)),
                contract_cells == expected_cells,
                len(execution_order) == len(execution_keys) == 80,
                execution_blocks_ok,
                sf4_contract.get("risk_policies")
                == ["adaptive", "fixed_medium"],
                sf4_contract.get("target_styles") == ["assertive", "reactive"],
                sf4_contract.get("supervisor_authority_modes") == ["on", "off"],
                sf4_contract.get("primary_did")
                == "(adaptive-fixed_medium)_on - (adaptive-fixed_medium)_off",
                common_controller.get("yield_rule_smpc_bypass_enabled") is True,
                common_controller.get("yield_post_solver_action_filter_mode")
                == "apply",
                common_controller.get("only_behavioral_arm_difference")
                == "vehicle_role_overrides.ego.yield_supervisor_behavioural_authority_mode",
                common_controller.get("authority_off_allowed_solver_influence")
                == ["interaction_estimator_to_adaptive_risk_allocation"],
                "rule_smpc_bypass"
                in (common_controller.get("authority_off_disabled_channels") or []),
                wall_contract.get("schema_version")
                == "server_wall_time_diagnostics_v1",
                wall_contract.get("clock") == "time.perf_counter",
                wall_contract.get("inferential_unit")
                == "ego_init_id paired cluster",
                wall_contract.get("server_side_diagnostic_only") is True,
                wall_contract.get("deployment_or_real_time_guarantee") is False,
                sf4_prereg.get("schema_version")
                == "sf4_supervisor_behavioural_authority_prereg_v1",
                sf4_prereg.get("status") == "frozen_before_outcomes",
                set(SF4_BEHAVIOURAL_OUTCOMES).issubset(
                    prereg_secondary_outcomes
                ),
                contract_hashes.get("prereg_json") == sha256(sf4_prereg_path),
                execution_sources_ok,
                frozen_tuning_ok,
                sf4_contract.get("no_post_outcome_tuning") is True,
            )
        )

        implementation_gate = sf4_analysis.get(
            "implementation_manipulation_gate"
        ) or {}
        first_stage = sf4_analysis.get("observed_first_stage_activity") or {}
        manipulation_gate = sf4_manipulation.get(
            "implementation_manipulation_gate"
        ) or {}
        manipulation_first_stage = sf4_manipulation.get(
            "observed_first_stage_activity"
        ) or {}
        required_manipulation_flags = (
            "rule_smpc_bypass_configured_identically",
            "authority_on_applies_eligible_rule_smpc_bypass",
            "authority_off_logs_shadow_bypass_but_always_solves",
            "authority_record_present_every_step",
            "all_upstream_and_downstream_candidates_computed",
            "authority_on_applies_candidate_channels",
            "authority_off_nonrisk_solver_control_and_next_state_neutral",
            "shadow_behaviour_state_isolated",
            "interaction_estimator_state_limited_to_adaptive_risk_when_off",
            "collision_outcomes_retained",
        )
        manipulation_ok = all(
            (
                sf4_manipulation.get("schema_version")
                == "sf4_supervisor_behavioural_authority_manipulation_v1",
                sf4_manipulation.get("status") == "pass",
                sf4_manipulation.get("rollouts_checked") == 80,
                implementation_gate == manipulation_gate,
                implementation_gate.get("status") == "pass",
                all(implementation_gate.get(name) is True for name in required_manipulation_flags),
                first_stage == manipulation_first_stage,
                first_stage.get("status")
                in {"active", "inactive_scientific_outcome"},
                first_stage.get("zero_activity_is_integrity_failure") is False,
                first_stage.get("zero_activity_triggers_extra_rollouts") is False,
                len(first_stage.get("by_authority_risk_style") or {}) == 8,
                (
                    first_stage.get("status") == "active"
                    or bool(first_stage.get("claim_limit_if_inactive"))
                ),
            )
        )
        controller_full = sf4_controller.get("full_matrix") or {}
        controller_attempts = int(controller_full.get("factual_solver_attempts", -1))
        controller_accepted = int(
            controller_full.get("controller_accepted_attempts", -1)
        )
        controller_fallback = int(
            controller_full.get("fallback_or_nonaccepted_attempts", -1)
        )
        controller_missing = int(
            controller_full.get("raw_solver_return_status_missing_count", -1)
        )
        controller_statuses = controller_full.get(
            "raw_solver_return_status_counts"
        ) or {}
        controller_ok = all(
            (
                sf4_controller.get("schema_version")
                == "sf4_controller_acceptance_and_solver_status_v1",
                sf4_controller.get("status") == "pass",
                "not strict optimizer-optimality or feasibility"
                in str(sf4_controller.get("semantic_boundary", "")),
                "factual SMPC attempts only"
                in str(sf4_controller.get("denominator", "")),
                sf4_controller.get("raw_return_status_is_separately_reported")
                is True,
                controller_attempts > 0,
                controller_attempts == controller_accepted + controller_fallback,
                controller_attempts
                == controller_missing
                + sum(int(value) for value in controller_statuses.values()),
                len(sf4_controller.get("by_authority_risk_style") or {}) == 8,
                (sf4_analysis.get("solver_execution") or {}).get(
                    "controller_acceptance_not_strict_optimizer_feasibility"
                )
                is True,
                (sf4_analysis.get("solver_execution") or {}).get(
                    "effective_bypass_excluded_from_controller_acceptance_denominator"
                )
                is True,
                (sf4_analysis.get("solver_execution") or {}).get(
                    "raw_solver_return_status_taxonomy"
                )
                == sf4_controller,
            )
        )
        wall_time_ok = all(
            (
                sf4_wall_time.get("schema_version")
                == "sf4_server_wall_time_analysis_v1",
                sf4_wall_time.get("status") in {"pass", "partial_secondary"},
                sf4_wall_time.get("formal_rollouts") == 80,
                sf4_wall_time.get("clock") == "time.perf_counter",
                sf4_wall_time.get("server_side_diagnostic_only") is True,
                sf4_wall_time.get("deployment_or_real_time_guarantee") is False,
                "never simulation step"
                in str(sf4_wall_time.get("inferential_unit", "")),
                sf4_analysis.get("server_wall_time_diagnostics") == sf4_wall_time,
            )
        )
        primary_entry = (
            (sf4_inference.get("outcomes") or {}).get(
                "failure_penalized_completion_time_s"
            )
            or {}
        )
        direct_primary = (
            (sf4_inference.get("direct_paired_effects") or {}).get(
                "failure_penalized_completion_time_s"
            )
            or {}
        )

        def sf4_effect_entry_ok(entry: Mapping[str, Any]) -> bool:
            try:
                defined = int(entry["defined_init_clusters"])
                total = int(entry["total_init_clusters"])
            except (KeyError, TypeError, ValueError):
                return False
            if total != 10 or not 0 <= defined <= total:
                return False
            if defined == total:
                try:
                    ci = entry["cluster_bootstrap_95ci"]
                    return all(
                        (
                            math.isfinite(float(entry["mean_effect"])),
                            isinstance(ci, list) and len(ci) == 2,
                            isinstance(ci, list)
                            and len(ci) == 2
                            and all(math.isfinite(float(value)) for value in ci),
                            0.0
                            <= float(
                                entry[
                                    "exact_two_sided_sign_flip_sensitivity_value"
                                ]
                            )
                            <= 1.0,
                            entry.get("randomisation_inference") is False,
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    return False
            return all(
                (
                    entry.get("status")
                    == "descriptive_only_missing_event_clock",
                    "mean_effect" not in entry,
                    "cluster_bootstrap_95ci" not in entry,
                    "exact_two_sided_sign_flip_sensitivity_value" not in entry,
                )
            )

        sf4_outcomes = sf4_inference.get("outcomes") or {}
        sf4_direct_effects = sf4_inference.get("direct_paired_effects") or {}
        expected_direct_keys = {
            "risk_effect_authority_on",
            "risk_effect_authority_off",
            "authority_effect_adaptive",
            "authority_effect_fixed_medium",
        }
        behavioural_inference_ok = all(
            metric in sf4_outcomes
            and sf4_effect_entry_ok(sf4_outcomes[metric])
            and metric in sf4_direct_effects
            and set(sf4_direct_effects[metric]) == expected_direct_keys
            and all(
                sf4_effect_entry_ok(entry)
                for entry in sf4_direct_effects[metric].values()
            )
            for metric in SF4_BEHAVIOURAL_OUTCOMES
        )
        inference_ok = all(
            (
                sf4_inference.get("schema_version")
                == "sf4_supervisor_behavioural_authority_cluster_inference_v1",
                sf4_inference.get("status") == "pass",
                sf4_inference.get("independent_unit") == "ego_init_id",
                sf4_inference.get("primary_estimand")
                == "(adaptive-fixed_medium)_on - (adaptive-fixed_medium)_off",
                sf4_inference.get("primary_outcome")
                == "failure_penalized_completion_time_s",
                "not randomisation inference"
                in str(sf4_inference.get("exact_sensitivity_analysis", "")),
                (sf4_inference.get("bootstrap") or {}).get("unit")
                == "complete ego-init block",
                (sf4_inference.get("bootstrap") or {}).get("replicates") == 10000,
                (sf4_inference.get("bootstrap") or {}).get("seed") == 20260814,
                primary_entry.get("defined_init_clusters") == 10,
                all(
                    name in primary_entry
                    for name in (
                        "mean_effect",
                        "cluster_bootstrap_95ci",
                        "exact_two_sided_sign_flip_sensitivity_value",
                    )
                ),
                set(direct_primary)
                == expected_direct_keys,
                behavioural_inference_ok,
            )
        )
        input_manifest_ok = all(
            (
                sf4_input_manifest.get("schema_version")
                == "sf4_supervisor_behavioural_authority_analysis_input_manifest_v1",
                sf4_input_manifest.get("status") == "pass",
                (sf4_input_manifest.get("contract") or {}).get("sha256")
                == sha256(sf4_contract_path),
                (sf4_input_manifest.get("preregistration") or {}).get("sha256")
                == sha256(sf4_prereg_path),
                len(sf4_input_manifest.get("rollouts") or []) == 80,
            )
        )
        tex_semantics_ok = all(
            (
                "Primary DID"
                in (sf4_analysis_path.parent / "sf4_primary_and_direct_effects.tex").read_text(encoding="utf-8"),
                all(
                    phrase
                    in (
                        sf4_analysis_path.parent
                        / "sf4_behavioural_authority_effects.tex"
                    ).read_text(encoding="utf-8")
                    for phrase in (
                        "SF4 supervisor-authority effects",
                        "$n/10$",
                        "Missing event clocks remain censored",
                        "not universally a benefit",
                        "Cautious approach progress",
                        "Signed stop-line error",
                    )
                ),
                "Zero activity is a retained scientific outcome"
                in (sf4_analysis_path.parent / "sf4_authority_manipulation_and_first_stage.tex").read_text(encoding="utf-8"),
                all(
                    phrase
                    in (
                        sf4_analysis_path.parent / "sf4_computational_wall_time.tex"
                    ).read_text(encoding="utf-8")
                    for phrase in (
                        "Ego policy P50",
                        "Ego policy P95",
                        "Ego policy P99",
                        "Shared prediction P50",
                        "Shared prediction P95",
                        "Shared prediction P99",
                        "not an end-to-end deployment or real-time guarantee",
                    )
                ),
                "not strict optimizer optimality or feasibility"
                in (sf4_analysis_path.parent / "sf4_controller_acceptance_and_solver_status.tex").read_text(encoding="utf-8"),
            )
        )
        keys: set[tuple[str, int]] = set()
        raw_hashes_ok = True
        critical_hashes_ok = True
        init_counts: dict[int, int] = {}
        for receipt_path in sf4_receipts:
            receipt = load_json(receipt_path)
            cell_id = str(receipt.get("cell_id", receipt_path.parent.name))
            init_id = int(receipt.get("ego_init_id", -1))
            keys.add((cell_id, init_id))
            init_counts[init_id] = init_counts.get(init_id, 0) + 1
            raw_hashes_ok = raw_hashes_ok and all(
                (
                    receipt.get("schema_version") == "formal_rollout_complete_v1",
                    receipt.get("stage") == "SF4",
                    receipt.get("status") == "pass",
                    cell_id == receipt_path.parent.name,
                    (cell_id, init_id) in execution_keys,
                )
            )
            raw_hashes_ok = raw_hashes_ok and _sha256_token(
                receipt.get("raw_evidence_sha256")
            )
            critical = receipt.get("critical_artifacts") or {}
            for required in SF4_REQUIRED_RAW_FILES:
                record = critical.get(required)
                critical_hashes_ok = critical_hashes_ok and isinstance(record, dict)
                if isinstance(record, dict):
                    critical_hashes_ok = critical_hashes_ok and _sha256_token(
                        record.get("sha256")
                    ) and int(record.get("bytes", 0)) > 0
            receipt_records.append((receipt_path, receipt))
        sf4_core_ok = all(
            (
                contract_ok,
                sf4_complete.get("status") == "pass",
                sf4_complete.get("schema_version")
                == "sf4_supervisor_behavioural_authority_complete_v1",
                sf4_complete.get("formal_evidence") is True,
                sf4_complete.get("observed_rollouts") == 80,
                sf4_complete.get("independent_init_clusters") == 10,
                sf4_complete.get("analysis_complete_sha256") == sha256(sf4_analysis_path),
                sf4_complete.get("contract_sha256") == sha256(sf4_contract_path),
                sf4_complete.get("preregistration_sha256") == sha256(sf4_prereg_path),
                sf4_complete.get("implementation_manipulation_gate")
                == implementation_gate,
                sf4_complete.get("observed_first_stage_activity_status")
                == first_stage.get("status"),
                sf4_complete.get("solver_execution")
                == sf4_analysis.get("solver_execution"),
                sf4_complete.get("server_wall_time_diagnostics") == sf4_wall_time,
                sf4_complete.get("additional_sf4_carla_rollouts_required") is False,
                sf4_complete.get("source_raw_evidence_deleted") is False,
                sf4_analysis.get("status") == "pass",
                sf4_analysis.get("schema_version")
                == "sf4_supervisor_behavioural_authority_analysis_complete_v1",
                sf4_analysis.get("formal_evidence") is True,
                sf4_analysis.get("observed_rollouts") == 80,
                sf4_analysis.get("independent_init_clusters") == 10,
                sf4_analysis.get("integrity_gate") == "pass",
                sf4_analysis.get("primary_estimand")
                == "(adaptive-fixed_medium)_on - (adaptive-fixed_medium)_off",
                sf4_analysis.get("primary_outcome")
                == "failure_penalized_completion_time_s",
                manipulation_ok,
                controller_ok,
                wall_time_ok,
                inference_ok,
                input_manifest_ok,
                tex_semantics_ok,
                len(sf4_receipts) == len(keys) == 80,
                keys == execution_keys,
                set(init_counts) == set(range(106, 116)),
                all(count == 8 for count in init_counts.values()),
                raw_hashes_ok,
                critical_hashes_ok,
                products_ok,
                products_exact,
                product_count == len(SF4_REQUIRED_ANALYSIS_PRODUCTS),
            )
        )
        for path in (
            sf4_complete_path,
            sf4_analysis_path,
            sf4_contract_path,
            sf4_prereg_path,
            *(sf4_analysis_path.parent / name for name in SF4_REQUIRED_ANALYSIS_PRODUCTS),
            *(repo / relative for relative in SF4_REQUIRED_EXECUTION_SOURCES),
            *(
                sf4_root / frozen_tuning_paths[mode]
                for mode in ("on", "off")
            ),
            *sf4_receipts,
        ):
            bind(path)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(f"sf4_core_exception:{type(exc).__name__}")
    _record_check(
        checks,
        failures,
        "sf4_80_rollouts_10_clusters_analysis",
        sf4_core_ok,
        display(sf4_complete_path),
    )

    full_sidecar_path = _find_existing(
        [
            sf4_root / "SF4_FULL_RAW_SNAPSHOT_COMPLETE.json",
            sf4_root
            / "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.json",
        ]
    )
    sf4_snapshot_ok = False
    try:
        sidecar = load_json(full_sidecar_path)
        archive_sidecar_value = sidecar.get("archive_sidecar")
        archive_sidecar_path = (
            sf4_root / Path(str(archive_sidecar_value)).name
            if archive_sidecar_value
            else sf4_root
            / "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.json"
        )
        archive_sidecar = load_json(archive_sidecar_path)
        manifest_value = sidecar.get("files_manifest")
        manifest_path = (
            sf4_root / Path(str(manifest_value)).name
            if manifest_value
            else sf4_root
            / "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.files.json"
        )
        snapshot_manifest = load_json(manifest_path)
        manifest_records = _manifest_file_map(snapshot_manifest)
        explicit_full_raw = all(
            (
                sidecar.get("schema_version")
                == "sf4_full_raw_snapshot_complete_v1",
                sidecar.get("formal_evidence") is True,
                sidecar.get("observed_rollouts") == 80,
                sidecar.get("receipt_raw_and_attempt_provenance_verified") is True,
                sidecar.get("bbox_and_separation_recomputation_supported") is True,
                sidecar.get("server_wall_time_recomputation_supported") is True,
                sidecar.get(
                    "controller_acceptance_and_raw_status_recomputation_supported"
                )
                is True,
                sidecar.get("source_files_deleted") is False,
                archive_sidecar.get("schema_version")
                == "sf4_supervisor_behavioural_authority_full_raw_snapshot_v1",
                archive_sidecar.get("status") == "pass",
                archive_sidecar.get("observed_rollouts") == 80,
                archive_sidecar.get("full_raw_evidence") is True,
                archive_sidecar.get("server_wall_time_recomputation_supported")
                is True,
                archive_sidecar.get(
                    "controller_acceptance_and_raw_status_recomputation_supported"
                )
                is True,
                archive_sidecar.get("source_files_deleted") is False,
                snapshot_manifest.get("schema_version")
                == "sf4_supervisor_behavioural_authority_full_raw_snapshot_files_manifest_v1",
                snapshot_manifest.get("status") == "pass",
                snapshot_manifest.get("source_files_deleted") is False,
            )
        )
        archive_value = sidecar.get("archive")
        archive_path = sf4_root / Path(str(archive_value)).name if archive_value else Path()
        archive_hash_ok = all(
            (
                _sha256_token(sidecar.get("archive_sha256")),
                archive_sidecar.get("archive_sha256")
                == sidecar.get("archive_sha256"),
                sf4_complete.get("full_raw_snapshot_sha256")
                == sidecar.get("archive_sha256"),
                sf4_complete.get("full_raw_snapshot_complete_sha256")
                == sha256(full_sidecar_path),
                sf4_complete.get("full_raw_snapshot_sidecar_sha256")
                == sha256(archive_sidecar_path),
                sidecar.get("archive_sidecar_sha256")
                == sha256(archive_sidecar_path),
            )
        )
        if archive_value and archive_path.is_file():
            archive_hash_ok = archive_hash_ok and sha256(archive_path) == sidecar.get(
                "archive_sha256"
            )
        manifest_hash_ok = all(
            (
                sidecar.get("files_manifest_sha256") == sha256(manifest_path),
                archive_sidecar.get("files_manifest_sha256") == sha256(manifest_path),
                sf4_complete.get("full_raw_snapshot_files_manifest_sha256")
                == sha256(manifest_path),
            )
        )
        required_counts = {
            required: sum(path.endswith("/" + required) or path == required for path in manifest_records)
            for required in SF4_REQUIRED_RAW_FILES
        }
        external_records = snapshot_manifest.get("external_files") or []
        external_prereg_ok = any(
            record.get("path")
            == "_external/SF4_SUPERVISOR_BEHAVIOURAL_AUTHORITY_PREREG.json"
            and record.get("sha256") == sha256(sf4_prereg_path)
            and int(record.get("bytes", 0)) == sf4_prereg_path.stat().st_size
            for record in external_records
        )
        snapshot_analysis_ok = all(
            (
                (_manifest_record(manifest_records, sf4_contract_path.name) or {}).get(
                    "sha256"
                )
                == sha256(sf4_contract_path),
                (
                    _manifest_record(
                        manifest_records, "analysis/SF4_ANALYSIS_COMPLETE.json"
                    )
                    or {}
                ).get("sha256")
                == sha256(sf4_analysis_path),
                all(
                    (
                        _manifest_record(manifest_records, f"analysis/{name}") or {}
                    ).get("sha256")
                    == sha256(sf4_analysis_path.parent / name)
                    for name in SF4_REQUIRED_ANALYSIS_PRODUCTS
                ),
            )
        )
        snapshot_receipts_ok = len(receipt_records) == 80
        for receipt_path, receipt in receipt_records:
            receipt_relative = receipt_path.relative_to(sf4_root).as_posix()
            receipt_record = _manifest_record(manifest_records, receipt_relative)
            if receipt_record is None or receipt_record.get("sha256") != sha256(receipt_path):
                snapshot_receipts_ok = False
                break
            scenario_dir = str(receipt.get("scenario_dir", "")).strip("/")
            cell = receipt_path.parent.relative_to(sf4_root).as_posix()
            critical = receipt.get("critical_artifacts") or {}
            for required in SF4_REQUIRED_RAW_FILES:
                relative = f"{cell}/{scenario_dir}/{required}"
                record = _manifest_record(manifest_records, relative)
                if record is None or record.get("sha256") != critical[required]["sha256"]:
                    snapshot_receipts_ok = False
                    break
            if not snapshot_receipts_ok:
                break
        sf4_snapshot_ok = all(
            (
                sidecar.get("status") == "pass",
                explicit_full_raw,
                archive_hash_ok,
                manifest_hash_ok,
                bool(manifest_records),
                len(snapshot_manifest.get("rollouts", [])) == 80,
                (snapshot_manifest.get("coverage") or {}).get(
                    "receipt_raw_and_attempt_provenance_verified"
                )
                is True,
                (snapshot_manifest.get("coverage") or {}).get(
                    "all_canonical_scenario_files_included"
                )
                is True,
                (snapshot_manifest.get("coverage") or {}).get(
                    "all_attempt_provenance_files_included"
                )
                is True,
                (snapshot_manifest.get("coverage") or {}).get(
                    "server_wall_time_recomputation_supported"
                )
                is True,
                (snapshot_manifest.get("coverage") or {}).get(
                    "controller_acceptance_and_raw_status_recomputation_supported"
                )
                is True,
                sf4_complete.get("bbox_and_separation_recomputation_supported")
                is True,
                sf4_complete.get("server_wall_time_recomputation_supported")
                is True,
                sf4_complete.get(
                    "controller_acceptance_and_raw_status_recomputation_supported"
                )
                is True,
                external_prereg_ok,
                snapshot_analysis_ok,
                snapshot_receipts_ok,
                all(count >= 80 for count in required_counts.values()),
            )
        )
        for path in (full_sidecar_path, archive_sidecar_path, manifest_path):
            bind(path)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(f"sf4_full_snapshot_exception:{type(exc).__name__}")
    _record_check(
        checks,
        failures,
        "sf4_full_raw_snapshot_and_hash_manifest",
        sf4_snapshot_ok,
        display(full_sidecar_path),
    )

    return {
        "schema_version": "supervisor_feedback_final_closure_gate_v1",
        "status": "pass" if checks and all(checks.values()) else "incomplete",
        "final_release_eligible": bool(checks) and all(checks.values()),
        "checks": checks,
        "failures": failures,
        "canonical_roots": {
            "supervisor_feedback": display(feedback_root),
            "sf4_results": display(sf4_root),
        },
        "verified_files_sha256": dict(sorted(verified_files.items())),
        "requirements": {
            "sf1": "80 hash-bound corrected-R3 behaviour rollouts plus verified source snapshot",
            "sf2": "80-file raw taxonomy and exact deadline evaluation pass",
            "sf3": "fine-tuning audit receipt, artifact hashes and source hashes pass",
            "sf4": "80 rollouts / 10 init clusters, analysis/manipulation pass, and full raw snapshot manifest/hash pass",
        },
    }


def audit_supervisor_feedback_content_integration(
    repo: Path,
    *,
    closure_mode: str = CLOSURE_FINAL,
    closure_payload: dict[str, Any] | None = None,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Require final results to be reachable, hash-bound compiled LaTeX inputs.

    Evidence-ID comments are useful locators, but deliberately insufficient:
    final eligibility requires canonical scientific tables to be directly
    input by one generated wrapper, that wrapper to be input by Results, and a
    successful current-source LaTeX build bound by the generated marker.
    """

    if closure_mode not in CLOSURE_MODES:
        raise ValueError(f"Unknown supervisor-feedback closure mode: {closure_mode}")
    repo = repo.resolve()
    try:
        from .build_supervisor_feedback_paper_integration import (
            ALL_CONTENT_EVIDENCE_IDS,
            CANONICAL_EVIDENCE_ASSETS,
            CANONICAL_EVIDENCE_DATA_SOURCES,
            CONCLUSION_RELATIVE,
            CONCLUSION_WRAPPER_LATEX_INPUT,
            CONCLUSION_WRAPPER_RELATIVE,
            DISCUSSION_WRAPPER_LATEX_INPUT,
            DISCUSSION_WRAPPER_RELATIVE,
            DISCUSSION_RELATIVE,
            LEGACY_DIRECT_SF2_INPUT_PREFIX,
            LEGACY_SF4_PRODUCTION_TOKENS,
            MAIN_RELATIVE,
            MARKER_RELATIVE,
            MISLEADING_SOLVER_PHRASE_PATTERN,
            PROVISIONAL_CONCLUSION_SENTINEL,
            RESULTS_RELATIVE,
            SCHEMA_VERSION as INTEGRATION_SCHEMA_VERSION,
            SF3_RESULTS_EVIDENCE_ID,
            SF3_RESULTS_LATEX_INPUT,
            WRAPPER_LATEX_INPUT,
            WRAPPER_RELATIVE,
            build_result_narrative,
            legacy_sf4_production_reference_hits,
            obsolete_percentage_accuracy_claim_hits,
            sf3_retraction_explanation_complete,
            strip_latex_comments,
        )
    except ImportError:  # pragma: no cover - direct script execution
        from build_supervisor_feedback_paper_integration import (  # type: ignore
            ALL_CONTENT_EVIDENCE_IDS,
            CANONICAL_EVIDENCE_ASSETS,
            CANONICAL_EVIDENCE_DATA_SOURCES,
            CONCLUSION_RELATIVE,
            CONCLUSION_WRAPPER_LATEX_INPUT,
            CONCLUSION_WRAPPER_RELATIVE,
            DISCUSSION_WRAPPER_LATEX_INPUT,
            DISCUSSION_WRAPPER_RELATIVE,
            DISCUSSION_RELATIVE,
            LEGACY_DIRECT_SF2_INPUT_PREFIX,
            LEGACY_SF4_PRODUCTION_TOKENS,
            MAIN_RELATIVE,
            MARKER_RELATIVE,
            MISLEADING_SOLVER_PHRASE_PATTERN,
            PROVISIONAL_CONCLUSION_SENTINEL,
            RESULTS_RELATIVE,
            SCHEMA_VERSION as INTEGRATION_SCHEMA_VERSION,
            SF3_RESULTS_EVIDENCE_ID,
            SF3_RESULTS_LATEX_INPUT,
            WRAPPER_LATEX_INPUT,
            WRAPPER_RELATIVE,
            build_result_narrative,
            legacy_sf4_production_reference_hits,
            obsolete_percentage_accuracy_claim_hits,
            sf3_retraction_explanation_complete,
            strip_latex_comments,
        )
    closure = closure_payload or audit_supervisor_feedback_closure(repo)
    marker = marker_path or (repo / MARKER_RELATIVE)
    latex = repo / "docs/dissertation/latex"
    tex_files = sorted(latex.rglob("*.tex")) if latex.is_dir() else []
    raw_tex = "\n".join(path.read_text(encoding="utf-8") for path in tex_files)
    visible_tex = strip_latex_comments(raw_tex)

    input_pattern = re.compile(r"\\(?:input|include)\s*\{\s*([^}]+?)\s*\}")

    def visible(path: Path) -> str:
        return strip_latex_comments(path.read_text(encoding="utf-8"))

    def resolve_input(value: str) -> Path:
        candidate = latex / value
        if not candidate.suffix:
            candidate = candidate.with_suffix(".tex")
        return candidate.resolve()

    def direct_inputs(path: Path) -> set[Path]:
        if not path.is_file():
            return set()
        return {resolve_input(value) for value in input_pattern.findall(visible(path))}

    def reachable_inputs(start: Path) -> set[Path]:
        reachable: set[Path] = set()
        pending = [start.resolve()]
        while pending:
            current = pending.pop()
            if current in reachable or not current.is_file():
                continue
            reachable.add(current)
            for child in direct_inputs(current):
                if child not in reachable:
                    pending.append(child)
        return reachable

    main_path = repo / MAIN_RELATIVE
    results_path = repo / RESULTS_RELATIVE
    discussion_path = repo / DISCUSSION_RELATIVE
    conclusion_path = repo / CONCLUSION_RELATIVE
    wrapper_path = repo / WRAPPER_RELATIVE
    discussion_wrapper_path = repo / DISCUSSION_WRAPPER_RELATIVE
    conclusion_wrapper_path = repo / CONCLUSION_WRAPPER_RELATIVE
    reachable = reachable_inputs(main_path) if main_path.is_file() else set()
    results_direct = direct_inputs(results_path)
    discussion_direct = direct_inputs(discussion_path)
    conclusion_direct = direct_inputs(conclusion_path)
    wrapper_direct = direct_inputs(wrapper_path)
    sf3_path = (repo / CANONICAL_EVIDENCE_ASSETS[SF3_RESULTS_EVIDENCE_ID]).resolve()
    obsolete_accuracy_hits_raw = obsolete_percentage_accuracy_claim_hits(
        sorted(path for path in reachable if path.suffix == ".tex")
    )
    obsolete_accuracy_hits = []
    for raw_hit in obsolete_accuracy_hits_raw:
        hit_path = Path(raw_hit).resolve()
        try:
            obsolete_accuracy_hits.append(hit_path.relative_to(repo).as_posix())
        except ValueError:
            obsolete_accuracy_hits.append(hit_path.as_posix())
    results_visible = visible(results_path) if results_path.is_file() else ""
    conclusion_visible = visible(conclusion_path) if conclusion_path.is_file() else ""
    conclusion_wrapper_raw = (
        conclusion_wrapper_path.read_text(encoding="utf-8")
        if conclusion_wrapper_path.is_file()
        else ""
    )
    wrapper_visible = visible(wrapper_path) if wrapper_path.is_file() else ""
    final_results_visible = results_visible + "\n" + wrapper_visible
    forbidden_patterns = {
        "pre_sf4_evidence_cut": r"\bpre[- ]SF4(?:\s+evidence\s+cut)?\b",
        "provisional_supervisor_feedback": r"\bprovisional\b[^.]{0,100}\b(?:SF[124]|supervisor)",
        "sf4_pending_or_not_run": r"\bSF4\b[^.]{0,100}\b(?:pending|not\s+run|awaiting)",
    }
    forbidden_hits = {
        name: re.findall(pattern, visible_tex, flags=re.IGNORECASE)
        for name, pattern in forbidden_patterns.items()
        if re.search(pattern, visible_tex, flags=re.IGNORECASE)
    }
    stale_result_patterns = {
        "conditional_sf2_receipt_language": (
            r"\bUntil\b[^.]{0,240}\b(?:receipt|raw(?:\s+archive)?|hash[- ]verified)"
            r"[^.]{0,160}\b(?:pass|complete|available)\b"
        ),
        "attempted_optimal_nonoptimal_semantics": (
            r"\battempted[-_ ](?:optimal|non[-_ ]?optimal)\b"
        ),
        "affirmative_feasibility_from_controller_acceptance": (
            r"\b(?:controller[- ]accepted|logger[- ]accepted|is[_ ]?opt|"
            r"optimal attempts?|accepted attempts?)\b[^.]{0,100}"
            r"\b(?:proves?|establishes?|means?|constitutes?|guarantees?)\b"
            r"[^.]{0,80}\bfeasib(?:le|ility)\b"
            r"|\bfeasib(?:le|ility)\b[^.]{0,100}\b(?:is|was)\s+"
            r"(?:measured|defined|established|proved)\s+by\b[^.]{0,80}"
            r"\b(?:is[_ ]?opt|accept(?:ed|ance))\b"
        ),
    }
    stale_result_hits = {
        name: re.findall(pattern, final_results_visible, flags=re.IGNORECASE)
        for name, pattern in stale_result_patterns.items()
        if re.search(pattern, final_results_visible, flags=re.IGNORECASE)
    }
    misleading_solver_phrase_hits = bool(
        MISLEADING_SOLVER_PHRASE_PATTERN.search(final_results_visible)
    )
    legacy_sf4_hits = legacy_sf4_production_reference_hits(
        visible_tex + "\n" + final_results_visible
    )
    checks: dict[str, bool] = {
        "scientific_closure_pass": closure.get("status") == "pass",
        "integration_marker_present": marker.is_file(),
        "pre_sf4_or_provisional_wording_absent": not forbidden_hits,
        "stale_conditional_or_feasibility_semantics_absent": not stale_result_hits,
        "misleading_attempted_solve_latency_feasibility_phrase_absent": (
            not misleading_solver_phrase_hits
        ),
        "obsolete_sf4_action_ablation_production_references_absent": (
            not legacy_sf4_hits
        ),
        "obsolete_percentage_accuracy_claim_absent": not obsolete_accuracy_hits,
        "required_evidence_id_locators_in_reachable_wrapper": wrapper_path.resolve()
        in reachable
        and all(
            evidence_id in wrapper_path.read_text(encoding="utf-8")
            for evidence_id in SUPERVISOR_CONTENT_EVIDENCE_IDS
        ),
        "results_directly_inputs_canonical_wrapper": wrapper_path.resolve()
        in results_direct,
        "discussion_directly_inputs_canonical_dynamic_interpretation": (
            discussion_wrapper_path.resolve() in discussion_direct
        ),
        "conclusion_directly_inputs_canonical_dynamic_synthesis": (
            conclusion_wrapper_path.resolve() in conclusion_direct
        ),
        "dynamic_conclusion_is_final_not_provisional": (
            conclusion_wrapper_path.is_file()
            and PROVISIONAL_CONCLUSION_SENTINEL not in conclusion_wrapper_raw
        ),
        "results_directly_inputs_corrected_sf3_table": sf3_path in results_direct,
        "legacy_direct_preliminary_sf2_inputs_absent": (
            LEGACY_DIRECT_SF2_INPUT_PREFIX not in results_visible
        ),
        "sf3_percentage_accuracy_withdrawal_explained": (
            sf3_retraction_explanation_complete(results_visible)
        ),
        "results_discussion_conclusion_and_wrappers_reachable_from_main": all(
            path.resolve() in reachable
            for path in (
                results_path,
                discussion_path,
                conclusion_path,
                wrapper_path,
                discussion_wrapper_path,
                conclusion_wrapper_path,
            )
        ),
    }
    failures: list[str] = [name for name, passed in checks.items() if not passed]
    verified_artifacts: dict[str, str] = {}
    marker_payload: dict[str, Any] = {}
    try:
        marker_payload = load_json(marker)
        checks["integration_marker_status_pass"] = all(
            (
                marker_payload.get("schema_version") == INTEGRATION_SCHEMA_VERSION,
                marker_payload.get("status") == "pass",
                marker_payload.get("final_release_eligible") is True,
            )
        )
        generator_relative = marker_payload.get("generated_by")
        generator_path = repo / str(generator_relative)
        checks["current_integration_builder_hash_bound"] = all(
            (
                generator_path.resolve()
                == (repo / "core/scripts/models/tools/build_supervisor_feedback_paper_integration.py").resolve(),
                generator_path.is_file(),
                _sha256_token(marker_payload.get("generated_by_sha256")),
                generator_path.is_file()
                and marker_payload.get("generated_by_sha256") == sha256(generator_path),
            )
        )
        declared_ids = marker_payload.get("evidence_ids") or []
        checks["integration_marker_has_required_evidence_ids"] = (
            declared_ids == list(ALL_CONTENT_EVIDENCE_IDS)
        )
        checks["integration_marker_evidence_placement_exact"] = all(
            (
                marker_payload.get("wrapper_evidence_ids")
                == list(SUPERVISOR_CONTENT_EVIDENCE_IDS),
                marker_payload.get("results_evidence_ids")
                == [SF3_RESULTS_EVIDENCE_ID],
            )
        )
        artifacts = marker_payload.get("artifacts") or {}
        artifact_ok = isinstance(artifacts, dict) and len(artifacts) >= 12
        for relative, record in artifacts.items() if isinstance(artifacts, dict) else ():
            expected = record.get("sha256") if isinstance(record, dict) else record
            path = repo / str(relative)
            if not path.is_file() or not _sha256_token(expected) or sha256(path) != expected:
                artifact_ok = False
                continue
            verified_artifacts[str(relative)] = expected
        checks["integration_artifacts_hash_bound"] = artifact_ok
        expected_narrative = build_result_narrative(repo)
        marker_narrative = marker_payload.get("result_narrative")
        checks["result_specific_narrative_exact_and_hash_bound"] = (
            marker_narrative == expected_narrative
        )
        narrative_texts = [
            str(expected_narrative[section]["text"])
            for section in ("sf1", "sf2", "sf4")
        ]
        narrative_positions = [wrapper_visible.find(text) for text in narrative_texts]
        checks["result_specific_narrative_visible_once_and_in_order"] = all(
            wrapper_visible.count(text) == 1 for text in narrative_texts
        ) and narrative_positions == sorted(narrative_positions) and all(
            position >= 0 for position in narrative_positions
        )
        discussion_wrapper_visible = (
            visible(discussion_wrapper_path)
            if discussion_wrapper_path.is_file()
            else ""
        )
        expected_discussion_text = str(expected_narrative["discussion"]["text"])
        checks["dynamic_discussion_interpretation_exact_and_visible_once"] = (
            discussion_wrapper_visible.count(expected_discussion_text) == 1
        )
        discussion_lower = discussion_wrapper_visible.lower()
        discussion_status = expected_narrative["discussion"]["facts"][
            "first_stage_status"
        ]
        checks["dynamic_discussion_claim_boundary_present"] = all(
            (
                "does not identify masking, amplification or a null supervisor interaction"
                in discussion_lower
                if discussion_status == "inactive_scientific_outcome"
                else "masking-like means only" in discussion_lower,
                "sole cause" in discussion_lower,
                "scientific outcome" in discussion_lower
                if discussion_status == "inactive_scientific_outcome"
                else all(
                    phrase in discussion_lower
                    for phrase in (
                        "estimates a bounded interaction contrast",
                        "supports a non-zero interaction is determined by its cluster interval",
                        "observed first stage",
                    )
                ),
                "predictor" in discussion_lower,
                "risk allocation" in discussion_lower,
                "smpc constraints remain shared" in discussion_lower,
            )
        )
        conclusion_wrapper_visible = (
            visible(conclusion_wrapper_path)
            if conclusion_wrapper_path.is_file()
            else ""
        )
        expected_conclusion_text = str(expected_narrative["conclusion"]["text"])
        checks["dynamic_conclusion_synthesis_exact_and_visible_once"] = (
            conclusion_wrapper_visible.count(expected_conclusion_text) == 1
        )
        conclusion_lower = conclusion_wrapper_visible.lower()
        conclusion_facts = expected_narrative["conclusion"]["facts"]
        conclusion_status = conclusion_facts["first_stage_status"]
        completion_pattern = conclusion_facts["primary_completion_point_pattern"]
        active_pattern_labels = {
            "masking_like_attenuation_point_pattern": "attenuation point-pattern",
            "amplifying_like_point_pattern": "amplification point-pattern",
            "direction_reversing_point_pattern": "direction reversal point-pattern",
            "near_null_interaction_point_pattern": "near-null point-pattern",
        }
        common_conclusion_boundaries = all(
            (
                "town05/b1 adaptive-versus-fixed-medium" in conclusion_lower,
                bool(
                    re.search(
                        r"do(?:es)? not make the supervisor the sole cause",
                        conclusion_lower,
                    )
                ),
                "shared b1 predictor" in conclusion_lower,
                "estimator-to-risk interface" in conclusion_lower,
                "risk-allocation implementation" in conclusion_lower,
                "smpc constraints" in conclusion_lower,
                conclusion_facts.get("sole_cause_claim") is False,
                conclusion_facts.get("scope")
                == "Town05/B1/adaptive-versus-fixed-medium",
                conclusion_facts.get("sentence_count") == 3,
            )
        )
        if conclusion_status == "active":
            expected_pattern_label = active_pattern_labels.get(completion_pattern, "")
            status_specific_conclusion = all(
                (
                    bool(expected_pattern_label),
                    expected_pattern_label in conclusion_lower,
                    "primary failure-penalised completion did" in conclusion_lower,
                    "cluster-bootstrap 95\\% ci" in conclusion_lower,
                    "interval uncertainty" in conclusion_lower,
                    (
                        "the interval spans zero" in conclusion_lower
                        if conclusion_facts.get("primary_completion_ci_spans_zero") is True
                        else "the interval does not span zero" in conclusion_lower
                    ),
                    "benefit or harm" in conclusion_lower,
                )
            )
        else:
            status_specific_conclusion = all(
                (
                    conclusion_status == "inactive_scientific_outcome",
                    completion_pattern == "not_identified_inactive_first_stage",
                    "passed its implementation gate" in conclusion_lower,
                    "first stage was inactive" in conclusion_lower,
                    "are not identified" in conclusion_lower,
                    "scientific outcome" in conclusion_lower,
                    "point-pattern" not in conclusion_lower,
                )
            )
        nonprimary_endpoint_repetition = any(
            phrase in conclusion_lower
            for phrase in (
                "cautious approach progress",
                "stop-line error",
                "stopped duration",
                "path-release latency",
                "sustained-resume latency",
                "margin-adjusted bbox separation",
            )
        )
        checks["dynamic_conclusion_claim_boundary_present"] = all(
            (
                common_conclusion_boundaries,
                status_specific_conclusion,
                not nonprimary_endpoint_repetition,
            )
        )
        expected_narrative_sources = expected_narrative.get("source_sha256") or {}
        checks["result_narrative_scientific_sources_hash_bound"] = bool(
            expected_narrative_sources
        ) and all(
            (repo / relative).is_file()
            and expected == sha256(repo / relative)
            and isinstance(artifacts.get(relative), dict)
            and artifacts[relative].get("sha256") == expected
            and artifacts[relative].get("bytes") == (repo / relative).stat().st_size
            and artifacts[relative].get("result_narrative_source") is True
            for relative, expected in expected_narrative_sources.items()
        )
        narrative_lower = wrapper_visible.lower()
        checks["result_narrative_scientific_boundaries_present"] = all(
            (
                "27 stop/resume/hysteresis definitions" in narrative_lower,
                "all 21 adaptive-minus-fixed mechanism cells" in narrative_lower,
                "fixed-aggressive" in narrative_lower,
                "fixed-medium" in narrative_lower,
                "fixed-conservative" in narrative_lower,
                "censored at missing release" in narrative_lower,
                "terminal stop is never substituted" in narrative_lower,
                "stop--path-release duration" in narrative_lower,
                "frozen-route coordinates, not bumper clearances" in narrative_lower,
                "positive upstream, negative after conflict" in narrative_lower,
                "positive means stopped upstream/short of the configured stop point"
                in narrative_lower,
                "na denotes scientific censoring" in narrative_lower,
                "finite recorded casadi solve-stage" in narrative_lower,
                "optimizer-internal" in narrative_lower,
                "neither end-to-end latency" in narrative_lower,
                "suboptimal" in narrative_lower,
                "not a certificate of mathematical optimality or feasibility"
                in narrative_lower,
                "cluster-paired adaptive-minus-fixed effects" in narrative_lower,
                "percentage points" in narrative_lower,
                "post-hoc small-n sensitivities, not treatment-randomisation inference"
                in narrative_lower,
                "joins exactly one canonical rollout" in narrative_lower,
                "occurred across" in narrative_lower,
                "descriptive and does not identify" in narrative_lower,
                "primary did" in narrative_lower,
                "direct adaptive-minus-fixed-medium effects" in narrative_lower,
                "implementation gate passed" in narrative_lower,
                "first-stage status" in narrative_lower,
                "minimum 0.25-m/actor margin-adjusted bbox separation"
                in narrative_lower,
                "cautious approach progress after yield entry" in narrative_lower,
                "first sustained-stop distance to conflict" in narrative_lower,
                "signed stop-line error" in narrative_lower,
                "stopped duration" in narrative_lower,
                "nominal-clear--actual-path-release latency" in narrative_lower,
                "actual-path-release--sustained-resume latency" in narrative_lower,
                "buffered-clear--sustained-resume latency" in narrative_lower,
                "authority on-minus-off within adaptive" in narrative_lower,
                "and within fixed-medium" in narrative_lower,
                "not automatically a benefit" in narrative_lower,
                "na/censored" in narrative_lower,
                "shared-prediction" in narrative_lower,
                "p50" in narrative_lower,
                "p95" in narrative_lower,
                "p99" in narrative_lower,
                "not a measured end-to-end loop latency" in narrative_lower,
                "deployment or real-time guarantee" in narrative_lower,
                "missing/non-finite secondary timing remains na" in narrative_lower,
                "zero first-stage activity would be retained as a scientific outcome"
                in narrative_lower,
            )
        )
        marker_visible = json.dumps(marker_payload, sort_keys=True).lower()
        checks["integration_marker_rejects_legacy_sf4_production_paths"] = not any(
            token in marker_visible for token in LEGACY_SF4_PRODUCTION_TOKENS
        )
        canonical_assets = marker_payload.get("canonical_evidence_assets") or {}
        expected_canonical_assets = {
            evidence_id: str(CANONICAL_EVIDENCE_ASSETS[evidence_id])
            for evidence_id in ALL_CONTENT_EVIDENCE_IDS
        }
        checks["canonical_per_id_assets_exact"] = canonical_assets == expected_canonical_assets
        canonical_data_sources = marker_payload.get(
            "canonical_evidence_data_sources"
        ) or {}
        expected_canonical_data_sources = {
            evidence_id: [str(path) for path in CANONICAL_EVIDENCE_DATA_SOURCES[evidence_id]]
            for evidence_id in ALL_CONTENT_EVIDENCE_IDS
        }
        checks["canonical_per_id_data_sources_exact"] = (
            canonical_data_sources == expected_canonical_data_sources
        )
        canonical_paths = {
            evidence_id: (repo / expected_canonical_assets[evidence_id]).resolve()
            for evidence_id in ALL_CONTENT_EVIDENCE_IDS
        }
        checks["canonical_assets_directly_input_and_reachable"] = all(
            path in reachable
            and (
                path in results_direct
                if evidence_id == SF3_RESULTS_EVIDENCE_ID
                else path in wrapper_direct
            )
            for evidence_id, path in canonical_paths.items()
        )
        checks["canonical_assets_are_substantive_tables"] = all(
            path.is_file()
            and re.search(
                r"\\begin\{table\*?\}", path.read_text(encoding="utf-8")
            )
            and len(path.read_text(encoding="utf-8").strip()) >= 100
            for path in canonical_paths.values()
        )
        evidence_data_sources = marker_payload.get("evidence_data_sources") or {}
        checks["canonical_data_sources_hash_bound"] = all(
            evidence_data_sources.get(evidence_id)
            == expected_canonical_data_sources[evidence_id]
            and all(
                relative in artifacts
                and (repo / relative).is_file()
                and artifacts[relative].get("role")
                == "canonical_scientific_data_source"
                and artifacts[relative].get("bytes") == (repo / relative).stat().st_size
                and artifacts[relative].get("sha256") == sha256(repo / relative)
                for relative in expected_canonical_data_sources[evidence_id]
            )
            for evidence_id in ALL_CONTENT_EVIDENCE_IDS
        )
        evidence_assets = marker_payload.get("evidence_assets") or {}
        checks["every_required_id_has_generated_asset"] = all(
            set(evidence_assets.get(evidence_id) or ())
            == {
                (
                    str(RESULTS_RELATIVE)
                    if evidence_id == SF3_RESULTS_EVIDENCE_ID
                    else str(WRAPPER_RELATIVE)
                ),
                expected_canonical_assets[evidence_id],
            }
            and (
                str(RESULTS_RELATIVE)
                if evidence_id == SF3_RESULTS_EVIDENCE_ID
                else str(WRAPPER_RELATIVE)
            )
            in artifacts
            and expected_canonical_assets[evidence_id] in artifacts
            for evidence_id in ALL_CONTENT_EVIDENCE_IDS
        )
        checks["canonical_wrapper_hash_bound"] = all(
            (
                marker_payload.get("canonical_wrapper") == str(WRAPPER_RELATIVE),
                wrapper_path.is_file(),
                marker_payload.get("canonical_wrapper_sha256") == sha256(wrapper_path),
            )
        )
        checks["canonical_discussion_wrapper_hash_bound"] = all(
            (
                marker_payload.get("canonical_discussion_wrapper")
                == str(DISCUSSION_WRAPPER_RELATIVE),
                discussion_wrapper_path.is_file(),
                marker_payload.get("canonical_discussion_wrapper_sha256")
                == sha256(discussion_wrapper_path),
            )
        )
        checks["canonical_conclusion_wrapper_hash_bound"] = all(
            (
                marker_payload.get("canonical_conclusion_wrapper")
                == str(CONCLUSION_WRAPPER_RELATIVE),
                conclusion_wrapper_path.is_file(),
                marker_payload.get("canonical_conclusion_wrapper_sha256")
                == sha256(conclusion_wrapper_path),
            )
        )
        manuscript_sources = marker_payload.get("manuscript_sources") or {}
        expected_manuscript_paths = (
            main_path,
            results_path,
            discussion_path,
            conclusion_path,
        )
        checks["results_discussion_conclusion_main_hash_bound"] = all(
            path.is_file()
            and manuscript_sources.get(path.relative_to(repo).as_posix()) == sha256(path)
            for path in expected_manuscript_paths
        )
        source_receipts = marker_payload.get("source_receipts") or {}
        closure_files = closure.get("verified_files_sha256") or {}
        receipt_names = (
            "SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json",
            "SUPERVISOR_FEEDBACK_02_COMPLETE.json",
            "SUPERVISOR_COMMENT_3_COMPLETE.json",
            "SF4_COMPLETE.json",
            "SF4_ANALYSIS_COMPLETE.json",
            "SF4_FULL_RAW_SNAPSHOT_COMPLETE.json",
        )
        receipt_binding_ok = isinstance(source_receipts, dict)
        for filename in receipt_names:
            matches = [
                (relative, expected)
                for relative, expected in source_receipts.items()
                if str(relative).endswith("/" + filename) or str(relative) == filename
            ]
            if len(matches) != 1:
                receipt_binding_ok = False
                continue
            relative, expected = matches[0]
            path = repo / str(relative)
            if (
                not path.is_file()
                or not _sha256_token(expected)
                or sha256(path) != expected
                or closure_files.get(str(relative)) != expected
            ):
                receipt_binding_ok = False
        checks["sf1_sf2_sf3_sf4_receipts_hash_bound"] = receipt_binding_ok

        latex_build = marker_payload.get("latex_build") or {}
        build_sources = latex_build.get("source_sha256") or {}
        expected_build_paths = {
            path.relative_to(repo).as_posix(): path
            for path in (
                main_path,
                results_path,
                discussion_path,
                conclusion_path,
                wrapper_path,
                discussion_wrapper_path,
                conclusion_wrapper_path,
                *canonical_paths.values(),
            )
        }
        build_sources_ok = set(build_sources) == set(expected_build_paths) and all(
            path.is_file() and build_sources.get(relative) == sha256(path)
            for relative, path in expected_build_paths.items()
        )
        pdf_path = repo / str(latex_build.get("pdf", ""))
        log_path = repo / str(latex_build.get("log", ""))
        command = latex_build.get("command") or []
        checks["successful_latex_build_current_sources_hash_bound"] = all(
            (
                latex_build.get("status") == "pass",
                latex_build.get("returncode") == 0,
                isinstance(command, list),
                bool(command),
                Path(str(command[0])).name == "latexmk",
                build_sources_ok,
                pdf_path.is_file(),
                pdf_path.is_file()
                and pdf_path.stat().st_size > 0
                and latex_build.get("pdf_sha256") == sha256(pdf_path),
                log_path.is_file(),
                log_path.is_file()
                and log_path.stat().st_size > 0
                and latex_build.get("log_sha256") == sha256(log_path),
            )
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        checks.setdefault("integration_marker_status_pass", False)
        checks.setdefault("current_integration_builder_hash_bound", False)
        checks.setdefault("integration_marker_has_required_evidence_ids", False)
        checks.setdefault("integration_marker_evidence_placement_exact", False)
        checks.setdefault("integration_artifacts_hash_bound", False)
        checks.setdefault("result_specific_narrative_exact_and_hash_bound", False)
        checks.setdefault(
            "result_specific_narrative_visible_once_and_in_order", False
        )
        checks.setdefault(
            "dynamic_discussion_interpretation_exact_and_visible_once", False
        )
        checks.setdefault("dynamic_discussion_claim_boundary_present", False)
        checks.setdefault(
            "dynamic_conclusion_synthesis_exact_and_visible_once", False
        )
        checks.setdefault("dynamic_conclusion_claim_boundary_present", False)
        checks.setdefault("result_narrative_scientific_sources_hash_bound", False)
        checks.setdefault("result_narrative_scientific_boundaries_present", False)
        checks.setdefault(
            "integration_marker_rejects_legacy_sf4_production_paths", False
        )
        checks.setdefault("canonical_per_id_assets_exact", False)
        checks.setdefault("canonical_per_id_data_sources_exact", False)
        checks.setdefault("canonical_assets_directly_input_and_reachable", False)
        checks.setdefault("canonical_assets_are_substantive_tables", False)
        checks.setdefault("canonical_data_sources_hash_bound", False)
        checks.setdefault("every_required_id_has_generated_asset", False)
        checks.setdefault("canonical_wrapper_hash_bound", False)
        checks.setdefault("canonical_discussion_wrapper_hash_bound", False)
        checks.setdefault("canonical_conclusion_wrapper_hash_bound", False)
        checks.setdefault("results_discussion_conclusion_main_hash_bound", False)
        checks.setdefault("sf1_sf2_sf3_sf4_receipts_hash_bound", False)
        checks.setdefault("successful_latex_build_current_sources_hash_bound", False)
    failures.extend(name for name, passed in checks.items() if not passed and name not in failures)
    final_ready = bool(checks) and all(checks.values())
    return {
        "schema_version": "supervisor_feedback_paper_content_gate_v5",
        "status": (
            "pass"
            if closure_mode == CLOSURE_FINAL and final_ready
            else "partial_pre_sf4"
            if closure_mode == CLOSURE_PRE_SF4
            else "fail"
        ),
        "closure_mode": closure_mode,
        "final_release_eligible": closure_mode == CLOSURE_FINAL and final_ready,
        "checks": checks,
        "failures": failures,
        "required_evidence_ids": list(ALL_CONTENT_EVIDENCE_IDS),
        "forbidden_wording_hits": forbidden_hits,
        "stale_result_wording_hits": stale_result_hits,
        "misleading_solver_phrase_hit": misleading_solver_phrase_hits,
        "legacy_sf4_production_reference_hits": legacy_sf4_hits,
        "obsolete_percentage_accuracy_claim_hits": obsolete_accuracy_hits,
        "integration_marker": (
            str(marker.resolve().relative_to(repo))
            if repo in marker.resolve().parents
            else str(marker.resolve())
        ),
        "verified_artifacts_sha256": dict(sorted(verified_artifacts.items())),
    }


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def json_pointer(payload: Any, pointer: str) -> Any:
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid JSON pointer: {pointer}")
    current = payload
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


def csv_value(rows: list[dict[str, str]], locator: dict[str, Any]) -> Any:
    filters = locator["where"]
    matched = [row for row in rows if all(row.get(key) == str(value) for key, value in filters.items())]
    if len(matched) != 1:
        raise ValueError(f"CSV locator matched {len(matched)} rows: {filters}")
    raw = matched[0][locator["field"]]
    value_type = locator.get("type", "string")
    if value_type == "float":
        return float(raw)
    if value_type == "int":
        return int(raw)
    if value_type == "bool01":
        return bool(int(raw))
    return raw


def equal(expected: Any, observed: Any) -> bool:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(observed, (int, float)) and math.isclose(float(expected), float(observed), rel_tol=1e-10, abs_tol=1e-12)
    return expected == observed


class Package:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.records: list[dict[str, Any]] = []
        self.ids: set[str] = set()

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.repo))

    def add_json(
        self,
        evidence_id: str,
        hypothesis: str,
        path: Path,
        pointer: str,
        *,
        metric: str,
        unit: str,
        aggregation_unit: str,
        evidence_role: str,
        consumer: str,
        implementation_tag: str,
    ) -> Any:
        value = json_pointer(load_json(path), pointer)
        return self._add(evidence_id, hypothesis, path, {"kind": "json_pointer", "pointer": pointer}, value, metric, unit, aggregation_unit, evidence_role, consumer, implementation_tag)

    def add_csv(
        self,
        evidence_id: str,
        hypothesis: str,
        path: Path,
        where: dict[str, Any],
        field: str,
        value_type: str,
        *,
        metric: str,
        unit: str,
        aggregation_unit: str,
        evidence_role: str,
        consumer: str,
        implementation_tag: str,
    ) -> Any:
        locator = {"kind": "csv_row", "where": where, "field": field, "type": value_type}
        value = csv_value(load_csv(path), locator)
        return self._add(evidence_id, hypothesis, path, locator, value, metric, unit, aggregation_unit, evidence_role, consumer, implementation_tag)

    def add_derived(
        self,
        evidence_id: str,
        hypothesis: str,
        left_id: str,
        right_id: str,
        *,
        metric: str,
        unit: str,
        aggregation_unit: str,
        evidence_role: str,
        consumer: str,
        implementation_tag: str,
    ) -> float:
        by_id = {record["evidence_id"]: record for record in self.records}
        value = float(by_id[left_id]["value"]) - float(by_id[right_id]["value"])
        if evidence_id in self.ids:
            raise ValueError(f"Duplicate evidence ID: {evidence_id}")
        self.ids.add(evidence_id)
        self.records.append({
            "evidence_id": evidence_id,
            "hypothesis": hypothesis,
            "value": value,
            "value_type": "float",
            "unit": unit,
            "metric": metric,
            "aggregation_unit": aggregation_unit,
            "evidence_role": evidence_role,
            "implementation_tag": implementation_tag,
            "source": {"kind": "derived_subtraction", "left_evidence_id": left_id, "right_evidence_id": right_id},
            "consumers": [consumer],
        })
        return value

    def _add(self, evidence_id: str, hypothesis: str, path: Path, locator: dict[str, Any], value: Any, metric: str, unit: str, aggregation_unit: str, evidence_role: str, consumer: str, implementation_tag: str) -> Any:
        if evidence_id in self.ids:
            raise ValueError(f"Duplicate evidence ID: {evidence_id}")
        self.ids.add(evidence_id)
        self.records.append({
            "evidence_id": evidence_id,
            "hypothesis": hypothesis,
            "value": value,
            "value_type": type(value).__name__,
            "unit": unit,
            "metric": metric,
            "aggregation_unit": aggregation_unit,
            "evidence_role": evidence_role,
            "implementation_tag": implementation_tag,
            "source": {"kind": "file", "file": self.relative(path), "sha256": sha256(path), "locator": locator},
            "consumers": [consumer],
        })
        return value


def audit(repo: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    checks = []
    values: dict[str, Any] = {}
    for record in records:
        error = None
        resolved = None
        try:
            source = record["source"]
            if source["kind"] == "file":
                path = repo / source["file"]
                if sha256(path) != source["sha256"]:
                    raise ValueError("source SHA256 mismatch")
                locator = source["locator"]
                if locator["kind"] == "json_pointer":
                    resolved = json_pointer(load_json(path), locator["pointer"])
                elif locator["kind"] == "csv_row":
                    resolved = csv_value(load_csv(path), locator)
                else:
                    raise ValueError("unknown file locator")
            elif source["kind"] == "derived_subtraction":
                resolved = float(values[source["left_evidence_id"]]) - float(values[source["right_evidence_id"]])
            else:
                raise ValueError("unknown source kind")
            if not equal(record["value"], resolved):
                raise ValueError(f"value mismatch: expected={record['value']!r}, observed={resolved!r}")
        except Exception as exc:  # audit must retain all failures
            error = str(exc)
        if error is None:
            values[record["evidence_id"]] = resolved
        checks.append({"evidence_id": record["evidence_id"], "status": "pass" if error is None else "fail", "error": error})
    failures = [check for check in checks if check["status"] == "fail"]
    hypotheses = {record["hypothesis"] for record in records}
    invalid_roles = [record["evidence_id"] for record in records if record["evidence_role"] not in {"primary", "secondary", "diagnostic", "boundary"}]
    mixed_implementations = [record["evidence_id"] for record in records if record["hypothesis"] in {"H3", "H4"} and record["implementation_tag"] != "corrected_r3_v1"]
    aggregation_semantic_violations = []
    by_id = {record["evidence_id"]: record for record in records}
    for record in records:
        if record.get("implementation_tag") != "offline_frozen_test_v1":
            continue
        if not str(record.get("aggregation_unit", "")).startswith("rollout-macro"):
            aggregation_semantic_violations.append(record["evidence_id"])
            continue
        source = record["source"]
        if source["kind"] == "file":
            locator = source["locator"]
            if (
                locator.get("kind") != "json_pointer"
                or "/rollout_aggregation/macro_mean/" not in locator.get("pointer", "")
            ):
                aggregation_semantic_violations.append(record["evidence_id"])
        elif source["kind"] == "derived_subtraction":
            endpoint_ids = (source["left_evidence_id"], source["right_evidence_id"])
            if any(
                endpoint not in by_id
                or by_id[endpoint].get("aggregation_unit") != record["aggregation_unit"]
                for endpoint in endpoint_ids
            ):
                aggregation_semantic_violations.append(record["evidence_id"])
    return {
        "schema_version": "m1_value_resolving_audit_v1",
        "status": "pass" if not failures and hypotheses == {"H1", "H2", "H3", "H4"} and not invalid_roles and not mixed_implementations and not aggregation_semantic_violations else "fail",
        "record_count": len(records),
        "hypotheses": sorted(hypotheses),
        "locator_resolution_failures": len(failures),
        "value_mismatches": sum("value mismatch" in (item["error"] or "") for item in failures),
        "invalid_evidence_roles": invalid_roles,
        "legacy_corrected_pooling_violations": mixed_implementations,
        "aggregation_semantic_violations": aggregation_semantic_violations,
        "orphan_headline_claims": 0 if hypotheses == {"H1", "H2", "H3", "H4"} else 4 - len(hypotheses),
        "checks": checks,
    }


def build(
    repo: Path,
    output: Path,
    *,
    closure_mode: str = CLOSURE_FINAL,
    supervisor_feedback_root: Path | None = None,
    sf4_results_root: Path | None = None,
) -> dict[str, Any]:
    if closure_mode not in CLOSURE_MODES:
        raise ValueError(f"Unknown supervisor-feedback closure mode: {closure_mode}")
    generated = repo / "docs/paper/generated"
    paths = {
        "test": generated / "day8/final_test/day8_frozen_test_summary.json",
        "b0": generated / "day10/gaps/b0_offline/b0_frozen_offline_summary.json",
        "finetune": generated / "supervisor_feedback_v1/03_finetune_audit/SUPERVISOR_COMMENT_3_COMPLETE.json",
        "capacity": generated / "distinction_v1/03_training_budget/model_capacity_training_budget_audit.json",
        "tail": generated / "distinction_v1/04_in_loop_prediction/formal_inloop_B1_minus_B0_contrasts.csv",
        "a2": generated / "distinction_v1/08_corrected_closed_loop/r3_final/synthesis/A2_COMPLETE.json",
        "h3": generated / "distinction_v1/08_corrected_closed_loop/r3_final/synthesis/table_r3_h3_translation.csv",
        "h4": generated / "distinction_v1/08_corrected_closed_loop/r3_final/synthesis/table_r3_h4_dominance.csv",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    for name in ("test", "b0", "finetune", "capacity", "a2"):
        if load_json(paths[name]).get("status") != "pass":
            raise ValueError(f"Input completion gate failed: {paths[name]}")

    finetune_gate = load_json(paths["finetune"])
    if (
        finetune_gate.get("old_percentage_accuracy_hit_count") != 0
        or finetune_gate.get("overlapping_windows_treated_as_independent") is not False
        or finetune_gate.get("independent_paired_init_groups") != 5
    ):
        raise ValueError("Supervisor fine-tuning evidence gate failed")

    test_summary = load_json(paths["test"])
    b0_summary = load_json(paths["b0"])
    frozen_test_rollout_records(repo, test_summary, b0_summary)
    test_eval_paths = frozen_test_evaluation_paths(repo)

    package = Package(repo)
    common_test = dict(unit="nats/step", aggregation_unit="rollout-macro: mean within each of 20 frozen-test rollouts, then equal mean across rollouts; 5 held-out init groups", evidence_role="primary", consumer="Results H1/H2 model comparison", implementation_tag="offline_frozen_test_v1")
    nll_pointer = "/uncalibrated/rollout_aggregation/macro_mean/trajectory_mixture_NLL_per_step_mean"
    h1_b1 = package.add_json("H1_B1_TEST_NLL", "H1", test_eval_paths["B1"], nll_pointer, metric="uncalibrated trajectory mixture NLL", **common_test)
    h1_b0 = package.add_json("H1_B0_TEST_NLL", "H1", test_eval_paths["B0"], nll_pointer, metric="uncalibrated trajectory mixture NLL", **common_test)
    package.add_derived("H1_B1_MINUS_B0_TEST_NLL", "H1", "H1_B1_TEST_NLL", "H1_B0_TEST_NLL", metric="B1 minus B0 uncalibrated trajectory mixture NLL", **common_test)
    for metric, field, unit in (("ADE", "top1_ADE_mean", "m"), ("FDE", "top1_FDE_mean", "m")):
        left = f"H1_B1_TEST_{metric}"
        right = f"H1_B0_TEST_{metric}"
        kwargs = dict(unit=unit, aggregation_unit=common_test["aggregation_unit"], evidence_role="secondary", consumer="Results H1 model comparison", implementation_tag="offline_frozen_test_v1")
        pointer = f"/uncalibrated/rollout_aggregation/macro_mean/{field}"
        package.add_json(left, "H1", test_eval_paths["B1"], pointer, metric=f"top-1 {metric}", **kwargs)
        package.add_json(right, "H1", test_eval_paths["B0"], pointer, metric=f"top-1 {metric}", **kwargs)
        package.add_derived(f"H1_B1_MINUS_B0_TEST_{metric}", "H1", left, right, metric=f"B1 minus B0 top-1 {metric}", **kwargs)

    for variant in ("B2-M", "T1", "B2-D", "T2"):
        package.add_json(
            f"H2_{variant.replace('-', '_')}_TEST_NLL",
            "H2",
            test_eval_paths[variant],
            nll_pointer,
            metric="uncalibrated trajectory mixture NLL",
            **common_test,
        )
    package.add_derived("H2_T1_MINUS_B2M_TEST_NLL", "H2", "H2_T1_TEST_NLL", "H2_B2_M_TEST_NLL", metric="T1 minus B2-M frozen-test NLL", **common_test)
    package.add_derived("H2_T2_MINUS_B2D_TEST_NLL", "H2", "H2_T2_TEST_NLL", "H2_B2_D_TEST_NLL", metric="T2 minus B2-D frozen-test NLL", **common_test)
    package.add_json("H2_PARAMETER_MATCHED", "H2", paths["capacity"], "/fairness_checks/parameter_matched", metric="parameter-matching audit", unit="boolean", aggregation_unit="five complete model configurations", evidence_role="boundary", consumer="Methods limitation and H2 interpretation", implementation_tag="offline_training_audit_v1")
    package.add_json("H2_RUNS_AT_EPOCH_BOUNDARY", "H2", paths["capacity"], "/fairness_checks/runs_best_at_budget_boundary", metric="runs selected at epoch ceiling", unit="runs", aggregation_unit="15 training runs", evidence_role="boundary", consumer="Methods limitation and H2 interpretation", implementation_tag="offline_training_audit_v1")
    package.add_csv("H1_TAIL_MINUS_B0_ADE_NEG3", "H1", paths["tail"], {"subset": "response_active", "target_offset_m": "-3.0", "metric": "top1_ADE_m"}, "B1_minus_B0_mean", "float", metric="B1 minus B0 response-active ADE at -3 m", unit="m", aggregation_unit="10 paired rollout conditions / 5 init groups", evidence_role="diagnostic", consumer="H1 boundary and Discussion", implementation_tag="legacy_timing_diagnostic_only")

    package.add_json("H3_SUPPORTED_CELLS", "H3", paths["a2"], "/h3/directionally_supported_cells", metric="H3 directionally supported cells", unit="cells", aggregation_unit="8 prespecified predictor-stack policy/style cells", evidence_role="primary", consumer="Results H3 headline", implementation_tag="corrected_r3_v1")
    package.add_json("H3_PRESPECIFIED_CELLS", "H3", paths["a2"], "/h3/prespecified_cells", metric="H3 prespecified cells", unit="cells", aggregation_unit="corrected R3 matrix", evidence_role="primary", consumer="Results H3 headline", implementation_tag="corrected_r3_v1")
    for row in load_csv(paths["h3"]):
        key = f"{row['risk_policy']}_{row['target_style']}"
        where = {"risk_policy": row["risk_policy"], "target_style": row["target_style"]}
        for suffix, field, unit in (("TIME", "mean_completion_effect_s", "s"), ("SEPARATION", "mean_separation_effect_m", "m"), ("SUPPORT", "cell_support_status", "category")):
            value_type = "float" if suffix != "SUPPORT" else "string"
            package.add_csv(f"H3_{key.upper()}_{suffix}", "H3", paths["h3"], where, field, value_type, metric=f"B1 minus B0 {field}", unit=unit, aggregation_unit="mean paired effect over 5 init groups", evidence_role="primary", consumer="R3 H3 table/figure", implementation_tag="corrected_r3_v1")

    package.add_json("H4_DOMINANCE_CELLS", "H4", paths["a2"], "/h4/dominance_cells", metric="adaptive-risk dominance cells", unit="cells", aggregation_unit="12 prespecified predictor/style/fixed-comparator contrasts", evidence_role="primary", consumer="Results H4 headline", implementation_tag="corrected_r3_v1")
    package.add_json("H4_PRESPECIFIED_CELLS", "H4", paths["a2"], "/h4/prespecified_cells", metric="H4 prespecified contrasts", unit="cells", aggregation_unit="corrected R3 matrix", evidence_role="primary", consumer="Results H4 headline", implementation_tag="corrected_r3_v1")
    for row in load_csv(paths["h4"]):
        key = f"{row['predictor']}_{row['target_style']}_{row['fixed_comparator']}"
        where = {"predictor": row["predictor"], "target_style": row["target_style"], "fixed_comparator": row["fixed_comparator"]}
        for suffix, field, unit in (("TIME", "mean_adaptive_minus_fixed_completion_s", "s"), ("SEPARATION", "mean_adaptive_minus_fixed_separation_m", "m"), ("DOMINANCE", "dominance_status", "category")):
            value_type = "float" if suffix != "DOMINANCE" else "string"
            package.add_csv(f"H4_{key.upper()}_{suffix}", "H4", paths["h4"], where, field, value_type, metric=f"adaptive minus fixed {field}", unit=unit, aggregation_unit="mean paired effect over 5 init groups", evidence_role="primary", consumer="R3 H4 table/figure", implementation_tag="corrected_r3_v1")

    audit_payload = audit(repo, package.records)
    closure_payload = audit_supervisor_feedback_closure(
        repo,
        supervisor_feedback_root=supervisor_feedback_root,
        sf4_results_root=sf4_results_root,
    )
    package_status = stage_aware_status(
        base_ready=audit_payload["status"] == "pass",
        closure_status=str(closure_payload["status"]),
        closure_mode=closure_mode,
    )
    output.mkdir(parents=True, exist_ok=True)
    hypotheses = [
        {"hypothesis": "H1", "verdict": "supported_with_boundary", "primary_evidence": "H1_B1_MINUS_B0_TEST_NLL", "claim": f"At rollout-macro aggregation, B1 reduces frozen-test NLL relative to B0 by {abs(h1_b1 - h1_b0):.3f} nats/step; the small response-active subset remains a separate diagnostic."},
        {"hypothesis": "H2", "verdict": "not_supported", "primary_evidence": "H2_T1_MINUS_B2M_TEST_NLL; H2_T2_MINUS_B2D_TEST_NLL", "claim": "The two matched-head comparisons point in different directions; tested Transformers do not show a consistent advantage over MLP adapters."},
        {"hypothesis": "H3", "verdict": "not_supported_as_universal_claim", "primary_evidence": "H3_SUPPORTED_CELLS; H3_PRESPECIFIED_CELLS", "claim": "B1 prediction gains jointly improve completion and separation in only 2/8 corrected closed-loop cells."},
        {"hypothesis": "H4", "verdict": "not_supported_as_universal_dominance", "primary_evidence": "H4_DOMINANCE_CELLS; H4_PRESPECIFIED_CELLS", "claim": "Adaptive risk dominates fixed risk in only 3/12 corrected comparisons."},
    ]
    manifest = {
        "schema_version": "m1_four_hypothesis_evidence_v1",
        "status": package_status,
        "value_audit_status": audit_payload["status"],
        "closure_mode": closure_mode,
        "supervisor_feedback_final_closure": closure_payload,
        "final_release_eligible": package_status == "pass",
        "central_claim": "Task adaptation strongly improves prediction, but closed-loop benefit is conditional on predictor-risk-interaction coupling under the shared supervisor.",
        "hypotheses": hypotheses,
        "records": package.records,
        "record_count": len(package.records),
        "additional_large_scale_carla_required": closure_payload["status"] != "pass",
        "headline_aggregation": "rollout_macro",
        "independent_unit": "held_out_ego_initialisation",
        "independent_paired_init_groups": 5,
        "overlapping_windows_treated_as_independent": False,
        "source_gates": {
            str(paths["finetune"].relative_to(repo)): sha256(paths["finetune"]),
        },
    }
    atomic_json(output / "M1_EVIDENCE_MANIFEST.json", manifest)
    atomic_json(output / "M1_VALUE_AUDIT.json", audit_payload)
    atomic_json(output / "M1_SUPERVISOR_FEEDBACK_CLOSURE_AUDIT.json", closure_payload)
    write_csv(output / "M1_HYPOTHESIS_VERDICTS.csv", hypotheses)
    markdown = "# M1 — Four-hypothesis evidence package\n\n" + "\n".join(f"- **{row['hypothesis']} — {row['verdict']}:** {row['claim']}" for row in hypotheses) + f"\n\nValue audit: **{audit_payload['status']}**; publication closure: **{package_status}** ({closure_mode}); {len(package.records)} records, {audit_payload['locator_resolution_failures']} locator/value failures, {len(audit_payload['legacy_corrected_pooling_violations'])} legacy/corrected pooling violations.\n"
    atomic_text(output / "M1_EVIDENCE_SUMMARY.md", markdown)
    artifacts = ["M1_EVIDENCE_MANIFEST.json", "M1_VALUE_AUDIT.json", "M1_SUPERVISOR_FEEDBACK_CLOSURE_AUDIT.json", "M1_HYPOTHESIS_VERDICTS.csv", "M1_EVIDENCE_SUMMARY.md"]
    complete = {
        "schema_version": "m1_complete_v1",
        "status": package_status,
        "stage": "M1",
        "value_audit_status": audit_payload["status"],
        "closure_mode": closure_mode,
        "supervisor_feedback_closure_status": closure_payload["status"],
        "supervisor_feedback_closure_checks": closure_payload["checks"],
        "supervisor_feedback_closure_failures": closure_payload["failures"],
        "final_release_eligible": package_status == "pass",
        "hypotheses": ["H1", "H2", "H3", "H4"],
        "record_count": len(package.records),
        "invalid_locators": audit_payload["locator_resolution_failures"],
        "value_mismatches": audit_payload["value_mismatches"],
        "orphan_headline_claims": audit_payload["orphan_headline_claims"],
        "legacy_corrected_pooling_violations": audit_payload["legacy_corrected_pooling_violations"],
        "aggregation_semantic_violations": audit_payload["aggregation_semantic_violations"],
        "additional_large_scale_carla_required": closure_payload["status"] != "pass",
        "headline_aggregation": "rollout_macro",
        "independent_unit": "held_out_ego_initialisation",
        "independent_paired_init_groups": 5,
        "overlapping_windows_treated_as_independent": False,
        "source_gates": {
            str(paths["finetune"].relative_to(repo)): sha256(paths["finetune"]),
        },
        "artifacts": {filename: sha256(output / filename) for filename in artifacts},
    }
    atomic_json(output / "M1_COMPLETE.json", complete)
    return complete


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--closure-mode",
        choices=CLOSURE_MODES,
        default=CLOSURE_FINAL,
        help=(
            "Use final for the fail-closed publication gate (default). Use pre-sf4 "
            "only to regenerate explicitly partial evidence before SF1/SF2/SF4 finish."
        ),
    )
    parser.add_argument("--supervisor-feedback-root", type=Path)
    parser.add_argument("--sf4-results-root", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output or repo / "docs/paper/generated/distinction_v1/10_four_hypothesis_evidence").resolve()
    result = build(
        repo,
        output,
        closure_mode=args.closure_mode,
        supervisor_feedback_root=args.supervisor_feedback_root,
        sf4_results_root=args.sf4_results_root,
    )
    print(json.dumps(result, indent=2))
    if result["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
