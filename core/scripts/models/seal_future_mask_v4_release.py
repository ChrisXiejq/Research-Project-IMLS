#!/usr/bin/env python3
"""Seal audited evidence, figures, and paper-ready outputs into one release gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload


REQUIRED_FIGURE_FILES = {
    "figure_mask_correction_impact.pdf",
    "figure_mask_correction_impact.png",
    "figure_corrected_capacity_information_architecture.pdf",
    "figure_corrected_capacity_information_architecture.png",
    "figure_selection_stability_v4_validation_frozen.pdf",
    "figure_selection_stability_v4_validation_frozen.png",
}
REQUIRED_PAPER_FILES = {
    "model_seed_metrics.csv",
    "controlled_effects.csv",
    "claim_decisions.csv",
    "paper_update_map.csv",
    "table_offline_matrix_v4.tex",
    "table_offline_effects_v4.tex",
    "table_mask_audit_v4.tex",
    "corrected_v4_conclusion_audit.md",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def valid(payload: Mapping[str, Any], field: str) -> bool:
    value = dict(payload)
    recorded = value.pop(field, None)
    return recorded == sha256_payload(value)


def validate_manifest_files(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    required_files: set[str],
    *,
    role: str,
) -> None:
    files = manifest.get("files")
    if not isinstance(files, Mapping) or not files:
        raise ValueError(f"{role} manifest has an empty or invalid files mapping")
    if not required_files.issubset(files):
        missing = sorted(required_files - set(files))
        raise ValueError(f"{role} manifest is missing required files: {missing}")

    base = manifest_path.parent.resolve()
    resolved_paths: set[Path] = set()
    for raw_name, recorded_sha256 in files.items():
        if not isinstance(raw_name, str) or not raw_name or not isinstance(
            recorded_sha256, str
        ) or not recorded_sha256:
            raise ValueError(f"{role} manifest contains an invalid file record")
        relative = Path(raw_name)
        if (
            relative.is_absolute()
            or raw_name != relative.as_posix()
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ValueError(f"{role} manifest contains an unsafe relative path: {raw_name}")
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as error:
            raise ValueError(
                f"{role} manifest file escapes its release directory: {raw_name}"
            ) from error
        if candidate in resolved_paths:
            raise ValueError(f"{role} manifest aliases one file more than once: {raw_name}")
        resolved_paths.add(candidate)
        if not candidate.is_file() or candidate.stat().st_size <= 0:
            raise ValueError(f"{role} release file is missing or empty: {raw_name}")
        if sha256_file(candidate) != recorded_sha256:
            raise ValueError(f"{role} release file hash mismatch: {raw_name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--figures", required=True, type=Path)
    parser.add_argument("--paper-outputs", required=True, type=Path)
    parser.add_argument("--foundation-scope", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    evidence = load(args.evidence)
    figures = load(args.figures)
    paper = load(args.paper_outputs)
    foundation = load(args.foundation_scope)
    if (
        not valid(evidence, "release_sha256")
        or not valid(figures, "manifest_sha256")
        or not valid(paper, "manifest_sha256")
        or not valid(foundation, "audit_sha256")
        or evidence.get("status") != "pass"
        or figures.get("status") != "pass"
        or paper.get("status") != "pass"
        or evidence.get("carla_was_launched") is not False
        or paper.get("paper_source_modified") is not False
        or evidence.get("schema_version")
        != "capacity_history_future_mask_v4_offline_evidence_release"
        or figures.get("schema_version")
        != "capacity_history_future_mask_v4_figure_manifest"
        or paper.get("schema_version")
        != "capacity_history_future_mask_v4_paper_outputs"
        or foundation.get("schema_version")
        != "capacity_history_foundation_future_mask_scope_audit_v4"
        or foundation.get("status") != "pass"
        or foundation.get("evaluated_membership", {}).get(
            "partial_windows_entered_foundation_metrics"
        )
        != 0
        or int(evidence.get("corrected_runs", -1)) != 27
        or int(paper.get("corrected_runs", -1)) != 27
        or evidence.get("future_validity_contract")
        != "future_valid_mask_fail_closed_v4"
        or paper.get("future_validity_contract")
        != "future_valid_mask_fail_closed_v4"
    ):
        raise ValueError("Offline release seal blocked by invalid upstream manifest")
    validate_manifest_files(
        args.figures,
        figures,
        REQUIRED_FIGURE_FILES,
        role="Figure",
    )
    validate_manifest_files(
        args.paper_outputs,
        paper,
        REQUIRED_PAPER_FILES,
        role="Paper-output",
    )
    gates = evidence.get("gate_artifacts", {})
    figure_sources = figures.get("source_artifacts", {})
    paper_sources = paper.get("source_artifacts", {})
    cross_links = (
        (figure_sources.get("impact_audit_sha256"), gates.get("historical_impact_audit_sha256")),
        (figure_sources.get("offline_synthesis_sha256"), gates.get("corrected_synthesis_sha256")),
        (figure_sources.get("full_horizon_sensitivity_sha256"), gates.get("full_horizon_sensitivity_sha256")),
        (figure_sources.get("selection_freeze_sha256"), gates.get("selection_freeze_sha256")),
        (paper_sources.get("selection_freeze_sha256"), gates.get("selection_freeze_sha256")),
        (paper_sources.get("synthesis_sha256"), gates.get("corrected_synthesis_sha256")),
        (paper_sources.get("cache_audit_sha256"), gates.get("cache_and_mask_audit_sha256")),
        (paper_sources.get("full_horizon_sensitivity_sha256"), gates.get("full_horizon_sensitivity_sha256")),
        (paper_sources.get("claim_consistency_audit_sha256"), evidence.get("claim_consistency_audit_sha256")),
        (paper_sources.get("carla_deployment_decision_sha256"), evidence.get("carla_deployment_decision_sha256")),
        (paper_sources.get("offline_evidence_release_sha256"), evidence.get("release_sha256")),
        (
            paper_sources.get("foundation_mask_scope_audit_sha256"),
            foundation.get("audit_sha256"),
        ),
        (
            paper_sources.get("extension_protocol_sha256"),
            gates.get("extension_protocol_sha256"),
        ),
    )
    if any(not left or left != right for left, right in cross_links):
        raise ValueError("Offline release seal blocked by cross-manifest identity mismatch")
    required_gates = {
        "cache_and_mask_audit_sha256",
        "historical_impact_audit_sha256",
        "training_curve_audit_sha256",
        "full_horizon_sensitivity_sha256",
        "formal_report_contract_audit_sha256",
        "pipeline_receipt_sha256",
        "pipeline_stage_receipt_sha256",
        "selection_freeze_sha256",
        "corrected_synthesis_sha256",
        "extension_protocol_sha256",
    }
    if any(not gates.get(key) for key in required_gates):
        raise ValueError("Offline release seal is missing required evidence gates")
    payload = {
        "schema_version": "capacity_history_future_mask_v4_final_offline_release",
        "status": "pass",
        "corrected_runs": 27,
        "future_validity_contract": "future_valid_mask_fail_closed_v4",
        "carla_was_launched": False,
        "paper_source_modified": False,
        "evidence_release_sha256": evidence["release_sha256"],
        "figure_manifest_sha256": figures["manifest_sha256"],
        "paper_outputs_manifest_sha256": paper["manifest_sha256"],
        "foundation_mask_scope_audit_sha256": foundation["audit_sha256"],
        "source_files": {
            "evidence": {"path": str(args.evidence), "sha256": sha256_file(args.evidence)},
            "figures": {"path": str(args.figures), "sha256": sha256_file(args.figures)},
            "paper_outputs": {
                "path": str(args.paper_outputs),
                "sha256": sha256_file(args.paper_outputs),
            },
            "foundation_scope": {
                "path": str(args.foundation_scope),
                "sha256": sha256_file(args.foundation_scope),
            },
        },
    }
    payload["release_sha256"] = sha256_payload(payload)
    atomic_json(args.output, payload)
    print(json.dumps({"status": "pass", "release_sha256": payload["release_sha256"]}))


if __name__ == "__main__":
    main()
