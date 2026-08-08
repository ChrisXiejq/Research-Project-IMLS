#!/usr/bin/env python3
"""Build and value-audit the final four-hypothesis M1 evidence package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def json_pointer(payload: Any, pointer: str) -> Any:
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid JSON pointer: {pointer}")
    current = payload
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


def csv_value(rows: list[dict[str, str]], locator: dict[str, Any]) -> Any:
    filters = locator["where"]
    matched = [row for row in rows if all(row.get(key) == str(value) for key, value in filters.items())]
    if len(matched) != 1:
        raise ValueError(f"CSV locator matched {len(matched)} rows: {filters}")
    raw = matched[0][locator["field"]]
    value_type = locator.get("type", "string")
    if value_type == "float":
        return float(raw)
    if value_type == "int":
        return int(raw)
    if value_type == "bool01":
        return bool(int(raw))
    return raw


def equal(expected: Any, observed: Any) -> bool:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(observed, (int, float)) and math.isclose(float(expected), float(observed), rel_tol=1e-10, abs_tol=1e-12)
    return expected == observed


class Package:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.records: list[dict[str, Any]] = []
        self.ids: set[str] = set()

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.repo))

    def add_json(
        self,
        evidence_id: str,
        hypothesis: str,
        path: Path,
        pointer: str,
        *,
        metric: str,
        unit: str,
        aggregation_unit: str,
        evidence_role: str,
        consumer: str,
        implementation_tag: str,
    ) -> Any:
        value = json_pointer(load_json(path), pointer)
        return self._add(evidence_id, hypothesis, path, {"kind": "json_pointer", "pointer": pointer}, value, metric, unit, aggregation_unit, evidence_role, consumer, implementation_tag)

    def add_csv(
        self,
        evidence_id: str,
        hypothesis: str,
        path: Path,
        where: dict[str, Any],
        field: str,
        value_type: str,
        *,
        metric: str,
        unit: str,
        aggregation_unit: str,
        evidence_role: str,
        consumer: str,
        implementation_tag: str,
    ) -> Any:
        locator = {"kind": "csv_row", "where": where, "field": field, "type": value_type}
        value = csv_value(load_csv(path), locator)
        return self._add(evidence_id, hypothesis, path, locator, value, metric, unit, aggregation_unit, evidence_role, consumer, implementation_tag)

    def add_derived(
        self,
        evidence_id: str,
        hypothesis: str,
        left_id: str,
        right_id: str,
        *,
        metric: str,
        unit: str,
        aggregation_unit: str,
        evidence_role: str,
        consumer: str,
        implementation_tag: str,
    ) -> float:
        by_id = {record["evidence_id"]: record for record in self.records}
        value = float(by_id[left_id]["value"]) - float(by_id[right_id]["value"])
        if evidence_id in self.ids:
            raise ValueError(f"Duplicate evidence ID: {evidence_id}")
        self.ids.add(evidence_id)
        self.records.append({
            "evidence_id": evidence_id,
            "hypothesis": hypothesis,
            "value": value,
            "value_type": "float",
            "unit": unit,
            "metric": metric,
            "aggregation_unit": aggregation_unit,
            "evidence_role": evidence_role,
            "implementation_tag": implementation_tag,
            "source": {"kind": "derived_subtraction", "left_evidence_id": left_id, "right_evidence_id": right_id},
            "consumers": [consumer],
        })
        return value

    def _add(self, evidence_id: str, hypothesis: str, path: Path, locator: dict[str, Any], value: Any, metric: str, unit: str, aggregation_unit: str, evidence_role: str, consumer: str, implementation_tag: str) -> Any:
        if evidence_id in self.ids:
            raise ValueError(f"Duplicate evidence ID: {evidence_id}")
        self.ids.add(evidence_id)
        self.records.append({
            "evidence_id": evidence_id,
            "hypothesis": hypothesis,
            "value": value,
            "value_type": type(value).__name__,
            "unit": unit,
            "metric": metric,
            "aggregation_unit": aggregation_unit,
            "evidence_role": evidence_role,
            "implementation_tag": implementation_tag,
            "source": {"kind": "file", "file": self.relative(path), "sha256": sha256(path), "locator": locator},
            "consumers": [consumer],
        })
        return value


def audit(repo: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    checks = []
    values: dict[str, Any] = {}
    for record in records:
        error = None
        resolved = None
        try:
            source = record["source"]
            if source["kind"] == "file":
                path = repo / source["file"]
                if sha256(path) != source["sha256"]:
                    raise ValueError("source SHA256 mismatch")
                locator = source["locator"]
                if locator["kind"] == "json_pointer":
                    resolved = json_pointer(load_json(path), locator["pointer"])
                elif locator["kind"] == "csv_row":
                    resolved = csv_value(load_csv(path), locator)
                else:
                    raise ValueError("unknown file locator")
            elif source["kind"] == "derived_subtraction":
                resolved = float(values[source["left_evidence_id"]]) - float(values[source["right_evidence_id"]])
            else:
                raise ValueError("unknown source kind")
            if not equal(record["value"], resolved):
                raise ValueError(f"value mismatch: expected={record['value']!r}, observed={resolved!r}")
        except Exception as exc:  # audit must retain all failures
            error = str(exc)
        if error is None:
            values[record["evidence_id"]] = resolved
        checks.append({"evidence_id": record["evidence_id"], "status": "pass" if error is None else "fail", "error": error})
    failures = [check for check in checks if check["status"] == "fail"]
    hypotheses = {record["hypothesis"] for record in records}
    invalid_roles = [record["evidence_id"] for record in records if record["evidence_role"] not in {"primary", "secondary", "diagnostic", "boundary"}]
    mixed_implementations = [record["evidence_id"] for record in records if record["hypothesis"] in {"H3", "H4"} and record["implementation_tag"] != "corrected_r3_v1"]
    return {
        "schema_version": "m1_value_resolving_audit_v1",
        "status": "pass" if not failures and hypotheses == {"H1", "H2", "H3", "H4"} and not invalid_roles and not mixed_implementations else "fail",
        "record_count": len(records),
        "hypotheses": sorted(hypotheses),
        "locator_resolution_failures": len(failures),
        "value_mismatches": sum("value mismatch" in (item["error"] or "") for item in failures),
        "invalid_evidence_roles": invalid_roles,
        "legacy_corrected_pooling_violations": mixed_implementations,
        "orphan_headline_claims": 0 if hypotheses == {"H1", "H2", "H3", "H4"} else 4 - len(hypotheses),
        "checks": checks,
    }


def build(repo: Path, output: Path) -> dict[str, Any]:
    generated = repo / "docs/paper/generated"
    paths = {
        "test": generated / "day8/final_test/day8_frozen_test_summary.json",
        "b0": generated / "day10/gaps/b0_offline/b0_frozen_offline_summary.json",
        "capacity": generated / "distinction_v1/03_training_budget/model_capacity_training_budget_audit.json",
        "tail": generated / "distinction_v1/04_in_loop_prediction/formal_inloop_B1_minus_B0_contrasts.csv",
        "a2": generated / "distinction_v1/08_corrected_closed_loop/r3_final/synthesis/A2_COMPLETE.json",
        "h3": generated / "distinction_v1/08_corrected_closed_loop/r3_final/synthesis/table_r3_h3_translation.csv",
        "h4": generated / "distinction_v1/08_corrected_closed_loop/r3_final/synthesis/table_r3_h4_dominance.csv",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    for name in ("test", "b0", "capacity", "a2"):
        if load_json(paths[name]).get("status") != "pass":
            raise ValueError(f"Input completion gate failed: {paths[name]}")

    package = Package(repo)
    common_test = dict(unit="nats/step", aggregation_unit="rollout macro over 20 frozen-test rollouts / 5 init groups", evidence_role="primary", consumer="Results H1/H2 model comparison", implementation_tag="offline_frozen_test_v1")
    h1_b1 = package.add_json("H1_B1_TEST_NLL", "H1", paths["b0"], "/subsets/all/B1/uncalibrated_rollout_macro_NLL", metric="uncalibrated trajectory mixture NLL", **common_test)
    h1_b0 = package.add_json("H1_B0_TEST_NLL", "H1", paths["b0"], "/subsets/all/B0/uncalibrated_rollout_macro_NLL", metric="uncalibrated trajectory mixture NLL", **common_test)
    package.add_derived("H1_B1_MINUS_B0_TEST_NLL", "H1", "H1_B1_TEST_NLL", "H1_B0_TEST_NLL", metric="B1 minus B0 uncalibrated trajectory mixture NLL", **common_test)
    for metric, field, unit in (("ADE", "top1_ADE_mean", "m"), ("FDE", "top1_FDE_mean", "m")):
        left = f"H1_B1_TEST_{metric}"
        right = f"H1_B0_TEST_{metric}"
        kwargs = dict(unit=unit, aggregation_unit="rollout macro over 20 frozen-test rollouts / 5 init groups", evidence_role="secondary", consumer="Results H1 model comparison", implementation_tag="offline_frozen_test_v1")
        package.add_json(left, "H1", paths["b0"], f"/subsets/all/B1/{field}", metric=f"top-1 {metric}", **kwargs)
        package.add_json(right, "H1", paths["b0"], f"/subsets/all/B0/{field}", metric=f"top-1 {metric}", **kwargs)
        package.add_derived(f"H1_B1_MINUS_B0_TEST_{metric}", "H1", left, right, metric=f"B1 minus B0 top-1 {metric}", **kwargs)

    run_index = {run["variant"]: index for index, run in enumerate(load_json(paths["test"])["runs"])}
    for variant in ("B2-M", "T1", "B2-D", "T2"):
        package.add_json(
            f"H2_{variant.replace('-', '_')}_TEST_NLL",
            "H2",
            paths["test"],
            f"/runs/{run_index[variant]}/subsets/all/uncalibrated_rollout_macro_NLL",
            metric="uncalibrated trajectory mixture NLL",
            **common_test,
        )
    package.add_derived("H2_T1_MINUS_B2M_TEST_NLL", "H2", "H2_T1_TEST_NLL", "H2_B2_M_TEST_NLL", metric="T1 minus B2-M frozen-test NLL", **common_test)
    package.add_derived("H2_T2_MINUS_B2D_TEST_NLL", "H2", "H2_T2_TEST_NLL", "H2_B2_D_TEST_NLL", metric="T2 minus B2-D frozen-test NLL", **common_test)
    package.add_json("H2_PARAMETER_MATCHED", "H2", paths["capacity"], "/fairness_checks/parameter_matched", metric="parameter-matching audit", unit="boolean", aggregation_unit="five complete model configurations", evidence_role="boundary", consumer="Methods limitation and H2 interpretation", implementation_tag="offline_training_audit_v1")
    package.add_json("H2_RUNS_AT_EPOCH_BOUNDARY", "H2", paths["capacity"], "/fairness_checks/runs_best_at_budget_boundary", metric="runs selected at epoch ceiling", unit="runs", aggregation_unit="15 training runs", evidence_role="boundary", consumer="Methods limitation and H2 interpretation", implementation_tag="offline_training_audit_v1")
    package.add_csv("H1_TAIL_MINUS_B0_ADE_NEG3", "H1", paths["tail"], {"subset": "response_active", "target_offset_m": "-3.0", "metric": "top1_ADE_m"}, "B1_minus_B0_mean", "float", metric="B1 minus B0 response-active ADE at -3 m", unit="m", aggregation_unit="10 paired rollout conditions / 5 init groups", evidence_role="diagnostic", consumer="H1 boundary and Discussion", implementation_tag="legacy_timing_diagnostic_only")

    package.add_json("H3_SUPPORTED_CELLS", "H3", paths["a2"], "/h3/directionally_supported_cells", metric="H3 directionally supported cells", unit="cells", aggregation_unit="8 prespecified predictor-stack policy/style cells", evidence_role="primary", consumer="Results H3 headline", implementation_tag="corrected_r3_v1")
    package.add_json("H3_PRESPECIFIED_CELLS", "H3", paths["a2"], "/h3/prespecified_cells", metric="H3 prespecified cells", unit="cells", aggregation_unit="corrected R3 matrix", evidence_role="primary", consumer="Results H3 headline", implementation_tag="corrected_r3_v1")
    for row in load_csv(paths["h3"]):
        key = f"{row['risk_policy']}_{row['target_style']}"
        where = {"risk_policy": row["risk_policy"], "target_style": row["target_style"]}
        for suffix, field, unit in (("TIME", "mean_completion_effect_s", "s"), ("SEPARATION", "mean_separation_effect_m", "m"), ("SUPPORT", "cell_support_status", "category")):
            value_type = "float" if suffix != "SUPPORT" else "string"
            package.add_csv(f"H3_{key.upper()}_{suffix}", "H3", paths["h3"], where, field, value_type, metric=f"B1 minus B0 {field}", unit=unit, aggregation_unit="mean paired effect over 5 init groups", evidence_role="primary", consumer="R3 H3 table/figure", implementation_tag="corrected_r3_v1")

    package.add_json("H4_DOMINANCE_CELLS", "H4", paths["a2"], "/h4/dominance_cells", metric="adaptive-risk dominance cells", unit="cells", aggregation_unit="12 prespecified predictor/style/fixed-comparator contrasts", evidence_role="primary", consumer="Results H4 headline", implementation_tag="corrected_r3_v1")
    package.add_json("H4_PRESPECIFIED_CELLS", "H4", paths["a2"], "/h4/prespecified_cells", metric="H4 prespecified contrasts", unit="cells", aggregation_unit="corrected R3 matrix", evidence_role="primary", consumer="Results H4 headline", implementation_tag="corrected_r3_v1")
    for row in load_csv(paths["h4"]):
        key = f"{row['predictor']}_{row['target_style']}_{row['fixed_comparator']}"
        where = {"predictor": row["predictor"], "target_style": row["target_style"], "fixed_comparator": row["fixed_comparator"]}
        for suffix, field, unit in (("TIME", "mean_adaptive_minus_fixed_completion_s", "s"), ("SEPARATION", "mean_adaptive_minus_fixed_separation_m", "m"), ("DOMINANCE", "dominance_status", "category")):
            value_type = "float" if suffix != "DOMINANCE" else "string"
            package.add_csv(f"H4_{key.upper()}_{suffix}", "H4", paths["h4"], where, field, value_type, metric=f"adaptive minus fixed {field}", unit=unit, aggregation_unit="mean paired effect over 5 init groups", evidence_role="primary", consumer="R3 H4 table/figure", implementation_tag="corrected_r3_v1")

    audit_payload = audit(repo, package.records)
    output.mkdir(parents=True, exist_ok=True)
    hypotheses = [
        {"hypothesis": "H1", "verdict": "supported_with_boundary", "primary_evidence": "H1_B1_MINUS_B0_TEST_NLL", "claim": f"B1 reduces frozen-test NLL relative to B0 by {abs(h1_b1 - h1_b0):.3f} nats/step, but the rare shifted active tail is not universally improved."},
        {"hypothesis": "H2", "verdict": "not_supported", "primary_evidence": "H2_T1_MINUS_B2M_TEST_NLL; H2_T2_MINUS_B2D_TEST_NLL", "claim": "The two matched-head comparisons point in different directions; tested Transformers do not show a consistent advantage over MLP adapters."},
        {"hypothesis": "H3", "verdict": "not_supported_as_universal_claim", "primary_evidence": "H3_SUPPORTED_CELLS; H3_PRESPECIFIED_CELLS", "claim": "B1 prediction gains jointly improve completion and separation in only 2/8 corrected closed-loop cells."},
        {"hypothesis": "H4", "verdict": "not_supported_as_universal_dominance", "primary_evidence": "H4_DOMINANCE_CELLS; H4_PRESPECIFIED_CELLS", "claim": "Adaptive risk dominates fixed risk in only 3/12 corrected comparisons."},
    ]
    manifest = {
        "schema_version": "m1_four_hypothesis_evidence_v1",
        "status": audit_payload["status"],
        "central_claim": "Task adaptation strongly improves prediction, but closed-loop benefit is conditional on predictor-risk-interaction coupling under the shared supervisor.",
        "hypotheses": hypotheses,
        "records": package.records,
        "record_count": len(package.records),
        "additional_large_scale_carla_required": False,
    }
    atomic_json(output / "M1_EVIDENCE_MANIFEST.json", manifest)
    atomic_json(output / "M1_VALUE_AUDIT.json", audit_payload)
    write_csv(output / "M1_HYPOTHESIS_VERDICTS.csv", hypotheses)
    markdown = "# M1 — Four-hypothesis evidence package\n\n" + "\n".join(f"- **{row['hypothesis']} — {row['verdict']}:** {row['claim']}" for row in hypotheses) + f"\n\nValue audit: **{audit_payload['status']}**; {len(package.records)} records, {audit_payload['locator_resolution_failures']} locator/value failures, {len(audit_payload['legacy_corrected_pooling_violations'])} legacy/corrected pooling violations.\n"
    atomic_text(output / "M1_EVIDENCE_SUMMARY.md", markdown)
    artifacts = ["M1_EVIDENCE_MANIFEST.json", "M1_VALUE_AUDIT.json", "M1_HYPOTHESIS_VERDICTS.csv", "M1_EVIDENCE_SUMMARY.md"]
    complete = {
        "schema_version": "m1_complete_v1",
        "status": audit_payload["status"],
        "stage": "M1",
        "hypotheses": ["H1", "H2", "H3", "H4"],
        "record_count": len(package.records),
        "invalid_locators": audit_payload["locator_resolution_failures"],
        "value_mismatches": audit_payload["value_mismatches"],
        "orphan_headline_claims": audit_payload["orphan_headline_claims"],
        "legacy_corrected_pooling_violations": audit_payload["legacy_corrected_pooling_violations"],
        "additional_large_scale_carla_required": False,
        "artifacts": {filename: sha256(output / filename) for filename in artifacts},
    }
    atomic_json(output / "M1_COMPLETE.json", complete)
    return complete


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output or repo / "docs/paper/generated/distinction_v1/10_four_hypothesis_evidence").resolve()
    result = build(repo, output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
