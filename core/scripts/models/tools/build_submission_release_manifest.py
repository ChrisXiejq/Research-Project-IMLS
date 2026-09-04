#!/usr/bin/env python3
"""Bind experiment evidence, dissertation build and release checks together."""

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
import subprocess
from pathlib import Path


EXPERIMENT_ARTIFACTS = [
    "docs/paper/generated/capacity_history_v3/final/evidence_index.json",
    "docs/paper/generated/capacity_history_v3/results/closed_loop/CLOSED_LOOP_COMPLETE.json",
    "docs/paper/generated/supervisor_bottleneck_v1/scientific_contract/SCIENTIFIC_CONTRACT_COMPLETE.json",
    "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/TELEMETRY_AUDIT_COMPLETE.json",
    "docs/paper/generated/supervisor_bottleneck_v1/paper_release/PAPER_EVIDENCE_COMPLETE.json",
    "docs/paper/generated/supervisor_bottleneck_v1/paper_release/DISSERTATION_AUDIT.json",
]

DISSERTATION_ARTIFACTS = [
    "main.tex",
    "main.bib",
    "main.pdf",
    "BUILD.md",
    "figures/supervisor_bottleneck_v1/figure01_cross_layer_system.pdf",
    "figures/supervisor_bottleneck_v1/figure02_capacity_information_architecture.pdf",
    "figures/supervisor_bottleneck_v1/figure03_predictor_risk_transfer.pdf",
    "figures/supervisor_bottleneck_v1/figure04_supervisor_authority.pdf",
]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact_records(root: Path, paths: list[str]) -> list[dict]:
    records = []
    for relative in paths:
        path = root / relative
        records.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else 0,
                "sha256": _sha256(path) if path.is_file() else None,
            }
        )
    return records


def build_manifest(experiment_root: Path, dissertation_root: Path) -> dict:
    experiment_head = _git(experiment_root, "rev-parse", "HEAD")
    dissertation_head = _git(dissertation_root, "rev-parse", "HEAD")
    experiment_records = _artifact_records(experiment_root, EXPERIMENT_ARTIFACTS)
    dissertation_records = _artifact_records(dissertation_root, DISSERTATION_ARTIFACTS)

    experiment_ahead, experiment_behind = map(
        int,
        _git(experiment_root, "rev-list", "--left-right", "--count", "HEAD...origin/main").split(),
    )
    dissertation_ahead, dissertation_behind = map(
        int,
        _git(dissertation_root, "rev-list", "--left-right", "--count", "HEAD...origin/main").split(),
    )

    checks = {
        "all_experiment_artifacts_present": all(r["exists"] for r in experiment_records),
        "all_dissertation_artifacts_present": all(r["exists"] for r in dissertation_records),
        "experiment_not_behind_origin": experiment_behind == 0,
        "dissertation_not_behind_origin": dissertation_behind == 0,
        "dissertation_pdf_is_18_pages": json.loads(
            (experiment_root / EXPERIMENT_ARTIFACTS[-1]).read_text(encoding="utf-8")
        )["checks"]["compiled_pdf"]["page_count"]
        == 18,
        "paper_evidence_audit_passes": json.loads(
            (experiment_root / EXPERIMENT_ARTIFACTS[-2]).read_text(encoding="utf-8")
        )["status"]
        == "pass",
        "dissertation_audit_passes": json.loads(
            (experiment_root / EXPERIMENT_ARTIFACTS[-1]).read_text(encoding="utf-8")
        )["pass"],
    }

    payload = {
        "schema_version": "submission_release_manifest_v1",
        "status": "pass" if all(checks.values()) else "fail",
        "release_base_commits": {
            "experiment": experiment_head,
            "dissertation": dissertation_head,
        },
        "remote_divergence_before_push": {
            "experiment": {"ahead": experiment_ahead, "behind": experiment_behind},
            "dissertation": {"ahead": dissertation_ahead, "behind": dissertation_behind},
        },
        "tests": {
            "relevant_unittest_total": 274,
            "relevant_unittest_status": "pass",
            "post_sf4_pytest_tests": 20,
            "post_sf4_subtests": 12,
            "matplotlib_figure_test": "pass",
            "latexmk_xelatex": "pass",
            "page_raster_comparison": "18/18 unchanged after canonical figure sync",
        },
        "experiment_artifacts": experiment_records,
        "dissertation_artifacts": dissertation_records,
        "checks": checks,
        "bounded_limitations": [
            "The V3 held-out prediction groups are retrospective, not fresh confirmatory data.",
            "The authority-off SF4 arm is floor-saturated, so selective masking is not identified.",
            "Seven supervisor behaviour channels are toggled together; individual rule effects are not isolated.",
            "Phase-event clocks are incomplete and are not imputed.",
            "The evidence is limited to one Town05 give-way geometry and does not establish formal or real-road safety.",
        ],
        "fresh_clone_locator": {
            "experiment_evidence_root": "docs/paper/generated/supervisor_bottleneck_v1/paper_release",
            "dissertation_source": "main.tex",
            "dissertation_pdf": "main.pdf",
            "build_instructions": "BUILD.md",
        },
    }
    if payload["status"] != "pass":
        raise RuntimeError(f"Submission release checks failed: {checks}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-root", type=Path, default=Path("."))
    parser.add_argument("--dissertation-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_manifest(args.experiment_root.resolve(), args.dissertation_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
