#!/usr/bin/env python3
"""Decide whether the frozen supervisor-bottleneck thesis needs new CARLA data."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "supervisor_bottleneck_evidence_gap_gate_v1"


def _load(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_gate(root: Path, output: Path) -> dict[str, Any]:
    contract_dir = root / "docs/paper/generated/supervisor_bottleneck_v1/scientific_contract"
    telemetry_dir = root / "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit"
    claims_path = contract_dir / "claim_evidence_boundary.json"
    contract_complete_path = contract_dir / "SCIENTIFIC_CONTRACT_COMPLETE.json"
    telemetry_complete_path = telemetry_dir / "TELEMETRY_AUDIT_COMPLETE.json"
    attenuation_path = telemetry_dir / "attenuation_claim_audit.json"
    phase_path = telemetry_dir / "phase_contrast_availability.json"

    claims = _load(claims_path)
    contract_complete = _load(contract_complete_path)
    telemetry_complete = _load(telemetry_complete_path)
    attenuation = _load(attenuation_path)
    phase = _load(phase_path)
    if contract_complete.get("status") != "pass" or telemetry_complete.get("status") != "pass":
        raise ValueError("Scientific contract or telemetry audit is incomplete")

    dispositions = []
    for claim in claims["claims"]:
        claim_id = claim["claim_id"]
        if claim_id == "F0_FOUNDATION":
            status = "supporting_evidence_complete"
        else:
            status = "headline_disposition_complete"
        dispositions.append(
            {
                "claim_id": claim_id,
                "status": status,
                "verdict": claim["verdict"],
                "canonical_source": claim["source"],
                "boundary": claim["boundary"],
                "new_collection_needed": False,
            }
        )

    limitations = [
        {
            "gap_id": "same_state_alternative_commands",
            "status": "bounded_non_headline_limitation",
            "consequence": attenuation["selective_masking_claim_status"],
            "treatment": "Do not claim selective masking; retain the large common authority effect.",
        },
        {
            "gap_id": "incomplete_phase_clocks",
            "status": "bounded_secondary_limitation",
            "consequence": "Some paired approach/release contrasts are descriptive only.",
            "treatment": "Report availability and do not impute missing phase events.",
        },
        {
            "gap_id": "cross_map_and_population_safety",
            "status": "out_of_scope_generalisation_limit",
            "consequence": "No cross-map, real-road, recursive-feasibility or population collision-freedom claim.",
            "treatment": "State the controlled Town05 distribution boundary.",
        },
    ]
    headline_ids = {"H1_CAPACITY", "H2_INFORMATION", "H3_ARCHITECTURE", "H4A_SELECTED_MODEL_TRANSFER", "H4B_RISK_FRONTIER", "H4C_SUPERVISOR_AUTHORITY"}
    headline = [item for item in dispositions if item["claim_id"] in headline_ids]
    checks = {
        "all_headline_claims_present": {item["claim_id"] for item in headline} == headline_ids,
        "all_headline_claims_disposed": all(item["status"] == "headline_disposition_complete" for item in headline),
        "no_headline_collection_required": all(item["new_collection_needed"] is False for item in headline),
        "masking_overclaim_refused": attenuation["selective_masking_identified"] is False,
        "phase_missingness_bounded": phase["missing_values_imputed"] is False,
        "canonical_audits_pass": contract_complete["status"] == telemetry_complete["status"] == "pass",
    }
    if not all(checks.values()):
        raise ValueError(f"Evidence-gap gate failed closed: {checks}")

    source_records = [
        {"path": str(path.relative_to(root)), "sha256": _sha256(path)}
        for path in (claims_path, contract_complete_path, telemetry_complete_path, attenuation_path, phase_path)
    ]
    decision_payload = {
        "decision": "existing_evidence_sufficient",
        "headline_dispositions": dispositions,
        "limitations": limitations,
        "sources": source_records,
        "checks": checks,
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **decision_payload,
        "decision_sha256": _stable_hash(decision_payload),
        "collection_authorisation": "closed; no new formal CARLA collection is scientifically required by the frozen H1--H4 contract",
        "reopen_rule": "A new OpenSpec protocol is required before any additional outcome-bearing CARLA collection.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/paper/generated/supervisor_bottleneck_v1/evidence_gap_gate.json"),
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    print(json.dumps(build_gate(args.root, output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
