#!/usr/bin/env python3
"""Quantify give-way approach, stop and release behaviour from SMPC logs.

This is a post-hoc mechanism audit motivated by supervisor feedback.  It does
not alter the four registered dissertation hypotheses and must not be used as
an outcome-dependent reason to rerun the corrected R3 matrix.

The formal mode intentionally reads only promoted R3 scenario directories,
checks their debug hashes against the matrix audit, and treats the five ego
initialisations as the independent units.  Simulation steps are never treated
as independent observations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "supervisor_feedback_behaviour_audit_v1"
FORMAL_CELL_RE = re.compile(
    r"^(?P<predictor>B[01])_(?P<risk>adaptive|fixed_(?:aggressive|medium|conservative))_"
    r"(?P<style>assertive|reactive)$"
)
SCENARIO_INIT_RE = re.compile(r"_ego_init_(?P<init>\d+)_")
ACTIVE_YIELD_PHASES = {
    "cautious_approach_observed_target",
    "approach_yield_line",
    "hold_yield_line",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        rows.append(value)
    return rows


def finite_number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def truthy(value: object) -> bool:
    return value is True or value in (1, "1", "true", "True")


def first_sustained_index(
    rows: Sequence[Mapping[str, Any]],
    predicate,
    *,
    consecutive: int,
    start_index: int = 0,
    end_index: int | None = None,
) -> int | None:
    if consecutive < 1:
        raise ValueError("consecutive must be positive")
    run_start: int | None = None
    run_length = 0
    stop_index = (
        len(rows)
        if end_index is None
        else min(len(rows), max(0, end_index))
    )
    for index in range(max(0, start_index), stop_index):
        if predicate(rows[index]):
            if run_start is None:
                run_start = index
            run_length += 1
            if run_length >= consecutive:
                return run_start
        else:
            run_start = None
            run_length = 0
    return None


def supervisor(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("yield_stop_supervisor")
    return value if isinstance(value, Mapping) else {}


def speed(row: Mapping[str, Any]) -> float | None:
    value = row.get("vehicle_state")
    return finite_number(value.get("speed")) if isinstance(value, Mapping) else None


def step(row: Mapping[str, Any]) -> int | None:
    value = finite_number(row.get("step"))
    return int(value) if value is not None and value.is_integer() else None


def event_time_s(rows: Sequence[Mapping[str, Any]], left: int | None, right: int | None, fps: float) -> float | None:
    if left is None or right is None:
        return None
    left_step = step(rows[left])
    right_step = step(rows[right])
    if left_step is None or right_step is None or right_step < left_step:
        return None
    return (right_step - left_step) / fps


def value_at(rows: Sequence[Mapping[str, Any]], index: int | None, field: str) -> float | None:
    if index is None:
        return None
    return finite_number(supervisor(rows[index]).get(field))


def _yield_entry_index(rows: Sequence[Mapping[str, Any]]) -> int | None:
    for index, row in enumerate(rows):
        state = supervisor(row)
        phase = str(state.get("phase") or "")
        if truthy(state.get("active")) or phase in ACTIVE_YIELD_PHASES:
            return index
    return None


def _release_index(rows: Sequence[Mapping[str, Any]], start_index: int | None) -> tuple[int | None, str | None]:
    if start_index is None:
        return None, None
    for index in range(start_index, len(rows)):
        state = supervisor(rows[index])
        recovery = state.get("recovery") if isinstance(state.get("recovery"), Mapping) else {}
        signals = (
            ("raw_reduced_clear_path_release", state.get("raw_reduced_clear_path_release")),
            ("reduced_clear_path_release", state.get("reduced_clear_path_release")),
            ("recovery.clear_path_release_start", recovery.get("clear_path_release_start")),
        )
        for name, value in signals:
            if truthy(value):
                return index, name
        if str(state.get("phase") or "") == "released_recovery":
            return index, "phase_released_recovery"
    return None, None


def _first_flag_index(
    rows: Sequence[Mapping[str, Any]], field: str, start_index: int | None
) -> int | None:
    if start_index is None:
        return None
    for index in range(start_index, len(rows)):
        if truthy(supervisor(rows[index]).get(field)):
            return index
    return None


def validate_debug_rows(
    rows: Sequence[Mapping[str, Any]], *, source: str = "debug rows"
) -> list[int]:
    """Validate one parsed rollout once and return its strictly ordered steps."""

    if not rows:
        raise ValueError(f"No debug rows in {source}")
    parsed_steps = [step(row) for row in rows]
    if any(value is None for value in parsed_steps):
        raise ValueError(f"Non-integral or missing step in {source}")
    integral_steps = [int(value) for value in parsed_steps if value is not None]
    if any(right <= left for left, right in zip(integral_steps, integral_steps[1:])):
        raise ValueError(f"Steps are not strictly increasing in {source}")
    return integral_steps


def analyze_rollout_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    fps: float,
    stop_speed_mps: float,
    resume_speed_mps: float,
    consecutive_steps: int,
    source: str = "debug rows",
) -> dict[str, Any]:
    parsed_steps = validate_debug_rows(rows, source=source)

    entry = _yield_entry_index(rows)
    nominal_clear = _first_flag_index(rows, "target_nominally_cleared_conflict", entry)
    buffered_clear = _first_flag_index(rows, "target_cleared_conflict", entry)
    release, release_source = _release_index(rows, entry)
    # A give-way stop must occur inside the activated supervisor episode.  A
    # later terminal/goal stop is a different event and must never be used to
    # fill a missing mechanism observation.
    stop_window_status = (
        "evaluated"
        if entry is not None and release is not None
        else "censored_missing_release"
        if entry is not None
        else "not_applicable_missing_yield_entry"
    )
    stop = (
        first_sustained_index(
            rows,
            lambda row: speed(row) is not None
            and float(speed(row)) <= stop_speed_mps,
            consecutive=consecutive_steps,
            start_index=entry,
            # The registered give-way stop window is half-open: yield entry
            # through, but not including, the actual path-release row.
            end_index=release,
        )
        if entry is not None and release is not None
        else None
    )
    resume = first_sustained_index(
        rows,
        lambda row: speed(row) is not None and float(speed(row)) >= resume_speed_mps,
        consecutive=consecutive_steps,
        start_index=release or 0,
    ) if release is not None else None

    entry_distance = value_at(rows, entry, "ego_distance_to_conflict")
    stop_distance = value_at(rows, stop, "ego_distance_to_conflict")
    entry_route_s = value_at(rows, entry, "ego_route_s")
    stop_route_s = value_at(rows, stop, "ego_route_s")
    designed_clearance = value_at(rows, stop, "stop_clearance")
    if designed_clearance is None:
        designed_clearance = value_at(rows, stop, "dynamic_stop_clearance")
    stop_line_error = value_at(rows, stop, "ego_distance_to_stop")
    if stop_line_error is None and stop_distance is not None and designed_clearance is not None:
        stop_line_error = stop_distance - designed_clearance

    approach_progress = None
    if entry_route_s is not None and stop_route_s is not None:
        approach_progress = stop_route_s - entry_route_s
    elif entry_distance is not None and stop_distance is not None:
        approach_progress = entry_distance - stop_distance

    active_indices = [
        index for index in range(entry or 0, (release + 1) if release is not None else len(rows))
        if truthy(supervisor(rows[index]).get("active"))
    ] if entry is not None else []
    active_speeds = [speed(rows[index]) for index in active_indices]
    active_speeds = [float(value) for value in active_speeds if value is not None]

    return {
        "debug_rows": len(rows),
        "first_step": parsed_steps[0],
        "last_step": parsed_steps[-1],
        "yield_entry_step": step(rows[entry]) if entry is not None else None,
        "first_sustained_stop_step": step(rows[stop]) if stop is not None else None,
        "target_nominal_clear_step": step(rows[nominal_clear]) if nominal_clear is not None else None,
        "target_buffered_clear_step": step(rows[buffered_clear]) if buffered_clear is not None else None,
        "path_release_step": step(rows[release]) if release is not None else None,
        "path_release_source": release_source,
        "sustained_resume_step": step(rows[resume]) if resume is not None else None,
        "yield_entry_distance_to_conflict_m": entry_distance,
        "first_stop_distance_to_conflict_m": stop_distance,
        "designed_stop_clearance_m": designed_clearance,
        "first_stop_distance_to_designed_stop_m": stop_line_error,
        "cautious_approach_progress_m": approach_progress,
        "cautious_approach_duration_s": event_time_s(rows, entry, stop, fps),
        "pre_clearance_stopped_duration_s": event_time_s(rows, stop, release, fps),
        "nominal_clear_to_release_latency_s": event_time_s(rows, nominal_clear, release, fps),
        "buffered_clear_to_resume_latency_s": event_time_s(rows, buffered_clear, resume, fps),
        "release_to_resume_latency_s": event_time_s(rows, release, resume, fps),
        "yield_active_mean_speed_mps": statistics.fmean(active_speeds) if active_speeds else None,
        "yield_active_min_speed_mps": min(active_speeds) if active_speeds else None,
        "yield_active_max_speed_mps": max(active_speeds) if active_speeds else None,
        "yield_entry_observed": entry is not None,
        "stop_window_status": stop_window_status,
        "stop_window_censored_missing_release": (
            entry is not None and release is None
        ),
        "sustained_stop_observed": stop is not None,
        "path_release_observed": release is not None,
        "target_nominal_clear_observed": nominal_clear is not None,
        "target_buffered_clear_observed": buffered_clear is not None,
        "sustained_resume_observed": resume is not None,
        "stop_precedes_release": stop is not None and release is not None and stop <= release,
    }


def analyze_rollout(
    debug_path: Path,
    *,
    fps: float,
    stop_speed_mps: float,
    resume_speed_mps: float,
    consecutive_steps: int,
) -> dict[str, Any]:
    """Compatibility wrapper for one-off callers; formal mode parses once."""

    return analyze_rollout_rows(
        read_jsonl(debug_path),
        fps=fps,
        stop_speed_mps=stop_speed_mps,
        resume_speed_mps=resume_speed_mps,
        consecutive_steps=consecutive_steps,
        source=str(debug_path),
    )


def formal_metadata(debug_path: Path, results_root: Path) -> dict[str, Any] | None:
    relative = debug_path.relative_to(results_root)
    if any(part.startswith("_") for part in relative.parts[:-1]):
        return None
    if len(relative.parts) < 3:
        return None
    match = FORMAL_CELL_RE.match(relative.parts[0])
    if not match:
        return None
    scenario_name = debug_path.parent.name
    init_match = SCENARIO_INIT_RE.search(scenario_name)
    if not init_match:
        raise ValueError(f"Cannot parse ego-init ID from {scenario_name!r}")
    return {
        "cell_id": relative.parts[0],
        "predictor": match.group("predictor"),
        "risk_policy": match.group("risk"),
        "target_style": match.group("style"),
        "ego_init_id": int(init_match.group("init")),
        "scenario": scenario_name,
        "debug_relative_path": relative.as_posix(),
    }


def expected_debug_hashes(matrix_audit: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for evaluation in matrix_audit.get("evaluations", []):
        cell_id = str(evaluation.get("cell_id"))
        for rollout in evaluation.get("rollouts", []):
            scenario = str(rollout.get("scenario"))
            digest = str((rollout.get("artifacts") or {}).get("debug_sha256") or "")
            if not digest:
                raise ValueError(f"Missing debug digest in matrix audit for {cell_id}/{scenario}")
            result[(cell_id, scenario)] = digest
    return result


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def aggregate(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    numeric_fields = (
        "designed_stop_clearance_m",
        "first_stop_distance_to_conflict_m",
        "first_stop_distance_to_designed_stop_m",
        "cautious_approach_progress_m",
        "cautious_approach_duration_s",
        "pre_clearance_stopped_duration_s",
        "nominal_clear_to_release_latency_s",
        "buffered_clear_to_resume_latency_s",
        "release_to_resume_latency_s",
        "yield_active_mean_speed_mps",
    )
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["predictor"]), str(row["risk_policy"]), str(row["target_style"]))].append(row)
    summaries: list[dict[str, Any]] = []
    for (predictor, policy, style), group in sorted(groups.items()):
        summary: dict[str, Any] = {
            "cell_id": f"{predictor}_{policy}_{style}",
            "predictor": predictor,
            "risk_policy": policy,
            "target_style": style,
            "independent_init_groups": len(group),
            "complete_event_chain_rollouts": sum(
                int(bool(row.get("yield_entry_observed")))
                and int(bool(row.get("sustained_stop_observed")))
                and int(bool(row.get("target_nominal_clear_observed")))
                and int(bool(row.get("target_buffered_clear_observed")))
                and int(bool(row.get("path_release_observed")))
                and int(bool(row.get("sustained_resume_observed")))
                and int(bool(row.get("stop_precedes_release")))
                for row in group
            ),
        }
        for field in numeric_fields:
            values = [finite_number(row.get(field)) for row in group]
            clean = [float(value) for value in values if value is not None]
            summary[f"{field}__mean"] = statistics.fmean(clean) if clean else None
            summary[f"{field}__median"] = statistics.median(clean) if clean else None
            summary[f"{field}__min"] = min(clean) if clean else None
            summary[f"{field}__max"] = max(clean) if clean else None
            summary[f"{field}__observed"] = len(clean)
        summaries.append(summary)
    return summaries


def aggregate_policy_cluster_macro(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Pool predictor/style conditions within init, then average five init units."""

    numeric_fields = (
        "designed_stop_clearance_m",
        "first_stop_distance_to_conflict_m",
        "first_stop_distance_to_designed_stop_m",
        "cautious_approach_progress_m",
        "pre_clearance_stopped_duration_s",
        "nominal_clear_to_release_latency_s",
        "buffered_clear_to_resume_latency_s",
        "release_to_resume_latency_s",
    )
    by_policy_init: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_policy_init[(str(row["risk_policy"]), int(row["ego_init_id"]))].append(row)
    result: list[dict[str, Any]] = []
    for policy in ("adaptive", "fixed_aggressive", "fixed_medium", "fixed_conservative"):
        policy_rows = [row for row in rows if row["risk_policy"] == policy]
        summary: dict[str, Any] = {
            "risk_policy": policy,
            "independent_init_groups": len({int(row["ego_init_id"]) for row in policy_rows}),
            "conditions_per_init": 4,
            "rollouts": len(policy_rows),
            "complete_event_chain_rollouts": sum(
                bool(row["yield_entry_observed"])
                and bool(row["sustained_stop_observed"])
                and bool(row["target_nominal_clear_observed"])
                and bool(row["target_buffered_clear_observed"])
                and bool(row["path_release_observed"])
                and bool(row["sustained_resume_observed"])
                and bool(row["stop_precedes_release"])
                for row in policy_rows
            ),
        }
        for field in numeric_fields:
            cluster_values: list[float] = []
            complete_clusters = 0
            for init_id in sorted({int(row["ego_init_id"]) for row in policy_rows}):
                conditions = by_policy_init[(policy, init_id)]
                values = [finite_number(row.get(field)) for row in conditions]
                clean = [float(value) for value in values if value is not None]
                # Keep the four B0/B1 x assertive/reactive nuisance conditions
                # balanced.  A partially observed init remains visible through
                # the completeness counts and rollout table, but cannot be
                # silently reweighted into a policy mean.
                if len(clean) == 4:
                    cluster_values.append(statistics.fmean(clean))
                    complete_clusters += 1
            summary[f"{field}__cluster_macro_mean"] = (
                statistics.fmean(cluster_values) if cluster_values else None
            )
            summary[f"{field}__clusters_observed"] = len(cluster_values)
            summary[f"{field}__clusters_complete"] = complete_clusters
        result.append(summary)
    return result


SENSITIVITY_STOP_SPEEDS_MPS = (0.10, 0.15, 0.20)
SENSITIVITY_RESUME_SPEEDS_MPS = (0.5, 0.8, 1.0)
SENSITIVITY_CONSECUTIVE_STEPS = (2, 3, 5)
SENSITIVITY_EVENT_FIELDS = (
    "yield_entry_observed",
    "sustained_stop_observed",
    "target_nominal_clear_observed",
    "target_buffered_clear_observed",
    "path_release_observed",
    "sustained_resume_observed",
    "stop_precedes_release",
)
SENSITIVITY_METRIC_FIELDS = (
    "first_stop_distance_to_conflict_m",
    "first_stop_distance_to_designed_stop_m",
    "cautious_approach_progress_m",
    "pre_clearance_stopped_duration_s",
    "nominal_clear_to_release_latency_s",
    "buffered_clear_to_resume_latency_s",
    "release_to_resume_latency_s",
)


def aggregate_threshold_sensitivity(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Cluster-balanced sensitivity summaries; debug steps are never samples.

    Each policy/init value first averages its four B0/B1 x style nuisance
    conditions, but only when all four values exist.  Policy means then average
    the independent ego-init clusters.  Coverage is reported at both rollout
    and complete-cluster levels so missing events cannot silently reweight a
    threshold definition.
    """

    grouped: dict[tuple[float, float, int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                float(row["stop_speed_mps"]),
                float(row["resume_speed_mps"]),
                int(row["consecutive_steps"]),
                str(row["risk_policy"]),
            )
        ].append(row)

    output: list[dict[str, Any]] = []
    for (stop_threshold, resume_threshold, sustained_steps, policy), group in sorted(
        grouped.items()
    ):
        init_ids = sorted({int(row["ego_init_id"]) for row in group})
        by_init = {
            init_id: [row for row in group if int(row["ego_init_id"]) == init_id]
            for init_id in init_ids
        }
        summary: dict[str, Any] = {
            "stop_speed_mps": stop_threshold,
            "resume_speed_mps": resume_threshold,
            "consecutive_steps": sustained_steps,
            "risk_policy": policy,
            "rollouts": len(group),
            "independent_init_groups": len(init_ids),
            "conditions_per_init": 4,
            "independent_unit": "ego_initialisation_group",
            "step_rows_are_not_independent_samples": True,
        }
        complete_rollouts = [
            all(bool(row.get(field)) for field in SENSITIVITY_EVENT_FIELDS)
            for row in group
        ]
        summary["complete_event_chain_rollouts"] = sum(complete_rollouts)
        summary["complete_event_chain_clusters"] = sum(
            len(by_init[init_id]) == 4
            and all(
                all(bool(row.get(field)) for field in SENSITIVITY_EVENT_FIELDS)
                for row in by_init[init_id]
            )
            for init_id in init_ids
        )
        for event in SENSITIVITY_EVENT_FIELDS:
            summary[f"{event}__rollouts"] = sum(bool(row.get(event)) for row in group)
            summary[f"{event}__complete_clusters"] = sum(
                len(by_init[init_id]) == 4
                and all(bool(row.get(event)) for row in by_init[init_id])
                for init_id in init_ids
            )
        for metric in SENSITIVITY_METRIC_FIELDS:
            cluster_values: list[float] = []
            for init_id in init_ids:
                condition_rows = by_init[init_id]
                values = [finite_number(row.get(metric)) for row in condition_rows]
                clean = [float(value) for value in values if value is not None]
                if len(condition_rows) == len(clean) == 4:
                    cluster_values.append(statistics.fmean(clean))
            summary[f"{metric}__cluster_macro_mean"] = (
                statistics.fmean(cluster_values) if cluster_values else None
            )
            summary[f"{metric}__complete_clusters"] = len(cluster_values)
        output.append(summary)
    return output


def exact_sign_flip_p(values: Sequence[float]) -> float | None:
    """Two-sided sign-flip sensitivity value under cluster-effect symmetry."""

    clean = [float(value) for value in values if math.isfinite(float(value))]
    if not clean:
        return None
    observed = abs(statistics.fmean(clean))
    extreme = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(clean)):
        candidate = abs(
            statistics.fmean(sign * value for sign, value in zip(signs, clean))
        )
        extreme += int(candidate >= observed - 1.0e-15)
    return extreme / (2 ** len(clean))


def paired_policy_contrasts(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Compare adaptive with each fixed policy after within-init nuisance averaging."""

    numeric_fields = (
        "first_stop_distance_to_conflict_m",
        "first_stop_distance_to_designed_stop_m",
        "cautious_approach_progress_m",
        "pre_clearance_stopped_duration_s",
        "nominal_clear_to_release_latency_s",
        "buffered_clear_to_resume_latency_s",
        "release_to_resume_latency_s",
    )
    by_policy_init: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    init_ids = sorted({int(row["ego_init_id"]) for row in rows})
    for row in rows:
        by_policy_init[(str(row["risk_policy"]), int(row["ego_init_id"]))].append(row)

    output: list[dict[str, Any]] = []
    for fixed in ("fixed_aggressive", "fixed_medium", "fixed_conservative"):
        for field in numeric_fields:
            effects: list[float] = []
            per_init: dict[str, float | None] = {}
            for init_id in init_ids:
                values: dict[str, float | None] = {}
                for policy in ("adaptive", fixed):
                    conditions = by_policy_init[(policy, init_id)]
                    observed = [finite_number(row.get(field)) for row in conditions]
                    clean = [float(value) for value in observed if value is not None]
                    # All B0/B1 x assertive/reactive nuisance conditions must be
                    # present; incomplete clusters are reported, never partially
                    # reweighted into the paired contrast.
                    values[policy] = statistics.fmean(clean) if len(clean) == 4 else None
                effect = (
                    float(values["adaptive"]) - float(values[fixed])
                    if values["adaptive"] is not None and values[fixed] is not None
                    else None
                )
                per_init[str(init_id)] = effect
                if effect is not None:
                    effects.append(effect)
            output.append(
                {
                    "contrast": f"adaptive_minus_{fixed}",
                    "metric": field,
                    "independent_init_groups": len(effects),
                    "expected_init_groups": len(init_ids),
                    "cluster_mean_effect": statistics.fmean(effects) if effects else None,
                    "cluster_median_effect": statistics.median(effects) if effects else None,
                    "minimum_effect": min(effects) if effects else None,
                    "maximum_effect": max(effects) if effects else None,
                    "negative_groups": sum(value < 0 for value in effects),
                    "zero_groups": sum(value == 0 for value in effects),
                    "positive_groups": sum(value > 0 for value in effects),
                    "two_sided_exact_sign_flip_p_descriptive": exact_sign_flip_p(effects),
                    "per_init_effects_json": json.dumps(
                        per_init, sort_keys=True, separators=(",", ":")
                    ),
                    "analysis_role": "post_hoc_paired_mechanism_contrast",
                }
            )
    return output


def latex_number(value: object, digits: int = 3) -> str:
    number = finite_number(value)
    return f"{number:.{digits}f}" if number is not None else "--"


def policy_label(policy: str) -> str:
    return {
        "adaptive": "Adaptive",
        "fixed_aggressive": "Fixed aggressive",
        "fixed_medium": "Fixed medium",
        "fixed_conservative": "Fixed conservative",
    }[policy]


def cluster_macro_with_coverage(
    row: Mapping[str, Any], field: str, *, digits: int = 3
) -> str:
    value = latex_number(row.get(f"{field}__cluster_macro_mean"), digits)
    observed = int(row.get(f"{field}__clusters_observed") or 0)
    expected = int(row.get("independent_init_groups") or 0)
    return f"{value} ({observed}/{expected})"


def write_latex_tables(output_dir: Path, rows: Sequence[Mapping[str, Any]]) -> tuple[Path, Path]:
    approach_path = output_dir / "behaviour_approach_stop.tex"
    release_path = output_dir / "behaviour_release.tex"
    approach_lines = [
        r"\begin{table}[t]",
        r"  \centering\small",
        r"  \caption{Post-hoc corrected-R3 approach and stopping audit. Stop--conflict is the signed distance $s_{\mathrm{conflict}}-s_{\mathrm{ego}}$ along the frozen ego route from the ego actor/reference point, not bumper clearance; positive values are upstream of the conflict point. Designed clearance is $s_{\mathrm{conflict}}-s_{\mathrm{stop}}$. Signed stop-line error is $s_{\mathrm{stop}}-s_{\mathrm{ego}}$: positive means the actor/reference point stopped upstream (short) of the configured stop point and negative means it passed that point. A stop is searched only in the half-open yield-entry--to--path-release episode; a missing release censors the stop window, so later route/goal stops cannot fill it. Values first average the four predictor--style conditions within a complete ego-init group and then average complete groups; each entry reports mean (complete init groups/5), and every missing event remains in the machine-readable tables.}",
        r"  \label{tab:supervisor-behaviour-approach}",
        r"  \begin{tabular}{@{}lrrrr@{}}",
        r"    \toprule",
        r"    Policy & Approach progress (m; $n/5$) & Stop--conflict (m; $n/5$) & Designed clearance (m; $n/5$) & Stop-line error (m; $n/5$) \\",
        r"    \midrule",
    ]
    release_lines = [
        r"\begin{table}[t]",
        r"  \centering\small",
        r"  \caption{Post-hoc corrected-R3 waiting and release audit. Stop--release is elapsed time from the first sustained give-way stop to path-release evidence; it includes necessary waiting and is not automatically avoidable delay. Nominal--release measures controller hold after nominal conflict clearance; buffered--resume uses the stricter footprint-buffered clearance. Values are condition-balanced means with complete init groups/5 shown in every entry; missing events are not imputed.}",
        r"  \label{tab:supervisor-behaviour-release}",
        r"  \begin{tabular}{@{}lrrrr@{}}",
        r"    \toprule",
        r"    Policy & Stop--release (s; $n/5$) & Nominal--release (s; $n/5$) & Release--resume (s; $n/5$) & Buffered--resume (s; $n/5$) \\",
        r"    \midrule",
    ]
    for row in rows:
        label = policy_label(str(row["risk_policy"]))
        approach_lines.append(
            "    " + label + " & "
            + cluster_macro_with_coverage(row, "cautious_approach_progress_m") + " & "
            + cluster_macro_with_coverage(row, "first_stop_distance_to_conflict_m") + " & "
            + cluster_macro_with_coverage(row, "designed_stop_clearance_m") + " & "
            + cluster_macro_with_coverage(row, "first_stop_distance_to_designed_stop_m")
            + r" \\"
        )
        release_lines.append(
            "    " + label + " & "
            + cluster_macro_with_coverage(row, "pre_clearance_stopped_duration_s") + " & "
            + cluster_macro_with_coverage(row, "nominal_clear_to_release_latency_s") + " & "
            + cluster_macro_with_coverage(row, "release_to_resume_latency_s") + " & "
            + cluster_macro_with_coverage(row, "buffered_clear_to_resume_latency_s")
            + r" \\"
        )
    approach_lines.extend([r"    \bottomrule", r"  \end{tabular}", r"\end{table}"])
    release_lines.extend([r"    \bottomrule", r"  \end{tabular}", r"\end{table}"])
    approach_path.write_text("\n".join(approach_lines) + "\n", encoding="utf-8")
    release_path.write_text("\n".join(release_lines) + "\n", encoding="utf-8")
    return approach_path, release_path


def write_policy_contrast_latex(
    output_dir: Path, contrasts: Sequence[Mapping[str, Any]]
) -> Path:
    """Render all post-hoc adaptive-minus-fixed mechanism contrasts."""

    path = output_dir / "behaviour_policy_paired_contrasts.tex"
    metric_labels = {
        "first_stop_distance_to_conflict_m": "Stop--conflict (m)",
        "first_stop_distance_to_designed_stop_m": "Stop-line error (m)",
        "cautious_approach_progress_m": "Approach progress (m)",
        "pre_clearance_stopped_duration_s": "Stop--release (s)",
        "nominal_clear_to_release_latency_s": "Nominal-clear--release (s)",
        "buffered_clear_to_resume_latency_s": "Buffered-clear--resume (s)",
        "release_to_resume_latency_s": "Release--resume (s)",
    }
    comparator_labels = {
        "adaptive_minus_fixed_aggressive": "Adaptive $-$ fixed aggressive",
        "adaptive_minus_fixed_medium": "Adaptive $-$ fixed medium",
        "adaptive_minus_fixed_conservative": "Adaptive $-$ fixed conservative",
    }
    lines = [
        r"\begin{table*}[t]",
        r"\centering\scriptsize",
        r"\caption{Post-hoc adaptive-minus-fixed behavioural contrasts from corrected R3. Stop--conflict is $s_{\mathrm{conflict}}-s_{\mathrm{ego}}$ along the frozen route from the actor/reference point, not bumper clearance. Designed stop-line error is $s_{\mathrm{stop}}-s_{\mathrm{ego}}$, positive upstream and negative after passing the configured stop point; it is not converted into an unsigned performance score. Each effect first balances the four predictor--style conditions within an ego-init group. $n/5$ is the number of complete paired init groups; missing mechanism events are censored rather than imputed. The final value is an exact two-sided sign-flip sensitivity under a symmetric paired-cluster-effect assumption, not treatment-randomisation inference.}",
        r"\label{tab:supervisor-behaviour-paired-risk}",
        r"\begin{tabular}{llrrrrr}",
        r"\toprule",
        r"Contrast & Metric & $n/5$ & Mean & Range & $-/0/+$ groups & Sign-flip sensitivity \\",
        r"\midrule",
    ]
    for row in contrasts:
        mean = latex_number(row.get("cluster_mean_effect"))
        minimum = latex_number(row.get("minimum_effect"))
        maximum = latex_number(row.get("maximum_effect"))
        p_value = latex_number(
            row.get("two_sided_exact_sign_flip_p_descriptive"), digits=4
        )
        lines.append(
            "%s & %s & %d/5 & %s & [%s, %s] & %d/%d/%d & %s \\\\" % (
                comparator_labels[str(row["contrast"])],
                metric_labels[str(row["metric"])],
                int(row["independent_init_groups"]),
                mean,
                minimum,
                maximum,
                int(row["negative_groups"]),
                int(row["zero_groups"]),
                int(row["positive_groups"]),
                p_value,
            )
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table*}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def analyze_formal(
    results_root: Path,
    matrix_audit_path: Path,
    output_dir: Path,
    *,
    fps: float,
    stop_speed_mps: float,
    resume_speed_mps: float,
    consecutive_steps: int,
    expected_rollouts: int,
) -> dict[str, Any]:
    matrix_audit = read_json(matrix_audit_path)
    if matrix_audit.get("integrity_status") not in (None, "pass"):
        raise ValueError("The source R3 matrix audit did not pass integrity")
    audited_fps: set[float] = set()
    for evaluation in matrix_audit.get("evaluations", []):
        for rollout in evaluation.get("rollouts", []):
            observed_fps = finite_number((rollout.get("control_variables") or {}).get("carla_fps"))
            if observed_fps is not None:
                audited_fps.add(observed_fps)
    if audited_fps and audited_fps != {float(fps)}:
        raise ValueError(f"CARLA FPS mismatch: matrix audit has {sorted(audited_fps)}, requested {fps}")
    expected_hashes = expected_debug_hashes(matrix_audit)
    rows: list[dict[str, Any]] = []
    sensitivity_rollout_rows: list[dict[str, Any]] = []
    duplicate_keys: list[str] = []
    seen: set[tuple[str, int]] = set()
    for debug_path in sorted(results_root.rglob("smpc_debug_steps.jsonl")):
        metadata = formal_metadata(debug_path, results_root)
        if metadata is None:
            continue
        key = (str(metadata["cell_id"]), int(metadata["ego_init_id"]))
        if key in seen:
            duplicate_keys.append(f"{key[0]}/{key[1]}")
            continue
        seen.add(key)
        expected_digest = expected_hashes.get((str(metadata["cell_id"]), str(metadata["scenario"])))
        observed_digest = sha256_file(debug_path)
        if expected_digest is None:
            raise ValueError(f"Promoted debug file is absent from matrix audit: {debug_path}")
        if observed_digest != expected_digest:
            raise ValueError(
                f"Debug hash mismatch for {metadata['cell_id']}/{metadata['scenario']}: "
                f"{observed_digest} != {expected_digest}"
            )
        # Parse each potentially large JSONL exactly once.  The registered
        # estimate and all 27 threshold definitions reuse the same in-memory
        # step sequence; this is a definition sensitivity analysis, never
        # 27 new experiments or step-level pseudoreplication.
        debug_rows = read_jsonl(debug_path)
        outcome = analyze_rollout_rows(
            debug_rows,
            fps=fps,
            stop_speed_mps=stop_speed_mps,
            resume_speed_mps=resume_speed_mps,
            consecutive_steps=consecutive_steps,
            source=str(debug_path),
        )
        rows.append({**metadata, "debug_sha256": observed_digest, **outcome})
        for sensitivity_stop, sensitivity_resume, sensitivity_steps in itertools.product(
            SENSITIVITY_STOP_SPEEDS_MPS,
            SENSITIVITY_RESUME_SPEEDS_MPS,
            SENSITIVITY_CONSECUTIVE_STEPS,
        ):
            sensitivity = analyze_rollout_rows(
                debug_rows,
                fps=fps,
                stop_speed_mps=sensitivity_stop,
                resume_speed_mps=sensitivity_resume,
                consecutive_steps=sensitivity_steps,
                source=str(debug_path),
            )
            sensitivity_rollout_rows.append(
                {
                    **metadata,
                    "debug_sha256": observed_digest,
                    "stop_speed_mps": sensitivity_stop,
                    "resume_speed_mps": sensitivity_resume,
                    "consecutive_steps": sensitivity_steps,
                    **sensitivity,
                }
            )

    if duplicate_keys:
        raise ValueError(f"Duplicate promoted rollout keys: {duplicate_keys}")
    if len(rows) != expected_rollouts:
        raise ValueError(f"Expected {expected_rollouts} formal rollouts, observed {len(rows)}")
    if len(expected_hashes) != expected_rollouts:
        raise ValueError(f"Matrix audit contains {len(expected_hashes)} rollouts, expected {expected_rollouts}")
    if set(seen) != {(cell, int(SCENARIO_INIT_RE.search(scenario).group('init'))) for cell, scenario in expected_hashes}:
        raise ValueError("Promoted rollout keys do not exactly match the matrix audit")

    summaries = aggregate(rows)
    if len(summaries) != 16 or any(row["independent_init_groups"] != 5 for row in summaries):
        raise ValueError("Formal design must contain 16 cells with five independent init groups each")
    complete_event_chains = sum(
        bool(row["yield_entry_observed"])
        and bool(row["sustained_stop_observed"])
        and bool(row["target_nominal_clear_observed"])
        and bool(row["target_buffered_clear_observed"])
        and bool(row["path_release_observed"])
        and bool(row["sustained_resume_observed"])
        and bool(row["stop_precedes_release"])
        for row in rows
    )

    rollout_path = output_dir / "behaviour_rollouts.csv"
    summary_path = output_dir / "behaviour_cell_summary.csv"
    policy_summaries = aggregate_policy_cluster_macro(rows)
    policy_summary_path = output_dir / "behaviour_policy_cluster_macro.csv"
    policy_contrasts = paired_policy_contrasts(rows)
    policy_contrasts_path = output_dir / "behaviour_policy_paired_contrasts.csv"
    sensitivity_summaries = aggregate_threshold_sensitivity(sensitivity_rollout_rows)
    expected_sensitivity_rows = (
        len(SENSITIVITY_STOP_SPEEDS_MPS)
        * len(SENSITIVITY_RESUME_SPEEDS_MPS)
        * len(SENSITIVITY_CONSECUTIVE_STEPS)
        * 4
    )
    if len(sensitivity_summaries) != expected_sensitivity_rows:
        raise ValueError(
            "Threshold sensitivity must contain 27 definitions x four risk policies; "
            f"observed {len(sensitivity_summaries)} rows"
        )
    if any(
        row["rollouts"] != 20 or row["independent_init_groups"] != 5
        for row in sensitivity_summaries
    ):
        raise ValueError("Threshold sensitivity lost its 20-rollout / five-cluster policy design")
    sensitivity_path = output_dir / "behaviour_threshold_sensitivity.csv"
    write_csv(rollout_path, rows, list(rows[0]))
    write_csv(summary_path, summaries, list(summaries[0]))
    write_csv(policy_summary_path, policy_summaries, list(policy_summaries[0]))
    write_csv(policy_contrasts_path, policy_contrasts, list(policy_contrasts[0]))
    write_csv(sensitivity_path, sensitivity_summaries, list(sensitivity_summaries[0]))
    approach_tex_path, release_tex_path = write_latex_tables(output_dir, policy_summaries)
    paired_contrasts_tex_path = write_policy_contrast_latex(
        output_dir, policy_contrasts
    )
    contract = {
        "analysis_role": "post_hoc_supervisor_feedback_mechanism_audit_not_primary_hypothesis_test",
        "fps": fps,
        "independent_unit": "ego_initialisation_group",
        "step_rows_are_not_independent_samples": True,
        "baseline_definition": {
            "stop_speed_mps": stop_speed_mps,
            "resume_speed_mps": resume_speed_mps,
            "minimum_consecutive_steps": consecutive_steps,
        },
        "stop_definition": {
            "speed_at_or_below_mps": stop_speed_mps,
            "minimum_consecutive_steps": consecutive_steps,
        },
        "resume_definition": {
            "speed_at_or_above_mps": resume_speed_mps,
            "minimum_consecutive_steps": consecutive_steps,
        },
        "threshold_sensitivity_grid": {
            "stop_speed_mps": list(SENSITIVITY_STOP_SPEEDS_MPS),
            "resume_speed_mps": list(SENSITIVITY_RESUME_SPEEDS_MPS),
            "minimum_consecutive_steps": list(SENSITIVITY_CONSECUTIVE_STEPS),
            "definitions": 27,
            "rows": expected_sensitivity_rows,
            "aggregation": (
                "four predictor-style conditions averaged only when complete within each "
                "ego-init group, followed by an equal-weight mean over five init groups"
            ),
        },
        "release_precedence": [
            "raw_reduced_clear_path_release",
            "reduced_clear_path_release",
            "recovery.clear_path_release_start",
            "phase_released_recovery",
        ],
        "censoring": {
            "missing_yield_entry": (
                "stop metrics are not applicable because no registered give-way episode began"
            ),
            "yield_entry_without_release": (
                "the stop-search window has no observable endpoint, so stop and "
                "approach-to-stop metrics are censored rather than searching later route/goal stops"
            ),
            "missing_events_are_not_imputed": True,
        },
        "interpretation": {
            "first_stop_distance_to_conflict_m": (
                "signed frozen-route coordinate difference conflict_s - ego_route_s "
                "from the ego actor/reference point, not bumper clearance; positive is upstream"
            ),
            "designed_stop_clearance_m": (
                "frozen-route coordinate difference conflict_s - stop_s"
            ),
            "first_stop_distance_to_designed_stop_m": (
                "signed frozen-route stop-line error stop_s - ego_route_s; positive "
                "means upstream/short of the configured stop point and negative means passed"
            ),
            "cautious_approach_progress_m": "route progress after first active yield detection and before first sustained stop",
            "pre_clearance_stopped_duration_s": "time from first sustained stop to path-release evidence; not avoidable delay",
            "nominal_clear_to_release_latency_s": "controller hold after the target passes the nominal conflict radius and before release",
            "buffered_clear_to_resume_latency_s": "speed recovery relative to the stricter conflict-radius-plus-clearance signal",
            "release_to_resume_latency_s": "time from path-release evidence to sustained speed recovery",
        },
    }
    contract_path = output_dir / "behaviour_analysis_contract.json"
    atomic_write_json(contract_path, contract)
    analysis_script = Path(__file__).resolve()
    offline_runner = analysis_script.parent / "run_supervisor_feedback_r3_offline_audits.sh"
    source_sha256 = {
        "core/scripts/models/analyze_supervisor_feedback_behaviour.py": sha256_file(
            analysis_script
        ),
        "core/scripts/models/run_supervisor_feedback_r3_offline_audits.sh": sha256_file(
            offline_runner
        ),
        "matrix_audit": sha256_file(matrix_audit_path),
    }
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass" if complete_event_chains == expected_rollouts else "pass_with_missing_mechanism_events",
        "formal_integrity_status": "pass",
        "results_root": str(results_root.resolve()),
        "matrix_audit": str(matrix_audit_path.resolve()),
        "matrix_audit_sha256": sha256_file(matrix_audit_path),
        "observed_rollouts": len(rows),
        "expected_rollouts": expected_rollouts,
        "independent_init_groups": sorted({int(row["ego_init_id"]) for row in rows}),
        "formal_cells": len(summaries),
        "complete_event_chain_rollouts": complete_event_chains,
        "missing_event_chain_rollouts": expected_rollouts - complete_event_chains,
        "contract_sha256": sha256_file(contract_path),
        "source_sha256": source_sha256,
        "artifacts": {
            contract_path.name: {"rows": 1, "sha256": sha256_file(contract_path)},
            rollout_path.name: {"rows": len(rows), "sha256": sha256_file(rollout_path)},
            summary_path.name: {"rows": len(summaries), "sha256": sha256_file(summary_path)},
            policy_summary_path.name: {"rows": len(policy_summaries), "sha256": sha256_file(policy_summary_path)},
            policy_contrasts_path.name: {"rows": len(policy_contrasts), "sha256": sha256_file(policy_contrasts_path)},
            sensitivity_path.name: {
                "rows": len(sensitivity_summaries),
                "sha256": sha256_file(sensitivity_path),
            },
            approach_tex_path.name: {"rows": len(policy_summaries), "sha256": sha256_file(approach_tex_path)},
            release_tex_path.name: {"rows": len(policy_summaries), "sha256": sha256_file(release_tex_path)},
            paired_contrasts_tex_path.name: {
                "rows": len(policy_contrasts),
                "sha256": sha256_file(paired_contrasts_tex_path),
            },
        },
    }
    summary_json_path = output_dir / "behaviour_analysis_summary.json"
    atomic_write_json(summary_json_path, summary_payload)
    receipt = {
        "schema_version": "supervisor_feedback_behaviour_complete_v1",
        "status": summary_payload["status"],
        "summary": summary_json_path.name,
        "summary_sha256": sha256_file(summary_json_path),
        "artifacts": {
            name: value["sha256"] for name, value in summary_payload["artifacts"].items()
        },
        "source_sha256": source_sha256,
        "contract": contract_path.name,
        "contract_sha256": sha256_file(contract_path),
        "limitations": [
            "post_hoc mechanism audit",
            "single Town05 junction",
            "five independent initialisation groups per cell",
            "no naturalistic human-driving comparator",
        ],
    }
    atomic_write_json(output_dir / "SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json", receipt)
    return summary_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--matrix-audit", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--stop-speed-mps", type=float, default=0.15)
    parser.add_argument("--resume-speed-mps", type=float, default=0.8)
    parser.add_argument("--consecutive-steps", type=int, default=3)
    parser.add_argument("--expected-rollouts", type=int, default=80)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.fps <= 0 or args.stop_speed_mps < 0 or args.resume_speed_mps <= args.stop_speed_mps:
        raise SystemExit("Invalid fps or speed thresholds")
    payload = analyze_formal(
        args.results_root.resolve(),
        args.matrix_audit.resolve(),
        args.output_dir.resolve(),
        fps=args.fps,
        stop_speed_mps=args.stop_speed_mps,
        resume_speed_mps=args.resume_speed_mps,
        consecutive_steps=args.consecutive_steps,
        expected_rollouts=args.expected_rollouts,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
