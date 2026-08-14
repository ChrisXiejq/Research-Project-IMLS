#!/usr/bin/env python3
"""Audit and inventory the canonical thesis evidence package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    from .build_m1_evidence_package import (
        CLOSURE_FINAL,
        CLOSURE_MODES,
        CLOSURE_PRE_SF4,
        audit_supervisor_feedback_closure,
        audit_supervisor_feedback_content_integration,
    )
except ImportError:  # direct script execution
    from build_m1_evidence_package import (
        CLOSURE_FINAL,
        CLOSURE_MODES,
        CLOSURE_PRE_SF4,
        audit_supervisor_feedback_closure,
        audit_supervisor_feedback_content_integration,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Empty output table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(
    repo: Path,
    assets: Path,
    *,
    closure_mode: str = CLOSURE_FINAL,
    supervisor_feedback_root: Path | None = None,
    sf4_results_root: Path | None = None,
) -> dict[str, Any]:
    if closure_mode not in CLOSURE_MODES:
        raise ValueError(f"Unknown supervisor-feedback closure mode: {closure_mode}")
    table_gate = read_json(assets / "PAPER_TABLES_COMPLETE.json")
    results_manifest = read_json(assets / "paper_results_manifest.json")
    figures_dir = assets / "figures"
    figure_gate = read_json(figures_dir / "PAPER_FIGURES_COMPLETE.json")
    png_gate = read_json(figures_dir / "PAPER_FIGURES_PNG_COMPLETE.json")
    figure_manifest = read_json(figures_dir / "paper_figures_manifest.json")
    expected_status = (
        "partial_pre_sf4" if closure_mode == CLOSURE_PRE_SF4 else "pass"
    )
    for name, payload in (
        ("tables", table_gate),
        ("results manifest", results_manifest),
        ("figures", figure_gate),
        ("PNG figures", png_gate),
        ("figure manifest", figure_manifest),
    ):
        if (
            payload.get("status") != expected_status
            or payload.get("closure_mode") != closure_mode
        ):
            raise ValueError(f"{name} gate is not stage-appropriate")
    closure = audit_supervisor_feedback_closure(
        repo,
        supervisor_feedback_root=supervisor_feedback_root,
        sf4_results_root=sf4_results_root,
    )
    if closure_mode == CLOSURE_FINAL and closure.get("status") != "pass":
        raise ValueError("Supervisor-feedback final closure gate has not passed")
    content_integration = audit_supervisor_feedback_content_integration(
        repo,
        closure_mode=closure_mode,
        closure_payload=closure,
    )
    if closure_mode == CLOSURE_FINAL and content_integration.get("status") != "pass":
        raise ValueError("Supervisor-feedback results are not integrated into the paper")
    if table_gate["manifest_sha256"] != sha256(assets / "paper_results_manifest.json"):
        raise ValueError("Result manifest hash mismatch")
    if figure_gate["source_results_manifest_sha256"] != sha256(assets / "paper_results_manifest.json"):
        raise ValueError("Figure/result manifest linkage mismatch")
    if figure_gate["figures_manifest_sha256"] != sha256(figures_dir / "paper_figures_manifest.json"):
        raise ValueError("Figure manifest hash mismatch")
    if png_gate.get("schema_version") != "paper_figures_png_complete_v2":
        raise ValueError("PNG completion gate predates source-linked hash auditing")
    if png_gate.get("source_figures_manifest_sha256") != sha256(figures_dir / "paper_figures_manifest.json"):
        raise ValueError("PNG/figure manifest linkage mismatch")
    if png_gate.get("source_figures_complete_sha256") != sha256(figures_dir / "PAPER_FIGURES_COMPLETE.json"):
        raise ValueError("PNG/SVG completion linkage mismatch")
    renderer = repo / "core/scripts/models/render_paper_figures_png.cjs"
    if png_gate.get("renderer_source_sha256") != sha256(renderer):
        raise ValueError("PNG renderer source hash mismatch")

    expected_svgs = sorted(figure_manifest["figures"])
    expected_pngs = [name.removesuffix(".svg") + ".png" for name in expected_svgs]
    if png_gate.get("figure_count") != len(expected_pngs):
        raise ValueError("PNG figure count does not match the canonical figure manifest")
    if sorted(png_gate.get("files", {})) != expected_pngs:
        raise ValueError("PNG completion gate does not cover exactly the canonical figures")
    for png_name, svg_name in zip(expected_pngs, expected_svgs):
        record = png_gate["files"][png_name]
        png_path = figures_dir / png_name
        svg_path = figures_dir / svg_name
        if not isinstance(record, dict):
            raise ValueError(f"PNG record lacks hash metadata: {png_name}")
        if record.get("source_svg") != svg_name:
            raise ValueError(f"PNG/SVG filename linkage mismatch: {png_name}")
        if record.get("source_svg_sha256") != sha256(svg_path):
            raise ValueError(f"PNG source SVG hash mismatch: {png_name}")
        if not png_path.is_file() or record.get("bytes") != png_path.stat().st_size:
            raise ValueError(f"PNG file size mismatch: {png_name}")
        if record.get("sha256") != sha256(png_path):
            raise ValueError(f"PNG file hash mismatch: {png_name}")

    source_failures = []
    for result_id, record in results_manifest["results"].items():
        source = repo / record["source_file"]
        if not source.is_file() or sha256(source) != record["source_sha256"]:
            source_failures.append(result_id)
    if source_failures:
        raise ValueError(f"Result source integrity failures: {source_failures[:5]}")

    inventory = []
    logical_assets_root = Path("docs/paper/generated/paper_assets_v1")
    categories = {
        "package_readme": [assets / "README.md"],
        "manifest": [assets / "paper_results_manifest.json", assets / "PAPER_TABLES_COMPLETE.json"],
        "table": [assets / name for name in results_manifest["table_files"]],
        "table_preview": [assets / "paper_tables.md"],
        "figure_manifest": [figures_dir / "paper_figures_manifest.json", figures_dir / "PAPER_FIGURES_COMPLETE.json", figures_dir / "PAPER_FIGURES_PNG_COMPLETE.json"],
        "caption": [figures_dir / "figure_captions.md"],
        "figure_svg": sorted(figures_dir.glob("figure*.svg")),
        "figure_png": sorted(figures_dir.glob("figure*.png")),
    }
    for category, paths in categories.items():
        for path in paths:
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"Missing or empty asset: {path}")
            inventory.append(
                {
                    "category": category,
                    "file": str(logical_assets_root / path.relative_to(assets)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    write_csv(assets / "paper_asset_inventory.csv", inventory)

    figure_by_evidence: dict[str, list[str]] = {}
    for filename, record in figure_manifest["figures"].items():
        path = figures_dir / filename
        if sha256(path) != record["sha256"]:
            raise ValueError(f"Figure hash mismatch: {filename}")
        for result_id in record["evidence_ids"]:
            if result_id not in results_manifest["results"]:
                raise ValueError(f"Unknown figure evidence ID: {result_id}")
            figure_by_evidence.setdefault(result_id, []).append(filename)

    with (assets / "table07_hypothesis_evidence_verdicts.csv").open(newline="", encoding="utf-8") as handle:
        hypotheses = list(csv.DictReader(handle))
    claim_rows = []
    for row in hypotheses:
        ids = row["evidence_ids"].split("; ")
        missing = [result_id for result_id in ids if result_id not in results_manifest["results"]]
        if missing:
            raise ValueError(f"{row['hypothesis_id']} has unresolved evidence IDs: {missing}")
        figures = sorted({name for result_id in ids for name in figure_by_evidence.get(result_id, [])})
        claim_rows.append(
            {
                "hypothesis_id": row["hypothesis_id"],
                "verdict": row["verdict"],
                "evidence_ids": row["evidence_ids"],
                "canonical_table": "table07_hypothesis_evidence_verdicts.csv",
                "supporting_figures": "; ".join(figures),
                "boundary": row["boundary"],
            }
        )
    write_csv(assets / "paper_claim_evidence_matrix.csv", claim_rows)

    key_ids = sorted({result_id for row in hypotheses for result_id in row["evidence_ids"].split("; ")})
    key_rows = []
    for result_id in key_ids:
        record = results_manifest["results"][result_id]
        key_rows.append(
            {
                "result_id": result_id,
                "value": record["value"],
                "unit": record["unit"],
                "metric": record["metric"],
                "aggregation_unit": record["aggregation_unit"],
                "evidence_role": record["evidence_role"],
                "source_file": record["source_file"],
                "source_locator": record["source_locator"],
            }
        )
    write_csv(assets / "paper_key_results.csv", key_rows)

    payload = {
        "schema_version": "paper_evidence_package_complete_v1",
        "status": expected_status,
        "closure_mode": closure_mode,
        "supervisor_feedback_closure_status": closure["status"],
        "supervisor_feedback_closure_checks": closure["checks"],
        "supervisor_feedback_paper_content_integration": content_integration,
        "final_release_eligible": (
            closure_mode == CLOSURE_FINAL and closure["status"] == "pass"
        ),
        "result_count": results_manifest["result_count"],
        "table_count": results_manifest["table_count"],
        "figure_count": figure_manifest["figure_count"],
        "png_figure_count": png_gate["figure_count"],
        "hypothesis_count": len(hypotheses),
        "key_result_count": len(key_rows),
        "inventory_count": len(inventory),
        "source_integrity_failures": 0,
        "unresolved_evidence_ids": 0,
        "results_manifest_sha256": sha256(assets / "paper_results_manifest.json"),
        "figures_manifest_sha256": sha256(figures_dir / "paper_figures_manifest.json"),
        "png_completion_sha256": sha256(figures_dir / "PAPER_FIGURES_PNG_COMPLETE.json"),
        "inventory_sha256": sha256(assets / "paper_asset_inventory.csv"),
        "claim_matrix_sha256": sha256(assets / "paper_claim_evidence_matrix.csv"),
        "key_results_sha256": sha256(assets / "paper_key_results.csv"),
    }
    atomic_json(assets / "PAPER_EVIDENCE_PACKAGE_COMPLETE.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--closure-mode", choices=CLOSURE_MODES, default=CLOSURE_FINAL)
    parser.add_argument("--supervisor-feedback-root", type=Path)
    parser.add_argument("--sf4-results-root", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    assets = (args.assets_dir or repo / "docs/paper/generated/paper_assets_v1").resolve()
    print(
        json.dumps(
            build(
                repo,
                assets,
                closure_mode=args.closure_mode,
                supervisor_feedback_root=args.supervisor_feedback_root,
                sf4_results_root=args.sf4_results_root,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
