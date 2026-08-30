#!/usr/bin/env python3
"""Materialise the frozen pre-freeze convergence gate without held-out access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_future_mask_v4_offline import audit_training_curves
from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()
    payload = audit_training_curves(args.training_root, args.manifest)
    payload["schema_version"] = "capacity_history_pre_freeze_training_curve_audit_v4"
    payload["manifest_sha256"] = sha256_file(args.manifest)
    payload["heldout_accessed"] = False
    payload["audit_sha256"] = sha256_payload(payload)
    atomic_json(args.output, payload)
    print(json.dumps({
        "status": payload["status"],
        "unresolved_boundary_underfit_runs": payload[
            "unresolved_boundary_underfit_runs"
        ],
        "audit_sha256": payload["audit_sha256"],
    }, indent=2, sort_keys=True))
    enforce_required_pass(payload, args.require_pass)


def enforce_required_pass(payload: dict[str, object], require_pass: bool) -> None:
    """Fail before calibration/held-out when the final convergence gate fails."""

    if require_pass and payload.get("status") != "pass":
        raise RuntimeError(
            "Final pre-held-out convergence audit failed: "
            f"{payload.get('unresolved_boundary_underfit_runs')}"
        )


if __name__ == "__main__":
    main()
