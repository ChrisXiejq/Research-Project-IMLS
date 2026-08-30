from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.carla.policies.same_state_shadow_replay import (
    AUTHORITY_CHANNELS,
    SameStateShadowRecorder,
    SMPCAgentShadowBank,
    ShadowSolveRequest,
    ShadowEligibilityTracker,
)
from core.scripts.models.analyze_shadow_command_transmission import (
    _load_rows,
    _state_contrasts,
)


ROOT = Path(__file__).resolve().parents[4]
PROTOCOL = (
    ROOT
    / "docs/paper/generated/supervisor_masking_v2/protocol/"
    / "SAME_STATE_SHADOW_PROTOCOL_V2.json"
)
PROTOCOL_V1 = PROTOCOL.with_name("SAME_STATE_SHADOW_PROTOCOL.json")


def debug_payload(
    *,
    mapping: str,
    nominal_accel: float = 1.0,
    candidate_accel: float = -1.0,
    requested_channels=(),
    optimal: bool = True,
    bypass: bool = False,
    omit: str | None = None,
):
    requested = set(requested_channels)
    enabled = mapping == "enabled"
    actual_accel = candidate_accel if enabled else nominal_accel
    channels = {
        channel: {
            "candidate_computed": True,
            "requested": channel in requested,
            "applied": enabled and channel in requested,
            "authority_assignment_consistent": True,
            "factual_neutral_when_off": True,
        }
        for channel in AUTHORITY_CHANNELS
    }
    payload = {
        "step": 4,
        "risk": {
            "solver_current_tight": 2.0,
            "solver_current_target_prob": 0.9,
        },
        "solver": {
            "optimal": optimal,
            "solve_time": 0.0 if bypass else 0.01,
            "bypassed": bypass,
        },
        "solver_bypass": {
            "shadow_requested": "rule_smpc_bypass" in requested,
            "enabled": bool(enabled and bypass),
        },
        "supervisor_behavioural_authority": {
            "mode": "on" if enabled else "off",
            "complete_candidate_channel_manifest": {"channels": channels},
        },
        "applied": {
            "nominal_solver_u0": [nominal_accel, 0.05],
            "nominal_solver_v_des": 4.0,
            "u0": [actual_accel, 0.10 if enabled else 0.05],
            "v_des": 1.0 if enabled else 4.0,
            "post_solver_action_filter": {
                "supervisor_candidate_command": {
                    "a_des": candidate_accel,
                    "df_des": 0.10,
                    "v_des": 1.0,
                }
            },
        },
    }
    if omit == "candidate":
        del payload["applied"]["post_solver_action_filter"]
    elif omit == "solver":
        del payload["solver"]
    return payload


class SameStateShadowReplayTests(unittest.TestCase):
    def _recorder(self, directory: str):
        return SameStateShadowRecorder(
            protocol_path=PROTOCOL,
            output_csv=Path(directory) / "shadow.csv",
        )

    def test_v2_auto_selects_frozen_event_schedule_and_v1_remains_available(self):
        with tempfile.TemporaryDirectory() as directory:
            v2 = self._recorder(directory)
            self.assertEqual(v2.eligibility.mode, "event_anchors")
            self.assertEqual(v2.eligibility.sustained_updates, 3)
            v1 = SameStateShadowRecorder(
                protocol_path=PROTOCOL_V1,
                output_csv=Path(directory) / "v1.csv",
            )
            self.assertEqual(v1.eligibility.mode, "every_planning_state")

    def test_concrete_shadow_bank_routes_frozen_inputs_without_control_interface(self):
        factual = ("B1", "fixed_medium", "enabled")
        expected = {
            (predictor, risk, mapping)
            for predictor in ("B1", "P_star")
            for risk in ("fixed_medium", "adaptive")
            for mapping in ("monitor_only", "enabled")
        } - {factual}

        class Agent:
            def __init__(self, identity):
                self.identity = identity
                self.calls = 0

            def run_same_state_shadow_step(self, **kwargs):
                self.calls += 1
                self.asserted_snapshot = kwargs["snapshot"]
                return {
                    "debug_payload": {"identity": self.identity},
                    "shadow_actuated": False,
                    "actuation_interface_exposed": False,
                }

        agents = {identity: Agent(identity) for identity in expected}
        bank = SMPCAgentShadowBank(
            factual_branch=factual,
            agents=agents,
            prediction_providers={
                "B1": lambda value: {"source": "B1", "frozen": value},
                "P_star": lambda value: {"source": "P_star", "frozen": value},
            },
        )
        request = ShadowSolveRequest(
            predictor="P_star",
            risk_policy="adaptive",
            supervisor_mapping="monitor_only",
            state_key="r:1",
            frozen_state={
                "prediction_replay_input": {"raster": "frozen"},
                "smpc_state": {"schema_version": "snapshot"},
            },
        )
        result = bank(request)
        self.assertFalse(result["shadow_actuated"])
        self.assertEqual(agents[("P_star", "adaptive", "monitor_only")].calls, 1)
        self.assertEqual(sum(agent.calls for agent in agents.values()), 1)

    def test_invokes_seven_shadow_branches_and_never_exports_actuation(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = self._recorder(directory)
            calls = []
            active = {
                "reference_shaping",
                "supervisor_forced_reference_linearization",
                "lane_entry_heading_cost",
                "post_solver_action_and_desired_speed",
                "release_recovery_state",
                "next_control_history",
            }
            factual = debug_payload(mapping="enabled", requested_channels=active)

            def solve(request):
                calls.append(
                    (request.predictor, request.risk_policy, request.supervisor_mapping)
                )
                self.assertNotIn("vehicle_actor", request.frozen_state)
                return {
                    "debug_payload": debug_payload(
                        mapping=request.supervisor_mapping,
                        nominal_accel=(
                            1.0 if request.predictor == "B1" else 0.4
                        ),
                        candidate_accel=-1.0,
                        requested_channels=active,
                    ),
                    "shadow_actuated": False,
                    "actuation_interface_exposed": False,
                }

            rows = recorder.evaluate_and_record(
                ego_init_id=116,
                factual_rollout_id="rollout_116",
                state_key="rollout_116:step_000004",
                factual_predictor="B1",
                factual_risk_policy="fixed_medium",
                factual_debug=factual,
                frozen_state={"actor_states": {}, "smpc_state": {"time": 4}},
                solve_shadow=solve,
            )

            self.assertEqual(len(calls), 7)
            self.assertEqual(len(set(calls)), 7)
            self.assertEqual(len(rows), 8)
            self.assertFalse(any(row["shadow_actuated"] for row in rows))
            self.assertEqual(sum(row["factual_branch"] for row in rows), 1)
            self.assertTrue(
                next(row for row in rows if row["factual_branch"])[
                    "factual_command_parity"
                ]
            )
            self.assertTrue(all(row["authority_mapping_recomputed_before_solver"] for row in rows))
            for row in rows:
                for channel in AUTHORITY_CHANNELS:
                    self.assertIn(f"{channel}_candidate_computed", row)
                    self.assertIn(f"{channel}_requested", row)
                    self.assertIn(f"{channel}_applied", row)
                    self.assertEqual(
                        row[f"{channel}_applied"],
                        row["supervisor_mapping"] == "enabled"
                        and row[f"{channel}_requested"],
                    )

            loaded = _load_rows(recorder.output_csv)
            contrasts = _state_contrasts(loaded)
            self.assertEqual(len(contrasts), 4)

    def test_inactive_supervision_keeps_all_channels_computed_but_unrequested(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = self._recorder(directory)
            factual = debug_payload(mapping="enabled")
            rows = recorder.evaluate_and_record(
                ego_init_id=116,
                factual_rollout_id="r",
                state_key="r:0",
                factual_predictor="B1",
                factual_risk_policy="fixed_medium",
                factual_debug=factual,
                frozen_state={"step": 0},
                solve_shadow=lambda request: debug_payload(
                    mapping=request.supervisor_mapping
                ),
            )
            self.assertTrue(all(not row["supervisor_any_requested"] for row in rows))
            self.assertTrue(all(
                row[f"{channel}_candidate_computed"]
                for row in rows
                for channel in AUTHORITY_CHANNELS
            ))

    def test_reference_shaping_and_post_action_replacement_are_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = self._recorder(directory)
            requested = {
                "reference_shaping",
                "post_solver_action_and_desired_speed",
            }
            rows = recorder.evaluate_and_record(
                ego_init_id=116,
                factual_rollout_id="r",
                state_key="r:1",
                factual_predictor="B1",
                factual_risk_policy="fixed_medium",
                factual_debug=debug_payload(
                    mapping="enabled", requested_channels=requested
                ),
                frozen_state={"step": 1},
                solve_shadow=lambda request: debug_payload(
                    mapping=request.supervisor_mapping,
                    requested_channels=requested,
                ),
            )
            enabled = next(
                row
                for row in rows
                if row["predictor"] == "P_star"
                and row["risk_policy"] == "adaptive"
                and row["supervisor_mapping"] == "enabled"
            )
            monitor = next(
                row
                for row in rows
                if row["predictor"] == "P_star"
                and row["risk_policy"] == "adaptive"
                and row["supervisor_mapping"] == "monitor_only"
            )
            self.assertTrue(enabled["reference_shaping_applied"])
            self.assertFalse(monitor["reference_shaping_applied"])
            self.assertEqual(enabled["post_accel_mps2"], -1.0)
            self.assertEqual(monitor["post_accel_mps2"], 1.0)

    def test_bypass_and_solver_failure_paths_are_reconciled(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = self._recorder(directory)
            requested = {"rule_smpc_bypass"}

            def solve(request):
                if request.predictor == "P_star" and request.risk_policy == "adaptive":
                    return debug_payload(
                        mapping=request.supervisor_mapping,
                        requested_channels=requested,
                        bypass=request.supervisor_mapping == "enabled",
                    )
                return debug_payload(
                    mapping=request.supervisor_mapping,
                    requested_channels=requested,
                    optimal=False,
                )

            rows = recorder.evaluate_and_record(
                ego_init_id=116,
                factual_rollout_id="r",
                state_key="r:2",
                factual_predictor="B1",
                factual_risk_policy="fixed_medium",
                factual_debug=debug_payload(
                    mapping="enabled", requested_channels=requested, bypass=True
                ),
                frozen_state={"step": 2},
                solve_shadow=solve,
            )
            self.assertTrue(any(row["solver_status"] == "bypassed" for row in rows))
            self.assertTrue(any(row["fallback_used"] for row in rows))
            self.assertTrue(all(
                not row["solver_attempted"]
                for row in rows
                if row["solver_status"] == "bypassed"
            ))

    def test_missing_field_fails_closed_and_writes_rejection_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = self._recorder(directory)
            with self.assertRaises((KeyError, ValueError)):
                recorder.evaluate_and_record(
                    ego_init_id=116,
                    factual_rollout_id="r",
                    state_key="r:3",
                    factual_predictor="B1",
                    factual_risk_policy="fixed_medium",
                    factual_debug=debug_payload(mapping="enabled", omit="candidate"),
                    frozen_state={"step": 3},
                    solve_shadow=lambda request: debug_payload(
                        mapping=request.supervisor_mapping
                    ),
                )
            receipts = recorder.rejection_jsonl.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(receipts), 1)
            self.assertEqual(json.loads(receipts[0])["reason"], "shadow_state_rejected")
            self.assertFalse(recorder.output_csv.exists())

    def test_actuation_attestation_violation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = self._recorder(directory)
            with self.assertRaisesRegex(ValueError, "actuation"):
                recorder.evaluate_and_record(
                    ego_init_id=116,
                    factual_rollout_id="r",
                    state_key="r:4",
                    factual_predictor="B1",
                    factual_risk_policy="fixed_medium",
                    factual_debug=debug_payload(mapping="enabled"),
                    frozen_state={"step": 4},
                    solve_shadow=lambda request: {
                        "debug_payload": debug_payload(
                            mapping=request.supervisor_mapping
                        ),
                        "shadow_actuated": True,
                    },
                )


class EligibilityTests(unittest.TestCase):
    def test_v1_default_selects_every_planning_state(self):
        tracker = ShadowEligibilityTracker()
        self.assertEqual(tracker.projected_controller_solve_multiplier, 8)
        for active in (False, True, False):
            selected = tracker.select(
                supervisor_requested=active,
                valid_prediction=True,
                frozen_state={"active": active},
            )
            self.assertEqual(selected[0][0], "every_planning_state")

    def test_event_anchors_are_structural_and_never_replaced(self):
        tracker = ShadowEligibilityTracker(
            "event_anchors",
            sustained_updates=3,
            protocol_amendment_id="protocol_v2_pre_outcome",
        )
        sequence = [
            (False, False),
            (False, True),
            (True, True),
            (True, True),
            (True, True),
            (False, True),
        ]
        names = []
        for step, (active, valid) in enumerate(sequence):
            names.extend(
                name
                for name, _ in tracker.select(
                    supervisor_requested=active,
                    valid_prediction=valid,
                    frozen_state={"step": step},
                )
            )
        self.assertEqual(
            names,
            [
                "first_valid_inactive",
                "activation_first",
                "sustained_active_after_3_updates",
                "release_first",
            ],
        )
        receipt = tracker.completion_receipt()
        self.assertEqual(receipt["structurally_missing_anchors"], [])
        self.assertFalse(receipt["missing_anchors_replaced"])
        self.assertFalse(receipt["selection_uses_command_magnitude"])
        self.assertFalse(receipt["historical_actor_state_buffered"])

    def test_event_anchors_require_pre_outcome_amendment(self):
        with self.assertRaisesRegex(ValueError, "protocol_amendment_id"):
            ShadowEligibilityTracker("event_anchors")

    def test_invalid_active_states_are_not_selected_or_counted(self):
        tracker = ShadowEligibilityTracker(
            "event_anchors",
            sustained_updates=3,
            protocol_amendment_id="protocol_v2_pre_outcome",
        )
        sequence = [
            (False, True),
            (True, False),
            (True, True),
            (True, True),
            (True, True),
            (False, False),
        ]
        names = []
        for step, (active, valid) in enumerate(sequence):
            names.extend(
                name
                for name, _ in tracker.select(
                    supervisor_requested=active,
                    valid_prediction=valid,
                    frozen_state={"step": step},
                )
            )
        self.assertEqual(
            names,
            ["first_valid_inactive", "sustained_active_after_3_updates"],
        )
        self.assertEqual(
            tracker.completion_receipt()["structurally_missing_anchors"],
            ["activation_first", "release_first"],
        )


class IntegrationSourceContractTests(unittest.TestCase):
    def test_runner_records_before_factual_apply_control(self):
        source = (
            ROOT / "core/scripts/carla/scenarios/run_intersection_scenario.py"
        ).read_text(encoding="utf-8")
        record = source.index("self._record_same_state_shadow_context(")
        apply_control = source.index("act.apply_control(control)", record)
        self.assertLess(record, apply_control)

    def test_smpc_shadow_wrapper_discards_vehicle_control(self):
        source = (
            ROOT / "core/scripts/carla/policies/smpc_agent.py"
        ).read_text(encoding="utf-8")
        start = source.index("def run_same_state_shadow_step")
        end = source.index("def get_last_debug_payload", start)
        method = source[start:end]
        self.assertIn("self.run_step", method)
        self.assertIn('"shadow_actuated": False', method)
        self.assertIn('"actuation_interface_exposed": False', method)
        self.assertNotIn("apply_control", method)


if __name__ == "__main__":
    unittest.main()
