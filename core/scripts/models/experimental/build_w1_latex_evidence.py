#!/usr/bin/env python3
"""Build W1 dissertation tables from canonical frozen evidence.

This is a presentation-only transformation.  It never edits experiment
outputs and deliberately refuses incomplete/malformed evidence packages.
"""

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
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from .frozen_prediction_evidence import (
        frozen_test_evaluation_paths,
        frozen_test_rollout_records,
        frozen_validation_evaluation_paths,
        frozen_validation_rollout_records,
    )
except ImportError:  # direct script execution
    from frozen_prediction_evidence import (
        frozen_test_evaluation_paths,
        frozen_test_rollout_records,
        frozen_validation_evaluation_paths,
        frozen_validation_rollout_records,
    )

try:
    from .build_m1_evidence_package import (
        CLOSURE_FINAL,
        CLOSURE_MODES,
        CLOSURE_PRE_SF4,
        audit_supervisor_feedback_closure,
    )
except ImportError:  # direct script execution
    from build_m1_evidence_package import (
        CLOSURE_FINAL,
        CLOSURE_MODES,
        CLOSURE_PRE_SF4,
        audit_supervisor_feedback_closure,
    )


REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "docs/paper/generated/distinction_v1/11_w1_manuscript"


def source_paths(repo: Path) -> Dict[str, Path]:
    sources = {
        "validation": repo / "docs/paper/generated/day8/final_validation/day8_validation_summary.json",
        "test": repo / "docs/paper/generated/day8/final_test/day8_frozen_test_summary.json",
        "b0": repo / "docs/paper/generated/day10/gaps/b0_offline/b0_frozen_offline_summary.json",
        "finetune_complete": repo / "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/SUPERVISOR_COMMENT_3_COMPLETE.json",
        "finetune_rollout_tex": repo / "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/finetune_b0_b1_rollout_macro.tex",
        "finetune_paired_tex": repo / "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/finetune_b0_b1_paired_init_effects.tex",
        "capacity": repo / "docs/paper/generated/distinction_v1/03_training_budget/model_capacity_training_budget_audit.json",
        "context": repo / "docs/paper/generated/day10/gaps/context_ablation/interaction_context_ablation_summary.json",
        "b1_inputs": repo / "docs/paper/generated/distinction_v1/02_input_ablations/b1_input_condition_summary.csv",
        "h3": repo / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h3_contrasts.csv",
        "h4": repo / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h4_contrasts.csv",
        "h4_dominance": repo / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/analysis/r3_h4_dominance.csv",
        "m1": repo / "docs/paper/generated/distinction_v1/10_four_hypothesis_evidence/M1_COMPLETE.json",
        "m1_manifest": repo / "docs/paper/generated/distinction_v1/10_four_hypothesis_evidence/M1_EVIDENCE_MANIFEST.json",
        "m1_audit": repo / "docs/paper/generated/distinction_v1/10_four_hypothesis_evidence/M1_VALUE_AUDIT.json",
        "a2": repo / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis/A2_COMPLETE.json",
    }
    sources.update(
        {f"test_eval_{variant}": path for variant, path in frozen_test_evaluation_paths(repo).items()}
    )
    sources.update(
        {
            f"validation_eval_{variant}_seed_{seed}": path
            for (variant, seed), path in frozen_validation_evaluation_paths(repo).items()
        }
    )
    return sources


SOURCES = source_paths(REPO_ROOT)


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


def validation_table(runs: List[Dict[str, Any]]) -> Path:
    if len(runs) != 15 or any(row["aggregation_level"] != "rollout_macro" for row in runs):
        raise ValueError("Day8 validation evidence must contain 15 rollout-macro runs")
    lines = [
        r"\begin{table}[p]",
        r"\centering\scriptsize",
        r"\caption{All validation runs used for frozen model selection. NLL, ADE and FDE are uncalibrated rollout-macro metrics: each is averaged within rollout and then equally across rollouts.}",
        r"\label{tab:app-validation}",
        r"\begin{tabular}{@{}llrrrrrr@{}}",
        r"\toprule",
        r"Variant & Seed & Epoch & Trainable & NLL & ADE & FDE & ms/sample \\",
        r"\midrule",
    ]
    for row in runs:
        lines.append(
            f"{tex(row['variant'])} & {row['seed']} & {row['best_epoch']} & "
            f"{row['trainable_parameters']:,} & "
            f"{f(row['uncalibrated_rollout_macro_NLL'])} & "
            f"{f(row['rollout_macro_top1_ADE_m'])} & "
            f"{f(row['rollout_macro_top1_FDE_m'])} & "
            f"{f(row['mean_prediction_ms_per_sample'], 2)} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return write("w1_validation_runs.tex", lines)


def frozen_test_table(rows: List[Dict[str, Any]]) -> Path:
    if len(rows) != 6 or any(row["aggregation_level"] != "rollout_macro" for row in rows):
        raise ValueError("Frozen test evidence must contain B0 plus five rollout-macro variants")
    lines = [
        r"\begin{table}[h]",
        r"\centering\small",
        r"\caption{One-shot frozen-test results at one common rollout-macro aggregation. NLL, ADE and FDE are first averaged within rollout and then equally across 20 rollouts. Calibration was fitted on validation and was not used for architecture ranking; 315 overlapping windows are not independent replications.}",
        r"\label{tab:app-test}",
        r"\begin{tabular}{@{}llrrrrrr@{}}",
        r"\toprule",
        r"Variant & Seed & Val. rank & NLL & ADE & FDE & Cal. NLL & ms/sample \\",
        r"\midrule",
    ]
    for row in rows:
        rank = "control" if row["variant"] == "B0" else row["validation_rank"]
        seed = "--" if row["seed"] is None else row["seed"]
        lines.append(
            f"{tex(row['variant'])} & {seed} & {rank} & "
            f"{f(row['uncalibrated_rollout_macro_NLL'])} & "
            f"{f(row['rollout_macro_top1_ADE_m'])} & "
            f"{f(row['rollout_macro_top1_FDE_m'])} & "
            f"{f(row['calibrated_rollout_macro_NLL'])} & "
            f"{f(row['mean_prediction_ms_per_sample'], 2)} \\\\"
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


def build(
    repo: Path,
    output: Path,
    *,
    closure_mode: str = CLOSURE_FINAL,
    supervisor_feedback_root: Path | None = None,
    sf4_results_root: Path | None = None,
) -> Dict[str, Any]:
    if closure_mode not in CLOSURE_MODES:
        raise ValueError(f"Unknown supervisor-feedback closure mode: {closure_mode}")
    global REPO_ROOT, OUT_DIR, SOURCES
    REPO_ROOT = repo.resolve()
    OUT_DIR = output.resolve()
    SOURCES = source_paths(REPO_ROOT)

    missing = [str(path) for path in SOURCES.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing canonical sources:\n" + "\n".join(missing))

    validation = load_json(SOURCES["validation"])
    test = load_json(SOURCES["test"])
    b0 = load_json(SOURCES["b0"])
    context = load_json(SOURCES["context"])
    finetune = load_json(SOURCES["finetune_complete"])
    m1 = load_json(SOURCES["m1"])
    m1_manifest = load_json(SOURCES["m1_manifest"])
    m1_audit = load_json(SOURCES["m1_audit"])
    a2 = load_json(SOURCES["a2"])
    expected_m1_status = (
        "partial_pre_sf4" if closure_mode == CLOSURE_PRE_SF4 else "pass"
    )
    if (
        m1.get("status") != expected_m1_status
        or m1.get("value_audit_status") != "pass"
        or m1.get("closure_mode") != closure_mode
        or m1_audit.get("status") != "pass"
        or m1_manifest.get("status") != expected_m1_status
        or m1_manifest.get("value_audit_status") != "pass"
        or m1_manifest.get("closure_mode") != closure_mode
        or m1.get("record_count") != m1_manifest.get("record_count")
        or m1.get("record_count") != m1_audit.get("record_count")
        or m1.get("aggregation_semantic_violations") != []
    ):
        raise ValueError("M1 evidence package has not passed its value/aggregation audit")
    closure = audit_supervisor_feedback_closure(
        REPO_ROOT,
        supervisor_feedback_root=supervisor_feedback_root,
        sf4_results_root=sf4_results_root,
    )
    if closure_mode == CLOSURE_FINAL and closure.get("status") != "pass":
        raise ValueError("Supervisor-feedback final closure gate has not passed")
    required_h1 = {
        "H1_B1_TEST_NLL",
        "H1_B0_TEST_NLL",
        "H1_B1_MINUS_B0_TEST_NLL",
        "H1_B1_TEST_ADE",
        "H1_B0_TEST_ADE",
        "H1_B1_MINUS_B0_TEST_ADE",
        "H1_B1_TEST_FDE",
        "H1_B0_TEST_FDE",
        "H1_B1_MINUS_B0_TEST_FDE",
    }
    h1_records = {
        row["evidence_id"]: row
        for row in m1_manifest["records"]
        if row["evidence_id"] in required_h1
    }
    if set(h1_records) != required_h1 or any(
        not row["aggregation_unit"].startswith("rollout-macro")
        for row in h1_records.values()
    ):
        raise ValueError("M1 H1 rollout-macro evidence is incomplete")
    if (
        finetune.get("status") != "pass"
        or finetune.get("overlapping_windows_treated_as_independent") is not False
        or finetune.get("old_percentage_accuracy_hit_count") != 0
    ):
        raise ValueError("Supervisor fine-tuning audit is not complete")
    for source_key in ("finetune_rollout_tex", "finetune_paired_tex"):
        name = SOURCES[source_key].name
        if finetune.get("artifacts", {}).get(name) != sha256(SOURCES[source_key]):
            raise ValueError(f"Fine-tuning LaTeX artifact hash mismatch: {name}")
    if a2.get("status") != "pass" or a2.get("r3_rollouts") != 80:
        raise ValueError("A2 evidence package is not the complete 80-rollout synthesis")
    validation_rollout_records = frozen_validation_rollout_records(REPO_ROOT, validation)
    test_rollout_records = frozen_test_rollout_records(REPO_ROOT, test, b0)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = [
        validation_table(validation_rollout_records),
        frozen_test_table(test_rollout_records),
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
        "status": (
            "partial_pre_sf4" if closure_mode == CLOSURE_PRE_SF4 else "pass"
        ),
        "closure_mode": closure_mode,
        "value_evidence_ready": True,
        "supervisor_feedback_closure_status": closure["status"],
        "supervisor_feedback_closure_checks": closure["checks"],
        "final_release_eligible": (
            closure_mode == CLOSURE_FINAL and closure["status"] == "pass"
        ),
        "role": "presentation_only_no_experiment_recomputation",
        "aggregation_contract": (
            "All displayed offline NLL/ADE/FDE values are read from each frozen "
            "evaluation's rollout_aggregation.macro_mean object."
        ),
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
            "m1_records": int(m1["record_count"]),
            "r3_rollouts": 80,
        },
    }
    write("W1_EVIDENCE_TABLES_COMPLETE.json", [json.dumps(completion, indent=2, sort_keys=True)])
    return completion


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate the W1 LaTeX evidence tables from the canonical frozen "
            "offline and corrected-R3 evidence. This is presentation-only and "
            "does not rerun an experiment."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--closure-mode",
        choices=CLOSURE_MODES,
        default=CLOSURE_FINAL,
        help=(
            "Default final mode requires all SF1--SF4 gates. pre-sf4 emits "
            "partial tables and can never emit pass."
        ),
    )
    parser.add_argument("--supervisor-feedback-root", type=Path)
    parser.add_argument("--sf4-results-root", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (
        args.output.resolve()
        if args.output
        else repo / "docs/paper/generated/distinction_v1/11_w1_manuscript"
    )
    completion = build(
        repo,
        output,
        closure_mode=args.closure_mode,
        supervisor_feedback_root=args.supervisor_feedback_root,
        sf4_results_root=args.sf4_results_root,
    )
    print(json.dumps(completion, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
