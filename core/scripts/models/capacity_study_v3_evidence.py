#!/usr/bin/env python3
"""Fail-closed dissertation evidence index and pre-execution placeholders for V3."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from capacity_study_v3_protocol import atomic_json, sha256_file


AXIS_REQUIREMENTS = {
    "capacity": {"H1_capacity_transformer_full_small_minus_large"},
    "information": {
        "H2_information_mlp_snapshot_minus_full",
        "H2_information_transformer_snapshot_minus_full",
    },
    "architecture": {
        "H3_attention_history_gain_difference_in_differences",
        "architecture_direct_full_mlp_minus_transformer",
    },
    "adaptation_allocation": {"B1_head_capacity_curve", "B1_data_efficiency_curve"},
    "predictor_risk": {"model_by_risk_interactions", "within_risk_contrasts"},
}

PROHIBITED_PATTERNS = {
    "safety": re.compile(r"\b(proves?|guarantees?|establishes?)\s+safety\b", re.I),
    "equivalence": re.compile(r"\b(equivalent|no difference)\b", re.I),
    "foundation_mismatch": re.compile(r"foundation mismatch.*(caused|explains|is the reason)", re.I),
    "universal_superiority": re.compile(r"\b(always|universally|all scenarios)\b.*\b(superior|better)\b", re.I),
}


PLANNED_OUTPUTS = (
    ("capacity_curves", "Capacity", "trainable parameters", "rollout-macro NLL"),
    ("history_horizon_curves", "Information", "trained horizon (s)", "rollout-macro NLL"),
    ("matched_architecture_table", "Architecture", "matched capacity/horizon", "MLP vs Transformer"),
    ("history_gain_interaction", "Architecture", "encoder family", "full-minus-snapshot gain"),
    ("response_stratified_mechanisms", "Information", "response stratum", "task metrics"),
    ("b1_allocation_table", "Adaptation allocation", "capacity tier", "B1 performance"),
    ("data_efficiency_curves", "Adaptation allocation", "rollout-group fraction", "NLL"),
    ("calibration_summary", "Calibration", "model cell", "temperature/covariance scale"),
    ("latency_pareto", "Deployment", "warmed batch-one latency (ms)", "NLL"),
    ("closed_loop_cells", "Predictor-risk", "160 frozen cells", "outcomes"),
    ("model_by_risk_interaction", "Predictor-risk", "risk policy", "P* minus B1"),
)


def validate_claim_text(text: str) -> None:
    hits = [name for name, pattern in PROHIBITED_PATTERNS.items() if pattern.search(text)]
    if hits:
        raise ValueError(f"Unsupported dissertation wording: {hits}")


def claim_record(
    *,
    claim_id: str,
    axis: str,
    text: str,
    evidence_ids: Sequence[str],
    source_fields: Sequence[Mapping[str, str]],
    completion_status: str,
) -> dict[str, Any]:
    if axis not in AXIS_REQUIREMENTS:
        raise ValueError(f"Unknown evidence axis: {axis}")
    validate_claim_text(text)
    evidence = set(evidence_ids)
    missing = AXIS_REQUIREMENTS[axis] - evidence
    if completion_status == "pass" and missing:
        raise ValueError(f"Claim {claim_id} lacks required evidence: {sorted(missing)}")
    for locator in source_fields:
        if set(locator) != {"artifact", "field", "unit"}:
            raise ValueError("Every scalar locator requires artifact, field, and unit")
    return {
        "claim_id": claim_id,
        "axis": axis,
        "status": "ready" if completion_status == "pass" and not missing else "placeholder",
        "text": text if completion_status == "pass" and not missing else "[RESULT PENDING — no numerical claim permitted]",
        "planned_text": text,
        "evidence_ids": list(evidence_ids),
        "missing_required_evidence": sorted(missing),
        "source_fields": [dict(value) for value in source_fields],
    }


def build_placeholder_package() -> dict[str, Any]:
    outputs = [
        {
            "artifact_id": artifact_id,
            "axis": axis,
            "x_or_rows": x_axis,
            "y_or_columns": y_axis,
            "status": "RESULT_PENDING",
            "source_artifact": None,
            "source_field": None,
            "unit": None,
        }
        for artifact_id, axis, x_axis, y_axis in PLANNED_OUTPUTS
    ]
    methods = (
        "The V3 study separates three questions. Capacity is tested by changing "
        "trainable parameter count within each family; Information is tested by "
        "training identical-capacity models on fixed 0.0, 0.4, and 1.0 s masks over "
        "the same complete six-token examples; Architecture is tested by matched "
        "MLP/Transformer contrasts and a difference-in-differences of their history "
        "gains. Matched runs use AdamW with weight decay 1e-5, gradient-norm clipping "
        "at 10, deterministic data order, and encoder dropout 0.1. Learning rates and "
        "checkpoints are selected on validation rollout-macro NLL with patience 12; "
        "the 80-to-120-epoch common-extension gate covers both core and matched "
        "data-fraction comparisons. Formal completion requires disjoint group splits, "
        "complete group/cell support, unique sample keys, finite inputs/losses/weights, "
        "and live source/data/model hashes; debug-limited runs are smoke-only. Fresh "
        "groups are opened once after convergence, capacity, calibration, and "
        "latency gates pass. The final CARLA study crosses B1 and P* with four risk "
        "policies, two target styles, and ten paired held-out groups."
    )
    return {
        "schema_version": "capacity_history_dissertation_evidence_v3",
        "status": "planned",
        "numeric_prose_allowed": False,
        "methods_text": methods,
        "planned_outputs": outputs,
        "claims": [],
    }


def write_placeholder_package(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    package = build_placeholder_package()
    json_path = root / "evidence_index.json"
    atomic_json(json_path, package)
    csv_path = root / "planned_outputs.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(package["planned_outputs"][0]))
        writer.writeheader()
        writer.writerows(package["planned_outputs"])
    markdown_path = root / "METHODS_AND_RESULT_PLACEHOLDERS.md"
    lines = [
        "# Capacity–Information–Architecture V3",
        "",
        "## Methods text",
        "",
        package["methods_text"],
        "",
        "## Planned result artefacts",
        "",
        "| Artefact | Axis | Rows/x | Columns/y | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in package["planned_outputs"]:
        lines.append(
            f"| {row['artifact_id']} | {row['axis']} | {row['x_or_rows']} | "
            f"{row['y_or_columns']} | RESULT PENDING |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "status": "pass",
        "numeric_prose_allowed": False,
        "evidence_index": str(json_path),
        "evidence_index_sha256": sha256_file(json_path),
        "planned_outputs_csv": str(csv_path),
        "placeholders_markdown": str(markdown_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(write_placeholder_package(args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
