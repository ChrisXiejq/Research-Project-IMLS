#!/usr/bin/env python3
"""Manifest-driven orchestration and validation-only selection for V3."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from capacity_model_config_v3 import capacity_manifest
from capacity_study_v3_protocol import (
    BOUNDARY_FRACTION,
    BOUNDARY_WINDOW_EPOCHS,
    CAPACITY_TARGETS,
    CORE_EPOCHS,
    DATA_FRACTIONS,
    EARLY_STOPPING_PATIENCE,
    ENCODER_FAMILIES,
    EXTENDED_EPOCHS,
    LEARNING_RATES,
    SEEDS,
    expected_model_cells,
    nested_training_groups,
    sha256_payload,
    validate_nested_training_groups,
    write_immutable_manifest,
)


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    model_cell_id: str
    family: str
    capacity_tier: str
    history_horizon_s: float | None
    learning_rate: float
    seed: int
    data_fraction: float
    train_groups: tuple[int, ...]
    epochs: int = CORE_EPOCHS
    patience: int = EARLY_STOPPING_PATIENCE
    linked_core_run_id: str | None = None
    is_additional_fraction_run: bool = False


def learning_rate_label(value: float) -> str:
    labels = {3.0e-5: "lr3e-5", 1.0e-4: "lr1e-4", 3.0e-4: "lr3e-4"}
    try:
        return labels[float(value)]
    except KeyError as error:
        raise ValueError(f"Learning rate is outside the frozen sweep: {value}") from error


def run_id(model_cell_id: str, learning_rate: float, seed: int, data_fraction: float) -> str:
    fraction = f"data{int(round(data_fraction * 100)):03d}"
    return f"v3__{model_cell_id}__{learning_rate_label(learning_rate)}__s{seed}__{fraction}"


def _cell_index() -> dict[str, dict[str, Any]]:
    return {row["cell_id"]: row for row in expected_model_cells()}


def core_runs() -> list[RunSpec]:
    groups = tuple(nested_training_groups()["1.00"])
    runs = []
    for cell in expected_model_cells():
        for learning_rate in LEARNING_RATES:
            for seed in SEEDS:
                runs.append(
                    RunSpec(
                        run_id=run_id(cell["cell_id"], learning_rate, seed, 1.0),
                        model_cell_id=cell["cell_id"],
                        family=cell["family"],
                        capacity_tier=cell["capacity_tier"],
                        history_horizon_s=cell["history_horizon_s"],
                        learning_rate=learning_rate,
                        seed=seed,
                        data_fraction=1.0,
                        train_groups=groups,
                    )
                )
    if len(runs) != 189 or len({row.run_id for row in runs}) != 189:
        raise AssertionError("Core run grid must contain exactly 189 unique runs")
    return runs


def fraction_runs() -> list[RunSpec]:
    fractions = nested_training_groups()
    validate_nested_training_groups(fractions)
    cell_ids = ("head-large", "mlp-h1p0-large", "transformer-h1p0-large")
    cells = _cell_index()
    runs = []
    for cell_id in cell_ids:
        cell = cells[cell_id]
        for fraction in DATA_FRACTIONS:
            fraction_label = f"{fraction:.2f}"
            for learning_rate in LEARNING_RATES:
                for seed in SEEDS:
                    core_id = (
                        run_id(cell_id, learning_rate, seed, 1.0)
                        if fraction == 1.0
                        else None
                    )
                    runs.append(
                        RunSpec(
                            run_id=run_id(cell_id, learning_rate, seed, fraction),
                            model_cell_id=cell_id,
                            family=cell["family"],
                            capacity_tier=cell["capacity_tier"],
                            history_horizon_s=cell["history_horizon_s"],
                            learning_rate=learning_rate,
                            seed=seed,
                            data_fraction=fraction,
                            train_groups=tuple(fractions[fraction_label]),
                            linked_core_run_id=core_id,
                            is_additional_fraction_run=fraction < 1.0,
                        )
                    )
    if len(runs) != 108:
        raise AssertionError("Fraction grid must contain 108 entries")
    if sum(row.is_additional_fraction_run for row in runs) != 81:
        raise AssertionError("Fraction grid must contain 81 non-duplicate runs")
    return runs


def run_payload(spec: RunSpec) -> dict[str, Any]:
    payload = asdict(spec)
    payload["train_groups"] = list(spec.train_groups)
    return payload


def run_manifest() -> dict[str, Any]:
    capacity = capacity_manifest()
    core = [run_payload(row) for row in core_runs()]
    fractions = [run_payload(row) for row in fraction_runs()]
    payload = {
        "schema_version": "capacity_history_run_manifest_v3",
        "status": "frozen",
        "capacity_manifest_sha256": sha256_payload(capacity),
        "capacity_manifest": capacity,
        "core_runs": core,
        "fraction_runs": fractions,
        "counts": {
            "core": len(core),
            "fraction_entries": len(fractions),
            "fraction_linked_to_core": sum(row["linked_core_run_id"] is not None for row in fractions),
            "fraction_additional": sum(row["is_additional_fraction_run"] for row in fractions),
        },
    }
    payload["manifest_sha256"] = sha256_payload(payload)
    return payload


def validate_run_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    recorded_hash = value.pop("manifest_sha256", None)
    value.pop("payload_sha256", None)
    if recorded_hash != sha256_payload(value):
        raise ValueError("Run manifest hash mismatch")
    expected = run_manifest()
    expected.pop("manifest_sha256")
    if value != expected:
        raise ValueError("Run manifest differs from the frozen V3 grid")
    return {"status": "pass", **payload["counts"], "manifest_sha256": recorded_hash}


def missing_runs(
    runs: Sequence[RunSpec], completed_run_ids: Iterable[str]
) -> list[RunSpec]:
    planned_ids = {row.run_id for row in runs}
    complete = {str(value) for value in completed_run_ids}
    unknown = complete - planned_ids
    if unknown:
        raise ValueError(f"Completion set contains unknown run ids: {sorted(unknown)}")
    return [row for row in runs if row.run_id not in complete]


def _assert_validation_row(row: Mapping[str, Any]) -> None:
    if row.get("split") not in {"val", "validation"}:
        raise ValueError("Model selection may consume validation rows only")
    if any(key.startswith("test_") or key.startswith("challenge_") for key in row):
        raise ValueError("Fresh-test fields are forbidden during model selection")
    if row.get("status") != "pass":
        raise ValueError(f"Incomplete validation run: {row.get('run_id')}")
    value = float(row["rollout_macro_nll"])
    if not math.isfinite(value):
        raise ValueError("Validation NLL must be finite")


def select_learning_rates(validation_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    planned = {row.run_id: row for row in core_runs()}
    grouped: dict[tuple[str, float], list[Mapping[str, Any]]] = {}
    for row in validation_rows:
        _assert_validation_row(row)
        identifier = str(row["run_id"])
        if identifier not in planned:
            raise ValueError(f"Validation result is not a planned core run: {identifier}")
        spec = planned[identifier]
        if int(row["seed"]) != spec.seed or float(row["learning_rate"]) != spec.learning_rate:
            raise ValueError(f"Validation metadata disagrees with run id: {identifier}")
        grouped.setdefault((spec.model_cell_id, spec.learning_rate), []).append(row)

    selected = []
    for cell in expected_model_cells():
        choices = []
        for learning_rate in LEARNING_RATES:
            rows = grouped.get((cell["cell_id"], learning_rate), [])
            if {int(row["seed"]) for row in rows} != set(SEEDS) or len(rows) != len(SEEDS):
                raise ValueError(
                    f"Expected three validation seeds for {cell['cell_id']} at {learning_rate}"
                )
            score = median(float(row["rollout_macro_nll"]) for row in rows)
            choices.append((score, learning_rate, rows))
        score, learning_rate, rows = min(choices, key=lambda item: (item[0], item[1]))
        selected.append(
            {
                "model_cell_id": cell["cell_id"],
                "selected_learning_rate": learning_rate,
                "median_validation_rollout_macro_nll": score,
                "retained_run_ids": sorted(
                    str(row.get("checkpoint_run_id", row["run_id"])) for row in rows
                ),
                "seed_scores": {
                    str(row["seed"]): float(row["rollout_macro_nll"]) for row in rows
                },
            }
        )
    payload = {
        "schema_version": "capacity_history_validation_selection_v3",
        "status": "pass",
        "selection_split": "validation",
        "selected_cells": selected,
    }
    payload["selection_sha256"] = sha256_payload(payload)
    return payload


def select_fraction_learning_rates(
    validation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Repeat validation-only LR selection independently within every data fraction."""

    planned = {row.run_id: row for row in fraction_runs()}
    grouped: dict[tuple[str, float, float], list[Mapping[str, Any]]] = {}
    for row in validation_rows:
        _assert_validation_row(row)
        identifier = str(row["run_id"])
        if identifier not in planned:
            raise ValueError(f"Validation result is not a planned fraction run: {identifier}")
        spec = planned[identifier]
        if (
            int(row["seed"]) != spec.seed
            or float(row["learning_rate"]) != spec.learning_rate
            or float(row["data_fraction"]) != spec.data_fraction
        ):
            raise ValueError(f"Fraction validation metadata disagrees with run id: {identifier}")
        grouped.setdefault(
            (spec.model_cell_id, spec.data_fraction, spec.learning_rate), []
        ).append(row)
    selected = []
    for cell_id in ("head-large", "mlp-h1p0-large", "transformer-h1p0-large"):
        for fraction in DATA_FRACTIONS:
            choices = []
            for learning_rate in LEARNING_RATES:
                rows = grouped.get((cell_id, fraction, learning_rate), [])
                if {int(row["seed"]) for row in rows} != set(SEEDS) or len(rows) != 3:
                    raise ValueError(
                        f"Expected three fraction validation seeds for {cell_id}/"
                        f"{fraction}/{learning_rate}"
                    )
                score = median(float(row["rollout_macro_nll"]) for row in rows)
                choices.append((score, learning_rate, rows))
            score, learning_rate, rows = min(choices, key=lambda item: (item[0], item[1]))
            selected.append(
                {
                    "model_cell_id": cell_id,
                    "data_fraction": fraction,
                    "selected_learning_rate": learning_rate,
                    "median_validation_rollout_macro_nll": score,
                    "retained_run_ids": sorted(
                        str(row.get("checkpoint_run_id", row["run_id"])) for row in rows
                    ),
                    "seed_scores": {
                        str(row["seed"]): float(row["rollout_macro_nll"]) for row in rows
                    },
                }
            )
    payload = {
        "schema_version": "capacity_history_fraction_validation_selection_v3",
        "status": "pass",
        "selection_split": "validation",
        "selected_fraction_cells": selected,
    }
    payload["selection_sha256"] = sha256_payload(payload)
    return payload


def fraction_convergence_extension_plan(
    selection: Mapping[str, Any], validation_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Apply the same boundary rule to each matched data-fraction comparison."""

    rows_by_checkpoint = {
        str(row.get("checkpoint_run_id", row["run_id"])): row
        for row in validation_rows
    }
    selected_by_key = {
        (str(row["model_cell_id"]), float(row["data_fraction"])): row
        for row in selection["selected_fraction_cells"]
    }
    audits = []
    boundary_fractions: set[float] = set()
    exhausted_fractions: set[float] = set()
    for (cell_id, fraction), selected in sorted(selected_by_key.items()):
        retained = [rows_by_checkpoint[identifier] for identifier in selected["retained_run_ids"]]
        boundary = sum(
            int(row["best_epoch"])
            > int(row.get("epochs_allowed", CORE_EPOCHS)) - BOUNDARY_WINDOW_EPOCHS
            for row in retained
        )
        boundary_fraction = boundary / len(retained)
        if boundary_fraction > BOUNDARY_FRACTION:
            boundary_fractions.add(fraction)
            if any(
                int(row.get("epochs_allowed", CORE_EPOCHS)) >= EXTENDED_EPOCHS
                for row in retained
            ):
                exhausted_fractions.add(fraction)
        audits.append(
            {
                "model_cell_id": cell_id,
                "data_fraction": fraction,
                "boundary_runs": boundary,
                "retained_runs": len(retained),
                "boundary_fraction": boundary_fraction,
            }
        )

    extension_runs = []
    planned = {row.run_id: row for row in fraction_runs()}
    if not exhausted_fractions:
        for fraction in sorted(boundary_fractions):
            for cell_id in ("head-large", "mlp-h1p0-large", "transformer-h1p0-large"):
                selected = selected_by_key[(cell_id, fraction)]
                for checkpoint_id in selected["retained_run_ids"]:
                    base_id = str(rows_by_checkpoint[checkpoint_id]["run_id"])
                    original = planned[base_id]
                    value = run_payload(original)
                    value["epochs"] = EXTENDED_EPOCHS
                    value["run_id"] = base_id + "__extended120"
                    value["extends_run_id"] = base_id
                    extension_runs.append(value)
    status = (
        "nonconverged_at_max_budget"
        if exhausted_fractions
        else "requires_extension" if boundary_fractions else "pass"
    )
    payload = {
        "schema_version": "capacity_history_fraction_convergence_plan_v3",
        "status": status,
        "fresh_test_access_allowed": status == "pass",
        "boundary_window_epochs": BOUNDARY_WINDOW_EPOCHS,
        "maximum_boundary_fraction": BOUNDARY_FRACTION,
        "cell_audits": audits,
        "boundary_data_fractions": sorted(boundary_fractions),
        "exhausted_data_fractions": sorted(exhausted_fractions),
        "extension_runs": extension_runs,
    }
    payload["plan_sha256"] = sha256_payload(payload)
    return payload


def select_p_star(
    selection: Mapping[str, Any],
    eligibility: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    candidates = []
    cells = _cell_index()
    for row in selection["selected_cells"]:
        cell_id = row["model_cell_id"]
        if cells[cell_id]["family"] not in ENCODER_FAMILIES:
            continue
        gate = eligibility.get(cell_id)
        if not gate or not all(
            bool(gate.get(name))
            for name in ("converged", "capacity_audit_pass", "calibration_complete", "latency_gate_pass")
        ):
            continue
        candidates.append(
            (
                float(row["median_validation_rollout_macro_nll"]),
                int(gate["trainable_parameters"]),
                float(gate["warmed_batch_one_latency"]),
                str(cell_id),
                row,
            )
        )
    if not candidates:
        raise ValueError("No eligible sequence-model candidate for P_star")
    score, parameters, latency, cell_id, selected = min(candidates, key=lambda item: item[:4])
    return {
        "role": "P_star",
        "model_cell_id": cell_id,
        "family": cells[cell_id]["family"],
        "capacity_tier": cells[cell_id]["capacity_tier"],
        "history_horizon_s": cells[cell_id]["history_horizon_s"],
        "selected_learning_rate": selected["selected_learning_rate"],
        "median_validation_rollout_macro_nll": score,
        "trainable_parameters": parameters,
        "warmed_batch_one_latency": latency,
        "retained_run_ids": selected["retained_run_ids"],
        "selection_rule": [
            "median_validation_rollout_macro_nll",
            "trainable_parameters",
            "warmed_batch_one_latency",
            "model_cell_id",
        ],
    }


def convergence_extension_plan(
    selection: Mapping[str, Any], validation_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    rows_by_id = {
        str(row.get("checkpoint_run_id", row["run_id"])): row
        for row in validation_rows
    }
    cells = _cell_index()
    boundary_cells = set()
    audits = []
    for selected in selection["selected_cells"]:
        retained = [rows_by_id[identifier] for identifier in selected["retained_run_ids"]]
        boundary = sum(
            int(row["best_epoch"]) > int(row.get("epochs_allowed", CORE_EPOCHS)) - BOUNDARY_WINDOW_EPOCHS
            for row in retained
        )
        fraction = boundary / len(retained)
        if fraction > BOUNDARY_FRACTION:
            boundary_cells.add(selected["model_cell_id"])
        audits.append(
            {
                "model_cell_id": selected["model_cell_id"],
                "boundary_runs": boundary,
                "retained_runs": len(retained),
                "boundary_fraction": fraction,
            }
        )

    selected_by_cell = {row["model_cell_id"]: row for row in selection["selected_cells"]}
    exhausted_cells = {
        cell_id
        for cell_id in boundary_cells
        if any(
            int(rows_by_id[identifier].get("epochs_allowed", CORE_EPOCHS))
            >= EXTENDED_EPOCHS
            for identifier in selected_by_cell[cell_id]["retained_run_ids"]
        )
    }
    if exhausted_cells:
        payload = {
            "schema_version": "capacity_history_convergence_plan_v3",
            "status": "nonconverged_at_max_budget",
            "fresh_test_access_allowed": False,
            "boundary_window_epochs": BOUNDARY_WINDOW_EPOCHS,
            "maximum_boundary_fraction": BOUNDARY_FRACTION,
            "cell_audits": audits,
            "boundary_cells": sorted(boundary_cells),
            "exhausted_cells": sorted(exhausted_cells),
            "extension_cells": [],
            "extension_runs": [],
        }
        payload["plan_sha256"] = sha256_payload(payload)
        return payload
    extension_cells = set(boundary_cells)
    for cell_id in tuple(boundary_cells):
        cell = cells[cell_id]
        tier = cell["capacity_tier"]
        horizon = cell["history_horizon_s"]
        if cell["family"] in ENCODER_FAMILIES:
            extension_cells.update(
                other["cell_id"]
                for other in cells.values()
                if other["family"] in ENCODER_FAMILIES
                and other["capacity_tier"] == tier
                and other["history_horizon_s"] == horizon
            )
        if cell["family"] == "transformer":
            extension_cells.update(
                other["cell_id"]
                for other in cells.values()
                if other["family"] == "transformer"
                and other["history_horizon_s"] == horizon
            )
        if tier in CAPACITY_TARGETS:
            extension_cells.add(f"head-{tier}")
            extension_cells.add(f"mlp-h1p0-{tier}")
            extension_cells.add(f"transformer-h1p0-{tier}")

    extension_runs = []
    planned = {row.run_id: row for row in core_runs()}
    for cell_id in sorted(extension_cells):
        for identifier in selected_by_cell[cell_id]["retained_run_ids"]:
            original = planned[identifier]
            value = run_payload(original)
            value["epochs"] = EXTENDED_EPOCHS
            value["run_id"] = identifier + "__extended120"
            value["extends_run_id"] = identifier
            extension_runs.append(value)
    payload = {
        "schema_version": "capacity_history_convergence_plan_v3",
        "status": "requires_extension" if extension_cells else "pass",
        "fresh_test_access_allowed": not extension_cells,
        "boundary_window_epochs": BOUNDARY_WINDOW_EPOCHS,
        "maximum_boundary_fraction": BOUNDARY_FRACTION,
        "cell_audits": audits,
        "boundary_cells": sorted(boundary_cells),
        "extension_cells": sorted(extension_cells),
        "extension_runs": extension_runs,
    }
    payload["plan_sha256"] = sha256_payload(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--completed-run-id", action="append", default=[])
    args = parser.parse_args()
    payload = run_manifest()
    validate_run_manifest(payload)
    missing = [
        row.run_id for row in missing_runs(core_runs(), args.completed_run_id)
    ]
    write_immutable_manifest(args.output, payload)
    print(
        json.dumps(
            {**payload["counts"], "missing_core_runs": len(missing)},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
