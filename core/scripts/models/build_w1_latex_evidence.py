#!/usr/bin/env python3
"""Build W1 dissertation tables from canonical frozen evidence.

This is a presentation-only transformation.  It never edits experiment
outputs and deliberately refuses incomplete/malformed evidence packages.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "docs/paper/generated/distinction_v1/11_w1_manuscript"

SOURCES = {
    "validation": REPO_ROOT / "docs/paper/generated/day8/final_validation/day8_validation_summary.json",
    "test": REPO_ROOT / "docs/paper/generated/day8/final_test/day8_frozen_test_summary.json",
    "b0": REPO_ROOT / "docs/paper/generated/day10/gaps/b0_offline/b0_frozen_offline_summary.json",
    "capacity": REPO_ROOT / "docs/paper/generated/distinction_v1/03_training_budget/model_capacity_training_budget_audit.json",
    "context": REPO_ROOT / "docs/paper/generated/day10/gaps/context_ablation/interaction_context_ablation_summary.json",
    "b1_inputs": REPO_ROOT / "docs/paper/generated/distinction_v1/02_input_ablations/b1_input_condition_summary.csv",
    "h3": REPO_ROOT / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h3_contrasts.csv",
    "h4": REPO_ROOT / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h4_contrasts.csv",
    "h4_dominance": REPO_ROOT / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h4_dominance.csv",
    "m1": REPO_ROOT / "docs/paper/generated/distinction_v1/10_four_hypothesis_evidence/M1_COMPLETE.json",
    "a2": REPO_ROOT / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis/A2_COMPLETE.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def tex(value: object) -> str:
    text = str(value)
    for old, new in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
    ):
        text = text.replace(old, new)
    return text


def f(value: object, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def signed(value: object, digits: int = 3) -> str:
    return f"{float(value):+.{digits}f}"


def write(name: str, lines: Iterable[str]) -> Path:
    path = OUT_DIR / name
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def validation_table(validation: Dict[str, Any]) -> Path:
    runs = validation["runs"]
    if validation.get("status", "pass") != "pass" or len(runs) != 15:
        raise ValueError("Day8 validation evidence must contain 15 complete runs")
    order = {name: index for index, name in enumerate(("B1", "B2-M", "B2-D", "T1", "T2"))}
    runs = sorted(runs, key=lambda row: (order[row["variant"]], row["seed"]))
    lines = [
        r"\begin{table}[p]",
        r"\centering\scriptsize",
        r"\caption{All validation runs used for frozen model selection. NLL is uncalibrated rollout-macro trajectory NLL per step.}",
        r"\label{tab:app-validation}",
        r"\begin{tabular}{@{}llrrrrrr@{}}",
        r"\toprule",
        r"Variant & Seed & Epoch & Trainable & NLL & ADE & FDE & ms/sample \\",
        r"\midrule",
    ]
    for row in runs:
        all_metrics = row["subsets"]["all"]
        training = row["training"]
        lines.append(
            f"{tex(row['variant'])} & {row['seed']} & {training['best_epoch']} & "
            f"{training['parameters']['trainable_parameters']:,} & "
            f"{f(all_metrics['uncalibrated_rollout_macro_trajectory_NLL_per_step'])} & "
            f"{f(all_metrics['top1_ADE_mean'])} & {f(all_metrics['top1_FDE_mean'])} & "
            f"{f(all_metrics['mean_prediction_ms_per_sample'], 2)} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return write("w1_validation_runs.tex", lines)


def frozen_test_table(test: Dict[str, Any], b0: Dict[str, Any]) -> Path:
    runs = test["runs"]
    if len(runs) != 5 or test.get("retraining_or_retuning_after_test_permitted") is not False:
        raise ValueError("Frozen test evidence is incomplete or permits post-test tuning")
    rows: List[Dict[str, Any]] = [{
        "variant": "B0",
        "seed": "--",
        "rank": "control",
        "metrics": b0["subsets"]["all"]["B0"],
    }]
    rows.extend({
        "variant": run["variant"],
        "seed": run["seed"],
        "rank": run["validation_rank"],
        "metrics": run["subsets"]["all"],
    } for run in sorted(runs, key=lambda row: row["validation_rank"]))
    lines = [
        r"\begin{table}[h]",
        r"\centering\small",
        r"\caption{One-shot frozen-test results. Calibration was fitted on validation and was not used for architecture ranking.}",
        r"\label{tab:app-test}",
        r"\begin{tabular}{@{}llrrrrrr@{}}",
        r"\toprule",
        r"Variant & Seed & Val. rank & NLL & ADE & FDE & Cal. NLL & ms/sample \\",
        r"\midrule",
    ]
    for row in rows:
        metrics = row["metrics"]
        uncal_nll = metrics.get("uncalibrated_rollout_macro_NLL")
        cal_nll = metrics.get("calibrated_rollout_macro_NLL")
        lines.append(
            f"{tex(row['variant'])} & {row['seed']} & {row['rank']} & {f(uncal_nll)} & "
            f"{f(metrics['top1_ADE_mean'])} & {f(metrics['top1_FDE_mean'])} & "
            f"{f(cal_nll)} & {f(metrics['mean_prediction_ms_per_sample'], 2)} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return write("w1_frozen_test.tex", lines)


def contrast_table(name: str, caption: str, label: str, rows: List[Dict[str, str]]) -> Path:
    if not rows:
        raise ValueError(f"No rows for {name}")
    lines = [
        r"\begin{table}[p]",
        r"\centering\scriptsize",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        r"\begin{tabular}{@{}L{0.25\linewidth}llrL{0.15\linewidth}rrr@{}}",
        r"\toprule",
        r"Contrast & Metric & Style & Effect & 95\% CI & $p$ & $p_{\mathrm{Holm}}$ & $n$ \\",
        r"\midrule",
    ]
    metric_names = {
        "ego_route_completion_duration_s": r"Completion (s)",
        "minimum_footprint_separation_m": r"Separation (m)",
    }
    for row in rows:
        raw_contrast = row["contrast_id"]
        if raw_contrast.startswith("H3_B1_minus_B0_"):
            policy = raw_contrast.removeprefix("H3_B1_minus_B0_").removesuffix(
                f"_{row['target_style']}"
            )
            contrast = f"B1--B0, {policy.replace('_', '-')}"
        else:
            contrast = raw_contrast.removeprefix("H4_").replace(
                f"_{row['target_style']}_adaptive_minus_", ": adaptive vs "
            ).replace("_", "-")
        ci = f"[{signed(row['bootstrap_mean_ci_lower'])}, {signed(row['bootstrap_mean_ci_upper'])}]"
        lines.append(
            f"{tex(contrast)} & {metric_names[row['metric']]} & {tex(row['target_style'])} & "
            f"{signed(row['mean_effect'])} & {ci} & {f(row['exact_sign_flip_p_raw'], 4)} & "
            f"{f(row['holm_adjusted_p'], 4)} & {row['complete_clusters']} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return write(name, lines)


def dominance_table(rows: List[Dict[str, str]]) -> Path:
    if len(rows) != 12:
        raise ValueError("H4 dominance table must contain 12 prespecified comparisons")
    lines = [
        r"\begin{table}[h]",
        r"\centering\small",
        r"\caption{Registered H4 dominance decisions. Effects are adaptive minus fixed; lower completion and higher separation are preferred.}",
        r"\label{tab:app-h4-dominance}",
        r"\begin{tabular}{@{}llllrrl@{}}",
        r"\toprule",
        r"Predictor & Style & Fixed comparator & $\Delta t$ (s) & $\Delta d$ (m) & Binary guards & Decision \\",
        r"\midrule",
    ]
    for row in rows:
        decision = "Dominates" if row["dominance_status"] == "dominates" else "Does not dominate"
        guards = "pass" if row["no_excess_binary_failures"] == "1" else "fail"
        lines.append(
            f"{row['predictor']} & {tex(row['target_style'])} & {tex(row['fixed_comparator'])} & "
            f"{signed(row['mean_adaptive_minus_fixed_completion_s'])} & "
            f"{signed(row['mean_adaptive_minus_fixed_separation_m'], 4)} & {guards} & {decision} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return write("w1_r3_h4_dominance.tex", lines)


def diagnostic_tables(context: Dict[str, Any], b1_rows: List[Dict[str, str]], b0: Dict[str, Any]) -> Path:
    if context.get("status") != "pass" or set(context["variants"]) != {"T1", "T2"}:
        raise ValueError("Transformer context-ablation package is incomplete")
    lines = [
        r"\begin{table}[h]",
        r"\centering\small",
        r"\caption{Post-selection sequence ablations on the frozen test set. Positive deltas mean ablation worsened the metric.}",
        r"\label{tab:app-sequence-ablation}",
        r"\begin{tabular}{@{}llrrr@{}}",
        r"\toprule",
        r"Variant & Ablation & $\Delta$NLL & $\Delta$ADE (m) & $\Delta$FDE (m) \\",
        r"\midrule",
    ]
    for variant in ("T1", "T2"):
        for mode in ("zero", "shuffle"):
            delta = context["variants"][variant]["modes"][mode]["subsets"]["all"]["deltas"]
            lines.append(
                f"{variant} & {mode} & {signed(delta['ablated_minus_original_uncalibrated_rollout_macro_NLL'])} & "
                f"{signed(delta['ablated_minus_original_top1_ADE_mean'])} & "
                f"{signed(delta['ablated_minus_original_top1_FDE_mean'])} \\\\"
            )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}", ""))

    selected = [row for row in b1_rows if row["condition"].startswith(("raster_shuffle", "past_shuffle"))]
    if len(selected) != 6:
        raise ValueError("Expected three raster and three history shuffle diagnostics")
    lines.extend((
        r"\begin{table}[h]",
        r"\centering\small",
        r"\caption{B1 input-shuffle diagnostics across three deterministic mappings.}",
        r"\label{tab:app-b1-inputs}",
        r"\begin{tabular}{@{}llrrr@{}}",
        r"\toprule",
        r"Input & Mapping seed & $\Delta$NLL & $\Delta$ADE (m) & Active-tail $\Delta$ADE (m) \\",
        r"\midrule",
    ))
    for row in selected:
        kind = "Raster" if row["condition"].startswith("raster") else "Target history"
        lines.append(
            f"{kind} & {row['diagnostic_seed']} & "
            f"{signed(row['delta_vs_original__all_uncalibrated_rollout_macro_NLL'])} & "
            f"{signed(row['delta_vs_original__all_top1_ADE_m'], 5)} & "
            f"{signed(row['delta_vs_original__response_active_top1_ADE_m'])} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}", ""))

    lines.extend((
        r"\begin{table}[h]",
        r"\centering\small",
        r"\caption{Aggregate and response-active calibration diagnostic for the frozen B0/B1 test stacks. The active tail has 15 windows from six rollouts and three initialisation groups.}",
        r"\label{tab:app-calibration-tail}",
        r"\begin{tabular}{@{}lllrrrr@{}}",
        r"\toprule",
        r"Subset & Stack & Windows & Rollouts & Init groups & Cal. NLL & Coverage MAE \\",
        r"\midrule",
    ))
    for subset in ("all", "response_active"):
        for stack in ("B0", "B1"):
            row = b0["subsets"][subset][stack]
            lines.append(
                f"{tex(subset)} & {stack} & {row['samples']} & {row['independent_rollouts']} & "
                f"{row['independent_init_groups']} & {f(row['calibrated_rollout_macro_NLL'])} & "
                f"{f(row['calibrated_coverage_MAE'])} \\\\"
            )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return write("w1_diagnostics.tex", lines)


def main() -> None:
    global REPO_ROOT, OUT_DIR, SOURCES

    parser = argparse.ArgumentParser(
        description=(
            "Regenerate the W1 LaTeX evidence tables from the canonical frozen "
            "offline and corrected-R3 evidence. This is presentation-only and "
            "does not rerun an experiment."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: inferred from this script).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Output directory (default: "
            "docs/paper/generated/distinction_v1/11_w1_manuscript under repo root)."
        ),
    )
    args = parser.parse_args()

    REPO_ROOT = args.repo_root.resolve()
    OUT_DIR = (
        args.output.resolve()
        if args.output
        else REPO_ROOT / "docs/paper/generated/distinction_v1/11_w1_manuscript"
    )
    SOURCES = {
        "validation": REPO_ROOT / "docs/paper/generated/day8/final_validation/day8_validation_summary.json",
        "test": REPO_ROOT / "docs/paper/generated/day8/final_test/day8_frozen_test_summary.json",
        "b0": REPO_ROOT / "docs/paper/generated/day10/gaps/b0_offline/b0_frozen_offline_summary.json",
        "capacity": REPO_ROOT / "docs/paper/generated/distinction_v1/03_training_budget/model_capacity_training_budget_audit.json",
        "context": REPO_ROOT / "docs/paper/generated/day10/gaps/context_ablation/interaction_context_ablation_summary.json",
        "b1_inputs": REPO_ROOT / "docs/paper/generated/distinction_v1/02_input_ablations/b1_input_condition_summary.csv",
        "h3": REPO_ROOT / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h3_contrasts.csv",
        "h4": REPO_ROOT / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h4_contrasts.csv",
        "h4_dominance": REPO_ROOT / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h4_dominance.csv",
        "m1": REPO_ROOT / "docs/paper/generated/distinction_v1/10_four_hypothesis_evidence/M1_COMPLETE.json",
        "a2": REPO_ROOT / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis/A2_COMPLETE.json",
    }

    missing = [str(path) for path in SOURCES.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing canonical sources:\n" + "\n".join(missing))

    validation = load_json(SOURCES["validation"])
    test = load_json(SOURCES["test"])
    b0 = load_json(SOURCES["b0"])
    context = load_json(SOURCES["context"])
    m1 = load_json(SOURCES["m1"])
    a2 = load_json(SOURCES["a2"])
    if m1.get("status") != "pass" or m1.get("record_count") != 82:
        raise ValueError("M1 evidence package has not passed its 82-record audit")
    if a2.get("status") != "pass" or a2.get("r3_rollouts") != 80:
        raise ValueError("A2 evidence package is not the complete 80-rollout synthesis")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = [
        validation_table(validation),
        frozen_test_table(test, b0),
        contrast_table(
            "w1_r3_h3_contrasts.tex",
            "All corrected R3 H3 metric contrasts. Effects are B1 minus B0; intervals are deterministic cluster-bootstrap descriptions and tests use five paired initialisation groups.",
            "tab:app-h3-contrasts",
            load_csv(SOURCES["h3"]),
        ),
        contrast_table(
            "w1_r3_h4_contrasts.tex",
            "All corrected R3 H4 metric contrasts. Effects are adaptive minus fixed; Holm adjustment is within each registered three-comparator predictor--style family.",
            "tab:app-h4-contrasts",
            load_csv(SOURCES["h4"]),
        ),
        dominance_table(load_csv(SOURCES["h4_dominance"])),
        diagnostic_tables(context, load_csv(SOURCES["b1_inputs"]), b0),
    ]

    completion = {
        "schema_version": "w1_latex_evidence_v1",
        "status": "pass",
        "role": "presentation_only_no_experiment_recomputation",
        "source_sha256": {
            str(path.relative_to(REPO_ROOT)): sha256(path)
            for path in SOURCES.values()
        },
        "artifacts": {
            path.name: sha256(path)
            for path in outputs
        },
        "validated_counts": {
            "validation_runs": 15,
            "frozen_trainable_test_variants": 5,
            "h3_metric_contrasts": 16,
            "h4_metric_contrasts": 24,
            "h4_dominance_comparisons": 12,
            "m1_records": 82,
            "r3_rollouts": 80,
        },
    }
    write("W1_EVIDENCE_TABLES_COMPLETE.json", [json.dumps(completion, indent=2, sort_keys=True)])
    print(f"Wrote {len(outputs)} LaTeX evidence files to {OUT_DIR}")


if __name__ == "__main__":
    main()
