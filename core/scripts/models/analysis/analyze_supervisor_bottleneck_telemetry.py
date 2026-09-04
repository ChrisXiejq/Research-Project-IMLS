#!/usr/bin/env python3
"""Audit SF4/V3 telemetry for the cross-layer supervisor-bottleneck thesis.

The analysis deliberately consumes the frozen, rollout-level canonical products.
It does not reinterpret repeated 10 Hz samples as independent observations and it
fails closed when a same-state counterfactual needed for a masking claim is absent.
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
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


SCHEMA_VERSION = "supervisor_bottleneck_telemetry_audit_v1"
SF4_ROOT = Path(
    "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results"
)
SF4_ANALYSIS = SF4_ROOT / "analysis"
V3_ROOT = Path("docs/paper/generated/capacity_history_v3/results/closed_loop")
DAY12_ROOT = Path("docs/paper/generated/day12/timing_synthesis")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int:
    parsed = _number(value)
    return 0 if parsed is None else int(parsed)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _bootstrap_ci(values: list[float], *, seed: int, draws: int = 10000) -> list[float] | None:
    """Percentile bootstrap over initialization-cluster summaries."""
    if not values:
        return None
    rng = random.Random(seed)
    estimates = sorted(
        mean(rng.choice(values) for _ in values)
        for _ in range(draws)
    )
    return [estimates[int(0.025 * (draws - 1))], estimates[int(0.975 * (draws - 1))]]


def classify_intervention_record(row: dict[str, Any], *, epsilon: float = 1e-9) -> str:
    """Classify a rollout summary without treating missing telemetry as zero."""
    requested = _number(row.get("supervisor_any_channel_requested_fraction"))
    applied = _number(row.get("supervisor_authority_applied_fraction"))
    bypass = _number(row.get("rule_smpc_bypass_applied_fraction"))
    actual_delta = _number(row.get("actual_minus_nominal_accel_abs_mean_mps2"))
    if any(value is None for value in (requested, applied, bypass, actual_delta)):
        return "missing"
    if bypass > epsilon:
        return "bypass"
    if applied > epsilon or actual_delta > epsilon:
        return "apply"
    if requested > epsilon:
        return "monitor_only"
    return "inactive"


def _field_availability(
    rows: list[dict[str, Any]], fields: Iterable[str], *, representation: str
) -> list[dict[str, Any]]:
    output = []
    total = len(rows)
    for field in fields:
        present = field in rows[0] if rows else False
        nonmissing = sum(_number(row.get(field)) is not None for row in rows) if present else 0
        output.append(
            {
                "field": field,
                "column_present": present,
                "nonmissing_rows": nonmissing,
                "total_rows": total,
                "availability": "complete" if total and nonmissing == total else "partial" if nonmissing else "absent",
                "representation": representation,
            }
        )
    return output


def _availability_report(sf4_rows: list[dict[str, str]], v3_rows: list[dict[str, Any]]) -> dict[str, Any]:
    sf4_fields = [
        "candidate_minus_nominal_accel_mean_mps2",
        "candidate_minus_nominal_accel_abs_mean_mps2",
        "actual_minus_nominal_accel_mean_mps2",
        "actual_minus_nominal_accel_abs_mean_mps2",
        "supervisor_candidate_requested_fraction",
        "supervisor_authority_applied_fraction",
        "supervisor_any_channel_requested_fraction",
        "upstream_reference_requested_fraction",
        "upstream_reference_linearization_requested_fraction",
        "rule_smpc_bypass_requested_fraction",
        "rule_smpc_bypass_applied_fraction",
        "yield_entry_step",
        "first_sustained_stop_step",
        "nominal_conflict_clear_step",
        "actual_path_release_step",
        "buffered_conflict_clear_step",
        "sustained_resume_step",
        "minimum_margin_adjusted_bbox_separation_m",
        "risk_policy",
        "factual_solver_attempt_count",
        "attempted_controller_accepted_count",
        "attempted_fallback_or_nonaccepted_count",
        "factual_solver_return_status_counts_json",
    ]
    v3_fields = [
        "predictor",
        "risk_policy",
        "target_style",
        "inloop_top1_ADE_m",
        "completion_time_s",
        "min_footprint_separation_m",
        "supervisor_active_fraction",
        "solver_failure_fraction",
    ]
    # Risk/status strings need a string-aware availability correction.
    sf4 = _field_availability(sf4_rows, sf4_fields, representation="rollout aggregate")
    v3 = _field_availability(v3_rows, v3_fields, representation="rollout aggregate")
    for record, rows in [(item, sf4_rows) for item in sf4] + [(item, v3_rows) for item in v3]:
        if record["field"] in {"risk_policy", "predictor", "target_style", "factual_solver_return_status_counts_json"}:
            count = sum(row.get(record["field"]) not in (None, "") for row in rows)
            record["nonmissing_rows"] = count
            record["availability"] = "complete" if count == len(rows) else "partial" if count else "absent"
    return {
        "schema_version": "supervisor_bottleneck_field_availability_v1",
        "status": "pass",
        "datasets": {
            "SF4": {"rows": len(sf4_rows), "fields": sf4},
            "V3_closed_loop": {"rows": len(v3_rows), "fields": v3},
        },
        "semantic_fields": {
            "nominal_solver_command_vector": "not_materialized_locally; only aligned acceleration deltas are canonical",
            "supervisor_candidate": "SF4 rollout-level candidate-minus-nominal acceleration summaries available",
            "executed_command": "SF4 rollout-level actual-minus-nominal acceleration summaries available",
            "same_state_alternative_predictor_or_risk_commands": "absent_by_design",
            "phase_events": "partially_available_and_never_imputed",
            "raw_per_step_debug": "manifested_in_full_raw_snapshot_but_not_required_for_current_rollout_estimands",
        },
    }


INTERVENTION_METRICS = [
    "supervisor_any_channel_requested_fraction",
    "supervisor_candidate_requested_fraction",
    "supervisor_authority_applied_fraction",
    "rule_smpc_bypass_requested_fraction",
    "rule_smpc_bypass_applied_fraction",
    "candidate_minus_nominal_accel_abs_mean_mps2",
    "actual_minus_nominal_accel_abs_mean_mps2",
]


def _intervention_outputs(sf4_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rollout_rows: list[dict[str, Any]] = []
    for row in sf4_rows:
        record: dict[str, Any] = {
            "cell_id": row["cell_id"],
            "ego_init_id": int(row["ego_init_id"]),
            "risk_policy": row["risk_policy"],
            "target_style": row["target_style"],
            "supervisor_authority_mode": row["supervisor_authority_mode"],
            "intervention_mode": classify_intervention_record(row),
        }
        record.update({metric: _number(row.get(metric)) for metric in INTERVENTION_METRICS})
        rollout_rows.append(record)

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rollout_rows:
        grouped[(row["supervisor_authority_mode"], row["risk_policy"], row["target_style"])].append(row)
    summaries: list[dict[str, Any]] = []
    for index, (key, rows) in enumerate(sorted(grouped.items())):
        authority, risk, style = key
        result: dict[str, Any] = {
            "supervisor_authority_mode": authority,
            "risk_policy": risk,
            "target_style": style,
            "independent_init_groups": len({row["ego_init_id"] for row in rows}),
            "rollouts": len(rows),
            "intervention_modes_json": json.dumps(dict(sorted(Counter(row["intervention_mode"] for row in rows).items()))),
        }
        for metric_index, metric in enumerate(INTERVENTION_METRICS):
            values = [row[metric] for row in rows if row[metric] is not None]
            result[f"mean_{metric}"] = mean(values) if values else None
            ci = _bootstrap_ci(values, seed=1729 + index * 101 + metric_index)
            result[f"ci95_low_{metric}"] = None if ci is None else ci[0]
            result[f"ci95_high_{metric}"] = None if ci is None else ci[1]
        summaries.append(result)
    return rollout_rows, summaries


PHASE_FIELDS = [
    "yield_entry_step",
    "first_sustained_stop_step",
    "nominal_conflict_clear_step",
    "actual_path_release_step",
    "buffered_conflict_clear_step",
    "sustained_resume_step",
    "cautious_approach_progress_m",
    "first_stop_distance_to_conflict_m",
    "first_stop_distance_to_designed_stop_m",
    "stopped_duration_s",
    "nominal_conflict_clear_to_actual_path_release_s",
    "actual_path_release_to_sustained_resume_s",
    "buffered_conflict_clear_to_sustained_resume_s",
]


def _phase_outputs(sf4_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    availability: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in sf4_rows:
        grouped[(row["supervisor_authority_mode"], row["risk_policy"], row["target_style"])].append(row)
    for key, rows in sorted(grouped.items()):
        authority, risk, style = key
        for field in PHASE_FIELDS:
            values = [_number(row.get(field)) for row in rows]
            defined = [value for value in values if value is not None]
            availability.append(
                {
                    "supervisor_authority_mode": authority,
                    "risk_policy": risk,
                    "target_style": style,
                    "phase_field": field,
                    "defined_init_groups": len(defined),
                    "total_init_groups": len(rows),
                    "availability_fraction": len(defined) / len(rows),
                    "analysis_status": "complete" if len(defined) == len(rows) else "descriptive_only_missing_event_clock" if defined else "unavailable",
                    "missing_values_imputed": False,
                }
            )
            outcomes.append(
                {
                    "supervisor_authority_mode": authority,
                    "risk_policy": risk,
                    "target_style": style,
                    "phase_field": field,
                    "defined_init_groups": len(defined),
                    "mean_defined_only": mean(defined) if defined else None,
                    "ci95_defined_only": _bootstrap_ci(defined, seed=9109 + len(outcomes)) if defined else None,
                    "claim_boundary": "defined cases only; missing event clocks were not imputed",
                }
            )
    return availability, outcomes


def _solver_reconciliation(sf4_rows: list[dict[str, str]], complete: dict[str, Any]) -> dict[str, Any]:
    totals = {
        "debug_steps": sum(_integer(row.get("debug_steps")) for row in sf4_rows),
        "factual_solver_attempts": sum(_integer(row.get("factual_solver_attempt_count")) for row in sf4_rows),
        "controller_accepted_attempts": sum(_integer(row.get("attempted_controller_accepted_count")) for row in sf4_rows),
        "fallback_or_nonaccepted_attempts": sum(_integer(row.get("attempted_fallback_or_nonaccepted_count")) for row in sf4_rows),
        "bypass_requested_steps": sum(_integer(row.get("rule_smpc_bypass_requested_count")) for row in sf4_rows),
        "bypass_applied_steps": sum(_integer(row.get("rule_smpc_bypass_applied_count")) for row in sf4_rows),
    }
    statuses: Counter[str] = Counter()
    for row in sf4_rows:
        statuses.update(json.loads(row["factual_solver_return_status_counts_json"]))
    totals["raw_solver_return_status_counts"] = dict(sorted(statuses.items()))
    canonical = complete["solver_execution"]
    checks = {
        "attempt_partition": totals["factual_solver_attempts"] == totals["controller_accepted_attempts"] + totals["fallback_or_nonaccepted_attempts"],
        "debug_partition": totals["debug_steps"] == totals["factual_solver_attempts"] + totals["bypass_applied_steps"],
        "raw_status_partition": sum(statuses.values()) == totals["factual_solver_attempts"],
        "canonical_18552_attempts": totals["factual_solver_attempts"] == 18552 == canonical["factual_solver_attempts"],
        "canonical_17822_accepted": totals["controller_accepted_attempts"] == 17822 == canonical["controller_accepted_attempts"],
        "canonical_730_fallback": totals["fallback_or_nonaccepted_attempts"] == 730 == canonical["fallback_or_nonaccepted_attempts"],
        "canonical_bypass": totals["bypass_applied_steps"] == canonical["bypass_applied_steps"],
    }
    if not all(checks.values()):
        raise ValueError(f"SF4 solver-path reconciliation failed: {checks}")
    return {
        "schema_version": "supervisor_bottleneck_solver_path_reconciliation_v1",
        "status": "pass",
        "rollouts": len(sf4_rows),
        "totals": totals,
        "checks": checks,
        "denominator": "factual SMPC attempts; effective rule-bypass steps excluded",
        "semantic_boundary": "controller acceptance is not a claim of strict optimizer feasibility",
    }


def _attenuation_audit(sf4_rows: list[dict[str, str]], inference: dict[str, Any]) -> dict[str, Any]:
    by_cell = []
    for row in sf4_rows:
        candidate = _number(row.get("candidate_minus_nominal_accel_abs_mean_mps2"))
        actual = _number(row.get("actual_minus_nominal_accel_abs_mean_mps2"))
        by_cell.append(
            {
                "cell_id": row["cell_id"],
                "ego_init_id": int(row["ego_init_id"]),
                "risk_policy": row["risk_policy"],
                "target_style": row["target_style"],
                "supervisor_authority_mode": row["supervisor_authority_mode"],
                "candidate_minus_nominal_accel_abs_mean_mps2": candidate,
                "actual_minus_nominal_accel_abs_mean_mps2": actual,
                "candidate_to_executed_transmission_ratio": None if candidate in (None, 0.0) or actual is None else actual / candidate,
            }
        )
    off = [row for row in sf4_rows if row["supervisor_authority_mode"] == "off"]
    on = [row for row in sf4_rows if row["supervisor_authority_mode"] == "on"]
    floor = {
        "authority_on_completion": sum(_integer(row["completion_success"]) for row in on),
        "authority_on_rollouts": len(on),
        "authority_off_completion": sum(_integer(row["completion_success"]) for row in off),
        "authority_off_rollouts": len(off),
    }
    if floor != {
        "authority_on_completion": 40,
        "authority_on_rollouts": 40,
        "authority_off_completion": 0,
        "authority_off_rollouts": 40,
    }:
        raise ValueError(f"Unexpected SF4 completion floor: {floor}")
    key_metrics = {
        metric: inference["direct_paired_effects"][metric]
        for metric in (
            "candidate_minus_nominal_accel_abs_mean_mps2",
            "actual_minus_nominal_accel_abs_mean_mps2",
            "failure_penalized_completion_time_s",
            "minimum_margin_adjusted_bbox_separation_m",
        )
    }
    return {
        "schema_version": "supervisor_bottleneck_attenuation_claim_audit_v1",
        "status": "pass",
        "rollout_channel_records": by_cell,
        "identified_estimands": {
            "authority_manipulation": "nominal-to-candidate and nominal-to-executed acceleration deltas within factual rollout summaries",
            "authority_and_risk_DID": key_metrics,
        },
        "floor_saturation": floor,
        "same_state_alternative_predictor_commands_available": False,
        "same_state_alternative_risk_commands_available": False,
        "selective_masking_identified": False,
        "selective_masking_claim_status": "refused_missing_identifying_comparison_and_authority_off_floor_saturation",
        "permitted_claim": "SF4 identifies a large common authority effect and verifies command intervention; it does not identify selective masking of one predictor or risk policy.",
    }


def _timing_registry(root: Path) -> dict[str, Any]:
    complete_path = root / DAY12_ROOT / "DAY12_TIMING_SYNTHESIS_COMPLETE.json"
    rollout_path = root / DAY12_ROOT / "day12_timing_rollout_metrics.csv"
    contrast_path = root / DAY12_ROOT / "day12_timing_paired_contrasts.csv"
    complete = _read_json(complete_path)
    rows = _read_csv(rollout_path)
    offsets = sorted({_number(row["target_offset_m"]) for row in rows})
    init_ids = sorted({int(row["ego_init_id"]) for row in rows})
    if complete.get("status") != "pass" or complete.get("rollouts") != len(rows):
        raise ValueError("Day12 timing evidence is incomplete")
    return {
        "schema_version": "supervisor_bottleneck_timing_threshold_registry_v1",
        "status": "pass",
        "records": [
            {
                "evidence_id": "legacy_day10_day11_arrival_timing_synthesis",
                "population_label": "Town05 ego initialisations 46--50; nominal and shifted batches",
                "independent_unit": "ego_init_id",
                "independent_groups": init_ids,
                "treatment": "target longitudinal arrival offset",
                "levels_m": offsets,
                "rollouts": len(rows),
                "role": "secondary timing sensitivity",
                "pooling_permission": "must_not_pool_with_R3_V3_or_SF4",
                "sources": [
                    {"path": str(complete_path.relative_to(root)), "sha256": _sha256(complete_path)},
                    {"path": str(rollout_path.relative_to(root)), "sha256": _sha256(rollout_path)},
                    {"path": str(contrast_path.relative_to(root)), "sha256": _sha256(contrast_path)},
                ],
            },
            {
                "evidence_id": "rule_parameter_threshold_sweep",
                "availability": "not_present_in_canonical_generated_evidence",
                "role": "not_claimed",
                "boundary": "Arrival-timing sensitivity changes initial conditions; it is not a sweep of supervisor thresholds.",
            },
        ],
    }


def build_audit(root: Path, output_dir: Path, server_inspection: Path | None = None) -> dict[str, Any]:
    sf4_csv = root / SF4_ANALYSIS / "sf4_rollout_outcomes.csv"
    sf4_complete_path = root / SF4_ANALYSIS / "SF4_ANALYSIS_COMPLETE.json"
    sf4_inference_path = root / SF4_ANALYSIS / "sf4_inference.json"
    sf4_snapshot_manifest = root / SF4_ROOT / "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.files.json"
    sf4_snapshot_sidecar = root / SF4_ROOT / "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz.json"
    v3_rows_path = root / V3_ROOT / "closed_loop_rows.json"
    v3_complete_path = root / V3_ROOT / "CLOSED_LOOP_COMPLETE.json"

    sf4_rows = _read_csv(sf4_csv)
    sf4_complete = _read_json(sf4_complete_path)
    inference = _read_json(sf4_inference_path)
    snapshot_manifest = _read_json(sf4_snapshot_manifest)
    snapshot_sidecar = _read_json(sf4_snapshot_sidecar)
    v3_rows = _read_json(v3_rows_path)
    v3_complete = _read_json(v3_complete_path)
    if len(sf4_rows) != 80 or sf4_complete.get("status") != "pass":
        raise ValueError("SF4 canonical analysis is not complete")
    if len(v3_rows) != 80 or v3_complete.get("status") != "pass":
        raise ValueError("V3 canonical closed-loop analysis is not complete")

    output_dir.mkdir(parents=True, exist_ok=True)
    availability = _availability_report(sf4_rows, v3_rows)
    _write_json(output_dir / "telemetry_availability.json", availability)

    rollout_intervention, intervention_summary = _intervention_outputs(sf4_rows)
    intervention_fields = list(rollout_intervention[0])
    _write_csv(output_dir / "supervisor_intervention_by_rollout.csv", rollout_intervention, intervention_fields)
    _write_csv(output_dir / "supervisor_intervention_by_cell.csv", intervention_summary, list(intervention_summary[0]))

    phase_availability, phase_outcomes = _phase_outputs(sf4_rows)
    _write_csv(output_dir / "phase_event_availability.csv", phase_availability, list(phase_availability[0]))
    _write_json(
        output_dir / "phase_outcomes.json",
        {
            "schema_version": "supervisor_bottleneck_phase_outcomes_v1",
            "status": "pass",
            "missing_values_imputed": False,
            "rows": phase_outcomes,
        },
    )
    phase_contrast_metrics = {
        metric: inference["direct_paired_effects"][metric]
        for metric in (
            "cautious_approach_progress_m",
            "first_stop_distance_to_conflict_m",
            "first_stop_distance_to_designed_stop_m",
            "stopped_duration_s",
            "nominal_conflict_clear_to_actual_path_release_s",
            "actual_path_release_to_sustained_resume_s",
            "buffered_conflict_clear_to_sustained_resume_s",
        )
    }
    _write_json(
        output_dir / "phase_contrast_availability.json",
        {
            "schema_version": "supervisor_bottleneck_phase_contrast_availability_v1",
            "status": "pass",
            "independent_unit": "ego_init_id",
            "missing_values_imputed": False,
            "metrics": phase_contrast_metrics,
            "boundary": "A paired contrast is confirmatory only when its required treatment cells are defined for the same initialization group; otherwise the canonical descriptive-only status is retained.",
        },
    )

    solver = _solver_reconciliation(sf4_rows, sf4_complete)
    _write_json(output_dir / "solver_path_reconciliation.json", solver)
    attenuation = _attenuation_audit(sf4_rows, inference)
    _write_json(output_dir / "attenuation_claim_audit.json", attenuation)
    timing = _timing_registry(root)
    _write_json(output_dir / "timing_threshold_evidence_registry.json", timing)

    remote = None
    if server_inspection is not None:
        remote = _read_json(server_inspection)
        if remote.get("status") != "pass":
            raise ValueError("Server inspection record is not complete")
        _write_json(output_dir / "remote_evidence_inspection.json", remote)

    sources = []
    for path in (
        sf4_csv,
        sf4_complete_path,
        sf4_inference_path,
        sf4_snapshot_manifest,
        sf4_snapshot_sidecar,
        v3_rows_path,
        v3_complete_path,
    ):
        sources.append({"path": str(path.relative_to(root)), "sha256": _sha256(path)})
    checks = {
        "sf4_rollouts_80": len(sf4_rows) == 80,
        "v3_rollouts_80": len(v3_rows) == 80,
        "solver_reconciled": solver["status"] == "pass",
        "missing_phase_events_not_imputed": all(not row["missing_values_imputed"] for row in phase_availability),
        "selective_masking_refused": attenuation["selective_masking_identified"] is False,
        "raw_snapshot_manifest_matches_sidecar": _sha256(sf4_snapshot_manifest) == snapshot_sidecar["files_manifest_sha256"],
        "raw_snapshot_declares_80_rollouts": snapshot_manifest["coverage"]["expected_rollouts"] == 80,
        "server_inspection_recorded": remote is not None,
    }
    if not all(checks.values()):
        raise ValueError(f"Telemetry audit failed: {checks}")
    artifacts = sorted(path.name for path in output_dir.iterdir() if path.is_file())
    complete = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "checks": checks,
        "artifacts": artifacts,
        "scientific_boundary": "Rollout/init groups are independent units. SF4 supports a common authority effect, not selective masking; legacy timing evidence remains a distinct population.",
    }
    _write_json(output_dir / "TELEMETRY_AUDIT_COMPLETE.json", complete)
    return complete


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit"),
    )
    parser.add_argument("--server-inspection", type=Path, required=True)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    inspection = args.server_inspection if args.server_inspection.is_absolute() else args.root / args.server_inspection
    result = build_audit(args.root, output, inspection)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
