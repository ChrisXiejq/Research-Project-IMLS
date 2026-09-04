#!/usr/bin/env python3

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
"""Create a fixed train/val/test split for CARLA prediction datasets."""

import argparse
import glob
import json
import os

from prediction_dataset_utils import SPLIT_RULE, read_jsonl, split_for_subrun


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result_dir", required=True, help="Prediction dataset collection result directory.")
    parser.add_argument("--output_dir", default=None, help="Default: <result_dir>/prediction_dataset_merged")
    return parser.parse_args()


def main():
    args = parse_args()
    result_dir = os.path.abspath(args.result_dir)
    output_dir = os.path.abspath(args.output_dir or os.path.join(result_dir, "prediction_dataset_merged"))
    os.makedirs(output_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(result_dir, "scenario_*", "prediction_dataset", "prediction_dataset_labeled.jsonl")))
    if not files:
        raise FileNotFoundError(f"No labeled prediction dataset files found under {result_dir}")

    handles = {
        split: open(os.path.join(output_dir, f"{split}.jsonl"), "w", encoding="utf-8")
        for split in ("all", "train", "val", "test")
    }
    splits = {"train": [], "val": [], "test": []}
    counts = {"all": 0, "train": 0, "val": 0, "test": 0}
    valid_counts = {"all": 0, "train": 0, "val": 0, "test": 0}

    try:
        for path in files:
            subrun = os.path.basename(os.path.dirname(os.path.dirname(path)))
            split = split_for_subrun(subrun)
            splits[split].append(subrun)
            prediction_dataset_dir = os.path.dirname(path)
            for sample in read_jsonl(path):
                sample["source_subrun"] = subrun
                sample["source_prediction_dataset_dir"] = prediction_dataset_dir
                raster_relpath = sample.get("raster_relpath")
                if raster_relpath:
                    raster_path = os.path.join(prediction_dataset_dir, raster_relpath)
                    sample["raster_relpath_from_result"] = os.path.relpath(raster_path, result_dir)
                    sample["raster_abspath"] = os.path.abspath(raster_path)
                line = json.dumps(sample, separators=(",", ":")) + "\n"
                handles["all"].write(line)
                handles[split].write(line)
                counts["all"] += 1
                counts[split] += 1
                if any(sample.get("future_valid_mask") or []):
                    valid_counts["all"] += 1
                    valid_counts[split] += 1
    finally:
        for handle in handles.values():
            handle.close()

    manifest = {
        "result_dir": result_dir,
        "merged_dir": output_dir,
        "source_labeled_files": len(files),
        "split_rule": SPLIT_RULE,
        "splits": splits,
        "sample_counts": counts,
        "valid_sample_counts": valid_counts,
        "files": {
            "all": "all.jsonl",
            "train": "train.jsonl",
            "val": "val.jsonl",
            "test": "test.jsonl",
        },
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(json.dumps({
        "merged_dir": output_dir,
        "split_rule": SPLIT_RULE,
        "sample_counts": counts,
        "valid_sample_counts": valid_counts,
        "manifest": manifest_path,
    }, indent=2))


if __name__ == "__main__":
    main()
