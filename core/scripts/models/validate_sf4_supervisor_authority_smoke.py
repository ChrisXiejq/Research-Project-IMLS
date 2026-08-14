#!/usr/bin/env python3
"""Validate the excluded init105 SF4 full-stack runtime smoke cases.

The smoke gate reads implementation telemetry only.  It never computes or
judges collision, completion, timing, separation, or any directional outcome.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


CASES = {
    "fixed_on": {"mode": "on", "risk": "fixed_medium", "policy": "smpc_fixed_risk"},
    "fixed_off": {"mode": "off", "risk": "fixed_medium", "policy": "smpc_fixed_risk"},
    "adaptive_on": {"mode": "on", "risk": "adaptive", "policy": "smpc_var_risk"},
    "adaptive_off": {"mode": "off", "risk": "adaptive", "policy": "smpc_var_risk"},
}
NEUTRAL_STATE = {
    "yield_stop_seen": False,
    "yield_stop_active_prev": False,
    "yield_recovery_steps_remaining": 0,
    "yield_last_applied_accel": None,
}
PRE_SOLVER_CANDIDATE_CHANNELS = {
    "reference_states",
    "reference_inputs",
    "linearization_states",
    "linearization_inputs",
    "heading_cost_weights",
    "yield_reference_active",
    "recovery_reference_active",
    "supervisor_forced_reference_linearization",
}
COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS = {
    "reference_shaping",
    "supervisor_forced_reference_linearization",
    "lane_entry_heading_cost",
    "rule_smpc_bypass",
    "post_solver_action_and_desired_speed",
    "release_recovery_state",
    "next_control_history",
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Smoke debug telemetry absent or malformed: {path}")
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def truthy(value: Any) -> bool:
    return value is True or value in (1, "1", "true", "True")


def commands(record: Mapping[str, Any], key: str) -> tuple[float, float, float]:
    value = record.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"Smoke post-action record missing {key}")
    return tuple(float(value[name]) for name in ("a_des", "df_des", "v_des"))  # type: ignore[return-value]


def equal(left: Sequence[float], right: Sequence[float]) -> bool:
    return all(abs(a - b) <= 1.0e-8 for a, b in zip(left, right))


def validate_wall_time_instrumentation(
    scenario: Path, summary: Mapping[str, Any]
) -> dict[str, int]:
    path = scenario / "scenario_steps.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    required = {
        "ego_policy_run_step_wall_time_s",
        "ego_policy_done_after_step",
        "prediction_pipeline_wall_time_s",
    }
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Smoke server wall-time columns are missing")
    active = 0
    for row in rows:
        done = str(row["ego_policy_done_after_step"]).strip().lower()
        if done not in {"true", "false", "1", "0"}:
            raise ValueError("Smoke ego-policy done marker is invalid")
        active += int(done in {"false", "0"})
        for column in (
            "ego_policy_run_step_wall_time_s",
            "prediction_pipeline_wall_time_s",
        ):
            try:
                value = float(row[column])
            except (TypeError, ValueError):
                raise ValueError("Smoke wall-time sample is not numeric")
            if not math.isfinite(value) or value < 0.0:
                raise ValueError("Smoke wall-time sample is non-finite")
    diagnostics = (summary.get("extra") or {}).get(
        "server_wall_time_diagnostics"
    ) or {}
    all_policy = diagnostics.get("ego_policy_all_invocations") or {}
    active_policy = diagnostics.get(
        "ego_policy_active_planning_invocations"
    ) or {}
    if (
        diagnostics.get("schema_version") != "server_wall_time_diagnostics_v1"
        or diagnostics.get("clock") != "time.perf_counter"
        or diagnostics.get("server_side_diagnostic_only") is not True
        or diagnostics.get("deployment_or_real_time_guarantee") is not False
        or int(all_policy.get("observed_sample_count", -1)) != len(rows)
        or int(all_policy.get("nonfinite_sample_count", -1)) != 0
        or int(all_policy.get("exception_count", -1)) != 0
        or int(active_policy.get("observed_sample_count", -1)) != active
        or int(active_policy.get("nonfinite_sample_count", -1)) != 0
        or int(active_policy.get("exception_count", -1)) != 0
        or active <= 0
    ):
        raise ValueError("Smoke wall-time summary/provenance is invalid")
    return {"all_invocations_checked": len(rows), "active_invocations_checked": active}


def audit_pass(value: Any, mode: str) -> bool:
    if not isinstance(value, Mapping) or value.get("status") != "pass" or value.get("mode") != mode:
        return False
    channels = value.get("channels")
    if not isinstance(channels, Mapping) or not channels:
        return False
    if mode == "off":
        return all(
            isinstance(channel, Mapping)
            and (
                truthy(channel.get("equal"))
                or truthy(channel.get("adaptive_risk_only_exception"))
            )
            for channel in channels.values()
        )
    return True


def validate_case(root: Path, label: str, expected: Mapping[str, str]) -> dict[str, Any]:
    case_root = root / "_smoke" / label
    scenarios = sorted(
        path for path in case_root.glob("scenario_uk_give_way_ego_init_105_*")
        if path.is_dir()
    )
    if len(scenarios) != 1:
        raise ValueError(f"Expected one {label} scenario directory, got {scenarios}")
    scenario = scenarios[0]
    if not scenario.name.endswith(expected["policy"]):
        raise ValueError(f"Smoke policy mismatch for {label}: {scenario.name}")
    setup_path = scenario / "smpc_debug_setup.json"
    steps_path = scenario / "smpc_debug_steps.jsonl"
    rollout_path = scenario / "scenario_rollout_config.json"
    setup = read_json(setup_path)
    rollout = read_json(rollout_path)
    summary = read_json(scenario / "scenario_run_summary.json")
    rows = read_jsonl(steps_path)
    timing_counts = validate_wall_time_instrumentation(scenario, summary)
    setup_supervisor = setup.get("yield_stop_supervisor") or {}
    authority_setup = setup_supervisor.get("behavioural_authority") or {}
    filter_setup = setup_supervisor.get("post_solver_action_filter") or {}
    mode = expected["mode"]
    effective_filter = "apply" if mode == "on" else "monitor_only"
    if (
        authority_setup.get("mode") != mode
        or truthy(authority_setup.get("authority_enabled")) != (mode == "on")
        or setup_supervisor.get("rule_smpc_bypass_enabled") is not True
        or filter_setup.get("configured_mode") != "apply"
        or filter_setup.get("mode") != effective_filter
    ):
        raise ValueError(f"Smoke setup authority mismatch for {label}")
    ego = next(
        (
            item for item in rollout.get("effective_runtime_vehicle_params", [])
            if isinstance(item, Mapping) and item.get("role") == "ego"
        ),
        {},
    )
    if (
        ego.get("yield_supervisor_behavioural_authority_mode") != mode
        or ego.get("yield_post_solver_action_filter_mode") != "apply"
        or ego.get("yield_rule_smpc_bypass_enabled") is not True
    ):
        raise ValueError(f"Smoke effective runtime config mismatch for {label}")

    adaptive_solver_observed = False
    bypass_requested_steps = 0
    bypass_applied_steps = 0
    factual_solver_attempts = 0
    for row in rows:
        bypass = row.get("solver_bypass") or {}
        shadow_bypass = truthy(bypass.get("shadow_requested"))
        effective_bypass = truthy(bypass.get("enabled"))
        if (
            not truthy(bypass.get("configuration_enabled"))
            or bypass.get("authority_mode") != mode
            or not truthy(bypass.get("authority_gated"))
            or not truthy(bypass.get("off_always_executes_solver"))
            or (mode == "on" and effective_bypass != shadow_bypass)
            or (mode == "off" and effective_bypass)
        ):
            raise ValueError(f"Smoke bypass authority semantics failed in {label}")
        bypass_requested_steps += int(shadow_bypass)
        bypass_applied_steps += int(effective_bypass)
        factual_solver_attempts += int(not effective_bypass)
        authority = row.get("supervisor_behavioural_authority") or {}
        implementation = authority.get("implementation_manipulation_gate") or {}
        reference = authority.get("reference_and_solver_input_audit") or {}
        solver_inputs = reference.get("solver_input_authority") or {}
        candidate_application = (
            reference.get("candidate_application_authority") or {}
        )
        candidate_channels = candidate_application.get("channels") or {}
        complete_manifest = (
            authority.get("complete_candidate_channel_manifest") or {}
        )
        complete_channels = complete_manifest.get("channels") or {}
        post = authority.get("post_action_and_next_state_audit") or {}
        estimator = authority.get("interaction_risk_estimator_state") or {}
        if (
            authority.get("schema_version") != "supervisor_behavioural_authority_step_v1"
            or authority.get("mode") != mode
            or truthy(authority.get("authority_enabled")) != (mode == "on")
            or implementation.get("status") != "pass"
            or not truthy(implementation.get("shadow_state_isolated"))
            or set(implementation.get("candidate_channels_computed") or [])
            != COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS
            or not audit_pass(reference, mode)
            or not audit_pass(solver_inputs, mode)
            or candidate_application.get("schema_version")
            != "supervisor_candidate_application_channels_v1"
            or candidate_application.get("mode") != mode
            or candidate_application.get("status") != "pass"
            or truthy(candidate_application.get("candidate_equality_required"))
            != (mode == "on")
            or not isinstance(candidate_channels, Mapping)
            or set(candidate_channels) != PRE_SOLVER_CANDIDATE_CHANNELS
            or (
                mode == "on"
                and not all(
                    isinstance(channel, Mapping)
                    and truthy(channel.get("equal"))
                    for channel in candidate_channels.values()
                )
            )
            or complete_manifest.get("schema_version")
            != "complete_supervisor_behavioural_authority_manifest_v1"
            or complete_manifest.get("mode") != mode
            or complete_manifest.get("status") != "pass"
            or set(complete_manifest.get("expected_channels") or [])
            != COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS
            or set(complete_channels)
            != COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS
            or any(
                not isinstance(channel, Mapping)
                or channel.get("candidate_computed") is not True
                or channel.get("authority_assignment_consistent") is not True
                or (
                    mode == "on"
                    and truthy(channel.get("applied"))
                    != truthy(channel.get("requested"))
                )
                or (
                    mode == "off"
                    and (
                        truthy(channel.get("applied"))
                        or channel.get("factual_neutral_when_off") is not True
                    )
                )
                for channel in complete_channels.values()
            )
            or not audit_pass(post, mode)
            or estimator.get("permitted_factual_use_when_authority_off")
            != ["adaptive_risk_allocation"]
            or estimator.get("nonrisk_solver_or_control_use_when_authority_off")
            is not False
            or authority.get("rule_smpc_bypass_configured") is not True
        ):
            raise ValueError(f"Smoke channel/isolation audit failed in {label}")
        if mode == "off" and (
            authority.get("factual_behaviour_state_before_solve") != NEUTRAL_STATE
            or authority.get("factual_behaviour_state_after_action") != NEUTRAL_STATE
        ):
            raise ValueError(f"Smoke factual supervisor-state leakage in {label}")
        state = row.get("yield_stop_supervisor") or {}
        record = state.get("post_solver_action_filter") or {}
        nominal = commands(record, "nominal_solver_command")
        candidate = commands(record, "supervisor_candidate_command")
        actual = commands(record, "actual_command")
        if record.get("mode") != effective_filter:
            raise ValueError(f"Smoke post-action mode mismatch in {label}")
        if mode == "on" and not equal(actual, candidate):
            raise ValueError(f"Smoke authority-on did not apply candidate in {label}")
        if mode == "off" and not equal(actual, nominal):
            raise ValueError(f"Smoke authority-off did not retain nominal action in {label}")
        adaptive_solver_observed = adaptive_solver_observed or truthy(
            (row.get("risk") or {}).get("solver_uses_adaptive_risk")
        )
    if expected["risk"] == "adaptive" and not adaptive_solver_observed:
        raise ValueError(
            f"Adaptive-risk smoke never exercised the adaptive solver path: {label}"
        )
    if expected["risk"] == "fixed_medium" and adaptive_solver_observed:
        raise ValueError(f"Fixed-risk smoke unexpectedly used adaptive risk: {label}")
    return {
        "label": label,
        "mode": mode,
        "risk_policy": expected["risk"],
        "ego_init_id": 105,
        "debug_steps_checked": len(rows),
        "adaptive_risk_solver_path_observed": adaptive_solver_observed,
        "bypass_requested_steps": bypass_requested_steps,
        "bypass_applied_steps": bypass_applied_steps,
        "factual_solver_attempts": factual_solver_attempts,
        "wall_time_instrumentation": {
            **timing_counts,
            "values_or_direction_exposed": False,
        },
        "setup_sha256": sha256(setup_path),
        "debug_steps_sha256": sha256(steps_path),
        "rollout_config_sha256": sha256(rollout_path),
        "status": "pass",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.results_dir.resolve()
    formal_receipts = [
        path for path in root.glob("SF4_*/SF4_ROLLOUT_*_COMPLETE.json")
        if "_smoke" not in path.parts
    ]
    if formal_receipts:
        raise SystemExit("SF4 smoke must be frozen before every formal receipt")
    contract = read_json(args.contract.resolve())
    if (
        contract.get("schema_version")
        != "sf4_supervisor_behavioural_authority_run_contract_v1"
    ):
        raise SystemExit("Unexpected SF4 contract schema for smoke")
    records = [validate_case(root, label, expected) for label, expected in CASES.items()]
    payload = {
        "schema_version": "sf4_supervisor_behavioural_authority_smoke_v1",
        "status": "pass",
        "formal_rollouts_observed": 0,
        "formal_evidence": False,
        "excluded_init_id": 105,
        "excluded_from_80_rollout_analysis": True,
        "runtime_and_implementation_diagnostics_only": True,
        "scientific_outcomes_read_or_used_for_tuning": False,
        "direction_dependent_decisions_allowed": False,
        "contract_sha256": sha256(args.contract.resolve()),
        "records": records,
    }
    output = args.output.resolve()
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output.is_file() and output.read_text(encoding="utf-8") != rendered:
        raise SystemExit("Frozen SF4 smoke marker drift")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, output)
    print(rendered, end="")


if __name__ == "__main__":
    main()
