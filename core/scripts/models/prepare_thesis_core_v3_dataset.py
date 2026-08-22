#!/usr/bin/env python3
"""Derive and seal the retrospective 35/5/5 thesis-core group split."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from capacity_study_v3_protocol import (
    COLLECTION_CELLS,
    THESIS_FIT_GROUPS,
    THESIS_HELDOUT_GROUPS,
    THESIS_SELECTION_GROUPS,
    atomic_json,
    canonical_json,
    sha256_file,
    sha256_payload,
)
from interaction_sequence_v3 import has_complete_interaction_history
from prediction_dataset_utils import read_jsonl, resolve_raster_path
from train_prediction_model_v3 import masked_local_label


SPLIT_GROUPS = {
    "fit": THESIS_FIT_GROUPS,
    "selection": THESIS_SELECTION_GROUPS,
    "heldout": THESIS_HELDOUT_GROUPS,
}


def sample_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        (
            str(row["ego_init_id"]),
            str(row.get("cell_id", row.get("source_cell", ""))),
            str(row["sample_id"]),
        )
    )


def eligible(row: Mapping[str, Any], label_horizon: int = 10) -> bool:
    if not has_complete_interaction_history(row.get("interaction_sequence_mask") or []):
        return False
    if not np.any(masked_local_label(row, label_horizon)[:, 2]):
        return False
    raster = resolve_raster_path(row)
    return bool(raster and os.path.exists(raster))


def _normalization(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    total = np.zeros(12, dtype=np.float64)
    total_sq = np.zeros(12, dtype=np.float64)
    count = 0
    for row in rows:
        sequence = np.asarray(row["interaction_sequence"], dtype=np.float64)
        mask = np.asarray(row["interaction_sequence_mask"], dtype=bool)
        valid = sequence[mask]
        if valid.size:
            total += valid.sum(axis=0)
            total_sq += np.square(valid).sum(axis=0)
            count += len(valid)
    if count < 1:
        raise ValueError("Fit split has no valid interaction tokens")
    mean = total / count
    variance = np.maximum(total_sq / count - np.square(mean), 0.0)
    std = np.maximum(np.sqrt(variance), 1.0e-6)
    payload = {
        "schema_version": "interaction_normalization_thesis_core_v3",
        "fit_groups": list(THESIS_FIT_GROUPS),
        "valid_token_count": count,
        "minimum_std": 1.0e-6,
        "mean": mean.tolist(),
        "std": std.tolist(),
    }
    payload["normalization_sha256"] = sha256_payload(payload)
    return payload


def load_thesis_normalization(path: str | Path) -> dict[str, Any]:
    """Load only the sealed groups-1--35 V3 normalization artifact."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    value = dict(payload)
    recorded = value.pop("normalization_sha256", None)
    if recorded != sha256_payload(value):
        raise ValueError("Thesis-core normalization hash mismatch")
    if payload.get("schema_version") != "interaction_normalization_thesis_core_v3":
        raise ValueError("Normalization is not a thesis-core V3 artifact")
    if payload.get("fit_groups") != list(THESIS_FIT_GROUPS):
        raise ValueError("Normalization is not restricted to thesis fit groups 1--35")
    mean = np.asarray(payload.get("mean", []), dtype=np.float64)
    std = np.asarray(payload.get("std", []), dtype=np.float64)
    if mean.shape != (12,) or std.shape != (12,):
        raise ValueError("Expected 12-feature thesis-core normalization")
    if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(std)) or not np.all(std > 0.0):
        raise ValueError("Normalization values must be finite with positive std")
    return payload


def derive_rows(source_dir: Path) -> dict[str, list[dict[str, Any]]]:
    source_rows = list(read_jsonl(str(source_dir / "train.jsonl")))
    source_rows.extend(read_jsonl(str(source_dir / "val.jsonl")))
    by_group = {name: set(groups) for name, groups in SPLIT_GROUPS.items()}
    result = {name: [] for name in SPLIT_GROUPS}
    seen: set[str] = set()
    for row in source_rows:
        group = int(row["ego_init_id"])
        destination = next((name for name, groups in by_group.items() if group in groups), None)
        if destination is None or not eligible(row):
            continue
        key = sample_key(row)
        if key in seen:
            raise ValueError(f"Duplicate sample key across thesis split: {key}")
        seen.add(key)
        result[destination].append(dict(row))
    return result


def audit_rows(rows: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    expected_cells = set(COLLECTION_CELLS)
    all_keys: dict[str, set[str]] = {}
    records: dict[str, Any] = {}
    for split, expected_groups in SPLIT_GROUPS.items():
        current = rows[split]
        groups = {int(row["ego_init_id"]) for row in current}
        if groups != set(expected_groups):
            raise ValueError(f"{split} group support mismatch: {sorted(groups)}")
        keys = {sample_key(row) for row in current}
        if len(keys) != len(current):
            raise ValueError(f"{split} contains duplicate sample keys")
        all_keys[split] = keys
        cells: dict[int, set[str]] = defaultdict(set)
        support: Counter[int] = Counter()
        for row in current:
            group = int(row["ego_init_id"])
            cells[group].add(str(row.get("cell_id", row.get("source_cell", ""))))
            support[group] += 1
        bad = {group: sorted(value) for group, value in cells.items() if value != expected_cells}
        if bad:
            raise ValueError(f"{split} four-cell support mismatch: {bad}")
        records[split] = {
            "groups": sorted(groups),
            "samples": len(current),
            "support_by_group": {str(group): support[group] for group in sorted(support)},
            "cells_by_group": {str(group): sorted(cells[group]) for group in sorted(cells)},
        }
    names = tuple(SPLIT_GROUPS)
    overlaps = {
        f"{left}_{right}": len(all_keys[left] & all_keys[right])
        for index, left in enumerate(names)
        for right in names[index + 1 :]
    }
    if any(overlaps.values()):
        raise ValueError(f"Thesis split sample overlap: {overlaps}")
    return {"status": "pass", "splits": records, "sample_overlaps": overlaps}


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
    os.replace(temporary, path)


def prepare(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    rows = derive_rows(source_dir)
    audit = audit_rows(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, values in rows.items():
        _write_jsonl(output_dir / f"{name}.jsonl", values)
    normalization = _normalization(rows["fit"])
    atomic_json(output_dir / "interaction_normalization_fit.json", normalization)
    manifest = {
        "schema_version": "capacity_history_thesis_core_dataset_v3",
        "status": "pass",
        "evidence_status": "retrospective_held_out",
        "source_dir": str(source_dir.resolve()),
        "source_sha256": {
            "train_jsonl": sha256_file(source_dir / "train.jsonl"),
            "val_jsonl": sha256_file(source_dir / "val.jsonl"),
        },
        "split_sha256": {
            name: sha256_file(output_dir / f"{name}.jsonl") for name in SPLIT_GROUPS
        },
        "normalization_sha256": sha256_file(output_dir / "interaction_normalization_fit.json"),
        "audit": audit,
    }
    manifest["manifest_sha256"] = sha256_payload(manifest)
    atomic_json(output_dir / "THESIS_CORE_DATASET_COMPLETE.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_dir, args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
