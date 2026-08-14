import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODELS_DIR = Path(__file__).resolve().parents[1]
if str(MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(MODELS_DIR))

from analyze_supervisor_feedback_behaviour import (  # noqa: E402
    analyze_formal,
    analyze_rollout,
    analyze_rollout_rows,
    first_sustained_index,
)


def debug_row(step, speed, *, active=False, phase="free_drive", distance=12.0, route_s=4.0, **extra):
    supervisor = {
        "active": int(active),
        "phase": phase,
        "ego_distance_to_conflict": distance,
        "ego_route_s": route_s,
        "stop_clearance": 4.0,
        "ego_distance_to_stop": distance - 4.0,
        **extra,
    }
    return {
        "step": step,
        "vehicle_state": {"speed": speed},
        "yield_stop_supervisor": supervisor,
    }


class SupervisorFeedbackBehaviourTests(unittest.TestCase):
    def test_first_sustained_index_rejects_one_step_noise(self):
        rows = [{"value": value} for value in [1, 0, 1, 0, 0, 0]]
        self.assertEqual(
            first_sustained_index(rows, lambda row: row["value"] == 0, consecutive=3),
            3,
        )

    def test_rollout_event_chain_and_metrics(self):
        rows = [
            debug_row(0, 6.0),
            debug_row(1, 5.0, active=True, phase="cautious_approach_observed_target", distance=10.0, route_s=6.0),
            debug_row(2, 3.0, active=True, phase="approach_yield_line", distance=8.0, route_s=8.0),
            debug_row(3, 0.10, active=True, phase="hold_yield_line", distance=4.5, route_s=11.5),
            debug_row(4, 0.05, active=True, phase="hold_yield_line", distance=4.5, route_s=11.5),
            debug_row(5, 0.02, active=True, phase="hold_yield_line", distance=4.5, route_s=11.5),
            debug_row(6, 0.02, phase="released_recovery", distance=4.5, route_s=11.5, target_nominally_cleared_conflict=1, raw_reduced_clear_path_release=1),
            debug_row(7, 0.9, phase="released_recovery", distance=4.4, route_s=11.6, target_nominally_cleared_conflict=1, target_cleared_conflict=1),
            debug_row(8, 1.0, phase="released_recovery", distance=4.3, route_s=11.7),
            debug_row(9, 1.1, phase="released_recovery", distance=4.2, route_s=11.8),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "smpc_debug_steps.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = analyze_rollout(
                path,
                fps=20.0,
                stop_speed_mps=0.15,
                resume_speed_mps=0.8,
                consecutive_steps=3,
            )
        self.assertEqual(result["yield_entry_step"], 1)
        self.assertEqual(result["first_sustained_stop_step"], 3)
        self.assertEqual(result["path_release_step"], 6)
        self.assertEqual(result["target_nominal_clear_step"], 6)
        self.assertEqual(result["target_buffered_clear_step"], 7)
        self.assertEqual(result["sustained_resume_step"], 7)
        self.assertAlmostEqual(result["first_stop_distance_to_conflict_m"], 4.5)
        self.assertAlmostEqual(result["first_stop_distance_to_designed_stop_m"], 0.5)
        self.assertAlmostEqual(result["cautious_approach_progress_m"], 5.5)
        self.assertAlmostEqual(result["pre_clearance_stopped_duration_s"], 0.15)
        self.assertAlmostEqual(result["nominal_clear_to_release_latency_s"], 0.0)
        self.assertAlmostEqual(result["buffered_clear_to_resume_latency_s"], 0.0)
        self.assertAlmostEqual(result["release_to_resume_latency_s"], 0.05)

    def test_terminal_stop_after_release_is_not_misclassified_as_yield_stop(self):
        rows = [
            debug_row(0, 5.0),
            debug_row(
                1,
                3.0,
                active=True,
                phase="cautious_approach_observed_target",
                distance=9.0,
                route_s=5.0,
            ),
            debug_row(
                2,
                2.0,
                phase="released_recovery",
                distance=4.5,
                route_s=9.5,
                target_nominally_cleared_conflict=1,
                target_cleared_conflict=1,
                raw_reduced_clear_path_release=1,
            ),
            debug_row(3, 1.0, phase="free_drive", distance=3.0, route_s=11.0),
            # This is a later goal stop, outside the give-way episode.
            debug_row(4, 0.1, phase="free_drive", distance=-10.0, route_s=24.0),
            debug_row(5, 0.1, phase="free_drive", distance=-10.0, route_s=24.0),
            debug_row(6, 0.1, phase="free_drive", distance=-10.0, route_s=24.0),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "smpc_debug_steps.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            result = analyze_rollout(
                path,
                fps=20.0,
                stop_speed_mps=0.15,
                resume_speed_mps=0.8,
                consecutive_steps=3,
            )
        self.assertFalse(result["sustained_stop_observed"])
        self.assertIsNone(result["first_sustained_stop_step"])

    def test_terminal_stop_without_yield_entry_is_not_a_give_way_stop(self):
        rows = [
            debug_row(step, speed, active=False, phase="free_drive")
            for step, speed in enumerate((4.0, 3.0, 0.05, 0.04, 0.03))
        ]
        result = analyze_rollout_rows(
            rows,
            fps=20.0,
            stop_speed_mps=0.15,
            resume_speed_mps=0.8,
            consecutive_steps=3,
        )
        self.assertFalse(result["yield_entry_observed"])
        self.assertFalse(result["sustained_stop_observed"])
        self.assertIsNone(result["first_sustained_stop_step"])
        self.assertIsNone(result["first_stop_distance_to_conflict_m"])

    def test_terminal_stop_with_entry_but_missing_release_is_censored(self):
        rows = [
            debug_row(0, 5.0),
            debug_row(
                1,
                3.0,
                active=True,
                phase="cautious_approach_observed_target",
                distance=9.0,
                route_s=5.0,
            ),
            debug_row(2, 2.0, active=True, phase="approach_yield_line", distance=6.0, route_s=8.0),
            debug_row(3, 1.0, active=True, phase="approach_yield_line", distance=4.5, route_s=9.5),
            # No path-release event is observed.  These final rows therefore
            # cannot be attributed to the registered give-way stop window.
            debug_row(4, 0.1, phase="free_drive", distance=-10.0, route_s=24.0),
            debug_row(5, 0.1, phase="free_drive", distance=-10.0, route_s=24.0),
            debug_row(6, 0.1, phase="free_drive", distance=-10.0, route_s=24.0),
        ]
        result = analyze_rollout_rows(
            rows,
            fps=20.0,
            stop_speed_mps=0.15,
            resume_speed_mps=0.8,
            consecutive_steps=3,
        )
        self.assertTrue(result["yield_entry_observed"])
        self.assertFalse(result["path_release_observed"])
        self.assertEqual(result["stop_window_status"], "censored_missing_release")
        self.assertTrue(result["stop_window_censored_missing_release"])
        self.assertFalse(result["sustained_stop_observed"])
        self.assertIsNone(result["first_sustained_stop_step"])
        self.assertIsNone(result["cautious_approach_progress_m"])
        self.assertIsNone(result["pre_clearance_stopped_duration_s"])

    def test_formal_analysis_hashes_and_excludes_attempt_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / "results"
            evaluations = []
            for predictor in ("B0", "B1"):
                for policy in ("adaptive", "fixed_aggressive", "fixed_medium", "fixed_conservative"):
                    for style in ("assertive", "reactive"):
                        cell_id = f"{predictor}_{policy}_{style}"
                        audit_rollouts = []
                        for init_id in range(101, 106):
                            scenario = f"scenario_uk_give_way_ego_init_{init_id}_smpc_" + (
                                "var_risk" if policy == "adaptive" else "fixed_risk"
                            )
                            path = results / cell_id / scenario / "smpc_debug_steps.jsonl"
                            path.parent.mkdir(parents=True)
                            rows = [
                                debug_row(0, 5.0),
                                debug_row(1, 4.0, active=True, phase="cautious_approach_observed_target", distance=9.0, route_s=5.0),
                                debug_row(2, 0.1, active=True, phase="hold_yield_line", distance=4.5, route_s=9.5),
                                debug_row(3, 0.1, active=True, phase="hold_yield_line", distance=4.5, route_s=9.5),
                                debug_row(4, 0.1, active=True, phase="hold_yield_line", distance=4.5, route_s=9.5),
                                debug_row(5, 0.1, phase="released_recovery", distance=4.5, route_s=9.5, target_nominally_cleared_conflict=1, raw_reduced_clear_path_release=1),
                                debug_row(6, 0.9, phase="released_recovery", distance=4.4, route_s=9.6, target_cleared_conflict=1),
                                debug_row(7, 0.9, phase="released_recovery", distance=4.3, route_s=9.7),
                                debug_row(8, 0.9, phase="released_recovery", distance=4.2, route_s=9.8),
                            ]
                            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
                            digest = hashlib.sha256(path.read_bytes()).hexdigest()
                            audit_rollouts.append({"scenario": scenario, "artifacts": {"debug_sha256": digest}})
                            attempt = results / cell_id / "_attempts" / f"init_{init_id}" / scenario / "smpc_debug_steps.jsonl"
                            attempt.parent.mkdir(parents=True)
                            attempt.write_text("{}\n", encoding="utf-8")
                        evaluations.append({"cell_id": cell_id, "rollouts": audit_rollouts})
            audit = root / "matrix.json"
            audit.write_text(json.dumps({"integrity_status": "pass", "evaluations": evaluations}), encoding="utf-8")
            output = root / "output"
            summary = analyze_formal(
                results,
                audit,
                output,
                fps=20.0,
                stop_speed_mps=0.15,
                resume_speed_mps=0.8,
                consecutive_steps=3,
                expected_rollouts=80,
            )
            self.assertEqual(summary["observed_rollouts"], 80)
            self.assertEqual(summary["formal_cells"], 16)
            self.assertEqual(summary["complete_event_chain_rollouts"], 80)
            self.assertTrue((output / "SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json").is_file())
            self.assertTrue((output / "behaviour_policy_cluster_macro.csv").is_file())
            sensitivity = (output / "behaviour_threshold_sensitivity.csv").read_text(
                encoding="utf-8"
            )
            self.assertEqual(len(sensitivity.splitlines()), 109)
            contract = json.loads(
                (output / "behaviour_analysis_contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(contract["baseline_definition"]["stop_speed_mps"], 0.15)
            self.assertEqual(contract["threshold_sensitivity_grid"]["definitions"], 27)
            self.assertEqual(contract["threshold_sensitivity_grid"]["rows"], 108)
            receipt = json.loads(
                (output / "SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("behaviour_analysis_contract.json", receipt["artifacts"])
            self.assertIn("behaviour_threshold_sensitivity.csv", receipt["artifacts"])
            self.assertIn(
                "core/scripts/models/analyze_supervisor_feedback_behaviour.py",
                receipt["source_sha256"],
            )
            self.assertIn(
                "core/scripts/models/run_supervisor_feedback_r3_offline_audits.sh",
                receipt["source_sha256"],
            )
            paired = (output / "behaviour_policy_paired_contrasts.csv").read_text(
                encoding="utf-8"
            )
            self.assertEqual(len(paired.splitlines()), 22)
            self.assertIn("adaptive_minus_fixed_medium", paired)
            self.assertIn("pre_clearance_stopped_duration_s", paired)
            self.assertIn(
                "Post-hoc corrected-R3 approach",
                (output / "behaviour_approach_stop.tex").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Designed clearance",
                (output / "behaviour_approach_stop.tex").read_text(encoding="utf-8"),
            )
            approach_tex = (output / "behaviour_approach_stop.tex").read_text(
                encoding="utf-8"
            )
            self.assertIn("not bumper clearance", approach_tex)
            self.assertIn(
                r"s_{\mathrm{conflict}}-s_{\mathrm{ego}}", approach_tex
            )
            self.assertIn(
                "positive means the actor/reference point stopped upstream",
                approach_tex,
            )
            paired_tex = (
                output / "behaviour_policy_paired_contrasts.tex"
            ).read_text(encoding="utf-8")
            self.assertIn("Adaptive $-$ fixed aggressive", paired_tex)
            self.assertIn("Adaptive $-$ fixed conservative", paired_tex)
            self.assertIn("$n/5$", paired_tex)
            self.assertIn(
                "behaviour_policy_paired_contrasts.tex", receipt["artifacts"]
            )
            self.assertIn(
                "Buffered--resume",
                (output / "behaviour_release.tex").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Stop--release",
                (output / "behaviour_release.tex").read_text(encoding="utf-8"),
            )

    def test_hash_mismatch_is_fatal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "results/B0_adaptive_assertive/scenario_uk_give_way_ego_init_101_smpc_var_risk/smpc_debug_steps.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(debug_row(0, 1.0)) + "\n", encoding="utf-8")
            audit = root / "matrix.json"
            audit.write_text(
                json.dumps({"evaluations": [{"cell_id": "B0_adaptive_assertive", "rollouts": [{"scenario": path.parent.name, "artifacts": {"debug_sha256": "0" * 64}}]}]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                analyze_formal(
                    root / "results", audit, root / "out", fps=20.0,
                    stop_speed_mps=0.15, resume_speed_mps=0.8,
                    consecutive_steps=3, expected_rollouts=1,
                )


if __name__ == "__main__":
    unittest.main()
