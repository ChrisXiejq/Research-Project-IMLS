#!/usr/bin/env python3
"""Prove whether the legacy B0--B1 foundation table used partial futures.

The foundation evaluation and the later CIA study share source JSONL files but
do not share sample inclusion rules.  This audit binds the frozen foundation
artifacts to the full-horizon subset and therefore prevents the future-mask
repair from being over- or under-applied.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload


SCHEMA = "capacity_history_foundation_future_mask_scope_audit_v4"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def mask_summary(path: Path, horizon: int = 10) -> dict[str, Any]:
    histogram: Counter[int] = Counter()
    masks: list[list[int]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            raw = row.get("future_valid_mask")
            if not isinstance(raw, list) or len(raw) < horizon:
                raise ValueError(f"Missing future_valid_mask at {path}:{line_number}")
            mask = [int(value) for value in raw[:horizon]]
            if any(value not in (0, 1) for value in mask):
                raise ValueError(f"Non-binary future_valid_mask at {path}:{line_number}")
            if mask != sorted(mask, reverse=True):
                raise ValueError(f"Non-prefix future_valid_mask at {path}:{line_number}")
            valid = sum(mask)
            if valid < 1:
                raise ValueError(f"Zero-valid-step sample at {path}:{line_number}")
            histogram[valid] += 1
            masks.append(mask)
    full = histogram[horizon]
    total = len(masks)
    return {
        "jsonl": artifact(path),
        "samples": total,
        "horizon_steps": horizon,
        "full_horizon_samples": full,
        "partial_horizon_samples": total - full,
        "valid_length_histogram": {
            str(key): histogram[key] for key in sorted(histogram)
        },
        "mask_sha256": sha256_payload(masks),
    }


def require_evaluation(
    payload: Mapping[str, Any],
    *,
    expected_samples: int,
    expected_jsonl: Mapping[str, Any],
    label: str,
) -> None:
    if (
        payload.get("status") != "pass"
        or int(payload.get("horizon", -1)) != 10
        or int(payload.get("samples", -1)) != expected_samples
        or payload.get("subset") != "all"
        or payload.get("jsonl", {}).get("sha256") != expected_jsonl["sha256"]
        or int(payload.get("jsonl", {}).get("bytes", -1)) != expected_jsonl["bytes"]
        or payload.get("top1_ADE_mean") is None
        or payload.get("top1_FDE_mean") is None
        or payload.get("uncalibrated", {}).get(
            "trajectory_mixture_NLL_per_step_mean"
        )
        is None
    ):
        raise ValueError(f"Foundation evaluation contract failed: {label}")


def audit(args: argparse.Namespace) -> dict[str, Any]:
    validation = mask_summary(args.validation_jsonl)
    test = mask_summary(args.test_jsonl)
    if (
        validation["samples"] != 506
        or validation["full_horizon_samples"] != 326
        or validation["partial_horizon_samples"] != 180
        or test["samples"] != 495
        or test["full_horizon_samples"] != 315
        or test["partial_horizon_samples"] != 180
    ):
        raise ValueError("Frozen foundation split membership drift")

    b0_validation = load(args.b0_validation_evaluation)
    b0_test = load(args.b0_test_evaluation)
    b1_test = load(args.b1_test_evaluation)
    summary = load(args.b0_summary)
    require_evaluation(
        b0_validation,
        expected_samples=validation["full_horizon_samples"],
        expected_jsonl=validation["jsonl"],
        label="B0 validation",
    )
    require_evaluation(
        b0_test,
        expected_samples=test["full_horizon_samples"],
        expected_jsonl=test["jsonl"],
        label="B0 test",
    )
    require_evaluation(
        b1_test,
        expected_samples=test["full_horizon_samples"],
        expected_jsonl=test["jsonl"],
        label="B1 test",
    )

    calibration = b0_validation.get("calibration", {})
    all_rows = summary.get("subsets", {}).get("all", {})
    legacy_source = args.legacy_evaluator_source.read_text(encoding="utf-8")
    source_gate = (
        "if not has_full_horizon(sample, horizon=horizon):" in legacy_source
        and "continue" in legacy_source.split(
            "if not has_full_horizon(sample, horizon=horizon):", 1
        )[1][:160]
    )
    if (
        summary.get("status") != "pass"
        or summary.get("test_used_for_selection") is not False
        or int(calibration.get("samples", -1))
        != validation["full_horizon_samples"]
        or int(all_rows.get("B0", {}).get("samples", -1))
        != test["full_horizon_samples"]
        or int(all_rows.get("B1", {}).get("samples", -1))
        != test["full_horizon_samples"]
        or summary.get("source_sha256", {}).get("b0_test_all")
        != sha256_file(args.b0_test_evaluation)
        or not source_gate
    ):
        raise ValueError("Foundation summary or full-horizon source gate failed")

    payload = {
        "schema_version": SCHEMA,
        "status": "pass",
        "future_validity_contract": "full_horizon_only_legacy_foundation_verified_v4",
        "validation_source": validation,
        "test_source": test,
        "evaluated_membership": {
            "B0_validation_samples": int(b0_validation["samples"]),
            "B0_test_samples": int(b0_test["samples"]),
            "B1_test_samples": int(b1_test["samples"]),
            "partial_windows_entered_foundation_metrics": 0,
            "fixed_horizon_FDE_is_defined_for_every_evaluated_sample": True,
        },
        "source_gate": {
            "legacy_evaluator": artifact(args.legacy_evaluator_source),
            "has_full_horizon_filter_verified": source_gate,
        },
        "artifacts": {
            "b0_validation_evaluation": artifact(args.b0_validation_evaluation),
            "b0_test_evaluation": artifact(args.b0_test_evaluation),
            "b1_test_evaluation": artifact(args.b1_test_evaluation),
            "b0_b1_summary": artifact(args.b0_summary),
        },
        "conclusion": (
            "The frozen B0--B1 foundation comparison evaluated only the complete "
            "2.0 s subset. Its reported NLL, ADE and FDE did not consume padded "
            "partial futures and therefore do not require numerical replacement "
            "for the V4 mask repair. This does not license reuse of the CIA model "
            "selection or held-out results, which consumed partial windows."
        ),
    }
    payload["audit_sha256"] = sha256_payload(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-jsonl", required=True, type=Path)
    parser.add_argument("--test-jsonl", required=True, type=Path)
    parser.add_argument("--b0-validation-evaluation", required=True, type=Path)
    parser.add_argument("--b0-test-evaluation", required=True, type=Path)
    parser.add_argument("--b1-test-evaluation", required=True, type=Path)
    parser.add_argument("--b0-summary", required=True, type=Path)
    parser.add_argument("--legacy-evaluator-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = audit(args)
    atomic_json(args.output, payload)
    print(json.dumps({
        "status": payload["status"],
        "audit_sha256": payload["audit_sha256"],
        "evaluated_membership": payload["evaluated_membership"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
