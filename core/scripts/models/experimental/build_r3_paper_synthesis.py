#!/usr/bin/env python3
"""Build the post-R3, paper-ready A2 synthesis from frozen server evidence."""

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
import html
import json
import os
from pathlib import Path
from typing import Any


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


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def require_pass(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if payload.get("status") != "pass":
        raise ValueError(f"Required R3 gate did not pass: {path}")
    return payload


def f(value: str) -> float:
    return float(value)


def i(value: str) -> int:
    return int(value)


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def svg_h3(rows: list[dict[str, Any]]) -> str:
    width, height = 1180, 620
    x0, y0, cell_w, cell_h = 300, 130, 205, 92
    policies = ["fixed_aggressive", "fixed_medium", "fixed_conservative", "adaptive"]
    styles = ["assertive", "reactive"]
    lookup = {(row["risk_policy"], row["target_style"]): row for row in rows}
    items = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#17212b}.title{font-size:25px;font-weight:700}.sub{font-size:14px;fill:#5b6773}.head{font-size:14px;font-weight:700}.val{font-size:13px}.small{font-size:12px;fill:#5b6773}</style>',
        '<text x="50" y="42" class="title">H3: prediction gains translate conditionally to closed-loop outcomes</text>',
        '<text x="50" y="69" class="sub">B1 minus B0; desirable quadrant is faster completion (negative) and no-worse separation (non-negative).</text>',
    ]
    for col, policy in enumerate(policies):
        label = policy.replace("fixed_", "fixed ").replace("_", " ")
        items.append(f'<text x="{x0 + col * cell_w + cell_w / 2:.1f}" y="108" text-anchor="middle" class="head">{esc(label)}</text>')
    for row_index, style in enumerate(styles):
        y = y0 + row_index * cell_h
        items.append(f'<text x="270" y="{y + 47}" text-anchor="end" class="head">{style}</text>')
        for col, policy in enumerate(policies):
            row = lookup[(policy, style)]
            supported = row["cell_support_status"] == "supported_directionally"
            fill = "#dff3e8" if supported else "#f7e4e4"
            stroke = "#17845b" if supported else "#c44e52"
            x = x0 + col * cell_w
            items.append(f'<rect x="{x + 5}" y="{y + 5}" width="{cell_w - 10}" height="{cell_h - 10}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
            items.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + 34}" text-anchor="middle" class="val">Δ time {f(row["mean_completion_effect_s"]):+.2f} s</text>')
            items.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + 56}" text-anchor="middle" class="val">Δ separation {f(row["mean_separation_effect_m"]):+.4f} m</text>')
            verdict = "supports both" if supported else "does not support both"
            items.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + 76}" text-anchor="middle" class="small">{verdict}</text>')
    items.extend([
        '<rect x="300" y="355" width="28" height="18" rx="3" fill="#dff3e8" stroke="#17845b"/><text x="338" y="369" class="small">directionally supports H3 cell criterion</text>',
        '<rect x="620" y="355" width="28" height="18" rx="3" fill="#f7e4e4" stroke="#c44e52"/><text x="658" y="369" class="small">does not jointly support both outcomes</text>',
        '<text x="50" y="432" class="head">Result: 2/8 cells support the prespecified direction; H3 is not supported as a universal closed-loop claim.</text>',
        '<text x="50" y="462" class="sub">All cells have five complete paired init groups. Holm-adjusted p-values are non-confirmatory; effects are reported as bounded descriptive evidence.</text>',
        '<text x="50" y="505" class="sub">Safety guard outcomes cannot discriminate treatments here: 0 native collisions, 0 footprint collisions, 0 yield failures and 0 completion failures in every arm.</text>',
        '<text x="50" y="558" class="small">Source: frozen formal closed-loop analysis (80 rollouts, init groups 101–105, Town05 give-way condition).</text>',
        '</svg>',
    ])
    return "\n".join(items) + "\n"


def svg_h4(rows: list[dict[str, Any]]) -> str:
    width, height = 1180, 690
    predictors = ["B0", "B1"]
    styles = ["assertive", "reactive"]
    comparators = ["fixed_aggressive", "fixed_medium", "fixed_conservative"]
    lookup = {(row["predictor"], row["target_style"], row["fixed_comparator"]): row for row in rows}
    items = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#17212b}.title{font-size:25px;font-weight:700}.sub{font-size:14px;fill:#5b6773}.head{font-size:14px;font-weight:700}.val{font-size:12.5px}.small{font-size:12px;fill:#5b6773}</style>',
        '<text x="50" y="42" class="title">H4: adaptive risk does not universally dominate fixed risk</text>',
        '<text x="50" y="69" class="sub">Adaptive minus fixed; dominance requires no-worse completion, no-worse separation, at least one strict improvement and no excess failures.</text>',
    ]
    x0, y0, cell_w, cell_h = 360, 125, 245, 92
    for col, comparator in enumerate(comparators):
        label = comparator.replace("fixed_", "fixed ")
        items.append(f'<text x="{x0 + col * cell_w + cell_w / 2:.1f}" y="105" text-anchor="middle" class="head">vs {label}</text>')
    row_index = 0
    for predictor in predictors:
        for style in styles:
            y = y0 + row_index * cell_h
            items.append(f'<text x="325" y="{y + 47}" text-anchor="end" class="head">{predictor} · {style}</text>')
            for col, comparator in enumerate(comparators):
                row = lookup[(predictor, style, comparator)]
                dominates = row["dominance_status"] == "dominates"
                fill = "#dff3e8" if dominates else "#f3f6f8"
                stroke = "#17845b" if dominates else "#aab4be"
                x = x0 + col * cell_w
                items.append(f'<rect x="{x + 5}" y="{y + 5}" width="{cell_w - 10}" height="{cell_h - 10}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
                items.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + 32}" text-anchor="middle" class="val">Δ time {f(row["mean_adaptive_minus_fixed_completion_s"]):+.2f} s</text>')
                items.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + 53}" text-anchor="middle" class="val">Δ separation {f(row["mean_adaptive_minus_fixed_separation_m"]):+.4f} m</text>')
                items.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + 74}" text-anchor="middle" class="small">{"dominates" if dominates else "does not dominate"}</text>')
            row_index += 1
    items.extend([
        '<text x="50" y="535" class="head">Result: adaptive dominates in 3/12 prespecified cells; H4 universal dominance is rejected.</text>',
        '<text x="50" y="565" class="sub">The pattern changes with predictor, target style and fixed comparator, supporting a coupled-system rather than component-only interpretation.</text>',
        '<text x="50" y="610" class="sub">All Holm-adjusted p-values are non-confirmatory. Dominance is a prespecified empirical Pareto rule, not an equivalence test.</text>',
        '<text x="50" y="658" class="small">Source: frozen formal closed-loop analysis (80 rollouts, five paired init groups per contrast).</text>',
        '</svg>',
    ])
    return "\n".join(items) + "\n"


def build(repo: Path, r3_root: Path, output: Path) -> dict[str, Any]:
    analysis = r3_root / "analysis"
    marker_paths = {
        "complete": r3_root / "R3_COMPLETE.json",
        "data": r3_root / "R3_DATA_COMPLETE.json",
        "raw": r3_root / "R3_RAW_COLLECTION_COMPLETE.json",
        "recovery": r3_root / "R3_INTEGRITY_RECOVERY_RESOLVED.json",
        "analysis": analysis / "R3_ANALYSIS_COMPLETE.json",
        "stop": analysis / "R3_STUDY_STOP_GATE.json",
    }
    markers = {name: require_pass(path) for name, path in marker_paths.items()}
    if markers["complete"].get("additional_large_scale_carla_required") is not False:
        raise ValueError("R3 completion marker has not closed large-scale CARLA collection")
    if markers["stop"].get("decision") != "stop_formal_large_scale_collection":
        raise ValueError("R3 stop gate has not frozen the collection stop decision")
    if markers["analysis"].get("observed_rollouts") != 80:
        raise ValueError("Expected exactly 80 observed R3 rollouts")

    expected_rows = markers["analysis"]["formal_table_row_counts"]
    source_tables: dict[str, list[dict[str, str]]] = {}
    for filename, expected in expected_rows.items():
        path = analysis / filename
        if sha256(path) != markers["analysis"]["formal_table_sha256"][filename]:
            raise ValueError(f"Frozen R3 table hash mismatch: {filename}")
        rows = read_csv(path)
        if len(rows) != expected:
            raise ValueError(f"Frozen R3 row-count mismatch: {filename}")
        source_tables[filename] = rows

    h3_support = source_tables["r3_h3_cell_support.csv"]
    h3_contrasts = source_tables["r3_h3_contrasts.csv"]
    h3_by_id_metric = {(row["contrast_id"], row["metric"]): row for row in h3_contrasts}
    h3_rows: list[dict[str, Any]] = []
    for support in h3_support:
        contrast_id = support["contrast_id"]
        completion = h3_by_id_metric[(contrast_id, "ego_route_completion_duration_s")]
        separation = h3_by_id_metric[(contrast_id, "minimum_footprint_separation_m")]
        h3_rows.append({
            "risk_policy": support["risk_policy"],
            "target_style": support["target_style"],
            "paired_init_groups": i(completion["complete_clusters"]),
            "mean_completion_effect_s": f(completion["mean_effect"]),
            "completion_bootstrap_ci_lower_s": f(completion["bootstrap_mean_ci_lower"]),
            "completion_bootstrap_ci_upper_s": f(completion["bootstrap_mean_ci_upper"]),
            "completion_holm_p": f(completion["holm_adjusted_p"]),
            "mean_separation_effect_m": f(separation["mean_effect"]),
            "separation_bootstrap_ci_lower_m": f(separation["bootstrap_mean_ci_lower"]),
            "separation_bootstrap_ci_upper_m": f(separation["bootstrap_mean_ci_upper"]),
            "separation_holm_p": f(separation["holm_adjusted_p"]),
            "cell_support_status": support["cell_support_status"],
        })

    h4_rows: list[dict[str, Any]] = []
    for row in source_tables["r3_h4_dominance.csv"]:
        h4_rows.append({
            "predictor": row["predictor"],
            "target_style": row["target_style"],
            "fixed_comparator": row["fixed_comparator"],
            "paired_init_groups": i(row["all_five_primary_pairs_complete"]) * 5,
            "mean_adaptive_minus_fixed_completion_s": f(row["mean_adaptive_minus_fixed_completion_s"]),
            "mean_adaptive_minus_fixed_separation_m": f(row["mean_adaptive_minus_fixed_separation_m"]),
            "no_excess_binary_failures": bool(i(row["no_excess_binary_failures"])),
            "dominance_status": row["dominance_status"],
        })

    prediction_rows = source_tables["r3_predictor_manipulation_checks.csv"]
    risk_rows = source_tables["r3_risk_manipulation_checks.csv"]
    binary_rows = source_tables["r3_binary_failure_contrasts.csv"]
    top1_ade = [row for row in prediction_rows if row["metric"] == "top1_ADE_m"]
    top1_fde = [row for row in prediction_rows if row["metric"] == "top1_FDE_m"]
    adaptive_risk = [row for row in risk_rows if row["risk_policy"] == "adaptive"]
    fixed_risk = [row for row in risk_rows if row["risk_policy"] != "adaptive"]
    failure_total = sum(i(row["treatment_failure_rollouts"]) + i(row["control_failure_rollouts"]) for row in binary_rows)

    hypothesis_rows = [
        {"hypothesis": "H1", "verdict": "supported", "paper_claim": "Task-adapted B1 materially improves in-distribution prediction over B0; R3 in-loop checks are consistent across all policy/style cells."},
        {"hypothesis": "H2", "verdict": "not_supported", "paper_claim": "The tested sequence/Transformer variants do not improve on the simpler B1 adaptation under the matched protocol."},
        {"hypothesis": "H3", "verdict": "not_supported_as_universal_claim", "paper_claim": "Large prediction gains do not universally translate into joint closed-loop efficiency and separation gains; only 2/8 cells support both directions."},
        {"hypothesis": "H4", "verdict": "not_supported_as_universal_dominance", "paper_claim": "Adaptive risk is conditionally useful but does not universally dominate fixed risk; dominance occurs in 3/12 prespecified comparisons."},
    ]
    manipulation_rows = [
        {"check": "B1 prediction direction", "result": f"{sum(f(row['B1_better_init_fraction']) == 1.0 for row in prediction_rows)}/{len(prediction_rows)} metric-policy-style checks have B1 better in all five init groups", "interpretation": "manipulation observed; not an independent benchmark"},
        {"check": "Top1 ADE effect range", "result": f"{min(f(row['mean_B1_minus_B0']) for row in top1_ade):.3f} to {max(f(row['mean_B1_minus_B0']) for row in top1_ade):.3f} m (B1−B0)", "interpretation": "large consistent reduction"},
        {"check": "Top1 FDE effect range", "result": f"{min(f(row['mean_B1_minus_B0']) for row in top1_fde):.3f} to {max(f(row['mean_B1_minus_B0']) for row in top1_fde):.3f} m (B1−B0)", "interpretation": "large consistent reduction"},
        {"check": "Adaptive solver identity", "result": f"{sum(f(row['adaptive_risk_solver_fraction']) == 1.0 for row in adaptive_risk)}/{len(adaptive_risk)} adaptive cells use the adaptive solver on every audited step", "interpretation": "risk treatment applied as specified"},
        {"check": "Adaptive within-rollout variation", "result": f"{sum(i(row['rollouts_with_within_rollout_adaptive_variation']) for row in adaptive_risk)}/{sum(i(row['rollouts']) for row in adaptive_risk)} adaptive rollouts vary within rollout", "interpretation": "adaptive treatment is not a disguised constant"},
        {"check": "Fixed across-init stability", "result": f"maximum range {max(f(row['risk_tightening_across_init_range']) for row in fixed_risk):.3g}", "interpretation": "fixed comparators remain fixed"},
        {"check": "Binary scientific failures", "result": f"{failure_total} failures summed over all prespecified binary contrasts", "interpretation": "cannot discriminate treatments in this nominal matrix"},
    ]

    output.mkdir(parents=True, exist_ok=True)
    table_paths = {
        "table_r3_h3_translation.csv": h3_rows,
        "table_r3_h4_dominance.csv": h4_rows,
        "table_r3_manipulation_and_safety.csv": manipulation_rows,
        "table_final_hypothesis_verdicts.csv": hypothesis_rows,
    }
    for filename, rows in table_paths.items():
        write_csv(output / filename, rows)
    atomic_text(output / "figure_r3_h3_translation.svg", svg_h3(h3_rows))
    atomic_text(output / "figure_r3_h4_dominance.svg", svg_h4(h4_rows))

    supported_h3 = sum(row["cell_support_status"] == "supported_directionally" for row in h3_rows)
    dominated_h4 = sum(row["dominance_status"] == "dominates" for row in h4_rows)
    narrative = f"""# A2 — R3 corrected evidence synthesis

## Completion decision

R3 is complete and integrity-valid: **80/80** prespecified rollouts and all formal tables passed their frozen gates. `R3_STUDY_STOP_GATE.json` records `stop_formal_large_scale_collection`, so its observed H3/H4 direction cannot justify an outcome-selected R3 extension or R4. A later, separately preregistered SF4 application-authority on/off audit of the corrected `reduced_intervention` supervisor responds to external supervisor feedback; it is not the historical `full` supervisor configuration and does not alter the R3 estimands, reopen H1--H4 or weaken this stop decision.

## Central thesis claim

**Task adaptation produces large, consistent in-distribution prediction gains, but their closed-loop value is conditional on the coupling among predictor stack, risk policy, target interaction style and shared supervisor. Neither a more complex temporal model nor adaptive risk is universally superior.**

This is the paper's single organising claim. It keeps machine learning central (the prediction manipulation is strong and consistent) while explaining why better prediction alone does not guarantee better planning outcomes.

## Four hypothesis verdicts

- **H1 — supported:** B1 improves prediction over B0. In R3, all {len(prediction_rows)}/{len(prediction_rows)} in-loop metric-policy-style checks favour B1 across every paired init group. These checks validate the deployed manipulation but are not an independent offline benchmark.
- **H2 — not supported:** the tested Transformer/sequence variants do not beat the simpler B1 adaptation under matched data, training and selection controls. Complexity is therefore not the contribution.
- **H3 — universal claim rejected:** only **{supported_h3}/{len(h3_rows)}** policy/style cells jointly show faster completion and no-worse footprint separation for B1 versus B0. Prediction improvement is real; closed-loop translation is conditional.
- **H4 — universal dominance rejected:** adaptive risk dominates its fixed comparator in only **{dominated_h4}/{len(h4_rows)}** prespecified predictor/style/comparator cells. Adaptive risk is a context-dependent policy, not a universally better one.

## Statistical interpretation

Each primary contrast uses five paired init groups (101–105). The smallest possible two-sided exact sign-flip p-value is 0.0625, and all Holm-adjusted results are non-confirmatory. The paper must therefore report effect sizes, paired directions and bootstrap intervals, and must not claim conventional statistical significance or equivalence.

No native collision, footprint collision, fixed-geometry yield failure or completion failure occurred. These are nominal outcome-reliability observations, not evidence that every MPC step was feasible: the legacy debug telemetry contains logger-unaccepted rows that require execution-level reclassification. The binary endpoints cannot distinguish the tested arms, so continuous footprint separation remains the primary safety-margin evidence.

## What the thesis may and may not claim

The thesis may claim robust in-distribution prediction improvement, failure of universal closed-loop transfer, and predictor–risk–interaction coupling in the tested Town05 give-way setting. It must not claim cross-map or real-world generalisation, a causal weight-only B1 effect, universal adaptive-risk superiority, Transformer superiority, statistical significance, or safety equivalence.

## Next writing action

Use the two generated SVG figures and four CSV tables in Results. Structure the chapter as manipulation validity → H3 translation test → H4 dominance test → mechanism/boundary interpretation. Preserve older timing experiments as secondary sensitivity evidence, not as the primary corrected R3 result.
"""
    atomic_text(output / "R3_FINAL_SYNTHESIS.md", narrative)

    artifacts = [*table_paths, "figure_r3_h3_translation.svg", "figure_r3_h4_dominance.svg", "R3_FINAL_SYNTHESIS.md"]
    source_files = {str(path.relative_to(repo)): sha256(path) for path in marker_paths.values()}
    for filename in expected_rows:
        path = analysis / filename
        source_files[str(path.relative_to(repo))] = sha256(path)
    payload = {
        "schema_version": "r3_paper_synthesis_v1",
        "status": "pass",
        "stage": "A2_corrected_synthesis",
        "r3_rollouts": 80,
        "independent_init_groups": 5,
        "additional_large_scale_carla_required": False,
        "study_stop_decision": markers["stop"]["decision"],
        "central_claim": "Task adaptation strongly improves prediction, but closed-loop benefit is conditional on predictor-risk-interaction coupling under the shared supervisor.",
        "h3": {"status": markers["analysis"]["h3_scientific_support_status"], "directionally_supported_cells": supported_h3, "prespecified_cells": len(h3_rows)},
        "h4": {"status": markers["analysis"]["h4_scientific_support_status"], "dominance_cells": dominated_h4, "prespecified_cells": len(h4_rows)},
        "prediction_manipulation": {"all_init_better_checks": sum(f(row["B1_better_init_fraction"]) == 1.0 for row in prediction_rows), "checks": len(prediction_rows)},
        "binary_failure_total_across_contrasts": failure_total,
        "artifacts": {filename: sha256(output / filename) for filename in artifacts},
        "source_files": source_files,
    }
    atomic_json(output / "A2_COMPLETE.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--r3-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    default_r3 = repo / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3"
    r3_root = (args.r3_root or default_r3).resolve()
    output = (args.output or repo / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis").resolve()
    result = build(repo, r3_root, output)
    print(json.dumps({"status": result["status"], "stage": result["stage"], "h3": result["h3"], "h4": result["h4"]}, indent=2))


if __name__ == "__main__":
    main()
