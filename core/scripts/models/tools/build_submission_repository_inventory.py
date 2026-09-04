#!/usr/bin/env python3
"""Build a provenance-preserving inventory of both submission repositories.

The inventory is intentionally descriptive.  It does not stage, delete, move,
commit, or otherwise mutate source files.  Every dirty path must match one
explicit scientific/release category; an unknown path fails the build.
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
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = "supervisor_bottleneck_repository_inventory_v1"
SELF_HASH_SENTINEL = "self_referential_generated_artifact"


def _run_git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {root}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _sanitize_remote(url: str) -> str:
    """Remove embedded HTTP credentials without changing normal SSH remotes."""

    if "://" not in url:
        return url
    split = urlsplit(url)
    if "@" not in split.netloc:
        return url
    hostname = split.netloc.rsplit("@", 1)[1]
    return urlunsplit((split.scheme, hostname, split.path, split.query, split.fragment))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _status_items(root: Path) -> list[dict[str, str]]:
    raw = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    tokens = raw.decode("utf-8", errors="surrogateescape").split("\0")
    items: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        status = token[:2]
        path = token[3:]
        old_path = ""
        if "R" in status or "C" in status:
            if index >= len(tokens):
                raise RuntimeError(f"Malformed porcelain rename record: {token!r}")
            old_path = path
            path = tokens[index]
            index += 1
        items.append({"status": status, "path": path, "old_path": old_path})
    return items


def classify_experiment_path(path: str) -> str:
    if path == ".gitignore":
        return "repository_hygiene"
    if path.startswith("openspec/changes/supervisor-bottleneck-thesis/"):
        return "new_thesis_work"
    if path == "core/scripts/models/tools/build_submission_repository_inventory.py":
        return "new_thesis_work"
    if path == "core/scripts/models/tests/test_build_submission_repository_inventory.py":
        return "new_thesis_work"
    if path.startswith("core/scripts/models/tools/build_supervisor_bottleneck_") and path.endswith(".py"):
        return "new_thesis_work"
    if path.startswith("core/scripts/models/tests/test_build_supervisor_bottleneck_") and path.endswith(".py"):
        return "new_thesis_work"
    if (
        path.startswith("core/scripts/models/")
        and "supervisor_bottleneck" in path
        and path.endswith(".py")
    ):
        return "new_thesis_work"
    if path.startswith("docs/paper/generated/supervisor_bottleneck_v1/"):
        return "generated_evidence"
    v3_prefixes = (
        "docs/paper/generated/capacity_history_v3/",
        "docs/paper/generated/integrated_thesis_story_v1/",
    )
    v3_files = {
        "core/scripts/models/experimental/capacity_study_v3_evidence.py",
        "core/scripts/models/experimental/generate_capacity_history_v3_results.py",
        "core/scripts/models/tools/generate_integrated_thesis_story.py",
        "core/scripts/models/tests/test_generate_capacity_history_v3_results.py",
        "core/scripts/models/tests/test_generate_integrated_thesis_story.py",
        "openspec/changes/capacity-controlled-transformer-study/tasks.md",
    }
    if path.startswith(v3_prefixes) or path in v3_files:
        return "v3_canonical"
    implicit_prefixes = (
        "core/scripts/carla/policies/",
        "core/scripts/carla/scenarios/",
        "core/scripts/carla/utils/",
        "docs/architecture/IMPLICIT_SMPC_SAFETY_FILTER.md",
    )
    implicit_files = {
        "core/scripts/analyze_implicit_smpc_safety_filter.py",
        "core/scripts/carla/render_implicit_smpc_birdeye.sh",
        "core/scripts/carla/run_all_scenarios.py",
        "core/scripts/carla/run_implicit_smpc_safety_filter.sh",
        "core/scripts/models/tests/test_distinction_regression_gates.py",
        "core/scripts/models/tests/test_implicit_smpc_safety_filter.py",
    }
    if path.startswith(implicit_prefixes) or path in implicit_files:
        return "implicit_filter_exploratory"
    if path.startswith("tmp/"):
        return "reproducible_cache"
    return "unresolved"


def classify_dissertation_path(path: str) -> str:
    if path in {"main.tex", "main.bib", "PROJECT_STATUS.md", "WRITING_GUIDE_ZH.md"}:
        return "manuscript_source"
    if path == "main.pdf":
        return "generated_final_pdf"
    if path.startswith("figures/"):
        return "manuscript_figure"
    if path.startswith("output/"):
        return "reproducible_build_output"
    if "Supervisor Progress Update" in path or "Supervisor Progress" in path:
        return "progress_document"
    if path.endswith("项目全流程中文说明.md") or "全流程中文" in path:
        return "progress_document"
    return "unresolved"


def _repository_snapshot(
    *,
    name: str,
    root: Path,
    classifier,
    output_path: Path,
) -> dict[str, Any]:
    if not (root / ".git").exists():
        raise FileNotFoundError(f"Expected Git repository: {root}")
    upstream = _run_git(root, "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
    ahead = behind = None
    if upstream:
        counts = _run_git(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        ahead_text, behind_text = counts.split()
        ahead, behind = int(ahead_text), int(behind_text)
    remotes: dict[str, str] = {}
    for remote in _run_git(root, "remote").splitlines():
        if remote:
            remotes[remote] = _sanitize_remote(
                _run_git(root, "remote", "get-url", remote)
            )

    dirty: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    output_resolved = output_path.resolve()
    for item in _status_items(root):
        relative = item["path"]
        absolute = root / relative
        category = classifier(relative)
        counts[category] = counts.get(category, 0) + 1
        sha256 = None
        size_bytes = None
        if absolute.is_file():
            size_bytes = absolute.stat().st_size
            sha256 = (
                SELF_HASH_SENTINEL
                if absolute.resolve() == output_resolved
                else _sha256(absolute)
            )
        dirty.append(
            {
                **item,
                "category": category,
                "size_bytes": size_bytes,
                "sha256": sha256,
            }
        )

    unresolved = [item["path"] for item in dirty if item["category"] == "unresolved"]
    return {
        "name": name,
        "root_name": root.name,
        "branch": _run_git(root, "branch", "--show-current"),
        "head": _run_git(root, "rev-parse", "HEAD"),
        "upstream": upstream or None,
        "ahead": ahead,
        "behind": behind,
        "remotes": remotes,
        "dirty_count": len(dirty),
        "classification_counts": counts,
        "unresolved_count": len(unresolved),
        "unresolved_paths": unresolved,
        "dirty_paths": dirty,
    }


def build_inventory(experiment_root: Path, dissertation_root: Path, output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    # Write a placeholder so the generated artifact appears in its own Git status.
    if not output.exists():
        output.write_text("{}\n", encoding="utf-8")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mutation_boundary": (
            "Read-only Git inspection plus this generated JSON artifact; no staging, "
            "move, delete, commit, reset, checkout or source-file write is performed."
        ),
        "repositories": [
            _repository_snapshot(
                name="experiment",
                root=experiment_root,
                classifier=classify_experiment_path,
                output_path=output,
            ),
            _repository_snapshot(
                name="dissertation",
                root=dissertation_root,
                classifier=classify_dissertation_path,
                output_path=output,
            ),
        ],
    }
    all_resolved = all(repo["unresolved_count"] == 0 for repo in payload["repositories"])
    payload["status"] = "pass" if all_resolved else "fail"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not all_resolved:
        details = {
            repo["name"]: repo["unresolved_paths"]
            for repo in payload["repositories"]
            if repo["unresolved_paths"]
        }
        raise RuntimeError(f"Unclassified dirty paths: {details}")
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    default_experiment = Path(__file__).resolve().parents[4]
    parser.add_argument("--experiment-root", type=Path, default=default_experiment)
    parser.add_argument(
        "--dissertation-root",
        type=Path,
        default=default_experiment.parent / "Jiaqi-Xie-Dissertation",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            default_experiment
            / "docs/paper/generated/supervisor_bottleneck_v1/repository_state/repository_snapshot.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    payload = build_inventory(
        args.experiment_root.resolve(),
        args.dissertation_root.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({"status": payload["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
