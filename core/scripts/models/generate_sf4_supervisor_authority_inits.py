#!/usr/bin/env python3
"""Generate auditable SF4 authority init106--115 candidates from PCG64.

The original 50-init collection consumed 50 speed draws followed by 50 offset
draws from NumPy ``default_rng(123)``.  R3 then consumed five speed draws and
five offset draws.  This generator continues that same already-declared stream
with ten new speed draws and ten new offset draws.  The output remains a
*candidate* until the dedicated Town05 spawn preflight succeeds; it is not
silently promoted to formal evidence by generation alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np


SEED = 123
ORIGINAL_COUNT = 50
R3_COUNT = 5
SF4_IDS = tuple(range(106, 116))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--r3-manifest", required=True, type=Path)
    args = parser.parse_args()

    root = args.output_dir.resolve()
    r3_manifest = args.r3_manifest.resolve()
    if not r3_manifest.is_file():
        raise SystemExit(f"Missing frozen R3 init manifest: {r3_manifest}")
    previous = json.loads(r3_manifest.read_text(encoding="utf-8"))
    if previous.get("seed") != SEED or len(previous.get("records") or []) != R3_COUNT:
        raise SystemExit("R3 manifest does not match the frozen stream prefix")

    rng = np.random.default_rng(SEED)
    rng.uniform(8.0, 10.0, ORIGINAL_COUNT)
    rng.uniform(-2.5, 2.5, ORIGINAL_COUNT)
    reproduced_r3_speeds = rng.uniform(8.0, 10.0, R3_COUNT)
    reproduced_r3_offsets = rng.uniform(-2.5, 2.5, R3_COUNT)
    for record, speed, offset in zip(
        previous["records"], reproduced_r3_speeds, reproduced_r3_offsets
    ):
        if (
            abs(float(record["init_speed"]) - float(speed)) > 1.0e-12
            or abs(float(record["start_longitudinal_offset"]) - float(offset))
            > 1.0e-12
        ):
            raise SystemExit("R3 manifest cannot be reproduced from the declared stream")

    speeds = rng.uniform(8.0, 10.0, len(SF4_IDS))
    offsets = rng.uniform(-2.5, 2.5, len(SF4_IDS))
    records = []
    for init_id, offset, speed in zip(SF4_IDS, offsets, speeds):
        payload = {
            "start_longitudinal_offset": float(offset),
            "init_speed": float(speed),
        }
        rendered = json.dumps(payload, sort_keys=True) + "\n"
        path = root / f"ego_init_{init_id}.json"
        if path.exists() and path.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"SF4 init candidate drift: {path}")
        atomic_text(path, rendered)
        records.append(
            {
                "ego_init_id": init_id,
                **payload,
                "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            }
        )

    manifest = {
        "schema_version": "sf4_supervisor_authority_ablation_init_candidates_v1",
        "status": "candidate_requires_town05_spawn_preflight",
        "generated_before_formal_outcomes": True,
        "numpy_generator": "default_rng/PCG64",
        "seed": SEED,
        "stream_predecessor": {
            "path": "core/scripts/carla/scenarios/inits/distinction_r3_new/R3_INIT_GENERATION_MANIFEST.json",
            "sha256": sha256(r3_manifest),
            "original_init_count": ORIGINAL_COUNT,
            "r3_continuation_count": R3_COUNT,
        },
        "speed_distribution": "Uniform(8.0, 10.0) m/s",
        "offset_distribution": "Uniform(-2.5, 2.5) m",
        "generation_order": (
            "reproduce/discard original 50 speeds, original 50 offsets, R3 five "
            "speeds and R3 five offsets; then draw 10 candidate speeds followed "
            "by 10 candidate offsets"
        ),
        "independent_of_training_validation_test_ids": True,
        "formal_use_condition": (
            "All ten candidates must pass the committed Town05 spawn preflight "
            "before any treatment rollout starts."
        ),
        "records": records,
    }
    manifest_path = root / "SF4_INIT_CANDIDATE_MANIFEST.json"
    rendered_manifest = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if (
        manifest_path.exists()
        and manifest_path.read_text(encoding="utf-8") != rendered_manifest
    ):
        raise SystemExit(f"SF4 init candidate manifest drift: {manifest_path}")
    atomic_text(manifest_path, rendered_manifest)
    print(rendered_manifest, end="")


if __name__ == "__main__":
    main()
