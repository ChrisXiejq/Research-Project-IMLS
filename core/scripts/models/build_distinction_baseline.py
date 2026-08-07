#!/usr/bin/env python3
"""Freeze the pre-remediation repository and evidence provenance (S0)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import tarfile
from pathlib import Path

from distinction_analysis_utils import atomic_write_json, run_command, sha256_file, sha256_text


CHECKLIST = [
    ("C1", "formal profile mode mapping can collapse distinct supervisor profiles"),
    ("C2", "fixed/adaptive risk reference generators use different acceleration floors"),
    ("C3", "formal Day 9 predictor comparison excludes B2-D/T1/T2"),
    ("C4", "B1 has materially more trainable parameters than compact variants"),
    ("C5", "five initialization groups limit exact two-sided paired-test resolution"),
    ("C6", "target-light native collision callbacks need event-level de-duplication"),
    ("C7", "legacy evidence locators are not all machine-resolvable"),
    ("C8", "reported d_min is an actor-centre distance, not footprint clearance"),
    ("C9", "physical and input-ablation baselines are missing from the frozen evidence"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def tar_summary(path: Path) -> dict:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        file_members = [member for member in members if member.isfile()]
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "member_count": len(members),
        "file_member_count": len(file_members),
    }


def main() -> None:
    args = parse_args()
    repo = args.repo.resolve()
    backup_dir = args.backup_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    status = run_command(["git", "status", "--porcelain=v1", "--untracked-files=all"], repo)
    diff = run_command(["git", "diff", "--binary", "--no-ext-diff"], repo)
    cached_diff = run_command(["git", "diff", "--cached", "--binary", "--no-ext-diff"], repo)
    head = run_command(["git", "rev-parse", "HEAD"], repo)
    try:
        origin = run_command(["git", "rev-parse", "origin/main"], repo)
    except Exception:
        origin = None

    tracked_files = run_command(["git", "ls-files"], repo).splitlines()
    untracked_files = run_command(["git", "ls-files", "--others", "--exclude-standard"], repo).splitlines()
    changed_paths = []
    for relative in sorted(set(tracked_files + untracked_files)):
        candidate = repo / relative
        if candidate.is_file() and (relative in untracked_files or relative.encode() in status.encode()):
            changed_paths.append(
                {"path": relative, "bytes": candidate.stat().st_size, "sha256": sha256_file(candidate)}
            )

    archives = [tar_summary(path) for path in sorted(backup_dir.glob("*.tar.gz"))]
    json_files = []
    for path in sorted(backup_dir.glob("*.json")):
        record = {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        try:
            with path.open("r", encoding="utf-8") as handle:
                json.load(handle)
            record["json_parse"] = "pass"
        except Exception as error:
            record["json_parse"] = "fail"
            record["error"] = str(error)
        json_files.append(record)

    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    provenance = {
        "schema_version": "distinction_provenance_v1",
        "created_at_utc": timestamp,
        "scope_note": (
            "Frozen after the distinction plan documents and S0 tooling were added, "
            "but before S1/E1-E6 analytical results were generated. Existing dirty files are preserved as user work."
        ),
        "repository": {
            "path": str(repo),
            "head": head,
            "origin_main": origin,
            "head_matches_origin_main": origin == head if origin else None,
            "status_porcelain": status.splitlines(),
            "status_sha256": sha256_text(status),
            "unstaged_diff_sha256": sha256_text(diff),
            "cached_diff_sha256": sha256_text(cached_diff),
            "changed_file_snapshots": changed_paths,
        },
        "evidence_backup": {
            "path": str(backup_dir),
            "archives": archives,
            "json_files": json_files,
        },
    }
    atomic_write_json(output / "legacy_evidence_v1.json", provenance)

    checklist = {
        "schema_version": "distinction_remediation_checklist_v1",
        "created_at_utc": timestamp,
        "rule": "open means acknowledged but not yet remediated; it is not a test failure",
        "items": [
            {"id": item_id, "risk": risk, "status": "open", "evidence": [], "resolution": None}
            for item_id, risk in CHECKLIST
        ],
    }
    atomic_write_json(output / "remediation_checklist.json", checklist)

    completion = {
        "status": "pass",
        "stage": "S0",
        "created_at_utc": timestamp,
        "head": head,
        "archive_count": len(archives),
        "all_archives_hashed": bool(archives) and all(item.get("sha256") for item in archives),
        "open_risks": [item_id for item_id, _ in CHECKLIST],
        "artifacts": ["legacy_evidence_v1.json", "remediation_checklist.json"],
    }
    atomic_write_json(output / "S0_COMPLETE.json", completion)
    print(json.dumps(completion, indent=2))


if __name__ == "__main__":
    main()
