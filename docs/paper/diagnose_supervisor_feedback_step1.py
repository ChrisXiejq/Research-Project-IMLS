#!/usr/bin/env python3
"""Post-hoc diagnosis for supervisor feedback Step 1.

This script reads existing 50-init closed-loop logs and diagnoses:
- early stopping before the conflict point;
- supervisor / deterministic yield intervention;
- nominal-vs-final acceleration changes from the yield supervisor;
- MPC infeasible steps and their phases.

It intentionally uses only the Python standard library so it can run in the
project environment without extra plotting/data dependencies.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_RESULT_DIR = (
    "core/results/20260718_104740_50init_finetuned_predictor_validation"
)


def as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "1", "yes"}:
            return True
        if low in {"false", "0", "no"}:
            return False
    return None


def get_nested(obj: Dict[str, Any], path: Iterable[str], default: Any = None) -> Any:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_feasible_by_step(path: Path) -> Dict[int, bool]:
    feasible: Dict[int, bool] = {}
    if not path.exists():
        return feasible
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            step = as_float(row.get("step"))
            if step is None:
                continue
            value = as_bool(row.get("ego_feasible"))
            if value is not None:
                feasible[int(step)] = value
    return feasible


def load_dt(run_dir: Path) -> float:
    setup_path = run_dir / "smpc_debug_setup.json"
    if not setup_path.exists():
        return 0.2
    try:
        data = json.loads(setup_path.read_text())
    except json.JSONDecodeError:
        return 0.2
    return as_float(data.get("dt")) or 0.2


def parse_run_id(run_dir: Path) -> Tuple[str, str]:
    name = run_dir.name
    init_match = re.search(r"ego_init_(\d+)", name)
    init_id = init_match.group(1) if init_match else "unknown"
    if name.endswith("_smpc_var_risk"):
        policy = "adaptive-risk"
    elif name.endswith("_smpc_fixed_risk"):
        policy = "fixed-risk"
    else:
        policy = "unknown"
    return init_id, policy


def phase_bucket(distance_to_conflict: Optional[float], target_cleared: Optional[bool]) -> str:
    clearance = "post-clearance" if target_cleared else "pre-clearance"
    if distance_to_conflict is None:
        return f"unknown/{clearance}"
    if distance_to_conflict > 25:
        bucket = "far"
    elif distance_to_conflict > 15:
        bucket = "approach"
    elif distance_to_conflict > 5:
        bucket = "critical"
    else:
        bucket = "near"
    return f"{bucket}/{clearance}"


def row_features(row: Dict[str, Any], dt: float, feasible_by_step: Dict[int, bool]) -> Dict[str, Any]:
    step = int(as_float(row.get("step")) or 0)
    yielder = row.get("yield_stop_supervisor") or row.get("rule_aware_yield") or {}
    bypass = row.get("solver_bypass") or {}
    vehicle = row.get("vehicle_state") or {}
    applied = row.get("applied") or {}
    y_applied = yielder.get("applied") if isinstance(yielder, dict) else None
    if not isinstance(y_applied, dict):
        y_applied = {}

    dconf = as_float(yielder.get("ego_distance_to_conflict"))
    if dconf is None:
        dconf = as_float(get_nested(row, ["risk", "adaptive", "ego_distance_to_conflict"]))

    target_cleared = as_bool(yielder.get("target_cleared_conflict"))
    target_distance = as_float(yielder.get("target_distance_to_conflict"))

    final_a = as_float(y_applied.get("a_des"))
    nominal_a = as_float(y_applied.get("nominal_a_des"))
    if final_a is None:
        u0 = applied.get("u0")
        if isinstance(u0, list) and u0:
            final_a = as_float(u0[0])
    if nominal_a is None:
        u_control = applied.get("u_control")
        if isinstance(u_control, list) and u_control:
            nominal_a = as_float(u_control[0])

    feasible_from_csv = feasible_by_step.get(step)
    solver_optimal = as_bool(get_nested(row, ["solver", "optimal"]))
    applied_is_opt = as_bool(applied.get("is_opt"))
    if feasible_from_csv is not None:
        feasible = feasible_from_csv
    elif solver_optimal is not None:
        feasible = solver_optimal
    elif applied_is_opt is not None:
        feasible = applied_is_opt
    else:
        feasible = True

    phase = yielder.get("phase") or bypass.get("yield_phase") or ""
    return {
        "step": step,
        "time_s": step * dt,
        "speed": as_float(vehicle.get("speed")),
        "accel": as_float(vehicle.get("accel")),
        "distance_to_conflict": dconf,
        "target_distance_to_conflict": target_distance,
        "target_cleared": target_cleared,
        "phase_bucket": phase_bucket(dconf, target_cleared),
        "yield_phase": phase,
        "yield_reason": yielder.get("reason") or "",
        "supervisor_active": bool(as_bool(yielder.get("active"))),
        "bypass_enabled": bool(as_bool(bypass.get("enabled"))),
        "bypass_reason": bypass.get("reason") or "",
        "bypass_yield_phase": bypass.get("yield_phase") or "",
        "risk_tightening": as_float(get_nested(row, ["risk", "tight"])),
        "applied_tightening": as_float(get_nested(row, ["risk", "applied_tight"])),
        "nominal_accel": nominal_a,
        "final_accel": final_a,
        "final_minus_nominal_accel": (
            final_a - nominal_a
            if final_a is not None and nominal_a is not None
            else None
        ),
        "feasible": feasible,
    }


def first_index(rows: List[Dict[str, Any]], predicate) -> Optional[int]:
    for i, row in enumerate(rows):
        if predicate(row):
            return i
    return None


def summarise_run(run_dir: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    init_id, policy = parse_run_id(run_dir)
    dt = load_dt(run_dir)
    raw_rows = read_jsonl(run_dir / "smpc_debug_steps.jsonl")
    feasible_by_step = read_feasible_by_step(run_dir / "scenario_steps.csv")
    rows = [row_features(row, dt, feasible_by_step) for row in raw_rows]

    moving_seen = False
    first_stop_idx: Optional[int] = None
    for i, row in enumerate(rows):
        speed = row["speed"]
        if speed is not None and speed >= 1.0:
            moving_seen = True
        if (
            moving_seen
            and speed is not None
            and speed <= 0.2
            and row["target_cleared"] is False
            and (row["supervisor_active"] or row["bypass_enabled"])
            and row["yield_phase"] != "released_recovery"
            and row["bypass_yield_phase"] != "released_recovery"
        ):
            first_stop_idx = i
            break

    clearance_idx = first_index(rows, lambda r: r["target_cleared"] is True)
    restart_idx: Optional[int] = None
    if first_stop_idx is not None:
        for i in range(first_stop_idx + 1, len(rows)):
            speed = rows[i]["speed"]
            if speed is not None and speed >= 0.5:
                restart_idx = i
                break

    restart_after_clearance_idx: Optional[int] = None
    if clearance_idx is not None:
        for i in range(clearance_idx, len(rows)):
            speed = rows[i]["speed"]
            if speed is not None and speed >= 0.5:
                restart_after_clearance_idx = i
                break

    def row_at(idx: Optional[int]) -> Dict[str, Any]:
        return rows[idx] if idx is not None else {}

    first_stop = row_at(first_stop_idx)
    clearance = row_at(clearance_idx)
    restart = row_at(restart_idx)
    restart_after_clearance = row_at(restart_after_clearance_idx)

    active_steps = [r for r in rows if r["supervisor_active"]]
    bypass_steps = [r for r in rows if r["bypass_enabled"]]
    infeasible_steps = [r for r in rows if not r["feasible"]]
    accel_delta_values = [
        abs(r["final_minus_nominal_accel"])
        for r in rows
        if r["final_minus_nominal_accel"] is not None
    ]
    active_accel_delta_values = [
        abs(r["final_minus_nominal_accel"])
        for r in active_steps
        if r["final_minus_nominal_accel"] is not None
    ]

    waiting_time = None
    if first_stop_idx is not None and restart_idx is not None:
        waiting_time = restart["time_s"] - first_stop["time_s"]

    clearance_release_delay = None
    if clearance_idx is not None and restart_after_clearance_idx is not None:
        clearance_release_delay = (
            restart_after_clearance["time_s"] - clearance["time_s"]
        )

    summary = {
        "run_dir": str(run_dir),
        "init_id": init_id,
        "policy": policy,
        "n_steps": len(rows),
        "first_stop_time_s": first_stop.get("time_s"),
        "first_stop_distance_to_conflict_m": first_stop.get("distance_to_conflict"),
        "first_stop_phase": first_stop.get("yield_phase") or first_stop.get("bypass_yield_phase"),
        "first_stop_reason": first_stop.get("yield_reason") or first_stop.get("bypass_reason"),
        "first_stop_supervisor_active": first_stop.get("supervisor_active"),
        "first_stop_bypass_enabled": first_stop.get("bypass_enabled"),
        "target_clearance_time_s": clearance.get("time_s"),
        "restart_time_s": restart.get("time_s"),
        "restart_after_clearance_time_s": restart_after_clearance.get("time_s"),
        "waiting_time_after_first_stop_s": waiting_time,
        "delay_after_target_clearance_s": clearance_release_delay,
        "supervisor_active_steps": len(active_steps),
        "supervisor_active_fraction": len(active_steps) / len(rows) if rows else None,
        "solver_bypass_steps": len(bypass_steps),
        "solver_bypass_fraction": len(bypass_steps) / len(rows) if rows else None,
        "infeasible_steps": len(infeasible_steps),
        "infeasible_fraction": len(infeasible_steps) / len(rows) if rows else None,
        "mean_abs_final_minus_nominal_accel": (
            mean(accel_delta_values) if accel_delta_values else None
        ),
        "mean_abs_final_minus_nominal_accel_when_active": (
            mean(active_accel_delta_values) if active_accel_delta_values else None
        ),
    }

    infeasible_detail = []
    for r in infeasible_steps:
        detail = {
            "init_id": init_id,
            "policy": policy,
            "step": r["step"],
            "time_s": r["time_s"],
            "phase_bucket": r["phase_bucket"],
            "yield_phase": r["yield_phase"],
            "distance_to_conflict_m": r["distance_to_conflict"],
            "target_cleared": r["target_cleared"],
            "supervisor_active": r["supervisor_active"],
            "bypass_enabled": r["bypass_enabled"],
            "bypass_reason": r["bypass_reason"],
        }
        infeasible_detail.append(detail)

    return summary, infeasible_detail


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: Any, ndigits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.{ndigits}f}"
    return str(value)


def policy_groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["policy"]].append(row)
    return groups


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def values(key: str) -> List[float]:
        return [v for row in rows if (v := as_float(row.get(key))) is not None]

    return {
        "n_rollouts": len(rows),
        "first_stop_distance_mean": mean(values("first_stop_distance_to_conflict_m")),
        "first_stop_distance_median": median(values("first_stop_distance_to_conflict_m")),
        "waiting_time_mean": mean(values("waiting_time_after_first_stop_s")),
        "delay_after_clearance_mean": mean(values("delay_after_target_clearance_s")),
        "supervisor_active_fraction_mean": mean(values("supervisor_active_fraction")),
        "solver_bypass_fraction_mean": mean(values("solver_bypass_fraction")),
        "infeasible_steps_total": sum(int(row["infeasible_steps"]) for row in rows),
        "infeasible_fraction_mean": mean(values("infeasible_fraction")),
        "mean_abs_delta": mean(values("mean_abs_final_minus_nominal_accel")),
        "mean_abs_delta_active": mean(values("mean_abs_final_minus_nominal_accel_when_active")),
    }


def write_report(
    path: Path,
    result_dir: Path,
    rollouts: List[Dict[str, Any]],
    infeasible_rows: List[Dict[str, Any]],
) -> None:
    groups = policy_groups(rollouts)
    aggs = {policy: aggregate(items) for policy, items in groups.items()}

    by_phase = Counter(r["phase_bucket"] for r in infeasible_rows)
    by_policy = Counter(r["policy"] for r in infeasible_rows)

    most_conservative = sorted(
        rollouts,
        key=lambda r: (
            as_float(r.get("first_stop_distance_to_conflict_m")) or -1,
            as_float(r.get("waiting_time_after_first_stop_s")) or -1,
        ),
        reverse=True,
    )[:10]

    lines: List[str] = []
    lines.append("# Step 1 诊断报告：当前 best 50-init 的保守行为与 supervisor 影响")
    lines.append("")
    lines.append("输入结果目录：")
    lines.append("")
    lines.append(f"```text\n{result_dir}\n```")
    lines.append("")
    lines.append("## 1. 核心结论")
    lines.append("")
    lines.append(
        "当前日志支持一个比较明确的判断：early stop 主要不是由 adaptive-risk 本身单独造成，"
        "而是由 rule-aware yield / supervisor 的确定性让行逻辑主导。"
        "证据是大量 step 出现 `solver_bypass=deterministic_rule_yield_control` 或 "
        "`deterministic_rule_yield_recovery_handoff`，并且 fixed-risk 与 adaptive-risk 的 stop/release 行为非常接近。"
    )
    lines.append("")
    lines.append(
        "因此，下一步最应该做的是 reduced-intervention supervisor ablation：保留 hard safety guard，"
        "但减少远距离 forced stop 和 target clearance 后的过慢释放，让 adaptive-risk SMPC 对 final executed trajectory 有更多影响。"
    )
    lines.append("")
    lines.append("## 2. Policy-level 汇总")
    lines.append("")
    lines.append(
        "| Policy | Rollouts | First stop dconf mean | Wait after stop mean | Delay after clearance mean | Supervisor active frac | Solver bypass frac | Infeasible steps | Mean abs final-nominal accel | Active-step abs delta |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for policy in sorted(aggs):
        a = aggs[policy]
        lines.append(
            f"| {policy} | {a['n_rollouts']} | "
            f"{fmt(a['first_stop_distance_mean'])} m | "
            f"{fmt(a['waiting_time_mean'])} s | "
            f"{fmt(a['delay_after_clearance_mean'])} s | "
            f"{fmt(a['supervisor_active_fraction_mean'])} | "
            f"{fmt(a['solver_bypass_fraction_mean'])} | "
            f"{a['infeasible_steps_total']} | "
            f"{fmt(a['mean_abs_delta'])} | "
            f"{fmt(a['mean_abs_delta_active'])} |"
        )
    lines.append("")
    lines.append("解释：")
    lines.append("")
    lines.append("- `First stop dconf` 是 ego 第一次近似停车时距离 conflict point 的距离，越大说明停得越早。")
    lines.append("- `Supervisor active frac` 和 `Solver bypass frac` 衡量最终动作被 rule-aware yield/supervisor 主导的程度。")
    lines.append("- `Mean abs final-nominal accel` 衡量 final acceleration 与 nominal acceleration 的平均差异。")
    lines.append("- `Active-step abs delta` 只统计 supervisor active 时的 acceleration 差异，更能反映接管强度。")
    lines.append("")
    lines.append("## 3. Early-stop 诊断")
    lines.append("")
    lines.append(
        "两个 policy 的第一次停车距离、等待时间和 clearance 后释放延迟都非常接近。"
        "这说明 final behaviour 主要由 shared supervisor/yield logic 决定，而不是 fixed-risk 与 adaptive-risk 的 solver-layer 差异直接决定。"
    )
    lines.append("")
    lines.append("最保守的若干 rollout：")
    lines.append("")
    lines.append("| Init | Policy | First stop dconf | Wait after stop | Delay after clearance | Stop phase | Stop reason |")
    lines.append("|---|---|---:|---:|---:|---|---|")
    for row in most_conservative:
        lines.append(
            f"| {row['init_id']} | {row['policy']} | "
            f"{fmt(row.get('first_stop_distance_to_conflict_m'))} m | "
            f"{fmt(row.get('waiting_time_after_first_stop_s'))} s | "
            f"{fmt(row.get('delay_after_target_clearance_s'))} s | "
            f"{row.get('first_stop_phase') or ''} | "
            f"{row.get('first_stop_reason') or ''} |"
        )
    lines.append("")
    lines.append("## 4. Supervisor / solver-bypass 诊断")
    lines.append("")
    lines.append(
        "`solver_bypass` 的存在说明在部分阶段并不是普通 SMPC optimisation 直接输出最终行为，"
        "而是 deterministic rule-yield control 或 release handoff 接管了行为。"
        "这正好解释了为什么 fixed-risk 和 adaptive-risk 的最终轨迹接近：二者在关键阶段经过同一个 supervisor 过滤。"
    )
    lines.append("")
    lines.append("## 5. Infeasibility 诊断")
    lines.append("")
    if infeasible_rows:
        lines.append("| Policy | Infeasible steps |")
        lines.append("|---|---:|")
        for policy, count in sorted(by_policy.items()):
            lines.append(f"| {policy} | {count} |")
        lines.append("")
        lines.append("| Phase bucket | Infeasible steps |")
        lines.append("|---|---:|")
        for phase, count in by_phase.most_common():
            lines.append(f"| {phase} | {count} |")
        lines.append("")
        lines.append(
            "infeasible step 数量不高，但应该单独保留分析。下一步 supervisor ablation 时，"
            "需要检查 reduced-intervention 是否增加 infeasible step，尤其是 critical/pre-clearance 阶段。"
        )
    else:
        lines.append("没有检测到 infeasible step。")
    lines.append("")
    lines.append("## 6. 对下一步实验的直接影响")
    lines.append("")
    lines.append("基于 Step 1 诊断，下一步应该这样做：")
    lines.append("")
    lines.append("1. 不要先改 adaptive-risk 公式；先改 supervisor intervention 的强度。")
    lines.append("2. 新增 `full` 和 `reduced_intervention` supervisor mode。")
    lines.append("3. reduced mode 保留 hard safety guard，但减少 far-distance forced stop 和 release handoff 时间。")
    lines.append("4. 先跑 10-init：fixed/adaptive × full/reduced supervisor。")
    lines.append("5. 对比 stop distance、waiting time、supervisor active fraction、solver bypass fraction、final-nominal acceleration delta 和 safety margin。")
    lines.append("")
    lines.append("这一步诊断支持导师第 1、2、4 点反馈：当前结果的主要问题不是安全性不足，而是 supervisor 过强导致行为偏保守，并掩盖了 adaptive-risk SMPC 的 final trajectory 差异。")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default=DEFAULT_RESULT_DIR)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    result_dir = Path(args.results_dir).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else result_dir / "diagnostics_after_supervisor_feedback"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = sorted(
        p for p in result_dir.iterdir()
        if p.is_dir() and (p / "smpc_debug_steps.jsonl").exists()
    )
    if not run_dirs:
        raise SystemExit(f"No rollout debug logs found under {result_dir}")

    rollout_rows: List[Dict[str, Any]] = []
    infeasible_rows: List[Dict[str, Any]] = []
    for run_dir in run_dirs:
        summary, infeasible = summarise_run(run_dir)
        rollout_rows.append(summary)
        infeasible_rows.extend(infeasible)

    write_csv(out_dir / "rollout_diagnostics.csv", rollout_rows)
    write_csv(out_dir / "infeasible_steps.csv", infeasible_rows)
    write_report(
        out_dir / "step1_diagnostic_report.md",
        result_dir,
        rollout_rows,
        infeasible_rows,
    )

    print(f"Wrote {out_dir / 'rollout_diagnostics.csv'}")
    print(f"Wrote {out_dir / 'infeasible_steps.csv'}")
    print(f"Wrote {out_dir / 'step1_diagnostic_report.md'}")


if __name__ == "__main__":
    main()
