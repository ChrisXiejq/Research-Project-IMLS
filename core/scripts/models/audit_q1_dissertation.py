#!/usr/bin/env python3
"""Run the Q1 scientific, rubric and release audit without reopening CARLA.

The audit has two deliberately separate outcomes:

* scientific/reproducibility readiness, which is machine-verifiable; and
* submission readiness, which additionally requires verified candidate and
  programme metadata that must never be guessed from the repository.

With ``--clean-checkout`` the command requires a clean Git worktree, creates a
temporary detached worktree at HEAD, regenerates A2/M1/W1 evidence, runs the
analysis tests, compiles the PDF and removes the temporary worktree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable

try:
    from .build_m1_evidence_package import (
        CLOSURE_FINAL,
        CLOSURE_MODES,
        CLOSURE_PRE_SF4,
        SUPERVISOR_CONTENT_EVIDENCE_IDS,
        audit_supervisor_feedback_closure,
        audit_supervisor_feedback_content_integration,
        stage_aware_status,
    )
except ImportError:  # direct script execution
    from build_m1_evidence_package import (
        CLOSURE_FINAL,
        CLOSURE_MODES,
        CLOSURE_PRE_SF4,
        SUPERVISOR_CONTENT_EVIDENCE_IDS,
        audit_supervisor_feedback_closure,
        audit_supervisor_feedback_content_integration,
        stage_aware_status,
    )


DEFAULT_REPO = Path(__file__).resolve().parents[3]
Q1_RELATIVE = Path("docs/paper/generated/distinction_v1/12_q1_final_audit")
LATEX_RELATIVE = Path("docs/dissertation/latex")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return payload


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    require_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )
    if require_success and completed.returncode != 0:
        rendered = " ".join(command)
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {rendered}\n"
            f"stdout:\n{completed.stdout[-4000:]}\n"
            f"stderr:\n{completed.stderr[-4000:]}"
        )
    return completed


def verify_completion(
    directory: Path, filename: str, *, accepted_statuses: tuple[str, ...] = ("pass",)
) -> list[str]:
    marker = directory / filename
    failures: list[str] = []
    if not marker.is_file():
        return [f"missing_marker:{marker}"]
    payload = load_json(marker)
    if payload.get("status") not in accepted_statuses:
        failures.append(f"status_not_pass:{marker}")
    for artifact, expected in payload.get("artifacts", {}).items():
        path = directory / artifact
        if not path.is_file() or sha256(path) != expected:
            failures.append(f"artifact_hash:{path}")
    return failures


def verify_w1_manifest(repo: Path, filename: str) -> list[str]:
    directory = repo / Q1_RELATIVE.parent / "11_w1_manuscript"
    marker = directory / filename
    failures: list[str] = []
    if not marker.is_file():
        return [f"missing_marker:{marker}"]
    payload = load_json(marker)
    if payload.get("status") != "pass":
        failures.append(f"status_not_pass:{marker}")
    for relative, expected in payload.get("source_sha256", {}).items():
        path = repo / relative
        if not path.is_file() or sha256(path) != expected:
            failures.append(f"source_hash:{relative}")
    for artifact, expected in payload.get("artifacts", {}).items():
        path = directory / artifact
        if not path.is_file() or sha256(path) != expected:
            failures.append(f"artifact_hash:{artifact}")
    return failures


def verify_paper_evidence_package(repo: Path, closure_mode: str) -> list[str]:
    assets = repo / "docs/paper/generated/paper_assets_v1"
    marker = assets / "PAPER_EVIDENCE_PACKAGE_COMPLETE.json"
    if not marker.is_file():
        return [f"missing_marker:{marker}"]
    payload = load_json(marker)
    expected_status = (
        "partial_pre_sf4" if closure_mode == CLOSURE_PRE_SF4 else "pass"
    )
    failures: list[str] = []
    if (
        payload.get("status") != expected_status
        or payload.get("closure_mode") != closure_mode
        or payload.get("final_release_eligible") is not (closure_mode == CLOSURE_FINAL)
    ):
        failures.append(f"paper_evidence_stage_status:{marker}")
    bindings = {
        "results_manifest_sha256": assets / "paper_results_manifest.json",
        "figures_manifest_sha256": assets / "figures/paper_figures_manifest.json",
        "png_completion_sha256": assets / "figures/PAPER_FIGURES_PNG_COMPLETE.json",
        "inventory_sha256": assets / "paper_asset_inventory.csv",
        "claim_matrix_sha256": assets / "paper_claim_evidence_matrix.csv",
        "key_results_sha256": assets / "paper_key_results.csv",
    }
    for field, path in bindings.items():
        if not path.is_file() or payload.get(field) != sha256(path):
            failures.append(f"paper_evidence_hash:{field}")
    return failures


def compare_artifacts(
    regenerated: Path, canonical: Path, names: Iterable[str]
) -> list[str]:
    failures: list[str] = []
    for name in names:
        new = regenerated / name
        old = canonical / name
        if not new.is_file():
            failures.append(f"regenerated_missing:{new}")
        elif not old.is_file():
            failures.append(f"canonical_missing:{old}")
        elif sha256(new) != sha256(old):
            failures.append(f"regenerated_mismatch:{name}")
    return failures


def discover_regression_test_count(repo: Path) -> int:
    """Count tests discoverable by the exact analysis-suite pattern."""

    suite = unittest.defaultTestLoader.discover(
        str(repo / "core/scripts/models/tests"),
        pattern="test_*.py",
    )
    return suite.countTestCases()


def pdf_pages(pdf: Path, cwd: Path) -> int | None:
    info = run(["pdfinfo", str(pdf)], cwd=cwd).stdout
    match = re.search(r"^Pages:\s+(\d+)$", info, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def clean_checkout_audit(
    repo: Path,
    *,
    python: str,
    node: str,
    expected_tests: int | None,
    closure_mode: str = CLOSURE_FINAL,
) -> dict[str, Any]:
    status = run(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    if status:
        raise RuntimeError(
            "--clean-checkout requires a clean repository; commit the Q1 source "
            "changes before running this gate."
        )
    commit = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    temporary_root = Path(tempfile.mkdtemp(prefix="imls_q1_clean_"))
    checkout = temporary_root / "repo"
    worktree_added = False
    commands: list[dict[str, Any]] = []
    comparisons: list[str] = []
    try:
        run(["git", "worktree", "add", "--detach", str(checkout), commit], cwd=repo)
        worktree_added = True
        regenerated_root = temporary_root / "regenerated"
        regenerated_root.mkdir()

        active_help = [
            [python, "core/scripts/models/build_r3_paper_synthesis.py", "--help"],
            [python, "core/scripts/models/build_m1_evidence_package.py", "--help"],
            [python, "core/scripts/models/build_w1_latex_evidence.py", "--help"],
            [python, "core/scripts/models/audit_w1_manuscript.py", "--help"],
            [python, "core/scripts/models/audit_q1_dissertation.py", "--help"],
            [python, "core/scripts/models/build_paper_results_manifest.py", "--help"],
            [python, "core/scripts/models/build_paper_figures.py", "--help"],
            [
                python,
                "core/scripts/models/build_supervisor_feedback_paper_integration.py",
                "--help",
            ],
            [python, "core/scripts/models/audit_paper_evidence_package.py", "--help"],
            [node, "core/scripts/models/render_w1_r3_figures_png.cjs", "--help"],
        ]
        for command in active_help:
            result = run(command, cwd=checkout)
            commands.append({"command": command, "returncode": result.returncode})

        stage_specs = [
            (
                [
                    python,
                    "core/scripts/models/build_r3_paper_synthesis.py",
                    "--repo-root",
                    str(checkout),
                    "--output",
                    str(regenerated_root / "a2"),
                ],
                regenerated_root / "a2",
                checkout
                / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis",
                "A2_COMPLETE.json",
            ),
            (
                [
                    python,
                    "core/scripts/models/build_m1_evidence_package.py",
                    "--repo-root",
                    str(checkout),
                    "--output",
                    str(regenerated_root / "m1"),
                    "--closure-mode",
                    closure_mode,
                ],
                regenerated_root / "m1",
                checkout
                / "docs/paper/generated/distinction_v1/10_four_hypothesis_evidence",
                "M1_COMPLETE.json",
            ),
            (
                [
                    python,
                    "core/scripts/models/build_w1_latex_evidence.py",
                    "--repo-root",
                    str(checkout),
                    "--output",
                    str(regenerated_root / "w1"),
                    "--closure-mode",
                    closure_mode,
                ],
                regenerated_root / "w1",
                checkout
                / "docs/paper/generated/distinction_v1/11_w1_manuscript",
                "W1_EVIDENCE_TABLES_COMPLETE.json",
            ),
            (
                [
                    python,
                    "core/scripts/models/build_paper_results_manifest.py",
                    "--repo-root",
                    str(checkout),
                    "--output-dir",
                    str(regenerated_root / "paper"),
                    "--closure-mode",
                    closure_mode,
                ],
                regenerated_root / "paper",
                checkout / "docs/paper/generated/paper_assets_v1",
                "PAPER_TABLES_COMPLETE.json",
            ),
            (
                [
                    python,
                    "core/scripts/models/build_paper_figures.py",
                    "--repo-root",
                    str(checkout),
                    "--output-dir",
                    str(regenerated_root / "paper/figures"),
                    "--tables-dir",
                    str(regenerated_root / "paper"),
                    "--closure-mode",
                    closure_mode,
                ],
                regenerated_root / "paper/figures",
                checkout / "docs/paper/generated/paper_assets_v1/figures",
                "PAPER_FIGURES_COMPLETE.json",
            ),
        ]
        for command, regenerated, canonical, marker_name in stage_specs:
            result = run(command, cwd=checkout)
            commands.append({"command": command, "returncode": result.returncode})
            marker = load_json(regenerated / marker_name)
            names = list(marker.get("artifacts", {}))
            comparisons.extend(compare_artifacts(regenerated, canonical, names))

        paper_root = regenerated_root / "paper"
        canonical_paper = checkout / "docs/paper/generated/paper_assets_v1"
        shutil.copy2(canonical_paper / "README.md", paper_root / "README.md")
        png = run(
            [
                node,
                "core/scripts/models/render_paper_figures_png.cjs",
                str(paper_root / "figures"),
            ],
            cwd=checkout,
        )
        commands.append(
            {
                "command": [node, "core/scripts/models/render_paper_figures_png.cjs"],
                "returncode": png.returncode,
            }
        )
        png_marker = load_json(
            paper_root / "figures/PAPER_FIGURES_PNG_COMPLETE.json"
        )
        comparisons.extend(
            compare_artifacts(
                paper_root / "figures",
                canonical_paper / "figures",
                [*sorted(png_marker.get("files", {})), "PAPER_FIGURES_PNG_COMPLETE.json"],
            )
        )
        paper_audit = run(
            [
                python,
                "core/scripts/models/audit_paper_evidence_package.py",
                "--repo-root",
                str(checkout),
                "--assets-dir",
                str(paper_root),
                "--closure-mode",
                closure_mode,
            ],
            cwd=checkout,
        )
        commands.append(
            {
                "command": [python, "core/scripts/models/audit_paper_evidence_package.py"],
                "returncode": paper_audit.returncode,
            }
        )
        comparisons.extend(
            compare_artifacts(
                paper_root,
                canonical_paper,
                [
                    "paper_asset_inventory.csv",
                    "paper_claim_evidence_matrix.csv",
                    "paper_key_results.csv",
                    "PAPER_EVIDENCE_PACKAGE_COMPLETE.json",
                ],
            )
        )

        tests = run(
            [
                python,
                "-m",
                "unittest",
                "discover",
                "-s",
                "core/scripts/models/tests",
                "-p",
                "test_*.py",
            ],
            cwd=checkout,
        )
        test_match = re.search(r"Ran (\d+) tests", tests.stdout + tests.stderr)
        test_count = int(test_match.group(1)) if test_match else None
        discovered_test_count = discover_regression_test_count(checkout)
        bound_test_count = (
            expected_tests if expected_tests is not None else discovered_test_count
        )
        commands.append(
            {"command": [python, "-m", "unittest", "discover"], "returncode": 0}
        )

        run(["make", "pdf"], cwd=checkout / LATEX_RELATIVE)
        pdf = checkout / LATEX_RELATIVE / "build/main.pdf"
        pages = pdf_pages(pdf, checkout)
        w1 = run(
            [
                python,
                "core/scripts/models/audit_w1_manuscript.py",
                "--visual-review-complete",
                "--closure-mode",
                closure_mode,
            ],
            cwd=checkout,
            require_success=closure_mode == CLOSURE_FINAL,
        )
        commands.append(
            {
                "command": [python, "core/scripts/models/audit_w1_manuscript.py"],
                "returncode": w1.returncode,
            }
        )
        expected_w1_status = (
            "pass" if closure_mode == CLOSURE_FINAL else "partial_pre_sf4"
        )
        base_checks = {
            "active_scripts_help": all(
                row["returncode"] == 0 for row in commands[: len(active_help)]
            ),
            "a2_m1_w1_recompute_matches": not comparisons,
            "paper_asset_chain_recompute_matches": not comparisons,
            "analysis_tests_pass": (
                test_count == discovered_test_count == bound_test_count
            ),
            "latex_build_pass": pdf.is_file() and pdf.stat().st_size > 0,
            "pdf_page_count_recorded": isinstance(pages, int) and pages > 0,
            "w1_audit_stage_appropriate": f'"status": "{expected_w1_status}"' in w1.stdout,
        }
        clean_status = (
            "pass"
            if closure_mode == CLOSURE_FINAL and all(base_checks.values())
            else "partial_pre_sf4"
            if closure_mode == CLOSURE_PRE_SF4 and all(base_checks.values())
            else "fail"
        )
        return {
            "schema_version": "q1_clean_checkout_v1",
            "status": clean_status,
            "closure_mode": closure_mode,
            "commit": commit,
            "checks": base_checks,
            "regression_test_count": test_count,
            "discovered_regression_test_count": discovered_test_count,
            "bound_regression_test_count": bound_test_count,
            "pdf": {
                "pages": pages,
                "sha256": sha256(pdf) if pdf.is_file() else None,
            },
            "regeneration_failures": comparisons,
            "commands": commands,
        }
    finally:
        if worktree_added:
            run(
                ["git", "worktree", "remove", "--force", str(checkout)],
                cwd=repo,
                require_success=False,
            )
        shutil.rmtree(temporary_root, ignore_errors=True)


def manuscript_audit(
    repo: Path,
    *,
    visual_review_complete: bool,
    programme_ai_confirmed: bool,
    module_length_rule_confirmed: bool,
    closure_mode: str = CLOSURE_FINAL,
    supervisor_feedback_root: Path | None = None,
    sf4_results_root: Path | None = None,
) -> dict[str, Any]:
    latex = repo / LATEX_RELATIVE
    tex_files = sorted(latex.rglob("*.tex"))
    tex = "\n".join(path.read_text(encoding="utf-8") for path in tex_files)
    visible_tex = "\n".join(
        line.split("%", 1)[0] for line in tex.splitlines()
    )
    bibliography = (latex / "references.bib").read_text(encoding="utf-8")
    citation_keys = {
        key.strip()
        for match in re.finditer(r"\\cite\w*\{([^}]*)\}", tex)
        for key in match.group(1).split(",")
        if key.strip()
    }
    bib_keys = set(
        re.findall(r"^@\w+\{([^,]+),", bibliography, flags=re.MULTILINE)
    )

    m1_dir = repo / "docs/paper/generated/distinction_v1/10_four_hypothesis_evidence"
    a2_dir = repo / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis"
    m1 = load_json(m1_dir / "M1_EVIDENCE_MANIFEST.json")
    m1_ids = {record["evidence_id"] for record in m1["records"]}
    evidence_comments: set[str] = set()
    for line in tex.splitlines():
        if "% EVIDENCE:" in line:
            evidence_comments.update(
                item.strip()
                for item in line.split("% EVIDENCE:", 1)[1].split(",")
                if item.strip()
            )

    a2 = load_json(a2_dir / "A2_COMPLETE.json")
    marker_failures = []
    expected_m1_statuses = (
        ("pass", "partial_pre_sf4")
        if closure_mode == CLOSURE_PRE_SF4
        else ("pass",)
    )
    marker_failures.extend(
        verify_completion(
            m1_dir,
            "M1_COMPLETE.json",
            accepted_statuses=expected_m1_statuses,
        )
    )
    marker_failures.extend(verify_completion(a2_dir, "A2_COMPLETE.json"))
    marker_failures.extend(
        verify_w1_manifest(repo, "W1_EVIDENCE_TABLES_COMPLETE.json")
    )
    marker_failures.extend(
        verify_w1_manifest(repo, "W1_R3_FIGURES_COMPLETE.json")
    )
    paper_evidence_failures = verify_paper_evidence_package(repo, closure_mode)
    marker_failures.extend(paper_evidence_failures)

    # Negated statements are safeguards, not overclaims. Remove the explicit
    # forms used by the manuscript before applying the assertion-language scan.
    assertion_tex = re.sub(
        r"\b(?:cannot|does not|do not|did not|not)\s+prove[sd]?\b",
        "bounded_statement",
        visible_tex,
        flags=re.IGNORECASE,
    )
    assertion_tex = re.sub(
        r"\b(?:avoid(?:ing)?|reject(?:ing)?)\b[^.]{0,120}\bprove[sd]?\b",
        "bounded_statement",
        assertion_tex,
        flags=re.IGNORECASE,
    )
    prohibited_patterns = {
        "proof_language": r"\b(?:prove[sd]?|proving)\b",
        "false_significance": r"\bstatistically significant\b",
        "transformer_general_null": r"Transformer(?:s)? (?:are|is) ineffective",
        "supervisor_single_cause": r"supervisor (?:is|was|caused) (?:the )?(?:single|only) cause",
        "complete_frontier": r"\bcomplete frontier\b",
        "real_world_safety": r"\bproves? real[- ]world safety\b",
    }
    overclaim_hits = {
        name: re.findall(pattern, assertion_tex, flags=re.IGNORECASE)
        for name, pattern in prohibited_patterns.items()
        if re.search(pattern, assertion_tex, flags=re.IGNORECASE)
    }
    credential_scan = run(
        [
            "git",
            "grep",
            "-nEI",
            (
                r"(password|passwd|api[_-]?key|secret)[[:space:]]*[:=]"
                r"[[:space:]]*[A-Za-z0-9+/=_-]{8,}|"
                r"ssh[[:space:]]+-p[[:space:]]+[0-9]+[[:space:]]+root@|"
                r"root@[A-Za-z0-9.-]+"
            ),
            "--",
            ".",
            ":!docs/dissertation/*.pdf",
        ],
        cwd=repo,
        require_success=False,
    )
    credential_hits = [
        line for line in credential_scan.stdout.splitlines() if line.strip()
    ]

    title_tokens = (
        "Task-Adapted Motion Prediction under",
        "Predictor--Risk Coupling: A Controlled CARLA",
        "Give-Way Study",
    )
    closure = audit_supervisor_feedback_closure(
        repo,
        supervisor_feedback_root=supervisor_feedback_root,
        sf4_results_root=sf4_results_root,
    )
    content_integration = audit_supervisor_feedback_content_integration(
        repo,
        closure_mode=closure_mode,
        closure_payload=closure,
    )
    base_scientific_checks = {
        "m1_value_audit_pass": (
            m1.get("status") in expected_m1_statuses
            and m1.get("record_count") == 82
            and load_json(m1_dir / "M1_VALUE_AUDIT.json").get("status") == "pass"
        ),
        "m1_a2_completion_hashes_resolve": not marker_failures,
        "paper_asset_chain_stage_and_hashes_resolve": not paper_evidence_failures,
        "a2_corrected_matrix_complete": (
            a2.get("status") == "pass"
            and a2.get("r3_rollouts") == 80
            and a2.get("independent_init_groups") == 5
        ),
        "h3_verdict_consistent": (
            a2.get("h3", {}).get("directionally_supported_cells") == 2
            and a2.get("h3", {}).get("prespecified_cells") == 8
            and "Only two of eight" in tex
        ),
        "h4_verdict_consistent": (
            a2.get("h4", {}).get("dominance_cells") == 3
            and a2.get("h4", {}).get("prespecified_cells") == 12
            and "3/12" in tex
        ),
        "h1_physical_baseline_boundary_present": (
            "constant velocity" in tex
            and "clipped constant acceleration" in tex
            and "train-mean" in tex
        ),
        "h2_matched_pair_boundary_present": all(
            token in tex for token in ("B2-M", "B2-D", "T1", "T2", "not parameter matched")
        ),
        "h3_stack_and_tail_boundary_present": (
            "frozen predictor-stack" in tex
            and "response-active" in tex
            and "not pooled with R3" in tex
        ),
        "h4_observation_not_causality": (
            "context-dependent operating point" in tex
            and "not an equivalence test" in tex
            and ("not a theorem" in tex or "rather than a theorem" in tex)
        ),
        "legacy_and_collision_boundary_present": (
            "Legacy Day10--13" in tex
            and "253 collision callbacks" in tex
            and "actual CARLA actor bounding boxes" in tex
        ),
        "small_n_disclosed_without_fake_significance": (
            "smallest attainable non-zero two-sided exact p-value" in tex
            and "0.0625" in tex
            and not overclaim_hits.get("false_significance")
        ),
        "title_matches_frozen_route": all(token in tex for token in title_tokens),
        "citation_keys_resolve": citation_keys == bib_keys,
        "primary_source_count_in_range": 25 <= len(bib_keys) <= 35,
        "headline_evidence_ids_resolve": evidence_comments
        <= (m1_ids | set(SUPERVISOR_CONTENT_EVIDENCE_IDS)),
        "prohibited_overclaim_absent": not overclaim_hits,
        "data_availability_boundary_present": (
            "Data and artefact availability" in tex
            and "clean checkout can reproduce the reported analysis" in tex
        ),
        "first_page_ai_disclosure_in_source": (
            "Generative-AI disclosure: OpenAI Codex" in tex
            and "neither an author nor an evidence source" in tex
        ),
        "visual_review_recorded": visual_review_complete,
    }
    scientific_checks = {
        **base_scientific_checks,
        "supervisor_feedback_final_closure": closure["status"] == "pass",
        "supervisor_feedback_results_integrated_into_paper": content_integration[
            "status"
        ]
        == "pass",
    }
    scientific_status = stage_aware_status(
        base_ready=(
            all(base_scientific_checks.values())
            and (
                closure_mode != CLOSURE_FINAL
                or content_integration["status"] == "pass"
            )
        ),
        closure_status=str(closure["status"]),
        closure_mode=closure_mode,
    )

    neutral_metadata = (
        "UCL MSc Candidate" in tex
        or "metadata withheld" in tex
        or "W1 review draft" in tex
    )
    release_checks = {
        "candidate_and_programme_metadata_verified": not neutral_metadata,
        "programme_ai_category_confirmed_by_candidate": programme_ai_confirmed,
        "module_word_or_page_rule_confirmed_by_candidate": module_length_rule_confirmed,
        "central_ucl_ai_disclosure_present": scientific_checks[
            "first_page_ai_disclosure_in_source"
        ],
        "no_credentials_in_submission_sources": not credential_hits,
    }
    return {
        "schema_version": "q1_scientific_manuscript_audit_v1",
        "status": scientific_status,
        "closure_mode": closure_mode,
        "final_release_eligible": scientific_status == "pass",
        "supervisor_feedback_final_closure": closure,
        "supervisor_feedback_paper_content_integration": content_integration,
        "scientific_checks": scientific_checks,
        "release_checks": release_checks,
        "release_status": (
            "pass" if all(release_checks.values()) else "human_metadata_pending"
        ),
        "bibliography_entry_count": len(bib_keys),
        "citation_count": len(citation_keys),
        "missing_citations": sorted(citation_keys - bib_keys),
        "uncited_entries": sorted(bib_keys - citation_keys),
        "headline_evidence_ids": sorted(evidence_comments),
        "marker_failures": marker_failures,
        "overclaim_hits": overclaim_hits,
        "credential_hits": credential_hits,
        "human_release_inputs_required": [
            "candidate number or verified name, as required by the ELEC0054 brief",
            "exact programme/degree title and any required supervisor field",
            "ELEC0054 GenAI assessment category or module-leader permission",
            "ELEC0054 word/page limit and required word-count presentation",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the frozen dissertation evidence, manuscript consistency, "
            "rubric readiness and release metadata without running CARLA."
        )
    )
    parser.add_argument(
        "--repo-root", type=Path, default=DEFAULT_REPO, help="Repository root."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Q1 output directory (default: distinction_v1/12_q1_final_audit).",
    )
    parser.add_argument(
        "--python", default=os.environ.get("PYTHON_BIN", "python3"), help="Python executable."
    )
    parser.add_argument(
        "--node", default="node", help="Node.js executable used for script --help checks."
    )
    parser.add_argument(
        "--expected-tests",
        type=int,
        help=(
            "Optional externally frozen analysis-test count. By default the gate "
            "binds the executed count to unittest discovery in the audited checkout."
        ),
    )
    parser.add_argument(
        "--clean-checkout",
        action="store_true",
        help="Run the detached clean-checkout regeneration, test and PDF gate.",
    )
    parser.add_argument(
        "--visual-review-complete",
        action="store_true",
        help="Confirm that every final PDF page and the key figures were visually inspected.",
    )
    parser.add_argument(
        "--programme-ai-confirmed",
        action="store_true",
        help="Confirm that the inserted AI disclosure complies with the ELEC0054 brief.",
    )
    parser.add_argument(
        "--module-length-rule-confirmed",
        action="store_true",
        help="Confirm that the current manuscript and word-count presentation comply with ELEC0054.",
    )
    parser.add_argument(
        "--closure-mode",
        choices=CLOSURE_MODES,
        default=CLOSURE_FINAL,
        help=(
            "Default final mode fails closed until SF1--SF4 are hash-verified. "
            "pre-sf4 records an explicitly partial audit and can never release Q1."
        ),
    )
    parser.add_argument("--supervisor-feedback-root", type=Path)
    parser.add_argument("--sf4-results-root", type=Path)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    output = (args.output or repo / Q1_RELATIVE).resolve()
    manuscript = manuscript_audit(
        repo,
        visual_review_complete=args.visual_review_complete,
        programme_ai_confirmed=args.programme_ai_confirmed,
        module_length_rule_confirmed=args.module_length_rule_confirmed,
        closure_mode=args.closure_mode,
        supervisor_feedback_root=args.supervisor_feedback_root,
        sf4_results_root=args.sf4_results_root,
    )

    clean: dict[str, Any] = {
        "schema_version": "q1_clean_checkout_v1",
        "status": "not_run",
    }
    if args.clean_checkout:
        clean = clean_checkout_audit(
            repo,
            python=args.python,
            node=args.node,
            expected_tests=args.expected_tests,
            closure_mode=args.closure_mode,
        )
    # Write receipts only after the detached worktree gate. Creating them
    # earlier would make the source repository dirty and defeat the purpose of
    # the clean-checkout precondition.
    atomic_json(output / "Q1_SCIENTIFIC_MANUSCRIPT_AUDIT.json", manuscript)
    atomic_json(output / "Q1_CLEAN_CHECKOUT_AUDIT.json", clean)

    scientific_pass = manuscript["status"] == "pass" and clean["status"] == "pass"
    partial_ready = (
        args.closure_mode == CLOSURE_PRE_SF4
        and manuscript["status"] == "partial_pre_sf4"
        and clean["status"] in {"not_run", "partial_pre_sf4"}
    )
    release_pass = manuscript["release_status"] == "pass"
    payload = {
        "schema_version": "q1_complete_v1",
        "stage": "Q1",
        "status": (
            "pass"
            if scientific_pass and release_pass
            else "scientific_pass_human_release_inputs_pending"
            if scientific_pass
            else "partial_pre_sf4"
            if partial_ready
            else "fail"
        ),
        "closure_mode": args.closure_mode,
        "supervisor_feedback_closure_status": manuscript[
            "supervisor_feedback_final_closure"
        ]["status"],
        "q1_scientific_gate_complete": scientific_pass,
        "q1_submission_release_gate_complete": scientific_pass and release_pass,
        "large_scale_carla_reopened": args.closure_mode == CLOSURE_PRE_SF4,
        "additional_large_scale_carla_required": manuscript[
            "supervisor_feedback_final_closure"
        ]["status"] != "pass",
        "scientific_audit_sha256": sha256(
            output / "Q1_SCIENTIFIC_MANUSCRIPT_AUDIT.json"
        ),
        "clean_checkout_audit_sha256": sha256(
            output / "Q1_CLEAN_CHECKOUT_AUDIT.json"
        ),
        "human_release_inputs_required": manuscript[
            "human_release_inputs_required"
        ],
        "next_gate": (
            "insert_verified_submission_metadata_then_rerun_q1"
            if scientific_pass and not release_pass
            else "V1_viva_and_submission_package"
            if scientific_pass
            else "complete_SF1_SF2_SF4_then_rerun_Q1_final"
            if partial_ready
            else "repair_q1_failures"
        ),
    }
    atomic_json(output / "Q1_COMPLETE.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not scientific_pass and not partial_ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
