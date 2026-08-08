#!/usr/bin/env python3
"""Prepare the single R3 rollout recovery authorized by the matrix audit.

The formal R3 audit can reject an otherwise valid rollout when a CARLA actor
starts the controlled loop one simulator tick out of phase with the other
treatments.  This utility does *not* edit, delete, or relabel that evidence.
It first proves the narrowly defined one-tick signature, atomically quarantines
the complete original cell, restores the four unaffected treatment keys, and
leaves exactly one key pending for the frozen collection runner.

The default mode is read-only.  Mutation requires ``--apply``.  Every move is
recoverable and the operation can be rerun after interruption.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


EXPECTED_CELL_ID = "B0_fixed_conservative_assertive"
EXPECTED_INIT_ID = 103
EXPECTED_INTEGRITY_FAILURES = {
    "matrix:first_state_consistency:init103:ego",
    "matrix:fixed_geometry_consistency:init103",
}
EXPECTED_ALL_INITS = (101, 102, 103, 104, 105)
FIRST_STATE_TOLERANCE = 0.1
NONCANDIDATE_GEOMETRY_TOLERANCE_M = 1e-3
MIN_CANDIDATE_PHASE_OFFSET_M = 0.25
MAX_CANDIDATE_PHASE_OFFSET_M = 0.75
ROOT_DERIVED_PATHS = (
    "R3_RAW_COLLECTION_COMPLETE.json",
    "r3_offline_finalization_provenance.json",
    "r3_corrected_matrix_audit.json",
    "R3_DATA_COMPLETE.json",
    "R3_COMPLETE.json",
    "analysis",
    "r3_corrected_formal_snapshot.tar.gz",
    "r3_corrected_formal_snapshot.tar.gz.json",
    "r3_corrected_formal_snapshot.tar.gz.files.json",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _find_rollouts(audit: dict[str, Any], init_id: int) -> list[dict[str, Any]]:
    rows = []
    for evaluation in audit.get("evaluations") or []:
        for rollout in evaluation.get("rollouts") or []:
            if int(rollout.get("ego_init_id", -1)) == init_id:
                rows.append({"cell_id": evaluation.get("cell_id"), **rollout})
    return rows


def _state_vector(row: dict[str, Any], role: str) -> np.ndarray:
    state = (
        (row.get("control_variables") or {})
        .get("first_states_txyyawspeed", {})
        .get(role)
    )
    value = np.asarray(state, dtype=float)
    if value.shape != (5,) or not np.isfinite(value).all():
        raise RuntimeError(f"Malformed {role} first state in {row.get('cell_id')}")
    return value


def _fixed_geometry(root: Path, cell_id: str, init_id: int) -> np.ndarray:
    gate_path = root / cell_id / "postcarla_trajectory_gate.json"
    gate = read_json(gate_path)
    matches = [
        item
        for item in gate.get("evaluations") or []
        if f"init_{init_id}_" in Path(str(item.get("scenario_dir", ""))).name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one gate row for {cell_id}/init{init_id}")
    rules = matches[0].get("fixed_geometry_yield_rules") or []
    if len(rules) != 1 or rules[0].get("geometry_source") != "controller_route_projection":
        raise RuntimeError(f"Missing fixed route geometry for {cell_id}/init{init_id}")
    points = np.asarray(
        [rules[0].get("ego_conflict_point_xy"), rules[0].get("target_conflict_point_xy")],
        dtype=float,
    )
    if points.shape != (2, 2) or not np.isfinite(points).all():
        raise RuntimeError(f"Malformed fixed route geometry for {cell_id}/init{init_id}")
    return points


def _candidate_second_state(root: Path, candidate: dict[str, Any]) -> np.ndarray:
    scenario = root / EXPECTED_CELL_ID / str(candidate.get("scenario"))
    with (scenario / "scenario_result.pkl").open("rb") as handle:
        result = pickle.load(handle)
    ego_keys = [key for key in result if str(key).startswith("ego_")]
    if len(ego_keys) != 1:
        raise RuntimeError("Candidate result does not contain exactly one ego trajectory")
    trajectory = np.asarray(result[ego_keys[0]].get("state_trajectory"), dtype=float)
    if trajectory.ndim != 2 or trajectory.shape[0] < 2 or trajectory.shape[1] < 5:
        raise RuntimeError("Candidate ego trajectory has no second state")
    state = trajectory[1, :5]
    if not np.isfinite(state).all():
        raise RuntimeError("Candidate second ego state is non-finite")
    return state


def build_recovery_plan(root: Path) -> dict[str, Any]:
    audit_path = root / "r3_corrected_matrix_audit.json"
    if not audit_path.is_file():
        raise FileNotFoundError(audit_path)
    audit = read_json(audit_path)
    failures = set(audit.get("integrity_failures") or [])
    if (
        audit.get("status") != "fail"
        or audit.get("integrity_status") != "fail"
        or int(audit.get("observed_rollouts", -1)) != 80
        or int(audit.get("passing_integrity_rollouts", -1)) != 80
        or failures != EXPECTED_INTEGRITY_FAILURES
    ):
        raise RuntimeError(
            "Recovery is authorized only for the exact two init103 matrix failures "
            "after 80/80 rollout-level integrity passes"
        )

    rows = _find_rollouts(audit, EXPECTED_INIT_ID)
    if len(rows) != 16 or len({str(row.get("cell_id")) for row in rows}) != 16:
        raise RuntimeError("Expected exactly 16 treatment rows for init103")
    candidate_rows = [row for row in rows if row.get("cell_id") == EXPECTED_CELL_ID]
    if len(candidate_rows) != 1:
        raise RuntimeError("The authorized recovery cell is absent or duplicated")
    candidate = candidate_rows[0]
    if candidate.get("integrity_status") != "pass" or candidate.get("failures"):
        raise RuntimeError("Candidate must have passed all rollout-level integrity checks")

    peer_rows = [row for row in rows if row is not candidate]
    peer_ego = np.asarray([_state_vector(row, "ego")[1:] for row in peer_rows])
    peer_target = np.asarray([_state_vector(row, "target")[1:] for row in peer_rows])
    peer_ego_reference = np.median(peer_ego, axis=0)
    peer_target_reference = np.median(peer_target, axis=0)
    peer_ego_max_deviation = float(np.max(np.abs(peer_ego - peer_ego_reference)))
    peer_target_max_deviation = float(np.max(np.abs(peer_target - peer_target_reference)))
    if peer_ego_max_deviation > FIRST_STATE_TOLERANCE or peer_target_max_deviation > FIRST_STATE_TOLERANCE:
        raise RuntimeError("The other 15 treatments do not form a consistent first-state cluster")

    candidate_first = _state_vector(candidate, "ego")
    candidate_target = _state_vector(candidate, "target")
    candidate_second = _candidate_second_state(root, candidate)
    first_xy_offset = float(np.linalg.norm(candidate_first[1:3] - peer_ego_reference[:2]))
    second_max_deviation = float(np.max(np.abs(candidate_second[1:] - peer_ego_reference)))
    target_max_deviation = float(np.max(np.abs(candidate_target[1:] - peer_target_reference)))
    if not (MIN_CANDIDATE_PHASE_OFFSET_M <= first_xy_offset <= MAX_CANDIDATE_PHASE_OFFSET_M):
        raise RuntimeError("Candidate first-state offset is not the authorized one-tick signature")
    if second_max_deviation > FIRST_STATE_TOLERANCE:
        raise RuntimeError("Candidate second state does not align with the peer first-state cluster")
    if target_max_deviation > FIRST_STATE_TOLERANCE:
        raise RuntimeError("Candidate target state differs, so this is not an ego-only phase offset")

    peer_geometry = np.asarray(
        [_fixed_geometry(root, str(row["cell_id"]), EXPECTED_INIT_ID) for row in peer_rows]
    )
    geometry_reference = np.median(peer_geometry, axis=0)
    peer_geometry_max_deviation = float(
        np.max(np.linalg.norm(peer_geometry - geometry_reference, axis=2))
    )
    candidate_geometry = _fixed_geometry(root, EXPECTED_CELL_ID, EXPECTED_INIT_ID)
    candidate_geometry_max_deviation = float(
        np.max(np.linalg.norm(candidate_geometry - geometry_reference, axis=1))
    )
    if peer_geometry_max_deviation > NONCANDIDATE_GEOMETRY_TOLERANCE_M:
        raise RuntimeError("The other 15 treatments do not share fixed route geometry")
    if candidate_geometry_max_deviation <= NONCANDIDATE_GEOMETRY_TOLERANCE_M:
        raise RuntimeError("Candidate is not the unique fixed-geometry outlier")

    cell_dir = root / EXPECTED_CELL_ID
    receipt_path = cell_dir / f"R3_ROLLOUT_{EXPECTED_INIT_ID}_COMPLETE.json"
    if not receipt_path.is_file():
        raise FileNotFoundError(receipt_path)
    receipt_hash = sha256(receipt_path)
    declared_receipt_hash = (
        (candidate.get("attempt_provenance") or {}).get("receipt_sha256")
    )
    if receipt_hash != declared_receipt_hash:
        raise RuntimeError("Candidate receipt changed after the failed matrix audit")
    receipt = read_json(receipt_path)
    if (
        receipt.get("cell_id") != EXPECTED_CELL_ID
        or int(receipt.get("ego_init_id", -1)) != EXPECTED_INIT_ID
        or receipt.get("status") != "pass"
    ):
        raise RuntimeError("Candidate receipt identity is invalid")

    previous_raw_marker_path = root / "R3_RAW_COLLECTION_COMPLETE.json"
    if not previous_raw_marker_path.is_file():
        raise FileNotFoundError(previous_raw_marker_path)
    previous_raw_marker = read_json(previous_raw_marker_path)
    previous_entries = previous_raw_marker.get("entries") or []
    if (
        previous_raw_marker.get("status") != "pass"
        or int(previous_raw_marker.get("accepted_rollouts", -1)) != 80
        or len(previous_entries) != 80
    ):
        raise RuntimeError("The pre-recovery raw collection marker is incomplete")
    previous_candidate_entries = [
        item
        for item in previous_entries
        if item.get("cell_id") == EXPECTED_CELL_ID
        and int(item.get("ego_init_id", -1)) == EXPECTED_INIT_ID
    ]
    if (
        len(previous_candidate_entries) != 1
        or previous_candidate_entries[0].get("receipt_sha256") != receipt_hash
        or previous_candidate_entries[0].get("raw_evidence_sha256")
        != receipt.get("raw_evidence_sha256")
    ):
        raise RuntimeError("The failed audit and frozen raw collection marker disagree")

    audit_hash = sha256(audit_path)
    recovery_id = f"init103_one_tick_phase_{audit_hash[:12]}"
    return {
        "schema_version": "r3_integrity_recovery_plan_v1",
        "status": "validated_read_only",
        "classification": "same_treatment_key_integrity_recovery",
        "recovery_id": recovery_id,
        "results_dir": str(root.resolve()),
        "cell_id": EXPECTED_CELL_ID,
        "ego_init_id": EXPECTED_INIT_ID,
        "audit": audit_path.name,
        "audit_sha256": audit_hash,
        "triggering_integrity_failures": sorted(EXPECTED_INTEGRITY_FAILURES),
        "observed_rollouts_before_recovery": 80,
        "passing_rollout_integrity_before_recovery": 80,
        "candidate_receipt_sha256": receipt_hash,
        "candidate_raw_evidence_sha256": receipt.get("raw_evidence_sha256"),
        "previous_raw_collection_marker_sha256": sha256(previous_raw_marker_path),
        "previous_raw_collection_receipt_manifest_sha256": previous_raw_marker.get(
            "receipt_manifest_sha256"
        ),
        "diagnostics": {
            "peer_treatments": 15,
            "peer_ego_first_state_max_abs_deviation": peer_ego_max_deviation,
            "peer_target_first_state_max_abs_deviation": peer_target_max_deviation,
            "candidate_first_xy_offset_m": first_xy_offset,
            "candidate_second_state_max_abs_deviation_from_peer_first_state": second_max_deviation,
            "candidate_target_max_abs_deviation_from_peer_target": target_max_deviation,
            "peer_fixed_geometry_max_deviation_m": peer_geometry_max_deviation,
            "candidate_fixed_geometry_max_deviation_m": candidate_geometry_max_deviation,
            "simulator_fps": 20,
            "diagnosis": "ego-only one-simulator-tick controlled-loop phase offset",
        },
        "scientific_outcomes_used_to_select_recovery": False,
        "outcome_dependent_rerun_prohibited": True,
        "replacement_scope": {"cell_id": EXPECTED_CELL_ID, "ego_init_id": EXPECTED_INIT_ID},
        "collection_runner_commit_required": "8ccecf848b87b6fa2936e081d9f6943cd7f5a449",
        "created_at_utc": now_utc(),
    }


def _move_if_present(source: Path, destination: Path) -> bool:
    if destination.exists():
        if source.exists():
            raise RuntimeError(f"Both source and destination exist: {source} -> {destination}")
        return False
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    return True


def _scenario_dirs(cell_dir: Path, init_id: int) -> list[Path]:
    return sorted(cell_dir.glob(f"scenario_*_ego_init_{init_id}_*"))


def _validate_prepared_layout(root: Path, recovery_dir: Path) -> None:
    cell_dir = root / EXPECTED_CELL_ID
    quarantined = recovery_dir / "quarantined_cell"
    for init_id in EXPECTED_ALL_INITS:
        expected_present = init_id != EXPECTED_INIT_ID
        receipt_present = (cell_dir / f"R3_ROLLOUT_{init_id}_COMPLETE.json").is_file()
        scenario_count = len(_scenario_dirs(cell_dir, init_id))
        attempt_present = (cell_dir / "_attempts" / f"init_{init_id}").is_dir()
        if (receipt_present, scenario_count == 1, attempt_present) != (
            expected_present,
            expected_present,
            expected_present,
        ):
            raise RuntimeError(f"Prepared replacement layout is invalid for init{init_id}")
    if not (quarantined / f"R3_ROLLOUT_{EXPECTED_INIT_ID}_COMPLETE.json").is_file():
        raise RuntimeError("Quarantine lost the rejected receipt")
    if len(_scenario_dirs(quarantined, EXPECTED_INIT_ID)) != 1:
        raise RuntimeError("Quarantine lost the rejected scenario")


def apply_recovery(root: Path, plan: dict[str, Any]) -> Path:
    recovery_dir = root / "_integrity_recovery" / str(plan["recovery_id"])
    plan_path = recovery_dir / "recovery_plan.json"
    marker_path = root / "R3_INTEGRITY_RECOVERY_PREPARED.json"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    if plan_path.is_file():
        frozen = read_json(plan_path)
        if frozen.get("audit_sha256") != plan.get("audit_sha256"):
            raise RuntimeError("Existing recovery plan does not match the failed audit")
        plan = frozen
    else:
        atomic_json(plan_path, plan)

    cell_dir = root / EXPECTED_CELL_ID
    quarantined = recovery_dir / "quarantined_cell"
    if cell_dir.exists() and not quarantined.exists():
        os.replace(cell_dir, quarantined)
    elif not cell_dir.exists() and not quarantined.exists():
        raise RuntimeError("Neither the original cell nor its quarantine exists")
    cell_dir.mkdir(parents=True, exist_ok=True)
    (cell_dir / "_attempts").mkdir(exist_ok=True)

    moves = []
    for init_id in EXPECTED_ALL_INITS:
        if init_id == EXPECTED_INIT_ID:
            continue
        receipt_name = f"R3_ROLLOUT_{init_id}_COMPLETE.json"
        if _move_if_present(quarantined / receipt_name, cell_dir / receipt_name):
            moves.append(receipt_name)
        source_scenarios = _scenario_dirs(quarantined, init_id)
        destination_scenarios = _scenario_dirs(cell_dir, init_id)
        if source_scenarios and destination_scenarios:
            raise RuntimeError(f"Duplicate scenario evidence while recovering init{init_id}")
        if len(source_scenarios) == 1:
            destination = cell_dir / source_scenarios[0].name
            os.replace(source_scenarios[0], destination)
            moves.append(destination.name)
        elif len(destination_scenarios) != 1:
            raise RuntimeError(f"Missing unaffected scenario for init{init_id}")
        source_attempt = quarantined / "_attempts" / f"init_{init_id}"
        destination_attempt = cell_dir / "_attempts" / f"init_{init_id}"
        if _move_if_present(source_attempt, destination_attempt):
            moves.append(f"_attempts/init_{init_id}")

    derived_archive = recovery_dir / "root_derived_before_recovery"
    for relative in ROOT_DERIVED_PATHS:
        source = root / relative
        destination = derived_archive / relative
        if source.exists():
            if destination.exists():
                raise RuntimeError(f"Derived evidence exists in both locations: {relative}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            moves.append(relative)

    _validate_prepared_layout(root, recovery_dir)
    marker = {
        **plan,
        "schema_version": "r3_integrity_recovery_prepared_v1",
        "status": "prepared",
        "prepared_at_utc": now_utc(),
        "quarantine": recovery_dir.relative_to(root).as_posix(),
        "preserved_rejected_receipt": (
            recovery_dir
            / "quarantined_cell"
            / f"R3_ROLLOUT_{EXPECTED_INIT_ID}_COMPLETE.json"
        ).relative_to(root).as_posix(),
        "pending_treatment_keys": 1,
        "preserved_accepted_treatment_keys": 79,
        "moves_completed_this_invocation": moves,
        "next_action": "run frozen collection commit 8ccecf8; it must launch only B0_fixed_conservative_assertive/init103",
    }
    atomic_json(marker_path, marker)
    return marker_path


def _resume_plan(root: Path) -> dict[str, Any] | None:
    marker = root / "R3_INTEGRITY_RECOVERY_PREPARED.json"
    if marker.is_file():
        return read_json(marker)
    plans = sorted((root / "_integrity_recovery").glob("*/recovery_plan.json"))
    if len(plans) > 1:
        raise RuntimeError("Multiple unfinished recovery plans exist")
    return read_json(plans[0]) if plans else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Quarantine the proven outlier and leave exactly its treatment key pending",
    )
    args = parser.parse_args()
    root = args.results_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)

    existing = _resume_plan(root)
    if existing is not None:
        plan = existing
    else:
        plan = build_recovery_plan(root)
    if not args.apply:
        print(json.dumps(plan, indent=2, sort_keys=True))
        print("READ-ONLY validation passed; rerun with --apply to prepare one-key recovery")
        return
    marker = apply_recovery(root, plan)
    print(json.dumps(read_json(marker), indent=2, sort_keys=True))
    print(f"Recovery preparation complete: {marker}")


if __name__ == "__main__":
    main()
