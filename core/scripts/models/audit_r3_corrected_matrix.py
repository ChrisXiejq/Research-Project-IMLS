#!/usr/bin/env python3
"""Integrity audit for the prospective corrected R3 closed-loop matrix.

Adverse scientific outcomes (collision, yield failure or completion failure)
are counted, never converted into missing data.  Only provenance, numerical,
coverage and telemetry defects make this audit fail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import re
from collections import defaultdict
from pathlib import Path

import numpy as np


CORRECTED = "corrected_joint_modes_shared_amin_v1"
MODE_MAP = [[0], [1], [2]]
RISK_PROFILES = {
    "fixed_aggressive": "fixed_frontier_aggressive",
    "fixed_medium": "fixed_frontier_medium",
    "fixed_conservative": "fixed_frontier_conservative",
    "adaptive": "adaptive_interaction_severity",
}
FIXED_RISK_TIGHTENING = {
    "fixed_aggressive": 1.2815515655446004,
    "fixed_medium": 1.64,
    "fixed_conservative": 2.053748910631823,
}
SCENARIO_VALIDITY_COLLISION_CATEGORIES = {
    "target_infrastructure",
    "target_static_vehicle",
}
EXPECTED_FOOTPRINT_SENSITIVITY_MARGINS = {"0", "0.25", "0.35", "0.5"}
R3_RAW_REQUIRED_FILES = (
    "scenario_run_summary.json",
    "scenario_rollout_config.json",
    "smpc_debug_setup.json",
    "prediction_deployment_manifest.json",
    "prediction_dataset/prediction_dataset_config.json",
    "prediction_dataset/prediction_dataset_manifest.json",
    "smpc_debug_steps.jsonl",
    "prediction_dataset/prediction_dataset_raw.jsonl",
    "prediction_dataset/prediction_dataset_labeled.jsonl",
    "scenario_result.pkl",
    "scenario_steps.csv",
)
R3_RAW_OPTIONAL_FILES = ("smpc_completion.json",)


def _close(observed: object, expected: object, tolerance: float = 1e-12) -> bool:
    try:
        return math.isclose(float(observed), float(expected), abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def _as_int(value: object, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def raw_evidence_sha256(scenario_dir: Path) -> str:
    digest = hashlib.sha256()
    for relative in R3_RAW_REQUIRED_FILES + R3_RAW_OPTIONAL_FILES:
        path = scenario_dir / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(
            sha256(path).encode("ascii") if path.is_file() else b"ABSENT_BY_DESIGN"
        )
        digest.update(b"\n")
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def preflight_semantics(value: dict) -> dict:
    """Exclude nondeterministic GPU float diagnostics from the resume contract."""

    return {
        "status": value.get("status"),
        "selected_variant": value.get("selected_variant"),
        "selected_seed": value.get("selected_seed"),
        "selection_freeze_sha256": value.get("selection_freeze_sha256"),
        "anchors": value.get("anchors"),
        "normalization": value.get("normalization"),
        "warmup_input": value.get("warmup_input"),
        "b1_deployment": (value.get("b1") or {}).get("deployment"),
        "b0_deployment": (value.get("b0") or {}).get("deployment"),
    }


def semantic_sha256(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def valid_hash(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def finite_summary(value: dict) -> bool:
    return int(value.get("nan_count", -1)) == 0 and float(value.get("finite_frac", 0.0)) == 1.0


def finite_numeric(value: object) -> bool:
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return False
    return bool(array.size and np.isfinite(array).all())


def scenario_init_id(name: str) -> int:
    match = re.search(r"_ego_init_(\d+)_", name)
    if not match:
        raise ValueError(f"Cannot parse init ID: {name}")
    return int(match.group(1))


def deployment_failures(deployment: dict, predictor: str, contract: dict) -> list[str]:
    failures = []
    expected = contract["predictors"][predictor]
    if deployment.get("status") != "pass" or deployment.get("warmup_passed") not in (True, 1, "true", "True"):
        failures.append("deployment_warmup")
    if (deployment.get("model_artifact") or {}).get("sha256_tree") != expected["model_sha256_tree"]:
        failures.append("model_hash")
    if (deployment.get("anchors_artifact") or {}).get("sha256") != contract["anchors_sha256"]:
        failures.append("anchors_hash")
    if predictor == "B1":
        if (deployment.get("calibration_artifact") or {}).get("sha256") != expected["calibration_sha256"]:
            failures.append("calibration_hash")
        if deployment.get("calibration_parameters") != expected["calibration_parameters"]:
            failures.append("calibration_parameters")
        if deployment.get("calibration_fit_split") != "val":
            failures.append("calibration_split")
    elif deployment.get("calibration_parameters") != {"temperature": 1.0, "covariance_scale": 1.0}:
        failures.append("b0_not_identity_calibrated")
    return failures


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(float(value) / math.sqrt(2.0)))


def _risk_manipulation_for_row(row: dict, risk_policy: str) -> tuple[list[str], dict]:
    failures: list[str] = []
    risk = row.get("risk") or {}
    tightening = risk.get("solver_current_tight")
    target_prob = risk.get("solver_current_target_prob")
    try:
        tightening = float(tightening)
        target_prob = float(target_prob)
    except (TypeError, ValueError):
        return ["risk_solver_values_missing"], {}
    if not math.isfinite(tightening) or not math.isfinite(target_prob):
        return ["risk_solver_values_nonfinite"], {}
    if not math.isclose(target_prob, _normal_cdf(tightening), abs_tol=1e-9):
        failures.append("risk_tightening_probability_mismatch")

    uses_adaptive = risk.get("solver_uses_adaptive_risk")
    mode = risk.get("solver_risk_mode")
    adaptive = risk.get("adaptive") or {}
    if risk_policy == "adaptive":
        if uses_adaptive is not True or mode != "adaptive_variable":
            failures.append("adaptive_not_applied_to_solver")
        if adaptive.get("enabled") is not True or adaptive.get("solver_applied") is not True:
            failures.append("adaptive_application_telemetry")
        for field, observed in (
            ("tightening", tightening),
            ("target_prob", target_prob),
        ):
            try:
                matches = math.isclose(float(adaptive.get(field)), observed, abs_tol=1e-9)
            except (TypeError, ValueError):
                matches = False
            if not matches:
                failures.append(f"adaptive_{field}_not_solver_value")
    else:
        expected = FIXED_RISK_TIGHTENING.get(risk_policy)
        if expected is None:
            failures.append("unknown_risk_policy")
        elif not math.isclose(tightening, expected, abs_tol=1e-9):
            failures.append("fixed_tightening_not_operating_point")
        if uses_adaptive is not False or mode != "fixed_static":
            failures.append("fixed_policy_not_static_in_solver")
        if adaptive.get("solver_applied") not in (False, None):
            failures.append("fixed_policy_adaptive_solver_application")
    return failures, {
        "tightening": tightening,
        "target_prob": target_prob,
        "solver_uses_adaptive_risk": bool(uses_adaptive),
        "solver_risk_mode": mode,
    }


def debug_audit(
    rows: list[dict], runtime_limit: float, risk_policy: str = None
) -> tuple[list[str], dict]:
    failures: list[str] = []
    valid_rows = []
    solve_times = []
    distinct_mode_rows = 0
    collapsed_mode_rows = 0
    risk_rows = []
    for row in rows:
        if not any(bool(value) for value in (row.get("prediction_valid") or [])):
            continue
        valid_rows.append(row)
        prediction = row.get("prediction") or {}
        if not all(finite_summary(prediction.get(field) or {}) for field in ("mode_probs", "mus", "sigmas")):
            failures.append("nonfinite_prediction_debug")
        mode = prediction.get("mode_consumption") or {}
        joint = mode.get("joint_modes") or []
        indices = []
        means = []
        covariances = []
        hashes_ok = True
        for joint_mode in joint:
            for consumed in joint_mode.get("per_vehicle") or []:
                indices.append(consumed.get("spatial_mode_index"))
                means.append(consumed.get("mean_sha256"))
                covariances.append(consumed.get("covariance_sha256"))
                hashes_ok = hashes_ok and valid_hash(means[-1]) and valid_hash(covariances[-1])
        if (
            mode.get("implementation_version") != CORRECTED
            or mode.get("mapping") != MODE_MAP
            or indices != [0, 1, 2]
            or not hashes_ok
        ):
            failures.append("mode_consumption")
        elif len(set(means)) == 3 and len(set(covariances)) == 3:
            distinct_mode_rows += 1
        else:
            # Valid indices with equal learned tensors are model mode collapse,
            # not evidence that the corrected consumption implementation failed.
            collapsed_mode_rows += 1
        if "yield_stop_supervisor" not in row:
            failures.append("supervisor_telemetry")
        if "solver" not in row or "solver_problem" not in row:
            failures.append("solver_telemetry")
        applied = row.get("applied") or {}
        if not all(finite_numeric(applied.get(field)) for field in ("u0", "u_control", "v_des", "control_prev_after")):
            failures.append("applied_control_numerics")
        solve_time = applied.get("solve_time")
        if solve_time is not None and math.isfinite(float(solve_time)):
            solve_times.append(float(solve_time))
        if risk_policy is not None:
            risk_failures, risk_stats = _risk_manipulation_for_row(row, risk_policy)
            failures.extend(risk_failures)
            if risk_stats:
                risk_rows.append(risk_stats)
    if not valid_rows:
        failures.append("no_valid_prediction_steps")
    p95 = float(np.quantile(solve_times, 0.95)) if solve_times else None
    runtime_gate_passed = p95 is not None and p95 <= runtime_limit
    tightenings = [float(item["tightening"]) for item in risk_rows]
    target_probs = [float(item["target_prob"]) for item in risk_rows]
    return sorted(set(failures)), {
        "debug_steps": len(rows),
        "valid_prediction_steps": len(valid_rows),
        "distinct_consumed_mode_steps": distinct_mode_rows,
        "learned_mode_collapse_steps": collapsed_mode_rows,
        "learned_mode_collapse_fraction": (
            collapsed_mode_rows / len(valid_rows) if valid_rows else None
        ),
        "p95_solve_time_s": p95,
        # Runtime is an operational/scientific observation, not data integrity.
        "runtime_gate_limit_s": float(runtime_limit),
        "runtime_gate_passed": bool(runtime_gate_passed),
        "risk_manipulation": {
            "audited_steps": len(risk_rows),
            "solver_applied_adaptive_steps": sum(
                item["solver_uses_adaptive_risk"] for item in risk_rows
            ),
            "tightening_min": min(tightenings) if tightenings else None,
            "tightening_max": max(tightenings) if tightenings else None,
            "tightening_unique_1e9": sorted(
                {round(value, 9) for value in tightenings}
            ),
            "target_prob_min": min(target_probs) if target_probs else None,
            "target_prob_max": max(target_probs) if target_probs else None,
            "adaptive_variation_observed": bool(
                risk_policy == "adaptive"
                and tightenings
                and max(tightenings) - min(tightenings) > 1e-9
            ),
        },
    }


def prediction_audit(rows: list[dict], cell: dict, init_id: int, contract: dict) -> tuple[list[str], dict]:
    failures: list[str] = []
    reactive_active = 0
    expected_style = "defensive_reactive" if cell["target_style"] == "reactive" else "assertive_constant_speed"
    for row in rows:
        if int(row.get("ego_init_id", -1)) != init_id:
            failures.append("prediction_init_id")
        if row.get("cell_id") != cell["cell_id"] or row.get("ego_policy") != cell["risk_policy"]:
            failures.append("prediction_treatment_identity")
        if row.get("protocol_id") != contract["prediction_protocol_id"]:
            failures.append("prediction_protocol")
        if row.get("git_commit") != contract["git_commit"]:
            failures.append("prediction_git_commit")
        if row.get("target_style") != expected_style:
            failures.append("prediction_target_style")
        if not math.isclose(
            float(row.get("target_start_offset_m", math.nan)),
            float(contract["target_offset_m"]),
            abs_tol=1e-12,
        ):
            failures.append("prediction_target_offset")
        if not math.isclose(
            float(row.get("target_speed_mps", math.nan)),
            float(contract["target_speed_mps"]),
            abs_tol=1e-12,
        ):
            failures.append("prediction_target_speed")
        style_parameters = row.get("target_style_parameters") or {}
        if cell["target_style"] == "reactive":
            for key, expected in contract["reactive_parameters"].items():
                if key not in style_parameters or not math.isclose(
                    float(style_parameters[key]), float(expected), abs_tol=1e-12
                ):
                    failures.append("prediction_reactive_parameters")
                    break
        elif not math.isclose(
            float(style_parameters.get("nominal_speed_mps", math.nan)),
            float(contract["target_speed_mps"]),
            abs_tol=1e-12,
        ):
            failures.append("prediction_assertive_parameters")
        probabilities = np.asarray(row.get("mode_probabilities"), dtype=float)
        means = np.asarray(row.get("pred_mus_world"), dtype=float)
        covariances = np.asarray(row.get("pred_sigmas_world"), dtype=float)
        if (
            probabilities.size == 0
            or means.size == 0
            or covariances.size == 0
            or not np.isfinite(probabilities).all()
            or not np.isfinite(means).all()
            or not np.isfinite(covariances).all()
            or (probabilities < 0).any()
            or not math.isclose(float(probabilities.sum()), 1.0, abs_tol=1e-6)
        ):
            failures.append("prediction_numerics")
        else:
            if not np.allclose(covariances, np.swapaxes(covariances, -1, -2), atol=1e-6):
                failures.append("covariance_symmetry")
            elif not bool((np.linalg.eigvalsh(covariances) > 0).all()):
                failures.append("covariance_positive_definite")
        reactive_active += int(bool((row.get("target_reactive_diagnostics") or {}).get("active")))
    if not rows:
        failures.append("no_prediction_samples")
    if cell["target_style"] == "assertive" and reactive_active:
        failures.append("assertive_reactive_activity")
    return sorted(set(failures)), {
        "prediction_samples": len(rows),
        "reactive_active_samples": reactive_active,
    }


def spawned_actor_audit(extra: dict) -> tuple[list[str], dict, dict]:
    """Validate exact CARLA actor identity/geometry captured before destruction."""

    failures: list[str] = []
    actors = extra.get("spawned_actor_telemetry")
    if not isinstance(actors, list) or not actors:
        return ["spawned_actor_telemetry_missing"], {}, {}
    by_key = {}
    by_id = {}
    roles = defaultdict(int)
    for actor in actors:
        if not isinstance(actor, dict):
            failures.append("spawned_actor_telemetry_malformed")
            continue
        actor_key = actor.get("actor_key")
        actor_id = actor.get("actor_id")
        if not isinstance(actor_key, str) or not actor_key:
            failures.append("spawned_actor_key")
            continue
        if not isinstance(actor_id, int):
            failures.append("spawned_actor_id")
            continue
        if actor_key in by_key or actor_id in by_id:
            failures.append("spawned_actor_identity_duplicate")
        if actor.get("schema_version") != "carla_spawned_actor_geometry_v1":
            failures.append("spawned_actor_schema")
        experiment_role = actor.get("experiment_role")
        if actor.get("actor_role_name") != experiment_role:
            failures.append("spawned_actor_role_mismatch")
        if not isinstance(actor.get("actor_type"), str) or not actor.get("actor_type"):
            failures.append("spawned_actor_type")
        dimensions = ((actor.get("bounding_box") or {}).get("dimensions_m") or {})
        local_center = ((actor.get("bounding_box") or {}).get("local_center_m") or {})
        local_rotation = (
            (actor.get("bounding_box") or {}).get("local_rotation_deg") or {}
        )
        try:
            values = [float(dimensions[key]) for key in ("length", "width", "height")]
            pose_values = [
                float(local_center[key]) for key in ("x", "y", "z")
            ] + [float(local_rotation[key]) for key in ("roll", "pitch", "yaw")]
        except (KeyError, TypeError, ValueError):
            values = []
            pose_values = []
        if len(values) != 3 or not all(math.isfinite(value) and value > 0 for value in values):
            failures.append("spawned_actor_bounding_box")
        if len(pose_values) != 6 or not all(math.isfinite(value) for value in pose_values):
            failures.append("spawned_actor_bounding_box_pose")
        by_key[actor_key] = actor
        by_id[actor_id] = actor
        roles[str(experiment_role)] += 1
    if roles["ego"] != 1 or roles["target"] != 1 or roles["static"] != 2:
        failures.append("spawned_actor_experiment_roles")
    summary = {
        "actor_count": len(actors),
        "role_counts": dict(sorted(roles.items())),
        "actors": actors,
    }
    return sorted(set(failures)), summary, by_id


def _expected_collision_category(role_a: str, role_b: str) -> str:
    roles = {role_a, role_b}
    if roles == {"ego", "target"}:
        return "ego_target"
    if "target" in roles and "infrastructure" in roles:
        return "target_infrastructure"
    if "target" in roles and "static_vehicle" in roles:
        return "target_static_vehicle"
    if "ego" in roles and "infrastructure" in roles:
        return "ego_infrastructure"
    if "ego" in roles and "static_vehicle" in roles:
        return "ego_static_vehicle"
    return "other"


def collision_episode_taxonomy(
    events: list[dict], spawned_by_id: dict, max_continuation_gap_frames: int = 1
) -> tuple[list[str], dict]:
    """Validate callbacks and merge mirrored/continuous callbacks into contact episodes."""

    failures: list[str] = []
    valid_events = []
    required = {
        "frame",
        "simulation_time_s",
        "monitored_actor_id",
        "monitored_actor_type",
        "monitored_actor_role_name",
        "monitored_experiment_role",
        "monitored_semantic_role",
        "counterpart_actor_id",
        "counterpart_actor_type",
        "counterpart_actor_role_name",
        "counterpart_semantic_role",
        "canonical_actor_id_pair",
        "canonical_actor_pair_key",
        "canonical_semantic_role_pair",
        "canonical_semantic_role_pair_key",
        "collision_category",
        "normal_impulse_magnitude",
    }
    for event in events:
        if not isinstance(event, dict) or not required.issubset(event):
            failures.append("collision_event_schema")
            continue
        try:
            frame = int(event["frame"])
            timestamp = float(event["simulation_time_s"])
            monitored_id = int(event["monitored_actor_id"])
            counterpart_id = int(event["counterpart_actor_id"])
            impulse = float(event["normal_impulse_magnitude"])
        except (TypeError, ValueError):
            failures.append("collision_event_numerics")
            continue
        if frame < 0 or not math.isfinite(timestamp) or timestamp < 0 or not math.isfinite(impulse) or impulse < 0:
            failures.append("collision_event_numerics")
        if monitored_id not in spawned_by_id:
            failures.append("collision_event_monitored_actor_unknown")
        else:
            monitored = spawned_by_id[monitored_id]
            if (
                event.get("monitored_actor_type") != monitored.get("actor_type")
                or event.get("monitored_actor_role_name") != monitored.get("actor_role_name")
                or event.get("monitored_experiment_role") != monitored.get("experiment_role")
            ):
                failures.append("collision_event_monitored_actor_identity")
        if counterpart_id in spawned_by_id:
            counterpart = spawned_by_id[counterpart_id]
            expected_semantic = counterpart.get("experiment_role")
            if expected_semantic == "static":
                expected_semantic = "static_vehicle"
            if (
                event.get("counterpart_actor_type") != counterpart.get("actor_type")
                or event.get("counterpart_actor_role_name")
                != counterpart.get("actor_role_name")
                or event.get("counterpart_semantic_role") != expected_semantic
            ):
                failures.append("collision_event_counterpart_actor_identity")
        actor_pair = sorted([monitored_id, counterpart_id])
        role_pair = sorted(
            [event["monitored_semantic_role"], event["counterpart_semantic_role"]]
        )
        expected_category = _expected_collision_category(*role_pair)
        if (
            event.get("canonical_actor_id_pair") != actor_pair
            or event.get("canonical_actor_pair_key") != ":".join(str(value) for value in actor_pair)
            or event.get("canonical_semantic_role_pair") != role_pair
            or event.get("canonical_semantic_role_pair_key") != ":".join(role_pair)
            or event.get("collision_category") != expected_category
        ):
            failures.append("collision_event_canonical_identity")
        valid_events.append(
            {
                **event,
                "frame": frame,
                "simulation_time_s": timestamp,
                "normal_impulse_magnitude": impulse,
            }
        )

    by_pair = defaultdict(list)
    for event in valid_events:
        by_pair[event["canonical_actor_pair_key"]].append(event)
    episodes = []
    for pair_key, pair_events in sorted(by_pair.items()):
        pair_events.sort(key=lambda item: (item["frame"], item["simulation_time_s"]))
        current = []
        previous_frame = None
        for event in pair_events:
            if previous_frame is None or event["frame"] - previous_frame <= max_continuation_gap_frames:
                current.append(event)
            else:
                episode = _collision_episode(pair_key, current)
                episodes.append(episode)
                if episode["collision_category"] == "inconsistent_identity":
                    failures.append("collision_episode_inconsistent_identity")
                current = [event]
            previous_frame = event["frame"]
        if current:
            episode = _collision_episode(pair_key, current)
            episodes.append(episode)
            if episode["collision_category"] == "inconsistent_identity":
                failures.append("collision_episode_inconsistent_identity")
    categories = defaultdict(lambda: {"callback_events": 0, "contact_episodes": 0})
    for event in valid_events:
        categories[event["collision_category"]]["callback_events"] += 1
    for episode in episodes:
        categories[episode["collision_category"]]["contact_episodes"] += 1
    return sorted(set(failures)), {
        "schema_version": "r3_native_collision_episode_taxonomy_v1",
        "episode_definition": {
            "identity": "canonical CARLA actor-id pair",
            "continuation": f"successive callback frames separated by <= {max_continuation_gap_frames}",
            "mirrored_callbacks_are_deduplicated": True,
        },
        "callback_event_count": len(events),
        "validated_callback_event_count": len(valid_events),
        "contact_episode_count": len(episodes),
        "categories": dict(sorted(categories.items())),
        "episodes": episodes,
    }


def _collision_episode(pair_key: str, events: list[dict]) -> dict:
    categories = {event["collision_category"] for event in events}
    role_pairs = {event["canonical_semantic_role_pair_key"] for event in events}
    if len(categories) != 1 or len(role_pairs) != 1:
        # The caller's canonical checks make this impossible unless CARLA actor IDs
        # are reused within one rollout; retain an explicit invalid category.
        category = "inconsistent_identity"
        role_pair = "inconsistent_identity"
    else:
        category = next(iter(categories))
        role_pair = next(iter(role_pairs))
    return {
        "canonical_actor_pair_key": pair_key,
        "canonical_semantic_role_pair_key": role_pair,
        "collision_category": category,
        "start_frame": min(event["frame"] for event in events),
        "end_frame": max(event["frame"] for event in events),
        "start_simulation_time_s": min(event["simulation_time_s"] for event in events),
        "end_simulation_time_s": max(event["simulation_time_s"] for event in events),
        "callback_count": len(events),
        "max_normal_impulse_magnitude": max(
            event["normal_impulse_magnitude"] for event in events
        ),
    }


def footprint_sensitivity_audit(
    gate_item: dict, actor_stats: dict = None
) -> tuple[list[str], dict]:
    failures: list[str] = []
    sensitivity = gate_item.get("footprint_margin_sensitivity")
    if not isinstance(sensitivity, dict):
        return ["footprint_sensitivity_missing"], {}
    if set(sensitivity) != EXPECTED_FOOTPRINT_SENSITIVITY_MARGINS:
        failures.append("footprint_sensitivity_margins")
    summary = {}
    actor_by_key = {
        actor.get("actor_key"): actor
        for actor in (actor_stats or {}).get("actors", [])
        if isinstance(actor, dict)
    }
    ego_keys = [key for key in actor_by_key if str(key).startswith("ego_")]
    for margin, pairs in sorted(sensitivity.items()):
        if not isinstance(pairs, list) or len(pairs) != 1:
            failures.append("footprint_sensitivity_pair_coverage")
            continue
        pair = pairs[0]
        sources = [pair.get("ego_geometry_source"), pair.get("target_geometry_source")]
        if not all(
            source in {
                "scenario_result_carla_bounding_box",
                "scenario_summary_carla_bounding_box",
            }
            for source in sources
        ):
            failures.append("footprint_geometry_not_actual_carla_bbox")
        try:
            margin_value = float(pair.get("footprint_margin_m"))
            expected_margin = float(margin)
            dimensions = [
                float(pair[key])
                for key in (
                    "ego_length_m",
                    "ego_width_m",
                    "target_length_m",
                    "target_width_m",
                )
            ]
            bbox_pose_offsets = [
                float(pair[key])
                for key in (
                    "ego_bbox_center_offset_x_m",
                    "ego_bbox_center_offset_y_rhs_m",
                    "ego_bbox_yaw_offset_rad_rhs",
                    "target_bbox_center_offset_x_m",
                    "target_bbox_center_offset_y_rhs_m",
                    "target_bbox_yaw_offset_rad_rhs",
                )
            ]
        except (TypeError, ValueError, KeyError):
            failures.append("footprint_sensitivity_geometry")
            continue
        if not math.isclose(margin_value, expected_margin, abs_tol=1e-12) or not all(
            math.isfinite(value) and value > 0 for value in dimensions
        ) or not all(math.isfinite(value) for value in bbox_pose_offsets):
            failures.append("footprint_sensitivity_geometry")
        target_key = pair.get("target_key")
        if len(ego_keys) == 1 and target_key in actor_by_key:
            expected_geometry = []
            for actor_key in (ego_keys[0], target_key):
                bbox = actor_by_key[actor_key].get("bounding_box") or {}
                dims = bbox.get("dimensions_m") or {}
                center = bbox.get("local_center_m") or {}
                rotation = bbox.get("local_rotation_deg") or {}
                expected_geometry.extend(
                    [
                        float(dims["length"]),
                        float(dims["width"]),
                        float(center["x"]),
                        -float(center["y"]),
                        -math.radians(float(rotation["yaw"])),
                    ]
                )
            observed_geometry = [
                dimensions[0],
                dimensions[1],
                bbox_pose_offsets[0],
                bbox_pose_offsets[1],
                bbox_pose_offsets[2],
                dimensions[2],
                dimensions[3],
                bbox_pose_offsets[3],
                bbox_pose_offsets[4],
                bbox_pose_offsets[5],
            ]
            if not np.allclose(observed_geometry, expected_geometry, atol=1e-12):
                failures.append("footprint_geometry_cross_log_mismatch")
        else:
            failures.append("footprint_geometry_actor_identity")
        summary[margin] = {
            "target_key": target_key,
            "footprint_collision": pair.get("footprint_collision"),
            "min_footprint_separation_m": pair.get("min_footprint_separation_m"),
            "geometry_sources": sources,
            "dimensions_m": dimensions,
            "bbox_pose_offsets_rhs": bbox_pose_offsets,
        }
    return sorted(set(failures)), summary


def control_variable_audit(
    scenario_dir: Path,
    summary: dict,
    rollout_config: dict,
    actor_stats: dict,
    cell: dict,
    init_id: int,
    contract: dict,
    frozen_init: dict,
) -> tuple[list[str], dict]:
    """Audit scenario, treatment and initial-state controls from independent logs."""

    failures: list[str] = []
    expected_style = (
        "defensive_reactive"
        if cell["target_style"] == "reactive"
        else "assertive_constant_speed"
    )
    expected_policy_config = (
        "smpc_var_risk" if cell["risk_policy"] == "adaptive" else "smpc_fixed_risk"
    )
    actual_map = ((summary.get("extra") or {}).get("map"))
    actual_fps = summary.get("carla_fps")
    actual_max_iters = summary.get("max_iters")
    if not str(actual_map or "").endswith("Town05"):
        failures.append("control_map")
    if not _close(actual_fps, 20.0) or int(actual_max_iters or -1) != 600:
        failures.append("control_fps_or_max_iters")

    if rollout_config.get("schema_version") != "scenario_rollout_config_v2":
        failures.append("rollout_config_schema")
    carla_config = rollout_config.get("carla_params") or {}
    expected_carla = {
        "map_str": "Town05",
        "fps": 20,
        "side_of_road": "right",
        "traffic_control": "unsignalised",
        "priority_rule": "turning_gives_way_to_oncoming_straight",
        "intersection_csv_loc": "intersection_01.csv",
    }
    if any(carla_config.get(key) != value for key, value in expected_carla.items()):
        failures.append("rollout_config_carla_conditions")
    description = rollout_config.get("scenario_description") or {}
    if (
        description.get("traffic_control") != "unsignalised"
        or description.get("side_of_road") != "right"
        or "give way" not in str(description.get("priority_rule", "")).lower()
    ):
        failures.append("rollout_config_give_way_scenario")

    provenance = rollout_config.get("execution_provenance") or {}
    if provenance.get("schema_version") != "carla_rollout_execution_provenance_v1":
        failures.append("rollout_execution_provenance_schema")
    init_source = provenance.get("ego_init_source") or {}
    if (
        init_source.get("sha256") != contract["init_sha256"].get(str(init_id))
        or init_source.get("parsed_values") != frozen_init
    ):
        failures.append("effective_init_provenance")
    scenario_source = provenance.get("scenario_source") or {}
    if (
        not valid_hash(scenario_source.get("sha256"))
        or scenario_source.get("sha256")
        != (contract.get("scenario_contract") or {}).get("sha256")
    ):
        failures.append("scenario_source_provenance")
    tuning_source = provenance.get("tuning_source") or {}
    if (
        provenance.get("tuning_applied") is not True
        or tuning_source.get("sha256") != contract.get("tuning_sha256")
    ):
        failures.append("tuning_source_provenance")
    if (
        provenance.get("ego_policy_config") != expected_policy_config
        or provenance.get("risk_profile") != RISK_PROFILES[cell["risk_policy"]]
        or provenance.get("target_style") != expected_style
    ):
        failures.append("treatment_execution_provenance")
    expected_adaptive = contract.get("adaptive_parameters") if cell["risk_policy"] == "adaptive" else {}
    if (provenance.get("adaptive_risk_config") or {}) != (expected_adaptive or {}):
        failures.append("adaptive_config_provenance")
    expected_reactive = contract.get("reactive_parameters") or {}
    if (provenance.get("reactive_config") or {}) != expected_reactive:
        failures.append("reactive_config_provenance")
    prediction = provenance.get("prediction") or {}
    if (
        prediction.get("protocol_id") != contract["prediction_protocol_id"]
        or prediction.get("cell_id") != cell["cell_id"]
        or prediction.get("ego_policy_label") != cell["risk_policy"]
        or prediction.get("git_commit") != contract["git_commit"]
        or prediction.get("logging_enabled") is not True
        or int(prediction.get("logging_stride") or -1) != 1
        or int(prediction.get("logging_horizon") or -1) != 10
        or not prediction.get("model_weights_argument")
        or not prediction.get("model_anchors_argument")
    ):
        failures.append("prediction_execution_provenance")
    calibration_argument = prediction.get("model_calibration_argument")
    if (cell["predictor"] == "B1") != bool(calibration_argument):
        failures.append("predictor_calibration_treatment_provenance")

    effective = rollout_config.get("effective_runtime_vehicle_params")
    actor_effective = [
        actor.get("effective_vehicle_params")
        for actor in actor_stats.get("actors", [])
    ]
    if not isinstance(effective, list) or effective != actor_effective:
        failures.append("effective_vehicle_params_cross_log")
        effective = []
    by_role = {
        value.get("role"): value
        for value in effective
        if isinstance(value, dict) and value.get("role") in {"ego", "target"}
    }
    ego = by_role.get("ego") or {}
    target = by_role.get("target") or {}
    if (
        not _close(ego.get("init_speed"), frozen_init.get("init_speed"))
        or not _close(
            ego.get("start_longitudinal_offset"),
            frozen_init.get("start_longitudinal_offset"),
        )
        or not _close(ego.get("nominal_speed"), 6.0)
        or ego.get("intersection_start_node_idx") != 0
        or ego.get("intersection_goal_node_idx") != 3
        or not _close(ego.get("start_left_offset"), 2.75)
        or not _close(ego.get("goal_left_offset"), 1.85)
        or not _close(ego.get("goal_longitudinal_offset"), 20.0)
        or ego.get("policy_type") != "smpc"
        or ego.get("smpc_config") != (
            "var_risk" if cell["risk_policy"] == "adaptive" else "fixed_risk"
        )
        or ego.get("risk_profile") != RISK_PROFILES[cell["risk_policy"]]
        or (ego.get("adaptive_risk_config") or {}) != (expected_adaptive or {})
    ):
        failures.append("effective_ego_conditions")
    reactive_field_map = {
        "caution_speed_mps": "reactive_caution_speed",
        "minimum_speed_mps": "reactive_minimum_speed",
        "activation_distance_m": "reactive_activation_distance",
        "release_clearance_m": "reactive_release_clearance",
        "arrival_time_gap_s": "reactive_arrival_time_gap",
        "closest_approach_time_s": "reactive_closest_approach_time",
        "closest_approach_distance_m": "reactive_closest_approach_distance",
        "release_hold_s": "reactive_release_hold",
    }
    reactive_parameters_match = all(
        _close(target.get(runtime_key), expected_reactive[public_key])
        for public_key, runtime_key in reactive_field_map.items()
    )
    if (
        not _close(target.get("init_speed"), contract["target_speed_mps"])
        or not _close(target.get("nominal_speed"), contract["target_speed_mps"])
        or not _close(
            target.get("start_longitudinal_offset"), contract["target_offset_m"]
        )
        or target.get("intersection_start_node_idx") != 2
        or target.get("intersection_goal_node_idx") != 2
        or not _close(target.get("start_left_offset"), 1.5)
        or not _close(target.get("goal_left_offset"), 1.5)
        or not _close(target.get("goal_longitudinal_offset"), 25.0)
        or target.get("target_style") != expected_style
        or target.get("policy_type") != (
            "defensive_reactive" if cell["target_style"] == "reactive" else "straight"
        )
        or target.get("traffic_role") != "priority_oncoming_straight"
        or target.get("obey_traffic_lights") is not False
        or not reactive_parameters_match
    ):
        failures.append("effective_target_conditions")

    first_states = {}
    result_path = scenario_dir / "scenario_result.pkl"
    try:
        with result_path.open("rb") as handle:
            result = pickle.load(handle)
        for role, expected_speed in (
            ("ego", float(frozen_init["init_speed"])),
            ("target", float(contract["target_speed_mps"])),
        ):
            keys = [key for key in result if str(key).startswith(role + "_")]
            if len(keys) != 1:
                raise ValueError(f"Expected one {role} trajectory")
            trajectory = np.asarray(result[keys[0]].get("state_trajectory"), dtype=float)
            if trajectory.ndim != 2 or trajectory.shape[0] < 1 or trajectory.shape[1] < 5:
                raise ValueError(f"Malformed {role} trajectory")
            state = trajectory[0, :5]
            if not np.isfinite(state).all() or not math.isclose(
                float(state[4]), expected_speed, abs_tol=0.75
            ):
                failures.append(f"first_state_{role}_speed")
            first_states[role] = state.tolist()
    except Exception:
        failures.append("first_state_evidence")

    return sorted(set(failures)), {
        "map": actual_map,
        "carla_fps": actual_fps,
        "max_iters": actual_max_iters,
        "ego_init_id": init_id,
        "frozen_init_values": frozen_init,
        "effective_ego_init_values": {
            "init_speed": ego.get("init_speed"),
            "start_longitudinal_offset": ego.get("start_longitudinal_offset"),
        },
        "target_nominal_conditions": {
            "init_speed": target.get("init_speed"),
            "nominal_speed": target.get("nominal_speed"),
            "start_longitudinal_offset": target.get("start_longitudinal_offset"),
            "target_style": target.get("target_style"),
        },
        "first_states_txyyawspeed": first_states,
        "scenario_source_sha256": scenario_source.get("sha256"),
        "tuning_source_sha256": tuning_source.get("sha256"),
        "init_source_sha256": init_source.get("sha256"),
    }


def rollout_receipt_audit(
    cell_dir: Path, cell_id: str, init_id: int, scenario_dir: Path
) -> tuple[list[str], dict]:
    """Independently bind the accepted attempt, receipt and immutable CARLA files."""

    failures: list[str] = []
    receipt_path = cell_dir / f"R3_ROLLOUT_{init_id}_COMPLETE.json"
    if not receipt_path.is_file():
        return ["rollout_receipt_missing"], {}
    try:
        receipt = read_json(receipt_path)
    except (OSError, ValueError, TypeError):
        return ["rollout_receipt_invalid_json"], {}
    relative_scenario = scenario_dir.relative_to(cell_dir).as_posix()
    if (
        receipt.get("schema_version") != "r3_rollout_complete_v2"
        or receipt.get("status") != "pass"
        or receipt.get("cell_id") != cell_id
        or _as_int(receipt.get("ego_init_id")) != init_id
        or receipt.get("scenario_dir") != relative_scenario
    ):
        failures.append("rollout_receipt_identity")
    try:
        accepted_attempt = int(receipt.get("accepted_attempt"))
    except (TypeError, ValueError):
        accepted_attempt = -1
        failures.append("rollout_receipt_accepted_attempt")
    raw_hash = raw_evidence_sha256(scenario_dir)
    if receipt.get("raw_evidence_sha256") != raw_hash:
        failures.append("rollout_receipt_raw_evidence_hash")
    summary_path = scenario_dir / "scenario_run_summary.json"
    if (
        not summary_path.is_file()
        or receipt.get("scenario_summary_sha256") != sha256(summary_path)
    ):
        failures.append("rollout_receipt_summary_hash")

    critical = receipt.get("critical_artifacts") or {}
    for relative in R3_RAW_REQUIRED_FILES:
        path = scenario_dir / relative
        declared = critical.get(relative) or {}
        if (
            not path.is_file()
            or _as_int(declared.get("bytes")) != path.stat().st_size
            or declared.get("sha256") != sha256(path)
        ):
            failures.append(f"rollout_receipt_critical_artifact:{relative}")
    for relative in R3_RAW_OPTIONAL_FILES:
        path = scenario_dir / relative
        declared_present = bool(
            (receipt.get("optional_artifact_presence") or {}).get(relative)
        )
        if declared_present != path.is_file():
            failures.append(f"rollout_receipt_optional_presence:{relative}")
        if path.is_file():
            declared = critical.get(relative) or {}
            if (
                _as_int(declared.get("bytes")) != path.stat().st_size
                or declared.get("sha256") != sha256(path)
            ):
                failures.append(f"rollout_receipt_optional_artifact:{relative}")

    record_relative = receipt.get("attempt_record")
    ledger_relative = receipt.get("attempt_ledger")
    record_path = cell_dir / str(record_relative or "")
    ledger_path = cell_dir / str(ledger_relative or "")
    record = {}
    ledger = {}
    if (
        not record_relative
        or not record_path.is_file()
        or receipt.get("attempt_record_sha256") != sha256(record_path)
    ):
        failures.append("rollout_receipt_attempt_record")
    else:
        try:
            record = read_json(record_path)
        except (OSError, ValueError, TypeError):
            failures.append("rollout_attempt_record_invalid_json")
        else:
            if (
                record.get("schema_version") != "r3_attempt_record_v2"
                or record.get("accepted") is not True
                or _as_int(record.get("attempt")) != accepted_attempt
                or record.get("cell_id") != cell_id
                or _as_int(record.get("ego_init_id")) != init_id
                or record.get("raw_evidence_sha256_before_promotion") not in (None, raw_hash)
            ):
                failures.append("rollout_attempt_record_identity")
    if (
        not ledger_relative
        or not ledger_path.is_file()
        or receipt.get("attempt_ledger_sha256_at_receipt") != sha256(ledger_path)
    ):
        failures.append("rollout_receipt_attempt_ledger")
    else:
        try:
            ledger = read_json(ledger_path)
        except (OSError, ValueError, TypeError):
            failures.append("rollout_attempt_ledger_invalid_json")
        else:
            accepted_entries = [
                item
                for item in ledger.get("attempts", [])
                if item.get("state") == "accepted"
                or ((item.get("record") or {}).get("accepted") is True)
            ]
            if (
                ledger.get("schema_version") != "r3_attempt_ledger_v2"
                or ledger.get("status") != "accepted"
                or ledger.get("cell_id") != cell_id
                or _as_int(ledger.get("ego_init_id")) != init_id
                or _as_int(ledger.get("accepted_attempts")) != 1
                or len(accepted_entries) != 1
                or _as_int(accepted_entries[0].get("attempt")) != accepted_attempt
            ):
                failures.append("rollout_attempt_ledger_identity")
    return sorted(set(failures)), {
        "receipt_path": receipt_path.relative_to(cell_dir).as_posix(),
        "receipt_sha256": sha256(receipt_path),
        "accepted_attempt": accepted_attempt,
        "recovered_after_interruption": receipt.get("recovered_after_interruption"),
        "raw_evidence_sha256": raw_hash,
        "attempt_record": record_relative,
        "attempt_record_sha256": (
            sha256(record_path) if record_path.is_file() else None
        ),
        "attempt_classification": record.get("classification"),
        "attempt_ledger": ledger_relative,
        "attempt_ledger_sha256": (
            sha256(ledger_path) if ledger_path.is_file() else None
        ),
        "attempts_started": ledger.get("attempts_started"),
        "accepted_attempts": ledger.get("accepted_attempts"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--contract-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    root = args.results_dir.resolve()
    contract_path = args.contract_json.resolve()
    contract = read_json(contract_path)
    if contract.get("status") != "frozen" or contract.get("implementation_version") != CORRECTED:
        raise ValueError("R3 contract is not a frozen corrected-v1 contract")

    failures: list[str] = []
    expected_inits = set(int(value) for value in contract["ego_init_ids"])
    expected_keys = {
        (cell["predictor"], cell["risk_policy"], cell["target_style"], init_id)
        for cell in contract["cells"]
        for init_id in expected_inits
    }
    order = contract.get("execution_order") or []
    order_keys = {
        (item["predictor"], item["risk_policy"], item["target_style"], int(item["ego_init_id"]))
        for item in order
    }
    if len(order) != len(order_keys) or order_keys != expected_keys:
        failures.append("matrix:execution_order_coverage_or_duplicates")
    block_size = len(contract["cells"])
    for block_index in range(len(expected_inits)):
        block = order[block_index * block_size : (block_index + 1) * block_size]
        block_inits = {int(item["ego_init_id"]) for item in block}
        block_cells = {(item["predictor"], item["risk_policy"], item["target_style"]) for item in block}
        expected_cells = {(item["predictor"], item["risk_policy"], item["target_style"]) for item in contract["cells"]}
        if len(block_inits) != 1 or block_cells != expected_cells:
            failures.append(f"matrix:block_randomisation:{block_index}")
    if len(expected_keys) != int(contract["expected_rollouts"]):
        failures.append("matrix:contract_rollout_count")

    for source_key, relative in (contract.get("frozen_source_files") or {}).items():
        path = root / relative["path"] if relative.get("scope") == "results" else Path(relative["path"])
        if not path.is_file() or sha256(path) != relative["sha256"]:
            failures.append(f"matrix:frozen_source:{source_key}")
    frozen_inits = {}
    for init_id in expected_inits:
        init_path = root / "_frozen_inits_101_105" / f"ego_init_{init_id}.json"
        if not init_path.is_file() or sha256(init_path) != contract["init_sha256"].get(str(init_id)):
            failures.append(f"matrix:init_sha256:{init_id}")
        else:
            frozen_inits[init_id] = read_json(init_path)
    preflight_path = root / "r3_deployment_preflight.json"
    if (
        not preflight_path.is_file()
        or semantic_sha256(preflight_semantics(read_json(preflight_path)))
        != contract.get("preflight_semantic_sha256")
    ):
        failures.append("matrix:preflight_semantics")

    evaluations = []
    observed_keys = set()
    geometry_by_init: dict[int, list[np.ndarray]] = defaultdict(list)
    total_native_collision_callbacks = 0
    total_native_collision_episodes = 0
    native_collision_rollouts = 0
    native_category_callbacks = defaultdict(int)
    native_category_episodes = defaultdict(int)
    native_category_rollouts = defaultdict(int)
    total_footprint_collisions = 0
    unavailable_footprint_outcomes = 0
    total_yield_failures = 0
    unavailable_yield_outcomes = 0
    total_completion_failures = 0
    unavailable_completion_outcomes = 0
    total_valid_prediction_steps = 0
    mode_consumption_by_predictor = defaultdict(
        lambda: {"valid_steps": 0, "learned_mode_collapse_steps": 0}
    )
    max_p95 = 0.0
    runtime_gate_exceeded_rollouts = 0
    reactive_cells_without_active_samples = []
    adaptive_cells_without_tightening_variation = []
    first_states_by_init = defaultdict(list)
    scenario_source_hashes = set()
    risk_manipulation_by_policy = defaultdict(
        lambda: {
            "audited_steps": 0,
            "solver_applied_adaptive_steps": 0,
            "tightening_min": None,
            "tightening_max": None,
        }
    )

    for cell in contract["cells"]:
        cell_dir = root / cell["cell_id"]
        gate_path = cell_dir / "postcarla_trajectory_gate.json"
        cell_failures: list[str] = []
        if not gate_path.is_file():
            evaluations.append(
                {
                    **cell,
                    "status": "fail",
                    "integrity_status": "fail",
                    "integrity_failures": ["missing_postcarla_gate"],
                    "failures": ["missing_postcarla_gate"],
                }
            )
            failures.append(f"{cell['cell_id']}:missing_postcarla_gate")
            continue
        gate = read_json(gate_path)
        gate_by_name = {Path(item["scenario_dir"]).name: item for item in gate.get("evaluations", [])}
        summaries = sorted(cell_dir.glob("scenario_*/scenario_run_summary.json"))
        if len(summaries) != len(expected_inits):
            cell_failures.append("rollout_count")
        rollout_evaluations = []
        cell_reactive_active = 0
        for summary_path in summaries:
            scenario_dir = summary_path.parent
            init_id = scenario_init_id(scenario_dir.name)
            key = (cell["predictor"], cell["risk_policy"], cell["target_style"], init_id)
            observed_keys.add(key)
            rollout_failures: list[str] = []
            summary = read_json(summary_path)
            if summary.get("ran_successfully") is not True:
                rollout_failures.append("scenario_not_successful")
            extra = summary.get("extra") or {}
            actor_failures, actor_stats, spawned_by_id = spawned_actor_audit(extra)
            rollout_failures.extend(actor_failures)
            if extra.get("collision_telemetry_schema_version") != "carla_collision_identity_v2":
                rollout_failures.append("native_collision_schema_version")
            if "collision_event_count" not in extra or "collision_events" not in extra:
                rollout_failures.append("native_collision_telemetry")
                native_count = 0
                native_events = []
            else:
                native_count = int(extra["collision_event_count"])
                native_events = extra["collision_events"] or []
                if native_count != len(native_events):
                    rollout_failures.append("native_collision_count_mismatch")
            collision_failures, collision_taxonomy = collision_episode_taxonomy(
                native_events, spawned_by_id
            )
            rollout_failures.extend(collision_failures)
            rollout_categories = set()
            for category, values in collision_taxonomy.get("categories", {}).items():
                native_category_callbacks[category] += int(values["callback_events"])
                native_category_episodes[category] += int(values["contact_episodes"])
                if int(values["contact_episodes"]):
                    rollout_categories.add(category)
            for category in rollout_categories:
                native_category_rollouts[category] += 1
            validity_categories = sorted(
                rollout_categories & SCENARIO_VALIDITY_COLLISION_CATEGORIES
            )
            total_native_collision_callbacks += native_count
            episode_count = int(collision_taxonomy.get("contact_episode_count", 0))
            total_native_collision_episodes += episode_count
            native_collision_rollouts += int(episode_count > 0)

            receipt_failures, receipt_stats = rollout_receipt_audit(
                cell_dir, cell["cell_id"], init_id, scenario_dir
            )
            rollout_failures.extend(receipt_failures)

            setup_path = scenario_dir / "smpc_debug_setup.json"
            debug_path = scenario_dir / "smpc_debug_steps.jsonl"
            deployment_path = scenario_dir / "prediction_deployment_manifest.json"
            prediction_path = scenario_dir / "prediction_dataset/prediction_dataset_raw.jsonl"
            rollout_config_path = scenario_dir / "scenario_rollout_config.json"
            scenario_result_path = scenario_dir / "scenario_result.pkl"
            for path, label in (
                (setup_path, "missing_setup"),
                (debug_path, "missing_debug"),
                (deployment_path, "missing_deployment"),
                (prediction_path, "missing_prediction"),
                (rollout_config_path, "missing_rollout_config"),
                (scenario_result_path, "missing_scenario_result"),
            ):
                if not path.is_file():
                    rollout_failures.append(label)
            gate_item = gate_by_name.get(scenario_dir.name)
            if gate_item is None:
                rollout_failures.append("missing_postcarla_rollout")
            if rollout_failures and any(item.startswith("missing_") for item in rollout_failures):
                rollout_evaluations.append(
                    {
                        "scenario": scenario_dir.name,
                        "ego_init_id": init_id,
                        "status": "fail",
                        "integrity_status": "fail",
                        "integrity_failures": sorted(set(rollout_failures)),
                        "failures": sorted(set(rollout_failures)),
                    }
                )
                cell_failures.extend(f"{scenario_dir.name}:{item}" for item in rollout_failures)
                continue

            setup = read_json(setup_path)
            control = setup.get("control_implementation") or {}
            if (
                control.get("version") != CORRECTED
                or control.get("legacy_explicitly_enabled") is not False
                or control.get("mode_consumption_map_at_n_tv_max") != MODE_MAP
                or control.get("reference_A_MIN") != -3.0
                or control.get("solver_A_MIN") != -3.0
            ):
                rollout_failures.append("corrected_control_contract")
            if setup.get("risk_profile") != RISK_PROFILES[cell["risk_policy"]]:
                rollout_failures.append("risk_profile")
            if bool(setup.get("fixed_risk")) != (cell["risk_policy"] != "adaptive"):
                rollout_failures.append("fixed_risk_flag")
            smpc_setup = setup.get("smpc") or {}
            setup_tightening = smpc_setup.get("tight")
            setup_target_prob = smpc_setup.get("target_prob")
            expected_setup_tightening = FIXED_RISK_TIGHTENING.get(
                cell["risk_policy"], 1.64
            )
            try:
                setup_risk_ok = (
                    math.isclose(
                        float(setup_tightening), expected_setup_tightening, abs_tol=1e-9
                    )
                    and math.isclose(
                        float(setup_target_prob),
                        _normal_cdf(expected_setup_tightening),
                        abs_tol=1e-9,
                    )
                )
            except (TypeError, ValueError):
                setup_risk_ok = False
            if not setup_risk_ok:
                rollout_failures.append("setup_risk_operating_point")
            supervisor = setup.get("yield_stop_supervisor") or {}
            if (
                supervisor.get("risk_owned_yield_enabled") != 1
                or supervisor.get("planner_ownership_stress_enabled") != 1
                or supervisor.get("mode") != "reduced_intervention"
            ):
                rollout_failures.append("authority_regime")
            if "collision_envelope" not in setup:
                rollout_failures.append("collision_envelope_telemetry")

            control_failures, control_stats = control_variable_audit(
                scenario_dir,
                summary,
                read_json(rollout_config_path),
                actor_stats,
                cell,
                init_id,
                contract,
                frozen_inits.get(init_id, {}),
            )
            rollout_failures.extend(control_failures)
            if control_stats.get("scenario_source_sha256"):
                scenario_source_hashes.add(control_stats["scenario_source_sha256"])
            if control_stats.get("first_states_txyyawspeed"):
                first_states_by_init[init_id].append(
                    {
                        "cell_id": cell["cell_id"],
                        **control_stats["first_states_txyyawspeed"],
                    }
                )

            rollout_failures.extend(deployment_failures(read_json(deployment_path), cell["predictor"], contract))
            debug_failures, debug_stats = debug_audit(
                read_jsonl(debug_path),
                float(contract["runtime_gate"]["max_p95_solve_time_s"]),
                cell["risk_policy"],
            )
            rollout_failures.extend(debug_failures)
            prediction_failures, prediction_stats = prediction_audit(read_jsonl(prediction_path), cell, init_id, contract)
            rollout_failures.extend(prediction_failures)
            total_valid_prediction_steps += debug_stats["valid_prediction_steps"]
            mode_consumption_by_predictor[cell["predictor"]]["valid_steps"] += int(
                debug_stats["valid_prediction_steps"]
            )
            mode_consumption_by_predictor[cell["predictor"]][
                "learned_mode_collapse_steps"
            ] += int(debug_stats["learned_mode_collapse_steps"])
            if debug_stats["p95_solve_time_s"] is not None:
                max_p95 = max(max_p95, float(debug_stats["p95_solve_time_s"]))
            runtime_gate_exceeded_rollouts += int(
                not debug_stats["runtime_gate_passed"]
            )
            risk_stats = debug_stats["risk_manipulation"]
            policy_risk_stats = risk_manipulation_by_policy[cell["risk_policy"]]
            policy_risk_stats["audited_steps"] += int(risk_stats["audited_steps"])
            policy_risk_stats["solver_applied_adaptive_steps"] += int(
                risk_stats["solver_applied_adaptive_steps"]
            )
            for field, reducer in (("tightening_min", min), ("tightening_max", max)):
                observed = risk_stats[field]
                if observed is not None:
                    previous = policy_risk_stats[field]
                    policy_risk_stats[field] = (
                        float(observed)
                        if previous is None
                        else reducer(float(previous), float(observed))
                    )
            if (
                cell["risk_policy"] == "adaptive"
                and not risk_stats["adaptive_variation_observed"]
            ):
                adaptive_cells_without_tightening_variation.append(
                    f"{cell['cell_id']}:init{init_id}"
                )
            cell_reactive_active += prediction_stats["reactive_active_samples"]

            if gate_item is not None:
                completion = gate_item.get("completion_valid")
                completion_source = gate_item.get("completion_source")
                completion_reason = gate_item.get("completion_reason")
                if not isinstance(completion_source, str) or not isinstance(
                    completion_reason, str
                ):
                    rollout_failures.append("completion_outcome_provenance")
                if not isinstance(completion, bool):
                    unavailable_completion_outcomes += 1
                else:
                    total_completion_failures += int(not completion)
                pairs = gate_item.get("pair_safety") or []
                if len(pairs) != 1:
                    rollout_failures.append("footprint_pair_coverage")
                    unavailable_footprint_outcomes += 1
                    footprint_outcome = None
                else:
                    footprint_outcome = pairs[0].get("footprint_collision")
                    if isinstance(footprint_outcome, bool):
                        total_footprint_collisions += int(footprint_outcome)
                    else:
                        unavailable_footprint_outcomes += 1
                sensitivity_failures, sensitivity_stats = footprint_sensitivity_audit(
                    gate_item, actor_stats
                )
                rollout_failures.extend(sensitivity_failures)
                fixed_rules = gate_item.get("fixed_geometry_yield_rules") or []
                if len(fixed_rules) != 1:
                    rollout_failures.append("fixed_geometry_rule_coverage")
                    unavailable_yield_outcomes += 1
                    fixed_rule_outcome = None
                    fixed_rule_outcome_reason = "fixed_geometry_rule_missing"
                else:
                    rule = fixed_rules[0]
                    outcome = rule.get("target_clears_before_ego_enters")
                    if not isinstance(outcome, bool):
                        unavailable_yield_outcomes += 1
                    else:
                        total_yield_failures += int(not outcome)
                    fixed_rule_outcome = outcome if isinstance(outcome, bool) else None
                    fixed_rule_outcome_reason = rule.get("outcome_reason")
                    if not isinstance(fixed_rule_outcome_reason, str):
                        rollout_failures.append("fixed_geometry_outcome_provenance")
                    points = np.asarray([rule.get("ego_conflict_point_xy"), rule.get("target_conflict_point_xy")], dtype=float)
                    if points.shape != (2, 2) or not np.isfinite(points).all() or rule.get("geometry_source") != "controller_route_projection":
                        rollout_failures.append("fixed_geometry_invalid")
                    else:
                        geometry_by_init[init_id].append(points)
            else:
                completion = None
                completion_source = "postcarla_rollout_missing"
                completion_reason = "postcarla_rollout_missing"
                footprint_outcome = None
                fixed_rule_outcome = None
                fixed_rule_outcome_reason = "postcarla_rollout_missing"
                sensitivity_stats = {}

            rollout = {
                "scenario": scenario_dir.name,
                "ego_init_id": init_id,
                "status": "pass" if not rollout_failures else "fail",
                "integrity_status": "pass" if not rollout_failures else "fail",
                "integrity_failures": sorted(set(rollout_failures)),
                # Backward-compatible alias; these are integrity failures only.
                "failures": sorted(set(rollout_failures)),
                "native_collision_callback_count": native_count,
                "native_collision_events": native_events,
                "native_collision_taxonomy": collision_taxonomy,
                "scientific_outcomes": {
                    "native_collision_contact_episodes": episode_count,
                    "native_collision_categories": sorted(rollout_categories),
                    "scenario_context_validity_warning_categories": validity_categories,
                    "footprint_collision": footprint_outcome,
                    "fixed_geometry_yield_success": fixed_rule_outcome,
                    "fixed_geometry_yield_outcome_reason": fixed_rule_outcome_reason,
                    "completion_success": completion if isinstance(completion, bool) else None,
                    "completion_source": completion_source,
                    "completion_reason": completion_reason,
                    "runtime_gate_passed": debug_stats["runtime_gate_passed"],
                    "reactive_active_samples": prediction_stats["reactive_active_samples"],
                    "adaptive_tightening_variation_observed": (
                        debug_stats["risk_manipulation"]["adaptive_variation_observed"]
                        if cell["risk_policy"] == "adaptive"
                        else None
                    ),
                    "footprint_margin_sensitivity": sensitivity_stats,
                },
                "spawned_actor_telemetry": actor_stats,
                "control_variables": control_stats,
                "attempt_provenance": receipt_stats,
                **debug_stats,
                **prediction_stats,
                "artifacts": {
                    "scenario_summary_sha256": sha256(summary_path),
                    "setup_sha256": sha256(setup_path),
                    "debug_sha256": sha256(debug_path),
                    "deployment_sha256": sha256(deployment_path),
                    "prediction_sha256": sha256(prediction_path),
                    "rollout_config_sha256": sha256(rollout_config_path),
                    "scenario_result_sha256": sha256(scenario_result_path),
                },
            }
            rollout_evaluations.append(rollout)
            cell_failures.extend(f"{scenario_dir.name}:{item}" for item in rollout["failures"])
        if cell["target_style"] == "reactive" and cell_reactive_active == 0:
            reactive_cells_without_active_samples.append(cell["cell_id"])
        evaluation = {
            **cell,
            "status": "pass" if not cell_failures else "fail",
            "integrity_status": "pass" if not cell_failures else "fail",
            "integrity_failures": sorted(set(cell_failures)),
            "failures": sorted(set(cell_failures)),
            "observed_rollouts": len(summaries),
            "reactive_active_samples": cell_reactive_active,
            "reactive_tail_exercised": bool(cell_reactive_active),
            "postcarla_overall_status_is_scientific_not_integrity": gate.get("overall_status"),
            "rollouts": rollout_evaluations,
        }
        evaluations.append(evaluation)
        failures.extend(f"{cell['cell_id']}:{item}" for item in evaluation["failures"])

    if observed_keys != expected_keys:
        failures.append("matrix:observed_treatment_keys")
    geometry_consistency = {}
    for init_id in sorted(expected_inits):
        points = geometry_by_init.get(init_id, [])
        consistent = len(points) == len(contract["cells"]) and all(
            np.allclose(points[0], value, atol=1e-3) for value in points[1:]
        )
        geometry_consistency[str(init_id)] = {
            "observations": len(points),
            "expected": len(contract["cells"]),
            "consistent_across_treatments": bool(consistent),
            "points": points[0].tolist() if points else None,
        }
        if not consistent:
            failures.append(f"matrix:fixed_geometry_consistency:init{init_id}")

    first_state_consistency = {}
    for init_id in sorted(expected_inits):
        observations = first_states_by_init.get(init_id, [])
        consistent_by_role = {}
        for role in ("ego", "target"):
            states = [
                np.asarray(item.get(role), dtype=float)
                for item in observations
                if item.get(role) is not None
            ]
            consistent_by_role[role] = bool(
                len(states) == len(contract["cells"])
                and all(state.shape == (5,) for state in states)
                and all(
                    np.allclose(states[0][1:], state[1:], atol=0.1)
                    for state in states[1:]
                )
            )
            if not consistent_by_role[role]:
                failures.append(f"matrix:first_state_consistency:init{init_id}:{role}")
        first_state_consistency[str(init_id)] = {
            "observations": len(observations),
            "expected": len(contract["cells"]),
            "consistent_by_role": consistent_by_role,
            "reference_txyyawspeed": {
                role: observations[0].get(role) if observations else None
                for role in ("ego", "target")
            },
            "comparison_ignores_absolute_simulation_timestamp": True,
            "state_tolerance_xy_yaw_speed": 0.1,
        }
    expected_scenario_hash = (contract.get("scenario_contract") or {}).get("sha256")
    scenario_source_consistent = len(scenario_source_hashes) == 1 and (
        expected_scenario_hash is None
        or next(iter(scenario_source_hashes), None) == expected_scenario_hash
    )
    if not scenario_source_consistent:
        failures.append("matrix:scenario_source_consistency")

    risk_manipulation_checks = {}
    for risk_policy, values in sorted(risk_manipulation_by_policy.items()):
        expected = FIXED_RISK_TIGHTENING.get(risk_policy)
        if expected is None:
            operating_point_ok = (
                values["audited_steps"] > 0
                and values["solver_applied_adaptive_steps"] == values["audited_steps"]
            )
        else:
            operating_point_ok = (
                values["audited_steps"] > 0
                and values["solver_applied_adaptive_steps"] == 0
                and math.isclose(float(values["tightening_min"]), expected, abs_tol=1e-9)
                and math.isclose(float(values["tightening_max"]), expected, abs_tol=1e-9)
            )
        risk_manipulation_checks[risk_policy] = {
            **values,
            "expected_fixed_tightening": expected,
            "solver_operating_point_identity_passed": bool(operating_point_ok),
        }
        if not operating_point_ok:
            failures.append(f"matrix:risk_manipulation:{risk_policy}")

    payload = {
        "schema_version": "r3_corrected_matrix_audit_v2",
        "status": "pass" if not failures else "fail",
        "integrity_status": "pass" if not failures else "fail",
        "stage": "R3",
        "formal_evidence": True,
        "implementation_version": CORRECTED,
        "expected_rollouts": int(contract["expected_rollouts"]),
        "observed_rollouts": len(observed_keys),
        "unique_treatment_keys": len(observed_keys),
        "passing_integrity_rollouts": sum(
            rollout.get("status") == "pass"
            for evaluation in evaluations
            for rollout in evaluation.get("rollouts", [])
        ),
        "scientific_outcome_taxonomy": {
            "native_collision_callback_events": total_native_collision_callbacks,
            "native_collision_contact_episodes": total_native_collision_episodes,
            "native_collision_rollouts": native_collision_rollouts,
            "native_collision_categories": {
                category: {
                    "callback_events": native_category_callbacks[category],
                    "contact_episodes": native_category_episodes[category],
                    "rollouts": native_category_rollouts[category],
                    "scenario_context_validity_warning": (
                        category in SCENARIO_VALIDITY_COLLISION_CATEGORIES
                    ),
                }
                for category in sorted(
                    set(native_category_callbacks)
                    | set(native_category_episodes)
                    | set(native_category_rollouts)
                )
            },
            "footprint_collision_rollouts": total_footprint_collisions,
            "footprint_outcome_unavailable_rollouts": unavailable_footprint_outcomes,
            "fixed_geometry_yield_failure_rollouts": total_yield_failures,
            "fixed_geometry_yield_outcome_unavailable_rollouts": unavailable_yield_outcomes,
            "completion_failure_rollouts": total_completion_failures,
            "completion_outcome_unavailable_rollouts": unavailable_completion_outcomes,
            "runtime_gate_exceeded_rollouts": runtime_gate_exceeded_rollouts,
            "reactive_cells_without_active_samples": sorted(
                reactive_cells_without_active_samples
            ),
            "adaptive_rollouts_without_tightening_variation": sorted(
                adaptive_cells_without_tightening_variation
            ),
            "learned_mode_collapse_by_predictor": {
                predictor: {
                    **values,
                    "fraction": (
                        values["learned_mode_collapse_steps"] / values["valid_steps"]
                        if values["valid_steps"]
                        else None
                    ),
                }
                for predictor, values in sorted(mode_consumption_by_predictor.items())
            },
            "adverse_outcomes_are_retained_not_excluded": True,
            "adverse_outcomes_do_not_change_integrity_status": True,
            "outcome_dependent_reruns_prohibited": True,
        },
        "risk_policy_manipulation_checks": risk_manipulation_checks,
        "total_valid_prediction_steps": total_valid_prediction_steps,
        "maximum_rollout_p95_solve_time_s": max_p95,
        "fixed_geometry_consistency": geometry_consistency,
        "first_state_consistency": first_state_consistency,
        "scenario_source_provenance": {
            "observed_sha256": sorted(scenario_source_hashes),
            "expected_sha256": expected_scenario_hash,
            "consistent": bool(scenario_source_consistent),
        },
        "contract_sha256": sha256(contract_path),
        "integrity_failures": sorted(set(failures)),
        "failures": sorted(set(failures)),
        "evaluations": evaluations,
    }
    atomic_json(args.output_json.resolve(), payload)
    print(json.dumps({key: payload[key] for key in ("status", "integrity_status", "observed_rollouts", "passing_integrity_rollouts", "scientific_outcome_taxonomy", "risk_policy_manipulation_checks", "integrity_failures")}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
