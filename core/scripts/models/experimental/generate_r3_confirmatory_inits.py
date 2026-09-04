#!/usr/bin/env python3
"""Reproduce and extend the original 50-init sampling stream for R3.

The original collection was generated with NumPy PCG64/default_rng seed 123:
50 speeds from Uniform(8, 10), followed by 50 offsets from Uniform(-2.5, 2.5).
R3 continues the already-consumed stream with five speeds and five offsets.
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
import hashlib
import json
import os
from pathlib import Path

import numpy as np


SEED = 123
PREFIX_COUNT = 50
R3_IDS = tuple(range(101, 106))


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.output_dir.resolve()

    rng = np.random.default_rng(SEED)
    rng.uniform(8.0, 10.0, PREFIX_COUNT)
    rng.uniform(-2.5, 2.5, PREFIX_COUNT)
    speeds = rng.uniform(8.0, 10.0, len(R3_IDS))
    offsets = rng.uniform(-2.5, 2.5, len(R3_IDS))
    records = []
    for init_id, offset, speed in zip(R3_IDS, offsets, speeds):
        payload = {
            "start_longitudinal_offset": float(offset),
            "init_speed": float(speed),
        }
        path = root / f"ego_init_{init_id}.json"
        rendered = json.dumps(payload, sort_keys=True) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"Frozen R3 init drift: {path}")
        atomic_text(path, rendered)
        records.append(
            {
                "ego_init_id": init_id,
                **payload,
                "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            }
        )

    manifest = {
        "schema_version": "r3_confirmatory_init_generation_v1",
        "status": "frozen",
        "generated_before_formal_outcomes": True,
        "numpy_generator": "default_rng/PCG64",
        "seed": SEED,
        "continuation_after_original_init_count": PREFIX_COUNT,
        "original_speed_distribution": "Uniform(8.0, 10.0) m/s",
        "original_offset_distribution": "Uniform(-2.5, 2.5) m",
        "generation_order": "discard original 50 speeds, discard original 50 offsets, draw 5 speeds, draw 5 offsets",
        "independent_of_training_validation_test_ids": True,
        "records": records,
    }
    atomic_text(root / "R3_INIT_GENERATION_MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
