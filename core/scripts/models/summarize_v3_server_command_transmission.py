#!/usr/bin/env python3
"""Build a compact, provenance-bound summary of V3 raw SMPC telemetry.

The script is intentionally read-only with respect to the raw result tree.  It
records file hashes and derives rollout-level means before paired aggregation;
raw control steps are never treated as independent experimental units.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable


SCHEMA_VERSION = "v3_server_command_transmission_audit_v1"
CELL_RE = re.compile(
    r"^(?P<predictor>B1|P_star)__(?P<risk>adaptive|fixed_medium)__"
    r"(?P<target>assertive_constant_speed|defensive_reactive)$"
)
INIT_RE = re.compile(r"ego_init_(?P<init>\d+)")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return fmean(values) if values else None


def _extract_step(record: dict[str, Any]) -> dict[str, Any]:
    risk = record.get("risk") or {}
    applied = record.get("applied") or {}
    post = applied.get("post_solver_action_filter") or {}
    if not post:
        post = ((record.get("rule_aware_yield") or {}).get("post_solver_action_filter") or {})
    nominal = post.get("nominal_solver_command") or {}
    actual = post.get("actual_command") or {}

    nominal_accel = _finite(nominal.get("a_des"))
    if nominal_accel is None:
        nominal_accel = _finite((applied.get("nominal_solver_u0") or [None])[0])
    actual_accel = _finite(actual.get("a_des"))
    if actual_accel is None:
        actual_accel = _finite((applied.get("u0") or [None])[0])
    tightening = _finite(risk.get("applied_tight"))
    if tightening is None:
        tightening = _finite(risk.get("tight"))

    authority = (record.get("supervisor_behavioural_authority") or {})
    observed = authority.get("observed_first_stage_activity") or {}
    requested = bool(post.get("intervention_requested")) or bool(observed.get("any_requested"))
    applied_flag = bool(post.get("intervention_applied"))
    delta = None
    if nominal_accel is not None and actual_accel is not None:
        delta = abs(actual_accel - nominal_accel)
    return {
        "tightening": tightening,
        "nominal_accel": nominal_accel,
        "actual_accel": actual_accel,
        "abs_supervisor_accel_delta": delta,
        "supervisor_requested": requested,
        "post_action_applied": applied_flag,
        "controller_accepted": bool(applied.get("is_opt")),
    }


def _rollout_summary(path: Path, closed_loop_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    relative = path.relative_to(closed_loop_root)
    cell_name = relative.parts[0]
    match = CELL_RE.match(cell_name)
    init_match = INIT_RE.search(relative.parts[1] if len(relative.parts) > 1 else "")
    if match is None or init_match is None:
        raise ValueError(f"Unrecognised V3 telemetry path: {relative}")

    steps: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON {path}:{line_number}: {exc}") from exc
            steps.append(_extract_step(record))
    if not steps:
        raise ValueError(f"Empty telemetry file: {path}")

    def values(key: str) -> list[float]:
        return [value for step in steps if (value := step.get(key)) is not None]

    row = {
        **match.groupdict(),
        "ego_init_id": int(init_match.group("init")),
        "relative_path": str(relative),
        "steps": len(steps),
        "valid_tightening_steps": len(values("tightening")),
        "valid_command_steps": len(values("nominal_accel")),
        "mean_tightening": _mean(values("tightening")),
        "mean_nominal_accel_mps2": _mean(values("nominal_accel")),
        "mean_actual_accel_mps2": _mean(values("actual_accel")),
        "mean_abs_supervisor_accel_delta_mps2": _mean(values("abs_supervisor_accel_delta")),
        "supervisor_request_fraction": fmean(bool(step["supervisor_requested"]) for step in steps),
        "post_action_applied_fraction": fmean(bool(step["post_action_applied"]) for step in steps),
        "controller_accepted_fraction": fmean(bool(step["controller_accepted"]) for step in steps),
    }
    source = {
        "relative_path": str(relative),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "line_count": len(steps),
    }
    return row, source


def _cell_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["predictor"], row["risk"], row["target"])].append(row)
    result = []
    metrics = [
        "mean_tightening",
        "mean_nominal_accel_mps2",
        "mean_actual_accel_mps2",
        "mean_abs_supervisor_accel_delta_mps2",
        "supervisor_request_fraction",
        "post_action_applied_fraction",
        "controller_accepted_fraction",
    ]
    for (predictor, risk, target), group in sorted(grouped.items()):
        item: dict[str, Any] = {
            "predictor": predictor,
            "risk": risk,
            "target": target,
            "independent_groups": len(group),
            "ego_init_ids": sorted(row["ego_init_id"] for row in group),
        }
        for metric in metrics:
            item[metric] = _mean(row[metric] for row in group if row[metric] is not None)
        result.append(item)
    return result


def _paired_risk_contrasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {
        (row["predictor"], row["target"], row["ego_init_id"], row["risk"]): row
        for row in rows
    }
    metrics = [
        "mean_tightening",
        "mean_nominal_accel_mps2",
        "mean_actual_accel_mps2",
        "mean_abs_supervisor_accel_delta_mps2",
    ]
    result = []
    for predictor in ("B1", "P_star"):
        for target in ("assertive_constant_speed", "defensive_reactive"):
            pairs = []
            for init_id in range(81, 91):
                adaptive = keyed.get((predictor, target, init_id, "adaptive"))
                fixed = keyed.get((predictor, target, init_id, "fixed_medium"))
                if adaptive is None or fixed is None:
                    raise ValueError(f"Missing paired rollout: {predictor}/{target}/{init_id}")
                pairs.append((adaptive, fixed))
            item: dict[str, Any] = {
                "predictor": predictor,
                "target": target,
                "contrast": "adaptive_minus_fixed_medium",
                "independent_groups": len(pairs),
                "ego_init_ids": list(range(81, 91)),
            }
            for metric in metrics:
                diffs = [a[metric] - f[metric] for a, f in pairs]
                item[f"{metric}_effect"] = fmean(diffs)
                item[f"{metric}_paired_values"] = diffs
            result.append(item)
    return result


def summarize(closed_loop_root: Path, output_dir: Path) -> dict[str, Any]:
    paths = sorted(closed_loop_root.glob("*/*/smpc_debug_steps.jsonl"))
    paths = [path for path in paths if CELL_RE.match(path.relative_to(closed_loop_root).parts[0])]
    if len(paths) != 80:
        raise ValueError(f"Expected exactly 80 formal V3 telemetry files, found {len(paths)}")
    rollouts, sources = zip(*(_rollout_summary(path, closed_loop_root) for path in paths))
    rollouts = list(rollouts)
    sources = list(sources)
    if sorted({row["ego_init_id"] for row in rollouts}) != list(range(81, 91)):
        raise ValueError("Unexpected V3 ego_init_id population")

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": str(closed_loop_root),
        "mutation_boundary": "Raw telemetry was read only; only compact summary files were written.",
        "population": {
            "rollouts": 80,
            "independent_unit": "ego_init_id",
            "ego_init_ids": list(range(81, 91)),
            "predictors": ["B1", "P_star"],
            "risk_policies": ["adaptive", "fixed_medium"],
            "target_styles": ["assertive_constant_speed", "defensive_reactive"],
            "step_rows_are_not_independent_units": True,
        },
        "rollout_summaries": rollouts,
        "cell_summaries": _cell_summaries(rollouts),
        "paired_risk_contrasts": _paired_risk_contrasts(rollouts),
        "source_inventory": sources,
        "identification_boundary": (
            "Risk arms are paired by ego_init_id but follow different factual states; "
            "these are descriptive rollout-level transmission contrasts, not same-state counterfactual commands."
        ),
        "same_state_alternative_commands_present": False,
    }
    json_path = output_dir / "v3_risk_command_transmission.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    csv_path = output_dir / "v3_rollout_command_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rollouts[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rollouts)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--closed-loop-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.closed_loop_root.resolve(), args.output_dir.resolve())
    print(json.dumps({"status": result["status"], "rollouts": len(result["rollout_summaries"])}))


if __name__ == "__main__":
    main()
