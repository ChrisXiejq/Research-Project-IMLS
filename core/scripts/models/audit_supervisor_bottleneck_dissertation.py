#!/usr/bin/env python3
"""Audit the dissertation against the frozen supervisor-bottleneck contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_SECTIONS = [
    "Introduction",
    "Literature Survey",
    "Problem Formulation",
    "Methodology",
    "Experimental Design",
    "Result Analysis",
    "Conclusion",
]

REQUIRED_FIGURES = [
    "figure01_cross_layer_system.pdf",
    "figure02_capacity_information_architecture.pdf",
    "figure03_predictor_risk_transfer.pdf",
    "figure04_supervisor_authority.pdf",
]

REQUIRED_EVIDENCE = [
    "2.170712",
    "1.857094",
    "0.000413",
    "0.004026",
    "0.003728",
    "-0.000298",
    "40/40",
    "0/40",
    "18,552",
    "17,822",
    "1,393",
]

PROHIBITED_CLAIMS = [
    "does not selectively erase",
    "rather than selectively masking adaptation",
    "proves that the supervisor masks",
    "proves that the supervisor does not mask",
]


def _citation_keys(tex: str) -> set[str]:
    return {
        key.strip()
        for group in re.findall(r"\\cite(?:t|p)?\{([^}]+)\}", tex)
        for key in group.split(",")
    }


def audit(thesis_root: Path) -> dict:
    tex_path = thesis_root / "main.tex"
    bib_path = thesis_root / "main.bib"
    log_path = thesis_root / "main.log"
    pdf_path = thesis_root / "main.pdf"
    tex = tex_path.read_text(encoding="utf-8")
    bib = bib_path.read_text(encoding="utf-8")
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    normalised_tex = re.sub(r"\s+", " ", tex)

    checks: dict[str, dict] = {}
    section_positions = [tex.find(rf"\section{{{name}}}") for name in REQUIRED_SECTIONS]
    checks["required_section_order"] = {
        "pass": all(pos >= 0 for pos in section_positions)
        and section_positions == sorted(section_positions),
        "positions": dict(zip(REQUIRED_SECTIONS, section_positions)),
    }

    bib_keys = set(re.findall(r"@[A-Za-z]+\{([^,]+),", bib))
    cite_keys = _citation_keys(tex)
    checks["bibliography"] = {
        "pass": len(bib_keys) >= 30 and cite_keys <= bib_keys and not (bib_keys - cite_keys),
        "entry_count": len(bib_keys),
        "cited_count": len(cite_keys),
        "missing_entries": sorted(cite_keys - bib_keys),
        "uncited_entries": sorted(bib_keys - cite_keys),
    }

    missing_figures = []
    for name in REQUIRED_FIGURES:
        path = thesis_root / "figures" / "supervisor_bottleneck_v1" / name
        if not path.is_file() or name not in tex:
            missing_figures.append(name)
    checks["python_generated_release_figures"] = {
        "pass": not missing_figures,
        "missing": missing_figures,
    }

    missing_evidence = [value for value in REQUIRED_EVIDENCE if value not in tex]
    checks["required_evidence_scalars"] = {
        "pass": not missing_evidence,
        "missing": missing_evidence,
    }

    prohibited = [
        claim for claim in PROHIBITED_CLAIMS if claim.lower() in normalised_tex.lower()
    ]
    checks["claim_boundaries"] = {"pass": not prohibited, "matches": prohibited}

    required_language = [
        "right-hand-traffic",
        "ego turns left",
        "opposing straight-through vehicle",
        "floor-saturated",
        "seven behaviour channels",
        "neither proves nor disproves selective masking",
    ]
    missing_language = [
        phrase for phrase in required_language if phrase.lower() not in normalised_tex.lower()
    ]
    checks["scenario_and_limitations"] = {
        "pass": not missing_language,
        "missing": missing_language,
    }

    unresolved = bool(
        re.search(r"undefined citations|undefined references|Citation .* undefined", log, re.I)
    )
    page_match = re.search(r"Output written on main\.xdv \((\d+) pages", log)
    page_count = int(page_match.group(1)) if page_match else None
    checks["compiled_pdf"] = {
        "pass": pdf_path.is_file() and pdf_path.stat().st_size > 0 and not unresolved,
        "page_count": page_count,
        "bytes": pdf_path.stat().st_size if pdf_path.exists() else 0,
        "unresolved_references": unresolved,
    }

    checks["controller_attribution"] = {
        "pass": all(
            phrase in normalised_tex
            for phrase in [
                "derived from the",
                "nair2025predictive",
                "without claiming a line-for-line reproduction",
                "not be presented as a certified safety filter",
            ]
        )
    }

    passed = all(item["pass"] for item in checks.values())
    return {
        "schema_version": "supervisor_bottleneck_dissertation_audit_v1",
        "pass": passed,
        "thesis_root": str(thesis_root.resolve()),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thesis-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.thesis_root)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
