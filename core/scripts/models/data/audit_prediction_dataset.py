#!/usr/bin/env python3
"""Audit a merged CARLA prediction dataset before model training.

The audit is intentionally independent of TensorFlow.  It verifies grouped
splits, sample identity, label horizons, raster assets, per-rollout manifests,
and basic ego/target/context distributions.  The machine-readable report is
the Day 2 gate for the legacy give-way prediction dataset.
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
import collections
import hashlib
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from prediction_dataset_utils import infer_init_id, resolve_raster_path, split_for_init


SPLITS = ("train", "val", "test")
CONTEXT_FIELDS = (
    "ego_rel_x_target_local_m",
    "ego_rel_y_target_local_m",
    "ego_speed_mps",
    "target_speed_mps",
    "ego_minus_target_speed_mps",
    "sin_relative_yaw",
    "cos_relative_yaw",
    "ego_target_distance_m",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-dir", required=True)
    parser.add_argument("--result-dir", default=None)
    parser.add_argument("--output-json", required=True)
    parser.add_argument(
        "--rollout-manifests-json",
        default=None,
        help="Optional consolidated rollout manifest JSON for metadata-only local reruns.",
    )
    parser.add_argument("--expected-horizon", type=int, default=10)
    parser.add_argument("--expected-dt", type=float, default=0.2)
    parser.add_argument("--check-rasters", action="store_true")
    parser.add_argument("--check-raster-content", action="store_true")
    parser.add_argument("--raster-content-samples", type=int, default=200)
    parser.add_argument("--ego-pixel-radius", type=int, default=25)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def numeric_summary(values: Iterable[Any]) -> Dict[str, Any]:
    clean = [value for value in (finite_float(item) for item in values) if value is not None]
    if not clean:
        return {"count": 0, "mean": None, "std": None, "min": None, "p50": None, "p95": None, "max": None}
    ordered = sorted(clean)

    def percentile(percent: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        position = (len(ordered) - 1) * percent / 100.0
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return ordered[lower]
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    return {
        "count": len(clean),
        "mean": statistics.fmean(clean),
        "std": statistics.pstdev(clean) if len(clean) > 1 else 0.0,
        "min": ordered[0],
        "p50": percentile(50.0),
        "p95": percentile(95.0),
        "max": ordered[-1],
    }


def read_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise TypeError(f"expected object, got {type(value).__name__}")
                rows.append(value)
            except (json.JSONDecodeError, TypeError) as exc:
                if len(errors) < 25:
                    errors.append({"line": line_number, "error": str(exc)})
    return rows, errors


def composite_id(sample: Mapping[str, Any]) -> str:
    return f"{sample.get('source_subrun', '<missing>')}::{sample.get('sample_id', '<missing>')}"


def future_stage(sample: Mapping[str, Any], horizon: int) -> str:
    mask = sample.get("future_valid_mask")
    future = sample.get("future_xy_world")
    if not isinstance(mask, list) or not isinstance(future, list):
        return "malformed"
    valid = 0
    for index in range(min(horizon, len(mask), len(future))):
        point = future[index]
        if mask[index] and isinstance(point, list) and len(point) >= 2:
            if finite_float(point[0]) is not None and finite_float(point[1]) is not None:
                valid += 1
    if valid == horizon:
        return "full_horizon"
    if valid > 0:
        return "any_future_label"
    return "raw_only"


def add_check(checks: List[Dict[str, Any]], name: str, passed: bool, details: Any) -> None:
    checks.append({"name": name, "status": "pass" if passed else "fail", "details": details})


def expected_init_ids(split: str) -> set[int]:
    if split == "train":
        return set(range(1, 41))
    if split == "val":
        return set(range(41, 46))
    if split == "test":
        return set(range(46, 51))
    raise ValueError(split)


def inspect_raster_content(
    samples: Sequence[Mapping[str, Any]],
    result_dir: Path,
    limit: int,
    radius: int,
) -> Dict[str, Any]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        return {
            "available": False,
            "error": f"OpenCV/NumPy unavailable: {exc}",
            "eligible": 0,
            "ego_vehicle_colour_hits": 0,
        }

    inspected = 0
    eligible = 0
    hits = 0
    failures: List[Dict[str, Any]] = []
    for sample in samples:
        if inspected >= limit:
            break
        context = sample.get("interaction_context")
        if not isinstance(context, list) or len(context) < 2:
            continue
        rel_x = finite_float(context[0])
        rel_y = finite_float(context[1])
        raster_path = resolve_raster_path(dict(sample), result_dir=str(result_dir))
        if rel_x is None or rel_y is None or not raster_path or not os.path.isfile(raster_path):
            continue
        image = cv2.imread(raster_path, cv2.IMREAD_COLOR)
        if image is None:
            continue
        inspected += 1
        # Frozen SemBoxRasterizer: 0.1 m/pixel, target centre=(100, 250).
        pixel_x = int(round(100.0 + rel_x / 0.1))
        pixel_y = int(round(250.0 - rel_y / 0.1))
        if not (0 <= pixel_x < image.shape[1] and 0 <= pixel_y < image.shape[0]):
            continue
        eligible += 1
        y0, y1 = max(0, pixel_y - radius), min(image.shape[0], pixel_y + radius + 1)
        x0, x1 = max(0, pixel_x - radius), min(image.shape[1], pixel_x + radius + 1)
        patch = image[y0:y1, x0:x1]
        # BoxRasterizer uses [255, 255, 0] for non-target vehicles at t=0.
        yellow_count = int(np.count_nonzero(np.all(patch == np.asarray([255, 255, 0]), axis=2)))
        if yellow_count > 0:
            hits += 1
        elif len(failures) < 20:
            failures.append(
                {
                    "sample": composite_id(sample),
                    "expected_pixel": [pixel_x, pixel_y],
                    "raster": raster_path,
                }
            )
    return {
        "available": True,
        "inspected": inspected,
        "eligible": eligible,
        "ego_vehicle_colour_hits": hits,
        "hit_rate": (hits / eligible) if eligible else None,
        "failures": failures,
        "method": "yellow vehicle-layer pixels near ego centre projected into target-local raster",
    }


def distribution_report(rows: Sequence[Mapping[str, Any]], horizon: int) -> Dict[str, Any]:
    values: MutableMapping[str, List[float]] = collections.defaultdict(list)
    context_dims: collections.Counter[int] = collections.Counter()
    past_lengths: collections.Counter[int] = collections.Counter()
    future_valid_counts: collections.Counter[int] = collections.Counter()
    for sample in rows:
        ego = sample.get("ego_state") or {}
        target = sample.get("target_state") or {}
        values["ego_speed_mps"].append(ego.get("speed"))
        values["target_speed_mps"].append(target.get("speed"))
        context = sample.get("interaction_context")
        if isinstance(context, list):
            context_dims[len(context)] += 1
            for field, value in zip(CONTEXT_FIELDS, context):
                values[f"context.{field}"].append(value)
        past = sample.get("past_states_local")
        if isinstance(past, list):
            past_lengths[len(past)] += 1
        mask = sample.get("future_valid_mask")
        if isinstance(mask, list):
            future_valid_counts[sum(bool(value) for value in mask[:horizon])] += 1

        future = sample.get("future_xy_world")
        target_x = finite_float(target.get("x"))
        target_y = finite_float(target.get("y_rhs"))
        if isinstance(future, list) and isinstance(mask, list) and target_x is not None and target_y is not None:
            valid_indices = [
                index
                for index in range(min(horizon, len(mask), len(future)))
                if mask[index] and isinstance(future[index], list) and len(future[index]) >= 2
            ]
            if valid_indices:
                final = future[valid_indices[-1]]
                final_x = finite_float(final[0])
                final_y = finite_float(final[1])
                if final_x is not None and final_y is not None:
                    values["label.final_displacement_m"].append(math.hypot(final_x - target_x, final_y - target_y))
    return {
        "numeric": {name: numeric_summary(field_values) for name, field_values in sorted(values.items())},
        "context_dimensions": dict(sorted(context_dims.items())),
        "past_state_lengths": dict(sorted(past_lengths.items())),
        "future_valid_step_counts": dict(sorted(future_valid_counts.items())),
    }


def main() -> int:
    args = parse_args()
    merged_dir = Path(args.merged_dir).expanduser().resolve()
    result_dir = Path(args.result_dir).expanduser().resolve() if args.result_dir else merged_dir.parent
    output_json = Path(args.output_json).expanduser().resolve()
    checks: List[Dict[str, Any]] = []

    manifest_path = merged_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    rows_by_split: Dict[str, List[Dict[str, Any]]] = {}
    parse_errors: Dict[str, List[Dict[str, Any]]] = {}
    file_metadata: Dict[str, Dict[str, Any]] = {}
    for split in (*SPLITS, "all"):
        path = merged_dir / f"{split}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(path)
        rows, errors = read_jsonl(path)
        rows_by_split[split] = rows
        parse_errors[split] = errors
        file_metadata[split] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "parsed_rows": len(rows),
            "parse_errors": errors,
        }
    add_check(checks, "jsonl_parse", not any(parse_errors.values()), parse_errors)

    split_stats: Dict[str, Dict[str, Any]] = {}
    subrun_to_splits: MutableMapping[str, set[str]] = collections.defaultdict(set)
    init_to_splits: MutableMapping[int, set[str]] = collections.defaultdict(set)
    union_ids: set[str] = set()
    all_split_composite_duplicates: Dict[str, List[str]] = {}
    raw_sample_id_occurrences: MutableMapping[Any, int] = collections.Counter()
    raster_missing: List[Dict[str, Any]] = []
    raster_checked = 0
    horizon_errors: List[Dict[str, Any]] = []
    dt_errors: List[Dict[str, Any]] = []
    split_assignment_errors: List[Dict[str, Any]] = []

    for split in SPLITS:
        rows = rows_by_split[split]
        composite_counts = collections.Counter(composite_id(sample) for sample in rows)
        duplicates = sorted(key for key, count in composite_counts.items() if count > 1)
        if duplicates:
            all_split_composite_duplicates[split] = duplicates[:50]
        ids = set(composite_counts)
        union_ids.update(ids)
        stages = collections.Counter()
        subruns: set[str] = set()
        init_ids: set[int] = set()
        for sample in rows:
            raw_sample_id_occurrences[sample.get("sample_id")] += 1
            subrun = str(sample.get("source_subrun", ""))
            init_id = infer_init_id(subrun)
            subruns.add(subrun)
            subrun_to_splits[subrun].add(split)
            if init_id is not None:
                init_ids.add(init_id)
                init_to_splits[init_id].add(split)
                if split_for_init(init_id) != split and len(split_assignment_errors) < 50:
                    split_assignment_errors.append(
                        {"sample": composite_id(sample), "actual_split": split, "expected_split": split_for_init(init_id)}
                    )
            else:
                if len(split_assignment_errors) < 50:
                    split_assignment_errors.append({"sample": composite_id(sample), "error": "init id not inferable"})

            stages[future_stage(sample, args.expected_horizon)] += 1
            if sample.get("horizon_steps") != args.expected_horizon and len(horizon_errors) < 50:
                horizon_errors.append(
                    {"sample": composite_id(sample), "horizon_steps": sample.get("horizon_steps")}
                )
            dt = finite_float(sample.get("dt"))
            if dt is None or not math.isclose(dt, args.expected_dt, rel_tol=0.0, abs_tol=1e-9):
                if len(dt_errors) < 50:
                    dt_errors.append({"sample": composite_id(sample), "dt": sample.get("dt")})
            if args.check_rasters:
                raster_checked += 1
                raster_path = resolve_raster_path(sample, result_dir=str(result_dir))
                if not raster_path or not os.path.isfile(raster_path):
                    if len(raster_missing) < 100:
                        raster_missing.append({"sample": composite_id(sample), "resolved_path": raster_path})

        split_stats[split] = {
            "raw_windows": len(rows),
            "samples_with_any_future_label": stages["any_future_label"] + stages["full_horizon"],
            "full_horizon_samples": stages["full_horizon"],
            "raw_only_samples": stages["raw_only"],
            "malformed_label_samples": stages["malformed"],
            "unique_composite_ids": len(ids),
            "source_subruns": len(subruns),
            "init_ids": sorted(init_ids),
            "distribution": distribution_report(rows, args.expected_horizon),
        }

    add_check(
        checks,
        "composite_sample_id_unique_within_split",
        not all_split_composite_duplicates,
        all_split_composite_duplicates,
    )
    add_check(
        checks,
        "split_assignment_matches_init_rule",
        not split_assignment_errors,
        split_assignment_errors,
    )
    subrun_leakage = {key: sorted(value) for key, value in subrun_to_splits.items() if len(value) > 1}
    init_leakage = {str(key): sorted(value) for key, value in init_to_splits.items() if len(value) > 1}
    add_check(checks, "source_subrun_no_split_leakage", not subrun_leakage, subrun_leakage)
    add_check(checks, "ego_init_no_split_leakage", not init_leakage, init_leakage)

    split_init_details = {}
    split_init_pass = True
    for split in SPLITS:
        actual = set(split_stats[split]["init_ids"])
        expected = expected_init_ids(split)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        split_init_details[split] = {"missing": missing, "unexpected": unexpected}
        split_init_pass = split_init_pass and not missing and not unexpected
    add_check(checks, "expected_init_coverage", split_init_pass, split_init_details)

    all_counts = collections.Counter(composite_id(sample) for sample in rows_by_split["all"])
    all_duplicates = sorted(key for key, count in all_counts.items() if count > 1)
    all_ids = set(all_counts)
    add_check(
        checks,
        "all_jsonl_equals_split_union",
        not all_duplicates and all_ids == union_ids,
        {
            "all_duplicates": all_duplicates[:50],
            "missing_from_all": sorted(union_ids - all_ids)[:50],
            "extra_in_all": sorted(all_ids - union_ids)[:50],
        },
    )
    add_check(checks, "horizon_steps", not horizon_errors, horizon_errors)
    add_check(checks, "dt", not dt_errors, dt_errors)

    manifest_counts = manifest.get("sample_counts") or {}
    manifest_count_details = {
        split: {"manifest": manifest_counts.get(split), "observed": len(rows_by_split[split])}
        for split in (*SPLITS, "all")
    }
    manifest_counts_pass = all(
        values["manifest"] == values["observed"] for values in manifest_count_details.values()
    )
    add_check(checks, "merged_manifest_sample_counts", manifest_counts_pass, manifest_count_details)

    rollout_manifest_paths: List[str] = []
    rollout_manifest_entries: List[Tuple[str, Optional[Dict[str, Any]], Optional[str]]] = []
    if args.rollout_manifests_json:
        consolidated_path = Path(args.rollout_manifests_json).expanduser().resolve()
        consolidated = json.loads(consolidated_path.read_text(encoding="utf-8"))
        for record in consolidated.get("rollouts", []):
            source = str(record.get("path") or record.get("source_subrun") or "<unknown>")
            item = record.get("manifest")
            rollout_manifest_paths.append(source)
            rollout_manifest_entries.append(
                (source, item if isinstance(item, dict) else None, None if isinstance(item, dict) else "missing manifest")
            )
    else:
        for path in sorted(result_dir.glob("scenario_*/prediction_dataset/prediction_dataset_manifest.json")):
            rollout_manifest_paths.append(str(path))
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                rollout_manifest_entries.append(
                    (str(path), item if isinstance(item, dict) else None, None if isinstance(item, dict) else "not an object")
                )
            except (OSError, json.JSONDecodeError) as exc:
                rollout_manifest_entries.append((str(path), None, str(exc)))

    rollout_manifest_errors: List[Dict[str, Any]] = []
    rollout_manifest_totals = collections.Counter()
    for source, item, load_error in rollout_manifest_entries:
        if item is None:
            rollout_manifest_errors.append({"path": source, "error": load_error})
            continue
        rollout_manifest_totals["sample_count"] += int(item.get("sample_count", 0))
        rollout_manifest_totals["samples_with_any_future_label"] += int(
            item.get("samples_with_any_future_label", 0)
        )
        if item.get("horizon") != args.expected_horizon or not math.isclose(
            float(item.get("dt", float("nan"))), args.expected_dt, rel_tol=0.0, abs_tol=1e-9
        ):
            rollout_manifest_errors.append(
                {"path": source, "horizon": item.get("horizon"), "dt": item.get("dt")}
            )
        if args.check_rasters and not item.get("save_raster"):
            rollout_manifest_errors.append({"path": source, "save_raster": item.get("save_raster")})
    rollout_manifest_pass = (
        len(rollout_manifest_paths) == 50
        and not rollout_manifest_errors
        and rollout_manifest_totals["sample_count"] == len(rows_by_split["all"])
        and rollout_manifest_totals["samples_with_any_future_label"]
        == sum(split_stats[split]["samples_with_any_future_label"] for split in SPLITS)
    )
    add_check(
        checks,
        "rollout_manifests",
        rollout_manifest_pass,
        {
            "count": len(rollout_manifest_paths),
            "totals": dict(rollout_manifest_totals),
            "errors": rollout_manifest_errors[:50],
        },
    )

    if args.check_rasters:
        add_check(
            checks,
            "raster_files_exist",
            not raster_missing,
            {"checked": raster_checked, "missing_count": len(raster_missing), "missing": raster_missing},
        )
    else:
        checks.append(
            {
                "name": "raster_files_exist",
                "status": "not_run",
                "details": "Run with --check-rasters on the server that stores the raster files.",
            }
        )

    raster_content = None
    if args.check_raster_content:
        raster_content = inspect_raster_content(
            [sample for split in SPLITS for sample in rows_by_split[split]],
            result_dir,
            args.raster_content_samples,
            args.ego_pixel_radius,
        )
        raster_content_pass = bool(
            raster_content.get("available")
            and raster_content.get("eligible")
            and raster_content.get("ego_vehicle_colour_hits") == raster_content.get("eligible")
        )
        add_check(checks, "base_raster_contains_ego", raster_content_pass, raster_content)
    else:
        checks.append(
            {
                "name": "base_raster_contains_ego",
                "status": "not_run",
                "details": "Run with --check-raster-content on the CARLA server.",
            }
        )

    failing_checks = [check["name"] for check in checks if check["status"] == "fail"]
    report = {
        "audit_schema_version": "prediction_dataset_audit_v1",
        "status": "pass" if not failing_checks else "fail",
        "failing_checks": failing_checks,
        "dataset_role": "deterministic_negative_control_pilot_only",
        "dataset_role_reason": (
            "All legacy rollouts use one assertive target style and adaptive ego-policy data; "
            "they cannot identify interaction conditioning or support the formal 2x2 model experiment."
        ),
        "inputs": {
            "merged_dir": str(merged_dir),
            "result_dir": str(result_dir),
            "manifest": str(manifest_path),
        },
        "expectations": {
            "split_rule": "train init 01-40, validation init 41-45, test init 46-50",
            "horizon_steps": args.expected_horizon,
            "dt_s": args.expected_dt,
            "sample_identity": "source_subrun + sample_id",
        },
        "merged_manifest": manifest,
        "files": file_metadata,
        "checks": checks,
        "counts": {
            "all_raw_windows": len(rows_by_split["all"]),
            "all_samples_with_any_future_label": sum(
                split_stats[split]["samples_with_any_future_label"] for split in SPLITS
            ),
            "all_full_horizon_samples": sum(
                split_stats[split]["full_horizon_samples"] for split in SPLITS
            ),
            "raw_sample_id_values_reused_across_rollouts": sum(
                count > 1 for count in raw_sample_id_occurrences.values()
            ),
            "raw_sample_id_reuse_is_expected": True,
        },
        "splits": split_stats,
        "leakage": {"source_subrun": subrun_leakage, "ego_init": init_leakage},
        "raster_content": raster_content,
        "rollout_manifests": {
            "paths": rollout_manifest_paths,
            "totals": dict(rollout_manifest_totals),
        },
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "failing_checks": failing_checks,
                "output_json": str(output_json),
                "counts": report["counts"],
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
