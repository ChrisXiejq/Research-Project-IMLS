#!/usr/bin/env python3
"""Validate and freeze the prospective SF4 behavioural-authority experiment."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import copy
import hashlib
import json
import os
import random
import subprocess
from pathlib import Path
from typing import Any, Iterable


EXPECTED_INIT_IDS = tuple(range(106, 116))
SUPERVISOR_AUTHORITY_MODES = ("on", "off")
RISK_POLICIES = ("adaptive", "fixed_medium")
TARGET_STYLES = ("assertive", "reactive")
EXPECTED_ROLLOUTS = 80
ORDER_SEED = 20260814
BEHAVIORAL_TREATMENT_PATH = (
    "vehicle_role_overrides",
    "ego",
    "yield_supervisor_behavioural_authority_mode",
)
NONBEHAVIORAL_KEYS = frozenset(
    {"config_name", "description", "experimental_arm_label"}
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(value for value in path.rglob("*") if value.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(item).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def atomic_text(path: Path, rendered: str, *, frozen: bool = False) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        if frozen:
            raise ValueError(f"Frozen artifact drift: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: dict[str, Any], *, frozen: bool = False) -> None:
    atomic_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        frozen=frozen,
    )


def nested_get(payload: dict[str, Any], path: Iterable[str]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"Missing required config path: {'.'.join(path)}")
        value = value[key]
    return value


def behavioral_view(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in payload.items()
        if key not in NONBEHAVIORAL_KEYS
    }


def recursive_differences(
    left: Any, right: Any, path: tuple[str, ...] = ()
) -> list[tuple[str, ...]]:
    if isinstance(left, dict) and isinstance(right, dict):
        differences = []
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                differences.append(path + (str(key),))
            else:
                differences.extend(
                    recursive_differences(left[key], right[key], path + (str(key),))
                )
        return differences
    return [] if left == right else [path]


def arm_config(base: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode not in SUPERVISOR_AUTHORITY_MODES:
        raise ValueError(f"Unknown supervisor-authority mode: {mode}")
    value = copy.deepcopy(base)
    value["config_name"] = f"give_way_v15_supervisor_behavioural_authority_{mode}"
    value["experimental_arm_label"] = mode
    value["description"] = (
        "Frozen SF4 corrected reduced-intervention supervisor behavioural-authority arm generated from "
        "the committed v15 base. The sole behavioural arm field is "
        f"yield_supervisor_behavioural_authority_mode={mode}."
    )
    value["vehicle_role_overrides"]["ego"][
        "yield_supervisor_behavioural_authority_mode"
    ] = mode
    return value


def validate_config_pair(base: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if nested_get(base, ("carla_params", "terminate_on_collision")) is not True:
        raise ValueError("SF4 requires terminate_on_collision=true")
    if nested_get(
        base,
        ("vehicle_role_overrides", "ego", "yield_rule_smpc_bypass_enabled"),
    ) is not True:
        raise ValueError(
            "SF4 complete authority requires a common configured bypass candidate; "
            "production gates its factual effect by authority on/off"
        )
    if nested_get(
        base,
        ("vehicle_role_overrides", "ego", "yield_supervisor_mode"),
    ) != "reduced_intervention":
        raise ValueError("SF4 common supervisor must remain reduced_intervention")
    if nested_get(
        base,
        ("vehicle_role_overrides", "ego", "yield_post_solver_action_filter_mode"),
    ) != "apply":
        raise ValueError("SF4 requires the common internal action filter to remain apply")
    if nested_get(base, BEHAVIORAL_TREATMENT_PATH) != "on":
        raise ValueError("SF4 v15 base must declare behavioural authority on")
    arms = {mode: arm_config(base, mode) for mode in SUPERVISOR_AUTHORITY_MODES}
    differences = recursive_differences(
        behavioral_view(arms["on"]),
        behavioral_view(arms["off"]),
    )
    if differences != [BEHAVIORAL_TREATMENT_PATH]:
        rendered = [".".join(path) for path in differences]
        raise ValueError(
            "Supervisor-authority arms have confounded behavioral differences: "
            f"{rendered}"
        )
    return arms


def validate_init_candidates(init_dir: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    if manifest.get("status") != "candidate_requires_town05_spawn_preflight":
        raise ValueError("SF4 init manifest candidate status is invalid")
    records = manifest.get("records") or []
    ids = tuple(int(record["ego_init_id"]) for record in records)
    if ids != EXPECTED_INIT_IDS:
        raise ValueError(f"Expected init106--115 exactly, got {ids}")
    pairs = []
    for record in records:
        init_id = int(record["ego_init_id"])
        path = init_dir / f"ego_init_{init_id}.json"
        if not path.is_file() or sha256(path) != record.get("sha256"):
            raise ValueError(f"Init candidate hash mismatch: {path}")
        value = read_json(path)
        if set(value) != {"init_speed", "start_longitudinal_offset"}:
            raise ValueError(f"Unexpected init fields: {path}")
        speed = float(value["init_speed"])
        offset = float(value["start_longitudinal_offset"])
        if not (8.0 <= speed < 10.0 and -2.5 <= offset < 2.5):
            raise ValueError(f"Init candidate outside declared support: {path}")
        pairs.append((speed, offset))
    if len(set(pairs)) != len(pairs):
        raise ValueError("Duplicate SF4 init candidate pair")
    return manifest


def validate_prereg(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if value.get("status") != "frozen_before_outcomes":
        raise ValueError("SF4 preregistration is not prospectively frozen")
    if int((value.get("scope") or {}).get("expected_rollouts", -1)) != EXPECTED_ROLLOUTS:
        raise ValueError("SF4 preregistration does not freeze 80 rollouts")
    formula = str((value.get("primary_estimand") or {}).get("formula", ""))
    if "adaptive,on" not in formula or "adaptive,off" not in formula:
        raise ValueError("SF4 primary DID orientation is absent")
    if int((value.get("inference") or {}).get("bootstrap_replicates", -1)) != 10000:
        raise ValueError("SF4 cluster-bootstrap replicate count drift")
    smoke = (value.get("design") or {}).get("excluded_full_stack_smoke") or {}
    expected_smoke_cases = {
        ("fixed_on", "fixed_medium", "on"),
        ("fixed_off", "fixed_medium", "off"),
        ("adaptive_on", "adaptive", "on"),
        ("adaptive_off", "adaptive", "off"),
    }
    observed_smoke_cases = {
        (
            str(case.get("label")),
            str(case.get("risk_policy")),
            str(case.get("authority")),
        )
        for case in smoke.get("cases", [])
        if isinstance(case, dict)
    } if isinstance(smoke, dict) else set()
    if (
        not isinstance(smoke, dict)
        or int(smoke.get("count", -1)) != 4
        or int(smoke.get("excluded_init_id", -1)) != 105
        or smoke.get("excluded_from_formal_evidence") is not True
        or smoke.get("scientific_outcomes_may_be_read") is not False
        or observed_smoke_cases != expected_smoke_cases
    ):
        raise ValueError("SF4 excluded smoke does not cover the full 2x2 factorial")
    primary_definition = str(
        (value.get("primary_estimand") or {}).get("outcome_definition", "")
    )
    secondary = value.get("secondary_estimands") or {}
    secondary_outcomes = set(secondary.get("same_did_and_direct_effects") or [])
    behaviour_contract = secondary.get("behaviour_endpoint_definitions") or {}
    collision_contract = secondary.get("collision_and_separation_definitions") or {}
    yield_contract = str(secondary.get("yield_failure_definition", ""))
    if (
        "native CARLA collision" not in primary_definition
        or "zero-margin actual-bounding-box overlap" not in primary_definition
        or "0.25 m per-actor margin violation" not in primary_definition
        or not {
            "minimum_margin_adjusted_bbox_separation_m",
            "native_collision_any",
            "physical_bbox_overlap_any",
            "margin_adjusted_bbox_violation_any",
            "adverse_collision_any",
            "trajectory_inferred_yield_rule_failure",
        }.issubset(secondary_outcomes)
        or set(collision_contract)
        != {
            "native_collision_any",
            "physical_bbox_overlap_any",
            "margin_adjusted_bbox_violation_any",
            "minimum_margin_adjusted_bbox_separation_m",
            "adverse_collision_any",
        }
        or "fixed_geometry_yield_rules" not in yield_contract
        or "never defines the primary endpoint" not in yield_contract
    ):
        raise ValueError("SF4 prospective collision/separation definitions are absent")
    required_behaviour_outcomes = {
        "cautious_approach_progress_m",
        "first_stop_distance_to_conflict_m",
        "first_stop_distance_to_designed_stop_m",
        "stopped_duration_s",
        "nominal_conflict_clear_to_actual_path_release_s",
        "actual_path_release_to_sustained_resume_s",
        "buffered_conflict_clear_to_sustained_resume_s",
    }
    if (
        not required_behaviour_outcomes.issubset(secondary_outcomes)
        or set(behaviour_contract)
        != {
            "cautious_approach_progress_m",
            "first_stop_distance_to_conflict_m",
            "first_stop_distance_to_designed_stop_m",
            "stopped_duration_s",
            "missingness",
        }
        or "not automatically beneficial" not in str(
            behaviour_contract.get("cautious_approach_progress_m", "")
        )
        or "rather than the front bumper" not in str(
            behaviour_contract.get("first_stop_distance_to_conflict_m", "")
        )
        or "Positive means upstream/short" not in str(
            behaviour_contract.get("first_stop_distance_to_designed_stop_m", "")
        )
        or "never imputed" not in str(behaviour_contract.get("missingness", ""))
    ):
        raise ValueError("SF4 prospective approach/stop/release definitions are absent")
    wall_time = secondary.get(
        "computational_wall_time"
    ) or {}
    if (
        wall_time.get("clock") != "time.perf_counter"
        or "ego policy.run_step" not in str(wall_time.get("ego_policy_scope", ""))
        or "not an embedded deployment benchmark" not in str(
            wall_time.get("claim_boundary", "")
        )
    ):
        raise ValueError("SF4 prospective server wall-time scope is absent")
    return value


def validate_sources(args: argparse.Namespace) -> dict[str, Any]:
    base = read_json(args.base_tuning.resolve())
    arms = validate_config_pair(base)
    manifest = validate_init_candidates(
        args.init_dir.resolve(), args.init_manifest.resolve()
    )
    prereg = validate_prereg(args.prereg.resolve())
    scenario = read_json(args.scenario.resolve())
    if (scenario.get("carla_params") or {}).get("map_str") != "Town05":
        raise ValueError("SF4 scenario must be Town05")
    return {
        "status": "pass",
        "expected_rollouts": EXPECTED_ROLLOUTS,
        "treatment_difference": ".".join(BEHAVIORAL_TREATMENT_PATH),
        "base_tuning_sha256": sha256(args.base_tuning.resolve()),
        "arm_semantic_sha256": {
            mode: hashlib.sha256(
                json.dumps(
                    behavioral_view(config), sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            for mode, config in arms.items()
        },
        "init_manifest_sha256": sha256(args.init_manifest.resolve()),
        "init_ids": [int(item["ego_init_id"]) for item in manifest["records"]],
        "prereg_sha256": sha256(args.prereg.resolve()),
        "preregistered_primary_formula": prereg["primary_estimand"]["formula"],
        "scenario_sha256": sha256(args.scenario.resolve()),
    }


def execution_cells() -> list[dict[str, str]]:
    return [
        {
            "cell_id": f"SF4_B1_{policy}_{style}_supervisor_{mode}",
            "predictor": "B1",
            "risk_policy": policy,
            "target_style": style,
            "supervisor_authority_mode": mode,
        }
        for policy in RISK_POLICIES
        for style in TARGET_STYLES
        for mode in SUPERVISOR_AUTHORITY_MODES
    ]


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    source_audit = validate_sources(args)
    results = args.results_dir.resolve()
    results.mkdir(parents=True, exist_ok=True)
    base = read_json(args.base_tuning.resolve())
    arms = validate_config_pair(base)
    tuning_dir = results / "_frozen_tuning"
    tuning_paths = {}
    for mode, config in arms.items():
        path = tuning_dir / f"supervisor_authority_{mode}.json"
        atomic_json(path, config, frozen=True)
        tuning_paths[mode] = path

    spawn_preflight_path = args.spawn_preflight.resolve()
    spawn_preflight = read_json(spawn_preflight_path)
    if spawn_preflight.get("status") != "pass":
        raise ValueError("Town05 init spawn preflight has not passed")
    if spawn_preflight.get("formal_rollouts_launched") != 0:
        raise ValueError("Spawn preflight was not treatment-free")
    if spawn_preflight.get("init_manifest_sha256") != sha256(
        args.init_manifest.resolve()
    ):
        raise ValueError("Spawn preflight does not bind the current init manifest")

    deployment_path = args.deployment_preflight.resolve()
    deployment = read_json(deployment_path)
    if deployment.get("status") != "pass":
        raise ValueError("B1 deployment preflight failed")
    cells = execution_cells()
    rng = random.Random(ORDER_SEED)
    order = []
    for init_id in EXPECTED_INIT_IDS:
        block = [{**cell, "ego_init_id": init_id} for cell in cells]
        rng.shuffle(block)
        order.extend(block)
    if len(order) != EXPECTED_ROLLOUTS:
        raise AssertionError("Internal SF4 matrix cardinality error")

    repo = args.repo.resolve()
    source_paths = [path.resolve() for path in args.execution_source]
    for path in source_paths:
        if not path.is_file():
            raise ValueError(f"Missing execution source: {path}")
    init_hashes = {
        str(init_id): sha256(args.init_dir.resolve() / f"ego_init_{init_id}.json")
        for init_id in EXPECTED_INIT_IDS
    }
    init_values = {
        str(init_id): read_json(
            args.init_dir.resolve() / f"ego_init_{init_id}.json"
        )
        for init_id in EXPECTED_INIT_IDS
    }
    try:
        reactive_parameters = json.loads(args.reactive_config_json)
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid frozen reactive-config JSON") from error
    if not isinstance(reactive_parameters, dict) or not reactive_parameters:
        raise ValueError("Frozen reactive-config JSON must be a non-empty object")
    contract = {
        "schema_version": "sf4_supervisor_behavioural_authority_run_contract_v1",
        "status": "frozen_before_outcomes",
        "formal_evidence": True,
        "stage": "SF4 corrected-supervisor behavioural-authority causal ablation",
        "expected_rollouts": EXPECTED_ROLLOUTS,
        "independent_unit": "ego_init_id",
        "ego_init_ids": list(EXPECTED_INIT_IDS),
        "cells": cells,
        "execution_order_seed": ORDER_SEED,
        "execution_order_method": (
            "eight-condition treatment block shuffled independently within each "
            "init; init blocks ordered 106--115"
        ),
        "execution_order": order,
        "predictor": "B1_seed37_calibrated",
        "risk_policies": list(RISK_POLICIES),
        "target_styles": list(TARGET_STYLES),
        "supervisor_authority_modes": list(SUPERVISOR_AUTHORITY_MODES),
        "primary_did": (
            "(adaptive-fixed_medium)_on - "
            "(adaptive-fixed_medium)_off"
        ),
        "direct_paired_effects": [
            "adaptive_on-fixed_medium_on",
            "adaptive_off-fixed_medium_off",
            "adaptive_on-adaptive_off",
            "fixed_medium_on-fixed_medium_off"
        ],
        "server_wall_time_contract": {
            "schema_version": "server_wall_time_diagnostics_v1",
            "clock": "time.perf_counter",
            "raw_columns": [
                "ego_policy_run_step_wall_time_s",
                "ego_policy_done_after_step",
                "prediction_pipeline_wall_time_s",
            ],
            "active_planning_definition": (
                "ego policy.done() is false immediately after run_step"
            ),
            "rollout_statistics": [
                "p50", "p95", "p99", "fraction_gt_50ms",
                "fraction_gt_200ms", "fraction_gt_500ms",
            ],
            "inferential_unit": "ego_init_id paired cluster",
            "server_side_diagnostic_only": True,
            "deployment_or_real_time_guarantee": False,
        },
        "common_controller_contract": {
            "yield_supervisor_mode": "reduced_intervention",
            "yield_rule_smpc_bypass_enabled": True,
            "yield_post_solver_action_filter_mode": "apply",
            "terminate_on_collision": True,
            "only_behavioral_arm_difference": ".".join(BEHAVIORAL_TREATMENT_PATH),
            "authority_off_allowed_solver_influence": [
                "interaction_estimator_to_adaptive_risk_allocation"
            ],
            "authority_off_disabled_channels": [
                "reference_shaping",
                "supervisor_forced_reference_linearization",
                "lane_entry_heading_cost",
                "post_solver_action_replacement",
                "release_recovery_reference_and_control",
                "next_step_control_history",
                "rule_smpc_bypass",
            ]
        },
        "scenario": {
            "map": "Town05",
            "fps": 20,
            "max_iters": 600,
            "max_duration_s": 30.0,
            "source_sha256": sha256(args.scenario.resolve()),
        },
        "prediction_protocol_id": str(args.prediction_protocol_id),
        "risk_profiles": {
            "adaptive": "adaptive_interaction_severity",
            "fixed_medium": "fixed_frontier_medium",
        },
        "target_styles_runtime": {
            "assertive": "assertive_constant_speed",
            "reactive": "defensive_reactive",
        },
        "target_conditions": {
            "start_longitudinal_offset_m": 0.0,
            "init_speed_mps": 9.0,
            "nominal_speed_mps": 9.0,
        },
        "reactive_parameters": reactive_parameters,
        "adaptive_parameters": {
            "variant_name": "floor_weak",
            "approach_preclearance_floor": 1.66,
            "critical_preclearance_floor": 1.72,
            "near_preclearance_floor": 1.78,
        },
        "fixed_policy": {
            "label": "original_fixed_medium",
            "risk_profile": "fixed_frontier_medium",
        },
        "retry_policy": {
            "max_attempts": int(args.max_attempts),
            "infrastructure_only": True,
            "scientific_outcomes_never_retried": True,
            "completed_rollouts_never_repeated": True,
        },
        "hashes": {
            "prereg_json": sha256(args.prereg.resolve()),
            "prereg_md": sha256(args.prereg_md.resolve()),
            "base_tuning": sha256(args.base_tuning.resolve()),
            "supervisor_authority_tuning": {
                mode: sha256(path) for mode, path in tuning_paths.items()
            },
            "init_manifest": sha256(args.init_manifest.resolve()),
            "init_files": init_hashes,
            "spawn_preflight": sha256(spawn_preflight_path),
            "deployment_preflight": sha256(deployment_path),
            "execution_sources": {
                str(path.relative_to(repo)): sha256(path) for path in source_paths
            },
            "b1_model_tree": tree_sha256(args.b1_model.resolve()),
            "b1_calibration": sha256(args.b1_calibration.resolve()),
            "anchors": sha256(args.anchors.resolve()),
        },
        "paths_relative_to_results": {
            "supervisor_authority_tuning": {
                mode: str(path.relative_to(results)) for mode, path in tuning_paths.items()
            }
        },
        "init_values": init_values,
        "git_commit": subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_validation": source_audit,
        "no_post_outcome_tuning": True,
    }
    contract_path = (
        results / "sf4_supervisor_behavioural_authority_run_contract.json"
    )
    atomic_json(contract_path, contract, frozen=True)
    return {
        "status": "pass",
        "contract": str(contract_path),
        "contract_sha256": sha256(contract_path),
        "expected_rollouts": EXPECTED_ROLLOUTS,
        "tuning_paths": {mode: str(path) for mode, path in tuning_paths.items()},
    }


def progress(args: argparse.Namespace) -> dict[str, Any]:
    root = args.results_dir.resolve()
    contract_path = (
        root / "sf4_supervisor_behavioural_authority_run_contract.json"
    )
    if not contract_path.is_file():
        return {
            "status": "not_prepared",
            "expected_rollouts": EXPECTED_ROLLOUTS,
            "accepted_rollouts": 0,
            "pending_rollouts": EXPECTED_ROLLOUTS,
        }
    contract = read_json(contract_path)
    accepted, pending = [], []
    for item in contract["execution_order"]:
        receipt = (
            root
            / item["cell_id"]
            / f"SF4_ROLLOUT_{item['ego_init_id']}_COMPLETE.json"
        )
        target = {"cell_id": item["cell_id"], "ego_init_id": item["ego_init_id"]}
        try:
            from r3_attempt_manager import valid_receipt

            valid = valid_receipt(
                root / item["cell_id"], item["cell_id"],
                int(item["ego_init_id"]), "SF4",
            )
        except (ImportError, OSError, ValueError, TypeError):
            valid = False
        (accepted if valid else pending).append({**target, "receipt": str(receipt)})
    return {
        "schema_version": "sf4_supervisor_behavioural_authority_progress_v1",
        "status": "complete" if not pending else "in_progress",
        "expected_rollouts": int(contract["expected_rollouts"]),
        "accepted_rollouts": len(accepted),
        "pending_rollouts": len(pending),
        "next_pending": pending[:20],
    }


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--base-tuning", required=True, type=Path)
    parser.add_argument("--init-dir", required=True, type=Path)
    parser.add_argument("--init-manifest", required=True, type=Path)
    parser.add_argument("--prereg", required=True, type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-sources")
    add_common(validate)
    prepare_parser = commands.add_parser("prepare")
    add_common(prepare_parser)
    prepare_parser.add_argument("--prereg-md", required=True, type=Path)
    prepare_parser.add_argument("--results-dir", required=True, type=Path)
    prepare_parser.add_argument("--spawn-preflight", required=True, type=Path)
    prepare_parser.add_argument("--deployment-preflight", required=True, type=Path)
    prepare_parser.add_argument("--repo", required=True, type=Path)
    prepare_parser.add_argument("--b1-model", required=True, type=Path)
    prepare_parser.add_argument("--b1-calibration", required=True, type=Path)
    prepare_parser.add_argument("--anchors", required=True, type=Path)
    prepare_parser.add_argument("--max-attempts", default=10, type=int)
    prepare_parser.add_argument("--prediction-protocol-id", required=True)
    prepare_parser.add_argument("--reactive-config-json", required=True)
    prepare_parser.add_argument(
        "--execution-source", required=True, action="append", type=Path
    )
    progress_parser = commands.add_parser("progress")
    progress_parser.add_argument("--results-dir", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "validate-sources":
        payload = validate_sources(args)
    elif args.command == "prepare":
        payload = prepare(args)
    else:
        payload = progress(args)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
