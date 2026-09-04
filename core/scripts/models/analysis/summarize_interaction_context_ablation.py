#!/usr/bin/env python3
"""Summarize frozen T1/T2 context ablations as reporting-only diagnostics."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from summarize_day8_frozen_test import metrics_for


VARIANTS = ("T1", "T2")
MODES = ("zero", "shuffle")
SUBSETS = ("all", "assertive", "reactive", "pre_response", "response_active")
REQUIRED_SUBSETS = ("all", "assertive", "reactive")
FIELDS = (
    "top1_ADE_mean",
    "top1_FDE_mean",
    "uncalibrated_rollout_macro_NLL",
    "calibrated_rollout_macro_NLL",
    "uncalibrated_coverage_MAE",
    "calibrated_coverage_MAE",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite {label}: {value}")
    return number


def summarize(results_dir: Path, day8_summary_path: Path, selection_path: Path) -> dict[str, Any]:
    day8 = json.loads(day8_summary_path.read_text())
    selection = json.loads(selection_path.read_text())
    if day8.get("status") != "pass" or day8.get("test_used_for_selection") is not False:
        raise ValueError("Invalid Day 8 frozen test summary")
    if selection.get("status") != "pass" or not selection.get(
        "closed_loop_selection_locked_before_test"
    ):
        raise ValueError("Invalid Day 8 pre-test selection freeze")

    original_runs = {run["variant"]: run for run in day8["runs"]}
    variants: dict[str, Any] = {}
    artifacts: dict[str, str] = {}
    for variant in VARIANTS:
        frozen = selection["representatives_for_single_test_pass"][variant]
        original = original_runs[variant]
        if int(original["seed"]) != int(frozen["seed"]):
            raise ValueError(f"Frozen seed mismatch for {variant}")
        modes: dict[str, Any] = {}
        for mode in MODES:
            subsets: dict[str, Any] = {}
            for subset in SUBSETS:
                path = results_dir / variant / mode / f"test_{subset}.json"
                payload = json.loads(path.read_text())
                artifacts[str(path.relative_to(results_dir))] = sha256(path)
                if payload.get("evaluation_schema_version") != "multipath_accuracy_calibration_v2":
                    raise ValueError(f"Stale evaluation schema: {path}")
                if payload.get("split") != "test" or payload.get("subset") != subset:
                    raise ValueError(f"Split/subset mismatch: {path}")
                if payload.get("model_artifact", {}).get("sha256_tree") != frozen["model"][
                    "sha256_tree"
                ]:
                    raise ValueError(f"Frozen model hash mismatch: {path}")
                if (payload.get("calibration") or {}).get("parameters") != frozen[
                    "calibration_parameters"
                ]:
                    raise ValueError(f"Frozen calibration mismatch: {path}")
                ablation = payload.get("interaction_ablation") or {}
                if ablation.get("mode") != mode or ablation.get("applied") is not True:
                    raise ValueError(f"Ablation metadata mismatch: {path}")
                if payload.get("calibration_fit_uses_test") is not False:
                    raise ValueError(f"Test leakage flag failed: {path}")

                if payload.get("status") == "not_applicable" and subset not in REQUIRED_SUBSETS:
                    subsets[subset] = {
                        "status": "not_applicable",
                        "samples": 0,
                        "reason": payload.get("reason"),
                    }
                    continue
                if payload.get("status") != "pass":
                    raise ValueError(f"Required ablation evaluation failed: {path}")
                ablated = metrics_for(payload)
                baseline = original["subsets"][subset]
                if baseline.get("status") != "pass":
                    raise ValueError(f"Original Day 8 subset unavailable: {variant}/{subset}")
                population = (
                    "samples",
                    "independent_rollouts",
                    "independent_init_groups",
                )
                if tuple(ablated[key] for key in population) != tuple(
                    baseline[key] for key in population
                ):
                    raise ValueError(f"Ablation population drift: {path}")
                deltas = {
                    f"ablated_minus_original_{field}": finite(
                        ablated[field], f"ablated {field}"
                    )
                    - finite(baseline[field], f"baseline {field}")
                    for field in FIELDS
                }
                subsets[subset] = {
                    "status": "pass",
                    "original": baseline,
                    "ablated": ablated,
                    "deltas": deltas,
                    "mapping_sha256": ablation.get("mapping_sha256"),
                }
            modes[mode] = {"subsets": subsets}
        variants[variant] = {"seed": int(frozen["seed"]), "modes": modes}

    return {
        "schema_version": "interaction_context_ablation_summary_v1",
        "status": "pass",
        "role": "post-selection reporting-only diagnostic",
        "test_used_for_selection": False,
        "retraining_or_retuning_after_diagnostic_permitted": False,
        "interpretation_rule": (
            "Positive ablated-minus-original ADE/FDE/NLL indicates that removing or "
            "misaligning interaction context worsened prediction; this supports actual "
            "sequence use but is not a causal performance guarantee in closed loop."
        ),
        "variants": variants,
        "source_sha256": {
            "day8_frozen_test_summary": sha256(day8_summary_path),
            "day8_model_selection_frozen": sha256(selection_path),
            **artifacts,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--day8-test-summary", required=True, type=Path)
    parser.add_argument("--selection-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    payload = summarize(
        args.results_dir.resolve(),
        args.day8_test_summary.resolve(),
        args.selection_json.resolve(),
    )
    output = args.output_json.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps({"status": "pass", "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
