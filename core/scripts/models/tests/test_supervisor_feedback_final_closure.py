#!/usr/bin/env python3

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.build_m1_evidence_package import (
    SF2_REQUIRED_FINAL_ARTIFACTS,
    SF3_REQUIRED_ARTIFACTS,
    SF4_REQUIRED_ANALYSIS_PRODUCTS,
    SF4_REQUIRED_EXECUTION_SOURCES,
    SF4_REQUIRED_RAW_FILES,
    SUPERVISOR_CONTENT_EVIDENCE_IDS,
    audit_supervisor_feedback_closure,
    audit_supervisor_feedback_content_integration,
    stage_aware_status,
)
from core.scripts.models.build_supervisor_feedback_paper_integration import (
    ALL_CONTENT_EVIDENCE_IDS,
    CANONICAL_EVIDENCE_ASSETS,
    CANONICAL_EVIDENCE_DATA_SOURCES,
    CONCLUSION_RELATIVE,
    CONCLUSION_WRAPPER_LATEX_INPUT,
    CONCLUSION_WRAPPER_RELATIVE,
    DISCUSSION_WRAPPER_LATEX_INPUT,
    DISCUSSION_WRAPPER_RELATIVE,
    PROVISIONAL_DISCUSSION_WRAPPER_TEXT,
    PROVISIONAL_CONCLUSION_WRAPPER_TEXT,
    RESULTS_RELATIVE,
    SF3_RESULTS_EVIDENCE_ID,
    SF3_RESULTS_LATEX_INPUT,
    WRAPPER_LATEX_INPUT,
    WRAPPER_RELATIVE,
    build as build_paper_integration,
    build_result_narrative,
    ensure_provisional_conclusion_wrapper,
    ensure_provisional_discussion_wrapper,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str = "evidence\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class SupervisorFeedbackFinalClosureTest(unittest.TestCase):
    def build_content_fixture(self, repo: Path, closure: dict) -> Path:
        latex = repo / "docs/dissertation/latex"
        write_text(
            latex / "main.tex",
            "\\documentclass{article}\n\\begin{document}\n"
            "\\input{sections/06_results.tex}\n"
            "\\input{sections/07_discussion.tex}\n"
            "\\input{sections/08_conclusion.tex}\n"
            "\\end{document}\n",
        )
        write_text(
            repo / RESULTS_RELATIVE,
            "\\section{Results}\nFinal supervisor-feedback results.\n"
            "An earlier report described a rise from 0.98\\% to 100\\%. "
            "That number was the fraction of windows for which the top-probability "
            "mode matched the oracle-best mode; it was not a thresholded "
            "trajectory-accuracy endpoint. We withdraw the number: it is not "
            "evidence for trajectory quality. The narrow split, oracle-best mode "
            "concentration and overlapping-window aggregation made the headline "
            "fragile. Replacement NLL, ADE and FDE use rollout-macro aggregation "
            "and held-out initialisations as independent paired units.\n"
            f"\\input{{{SF3_RESULTS_LATEX_INPUT}}}\n"
            f"\\input{{{WRAPPER_LATEX_INPUT}}}\n",
        )
        write_text(
            latex / "sections/07_discussion.tex",
            "\\section{Discussion}\nFinal bounded interpretation.\n"
            f"\\input{{{DISCUSSION_WRAPPER_LATEX_INPUT}}}\n",
        )
        write_text(
            repo / CONCLUSION_RELATIVE,
            "\\section{Conclusion}\n"
            "Static H1--H4 synthesis remains in the manuscript.\n"
            f"\\input{{{CONCLUSION_WRAPPER_LATEX_INPUT}}}\n",
        )
        for evidence_id, relative in CANONICAL_EVIDENCE_ASSETS.items():
            if evidence_id == "SF2_DEADLINE_EXCEEDANCE":
                continue
            if (repo / relative).is_file():
                continue
            write_text(
                repo / relative,
                "\\begin{table}[t]\n\\caption{Canonical scientific evidence table "
                + evidence_id.replace("_", " ")
                + ".}\n\\begin{tabular}{lr}Outcome & 1 \\\\\n\\end{tabular}\n\\end{table}\n",
            )
        data_paths = {
            relative
            for paths in CANONICAL_EVIDENCE_DATA_SOURCES.values()
            for relative in paths
        }
        for relative in data_paths:
            path = repo / relative
            if path.name == "deadline_exceedance.csv":
                continue
            if path.is_file():
                continue
            if path.suffix == ".json":
                write_json(path, {"status": "pass", "value": 1})
            else:
                write_text(path, "metric,value\nfixture,1\n")
        deadline = (
            repo
            / "docs/paper/generated/supervisor_feedback_v1/r3_offline/"
            "02_cost_feasibility/deadline_exceedance.csv"
        )
        deadline.parent.mkdir(parents=True, exist_ok=True)
        with deadline.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "risk_policy",
                    "deadline_name",
                    "deadline_s",
                    "evaluation_status",
                    "finite_attempted_solve_steps",
                    "nonfinite_attempted_solve_steps_excluded",
                    "deadline_exceedance_steps",
                    "deadline_exceedance_fraction_of_finite_attempts",
                ),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "risk_policy": "adaptive",
                    "deadline_name": "smpc_planning_interval",
                    "deadline_s": 0.2,
                    "evaluation_status": "evaluated",
                    "finite_attempted_solve_steps": 99,
                    "nonfinite_attempted_solve_steps_excluded": 1,
                    "deadline_exceedance_steps": 2,
                    "deadline_exceedance_fraction_of_finite_attempts": 2 / 99,
                }
            )

        def fake_latex_runner(*, latex_root, output_dir, main):
            del latex_root, main
            output_dir.mkdir(parents=True, exist_ok=True)
            pdf = output_dir / "main.pdf"
            log = output_dir / "supervisor_feedback_final_latexmk.log"
            write_text(pdf, "%PDF-1.4\nfinal compiled fixture\n")
            write_text(log, "Latexmk: All targets are up-to-date\n")
            return pdf, log, ("latexmk", "-pdf", "main.tex"), 0

        result = build_paper_integration(
            repo, closure_payload=closure, latex_runner=fake_latex_runner
        )
        marker = (
            repo
            / "docs/paper/generated/supervisor_feedback_v1/paper_integration/"
            "SUPERVISOR_FEEDBACK_PAPER_INTEGRATION_COMPLETE.json"
        )
        self.assertEqual(result["status"], "pass")
        return marker

    def build_fixture(self, repo: Path) -> tuple[Path, Path]:
        feedback = repo / "docs/paper/generated/supervisor_feedback_v1"
        offline = feedback / "r3_offline"
        behaviour = offline / "01_behaviour"
        cost = offline / "02_cost_feasibility"
        sf3 = feedback / "03_finetune_audit"
        sf4 = (
            repo
            / "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs"
            / "sf4_supervisor_behavioural_authority_v1"
        )
        behaviour_source = repo / "core/scripts/models/analyze_supervisor_feedback_behaviour.py"
        behaviour_runner = repo / "core/scripts/models/run_supervisor_feedback_r3_offline_audits.sh"
        cost_source = repo / "core/scripts/models/analyze_supervisor_feedback_cost_feasibility.py"
        for path, contents in (
            (behaviour_source, "# behaviour analyzer\n"),
            (behaviour_runner, "#!/usr/bin/env bash\n# offline runner\n"),
            (cost_source, "# cost analyzer\n"),
            (
                repo / "core/scripts/models/build_supervisor_feedback_paper_integration.py",
                "# final paper integration builder\n",
            ),
        ):
            write_text(path, contents)

        r3_snapshot = (
            repo
            / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final"
            / "server_runs/r3_corrected_formal_v3"
        )
        r3_matrix = r3_snapshot / "r3_corrected_matrix_audit.json"
        r3_rollouts = r3_snapshot / "analysis/r3_rollout_outcomes.csv"
        r3_analysis = r3_snapshot / "analysis/R3_ANALYSIS_COMPLETE.json"
        r3_data = r3_snapshot / "R3_DATA_COMPLETE.json"
        for path, contents in (
            (r3_matrix, "{}\n"),
            (r3_rollouts, "cell_id,ego_init_id\n"),
            (r3_analysis, "{}\n"),
            (r3_data, "{}\n"),
        ):
            write_text(path, contents)

        rollout_path = behaviour / "behaviour_rollouts.csv"
        rollout_path.parent.mkdir(parents=True, exist_ok=True)
        with rollout_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "cell_id",
                    "ego_init_id",
                    "debug_sha256",
                    "stop_window_status",
                    "stop_window_censored_missing_release",
                    "path_release_observed",
                    "sustained_stop_observed",
                    "first_sustained_stop_step",
                    "first_stop_distance_to_conflict_m",
                    "first_stop_distance_to_designed_stop_m",
                    "cautious_approach_progress_m",
                    "cautious_approach_duration_s",
                    "pre_clearance_stopped_duration_s",
                ),
            )
            writer.writeheader()
            for index in range(80):
                censored = index == 0
                writer.writerow(
                    {
                        "cell_id": f"cell_{index // 5}",
                        "ego_init_id": 101 + index % 5,
                        "debug_sha256": token(f"r3-debug-{index}"),
                        "stop_window_status": (
                            "censored_missing_release" if censored else "evaluated"
                        ),
                        "stop_window_censored_missing_release": censored,
                        "path_release_observed": not censored,
                        "sustained_stop_observed": not censored,
                        "first_sustained_stop_step": "" if censored else 20,
                        "first_stop_distance_to_conflict_m": "" if censored else 5.0,
                        "first_stop_distance_to_designed_stop_m": "" if censored else 0.2,
                        "cautious_approach_progress_m": "" if censored else 4.0,
                        "cautious_approach_duration_s": "" if censored else 1.0,
                        "pre_clearance_stopped_duration_s": "" if censored else 2.0,
                    }
                )
        behaviour_artifacts = {rollout_path.name: digest(rollout_path)}
        for index in range(5):
            path = behaviour / f"behaviour_artifact_{index}.txt"
            write_text(path, f"behaviour-{index}\n")
            behaviour_artifacts[path.name] = digest(path)
        sensitivity = behaviour / "behaviour_threshold_sensitivity.csv"
        sensitivity.parent.mkdir(parents=True, exist_ok=True)
        with sensitivity.open("w", newline="", encoding="utf-8") as handle:
            fieldnames = (
                "stop_speed_mps",
                "resume_speed_mps",
                "consecutive_steps",
                "risk_policy",
                "independent_unit",
                "step_rows_are_not_independent_samples",
                "first_stop_distance_to_conflict_m__cluster_macro_mean",
            )
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for stop in (0.10, 0.15, 0.20):
                for resume in (0.5, 0.8, 1.0):
                    for sustained in (2, 3, 5):
                        for policy in (
                            "adaptive",
                            "fixed_aggressive",
                            "fixed_medium",
                            "fixed_conservative",
                        ):
                            writer.writerow(
                                {
                                    "stop_speed_mps": stop,
                                    "resume_speed_mps": resume,
                                    "consecutive_steps": sustained,
                                    "risk_policy": policy,
                                    "independent_unit": "ego_initialisation_group",
                                    "step_rows_are_not_independent_samples": True,
                                    "first_stop_distance_to_conflict_m__cluster_macro_mean": (
                                        4.5 + stop + 0.01 * sustained
                                    ),
                                }
                            )
        behaviour_artifacts[sensitivity.name] = digest(sensitivity)
        policy_macro = behaviour / "behaviour_policy_cluster_macro.csv"
        policy_macro_rows = [
            {
                "risk_policy": policy,
                "independent_init_groups": 5,
                "conditions_per_init": 4,
                "rollouts": 20,
                "cautious_approach_progress_m__cluster_macro_mean": 4.0 + offset,
                "cautious_approach_progress_m__clusters_observed": 5,
                "pre_clearance_stopped_duration_s__cluster_macro_mean": 2.0 + offset,
                "pre_clearance_stopped_duration_s__clusters_observed": 5,
                "first_stop_distance_to_conflict_m__cluster_macro_mean": 5.0 + offset,
                "first_stop_distance_to_conflict_m__clusters_observed": 5,
                "designed_stop_clearance_m__cluster_macro_mean": 4.8 + offset,
                "designed_stop_clearance_m__clusters_observed": 5,
                "first_stop_distance_to_designed_stop_m__cluster_macro_mean": 0.2,
                "first_stop_distance_to_designed_stop_m__clusters_observed": 5,
                "nominal_clear_to_release_latency_s__cluster_macro_mean": 0.4 + offset,
                "nominal_clear_to_release_latency_s__clusters_observed": 5,
                "release_to_resume_latency_s__cluster_macro_mean": 0.2 + offset,
                "release_to_resume_latency_s__clusters_observed": 5,
                "buffered_clear_to_resume_latency_s__cluster_macro_mean": 0.3 + offset,
                "buffered_clear_to_resume_latency_s__clusters_observed": 5,
            }
            for policy, offset in (
                ("adaptive", 0.0),
                ("fixed_aggressive", -0.2),
                ("fixed_medium", -0.1),
                ("fixed_conservative", 0.2),
            )
        ]
        write_csv(policy_macro, tuple(policy_macro_rows[0]), policy_macro_rows)
        behaviour_artifacts[policy_macro.name] = digest(policy_macro)
        paired_contrasts = behaviour / "behaviour_policy_paired_contrasts.csv"
        paired_contrast_rows = [
            {
                "contrast": f"adaptive_minus_{fixed}",
                "metric": metric,
                "independent_init_groups": 5,
                "expected_init_groups": 5,
                "cluster_mean_effect": effect,
                "cluster_median_effect": effect,
                "minimum_effect": effect,
                "maximum_effect": effect,
                "negative_groups": 5 if effect < 0 else 0,
                "zero_groups": 5 if effect == 0 else 0,
                "positive_groups": 5 if effect > 0 else 0,
                "two_sided_exact_sign_flip_p_descriptive": 0.0625,
                "per_init_effects_json": json.dumps(
                    {str(init_id): effect for init_id in range(101, 106)},
                    sort_keys=True,
                ),
                "analysis_role": "post_hoc_paired_mechanism_contrast",
            }
            for fixed, effect in (
                ("fixed_aggressive", 0.2),
                ("fixed_medium", 0.1),
                ("fixed_conservative", -0.2),
            )
            for metric in (
                "first_stop_distance_to_conflict_m",
                "first_stop_distance_to_designed_stop_m",
                "cautious_approach_progress_m",
                "pre_clearance_stopped_duration_s",
                "nominal_clear_to_release_latency_s",
                "buffered_clear_to_resume_latency_s",
                "release_to_resume_latency_s",
            )
        ]
        write_csv(
            paired_contrasts,
            tuple(paired_contrast_rows[0]),
            paired_contrast_rows,
        )
        behaviour_artifacts[paired_contrasts.name] = digest(paired_contrasts)
        contract = behaviour / "behaviour_analysis_contract.json"
        write_json(
            contract,
            {
                "fps": 20.0,
                "independent_unit": "ego_initialisation_group",
                "step_rows_are_not_independent_samples": True,
                "baseline_definition": {
                    "stop_speed_mps": 0.15,
                    "resume_speed_mps": 0.8,
                    "minimum_consecutive_steps": 3,
                },
                "threshold_sensitivity_grid": {
                    "stop_speed_mps": [0.1, 0.15, 0.2],
                    "resume_speed_mps": [0.5, 0.8, 1.0],
                    "minimum_consecutive_steps": [2, 3, 5],
                    "definitions": 27,
                    "rows": 108,
                },
            },
        )
        behaviour_artifacts[contract.name] = digest(contract)
        behaviour_tables = {
            "behaviour_cell_summary.csv": "cell_id,value\nfixture,1\n",
            "behaviour_approach_stop.tex": (
                "\\begin{table}[t]\\caption{Approach, configured designed clearance, "
                "and stopping with complete init groups/5.}\\begin{tabular}{lr}"
                "Outcome & 1 \\\\ \\end{tabular}\\end{table}\n"
            ),
            "behaviour_release.tex": (
                "\\begin{table}[t]\\caption{Release clocks with complete init "
                "groups/5 and no imputation.}\\begin{tabular}{lr}Outcome & 1 "
                "\\\\ \\end{tabular}\\end{table}\n"
            ),
            "behaviour_policy_paired_contrasts.tex": (
                "\\begin{table*}[t]\\caption{Post-hoc adaptive-minus-fixed "
                "behavioural contrasts; missing mechanism events are censored rather "
                "than imputed.}\\begin{tabular}{lr}All three fixed comparators & "
                "n/5 \\\\ \\end{tabular}\\end{table*}\n"
            ),
        }
        for filename, contents in behaviour_tables.items():
            path = behaviour / filename
            write_text(path, contents)
            behaviour_artifacts[path.name] = digest(path)
        sf1_source_hashes = {
            "core/scripts/models/analyze_supervisor_feedback_behaviour.py": digest(
                behaviour_source
            ),
            "core/scripts/models/run_supervisor_feedback_r3_offline_audits.sh": digest(
                behaviour_runner
            ),
            "matrix_audit": digest(r3_matrix),
        }
        behaviour_summary = behaviour / "behaviour_analysis_summary.json"
        write_json(
            behaviour_summary,
            {
                "status": "pass",
                "formal_integrity_status": "pass",
                "observed_rollouts": 80,
                "expected_rollouts": 80,
                "formal_cells": 16,
                "independent_init_groups": [101, 102, 103, 104, 105],
                "contract_sha256": digest(contract),
                "source_sha256": sf1_source_hashes,
            },
        )
        behaviour_receipt = behaviour / "SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json"
        write_json(
            behaviour_receipt,
            {
                "status": "pass",
                "summary": behaviour_summary.name,
                "summary_sha256": digest(behaviour_summary),
                "artifacts": behaviour_artifacts,
                "contract": contract.name,
                "contract_sha256": digest(contract),
                "source_sha256": sf1_source_hashes,
            },
        )

        policies = (
            "adaptive",
            "fixed_aggressive",
            "fixed_medium",
            "fixed_conservative",
        )
        step_rows = []
        for policy in policies:
            for init_id in range(101, 106):
                for rollout_index in range(4):
                    common = {
                        "cell_id": f"cell_{policy}_{rollout_index}",
                        "predictor": "B1",
                        "risk_policy": policy,
                        "target_style": "assertive",
                        "ego_init_id": init_id,
                    }
                    step_rows.append(
                        {
                            **common,
                            "debug_row_index": 0,
                            "step": 10,
                            "classification": (
                                "attempted_fallback_or_nonaccepted"
                                if rollout_index == 0
                                else "attempted_accepted"
                            ),
                        }
                    )
                    if rollout_index == 0:
                        step_rows.append(
                            {
                                **common,
                                "debug_row_index": 1,
                                "step": 11,
                                "classification": "rule_bypass_no_solve",
                            }
                        )
        write_csv(
            cost / "raw_step_classification.csv",
            (
                "cell_id",
                "predictor",
                "risk_policy",
                "target_style",
                "ego_init_id",
                "debug_row_index",
                "step",
                "classification",
            ),
            step_rows,
        )
        summary_fields = (
            "risk_policy",
            "ego_init_id",
            "debug_rows",
            "prediction_valid_context_steps",
            "prediction_invalid_context_steps",
            "no_solver_telemetry_context_steps",
            "attempted_solve_steps",
            "prediction_valid_attempted_solve_steps",
            "prediction_invalid_attempted_solve_steps",
            "prediction_valid_bypass_no_solve_steps",
            "prediction_invalid_bypass_no_solve_steps",
            "attempted_accepted_steps",
            "attempted_fallback_or_nonaccepted_steps",
            "rule_bypass_no_solve_steps",
            "solver_execution_decisions",
            "finite_attempted_latency_steps",
            "nonfinite_attempted_latency_steps",
            "attempted_latency_p50_s",
            "attempted_latency_p95_s",
            "attempted_latency_p99_s",
            "controller_acceptance_rate_attempted_solve",
            "bypass_fraction_of_solver_execution_decisions",
        )
        policy_rows = [
            {
                "risk_policy": policy,
                "ego_init_id": "ALL",
                "debug_rows": 25,
                "prediction_valid_context_steps": 20,
                "prediction_invalid_context_steps": 5,
                "no_solver_telemetry_context_steps": 0,
                "attempted_solve_steps": 20,
                "prediction_valid_attempted_solve_steps": 15,
                "prediction_invalid_attempted_solve_steps": 5,
                "prediction_valid_bypass_no_solve_steps": 5,
                "prediction_invalid_bypass_no_solve_steps": 0,
                "attempted_accepted_steps": 15,
                "attempted_fallback_or_nonaccepted_steps": 5,
                "rule_bypass_no_solve_steps": 5,
                "solver_execution_decisions": 25,
                "finite_attempted_latency_steps": 19,
                "nonfinite_attempted_latency_steps": 1,
                "attempted_latency_p50_s": 0.05,
                "attempted_latency_p95_s": 0.10,
                "attempted_latency_p99_s": 0.12,
                "controller_acceptance_rate_attempted_solve": 0.75,
                "bypass_fraction_of_solver_execution_decisions": 0.2,
            }
            for policy in policies
        ]
        write_csv(cost / "raw_policy_solver_summary.csv", summary_fields, policy_rows)
        policy_init_rows = []
        for policy in policies:
            for init_id in range(101, 106):
                policy_init_rows.append(
                    {
                        "risk_policy": policy,
                        "ego_init_id": init_id,
                        "debug_rows": 5,
                        "prediction_valid_context_steps": 4,
                        "prediction_invalid_context_steps": 1,
                        "no_solver_telemetry_context_steps": 0,
                        "attempted_solve_steps": 4,
                        "prediction_valid_attempted_solve_steps": 3,
                        "prediction_invalid_attempted_solve_steps": 1,
                        "prediction_valid_bypass_no_solve_steps": 1,
                        "prediction_invalid_bypass_no_solve_steps": 0,
                        "attempted_accepted_steps": 3,
                        "attempted_fallback_or_nonaccepted_steps": 1,
                        "rule_bypass_no_solve_steps": 1,
                        "solver_execution_decisions": 5,
                        "finite_attempted_latency_steps": 4,
                        "nonfinite_attempted_latency_steps": 0,
                        "attempted_latency_p50_s": 0.05,
                        "attempted_latency_p95_s": 0.10,
                        "attempted_latency_p99_s": 0.12,
                        "controller_acceptance_rate_attempted_solve": 0.75,
                        "bypass_fraction_of_solver_execution_decisions": 0.2,
                    }
                )
        write_csv(
            cost / "raw_policy_init_solver_summary.csv",
            summary_fields,
            policy_init_rows,
        )
        write_csv(
            cost / "policy_cost_summary.csv",
            (
                "risk_policy",
                "corrected_attempted_solve_status",
                "attempted_solve_steps",
                "attempted_accepted_steps",
                "attempted_fallback_or_nonaccepted_steps",
                "rule_bypass_no_solve_steps",
                "attempted_latency_p50_s",
                "attempted_latency_p95_s",
                "attempted_latency_p99_s",
            ),
            [
                {
                    "risk_policy": policy,
                    "corrected_attempted_solve_status": "pass",
                    "attempted_solve_steps": 20,
                    "attempted_accepted_steps": 15,
                    "attempted_fallback_or_nonaccepted_steps": 5,
                    "rule_bypass_no_solve_steps": 5,
                    "attempted_latency_p50_s": 0.05,
                    "attempted_latency_p95_s": 0.1,
                    "attempted_latency_p99_s": 0.12,
                }
                for policy in policies
            ],
        )
        for name in (
            "corrected_attempted_cost_effects.csv",
            "corrected_attempted_acceptance_effects.csv",
        ):
            write_csv(cost / name, ("metric", "value"), [{"metric": "fixture", "value": 1}])
        paired_fields = (
            "contrast",
            "metric",
            "unit",
            "paired_rollouts",
            "mean_effect",
            "median_effect",
            "minimum_effect",
            "maximum_effect",
            "positive_pairs",
            "zero_pairs",
            "negative_pairs",
            "independent_init_clusters",
            "cluster_mean_effect",
            "cluster_minimum_effect",
            "cluster_maximum_effect",
            "cluster_positive",
            "cluster_zero",
            "cluster_negative",
            "cluster_effects_json",
            "two_sided_exact_sign_flip_p_descriptive",
            "inference_scope",
        )
        for filename, metric, unit, effect in (
            (
                "corrected_attempted_cost_contrasts.csv",
                "adaptive_minus_control_attempted_p95_solve_time_s",
                "s",
                0.01,
            ),
            (
                "corrected_attempted_acceptance_contrasts.csv",
                "adaptive_minus_control_attempted_fallback_or_nonaccepted_fraction",
                "fraction",
                0.05,
            ),
        ):
            rows = []
            for index, fixed in enumerate(
                ("fixed_aggressive", "fixed_medium", "fixed_conservative"),
                start=1,
            ):
                value = effect * index
                rows.append(
                    {
                        "contrast": f"adaptive_minus_{fixed}",
                        "metric": metric,
                        "unit": unit,
                        "paired_rollouts": 20,
                        "mean_effect": value,
                        "median_effect": value,
                        "minimum_effect": value,
                        "maximum_effect": value,
                        "positive_pairs": 20,
                        "zero_pairs": 0,
                        "negative_pairs": 0,
                        "independent_init_clusters": 5,
                        "cluster_mean_effect": value,
                        "cluster_minimum_effect": value,
                        "cluster_maximum_effect": value,
                        "cluster_positive": 5,
                        "cluster_zero": 0,
                        "cluster_negative": 0,
                        "cluster_effects_json": json.dumps(
                            {str(init_id): value for init_id in range(101, 106)},
                            sort_keys=True,
                        ),
                        "two_sided_exact_sign_flip_p_descriptive": 0.0625,
                        "inference_scope": (
                            "descriptive post-hoc supervisor-feedback audit"
                        ),
                    }
                )
            write_csv(cost / filename, paired_fields, rows)
        deadline_rows = []
        for policy in policies:
            for deadline_name, deadline_s in (
                ("simulator_control_period_s", 0.05),
                ("smpc_planning_interval_s", 0.2),
                ("frozen_runtime_gate_s", 0.5),
            ):
                deadline_rows.append(
                    {
                        "risk_policy": policy,
                        "deadline_name": deadline_name,
                        "deadline_s": deadline_s,
                        "evaluation_status": "evaluated",
                        "finite_attempted_solve_steps": 19,
                        "nonfinite_attempted_solve_steps_excluded": 1,
                        "deadline_exceedance_steps": 2,
                        "deadline_exceedance_fraction_of_finite_attempts": 2 / 19,
                    }
                )
        write_csv(
            cost / "deadline_exceedance.csv",
            (
                "risk_policy",
                "deadline_name",
                "deadline_s",
                "evaluation_status",
                "finite_attempted_solve_steps",
                "nonfinite_attempted_solve_steps_excluded",
                "deadline_exceedance_steps",
                "deadline_exceedance_fraction_of_finite_attempts",
            ),
            deadline_rows,
        )
        failure_events = []
        affected_outcomes = []
        rollout_validation = []
        for policy in policies:
            for init_id in range(101, 106):
                for rollout_index in range(4):
                    common = {
                        "cell_id": f"cell_{policy}_{rollout_index}",
                        "predictor": "B1",
                        "risk_policy": policy,
                        "target_style": "assertive",
                        "ego_init_id": init_id,
                    }
                    rollout_validation.append(
                        {**common, "classification_validation_status": "pass"}
                    )
                    if rollout_index != 0:
                        continue
                    failure_events.append(
                        {
                            **common,
                            "rollout_completion_valid": 1,
                            "rollout_completion_failure": 0,
                            "rollout_completion_reason": "completed",
                            "rollout_completion_duration_s": 12.0,
                            "rollout_yield_outcome_observed": 1,
                            "rollout_yield_failure": 0,
                            "rollout_yield_outcome_reason": "valid_yield",
                            "rollout_minimum_footprint_separation_m": 1.5,
                            "rollout_footprint_collision": 0,
                            "rollout_native_collision_any": 0,
                            "rollout_native_collision_episode_count": 0,
                        }
                    )
                    affected_outcomes.append(
                        {
                            **common,
                            "attempted_solve_steps": 1,
                            "attempted_fallback_or_nonaccepted_steps": 1,
                            "attempted_fallback_or_nonaccepted_fraction": 1.0,
                            "completion_valid": 1,
                            "completion_failure": 0,
                            "completion_reason": "completed",
                            "completion_duration_s": 12.0,
                            "yield_outcome_observed": 1,
                            "yield_failure": 0,
                            "yield_outcome_reason": "valid_yield",
                            "minimum_footprint_separation_m": 1.5,
                            "footprint_collision": 0,
                            "native_collision_any": 0,
                            "native_collision_episode_count": 0,
                            "interpretation_boundary": (
                                "descriptive association, not a causal effect; not a "
                                "mathematical feasibility diagnosis"
                            ),
                        }
                    )
        write_csv(
            cost / "solver_failure_events.csv",
            tuple(failure_events[0]),
            failure_events,
        )
        write_csv(
            cost / "solver_failure_affected_rollout_outcomes.csv",
            tuple(affected_outcomes[0]),
            affected_outcomes,
        )
        write_csv(
            cost / "solver_failure_taxonomy.csv",
            ("return_status", "failure_events"),
            [{"return_status": "Infeasible_Problem_Detected", "failure_events": 20}],
        )
        write_csv(
            cost / "raw_rollout_validation.csv",
            tuple(rollout_validation[0]),
            rollout_validation,
        )
        raw_status = cost / "raw_taxonomy_status.json"
        write_json(
            raw_status,
            {
                "status": "pass",
                "hash_validation_status": "pass",
                "canonical_debug_files": 80,
                "expected_canonical_debug_files": 80,
                "failure_event_count": 20,
                "failure_taxonomy_rows": 1,
                "step_classification_status": "pass",
                "raw_step_identity_status": "pass",
                "telemetry_integrity_status": "pass",
                "no_solver_telemetry_context_steps": 0,
                "corrected_latency_status": "pass",
                "corrected_acceptance_status": "pass",
                "failure_downstream_outcome_join_status": "pass",
                "affected_rollout_outcome_rows": 20,
                "deadline_evaluation_status": "evaluated",
                "deadline_claim_status": "pass",
            },
        )
        write_json(
            cost / "analysis_summary.json",
            {
                "schema_version": "supervisor_feedback_cost_feasibility_v3",
                "status": "pass",
                "final_evidence_ready": True,
                "raw_step_classification_status": "pass",
                "raw_step_identity_status": "pass",
                "raw_telemetry_integrity_status": "pass",
                "raw_no_solver_telemetry_context_steps": 0,
                "corrected_attempted_latency_status": "pass",
                "corrected_attempted_acceptance_status": "pass",
                "failure_downstream_outcome_join_status": "pass",
            },
        )
        write_text(
            cost / "supervisor_feedback_02_policy_cost.tex",
            "\\begin{table}[t]\n\\caption{Corrected actual SMPC solve attempts only with P50, P95, P99, finite, non-finite and bypass counts.}\n\\begin{tabular}{lr}Policy & Attempts \\\\ Adaptive & 20 \\\\ \\end{tabular}\n\\end{table}\n",
        )
        write_text(
            cost / "supervisor_feedback_02_solver_nonoptimal.tex",
            "\\begin{table}[t]\n\\caption{Corrected-R3 controller acceptance and fallback audit. The accepted flag includes SUBOPTIMAL and is not mathematical optimality or a proof of feasibility. The denominator is actual solve attempts; bypass/no-solve decisions are shown separately.}\n\\begin{tabular}{lr}Policy & Fallback/nonaccepted \\\\ Adaptive & 5 \\\\ \\end{tabular}\n\\end{table}\n",
        )
        write_text(
            cost / "supervisor_feedback_02_paired_cost_acceptance.tex",
            "\\begin{table}[t]\n\\caption{Corrected adaptive-minus-all-fixed "
            "init-cluster paired effects; not end-to-end latency and not a "
            "feasibility certificate.}\n\\begin{tabular}{lr}Init $n$ & 5 "
            "\\\\ Recorded solve P95 & 1 \\\\ Fallback/nonacceptance & 1 "
            "\\\\ Fixed aggressive & 1 \\\\ Fixed medium & 1 "
            "\\\\ Fixed conservative & 1 \\\\ \\end{tabular}\n\\end{table}\n",
        )
        write_text(
            cost / "supervisor_feedback_02_failure_taxonomy.tex",
            "\\begin{table}[t]\n\\caption{Hash-validated fallback/nonaccepted taxonomy and recorded controller context.}\n\\begin{tabular}{lr}Status & Events \\\\ Recorded & 20 \\\\ \\end{tabular}\n\\end{table}\n",
        )
        write_text(
            cost / "supervisor_feedback_02_failure_downstream.tex",
            "\\begin{table}[t]\n\\caption{Canonical downstream outcomes for fallback/nonaccepted rollouts; descriptive association, not causal.}\n\\begin{tabular}{lr}Policy & Affected \\\\ Adaptive & 5 \\\\ \\end{tabular}\n\\end{table}\n",
        )
        cost_artifacts = {}
        for name in SF2_REQUIRED_FINAL_ARTIFACTS:
            path = cost / name
            cost_artifacts[name] = {
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
        r3_files = r3_snapshot / "r3_corrected_formal_snapshot.tar.gz.files.json"
        write_json(r3_files, {"file_count": 2325, "files": []})
        cost_source_paths = {
            "analysis_script": cost_source,
            "r3_corrected_matrix_audit": r3_matrix,
            "r3_rollout_outcomes": r3_rollouts,
            "r3_analysis_complete": r3_analysis,
            "r3_data_complete": r3_data,
            "r3_snapshot_files_manifest": r3_files,
        }
        cost_manifest = cost / "artifact_manifest.json"
        write_json(
            cost_manifest,
            {
                "schema_version": "supervisor_feedback_cost_feasibility_manifest_v3",
                "status": "pass",
                "legacy_aggregate_artifact_status": "preliminary_legacy_conflated",
                "final_evidence_ready": True,
                "raw_telemetry_integrity": {
                    "status": "pass",
                    "no_solver_telemetry_context_steps": 0,
                    "required_context_steps_for_final": 0,
                },
                "raw_debug_hash_validation": {
                    "status": "pass",
                    "validated_files": 80,
                    "validated_file_set_sha256": token("validated-r3-debug-set"),
                },
                "sources": {
                    name: {"bytes": path.stat().st_size, "sha256": digest(path)}
                    for name, path in cost_source_paths.items()
                },
                "artifacts": cost_artifacts,
            },
        )
        cost_receipt = cost / "SUPERVISOR_FEEDBACK_02_COMPLETE.json"
        write_json(
            cost_receipt,
            {
                "schema_version": "supervisor_feedback_02_complete_v3",
                "status": "pass",
                "final_evidence_ready": True,
                "legacy_aggregate_evidence_status": "preliminary_legacy_conflated",
                "observed_rollouts": 80,
                "legacy_total_nonoptimal_steps": 20,
                "legacy_total_debug_steps": 100,
                "raw_step_classification_status": "pass",
                "raw_step_identity_status": "pass",
                "raw_telemetry_integrity_status": "pass",
                "raw_no_solver_telemetry_context_steps": 0,
                "corrected_attempted_latency_status": "pass",
                "corrected_attempted_acceptance_status": "pass",
                "failure_downstream_outcome_join_status": "pass",
                "corrected_attempted_solve_steps": 80,
                "corrected_rule_bypass_no_solve_steps": 20,
                "corrected_attempted_fallback_or_nonaccepted_steps": 20,
                "legacy_minus_corrected_fallback_or_nonaccepted_steps": 0,
                "raw_taxonomy_status": "pass",
                "deadline_evaluation_status": "evaluated",
                "deadline_claim_status": "pass",
                "artifact_manifest": cost_manifest.name,
                "artifact_manifest_sha256": digest(cost_manifest),
                "artifacts": [*cost_artifacts, cost_manifest.name],
            },
        )

        r3_archive_hash = token("r3-full-archive")
        write_json(
            r3_snapshot / "r3_corrected_formal_snapshot.tar.gz.json",
            {
                "status": "pass",
                "archive_sha256": r3_archive_hash,
                "archive_verification": {"status": "pass", "verified_members": 2325},
                "files": 2325,
                "files_manifest_sha256": digest(r3_files),
            },
        )
        write_json(
            offline / "SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json",
            {
                "status": "pass",
                "source_r3_archive_sha256": r3_archive_hash,
                "receipts": {
                    "01_behaviour/SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json": digest(
                        behaviour_receipt
                    ),
                    "02_cost_feasibility/SUPERVISOR_FEEDBACK_02_COMPLETE.json": digest(
                        cost_receipt
                    ),
                },
                "source_sha256": {
                    "core/scripts/models/analyze_supervisor_feedback_behaviour.py": digest(
                        behaviour_source
                    ),
                    "core/scripts/models/analyze_supervisor_feedback_cost_feasibility.py": digest(
                        cost_source
                    ),
                    "core/scripts/models/run_supervisor_feedback_r3_offline_audits.sh": digest(
                        behaviour_runner
                    ),
                    "r3_corrected_matrix_audit.json": digest(r3_matrix),
                },
            },
        )

        sf3_source = repo / "sf3_source.txt"
        write_text(sf3_source)
        write_text(sf3 / "SUPERVISOR_COMMENT_3_AUDIT.md", "# Corrected fine-tuning audit\n")
        write_json(
            sf3 / "finetune_audit.json",
            {
                "schema_version": "supervisor_finetune_feedback_audit_v2",
                "status": "pass",
                "metric_policy": {
                    "overlapping_windows_are_independent": False,
                    "superseded_percentage_accuracy_is_current_evidence": False,
                },
            },
        )
        table_text = (
            "\\begin{table}[t]\n\\caption{Corrected B0--B1 frozen-test metrics "
            "using common rollout-macro aggregation and five independent held-out "
            "initialisation groups.}\n\\begin{tabular}{lrrr}Model & NLL & ADE & FDE "
            "\\\\ B0 & 2.17 & 1.28 & 2.64 \\\\ B1 & 1.86 & 0.10 & 0.12 "
            "\\\\ \\end{tabular}\n\\end{table}\n"
        )
        write_text(sf3 / "finetune_b0_b1_rollout_macro.tex", table_text)
        write_text(
            sf3 / "finetune_b0_b1_paired_init_effects.tex",
            table_text.replace("rollout-macro", "paired-init"),
        )
        same_rows = [
            {
                "variant": variant,
                "aggregation_level": aggregation,
                "full_horizon_windows": 315,
                "rollouts": 20,
                "held_out_init_groups": 5,
                "top1_ADE_m": ade,
                "top1_FDE_m": fde,
                "trajectory_mixture_NLL_nats_per_step": nll,
            }
            for aggregation in ("rollout_macro", "held_out_init_group_macro")
            for variant, ade, fde, nll in (
                ("B0", 1.28, 2.64, 2.17),
                ("B1", 0.10, 0.12, 1.86),
            )
        ]
        write_csv(
            sf3 / "frozen_test_same_aggregation.csv",
            tuple(same_rows[0]),
            same_rows,
        )
        contrast_rows = [
            {
                "contrast": "B1_minus_B0",
                "aggregation_level": aggregation,
                "full_horizon_windows": 315,
                "rollouts": 20,
                "held_out_init_groups": 5,
                "delta_top1_ADE_m": -1.18,
                "delta_top1_FDE_m": -2.52,
                "delta_trajectory_mixture_NLL_nats_per_step": -0.31,
            }
            for aggregation in ("rollout_macro", "held_out_init_group_macro")
        ]
        write_csv(
            sf3 / "frozen_test_same_aggregation_contrasts.csv",
            tuple(contrast_rows[0]),
            contrast_rows,
        )
        paired_rows = [
            {
                "ego_init_id": init_id,
                "B1_better_top1_ADE_m": 1,
                "B1_better_top1_FDE_m": 1,
                "B1_better_trajectory_mixture_NLL_nats_per_step": 1,
            }
            for init_id in range(46, 51)
        ]
        write_csv(
            sf3 / "frozen_test_paired_by_init.csv",
            tuple(paired_rows[0]),
            paired_rows,
        )
        paired_summary_rows = [
            {
                "metric": metric,
                "independent_paired_init_groups": 5,
                "favourable_init_count": 5,
                "two_sided_exact_sign_flip_p": 0.0625,
                "inference_note": (
                    "The exact two-sided sign-flip value is a sensitivity analysis "
                    "under a symmetric paired-cluster-effect assumption, not "
                    "treatment-randomisation inference."
                ),
            }
            for metric in (
                "top1_ADE_m",
                "top1_FDE_m",
                "trajectory_mixture_NLL_nats_per_step",
            )
        ]
        write_csv(
            sf3 / "frozen_test_paired_summary.csv",
            tuple(paired_summary_rows[0]),
            paired_summary_rows,
        )
        write_json(
            sf3 / "percentage_accuracy_scan.json",
            {"status": "pass", "hit_count": 0, "hits": []},
        )
        for name in (
            "physical_baselines_paired_by_init.csv",
            "physical_baselines_same_aggregation.csv",
        ):
            write_csv(sf3 / name, ("baseline", "ADE"), [{"baseline": "CV", "ADE": 1.0}])
        population_contract = sf3 / "frozen_test_population_contract.json"
        write_json(
            population_contract,
            {
                "schema_version": "frozen_test_population_contract_v1",
                "status": "pass",
                "checks": {
                    "jsonl_sha256_exact_and_equal": True,
                    "jsonl_bytes_exact_and_equal": True,
                    "anchors_sha256_exact_and_equal": True,
                    "anchors_bytes_exact_and_equal": True,
                    "evaluation_contract_exact_and_equal": True,
                    "aggregate_counts_exact_and_equal": True,
                    "per_init_keys_and_counts_exact_and_equal": True,
                    "per_rollout_keys_and_counts_exact_and_equal": True,
                },
                "test_jsonl": {
                    "sha256": "29291fe2a172047267c3a0c4c3d5693519f550881010a965fb60166a5013d770",
                    "bytes": 5_673_913,
                },
                "anchors": {
                    "sha256": "52ab777b9bf695ed56f069b96cbce337014a47f457ed19c638abfb1cde6aa982",
                    "bytes": 6_528,
                },
            },
        )
        sf3_artifacts = {
            name: digest(sf3 / name) for name in SF3_REQUIRED_ARTIFACTS
        }
        sf3_sources = {"sf3_source.txt": digest(sf3_source)}
        sf3_manifest = sf3 / "FINETUNE_AUDIT_MANIFEST.json"
        write_json(
            sf3_manifest,
            {
                "schema_version": "supervisor_finetune_feedback_manifest_v2",
                "status": "pass",
                "checks_failed": 0,
                "checks_passed": 9,
                "independent_paired_init_groups": 5,
                "analysis_requires_carla": False,
                "analysis_requires_training": False,
                "frozen_test_population_contract_status": "pass",
                "frozen_test_population_contract_sha256": digest(population_contract),
                "test_jsonl_sha256": "29291fe2a172047267c3a0c4c3d5693519f550881010a965fb60166a5013d770",
                "anchors_sha256": "52ab777b9bf695ed56f069b96cbce337014a47f457ed19c638abfb1cde6aa982",
                "artifacts": sf3_artifacts,
                "source_sha256": sf3_sources,
            },
        )
        write_json(
            sf3 / "SUPERVISOR_COMMENT_3_COMPLETE.json",
            {
                "schema_version": "supervisor_comment_3_complete_v2",
                "stage": "supervisor_feedback_item_3_finetune_audit",
                "status": "pass",
                "failure_count": 0,
                "old_percentage_accuracy_hit_count": 0,
                "overlapping_windows_treated_as_independent": False,
                "independent_paired_init_groups": 5,
                "frozen_test_population_contract_status": "pass",
                "frozen_test_population_contract_sha256": digest(population_contract),
                "test_jsonl_sha256": "29291fe2a172047267c3a0c4c3d5693519f550881010a965fb60166a5013d770",
                "anchors_sha256": "52ab777b9bf695ed56f069b96cbce337014a47f457ed19c638abfb1cde6aa982",
                "manifest": sf3_manifest.name,
                "manifest_sha256": digest(sf3_manifest),
                "artifacts": sf3_artifacts,
                "source_sha256": sf3_sources,
            },
        )

        prereg = (
            repo
            / "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/"
            "prereg/SF4_SUPERVISOR_BEHAVIOURAL_AUTHORITY_PREREG.json"
        )
        write_json(
            prereg,
            {
                "schema_version": "sf4_supervisor_behavioural_authority_prereg_v1",
                "status": "frozen_before_outcomes",
                "secondary_estimands": {
                    "same_did_and_direct_effects": [
                        "minimum_margin_adjusted_bbox_separation_m",
                        "cautious_approach_progress_m",
                        "first_stop_distance_to_conflict_m",
                        "first_stop_distance_to_designed_stop_m",
                        "stopped_duration_s",
                        "nominal_conflict_clear_to_actual_path_release_s",
                        "actual_path_release_to_sustained_resume_s",
                        "buffered_conflict_clear_to_sustained_resume_s",
                    ]
                },
            },
        )
        for relative in SF4_REQUIRED_EXECUTION_SOURCES:
            path = repo / relative
            if not path.is_file():
                write_text(path, f"# fixture execution source: {relative}\n")
        tuning_paths = {
            mode: sf4 / f"_frozen_tuning/supervisor_authority_{mode}.json"
            for mode in ("on", "off")
        }
        for mode, path in tuning_paths.items():
            write_json(
                path,
                {"yield_supervisor_behavioural_authority_mode": mode},
            )
        cells = [
            {
                "cell_id": f"SF4_B1_{risk}_{style}_supervisor_{mode}",
                "predictor": "B1",
                "risk_policy": risk,
                "target_style": style,
                "supervisor_authority_mode": mode,
            }
            for risk in ("adaptive", "fixed_medium")
            for style in ("assertive", "reactive")
            for mode in ("on", "off")
        ]
        execution_order = [
            {**cell, "ego_init_id": init_id}
            for init_id in range(106, 116)
            for cell in cells
        ]
        spawn_preflight = sf4 / "sf4_town05_spawn_preflight.json"
        deployment_preflight = sf4 / "sf4_b1_deployment_preflight.json"
        write_json(spawn_preflight, {"status": "pass"})
        write_json(deployment_preflight, {"status": "pass"})
        contract = sf4 / "sf4_supervisor_behavioural_authority_run_contract.json"
        write_json(
            contract,
            {
                "schema_version": "sf4_supervisor_behavioural_authority_run_contract_v1",
                "status": "frozen_before_outcomes",
                "formal_evidence": True,
                "expected_rollouts": 80,
                "independent_unit": "ego_init_id",
                "ego_init_ids": list(range(106, 116)),
                "cells": cells,
                "execution_order": execution_order,
                "risk_policies": ["adaptive", "fixed_medium"],
                "target_styles": ["assertive", "reactive"],
                "supervisor_authority_modes": ["on", "off"],
                "primary_did": "(adaptive-fixed_medium)_on - (adaptive-fixed_medium)_off",
                "common_controller_contract": {
                    "yield_rule_smpc_bypass_enabled": True,
                    "yield_post_solver_action_filter_mode": "apply",
                    "only_behavioral_arm_difference": "vehicle_role_overrides.ego.yield_supervisor_behavioural_authority_mode",
                    "authority_off_allowed_solver_influence": [
                        "interaction_estimator_to_adaptive_risk_allocation"
                    ],
                    "authority_off_disabled_channels": ["rule_smpc_bypass"],
                },
                "server_wall_time_contract": {
                    "schema_version": "server_wall_time_diagnostics_v1",
                    "clock": "time.perf_counter",
                    "inferential_unit": "ego_init_id paired cluster",
                    "server_side_diagnostic_only": True,
                    "deployment_or_real_time_guarantee": False,
                },
                "hashes": {
                    "prereg_json": digest(prereg),
                    "spawn_preflight": digest(spawn_preflight),
                    "deployment_preflight": digest(deployment_preflight),
                    "execution_sources": {
                        relative: digest(repo / relative)
                        for relative in SF4_REQUIRED_EXECUTION_SOURCES
                    },
                    "supervisor_authority_tuning": {
                        mode: digest(path) for mode, path in tuning_paths.items()
                    },
                },
                "paths_relative_to_results": {
                    "supervisor_authority_tuning": {
                        mode: path.relative_to(sf4).as_posix()
                        for mode, path in tuning_paths.items()
                    }
                },
                "no_post_outcome_tuning": True,
            },
        )

        implementation_gate = {
            "status": "pass",
            "rule_smpc_bypass_configured_identically": True,
            "authority_on_applies_eligible_rule_smpc_bypass": True,
            "authority_off_logs_shadow_bypass_but_always_solves": True,
            "authority_record_present_every_step": True,
            "all_upstream_and_downstream_candidates_computed": True,
            "authority_on_applies_candidate_channels": True,
            "authority_off_nonrisk_solver_control_and_next_state_neutral": True,
            "shadow_behaviour_state_isolated": True,
            "interaction_estimator_state_limited_to_adaptive_risk_when_off": True,
            "collision_outcomes_retained": True,
        }
        first_stage_cell = {
            "rollouts": 10,
            "any_channel_requested_fraction": 0.2,
            "post_action_requested_fraction": 0.1,
            "authority_applied_fraction": 0.1,
        }
        first_stage = {
            "status": "active",
            "by_authority": {
                "on": {
                    "rollouts": 40,
                    "any_channel_requested_fraction": 0.25,
                    "post_action_requested_fraction": 0.1,
                    "authority_applied_fraction": 0.1,
                },
                "off": {
                    "rollouts": 40,
                    "any_channel_requested_fraction": 0.25,
                    "post_action_requested_fraction": 0.1,
                    "authority_applied_fraction": 0.0,
                },
            },
            "by_authority_risk_style": {
                f"{mode}__{risk}__{style}": dict(first_stage_cell)
                for mode in ("on", "off")
                for risk in ("adaptive", "fixed_medium")
                for style in ("assertive", "reactive")
            },
            "zero_activity_is_integrity_failure": False,
            "zero_activity_triggers_extra_rollouts": False,
            "claim_limit_if_inactive": "No activation means masking is unidentified.",
        }
        manipulation = {
            "schema_version": "sf4_supervisor_behavioural_authority_manipulation_v1",
            "status": "pass",
            "rollouts_checked": 80,
            "implementation_manipulation_gate": implementation_gate,
            "observed_first_stage_activity": first_stage,
        }
        controller_cells = {
            f"{mode}__{risk}__{style}": {
                "rollouts": 10,
                "factual_solver_attempts": 10,
                "controller_accepted_attempts": 8,
                "fallback_or_nonaccepted_attempts": 2,
                "controller_accepted_fraction": 0.8,
                "fallback_or_nonaccepted_fraction": 0.2,
                "raw_solver_return_status_counts": {"Solve_Succeeded": 10},
                "raw_solver_return_status_missing_count": 0,
            }
            for mode in ("on", "off")
            for risk in ("adaptive", "fixed_medium")
            for style in ("assertive", "reactive")
        }
        controller = {
            "schema_version": "sf4_controller_acceptance_and_solver_status_v1",
            "status": "pass",
            "semantic_boundary": (
                "controller acceptance includes SUBOPTIMAL and is not strict "
                "optimizer-optimality or feasibility"
            ),
            "denominator": (
                "factual SMPC attempts only; effective bypass excluded"
            ),
            "raw_return_status_is_separately_reported": True,
            "full_matrix": {
                "rollouts": 80,
                "factual_solver_attempts": 80,
                "controller_accepted_attempts": 64,
                "fallback_or_nonaccepted_attempts": 16,
                "controller_accepted_fraction": 0.8,
                "fallback_or_nonaccepted_fraction": 0.2,
                "raw_solver_return_status_counts": {"Solve_Succeeded": 80},
                "raw_solver_return_status_missing_count": 0,
            },
            "by_authority_risk_style": controller_cells,
        }
        wall_time = {
            "schema_version": "sf4_server_wall_time_analysis_v1",
            "status": "pass",
            "formal_rollouts": 80,
            "clock": "time.perf_counter",
            "server_side_diagnostic_only": True,
            "deployment_or_real_time_guarantee": False,
            "inferential_unit": "ego_init_id paired cluster, never simulation step",
            "by_authority_rollout_means": {
                "on": {
                    "rollouts": 40,
                    "ego_policy_wall_time_p50_ms__rollout_mean": 8.0,
                    "ego_policy_wall_time_p95_ms__rollout_mean": 12.0,
                    "ego_policy_wall_time_p99_ms__rollout_mean": 14.0,
                    "prediction_wall_time_p50_ms__rollout_mean": 4.0,
                    "prediction_wall_time_p95_ms__rollout_mean": 6.0,
                    "prediction_wall_time_p99_ms__rollout_mean": 7.0,
                },
                "off": {
                    "rollouts": 40,
                    "ego_policy_wall_time_p50_ms__rollout_mean": 7.0,
                    "ego_policy_wall_time_p95_ms__rollout_mean": 10.0,
                    "ego_policy_wall_time_p99_ms__rollout_mean": 13.0,
                    "prediction_wall_time_p50_ms__rollout_mean": 4.0,
                    "prediction_wall_time_p95_ms__rollout_mean": 6.0,
                    "prediction_wall_time_p99_ms__rollout_mean": 7.0,
                },
            },
        }
        primary_effect = {
            "defined_init_clusters": 10,
            "total_init_clusters": 10,
            "mean_effect": 0.25,
            "cluster_bootstrap_95ci": [-0.1, 0.6],
            "exact_two_sided_sign_flip_sensitivity_value": 0.125,
            "sign_flip_assumption": "symmetric distribution of init-cluster effects",
            "randomisation_inference": False,
        }
        direct_effects = {
            name: dict(primary_effect)
            for name in (
                "risk_effect_authority_on",
                "risk_effect_authority_off",
                "authority_effect_adaptive",
                "authority_effect_fixed_medium",
            )
        }
        inference = {
            "schema_version": "sf4_supervisor_behavioural_authority_cluster_inference_v1",
            "status": "pass",
            "independent_unit": "ego_init_id",
            "primary_estimand": "(adaptive-fixed_medium)_on - (adaptive-fixed_medium)_off",
            "primary_outcome": "failure_penalized_completion_time_s",
            "exact_sensitivity_analysis": (
                "two-sided sign flips under symmetry; not randomisation inference"
            ),
            "bootstrap": {
                "unit": "complete ego-init block",
                "replicates": 10000,
                "seed": 20260814,
            },
            "outcomes": {
                metric: dict(primary_effect)
                for metric in (
                    "failure_penalized_completion_time_s",
                    "minimum_margin_adjusted_bbox_separation_m",
                    "cautious_approach_progress_m",
                    "first_stop_distance_to_conflict_m",
                    "first_stop_distance_to_designed_stop_m",
                    "stopped_duration_s",
                    "nominal_conflict_clear_to_actual_path_release_s",
                    "actual_path_release_to_sustained_resume_s",
                    "buffered_conflict_clear_to_sustained_resume_s",
                )
            },
            "direct_paired_effects": {
                metric: {name: dict(primary_effect) for name in direct_effects}
                for metric in (
                    "failure_penalized_completion_time_s",
                    "minimum_margin_adjusted_bbox_separation_m",
                    "cautious_approach_progress_m",
                    "first_stop_distance_to_conflict_m",
                    "first_stop_distance_to_designed_stop_m",
                    "stopped_duration_s",
                    "nominal_conflict_clear_to_actual_path_release_s",
                    "actual_path_release_to_sustained_resume_s",
                    "buffered_conflict_clear_to_sustained_resume_s",
                )
            },
        }
        analysis_dir = sf4 / "analysis"
        write_text(analysis_dir / "sf4_rollout_outcomes.csv", "cell_id,value\nfixture,1\n")
        write_text(analysis_dir / "sf4_per_init_did.csv", "ego_init_id,did\n106,0.1\n")
        write_text(analysis_dir / "sf4_per_init_direct_effects.csv", "ego_init_id,effect\n106,0.1\n")
        write_json(analysis_dir / "sf4_inference.json", inference)
        write_json(analysis_dir / "sf4_manipulation_checks.json", manipulation)
        write_json(analysis_dir / "sf4_server_wall_time_diagnostics.json", wall_time)
        write_json(
            analysis_dir / "sf4_controller_acceptance_and_solver_status.json",
            controller,
        )
        write_json(
            analysis_dir / "sf4_input_manifest.json",
            {
                "schema_version": "sf4_supervisor_behavioural_authority_analysis_input_manifest_v1",
                "status": "pass",
                "contract": {"sha256": digest(contract)},
                "preregistration": {"sha256": digest(prereg)},
                "rollouts": [
                    {"cell_id": item["cell_id"], "ego_init_id": item["ego_init_id"]}
                    for item in execution_order
                ],
            },
        )
        write_text(analysis_dir / "SF4_ANALYSIS_REPORT.md", "# Final SF4 report\n")
        write_text(
            analysis_dir / "sf4_primary_and_direct_effects.tex",
            "\\begin{table}[t]\\caption{Primary DID and direct paired effects.}\\begin{tabular}{lr}Primary DID & 0.25 \\\\ \\end{tabular}\\end{table}\n",
        )
        write_text(
            analysis_dir / "sf4_behavioural_authority_effects.tex",
            "\\begin{table*}[t]\\caption{SF4 supervisor-authority effects on "
            "separation and behaviour; $n/10$ is reported. Missing event clocks "
            "remain censored and a positive value is not universally a benefit.}"
            "\\begin{tabular}{lr}Cautious approach progress & 0.25 \\\\ "
            "Signed stop-line error & 0.25 \\\\ DID & 0.25 \\\\ "
            "\\end{tabular}\\end{table*}\n",
        )
        write_text(
            analysis_dir / "sf4_authority_manipulation_and_first_stage.tex",
            "\\begin{table}[t]\\caption{Zero activity is a retained scientific outcome.}\\begin{tabular}{lr}First stage & active \\\\ \\end{tabular}\\end{table}\n",
        )
        write_text(
            analysis_dir / "sf4_computational_wall_time.tex",
            "\\begin{table*}[t]\\caption{Server diagnostics, not an end-to-end "
            "deployment or real-time guarantee.}\\begin{tabular}{lr}Ego policy P50 "
            "& 8 \\\\ Ego policy P95 & 10 \\\\ Ego policy P99 & 14 \\\\ "
            "Shared prediction P50 & 4 \\\\ Shared prediction P95 & 6 \\\\ "
            "Shared prediction P99 & 7 \\\\ \\end{tabular}\\end{table*}\n",
        )
        write_text(
            analysis_dir / "sf4_controller_acceptance_and_solver_status.tex",
            "\\begin{table}[t]\\caption{Controller acceptance is not strict optimizer optimality or feasibility.}\\begin{tabular}{lr}Accepted & 64 \\\\ \\end{tabular}\\end{table}\n",
        )
        analysis_products = {
            name: {
                "bytes": (analysis_dir / name).stat().st_size,
                "sha256": digest(analysis_dir / name),
            }
            for name in SF4_REQUIRED_ANALYSIS_PRODUCTS
        }
        solver_execution = {
            "debug_steps": 100,
            "bypass_requested_steps": 20,
            "bypass_applied_steps": 10,
            "factual_solver_attempts": 80,
            "controller_accepted_attempts": 64,
            "fallback_or_nonaccepted_attempts": 16,
            "controller_acceptance_not_strict_optimizer_feasibility": True,
            "effective_bypass_excluded_from_controller_acceptance_denominator": True,
            "raw_solver_return_status_taxonomy": controller,
        }
        analysis_receipt = analysis_dir / "SF4_ANALYSIS_COMPLETE.json"
        write_json(
            analysis_receipt,
            {
                "schema_version": "sf4_supervisor_behavioural_authority_analysis_complete_v1",
                "status": "pass",
                "formal_evidence": True,
                "observed_rollouts": 80,
                "independent_init_clusters": 10,
                "primary_estimand": "(adaptive-fixed_medium)_on - (adaptive-fixed_medium)_off",
                "primary_outcome": "failure_penalized_completion_time_s",
                "integrity_gate": "pass",
                "implementation_manipulation_gate": implementation_gate,
                "observed_first_stage_activity": first_stage,
                "solver_execution": solver_execution,
                "server_wall_time_diagnostics": wall_time,
                "products": analysis_products,
            },
        )

        snapshot_records = [
            {
                "path": contract.name,
                "bytes": contract.stat().st_size,
                "sha256": digest(contract),
            },
            {
                "path": "analysis/SF4_ANALYSIS_COMPLETE.json",
                "bytes": analysis_receipt.stat().st_size,
                "sha256": digest(analysis_receipt),
            },
            *[
                {
                    "path": f"analysis/{name}",
                    "bytes": (analysis_dir / name).stat().st_size,
                    "sha256": digest(analysis_dir / name),
                }
                for name in SF4_REQUIRED_ANALYSIS_PRODUCTS
            ],
        ]
        snapshot_rollouts = []
        for init_id in range(106, 116):
            for cell_record in cells:
                cell = cell_record["cell_id"]
                scenario = f"scenario_ego_init_{init_id}"
                critical = {}
                for required in SF4_REQUIRED_RAW_FILES:
                    critical[required] = {
                        "bytes": 1,
                        "sha256": token(f"{cell}/{scenario}/{required}"),
                    }
                    snapshot_records.append(
                        {
                            "path": f"{cell}/{scenario}/{required}",
                            "bytes": 1,
                            "sha256": critical[required]["sha256"],
                        }
                    )
                receipt = sf4 / cell / f"SF4_ROLLOUT_{init_id}_COMPLETE.json"
                write_json(
                    receipt,
                    {
                        "schema_version": "formal_rollout_complete_v1",
                        "stage": "SF4",
                        "status": "pass",
                        "cell_id": cell,
                        "ego_init_id": init_id,
                        "scenario_dir": scenario,
                        "raw_evidence_sha256": token(f"raw-{cell}-{init_id}"),
                        "critical_artifacts": critical,
                    },
                )
                snapshot_records.append(
                    {
                        "path": receipt.relative_to(sf4).as_posix(),
                        "bytes": receipt.stat().st_size,
                        "sha256": digest(receipt),
                    }
                )
                snapshot_rollouts.append(
                    {
                        "cell_id": cell,
                        "ego_init_id": init_id,
                        "receipt": receipt.relative_to(sf4).as_posix(),
                        "receipt_sha256": digest(receipt),
                        "raw_evidence_sha256": token(f"raw-{cell}-{init_id}"),
                    }
                )
        full_manifest = (
            sf4
            / "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.files.json"
        )
        write_json(
            full_manifest,
            {
                "schema_version": "sf4_supervisor_behavioural_authority_full_raw_snapshot_files_manifest_v1",
                "status": "pass",
                "source_files_deleted": False,
                "file_count": len(snapshot_records),
                "files": snapshot_records,
                "external_files": [
                    {
                        "path": "_external/SF4_SUPERVISOR_BEHAVIOURAL_AUTHORITY_PREREG.json",
                        "bytes": prereg.stat().st_size,
                        "sha256": digest(prereg),
                    }
                ],
                "rollouts": snapshot_rollouts,
                "coverage": {
                    "receipt_raw_and_attempt_provenance_verified": True,
                    "all_canonical_scenario_files_included": True,
                    "all_attempt_provenance_files_included": True,
                    "server_wall_time_recomputation_supported": True,
                    "controller_acceptance_and_raw_status_recomputation_supported": True,
                },
            },
        )
        archive_name = "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz"
        archive_hash = token("sf4-full-archive")
        archive_sidecar = sf4 / f"{archive_name}.json"
        write_json(
            archive_sidecar,
            {
                "schema_version": "sf4_supervisor_behavioural_authority_full_raw_snapshot_v1",
                "status": "pass",
                "archive": archive_name,
                "archive_sha256": archive_hash,
                "observed_rollouts": 80,
                "full_raw_evidence": True,
                "bbox_and_separation_recomputation_supported": True,
                "server_wall_time_recomputation_supported": True,
                "controller_acceptance_and_raw_status_recomputation_supported": True,
                "source_files_deleted": False,
                "files_manifest": full_manifest.name,
                "files_manifest_sha256": digest(full_manifest),
            },
        )
        full_marker = sf4 / "SF4_FULL_RAW_SNAPSHOT_COMPLETE.json"
        write_json(
            full_marker,
            {
                "schema_version": "sf4_full_raw_snapshot_complete_v1",
                "status": "pass",
                "formal_evidence": True,
                "observed_rollouts": 80,
                "archive": archive_name,
                "archive_sha256": archive_hash,
                "archive_sidecar": archive_sidecar.name,
                "archive_sidecar_sha256": digest(archive_sidecar),
                "files_manifest": full_manifest.name,
                "files_manifest_sha256": digest(full_manifest),
                "receipt_raw_and_attempt_provenance_verified": True,
                "bbox_and_separation_recomputation_supported": True,
                "server_wall_time_recomputation_supported": True,
                "controller_acceptance_and_raw_status_recomputation_supported": True,
                "source_files_deleted": False,
            },
        )
        write_json(
            sf4 / "SF4_COMPLETE.json",
            {
                "schema_version": "sf4_supervisor_behavioural_authority_complete_v1",
                "status": "pass",
                "formal_evidence": True,
                "observed_rollouts": 80,
                "independent_init_clusters": 10,
                "contract_sha256": digest(contract),
                "preregistration_sha256": digest(prereg),
                "spawn_preflight_sha256": digest(spawn_preflight),
                "deployment_preflight_sha256": digest(deployment_preflight),
                "analysis_complete_sha256": digest(analysis_receipt),
                "implementation_manipulation_gate": implementation_gate,
                "observed_first_stage_activity_status": "active",
                "solver_execution": solver_execution,
                "server_wall_time_diagnostics": wall_time,
                "additional_sf4_carla_rollouts_required": False,
                "full_raw_snapshot_sha256": archive_hash,
                "full_raw_snapshot_sidecar_sha256": digest(archive_sidecar),
                "full_raw_snapshot_files_manifest_sha256": digest(full_manifest),
                "full_raw_snapshot_complete_sha256": digest(full_marker),
                "bbox_and_separation_recomputation_supported": True,
                "server_wall_time_recomputation_supported": True,
                "controller_acceptance_and_raw_status_recomputation_supported": True,
                "source_raw_evidence_deleted": False,
            },
        )
        return feedback, sf4

    def test_complete_fixture_is_final_release_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            feedback, sf4 = self.build_fixture(repo)
            result = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
        self.assertEqual(result["status"], "pass", result["failures"])
        self.assertTrue(result["final_release_eligible"])
        self.assertTrue(all(result["checks"].values()))

    def test_removing_any_required_stage_prevents_final_pass(self) -> None:
        removals = {
            "sf1": Path("r3_offline/01_behaviour/SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json"),
            "sf2": Path("r3_offline/02_cost_feasibility/raw_taxonomy_status.json"),
            "sf3": Path("03_finetune_audit/SUPERVISOR_COMMENT_3_COMPLETE.json"),
            "sf4_receipt": None,
            "sf4_full_snapshot": None,
        }
        for name, relative in removals.items():
            with self.subTest(stage=name), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary)
                feedback, sf4 = self.build_fixture(repo)
                if relative is not None:
                    (feedback / relative).unlink()
                elif name == "sf4_receipt":
                    next(sf4.glob("SF4_*/SF4_ROLLOUT_*_COMPLETE.json")).unlink()
                else:
                    (sf4 / "SF4_FULL_RAW_SNAPSHOT_COMPLETE.json").unlink()
                result = audit_supervisor_feedback_closure(
                    repo,
                    supervisor_feedback_root=feedback,
                    sf4_results_root=sf4,
                )
                self.assertNotEqual(result["status"], "pass")
                self.assertFalse(result["final_release_eligible"])

    def test_sf1_contract_and_source_drift_are_fatal(self) -> None:
        mutations = (
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/behaviour_analysis_contract.json",
            "core/scripts/models/analyze_supervisor_feedback_behaviour.py",
            "core/scripts/models/run_supervisor_feedback_r3_offline_audits.sh",
            "core/scripts/models/analyze_supervisor_feedback_cost_feasibility.py",
        )
        for relative in mutations:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary)
                feedback, sf4 = self.build_fixture(repo)
                path = repo / relative
                path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
                result = audit_supervisor_feedback_closure(
                    repo,
                    supervisor_feedback_root=feedback,
                    sf4_results_root=sf4,
                )
                self.assertEqual(result["status"], "incomplete")
                self.assertFalse(result["final_release_eligible"])

    def test_sf2_v3_schema_fields_counts_and_required_artifacts_are_fail_closed(self) -> None:
        mutations = (
            "old_v2_schema",
            "missing_integrity_field",
            "inconsistent_attempt_count",
            "missing_corrected_artifact",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary)
                feedback, sf4 = self.build_fixture(repo)
                cost = feedback / "r3_offline/02_cost_feasibility"
                receipt_path = cost / "SUPERVISOR_FEEDBACK_02_COMPLETE.json"
                manifest_path = cost / "artifact_manifest.json"
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if mutation == "old_v2_schema":
                    receipt["schema_version"] = "supervisor_feedback_02_complete_v2"
                elif mutation == "missing_integrity_field":
                    receipt.pop("raw_telemetry_integrity_status")
                elif mutation == "inconsistent_attempt_count":
                    receipt["corrected_attempted_solve_steps"] += 1
                else:
                    name = "corrected_attempted_acceptance_contrasts.csv"
                    (cost / name).unlink()
                    manifest["artifacts"].pop(name)
                    receipt["artifacts"].remove(name)
                    write_json(manifest_path, manifest)
                    receipt["artifact_manifest_sha256"] = digest(manifest_path)
                write_json(receipt_path, receipt)

                # Rebind the synthetic combined receipt so the adversary cannot be
                # rejected merely because it forgot to update an outer checksum.
                combined_path = (
                    feedback
                    / "r3_offline/SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json"
                )
                combined = json.loads(combined_path.read_text(encoding="utf-8"))
                key = "02_cost_feasibility/SUPERVISOR_FEEDBACK_02_COMPLETE.json"
                combined["receipts"][key] = digest(receipt_path)
                write_json(combined_path, combined)

                result = audit_supervisor_feedback_closure(
                    repo,
                    supervisor_feedback_root=feedback,
                    sf4_results_root=sf4,
                )
                self.assertEqual(result["status"], "incomplete")
                self.assertFalse(result["checks"]["sf2_raw_taxonomy_and_deadlines_final"])
                self.assertFalse(result["final_release_eligible"])

    def test_stage_status_cannot_promote_partial_closure(self) -> None:
        self.assertEqual(
            stage_aware_status(
                base_ready=True, closure_status="incomplete", closure_mode="final"
            ),
            "fail",
        )
        self.assertEqual(
            stage_aware_status(
                base_ready=True, closure_status="incomplete", closure_mode="pre-sf4"
            ),
            "partial_pre_sf4",
        )
        self.assertEqual(
            stage_aware_status(
                base_ready=True, closure_status="pass", closure_mode="final"
            ),
            "pass",
        )

    def test_final_content_gate_requires_assets_ids_receipts_and_final_wording(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            feedback, sf4 = self.build_fixture(repo)
            closure = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            self.build_content_fixture(repo, closure)
            result = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertEqual(result["status"], "pass", result["failures"])

            wrapper = repo / WRAPPER_RELATIVE
            wrapper.write_text(
                wrapper.read_text().replace(
                    SUPERVISOR_CONTENT_EVIDENCE_IDS[-1], "REMOVED"
                ),
                encoding="utf-8",
            )
            missing_id = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertEqual(missing_id["status"], "fail")

            self.build_content_fixture(repo, closure)
            results_path = repo / RESULTS_RELATIVE
            results_path.write_text(
                results_path.read_text(encoding="utf-8")
                + "\n\\section{Results} This is a pre-SF4 evidence cut.\n"
                + f"% EVIDENCE: {SUPERVISOR_CONTENT_EVIDENCE_IDS[-1]}\n",
                encoding="utf-8",
            )
            provisional = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertEqual(provisional["status"], "fail")

            partial = audit_supervisor_feedback_content_integration(
                repo, closure_mode="pre-sf4", closure_payload=closure
            )
            self.assertEqual(partial["status"], "partial_pre_sf4")
            self.assertFalse(partial["final_release_eligible"])

    def test_fail_closed_provisional_discussion_exists_without_outcome_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            path = ensure_provisional_discussion_wrapper(repo)
            self.assertEqual(path, (repo / DISCUSSION_WRAPPER_RELATIVE).resolve())
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                PROVISIONAL_DISCUSSION_WRAPPER_TEXT,
            )
            self.assertFalse(
                any(character.isdigit() for character in PROVISIONAL_DISCUSSION_WRAPPER_TEXT)
            )
            self.assertIn("no outcome estimate", PROVISIONAL_DISCUSSION_WRAPPER_TEXT)

            feedback, sf4 = self.build_fixture(repo)
            closure = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            self.build_content_fixture(repo, closure)
            final_text = path.read_text(encoding="utf-8")
            self.assertNotEqual(final_text, PROVISIONAL_DISCUSSION_WRAPPER_TEXT)
            self.assertIn("estimates a bounded interaction contrast", final_text)
            self.assertIn(
                "supports a non-zero interaction is determined by its cluster interval",
                final_text,
            )

            # The draft helper cannot overwrite a completed final wrapper.
            ensure_provisional_discussion_wrapper(repo)
            self.assertEqual(path.read_text(encoding="utf-8"), final_text)

    def test_fail_closed_provisional_conclusion_is_numberless_and_final_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            path = ensure_provisional_conclusion_wrapper(repo)
            self.assertEqual(path, (repo / CONCLUSION_WRAPPER_RELATIVE).resolve())
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                PROVISIONAL_CONCLUSION_WRAPPER_TEXT,
            )
            self.assertFalse(
                any(character.isdigit() for character in PROVISIONAL_CONCLUSION_WRAPPER_TEXT)
            )
            provisional_lower = PROVISIONAL_CONCLUSION_WRAPPER_TEXT.lower()
            for forbidden in (
                "increased",
                "decreased",
                "attenuation point-pattern",
                "amplification point-pattern",
                "direction reversal point-pattern",
                "near-null point-pattern",
                "outperformed",
            ):
                self.assertNotIn(forbidden, provisional_lower)

            feedback, sf4 = self.build_fixture(repo)
            closure = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            self.build_content_fixture(repo, closure)
            final_text = path.read_text(encoding="utf-8")
            self.assertNotEqual(final_text, PROVISIONAL_CONCLUSION_WRAPPER_TEXT)
            self.assertIn("primary failure-penalised completion DID", final_text)
            self.assertIn("interval uncertainty", final_text)
            self.assertIn("Town05/B1 adaptive-versus-fixed-medium", final_text)
            self.assertIn("do not make the supervisor the sole cause", final_text)

            # The provisional helper never overwrites a final hash-bound synthesis.
            ensure_provisional_conclusion_wrapper(repo)
            self.assertEqual(path.read_text(encoding="utf-8"), final_text)

    def test_dynamic_conclusion_missing_tamper_and_provisional_all_fail_final_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            feedback, sf4 = self.build_fixture(repo)
            closure = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            self.build_content_fixture(repo, closure)
            wrapper = repo / CONCLUSION_WRAPPER_RELATIVE

            wrapper.unlink()
            missing = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertEqual(missing["status"], "fail")
            self.assertFalse(
                missing["checks"]["canonical_conclusion_wrapper_hash_bound"]
            )

            self.build_content_fixture(repo, closure)
            wrapper.write_text(
                wrapper.read_text(encoding="utf-8") + "\nTampered conclusion.\n",
                encoding="utf-8",
            )
            tampered = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertEqual(tampered["status"], "fail")
            self.assertFalse(
                tampered["checks"]["canonical_conclusion_wrapper_hash_bound"]
            )

            self.build_content_fixture(repo, closure)
            wrapper.write_text(PROVISIONAL_CONCLUSION_WRAPPER_TEXT, encoding="utf-8")
            provisional = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertEqual(provisional["status"], "fail")
            self.assertFalse(
                provisional["checks"]["dynamic_conclusion_is_final_not_provisional"]
            )
            self.assertFalse(
                provisional["checks"][
                    "dynamic_conclusion_synthesis_exact_and_visible_once"
                ]
            )

            self.build_content_fixture(repo, closure)
            static_conclusion = repo / CONCLUSION_RELATIVE
            static_conclusion.write_text(
                static_conclusion.read_text(encoding="utf-8").replace(
                    f"\\input{{{CONCLUSION_WRAPPER_LATEX_INPUT}}}\n", ""
                ),
                encoding="utf-8",
            )
            unreachable = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertEqual(unreachable["status"], "fail")
            self.assertFalse(
                unreachable["checks"][
                    "conclusion_directly_inputs_canonical_dynamic_synthesis"
                ]
            )

    def test_comments_and_unrelated_artifacts_cannot_satisfy_final_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            feedback, sf4 = self.build_fixture(repo)
            closure = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            self.build_content_fixture(repo, closure)
            results = repo / RESULTS_RELATIVE
            unrelated = repo / "docs/dissertation/latex/unrelated.tex"
            write_text(unrelated, "\\begin{table}unrelated\\end{table}\n")
            comments = "\n".join(
                f"% EVIDENCE: {evidence_id}"
                for evidence_id in SUPERVISOR_CONTENT_EVIDENCE_IDS
            )
            results.write_text(
                "\\section{Results}\n"
                + comments
                + "\n\\input{unrelated.tex}\n",
                encoding="utf-8",
            )
            audited = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertEqual(audited["status"], "fail")
            self.assertFalse(
                audited["checks"]["results_directly_inputs_canonical_wrapper"]
            )
            self.assertFalse(
                audited["checks"]["canonical_assets_directly_input_and_reachable"]
            )

    def test_each_of_fifteen_canonical_tables_is_individually_required(self) -> None:
        self.assertEqual(len(SUPERVISOR_CONTENT_EVIDENCE_IDS), 14)
        self.assertEqual(len(ALL_CONTENT_EVIDENCE_IDS), 15)
        self.assertEqual(set(ALL_CONTENT_EVIDENCE_IDS), set(CANONICAL_EVIDENCE_ASSETS))
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            feedback, sf4 = self.build_fixture(repo)
            closure = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            self.build_content_fixture(repo, closure)
            for evidence_id in ALL_CONTENT_EVIDENCE_IDS:
                with self.subTest(evidence_id=evidence_id):
                    asset = repo / CANONICAL_EVIDENCE_ASSETS[evidence_id]
                    original = asset.read_bytes()
                    asset.unlink()
                    audited = audit_supervisor_feedback_content_integration(
                        repo, closure_payload=closure
                    )
                    self.assertEqual(audited["status"], "fail")
                    self.assertFalse(audited["final_release_eligible"])
                    asset.parent.mkdir(parents=True, exist_ok=True)
                    asset.write_bytes(original)

    def test_obsolete_percentage_accuracy_claim_cannot_reenter_final_paper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            feedback, sf4 = self.build_fixture(repo)
            closure = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            self.build_content_fixture(repo, closure)
            results = repo / RESULTS_RELATIVE
            results.write_text(
                results.read_text(encoding="utf-8")
                + "\nFine-tuning accuracy increased from 0.98\\% to 100\\%.\n",
                encoding="utf-8",
            )
            audited = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertEqual(audited["status"], "fail")
            self.assertFalse(
                audited["checks"]["obsolete_percentage_accuracy_claim_absent"]
            )
            self.assertIn(
                RESULTS_RELATIVE.as_posix(),
                audited["obsolete_percentage_accuracy_claim_hits"],
            )

    def test_sf1_scientific_censoring_is_missing_safe_not_an_integrity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            feedback, sf4 = self.build_fixture(repo)
            paired_path = (
                feedback
                / "r3_offline/01_behaviour/behaviour_policy_paired_contrasts.csv"
            )
            with paired_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            target = next(
                row
                for row in rows
                if row["contrast"] == "adaptive_minus_fixed_aggressive"
                and row["metric"] == "pre_clearance_stopped_duration_s"
            )
            target.update(
                {
                    "independent_init_groups": "0",
                    "cluster_mean_effect": "",
                    "cluster_median_effect": "",
                    "minimum_effect": "",
                    "maximum_effect": "",
                    "negative_groups": "0",
                    "zero_groups": "0",
                    "positive_groups": "0",
                    "two_sided_exact_sign_flip_p_descriptive": "",
                    "per_init_effects_json": json.dumps(
                        {str(init_id): None for init_id in range(101, 106)},
                        sort_keys=True,
                    ),
                }
            )
            write_csv(paired_path, tuple(rows[0]), rows)
            receipt_path = (
                feedback
                / "r3_offline/01_behaviour/SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json"
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["artifacts"][paired_path.name] = digest(paired_path)
            write_json(receipt_path, receipt)
            combined_path = (
                feedback
                / "r3_offline/SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json"
            )
            combined = json.loads(combined_path.read_text(encoding="utf-8"))
            combined["receipts"][
                "01_behaviour/SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json"
            ] = digest(receipt_path)
            write_json(combined_path, combined)

            closure = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            self.assertEqual(closure["status"], "pass", closure["failures"])
            narrative = build_result_narrative(repo)
            fact = narrative["sf1"]["facts"]["paired_contrasts"][
                "fixed_aggressive"
            ]["pre_clearance_stopped_duration_s"]
            self.assertEqual(fact["observed_init_groups"], 0)
            self.assertIsNone(fact["cluster_mean_effect"])
            self.assertIn("NA denotes scientific censoring", narrative["sf1"]["text"])

    def test_sf2_paired_scientific_values_are_validated_beyond_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            feedback, sf4 = self.build_fixture(repo)
            cost = feedback / "r3_offline/02_cost_feasibility"
            contrast_path = cost / "corrected_attempted_cost_contrasts.csv"
            with contrast_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["cluster_mean_effect"] = "999"
            write_csv(contrast_path, tuple(rows[0]), rows)

            manifest_path = cost / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"][contrast_path.name] = {
                "bytes": contrast_path.stat().st_size,
                "sha256": digest(contrast_path),
            }
            write_json(manifest_path, manifest)
            receipt_path = cost / "SUPERVISOR_FEEDBACK_02_COMPLETE.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["artifact_manifest_sha256"] = digest(manifest_path)
            write_json(receipt_path, receipt)
            combined_path = (
                feedback
                / "r3_offline/SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json"
            )
            combined = json.loads(combined_path.read_text(encoding="utf-8"))
            combined["receipts"][
                "02_cost_feasibility/SUPERVISOR_FEEDBACK_02_COMPLETE.json"
            ] = digest(receipt_path)
            write_json(combined_path, combined)

            audited = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            self.assertEqual(audited["status"], "incomplete")
            self.assertFalse(audited["checks"]["sf2_raw_taxonomy_and_deadlines_final"])

    def test_inactive_sf4_first_stage_narrows_dynamic_discussion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            _, sf4 = self.build_fixture(repo)
            manipulation_path = sf4 / "analysis/sf4_manipulation_checks.json"
            payload = json.loads(manipulation_path.read_text(encoding="utf-8"))
            observed = payload["observed_first_stage_activity"]
            observed["status"] = "inactive_scientific_outcome"
            observed["claim_limit_if_inactive"] = (
                "No measured supervisor behavioural channel activated; masking is not "
                "identified."
            )
            for mode in ("on", "off"):
                observed["by_authority"][mode]["any_channel_requested_fraction"] = 0.0
            write_json(manipulation_path, payload)
            narrative = build_result_narrative(repo)
            discussion = narrative["discussion"]["text"]
            self.assertIn(
                "does not identify masking, amplification or a null supervisor interaction",
                discussion,
            )
            self.assertIn("not an integrity failure", discussion)
            self.assertNotIn("masking-like means only", discussion)
            conclusion = narrative["conclusion"]["text"]
            self.assertIn("passed its implementation gate", conclusion)
            self.assertIn("first stage was inactive", conclusion)
            self.assertIn("are not identified", conclusion)
            self.assertIn("scientific outcome", conclusion)
            self.assertIn("Town05/B1 adaptive-versus-fixed-medium", conclusion)
            self.assertIn("does not make the supervisor the sole cause", conclusion)
            self.assertNotIn("point-pattern", conclusion)
            self.assertEqual(
                narrative["conclusion"]["facts"][
                    "primary_completion_point_pattern"
                ],
                "not_identified_inactive_first_stage",
            )

    def test_narrative_tamper_legacy_sf4_path_and_misleading_phrase_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            feedback, sf4 = self.build_fixture(repo)
            closure = audit_supervisor_feedback_closure(
                repo,
                supervisor_feedback_root=feedback,
                sf4_results_root=sf4,
            )
            marker = self.build_content_fixture(repo, closure)
            payload = json.loads(marker.read_text(encoding="utf-8"))
            payload["result_narrative"]["sf1"]["text"] += " tampered"
            write_json(marker, payload)
            tampered = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertFalse(
                tampered["checks"]["result_specific_narrative_exact_and_hash_bound"]
            )

            self.build_content_fixture(repo, closure)
            discussion = repo / "docs/dissertation/latex/sections/07_discussion.tex"
            discussion.write_text(
                discussion.read_text(encoding="utf-8")
                + "\nReceipt: sf4_supervisor_action_ablation_v1.\n",
                encoding="utf-8",
            )
            legacy = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertFalse(
                legacy["checks"][
                    "obsolete_sf4_action_ablation_production_references_absent"
                ]
            )

            self.build_content_fixture(repo, closure)
            results = repo / RESULTS_RELATIVE
            results.write_text(
                results.read_text(encoding="utf-8")
                + "\nAttempted-solve latency/feasibility is the endpoint.\n",
                encoding="utf-8",
            )
            misleading = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertFalse(
                misleading["checks"][
                    "misleading_attempted_solve_latency_feasibility_phrase_absent"
                ]
            )

            self.build_content_fixture(repo, closure)
            conclusion = repo / CONCLUSION_WRAPPER_RELATIVE
            conclusion.write_text(
                conclusion.read_text(encoding="utf-8").replace(
                    "do not make the supervisor the sole cause",
                    "assigns the supervisor as the sole cause",
                ),
                encoding="utf-8",
            )
            unbounded_conclusion = audit_supervisor_feedback_content_integration(
                repo, closure_payload=closure
            )
            self.assertFalse(
                unbounded_conclusion["checks"][
                    "dynamic_conclusion_claim_boundary_present"
                ]
            )
            self.assertFalse(
                unbounded_conclusion["checks"][
                    "dynamic_conclusion_synthesis_exact_and_visible_once"
                ]
            )


if __name__ == "__main__":
    unittest.main()
