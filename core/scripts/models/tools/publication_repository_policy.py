#!/usr/bin/env python3
"""Fail-closed checks for the publication-facing repository boundary."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping
from urllib.parse import unquote


FORBIDDEN_PREFIXES = (
    "artifacts/",
    "tmp/",
    "openspec/",
    ".agents/",
    ".codex/",
    ".repo-maintenance/",
    "docs/internal/",
    "docs/presentation/",
    "docs/paper/",
)
PUBLIC_MEDIA_PATHS = {"docs/paper/CARLA_video.mp4"}
FORBIDDEN_BASENAMES = {"CODEX_HANDOFF.md", "PROJECT_STATUS.md"}
FORBIDDEN_SUFFIXES = (
    ".log",
    ".jsonl",
    ".mp4",
    ".avi",
    ".ckpt",
    ".h5",
    ".pt",
    ".pth",
    ".pb",
)
FORBIDDEN_COMPOUND_SUFFIXES = (".tar.gz", ".tar.xz", ".tar.bz2")
REQUIRED_PATHS = {
    "README.md",
    "REPRODUCIBILITY.md",
    "CITATION.cff",
    "THIRD_PARTY_NOTICES.md",
    "core/scripts/carla/run_all_scenarios.py",
    "core/scripts/carla/policies/smpc_agent.py",
    "core/scripts/models/evaluate_prediction_model.py",
}
MAX_TRACKED_FILE_BYTES = 20 * 1024 * 1024
TRACKED_BYTES_EXCLUDED_PATHS: set[str] = set()
PUBLIC_MARKDOWN_PATHS = (
    "README.md",
    "REPRODUCIBILITY.md",
    "THIRD_PARTY_NOTICES.md",
)
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
REPOSITORY_PATH_PREFIXES = ("core/", "docs/")


def _normalise_path(value: str) -> str:
    path = value.replace(os.sep, "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _is_forbidden(path: str) -> bool:
    normalised = _normalise_path(path)
    pure = PurePosixPath(normalised)
    lower = normalised.lower()
    return (
        pure.is_absolute()
        or ".." in pure.parts
        or (
            normalised not in PUBLIC_MEDIA_PATHS
            and any(normalised.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)
        )
        or pure.name in FORBIDDEN_BASENAMES
        or pure.name.startswith("HANDOFF_")
        or normalised.startswith("docs/literature/")
        or normalised.startswith("docs/dissertation/")
        or (
            normalised not in PUBLIC_MEDIA_PATHS
            and any(lower.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES)
        )
        or any(lower.endswith(suffix) for suffix in FORBIDDEN_COMPOUND_SUFFIXES)
    )


def audit_paths(
    tracked_paths: list[str], file_sizes: Mapping[str, int]
) -> dict[str, object]:
    """Classify a deterministic list of repository-relative tracked paths."""

    paths = sorted({_normalise_path(path) for path in tracked_paths if path})
    path_set = set(paths)
    missing = sorted(REQUIRED_PATHS - path_set)
    forbidden = sorted(path for path in paths if _is_forbidden(path))
    oversized = [
        {"path": path, "bytes": int(file_sizes.get(path, 0))}
        for path in paths
        if int(file_sizes.get(path, 0)) > MAX_TRACKED_FILE_BYTES
    ]
    status = "pass" if not missing and not forbidden and not oversized else "fail"
    return {
        "schema_version": "publication_repository_policy_v1",
        "status": status,
        "tracked_path_count": len(paths),
        "tracked_bytes": int(
            sum(
                int(file_sizes.get(path, 0))
                for path in paths
                if path not in TRACKED_BYTES_EXCLUDED_PATHS
            )
        ),
        "tracked_bytes_excluded_paths": sorted(
            path for path in paths if path in TRACKED_BYTES_EXCLUDED_PATHS
        ),
        "missing_required_paths": missing,
        "forbidden_tracked_paths": forbidden,
        "oversized_tracked_files": oversized,
        "maximum_tracked_file_bytes": MAX_TRACKED_FILE_BYTES,
    }


def _repository_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if completed.returncode == 0:
        return [
            entry.decode("utf-8", errors="surrogateescape")
            for entry in completed.stdout.split(b"\0")
            if entry
        ]
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )


def _local_link_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    target = unquote(target.split("#", 1)[0])
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    return target


def _repository_code_path(value: str) -> str | None:
    candidate = value.strip().rstrip(".,:;")
    if candidate.startswith("/path/to/") or candidate.endswith("/"):
        return None
    if candidate.startswith(REPOSITORY_PATH_PREFIXES):
        return candidate
    if candidate in {"README.md", "REPRODUCIBILITY.md", "CITATION.cff", "THIRD_PARTY_NOTICES.md"}:
        return candidate
    return None


def audit_markdown_links(
    root: Path, markdown_paths: Iterable[str]
) -> list[dict[str, str]]:
    """Return broken local Markdown links and explicit repository code paths."""

    findings: list[dict[str, str]] = []
    for document_relative in sorted(markdown_paths):
        document = root / document_relative
        if not document.is_file():
            continue
        text = document.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(text):
            target = _local_link_target(match.group(1))
            if target is None:
                continue
            if target.startswith("/"):
                exists = False
            else:
                exists = (document.parent / target).resolve().exists()
            if not exists:
                findings.append(
                    {
                        "document": document_relative,
                        "target": target,
                        "kind": "markdown_link",
                    }
                )
        for match in BACKTICK_RE.finditer(text):
            target = _repository_code_path(match.group(1))
            if target is None or (root / target).exists():
                continue
            findings.append(
                {
                    "document": document_relative,
                    "target": target,
                    "kind": "repository_path",
                }
            )
    return sorted(findings, key=lambda row: (row["document"], row["target"], row["kind"]))


def audit_repository(root: Path) -> dict[str, object]:
    """Audit a Git worktree or an unpacked source archive without mutating it."""

    resolved_root = root.resolve()
    tracked_paths = _repository_paths(resolved_root)
    file_sizes = {
        relative: (resolved_root / relative).stat().st_size
        for relative in tracked_paths
        if (resolved_root / relative).is_file()
    }
    report = audit_paths(tracked_paths, file_sizes)
    broken_links = audit_markdown_links(resolved_root, PUBLIC_MARKDOWN_PATHS)
    report.update(
        {
            "repository_root": ".",
            "broken_public_document_links": broken_links,
        }
    )
    if broken_links:
        report["status"] = "fail"
    return report


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit_repository(args.root)
    output = args.output
    if not output.is_absolute():
        output = args.root / output
    _write_json(output, report)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
