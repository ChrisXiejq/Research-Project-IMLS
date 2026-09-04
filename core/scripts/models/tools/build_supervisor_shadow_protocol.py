#!/usr/bin/env python3
"""Freeze the pre-outcome protocol for same-state supervisor masking tests."""

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


SCHEMA_VERSION = "supervisor_same_state_shadow_protocol_v1"
EXPECTED_CHANNELS = [
    "reference_shaping",
    "supervisor_forced_reference_linearization",
    "lane_entry_heading_cost",
    "rule_smpc_bypass",
    "post_solver_action_and_desired_speed",
    "release_recovery_state",
    "next_control_history",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_protocol(root: Path, output: Path) -> dict[str, Any]:
    sources = [
        _source(root, "core/scripts/carla/policies/smpc_agent.py"),
        _source(root, "core/scripts/carla/policies/supervisor_action_filter.py"),
        _source(root, "core/scripts/carla/utils/mpc_utils.py"),
        _source(root, "docs/paper/generated/capacity_history_v3/results/postprocess/selection_freeze.json"),
        _source(root, "docs/paper/generated/capacity_history_v3/results/closed_loop/CLOSED_LOOP_MANIFEST.json"),
    ]
    frozen = {
        "scientific_question": (
            "For the same factual planning state, how much predictor- or risk-policy "
            "command separation is created by SMPC, and how much remains after the "
            "complete rule-based supervisor mapping?"
        ),
        "causal_scope": (
            "Immediate same-state command transmission conditional on the frozen factual "
            "state distribution; not a long-horizon counterfactual trajectory or safety effect."
        ),
        "scenario": {
            "simulator": "CARLA 0.9.14",
            "map": "Town05",
            "traffic_side": "right-hand",
            "ego_manoeuvre": "left turn",
            "target_manoeuvre": "opposing straight priority movement",
            "target_styles": ["assertive_constant_speed", "defensive_reactive"],
            "camera_formal": False,
        },
        "factual_rollout_treatments": {
            "predictors": ["B1", "P_star"],
            "risk_policies": ["fixed_medium", "adaptive"],
            "supervisor_authority": "on",
            "ego_init_ids": list(range(116, 136)),
            "independent_unit": "ego_init_id",
            "planned_rollouts": 160,
            "factorisation": "2 predictor x 2 risk x 2 target x 20 init",
        },
        "shadow_factorial_per_state": {
            "predictors": ["B1", "P_star"],
            "risk_policies": ["fixed_medium", "adaptive"],
            "supervisor_mappings": ["enabled", "monitor_only"],
            "planned_shadow_branches": 8,
            "actuation_allowed": False,
            "factual_branch_parity_required": True,
        },
        "authority_channels": EXPECTED_CHANNELS,
        "required_state_freeze": [
            "ego and target state",
            "MultiPath raster/state/history input",
            "prediction modes, probabilities, per-step covariances",
            "reference trajectory and route progress",
            "SMPC previous control and warm-start snapshot",
            "solver and risk configuration",
            "factual and shadow supervisor behaviour states",
        ],
        "required_step_log": [
            "factual state key and ego_init_id",
            "branch predictor/risk/supervisor mapping",
            "risk tightening and required probability mass",
            "solver attempted/status/accepted/fallback/solve time",
            "nominal acceleration, steering and desired speed",
            "all seven supervisor candidate request/application flags",
            "post-supervisor acceleration, steering and desired speed",
            "proof that shadow branch was not actuated",
            "factual branch command parity",
        ],
        "primary_estimands": {
            "predictor_nominal_separation": "|u_nom(P*) - u_nom(B1)| at matched risk and mapping",
            "predictor_executed_separation": "|u_post(P*) - u_post(B1)| at matched risk",
            "risk_nominal_separation": "|u_nom(adaptive) - u_nom(fixed_medium)| at matched predictor and mapping",
            "risk_executed_separation": "|u_post(adaptive) - u_post(fixed_medium)| at matched predictor",
            "supervisor_attenuation": "Delta_post - Delta_monitor at the same state",
            "retention_ratio": "Delta_post / (Delta_monitor + epsilon), reported only above the frozen denominator threshold",
        },
        "primary_command_component": "longitudinal acceleration in m/s^2",
        "secondary_components": ["steering angle in rad", "desired speed in m/s"],
        "strata": ["any supervisor channel requested", "no supervisor channel requested"],
        "uncertainty": {
            "aggregation": "mean within ego_init_id before population aggregation",
            "bootstrap_unit": "ego_init_id",
            "bootstrap_resamples": 10000,
            "confidence_interval": 0.95,
            "random_seed": 20260825,
        },
        "decision_rules": {
            "command_level_masking": (
                "The upstream policy contrast is non-degenerate and the paired enabled-minus-"
                "monitor contrast reduces command separation with a 95% group-bootstrap interval below zero."
            ),
            "controller_insensitivity": (
                "The monitor-only nominal policy contrast is below the frozen denominator threshold; "
                "do not attribute the downstream null to the supervisor."
            ),
            "limited_power_or_unresolved": (
                "The interval crosses zero or parity/integrity gates fail; do not claim masking."
            ),
            "denominator_thresholds": {
                "acceleration_mps2": 0.05,
                "steering_rad": 0.005,
                "desired_speed_mps": 0.10,
            },
        },
        "solver_accounting": {
            "primary": "intention-to-shadow including declared fallback command",
            "secondary": "both compared branches controller-accepted",
            "missing_or_nonfinite": "fail closed for the affected state; reconcile counts",
        },
        "stopping_rule": (
            "Stop only after all 160 planned factual rollouts have valid receipts or after a "
            "predeclared infrastructure abort. No outcome-driven extension, cell replacement, "
            "threshold change or parameter search is allowed."
        ),
        "smoke_gate": [
            "shadow_actuation_count equals zero",
            "factual branch command equals the pre-shadow factual command within 1e-9",
            "all eight shadow branches are logged on every eligible planning step",
            "all seven authority channels are computed for enabled and monitor-only mappings",
            "factual trajectory is unchanged relative to shadow-disabled execution within declared deterministic tolerance",
        ],
        "sources": sources,
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "frozen_pre_outcome",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": frozen,
        "protocol_sha256": _stable_hash(frozen),
        "outcome_data_seen_before_freeze": False,
        "amendment_rule": "Any material amendment requires a new version and must precede outcome inspection.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate_protocol(payload: dict[str, Any]) -> dict[str, bool]:
    protocol = payload.get("protocol") or {}
    factual = protocol.get("factual_rollout_treatments") or {}
    shadow = protocol.get("shadow_factorial_per_state") or {}
    checks = {
        "frozen_before_outcomes": payload.get("status") == "frozen_pre_outcome" and payload.get("outcome_data_seen_before_freeze") is False,
        "twenty_independent_groups": factual.get("ego_init_ids") == list(range(116, 136)),
        "planned_rollouts_reconcile": factual.get("planned_rollouts") == 160,
        "eight_same_state_branches": shadow.get("planned_shadow_branches") == 8,
        "shadow_never_actuates": shadow.get("actuation_allowed") is False,
        "parity_required": shadow.get("factual_branch_parity_required") is True,
        "all_channels_present": protocol.get("authority_channels") == EXPECTED_CHANNELS,
        "cluster_bootstrap": (protocol.get("uncertainty") or {}).get("bootstrap_unit") == "ego_init_id",
        "fixed_stopping_rule": "No outcome-driven extension" in protocol.get("stopping_rule", ""),
        "source_hashes_present": all(len(item.get("sha256", "")) == 64 for item in protocol.get("sources", [])),
        "stable_hash_matches": payload.get("protocol_sha256") == _stable_hash(protocol),
    }
    if not all(checks.values()):
        raise ValueError(f"Shadow protocol validation failed: {checks}")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    default_root = Path(__file__).resolve().parents[4]
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/paper/generated/supervisor_masking_v2/protocol/SAME_STATE_SHADOW_PROTOCOL.json"),
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    payload = build_protocol(args.root.resolve(), output.resolve())
    checks = validate_protocol(payload)
    print(json.dumps({"status": "pass", "output": str(output), "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
