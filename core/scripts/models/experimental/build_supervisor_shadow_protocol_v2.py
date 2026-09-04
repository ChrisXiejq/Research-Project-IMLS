#!/usr/bin/env python3
"""Freeze the event-anchored amendment to the same-state shadow protocol."""

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
from typing import Any

try:
    from core.scripts.models.tools.build_supervisor_shadow_protocol import (
        EXPECTED_CHANNELS,
        _stable_hash,
    )
except ModuleNotFoundError:  # Direct ``python path/to/script.py`` execution.
    from build_supervisor_shadow_protocol import EXPECTED_CHANNELS, _stable_hash


SCHEMA_VERSION = "supervisor_same_state_shadow_protocol_v2"
ANCHORS = [
    "first_valid_inactive",
    "activation_first",
    "sustained_active_after_3_updates",
    "release_first",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_label(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def build_protocol(root: Path, v1_path: Path, output: Path) -> dict[str, Any]:
    v1 = json.loads(v1_path.read_text(encoding="utf-8"))
    if v1.get("status") != "frozen_pre_outcome":
        raise ValueError("Protocol v1 is not frozen pre-outcome")
    if v1.get("protocol_sha256") != _stable_hash(v1.get("protocol")):
        raise ValueError("Protocol v1 hash mismatch")

    frozen = json.loads(json.dumps(v1["protocol"]))
    frozen["eligibility_schedule"] = {
        "amendment_reason": "Reduce redundant repeated solves while retaining transition and active/inactive command mappings; amendment frozen before any supplemental command outcome is inspected.",
        "selection_uses": ["valid planning state", "factual any-channel request transition", "three-update active dwell"],
        "selection_never_uses": ["command magnitude", "policy separation", "collision", "completion", "minimum separation", "statistical result"],
        "event_anchors": ANCHORS,
        "definitions": {
            "first_valid_inactive": "First valid planning state with no factual supervisor channel requested.",
            "activation_first": "First valid state on the false-to-true factual any-channel request transition.",
            "sustained_active_after_3_updates": "Third consecutive valid planning update with a factual request active.",
            "release_first": "First valid state on the true-to-false factual any-channel request transition.",
        },
        "maximum_selected_states_per_rollout": 4,
        "planned_state_upper_bound": 640,
        "structurally_missing_anchor": "Log as missing and do not replace or extend the population.",
        "buffered_past_actor_state_replay": False,
    }
    frozen["shadow_factorial_per_state"].update({
        "controller_solve_policy": "Evaluate enabled and monitor-only separately whenever upstream authority changes reference shaping, linearisation, cost or bypass; reuse is allowed only with an explicit mathematical-identity receipt.",
        "maximum_branch_evaluations_per_selected_state": 8,
    })
    frozen["required_state_freeze"].append(
        "proof that every shadow solver callback consumes the captured state rather than querying an advanced CARLA actor"
    )
    frozen["stopping_rule"] = (
        "Stop only after all 160 planned factual rollouts have valid receipts or after a predeclared infrastructure abort. "
        "Evaluate only the four prospectively defined event anchors; record structurally missing anchors without replacement. "
        "No outcome-driven extension, cell replacement, threshold change, anchor change or parameter search is allowed."
    )
    frozen["smoke_gate"] = [
        item.replace("every eligible planning step", "every selected event-anchor state")
        for item in frozen["smoke_gate"]
    ] + [
        "anchor selection is invariant to command magnitude and physical outcomes",
        "shadow callbacks do not query actor state after capture",
    ]
    frozen["sources"].append({
        "path": _source_label(root, v1_path),
        "bytes": v1_path.stat().st_size,
        "sha256": _sha256(v1_path),
    })

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "frozen_pre_outcome",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": frozen,
        "protocol_sha256": _stable_hash(frozen),
        "outcome_data_seen_before_freeze": False,
        "supersedes": {
            "schema_version": v1["schema_version"],
            "path": _source_label(root, v1_path),
            "file_sha256": _sha256(v1_path),
            "protocol_sha256": v1["protocol_sha256"],
        },
        "amendment_class": "runtime_reduction_without_outcome_selection",
        "amendment_rule": "Any later material amendment requires a new version and must precede supplemental outcome inspection.",
    }
    validate_protocol(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate_protocol(payload: dict[str, Any]) -> dict[str, bool]:
    protocol = payload.get("protocol") or {}
    eligibility = protocol.get("eligibility_schedule") or {}
    checks = {
        "v2_frozen_before_outcomes": payload.get("status") == "frozen_pre_outcome" and payload.get("outcome_data_seen_before_freeze") is False,
        "v1_superseded_with_hash": len((payload.get("supersedes") or {}).get("file_sha256", "")) == 64,
        "twenty_groups_and_160_rollouts_preserved": (protocol.get("factual_rollout_treatments") or {}).get("ego_init_ids") == list(range(116, 136)) and (protocol.get("factual_rollout_treatments") or {}).get("planned_rollouts") == 160,
        "four_anchors_exact": eligibility.get("event_anchors") == ANCHORS and eligibility.get("maximum_selected_states_per_rollout") == 4,
        "no_outcome_selection": "command magnitude" in eligibility.get("selection_never_uses", []) and "collision" in eligibility.get("selection_never_uses", []),
        "no_replacement": "do not replace" in eligibility.get("structurally_missing_anchor", ""),
        "no_buffered_actor_replay": eligibility.get("buffered_past_actor_state_replay") is False,
        "eight_branches_and_all_channels": (protocol.get("shadow_factorial_per_state") or {}).get("planned_shadow_branches") == 8 and protocol.get("authority_channels") == EXPECTED_CHANNELS,
        "shadow_never_actuates": (protocol.get("shadow_factorial_per_state") or {}).get("actuation_allowed") is False,
        "stable_hash_matches": payload.get("protocol_sha256") == _stable_hash(protocol),
    }
    if not all(checks.values()):
        raise ValueError(f"Protocol v2 validation failed: {checks}")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    default_root = Path(__file__).resolve().parents[4]
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--v1", type=Path, default=Path("docs/paper/generated/supervisor_masking_v2/protocol/SAME_STATE_SHADOW_PROTOCOL.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/paper/generated/supervisor_masking_v2/protocol/SAME_STATE_SHADOW_PROTOCOL_V2.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    v1 = args.v1 if args.v1.is_absolute() else root / args.v1
    output = args.output if args.output.is_absolute() else root / args.output
    payload = build_protocol(root, v1.resolve(), output.resolve())
    print(json.dumps({"status": "pass", "checks": validate_protocol(payload), "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
