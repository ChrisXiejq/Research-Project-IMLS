#!/usr/bin/env python3
"""Freeze and verify a provenance-preserving SF4 infrastructure recovery.

This tool may extend the attempt cap for exactly one exhausted rollout only
when every prior attempt is a retryable CARLA infrastructure failure and no
usable or partial scientific payload was observed.  A failed scenario summary
is retained as infrastructure provenance, but is not confused with a valid
rollout.  The original run contract, treatment sources, accepted receipts and
statistical design remain immutable.
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
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from r3_attempt_manager import (
    scenario_summaries,
    scenario_validation_failures,
    valid_receipt,
    valid_scenario,
)


SCHEMA = "sf4_infrastructure_exhaustion_recovery_amendment_v2"
COMPLETE_SCHEMA = "sf4_supervisor_behavioural_authority_complete_v1"

# These are measurements from a rollout rather than setup/configuration
# metadata.  Their non-empty presence would make an interrupted attempt
# scientifically ambiguous, so recovery must stop instead of silently
# discarding them.
SCIENTIFIC_PAYLOAD_BASENAMES = {
    "scenario_result.pkl",
    "scenario_steps.csv",
    "smpc_debug_steps.jsonl",
    "prediction_dataset_raw.jsonl",
    "prediction_dataset_labeled.jsonl",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def atomic_json(path: Path, value: Mapping[str, Any], *, frozen: bool = False) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if frozen and path.is_file():
        previous = read_json(path)
        for payload in (previous, value):
            payload.pop("created_at_utc", None)
        if previous != value:
            raise ValueError(f"Frozen recovery amendment drift: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, path)


def contract_keys(contract: Mapping[str, Any]) -> set[tuple[str, int]]:
    order = contract.get("execution_order")
    if not isinstance(order, list) or len(order) != 80:
        raise ValueError("SF4 contract does not contain 80 execution keys")
    keys = {
        (str(item.get("cell_id")), int(item.get("ego_init_id", -1)))
        for item in order
        if isinstance(item, Mapping)
    }
    if len(keys) != 80:
        raise ValueError("SF4 execution keys are not unique")
    return keys


def validate_frozen_sources(repo: Path, contract: Mapping[str, Any]) -> dict[str, str]:
    expected = ((contract.get("hashes") or {}).get("execution_sources") or {})
    if not isinstance(expected, dict) or not expected:
        raise ValueError("SF4 contract execution-source hashes are missing")
    observed = {}
    for relative, expected_hash in sorted(expected.items()):
        path = repo / str(relative)
        if not path.is_file():
            raise ValueError(f"Frozen execution source missing: {path}")
        observed_hash = sha256(path)
        if observed_hash != expected_hash:
            raise ValueError(f"Frozen execution source drift: {relative}")
        observed[str(relative)] = observed_hash
    return observed


def validate_markers(
    root: Path, contract_path: Path, preflight_path: Path, smoke_path: Path
) -> None:
    contract_hash = sha256(contract_path)
    preflight = read_json(preflight_path)
    smoke = read_json(smoke_path)
    if not (
        preflight.get("status") == "pass"
        and preflight.get("formal_rollouts_launched") == 0
        and preflight.get("contract_sha256") == contract_hash
    ):
        raise ValueError("SF4 preflight marker is not bound to the frozen contract")
    labels = {row.get("label") for row in smoke.get("records", [])}
    if not (
        smoke.get("status") == "pass"
        and smoke.get("formal_rollouts_observed") == 0
        and smoke.get("contract_sha256") == contract_hash
        and labels == {"fixed_on", "fixed_off", "adaptive_on", "adaptive_off"}
        and all(row.get("status") == "pass" for row in smoke.get("records", []))
    ):
        raise ValueError("SF4 excluded smoke marker is invalid")


def audit_infrastructure_attempt(record_path: Path) -> dict[str, Any]:
    """Prove that one finalized attempt contains no scientific observation.

    The attempt manager writes a failure summary even when CARLA times out
    before the first simulation tick.  Therefore summary *existence* is not a
    success criterion: the canonical ``valid_scenario`` predicate is.  We also
    reject non-empty partial measurement files, since accepting those would
    permit outcome-dependent retrying.
    """

    attempt = record_path.parent
    record = read_json(record_path)
    log_path = attempt / "runner_attempt.log"
    hygiene_path = attempt / "world_hygiene.json"
    directory_match = re.fullmatch(r"attempt_([0-9]{3})", attempt.name)
    if directory_match is None:
        raise ValueError(f"Invalid attempt directory: {attempt}")
    directory_attempt = int(directory_match.group(1))
    if not (
        log_path.is_file()
        and hygiene_path.is_file()
        and record.get("attempt_log_sha256") == sha256(log_path)
        and record.get("world_hygiene_sha256") == sha256(hygiene_path)
    ):
        raise ValueError(f"Exhausted attempt log/hygiene provenance drift: {attempt}")
    matches = set(record.get("classifier_matches") or [])
    if not (
        record.get("schema_version") == "r3_attempt_record_v2"
        and int(record.get("attempt", -1)) == directory_attempt
        and record.get("accepted") is False
        and record.get("classification") == "infrastructure_failure"
        and record.get("retry_allowed") is True
        and int(record.get("exit_code", 0)) != 0
        and "carla_timeout" in matches
        and "raw_evidence_sha256_before_promotion" in record
        and record["raw_evidence_sha256_before_promotion"] is None
    ):
        raise ValueError(f"Attempt is not eligible infrastructure-only evidence: {record_path}")

    init_id = int(record.get("ego_init_id", -1))
    summaries = scenario_summaries(attempt, init_id)
    valid = [path for path in summaries if valid_scenario(path)]
    if (
        int(record.get("scenario_summaries_found", -1)) != len(summaries)
        or int(record.get("successful_scenarios_found", -1)) != len(valid)
        or valid
    ):
        raise ValueError(f"Attempt scenario inventory/provenance drift: {record_path}")

    summary_entries = []
    for summary_path in summaries:
        summary = read_json(summary_path)
        error = str(summary.get("error") or "")
        normalized_error = error.lower().replace("-", "")
        if summary.get("ran_successfully") is not False or not (
            "timeout" in normalized_error
            and ("simulator" in normalized_error or "server" in normalized_error)
        ):
            raise ValueError(
                f"Failure summary is not an unambiguous CARLA timeout: {summary_path}"
            )
        failures = scenario_validation_failures(summary_path)
        if not failures or "summary_not_successful" not in failures:
            raise ValueError(f"Failure summary unexpectedly validates: {summary_path}")
        summary_entries.append(
            {
                "path": str(summary_path),
                "sha256": sha256(summary_path),
                "ran_successfully": False,
                "error_sha256": hashlib.sha256(error.encode("utf-8")).hexdigest(),
                "validation_failures": failures,
            }
        )

    nonempty_payloads = sorted(
        str(path.relative_to(attempt))
        for path in attempt.rglob("*")
        if path.is_file()
        and path.name in SCIENTIFIC_PAYLOAD_BASENAMES
        and path.stat().st_size > 0
    )
    if nonempty_payloads:
        raise ValueError(
            f"Attempt contains partial scientific payloads {nonempty_payloads}: {record_path}"
        )
    return {
        "record": record,
        "log_path": log_path,
        "scenario_summaries": summary_entries,
        "scenario_summaries_found": len(summaries),
        "valid_scientific_scenarios_found": 0,
        "nonempty_scientific_payloads": [],
    }


def find_exhausted(
    root: Path, keys: set[tuple[str, int]], original_max: int
) -> tuple[str, int, Path, list[tuple[Path, dict[str, Any], dict[str, Any]]], int]:
    observed_receipts = 0
    exhausted = []
    for cell_id, init_id in sorted(keys):
        cell = root / cell_id
        receipt = cell / f"SF4_ROLLOUT_{init_id}_COMPLETE.json"
        if receipt.is_file():
            if not valid_receipt(cell, cell_id, init_id, "SF4"):
                raise ValueError(f"Existing SF4 receipt/provenance drift: {receipt}")
            observed_receipts += 1
            continue
        attempts_root = cell / "_attempts" / f"init_{init_id}"
        attempts = sorted(attempts_root.glob("attempt_[0-9][0-9][0-9]"))
        if len(attempts) >= original_max:
            exhausted.append((cell_id, init_id, attempts_root, attempts))
    if len(exhausted) != 1:
        raise ValueError(
            f"Recovery requires exactly one exhausted pending key, found {len(exhausted)}"
        )
    cell_id, init_id, attempts_root, attempts = exhausted[0]
    if len(attempts) != original_max:
        raise ValueError("Exhausted key does not have exactly the original attempt cap")
    records = []
    for attempt in attempts:
        record_path = attempt / "attempt_record.json"
        if not record_path.is_file():
            raise ValueError(f"Exhausted attempt lacks final record: {attempt}")
        audit = audit_infrastructure_attempt(record_path)
        record = audit["record"]
        if not (
            record.get("cell_id") == cell_id
            and int(record.get("ego_init_id", -1)) == init_id
        ):
            raise ValueError(f"Attempt target identity drift: {record_path}")
        records.append((record_path, audit["record"], audit))
    return cell_id, init_id, attempts_root, records, observed_receipts


def prepare(args: argparse.Namespace) -> None:
    root = args.results_dir.resolve()
    repo = args.repo.resolve()
    contract_path = args.contract.resolve()
    preflight_path = args.preflight.resolve()
    smoke_path = args.smoke.resolve()
    contract = read_json(contract_path)
    if contract.get("schema_version") != "sf4_supervisor_behavioural_authority_run_contract_v1":
        raise ValueError("Unexpected SF4 run-contract schema")
    original_max = int((contract.get("retry_policy") or {}).get("max_attempts", -1))
    if original_max <= 0 or args.extended_max <= original_max:
        raise ValueError("Recovery cap must strictly extend the frozen positive cap")
    keys = contract_keys(contract)
    validate_markers(root, contract_path, preflight_path, smoke_path)
    source_hashes = validate_frozen_sources(repo, contract)
    script_path = Path(__file__).resolve()
    recovery_runner = args.recovery_runner.resolve()
    current_commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    existing_amendments = sorted(
        root.glob(
            "SF4_B1_*/_attempts/init_*/"
            "SF4_INFRASTRUCTURE_RECOVERY_AMENDMENT.json"
        )
    )
    if existing_amendments:
        if len(existing_amendments) != 1:
            raise ValueError("Expected exactly one existing SF4 recovery amendment")
        output = existing_amendments[0]
        amendment = read_json(output)
        target = amendment.get("target") or {}
        if not (
            amendment.get("schema_version") == SCHEMA
            and amendment.get("status") == "frozen_before_recovery_attempt"
            and amendment.get("contract_sha256") == sha256(contract_path)
            and amendment.get("contract_git_commit") == contract.get("git_commit")
            and amendment.get("original_max_attempts") == original_max
            and amendment.get("extended_max_attempts_for_target_only")
            == int(args.extended_max)
            and amendment.get("frozen_execution_source_sha256") == source_hashes
            and (str(target.get("cell_id")), int(target.get("ego_init_id", -1)))
            in keys
        ):
            raise ValueError("Existing SF4 recovery amendment is invalid or stale")
        expected_recovery_sources = {
            str(script_path.relative_to(repo)): sha256(script_path),
            str(recovery_runner.relative_to(repo)): sha256(recovery_runner),
        }
        if amendment.get("recovery_source_sha256") != expected_recovery_sources:
            raise ValueError("Existing SF4 recovery source hashes drifted")
        prior_attempts = amendment.get("prior_attempts") or []
        if (
            len(prior_attempts) != original_max
            or [int(item.get("attempt", -1)) for item in prior_attempts]
            != list(range(1, original_max + 1))
        ):
            raise ValueError("Frozen pre-recovery attempt set is incomplete")
        for frozen in prior_attempts:
            record_path = root / str(frozen.get("record"))
            log_path = root / str(frozen.get("log"))
            if not (
                record_path.is_file()
                and log_path.is_file()
                and sha256(record_path) == frozen.get("record_sha256")
                and sha256(log_path) == frozen.get("log_sha256")
            ):
                raise ValueError("Frozen pre-recovery attempt provenance drifted")
            audit = audit_infrastructure_attempt(record_path)
            audit_record = audit["record"]
            expected_summaries = []
            for item in audit["scenario_summaries"]:
                expected_summaries.append(
                    {
                        **item,
                        "path": str(Path(item["path"]).relative_to(root)),
                    }
                )
            if not (
                audit_record.get("cell_id") == target.get("cell_id")
                and int(audit_record.get("ego_init_id", -1))
                == int(target.get("ego_init_id", -1))
                and int(audit_record.get("attempt", -1))
                == int(frozen.get("attempt", -2))
                and frozen.get("scenario_summaries") == expected_summaries
                and frozen.get("scenario_summaries_found")
                == audit["scenario_summaries_found"]
                and frozen.get("valid_scientific_scenarios_found") == 0
                and frozen.get("nonempty_scientific_payloads") == []
            ):
                raise ValueError("Frozen pre-recovery scientific inventory drifted")
        print(
            json.dumps(
                {
                    "status": "pass",
                    "cell_id": str(target["cell_id"]),
                    "ego_init_id": int(target["ego_init_id"]),
                    "original_max_attempts": original_max,
                    "extended_max_attempts": args.extended_max,
                    "contract_git_commit": contract.get("git_commit"),
                    "amendment": str(output),
                    "amendment_sha256": sha256(output),
                    "observed_receipts": sum(
                        1
                        for cell_id, init_id in keys
                        if (root / cell_id / f"SF4_ROLLOUT_{init_id}_COMPLETE.json").is_file()
                    ),
                },
                sort_keys=True,
            )
        )
        return
    if (root / "SF4_COMPLETE.json").exists():
        raise ValueError("SF4 is already complete; new recovery is not applicable")
    cell_id, init_id, attempts_root, records, observed_receipts = find_exhausted(
        root, keys, original_max
    )
    record_entries = []
    for record_path, record, audit in records:
        log_path = audit["log_path"]
        summaries = [
            {**item, "path": str(Path(item["path"]).relative_to(root))}
            for item in audit["scenario_summaries"]
        ]
        record_entries.append(
            {
                "attempt": int(record["attempt"]),
                "record": str(record_path.relative_to(root)),
                "record_sha256": sha256(record_path),
                "log": str(log_path.relative_to(root)),
                "log_sha256": sha256(log_path),
                "classifier_matches": record.get("classifier_matches"),
                "scenario_summaries": summaries,
                "scenario_summaries_found": audit["scenario_summaries_found"],
                "valid_scientific_scenarios_found": 0,
                "nonempty_scientific_payloads": [],
            }
        )
    amendment = {
        "schema_version": SCHEMA,
        "status": "frozen_before_recovery_attempt",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": "CARLA API outage exhausted the infrastructure-only attempt cap",
        "decision_basis_excludes_scientific_outcomes": True,
        "complete_scientific_scenario_outputs_observed": False,
        "treatment_or_analysis_changed": False,
        "existing_receipts_modified": False,
        "existing_receipts_observed": observed_receipts,
        "target": {"cell_id": cell_id, "ego_init_id": init_id},
        "original_max_attempts": original_max,
        "extended_max_attempts_for_target_only": int(args.extended_max),
        "other_keys_max_attempts": original_max,
        "prior_attempts": record_entries,
        "contract": str(contract_path.relative_to(root)),
        "contract_sha256": sha256(contract_path),
        "contract_git_commit": contract.get("git_commit"),
        "recovery_code_git_commit": current_commit,
        "frozen_execution_source_sha256": source_hashes,
        "recovery_source_sha256": {
            str(script_path.relative_to(repo)): sha256(script_path),
            str(recovery_runner.relative_to(repo)): sha256(recovery_runner),
        },
    }
    output = attempts_root / "SF4_INFRASTRUCTURE_RECOVERY_AMENDMENT.json"
    atomic_json(output, amendment, frozen=True)
    print(
        json.dumps(
            {
                "status": "pass",
                "cell_id": cell_id,
                "ego_init_id": init_id,
                "original_max_attempts": original_max,
                "extended_max_attempts": args.extended_max,
                "contract_git_commit": contract.get("git_commit"),
                "amendment": str(output),
                "amendment_sha256": sha256(output),
                "observed_receipts": observed_receipts,
            },
            sort_keys=True,
        )
    )


def complete(args: argparse.Namespace) -> None:
    root = args.results_dir.resolve()
    contract = args.contract.resolve()
    prereg = args.prereg.resolve()
    spawn = args.spawn.resolve()
    deployment = args.deployment.resolve()
    analysis_path = args.analysis.resolve()
    archive = args.archive.resolve()
    sidecar = Path(str(archive) + ".json")
    manifest = Path(str(archive) + ".files.json")
    full_marker = args.full_marker.resolve()
    amendment = args.amendment.resolve()
    analysis = read_json(analysis_path)
    marker = read_json(full_marker)
    archive_sidecar = read_json(sidecar)
    files_manifest = read_json(manifest)
    if not (
        analysis.get("status") == "pass"
        and analysis.get("observed_rollouts") == 80
        and analysis.get("independent_init_clusters") == 10
        and (analysis.get("implementation_manipulation_gate") or {}).get("status") == "pass"
    ):
        raise ValueError("SF4 formal analysis is incomplete")
    if (analysis.get("observed_first_stage_activity") or {}).get("status") not in {
        "active", "inactive_scientific_outcome"
    }:
        raise ValueError("SF4 first-stage activity result is missing")
    if not (
        marker.get("status") == "pass"
        and marker.get("observed_rollouts") == 80
        and marker.get("archive_sha256") == sha256(archive)
        and archive_sidecar.get("archive_sha256") == sha256(archive)
        and marker.get("files_manifest_sha256") == sha256(manifest)
        and archive_sidecar.get("files_manifest_sha256") == sha256(manifest)
        and marker.get("archive_sidecar_sha256") == sha256(sidecar)
        and marker.get("bbox_and_separation_recomputation_supported") is True
        and marker.get("server_wall_time_recomputation_supported") is True
        and marker.get("controller_acceptance_and_raw_status_recomputation_supported")
        is True
        and marker.get("receipt_raw_and_attempt_provenance_verified") is True
        and marker.get("source_files_deleted") is False
    ):
        raise ValueError("SF4 full raw snapshot is incomplete")
    amendment_value = read_json(amendment)
    if amendment_value.get("status") != "frozen_before_recovery_attempt":
        raise ValueError("SF4 recovery amendment is invalid")
    amendment_relative = str(amendment.relative_to(root))
    archived_paths = {
        str(item.get("path")) for item in files_manifest.get("files", [])
        if isinstance(item, Mapping)
    }
    if amendment_relative not in archived_paths:
        raise ValueError("Full raw snapshot does not contain the recovery amendment")
    payload = {
        "schema_version": COMPLETE_SCHEMA,
        "status": "pass",
        "formal_evidence": True,
        "observed_rollouts": 80,
        "independent_init_clusters": 10,
        "scientific_direction_never_blocks_completion": True,
        "observed_activity_never_triggers_extra_rollouts": True,
        "primary_estimand": "(adaptive-fixed_medium)_on - (adaptive-fixed_medium)_off",
        "implementation_manipulation_gate": analysis.get("implementation_manipulation_gate"),
        "observed_first_stage_activity_status": (
            analysis.get("observed_first_stage_activity") or {}
        ).get("status"),
        "solver_execution": analysis.get("solver_execution"),
        "server_wall_time_diagnostics": analysis.get("server_wall_time_diagnostics"),
        "infrastructure_recovery_amendment": amendment_relative,
        "infrastructure_recovery_amendment_sha256": sha256(amendment),
        "additional_sf4_carla_rollouts_required": False,
        "contract_sha256": sha256(contract),
        "preregistration_sha256": sha256(prereg),
        "spawn_preflight_sha256": sha256(spawn),
        "deployment_preflight_sha256": sha256(deployment),
        "analysis_complete_sha256": sha256(analysis_path),
        "full_raw_snapshot": archive.name,
        "full_raw_snapshot_sha256": sha256(archive),
        "full_raw_snapshot_sidecar_sha256": sha256(sidecar),
        "full_raw_snapshot_files_manifest_sha256": sha256(manifest),
        "full_raw_snapshot_complete_sha256": sha256(full_marker),
        "bbox_and_separation_recomputation_supported": True,
        "server_wall_time_recomputation_supported": True,
        "controller_acceptance_and_raw_status_recomputation_supported": True,
        "source_raw_evidence_deleted": False,
    }
    atomic_json(root / "SF4_COMPLETE.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--results-dir", required=True, type=Path)
    prepare_parser.add_argument("--repo", required=True, type=Path)
    prepare_parser.add_argument("--contract", required=True, type=Path)
    prepare_parser.add_argument("--preflight", required=True, type=Path)
    prepare_parser.add_argument("--smoke", required=True, type=Path)
    prepare_parser.add_argument("--recovery-runner", required=True, type=Path)
    prepare_parser.add_argument("--extended-max", default=20, type=int)
    prepare_parser.set_defaults(func=prepare)
    complete_parser = sub.add_parser("complete")
    complete_parser.add_argument("--results-dir", required=True, type=Path)
    complete_parser.add_argument("--contract", required=True, type=Path)
    complete_parser.add_argument("--prereg", required=True, type=Path)
    complete_parser.add_argument("--spawn", required=True, type=Path)
    complete_parser.add_argument("--deployment", required=True, type=Path)
    complete_parser.add_argument("--analysis", required=True, type=Path)
    complete_parser.add_argument("--archive", required=True, type=Path)
    complete_parser.add_argument("--full-marker", required=True, type=Path)
    complete_parser.add_argument("--amendment", required=True, type=Path)
    complete_parser.set_defaults(func=complete)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
