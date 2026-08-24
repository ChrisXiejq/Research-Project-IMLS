#!/usr/bin/env python3
"""Build the post-SF4, claim-safe tabular evidence release."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


SCHEMA_VERSION = "supervisor_bottleneck_paper_release_v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields or list(rows[0]),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _one(rows: list[dict[str, str]], **criteria: str) -> dict[str, str]:
    found = [row for row in rows if all(row.get(key) == value for key, value in criteria.items())]
    if len(found) != 1:
        raise ValueError(f"Expected one row for {criteria}, found {len(found)}")
    return found[0]


def build_release(root: Path, output: Path) -> dict[str, Any]:
    contract = root / "docs/paper/generated/supervisor_bottleneck_v1/scientific_contract"
    telemetry = root / "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit"
    v3 = root / "docs/paper/generated/capacity_history_v3/final"
    r3 = root / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis"
    sf4 = root / "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/analysis"
    f1 = root / "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit"
    gate_path = root / "docs/paper/generated/supervisor_bottleneck_v1/evidence_gap_gate.json"

    claims_path = contract / "claim_evidence_boundary.json"
    blocks_path = contract / "evidence_blocks.json"
    f1_path = f1 / "frozen_test_same_aggregation.csv"
    axes_path = v3 / "table_three_axis_contrasts.csv"
    offline_path = v3 / "table_offline_model_cells.csv"
    v3_cells_path = v3 / "table_closed_loop_cells.csv"
    v3_contrasts_path = v3 / "table_model_by_risk_contrasts.csv"
    r3_risk_path = r3 / "table_r3_h4_dominance.csv"
    r3_transfer_path = r3 / "table_r3_h3_translation.csv"
    sf4_rollouts_path = sf4 / "sf4_rollout_outcomes.csv"
    sf4_inference_path = sf4 / "sf4_inference.json"
    intervention_path = telemetry / "supervisor_intervention_by_cell.csv"
    attenuation_path = telemetry / "attenuation_claim_audit.json"
    solver_path = telemetry / "solver_path_reconciliation.json"

    claims = _json(claims_path)["claims"]
    blocks = _json(blocks_path)["blocks"]
    gate = _json(gate_path)
    if gate.get("decision") != "existing_evidence_sufficient":
        raise ValueError("Paper release is blocked until the evidence-gap gate closes")
    f1_rows = _csv(f1_path)
    axes = _csv(axes_path)
    offline = _csv(offline_path)
    v3_cells = _csv(v3_cells_path)
    v3_contrasts = _csv(v3_contrasts_path)
    r3_risk = _csv(r3_risk_path)
    r3_transfer = _csv(r3_transfer_path)
    sf4_rollouts = _csv(sf4_rollouts_path)
    sf4_inference = _json(sf4_inference_path)
    intervention = _csv(intervention_path)
    attenuation = _json(attenuation_path)
    solver = _json(solver_path)

    output.mkdir(parents=True, exist_ok=True)
    tables = output / "tables"
    tables.mkdir(exist_ok=True)

    hypothesis_rows = [
        {
            "claim_id": row["claim_id"],
            "hypothesis": row["hypothesis"],
            "verdict": row["verdict"],
            "estimand": row["estimand"],
            "independent_unit": row["independent_unit"],
            "boundary": row["boundary"],
            "prohibited_overclaim": row["prohibited_overclaim"],
            "source_path": row["source"]["path"],
            "source_locator": row["source"]["locator"],
        }
        for row in claims
    ]
    _write_csv(tables / "table01_hypothesis_verdicts.csv", hypothesis_rows)

    foundation_rows = []
    for variant in ("B0", "B1"):
        row = _one(f1_rows, variant=variant, aggregation_level="rollout_macro")
        foundation_rows.append(
            {
                "evidence_block": "F0_foundation",
                "comparison_member": variant,
                "metric": "rollout_macro_NLL",
                "estimate": row["trajectory_mixture_NLL_nats_per_step"],
                "ci95_low": "",
                "ci95_high": "",
                "independent_groups": 5,
                "population": "Town05 groups 46--50",
                "source_locator": f"{f1_path.relative_to(root)}::variant={variant};aggregation_level=rollout_macro",
            }
        )
        for metric, field in (("top1_ADE_m", "top1_ADE_m"), ("top1_FDE_m", "top1_FDE_m")):
            foundation_rows.append(
                {
                    "evidence_block": "F0_foundation",
                    "comparison_member": variant,
                    "metric": metric,
                    "estimate": row[field],
                    "ci95_low": "",
                    "ci95_high": "",
                    "independent_groups": 5,
                    "population": "Town05 groups 46--50",
                    "source_locator": f"{f1_path.relative_to(root)}::variant={variant};aggregation_level=rollout_macro",
                }
            )
    cia_ids = [
        "H1_capacity_transformer_full_small_minus_large",
        "H2_information_mlp_snapshot_minus_full",
        "H2_information_transformer_snapshot_minus_full",
        "H3_attention_history_gain_difference_in_differences",
        "architecture_direct_mlp_minus_transformer__h1p0__large",
    ]
    for contrast_id in cia_ids:
        row = _one(axes, contrast_id=contrast_id)
        foundation_rows.append(
            {
                "evidence_block": "F4_capacity_information_architecture",
                "comparison_member": contrast_id,
                "metric": row["metric"],
                "estimate": row["effect"],
                "ci95_low": row["ci95_low"],
                "ci95_high": row["ci95_high"],
                "independent_groups": row["independent_groups"],
                "population": "Town05 retrospective held-out groups 41--45",
                "source_locator": f"{axes_path.relative_to(root)}::contrast_id={contrast_id}",
            }
        )
    _write_csv(tables / "table02_foundation_and_cia.csv", foundation_rows)

    # Preserve cell-level data for figure regeneration rather than reconstructing it from prose.
    offline_release = []
    for row in offline:
        item = dict(row)
        item["population_id"] = "F4_capacity_information_architecture_v3"
        item["source_locator"] = f"{offline_path.relative_to(root)}::model_cell_id={row['model_cell_id']}"
        offline_release.append(item)
    _write_csv(tables / "table03_offline_model_cells.csv", offline_release)

    v3_release = []
    for row in v3_cells:
        item = dict(row)
        item["population_id"] = "F5_v3_selected_model_closed_loop"
        item["source_locator"] = f"{v3_cells_path.relative_to(root)}::predictor={row['predictor']};risk_policy={row['risk_policy']}"
        v3_release.append(item)
    _write_csv(tables / "table04_v3_closed_loop_cells.csv", v3_release)

    transfer_ids = {
        "completion_time_s__P_star_minus_B1__fixed_medium",
        "completion_time_s__P_star_minus_B1__adaptive",
        "min_footprint_separation_m__P_star_minus_B1__fixed_medium",
        "min_footprint_separation_m__P_star_minus_B1__adaptive",
        "inloop_top1_ADE_m__P_star_minus_B1__fixed_medium",
        "inloop_top1_ADE_m__P_star_minus_B1__adaptive",
        "completion_time_s__model_by_risk__adaptive_minus_fixed_medium",
        "min_footprint_separation_m__model_by_risk__adaptive_minus_fixed_medium",
    }
    v3_effects = []
    for row in v3_contrasts:
        if row["contrast_id"] not in transfer_ids:
            continue
        item = dict(row)
        item["population_id"] = "F5_v3_selected_model_closed_loop"
        item["source_locator"] = f"{v3_contrasts_path.relative_to(root)}::contrast_id={row['contrast_id']}"
        v3_effects.append(item)
    _write_csv(tables / "table05_v3_transfer_effects.csv", v3_effects)

    r3_release = []
    for row in r3_risk:
        item = dict(row)
        item["population_id"] = "F2_r3_predictor_risk"
        item["source_locator"] = f"{r3_risk_path.relative_to(root)}::predictor={row['predictor']};target_style={row['target_style']};fixed_comparator={row['fixed_comparator']}"
        r3_release.append(item)
    _write_csv(tables / "table06_r3_risk_frontier.csv", r3_release)

    r3_transfer_release = []
    for row in r3_transfer:
        item = dict(row)
        item["population_id"] = "F2_r3_predictor_risk"
        item["source_locator"] = f"{r3_transfer_path.relative_to(root)}::risk_policy={row['risk_policy']};target_style={row['target_style']}"
        r3_transfer_release.append(item)
    _write_csv(tables / "table07_r3_predictor_transfer.csv", r3_transfer_release)

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in sf4_rollouts:
        grouped[(row["supervisor_authority_mode"], row["risk_policy"])].append(row)
    sf4_summary = []
    for (authority, risk), rows in sorted(grouped.items()):
        sf4_summary.append(
            {
                "supervisor_authority": authority,
                "risk_policy": risk,
                "rollouts": len(rows),
                "independent_groups": len({row["ego_init_id"] for row in rows}),
                "completion_successes": sum(int(row["completion_success"]) for row in rows),
                "yield_rule_failures": sum(int(row["yield_rule_failure"]) for row in rows),
                "adverse_collision_rollouts": sum(int(row["adverse_collision_any"]) for row in rows),
                "mean_failure_penalized_completion_time_s": mean(float(row["failure_penalized_completion_time_s"]) for row in rows),
                "mean_minimum_margin_adjusted_bbox_separation_m": mean(float(row["minimum_margin_adjusted_bbox_separation_m"]) for row in rows),
                "mean_authority_applied_fraction": mean(float(row["supervisor_authority_applied_fraction"]) for row in rows),
                "mean_candidate_requested_fraction": mean(float(row["supervisor_candidate_requested_fraction"]) for row in rows),
                "mean_fallback_or_nonaccepted_fraction": mean(float(row["attempted_fallback_or_nonaccepted_fraction"]) for row in rows),
                "population_id": "F3_sf4_supervisor_authority",
                "source_locator": f"{sf4_rollouts_path.relative_to(root)}::authority={authority};risk={risk}",
            }
        )
    _write_csv(tables / "table08_sf4_authority_cells.csv", sf4_summary)

    sf4_effects = []
    for metric in (
        "failure_penalized_completion_time_s",
        "minimum_margin_adjusted_bbox_separation_m",
        "actual_minus_nominal_accel_abs_mean_mps2",
        "attempted_fallback_or_nonaccepted_fraction",
    ):
        for contrast, effect in sf4_inference["direct_paired_effects"][metric].items():
            sf4_effects.append(
                {
                    "metric": metric,
                    "contrast": contrast,
                    "mean_effect": effect.get("mean_effect", ""),
                    "ci95_low": (effect.get("cluster_bootstrap_95ci") or ["", ""])[0],
                    "ci95_high": (effect.get("cluster_bootstrap_95ci") or ["", ""])[1],
                    "defined_init_clusters": effect.get("defined_init_clusters", ""),
                    "status": effect.get("status", "estimated"),
                    "population_id": "F3_sf4_supervisor_authority",
                    "source_locator": f"{sf4_inference_path.relative_to(root)}::/direct_paired_effects/{metric}/{contrast}",
                }
            )
    _write_csv(tables / "table09_sf4_paired_effects.csv", sf4_effects)

    limitations = [
        {
            "limitation_id": "L1",
            "scope": "single controlled scenario distribution",
            "evidence": "Town05 right-hand-traffic left-turn give-way",
            "paper_boundary": "No cross-map, real-road or population safety generalisation.",
        },
        {
            "limitation_id": "L2",
            "scope": "retrospective offline held-out groups",
            "evidence": "Capacity--Information--Architecture groups 41--45",
            "paper_boundary": "Treat H1--H3 as controlled retrospective evidence, not a new prospective benchmark.",
        },
        {
            "limitation_id": "L3",
            "scope": "authority-off floor saturation",
            "evidence": "0/40 completion under authority off",
            "paper_boundary": "Common authority effect is identified; selective masking is not.",
        },
        {
            "limitation_id": "L4",
            "scope": "incomplete phase clocks",
            "evidence": "Some release/resume contrasts have fewer than 10 paired groups",
            "paper_boundary": "Undefined events remain missing and descriptive only.",
        },
        {
            "limitation_id": "L5",
            "scope": "controller acceptance semantics",
            "evidence": f"{solver['totals']['factual_solver_attempts']} attempts; {solver['totals']['fallback_or_nonaccepted_attempts']} fallback/nonaccepted",
            "paper_boundary": "Controller acceptance is not a proof of strict feasibility or recursive feasibility.",
        },
        {
            "limitation_id": "L6",
            "scope": "rule-based supervisor bundle",
            "evidence": "Seven behavioural channels and rule bypass are jointly toggled",
            "paper_boundary": "The experiment attributes effects to complete authority, not to a single rule.",
        },
    ]
    _write_csv(tables / "table10_limitations.csv", limitations)

    scalar_provenance = []
    for table in sorted(tables.glob("*.csv")):
        rows = _csv(table)
        for index, row in enumerate(rows, start=2):
            source_locator = row.get("source_locator", "release-authored boundary row")
            for key, value in row.items():
                if key in {"estimate", "effect", "mean_effect", "completion_successes", "yield_rule_failures", "adverse_collision_rollouts", "mean_failure_penalized_completion_time_s", "mean_minimum_margin_adjusted_bbox_separation_m"} and value not in (None, ""):
                    scalar_provenance.append(
                        {
                            "release_table": table.name,
                            "release_row": index,
                            "field": key,
                            "value": value,
                            "canonical_source_locator": source_locator,
                            "aggregation_unit": row.get("independent_unit") or row.get("independent_groups") or row.get("paired_init_groups") or "declared in source",
                            "population_id": row.get("population_id") or row.get("evidence_block") or "boundary_metadata",
                        }
                    )
    _write_csv(tables / "scalar_provenance_index.csv", scalar_provenance)

    sources = []
    for path in (
        claims_path, blocks_path, gate_path, f1_path, axes_path, offline_path,
        v3_cells_path, v3_contrasts_path, r3_risk_path, r3_transfer_path,
        sf4_rollouts_path, sf4_inference_path, intervention_path, attenuation_path, solver_path,
    ):
        sources.append({"path": str(path.relative_to(root)), "sha256": _sha(path)})
    population_ids = [block["block_id"] for block in blocks]
    checks = {
        "evidence_gap_gate_closed": gate["decision"] == "existing_evidence_sufficient",
        "population_ids_unique": len(population_ids) == len(set(population_ids)),
        "headline_claims_present": len([row for row in hypothesis_rows if row["claim_id"].startswith("H")]) == 6,
        "sf4_rollouts_reconcile": sum(int(row["rollouts"]) for row in sf4_summary) == 80,
        "sf4_floor_boundary_present": attenuation["floor_saturation"]["authority_off_completion"] == 0,
        "selective_masking_refused": attenuation["selective_masking_identified"] is False,
        "scalar_provenance_nonempty": len(scalar_provenance) > 0,
    }
    if not all(checks.values()):
        raise ValueError(f"Paper release checks failed: {checks}")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "tables": [
            {"path": str(path.relative_to(output)), "sha256": _sha(path), "rows": len(_csv(path))}
            for path in sorted(tables.glob("*.csv"))
        ],
        "population_registry": [
            {
                "population_id": block["block_id"],
                "population": block["population"],
                "independent_unit": block["independent_unit"],
                "pooling": "forbidden_across_evidence_blocks",
            }
            for block in blocks
        ],
        "checks": checks,
        "headline_boundary": "Compatible metadata are juxtaposed, never pooled. SF4 supports a large common authority effect but not selective masking.",
    }
    _write_json(output / "PAPER_RELEASE_COMPLETE.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/paper/generated/supervisor_bottleneck_v1/paper_release"),
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    print(json.dumps(build_release(args.root, output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
