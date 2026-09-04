#!/usr/bin/env python3
"""Frozen B1/P* by risk closed-loop design, preflight, audit, and inference."""

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
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from capacity_study_v3_analysis import (
    cluster_bootstrap_interval,
    paired_sign_flip_p,
)
from capacity_study_v3_freeze import validate_selection_freeze
from capacity_study_v3_protocol import (
    CLOSED_LOOP_GROUPS,
    build_group_registry,
    sha256_file,
    sha256_payload,
    validate_group_registry,
    write_immutable_manifest,
)


RISK_POLICIES = ("fixed_medium", "adaptive")
TARGET_STYLES = ("assertive_constant_speed", "defensive_reactive")
PREDICTORS = ("B1", "P_star")
EXPECTED_ROLLOUTS = (
    len(PREDICTORS) * len(RISK_POLICIES) * len(TARGET_STYLES) * len(CLOSED_LOOP_GROUPS)
)


def build_closed_loop_manifest(
    freeze: Mapping[str, Any],
    registry: Mapping[str, Any],
    *,
    nuisance_settings: Mapping[str, Any],
) -> dict[str, Any]:
    validate_selection_freeze(freeze)
    validate_group_registry(registry)
    required_nuisance = {
        "town",
        "scenario",
        "tuning_sha256",
        "anchors_sha256",
        "supervisor_authority",
        "target_speed_mps",
        "target_offset_m",
    }
    if set(nuisance_settings) != required_nuisance:
        raise ValueError(
            f"Closed-loop nuisance settings must be exact: {sorted(required_nuisance)}"
        )
    if nuisance_settings["supervisor_authority"] != "enabled":
        raise ValueError("Formal closed-loop study requires supervisor-on authority")
    records = []
    for predictor in PREDICTORS:
        predictor_freeze = freeze[predictor]
        for risk in RISK_POLICIES:
            for style in TARGET_STYLES:
                for group_id in CLOSED_LOOP_GROUPS:
                    records.append(
                        {
                            "rollout_id": (
                                f"v3_online__{predictor.lower()}__{risk}__"
                                f"{style}__init{group_id:02d}"
                            ),
                            "predictor": predictor,
                            "model_cell_id": predictor_freeze["model_cell_id"],
                            "representative_run_id": predictor_freeze[
                                "representative_run_id"
                            ],
                            "risk_policy": risk,
                            "target_style": style,
                            "ego_init_id": group_id,
                            "status": "planned",
                        }
                    )
    payload = {
        "schema_version": "capacity_history_predictor_risk_manifest_v3",
        "status": "frozen",
        "formal_evidence": True,
        "selection_uses_fresh_or_closed_loop_outcomes": False,
        "selection_freeze_sha256": freeze["freeze_sha256"],
        "group_registry_sha256": registry["registry_sha256"],
        "predictors": list(PREDICTORS),
        "risk_policies": list(RISK_POLICIES),
        "target_styles": list(TARGET_STYLES),
        "ego_init_ids": list(CLOSED_LOOP_GROUPS),
        "nuisance_settings": dict(nuisance_settings),
        "expected_rollouts": EXPECTED_ROLLOUTS,
        "rollouts": records,
    }
    payload["manifest_sha256"] = sha256_payload(payload)
    return payload


def validate_closed_loop_manifest(
    manifest: Mapping[str, Any], freeze: Mapping[str, Any]
) -> dict[str, Any]:
    validate_selection_freeze(freeze)
    value = dict(manifest)
    recorded = value.pop("manifest_sha256", None)
    value.pop("payload_sha256", None)
    if recorded != sha256_payload(value):
        raise ValueError("Closed-loop manifest hash mismatch")
    if manifest.get("selection_freeze_sha256") != freeze["freeze_sha256"]:
        raise ValueError("Closed-loop manifest/selection freeze mismatch")
    if manifest.get("selection_uses_fresh_or_closed_loop_outcomes") is not False:
        raise ValueError("P* selection is contaminated by outcome data")
    expected = {
        (predictor, risk, style, group)
        for predictor in PREDICTORS
        for risk in RISK_POLICIES
        for style in TARGET_STYLES
        for group in CLOSED_LOOP_GROUPS
    }
    observed = {
        (
            row["predictor"],
            row["risk_policy"],
            row["target_style"],
            int(row["ego_init_id"]),
        )
        for row in manifest["rollouts"]
    }
    if observed != expected or len(manifest["rollouts"]) != EXPECTED_ROLLOUTS:
        raise ValueError(
            f"Closed-loop matrix is not the exact {EXPECTED_ROLLOUTS}-cell design"
        )
    if set(CLOSED_LOOP_GROUPS).intersection(range(1, 81)):
        raise ValueError("Closed-loop groups overlap offline groups")
    if manifest["nuisance_settings"].get("supervisor_authority") != "enabled":
        raise ValueError("Supervisor authority drift")
    return {
        "status": "pass",
        "rollouts": EXPECTED_ROLLOUTS,
        "independent_groups": len(CLOSED_LOOP_GROUPS),
    }


def validate_dual_predictor_preflight(
    manifest: Mapping[str, Any],
    freeze: Mapping[str, Any],
    predictor_records: Mapping[str, Mapping[str, Any]],
    solver_record: Mapping[str, Any],
) -> dict[str, Any]:
    validate_closed_loop_manifest(manifest, freeze)
    if set(predictor_records) != set(PREDICTORS):
        raise ValueError("Preflight requires exactly B1 and P_star")
    checks = {}
    for predictor in PREDICTORS:
        record = predictor_records[predictor]
        expected_run = freeze[predictor]["representative_run_id"]
        required_true = (
            "output_shape_valid",
            "probabilities_valid",
            "covariances_valid",
            "joint_mode_mapping_valid",
            "solver_smoke_valid",
        )
        failures = [name for name in required_true if record.get(name) is not True]
        if record.get("representative_run_id") != expected_run:
            failures.append("representative_run_id")
        if record.get("calibration_fit_split") not in {"val", "validation"}:
            failures.append("calibration_fit_split")
        if record.get("model_identity") != record.get("calibration_model_identity"):
            failures.append("calibration_model_identity")
        parity = float(record.get("offline_online_max_abs_diff", math.inf))
        if not math.isfinite(parity) or parity > 1.0e-5:
            failures.append("offline_online_numerical_parity")
        latency = float(record.get("warmed_batch_one_latency_ms", math.inf))
        limit = float(record.get("latency_limit_ms", 50.0))
        if not math.isfinite(latency) or latency > limit:
            failures.append("latency")
        if failures:
            raise ValueError(f"Deployment preflight failed for {predictor}: {failures}")
        checks[predictor] = {
            "representative_run_id": expected_run,
            "model_identity": record["model_identity"],
            "calibration_identity": record["calibration_identity"],
            "warmed_batch_one_latency_ms": latency,
            "offline_online_max_abs_diff": parity,
        }
    if solver_record.get("status") != "pass" or solver_record.get("gurobi") is not True:
        raise ValueError("Formal solver preflight failed")
    payload = {
        "schema_version": "capacity_history_dual_predictor_preflight_v3",
        "status": "pass",
        "closed_loop_manifest_sha256": manifest["manifest_sha256"],
        "predictors": checks,
        "solver": dict(solver_record),
    }
    payload["preflight_sha256"] = sha256_payload(payload)
    return payload


def audit_closed_loop_outputs(
    manifest: Mapping[str, Any],
    freeze: Mapping[str, Any],
    results_dir: str | Path,
) -> dict[str, Any]:
    validate_closed_loop_manifest(manifest, freeze)
    observed = []
    for path in sorted(Path(results_dir).rglob("ROLLOUT_COMPLETE.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        observed.append(
            {
                "rollout_id": payload.get("rollout_id"),
                "status": payload.get("status"),
                "manifest_sha256": payload.get("manifest_sha256"),
                "path": str(path),
                "sha256": sha256_file(path),
            }
        )
    expected = {row["rollout_id"] for row in manifest["rollouts"]}
    counts = Counter(row["rollout_id"] for row in observed)
    duplicate = sorted(key for key, count in counts.items() if count != 1)
    missing = sorted(expected - set(counts))
    extra = sorted(set(counts) - expected)
    invalid = sorted(
        row["rollout_id"]
        for row in observed
        if row["status"] != "pass"
        or row["manifest_sha256"] != manifest["manifest_sha256"]
    )
    passed = not duplicate and not missing and not extra and not invalid
    return {
        "schema_version": "capacity_history_closed_loop_audit_v3",
        "status": "pass" if passed else "incomplete",
        "expected_rollouts": EXPECTED_ROLLOUTS,
        "observed_rollouts": len(observed),
        "duplicate_rollout_ids": duplicate,
        "missing_rollout_ids": missing,
        "extra_rollout_ids": extra,
        "invalid_rollout_ids": invalid,
        "observed": observed,
    }


def _representative_seed_record(freeze: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    if "runs" in freeze:
        matches = [dict(seed) for seed in freeze["runs"] if seed["run_id"] == run_id]
    else:
        matches = [
            dict(seed)
            for cell in freeze["cells"]
            for seed in cell["retained_seeds"]
            if seed["run_id"] == run_id
        ]
    if len(matches) != 1:
        raise ValueError(f"Frozen representative is not unique: {run_id}")
    return matches[0]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def materialize_carla_rollout_completions(
    manifest: Mapping[str, Any],
    freeze: Mapping[str, Any],
    results_dir: str | Path,
) -> dict[str, Any]:
    """Audit raw CARLA artifacts before creating per-rollout completion gates."""

    validate_closed_loop_manifest(manifest, freeze)
    root = Path(results_dir)
    completed = []
    failures = {}
    for planned in manifest["rollouts"]:
        cell_id = "__".join(
            (
                planned["predictor"],
                planned["risk_policy"],
                planned["target_style"],
            )
        )
        cell_dir = root / cell_id
        candidates = sorted(cell_dir.glob(f"*ego_init_{int(planned['ego_init_id']):02d}*"))
        problems = []
        if len(candidates) != 1:
            failures[planned["rollout_id"]] = ["scenario_directory_count"]
            continue
        scenario = candidates[0]
        summary_path = scenario / "scenario_run_summary.json"
        deployment_path = scenario / "prediction_deployment_manifest.json"
        setup_path = scenario / "smpc_debug_setup.json"
        debug_path = scenario / "smpc_debug_steps.jsonl"
        prediction_path = scenario / "prediction_dataset" / "prediction_dataset_raw.jsonl"
        for name, path in (
            ("scenario_summary", summary_path),
            ("deployment", deployment_path),
            ("solver_setup", setup_path),
            ("solver_steps", debug_path),
            ("prediction_log", prediction_path),
        ):
            if not path.is_file():
                problems.append(f"missing_{name}")
        if problems:
            failures[planned["rollout_id"]] = problems
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
        setup = json.loads(setup_path.read_text(encoding="utf-8"))
        prediction_rows = _read_jsonl(prediction_path)
        debug_rows = _read_jsonl(debug_path)
        if summary.get("ran_successfully") is not True:
            problems.append("scenario_failed")
        if not prediction_rows:
            problems.append("empty_prediction_log")
        if not debug_rows:
            problems.append("empty_solver_log")
        expected_run = planned["representative_run_id"]
        frozen_seed = _representative_seed_record(freeze, expected_run)
        model_identity = (deployment.get("model_artifact") or {}).get(
            "sha256_tree"
        ) or (deployment.get("model_artifact") or {}).get("sha256")
        if deployment.get("status") != "pass" or model_identity != frozen_seed["model_identity"]:
            problems.append("deployment_model_hash")
        if deployment.get("calibration_fit_split") not in {"val", "validation"}:
            problems.append("calibration_split")
        calibration_source = deployment.get("calibration_source")
        if not calibration_source or not Path(calibration_source).is_file():
            problems.append("calibration_source")
        else:
            calibration_payload = json.loads(Path(calibration_source).read_text(encoding="utf-8"))
            calibration_value = dict(calibration_payload)
            embedded_calibration_hash = calibration_value.pop("calibration_sha256", None)
            embedded_hash_valid = (
                embedded_calibration_hash is not None
                and embedded_calibration_hash == sha256_payload(calibration_value)
            )
            accepted_calibration_hashes = {sha256_payload(calibration_payload)}
            if embedded_hash_valid:
                accepted_calibration_hashes.add(str(embedded_calibration_hash))
            if frozen_seed["calibration_sha256"] not in accepted_calibration_hashes:
                problems.append("calibration_hash")
        supervisor = setup.get("yield_stop_supervisor") or {}
        if (
            supervisor.get("risk_owned_yield_enabled") != 1
            or supervisor.get("planner_ownership_stress_enabled") != 1
        ):
            problems.append("supervisor_authority")
        expected_profile = {
            "fixed_medium": "fixed_frontier_medium",
            "adaptive": "adaptive_interaction_severity",
        }[planned["risk_policy"]]
        if setup.get("risk_profile") != expected_profile:
            problems.append("risk_profile")
        for row in prediction_rows:
            if (
                row.get("cell_id") != cell_id
                or int(row.get("ego_init_id", -1)) != int(planned["ego_init_id"])
                or row.get("target_style") != planned["target_style"]
                or row.get("ego_policy") != planned["risk_policy"]
            ):
                problems.append("prediction_metadata")
                break
            probabilities = np.asarray(row.get("mode_probabilities"), dtype=float)
            covariances = np.asarray(row.get("pred_sigmas_world"), dtype=float)
            if (
                probabilities.size == 0
                or not np.isfinite(probabilities).all()
                or (probabilities < 0.0).any()
                or not np.isclose(probabilities.sum(), 1.0, atol=1.0e-6)
            ):
                problems.append("invalid_probability")
                break
            if (
                covariances.size == 0
                or not np.isfinite(covariances).all()
                or not np.allclose(covariances, np.swapaxes(covariances, -1, -2), atol=1e-6)
                or not (np.linalg.eigvalsh(covariances) > 0.0).all()
            ):
                problems.append("invalid_covariance")
                break
        if problems:
            failures[planned["rollout_id"]] = sorted(set(problems))
            continue
        completion = {
            "schema_version": "capacity_history_carla_rollout_complete_v3",
            "status": "pass",
            "rollout_id": planned["rollout_id"],
            "manifest_sha256": manifest["manifest_sha256"],
            "scenario_dir": str(scenario.resolve()),
            "artifacts": {
                "scenario_summary": sha256_file(summary_path),
                "deployment": sha256_file(deployment_path),
                "solver_setup": sha256_file(setup_path),
                "solver_steps": sha256_file(debug_path),
                "prediction_log": sha256_file(prediction_path),
            },
        }
        write_immutable_manifest(scenario / "ROLLOUT_COMPLETE.json", completion)
        completed.append(planned["rollout_id"])
    return {
        "schema_version": "capacity_history_carla_materialization_v3",
        "status": (
            "pass"
            if len(completed) == EXPECTED_ROLLOUTS and not failures
            else "incomplete"
        ),
        "completed_rollouts": len(completed),
        "failures": failures,
    }


def _float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _prediction_diagnostics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entropies = []
    top_ades = []
    for row in rows:
        probabilities = np.asarray(row.get("mode_probabilities"), dtype=float)
        if probabilities.size and np.isfinite(probabilities).all():
            entropies.append(
                float(-np.sum(probabilities * np.log(np.maximum(probabilities, 1.0e-300))))
            )
        future = np.asarray(row.get("future_xy_world"), dtype=object)
        valid = np.asarray(row.get("future_valid_mask"), dtype=bool)
        means = np.asarray(row.get("pred_mus_world"), dtype=float)
        if (
            probabilities.size
            and means.ndim == 3
            and future.ndim == 2
            and len(valid)
        ):
            indices = [
                index
                for index in range(min(len(valid), len(future), means.shape[1]))
                if valid[index] and future[index, 0] is not None
            ]
            if indices:
                truth = np.asarray(future[indices], dtype=float)
                top = int(np.argmax(probabilities))
                top_ades.append(
                    float(np.mean(np.linalg.norm(means[top, indices] - truth, axis=-1)))
                )
    return {
        "inloop_prediction_entropy": float(np.mean(entropies)) if entropies else None,
        "inloop_top1_ADE_m": float(np.mean(top_ades)) if top_ades else None,
        "prediction_windows": len(rows),
    }


def extract_carla_outcome_rows(
    manifest: Mapping[str, Any],
    freeze: Mapping[str, Any],
    results_dir: str | Path,
) -> list[dict[str, Any]]:
    audit = audit_closed_loop_outputs(manifest, freeze, results_dir)
    if audit["status"] != "pass":
        raise ValueError(
            f"Closed-loop outcome extraction requires all {EXPECTED_ROLLOUTS} completion gates"
        )
    root = Path(results_dir)
    rows = []
    for planned in manifest["rollouts"]:
        cell_id = "__".join(
            (planned["predictor"], planned["risk_policy"], planned["target_style"])
        )
        cell_dir = root / cell_id
        with (cell_dir / "df_full.csv").open(newline="", encoding="utf-8") as handle:
            metrics = {
                int(row["initial"]): row for row in csv.DictReader(handle)
            }
        gate = json.loads(
            (cell_dir / "postcarla_trajectory_gate.json").read_text(encoding="utf-8")
        )
        gate_by_init = {
            int(Path(item["scenario_dir"]).name.split("_ego_init_")[1].split("_")[0]): item
            for item in gate["evaluations"]
        }
        init_id = int(planned["ego_init_id"])
        scenario = next(cell_dir.glob(f"*ego_init_{init_id:02d}*"))
        debug = _read_jsonl(scenario / "smpc_debug_steps.jsonl")
        labeled = _read_jsonl(
            scenario / "prediction_dataset" / "prediction_dataset_labeled.jsonl"
        )
        metric = metrics[init_id]
        gate_item = gate_by_init[init_id]
        safety = gate_item["pair_safety"][0]
        prediction_valid = [
            bool(value)
            for row in debug
            for value in (row.get("prediction_valid") or [])
        ]
        supervisor = [
            row.get("yield_stop_supervisor") or {} for row in debug
        ]
        row = {
            **planned,
            "completion_rate": _float(metric.get("completion_valid")),
            "completion_time_s": _float(metric.get("completion_time")),
            "min_footprint_separation_m": _float(
                safety.get("min_footprint_separation_m")
            ),
            "footprint_collision_rate": _float(safety.get("footprint_collision")),
            "solver_failure_fraction": _float(metric.get("solver_failure_frac")),
            "prediction_fallback_fraction": (
                float(1.0 - np.mean(prediction_valid)) if prediction_valid else None
            ),
            "solver_activity_fraction": (
                float(np.mean([bool(row.get("solver")) for row in debug]))
                if debug
                else None
            ),
            "supervisor_active_fraction": (
                float(
                    np.mean(
                        [
                            bool(
                                item.get("active")
                                or item.get("hard_stop_active")
                                or item.get("override_active")
                            )
                            for item in supervisor
                        ]
                    )
                )
                if supervisor
                else None
            ),
            **_prediction_diagnostics(labeled),
        }
        rows.append(row)
    if len(rows) != EXPECTED_ROLLOUTS:
        raise ValueError(
            f"Closed-loop outcome table must contain {EXPECTED_ROLLOUTS} rows"
        )
    return rows


def _paired_predictor_effects(
    rows: Sequence[Mapping[str, Any]], metric: str, risk: str
) -> dict[int, float]:
    values: dict[tuple[str, str, int], dict[str, float]] = defaultdict(dict)
    for row in rows:
        if row["risk_policy"] != risk or row.get(metric) is None:
            continue
        key = (str(row["target_style"]), risk, int(row["ego_init_id"]))
        values[key][str(row["predictor"])] = float(row[metric])
    by_group: dict[int, list[float]] = defaultdict(list)
    for (_, _, group), pair in values.items():
        if set(pair) == set(PREDICTORS):
            by_group[group].append(pair["P_star"] - pair["B1"])
    effects = {group: float(np.mean(style_effects)) for group, style_effects in by_group.items()}
    if set(effects) != set(CLOSED_LOOP_GROUPS):
        raise ValueError(f"Incomplete paired closed-loop units for {metric}/{risk}")
    return effects


def _effect_record(identifier: str, metric: str, effects: Mapping[int, float]) -> dict[str, Any]:
    low, high = cluster_bootstrap_interval(effects)
    return {
        "contrast_id": identifier,
        "metric": metric,
        "effect_P_star_minus_B1": float(np.mean(list(effects.values()))),
        "cluster_interval_95": [low, high],
        "raw_sign_flip_p": paired_sign_flip_p(effects),
        "independent_groups": len(effects),
        "paired_group_effects": {str(k): v for k, v in sorted(effects.items())},
    }


def analyze_predictor_by_risk(
    rows: Sequence[Mapping[str, Any]], metrics: Sequence[str]
) -> dict[str, Any]:
    within = []
    interactions = []
    unavailable = []
    for metric in metrics:
        try:
            effects = {
                risk: _paired_predictor_effects(rows, metric, risk)
                for risk in RISK_POLICIES
            }
        except ValueError as error:
            unavailable.append(
                {
                    "metric": metric,
                    "status": "under_supported_or_undefined",
                    "reason": str(error),
                    "claim_allowed": False,
                }
            )
            continue
        for risk in RISK_POLICIES:
            within.append(
                _effect_record(f"{metric}__P_star_minus_B1__{risk}", metric, effects[risk])
            )
        reference = effects["fixed_medium"]
        for risk in RISK_POLICIES:
            if risk == "fixed_medium":
                continue
            did = {group: effects[risk][group] - reference[group] for group in CLOSED_LOOP_GROUPS}
            interactions.append(
                _effect_record(
                    f"{metric}__model_by_risk__{risk}_minus_fixed_medium",
                    metric,
                    did,
                )
            )
    return {
        "schema_version": "capacity_history_predictor_by_risk_analysis_v3",
        "status": "pass",
        "effect_sign": "P_star minus B1; interpretation depends on outcome desirability",
        "independent_groups": len(CLOSED_LOOP_GROUPS),
        "within_risk_contrasts": within,
        "model_by_risk_interactions": interactions,
        "null_or_under_supported_metrics": unavailable,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_parser = subparsers.add_parser("freeze")
    freeze_parser.add_argument("--selection-freeze", required=True, type=Path)
    freeze_parser.add_argument("--nuisance-json", required=True, type=Path)
    freeze_parser.add_argument("--output", required=True, type=Path)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--selection-freeze", required=True, type=Path)
    audit_parser.add_argument("--manifest", required=True, type=Path)
    audit_parser.add_argument("--results-dir", required=True, type=Path)
    audit_parser.add_argument("--output", required=True, type=Path)
    materialize_parser = subparsers.add_parser("materialize-carla")
    materialize_parser.add_argument("--selection-freeze", required=True, type=Path)
    materialize_parser.add_argument("--manifest", required=True, type=Path)
    materialize_parser.add_argument("--results-dir", required=True, type=Path)
    materialize_parser.add_argument("--output", required=True, type=Path)
    analysis_parser = subparsers.add_parser("analyze")
    analysis_parser.add_argument("--rows-json", required=True, type=Path)
    analysis_parser.add_argument("--metric", action="append", required=True)
    analysis_parser.add_argument("--output", required=True, type=Path)
    synthesize_parser = subparsers.add_parser("synthesize-carla")
    synthesize_parser.add_argument("--selection-freeze", required=True, type=Path)
    synthesize_parser.add_argument("--manifest", required=True, type=Path)
    synthesize_parser.add_argument("--results-dir", required=True, type=Path)
    synthesize_parser.add_argument("--rows-output", required=True, type=Path)
    synthesize_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        selection = json.loads(args.selection_freeze.read_text(encoding="utf-8"))
        nuisance = json.loads(args.nuisance_json.read_text(encoding="utf-8"))
        payload = build_closed_loop_manifest(
            selection, build_group_registry(), nuisance_settings=nuisance
        )
        validate_closed_loop_manifest(payload, selection)
        report = write_immutable_manifest(args.output, payload)
    elif args.command == "audit":
        selection = json.loads(args.selection_freeze.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = audit_closed_loop_outputs(
            manifest, selection, args.results_dir
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    elif args.command == "materialize-carla":
        selection = json.loads(args.selection_freeze.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = materialize_carla_rollout_completions(
            manifest, selection, args.results_dir
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    elif args.command == "analyze":
        rows = json.loads(args.rows_json.read_text(encoding="utf-8"))
        report = analyze_predictor_by_risk(rows, args.metric)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    else:
        selection = json.loads(args.selection_freeze.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        rows = extract_carla_outcome_rows(
            manifest, selection, args.results_dir
        )
        args.rows_output.parent.mkdir(parents=True, exist_ok=True)
        args.rows_output.write_text(
            json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        report = analyze_predictor_by_risk(
            rows,
            [
                "completion_rate",
                "completion_time_s",
                "min_footprint_separation_m",
                "footprint_collision_rate",
                "solver_failure_fraction",
                "prediction_fallback_fraction",
                "solver_activity_fraction",
                "supervisor_active_fraction",
                "inloop_prediction_entropy",
                "inloop_top1_ADE_m",
            ],
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
