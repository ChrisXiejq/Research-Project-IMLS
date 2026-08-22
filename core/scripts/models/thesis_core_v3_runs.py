#!/usr/bin/env python3
"""Deterministic 27-run thesis-core manifest and six-way sharding."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from capacity_model_config_v3 import capacity_manifest
from capacity_study_v3_protocol import (
    CORE_EPOCHS,
    EARLY_STOPPING_PATIENCE,
    SEEDS,
    THESIS_CORE_CELL_IDS,
    THESIS_CORE_LEARNING_RATE,
    THESIS_CORE_RUN_COUNT,
    THESIS_FIT_GROUPS,
    atomic_json,
    expected_model_cells,
    sha256_payload,
)
from capacity_study_v3_runs import RunSpec, run_id, run_payload


DOSE_RESPONSE_CELL_IDS = ("mlp-h0p4-large", "transformer-h0p4-large")
ENDPOINT_CELL_IDS = tuple(
    cell_id for cell_id in THESIS_CORE_CELL_IDS if cell_id not in DOSE_RESPONSE_CELL_IDS
)


def thesis_core_runs() -> list[RunSpec]:
    cells = {row["cell_id"]: row for row in expected_model_cells()}
    ordered_ids = ENDPOINT_CELL_IDS + DOSE_RESPONSE_CELL_IDS
    runs: list[RunSpec] = []
    for cell_id in ordered_ids:
        cell = cells[cell_id]
        for seed in SEEDS:
            runs.append(
                RunSpec(
                    run_id=run_id(cell_id, THESIS_CORE_LEARNING_RATE, seed, 1.0),
                    model_cell_id=cell_id,
                    family=cell["family"],
                    capacity_tier=cell["capacity_tier"],
                    history_horizon_s=cell["history_horizon_s"],
                    learning_rate=THESIS_CORE_LEARNING_RATE,
                    seed=seed,
                    data_fraction=1.0,
                    train_groups=tuple(THESIS_FIT_GROUPS),
                    epochs=CORE_EPOCHS,
                    patience=EARLY_STOPPING_PATIENCE,
                )
            )
    if len(runs) != THESIS_CORE_RUN_COUNT or len({row.run_id for row in runs}) != THESIS_CORE_RUN_COUNT:
        raise AssertionError("Thesis-core grid must contain exactly 27 unique runs")
    return runs


def thesis_core_manifest() -> dict[str, Any]:
    capacity = capacity_manifest()
    runs = [run_payload(row) for row in thesis_core_runs()]
    payload = {
        "schema_version": "capacity_history_thesis_core_run_manifest_v3",
        "status": "frozen",
        "evidence_status": "retrospective_held_out",
        "capacity_manifest": capacity,
        "capacity_manifest_sha256": sha256_payload(capacity),
        "fixed_learning_rate": THESIS_CORE_LEARNING_RATE,
        "fit_groups": list(THESIS_FIT_GROUPS),
        "endpoint_runs": sum(row["model_cell_id"] in ENDPOINT_CELL_IDS for row in runs),
        "dose_response_runs": sum(row["model_cell_id"] in DOSE_RESPONSE_CELL_IDS for row in runs),
        "runs": runs,
    }
    payload["manifest_sha256"] = sha256_payload(payload)
    return payload


def validate_thesis_core_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    recorded = value.pop("manifest_sha256", None)
    if recorded != sha256_payload(value):
        raise ValueError("Thesis-core run manifest hash mismatch")
    expected = thesis_core_manifest()
    expected.pop("manifest_sha256")
    if value != expected:
        raise ValueError("Run manifest differs from the frozen thesis-core grid")
    return {
        "status": "pass",
        "planned_runs": len(payload["runs"]),
        "endpoint_runs": payload["endpoint_runs"],
        "dose_response_runs": payload["dose_response_runs"],
        "manifest_sha256": recorded,
    }


def shard_runs(runs: Sequence[RunSpec], shard_index: int, shard_count: int) -> list[RunSpec]:
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("Invalid shard index/count")
    return [row for index, row in enumerate(runs) if index % shard_count == shard_index]


def missing_thesis_runs(
    runs: Sequence[RunSpec], completed_run_ids: Iterable[str]
) -> list[RunSpec]:
    planned = {row.run_id for row in runs}
    complete = {str(value) for value in completed_run_ids}
    unknown = complete - planned
    if unknown:
        raise ValueError(f"Completion set contains unknown thesis run ids: {sorted(unknown)}")
    return [row for row in runs if row.run_id not in complete]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int, default=6)
    args = parser.parse_args()
    payload = thesis_core_manifest()
    validate_thesis_core_manifest(payload)
    atomic_json(args.output, payload)
    report: dict[str, Any] = {
        "manifest": str(args.output),
        "planned_runs": THESIS_CORE_RUN_COUNT,
        "endpoint_runs": len(ENDPOINT_CELL_IDS) * len(SEEDS),
        "dose_response_runs": len(DOSE_RESPONSE_CELL_IDS) * len(SEEDS),
    }
    if args.shard_index is not None:
        report["shard_index"] = args.shard_index
        report["shard_run_ids"] = [
            row.run_id
            for row in shard_runs(thesis_core_runs(), args.shard_index, args.shard_count)
        ]
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
