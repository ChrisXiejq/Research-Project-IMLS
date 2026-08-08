#!/usr/bin/env python3
"""Audit and bind the completed W1 dissertation manuscript.

The audit is intentionally narrower than the later Q1 submission audit.  It
checks the scientific manuscript, citations, generated presentation assets,
LaTeX build and local regression suite without reopening any experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
LATEX_DIR = REPO_ROOT / "docs/dissertation/latex"
W1_DIR = REPO_ROOT / "docs/paper/generated/distinction_v1/11_w1_manuscript"
OUTPUT = W1_DIR / "W1_MANUSCRIPT_COMPLETE.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def verify_generated_manifest(path: Path) -> list[str]:
    payload = load_json(path)
    failures: list[str] = []
    if payload.get("status") != "pass":
        failures.append(f"status_not_pass:{path.name}")
    for relative, expected in payload.get("source_sha256", {}).items():
        source = REPO_ROOT / relative
        if not source.is_file() or sha256(source) != expected:
            failures.append(f"source_hash:{relative}")
    for name, expected in payload.get("artifacts", {}).items():
        artifact = W1_DIR / name
        if not artifact.is_file() or sha256(artifact) != expected:
            failures.append(f"artifact_hash:{name}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--visual-review-complete",
        action="store_true",
        help="Confirm that all colour pages and key greyscale figures were manually inspected.",
    )
    args = parser.parse_args()

    tex_files = sorted(LATEX_DIR.rglob("*.tex"))
    source_files = tex_files + [
        LATEX_DIR / "references.bib",
        LATEX_DIR / "vendor/tmlr.sty",
        LATEX_DIR / "vendor/tmlr.bst",
        LATEX_DIR / "vendor/fancyhdr.sty",
    ]
    missing_sources = [str(path) for path in source_files if not path.is_file()]

    tex = "\n".join(path.read_text(encoding="utf-8") for path in tex_files)
    marker_pattern = re.compile(r"TODO|TBD|PLACEHOLDER|\\TODO|XXXX", re.IGNORECASE)
    drafting_markers = sorted(set(marker_pattern.findall(tex)))

    cited = {
        key.strip()
        for match in re.finditer(r"\\cite\w*\{([^}]*)\}", tex)
        for key in match.group(1).split(",")
        if key.strip()
    }
    bibliography = (LATEX_DIR / "references.bib").read_text(encoding="utf-8")
    entries = set(re.findall(r"^@\w+\{([^,]+),", bibliography, flags=re.MULTILINE))

    generated_failures: list[str] = []
    for completion_name in (
        "W1_EVIDENCE_TABLES_COMPLETE.json",
        "W1_R3_FIGURES_COMPLETE.json",
    ):
        generated_failures.extend(verify_generated_manifest(W1_DIR / completion_name))

    pdf = LATEX_DIR / "build/main.pdf"
    log = LATEX_DIR / "build/main.log"
    blg = LATEX_DIR / "build/main.blg"
    build_text = (log.read_text(encoding="utf-8", errors="replace") if log.is_file() else "")
    bib_text = (blg.read_text(encoding="utf-8", errors="replace") if blg.is_file() else "")
    forbidden_build_patterns = {
        "undefined_reference": r"There were undefined references|Reference `[^']+' .* undefined",
        "undefined_citation": r"undefined citations|Citation `[^']+' .* undefined",
        "horizontal_overflow": r"Overfull \\hbox",
        "latex_error": r"LaTeX Error:|Emergency stop|Fatal error",
        "bibtex_warning": r"Warning--",
    }
    build_failures = [
        name
        for name, pattern in forbidden_build_patterns.items()
        if re.search(pattern, build_text + "\n" + bib_text)
    ]

    page_count = None
    if pdf.is_file():
        info = subprocess.run(
            ["pdfinfo", str(pdf)], capture_output=True, text=True, check=True
        ).stdout
        match = re.search(r"^Pages:\s+(\d+)$", info, flags=re.MULTILINE)
        page_count = int(match.group(1)) if match else None

    tests = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "core/scripts/models/tests",
            "-p",
            "test_*.py",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    match = re.search(r"Ran (\d+) tests", tests.stderr + tests.stdout)
    test_count = int(match.group(1)) if match else None

    checks = {
        "manuscript_sources_present": not missing_sources,
        "drafting_markers_absent": not drafting_markers,
        "citation_keys_resolved": cited == entries,
        "checked_source_count_in_range": 25 <= len(entries) <= 35,
        "generated_asset_hashes_resolve": not generated_failures,
        "pdf_present": pdf.is_file() and pdf.stat().st_size > 0,
        "pdf_page_count_recorded": page_count == 24,
        "latex_has_no_blocking_warning": not build_failures,
        "regression_suite_passes": tests.returncode == 0 and test_count == 66,
        "visual_review_recorded": args.visual_review_complete,
    }
    status = "pass" if all(checks.values()) else "fail"
    payload = {
        "schema_version": "w1_manuscript_complete_v1",
        "status": status,
        "stage": "W1",
        "checks": checks,
        "citation_count": len(cited),
        "bibliography_entry_count": len(entries),
        "missing_citations": sorted(cited - entries),
        "uncited_entries": sorted(entries - cited),
        "drafting_markers": drafting_markers,
        "generated_asset_failures": generated_failures,
        "build_failures": build_failures,
        "regression_test_count": test_count,
        "pdf": {
            "path": str(pdf.relative_to(REPO_ROOT)),
            "pages": page_count,
            "sha256": sha256(pdf) if pdf.is_file() else None,
        },
        "source_sha256": {
            str(path.relative_to(REPO_ROOT)): sha256(path)
            for path in source_files
            if path.is_file()
        },
        "visual_review": {
            "all_pages_colour": "pass" if args.visual_review_complete else "not_recorded",
            "key_figures_greyscale": "pass" if args.visual_review_complete else "not_recorded",
            "horizontal_overflow": "none_observed" if args.visual_review_complete else "not_recorded",
            "figure_and_appendix_order": "pass" if args.visual_review_complete else "not_recorded",
        },
        "scope": {
            "additional_carla_required": False,
            "r4_status": "not_run_by_frozen_design",
            "next_gate": "Q1_scientific_rubric_and_release_audit",
        },
        "release_only_pending": [
            "verified UCL candidate and supervisor metadata",
            "programme-approved AI-use disclosure wording",
            "final release Git commit and submitted-PDF digest",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({"status": status, "checks": checks}, indent=2, sort_keys=True))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
