#!/usr/bin/env python3
"""Generate traceable thesis result IDs and the eight canonical paper tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


class Results:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.records: dict[str, dict[str, Any]] = {}
        self.source_hashes: dict[str, str] = {}

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    def add(
        self,
        result_id: str,
        value: Any,
        *,
        source: Path,
        locator: str,
        metric: str,
        unit: str,
        aggregation_unit: str,
        role: str = "primary",
        filter_rule: str = "none",
    ) -> None:
        if result_id in self.records:
            raise ValueError(f"Duplicate result id: {result_id}")
        relative = self.rel(source)
        source_hash = self.source_hashes.setdefault(relative, sha256(source))
        self.records[result_id] = {
            "value": value,
            "metric": metric,
            "unit": unit,
            "source_file": relative,
            "source_sha256": source_hash,
            "source_locator": locator,
            "filter": filter_rule,
            "aggregation_unit": aggregation_unit,
            "evidence_role": role,
        }


def require_pass(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if payload.get("status") != "pass":
        raise ValueError(f"Completion gate did not pass: {path}")
    return payload


def markdown_table(rows: list[dict[str, Any]]) -> str:
    fields = list(rows[0])
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---:" if field not in ("variant", "split", "predictor", "risk_policy", "target_style", "hypothesis_id", "claim", "verdict", "threat_id", "threat", "mitigation", "remaining_boundary", "subset", "contrast", "metric") else "---" for field in fields) + " |",
    ]
    for row in rows:
        values = []
        for field in fields:
            value = row[field]
            if isinstance(value, float):
                text = f"{value:.6g}"
            else:
                text = str(value)
            values.append(text.replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def build(repo: Path, output: Path) -> dict[str, Any]:
    generated = repo / "docs/paper/generated"
    paths = {
        "day7": generated / "day7/day7_split_audit.json",
        "validation": generated / "day8/final_validation/day8_validation_summary.json",
        "test": generated / "day8/final_test/day8_frozen_test_summary.json",
        "b0": generated / "day10/gaps/b0_offline/b0_frozen_offline_summary.json",
        "ablation": generated / "day10/gaps/context_ablation/interaction_context_ablation_summary.json",
        "day10_summary": generated / "day10/analysis/day10_analysis_summary.json",
        "day10_cells": generated / "day10/analysis/day10_cell_summary.csv",
        "timing_summary": generated / "day12/timing_synthesis/day12_timing_synthesis_summary.json",
        "timing_cells": generated / "day12/timing_synthesis/day12_timing_cell_summary.csv",
        "timing_contrasts": generated / "day12/timing_synthesis/day12_timing_paired_contrasts.csv",
        "collision": generated / "day12/server_stage/collision_attribution/day12_collision_window_audit.json",
        "day13": generated / "day13/analysis/day13_filtered_sensitivity_summary.json",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    day7 = require_pass(paths["day7"])
    validation = require_pass(paths["validation"])
    test = require_pass(paths["test"])
    b0 = require_pass(paths["b0"])
    ablation = require_pass(paths["ablation"])
    day10 = require_pass(paths["day10_summary"])
    timing = require_pass(paths["timing_summary"])
    collision = require_pass(paths["collision"])
    day13 = require_pass(paths["day13"])
    if validation.get("test_accessed") is not False or test.get("test_used_for_selection") is not False:
        raise ValueError("Offline selection/test separation gate failed")
    if day13.get("test_accessed") is not False or day13.get("selected_architecture_stable") is not True:
        raise ValueError("Day13 sensitivity gate failed")

    results = Results(repo)
    tables: dict[str, list[dict[str, Any]]] = {}

    dataset_rows = []
    for split in ("train", "val", "test"):
        row = {
            "split": split,
            "init_ids": {"train": "1–40", "val": "41–45", "test": "46–50"}[split],
            "rollouts": int(day7["rollouts_by_split"][split]),
            "raw_samples": int(day7["raw_sample_counts"][split]),
            "usable_samples": int(day7["usable_any_label_counts"][split]),
            "full_horizon_samples": int(day7["full_horizon_counts"][split]),
            "partial_horizon_samples": int(day7["partial_horizon_counts"][split]),
        }
        dataset_rows.append(row)
        for metric in ("rollouts", "raw_samples", "usable_samples", "full_horizon_samples"):
            results.add(
                f"R_DATA_{split.upper()}_{slug(metric)}",
                row[metric],
                source=paths["day7"],
                locator=f"/{metric if metric == 'rollouts' else metric.replace('_samples','_counts')}/{split}",
                metric=metric,
                unit="count",
                aggregation_unit="rollout split" if metric == "rollouts" else "prediction window",
            )
    tables["table01_dataset_split_counts.csv"] = dataset_rows

    validation_rows = []
    for run in validation["runs"]:
        all_metrics = run["subsets"]["all"]
        reactive = run["subsets"]["reactive"]
        row = {
            "variant": run["variant"],
            "seed": int(run["seed"]),
            "best_epoch": int(run["training"]["best_epoch"]),
            "validation_macro_nll": float(all_metrics["uncalibrated_rollout_macro_trajectory_NLL_per_step"]),
            "validation_top1_ade_m": float(all_metrics["top1_ADE_mean"]),
            "reactive_top1_ade_m": float(reactive["top1_ADE_mean"]),
            "latency_ms_per_sample": float(all_metrics["mean_prediction_ms_per_sample"]),
        }
        validation_rows.append(row)
        results.add(
            f"R_VAL_{slug(run['variant'])}_S{run['seed']}_MACRO_NLL",
            row["validation_macro_nll"],
            source=paths["validation"],
            locator=f"/runs/{run['variant']}/seed_{run['seed']}/subsets/all/uncalibrated_rollout_macro_trajectory_NLL_per_step",
            metric="validation rollout-macro trajectory mixture NLL per step",
            unit="nats/step",
            aggregation_unit="rollout macro mean over validation split",
        )
    validation_rows.sort(key=lambda row: (row["variant"], row["seed"]))
    tables["table02_validation_5models_3seeds.csv"] = validation_rows

    test_rows = []
    for run in test["runs"]:
        subset = run["subsets"]["all"]
        row = {
            "variant": run["variant"],
            "seed": int(run["seed"]),
            "validation_rank": int(run["validation_rank"]),
            "test_macro_nll": float(subset["uncalibrated_rollout_macro_NLL"]),
            "test_top1_ade_m": float(subset["top1_ADE_mean"]),
            "test_top1_fde_m": float(subset["top1_FDE_mean"]),
            "test_rollouts": int(subset["independent_rollouts"]),
            "test_init_groups": int(subset["independent_init_groups"]),
        }
        test_rows.append(row)
        for metric, unit in (("test_macro_nll", "nats/step"), ("test_top1_ade_m", "m"), ("test_top1_fde_m", "m")):
            results.add(
                f"R_TEST_{slug(run['variant'])}_{slug(metric.replace('test_',''))}",
                row[metric],
                source=paths["test"],
                locator=f"/runs/{run['variant']}/subsets/all/{metric.replace('test_macro_nll','uncalibrated_rollout_macro_NLL').replace('test_top1_ade_m','top1_ADE_mean').replace('test_top1_fde_m','top1_FDE_mean')}",
                metric=metric,
                unit=unit,
                aggregation_unit="rollout-macro over 20 test rollouts" if metric == "test_macro_nll" else "window mean over test split",
                role="frozen_test_reporting",
            )
    b0_all = b0["subsets"]["all"]["B0"]
    test_rows.append(
        {
            "variant": "B0 pretrained control",
            "seed": "n/a",
            "validation_rank": "n/a",
            "test_macro_nll": float(b0_all["uncalibrated_rollout_macro_NLL"]),
            "test_top1_ade_m": float(b0_all["top1_ADE_mean"]),
            "test_top1_fde_m": float(b0_all["top1_FDE_mean"]),
            "test_rollouts": int(b0_all["independent_rollouts"]),
            "test_init_groups": int(b0_all["independent_init_groups"]),
        }
    )
    tables["table03_frozen_test_and_b0_control.csv"] = test_rows
    for metric, value, unit in (
        ("ADE", b0["subsets"]["all"]["contrasts"]["B1_minus_B0_top1_ADE_mean"], "m"),
        ("FDE", b0["subsets"]["all"]["contrasts"]["B1_minus_B0_top1_FDE_mean"], "m"),
        ("MACRO_NLL", b0["subsets"]["all"]["contrasts"]["B1_minus_B0_uncalibrated_rollout_macro_NLL"], "nats/step"),
    ):
        results.add(
            f"R_TEST_B1_MINUS_B0_{metric}",
            float(value),
            source=paths["b0"],
            locator=f"/subsets/all/contrasts/B1_minus_B0_{metric}",
            metric=f"B1 minus B0 {metric}",
            unit=unit,
            aggregation_unit="matched test split; 20 rollouts, 5 init groups",
            role="matched_control",
        )

    calibration_rows = []
    b1_test = next(run for run in test["runs"] if run["variant"] == "B1")
    for model, source_payload, source_path in (
        ("B0", b0["subsets"], paths["b0"]),
        ("B1", {name: {"B1": metrics} for name, metrics in b1_test["subsets"].items()}, paths["test"]),
    ):
        for subset_name in ("all", "response_active"):
            metrics = source_payload[subset_name][model]
            calibration_rows.append(
                {
                    "variant": model,
                    "subset": subset_name,
                    "samples": int(metrics["samples"]),
                    "uncalibrated_macro_nll": float(metrics["uncalibrated_rollout_macro_NLL"]),
                    "calibrated_macro_nll": float(metrics["calibrated_rollout_macro_NLL"]),
                    "uncalibrated_coverage_mae": float(metrics["uncalibrated_coverage_MAE"]),
                    "calibrated_coverage_mae": float(metrics["calibrated_coverage_MAE"]),
                    "top1_ade_m": float(metrics["top1_ADE_mean"]),
                }
            )
    tables["table04_calibration_aggregate_vs_response_tail.csv"] = calibration_rows
    results.add(
        "R_CAL_B1_RESPONSE_ACTIVE_MINUS_B0_CAL_NLL",
        float(b0["subsets"]["response_active"]["contrasts"]["B1_minus_B0_calibrated_rollout_macro_NLL"]),
        source=paths["b0"],
        locator="/subsets/response_active/contrasts/B1_minus_B0_calibrated_rollout_macro_NLL",
        metric="B1 minus B0 calibrated response-active macro NLL",
        unit="nats/step",
        aggregation_unit="6 response-active test rollouts across 3 init groups",
        role="tail_diagnostic",
    )

    for variant in ("T1", "T2"):
        for mode in ("zero", "shuffle"):
            deltas = ablation["variants"][variant]["modes"][mode]["subsets"]["all"]["deltas"]
            for metric_key, metric_label, unit in (
                ("ablated_minus_original_top1_ADE_mean", "ablated minus original top-1 ADE", "m"),
                (
                    "ablated_minus_original_uncalibrated_rollout_macro_NLL",
                    "ablated minus original rollout-macro NLL",
                    "nats/step",
                ),
            ):
                results.add(
                    f"R_ABLATION_{variant}_{mode.upper()}_{'ADE' if metric_key.endswith('ADE_mean') else 'MACRO_NLL'}",
                    float(deltas[metric_key]),
                    source=paths["ablation"],
                    locator=f"/variants/{variant}/modes/{mode}/subsets/all/deltas/{metric_key}",
                    metric=metric_label,
                    unit=unit,
                    aggregation_unit="frozen test split; 20 rollouts, 5 init groups",
                    role="post_selection_mechanistic_diagnostic",
                    filter_rule=f"{variant} interaction context replaced by {mode}",
                )

    day10_rows = []
    for row in read_csv(paths["day10_cells"]):
        compact = {
            "predictor": row["predictor"],
            "risk_policy": row["risk_policy"],
            "target_style": row["target_style"],
            "rollouts": int(row["n_rollouts"]),
            "adjusted_delay_s": float(row["target_clearance_adjusted_completion_delay_s_mean"]),
            "footprint_margin_m": float(row["min_footprint_separation_m_mean"]),
            "solver_failure_fraction": float(row["solver_failure_fraction_mean"]),
            "supervisor_active_fraction": float(row["supervisor_active_fraction_mean"]),
            "observed_collisions": int(float(row["collision_rate"]) * int(row["n_rollouts"])),
            "yield_success_rate": float(row["yield_success_rate"]),
        }
        day10_rows.append(compact)
        cell = f"{slug(row['predictor'])}_{slug(row['target_style'])}_{slug(row['risk_policy'])}"
        for metric, unit in (("adjusted_delay_s", "s"), ("footprint_margin_m", "m")):
            source_column = {
                "adjusted_delay_s": "target_clearance_adjusted_completion_delay_s_mean",
                "footprint_margin_m": "min_footprint_separation_m_mean",
            }[metric]
            results.add(
                f"R_DAY10_{cell}_{slug(metric)}",
                compact[metric],
                source=paths["day10_cells"],
                locator=f"filter: predictor={row['predictor']}; target_style={row['target_style']}; risk_policy={row['risk_policy']}; column={source_column}",
                metric=metric,
                unit=unit,
                aggregation_unit="cell mean over five paired ego-init rollouts",
                filter_rule=f"predictor={row['predictor']}; style={row['target_style']}; risk={row['risk_policy']}",
            )
    tables["table05_day10_predictor_risk_frontier.csv"] = day10_rows
    for key, value in day10["reliability"].items():
        if isinstance(value, (int, float)):
            results.add(
                f"R_DAY10_RELIABILITY_{slug(key)}",
                value,
                source=paths["day10_summary"],
                locator=f"/reliability/{key}",
                metric=key,
                unit="count" if "failure" in key or "collision" in key else "fraction" if "fraction" in key else "m",
                aggregation_unit="80 formal closed-loop rollouts",
            )

    timing_rows = []
    kept_scopes = {
        "synthesis_predictor_pooled_primary",
        "synthesis_policy_pooled_primary",
        "synthesis_predictor_by_offset_primary",
        "synthesis_policy_by_offset_primary",
        "synthesis_offset_primary",
    }
    for row in read_csv(paths["timing_contrasts"]):
        if row["inference_scope"] not in kept_scopes:
            continue
        compact = {
            "scope": row["inference_scope"],
            "contrast": row["contrast"],
            "metric": row["metric"],
            "effect": float(row["left_minus_right_mean"]),
            "ci95_low": float(row["ci95_low"]),
            "ci95_high": float(row["ci95_high"]),
            "exact_p": float(row["exact_init_cluster_sign_flip_p"]),
            "holm_p": float(row["holm_adjusted_p_within_scope"]),
            "independent_init_groups": int(row["independent_init_groups"]),
        }
        timing_rows.append(compact)
        results.add(
            f"R_TIMING_{slug(row['contrast'])}_{slug(row['metric'])}",
            compact["effect"],
            source=paths["timing_contrasts"],
            locator=f"filter: inference_scope={row['inference_scope']}; contrast={row['contrast']}; metric={row['metric']}",
            metric=row["metric"],
            unit="s" if row["metric"].endswith("delay_s") else "m" if row["metric"].endswith("_m") else "fraction",
            aggregation_unit="five ego-init cluster means",
            filter_rule=row["contrast"],
        )
    tables["table06_timing_robustness_key_contrasts.csv"] = timing_rows

    hypotheses = [
        {"hypothesis_id": "H1", "claim": "Task adaptation improves in-distribution prediction relative to pretrained B0.", "evidence_ids": "R_TEST_B1_MINUS_B0_ADE; R_TEST_B1_MINUS_B0_FDE; R_TEST_B1_MINUS_B0_MACRO_NLL", "verdict": "supported", "boundary": "same Town05 give-way distribution"},
        {"hypothesis_id": "H2", "claim": "Explicit interaction-sequence models use the added sequence input.", "evidence_ids": "R_ABLATION_T1_SHUFFLE_MACRO_NLL; R_ABLATION_T2_ZERO_MACRO_NLL; R_ABLATION_T2_SHUFFLE_MACRO_NLL", "verdict": "supported mechanistically", "boundary": "input sensitivity is not causal understanding"},
        {"hypothesis_id": "H3", "claim": "Transformer variants outperform simple B1 adaptation.", "evidence_ids": "R_VAL_B1_S11_MACRO_NLL; R_TEST_B1_MACRO_NLL", "verdict": "refuted", "boundary": "finite controlled dataset and tested architectures"},
        {"hypothesis_id": "H4", "claim": "Better offline prediction produces uniform closed-loop gains.", "evidence_ids": "R_TEST_B1_MINUS_B0_ADE; R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_M3_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S; R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_0_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S", "verdict": "refuted", "boundary": "effects are policy/style/timing conditional"},
        {"hypothesis_id": "H5", "claim": "Adaptive risk universally dominates the fixed-risk frontier.", "evidence_ids": "R_DAY10_B1_REACTIVE_ADAPTIVE_ADJUSTED_DELAY_S; R_DAY10_B1_REACTIVE_FIXED_AGGRESSIVE_ADJUSTED_DELAY_S; R_DAY10_B1_REACTIVE_ADAPTIVE_FOOTPRINT_MARGIN_M; R_DAY10_B1_REACTIVE_FIXED_AGGRESSIVE_FOOTPRINT_MARGIN_M; R_TIMING_ADAPTIVE_MINUS_FIXED_MEDIUM_B1_OFFSET_P3_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S; R_TIMING_ADAPTIVE_MINUS_FIXED_MEDIUM_B1_OFFSET_P3_MIN_FOOTPRINT_SEPARATION_M", "verdict": "refuted", "boundary": "adaptive remains a frontier point, not a universal replacement"},
        {"hypothesis_id": "H6", "claim": "Predictor effects are moderated by risk policy and arrival timing.", "evidence_ids": "R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_M3_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S; R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_0_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S; R_TIMING_B1_MINUS_B0_ADAPTIVE_OFFSET_P3_MIN_FOOTPRINT_SEPARATION_M", "verdict": "descriptively supported", "boundary": "five init groups limit confirmatory power"},
        {"hypothesis_id": "H7", "claim": "Collision-containing training rollouts determine the selected architecture.", "evidence_ids": "R_SENS_SELECTED_ARCHITECTURE_STABLE", "verdict": "refuted", "boundary": "whole-rollout conservative filter"},
        {"hypothesis_id": "H8", "claim": "The frozen deployment chain satisfies the declared reliability gates.", "evidence_ids": "R_DAY10_RELIABILITY_FOOTPRINT_COLLISIONS; R_DAY10_RELIABILITY_YIELD_ORDER_FAILURES", "verdict": "supported for observed runs", "boundary": "zero observed events is not zero population risk"},
    ]
    tables["table07_hypothesis_evidence_verdicts.csv"] = hypotheses

    threats = [
        {"threat_id": "T1", "threat": "Only five independent validation/test init groups", "mitigation": "rollout-macro metrics, init-cluster bootstrap/sign-flip inference", "remaining_boundary": "minimum two-sided exact p=0.0625"},
        {"threat_id": "T2", "threat": "Single CARLA map and controlled give-way geometry", "mitigation": "factorial target style, risk and ±3 m timing shifts", "remaining_boundary": "no cross-map or real-world generalisation claim"},
        {"threat_id": "T3", "threat": "Day6 callback frames lack per-rollout sample-clock anchor", "mitigation": "whole-rollout conservative exclusion and 15-run sensitivity", "remaining_boundary": "exact affected-window fraction remains unidentified"},
        {"threat_id": "T4", "threat": "Supervisor and solver can mask predictor/controller effects", "mitigation": "A3 authority regime plus supervisor/solver mechanism metrics", "remaining_boundary": "closed-loop effect remains a coupled-system property"},
        {"threat_id": "T5", "threat": "Zero observed closed-loop collisions", "mitigation": "report event count and footprint margins separately", "remaining_boundary": "does not estimate zero collision probability"},
        {"threat_id": "T6", "threat": "Global calibration fails in response-active tail", "mitigation": "report aggregate and response-active calibration separately", "remaining_boundary": "tail calibration requires more interaction data"},
        {"threat_id": "T7", "threat": "Nominal and shifted timing batches ran separately", "mitigation": "contract/hash compatibility gate and shared five init groups", "remaining_boundary": "residual batch effect cannot be fully excluded"},
        {"threat_id": "T8", "threat": "Post-hoc filtered sensitivity reuses validation", "mitigation": "original experiment remains primary; no filtered test evaluation", "remaining_boundary": "sensitivity supports robustness, not new model selection"},
    ]
    tables["table08_threats_to_validity.csv"] = threats

    results.add(
        "R_SENS_EXCLUDED_TRAIN_WINDOWS",
        int(day13["filter_counts"]["excluded_train_usable"]),
        source=paths["day13"],
        locator="/filter_counts/excluded_train_usable",
        metric="excluded training windows",
        unit="count",
        aggregation_unit="usable prediction windows",
        role="post_hoc_sensitivity",
    )
    results.add(
        "R_SENS_SELECTED_ARCHITECTURE_STABLE",
        bool(day13["selected_architecture_stable"]),
        source=paths["day13"],
        locator="/selected_architecture_stable",
        metric="validation-selected architecture unchanged after conservative filter",
        unit="boolean",
        aggregation_unit="matched 5-variant x 3-seed validation matrix",
        role="post_hoc_sensitivity",
    )
    results.add(
        "R_COLLISION_CALLBACK_EPISODES",
        int(collision["totals"]["contact_episodes"]),
        source=paths["collision"],
        locator="/totals/contact_episodes",
        metric="target-infrastructure contact episodes",
        unit="count",
        aggregation_unit="200 Day6 rollouts",
        role="data_quality_audit",
    )
    results.add(
        "R_TIMING_OBSERVED_COLLISIONS",
        int(timing["safety_gate"]["collisions"]),
        source=paths["timing_summary"],
        locator="/safety_gate/collisions",
        metric="observed footprint collisions",
        unit="count",
        aggregation_unit="120 Day10+Day11 formal rollouts",
    )

    output.mkdir(parents=True, exist_ok=True)
    for filename, rows in tables.items():
        write_csv(output / filename, rows)
    manifest = {
        "schema_version": "ucl_thesis_paper_results_manifest_v1",
        "status": "pass",
        "result_count": len(results.records),
        "table_count": len(tables),
        "source_files": results.source_hashes,
        "results": results.records,
        "table_files": sorted(tables),
        "rules": [
            "Every numeric thesis claim must cite a stable result ID or a canonical table row.",
            "Original Day8/frozen test and Day10/Day11 remain primary; Day13 is post-hoc sensitivity only.",
            "Inference uses five ego-init clusters, never simulator steps as independent samples.",
            "Zero collision values are observed counts, not population-risk estimates.",
        ],
    }
    manifest_path = output / "paper_results_manifest.json"
    atomic_json(manifest_path, manifest)
    sections = [
        "# Canonical thesis tables",
        "",
        "> Generated from `paper_results_manifest.json`; do not edit values manually.",
    ]
    for index, (filename, rows) in enumerate(tables.items(), 1):
        sections.extend(("", f"## Table {index}: {filename}", "", markdown_table(rows)))
    (output / "paper_tables.md").write_text("\n".join(sections) + "\n", encoding="utf-8")
    completion = {
        "schema_version": "paper_tables_complete_v1",
        "status": "pass",
        "result_count": len(results.records),
        "table_count": len(tables),
        "manifest_sha256": sha256(manifest_path),
    }
    atomic_json(output / "PAPER_TABLES_COMPLETE.json", completion)
    return completion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output_dir or repo / "docs/paper/generated/paper_assets_v1").resolve()
    result = build(repo, output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
