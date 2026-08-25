"""Fail-closed same-state shadow-policy command replay.

The factual CARLA policy remains the only source of actuation.  This module
evaluates the seven non-factual predictor/risk/authority branches through an
injected solver callback and reuses only the factual enabled branch.  The
complete authority bundle changes solver inputs (reference shaping,
linearisation and heading costs) and can bypass the solve, so enabled and
monitor-only branches are deliberately solved separately.  It therefore
produces eight compact rows from eight branch evaluations (one factual plus
seven shadow evaluations).

The module deliberately has no CARLA import.  A callback receives only a
frozen data snapshot and returns an SMPC debug payload; no ``VehicleControl``
object is accepted or returned at this boundary.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


SCHEMA_VERSION = "same_state_shadow_command_rows_v1"
PREDICTORS = ("B1", "P_star")
RISK_POLICIES = ("fixed_medium", "adaptive")
SUPERVISOR_MAPPINGS = ("monitor_only", "enabled")
AUTHORITY_CHANNELS = (
    "reference_shaping",
    "supervisor_forced_reference_linearization",
    "lane_entry_heading_cost",
    "rule_smpc_bypass",
    "post_solver_action_and_desired_speed",
    "release_recovery_state",
    "next_control_history",
)
EVENT_ANCHORS = (
    "first_valid_inactive",
    "activation_first",
    "sustained_active_after_3_updates",
    "release_first",
)


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _finite_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _dig(value: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            raise KeyError(".".join(path))
        current = current[key]
    return current


def _command_pair(value: Any, name: str) -> tuple[float, float]:
    if hasattr(value, "reshape") and hasattr(value, "tolist"):
        flattened = value.reshape(-1).tolist()
    elif isinstance(value, (list, tuple)):
        flattened = list(value)
        while len(flattened) == 1 and isinstance(flattened[0], (list, tuple)):
            flattened = list(flattened[0])
    else:
        raise ValueError(f"{name} must contain acceleration and steering")
    if len(flattened) != 2:
        raise ValueError(f"{name} must contain exactly two values")
    return (
        _finite_float(flattened[0], name + ".acceleration"),
        _finite_float(flattened[1], name + ".steering"),
    )


@dataclass(frozen=True)
class ShadowSolveRequest:
    """One non-factual predictor/risk solve on the frozen factual state."""

    predictor: str
    risk_policy: str
    supervisor_mapping: str
    state_key: str
    frozen_state: Mapping[str, Any]


class ShadowEligibilityTracker:
    """Protocol-v1 eligibility plus a pre-outcome event-anchor interface.

    ``every_planning_state`` is the only mode licensed by protocol v1.  Event
    anchors are exposed for a future amendment and require a non-empty
    amendment identifier.  Anchor selection uses request-state transitions
    only; command magnitudes and physical outcomes are never accepted.

    No historical actor state is buffered or replayed.  Every anchor is
    evaluated while its factual state is current, which avoids querying a
    subsequently advanced CARLA actor.  Structurally absent anchors are
    reported at completion and are never replaced by a nearby state.
    """

    def __init__(
        self,
        mode: str = "every_planning_state",
        *,
        sustained_updates: int = 3,
        protocol_amendment_id: Optional[str] = None,
    ) -> None:
        if mode not in {"every_planning_state", "event_anchors"}:
            raise ValueError(f"Unsupported shadow eligibility mode: {mode!r}")
        if mode == "event_anchors" and not str(protocol_amendment_id or "").strip():
            raise ValueError(
                "event_anchors changes frozen protocol v1 and requires a "
                "pre-outcome protocol_amendment_id"
            )
        if int(sustained_updates) < 1:
            raise ValueError("sustained_updates must be positive")
        self.mode = mode
        self.sustained_updates = int(sustained_updates)
        self.protocol_amendment_id = protocol_amendment_id
        self._previous_active = False
        self._active_updates = 0
        self._emitted: set[str] = set()

    @property
    def projected_controller_solve_multiplier(self) -> int:
        """One factual plus seven shadow branch evaluations per selected state."""

        return 8

    def select(
        self,
        *,
        supervisor_requested: bool,
        valid_prediction: bool,
        frozen_state: Mapping[str, Any],
    ) -> list[tuple[str, Mapping[str, Any]]]:
        snapshot = deepcopy(dict(frozen_state))
        if self.mode == "every_planning_state":
            return [("every_planning_state", snapshot)]

        active = bool(supervisor_requested)
        valid = bool(valid_prediction)
        selected: list[tuple[str, Mapping[str, Any]]] = []
        if not active:
            self._active_updates = 0
            if valid and "first_valid_inactive" not in self._emitted:
                selected.append(("first_valid_inactive", snapshot))
                self._emitted.add("first_valid_inactive")
            if (
                valid
                and self._previous_active
                and "release_first" not in self._emitted
            ):
                selected.append(("release_first", snapshot))
                self._emitted.add("release_first")
        else:
            if valid:
                self._active_updates = (
                    self._active_updates + 1 if self._previous_active else 1
                )
            else:
                # Protocol V2 defines selected anchors on valid planning
                # states. An invalid prediction is neither evaluated nor
                # allowed to advance the three-valid-update dwell counter.
                self._active_updates = 0
            if valid and not self._previous_active:
                if "activation_first" not in self._emitted:
                    selected.append(("activation_first", snapshot))
                    self._emitted.add("activation_first")
            if (
                valid
                and
                self._active_updates == self.sustained_updates
                and "sustained_active_after_3_updates" not in self._emitted
            ):
                selected.append(("sustained_active_after_3_updates", snapshot))
                self._emitted.add("sustained_active_after_3_updates")
        self._previous_active = active
        return selected

    def completion_receipt(self) -> dict[str, Any]:
        expected = set(EVENT_ANCHORS) if self.mode == "event_anchors" else set()
        return {
            "schema_version": "same_state_shadow_eligibility_receipt_v1",
            "mode": self.mode,
            "protocol_amendment_id": self.protocol_amendment_id,
            "emitted_anchors": sorted(self._emitted),
            "structurally_missing_anchors": sorted(expected - self._emitted),
            "missing_anchors_replaced": False,
            "selection_uses_command_magnitude": False,
            "selection_uses_physical_outcome": False,
            "historical_actor_state_buffered": False,
        }


class SameStateShadowRecorder:
    """Validate, evaluate and atomically append one eight-row state block."""

    BASE_COLUMNS = (
        "schema_version",
        "ego_init_id",
        "factual_rollout_id",
        "state_key",
        "event_anchor",
        "predictor",
        "risk_policy",
        "supervisor_mapping",
        "nominal_accel_mps2",
        "nominal_steer_rad",
        "nominal_desired_speed_mps",
        "post_accel_mps2",
        "post_steer_rad",
        "post_desired_speed_mps",
        "supervisor_any_requested",
        "shadow_actuated",
        "solver_attempted",
        "solver_status",
        "solver_accepted",
        "fallback_used",
        "solver_bypass_requested",
        "solver_bypass_effective",
        "solve_time_s",
        "risk_tightening",
        "risk_required_probability_mass",
        "factual_branch",
        "factual_command_parity",
        "factual_command_parity_basis",
        "frozen_state_sha256",
        "common_solve_id",
        "common_nominal_reused_across_mappings",
        "authority_mapping_recomputed_before_solver",
        "missing_fields",
    )
    CHANNEL_COLUMNS = tuple(
        f"{channel}_{suffix}"
        for channel in AUTHORITY_CHANNELS
        for suffix in ("candidate_computed", "requested", "applied")
    )
    COLUMNS = BASE_COLUMNS + CHANNEL_COLUMNS

    def __init__(
        self,
        *,
        protocol_path: Path,
        output_csv: Path,
        rejection_jsonl: Optional[Path] = None,
        eligibility: Optional[ShadowEligibilityTracker] = None,
        parity_tolerance: float = 1.0e-9,
    ) -> None:
        self.protocol_path = Path(protocol_path)
        self.output_csv = Path(output_csv)
        self.rejection_jsonl = (
            Path(rejection_jsonl)
            if rejection_jsonl is not None
            else self.output_csv.with_suffix(".rejections.jsonl")
        )
        self.eligibility_receipt_path = self.output_csv.with_suffix(
            ".eligibility.json"
        )
        self.parity_tolerance = _finite_float(parity_tolerance, "parity_tolerance")
        if self.parity_tolerance < 0.0:
            raise ValueError("parity_tolerance must be non-negative")
        self.protocol = self._load_and_validate_protocol()
        if eligibility is None:
            if self.protocol_schema_version.endswith("_v2"):
                eligibility = ShadowEligibilityTracker(
                    "event_anchors",
                    sustained_updates=3,
                    protocol_amendment_id=self.protocol_schema_version,
                )
            else:
                eligibility = ShadowEligibilityTracker()
        self.eligibility = eligibility
        schedule = self.protocol.get("eligibility_schedule")
        if schedule is not None:
            if self.eligibility.mode != "event_anchors":
                raise ValueError("Protocol v2 requires event-anchor eligibility")
            if tuple(schedule.get("event_anchors") or ()) != EVENT_ANCHORS:
                raise ValueError("Protocol v2 event-anchor contract mismatch")
            if self.eligibility.sustained_updates != 3:
                raise ValueError("Protocol v2 requires three active updates")

    def write_eligibility_receipt(self) -> dict[str, Any]:
        receipt = self.eligibility.completion_receipt()
        receipt.update(
            {
                "protocol_path": str(self.protocol_path),
                "protocol_sha256": _stable_hash(self.protocol),
                "output_csv": str(self.output_csv),
            }
        )
        self.eligibility_receipt_path.parent.mkdir(parents=True, exist_ok=True)
        self.eligibility_receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt

    def _load_and_validate_protocol(self) -> Mapping[str, Any]:
        payload = json.loads(self.protocol_path.read_text(encoding="utf-8"))
        self.protocol_schema_version = str(payload.get("schema_version", ""))
        protocol = payload.get("protocol")
        if payload.get("status") != "frozen_pre_outcome" or not isinstance(
            protocol, Mapping
        ):
            raise ValueError("Shadow protocol must be frozen_pre_outcome")
        if payload.get("protocol_sha256") != _stable_hash(protocol):
            raise ValueError("Shadow protocol stable hash mismatch")
        factorial = protocol.get("shadow_factorial_per_state") or {}
        if factorial.get("planned_shadow_branches") != 8:
            raise ValueError("Shadow protocol must require eight branches per state")
        if factorial.get("actuation_allowed") is not False:
            raise ValueError("Shadow protocol must prohibit actuation")
        if tuple(protocol.get("authority_channels") or ()) != AUTHORITY_CHANNELS:
            raise ValueError("Shadow protocol authority-channel contract mismatch")
        return protocol

    def _reject(self, *, state_key: str, reason: str, details: Any) -> None:
        self.rejection_jsonl.parent.mkdir(parents=True, exist_ok=True)
        receipt = {
            "schema_version": "same_state_shadow_rejection_v1",
            "state_key": state_key,
            "reason": reason,
            "details": details,
        }
        with self.rejection_jsonl.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, sort_keys=True, default=str) + "\n")

    @staticmethod
    def _extract_common(debug: Mapping[str, Any]) -> dict[str, Any]:
        nominal_u = _command_pair(
            _dig(debug, ("applied", "nominal_solver_u0")),
            "applied.nominal_solver_u0",
        )
        nominal_speed = _finite_float(
            _dig(debug, ("applied", "nominal_solver_v_des")),
            "applied.nominal_solver_v_des",
        )
        action = _dig(debug, ("applied", "post_solver_action_filter"))
        candidate_command = _dig(action, ("supervisor_candidate_command",))
        candidate_u = (
            _finite_float(candidate_command.get("a_des"), "candidate.a_des"),
            _finite_float(candidate_command.get("df_des"), "candidate.df_des"),
        )
        candidate_speed = _finite_float(
            candidate_command.get("v_des"), "candidate.v_des"
        )
        actual_u = _command_pair(
            _dig(debug, ("applied", "u0")), "applied.u0"
        )
        actual_speed = _finite_float(
            _dig(debug, ("applied", "v_des")), "applied.v_des"
        )
        manifest = _dig(
            debug,
            (
                "supervisor_behavioural_authority",
                "complete_candidate_channel_manifest",
                "channels",
            ),
        )
        if set(manifest) != set(AUTHORITY_CHANNELS):
            raise ValueError("Debug payload does not contain all seven authority channels")
        channels: dict[str, dict[str, bool]] = {}
        for channel in AUTHORITY_CHANNELS:
            value = manifest[channel]
            if not isinstance(value, Mapping):
                raise ValueError(f"Authority channel {channel} is not a mapping")
            if value.get("candidate_computed") is not True:
                raise ValueError(f"Authority channel {channel} candidate was not computed")
            channels[channel] = {
                "candidate_computed": True,
                "requested": value.get("requested") is True,
                "applied": value.get("applied") is True,
            }

        solver = debug.get("solver")
        if not isinstance(solver, Mapping):
            raise ValueError("Missing solver record")
        bypass = debug.get("solver_bypass") or {}
        bypass_requested = _bool(bypass.get("shadow_requested", False))
        bypass_effective = _bool(bypass.get("enabled", False))
        solver_bypassed = _bool(solver.get("bypassed", False))
        exception = solver.get("exception")
        optimal = solver.get("optimal") is True
        attempted = not solver_bypassed and exception is None
        accepted = bool(optimal and attempted)
        fallback = bool(attempted and not accepted)
        if exception is not None:
            status = "exception"
        elif solver_bypassed:
            status = "bypassed"
        elif accepted:
            status = "accepted"
        else:
            status = "fallback"
        solve_time = solver.get("solve_time")
        if solve_time is None and status == "exception":
            solve_time_value: Any = ""
        else:
            solve_time_value = _finite_float(solve_time, "solver.solve_time")

        risk = debug.get("risk") or {}
        tightening = risk.get("solver_current_tight", risk.get("applied_tight"))
        probability = risk.get(
            "solver_current_target_prob", risk.get("applied_target_prob")
        )
        return {
            "nominal_u": nominal_u,
            "nominal_speed": nominal_speed,
            "candidate_u": candidate_u,
            "candidate_speed": candidate_speed,
            "actual_u": actual_u,
            "actual_speed": actual_speed,
            "channels": channels,
            "solver_attempted": attempted,
            "solver_status": status,
            "solver_accepted": accepted,
            "fallback_used": fallback,
            "solver_bypass_requested": bypass_requested,
            "solver_bypass_effective": bypass_effective,
            "solve_time_s": solve_time_value,
            "risk_tightening": _finite_float(tightening, "risk.tightening"),
            "risk_required_probability_mass": _finite_float(
                probability, "risk.required_probability_mass"
            ),
        }

    def _row_for_branch(
        self,
        *,
        debug: Mapping[str, Any],
        predictor: str,
        risk_policy: str,
        supervisor_mapping: str,
        factual_predictor: str,
        factual_risk_policy: str,
        factual_debug: Mapping[str, Any],
        ego_init_id: int,
        factual_rollout_id: str,
        state_key: str,
        event_anchor: str,
        frozen_state_sha256: str,
    ) -> dict[str, Any]:
        common = self._extract_common(debug)
        factual_branch = (
            predictor == factual_predictor and risk_policy == factual_risk_policy
            and supervisor_mapping == "enabled"
        )
        actual_factual_u = _command_pair(
            _dig(factual_debug, ("applied", "u0")), "factual.applied.u0"
        )
        actual_factual_speed = _finite_float(
            _dig(factual_debug, ("applied", "v_des")), "factual.applied.v_des"
        )
        authority = _dig(debug, ("supervisor_behavioural_authority",))
        observed_mode = str(authority.get("mode", "")).strip().lower()
        expected_mode = "on" if supervisor_mapping == "enabled" else "off"
        if observed_mode != expected_mode:
            raise ValueError(
                f"Branch {predictor}/{risk_policy}/{supervisor_mapping} expected "
                f"authority mode {expected_mode!r}, observed {observed_mode!r}"
            )
        solve_id = _stable_hash(
            {
                "state_key": state_key,
                "predictor": predictor,
                "risk_policy": risk_policy,
                "supervisor_mapping": supervisor_mapping,
                "nominal_u": common["nominal_u"],
                "nominal_speed": common["nominal_speed"],
            }
        )
        post_u = common["actual_u"]
        post_speed = common["actual_speed"]
        if factual_branch:
            parity = max(
                abs(post_u[0] - actual_factual_u[0]),
                abs(post_u[1] - actual_factual_u[1]),
                abs(post_speed - actual_factual_speed),
            ) <= self.parity_tolerance
            parity_basis = "enabled_row_reuses_pre_shadow_factual_debug_command"
        else:
            parity = True
            parity_basis = "not_physically_factual_branch"
        row: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "ego_init_id": int(ego_init_id),
                "factual_rollout_id": str(factual_rollout_id),
                "state_key": state_key,
                "event_anchor": event_anchor,
                "predictor": predictor,
                "risk_policy": risk_policy,
                "supervisor_mapping": supervisor_mapping,
                "nominal_accel_mps2": common["nominal_u"][0],
                "nominal_steer_rad": common["nominal_u"][1],
                "nominal_desired_speed_mps": common["nominal_speed"],
                "post_accel_mps2": post_u[0],
                "post_steer_rad": post_u[1],
                "post_desired_speed_mps": post_speed,
                "supervisor_any_requested": any(
                    channel["requested"] for channel in common["channels"].values()
                ),
                "shadow_actuated": False,
                "solver_attempted": common["solver_attempted"],
                "solver_status": common["solver_status"],
                "solver_accepted": common["solver_accepted"],
                "fallback_used": common["fallback_used"],
                "solver_bypass_requested": common["solver_bypass_requested"],
                "solver_bypass_effective": common["solver_bypass_effective"],
                "solve_time_s": common["solve_time_s"],
                "risk_tightening": common["risk_tightening"],
                "risk_required_probability_mass": common[
                    "risk_required_probability_mass"
                ],
                "factual_branch": factual_branch,
                "factual_command_parity": parity,
                "factual_command_parity_basis": parity_basis,
                "frozen_state_sha256": frozen_state_sha256,
                "common_solve_id": solve_id,
                "common_nominal_reused_across_mappings": False,
                "authority_mapping_recomputed_before_solver": True,
                "missing_fields": "",
            }
        for channel, values in common["channels"].items():
            row[f"{channel}_candidate_computed"] = True
            row[f"{channel}_requested"] = values["requested"]
            row[f"{channel}_applied"] = values["applied"]
            expected_applied = bool(
                supervisor_mapping == "enabled" and values["requested"]
            )
            if values["applied"] != expected_applied:
                raise ValueError(
                    f"Authority application mismatch for {channel} in "
                    f"{supervisor_mapping}: requested={values['requested']} "
                    f"applied={values['applied']}"
                )
        return row

    def _append_state_rows(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        existing = self.output_csv.read_text(encoding="utf-8") if self.output_csv.exists() else ""
        temporary = self.output_csv.with_suffix(self.output_csv.suffix + ".tmp")
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            if existing:
                handle.write(existing)
                if not existing.endswith("\n"):
                    handle.write("\n")
                writer = csv.DictWriter(handle, fieldnames=self.COLUMNS)
            else:
                writer = csv.DictWriter(handle, fieldnames=self.COLUMNS)
                writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.output_csv)

    def evaluate_and_record(
        self,
        *,
        ego_init_id: int,
        factual_rollout_id: str,
        state_key: str,
        factual_predictor: str,
        factual_risk_policy: str,
        factual_debug: Mapping[str, Any],
        frozen_state: Mapping[str, Any],
        solve_shadow: Callable[[ShadowSolveRequest], Mapping[str, Any]],
        event_anchor: str = "every_planning_state",
    ) -> list[dict[str, Any]]:
        if factual_predictor not in PREDICTORS:
            raise ValueError(f"Unknown factual predictor {factual_predictor!r}")
        if factual_risk_policy not in RISK_POLICIES:
            raise ValueError(f"Unknown factual risk policy {factual_risk_policy!r}")
        if event_anchor not in {"every_planning_state", *EVENT_ANCHORS}:
            raise ValueError(f"Unknown event anchor {event_anchor!r}")
        frozen_hash = _stable_hash(frozen_state)
        debug_by_branch: dict[tuple[str, str, str], Mapping[str, Any]] = {
            (factual_predictor, factual_risk_policy, "enabled"): factual_debug
        }
        try:
            for predictor in PREDICTORS:
                for risk_policy in RISK_POLICIES:
                    for supervisor_mapping in SUPERVISOR_MAPPINGS:
                        key = (predictor, risk_policy, supervisor_mapping)
                        if key in debug_by_branch:
                            continue
                        request = ShadowSolveRequest(
                            predictor=predictor,
                            risk_policy=risk_policy,
                            supervisor_mapping=supervisor_mapping,
                            state_key=state_key,
                            frozen_state=deepcopy(dict(frozen_state)),
                        )
                        result = solve_shadow(request)
                        if not isinstance(result, Mapping):
                            raise ValueError(
                                "Shadow solve callback must return a debug mapping only; "
                                "VehicleControl/tuple results are prohibited"
                            )
                        if result.get("shadow_actuated") is True:
                            raise ValueError("Shadow solve reported an actuation attempt")
                        debug_by_branch[key] = result.get("debug_payload", result)

            rows: list[dict[str, Any]] = []
            for predictor in PREDICTORS:
                for risk_policy in RISK_POLICIES:
                    for supervisor_mapping in SUPERVISOR_MAPPINGS:
                        rows.append(
                            self._row_for_branch(
                            debug=debug_by_branch[
                                (predictor, risk_policy, supervisor_mapping)
                            ],
                            predictor=predictor,
                            risk_policy=risk_policy,
                            supervisor_mapping=supervisor_mapping,
                            factual_predictor=factual_predictor,
                            factual_risk_policy=factual_risk_policy,
                            factual_debug=factual_debug,
                            ego_init_id=ego_init_id,
                            factual_rollout_id=factual_rollout_id,
                            state_key=state_key,
                            event_anchor=event_anchor,
                            frozen_state_sha256=frozen_hash,
                            )
                    )
            if len(rows) != 8:
                raise ValueError(f"Expected 8 rows, produced {len(rows)}")
            if any(_bool(row["shadow_actuated"]) for row in rows):
                raise ValueError("Shadow actuation invariant failed")
            expected = {
                (predictor, risk, mapping)
                for predictor in PREDICTORS
                for risk in RISK_POLICIES
                for mapping in SUPERVISOR_MAPPINGS
            }
            observed = {
                (row["predictor"], row["risk_policy"], row["supervisor_mapping"])
                for row in rows
            }
            if observed != expected:
                raise ValueError("Incomplete same-state shadow factorial")
            factual_rows = [row for row in rows if row["factual_branch"]]
            if len(factual_rows) != 1 or not all(
                row["factual_command_parity"] for row in factual_rows
            ):
                raise ValueError("Factual branch command parity failed")
            self._append_state_rows(rows)
            return rows
        except Exception as exc:
            self._reject(
                state_key=state_key,
                reason="shadow_state_rejected",
                details={"error": repr(exc), "frozen_state_sha256": frozen_hash},
            )
            raise


class SMPCAgentShadowBank:
    """Concrete callback routing frozen inputs to seven shadow-only agents.

    Prediction providers are keyed by predictor label and receive the frozen
    ``prediction_replay_input`` mapping.  Agents are keyed by the complete
    predictor/risk/mapping tuple and must implement
    ``run_same_state_shadow_step``.  Construction of heavyweight MultiPath and
    SMPC objects remains with the experiment launcher, where GPU placement and
    model asset manifests are already controlled.
    """

    def __init__(
        self,
        *,
        factual_branch: tuple[str, str, str],
        agents: Mapping[tuple[str, str, str], Any],
        prediction_providers: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]],
    ) -> None:
        expected = {
            (predictor, risk, mapping)
            for predictor in PREDICTORS
            for risk in RISK_POLICIES
            for mapping in SUPERVISOR_MAPPINGS
        }
        if factual_branch not in expected or factual_branch[2] != "enabled":
            raise ValueError("factual_branch must be one enabled factorial branch")
        if set(agents) != expected - {factual_branch}:
            raise ValueError("Shadow bank must contain exactly the seven non-factual agents")
        if set(prediction_providers) != set(PREDICTORS):
            raise ValueError("Shadow bank requires B1 and P_star prediction providers")
        self.factual_branch = factual_branch
        self.agents = dict(agents)
        self.prediction_providers = dict(prediction_providers)

    def __call__(self, request: ShadowSolveRequest) -> Mapping[str, Any]:
        key = (
            request.predictor,
            request.risk_policy,
            request.supervisor_mapping,
        )
        if key == self.factual_branch or key not in self.agents:
            raise ValueError(f"Invalid non-factual shadow request: {key}")
        replay_input = request.frozen_state.get("prediction_replay_input")
        if not isinstance(replay_input, Mapping):
            raise ValueError("Frozen state has no prediction_replay_input")
        pred_dict = self.prediction_providers[request.predictor](replay_input)
        if not isinstance(pred_dict, Mapping):
            raise ValueError("Prediction provider must return a pred_dict mapping")
        smpc_snapshot = request.frozen_state.get("smpc_state")
        if not isinstance(smpc_snapshot, Mapping):
            raise ValueError("Frozen state has no smpc_state snapshot")
        return self.agents[key].run_same_state_shadow_step(
            pred_dict=pred_dict,
            snapshot=smpc_snapshot,
            branch_identity={
                "predictor": request.predictor,
                "risk_policy": request.risk_policy,
                "supervisor_mapping": request.supervisor_mapping,
            },
        )


__all__ = [
    "AUTHORITY_CHANNELS",
    "EVENT_ANCHORS",
    "PREDICTORS",
    "RISK_POLICIES",
    "SUPERVISOR_MAPPINGS",
    "SameStateShadowRecorder",
    "SMPCAgentShadowBank",
    "ShadowEligibilityTracker",
    "ShadowSolveRequest",
]
