#!/usr/bin/env python3
"""Formal R3 v2 outcome analysis.

The top-level status in the generated receipt is an *analysis integrity*
status.  Collisions, null effects, failed manipulation checks and failure to
support H3/H4 are valid scientific results and never make that status fail.
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
import csv
import datetime as dt
import hashlib
import itertools
import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from analyze_formal_inloop_prediction_quality import METRICS as PREDICTION_METRICS
from analyze_formal_inloop_prediction_quality import full_horizon, sample_metrics
from distinction_analysis_utils import atomic_write_json, sha256_file, write_csv


SCHEMA_VERSION = "r3_corrected_formal_analysis_v2_hardened"
IMPLEMENTATION_VERSION = "corrected_joint_modes_shared_amin_v1"
PRIMARY_METRICS = (
    "ego_route_completion_duration_s",
    "minimum_footprint_separation_m",
)
FAILURE_METRICS = (
    "native_collision_any",
    "footprint_collision",
    "fixed_geometry_yield_failure",
    "completion_failure",
)
FIXED_POLICIES = ("fixed_aggressive", "fixed_medium", "fixed_conservative")
PREDICTORS = ("B1", "B0")
STYLES = ("assertive", "reactive")
FOOTPRINT_MARGINS = (0.0, 0.25, 0.35, 0.5)
COLLISION_CATEGORIES = (
    "ego_target",
    "ego_infrastructure",
    "target_infrastructure",
    "ego_static_vehicle",
    "target_static_vehicle",
    "other",
)
RAW_REQUIRED_FILES = (
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
RAW_OPTIONAL_FILES = ("smpc_completion.json",)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def raw_evidence_sha256(scenario_dir: Path) -> str:
    """Recompute the attempt-manager immutable raw-evidence digest."""

    digest = hashlib.sha256()
    for relative in RAW_REQUIRED_FILES + RAW_OPTIONAL_FILES:
        path = scenario_dir / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii") if path.is_file() else b"ABSENT_BY_DESIGN")
        digest.update(b"\n")
    return digest.hexdigest()


def finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def number(value: object) -> float | None:
    return float(value) if finite(value) else None


def boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True"):
        return True
    if value in (0, "0", "false", "False"):
        return False
    return None


def init_id_from_name(name: str) -> int:
    match = re.search(r"_ego_init_(\d+)_", name)
    if not match:
        raise ValueError(f"Cannot parse ego init ID from {name!r}")
    return int(match.group(1))


def mean(values: Iterable[float]) -> float | None:
    clean = [float(value) for value in values if finite(value)]
    return statistics.fmean(clean) if clean else None


def median(values: Iterable[float]) -> float | None:
    clean = [float(value) for value in values if finite(value)]
    return statistics.median(clean) if clean else None


def weighted_mean(rows: Sequence[Mapping[str, object]], field: str, weight_field: str = "n_steps") -> float | None:
    values: list[tuple[float, float]] = []
    for row in rows:
        value = number(row.get(field))
        weight = number(row.get(weight_field))
        if value is not None and weight is not None and weight > 0:
            values.append((value, weight))
    denominator = sum(weight for _, weight in values)
    return sum(value * weight for value, weight in values) / denominator if denominator else None


def exact_sign_flip_p(effects: Sequence[float], tolerance: float = 1e-15) -> float | None:
    """Two-sided exhaustive randomisation p-value for paired cluster effects."""

    values = [float(value) for value in effects if finite(value)]
    if not values:
        return None
    observed = abs(statistics.fmean(values))
    extreme = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(values)):
        permuted = abs(statistics.fmean(sign * value for sign, value in zip(signs, values)))
        extreme += int(permuted + tolerance >= observed)
    return extreme / float(2 ** len(values))


def bootstrap_seed(global_seed: int, contrast_id: str, metric: str) -> int:
    value = f"{global_seed}|{contrast_id}|{metric}".encode("utf-8")
    return int(hashlib.sha256(value).hexdigest()[:16], 16)


def bootstrap_mean_ci(
    effects: Sequence[float],
    *,
    global_seed: int,
    contrast_id: str,
    metric: str,
    replicates: int,
    lower: float,
    upper: float,
) -> tuple[float | None, float | None]:
    values = np.asarray([float(value) for value in effects if finite(value)], dtype=np.float64)
    if values.size == 0:
        return None, None
    rng = np.random.default_rng(bootstrap_seed(global_seed, contrast_id, metric))
    indices = rng.integers(0, values.size, size=(replicates, values.size))
    boot = values[indices].mean(axis=1)
    return float(np.percentile(boot, lower)), float(np.percentile(boot, upper))


def holm_adjust(rows: list[dict], family_fields: Sequence[str], declared_size: int) -> None:
    """Add Holm p-values in place, retaining the prespecified family size."""

    families: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        families[tuple(row[field] for field in family_fields)].append(row)
    for family_rows in families.values():
        finite_rows = sorted(
            (row for row in family_rows if finite(row.get("exact_sign_flip_p_raw"))),
            key=lambda row: float(row["exact_sign_flip_p_raw"]),
        )
        running = 0.0
        for rank, row in enumerate(finite_rows, start=1):
            candidate = min(1.0, (declared_size - rank + 1) * float(row["exact_sign_flip_p_raw"]))
            running = max(running, candidate)
            row["holm_adjusted_p"] = running
        for row in family_rows:
            row.setdefault("holm_adjusted_p", None)
            row["holm_family_declared_size"] = declared_size
            row["holm_family_observed_p_values"] = len(finite_rows)


def _missing_reason(row: Mapping[str, object], metric: str) -> str:
    reasons = str(row.get("continuous_outcome_missing_reasons") or "")
    matched = [part for part in reasons.split(";") if part.startswith(f"{metric}:")]
    return ";".join(matched) or "nonfinite_or_missing"


def paired_continuous_contrast(
    index: Mapping[tuple[str, str, str, int], Mapping[str, object]],
    *,
    hypothesis: str,
    contrast_id: str,
    treatment_predictor: str,
    control_predictor: str,
    treatment_policy: str,
    control_policy: str,
    target_style: str,
    metric: str,
    init_ids: Sequence[int],
    bootstrap: Mapping[str, object],
) -> tuple[list[dict], dict]:
    effects: list[dict] = []
    for init_id in init_ids:
        treatment = index.get((treatment_predictor, treatment_policy, target_style, init_id))
        control = index.get((control_predictor, control_policy, target_style, init_id))
        treatment_value = number(treatment.get(metric)) if treatment else None
        control_value = number(control.get(metric)) if control else None
        complete = treatment_value is not None and control_value is not None
        reasons: list[str] = []
        if treatment is None:
            reasons.append("treatment_row_missing")
        elif treatment_value is None:
            reasons.append(f"treatment:{_missing_reason(treatment, metric)}")
        if control is None:
            reasons.append("control_row_missing")
        elif control_value is None:
            reasons.append(f"control:{_missing_reason(control, metric)}")
        effects.append(
            {
                "hypothesis": hypothesis,
                "contrast_id": contrast_id,
                "metric": metric,
                "target_style": target_style,
                "treatment_predictor": treatment_predictor,
                "control_predictor": control_predictor,
                "treatment_policy": treatment_policy,
                "control_policy": control_policy,
                "ego_init_id": init_id,
                "treatment_value": treatment_value,
                "control_value": control_value,
                "treatment_minus_control": treatment_value - control_value if complete else None,
                "pair_complete": int(complete),
                "missing_reason": ";".join(reasons),
            }
        )
    complete_effects = [float(row["treatment_minus_control"]) for row in effects if row["pair_complete"]]
    missing_ids = [int(row["ego_init_id"]) for row in effects if not row["pair_complete"]]
    lower, upper = bootstrap_mean_ci(
        complete_effects,
        global_seed=int(bootstrap["global_seed"]),
        contrast_id=contrast_id,
        metric=metric,
        replicates=int(bootstrap["replicates"]),
        lower=float(bootstrap["lower_percentile"]),
        upper=float(bootstrap["upper_percentile"]),
    )
    summary = {
        "hypothesis": hypothesis,
        "contrast_id": contrast_id,
        "metric": metric,
        "target_style": target_style,
        "treatment_predictor": treatment_predictor,
        "control_predictor": control_predictor,
        "treatment_policy": treatment_policy,
        "control_policy": control_policy,
        "effect_orientation": "treatment_minus_control",
        "expected_clusters": len(init_ids),
        "complete_clusters": len(complete_effects),
        "missing_clusters": len(missing_ids),
        "missing_init_ids": ";".join(map(str, missing_ids)),
        "mean_effect": mean(complete_effects),
        "median_effect": median(complete_effects),
        "exact_sign_flip_p_raw": exact_sign_flip_p(complete_effects),
        "bootstrap_mean_ci_lower": lower,
        "bootstrap_mean_ci_upper": upper,
        "bootstrap_replicates": int(bootstrap["replicates"]),
        "bootstrap_global_seed": int(bootstrap["global_seed"]),
        "bootstrap_role": "descriptive_only",
    }
    return effects, summary


def paired_binary_summary(
    index: Mapping[tuple[str, str, str, int], Mapping[str, object]],
    *,
    hypothesis: str,
    contrast_id: str,
    treatment_predictor: str,
    control_predictor: str,
    treatment_policy: str,
    control_policy: str,
    target_style: str,
    metric: str,
    init_ids: Sequence[int],
) -> dict:
    effects: list[int] = []
    missing_ids: list[int] = []
    treatment_events = 0
    control_events = 0
    raw: list[str] = []
    for init_id in init_ids:
        treatment = index.get((treatment_predictor, treatment_policy, target_style, init_id))
        control = index.get((control_predictor, control_policy, target_style, init_id))
        left = treatment.get(metric) if treatment else None
        right = control.get(metric) if control else None
        if left not in (0, 1) or right not in (0, 1):
            missing_ids.append(init_id)
            raw.append(f"{init_id}:NA")
            continue
        effect = int(left) - int(right)
        treatment_events += int(left)
        control_events += int(right)
        effects.append(effect)
        raw.append(f"{init_id}:{effect}")
    return {
        "hypothesis": hypothesis,
        "contrast_id": contrast_id,
        "failure_metric": metric,
        "target_style": target_style,
        "treatment_predictor": treatment_predictor,
        "control_predictor": control_predictor,
        "treatment_policy": treatment_policy,
        "control_policy": control_policy,
        "expected_clusters": len(init_ids),
        "complete_clusters": len(effects),
        "missing_clusters": len(missing_ids),
        "missing_init_ids": ";".join(map(str, missing_ids)),
        "treatment_failure_rollouts": treatment_events,
        "control_failure_rollouts": control_events,
        "mean_treatment_minus_control": mean(effects),
        "raw_init_effects": ";".join(raw),
        "no_excess_observed_failure": int(len(effects) == len(init_ids) and sum(effects) <= 0),
        "intent_to_treat_rollout_binary": 1,
    }


def _prediction_rollout(path: Path, predictor: str, calibration: Mapping[str, object]) -> dict:
    rows = read_jsonl(path)
    metrics: dict[str, list[float]] = defaultdict(list)
    reactive = 0
    full = 0
    for row in rows:
        reactive += int(bool((row.get("target_reactive_diagnostics") or {}).get("active")))
        if not full_horizon(row):
            continue
        values = sample_metrics(row, predictor, dict(calibration))
        full += 1
        for metric in PREDICTION_METRICS:
            metrics[metric].append(float(values[metric]))
    return {
        "prediction_logged_samples": len(rows),
        "prediction_full_horizon_samples": full,
        "prediction_reactive_active_samples": reactive,
        **{f"prediction_{metric}": mean(metrics[metric]) for metric in PREDICTION_METRICS},
    }


def _canonical_collision_stats(audit_item: Mapping[str, object] | None) -> tuple[dict, list[str]]:
    issues: list[str] = []
    taxonomy = (audit_item or {}).get("native_collision_taxonomy") or {}
    categories = taxonomy.get("categories") or {}
    required = (
        "schema_version",
        "episode_definition",
        "callback_event_count",
        "validated_callback_event_count",
        "contact_episode_count",
        "episodes",
    )
    if not taxonomy or any(key not in taxonomy for key in required):
        issues.append("canonical_native_collision_taxonomy_missing")
    callbacks = int(taxonomy.get("callback_event_count", 0) or 0)
    validated = int(taxonomy.get("validated_callback_event_count", 0) or 0)
    episodes = int(taxonomy.get("contact_episode_count", 0) or 0)
    category_callbacks: dict[str, int] = {}
    category_episodes: dict[str, int] = {}
    unknown_categories = sorted(set(categories) - set(COLLISION_CATEGORIES))
    if unknown_categories:
        issues.append(f"native_collision_unknown_categories:{','.join(unknown_categories)}")
    for category in COLLISION_CATEGORIES:
        value = categories.get(category) or {}
        category_callbacks[category] = int(value.get("callback_events", 0) or 0)
        category_episodes[category] = int(value.get("contact_episodes", 0) or 0)
    if sum(category_callbacks.values()) != validated:
        issues.append("canonical_collision_category_callback_sum_mismatch")
    if sum(category_episodes.values()) != episodes:
        issues.append("canonical_collision_category_episode_sum_mismatch")
    if len(taxonomy.get("episodes") or []) != episodes:
        issues.append("canonical_collision_episode_record_count_mismatch")
    return {
        "native_collision_callback_count": callbacks,
        "native_collision_validated_callback_count": validated,
        "native_collision_episode_count": episodes,
        "native_collision_any": int(episodes > 0),
        "native_collision_rollout_count": int(episodes > 0),
        "native_collision_taxonomy_schema": taxonomy.get("schema_version"),
        "native_collision_episode_definition_json": json.dumps(taxonomy.get("episode_definition"), sort_keys=True),
        "native_collision_category_callback_counts_json": json.dumps(category_callbacks, sort_keys=True),
        "native_collision_category_episode_counts_json": json.dumps(category_episodes, sort_keys=True),
        "native_collision_episodes_json": json.dumps(taxonomy.get("episodes") or [], sort_keys=True),
        **{f"native_collision_{category}_callback_count": category_callbacks[category] for category in COLLISION_CATEGORIES},
        **{f"native_collision_{category}_episode_count": category_episodes[category] for category in COLLISION_CATEGORIES},
    }, issues


def _actor_geometry(audit_item: Mapping[str, object] | None) -> tuple[dict, list[str]]:
    issues: list[str] = []
    telemetry = (audit_item or {}).get("spawned_actor_telemetry") or {}
    actors = telemetry.get("actors") or []
    if not telemetry or not actors:
        issues.append("spawned_actor_telemetry_missing")
    selected: dict[str, Mapping[str, object]] = {}
    for actor in actors:
        role = str(actor.get("experiment_role") or "")
        if role in ("ego", "target") and role not in selected:
            selected[role] = actor
    for role in ("ego", "target"):
        if role not in selected:
            issues.append(f"spawned_actor_role_missing:{role}")
    output: dict[str, object] = {
        "spawned_actor_count": telemetry.get("actor_count"),
        "spawned_actor_role_counts_json": json.dumps(telemetry.get("role_counts") or {}, sort_keys=True),
        "spawned_actor_telemetry_json": json.dumps(telemetry, sort_keys=True),
    }
    for role in ("ego", "target"):
        actor = selected.get(role) or {}
        bbox = actor.get("bounding_box") or {}
        dimensions = bbox.get("dimensions_m") or {}
        if isinstance(dimensions, dict):
            dimension_values = [dimensions.get(key) for key in ("length", "width", "height")]
        else:
            dimension_values = list(dimensions)
        output.update(
            {
                f"{role}_actor_id": actor.get("actor_id"),
                f"{role}_actor_type": actor.get("actor_type"),
                f"{role}_requested_blueprint": actor.get("requested_blueprint"),
                f"{role}_bbox_dimensions_m_json": json.dumps(dimensions, sort_keys=True),
                f"{role}_bbox_local_center_m_json": json.dumps(bbox.get("local_center_m")),
                f"{role}_bbox_local_rotation_deg_json": json.dumps(bbox.get("local_rotation_deg")),
                f"{role}_effective_vehicle_params_json": json.dumps(actor.get("effective_vehicle_params"), sort_keys=True),
            }
        )
        if len(dimension_values) < 2 or not all(finite(value) and float(value) > 0 for value in dimension_values[:2]):
            issues.append(f"{role}_bbox_dimensions_invalid")
    return output, issues


def _rollout_receipt(cell_dir: Path, cell_id: str, init_id: int, scenario_name: str) -> tuple[dict, list[str]]:
    issues: list[str] = []
    receipt_path = cell_dir / f"R3_ROLLOUT_{init_id}_COMPLETE.json"
    if not receipt_path.is_file():
        return {"rollout_receipt_path": str(receipt_path)}, ["rollout_receipt_missing"]
    receipt = read_json(receipt_path)
    if (
        receipt.get("schema_version") != "r3_rollout_complete_v2"
        or receipt.get("status") != "pass"
        or receipt.get("cell_id") != cell_id
        or int(receipt.get("ego_init_id", -1)) != init_id
        or Path(str(receipt.get("scenario_dir") or "")).name != scenario_name
    ):
        issues.append("rollout_receipt_identity_or_status")
    critical = receipt.get("critical_artifacts") or {}
    accepted_scenario_dir = cell_dir / str(receipt.get("scenario_dir") or "")
    for relative in RAW_REQUIRED_FILES:
        artifact = critical.get(relative) or {}
        if not finite(artifact.get("bytes")) or not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256") or "")):
            issues.append(f"rollout_receipt_critical_artifact:{relative}")
            continue
        artifact_path = accepted_scenario_dir / relative
        if (
            not artifact_path.is_file()
            or artifact_path.stat().st_size != int(artifact["bytes"])
            or sha256_file(artifact_path) != artifact["sha256"]
        ):
            issues.append(f"rollout_receipt_critical_artifact_hash:{relative}")
    optional_presence = receipt.get("optional_artifact_presence") or {}
    for relative in RAW_OPTIONAL_FILES:
        source = accepted_scenario_dir / relative
        declared_present = boolean(optional_presence.get(relative))
        if declared_present is None or declared_present != source.is_file():
            issues.append(f"rollout_receipt_optional_presence:{relative}")
        if source.is_file():
            artifact = critical.get(relative) or {}
            if (
                not finite(artifact.get("bytes"))
                or int(artifact["bytes"]) != source.stat().st_size
                or artifact.get("sha256") != sha256_file(source)
            ):
                issues.append(f"rollout_receipt_optional_artifact_hash:{relative}")
    for field in (
        "raw_evidence_sha256",
        "scenario_summary_sha256",
        "attempt_record_sha256",
        "attempt_ledger_sha256_at_receipt",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get(field) or "")):
            issues.append(f"rollout_receipt_hash:{field}")
    if not isinstance(receipt.get("accepted_attempt"), int) or int(receipt.get("accepted_attempt", 0)) < 1:
        issues.append("rollout_receipt_accepted_attempt")
    recomputed_raw_hash = raw_evidence_sha256(accepted_scenario_dir)
    if receipt.get("raw_evidence_sha256") != recomputed_raw_hash:
        issues.append("rollout_receipt_raw_evidence_hash")
    if receipt.get("scenario_summary_sha256") != (critical.get("scenario_run_summary.json") or {}).get("sha256"):
        issues.append("rollout_receipt_scenario_summary_hash_disagreement")
    for path_field, hash_field in (
        ("attempt_record", "attempt_record_sha256"),
        ("attempt_ledger", "attempt_ledger_sha256_at_receipt"),
    ):
        relative = receipt.get(path_field)
        source = cell_dir / str(relative) if relative else None
        if source is None or not source.is_file() or sha256_file(source) != receipt.get(hash_field):
            issues.append(f"rollout_receipt_source_hash:{path_field}")
    return {
        "rollout_receipt_path": str(receipt_path.relative_to(cell_dir.parent)),
        "rollout_receipt_sha256": sha256_file(receipt_path),
        "accepted_attempt": receipt.get("accepted_attempt"),
        "recovered_after_interruption": int(bool(receipt.get("recovered_after_interruption"))),
        "raw_evidence_sha256": receipt.get("raw_evidence_sha256"),
        "receipt_scenario_summary_sha256": receipt.get("scenario_summary_sha256"),
        "attempt_record_path": receipt.get("attempt_record"),
        "attempt_record_sha256": receipt.get("attempt_record_sha256"),
        "attempt_ledger_path": receipt.get("attempt_ledger"),
        "attempt_ledger_sha256_at_receipt": receipt.get("attempt_ledger_sha256_at_receipt"),
        "critical_artifacts_json": json.dumps(critical, sort_keys=True),
        "critical_scenario_result_sha256": (critical.get("scenario_result.pkl") or {}).get("sha256"),
        "critical_scenario_steps_sha256": (critical.get("scenario_steps.csv") or {}).get("sha256"),
        "critical_smpc_debug_steps_sha256": (critical.get("smpc_debug_steps.jsonl") or {}).get("sha256"),
        "accepted_at_utc": receipt.get("accepted_at_utc"),
    }, issues


def load_rollout_outcomes(
    results_dir: Path,
    contract: Mapping[str, object],
    audit: Mapping[str, object],
    analysis_contract: Mapping[str, object],
) -> tuple[list[dict], list[dict], list[str]]:
    """Materialise one row for every prespecified treatment-init key."""

    issues: list[str] = []
    audit_rollouts: dict[tuple[str, int], Mapping[str, object]] = {}
    for evaluation in audit.get("evaluations", []):
        for rollout in evaluation.get("rollouts", []):
            audit_rollouts[(str(evaluation["cell_id"]), int(rollout["ego_init_id"]))] = rollout
    tolerances = analysis_contract["numerical_tolerances"]
    timestamp_tolerance = float(tolerances["timestamp_consistency_tolerance_s"])
    distance_tolerance = float(tolerances["distance_dominance_tolerance_m"])
    outcomes: list[dict] = []
    sensitivity_outcomes: list[dict] = []
    for cell in contract["cells"]:
        cell_id = str(cell["cell_id"])
        cell_dir = results_dir / cell_id
        gate_path = cell_dir / "postcarla_trajectory_gate.json"
        df_path = cell_dir / "df_full.csv"
        risk_path = cell_dir / "risk_by_conflict_distance_summary.csv"
        gate = read_json(gate_path) if gate_path.is_file() else {"evaluations": []}
        df_rows = read_csv(df_path) if df_path.is_file() else []
        risk_rows = read_csv(risk_path) if risk_path.is_file() else []
        if not gate_path.is_file():
            issues.append(f"{cell_id}:missing_postcarla_trajectory_gate")
        if not df_path.is_file():
            issues.append(f"{cell_id}:missing_df_full")
        if not risk_path.is_file():
            issues.append(f"{cell_id}:missing_risk_summary")
        gate_by_init: dict[int, dict] = {}
        for item in gate.get("evaluations", []):
            try:
                gate_by_init[init_id_from_name(Path(item["scenario_dir"]).name)] = item
            except (KeyError, ValueError):
                issues.append(f"{cell_id}:unparseable_gate_scenario")
        risk_by_init: dict[int, list[dict]] = defaultdict(list)
        for item in risk_rows:
            value = number(item.get("initial"))
            if value is not None:
                risk_by_init[int(value)].append(item)
        for init_id in map(int, contract["ego_init_ids"]):
            integrity: list[str] = []
            missing: list[str] = []
            gate_item = gate_by_init.get(init_id)
            df_matches = [row for row in df_rows if number(row.get("initial")) == float(init_id)]
            df_item = df_matches[0] if len(df_matches) == 1 else None
            rollout_risk = risk_by_init.get(init_id, [])
            audit_item = audit_rollouts.get((cell_id, init_id))
            if gate_item is None:
                integrity.append("gate_rollout_missing")
            if df_item is None:
                integrity.append(f"df_rollout_count_{len(df_matches)}")
            if not rollout_risk:
                integrity.append("risk_rollout_missing")
            if audit_item is None:
                integrity.append("audit_rollout_missing")
            elif audit_item.get("integrity_status") != "pass" or audit_item.get("integrity_failures"):
                integrity.append("audit_rollout_integrity_not_pass")

            scenario_name = Path(gate_item["scenario_dir"]).name if gate_item else ""
            completion = boolean(gate_item.get("completion_valid")) if gate_item else None
            df_completion = boolean(df_item.get("completion_valid")) if df_item else None
            if completion is not None and df_completion is not None and completion != df_completion:
                integrity.append("completion_flag_disagreement")
            df_logged_duration = number(df_item.get("completion_time")) if df_item else None
            scenario_dir = cell_dir / scenario_name if scenario_name else None
            completion_marker_path = scenario_dir / "smpc_completion.json" if scenario_dir else None
            scenario_summary_path = scenario_dir / "scenario_run_summary.json" if scenario_dir else None
            completion_marker = (
                read_json(completion_marker_path)
                if completion_marker_path is not None and completion_marker_path.is_file()
                else None
            )
            scenario_summary = (
                read_json(scenario_summary_path)
                if scenario_summary_path is not None and scenario_summary_path.is_file()
                else None
            )
            completion_step = number((completion_marker or {}).get("step"))
            carla_fps = number((scenario_summary or {}).get("carla_fps"))
            completion_duration = (
                completion_step / carla_fps
                if completion is True
                and completion_step is not None
                and carla_fps is not None
                and carla_fps > 0
                else None
            )
            if completion is not True:
                missing.append("ego_route_completion_duration_s:completion_not_valid")
            elif completion_duration is None:
                integrity.append("valid_completion_missing_event_clock")
                missing.append("ego_route_completion_duration_s:event_clock_nonfinite_or_missing")
            if completion is True and completion_marker is None:
                integrity.append("valid_completion_marker_missing")
            if scenario_summary is None:
                integrity.append("scenario_run_summary_missing")
            if (
                completion_duration is not None
                and df_logged_duration is not None
                and abs(completion_duration - df_logged_duration) > timestamp_tolerance
            ):
                integrity.append("event_clock_disagrees_with_df_logged_duration")

            rollout_start = min(
                (float(row["sim_time_start_s"]) for row in rollout_risk if finite(row.get("sim_time_start_s"))),
                default=None,
            )
            rollout_end = max(
                (float(row["sim_time_end_s"]) for row in rollout_risk if finite(row.get("sim_time_end_s"))),
                default=None,
            )
            ego_completion_timestamp = (
                rollout_start + completion_duration
                if rollout_start is not None and completion_duration is not None
                else None
            )
            if rollout_start is None:
                integrity.append("rollout_start_missing")
            if (
                ego_completion_timestamp is not None
                and rollout_end is not None
                and abs(ego_completion_timestamp - rollout_end) > timestamp_tolerance
            ):
                integrity.append("completion_timestamp_disagrees_with_rollout_end")

            fixed_rules = (gate_item or {}).get("fixed_geometry_yield_rules") or []
            rule = fixed_rules[0] if len(fixed_rules) == 1 else None
            if rule is None:
                integrity.append(f"fixed_geometry_rule_count_{len(fixed_rules)}")
            target_exit = number(rule.get("target_exit_time_s")) if rule else None
            target_enter = number(rule.get("target_enter_time_s")) if rule else None
            ego_enter = number(rule.get("ego_enter_time_s")) if rule else None
            ego_exit = number(rule.get("ego_exit_time_s")) if rule else None
            target_exit_elapsed = target_exit - rollout_start if target_exit is not None and rollout_start is not None else None
            post_clearance_lag = (
                ego_completion_timestamp - target_exit
                if ego_completion_timestamp is not None and target_exit is not None
                else None
            )
            yield_gap = ego_enter - target_exit if ego_enter is not None and target_exit is not None else None
            if target_exit is None:
                missing.append("target_fixed_zone_exit_elapsed_s:target_exit_censored")
                missing.append("post_clearance_completion_lag_s:target_exit_censored")
            if ego_completion_timestamp is None:
                missing.append("post_clearance_completion_lag_s:ego_completion_censored")
            if ego_enter is None or target_exit is None:
                missing.append("fixed_geometry_yield_gap_s:entry_or_exit_censored")
            yield_outcome = boolean(rule.get("target_clears_before_ego_enters")) if rule else None

            pairs = (gate_item or {}).get("pair_safety") or []
            pair = pairs[0] if len(pairs) == 1 else None
            if pair is None:
                integrity.append(f"pair_safety_count_{len(pairs)}")
            separation = number(pair.get("min_footprint_separation_m")) if pair else None
            footprint_collision = boolean(pair.get("footprint_collision")) if pair else None
            if separation is None:
                missing.append("minimum_footprint_separation_m:nonfinite_or_missing")

            scientific_outcomes = (audit_item or {}).get("scientific_outcomes") or {}
            native_stats, native_issues = _canonical_collision_stats(audit_item)
            actor_geometry, actor_issues = _actor_geometry(audit_item)
            integrity.extend(native_issues)
            integrity.extend(actor_issues)
            if (
                audit_item is not None
                and int(audit_item.get("native_collision_callback_count", -1))
                != int(native_stats["native_collision_callback_count"])
            ):
                integrity.append("audit_native_collision_callback_count_mismatch")
            receipt_provenance, receipt_issues = _rollout_receipt(cell_dir, cell_id, init_id, scenario_name)
            integrity.extend(receipt_issues)
            audited_attempt = (audit_item or {}).get("attempt_provenance") or {}
            if not audited_attempt:
                integrity.append("audit_attempt_provenance_missing")
            elif (
                audited_attempt.get("receipt_sha256") != receipt_provenance.get("rollout_receipt_sha256")
                or audited_attempt.get("accepted_attempt") != receipt_provenance.get("accepted_attempt")
                or audited_attempt.get("raw_evidence_sha256") != receipt_provenance.get("raw_evidence_sha256")
                or int(audited_attempt.get("accepted_attempts", -1)) != 1
            ):
                integrity.append("audit_receipt_attempt_provenance_disagreement")
            control_variables = (audit_item or {}).get("control_variables") or {}
            if not control_variables:
                integrity.append("audit_control_variables_missing")
            elif (
                int(control_variables.get("ego_init_id", -1)) != init_id
                or number(control_variables.get("carla_fps")) != carla_fps
            ):
                integrity.append("audit_control_variables_identity_or_fps")
            if scientific_outcomes:
                if boolean(scientific_outcomes.get("completion_success")) != completion:
                    integrity.append("audit_gate_completion_disagreement")
                if boolean(scientific_outcomes.get("fixed_geometry_yield_success")) != yield_outcome:
                    integrity.append("audit_gate_yield_disagreement")
                if boolean(scientific_outcomes.get("footprint_collision")) != footprint_collision:
                    integrity.append("audit_gate_footprint_disagreement")
            else:
                integrity.append("audit_scientific_outcomes_missing")

            margin_map = scientific_outcomes.get("footprint_margin_sensitivity") or {}
            for margin in FOOTPRINT_MARGINS:
                margin_value = next(
                    (
                        value
                        for key, value in margin_map.items()
                        if finite(key) and math.isclose(float(key), margin, abs_tol=1e-12)
                    ),
                    None,
                )
                if margin_value is None:
                    integrity.append(f"footprint_margin_sensitivity_missing:{margin:g}")
                    sensitivity_separation = None
                    sensitivity_collision = None
                    geometry_sources: list[object] = []
                    dimensions: list[object] = []
                    pose_offsets: list[object] = []
                else:
                    sensitivity_separation = number(margin_value.get("min_footprint_separation_m"))
                    sensitivity_collision = boolean(margin_value.get("footprint_collision"))
                    geometry_sources = list(margin_value.get("geometry_sources") or [])
                    dimensions = list(margin_value.get("dimensions_m") or [])
                    pose_offsets = list(margin_value.get("bbox_pose_offsets_rhs") or [])
                    if (
                        sensitivity_separation is None
                        or sensitivity_collision is None
                        or len(geometry_sources) != 2
                        or len(dimensions) != 4
                        or not all(finite(value) for value in dimensions)
                        or len(pose_offsets) != 6
                        or not all(finite(value) for value in pose_offsets)
                    ):
                        integrity.append(f"footprint_margin_sensitivity_invalid:{margin:g}")
                sensitivity_outcomes.append(
                    {
                        "cell_id": cell_id,
                        "predictor": cell["predictor"],
                        "risk_policy": cell["risk_policy"],
                        "target_style": cell["target_style"],
                        "ego_init_id": init_id,
                        "footprint_margin_m_per_actor": margin,
                        "primary_margin": int(math.isclose(margin, 0.25, abs_tol=1e-12)),
                        "ego_route_completion_duration_s": completion_duration,
                        "post_clearance_completion_lag_s": post_clearance_lag,
                        "minimum_footprint_separation_m": sensitivity_separation,
                        "footprint_collision": int(sensitivity_collision) if sensitivity_collision is not None else None,
                        "native_collision_any": native_stats["native_collision_any"],
                        "fixed_geometry_yield_failure": int(not yield_outcome) if yield_outcome is not None else None,
                        "completion_failure": int(not completion) if completion is not None else None,
                        "continuous_outcome_missing_reasons": ";".join(sorted(set(missing))),
                        "rollout_receipt_sha256": receipt_provenance.get("rollout_receipt_sha256"),
                        "geometry_sources_json": json.dumps(geometry_sources),
                        "dimensions_m_json": json.dumps(dimensions),
                        "bbox_pose_offsets_rhs_json": json.dumps(pose_offsets),
                    }
                )
                if math.isclose(margin, 0.25, abs_tol=1e-12):
                    if (
                        separation is None
                        or sensitivity_separation is None
                        or abs(separation - sensitivity_separation) > distance_tolerance
                        or footprint_collision is None
                        or sensitivity_collision != footprint_collision
                    ):
                        integrity.append("primary_footprint_margin_disagrees_with_pair_safety")

            risk_values = [number(row.get("risk_tightening_mean")) for row in rollout_risk]
            finite_risk = [value for value in risk_values if value is not None]
            audit_risk = (audit_item or {}).get("risk_manipulation") or {}
            if not audit_risk:
                integrity.append("audit_risk_manipulation_missing")
            predictor_metrics = {
                "prediction_logged_samples": 0,
                "prediction_full_horizon_samples": 0,
                "prediction_reactive_active_samples": 0,
                **{f"prediction_{metric}": None for metric in PREDICTION_METRICS},
            }
            if scenario_name:
                prediction_path = cell_dir / scenario_name / "prediction_dataset" / "prediction_dataset_labeled.jsonl"
                if prediction_path.is_file():
                    try:
                        calibration = (
                            contract["predictors"].get(str(cell["predictor"]), {}).get("calibration_parameters")
                            or {"temperature": 1.0, "covariance_scale": 1.0}
                        )
                        predictor_metrics = _prediction_rollout(prediction_path, str(cell["predictor"]), calibration)
                    except Exception as exc:  # preserve the affected row and fail analysis integrity
                        integrity.append(f"prediction_metric_error:{type(exc).__name__}")
                else:
                    integrity.append("prediction_labeled_missing")

            outcome = {
                "result_generation": contract["result_generation"],
                "implementation_version": contract["implementation_version"],
                "cell_id": cell_id,
                "predictor": cell["predictor"],
                "risk_policy": cell["risk_policy"],
                "target_style": cell["target_style"],
                "target_offset_m": contract.get("target_offset_m"),
                "ego_init_id": init_id,
                "scenario": scenario_name,
                "completion_valid": int(completion) if completion is not None else None,
                "completion_failure": int(not completion) if completion is not None else None,
                "completion_event_step": completion_step,
                "carla_fps": carla_fps,
                "rollout_start_timestamp_s": rollout_start,
                "rollout_end_timestamp_s": rollout_end,
                "ego_route_completion_duration_s": completion_duration,
                "df_logged_trajectory_duration_s": df_logged_duration,
                "ego_completion_timestamp_s": ego_completion_timestamp,
                "target_fixed_zone_entry_timestamp_s": target_enter,
                "target_fixed_zone_exit_timestamp_s": target_exit,
                "target_fixed_zone_exit_elapsed_s": target_exit_elapsed,
                "ego_fixed_zone_entry_timestamp_s": ego_enter,
                "ego_fixed_zone_exit_timestamp_s": ego_exit,
                "post_clearance_completion_lag_s": post_clearance_lag,
                "fixed_geometry_yield_gap_s": yield_gap,
                "fixed_geometry_yield_outcome_observed": int(yield_outcome) if yield_outcome is not None else None,
                "fixed_geometry_yield_failure": int(not yield_outcome) if yield_outcome is not None else None,
                "minimum_footprint_separation_m": separation,
                "footprint_collision": int(footprint_collision) if footprint_collision is not None else None,
                **native_stats,
                **actor_geometry,
                **receipt_provenance,
                "audit_attempt_classification": audited_attempt.get("attempt_classification"),
                "audit_attempts_started": audited_attempt.get("attempts_started"),
                "audit_accepted_attempts": audited_attempt.get("accepted_attempts"),
                "audit_attempt_provenance_json": json.dumps(audited_attempt, sort_keys=True),
                "solver_failure_fraction": (
                    number((gate_item or {}).get("solver_failure_frac"))
                    if number((gate_item or {}).get("solver_failure_frac")) is not None
                    else weighted_mean(rollout_risk, "solver_failure_frac")
                ),
                "supervisor_active_fraction": weighted_mean(rollout_risk, "supervisor_active_frac"),
                "risk_tightening_mean": weighted_mean(rollout_risk, "risk_tightening_mean"),
                "risk_tightening_min_observed": min(finite_risk) if finite_risk else None,
                "risk_tightening_max_observed": max(finite_risk) if finite_risk else None,
                "adaptive_risk_solver_fraction": weighted_mean(rollout_risk, "solver_uses_adaptive_risk_frac"),
                "audit_runtime_gate_passed": int(bool((audit_item or {}).get("runtime_gate_passed"))),
                "audit_learned_mode_collapse_steps": (audit_item or {}).get("learned_mode_collapse_steps"),
                "audit_learned_mode_collapse_fraction": (audit_item or {}).get("learned_mode_collapse_fraction"),
                "audit_risk_audited_steps": audit_risk.get("audited_steps"),
                "audit_risk_solver_applied_adaptive_steps": audit_risk.get("solver_applied_adaptive_steps"),
                "audit_risk_tightening_min": audit_risk.get("tightening_min"),
                "audit_risk_tightening_max": audit_risk.get("tightening_max"),
                "audit_risk_tightening_unique_1e9": audit_risk.get("unique_1e9"),
                "audit_risk_adaptive_variation_observed": int(bool(audit_risk.get("adaptive_variation_observed"))),
                "audit_risk_manipulation_json": json.dumps(audit_risk, sort_keys=True),
                "audit_scientific_outcomes_json": json.dumps(scientific_outcomes, sort_keys=True),
                "audit_control_variables_json": json.dumps(control_variables, sort_keys=True),
                "scenario_source_sha256": control_variables.get("scenario_source_sha256"),
                "tuning_source_sha256": control_variables.get("tuning_source_sha256"),
                "init_source_sha256": control_variables.get("init_source_sha256"),
                "ego_first_state_txyyawspeed_json": json.dumps(
                    (control_variables.get("first_states_txyyawspeed") or {}).get("ego")
                ),
                "target_first_state_txyyawspeed_json": json.dumps(
                    (control_variables.get("first_states_txyyawspeed") or {}).get("target")
                ),
                **predictor_metrics,
                "continuous_outcome_missing_reasons": ";".join(sorted(set(missing))),
                "binary_outcome_missing_reasons": ";".join(
                    sorted(
                        reason
                        for reason in (
                            "completion_failure:completion_flag_missing" if completion is None else "",
                            "fixed_geometry_yield_failure:entry_or_exit_censored" if yield_outcome is None else "",
                            "footprint_collision:pair_outcome_missing" if footprint_collision is None else "",
                        )
                        if reason
                    )
                ),
                "analysis_integrity_issues": ";".join(sorted(set(integrity))),
            }
            outcomes.append(outcome)
            issues.extend(f"{cell_id}:init{init_id}:{item}" for item in integrity)
    return outcomes, sensitivity_outcomes, sorted(set(issues))


def cell_summaries(outcomes: Sequence[Mapping[str, object]]) -> list[dict]:
    groups: dict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in outcomes:
        groups[(str(row["cell_id"]), str(row["predictor"]), str(row["risk_policy"]), str(row["target_style"]))].append(row)
    rows: list[dict] = []
    continuous = (
        "ego_route_completion_duration_s",
        "target_fixed_zone_exit_elapsed_s",
        "post_clearance_completion_lag_s",
        "fixed_geometry_yield_gap_s",
        "minimum_footprint_separation_m",
        "solver_failure_fraction",
        "supervisor_active_fraction",
        "risk_tightening_mean",
        "adaptive_risk_solver_fraction",
    )
    for (cell_id, predictor, policy, style), subset in sorted(groups.items()):
        record: dict[str, object] = {
            "cell_id": cell_id,
            "predictor": predictor,
            "risk_policy": policy,
            "target_style": style,
            "rollouts": len(subset),
            "init_ids": ";".join(str(row["ego_init_id"]) for row in sorted(subset, key=lambda item: int(item["ego_init_id"]))),
        }
        for metric in continuous:
            values = [float(row[metric]) for row in subset if finite(row.get(metric))]
            record[f"{metric}_n"] = len(values)
            record[f"{metric}_mean"] = mean(values)
            record[f"{metric}_median"] = median(values)
        for metric in FAILURE_METRICS:
            values = [int(row[metric]) for row in subset if row.get(metric) in (0, 1)]
            record[f"{metric}_observed_n"] = len(values)
            record[f"{metric}_rollouts"] = sum(values)
        rows.append(record)
    return rows


def collision_category_summaries(outcomes: Sequence[Mapping[str, object]]) -> list[dict]:
    groups: dict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in outcomes:
        groups[(str(row["cell_id"]), str(row["predictor"]), str(row["risk_policy"]), str(row["target_style"]))].append(row)
    output: list[dict] = []
    for (cell_id, predictor, policy, style), subset in sorted(groups.items()):
        for category in COLLISION_CATEGORIES:
            callbacks = [int(row[f"native_collision_{category}_callback_count"]) for row in subset]
            episodes = [int(row[f"native_collision_{category}_episode_count"]) for row in subset]
            output.append(
                {
                    "cell_id": cell_id,
                    "predictor": predictor,
                    "risk_policy": policy,
                    "target_style": style,
                    "collision_category": category,
                    "independent_rollouts": len(subset),
                    "callback_events": sum(callbacks),
                    "canonical_contact_episodes": sum(episodes),
                    "rollouts_with_category": sum(value > 0 for value in episodes),
                    "callbacks_and_episodes_are_not_independent_units": 1,
                }
            )
    return output


def scientific_analysis(
    outcomes: Sequence[Mapping[str, object]],
    contract: Mapping[str, object],
    analysis_contract: Mapping[str, object],
) -> dict:
    init_ids = tuple(map(int, contract["ego_init_ids"]))
    index = {
        (str(row["predictor"]), str(row["risk_policy"]), str(row["target_style"]), int(row["ego_init_id"])): row
        for row in outcomes
    }
    bootstrap = analysis_contract["inference"]["bootstrap"]
    tolerances = analysis_contract["numerical_tolerances"]
    time_tol = float(tolerances["time_dominance_tolerance_s"])
    distance_tol = float(tolerances["distance_dominance_tolerance_m"])

    h3_effects: list[dict] = []
    h3_contrasts: list[dict] = []
    h3_binary: list[dict] = []
    for policy in (*FIXED_POLICIES, "adaptive"):
        for style in STYLES:
            base_id = f"H3_B1_minus_B0_{policy}_{style}"
            for metric in PRIMARY_METRICS:
                effects, summary = paired_continuous_contrast(
                    index,
                    hypothesis="H3",
                    contrast_id=base_id,
                    treatment_predictor="B1",
                    control_predictor="B0",
                    treatment_policy=policy,
                    control_policy=policy,
                    target_style=style,
                    metric=metric,
                    init_ids=init_ids,
                    bootstrap=bootstrap,
                )
                h3_effects.extend(effects)
                h3_contrasts.append(summary)
            for metric in FAILURE_METRICS:
                h3_binary.append(
                    paired_binary_summary(
                        index,
                        hypothesis="H3",
                        contrast_id=base_id,
                        treatment_predictor="B1",
                        control_predictor="B0",
                        treatment_policy=policy,
                        control_policy=policy,
                        target_style=style,
                        metric=metric,
                        init_ids=init_ids,
                    )
                )
    holm_adjust(h3_contrasts, ("metric",), declared_size=8)
    h3_by_id: dict[str, list[dict]] = defaultdict(list)
    h3_binary_by_id: dict[str, list[dict]] = defaultdict(list)
    for row in h3_contrasts:
        h3_by_id[str(row["contrast_id"])].append(row)
    for row in h3_binary:
        h3_binary_by_id[str(row["contrast_id"])].append(row)
    h3_cells: list[dict] = []
    for contrast_id in sorted(h3_by_id):
        metrics = {str(row["metric"]): row for row in h3_by_id[contrast_id]}
        duration = metrics["ego_route_completion_duration_s"]
        separation = metrics["minimum_footprint_separation_m"]
        binary = h3_binary_by_id[contrast_id]
        complete = (
            duration["complete_clusters"] == len(init_ids)
            and separation["complete_clusters"] == len(init_ids)
            and all(row["complete_clusters"] == len(init_ids) for row in binary)
        )
        duration_ok = complete and float(duration["mean_effect"]) <= time_tol
        separation_ok = complete and float(separation["mean_effect"]) >= -distance_tol
        binary_ok = complete and all(row["no_excess_observed_failure"] for row in binary)
        status = "supported_directionally" if duration_ok and separation_ok and binary_ok else (
            "not_supported" if complete else "not_supported_due_prespecified_censoring_or_missingness"
        )
        h3_cells.append(
            {
                "contrast_id": contrast_id,
                "target_style": duration["target_style"],
                "risk_policy": duration["treatment_policy"],
                "all_five_primary_pairs_complete": int(
                    duration["complete_clusters"] == len(init_ids)
                    and separation["complete_clusters"] == len(init_ids)
                ),
                "all_binary_guards_observed": int(all(row["complete_clusters"] == len(init_ids) for row in binary)),
                "completion_direction_met": int(bool(duration_ok)),
                "separation_direction_met": int(bool(separation_ok)),
                "no_excess_binary_failures": int(bool(binary_ok)),
                "cell_support_status": status,
            }
        )
    if all(row["cell_support_status"] == "supported_directionally" for row in h3_cells):
        h3_status = "supported_directionally_at_nominal_timing"
    else:
        h3_status = "not_supported_as_universal_claim"

    h4_effects: list[dict] = []
    h4_contrasts: list[dict] = []
    h4_binary: list[dict] = []
    for predictor in PREDICTORS:
        for style in STYLES:
            for fixed in FIXED_POLICIES:
                base_id = f"H4_{predictor}_{style}_adaptive_minus_{fixed}"
                for metric in PRIMARY_METRICS:
                    effects, summary = paired_continuous_contrast(
                        index,
                        hypothesis="H4",
                        contrast_id=base_id,
                        treatment_predictor=predictor,
                        control_predictor=predictor,
                        treatment_policy="adaptive",
                        control_policy=fixed,
                        target_style=style,
                        metric=metric,
                        init_ids=init_ids,
                        bootstrap=bootstrap,
                    )
                    h4_effects.extend(effects)
                    h4_contrasts.append(summary)
                for metric in FAILURE_METRICS:
                    h4_binary.append(
                        paired_binary_summary(
                            index,
                            hypothesis="H4",
                            contrast_id=base_id,
                            treatment_predictor=predictor,
                            control_predictor=predictor,
                            treatment_policy="adaptive",
                            control_policy=fixed,
                            target_style=style,
                            metric=metric,
                            init_ids=init_ids,
                        )
                    )
    holm_adjust(h4_contrasts, ("treatment_predictor", "target_style", "metric"), declared_size=3)
    h4_by_id: dict[str, list[dict]] = defaultdict(list)
    h4_binary_by_id: dict[str, list[dict]] = defaultdict(list)
    for row in h4_contrasts:
        h4_by_id[str(row["contrast_id"])].append(row)
    for row in h4_binary:
        h4_binary_by_id[str(row["contrast_id"])].append(row)
    dominance: list[dict] = []
    for contrast_id in sorted(h4_by_id):
        metrics = {str(row["metric"]): row for row in h4_by_id[contrast_id]}
        duration = metrics["ego_route_completion_duration_s"]
        separation = metrics["minimum_footprint_separation_m"]
        binary = h4_binary_by_id[contrast_id]
        complete = (
            duration["complete_clusters"] == len(init_ids)
            and separation["complete_clusters"] == len(init_ids)
            and all(row["complete_clusters"] == len(init_ids) for row in binary)
        )
        duration_effect = number(duration["mean_effect"])
        separation_effect = number(separation["mean_effect"])
        duration_no_worse = complete and duration_effect is not None and duration_effect <= time_tol
        separation_no_worse = complete and separation_effect is not None and separation_effect >= -distance_tol
        strict_better = complete and (
            (duration_effect is not None and duration_effect < -time_tol)
            or (separation_effect is not None and separation_effect > distance_tol)
        )
        no_excess = complete and all(row["no_excess_observed_failure"] for row in binary)
        dominates = duration_no_worse and separation_no_worse and strict_better and no_excess
        dominance.append(
            {
                "contrast_id": contrast_id,
                "predictor": duration["treatment_predictor"],
                "target_style": duration["target_style"],
                "fixed_comparator": duration["control_policy"],
                "all_five_primary_pairs_complete": int(
                    duration["complete_clusters"] == len(init_ids)
                    and separation["complete_clusters"] == len(init_ids)
                ),
                "all_binary_guards_observed": int(all(row["complete_clusters"] == len(init_ids) for row in binary)),
                "mean_adaptive_minus_fixed_completion_s": duration_effect,
                "mean_adaptive_minus_fixed_separation_m": separation_effect,
                "completion_no_worse_within_tolerance": int(bool(duration_no_worse)),
                "separation_no_worse_within_tolerance": int(bool(separation_no_worse)),
                "at_least_one_strictly_better": int(bool(strict_better)),
                "no_excess_binary_failures": int(bool(no_excess)),
                "dominance_status": "dominates" if dominates else (
                    "does_not_dominate" if complete else "does_not_dominate_due_prespecified_censoring_or_missingness"
                ),
            }
        )
    if all(row["dominance_status"] == "dominates" for row in dominance):
        h4_status = "supported_as_universal_dominance"
    else:
        h4_status = "not_supported_as_universal_dominance"

    return {
        "h3_effects": h3_effects,
        "h3_contrasts": h3_contrasts,
        "h3_binary": h3_binary,
        "h3_cells": h3_cells,
        "h3_status": h3_status,
        "h4_effects": h4_effects,
        "h4_contrasts": h4_contrasts,
        "h4_binary": h4_binary,
        "h4_dominance": dominance,
        "h4_status": h4_status,
    }


def predictor_manipulation(outcomes: Sequence[Mapping[str, object]], init_ids: Sequence[int]) -> list[dict]:
    index = {
        (str(row["predictor"]), str(row["risk_policy"]), str(row["target_style"]), int(row["ego_init_id"])): row
        for row in outcomes
    }
    rows: list[dict] = []
    for policy in (*FIXED_POLICIES, "adaptive"):
        for style in STYLES:
            for metric in PREDICTION_METRICS:
                field = f"prediction_{metric}"
                effects: list[float] = []
                missing: list[int] = []
                for init_id in init_ids:
                    b1 = index[("B1", policy, style, init_id)].get(field)
                    b0 = index[("B0", policy, style, init_id)].get(field)
                    if finite(b1) and finite(b0):
                        effects.append(float(b1) - float(b0))
                    else:
                        missing.append(init_id)
                rows.append(
                    {
                        "risk_policy": policy,
                        "target_style": style,
                        "metric": metric,
                        "effect_orientation": "B1_minus_B0",
                        "complete_init_pairs": len(effects),
                        "missing_init_ids": ";".join(map(str, missing)),
                        "mean_B1_minus_B0": mean(effects),
                        "median_B1_minus_B0": median(effects),
                        "B1_better_init_fraction": mean(int(effect < 0) for effect in effects),
                        "exact_sign_flip_p_descriptive": exact_sign_flip_p(effects),
                        "interpretation": "descriptive_in_loop_manipulation_check_not_independent_closed_loop_benchmark",
                    }
                )
    return rows


def risk_manipulation(outcomes: Sequence[Mapping[str, object]], tolerance: float = 1e-6) -> list[dict]:
    groups: dict[tuple[str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in outcomes:
        groups[(str(row["predictor"]), str(row["risk_policy"]), str(row["target_style"]))].append(row)
    output: list[dict] = []
    for (predictor, policy, style), subset in sorted(groups.items()):
        adaptive_fraction = mean(row["adaptive_risk_solver_fraction"] for row in subset if finite(row.get("adaptive_risk_solver_fraction")))
        risks = [float(row["risk_tightening_mean"]) for row in subset if finite(row.get("risk_tightening_mean"))]
        observed_range = max(risks) - min(risks) if risks else None
        audited_steps = sum(int(row.get("audit_risk_audited_steps") or 0) for row in subset)
        adaptive_steps = sum(int(row.get("audit_risk_solver_applied_adaptive_steps") or 0) for row in subset)
        within_rollout_variation = sum(int(row.get("audit_risk_adaptive_variation_observed") or 0) for row in subset)
        if policy == "adaptive":
            solver_identity_ok = adaptive_steps > 0 and adaptive_fraction is not None and adaptive_fraction > tolerance
            variation_observed = within_rollout_variation == len(subset)
            status = "observed" if solver_identity_ok and variation_observed else "weak_or_not_observed"
        else:
            solver_identity_ok = adaptive_steps == 0 and adaptive_fraction is not None and abs(adaptive_fraction) <= tolerance
            variation_observed = within_rollout_variation > 0
            status = "observed" if solver_identity_ok else "wrong_solver_identity"
        output.append(
            {
                "predictor": predictor,
                "risk_policy": policy,
                "target_style": style,
                "rollouts": len(subset),
                "risk_tightening_mean": mean(risks),
                "risk_tightening_across_init_range": observed_range,
                "adaptive_risk_solver_fraction": adaptive_fraction,
                "audited_solver_steps": audited_steps,
                "solver_applied_adaptive_steps": adaptive_steps,
                "rollouts_with_within_rollout_adaptive_variation": within_rollout_variation,
                "expected_adaptive_solver": int(policy == "adaptive"),
                "solver_identity_matches_arm": int(bool(solver_identity_ok)),
                "risk_variation_observed": int(bool(variation_observed)),
                "manipulation_status": status,
                "scientific_not_analysis_gate": 1,
            }
        )
    return output


def footprint_h4_dominance_sensitivity(
    outcomes: Sequence[Mapping[str, object]],
    sensitivity_outcomes: Sequence[Mapping[str, object]],
    contract: Mapping[str, object],
    analysis_contract: Mapping[str, object],
) -> list[dict]:
    base = {
        (str(row["predictor"]), str(row["risk_policy"]), str(row["target_style"]), int(row["ego_init_id"])): row
        for row in outcomes
    }
    sensitivity = {
        (
            str(row["predictor"]),
            str(row["risk_policy"]),
            str(row["target_style"]),
            int(row["ego_init_id"]),
            float(row["footprint_margin_m_per_actor"]),
        ): row
        for row in sensitivity_outcomes
    }
    output: list[dict] = []
    for margin in FOOTPRINT_MARGINS:
        rows: list[dict] = []
        for key, source in base.items():
            selected = sensitivity.get((*key, margin), {})
            row = dict(source)
            row["minimum_footprint_separation_m"] = selected.get("minimum_footprint_separation_m")
            row["footprint_collision"] = selected.get("footprint_collision")
            rows.append(row)
        science = scientific_analysis(rows, contract, analysis_contract)
        for decision in science["h4_dominance"]:
            output.append(
                {
                    "footprint_margin_m_per_actor": margin,
                    "primary_margin": int(math.isclose(margin, 0.25, abs_tol=1e-12)),
                    **decision,
                }
            )
    return output


def _write_table(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty formal table: {path.name}")
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    write_csv(path, rows, fields)


def validate_contracts(contract: Mapping[str, object], analysis: Mapping[str, object], analysis_path: Path) -> list[str]:
    issues: list[str] = []
    if contract.get("status") != "frozen":
        issues.append("run_contract_not_frozen")
    if contract.get("implementation_version") != IMPLEMENTATION_VERSION:
        issues.append("run_contract_wrong_implementation")
    if contract.get("result_generation") != analysis.get("result_generation"):
        issues.append("result_generation_mismatch")
    if int(contract.get("expected_rollouts", -1)) != int(analysis.get("expected_rollouts", -2)):
        issues.append("expected_rollout_mismatch")
    if analysis.get("status") != "frozen_amendment_before_r3_outcomes":
        issues.append("analysis_contract_not_frozen_amendment")
    if tuple(analysis.get("primary_outcomes", {}).keys()) != PRIMARY_METRICS:
        issues.append("analysis_contract_primary_estimand_drift")
    original = analysis.get("amends_without_overwriting") or {}
    original_path = analysis_path.parent / str(original.get("path") or "")
    if not original_path.is_file() or sha256_file(original_path) != original.get("sha256"):
        issues.append("original_m0_hash_mismatch")
    amendment_marker_path = analysis_path.parent / "M0_AMENDMENT_COMPLETE.json"
    if not amendment_marker_path.is_file():
        issues.append("m0_amendment_completion_marker_missing")
    else:
        marker = read_json(amendment_marker_path)
        amended = marker.get("amended_m0_v2") or {}
        readable = marker.get("human_readable_amendment") or {}
        readable_path = analysis_path.parent / str(readable.get("path") or "")
        if (
            marker.get("status") != "pass"
            or amended.get("path") != analysis_path.name
            or amended.get("sha256") != sha256_file(analysis_path)
            or not readable_path.is_file()
            or readable.get("sha256") != sha256_file(readable_path)
        ):
            issues.append("m0_amendment_completion_marker_mismatch")
    expected_keys = {
        (str(cell["predictor"]), str(cell["risk_policy"]), str(cell["target_style"]), int(init_id))
        for cell in contract.get("cells", [])
        for init_id in contract.get("ego_init_ids", [])
    }
    if len(expected_keys) != int(contract.get("expected_rollouts", -1)):
        issues.append("run_contract_treatment_key_coverage")
    if float(contract.get("target_offset_m", math.nan)) != 0.0:
        issues.append("h3_not_nominal_target_timing")
    return issues


def analyze(
    results_dir: Path,
    contract_path: Path,
    analysis_contract_path: Path,
    output_dir: Path,
    audit_path: Path | None = None,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = read_json(contract_path)
    analysis_contract = read_json(analysis_contract_path)
    audit_path = audit_path or results_dir / "r3_corrected_matrix_audit.json"
    audit = read_json(audit_path) if audit_path.is_file() else {}
    integrity_issues = validate_contracts(contract, analysis_contract, analysis_contract_path)
    if not audit_path.is_file():
        integrity_issues.append("matrix_audit_missing")
    else:
        if audit.get("status") != "pass":
            integrity_issues.append("matrix_audit_status_not_pass")
        if int(audit.get("observed_rollouts", -1)) != int(contract.get("expected_rollouts", -2)):
            integrity_issues.append("matrix_audit_rollout_count")
        if int(audit.get("passing_integrity_rollouts", -1)) != int(contract.get("expected_rollouts", -2)):
            integrity_issues.append("matrix_audit_passing_integrity_rollout_count")

    outcomes, sensitivity_outcomes, load_issues = load_rollout_outcomes(
        results_dir, contract, audit, analysis_contract
    )
    integrity_issues.extend(load_issues)
    observed_keys = {
        (str(row["predictor"]), str(row["risk_policy"]), str(row["target_style"]), int(row["ego_init_id"]))
        for row in outcomes
    }
    if len(outcomes) != int(contract["expected_rollouts"]) or len(observed_keys) != len(outcomes):
        integrity_issues.append("outcome_table_not_exactly_80_unique_rows")

    science = scientific_analysis(outcomes, contract, analysis_contract)
    cells = cell_summaries(outcomes)
    collision_categories = collision_category_summaries(outcomes)
    prediction_checks = predictor_manipulation(outcomes, tuple(map(int, contract["ego_init_ids"])))
    risk_checks = risk_manipulation(outcomes)
    h4_margin_sensitivity = footprint_h4_dominance_sensitivity(
        outcomes, sensitivity_outcomes, contract, analysis_contract
    )
    tables = {
        "r3_rollout_outcomes.csv": outcomes,
        "r3_footprint_margin_outcomes.csv": sensitivity_outcomes,
        "r3_cell_outcome_summary.csv": cells,
        "r3_collision_category_summary.csv": collision_categories,
        "r3_h3_init_effects.csv": science["h3_effects"],
        "r3_h3_contrasts.csv": science["h3_contrasts"],
        "r3_h3_cell_support.csv": science["h3_cells"],
        "r3_h4_init_effects.csv": science["h4_effects"],
        "r3_h4_contrasts.csv": science["h4_contrasts"],
        "r3_h4_dominance.csv": science["h4_dominance"],
        "r3_h4_footprint_margin_dominance_sensitivity.csv": h4_margin_sensitivity,
        "r3_binary_failure_contrasts.csv": science["h3_binary"] + science["h4_binary"],
        "r3_predictor_manipulation_checks.csv": prediction_checks,
        "r3_risk_manipulation_checks.csv": risk_checks,
    }
    expected_counts = {
        "r3_rollout_outcomes.csv": 80,
        "r3_footprint_margin_outcomes.csv": 320,
        "r3_cell_outcome_summary.csv": 16,
        "r3_collision_category_summary.csv": 96,
        "r3_h3_init_effects.csv": 80,
        "r3_h3_contrasts.csv": 16,
        "r3_h3_cell_support.csv": 8,
        "r3_h4_init_effects.csv": 120,
        "r3_h4_contrasts.csv": 24,
        "r3_h4_dominance.csv": 12,
        "r3_h4_footprint_margin_dominance_sensitivity.csv": 48,
        "r3_binary_failure_contrasts.csv": 80,
        "r3_predictor_manipulation_checks.csv": 40,
        "r3_risk_manipulation_checks.csv": 16,
    }
    for name, rows in tables.items():
        if len(rows) != expected_counts[name]:
            integrity_issues.append(f"formal_table_count:{name}:{len(rows)}!={expected_counts[name]}")
        _write_table(output_dir / name, rows)

    primary_contrasts_finite = all(
        row["complete_clusters"] == 5 for row in science["h3_contrasts"] + science["h4_contrasts"]
    )
    binary_contrasts_observed = all(
        row["complete_clusters"] == 5 for row in science["h3_binary"] + science["h4_binary"]
    )
    outcomes_classified = all(
        all(
            finite(row.get(metric))
            or f"{metric}:" in str(row.get("continuous_outcome_missing_reasons") or "")
            for metric in PRIMARY_METRICS
        )
        and all(
            row.get(metric) in (0, 1)
            or f"{metric}:" in str(row.get("binary_outcome_missing_reasons") or "")
            for metric in FAILURE_METRICS
        )
        for row in outcomes
    )
    integrity_issues = sorted(set(integrity_issues))
    table_hashes = {name: sha256_file(output_dir / name) for name in tables}
    analysis_integrity_pass = not integrity_issues
    tables_complete = all(
        len(tables[name]) == expected_counts[name] and (output_dir / name).is_file()
        for name in expected_counts
    )
    stop_gate_passed = analysis_integrity_pass and outcomes_classified and tables_complete
    summary = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass" if analysis_integrity_pass else "fail",
        "status_semantics": "analysis_integrity_only_scientific_negative_results_do_not_fail",
        "result_generation": contract["result_generation"],
        "implementation_version": contract["implementation_version"],
        "observed_rollouts": len(outcomes),
        "unique_treatment_keys": len(observed_keys),
        "independent_init_clusters": len(contract["ego_init_ids"]),
        "h3": {
            "scope": "nominal_target_timing_only",
            "scientific_support_status": science["h3_status"],
            "claim_language": "directional_consistency_not_confirmatory_significance",
        },
        "h4": {"scientific_support_status": science["h4_status"]},
        "all_outcomes_observed_or_prespecified_undefined": outcomes_classified,
        "all_primary_contrasts_have_five_finite_pairs": primary_contrasts_finite,
        "all_binary_contrasts_have_five_observed_pairs": binary_contrasts_observed,
        "integrity_issues": integrity_issues,
        "scientific_adverse_outcomes_are_not_analysis_errors": True,
        "manipulation_checks_are_not_analysis_or_stop_gates": True,
        "contract_sha256": sha256_file(contract_path),
        "analysis_contract_sha256": sha256_file(analysis_contract_path),
        "original_m0_sha256": analysis_contract["amends_without_overwriting"]["sha256"],
        "analysis_contract_marker_sha256": sha256_file(
            analysis_contract_path.parent / "M0_AMENDMENT_COMPLETE.json"
        ),
        "matrix_audit_sha256": sha256_file(audit_path) if audit_path.is_file() else None,
        "formal_table_sha256": table_hashes,
        "formal_table_row_counts": {name: len(rows) for name, rows in tables.items()},
    }
    atomic_write_json(output_dir / "r3_analysis_summary.json", summary)
    summary_hash = sha256_file(output_dir / "r3_analysis_summary.json")
    stop_gate = {
        "schema_version": "r3_study_stop_gate_v1",
        "status": "pass" if stop_gate_passed else "fail",
        "study_stop_gate_passed": stop_gate_passed,
        "additional_large_scale_carla_required": not stop_gate_passed,
        "decision": "stop_formal_large_scale_collection" if stop_gate_passed else "formal_collection_not_yet_stoppable",
        "basis": {
            "analysis_integrity_pass": analysis_integrity_pass,
            "observed_rollouts_80_of_80": len(outcomes) == 80 and len(observed_keys) == 80,
            "all_outcomes_observed_or_prespecified_undefined": outcomes_classified,
            "all_formal_tables_exist_with_expected_rows": tables_complete,
        },
        "scientific_results_do_not_change_stop_decision": {
            "negative_null_or_mixed_H3_H4": True,
            "zero_observed_collisions": True,
            "zero_reactive_activity": True,
            "failed_predictor_or_risk_manipulation": True,
            "prespecified_scientific_censoring": True,
        },
        "analysis_summary_sha256": summary_hash,
        "analysis_contract_sha256": sha256_file(analysis_contract_path),
        "analysis_contract_marker_sha256": sha256_file(
            analysis_contract_path.parent / "M0_AMENDMENT_COMPLETE.json"
        ),
        "formal_table_row_counts": {name: len(rows) for name, rows in tables.items()},
        "formal_table_sha256": table_hashes,
    }
    atomic_write_json(output_dir / "R3_STUDY_STOP_GATE.json", stop_gate)
    receipt = {
        "schema_version": "r3_analysis_complete_v2",
        "status": summary["status"],
        "status_semantics": summary["status_semantics"],
        "observed_rollouts": len(outcomes),
        "unique_treatment_keys": len(observed_keys),
        "h3_scientific_support_status": science["h3_status"],
        "h4_scientific_support_status": science["h4_status"],
        "study_stop_gate_passed": stop_gate_passed,
        "additional_large_scale_carla_required": not stop_gate_passed,
        "analysis_summary": "r3_analysis_summary.json",
        "analysis_summary_sha256": summary_hash,
        "study_stop_gate": "R3_STUDY_STOP_GATE.json",
        "study_stop_gate_sha256": sha256_file(output_dir / "R3_STUDY_STOP_GATE.json"),
        "formal_table_sha256": table_hashes,
        "formal_table_row_counts": {name: len(rows) for name, rows in tables.items()},
        "integrity_issues": integrity_issues,
    }
    atomic_write_json(output_dir / "R3_ANALYSIS_COMPLETE.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--contract-json", type=Path, required=True)
    parser.add_argument("--analysis-contract", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-json", type=Path, default=None)
    args = parser.parse_args()
    receipt = analyze(
        args.results_dir.resolve(),
        args.contract_json.resolve(),
        args.analysis_contract.resolve(),
        args.output_dir.resolve(),
        args.audit_json.resolve() if args.audit_json else None,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
