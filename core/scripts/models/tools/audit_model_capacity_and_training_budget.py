#!/usr/bin/env python3
"""E3: quantify parameter, seed, latency, and convergence confounds in Day 8."""

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
import datetime as dt
import io
import json
import statistics
import tarfile
from collections import defaultdict
from pathlib import Path

from distinction_analysis_utils import atomic_write_json, sha256_file, write_csv


def median(values):
    return float(statistics.median(float(value) for value in values))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-summary", type=Path, required=True)
    parser.add_argument("--model-tar", type=Path, required=True)
    parser.add_argument("--history-tar", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(args.validation_summary.read_text(encoding="utf-8"))

    rows = []
    for run in payload["runs"]:
        training = run["training"]
        all_metrics = run["subsets"]["all"]
        rows.append(
            {
                "variant": run["variant"],
                "seed": run["seed"],
                "trainable_parameters": training["parameters"]["trainable_parameters"],
                "total_parameters": training["parameters"]["total_parameters"],
                "epochs_completed": training["epochs_completed"],
                "best_epoch": training["best_epoch"],
                "best_epoch_at_budget_boundary": int(training["best_epoch"] >= training["epochs_completed"]),
                "best_val_masked_nll": training["best_val_masked_nll"],
                "validation_rollout_macro_NLL": all_metrics["uncalibrated_rollout_macro_trajectory_NLL_per_step"],
                "validation_top1_ADE_m": all_metrics["top1_ADE_mean"],
                "validation_top1_FDE_m": all_metrics["top1_FDE_mean"],
                "latency_ms_per_sample": all_metrics["mean_prediction_ms_per_sample"],
            }
        )

    by_variant = defaultdict(list)
    for row in rows:
        by_variant[row["variant"]].append(row)
    variants = []
    b1_parameters = next(row["trainable_parameters"] for row in rows if row["variant"] == "B1")
    for variant, subset in sorted(by_variant.items()):
        variants.append(
            {
                "variant": variant,
                "seeds": len(subset),
                "trainable_parameters": subset[0]["trainable_parameters"],
                "trainable_parameter_ratio_vs_B1": subset[0]["trainable_parameters"] / b1_parameters,
                "median_validation_rollout_macro_NLL": median([r["validation_rollout_macro_NLL"] for r in subset]),
                "min_validation_rollout_macro_NLL": min(r["validation_rollout_macro_NLL"] for r in subset),
                "max_validation_rollout_macro_NLL": max(r["validation_rollout_macro_NLL"] for r in subset),
                "seed_range_validation_rollout_macro_NLL": max(r["validation_rollout_macro_NLL"] for r in subset)
                - min(r["validation_rollout_macro_NLL"] for r in subset),
                "median_validation_top1_ADE_m": median([r["validation_top1_ADE_m"] for r in subset]),
                "median_latency_ms_per_sample": median([r["latency_ms_per_sample"] for r in subset]),
                "runs_best_at_epoch_budget_boundary": sum(r["best_epoch_at_budget_boundary"] for r in subset),
            }
        )

    histories = []
    history_tar = args.history_tar or args.model_tar
    with tarfile.open(history_tar, "r:gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith("/history.csv"):
                continue
            handle = archive.extractfile(member)
            assert handle is not None
            records = list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8")))
            val_fields = [field for field in records[0] if field.startswith("val_") and "loss" in field.lower()]
            val_field = "val_loss" if "val_loss" in records[0] else (val_fields[0] if val_fields else None)
            values = [float(record[val_field]) for record in records] if val_field else []
            histories.append(
                {
                    "member": member.name,
                    "epochs": len(records),
                    "validation_field": val_field,
                    "best_validation_value": min(values) if values else None,
                    "best_epoch_from_history": values.index(min(values)) + 1 if values else None,
                    "last_validation_value": values[-1] if values else None,
                    "last5_linear_change_per_epoch": ((values[-1] - values[-5]) / 4.0) if len(values) >= 5 else None,
                }
            )

    boundary_runs = sum(row["best_epoch_at_budget_boundary"] for row in rows)
    parameter_matched = len({row["trainable_parameters"] for row in rows}) == 1
    conclusions = [
        "All variants used the same nominal epoch ceiling and seed set, but they were not parameter matched.",
        "B1 contains substantially more trainable parameters than every compact interaction-aware variant.",
        "Architecture-only causal attribution is therefore not supported by this experiment.",
    ]
    if boundary_runs:
        conclusions.append(
            f"{boundary_runs}/15 runs selected their final allowed epoch, so some comparisons may be training-budget censored."
        )

    write_csv(args.output_dir / "day8_run_capacity_metrics.csv", rows, list(rows[0]))
    write_csv(args.output_dir / "day8_variant_capacity_summary.csv", variants, list(variants[0]))
    write_csv(args.output_dir / "representative_training_history_audit.csv", histories, list(histories[0]))
    audit = {
        "schema_version": "distinction_model_capacity_budget_audit_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass",
        "result_generation": "distinction_v1",
        "source_sha256": {
            "validation_summary": sha256_file(args.validation_summary),
            "model_tar": sha256_file(args.model_tar),
            "history_tar": sha256_file(history_tar),
        },
        "runs": len(rows),
        "variants": variants,
        "training_histories": histories,
        "fairness_checks": {
            "same_seed_set": all(sorted(r["seed"] for r in subset) == [11, 23, 37] for subset in by_variant.values()),
            "same_epoch_ceiling": len({r["epochs_completed"] for r in rows}) == 1,
            "parameter_matched": parameter_matched,
            "runs_best_at_budget_boundary": boundary_runs,
            "all_15_histories_available": len(histories) == 15,
            "training_histories_available_count": len(histories),
        },
        "conclusions": conclusions,
        "claim_boundary": (
            "Report the observed variant ranking as a comparison of complete model/training configurations, "
            "not as a clean causal estimate of transformer attention or interaction-token design."
        ),
    }
    atomic_write_json(args.output_dir / "model_capacity_training_budget_audit.json", audit)
    atomic_write_json(
        args.output_dir / "E3_COMPLETE.json",
        {"stage": "E3", "status": "pass", "architecture_only_claim_permitted": False, "artifact": "model_capacity_training_budget_audit.json"},
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
