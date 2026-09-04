#!/usr/bin/env python3
"""Generate claim-safe dissertation artefacts from completed V3 evidence.

The generator is deliberately dependency-free.  It consumes only immutable
JSON evidence, checks the completion/provenance chain, and emits small CSV,
Markdown, JSON, and SVG files suitable for source control.
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
import statistics
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PRIMARY_IDS = {
    "H1_capacity_transformer_full_small_minus_large",
    "H2_information_mlp_snapshot_minus_full",
    "H2_information_transformer_snapshot_minus_full",
    "H3_attention_history_gain_difference_in_differences",
}
RESPONSE_STRATA = (
    "assertive",
    "reactive_pre_response",
    "response_onset",
    "response_active",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _atomic_json(path: Path, payload: Any) -> None:
    _atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path.name}")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_evidence_chain(
    *,
    offline_path: Path,
    audit_path: Path,
    freeze_path: Path,
    closed_loop_path: Path,
    closed_loop_rows_path: Path,
    closed_loop_gate_path: Path,
) -> dict[str, Any]:
    offline = _load(offline_path)
    audit = _load(audit_path)
    freeze = _load(freeze_path)
    closed = _load(closed_loop_path)
    rows = _load(closed_loop_rows_path)
    gate = _load(closed_loop_gate_path)

    _require(offline.get("status") == "pass", "Offline synthesis gate did not pass")
    _require(
        offline.get("evidence_status") == "retrospective_held_out",
        "Offline evidence must retain the retrospective-held-out label",
    )
    _require(audit.get("status") == "pass", "Training audit did not pass")
    _require(audit.get("planned_runs") == 27, "Training audit does not declare 27 runs")
    _require(audit.get("valid_runs") == 27, "Not all 27 training runs are valid")
    _require(not audit.get("invalid_runs_or_gates"), "Training audit contains invalid runs")
    _require(freeze.get("status") == "pass", "Selection freeze did not pass")
    _require(
        freeze.get("heldout_access_authorized") is True,
        "Selection freeze did not authorize gated held-out access",
    )
    _require(
        offline.get("selection_freeze_sha256") == freeze.get("freeze_sha256"),
        "Offline synthesis is not bound to the supplied selection freeze",
    )
    _require(
        freeze.get("training_audit_sha256") == audit.get("audit_sha256"),
        "Selection freeze is not bound to the supplied training audit",
    )
    _require(closed.get("status") == "pass", "Closed-loop synthesis did not pass")
    _require(gate.get("status") == "pass", "Closed-loop completion gate did not pass")
    _require(gate.get("formal_evidence") is True, "Closed-loop gate is not formal evidence")
    _require(gate.get("observed_rollouts") == 80, "Closed-loop gate does not contain 80 rollouts")
    _require(isinstance(rows, list) and len(rows) == 80, "Closed-loop rows are not 80 complete cells")
    _require(
        gate.get("artifact_sha256", {}).get("synthesis") == sha256_file(closed_loop_path),
        "Closed-loop synthesis hash differs from the completion gate",
    )
    _require(
        gate.get("artifact_sha256", {}).get("rows") == sha256_file(closed_loop_rows_path),
        "Closed-loop row hash differs from the completion gate",
    )

    primary = offline.get("three_axes", {}).get("primary_contrasts", [])
    _require(
        {row.get("contrast_id") for row in primary} == PRIMARY_IDS,
        "Offline synthesis is missing one or more preregistered primary contrasts",
    )
    _require(
        offline.get("evaluated_runs") == 27,
        "Offline synthesis does not contain all 27 retained runs",
    )
    _require(
        offline.get("independent_init_groups") == 5,
        "Offline synthesis does not retain five independent held-out groups",
    )
    _require(
        closed.get("independent_groups") == 10,
        "Closed-loop synthesis does not retain ten paired groups",
    )
    return {
        "offline": offline,
        "audit": audit,
        "freeze": freeze,
        "closed": closed,
        "closed_rows": rows,
        "gate": gate,
    }


def _contrast_row(row: Mapping[str, Any], category: str) -> dict[str, Any]:
    interval = row.get("cluster_interval_95") or [None, None]
    return {
        "category": category,
        "contrast_id": row["contrast_id"],
        "metric": row.get("metric"),
        "effect": row.get("effect", row.get("effect_P_star_minus_B1")),
        "ci95_low": interval[0],
        "ci95_high": interval[1],
        "raw_sign_flip_p": row.get("raw_sign_flip_p"),
        "holm_adjusted_p": row.get("holm_adjusted_p"),
        "independent_groups": row.get("independent_init_groups", row.get("independent_groups")),
        "evidence_status": "retrospective_held_out" if category != "closed_loop" else "formal_closed_loop",
    }


def build_offline_tables(offline: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    cells = []
    for row in offline["cell_summaries"]:
        cells.append(
            {
                "model_cell_id": row["model_cell_id"],
                "history_horizon_s": row.get("history_horizon_s"),
                "trainable_parameters": row["trainable_parameters"],
                "selection_median_rollout_macro_nll": row["selection_median_rollout_macro_nll"],
                "heldout_rollout_macro_nll_mean": row["heldout_rollout_macro_nll_mean"],
                "heldout_rollout_macro_nll_seed_sd": row["heldout_rollout_macro_nll_seed_sd"],
                "seed_11_nll": row["per_seed"].get("11"),
                "seed_23_nll": row["per_seed"].get("23"),
                "seed_37_nll": row["per_seed"].get("37"),
                "evidence_status": offline["evidence_status"],
            }
        )
    contrasts = [
        _contrast_row(row, "primary")
        for row in offline["three_axes"]["primary_contrasts"]
    ]
    contrasts.extend(
        _contrast_row(row, "direct_architecture")
        for row in offline["direct_architecture_contrasts"]
    )
    contrasts.extend(
        _contrast_row(row, "supporting") for row in offline["supporting_contrasts"]
    )
    return {"cells": cells, "contrasts": contrasts}


def _mean(values: Iterable[float]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.fmean(finite) if finite else None


def build_closed_loop_tables(
    closed: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    metrics = (
        "completion_time_s",
        "min_footprint_separation_m",
        "footprint_collision_rate",
        "solver_failure_fraction",
        "prediction_fallback_fraction",
        "solver_activity_fraction",
        "supervisor_active_fraction",
        "inloop_prediction_entropy",
        "inloop_top1_ADE_m",
    )
    cells: list[dict[str, Any]] = []
    for predictor in ("B1", "P_star"):
        for risk in ("fixed_medium", "adaptive"):
            selected = [
                row for row in rows
                if row["predictor"] == predictor and row["risk_policy"] == risk
            ]
            _require(len(selected) == 20, f"Closed-loop cell {predictor}/{risk} is incomplete")
            cell = {
                "predictor": predictor,
                "risk_policy": risk,
                "rollouts": len(selected),
                "independent_groups": len({int(row["ego_init_id"]) for row in selected}),
                "target_styles": len({row["target_style"] for row in selected}),
                "evidence_status": "formal_closed_loop",
            }
            for metric in metrics:
                cell[metric] = _mean(row.get(metric) for row in selected)
            cells.append(cell)
    contrasts = [
        _contrast_row(row, "closed_loop")
        for row in closed["within_risk_contrasts"] + closed["model_by_risk_interactions"]
    ]
    for row in closed.get("null_or_under_supported_metrics", []):
        contrasts.append(
            {
                "category": "under_supported",
                "contrast_id": row["metric"],
                "metric": row["metric"],
                "effect": None,
                "ci95_low": None,
                "ci95_high": None,
                "raw_sign_flip_p": None,
                "holm_adjusted_p": None,
                "independent_groups": None,
                "evidence_status": "formal_closed_loop_under_supported",
                "reason": row["reason"],
            }
        )
    return {"cells": cells, "contrasts": contrasts}


def build_b1_allocation_table(offline: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for contrast in offline["supporting_contrasts"]:
        if not contrast["contrast_id"].startswith("B1_minus_"):
            continue
        row = _contrast_row(contrast, "adaptation_allocation")
        row["interpretation"] = (
            "positive means the history encoder has lower NLL than B1; "
            "this is a complete-configuration allocation contrast"
        )
        rows.append(row)
    _require(len(rows) == 2, "Expected B1 allocation contrasts against MLP and Transformer")
    return rows


def _discover_json(root: Path, directory: str, name: str) -> list[dict[str, Any]]:
    paths = sorted((root / directory).glob(f"*/{name}"))
    return [_load(path) for path in paths]


def build_calibration_latency_tables(results_root: Path) -> dict[str, list[dict[str, Any]]]:
    calibrations = _discover_json(results_root, "postprocess/calibration", "calibration.json")
    latencies = _discover_json(results_root, "postprocess/latency", "latency.json")
    by_cell_cal: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_cell_latency: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in calibrations:
        _require(row.get("calibration_fit_uses_test") is False, "Calibration accessed held-out data")
        by_cell_cal[row["model_cell_id"]].append(row)
    for row in latencies:
        _require(row.get("status") == "pass", "A latency audit did not pass")
        _require(row.get("warmup_count", 0) >= 20, "Latency warm-up contract was not met")
        _require(row.get("measured_count", 0) >= 100, "Latency measurement contract was not met")
        by_cell_latency[row["model_cell_id"]].append(row)
    _require(len(calibrations) == 27, "Expected 27 calibration reports")
    _require(len(latencies) == 27, "Expected 27 latency reports")
    calibration_rows = []
    for cell, items in sorted(by_cell_cal.items()):
        calibration_rows.append(
            {
                "model_cell_id": cell,
                "retained_seeds": len(items),
                "temperature_mean": _mean(item["parameters"]["temperature"] for item in items),
                "covariance_scale_mean": _mean(item["parameters"]["covariance_scale"] for item in items),
                "identity_validation_nll_mean": _mean(item["search"]["identity_validation_NLL_per_step"] for item in items),
                "calibrated_validation_nll_mean": _mean(item["search"]["best_validation_NLL_per_step"] for item in items),
                "fit_groups": "36--40",
                "heldout_used_for_fit": False,
            }
        )
    latency_rows = []
    for cell, items in sorted(by_cell_latency.items()):
        latency_rows.append(
            {
                "model_cell_id": cell,
                "retained_seeds": len(items),
                "mean_latency_ms": _mean(item["mean_ms"] for item in items),
                "p50_latency_ms": _mean(item["p50_ms"] for item in items),
                "p95_latency_ms": _mean(item["p95_ms"] for item in items),
                "trainable_parameters": items[0]["trainable_parameters"],
                "warmup_count": min(item["warmup_count"] for item in items),
                "measured_count": min(item["measured_count"] for item in items),
            }
        )
    return {"calibration": calibration_rows, "latency": latency_rows}


def add_latency_pareto(
    latency_rows: Sequence[Mapping[str, Any]],
    offline_cells: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    nll = {row["model_cell_id"]: float(row["heldout_rollout_macro_nll_mean"]) for row in offline_cells}
    joined = []
    for item in latency_rows:
        row = dict(item)
        row["heldout_rollout_macro_nll_mean"] = nll[row["model_cell_id"]]
        joined.append(row)
    for row in joined:
        dominated = any(
            other["mean_latency_ms"] <= row["mean_latency_ms"]
            and other["heldout_rollout_macro_nll_mean"] <= row["heldout_rollout_macro_nll_mean"]
            and (
                other["mean_latency_ms"] < row["mean_latency_ms"]
                or other["heldout_rollout_macro_nll_mean"] < row["heldout_rollout_macro_nll_mean"]
            )
            for other in joined
        )
        row["pareto_member"] = not dominated
        row["evidence_status"] = "validation_latency_and_retrospective_heldout_accuracy"
    return sorted(joined, key=lambda row: row["mean_latency_ms"])


def build_response_table(results_root: Path) -> list[dict[str, Any]]:
    reports = _discover_json(results_root, "postprocess/heldout", "heldout_metrics.json")
    _require(len(reports) == 27, "Expected 27 retrospective held-out reports")
    focus = {"head-large", "mlp-h1p0-large", "transformer-h1p0-large"}
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for report in reports:
        _require(report.get("status") == "pass", "A held-out evaluation did not pass")
        _require(
            report.get("evidence_status") == "retrospective_held_out",
            "Held-out evidence status drifted",
        )
        if report["model_cell_id"] not in focus:
            continue
        strata = report["calibrated"].get("response_strata_v3", {})
        for stratum in RESPONSE_STRATA:
            if stratum in strata:
                grouped[(report["model_cell_id"], stratum)].append(strata[stratum])
    rows = []
    for model in sorted(focus):
        for stratum in RESPONSE_STRATA:
            items = grouped.get((model, stratum), [])
            macro_keys = (
                "target_speed_profile_RMSE_mps",
                "response_onset_timing_error_s",
                "conflict_zone_entry_time_error_s",
                "conflict_zone_probability_mass",
            )
            row = {
                "model_cell_id": model,
                "response_stratum": stratum,
                "support_status": "observed" if items else "sparse_or_absent",
                "retained_seeds": len(items),
                "independent_init_groups": min(
                    (int(item["independent_init_groups"]) for item in items), default=0
                ),
                "independent_rollouts": min(
                    (int(item["independent_rollouts"]) for item in items), default=0
                ),
                "windows_mean": _mean(item["windows"] for item in items),
                "evidence_status": "retrospective_held_out",
            }
            for key in macro_keys:
                row[key] = _mean(item["rollout_macro"].get(key) for item in items)
            rows.append(row)
    return rows


def _svg_document(width: int, height: int, body: str, title: str, description: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title>
<desc id="desc">{escape(description)}</desc>
<style>
text {{ font-family: Helvetica, Arial, sans-serif; fill: #1f2937; }}
.axis {{ stroke: #374151; stroke-width: 1.2; }}
.grid {{ stroke: #d1d5db; stroke-width: 0.8; }}
.label {{ font-size: 13px; }}
.small {{ font-size: 12px; }}
.title {{ font-size: 17px; font-weight: 600; }}
.mlp {{ stroke: #c2410c; fill: #c2410c; }}
.transformer {{ stroke: #0369a1; fill: #0369a1; }}
.neutral {{ stroke: #4b5563; fill: #4b5563; }}
.series-line {{ fill: none; }}
</style>
{body}
</svg>
'''


def _linear(value: float, low: float, high: float, start: float, end: float) -> float:
    if high == low:
        return (start + end) / 2
    return start + (value - low) / (high - low) * (end - start)


def write_capacity_svg(path: Path, cells: Sequence[Mapping[str, Any]]) -> None:
    rows = sorted(
        (row for row in cells if row["model_cell_id"].startswith("transformer-h1p0")),
        key=lambda row: row["trainable_parameters"],
    )
    _require(len(rows) == 3, "Capacity plot requires small, medium, and large Transformer cells")
    width, height = 760, 440
    left, right, top, bottom = 92, 720, 55, 365
    ys = [float(row["heldout_rollout_macro_nll_mean"]) for row in rows]
    lower = [
        float(row["heldout_rollout_macro_nll_mean"])
        - float(row["heldout_rollout_macro_nll_seed_sd"])
        for row in rows
    ]
    upper = [
        float(row["heldout_rollout_macro_nll_mean"])
        + float(row["heldout_rollout_macro_nll_seed_sd"])
        for row in rows
    ]
    pad = max((max(upper) - min(lower)) * 0.12, 0.00015)
    y_low, y_high = min(lower) - pad, max(upper) + pad
    x_low, x_high = 0.12, 1.10
    parts = [
        '<text class="title" x="380" y="28" text-anchor="middle">Transformer capacity at 1.0 s history</text>',
        f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{bottom}"/>',
    ]
    for idx in range(5):
        value = y_low + idx * (y_high - y_low) / 4
        y = _linear(value, y_low, y_high, bottom, top)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="small" x="{left-10}" y="{y+4:.1f}" text-anchor="end">{value:.4f}</text>')
    points = []
    labels = ("Small", "Medium", "Large")
    for label, row in zip(labels, rows):
        x_val = float(row["trainable_parameters"]) / 1_000_000
        y_val = float(row["heldout_rollout_macro_nll_mean"])
        sd = float(row["heldout_rollout_macro_nll_seed_sd"])
        x = _linear(x_val, x_low, x_high, left, right)
        y = _linear(y_val, y_low, y_high, bottom, top)
        y1 = _linear(y_val - sd, y_low, y_high, bottom, top)
        y2 = _linear(y_val + sd, y_low, y_high, bottom, top)
        points.append(f"{x:.1f},{y:.1f}")
        parts.extend(
            [
                f'<line class="transformer" x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}"/>',
                f'<line class="transformer" x1="{x-5:.1f}" y1="{y1:.1f}" x2="{x+5:.1f}" y2="{y1:.1f}"/>',
                f'<line class="transformer" x1="{x-5:.1f}" y1="{y2:.1f}" x2="{x+5:.1f}" y2="{y2:.1f}"/>',
                f'<circle class="transformer" cx="{x:.1f}" cy="{y:.1f}" r="5"/>',
                f'<text class="small" x="{x:.1f}" y="{y-13:.1f}" text-anchor="middle">{label}: {y_val:.4f}</text>',
                f'<text class="small" x="{x:.1f}" y="{bottom+22}" text-anchor="middle">{x_val:.3f}M</text>',
            ]
        )
    parts.insert(3, f'<polyline class="transformer series-line" stroke-width="2" points="{" ".join(points)}"/>')
    parts.extend(
        [
            f'<text class="label" x="{(left+right)/2}" y="415" text-anchor="middle">Trainable parameters</text>',
            '<text class="label" transform="translate(24 210) rotate(-90)" text-anchor="middle">Retrospective held-out rollout-macro NLL (lower is better)</text>',
            '<text class="small" x="720" y="392" text-anchor="end">Error bars: seed SD; 5 independent groups</text>',
        ]
    )
    _atomic_text(
        path,
        _svg_document(
            width,
            height,
            "\n".join(parts),
            "Transformer capacity curve",
            "Small-to-large improvement is small and non-monotonic because the medium model has the lowest mean NLL.",
        ),
    )


def write_history_svg(path: Path, cells: Sequence[Mapping[str, Any]]) -> None:
    by_id = {row["model_cell_id"]: row for row in cells}
    series = {
        "MLP": [by_id[f"mlp-h{key}-large"] for key in ("0p0", "0p4", "1p0")],
        "Transformer": [by_id[f"transformer-h{key}-large"] for key in ("0p0", "0p4", "1p0")],
    }
    width, height = 760, 440
    left, right, top, bottom = 92, 720, 55, 365
    all_rows = [row for rows in series.values() for row in rows]
    lower = [
        float(row["heldout_rollout_macro_nll_mean"])
        - float(row["heldout_rollout_macro_nll_seed_sd"])
        for row in all_rows
    ]
    upper = [
        float(row["heldout_rollout_macro_nll_mean"])
        + float(row["heldout_rollout_macro_nll_seed_sd"])
        for row in all_rows
    ]
    pad = max((max(upper) - min(lower)) * 0.10, 0.00025)
    y_low, y_high = min(lower) - pad, max(upper) + pad
    parts = [
        '<text class="title" x="380" y="28" text-anchor="middle">Matched large encoders across trained history horizons</text>',
        f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{bottom}"/>',
    ]
    for idx in range(5):
        value = y_low + idx * (y_high - y_low) / 4
        y = _linear(value, y_low, y_high, bottom, top)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="small" x="{left-10}" y="{y+4:.1f}" text-anchor="end">{value:.4f}</text>')
    horizons = (0.0, 0.4, 1.0)
    for name, rows in series.items():
        css = "mlp" if name == "MLP" else "transformer"
        points = []
        for horizon, row in zip(horizons, rows):
            x = _linear(horizon, 0.0, 1.0, left, right)
            value = float(row["heldout_rollout_macro_nll_mean"])
            sd = float(row["heldout_rollout_macro_nll_seed_sd"])
            y = _linear(value, y_low, y_high, bottom, top)
            y1 = _linear(value - sd, y_low, y_high, bottom, top)
            y2 = _linear(value + sd, y_low, y_high, bottom, top)
            points.append(f"{x:.1f},{y:.1f}")
            parts.extend(
                [
                    f'<line class="{css}" x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}"/>',
                    f'<circle class="{css}" cx="{x:.1f}" cy="{y:.1f}" r="5"/>',
                    f'<text class="small" x="{x:.1f}" y="{y-12:.1f}" text-anchor="middle">{value:.4f}</text>',
                ]
            )
        parts.append(f'<polyline class="{css} series-line" stroke-width="2" points="{" ".join(points)}"/>')
    for horizon in horizons:
        x = _linear(horizon, 0.0, 1.0, left, right)
        parts.append(f'<text class="small" x="{x:.1f}" y="{bottom+22}" text-anchor="middle">{horizon:.1f}</text>')
    parts.extend(
        [
            '<line class="mlp" x1="540" y1="52" x2="572" y2="52" stroke-width="2"/><text class="small" x="580" y="56">MLP</text>',
            '<line class="transformer" x1="630" y1="52" x2="662" y2="52" stroke-width="2"/><text class="small" x="670" y="56">Transformer</text>',
            f'<text class="label" x="{(left+right)/2}" y="415" text-anchor="middle">Trained explicit interaction history (s)</text>',
            '<text class="label" transform="translate(24 210) rotate(-90)" text-anchor="middle">Retrospective held-out rollout-macro NLL</text>',
        ]
    )
    _atomic_text(
        path,
        _svg_document(
            width,
            height,
            "\n".join(parts),
            "History horizon and encoder comparison",
            "Both encoders improve by 0.4 seconds. Transformer remains better at every horizon, while its history gain is not larger than the MLP history gain.",
        ),
    )


def write_history_gain_svg(path: Path, offline: Mapping[str, Any]) -> None:
    primary = {row["contrast_id"]: row for row in offline["three_axes"]["primary_contrasts"]}
    records = [
        ("MLP history gain", primary["H2_information_mlp_snapshot_minus_full"]),
        ("Transformer history gain", primary["H2_information_transformer_snapshot_minus_full"]),
        ("Attention-specific DID", primary["H3_attention_history_gain_difference_in_differences"]),
    ]
    width, height = 760, 420
    left, right, top, bottom = 220, 710, 58, 330
    low = min(float(row["cluster_interval_95"][0]) for _, row in records) - 0.0005
    high = max(float(row["cluster_interval_95"][1]) for _, row in records) + 0.0005
    zero = _linear(0.0, low, high, left, right)
    parts = [
        '<text class="title" x="380" y="28" text-anchor="middle">History gains and attention-specific interaction</text>',
        f'<line class="grid" x1="{zero:.1f}" y1="{top}" x2="{zero:.1f}" y2="{bottom}" stroke-width="1.5"/>',
        f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"/>',
    ]
    for tick_idx in range(6):
        value = low + tick_idx * (high - low) / 5
        x = _linear(value, low, high, left, right)
        parts.append(f'<line class="axis" x1="{x:.1f}" y1="{bottom}" x2="{x:.1f}" y2="{bottom+5}"/>')
        parts.append(f'<text class="small" x="{x:.1f}" y="{bottom+22}" text-anchor="middle">{value:+.3f}</text>')
    for idx, (label, row) in enumerate(records):
        y = 100 + idx * 86
        effect = float(row["effect"])
        lo, hi = (float(value) for value in row["cluster_interval_95"])
        xe, xl, xh = (
            _linear(value, low, high, left, right) for value in (effect, lo, hi)
        )
        css = "transformer" if idx == 1 else "mlp" if idx == 0 else "neutral"
        parts.extend(
            [
                f'<text class="small" x="{left-12}" y="{y+4}" text-anchor="end">{escape(label)}</text>',
                f'<line class="{css}" x1="{xl:.1f}" y1="{y}" x2="{xh:.1f}" y2="{y}" stroke-width="2"/>',
                f'<line class="{css}" x1="{xl:.1f}" y1="{y-5}" x2="{xl:.1f}" y2="{y+5}"/>',
                f'<line class="{css}" x1="{xh:.1f}" y1="{y-5}" x2="{xh:.1f}" y2="{y+5}"/>',
                f'<circle class="{css}" cx="{xe:.1f}" cy="{y}" r="5"/>',
                f'<text class="small" x="{xe:.1f}" y="{y-12}" text-anchor="middle">{effect:+.4f}</text>',
            ]
        )
    parts.extend(
        [
            '<text class="label" x="465" y="392" text-anchor="middle">NLL gain (positive favours preregistered direction)</text>',
            '<text class="small" x="710" y="371" text-anchor="end">95% paired-group cluster intervals; 5 groups</text>',
        ]
    )
    _atomic_text(
        path,
        _svg_document(
            width,
            height,
            "\n".join(parts),
            "History gain interaction",
            "Both encoder history gains are positive, while the attention-specific difference-in-differences crosses zero.",
        ),
    )


def write_latency_pareto_svg(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _require(len(rows) == 9, "Latency Pareto plot requires nine model cells")
    width, height = 820, 470
    left, right, top, bottom = 88, 775, 55, 390
    x_values = [float(row["mean_latency_ms"]) for row in rows]
    y_values = [float(row["heldout_rollout_macro_nll_mean"]) for row in rows]
    x_pad = max((max(x_values) - min(x_values)) * 0.10, 1.0)
    y_pad = max((max(y_values) - min(y_values)) * 0.10, 0.001)
    x_low, x_high = min(x_values) - x_pad, max(x_values) + x_pad
    y_low, y_high = min(y_values) - y_pad, max(y_values) + y_pad
    parts = [
        '<text class="title" x="410" y="28" text-anchor="middle">Accuracy-latency trade-off</text>',
        f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{bottom}"/>',
    ]
    for idx in range(5):
        xv = x_low + idx * (x_high - x_low) / 4
        x = _linear(xv, x_low, x_high, left, right)
        parts.append(f'<text class="small" x="{x:.1f}" y="{bottom+22}" text-anchor="middle">{xv:.1f}</text>')
        yv = y_low + idx * (y_high - y_low) / 4
        y = _linear(yv, y_low, y_high, bottom, top)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="small" x="{left-9}" y="{y+4:.1f}" text-anchor="end">{yv:.3f}</text>')
    label_layout = {
        "head-large": (8, -10, "start"),
        "mlp-h0p0-large": (8, -8, "start"),
        "mlp-h0p4-large": (8, -8, "start"),
        "mlp-h1p0-large": (8, -8, "start"),
        "transformer-h0p0-large": (8, -8, "start"),
        "transformer-h0p4-large": (-8, -12, "end"),
        "transformer-h1p0-large": (-8, 18, "end"),
        "transformer-h1p0-medium": (8, 18, "start"),
        "transformer-h1p0-small": (8, -10, "start"),
    }
    for row in rows:
        x = _linear(float(row["mean_latency_ms"]), x_low, x_high, left, right)
        y = _linear(float(row["heldout_rollout_macro_nll_mean"]), y_low, y_high, bottom, top)
        model = str(row["model_cell_id"])
        css = "transformer" if model.startswith("transformer") else "mlp" if model.startswith("mlp") else "neutral"
        radius = 7 if row["pareto_member"] else 4
        parts.append(f'<circle class="{css}" cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill-opacity="{1.0 if row["pareto_member"] else 0.55}"/>')
        short = model.replace("transformer-", "T-").replace("mlp-", "M-").replace("head-large", "B1")
        dx, dy, anchor = label_layout[model]
        parts.append(f'<text class="small" x="{x+dx:.1f}" y="{y+dy:.1f}" text-anchor="{anchor}">{escape(short)}</text>')
    parts.extend(
        [
            f'<text class="label" x="{(left+right)/2}" y="448" text-anchor="middle">Warmed batch-one mean latency (ms; lower is better)</text>',
            '<text class="label" transform="translate(22 225) rotate(-90)" text-anchor="middle">Retrospective held-out NLL (lower is better)</text>',
            '<text class="small" x="775" y="420" text-anchor="end">Larger markers are nondominated within the nine-cell study</text>',
        ]
    )
    _atomic_text(
        path,
        _svg_document(
            width,
            height,
            "\n".join(parts),
            "Accuracy latency Pareto plot",
            "Nine model cells plotted by warmed batch-one mean latency and retrospective held-out NLL; larger markers identify the bounded Pareto frontier.",
        ),
    )


def _find_contrast(rows: Sequence[Mapping[str, Any]], identifier: str) -> Mapping[str, Any]:
    for row in rows:
        if row["contrast_id"] == identifier:
            return row
    raise ValueError(f"Missing contrast: {identifier}")


def write_closed_loop_svg(path: Path, closed: Mapping[str, Any]) -> None:
    within = closed["within_risk_contrasts"]
    interactions = closed["model_by_risk_interactions"]
    panels = [
        ("completion_time_s", "Completion time (s)", -1.05, 0.65),
        ("min_footprint_separation_m", "Minimum separation (m)", -0.045, 0.080),
    ]
    width, height = 840, 440
    parts = ['<text class="title" x="420" y="27" text-anchor="middle">P* versus B1 within risk and model-by-risk interaction</text>']
    labels = ("Fixed medium", "Adaptive", "Interaction")
    for panel_idx, (metric, title, x_low, x_high) in enumerate(panels):
        x0 = 92 + panel_idx * 405
        x1 = x0 + 315
        y0, y1 = 78, 330
        parts.append(f'<text class="label" x="{(x0+x1)/2}" y="54" text-anchor="middle">{escape(title)}</text>')
        zero = _linear(0.0, x_low, x_high, x0, x1)
        parts.append(f'<line class="grid" x1="{zero:.1f}" y1="{y0}" x2="{zero:.1f}" y2="{y1}" stroke-width="1.5"/>')
        for tick_idx in range(5):
            value = x_low + tick_idx * (x_high - x_low) / 4
            x = _linear(value, x_low, x_high, x0, x1)
            parts.append(f'<line class="axis" x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y1+5}"/>')
            parts.append(f'<text class="small" x="{x:.1f}" y="{y1+21}" text-anchor="middle">{value:.2f}</text>')
        records = [
            _find_contrast(within, f"{metric}__P_star_minus_B1__fixed_medium"),
            _find_contrast(within, f"{metric}__P_star_minus_B1__adaptive"),
            _find_contrast(interactions, f"{metric}__model_by_risk__adaptive_minus_fixed_medium"),
        ]
        for idx, (label, row) in enumerate(zip(labels, records)):
            y = 120 + idx * 82
            effect = float(row["effect_P_star_minus_B1"])
            low, high = (float(v) for v in row["cluster_interval_95"])
            xe = _linear(effect, x_low, x_high, x0, x1)
            xl = _linear(low, x_low, x_high, x0, x1)
            xh = _linear(high, x_low, x_high, x0, x1)
            parts.extend(
                [
                    f'<text class="small" x="{x0-8}" y="{y+4}" text-anchor="end">{escape(label)}</text>',
                    f'<line class="neutral" x1="{xl:.1f}" y1="{y}" x2="{xh:.1f}" y2="{y}" stroke-width="2"/>',
                    f'<line class="neutral" x1="{xl:.1f}" y1="{y-5}" x2="{xl:.1f}" y2="{y+5}"/>',
                    f'<line class="neutral" x1="{xh:.1f}" y1="{y-5}" x2="{xh:.1f}" y2="{y+5}"/>',
                    f'<circle class="neutral" cx="{xe:.1f}" cy="{y}" r="5"/>',
                    f'<text class="small" x="{xe:.1f}" y="{y-11}" text-anchor="middle">{effect:+.3f}</text>',
                ]
            )
        parts.append(f'<line class="axis" x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}"/>')
    parts.append('<text class="small" x="420" y="410" text-anchor="middle">Effects are P* minus B1; interaction is adaptive minus fixed-medium. Bars are paired-group 95% cluster intervals (10 groups).</text>')
    _atomic_text(
        path,
        _svg_document(
            width,
            height,
            "\n".join(parts),
            "Closed-loop model-by-risk contrasts",
            "Intervals for completion time, minimum separation, and their model-by-risk interactions cross zero.",
        ),
    )


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "undefined"
    return f"{float(value):.{digits}f}"


def _scalar_unit(field: str) -> str:
    lowered = field.lower()
    if "nll" in lowered:
        return "nats per valid prediction step"
    if lowered.endswith("_ms") or "latency_ms" in lowered:
        return "milliseconds"
    if lowered.endswith("_s") or "time_s" in lowered:
        return "seconds"
    if lowered.endswith("_m") or "ade_m" in lowered or "separation_m" in lowered:
        return "metres"
    if lowered.endswith("_mps"):
        return "metres per second"
    if any(token in lowered for token in ("fraction", "rate", "probability", "temperature", "scale", "_p")):
        return "unitless"
    if any(token in lowered for token in ("parameters", "rollouts", "groups", "seeds", "windows", "count")):
        return "count"
    return "unitless"


def build_scalar_index(
    tables: Mapping[str, Sequence[Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    source_map = {
        "offline_cells": "postprocess/offline_synthesis.json",
        "offline_contrasts": "postprocess/offline_synthesis.json",
        "response_strata": "postprocess/heldout/*/heldout_metrics.json",
        "calibration": "postprocess/calibration/*/calibration.json",
        "latency": "postprocess/latency/*/latency.json",
        "closed_loop_cells": "closed_loop/closed_loop_rows.json",
        "closed_loop_contrasts": "closed_loop/PREDICTOR_BY_RISK_SYNTHESIS.json",
        "b1_allocation": "postprocess/offline_synthesis.json",
    }
    table_filename_map = {
        "offline_cells": "table_offline_model_cells.csv",
        "offline_contrasts": "table_three_axis_contrasts.csv",
        "response_strata": "table_response_strata.csv",
        "calibration": "table_calibration_summary.csv",
        "latency": "table_latency_summary.csv",
        "closed_loop_cells": "table_closed_loop_cells.csv",
        "closed_loop_contrasts": "table_model_by_risk_contrasts.csv",
        "b1_allocation": "table_b1_adaptation_allocation.csv",
    }
    identifiers = (
        "model_cell_id",
        "contrast_id",
        "predictor",
        "risk_policy",
        "response_stratum",
        "category",
    )
    output: list[dict[str, Any]] = []
    for table_id, rows in tables.items():
        for row_index, row in enumerate(rows):
            identity = ";".join(
                f"{key}={row[key]}" for key in identifiers if row.get(key) not in (None, "")
            ) or f"row={row_index}"
            independent_units = row.get("independent_groups")
            if independent_units is None:
                independent_units = row.get("independent_init_groups")
            if independent_units is None:
                independent_units = row.get("retained_seeds")
            evidence_status = row.get("evidence_status")
            if evidence_status is None:
                evidence_status = (
                    "formal_closed_loop" if table_id.startswith("closed_loop")
                    else "validation_only" if table_id in {"calibration", "latency"}
                    else "retrospective_held_out"
                )
            for field, value in row.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if isinstance(value, float) and not math.isfinite(value):
                    continue
                unit_field = (
                    str(row.get("metric", field))
                    if field in {"effect", "ci95_low", "ci95_high"}
                    else field
                )
                output.append(
                    {
                        "scalar_id": f"{table_id}:{identity}:{field}",
                        "generated_table": table_filename_map[table_id],
                        "row_identity": identity,
                        "field": field,
                        "value": value,
                        "unit": _scalar_unit(unit_field),
                        "estimator": (
                            "paired initialisation-group contrast"
                            if "contrast" in table_id
                            else "macro mean over declared grouping unit"
                        ),
                        "independent_unit_count": independent_units,
                        "evidence_status": evidence_status,
                        "source_artifact": source_map[table_id],
                        "source_field": f"{identity}.{field}",
                    }
                )
    return output


def build_claims(offline: Mapping[str, Any], closed: Mapping[str, Any]) -> list[dict[str, Any]]:
    primary = {row["contrast_id"]: row for row in offline["three_axes"]["primary_contrasts"]}
    direct = {row["contrast_id"]: row for row in offline["direct_architecture_contrasts"]}
    supporting = {row["contrast_id"]: row for row in offline["supporting_contrasts"]}
    h1 = primary["H1_capacity_transformer_full_small_minus_large"]
    hm = primary["H2_information_mlp_snapshot_minus_full"]
    ht = primary["H2_information_transformer_snapshot_minus_full"]
    h3 = primary["H3_attention_history_gain_difference_in_differences"]
    arch0 = direct["architecture_direct_mlp_minus_transformer__h0p0__large"]
    arch1 = direct["architecture_direct_mlp_minus_transformer__h1p0__large"]
    b1t = supporting["B1_minus_transformer_full_large"]
    completion = _find_contrast(
        closed["model_by_risk_interactions"],
        "completion_time_s__model_by_risk__adaptive_minus_fixed_medium",
    )
    separation = _find_contrast(
        closed["model_by_risk_interactions"],
        "min_footprint_separation_m__model_by_risk__adaptive_minus_fixed_medium",
    )
    ade_fixed = _find_contrast(
        closed["within_risk_contrasts"],
        "inloop_top1_ADE_m__P_star_minus_B1__fixed_medium",
    )
    return [
        {
            "claim_id": "C1_capacity",
            "axis": "capacity",
            "status": "directional_but_not_confirmed",
            "text": (
                f"At 1.0 s history, small-to-large Transformer scaling changed rollout-macro NLL by "
                f"{_fmt(h1['effect'], 6)} in the preregistered direction, but the tier ordering was "
                f"non-monotonic and the Holm-adjusted p value was {_fmt(h1['holm_adjusted_p'], 3)}. "
                "The data therefore do not support a strong capacity-limitation explanation."
            ),
            "evidence_ids": [h1["contrast_id"], "capacity_transformer_full_medium_minus_large"],
            "source_fields": [
                {"artifact": "offline_synthesis.json", "field": "three_axes.primary_contrasts[H1].effect", "unit": "NLL per step"},
                {"artifact": "table_offline_model_cells.csv", "field": "Transformer tier means", "unit": "NLL per step"},
            ],
        },
        {
            "claim_id": "C2_information",
            "axis": "information",
            "status": "consistent_directional_retrospective_evidence",
            "text": (
                f"Training with 1.0 s rather than current-token-only interaction input improved NLL by "
                f"{_fmt(hm['effect'], 6)} for the MLP and {_fmt(ht['effect'], 6)} for the Transformer. "
                "All five paired groups had the preregistered direction, while exact multiplicity-adjusted "
                "tests remained underpowered; the 0.4 s condition captured nearly all of the gain."
            ),
            "evidence_ids": [hm["contrast_id"], ht["contrast_id"], "trained_horizon_0p4_support"],
            "source_fields": [
                {"artifact": "offline_synthesis.json", "field": "three_axes.primary_contrasts[H2]", "unit": "NLL per step"},
                {"artifact": "figure_history_architecture.svg", "field": "trained horizon curves", "unit": "NLL per step"},
            ],
        },
        {
            "claim_id": "C3_architecture",
            "axis": "architecture",
            "status": "generic_encoder_advantage_not_attention_specific",
            "text": (
                f"The matched Transformer reduced NLL relative to the MLP at both 0.0 s "
                f"({_fmt(arch0['effect'], 6)}) and 1.0 s ({_fmt(arch1['effect'], 6)}). "
                f"However, its history gain was not larger (difference-in-differences "
                f"{_fmt(h3['effect'], 6)}, 95% interval {_fmt(h3['cluster_interval_95'][0], 6)} to "
                f"{_fmt(h3['cluster_interval_95'][1], 6)}), so the evidence supports a bounded encoder-family "
                "advantage, not an attention-specific extraction advantage."
            ),
            "evidence_ids": [arch0["contrast_id"], arch1["contrast_id"], h3["contrast_id"]],
            "source_fields": [
                {"artifact": "offline_synthesis.json", "field": "direct_architecture_contrasts", "unit": "NLL per step"},
                {"artifact": "offline_synthesis.json", "field": "three_axes.primary_contrasts[H3]", "unit": "NLL per step"},
            ],
        },
        {
            "claim_id": "C4_adaptation_allocation",
            "axis": "adaptation_allocation",
            "status": "complete_configuration_result",
            "text": (
                f"Large B1 had higher retrospective held-out NLL than the matched full-history Transformer by "
                f"{_fmt(b1t['effect'], 6)}. This compares complete task-adaptation allocations and is not a "
                "pure architecture effect."
            ),
            "evidence_ids": [b1t["contrast_id"]],
            "source_fields": [
                {"artifact": "offline_synthesis.json", "field": "supporting_contrasts[B1_minus_transformer_full_large]", "unit": "NLL per step"}
            ],
        },
        {
            "claim_id": "C5_predictor_risk",
            "axis": "predictor_risk",
            "status": "no_demonstrated_physical_moderation",
            "text": (
                f"The model-by-risk interaction was {_fmt(completion['effect_P_star_minus_B1'], 3)} s for "
                f"completion time and {_fmt(separation['effect_P_star_minus_B1'], 3)} m for minimum separation; "
                "both paired-group intervals crossed zero. P* improved in-loop top-1 ADE under fixed-medium risk "
                f"by {_fmt(-ade_fixed['effect_P_star_minus_B1'], 3)} m, but this predictive difference did not "
                "produce a demonstrated change in the co-primary physical outcomes."
            ),
            "evidence_ids": ["model_by_risk_interactions", "within_risk_contrasts"],
            "source_fields": [
                {"artifact": "PREDICTOR_BY_RISK_SYNTHESIS.json", "field": "model_by_risk_interactions", "unit": "seconds or metres"},
                {"artifact": "PREDICTOR_BY_RISK_SYNTHESIS.json", "field": "within_risk_contrasts[inloop_top1_ADE_m]", "unit": "metres"},
            ],
        },
    ]


def _result_markdown(
    claims: Sequence[Mapping[str, Any]],
    offline: Mapping[str, Any],
    audit: Mapping[str, Any],
    gate: Mapping[str, Any],
) -> str:
    lines = [
        "# Capacity–Information–Architecture V3: results and claim boundary",
        "",
        "## Evidence gates",
        "",
        f"- Offline training: {audit['valid_runs']}/{audit['planned_runs']} valid runs; "
        f"maximum cached/full absolute error {audit['maximum_cached_full_absolute_error']:.3g}.",
        f"- Retrospective held-out evaluation: {offline['evaluated_runs']} retained runs over "
        f"{offline['independent_init_groups']} independent groups (41--45).",
        f"- Formal CARLA matrix: {gate['observed_rollouts']}/80 rollout gates passed.",
        f"- Convergence: {audit['boundary_limited_runs']} boundary-limited runs; no post-outcome budget extension.",
        "",
        "## Claim-safe conclusions",
        "",
    ]
    for index, claim in enumerate(claims, 1):
        lines.extend([f"### {index}. {claim['axis'].replace('_', ' ').title()}", "", claim["text"], ""])
    lines.extend(
        [
            "## Evidence boundary",
            "",
            offline["claim_boundary"],
            "The five-group offline exact tests have coarse attainable p values, so interval direction and "
            "paired consistency are reported alongside multiplicity-adjusted decisions. Zero observed collisions "
            "do not establish equality between configurations or license a broader conclusion outside this matrix.",
            "",
        ]
    )
    return "\n".join(lines)


def write_final_package(
    *, results_root: Path, output_dir: Path
) -> dict[str, Any]:
    offline_path = results_root / "postprocess/offline_synthesis.json"
    audit_path = results_root / "postprocess/training_audit.json"
    freeze_path = results_root / "postprocess/selection_freeze.json"
    closed_path = results_root / "closed_loop/PREDICTOR_BY_RISK_SYNTHESIS.json"
    closed_rows_path = results_root / "closed_loop/closed_loop_rows.json"
    gate_path = results_root / "closed_loop/CLOSED_LOOP_COMPLETE.json"
    evidence = validate_evidence_chain(
        offline_path=offline_path,
        audit_path=audit_path,
        freeze_path=freeze_path,
        closed_loop_path=closed_path,
        closed_loop_rows_path=closed_rows_path,
        closed_loop_gate_path=gate_path,
    )
    offline_tables = build_offline_tables(evidence["offline"])
    closed_tables = build_closed_loop_tables(evidence["closed"], evidence["closed_rows"])
    calibration_latency = build_calibration_latency_tables(results_root)
    latency_pareto = add_latency_pareto(calibration_latency["latency"], offline_tables["cells"])
    b1_allocation = build_b1_allocation_table(evidence["offline"])
    response_rows = build_response_table(results_root)
    claims = build_claims(evidence["offline"], evidence["closed"])

    output_dir.mkdir(parents=True, exist_ok=True)
    table_paths = {
        "offline_cells": output_dir / "table_offline_model_cells.csv",
        "offline_contrasts": output_dir / "table_three_axis_contrasts.csv",
        "response_strata": output_dir / "table_response_strata.csv",
        "calibration": output_dir / "table_calibration_summary.csv",
        "latency": output_dir / "table_latency_summary.csv",
        "closed_loop_cells": output_dir / "table_closed_loop_cells.csv",
        "closed_loop_contrasts": output_dir / "table_model_by_risk_contrasts.csv",
        "b1_allocation": output_dir / "table_b1_adaptation_allocation.csv",
    }
    _write_csv(table_paths["offline_cells"], offline_tables["cells"])
    _write_csv(table_paths["offline_contrasts"], offline_tables["contrasts"])
    _write_csv(table_paths["response_strata"], response_rows)
    _write_csv(table_paths["calibration"], calibration_latency["calibration"])
    _write_csv(table_paths["latency"], latency_pareto)
    _write_csv(table_paths["closed_loop_cells"], closed_tables["cells"])
    _write_csv(table_paths["closed_loop_contrasts"], closed_tables["contrasts"])
    _write_csv(table_paths["b1_allocation"], b1_allocation)
    scalar_tables = {
        "offline_cells": offline_tables["cells"],
        "offline_contrasts": offline_tables["contrasts"],
        "response_strata": response_rows,
        "calibration": calibration_latency["calibration"],
        "latency": latency_pareto,
        "closed_loop_cells": closed_tables["cells"],
        "closed_loop_contrasts": closed_tables["contrasts"],
        "b1_allocation": b1_allocation,
    }
    scalar_index_path = output_dir / "scalar_provenance_index.csv"
    _write_csv(scalar_index_path, build_scalar_index(scalar_tables))
    table_paths["scalar_provenance"] = scalar_index_path

    figure_paths = {
        "capacity": output_dir / "figure_capacity_curve.svg",
        "history_architecture": output_dir / "figure_history_architecture.svg",
        "model_by_risk": output_dir / "figure_model_by_risk.svg",
        "history_gain_interaction": output_dir / "figure_history_gain_interaction.svg",
        "latency_pareto": output_dir / "figure_latency_pareto.svg",
    }
    write_capacity_svg(figure_paths["capacity"], offline_tables["cells"])
    write_history_svg(figure_paths["history_architecture"], offline_tables["cells"])
    write_closed_loop_svg(figure_paths["model_by_risk"], evidence["closed"])
    write_history_gain_svg(figure_paths["history_gain_interaction"], evidence["offline"])
    write_latency_pareto_svg(figure_paths["latency_pareto"], latency_pareto)

    results_markdown = output_dir / "RESULTS_AND_CLAIMS.md"
    _atomic_text(
        results_markdown,
        _result_markdown(claims, evidence["offline"], evidence["audit"], evidence["gate"]),
    )
    source_paths = {
        "offline_synthesis": offline_path,
        "training_audit": audit_path,
        "selection_freeze": freeze_path,
        "closed_loop_synthesis": closed_path,
        "closed_loop_rows": closed_rows_path,
        "closed_loop_gate": gate_path,
    }
    index = {
        "schema_version": "capacity_history_dissertation_evidence_v3_final",
        "status": "pass",
        "numeric_prose_allowed": True,
        "evidence_status": {
            "offline": "retrospective_held_out",
            "closed_loop": "formal_closed_loop",
        },
        "source_artifacts": {
            key: {"path": str(path), "sha256": sha256_file(path)}
            for key, path in source_paths.items()
        },
        "generated_artifacts": {},
        "claims": claims,
        "limitations": [
            "Offline inference has five independent groups and is retrospective held-out evidence.",
            "The 0.4 s condition captures most history gain; 1.0 s is not uniformly best.",
            "Direct Transformer advantages do not identify attention-specific history use without a favourable history-gain interaction.",
            "Completion rate was undefined in the closed-loop export, so completion time and minimum separation remain the co-primary estimable outcomes.",
            "Zero observed collisions do not establish equality or generalize beyond the 80-rollout matrix.",
        ],
    }
    for key, path in {**table_paths, **figure_paths, "results_markdown": results_markdown}.items():
        index["generated_artifacts"][key] = {
            "path": str(path),
            "sha256": sha256_file(path),
        }
    for key, svg_path in figure_paths.items():
        png_path = svg_path.with_suffix(".png")
        if png_path.is_file():
            index["generated_artifacts"][f"{key}_png"] = {
                "path": str(png_path),
                "sha256": sha256_file(png_path),
                "derived_from": key,
            }
    index_path = output_dir / "evidence_index.json"
    _atomic_json(index_path, index)
    return {
        "status": "pass",
        "numeric_prose_allowed": True,
        "claims": len(claims),
        "tables": len(table_paths),
        "figures": len(figure_paths),
        "evidence_index": str(index_path),
        "evidence_index_sha256": sha256_file(index_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(write_final_package(results_root=args.results_root, output_dir=args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
