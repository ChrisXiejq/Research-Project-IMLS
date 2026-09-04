#!/usr/bin/env python3
"""Decide whether the supervisor-masking paper needs supplemental evidence.

The gate is intentionally conservative.  A physical authority effect licenses H1,
but H2/H3 use the word ``masking`` only when aligned same-state command evidence
or a non-saturated factorial interaction is available.
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
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "supervisor_masking_evidence_gap_gate_v1"


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_gate(
    contract_path: Path,
    evidence_path: Path,
    protocol_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    contract = _load(contract_path)
    evidence = _load(evidence_path)
    protocol = _load(protocol_path)

    if contract.get("status") != "pass":
        raise ValueError("Scientific contract is not complete")
    if evidence.get("status") != "pass":
        raise ValueError("Evidence analysis is not complete")
    if protocol.get("status") != "frozen_pre_outcome":
        raise ValueError("Supplemental protocol is not frozen pre-outcome")

    verdicts = evidence.get("identification_verdicts", {})
    aligned = bool(verdicts.get("same_state_alternative_commands_available"))
    factorial = bool(verdicts.get("non_saturated_policy_by_authority_factorial_available"))
    masking_identified = aligned or factorial

    h1 = evidence.get("H1_authority", {}).get("arms", {})
    h1_sufficient = (
        h1.get("on", {}).get("completion_successes") == 40
        and h1.get("on", {}).get("rollouts") == 40
        and h1.get("off", {}).get("completion_successes") == 0
        and h1.get("off", {}).get("rollouts") == 40
    )

    claims = {
        "H1_nominal_physical_authority_effect": {
            "decision": "existing_evidence_sufficient" if h1_sufficient else "material_gap_requires_collection",
            "licensed_wording": "The seven-channel rule-based authority bundle was decisive for nominal completion and yielding in the tested Town05 population.",
            "boundary": "Observed scenario-bounded effect; not formal, universal or real-road safety.",
        },
        "H2_predictor_advantage_is_masked_by_supervisor": {
            "decision": "existing_evidence_sufficient" if masking_identified else "material_gap_requires_collection",
            "licensed_wording_before_collection": "Predictor improvements were not uniformly transferred to physical outcomes; the current evidence does not isolate supervisor-caused masking.",
            "required_estimand": "same-state predictor command separation before and after the identical frozen authority mapping",
        },
        "H3_risk_allocation_advantage_is_masked_by_supervisor": {
            "decision": "existing_evidence_sufficient" if masking_identified else "material_gap_requires_collection",
            "licensed_wording_before_collection": "Risk allocation changed stochastic tightening, but its physical advantage was inconsistent and most command separation was already small at the nominal SMPC layer.",
            "required_estimand": "same-state fixed/adaptive command separation before and after the identical frozen authority mapping",
        },
    }
    headline_decision = (
        "existing_evidence_sufficient"
        if all(c["decision"] == "existing_evidence_sufficient" for c in claims.values())
        else "material_gap_requires_collection"
    )

    checks = {
        "contract_passes": contract.get("status") == "pass",
        "evidence_passes": evidence.get("status") == "pass",
        "h1_reason_is_explicit": h1_sufficient,
        "h2_reason_is_explicit": bool(claims["H2_predictor_advantage_is_masked_by_supervisor"]["required_estimand"]),
        "h3_reason_is_explicit": bool(claims["H3_risk_allocation_advantage_is_masked_by_supervisor"]["required_estimand"]),
        "masking_fails_closed_without_identification": masking_identified or headline_decision == "material_gap_requires_collection",
        "protocol_is_pre_outcome": protocol.get("outcome_data_seen_before_freeze") is False,
        "protocol_has_hash": len(str(protocol.get("protocol_sha256", ""))) == 64,
    }
    if not all(checks.values()):
        raise ValueError(f"Evidence-gap gate failed: {checks}")

    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "headline_decision": headline_decision,
        "claims": claims,
        "identification_state": {
            "same_state_alternative_commands_available": aligned,
            "non_saturated_factorial_available": factorial,
            "supervisor_specific_masking_identified": masking_identified,
        },
        "supplemental_protocol": {
            "path": str(protocol_path),
            "file_sha256": _sha256(protocol_path),
            "protocol_sha256": protocol["protocol_sha256"],
            "conditional_action": "implement_and_run" if headline_decision == "material_gap_requires_collection" else "not_required",
        },
        "sources": {
            "contract": {"path": str(contract_path), "sha256": _sha256(contract_path)},
            "evidence": {"path": str(evidence_path), "sha256": _sha256(evidence_path)},
        },
        "checks": checks,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_gate(args.contract, args.evidence, args.protocol, args.output)
    print(json.dumps({"status": result["status"], "headline_decision": result["headline_decision"], "checks": result["checks"]}, indent=2))


if __name__ == "__main__":
    main()
