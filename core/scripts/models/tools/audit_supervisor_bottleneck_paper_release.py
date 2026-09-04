#!/usr/bin/env python3
"""Fail-closed provenance and claim audit for the post-SF4 paper release."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def audit_release(root: Path, release: Path, output: Path | None = None) -> dict[str, Any]:
    manifest_path = release / "PAPER_RELEASE_COMPLETE.json"
    figure_manifest_path = release / "figures/FIGURE_MANIFEST.json"
    manifest = _json(manifest_path)
    figure_manifest = _json(figure_manifest_path)
    failures: list[str] = []
    for source in manifest["sources"]:
        path = root / source["path"]
        if not path.is_file() or _sha(path) != source["sha256"]:
            failures.append(f"stale_source:{source['path']}")
    for table in manifest["tables"]:
        path = release / table["path"]
        if not path.is_file() or _sha(path) != table["sha256"]:
            failures.append(f"stale_table:{table['path']}")
        elif len(_csv(path)) != table["rows"]:
            failures.append(f"row_count:{table['path']}")
    for figure in figure_manifest["figures"]:
        for item in figure["files"]:
            path = release / "figures" / item["path"]
            if not path.is_file() or _sha(path) != item["sha256"]:
                failures.append(f"stale_figure:{item['path']}")

    claims = _csv(release / "tables/table01_hypothesis_verdicts.csv")
    provenance = _csv(release / "tables/scalar_provenance_index.csv")
    sf4 = _csv(release / "tables/table08_sf4_authority_cells.csv")
    cia = _csv(release / "tables/table02_foundation_and_cia.csv")
    required_claims = {
        "F0_FOUNDATION", "H1_CAPACITY", "H2_INFORMATION", "H3_ARCHITECTURE",
        "H4A_SELECTED_MODEL_TRANSFER", "H4B_RISK_FRONTIER", "H4C_SUPERVISOR_AUTHORITY",
    }
    checks = {
        "manifest_status_pass": manifest.get("status") == "pass" and figure_manifest.get("status") == "pass",
        "no_stale_artifacts": not failures,
        "required_claims_present": {row["claim_id"] for row in claims} == required_claims,
        "all_claim_boundaries_present": all(row["boundary"] and row["prohibited_overclaim"] for row in claims),
        "all_scalars_located": bool(provenance) and all(row["canonical_source_locator"] for row in provenance),
        "figures_python_only": figure_manifest["checks"]["all_python_generated"],
        "figures_do_not_pool": figure_manifest["checks"]["no_cross_population_pooling"],
        "five_population_registry": len(manifest["population_registry"]) == 5,
        "all_populations_nonpooled": all(row["pooling"] == "forbidden_across_evidence_blocks" for row in manifest["population_registry"]),
        "sf4_40_on_0_off_completion": sum(int(row["completion_successes"]) for row in sf4 if row["supervisor_authority"] == "on") == 40 and sum(int(row["completion_successes"]) for row in sf4 if row["supervisor_authority"] == "off") == 0,
        "foundation_values_reconcile": any(row["comparison_member"] == "B0" and row["metric"] == "rollout_macro_NLL" and abs(float(row["estimate"]) - 2.1707117557525635) < 1e-12 for row in cia) and any(row["comparison_member"] == "B1" and row["metric"] == "rollout_macro_NLL" and abs(float(row["estimate"]) - 1.857094407081604) < 1e-12 for row in cia),
        "masking_overclaim_absent": all(("do not" in row["prohibited_overclaim"].lower() and "selective masking" in row["prohibited_overclaim"].lower()) or row["claim_id"] != "H4C_SUPERVISOR_AUTHORITY" for row in claims),
    }
    if not all(checks.values()):
        raise ValueError(f"Paper release audit failed: checks={checks}; failures={failures}")
    receipt = {
        "schema_version": "supervisor_bottleneck_paper_evidence_complete_v1",
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failures": failures,
        "release_manifest_sha256": _sha(manifest_path),
        "figure_manifest_sha256": _sha(figure_manifest_path),
        "tables": len(manifest["tables"]),
        "figures": len(figure_manifest["figures"]),
        "headline_boundary": "The release juxtaposes five populations without pooling and refuses selective-masking, universal-dominance and population-safety claims.",
    }
    destination = output or (release / "PAPER_EVIDENCE_COMPLETE.json")
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument(
        "--release",
        type=Path,
        default=Path("docs/paper/generated/supervisor_bottleneck_v1/paper_release"),
    )
    args = parser.parse_args()
    release = args.release if args.release.is_absolute() else args.root / args.release
    print(json.dumps(audit_release(args.root, release), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
