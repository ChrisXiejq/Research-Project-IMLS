#!/usr/bin/env python3
"""G1: freeze the final ML-centred contribution from E1-E6 evidence."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import datetime as dt
import json
from pathlib import Path

from distinction_analysis_utils import atomic_write_json, sha256_file, write_csv


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e1", type=Path, required=True)
    parser.add_argument("--e2", type=Path, required=True)
    parser.add_argument("--e3", type=Path, required=True)
    parser.add_argument("--e4", type=Path, required=True)
    parser.add_argument("--e5", type=Path, required=True)
    parser.add_argument("--e6", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    e1, e2, e3, e4, e5, e6 = (load(getattr(args, name)) for name in ("e1", "e2", "e3", "e4", "e5", "e6"))

    b1_beats_all_physical = all(
        row["B1_minus_baseline_ADE_m"] < 0 and row["B1_minus_baseline_FDE_m"] < 0
        for row in e1["comparison"]
    )
    all_inloop_ade = [
        row
        for row in e4["B1_minus_B0_contrasts"]
        if row["subset"] == "all" and row["metric"] == "top1_ADE_m"
    ]
    active_inloop_ade = [
        row
        for row in e4["B1_minus_B0_contrasts"]
        if row["subset"] == "response_active" and row["metric"] == "top1_ADE_m"
    ]
    aggregate_inloop_consistent = bool(all_inloop_ade) and all(row["B1_minus_B0_mean"] < 0 for row in all_inloop_ade)
    active_tail_failure = any(row["B1_minus_B0_mean"] > 0 for row in active_inloop_ade)
    transformer_ranking = {row["variant"]: row for row in e3["variants"]}
    transformer_consistent_advantage = (
        transformer_ranking["T1"]["median_validation_rollout_macro_NLL"]
        < transformer_ranking["B2-M"]["median_validation_rollout_macro_NLL"]
        and transformer_ranking["T2"]["median_validation_rollout_macro_NLL"]
        < transformer_ranking["B2-D"]["median_validation_rollout_macro_NLL"]
    )

    e2_conditions = {row["condition"]: row for row in e2["conditions"]}
    input_findings = []
    for family in ("raster", "past"):
        shuffle_rows = [row for name, row in e2_conditions.items() if name.startswith(f"{family}_shuffle")]
        if not shuffle_rows and f"{family}_shuffle" in e2_conditions:
            shuffle_rows = [e2_conditions[f"{family}_shuffle"]]
        deltas = [row.get("delta_vs_original__all_top1_ADE_m") for row in shuffle_rows]
        deltas = [float(value) for value in deltas if value is not None]
        input_findings.append(
            {
                "input": family,
                "shuffle_runs": len(deltas),
                "mean_ADE_delta_m": sum(deltas) / len(deltas) if deltas else None,
                "all_shuffle_ADE_deltas_positive": bool(deltas) and all(value > 0 for value in deltas),
            }
        )

    claims = [
        {
            "claim_id": "ML-C1",
            "claim": "Frozen B1 task adaptation improves aggregate in-distribution give-way prediction beyond B0 and simple physical/route-prior baselines.",
            "verdict": "supported_descriptively" if b1_beats_all_physical and aggregate_inloop_consistent else "not_supported",
            "headline": 1,
            "boundary": "single Town05 give-way distribution; five held-out init groups; B1 is a complete adaptation configuration",
        },
        {
            "claim_id": "ML-C2",
            "claim": "The lightweight Transformer residual adapter provides a consistent advantage over the corresponding MLP adapter.",
            "verdict": "supported" if transformer_consistent_advantage else "not_supported",
            "headline": 1,
            "boundary": "comparisons are not parameter matched and 10/15 runs reached the epoch ceiling",
        },
        {
            "claim_id": "ML-C3",
            "claim": "Aggregate B1 improvement guarantees better prediction in the rare response-active interaction tail.",
            "verdict": "refuted_by_posthoc_tail_diagnostic" if active_tail_failure else "not_refuted",
            "headline": 1,
            "boundary": "response-active windows are outcome-dependent and post hoc; -3 m tail is the clearest failure",
        },
        {
            "claim_id": "ML-C4",
            "claim": "B1 uses its raster and target-history inputs rather than acting only as a fixed route-prior correction.",
            "verdict": (
                "supported_mechanistically"
                if all(item["all_shuffle_ADE_deltas_positive"] for item in input_findings)
                else "partially_supported_or_inconclusive"
            ),
            "headline": 0,
            "boundary": "shuffle sensitivity is not proof of semantic or causal understanding; neutralisation is OOD",
        },
    ]

    central_thesis = (
        "Under a frozen small-data give-way protocol, output-head task adaptation produced a large aggregate "
        "in-distribution prediction gain beyond simple physical baselines, while lightweight Transformer residual "
        "adapters did not establish a consistent advantage over corresponding MLP adapters. The aggregate gain did "
        "not extend to the rare, timing-shifted response-active tail, and closed-loop policy effects remained coupled "
        "to calibration, supervisor and operating context."
    )
    decision = {
        "schema_version": "distinction_g1_ml_contribution_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass",
        "result_generation": "distinction_v1",
        "gate": "G1",
        "central_thesis": central_thesis,
        "claims": claims,
        "input_diagnostics": input_findings,
        "decision_checks": {
            "B1_beats_all_physical_baselines_ADE_and_FDE": b1_beats_all_physical,
            "B1_aggregate_inloop_ADE_better_at_all_offsets": aggregate_inloop_consistent,
            "B1_response_active_tail_failure_present": active_tail_failure,
            "transformer_consistent_advantage": transformer_consistent_advantage,
            "parameter_matched_architecture_comparison": e3["fairness_checks"]["parameter_matched"],
            "split_audit_pass": e6["status"] == "pass",
            "formal_zero_ego_target_footprint_collisions": e5["footprint_safety"]["footprint_collisions"] == 0,
        },
        "prohibited_wording": [
            "Transformer is the best/optimal architecture",
            "B1 improves every give-way interaction",
            "adaptive risk is universally superior to fixed risk",
            "zero observed collision proves safety",
            "architecture-only causal effect",
        ],
        "source_sha256": {name: sha256_file(getattr(args, name)) for name in ("e1", "e2", "e3", "e4", "e5", "e6")},
    }
    atomic_write_json(args.output_dir / "G1_ML_CONTRIBUTION_FROZEN.json", decision)
    write_csv(args.output_dir / "G1_claim_matrix.csv", claims, list(claims[0]))
    markdown = "# G1 — Frozen machine-learning contribution\n\n"
    markdown += f"> {central_thesis}\n\n"
    markdown += "## Claim decisions\n\n| ID | Verdict | Frozen claim boundary |\n| --- | --- | --- |\n"
    for claim in claims:
        markdown += f"| {claim['claim_id']} | {claim['verdict']} | {claim['boundary']} |\n"
    markdown += "\n## Prohibited wording\n\n" + "\n".join(f"- {item}" for item in decision["prohibited_wording"]) + "\n"
    (args.output_dir / "G1_ML_CONTRIBUTION_FROZEN.md").write_text(markdown, encoding="utf-8")
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
