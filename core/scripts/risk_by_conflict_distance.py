#!/usr/bin/env python3
"""Summarise adaptive-risk behaviour by ego conflict-zone distance.

This is a behaviour-preserving postprocess script. It reads existing CARLA
rollout debug logs and writes diagnostics that separate optimiser-level
adaptive risk from rule-aware yield supervisor intervention.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SMPC_POLICIES = ("smpc_var_risk", "smpc_fixed_risk")

STEP_COLUMNS = [
    "scenario_dir",
    "scenario",
    "initial",
    "policy",
    "step",
    "sim_time_s",
    "bucket",
    "ego_distance_to_conflict",
    "target_distance_to_conflict",
    "yield_phase",
    "yield_reason",
    "yield_supervisor_active",
    "hard_stop_required",
    "rolling_caution_active",
    "emergency_brake_active",
    "target_cleared_conflict",
    "clearance_phase",
    "adaptive_risk_enabled",
    "solver_uses_adaptive_risk",
    "solver_risk_mode",
    "risk_phase",
    "risk_tightening",
    "risk_target_prob",
    "diagnostic_risk_tightening",
    "diagnostic_risk_target_prob",
    "raw_tightening_before_floor",
    "preclearance_tight_floor",
    "preclearance_floor_active",
    "preclearance_floor_applied",
    "preclearance_floor_reason",
    "raw_severity_score",
    "effective_severity_score",
    "severity_phase",
    "solver_success",
    "solver_solve_time_s",
    "solver_nominal_accel_before_override",
    "solver_nominal_steer_before_override",
    "final_applied_accel_after_override",
    "final_applied_steer_after_override",
    "accel_override_delta",
    "steer_override_delta",
    "final_control_overridden",
    "supervisor_applied_mode",
    "reference_speed_cap",
    "current_center_distance_to_target",
    "policy_min_footprint_separation",
    "policy_min_center_distance",
    "policy_yield_ok",
]

SUMMARY_COLUMNS = [
    "scenario",
    "initial",
    "policy",
    "bucket",
    "clearance_phase",
    "n_steps",
    "sim_time_start_s",
    "sim_time_end_s",
    "ego_dconf_min",
    "ego_dconf_mean",
    "ego_dconf_max",
    "target_dconf_mean",
    "supervisor_active_frac",
    "hard_stop_override_frac",
    "rolling_caution_frac",
    "emergency_brake_frac",
    "final_control_overridden_frac",
    "solver_failure_frac",
    "solver_uses_adaptive_risk_frac",
    "solver_risk_mode",
    "risk_tightening_mean",
    "risk_tightening_min",
    "risk_tightening_max",
    "risk_target_prob_mean",
    "diagnostic_risk_tightening_mean",
    "raw_tightening_before_floor_mean",
    "preclearance_floor_active_frac",
    "preclearance_floor_applied_frac",
    "effective_severity_mean",
    "raw_severity_mean",
    "nominal_accel_mean",
    "final_accel_mean",
    "accel_override_delta_mean",
    "current_center_distance_min",
    "policy_min_footprint_separation",
    "policy_min_center_distance",
    "policy_yield_ok",
]

COMPARISON_COLUMNS = [
    "scenario",
    "initial",
    "bucket",
    "clearance_phase",
    "var_steps",
    "fixed_steps",
    "var_minus_fixed_risk_tightening_mean",
    "var_minus_fixed_diagnostic_risk_tightening_mean",
    "var_minus_fixed_floor_applied_frac",
    "var_minus_fixed_nominal_accel_mean",
    "var_minus_fixed_final_accel_mean",
    "var_minus_fixed_solver_failure_frac",
    "var_minus_fixed_supervisor_override_frac",
    "var_minus_fixed_hard_stop_override_frac",
    "var_minus_fixed_min_footprint_separation",
    "var_risk_tightening_mean",
    "fixed_risk_tightening_mean",
    "var_floor_applied_frac",
    "fixed_floor_applied_frac",
    "var_solver_failure_frac",
    "fixed_solver_failure_frac",
    "var_supervisor_override_frac",
    "fixed_supervisor_override_frac",
    "var_policy_min_footprint_separation",
    "fixed_policy_min_footprint_separation",
]


@dataclass(frozen=True)
class ScenarioIdentity:
    scenario_dir: str
    scenario: str
    initial: int
    policy: str


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        val = float(value)
    except Exception:
        return None
    if not math.isfinite(val):
        return None
    return val


def _as_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _format_float(value: Any, digits: int = 6) -> str:
    val = _as_float(value)
    if val is None:
        return ""
    return f"{val:.{digits}g}"


def _parse_identity(path: str) -> Optional[ScenarioIdentity]:
    name = os.path.basename(path.rstrip(os.sep))
    match = re.match(r"(?P<scenario>.+)_ego_init_(?P<initial>\d+)_(?P<policy>.+)$", name)
    if not match:
        return None
    return ScenarioIdentity(
        scenario_dir=name,
        scenario=match.group("scenario"),
        initial=int(match.group("initial")),
        policy=match.group("policy"),
    )


def _list_smpc_dirs(results_dir: str, policies: Sequence[str]) -> List[Tuple[str, ScenarioIdentity]]:
    policy_set = set(policies)
    out: List[Tuple[str, ScenarioIdentity]] = []
    for entry in sorted(os.listdir(results_dir)):
        path = os.path.join(results_dir, entry)
        if not os.path.isdir(path):
            continue
        ident = _parse_identity(path)
        if ident is None or ident.policy not in policy_set:
            continue
        if os.path.isfile(os.path.join(path, "smpc_debug_steps.jsonl")):
            out.append((path, ident))
    return out


def _load_scenario_steps(path: str) -> Dict[int, Dict[str, Any]]:
    csv_path = os.path.join(path, "scenario_steps.csv")
    if not os.path.isfile(csv_path):
        return {}
    rows: Dict[int, Dict[str, Any]] = {}
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                step = int(float(row.get("step", "")))
            except Exception:
                continue
            rows[step] = row
    return rows


def _load_gate_policy_metrics(results_dir: str) -> Dict[str, Dict[str, Any]]:
    path = os.path.join(results_dir, "postcarla_trajectory_gate.json")
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    metrics: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("evaluations", []):
        policy = item.get("policy")
        if not policy:
            continue
        pair = (item.get("pair_safety") or [{}])[0] or {}
        rule = (item.get("yield_rules") or [{}])[0] or {}
        metric = {
            "solver_failure_frac": item.get("solver_failure_frac"),
            "min_footprint_separation": pair.get("min_footprint_separation_m"),
            "min_center_distance": pair.get("min_center_distance_m"),
            "footprint_collision": pair.get("footprint_collision"),
            "yield_ok": rule.get("target_clears_before_ego_enters"),
        }
        scenario_dir = item.get("scenario_dir")
        if scenario_dir:
            metrics[os.path.basename(str(scenario_dir).rstrip(os.sep))] = metric
        metrics[policy] = metric
    return metrics


def _bucket_for_dconf(dconf: Optional[float]) -> str:
    if dconf is None:
        return "unknown"
    if dconf > 25.0:
        return "far"
    if dconf > 15.0:
        return "approach"
    if dconf > 5.0:
        return "critical"
    return "near"


def _array_head(summary: Any, index: int) -> Optional[float]:
    if isinstance(summary, dict):
        head = summary.get("head")
        if isinstance(head, list) and index < len(head):
            return _as_float(head[index])
    if isinstance(summary, list) and index < len(summary):
        return _as_float(summary[index])
    return None


def _control_pair(value: Any) -> Tuple[Optional[float], Optional[float]]:
    if isinstance(value, list) and len(value) >= 2:
        return _as_float(value[0]), _as_float(value[1])
    if isinstance(value, dict):
        return _array_head(value, 0), _array_head(value, 1)
    return None, None


def _extract_reference_speed_cap(row: Dict[str, Any]) -> Optional[float]:
    status = (((row.get("reference") or {}).get("status") or {}).get("rule_aware_reference") or {})
    return _as_float(status.get("speed_cap"))


def _solver_debug_payload(solver: Dict[str, Any]) -> Dict[str, Any]:
    debug = solver.get("debug") if isinstance(solver, dict) else None
    return debug if isinstance(debug, dict) else {}


def _first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _extract_step_row(
    raw: Dict[str, Any],
    ident: ScenarioIdentity,
    scenario_step: Optional[Dict[str, Any]],
    gate_policy: Dict[str, Any],
) -> Dict[str, Any]:
    step = raw.get("step")
    ystatus = raw.get("yield_stop_supervisor") or raw.get("rule_aware_yield") or {}
    risk_payload = raw.get("risk") or {}
    adaptive = risk_payload.get("adaptive") or {}
    applied = raw.get("applied") or {}
    solver = raw.get("solver") or {}
    solver_debug = _solver_debug_payload(solver)
    vehicle_state = raw.get("vehicle_state") or {}
    relative = raw.get("relative_geometry_tv0") or {}

    ego_dconf = _as_float(ystatus.get("ego_distance_to_conflict"))
    target_dconf = _as_float(ystatus.get("target_distance_to_conflict"))
    bucket = _bucket_for_dconf(ego_dconf)

    nominal_accel, nominal_steer = _control_pair(applied.get("u_control"))
    if nominal_accel is None and isinstance(solver, dict):
        nominal_accel, nominal_steer = _control_pair(solver.get("u_control"))

    final_accel, final_steer = _control_pair(applied.get("u0"))
    y_applied = ystatus.get("applied") or {}
    if y_applied:
        final_accel = _as_float(y_applied.get("a_des"))
        final_steer = _as_float(y_applied.get("df_des"))

    accel_delta = (
        final_accel - nominal_accel
        if final_accel is not None and nominal_accel is not None
        else None
    )
    steer_delta = (
        final_steer - nominal_steer
        if final_steer is not None and nominal_steer is not None
        else None
    )
    overridden = bool(
        ystatus.get("active")
        and (
            (accel_delta is not None and abs(accel_delta) > 1.0e-4)
            or (steer_delta is not None and abs(steer_delta) > 1.0e-4)
        )
    )

    emergency = ((y_applied.get("emergency_brake") or {}).get("active"))
    sim_time = None
    if scenario_step:
        sim_time = _as_float(scenario_step.get("sim_time_s"))

    solver_success = _as_bool(solver.get("optimal"))
    if solver_success is None:
        solver_success = _as_bool(applied.get("is_opt"))
    solver_risk_mode = _first_non_null(
        risk_payload.get("solver_risk_mode"),
        solver.get("solver_risk_mode"),
        solver_debug.get("solver_risk_mode"),
        "unknown",
    )
    solver_current_tight = _first_non_null(
        risk_payload.get("solver_current_tight"),
        solver.get("current_tight"),
        solver_debug.get("current_tight"),
        risk_payload.get("applied_tight"),
        adaptive.get("tightening"),
    )
    solver_current_target_prob = _first_non_null(
        risk_payload.get("solver_current_target_prob"),
        solver.get("current_target_prob"),
        solver_debug.get("current_target_prob"),
        risk_payload.get("applied_target_prob"),
        adaptive.get("target_prob"),
    )
    solver_uses_adaptive = _as_bool(
        _first_non_null(
            risk_payload.get("solver_uses_adaptive_risk"),
            adaptive.get("solver_applied"),
            solver_debug.get("adaptive_risk_allocation", {}).get("solver_applied")
            if isinstance(solver_debug.get("adaptive_risk_allocation"), dict)
            else None,
        )
    )
    if solver_uses_adaptive is None:
        solver_uses_adaptive = bool(str(solver_risk_mode) == "adaptive_variable")

    target_cleared_conflict = bool(ystatus.get("target_cleared_conflict", False))
    clearance_phase = "post_clearance" if target_cleared_conflict else "pre_clearance"

    return {
        "scenario_dir": ident.scenario_dir,
        "scenario": ident.scenario,
        "initial": ident.initial,
        "policy": ident.policy,
        "step": step,
        "sim_time_s": sim_time,
        "bucket": bucket,
        "ego_distance_to_conflict": ego_dconf,
        "target_distance_to_conflict": target_dconf,
        "yield_phase": ystatus.get("phase"),
        "yield_reason": ystatus.get("reason"),
        "yield_supervisor_active": bool(ystatus.get("active", False)),
        "hard_stop_required": bool(ystatus.get("hard_stop_required", False)),
        "rolling_caution_active": bool(
            ystatus.get("active", False)
            and not ystatus.get("hard_stop_required", False)
        ),
        "emergency_brake_active": bool(emergency),
        "target_cleared_conflict": target_cleared_conflict,
        "clearance_phase": clearance_phase,
        "adaptive_risk_enabled": bool(adaptive.get("enabled", False)),
        "solver_uses_adaptive_risk": bool(solver_uses_adaptive),
        "solver_risk_mode": solver_risk_mode,
        "risk_phase": adaptive.get("phase"),
        "risk_tightening": solver_current_tight,
        "risk_target_prob": solver_current_target_prob,
        "diagnostic_risk_tightening": adaptive.get("tightening"),
        "diagnostic_risk_target_prob": adaptive.get("target_prob"),
        "raw_tightening_before_floor": adaptive.get("raw_tightening_before_floor"),
        "preclearance_tight_floor": adaptive.get("preclearance_tight_floor"),
        "preclearance_floor_active": bool(
            solver_uses_adaptive and _as_bool(adaptive.get("preclearance_floor_active"))
        ),
        "preclearance_floor_applied": bool(
            solver_uses_adaptive and _as_bool(adaptive.get("preclearance_floor_applied"))
        ),
        "preclearance_floor_reason": adaptive.get("preclearance_floor_reason"),
        "raw_severity_score": adaptive.get("raw_severity_score"),
        "effective_severity_score": adaptive.get("effective_severity_score"),
        "severity_phase": ystatus.get("severity_phase"),
        "solver_success": solver_success,
        "solver_solve_time_s": solver.get("solve_time", applied.get("solve_time")),
        "solver_nominal_accel_before_override": nominal_accel,
        "solver_nominal_steer_before_override": nominal_steer,
        "final_applied_accel_after_override": final_accel,
        "final_applied_steer_after_override": final_steer,
        "accel_override_delta": accel_delta,
        "steer_override_delta": steer_delta,
        "final_control_overridden": overridden,
        "supervisor_applied_mode": y_applied.get("mode"),
        "reference_speed_cap": _extract_reference_speed_cap(raw),
        "current_center_distance_to_target": relative.get("distance"),
        "policy_min_footprint_separation": gate_policy.get("min_footprint_separation"),
        "policy_min_center_distance": gate_policy.get("min_center_distance"),
        "policy_yield_ok": gate_policy.get("yield_ok"),
    }


def _load_step_rows(path: str, ident: ScenarioIdentity, gate_policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    scenario_steps = _load_scenario_steps(path)
    out: List[Dict[str, Any]] = []
    debug_path = os.path.join(path, "smpc_debug_steps.jsonl")
    with open(debug_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                step_key = int(raw.get("step"))
            except Exception:
                step_key = -1
            out.append(_extract_step_row(raw, ident, scenario_steps.get(step_key), gate_policy))
    return out


def _mean(values: Iterable[Any]) -> Optional[float]:
    vals = [_as_float(v) for v in values]
    vals = [v for v in vals if v is not None]
    return None if not vals else sum(vals) / len(vals)


def _min(values: Iterable[Any]) -> Optional[float]:
    vals = [_as_float(v) for v in values]
    vals = [v for v in vals if v is not None]
    return None if not vals else min(vals)


def _max(values: Iterable[Any]) -> Optional[float]:
    vals = [_as_float(v) for v in values]
    vals = [v for v in vals if v is not None]
    return None if not vals else max(vals)


def _frac(rows: Sequence[Dict[str, Any]], key: str, positive: bool = True) -> Optional[float]:
    vals = [_as_bool(r.get(key)) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    if positive:
        return sum(1 for v in vals if v) / len(vals)
    return sum(1 for v in vals if not v) / len(vals)


def _mode_label(rows: Sequence[Dict[str, Any]], key: str) -> str:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        value = row.get(key)
        if value is None or value == "":
            continue
        counts[str(value)] += 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _diff(var_value: Any, fixed_value: Any) -> Optional[float]:
    var_float = _as_float(var_value)
    fixed_float = _as_float(fixed_value)
    if var_float is None or fixed_float is None:
        return None
    return var_float - fixed_float


def _summarise_rows(step_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for row in step_rows:
        key = (
            row["scenario"],
            row["initial"],
            row["policy"],
            row["bucket"],
            row["clearance_phase"],
        )
        grouped[key].append(row)

    summary: List[Dict[str, Any]] = []
    bucket_order = {"far": 0, "approach": 1, "critical": 2, "near": 3, "unknown": 4}
    clearance_phase_order = {"pre_clearance": 0, "post_clearance": 1}
    for (scenario, initial, policy, bucket, clearance_phase), rows in sorted(
        grouped.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            item[0][2],
            bucket_order.get(item[0][3], 99),
            clearance_phase_order.get(item[0][4], 99),
        ),
    ):
        summary.append(
            {
                "scenario": scenario,
                "initial": initial,
                "policy": policy,
                "bucket": bucket,
                "clearance_phase": clearance_phase,
                "n_steps": len(rows),
                "sim_time_start_s": _min(r.get("sim_time_s") for r in rows),
                "sim_time_end_s": _max(r.get("sim_time_s") for r in rows),
                "ego_dconf_min": _min(r.get("ego_distance_to_conflict") for r in rows),
                "ego_dconf_mean": _mean(r.get("ego_distance_to_conflict") for r in rows),
                "ego_dconf_max": _max(r.get("ego_distance_to_conflict") for r in rows),
                "target_dconf_mean": _mean(r.get("target_distance_to_conflict") for r in rows),
                "supervisor_active_frac": _frac(rows, "yield_supervisor_active"),
                "hard_stop_override_frac": _frac(rows, "hard_stop_required"),
                "rolling_caution_frac": _frac(rows, "rolling_caution_active"),
                "emergency_brake_frac": _frac(rows, "emergency_brake_active"),
                "final_control_overridden_frac": _frac(rows, "final_control_overridden"),
                "solver_failure_frac": _frac(rows, "solver_success", positive=False),
                "solver_uses_adaptive_risk_frac": _frac(rows, "solver_uses_adaptive_risk"),
                "solver_risk_mode": _mode_label(rows, "solver_risk_mode"),
                "risk_tightening_mean": _mean(r.get("risk_tightening") for r in rows),
                "risk_tightening_min": _min(r.get("risk_tightening") for r in rows),
                "risk_tightening_max": _max(r.get("risk_tightening") for r in rows),
                "risk_target_prob_mean": _mean(r.get("risk_target_prob") for r in rows),
                "diagnostic_risk_tightening_mean": _mean(r.get("diagnostic_risk_tightening") for r in rows),
                "raw_tightening_before_floor_mean": _mean(r.get("raw_tightening_before_floor") for r in rows),
                "preclearance_floor_active_frac": _frac(rows, "preclearance_floor_active"),
                "preclearance_floor_applied_frac": _frac(rows, "preclearance_floor_applied"),
                "effective_severity_mean": _mean(r.get("effective_severity_score") for r in rows),
                "raw_severity_mean": _mean(r.get("raw_severity_score") for r in rows),
                "nominal_accel_mean": _mean(r.get("solver_nominal_accel_before_override") for r in rows),
                "final_accel_mean": _mean(r.get("final_applied_accel_after_override") for r in rows),
                "accel_override_delta_mean": _mean(r.get("accel_override_delta") for r in rows),
                "current_center_distance_min": _min(r.get("current_center_distance_to_target") for r in rows),
                "policy_min_footprint_separation": _mean(r.get("policy_min_footprint_separation") for r in rows),
                "policy_min_center_distance": _mean(r.get("policy_min_center_distance") for r in rows),
                "policy_yield_ok": rows[0].get("policy_yield_ok"),
            }
        )
    return summary


def _comparison_rows(summary_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Any, ...], Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for row in summary_rows:
        key = (
            row.get("scenario"),
            row.get("initial"),
            row.get("bucket"),
            row.get("clearance_phase"),
        )
        grouped[key][str(row.get("policy"))] = row

    rows: List[Dict[str, Any]] = []
    bucket_order = {"far": 0, "approach": 1, "critical": 2, "near": 3, "unknown": 4}
    clearance_phase_order = {"pre_clearance": 0, "post_clearance": 1}
    for (scenario, initial, bucket, clearance_phase), policies in sorted(
        grouped.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            bucket_order.get(item[0][2], 99),
            clearance_phase_order.get(item[0][3], 99),
        ),
    ):
        var_row = policies.get("smpc_var_risk")
        fixed_row = policies.get("smpc_fixed_risk")
        if not var_row or not fixed_row:
            continue
        rows.append(
            {
                "scenario": scenario,
                "initial": initial,
                "bucket": bucket,
                "clearance_phase": clearance_phase,
                "var_steps": var_row.get("n_steps"),
                "fixed_steps": fixed_row.get("n_steps"),
                "var_minus_fixed_risk_tightening_mean": _diff(
                    var_row.get("risk_tightening_mean"), fixed_row.get("risk_tightening_mean")
                ),
                "var_minus_fixed_diagnostic_risk_tightening_mean": _diff(
                    var_row.get("diagnostic_risk_tightening_mean"),
                    fixed_row.get("diagnostic_risk_tightening_mean"),
                ),
                "var_minus_fixed_floor_applied_frac": _diff(
                    var_row.get("preclearance_floor_applied_frac"),
                    fixed_row.get("preclearance_floor_applied_frac"),
                ),
                "var_minus_fixed_nominal_accel_mean": _diff(
                    var_row.get("nominal_accel_mean"), fixed_row.get("nominal_accel_mean")
                ),
                "var_minus_fixed_final_accel_mean": _diff(
                    var_row.get("final_accel_mean"), fixed_row.get("final_accel_mean")
                ),
                "var_minus_fixed_solver_failure_frac": _diff(
                    var_row.get("solver_failure_frac"), fixed_row.get("solver_failure_frac")
                ),
                "var_minus_fixed_supervisor_override_frac": _diff(
                    var_row.get("final_control_overridden_frac"),
                    fixed_row.get("final_control_overridden_frac"),
                ),
                "var_minus_fixed_hard_stop_override_frac": _diff(
                    var_row.get("hard_stop_override_frac"), fixed_row.get("hard_stop_override_frac")
                ),
                "var_minus_fixed_min_footprint_separation": _diff(
                    var_row.get("policy_min_footprint_separation"),
                    fixed_row.get("policy_min_footprint_separation"),
                ),
                "var_risk_tightening_mean": var_row.get("risk_tightening_mean"),
                "fixed_risk_tightening_mean": fixed_row.get("risk_tightening_mean"),
                "var_floor_applied_frac": var_row.get("preclearance_floor_applied_frac"),
                "fixed_floor_applied_frac": fixed_row.get("preclearance_floor_applied_frac"),
                "var_solver_failure_frac": var_row.get("solver_failure_frac"),
                "fixed_solver_failure_frac": fixed_row.get("solver_failure_frac"),
                "var_supervisor_override_frac": var_row.get("final_control_overridden_frac"),
                "fixed_supervisor_override_frac": fixed_row.get("final_control_overridden_frac"),
                "var_policy_min_footprint_separation": var_row.get("policy_min_footprint_separation"),
                "fixed_policy_min_footprint_separation": fixed_row.get("policy_min_footprint_separation"),
            }
        )
    return rows


def _write_csv(path: str, rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _to_markdown(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, float):
                cells.append(_format_float(value, 4))
            else:
                cells.append("" if value is None else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _overall_summary(step_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for row in step_rows:
        grouped[(row["scenario"], row["initial"], row["policy"])].append(row)

    out: List[Dict[str, Any]] = []
    for (scenario, initial, policy), rows in sorted(grouped.items()):
        out.append(
            {
                "scenario": scenario,
                "initial": initial,
                "policy": policy,
                "n_steps": len(rows),
                "supervisor_active_frac": _frac(rows, "yield_supervisor_active"),
                "hard_stop_override_frac": _frac(rows, "hard_stop_required"),
                "rolling_caution_frac": _frac(rows, "rolling_caution_active"),
                "emergency_brake_frac": _frac(rows, "emergency_brake_active"),
                "final_control_overridden_frac": _frac(rows, "final_control_overridden"),
                "solver_failure_frac": _frac(rows, "solver_success", positive=False),
                "solver_uses_adaptive_risk_frac": _frac(rows, "solver_uses_adaptive_risk"),
                "solver_risk_mode": _mode_label(rows, "solver_risk_mode"),
                "risk_tightening_mean": _mean(r.get("risk_tightening") for r in rows),
                "risk_tightening_min": _min(r.get("risk_tightening") for r in rows),
                "risk_tightening_max": _max(r.get("risk_tightening") for r in rows),
                "risk_target_prob_mean": _mean(r.get("risk_target_prob") for r in rows),
                "diagnostic_risk_tightening_mean": _mean(r.get("diagnostic_risk_tightening") for r in rows),
                "preclearance_floor_active_frac": _frac(rows, "preclearance_floor_active"),
                "preclearance_floor_applied_frac": _frac(rows, "preclearance_floor_applied"),
                "effective_severity_mean": _mean(r.get("effective_severity_score") for r in rows),
                "policy_min_footprint_separation": _mean(r.get("policy_min_footprint_separation") for r in rows),
                "policy_min_center_distance": _mean(r.get("policy_min_center_distance") for r in rows),
                "policy_yield_ok": rows[0].get("policy_yield_ok"),
            }
        )
    return out


def _write_markdown(
    path: str,
    results_dir: str,
    step_rows: Sequence[Dict[str, Any]],
    summary_rows: Sequence[Dict[str, Any]],
    comparison_rows: Sequence[Dict[str, Any]],
    output_paths: Dict[str, str],
) -> None:
    overall = _overall_summary(step_rows)
    overall_cols = [
        "scenario",
        "initial",
        "policy",
        "n_steps",
        "supervisor_active_frac",
        "hard_stop_override_frac",
        "final_control_overridden_frac",
        "solver_failure_frac",
        "solver_uses_adaptive_risk_frac",
        "solver_risk_mode",
        "risk_tightening_mean",
        "risk_tightening_max",
        "preclearance_floor_applied_frac",
        "policy_min_footprint_separation",
        "policy_yield_ok",
    ]
    bucket_cols = [
        "scenario",
        "initial",
        "policy",
        "bucket",
        "clearance_phase",
        "n_steps",
        "ego_dconf_mean",
        "supervisor_active_frac",
        "hard_stop_override_frac",
        "final_control_overridden_frac",
        "solver_failure_frac",
        "solver_uses_adaptive_risk_frac",
        "solver_risk_mode",
        "risk_tightening_mean",
        "risk_tightening_max",
        "risk_target_prob_mean",
        "diagnostic_risk_tightening_mean",
        "raw_tightening_before_floor_mean",
        "preclearance_floor_active_frac",
        "preclearance_floor_applied_frac",
        "effective_severity_mean",
        "nominal_accel_mean",
        "final_accel_mean",
    ]
    comparison_cols = [
        "scenario",
        "initial",
        "bucket",
        "clearance_phase",
        "var_minus_fixed_risk_tightening_mean",
        "var_minus_fixed_diagnostic_risk_tightening_mean",
        "var_minus_fixed_floor_applied_frac",
        "var_minus_fixed_nominal_accel_mean",
        "var_minus_fixed_solver_failure_frac",
        "var_minus_fixed_supervisor_override_frac",
        "var_minus_fixed_min_footprint_separation",
        "var_risk_tightening_mean",
        "fixed_risk_tightening_mean",
        "var_floor_applied_frac",
        "fixed_floor_applied_frac",
        "var_solver_failure_frac",
        "fixed_solver_failure_frac",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Risk By Conflict Distance Summary\n\n")
        f.write(f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`\n")
        f.write(f"- Results dir: `{os.path.abspath(results_dir)}`\n")
        f.write("- Purpose: quantify adaptive-variable-risk behaviour without changing controller outputs.\n\n")
        f.write("## Output Files\n\n")
        for label, out_path in output_paths.items():
            f.write(f"- `{label}`: `{out_path}`\n")
        f.write("\n")
        f.write("## Overall Policy Summary\n\n")
        f.write(_to_markdown(overall, overall_cols))
        f.write("\n\n")
        f.write("## Conflict-Distance Bucket Summary\n\n")
        f.write(_to_markdown(summary_rows, bucket_cols))
        f.write("\n\n")
        f.write("## Var Risk Minus Fixed Risk\n\n")
        f.write(_to_markdown(comparison_rows, comparison_cols))
        f.write("\n\n")
        f.write("## Interpretation Notes\n\n")
        f.write("- `risk_tightening_mean/max` and `risk_target_prob_mean` show the risk values actually used by the solver when new logs provide `solver_current_*`; older logs fall back to legacy `applied_*`/adaptive fields.\n")
        f.write("- `diagnostic_risk_tightening_mean` records the adaptive severity mapping even for fixed-risk runs; it is diagnostic and may differ from the actual solver risk.\n")
        f.write("- `clearance_phase` separates pre-clearance interaction from post-clearance recovery. Use `pre_clearance` rows to evaluate whether adaptive risk is more conservative before the target clears the conflict zone.\n")
        f.write("- `hard_stop_override_frac` and `final_control_overridden_frac` show how much the rule-aware supervisor, rather than the raw SMPC action, controlled the final command.\n")
        f.write("- `policy_min_footprint_separation` is the policy-level post-CARLA gate minimum repeated for context; this script does not estimate per-step footprints.\n")
        f.write("- A useful adaptive-risk contribution should appear as stronger pre-clearance tightening in `approach`/`critical`/`near` buckets without increasing solver failures or supervisor override reliance, followed by relaxed post-clearance risk when the target has cleared.\n")


def run(results_dir: str, policies: Sequence[str]) -> Dict[str, str]:
    results_dir = os.path.abspath(results_dir)
    gate_metrics = _load_gate_policy_metrics(results_dir)
    step_rows: List[Dict[str, Any]] = []

    for scenario_dir, ident in _list_smpc_dirs(results_dir, policies):
        gate_policy = gate_metrics.get(ident.scenario_dir) or gate_metrics.get(ident.policy, {})
        step_rows.extend(_load_step_rows(scenario_dir, ident, gate_policy))

    summary_rows = _summarise_rows(step_rows)
    comparison_rows = _comparison_rows(summary_rows)
    output_paths = {
        "step_csv": os.path.join(results_dir, "risk_by_conflict_distance.csv"),
        "summary_csv": os.path.join(results_dir, "risk_by_conflict_distance_summary.csv"),
        "comparison_csv": os.path.join(results_dir, "risk_by_conflict_distance_comparison.csv"),
        "summary_json": os.path.join(results_dir, "risk_by_conflict_distance_summary.json"),
        "summary_md": os.path.join(results_dir, "risk_by_conflict_distance_summary.md"),
    }
    _write_csv(output_paths["step_csv"], step_rows, STEP_COLUMNS)
    _write_csv(output_paths["summary_csv"], summary_rows, SUMMARY_COLUMNS)
    _write_csv(output_paths["comparison_csv"], comparison_rows, COMPARISON_COLUMNS)
    with open(output_paths["summary_json"], "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "results_dir": results_dir,
                "policies": list(policies),
                "n_step_rows": len(step_rows),
                "n_summary_rows": len(summary_rows),
                "n_comparison_rows": len(comparison_rows),
                "summary": summary_rows,
                "comparison": comparison_rows,
            },
            f,
            indent=2,
            sort_keys=True,
        )
    _write_markdown(output_paths["summary_md"], results_dir, step_rows, summary_rows, comparison_rows, output_paths)
    return output_paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarise adaptive SMPC risk allocation by conflict-zone distance."
    )
    parser.add_argument("results_dir", help="CARLA batch results directory.")
    parser.add_argument(
        "--policies",
        nargs="+",
        default=list(SMPC_POLICIES),
        help="SMPC policies to include. Default: smpc_var_risk smpc_fixed_risk.",
    )
    args = parser.parse_args()

    paths = run(args.results_dir, args.policies)
    print("Risk-by-conflict-distance diagnostics written:")
    for label, path in paths.items():
        print(f"- {label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
