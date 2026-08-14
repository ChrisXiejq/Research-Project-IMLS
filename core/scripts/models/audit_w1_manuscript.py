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

try:
    from .build_m1_evidence_package import (
        CLOSURE_FINAL,
        CLOSURE_MODES,
        audit_supervisor_feedback_closure,
        audit_supervisor_feedback_content_integration,
        stage_aware_status,
    )
except ImportError:  # direct script execution
    from build_m1_evidence_package import (
        CLOSURE_FINAL,
        CLOSURE_MODES,
        audit_supervisor_feedback_closure,
        audit_supervisor_feedback_content_integration,
        stage_aware_status,
    )


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


def verify_generated_manifest(
    path: Path, *, accepted_statuses: tuple[str, ...] = ("pass",)
) -> list[str]:
    payload = load_json(path)
    failures: list[str] = []
    if payload.get("status") not in accepted_statuses:
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


def discover_regression_test_count(repo: Path) -> int:
    """Count the tests discoverable by the exact suite invoked below.

    Binding execution to discovery is stricter and less brittle than a stale
    hard-coded count: deleting, adding, or silently skipping a test changes the
    expected count in the same checkout and is recorded in the receipt. Use a
    clean interpreter because this audit is executed as a script from inside
    ``core/scripts/models``; its already-imported module namespace otherwise
    changes unittest discovery and can collapse an import failure to one
    ``_FailedTest`` record.
    """

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,sys,unittest; "
                "start=pathlib.Path(sys.argv[1]); "
                "suite=unittest.defaultTestLoader.discover("
                "str(start),pattern='test_*.py'); "
                "print(suite.countTestCases())"
            ),
            str(repo / "core/scripts/models/tests"),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return int(completed.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--visual-review-complete",
        action="store_true",
        help="Confirm that all colour pages and key greyscale figures were manually inspected.",
    )
    parser.add_argument(
        "--closure-mode",
        choices=CLOSURE_MODES,
        default=CLOSURE_FINAL,
        help=(
            "Default final mode fails closed until SF1--SF4 are hash-verified. "
            "pre-sf4 emits an explicitly partial receipt and can never emit pass."
        ),
    )
    parser.add_argument("--supervisor-feedback-root", type=Path)
    parser.add_argument("--sf4-results-root", type=Path)
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
    accepted_generated_statuses = (
        ("pass", "partial_pre_sf4")
        if args.closure_mode != CLOSURE_FINAL
        else ("pass",)
    )
    for completion_name in (
        "W1_EVIDENCE_TABLES_COMPLETE.json",
        "W1_R3_FIGURES_COMPLETE.json",
    ):
        generated_failures.extend(
            verify_generated_manifest(
                W1_DIR / completion_name,
                accepted_statuses=accepted_generated_statuses,
            )
        )

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

    # Freeze discovery before executing the suite. Some regression tests
    # intentionally rebuild generated receipts; counting after the subprocess
    # can observe a transient fixture state and produce a false mismatch.
    discovered_test_count = discover_regression_test_count(REPO_ROOT)
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
    closure = audit_supervisor_feedback_closure(
        REPO_ROOT,
        supervisor_feedback_root=args.supervisor_feedback_root,
        sf4_results_root=args.sf4_results_root,
    )
    content_integration = audit_supervisor_feedback_content_integration(
        REPO_ROOT,
        closure_mode=args.closure_mode,
        closure_payload=closure,
    )
    base_checks = {
        "manuscript_sources_present": not missing_sources,
        "drafting_markers_absent": not drafting_markers,
        "citation_keys_resolved": cited == entries,
        "checked_source_count_in_range": 25 <= len(entries) <= 35,
        "generated_asset_hashes_resolve": not generated_failures,
        "pdf_present": pdf.is_file() and pdf.stat().st_size > 0,
        "pdf_page_count_recorded": isinstance(page_count, int) and page_count > 0,
        "latex_has_no_blocking_warning": not build_failures,
        "regression_suite_passes": (
            tests.returncode == 0 and test_count == discovered_test_count
        ),
        "visual_review_recorded": args.visual_review_complete,
    }
    checks = {
        **base_checks,
        "supervisor_feedback_final_closure": closure["status"] == "pass",
        "supervisor_feedback_results_integrated_into_paper": content_integration[
            "status"
        ]
        == "pass",
    }
    status = stage_aware_status(
        base_ready=(
            all(base_checks.values())
            and (
                args.closure_mode != CLOSURE_FINAL
                or content_integration["status"] == "pass"
            )
        ),
        closure_status=str(closure["status"]),
        closure_mode=args.closure_mode,
    )
    payload = {
        "schema_version": "w1_manuscript_complete_v1",
        "status": status,
        "stage": "W1",
        "closure_mode": args.closure_mode,
        "final_release_eligible": status == "pass",
        "supervisor_feedback_final_closure": closure,
        "supervisor_feedback_paper_content_integration": content_integration,
        "checks": checks,
        "citation_count": len(cited),
        "bibliography_entry_count": len(entries),
        "missing_citations": sorted(cited - entries),
        "uncited_entries": sorted(entries - cited),
        "drafting_markers": drafting_markers,
        "generated_asset_failures": generated_failures,
        "build_failures": build_failures,
        "regression_test_count": test_count,
        "discovered_regression_test_count": discovered_test_count,
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
            "additional_carla_required": closure["status"] != "pass",
            "r4_status": "not_run_by_frozen_design",
            "next_gate": (
                "Q1_scientific_rubric_and_release_audit"
                if status == "pass"
                else "complete_SF1_SF2_SF4_then_rerun_W1_final"
            ),
        },
        "release_only_pending": [
            "verified UCL candidate and supervisor metadata",
            "programme confirmation of the inserted AI-use disclosure",
            "programme word/page limit and word-count presentation",
            "final release Git commit and submitted-PDF digest",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({"status": status, "checks": checks}, indent=2, sort_keys=True))
    if status == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
