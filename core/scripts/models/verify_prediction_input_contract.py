#!/usr/bin/env python3
"""Verify the frozen V2 raster and interaction-sequence input contract."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np

from interaction_sequence import (
    FEATURE_NAMES,
    HISTORY_TIMES_S,
    assert_logged_feature_equivalence,
    build_interaction_sequence,
)
from prediction_input_contract import (
    RASTER_CONTRACT_ID,
    load_logged_raster,
    preprocess_resnet_raster,
    raster_array_sha256,
    save_logged_raster,
)


REQUIRED_V2_FIELDS = {
    "dataset_version",
    "protocol_id",
    "git_commit",
    "scenario",
    "map",
    "ego_init_id",
    "ego_policy",
    "cell_id",
    "target_style",
    "target_style_parameters",
    "target_speed_mps",
    "target_start_offset_m",
    "prediction_horizon_steps",
    "dt_s",
    "history_times_s",
    "feature_schema_id",
    "source_subrun",
    "sample_id",
    "raster_relpath",
    "raster_contract_id",
    "raster_uint8_sha256",
    "interaction_history_world",
    "interaction_sequence",
    "interaction_sequence_mask",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-jsonl", default=None)
    parser.add_argument("--prediction-dataset-dir", default=None)
    parser.add_argument("--output-json", default=None)
    return parser.parse_args()


def synthetic_history():
    rows = []
    for index, time_offset in enumerate(HISTORY_TIMES_S):
        rows.append(
            {
                "time_offset_s": time_offset,
                "valid": index >= 1,
                "ego": None if index == 0 else {
                    "x": 4.0 + index,
                    "y_rhs": 3.0 - 0.2 * index,
                    "yaw_rad_rhs": 0.45,
                    "vx_rhs": 4.2,
                    "vy_rhs": -0.3,
                },
                "target": None if index == 0 else {
                    "x": 10.0 + 1.5 * index,
                    "y_rhs": -2.0,
                    "yaw_rad_rhs": 0.0,
                    "vx_rhs": 7.5,
                    "vy_rhs": 0.0,
                },
            }
        )
    return rows


def synthetic_checks():
    height, width = 37, 53
    yy, xx = np.indices((height, width))
    raster = np.stack(
        [
            (3 * xx + yy) % 256,
            (xx + 5 * yy + 17) % 256,
            (7 * xx + 11 * yy + 91) % 256,
        ],
        axis=-1,
    ).astype(np.uint8)
    with tempfile.TemporaryDirectory(prefix="day4_input_contract_") as tempdir:
        path = Path(tempdir) / "raster.png"
        online = save_logged_raster(str(path), raster)
        offline = load_logged_raster(str(path))
        online_preprocessed = preprocess_resnet_raster(online)
        offline_preprocessed = preprocess_resnet_raster(offline)
    history = synthetic_history()
    online_interaction = build_interaction_sequence(history)
    sample = {
        "history_times_s": list(HISTORY_TIMES_S),
        "interaction_history_world": history,
        "interaction_sequence": online_interaction.values.tolist(),
        "interaction_sequence_mask": online_interaction.mask.tolist(),
    }
    feature_difference = assert_logged_feature_equivalence(sample)
    return {
        "raster_pixel_max_abs_difference": int(
            np.max(np.abs(online.astype(np.int16) - offline.astype(np.int16)))
        ),
        "raster_preprocessed_max_abs_difference": float(
            np.max(np.abs(online_preprocessed - offline_preprocessed))
        ),
        "raster_sha256_equal": raster_array_sha256(online)
        == raster_array_sha256(offline),
        "interaction": feature_difference,
        "interaction_shape": list(online_interaction.values.shape),
        "mask": online_interaction.mask.tolist(),
    }


def first_jsonl_row(path):
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                return json.loads(line)
    raise ValueError(f"No samples in {path}")


def real_sample_checks(jsonl_path, prediction_dataset_dir):
    sample = first_jsonl_row(jsonl_path)
    missing = sorted(REQUIRED_V2_FIELDS - set(sample))
    raster_path = Path(prediction_dataset_dir) / sample["raster_relpath"]
    raster = load_logged_raster(str(raster_path))
    observed_hash = raster_array_sha256(raster)
    expected_hash = sample.get("raster_uint8_sha256")
    feature_difference = assert_logged_feature_equivalence(sample)
    sequence = np.asarray(sample["interaction_sequence"], dtype=np.float32)
    mask = np.asarray(sample["interaction_sequence_mask"], dtype=np.float32)
    return {
        "sample_id": sample.get("sample_id"),
        "source_subrun": sample.get("source_subrun"),
        "missing_required_fields": missing,
        "raster_contract_id": sample.get("raster_contract_id"),
        "raster_sha256_equal": bool(expected_hash and observed_hash == expected_hash),
        "interaction": feature_difference,
        "interaction_shape": list(sequence.shape),
        "mask_shape": list(mask.shape),
        "valid_tokens": int(np.sum(mask)),
        "masked_tokens_zero_filled": bool(np.all(sequence[mask == 0.0] == 0.0)),
    }


def main():
    args = parse_args()
    synthetic = synthetic_checks()
    real = None
    if bool(args.sample_jsonl) != bool(args.prediction_dataset_dir):
        raise ValueError(
            "--sample-jsonl and --prediction-dataset-dir must be supplied together"
        )
    if args.sample_jsonl:
        real = real_sample_checks(
            args.sample_jsonl,
            args.prediction_dataset_dir,
        )
    synthetic_pass = (
        synthetic["raster_pixel_max_abs_difference"] == 0
        and synthetic["raster_preprocessed_max_abs_difference"] == 0.0
        and synthetic["raster_sha256_equal"]
        and synthetic["interaction"]["sequence_max_abs_difference"] == 0.0
        and synthetic["interaction"]["mask_max_abs_difference"] == 0.0
        and synthetic["interaction_shape"] == [6, len(FEATURE_NAMES)]
    )
    real_pass = real is None or (
        not real["missing_required_fields"]
        and real["raster_contract_id"] == RASTER_CONTRACT_ID
        and real["raster_sha256_equal"]
        and real["interaction"]["sequence_max_abs_difference"] == 0.0
        and real["interaction"]["mask_max_abs_difference"] == 0.0
        and real["interaction_shape"] == [6, len(FEATURE_NAMES)]
        and real["mask_shape"] == [6]
        and real["masked_tokens_zero_filled"]
    )
    report = {
        "input_contract_schema_version": "prediction_input_contract_v2",
        "status": "pass" if synthetic_pass and real_pass else "fail",
        "raster_contract_id": RASTER_CONTRACT_ID,
        "feature_schema_id": "give_way_interaction_sequence_v2",
        "synthetic": synthetic,
        "real_sample": real,
    }
    if args.output_json:
        output = Path(args.output_json).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
