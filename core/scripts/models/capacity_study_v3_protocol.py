#!/usr/bin/env python3
"""Frozen protocol and integrity gates for the V3 capacity-history study.

This module is deliberately TensorFlow-free.  Training, evaluation, CARLA
collection, and thesis tooling all import the same immutable scientific
contract, so no downstream stage can silently redefine a model cell, split,
primary estimand, or deployment-selection rule.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "capacity_history_study_v3.0"
PROTOCOL_FILENAME = "capacity_history_study_v3.json"
PROTOCOL_PATH = Path(__file__).resolve().parent / "protocols" / PROTOCOL_FILENAME

CAPACITY_TARGETS = {
    "small": 170_000,
    "medium": 500_000,
    "large": 1_034_208,
}
CAPACITY_TOLERANCE_FRACTION = 0.05
HISTORY_TIMES_S = (-1.0, -0.8, -0.6, -0.4, -0.2, 0.0)
HISTORY_HORIZONS_S = (0.0, 0.4, 1.0)
HISTORY_MASKS = {
    0.0: (0, 0, 0, 0, 0, 1),
    0.4: (0, 0, 0, 1, 1, 1),
    1.0: (1, 1, 1, 1, 1, 1),
}
ENCODER_FAMILIES = ("mlp", "transformer")
HEAD_FAMILY = "head"
SEEDS = (11, 23, 37)
LEARNING_RATES = (3.0e-5, 1.0e-4, 3.0e-4)
CORE_EPOCHS = 80
EXTENDED_EPOCHS = 120
EARLY_STOPPING_PATIENCE = 12
OPTIMIZER_NAME = "adamw"
WEIGHT_DECAY = 1.0e-5
GRADIENT_CLIP_NORM = 10.0
ENCODER_DROPOUT = 0.1
BOUNDARY_WINDOW_EPOCHS = 5
BOUNDARY_FRACTION = 0.20
DATA_FRACTIONS = (0.25, 0.50, 0.75, 1.00)
GENERAL_TEST_GROUPS = tuple(range(51, 61))
CHALLENGE_TEST_GROUPS = tuple(range(61, 81))
CLOSED_LOOP_GROUPS = tuple(range(81, 91))
TRAIN_GROUPS = tuple(range(1, 41))
VALIDATION_GROUPS = tuple(range(41, 46))
RETROSPECTIVE_TEST_GROUPS = tuple(range(46, 51))
COLLECTION_CELLS = (
    "S0_FIXED",
    "S0_ADAPTIVE",
    "S1_FIXED",
    "S1_ADAPTIVE",
)
RISK_POLICIES = (
    "fixed_aggressive",
    "fixed_medium",
    "fixed_conservative",
    "adaptive",
)
TARGET_STYLES = ("assertive", "reactive")
PREDICTOR_ROLES = ("B1", "P_star")

# The band is inclusive so boundary samples have deterministic membership.
RESPONSE_ONSET_HALF_WIDTH_S = 0.6
DECELERATION_DROP_MPS = 0.5
CONFLICT_ZONE_BOUNDS_M = {
    "x_min": -4.0,
    "x_max": 4.0,
    "y_min": -4.0,
    "y_max": 4.0,
}


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def history_label(horizon_s: float) -> str:
    if horizon_s not in HISTORY_HORIZONS_S:
        raise ValueError(f"Unsupported history horizon: {horizon_s}")
    return f"h{horizon_s:.1f}".replace(".", "p")


def model_cell_id(family: str, capacity: str, history_s: float | None = None) -> str:
    if family == HEAD_FAMILY:
        if history_s is not None:
            raise ValueError("Head cells do not accept explicit interaction history")
        return f"head-{capacity}"
    if family not in ENCODER_FAMILIES or history_s is None:
        raise ValueError((family, capacity, history_s))
    return f"{family}-{history_label(history_s)}-{capacity}"


def expected_model_cells() -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for capacity, target in CAPACITY_TARGETS.items():
        cells.append(
            {
                "cell_id": model_cell_id(HEAD_FAMILY, capacity),
                "family": HEAD_FAMILY,
                "capacity_tier": capacity,
                "target_trainable_parameters": target,
                "history_horizon_s": None,
                "history_mask": None,
                "output_scope": "full_distribution",
                "foundation": "pretrained_B0",
            }
        )
    for family in ENCODER_FAMILIES:
        for horizon_s in HISTORY_HORIZONS_S:
            for capacity, target in CAPACITY_TARGETS.items():
                cells.append(
                    {
                        "cell_id": model_cell_id(family, capacity, horizon_s),
                        "family": family,
                        "capacity_tier": capacity,
                        "target_trainable_parameters": target,
                        "history_horizon_s": horizon_s,
                        "history_mask": list(HISTORY_MASKS[horizon_s]),
                        "output_scope": "full_distribution",
                        "foundation": "pretrained_B0",
                    }
                )
    return cells


def expected_core_run_count() -> int:
    return len(expected_model_cells()) * len(LEARNING_RATES) * len(SEEDS)


def expected_fraction_run_count() -> int:
    return 3 * len(DATA_FRACTIONS) * len(LEARNING_RATES) * len(SEEDS)


def load_protocol(path: str | Path = PROTOCOL_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require_equal(payload: Mapping[str, Any], key: str, expected: Any) -> None:
    if key not in payload:
        raise ValueError(f"Protocol is missing required field: {key}")
    if payload[key] != expected:
        raise ValueError(f"Frozen protocol field drift: {key}")


def validate_protocol(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate exact preregistered values, not merely JSON shape."""

    _require_equal(payload, "schema_version", SCHEMA_VERSION)
    _require_equal(payload, "status", "frozen")
    _require_equal(payload, "model_cells", expected_model_cells())
    _require_equal(payload, "capacity_targets", CAPACITY_TARGETS)
    _require_equal(payload, "capacity_tolerance_fraction", CAPACITY_TOLERANCE_FRACTION)
    _require_equal(payload, "history_times_s", list(HISTORY_TIMES_S))
    _require_equal(payload, "history_horizons_s", list(HISTORY_HORIZONS_S))
    _require_equal(payload, "seeds", list(SEEDS))
    _require_equal(payload, "learning_rates", list(LEARNING_RATES))
    _require_equal(payload, "core_epochs", CORE_EPOCHS)
    _require_equal(payload, "extended_epochs", EXTENDED_EPOCHS)
    _require_equal(payload, "early_stopping_patience", EARLY_STOPPING_PATIENCE)
    _require_equal(
        payload,
        "optimization_protocol",
        {
            "optimizer": OPTIMIZER_NAME,
            "weight_decay": WEIGHT_DECAY,
            "gradient_clip_norm": GRADIENT_CLIP_NORM,
            "encoder_dropout": ENCODER_DROPOUT,
            "checkpoint_metric": "validation_rollout_macro_trajectory_mixture_NLL_per_step",
            "checkpoint_unit": "rollout",
            "early_stopping_patience": EARLY_STOPPING_PATIENCE,
            "terminate_on_non_finite_loss_or_weights": True,
            "debug_sample_limits_allowed_in_formal_runs": False,
        },
    )
    _require_equal(
        payload,
        "training_integrity_gates",
        {
            "train_validation_group_disjoint": True,
            "expected_group_and_four_cell_support_required": True,
            "duplicate_sample_keys_forbidden": True,
            "missing_rasters_forbidden": True,
            "non_finite_inputs_or_labels_forbidden": True,
            "dataset_and_source_hashes_bound_to_completion": True,
            "training_health_report_required": True,
        },
    )
    _require_equal(payload, "core_run_count", expected_core_run_count())
    _require_equal(payload, "fraction_grid_run_count", expected_fraction_run_count())
    _require_equal(payload, "general_test_groups", list(GENERAL_TEST_GROUPS))
    _require_equal(payload, "challenge_test_groups", list(CHALLENGE_TEST_GROUPS))
    _require_equal(payload, "closed_loop_groups", list(CLOSED_LOOP_GROUPS))
    _require_equal(payload, "collection_cells", list(COLLECTION_CELLS))

    required_hypotheses = {
        "H1_capacity",
        "H2_information",
        "H3_architecture",
        "H4_model_risk_interaction",
    }
    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list) or {
        row.get("id") for row in hypotheses if isinstance(row, Mapping)
    } != required_hypotheses:
        raise ValueError("Protocol hypotheses are incomplete or changed")

    primary = payload.get("primary_estimands")
    expected_estimands = {
        "capacity_transformer_full_history_small_minus_large",
        "information_mlp_large_snapshot_minus_full",
        "information_transformer_large_snapshot_minus_full",
        "architecture_large_transformer_minus_mlp_history_gain",
        "model_risk_adaptive_minus_fixed_medium_difference_in_differences",
    }
    if not isinstance(primary, list) or {
        row.get("id") for row in primary if isinstance(row, Mapping)
    } != expected_estimands:
        raise ValueError("Primary estimand family is incomplete or changed")

    selection = payload.get("deployment_selection")
    if not isinstance(selection, Mapping):
        raise ValueError("deployment_selection is required")
    _require_equal(selection, "candidate_families", list(ENCODER_FAMILIES))
    _require_equal(selection, "metric", "median_validation_rollout_macro_nll")
    _require_equal(selection, "maximum_warmed_batch_one_latency_ms", 50.0)
    _require_equal(
        selection,
        "tie_breakers",
        ["trainable_parameters", "warmed_batch_one_latency", "model_cell_id"],
    )
    if payload.get("multiplicity", {}).get("method") != "holm":
        raise ValueError("Primary multiplicity method must remain Holm")
    if not payload.get("result_branches"):
        raise ValueError("Outcome-independent result branches are required")

    cell_ids = [row["cell_id"] for row in payload["model_cells"]]
    if len(cell_ids) != 21 or len(set(cell_ids)) != 21:
        raise ValueError("The V3 core must contain exactly 21 unique model cells")
    return {
        "status": "pass",
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": sha256_payload(payload),
        "model_cells": len(cell_ids),
        "core_runs": expected_core_run_count(),
    }


def validate_capacity_count(actual: int, target: int) -> None:
    if actual <= 0:
        raise ValueError("Trainable parameter count must be positive")
    relative_error = abs(actual - target) / target
    if relative_error > CAPACITY_TOLERANCE_FRACTION + 1.0e-12:
        raise ValueError(
            f"Capacity {actual} differs from target {target} by {relative_error:.3%}"
        )


def build_group_registry(seed: int = 20260822) -> dict[str, Any]:
    """Build deterministic init metadata without using candidate-model outputs."""

    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    challenge_offsets = [
        -2.50,
        -2.25,
        -2.00,
        -1.75,
        -1.50,
        -1.25,
        -1.00,
        -0.75,
        -0.50,
        -0.25,
        0.25,
        0.50,
        0.75,
        1.00,
        1.25,
        1.50,
        1.75,
        2.00,
        2.25,
        2.50,
    ]
    for group_id in (*GENERAL_TEST_GROUPS, *CHALLENGE_TEST_GROUPS, *CLOSED_LOOP_GROUPS):
        if group_id in GENERAL_TEST_GROUPS:
            group_set = "general_test"
            offset = rng.uniform(-2.5, 2.5)
        elif group_id in CHALLENGE_TEST_GROUPS:
            group_set = "interaction_challenge"
            offset = challenge_offsets[group_id - CHALLENGE_TEST_GROUPS[0]]
        else:
            group_set = "closed_loop"
            offset = rng.uniform(-2.5, 2.5)
        speed = rng.uniform(8.0, 10.0)
        records.append(
            {
                "ego_init_id": group_id,
                "group_set": group_set,
                "start_longitudinal_offset_m": round(offset, 9),
                "init_speed_mps": round(speed, 9),
                "generation_seed": seed,
            }
        )
    registry = {
        "schema_version": "capacity_history_group_registry_v1",
        "status": "frozen",
        "generated_without_candidate_model_outputs": True,
        "seed": seed,
        "geometry_bounds": {
            "start_longitudinal_offset_m": [-2.5, 2.5],
            "init_speed_mps": [8.0, 10.0],
        },
        "collection_cells": list(COLLECTION_CELLS),
        "records": records,
    }
    registry["registry_sha256"] = sha256_payload(registry)
    return registry


def validate_group_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(registry)
    payload.pop("payload_sha256", None)
    recorded_hash = payload.pop("registry_sha256", None)
    if recorded_hash != sha256_payload(payload):
        raise ValueError("Group registry hash mismatch")
    if payload.get("status") != "frozen" or not payload.get(
        "generated_without_candidate_model_outputs"
    ):
        raise ValueError("Group registry is not prospectively frozen")
    if payload.get("collection_cells") != list(COLLECTION_CELLS):
        raise ValueError("Four-cell collection pairing drift")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Group records are required")
    expected_ids = set(GENERAL_TEST_GROUPS + CHALLENGE_TEST_GROUPS + CLOSED_LOOP_GROUPS)
    actual_ids = [int(row["ego_init_id"]) for row in records]
    if len(actual_ids) != 40 or set(actual_ids) != expected_ids or len(set(actual_ids)) != 40:
        raise ValueError("Group registry must contain unique groups 51--90")
    if set(actual_ids).intersection(TRAIN_GROUPS + VALIDATION_GROUPS + RETROSPECTIVE_TEST_GROUPS):
        raise ValueError("Fresh groups overlap historical groups 1--50")
    for row in records:
        offset = float(row["start_longitudinal_offset_m"])
        speed = float(row["init_speed_mps"])
        if not -2.5 <= offset <= 2.5 or not 8.0 <= speed <= 10.0:
            raise ValueError(f"Geometry bounds failed for group {row['ego_init_id']}")
    counts = {
        name: sum(row["group_set"] == name for row in records)
        for name in ("general_test", "interaction_challenge", "closed_loop")
    }
    if counts != {"general_test": 10, "interaction_challenge": 20, "closed_loop": 10}:
        raise ValueError(f"Unexpected group-set counts: {counts}")
    return {"status": "pass", "group_counts": counts, "registry_sha256": recorded_hash}


def classify_response_stratum(
    *,
    target_style: str,
    sample_time_s: float,
    trigger_time_s: float | None,
    reactive_active: bool,
) -> str:
    """Return mutually exclusive preregistered response stratum."""

    if target_style in {"assertive", "assertive_constant_speed"}:
        return "assertive"
    if target_style not in {"reactive", "defensive_reactive"}:
        raise ValueError(f"Unknown target style: {target_style}")
    if trigger_time_s is None or not math.isfinite(float(trigger_time_s)):
        return "reactive_pre_response"
    delta = float(sample_time_s) - float(trigger_time_s)
    if -RESPONSE_ONSET_HALF_WIDTH_S <= delta <= RESPONSE_ONSET_HALF_WIDTH_S:
        return "response_onset"
    if delta > RESPONSE_ONSET_HALF_WIDTH_S and reactive_active:
        return "response_active"
    return "reactive_pre_response"


def first_deceleration_onset_s(
    times_s: Sequence[float],
    speeds_mps: Sequence[float],
    *,
    drop_mps: float = DECELERATION_DROP_MPS,
) -> float | None:
    if len(times_s) != len(speeds_mps) or len(times_s) == 0:
        raise ValueError("Times and speeds must be non-empty and equally sized")
    baseline = float(speeds_mps[0])
    for time_s, speed in zip(times_s, speeds_mps):
        if baseline - float(speed) >= drop_mps:
            return float(time_s)
    return None


def conflict_zone_entry_time_s(
    times_s: Sequence[float],
    xy_m: Sequence[Sequence[float]],
    *,
    bounds: Mapping[str, float] = CONFLICT_ZONE_BOUNDS_M,
) -> float | None:
    if len(times_s) != len(xy_m):
        raise ValueError("Times and positions must be equally sized")
    for time_s, point in zip(times_s, xy_m):
        if len(point) != 2:
            raise ValueError("Every conflict-zone point must be two-dimensional")
        x, y = float(point[0]), float(point[1])
        if (
            bounds["x_min"] <= x <= bounds["x_max"]
            and bounds["y_min"] <= y <= bounds["y_max"]
        ):
            return float(time_s)
    return None


def write_immutable_manifest(path: str | Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Write once; an identical retry is safe and any semantic drift fails."""

    destination = Path(path)
    frozen = dict(payload)
    frozen.setdefault("status", "pass")
    frozen["payload_sha256"] = sha256_payload(
        {key: value for key, value in frozen.items() if key != "payload_sha256"}
    )
    if destination.exists():
        existing = json.loads(destination.read_text(encoding="utf-8"))
        if existing != frozen:
            raise ValueError(f"Immutable manifest drift: {destination}")
        return existing
    atomic_json(destination, frozen)
    return frozen


def verify_immutable_manifest(
    path: str | Path,
    *,
    required_status: str = "pass",
    bound_artifacts: Mapping[str, str | Path] | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    expected_hash = sha256_payload(
        {key: value for key, value in payload.items() if key != "payload_sha256"}
    )
    if payload.get("payload_sha256") != expected_hash:
        raise ValueError(f"Manifest payload hash mismatch: {path}")
    if payload.get("status") != required_status:
        raise ValueError(f"Manifest status is not {required_status}: {path}")
    if bound_artifacts:
        recorded = payload.get("artifact_sha256", {})
        for name, artifact_path in bound_artifacts.items():
            if recorded.get(name) != sha256_file(artifact_path):
                raise ValueError(f"Bound artifact drift: {name}")
    return payload


STAGE_GATE_REQUIREMENTS = {
    "training": ("protocol", "train_dataset"),
    "validation_selection": ("training_matrix", "validation_metrics", "capacity_audit"),
    "calibration": ("selection", "validation_dataset"),
    "general_test": ("selection", "convergence", "capacity_audit", "calibration"),
    "challenge_test": ("selection", "convergence", "capacity_audit", "calibration"),
    "deployment": ("selection", "calibration", "latency"),
    "formal_carla": ("deployment", "closed_loop_manifest", "preflight"),
}


def require_stage_gates(stage: str, gates: Mapping[str, str | Path]) -> dict[str, Any]:
    if stage not in STAGE_GATE_REQUIREMENTS:
        raise ValueError(f"Unknown protected stage: {stage}")
    required = STAGE_GATE_REQUIREMENTS[stage]
    missing = [name for name in required if name not in gates]
    if missing:
        raise ValueError(f"Missing gates for {stage}: {missing}")
    verified: dict[str, str] = {}
    for name in required:
        path = Path(gates[name])
        verify_immutable_manifest(path)
        verified[name] = sha256_file(path)
    return {"status": "pass", "stage": stage, "verified_gates": verified}


def nested_training_groups(seed: int = 20260822) -> dict[str, list[int]]:
    ordered = list(TRAIN_GROUPS)
    random.Random(seed).shuffle(ordered)
    return {
        "0.25": sorted(ordered[:10]),
        "0.50": sorted(ordered[:20]),
        "0.75": sorted(ordered[:30]),
        "1.00": sorted(ordered[:40]),
    }


def validate_nested_training_groups(fractions: Mapping[str, Iterable[int]]) -> None:
    previous: set[int] = set()
    expected_sizes = {"0.25": 10, "0.50": 20, "0.75": 30, "1.00": 40}
    for label, size in expected_sizes.items():
        current = {int(value) for value in fractions[label]}
        if len(current) != size or not previous.issubset(current):
            raise ValueError(f"Training fraction {label} is not nested with size {size}")
        if not current.issubset(TRAIN_GROUPS):
            raise ValueError(f"Training fraction {label} leaks outside groups 1--40")
        previous = current


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--write-group-registry", type=Path)
    parser.add_argument("--validate-group-registry", type=Path)
    args = parser.parse_args()
    report = validate_protocol(load_protocol(args.protocol))
    if args.write_group_registry:
        registry = build_group_registry()
        existing = write_immutable_manifest(args.write_group_registry, registry)
        report["group_registry"] = validate_group_registry(existing)
    if args.validate_group_registry:
        registry = json.loads(args.validate_group_registry.read_text(encoding="utf-8"))
        report["group_registry"] = validate_group_registry(registry)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
