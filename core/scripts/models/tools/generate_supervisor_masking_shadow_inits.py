#!/usr/bin/env python3
"""Freeze prospective init116--135 from the declared PCG64 stream."""

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

import numpy as np


SEED = 123
ORIGINAL_COUNT = 50
R3_IDS = tuple(range(101, 106))
SF4_IDS = tuple(range(106, 116))
SHADOW_IDS = tuple(range(116, 136))
ABS_TOL = 1.0e-12
R3_SCHEMA = "r3_confirmatory_init_generation_v1"
SF4_SCHEMA = "sf4_supervisor_authority_ablation_init_candidates_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def canonical_payload(speed: float, offset: float) -> tuple[dict[str, float], str]:
    payload = {
        "start_longitudinal_offset": float(offset),
        "init_speed": float(speed),
    }
    return payload, json.dumps(payload, sort_keys=True) + "\n"


def _load_manifest(path: Path, schema: str, ids: tuple[int, ...]) -> dict:
    if not path.is_file():
        raise SystemExit(f"Missing frozen predecessor manifest: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid predecessor manifest: {path}: {exc}") from exc
    if (
        manifest.get("schema_version") != schema
        or manifest.get("seed") != SEED
        or [row.get("ego_init_id") for row in manifest.get("records", [])] != list(ids)
    ):
        raise SystemExit(f"Frozen predecessor manifest contract drift: {path}")
    return manifest


def _validate_predecessor_records(
    manifest_path: Path,
    manifest: dict,
    ids: tuple[int, ...],
    speeds: np.ndarray,
    offsets: np.ndarray,
) -> None:
    for init_id, row, expected_speed, expected_offset in zip(
        ids, manifest["records"], speeds, offsets
    ):
        if not (
            math.isclose(float(row["init_speed"]), float(expected_speed), rel_tol=0.0, abs_tol=ABS_TOL)
            and math.isclose(
                float(row["start_longitudinal_offset"]),
                float(expected_offset),
                rel_tol=0.0,
                abs_tol=ABS_TOL,
            )
        ):
            raise SystemExit(
                f"Predecessor stream reproduction drift: {manifest_path}:ego_init_{init_id}"
            )
        candidate_path = manifest_path.parent / f"ego_init_{init_id}.json"
        if not candidate_path.is_file() or sha256(candidate_path) != row.get("sha256"):
            raise SystemExit(
                f"Predecessor candidate hash drift: {candidate_path}"
            )
        frozen = candidate_path.read_text(encoding="utf-8")
        _, canonical = canonical_payload(float(row["init_speed"]), float(row["start_longitudinal_offset"]))
        if frozen != canonical:
            raise SystemExit(f"Predecessor candidate serialization drift: {candidate_path}")


def _freeze_candidate(path: Path, generated: dict[str, float], rendered: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise SystemExit(f"Frozen shadow init drift: {path}")
    atomic_text(path, rendered)


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def generate_candidates(
    output_dir: Path,
    r3_manifest_path: Path,
    sf4_manifest_path: Path,
    repo_root: Path,
) -> dict:
    output_dir = output_dir.resolve()
    r3_manifest_path = r3_manifest_path.resolve()
    sf4_manifest_path = sf4_manifest_path.resolve()
    repo_root = repo_root.resolve()

    r3 = _load_manifest(r3_manifest_path, R3_SCHEMA, R3_IDS)
    sf4 = _load_manifest(sf4_manifest_path, SF4_SCHEMA, SF4_IDS)
    if sf4.get("stream_predecessor", {}).get("sha256") != sha256(r3_manifest_path):
        raise SystemExit("SF4 predecessor hash no longer matches the frozen R3 manifest")

    rng = np.random.default_rng(SEED)
    rng.uniform(8.0, 10.0, ORIGINAL_COUNT)
    rng.uniform(-2.5, 2.5, ORIGINAL_COUNT)
    r3_speeds = rng.uniform(8.0, 10.0, len(R3_IDS))
    r3_offsets = rng.uniform(-2.5, 2.5, len(R3_IDS))
    _validate_predecessor_records(
        r3_manifest_path, r3, R3_IDS, r3_speeds, r3_offsets
    )
    sf4_speeds = rng.uniform(8.0, 10.0, len(SF4_IDS))
    sf4_offsets = rng.uniform(-2.5, 2.5, len(SF4_IDS))
    _validate_predecessor_records(
        sf4_manifest_path, sf4, SF4_IDS, sf4_speeds, sf4_offsets
    )

    speeds = rng.uniform(8.0, 10.0, len(SHADOW_IDS))
    offsets = rng.uniform(-2.5, 2.5, len(SHADOW_IDS))
    records = []
    for init_id, speed, offset in zip(SHADOW_IDS, speeds, offsets):
        payload, rendered = canonical_payload(float(speed), float(offset))
        path = output_dir / f"ego_init_{init_id}.json"
        _freeze_candidate(path, payload, rendered)
        records.append(
            {
                "ego_init_id": init_id,
                **payload,
                "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            }
        )

    prior_ids = set(range(1, ORIGINAL_COUNT + 1)) | set(R3_IDS) | set(SF4_IDS)
    if prior_ids.intersection(SHADOW_IDS):
        raise SystemExit("Prospective init IDs overlap a predecessor population")
    manifest = {
        "schema_version": "supervisor_masking_shadow_init_candidates_v2",
        "status": "frozen_candidates_require_protocol_preflight",
        "generated_before_shadow_outcomes": True,
        "numpy_generator": "default_rng/PCG64",
        "numpy_bit_generator": type(rng.bit_generator).__name__,
        "seed": SEED,
        "speed_distribution": "Uniform(8.0, 10.0) m/s",
        "offset_distribution": "Uniform(-2.5, 2.5) m",
        "generation_order": (
            "reproduce/discard original 50 speeds, original 50 offsets, R3 five "
            "speeds, R3 five offsets, SF4 ten speeds and SF4 ten offsets; then "
            "draw 20 prospective speeds followed by 20 prospective offsets"
        ),
        "stream_predecessors": {
            "r3": {
                "path": _display_path(r3_manifest_path, repo_root),
                "sha256": sha256(r3_manifest_path),
                "ids": list(R3_IDS),
            },
            "sf4": {
                "path": _display_path(sf4_manifest_path, repo_root),
                "sha256": sha256(sf4_manifest_path),
                "ids": list(SF4_IDS),
            },
        },
        "stream_counts_before_shadow": {
            "original_speeds": 50,
            "original_offsets": 50,
            "r3_speeds": 5,
            "r3_offsets": 5,
            "sf4_speeds": 10,
            "sf4_offsets": 10,
        },
        "candidate_ids": list(SHADOW_IDS),
        "no_id_overlap_with": {
            "original": [1, 50],
            "r3": list(R3_IDS),
            "sf4": list(SF4_IDS),
        },
        "formal_use_condition": (
            "Candidates remain unexecuted until the frozen shadow protocol and its "
            "pre-outcome integrity/spawn gates pass; generation does not authorise CARLA."
        ),
        "records": records,
    }
    manifest_path = output_dir / "SUPERVISOR_MASKING_SHADOW_INIT_CANDIDATE_MANIFEST.json"
    rendered_manifest = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != rendered_manifest:
        raise SystemExit(f"Frozen shadow init manifest drift: {manifest_path}")
    atomic_text(manifest_path, rendered_manifest)
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[4]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "core/scripts/carla/scenarios/inits/supervisor_masking_shadow_v2",
    )
    parser.add_argument(
        "--r3-manifest",
        type=Path,
        default=root / "core/scripts/carla/scenarios/inits/distinction_r3_new/R3_INIT_GENERATION_MANIFEST.json",
    )
    parser.add_argument(
        "--sf4-manifest",
        type=Path,
        default=root / "core/scripts/carla/scenarios/inits/distinction_sf4_supervisor_authority_ablation/SF4_INIT_CANDIDATE_MANIFEST.json",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = generate_candidates(
        args.output_dir, args.r3_manifest, args.sf4_manifest, args.root
    )
    print(json.dumps({"status": result["status"], "candidates": len(result["records"])}))


if __name__ == "__main__":
    main()
