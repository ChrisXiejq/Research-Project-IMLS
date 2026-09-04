#!/usr/bin/env python3
"""Analyze same-state 2x2 predictor/risk/supervisor shadow commands."""

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
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable


SCHEMA_VERSION = "shadow_command_transmission_analysis_v1"
PREDICTORS = ("B1", "P_star")
RISKS = ("fixed_medium", "adaptive")
MAPPINGS = ("monitor_only", "enabled")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _as_float(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite {name}: {value!r}")
    return result


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "ego_init_id", "factual_rollout_id", "state_key", "predictor",
        "risk_policy", "supervisor_mapping", "nominal_accel_mps2",
        "post_accel_mps2", "supervisor_any_requested", "shadow_actuated",
        "solver_accepted", "fallback_used", "factual_branch",
        "factual_command_parity",
    }
    missing = required - set(rows[0] if rows else {})
    if missing:
        raise ValueError(f"Missing shadow columns: {sorted(missing)}")
    result = []
    for row in rows:
        result.append({
            **row,
            "ego_init_id": int(row["ego_init_id"]),
            "nominal_accel_mps2": _as_float(row["nominal_accel_mps2"], "nominal_accel_mps2"),
            "post_accel_mps2": _as_float(row["post_accel_mps2"], "post_accel_mps2"),
            "supervisor_any_requested": _as_bool(row["supervisor_any_requested"]),
            "shadow_actuated": _as_bool(row["shadow_actuated"]),
            "solver_accepted": _as_bool(row["solver_accepted"]),
            "fallback_used": _as_bool(row["fallback_used"]),
            "factual_branch": _as_bool(row["factual_branch"]),
            "factual_command_parity": _as_bool(row["factual_command_parity"]),
        })
    return result


def _bootstrap_ci(values_by_group: dict[int, float], *, seed: int, resamples: int) -> list[float]:
    groups = sorted(values_by_group)
    if len(groups) < 2:
        raise ValueError("At least two independent ego_init_id groups are required")
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        sample = [values_by_group[rng.choice(groups)] for _ in groups]
        estimates.append(fmean(sample))
    estimates.sort()
    low = estimates[int(0.025 * (resamples - 1))]
    high = estimates[int(0.975 * (resamples - 1))]
    return [low, high]


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        raise ValueError("Cannot average an empty contrast")
    return fmean(values)


def _state_contrasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["factual_rollout_id"], row["state_key"])].append(row)
    output = []
    for (rollout_id, state_key), group in sorted(grouped.items()):
        if len(group) != 8:
            raise ValueError(f"Expected 8 shadow branches for {rollout_id}/{state_key}, found {len(group)}")
        if any(row["shadow_actuated"] for row in group):
            raise ValueError(f"Shadow actuation detected at {rollout_id}/{state_key}")
        # Only the authority-enabled predictor/risk branch is physically
        # factual.  Monitor-only is a shadow mapping and must never be counted
        # as a second factual command merely because predictor and risk match.
        factual = [row for row in group if row["factual_branch"]]
        if (
            len(factual) != 1
            or factual[0]["supervisor_mapping"] != "enabled"
            or not factual[0]["factual_command_parity"]
        ):
            raise ValueError(f"Factual branch parity failed at {rollout_id}/{state_key}")
        keyed = {(r["predictor"], r["risk_policy"], r["supervisor_mapping"]): r for r in group}
        expected = {(p, r, m) for p in PREDICTORS for r in RISKS for m in MAPPINGS}
        if set(keyed) != expected:
            raise ValueError(f"Incomplete or duplicate shadow factorial at {rollout_id}/{state_key}")
        init_ids = {row["ego_init_id"] for row in group}
        if len(init_ids) != 1:
            raise ValueError(f"Mixed init groups at {rollout_id}/{state_key}")
        active = any(row["supervisor_any_requested"] for row in group)
        for axis in ("predictor", "risk"):
            matched_values = RISKS if axis == "predictor" else PREDICTORS
            for matched in matched_values:
                if axis == "predictor":
                    left_key = ("B1", matched, "monitor_only")
                    right_key = ("P_star", matched, "monitor_only")
                    left_enabled = ("B1", matched, "enabled")
                    right_enabled = ("P_star", matched, "enabled")
                else:
                    left_key = (matched, "fixed_medium", "monitor_only")
                    right_key = (matched, "adaptive", "monitor_only")
                    left_enabled = (matched, "fixed_medium", "enabled")
                    right_enabled = (matched, "adaptive", "enabled")
                monitor_sep = abs(keyed[right_key]["post_accel_mps2"] - keyed[left_key]["post_accel_mps2"])
                enabled_sep = abs(keyed[right_enabled]["post_accel_mps2"] - keyed[left_enabled]["post_accel_mps2"])
                output.append({
                    "ego_init_id": next(iter(init_ids)),
                    "factual_rollout_id": rollout_id,
                    "state_key": state_key,
                    "axis": axis,
                    "matched_policy": matched,
                    "supervisor_active": active,
                    "monitor_separation_accel_mps2": monitor_sep,
                    "enabled_separation_accel_mps2": enabled_sep,
                    "attenuation_accel_mps2": enabled_sep - monitor_sep,
                    "both_monitor_solver_accepted": keyed[left_key]["solver_accepted"] and keyed[right_key]["solver_accepted"],
                    "both_enabled_solver_accepted": keyed[left_enabled]["solver_accepted"] and keyed[right_enabled]["solver_accepted"],
                })
    return output


def _aggregate(contrasts: list[dict[str, Any]], *, threshold: float, seed: int, resamples: int) -> list[dict[str, Any]]:
    cells: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in contrasts:
        stratum = "active" if row["supervisor_active"] else "inactive"
        cells[(row["axis"], row["matched_policy"], stratum)].append(row)
        cells[(row["axis"], row["matched_policy"], "all")].append(row)
    results = []
    for (axis, matched, stratum), rows in sorted(cells.items()):
        by_group: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_group[row["ego_init_id"]].append(row)
        if len(by_group) < 2:
            continue
        group_monitor = {g: _mean(r["monitor_separation_accel_mps2"] for r in values) for g, values in by_group.items()}
        group_enabled = {g: _mean(r["enabled_separation_accel_mps2"] for r in values) for g, values in by_group.items()}
        group_attenuation = {g: group_enabled[g] - group_monitor[g] for g in by_group}
        monitor = _mean(group_monitor.values())
        enabled = _mean(group_enabled.values())
        attenuation = _mean(group_attenuation.values())
        ci = _bootstrap_ci(group_attenuation, seed=seed, resamples=resamples)
        if monitor < threshold:
            verdict = "controller_insensitivity_supervisor_masking_not_testable"
            ratio = None
        else:
            ratio = enabled / monitor
            verdict = "command_level_masking_identified" if ci[1] < 0 else "supervisor_attenuation_unresolved"
        results.append({
            "axis": axis,
            "matched_policy": matched,
            "stratum": stratum,
            "independent_groups": len(by_group),
            "states": len(rows),
            "monitor_separation_accel_mps2": monitor,
            "enabled_separation_accel_mps2": enabled,
            "attenuation_accel_mps2": attenuation,
            "attenuation_ci95": ci,
            "retention_ratio": ratio,
            "denominator_threshold_accel_mps2": threshold,
            "verdict": verdict,
        })
    return results


def analyze(input_csv: Path, output: Path, *, threshold: float = 0.05, seed: int = 20260825, resamples: int = 10000) -> dict[str, Any]:
    rows = _load_rows(input_csv)
    contrasts = _state_contrasts(rows)
    aggregates = _aggregate(contrasts, threshold=threshold, seed=seed, resamples=resamples)
    if not aggregates:
        raise ValueError("No valid group-level shadow contrasts")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(input_csv), "sha256": _sha256(input_csv), "rows": len(rows)},
        "integrity": {
            "shadow_actuation_count": sum(row["shadow_actuated"] for row in rows),
            "all_factual_parity": all(row["factual_command_parity"] for row in rows if row["factual_branch"]),
            "state_factorial_size": 8,
        },
        "state_contrasts": contrasts,
        "aggregates": aggregates,
        "causal_scope": "same-state immediate longitudinal command transmission only",
        "prohibited_overclaim": "Do not infer long-horizon counterfactual trajectories, formal safety or population-level collision effects.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--resamples", type=int, default=10000)
    args = parser.parse_args()
    result = analyze(args.input_csv, args.output, threshold=args.threshold, seed=args.seed, resamples=args.resamples)
    print(json.dumps({"status": result["status"], "aggregates": len(result["aggregates"])}))


if __name__ == "__main__":
    main()
