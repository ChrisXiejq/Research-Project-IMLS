#!/usr/bin/env python3
"""S1 static/runtime gates for known dissertation evidence hazards."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import ast
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from distinction_analysis_utils import atomic_write_json, resolve_json_pointer, sha256_file


FORMAL_PROFILES = (
    "adaptive_interaction_severity",
    "fixed_frontier_aggressive",
    "fixed_frontier_medium",
    "fixed_frontier_conservative",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def isolated_mode_function(source: str):
    tree = ast.parse(source)
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in {"_joint_mode_component", "_mode_component"}
    ]
    namespace: dict[str, Any] = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<mode-functions>", "exec"), namespace)
    return namespace["_mode_component"]


def audit_locators(repo: Path) -> dict:
    manifest_path = repo / "docs/paper/generated/paper_assets_v1/paper_results_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = payload.get("results", {})
    checked = []
    invalid = []
    skipped = []
    for evidence_id, record in results.items():
        locator = record.get("source_locator")
        source = repo / str(record.get("source_file", ""))
        if not isinstance(locator, str) or not locator.startswith("/") or source.suffix.lower() != ".json":
            skipped.append(evidence_id)
            continue
        item = {"evidence_id": evidence_id, "source_file": str(source.relative_to(repo)), "locator": locator}
        checked.append(item)
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
            resolve_json_pointer(document, locator)
        except Exception as error:
            invalid.append({**item, "error": f"{type(error).__name__}: {error}"})
    return {
        "manifest": str(manifest_path.relative_to(repo)),
        "total_results": len(results),
        "json_pointer_checked": len(checked),
        "valid": len(checked) - len(invalid),
        "invalid": len(invalid),
        "skipped_non_json_or_filter_locator": len(skipped),
        "invalid_records": invalid,
    }


def main() -> None:
    args = parse_args()
    repo = args.repo.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    mpc_path = repo / "core/scripts/carla/utils/mpc_utils.py"
    smpc_path = repo / "core/scripts/carla/policies/smpc_agent.py"
    metrics_path = repo / "core/scripts/evaluation/closed_loop_metrics.py"
    day9_path = repo / "core/scripts/carla/experimental/run_day9_deployment_smoke.sh"

    mpc_source = mpc_path.read_text(encoding="utf-8")
    mode = isolated_mode_function(mpc_source)
    formal_mapping = {
        profile: [mode(index, 0, 3, 1, profile) for index in range(3)] for profile in FORMAL_PROFILES
    }
    mode_collapse = all(values == [0, 0, 0] for values in formal_mapping.values())

    smpc_source = smpc_path.read_text(encoding="utf-8")
    floor_match = re.search(
        r"if self\.fixed_risk and not self\.obca_flag:\s+self\._ref_gen_a_min\s*=\s*(-?[0-9.]+)"
        r"\s+else:\s+self\._ref_gen_a_min\s*=\s*(-?[0-9.]+)",
        smpc_source,
    )
    fixed_floor, adaptive_floor = (float(floor_match.group(1)), float(floor_match.group(2))) if floor_match else (None, None)

    day9_source = day9_path.read_text(encoding="utf-8")
    day9_predictors = sorted(set(re.findall(r"for predictor in ([A-Za-z0-9 -]+); do", day9_source)[0].split()))

    metrics_source = metrics_path.read_text(encoding="utf-8")
    chained_inequality_present = bool(
        re.search(r"shape\[0\]\s*!=\s*\\?\s*\n.*shape\[0\]\s*!=", metrics_source)
    )
    explicit_length_set_guard = "len(set(lengths.values())) != 1" in metrics_source
    locator_audit = audit_locators(repo)

    gates = {
        "C1_mode_mapping": {
            "status": "known_defect_detected" if mode_collapse else "remediated",
            "formal_mapping": formal_mapping,
            "scientific_effect": "all three GMM hypotheses select component zero for every formal one-TV profile",
        },
        "C2_reference_floor": {
            "status": "known_defect_detected" if fixed_floor != adaptive_floor else "remediated",
            "fixed_risk_a_min": fixed_floor,
            "adaptive_risk_a_min": adaptive_floor,
        },
        "C3_day9_scope": {
            "status": "scope_confirmed",
            "predictors": day9_predictors,
            "excluded_from_formal_closed_loop": ["B2-D", "T1", "T2"],
        },
        "length_validation": {
            "status": "pass" if explicit_length_set_guard and not chained_inequality_present else "fail",
            "explicit_all_equal_guard": explicit_length_set_guard,
            "old_chained_inequality_present": chained_inequality_present,
        },
        "C7_evidence_locators": {
            "status": "pass" if locator_audit["invalid"] == 0 else "known_defect_detected",
            **locator_audit,
        },
    }
    blocking_failures = [name for name, gate in gates.items() if gate["status"] == "fail"]
    payload = {
        "schema_version": "distinction_regression_gates_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass" if not blocking_failures else "fail",
        "interpretation": (
            "Pass means the audit itself ran and mandatory code regressions pass. "
            "known_defect_detected is an acknowledged scientific hazard that remains open for E/G-stage handling."
        ),
        "blocking_failures": blocking_failures,
        "source_sha256": {
            str(path.relative_to(repo)): sha256_file(path)
            for path in (mpc_path, smpc_path, metrics_path, day9_path)
        },
        "gates": gates,
    }
    atomic_write_json(output / "S1_regression_gate_audit.json", payload)
    atomic_write_json(
        output / "S1_COMPLETE.json",
        {
            "stage": "S1",
            "status": payload["status"],
            "blocking_failures": blocking_failures,
            "known_scientific_defects": [
                name for name, gate in gates.items() if gate["status"] == "known_defect_detected"
            ],
            "artifact": "S1_regression_gate_audit.json",
        },
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
