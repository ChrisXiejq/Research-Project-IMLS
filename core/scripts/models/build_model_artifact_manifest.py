#!/usr/bin/env python3
"""Build a reproducibility manifest for a TensorFlow SavedModel artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--history-json", required=True)
    parser.add_argument("--training-log", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--artifact-role", default="legacy_interaction_transformer_negative_control_pilot")
    parser.add_argument("--training-git-commit", required=True)
    parser.add_argument("--seed", type=int, default=11)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path, root: Path | None = None) -> Dict[str, Any]:
    return {
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if root else path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def saved_model_files(model_dir: Path) -> Iterable[Path]:
    return sorted(path for path in model_dir.rglob("*") if path.is_file())


def main() -> int:
    args = parse_args()
    model_dir = Path(args.model_dir).expanduser().resolve()
    history_path = Path(args.history_json).expanduser().resolve()
    training_log_path = Path(args.training_log).expanduser().resolve()
    anchors_path = Path(args.anchors).expanduser().resolve()
    output_path = Path(args.output_json).expanduser().resolve()

    required = {
        "model_dir": model_dir,
        "saved_model_pb": model_dir / "saved_model.pb",
        "variables_index": model_dir / "variables" / "variables.index",
        "history_json": history_path,
        "training_log": training_log_path,
        "anchors": anchors_path,
    }
    missing = [name for name, path in required.items() if not path.exists()]
    history: Dict[str, Any] = {}
    history_error = None
    if history_path.is_file():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            history_error = str(exc)

    model_files = list(saved_model_files(model_dir)) if model_dir.is_dir() else []
    variable_data_files = [
        path for path in model_files if path.name.startswith("variables.data-")
    ]
    if not variable_data_files:
        missing.append("variables_data")

    manifest = {
        "artifact_manifest_version": "tensorflow_saved_model_manifest_v1",
        "status": "pass" if not missing and history_error is None else "fail",
        "artifact_role": args.artifact_role,
        "training_git_commit": args.training_git_commit,
        "seed": args.seed,
        "seed_provenance": (
            "run launcher did not override --seed; value is inherited from the frozen historical "
            "training script default"
        ),
        "normalization": {
            "raster": "tensorflow.keras.applications.resnet.preprocess_input",
            "past_states_local": "no explicit normalization in legacy pilot",
            "interaction_context_8d": "no explicit normalization in legacy pilot",
            "warning": "This legacy static-context pilot is not the formal V2 interaction-sequence model.",
        },
        "missing_required_assets": sorted(set(missing)),
        "history_parse_error": history_error,
        "training_metadata": history,
        "model": {
            "directory": str(model_dir),
            "files": [file_record(path, root=model_dir) for path in model_files],
            "total_bytes": sum(path.stat().st_size for path in model_files),
        },
        "associated_assets": {
            "history_json": file_record(history_path) if history_path.is_file() else None,
            "training_log": file_record(training_log_path) if training_log_path.is_file() else None,
            "anchors": file_record(anchors_path) if anchors_path.is_file() else None,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "missing_required_assets": manifest["missing_required_assets"],
                "model_files": len(model_files),
                "model_bytes": manifest["model"]["total_bytes"],
                "output_json": str(output_path),
            },
            indent=2,
        )
    )
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
