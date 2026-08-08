#!/usr/bin/env python3
"""Transactional attempt isolation and recovery for the formal R3 matrix.

Each CARLA invocation writes into a fresh ``attempt_NNN`` directory.  A
successful scenario directory is atomically promoted into the canonical cell
directory; failed and interrupted attempts remain immutable provenance.  This
prevents JSONL/CSV data from different process lifetimes being mixed after a
server interruption.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INFRASTRUCTURE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("world_hygiene", r"R3_INFRASTRUCTURE_WORLD_HYGIENE_FAILURE"),
    ("spawn_collision", r"Spawn failed because of collision at spawn position"),
    ("scenario_setup", r"Failed to setup the scenario!"),
    ("carla_connection", r"(?:connection refused|failed to connect|tcp connection|rpc.*(?:timeout|error)|carla server.*(?:lost|unavailable))"),
    ("carla_timeout", r"(?:time-out of \d+ms|timeout while waiting|RuntimeError:.*(?:time-out|timeout))"),
    ("process_resource", r"(?:CUDA out of memory|std::bad_alloc|Killed\s*$|Segmentation fault)"),
)
SIGNAL_EXIT_CODES = set(range(128 + 1, 128 + 16))


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def attempt_root(cell_dir: Path, init_id: int) -> Path:
    return cell_dir / "_attempts" / f"init_{init_id}"


def receipt_path(cell_dir: Path, init_id: int) -> Path:
    return cell_dir / f"R3_ROLLOUT_{init_id}_COMPLETE.json"


def scenario_summaries(root: Path, init_id: int) -> list[Path]:
    return sorted(root.glob(f"scenario_*_ego_init_{init_id}_*/scenario_run_summary.json"))


RAW_REQUIRED_JSON = (
    "scenario_run_summary.json",
    "scenario_rollout_config.json",
    "smpc_debug_setup.json",
    "prediction_deployment_manifest.json",
    "prediction_dataset/prediction_dataset_config.json",
    "prediction_dataset/prediction_dataset_manifest.json",
)
RAW_REQUIRED_JSONL = (
    "smpc_debug_steps.jsonl",
    "prediction_dataset/prediction_dataset_raw.jsonl",
    "prediction_dataset/prediction_dataset_labeled.jsonl",
)
RAW_REQUIRED_FILES = RAW_REQUIRED_JSON + RAW_REQUIRED_JSONL + ("scenario_result.pkl", "scenario_steps.csv")
RAW_OPTIONAL_FILES = ("smpc_completion.json",)


def scenario_validation_failures(summary_path: Path) -> list[str]:
    scenario_dir = summary_path.parent
    failures: list[str] = []
    values: dict[str, Any] = {}
    for relative in RAW_REQUIRED_JSON:
        path = scenario_dir / relative
        if not path.is_file() or path.stat().st_size == 0:
            failures.append(f"missing_or_empty:{relative}")
            continue
        try:
            values[relative] = read_json(path)
        except (OSError, ValueError, TypeError):
            failures.append(f"invalid_json:{relative}")
    if (values.get("scenario_run_summary.json") or {}).get("ran_successfully") is not True:
        failures.append("summary_not_successful")
    for relative in RAW_REQUIRED_JSONL:
        path = scenario_dir / relative
        if not path.is_file() or path.stat().st_size == 0:
            failures.append(f"missing_or_empty:{relative}")
            continue
        try:
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if not rows:
                failures.append(f"no_jsonl_rows:{relative}")
        except (OSError, ValueError, TypeError):
            failures.append(f"invalid_jsonl:{relative}")
    pkl_path = scenario_dir / "scenario_result.pkl"
    if not pkl_path.is_file() or pkl_path.stat().st_size == 0:
        failures.append("missing_or_empty:scenario_result.pkl")
    else:
        try:
            with pkl_path.open("rb") as handle:
                value = pickle.load(handle)
            if not isinstance(value, dict) or not value:
                failures.append("invalid_payload:scenario_result.pkl")
        except Exception:  # pickle may surface several truncation/import errors.
            failures.append("invalid_pickle:scenario_result.pkl")
    steps_path = scenario_dir / "scenario_steps.csv"
    if not steps_path.is_file() or steps_path.stat().st_size == 0:
        failures.append("missing_or_empty:scenario_steps.csv")
    else:
        try:
            rows = [line for line in steps_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if len(rows) < 2:
                failures.append("no_data_rows:scenario_steps.csv")
        except (OSError, UnicodeError):
            failures.append("invalid_text:scenario_steps.csv")
    completion_path = scenario_dir / "smpc_completion.json"
    if completion_path.is_file():
        try:
            read_json(completion_path)
        except (OSError, ValueError, TypeError):
            failures.append("invalid_json:smpc_completion.json")
    return sorted(set(failures))


def valid_scenario(summary_path: Path) -> bool:
    try:
        return not scenario_validation_failures(summary_path)
    except (OSError, ValueError, TypeError, EOFError):
        return False


def raw_evidence_sha256(scenario_dir: Path) -> str:
    """Hash only immutable CARLA outputs, not later derived post-processing."""

    digest = hashlib.sha256()
    for relative in RAW_REQUIRED_FILES + RAW_OPTIONAL_FILES:
        path = scenario_dir / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(path).encode("ascii") if path.is_file() else b"ABSENT_BY_DESIGN")
        digest.update(b"\n")
    return digest.hexdigest()


def is_experiment_actor_type(type_id: object) -> bool:
    value = str(type_id or "")
    return value.startswith("vehicle.") or value.startswith("sensor.")


def stale_actor_records(actors: Any) -> list[dict[str, Any]]:
    records = []
    for actor in actors:
        if not is_experiment_actor_type(getattr(actor, "type_id", "")):
            continue
        attributes = dict(getattr(actor, "attributes", {}) or {})
        records.append(
            {
                "id": int(actor.id),
                "type_id": str(actor.type_id),
                "role_name": attributes.get("role_name"),
            }
        )
    return sorted(records, key=lambda item: item["id"])


def critical_artifacts(scenario_dir: Path) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for relative in RAW_REQUIRED_FILES + RAW_OPTIONAL_FILES:
        path = scenario_dir / relative
        if path.is_file():
            artifacts[relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    return artifacts


def refresh_ledger(cell_dir: Path, cell_id: str, init_id: int, max_attempts: int) -> Path:
    root = attempt_root(cell_dir, init_id)
    entries = []
    for directory in sorted(root.glob("attempt_[0-9][0-9][0-9]")):
        started_path = directory / "attempt_started.json"
        record_path = directory / "attempt_record.json"
        entry: dict[str, Any] = {
            "attempt": int(directory.name.rsplit("_", 1)[1]),
            "directory": str(directory.relative_to(cell_dir)),
            "state": "running_or_interrupted",
        }
        if started_path.is_file():
            entry["started"] = read_json(started_path)
            entry["started_sha256"] = sha256(started_path)
        if record_path.is_file():
            entry["record"] = read_json(record_path)
            entry["record_sha256"] = sha256(record_path)
            entry["state"] = "accepted" if entry["record"].get("accepted") else "failed"
        entries.append(entry)
    accepted = [entry for entry in entries if entry["state"] == "accepted"]
    payload = {
        "schema_version": "r3_attempt_ledger_v2",
        "status": "accepted" if accepted else "open",
        "cell_id": cell_id,
        "ego_init_id": init_id,
        "max_attempts": max_attempts,
        "attempts_started": len(entries),
        "accepted_attempts": len(accepted),
        "attempts": entries,
        "updated_at_utc": now_utc(),
    }
    path = root / "attempt_ledger.json"
    if path.is_file():
        previous = read_json(path)
        previous_semantic = {key: value for key, value in previous.items() if key != "updated_at_utc"}
        payload_semantic = {key: value for key, value in payload.items() if key != "updated_at_utc"}
        if previous_semantic == payload_semantic:
            return path
    atomic_json(path, payload)
    return path


def classify_failure(exit_code: int, log_text: str) -> tuple[str, bool, list[str]]:
    matches = [
        name
        for name, expression in INFRASTRUCTURE_PATTERNS
        if re.search(expression, log_text, flags=re.IGNORECASE | re.MULTILINE)
    ]
    if exit_code in SIGNAL_EXIT_CODES:
        matches.append("external_signal")
    if matches:
        return "infrastructure_failure", True, sorted(set(matches))
    return "unknown_nonretryable_failure", False, []


def write_receipt(
    *,
    cell_dir: Path,
    cell_id: str,
    init_id: int,
    scenario_dir: Path,
    attempt_number: int,
    record_path: Path,
    ledger_path: Path,
    recovery: bool,
) -> Path:
    summary_path = scenario_dir / "scenario_run_summary.json"
    payload = {
        "schema_version": "r3_rollout_complete_v2",
        "status": "pass",
        "cell_id": cell_id,
        "ego_init_id": init_id,
        "accepted_attempt": attempt_number,
        "recovered_after_interruption": recovery,
        "scenario_dir": str(scenario_dir.relative_to(cell_dir)),
        "raw_evidence_sha256": raw_evidence_sha256(scenario_dir),
        "scenario_summary_sha256": sha256(summary_path),
        "attempt_record": str(record_path.relative_to(cell_dir)),
        "attempt_record_sha256": sha256(record_path),
        "attempt_ledger": str(ledger_path.relative_to(cell_dir)),
        "attempt_ledger_sha256_at_receipt": sha256(ledger_path),
        "critical_artifacts": critical_artifacts(scenario_dir),
        "optional_artifact_presence": {
            relative: (scenario_dir / relative).is_file() for relative in RAW_OPTIONAL_FILES
        },
        "accepted_at_utc": now_utc(),
    }
    output = receipt_path(cell_dir, init_id)
    atomic_json(output, payload)
    return output


def valid_receipt(cell_dir: Path, cell_id: str, init_id: int) -> bool:
    path = receipt_path(cell_dir, init_id)
    try:
        payload = read_json(path)
        scenario_dir = cell_dir / payload["scenario_dir"]
        summary_path = scenario_dir / "scenario_run_summary.json"
        return (
            payload.get("status") == "pass"
            and payload.get("cell_id") == cell_id
            and int(payload.get("ego_init_id", -1)) == init_id
            and valid_scenario(summary_path)
            and sha256(summary_path) == payload.get("scenario_summary_sha256")
            and raw_evidence_sha256(scenario_dir) == payload.get("raw_evidence_sha256")
        )
    except (OSError, KeyError, TypeError, ValueError):
        return False


def reconcile(cell_dir: Path, cell_id: str, init_id: int, max_attempts: int) -> None:
    root = attempt_root(cell_dir, init_id)
    root.mkdir(parents=True, exist_ok=True)
    canonical = scenario_summaries(cell_dir, init_id)
    if len(canonical) > 1:
        raise RuntimeError(f"Multiple canonical scenarios for {cell_id}/init{init_id}")

    for directory in sorted(root.glob("attempt_[0-9][0-9][0-9]")):
        record_path = directory / "attempt_record.json"
        if record_path.is_file():
            continue
        attempt_number = int(directory.name.rsplit("_", 1)[1])
        summaries = scenario_summaries(directory, init_id)
        successful = [path for path in summaries if valid_scenario(path)]
        if len(successful) == 1 and not canonical:
            source = successful[0].parent
            destination = cell_dir / source.name
            os.replace(source, destination)
            canonical = [destination / "scenario_run_summary.json"]
            classification = "accepted_recovered_before_promotion"
            accepted = True
        elif len(successful) == 0 and len(canonical) == 1:
            # Power may have failed after the atomic promotion but before the
            # terminal record/receipt was committed.
            classification = "accepted_recovered_after_promotion"
            accepted = True
        else:
            classification = "infrastructure_external_interruption"
            accepted = False
        record = {
            "schema_version": "r3_attempt_record_v2",
            "attempt": attempt_number,
            "cell_id": cell_id,
            "ego_init_id": init_id,
            "accepted": accepted,
            "classification": classification,
            "retry_allowed": not accepted,
            "exit_code": None,
            "classifier_matches": ["missing_terminal_record"],
            "recovered_at_utc": now_utc(),
        }
        atomic_json(record_path, record)

    ledger = refresh_ledger(cell_dir, cell_id, init_id, max_attempts)
    if canonical and not valid_scenario(canonical[0]):
        raise RuntimeError(f"Invalid canonical scenario for {cell_id}/init{init_id}")
    receipt = receipt_path(cell_dir, init_id)
    if canonical and receipt.exists() and not valid_receipt(cell_dir, cell_id, init_id):
        raise RuntimeError(f"Existing rollout receipt or immutable raw evidence drifted: {receipt}")
    if canonical and not receipt.exists():
        accepted_records = []
        for record_path in root.glob("attempt_[0-9][0-9][0-9]/attempt_record.json"):
            record = read_json(record_path)
            if record.get("accepted"):
                accepted_records.append((int(record["attempt"]), record_path))
        if len(accepted_records) != 1:
            raise RuntimeError(f"Cannot identify unique accepted attempt for {cell_id}/init{init_id}")
        attempt_number, record_path = accepted_records[0]
        write_receipt(
            cell_dir=cell_dir,
            cell_id=cell_id,
            init_id=init_id,
            scenario_dir=canonical[0].parent,
            attempt_number=attempt_number,
            record_path=record_path,
            ledger_path=ledger,
            recovery=True,
        )


def command_prepare(args: argparse.Namespace) -> int:
    cell_dir = args.cell_dir.resolve()
    cell_dir.mkdir(parents=True, exist_ok=True)
    reconcile(cell_dir, args.cell_id, args.init_id, args.max_attempts)
    if valid_receipt(cell_dir, args.cell_id, args.init_id):
        print(json.dumps({"status": "complete", "receipt": str(receipt_path(cell_dir, args.init_id))}))
        return 0
    root = attempt_root(cell_dir, args.init_id)
    attempts = sorted(root.glob("attempt_[0-9][0-9][0-9]"))
    if attempts:
        latest_record_path = attempts[-1] / "attempt_record.json"
        if latest_record_path.is_file():
            latest_record = read_json(latest_record_path)
            if not latest_record.get("accepted") and latest_record.get("retry_allowed") is not True:
                print(
                    json.dumps(
                        {
                            "status": "blocked_nonretryable",
                            "attempts_started": len(attempts),
                            "classification": latest_record.get("classification"),
                            "record": str(latest_record_path),
                        }
                    )
                )
                return 5
    if len(attempts) >= args.max_attempts:
        print(json.dumps({"status": "exhausted", "attempts_started": len(attempts)}))
        return 4
    attempt_number = len(attempts) + 1
    directory = root / f"attempt_{attempt_number:03d}"
    directory.mkdir()
    atomic_json(
        directory / "attempt_started.json",
        {
            "schema_version": "r3_attempt_started_v2",
            "attempt": attempt_number,
            "cell_id": args.cell_id,
            "ego_init_id": args.init_id,
            "started_at_utc": now_utc(),
            "pid": os.getpid(),
        },
    )
    ledger = refresh_ledger(cell_dir, args.cell_id, args.init_id, args.max_attempts)
    print(
        json.dumps(
            {
                "status": "ready",
                "attempt": attempt_number,
                "attempt_dir": str(directory),
                "attempt_log": str(directory / "runner_attempt.log"),
                "ledger": str(ledger),
            }
        )
    )
    return 0


def command_finalize(args: argparse.Namespace) -> int:
    cell_dir = args.cell_dir.resolve()
    directory = args.attempt_dir.resolve()
    started = read_json(directory / "attempt_started.json")
    attempt_number = int(started["attempt"])
    record_path = directory / "attempt_record.json"
    if record_path.exists():
        raise RuntimeError(f"Attempt already finalized: {record_path}")
    summaries = scenario_summaries(directory, args.init_id)
    successful = [path for path in summaries if valid_scenario(path)]
    log_path = directory / "runner_attempt.log"
    hygiene_path = directory / "world_hygiene.json"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    accepted = args.exit_code == 0 and len(summaries) == 1 and len(successful) == 1
    if accepted:
        existing = scenario_summaries(cell_dir, args.init_id)
        if existing:
            raise RuntimeError(f"Canonical scenario already exists for {args.cell_id}/init{args.init_id}")
        source = successful[0].parent
        destination = cell_dir / source.name
        source_tree = raw_evidence_sha256(source)
        os.replace(source, destination)
        classification, retry_allowed, matches = "accepted", False, []
    else:
        source_tree = None
        classification, retry_allowed, matches = classify_failure(args.exit_code, log_text)
        if args.exit_code == 0:
            classification, retry_allowed = "integrity_failure_after_zero_exit", False
            matches = ["missing_or_ambiguous_successful_scenario"]
    record = {
        "schema_version": "r3_attempt_record_v2",
        "attempt": attempt_number,
        "cell_id": args.cell_id,
        "ego_init_id": args.init_id,
        "accepted": accepted,
        "classification": classification,
        "retry_allowed": retry_allowed,
        "exit_code": args.exit_code,
        "classifier_matches": matches,
        "scenario_summaries_found": len(summaries),
        "successful_scenarios_found": len(successful),
        "attempt_log_sha256": sha256(log_path) if log_path.is_file() else None,
        "world_hygiene_sha256": sha256(hygiene_path) if hygiene_path.is_file() else None,
        "world_hygiene": read_json(hygiene_path) if hygiene_path.is_file() else None,
        "raw_evidence_sha256_before_promotion": source_tree,
        "ended_at_utc": now_utc(),
    }
    atomic_json(record_path, record)
    ledger = refresh_ledger(cell_dir, args.cell_id, args.init_id, args.max_attempts)
    receipt = None
    if accepted:
        receipt = write_receipt(
            cell_dir=cell_dir,
            cell_id=args.cell_id,
            init_id=args.init_id,
            scenario_dir=destination,
            attempt_number=attempt_number,
            record_path=record_path,
            ledger_path=ledger,
            recovery=False,
        )
    result = {
        "status": "accepted" if accepted else "failed",
        "attempt": attempt_number,
        "classification": classification,
        "retry_allowed": retry_allowed,
        "classifier_matches": matches,
        "receipt": str(receipt) if receipt else None,
    }
    print(json.dumps(result))
    return 0 if accepted or retry_allowed else 5


def command_verify(args: argparse.Namespace) -> int:
    cell_dir = args.cell_dir.resolve()
    reconcile(cell_dir, args.cell_id, args.init_id, args.max_attempts)
    valid = valid_receipt(cell_dir, args.cell_id, args.init_id)
    print(json.dumps({"status": "pass" if valid else "fail", "cell_id": args.cell_id, "ego_init_id": args.init_id}))
    return 0 if valid else 1


def command_hygiene(args: argparse.Namespace) -> int:
    """Remove only stale experiment vehicles/sensors on a dedicated server."""

    try:
        import carla  # type: ignore

        client = carla.Client(args.host, args.port)
        client.set_timeout(args.timeout)
        world = client.get_world()
        before = stale_actor_records(world.get_actors())
        responses = []
        if before:
            batch = [carla.command.DestroyActor(item["id"]) for item in before]
            for item in client.apply_batch_sync(batch, True):
                responses.append(
                    {
                        "actor_id": int(getattr(item, "actor_id", 0) or 0),
                        "error": str(getattr(item, "error", "") or ""),
                    }
                )
        after = stale_actor_records(world.get_actors())
        status = "pass" if not after else "fail"
        payload = {
            "schema_version": "r3_world_hygiene_v2",
            "status": status,
            "host": args.host,
            "port": args.port,
            "selection_rule": "type_id starts with vehicle. or sensor.; traffic/infrastructure excluded",
            "dedicated_carla_instance_asserted": True,
            "before": before,
            "destroy_requests": responses,
            "remaining": after,
            "destroyed_count": len(before) - len(after),
            "checked_at_utc": now_utc(),
        }
        atomic_json(args.attempt_dir.resolve() / "world_hygiene.json", payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        if after:
            print("R3_INFRASTRUCTURE_WORLD_HYGIENE_FAILURE: experiment actors remain", file=sys.stderr)
            return 6
        return 0
    except Exception as error:
        payload = {
            "schema_version": "r3_world_hygiene_v2",
            "status": "fail",
            "host": args.host,
            "port": args.port,
            "error_type": type(error).__name__,
            "error": str(error),
            "checked_at_utc": now_utc(),
        }
        atomic_json(args.attempt_dir.resolve() / "world_hygiene.json", payload)
        print(f"R3_INFRASTRUCTURE_WORLD_HYGIENE_FAILURE: {type(error).__name__}: {error}", file=sys.stderr)
        return 6


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "finalize", "verify"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--cell-dir", required=True, type=Path)
        sub.add_argument("--cell-id", required=True)
        sub.add_argument("--init-id", required=True, type=int)
        sub.add_argument("--max-attempts", required=True, type=int)
        if name == "finalize":
            sub.add_argument("--attempt-dir", required=True, type=Path)
            sub.add_argument("--exit-code", required=True, type=int)
    hygiene = subparsers.add_parser("hygiene")
    hygiene.add_argument("--attempt-dir", required=True, type=Path)
    hygiene.add_argument("--host", default="127.0.0.1")
    hygiene.add_argument("--port", default=2000, type=int)
    hygiene.add_argument("--timeout", default=10.0, type=float)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    functions = {
        "prepare": command_prepare,
        "finalize": command_finalize,
        "verify": command_verify,
        "hygiene": command_hygiene,
    }
    raise SystemExit(functions[args.command](args))


if __name__ == "__main__":
    main()
