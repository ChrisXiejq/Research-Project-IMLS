import unittest
from pathlib import Path

import numpy as np

from core.scripts.analyze_implicit_smpc_safety_filter import (
    evaluate_three_phase_behavior,
)
from core.scripts.carla.policies.exogenous_straight_prediction import (
    build_exogenous_straight_gmm,
    route_line_conflict_geometry,
)
from core.scripts.carla.policies.conflict_zone_safety_filter import (
    conflict_zone_filter_bounds,
)
from core.scripts.carla.policies.route_corridor import (
    project_points_to_route_segments,
    reference_index_from_route_progress,
)
from core.scripts.experiment_tuning import load_scenario_with_tuning
from core.scripts.carla.utils.carla_sync_mode import CarlaSyncMode


class ExogenousStraightPredictionTests(unittest.TestCase):
    def test_prediction_is_straight_multimodal_and_ego_independent(self):
        probabilities, means, covariances = build_exogenous_straight_gmm(
            [10.0, -2.0],
            [-9.0, 0.0],
            horizon_steps=25,
            dt_s=0.2,
            speed_offsets_mps=(-0.75, 0.0, 0.75),
            mode_probabilities=(0.2, 0.6, 0.2),
            initial_longitudinal_std_m=0.35,
            initial_lateral_std_m=0.25,
            longitudinal_std_growth_mps=0.20,
            lateral_std_growth_mps=0.08,
        )

        self.assertEqual(probabilities.tolist(), [0.2, 0.6, 0.2])
        self.assertEqual(means.shape, (3, 25, 2))
        self.assertEqual(covariances.shape, (3, 25, 2, 2))
        self.assertTrue(np.allclose(means[:, :, 1], -2.0))
        self.assertTrue(np.all(np.diff(means[:, :, 0], axis=1) < 0.0))
        self.assertGreater(means[0, -1, 0], means[2, -1, 0])
        self.assertTrue(np.all(np.linalg.eigvalsh(covariances) > 0.0))
        self.assertGreater(covariances[0, -1, 0, 0], covariances[0, 0, 0, 0])

    def test_invalid_probability_contract_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "sum to one"):
            build_exogenous_straight_gmm(
                [0.0, 0.0],
                [1.0, 0.0],
                horizon_steps=25,
                dt_s=0.2,
                speed_offsets_mps=(-0.5, 0.0, 0.5),
                mode_probabilities=(0.2, 0.2, 0.2),
                initial_longitudinal_std_m=0.35,
                initial_lateral_std_m=0.25,
                longitudinal_std_growth_mps=0.20,
                lateral_std_growth_mps=0.08,
            )

    def test_conflict_geometry_is_evaluation_only_and_route_defined(self):
        geometry = route_line_conflict_geometry(
            [[-2.0, -3.0], [-1.0, -1.0], [0.5, 0.2], [2.0, 1.0]],
            [-5.0, 0.0],
            [5.0, 0.0],
        )

        self.assertFalse(geometry["controller_input"])
        self.assertEqual(geometry["ego_route_index"], 2)
        self.assertTrue(
            np.allclose(geometry["ego_conflict_point_xy"], [0.5, 0.2])
        )
        self.assertTrue(
            np.allclose(geometry["target_conflict_point_xy"], [0.5, 0.0])
        )
        self.assertAlmostEqual(geometry["route_line_separation_m"], 0.2)


class ConflictZoneSafetyFilterTests(unittest.TestCase):
    def test_bounds_activate_from_multimodal_occupancy_and_release_after_clearance(self):
        # Mode 0 crosses the conflict point at prediction step 2; mode 1 is
        # already clear. The union-of-modes constraint must therefore activate
        # only around the plausible occupancy and then release automatically.
        means = np.asarray(
            [
                [[-8.0, 0.0], [-3.0, 0.0], [1.0, 0.0], [8.0, 0.0]],
                [[5.0, 0.0], [9.0, 0.0], [13.0, 0.0], [17.0, 0.0]],
            ],
            dtype=float,
        )
        covariances = np.repeat(
            (0.25 * np.eye(2))[None, None, :, :],
            means.shape[0] * means.shape[1],
            axis=0,
        ).reshape(means.shape[0], means.shape[1], 2, 2)
        bounds, status = conflict_zone_filter_bounds(
            means,
            covariances,
            target_conflict_point_xy=[0.0, 0.0],
            target_tangent_xy=[1.0, 0.0],
            ego_buffer_m=3.0,
            target_conflict_half_length_m=2.0,
            sigma_scale=2.0,
            inactive_bound_m=1000.0,
            horizon_steps=4,
        )

        self.assertEqual(bounds.tolist(), [-3.0, -3.0, -3.0, 1000.0])
        self.assertEqual(status["raw_occupancy_steps"], [1, 2])
        self.assertEqual(status["active_steps"], [0, 1, 2])
        self.assertEqual(status["earliest_active_step"], 0)
        self.assertEqual(
            status["temporal_policy"], "target_priority_prefix_closure"
        )
        self.assertTrue(status["uses_all_modes"])

    def test_no_future_occupancy_leaves_filter_inactive(self):
        means = np.asarray([[[8.0, 0.0], [10.0, 0.0], [12.0, 0.0]]])
        covariances = np.repeat(
            (0.01 * np.eye(2))[None, None, :, :], 3, axis=1
        )
        bounds, status = conflict_zone_filter_bounds(
            means,
            covariances,
            target_conflict_point_xy=[0.0, 0.0],
            target_tangent_xy=[1.0, 0.0],
            ego_buffer_m=3.0,
            target_conflict_half_length_m=2.0,
            sigma_scale=2.0,
            inactive_bound_m=1000.0,
            horizon_steps=3,
        )

        self.assertEqual(bounds.tolist(), [1000.0, 1000.0, 1000.0])
        self.assertEqual(status["raw_occupancy_steps"], [])
        self.assertEqual(status["active_steps"], [])

    def test_conflict_geometry_provides_unit_ego_tangent(self):
        geometry = route_line_conflict_geometry(
            [[0.0, -4.0], [0.0, -2.0], [0.0, 0.0], [1.0, 2.0]],
            [-5.0, 0.0],
            [5.0, 0.0],
        )
        self.assertAlmostEqual(
            np.linalg.norm(geometry["ego_tangent_xy"]), 1.0
        )


class RouteCorridorGeometryTests(unittest.TestCase):
    def test_projection_uses_nearest_segment_and_unit_lateral_normal(self):
        points, normals, indices, distances = project_points_to_route_segments(
            [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]],
            [[4.0, 2.0], [8.0, 6.0]],
        )

        self.assertTrue(np.allclose(points[0], [4.0, 0.0]))
        self.assertTrue(np.allclose(normals[0], [0.0, 1.0]))
        self.assertEqual(indices[0], 0)
        self.assertAlmostEqual(distances[0], 2.0)
        self.assertTrue(np.allclose(points[1], [10.0, 6.0]))
        self.assertTrue(np.allclose(normals[1], [-1.0, 0.0]))
        self.assertEqual(indices[1], 1)
        self.assertAlmostEqual(distances[1], 2.0)

    def test_projection_cannot_move_backwards_after_anchor(self):
        points, _, indices, _ = project_points_to_route_segments(
            [[0.0, 0.0], [10.0, 0.0], [20.0, 0.0], [30.0, 0.0]],
            [[18.0, 1.0], [8.0, 1.0], [25.0, 1.0]],
            anchor_xy=[15.0, 0.0],
        )

        self.assertTrue(np.all(np.diff(indices) >= 0))
        self.assertGreaterEqual(points[0, 0], 15.0)
        self.assertGreaterEqual(points[1, 0], points[0, 0])
        self.assertGreaterEqual(points[2, 0], points[1, 0])

    def test_reference_index_uses_route_progress_not_spatial_proximity(self):
        # A folded route may place the exit near the approach in x-y.  The
        # one-dimensional progress index must still select the approach.
        self.assertEqual(
            reference_index_from_route_progress([0.0, 2.0, 4.0, 40.0, 42.0], 3.0),
            1,
        )
        self.assertEqual(
            reference_index_from_route_progress([0.0, 2.0, 4.0, 40.0, 42.0], 4.1),
            2,
        )


class SmpcTrackingObjectiveTests(unittest.TestCase):
    def test_main_state_cost_uses_absolute_route_tracking_error(self):
        repo_root = Path(__file__).resolve().parents[4]
        source = (
            repo_root / "core/scripts/carla/utils/mpc_utils.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "nom_z_err, 10 * cost_matrix_z[4:, 4:]",
            source,
        )
        self.assertNotIn(
            "cost+=RefTrajGenerator._quad_form(nom_z_ev, 10*cost_matrix_z)",
            source,
        )


class CarlaSyncModeTests(unittest.TestCase):
    def test_five_hz_configures_enough_physics_substeps(self):
        class Settings:
            synchronous_mode = False
            fixed_delta_seconds = None
            substepping = True
            max_substep_delta_time = 0.01
            max_substeps = 10

        class World:
            def __init__(self):
                self.settings = Settings()

            def get_settings(self):
                clone = Settings()
                clone.__dict__.update(self.settings.__dict__)
                return clone

            def apply_settings(self, settings):
                self.settings = settings
                return 1

            def on_tick(self, callback):
                self.callback = callback

        world = World()
        mode = CarlaSyncMode(world, fps=5)
        mode.__enter__()

        self.assertAlmostEqual(world.settings.fixed_delta_seconds, 0.2)
        self.assertTrue(world.settings.substepping)
        self.assertAlmostEqual(world.settings.max_substep_delta_time, 0.01)
        self.assertGreaterEqual(world.settings.max_substeps, 20)
        self.assertLessEqual(
            world.settings.fixed_delta_seconds,
            world.settings.max_substep_delta_time * world.settings.max_substeps,
        )


class ThreePhaseEvaluationTests(unittest.TestCase):
    @staticmethod
    def _trajectory_fixture():
        times = np.arange(11, dtype=float)
        target_x = 15.0 - 3.0 * times
        target = np.column_stack(
            (times, target_x, np.zeros_like(times), np.zeros_like(times), np.full_like(times, 3.0))
        )
        ego_y = np.asarray(
            [-15.0, -13.0, -11.0, -9.0, -7.0, -6.0, -5.0, -3.0, 0.0, 4.0, 8.0]
        )
        ego_speed = np.asarray([5.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.5, 1.0, 3.0, 4.0, 5.0])
        ego = np.column_stack(
            (times, np.zeros_like(times), ego_y, np.zeros_like(times), ego_speed)
        )
        geometry = {
            "ego_conflict_point_xy": [0.0, 0.0],
            "target_conflict_point_xy": [0.0, 0.0],
            "target_tangent_xy": [-1.0, 0.0],
        }
        return ego, target, geometry

    def test_three_phase_pass_requires_proceed_yield_resume_and_integrity(self):
        ego, target, geometry = self._trajectory_fixture()
        result = evaluate_three_phase_behavior(
            ego,
            target,
            geometry,
            completion_valid=True,
            native_collision=False,
            footprint_collision=False,
            solver_failure_fraction=0.0,
            contract_valid=True,
        )

        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["phase1_proceed_before_target"]["pass"])
        self.assertTrue(result["phase2_slow_and_yield"]["pass"])
        self.assertTrue(result["phase3_resume_after_target"]["pass"])

    def test_three_phase_fails_if_ego_crosses_without_slowing(self):
        ego, target, geometry = self._trajectory_fixture()
        ego[:, 2] = np.linspace(-15.0, 15.0, len(ego))
        ego[:, 4] = 5.0
        result = evaluate_three_phase_behavior(
            ego,
            target,
            geometry,
            completion_valid=True,
            native_collision=False,
            footprint_collision=False,
            solver_failure_fraction=0.0,
            contract_valid=True,
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["phase2_slow_and_yield"]["pass"])

    def test_three_phase_fails_closed_when_route_adherence_is_violated(self):
        ego, target, geometry = self._trajectory_fixture()
        result = evaluate_three_phase_behavior(
            ego,
            target,
            geometry,
            settings={"maximum_absolute_lateral_error_m": 2.5},
            completion_valid=True,
            native_collision=False,
            footprint_collision=False,
            solver_failure_fraction=0.0,
            contract_valid=True,
            observed_max_abs_lateral_error_m=7.0,
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(
            result["safety_and_integrity"]["ego_route_adherence_pass"]
        )
        self.assertIn(
            "ego_exceeded_maximum_lateral_route_error", result["errors"]
        )


class FrozenExperimentConfigurationTests(unittest.TestCase):
    def test_conflict_filter_candidate_is_optimisation_internal_and_supervisor_free(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_path = (
            scenario_path.parent
            / "tuning_configs/give_way_implicit_smpc_h4_conflict_filter.json"
        )
        scenario, metadata = load_scenario_with_tuning(
            str(scenario_path), str(tuning_path)
        )
        ego = next(item for item in scenario["vehicle_params"] if item["role"] == "ego")
        contract = metadata["config"]["innovation_contract"]

        self.assertEqual(ego["N"], 20)
        self.assertTrue(ego["implicit_safety_filter_enabled"])
        self.assertTrue(ego["smpc_terminal_collision_constraint_enabled"])
        self.assertTrue(ego["smpc_conflict_zone_filter_enabled"])
        self.assertTrue(ego["supervisor_free_smpc_enabled"])
        self.assertFalse(ego["yield_stop_enabled"])
        self.assertFalse(ego["yield_rule_smpc_bypass_enabled"])
        self.assertEqual(ego["yield_post_solver_action_filter_mode"], "monitor_only")
        self.assertFalse(contract["rule_state_machine"])
        self.assertFalse(contract["post_solver_override"])
        self.assertIsNone(contract["distance_trigger_m"])
        self.assertFalse(contract["evaluation_12m_window_used_by_controller"])

    def test_upstream_equivalent_baseline_is_supervisor_free_without_filter_changes(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_path = (
            scenario_path.parent
            / "tuning_configs/give_way_upstream_equivalent_smpc_baseline.json"
        )
        scenario, metadata = load_scenario_with_tuning(
            str(scenario_path), str(tuning_path)
        )
        ego = next(item for item in scenario["vehicle_params"] if item["role"] == "ego")
        target = next(
            item for item in scenario["vehicle_params"] if item["role"] == "target"
        )

        self.assertTrue(metadata["applied"])
        self.assertEqual(ego["N"], 10)
        self.assertAlmostEqual(ego["dt"], 0.2)
        self.assertEqual(ego["num_modes"], 3)
        self.assertEqual(ego["risk_profile"], "upstream_code")
        self.assertEqual(
            ego["control_implementation_version"],
            "legacy_single_tv_mode0_shared_amin_probability_weighted_v2",
        )
        self.assertEqual(ego["smpc_state_weights"], [5.0, 2.5, 10.0, 1.0])
        self.assertFalse(ego["smpc_correct_path_frame_cost_rotation"])
        self.assertFalse(ego["smpc_terminal_collision_constraint_enabled"])
        self.assertTrue(ego["supervisor_free_smpc_enabled"])
        self.assertFalse(ego["implicit_safety_filter_enabled"])
        self.assertFalse(ego["yield_stop_enabled"])
        self.assertFalse(ego["yield_rule_smpc_bypass_enabled"])
        self.assertEqual(ego["yield_post_solver_action_filter_mode"], "monitor_only")
        self.assertEqual(ego["yield_supervisor_behavioural_authority_mode"], "off")
        self.assertEqual(target["policy_type"], "straight")
        self.assertEqual(target["target_style"], "assertive_constant_speed")

    def test_dedicated_scenario_is_supervisor_free_and_paper_profile_ready(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        scenario, metadata = load_scenario_with_tuning(str(scenario_path))
        ego = next(item for item in scenario["vehicle_params"] if item["role"] == "ego")
        target = next(
            item for item in scenario["vehicle_params"] if item["role"] == "target"
        )

        self.assertTrue(metadata["applied"])
        self.assertEqual(ego["N"], 25)
        self.assertAlmostEqual(ego["N"] * ego["dt"], 5.0)
        self.assertEqual(ego["route_goal_extension_m"], 20.0)
        self.assertTrue(ego["exit_alignment_path_enabled"])
        self.assertEqual(ego["exit_alignment_path_length"], 10.0)
        self.assertTrue(ego["implicit_safety_filter_enabled"])
        self.assertFalse(ego["yield_stop_enabled"])
        self.assertFalse(ego["yield_rule_smpc_bypass_enabled"])
        self.assertEqual(ego["yield_post_solver_action_filter_mode"], "monitor_only")
        self.assertEqual(ego["yield_supervisor_behavioural_authority_mode"], "off")
        self.assertEqual(target["policy_type"], "straight")
        self.assertEqual(target["start_longitudinal_offset"], -2.0)
        self.assertFalse(scenario["drone_viz_params"]["attach_to_ego"])
        self.assertEqual(scenario["drone_viz_params"]["z"], 80.0)
        self.assertEqual(scenario["drone_viz_params"]["y"], -20.0)
        self.assertEqual(
            scenario["prediction_params"]["target_prediction_mode"],
            "exogenous_straight_gmm",
        )
        self.assertEqual(
            metadata["config"]["implicit_filter_evaluation"][
                "max_solver_failure_fraction"
            ],
            0.0,
        )

    def test_horizon_candidates_change_only_declared_horizon_contract(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_root = scenario_path.parent / "tuning_configs"

        for name, expected_steps in (("h2", 10), ("h3", 15), ("h4", 20)):
            with self.subTest(candidate=name):
                scenario, metadata = load_scenario_with_tuning(
                    str(scenario_path),
                    str(tuning_root / f"give_way_implicit_smpc_{name}.json"),
                )
                ego = next(
                    item for item in scenario["vehicle_params"]
                    if item["role"] == "ego"
                )
                target = next(
                    item for item in scenario["vehicle_params"]
                    if item["role"] == "target"
                )

                self.assertTrue(metadata["applied"])
                self.assertEqual(ego["N"], expected_steps)
                self.assertAlmostEqual(
                    ego["N"] * ego["dt"],
                    ego["implicit_safety_filter_min_horizon_s"],
                )
                self.assertTrue(ego["implicit_safety_filter_enabled"])
                self.assertEqual(ego["route_goal_extension_m"], 20.0)
                self.assertTrue(ego["exit_alignment_path_enabled"])
                self.assertEqual(ego["exit_alignment_path_length"], 10.0)
                self.assertFalse(ego["yield_stop_enabled"])
                self.assertFalse(ego["yield_rule_smpc_bypass_enabled"])
                self.assertEqual(
                    ego["yield_post_solver_action_filter_mode"], "monitor_only"
                )
                self.assertEqual(
                    ego["yield_supervisor_behavioural_authority_mode"], "off"
                )
                self.assertEqual(target["target_style"], "assertive_constant_speed")
                self.assertEqual(target["start_longitudinal_offset"], -2.0)
                self.assertEqual(
                    metadata["config"]["implicit_filter_evaluation"][
                        "max_solver_failure_fraction"
                    ],
                    0.0,
                )

    def test_route_corridor_candidates_are_solver_constraints_not_supervisors(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_root = scenario_path.parent / "tuning_configs"

        for suffix, expected_width in (("125", 1.25), ("150", 1.50)):
            with self.subTest(candidate=suffix):
                scenario, metadata = load_scenario_with_tuning(
                    str(scenario_path),
                    str(
                        tuning_root
                        / f"give_way_implicit_smpc_h4_corridor_{suffix}.json"
                    ),
                )
                ego = next(
                    item for item in scenario["vehicle_params"]
                    if item["role"] == "ego"
                )

                self.assertAlmostEqual(
                    ego["implicit_route_corridor_half_width_m"],
                    expected_width,
                )
                self.assertTrue(ego["implicit_safety_filter_enabled"])
                self.assertFalse(ego["yield_stop_enabled"])
                self.assertFalse(ego["yield_recovery_enabled"])
                self.assertFalse(ego["yield_rule_smpc_bypass_enabled"])
                self.assertEqual(
                    ego["yield_post_solver_action_filter_mode"], "monitor_only"
                )
                self.assertEqual(
                    ego["yield_supervisor_behavioural_authority_mode"], "off"
                )
                self.assertEqual(
                    metadata["config"]["postcarla_gate"][
                        "max_solver_failure_frac"
                    ],
                    0.0,
                )

    def test_lateral_weight_candidates_change_only_static_smpc_cost(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_root = scenario_path.parent / "tuning_configs"

        for suffix, expected_weight in (("10", 10.0), ("25", 25.0)):
            with self.subTest(candidate=suffix):
                scenario, metadata = load_scenario_with_tuning(
                    str(scenario_path),
                    str(tuning_root / f"give_way_implicit_smpc_h4_latq{suffix}.json"),
                )
                ego = next(
                    item for item in scenario["vehicle_params"]
                    if item["role"] == "ego"
                )

                self.assertEqual(ego["N"], 20)
                self.assertEqual(
                    ego["smpc_state_weights"],
                    [5.0, expected_weight, 10.0, 1.0],
                )
                self.assertIsNone(ego["implicit_route_corridor_half_width_m"])
                self.assertTrue(ego["implicit_safety_filter_enabled"])
                self.assertFalse(ego["yield_stop_enabled"])
                self.assertFalse(ego["yield_recovery_enabled"])
                self.assertFalse(ego["yield_rule_smpc_bypass_enabled"])
                self.assertEqual(
                    ego["yield_supervisor_behavioural_authority_mode"], "off"
                )
                self.assertEqual(
                    metadata["config"]["implicit_filter_evaluation"][
                        "max_solver_failure_fraction"
                    ],
                    0.0,
                )

    def test_path_frame_rotation_candidates_are_explicit_and_supervisor_free(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_root = scenario_path.parent / "tuning_configs"

        for suffix, expected_lateral_weight in (("q2p5", 2.5), ("q10", 10.0)):
            with self.subTest(candidate=suffix):
                scenario, metadata = load_scenario_with_tuning(
                    str(scenario_path),
                    str(
                        tuning_root
                        / f"give_way_implicit_smpc_h4_rotfix_{suffix}.json"
                    ),
                )
                ego = next(
                    item for item in scenario["vehicle_params"]
                    if item["role"] == "ego"
                )

                self.assertTrue(ego["smpc_correct_path_frame_cost_rotation"])
                self.assertEqual(
                    ego["smpc_state_weights"],
                    [5.0, expected_lateral_weight, 10.0, 1.0],
                )
                self.assertIsNone(ego["implicit_route_corridor_half_width_m"])
                self.assertFalse(ego["yield_stop_enabled"])
                self.assertFalse(ego["yield_recovery_enabled"])
                self.assertFalse(ego["yield_rule_smpc_bypass_enabled"])
                self.assertEqual(
                    ego["yield_supervisor_behavioural_authority_mode"], "off"
                )
                self.assertEqual(
                    metadata["config"]["postcarla_gate"][
                        "max_solver_failure_frac"
                    ],
                    0.0,
                )

    def test_conflict_filter_rotation_candidates_keep_only_optimisation_authority(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_root = scenario_path.parent / "tuning_configs"

        for suffix, expected_lateral_weight in (
            ("rotfix", 2.5),
            ("rotfix_latq10", 10.0),
        ):
            with self.subTest(candidate=suffix):
                scenario, metadata = load_scenario_with_tuning(
                    str(scenario_path),
                    str(
                        tuning_root
                        / f"give_way_implicit_smpc_h4_conflict_filter_{suffix}.json"
                    ),
                )
                ego = next(
                    item for item in scenario["vehicle_params"]
                    if item["role"] == "ego"
                )
                evaluation = metadata["config"]["implicit_filter_evaluation"]
                contract = metadata["config"]["innovation_contract"]

                self.assertTrue(ego["smpc_correct_path_frame_cost_rotation"])
                self.assertTrue(ego["smpc_conflict_zone_filter_enabled"])
                self.assertTrue(ego["smpc_terminal_collision_constraint_enabled"])
                self.assertEqual(
                    ego["smpc_state_weights"],
                    [5.0, expected_lateral_weight, 10.0, 1.0],
                )
                self.assertFalse(ego["yield_stop_enabled"])
                self.assertFalse(ego["yield_recovery_enabled"])
                self.assertFalse(ego["yield_rule_smpc_bypass_enabled"])
                self.assertEqual(
                    ego["yield_supervisor_behavioural_authority_mode"], "off"
                )
                self.assertEqual(
                    ego["yield_post_solver_action_filter_mode"], "monitor_only"
                )
                self.assertEqual(evaluation["maximum_absolute_lateral_error_m"], 2.5)
                self.assertFalse(contract["rule_state_machine"])
                self.assertFalse(contract["post_solver_override"])
                self.assertIsNone(contract["distance_trigger_m"])

    def test_detour_allowed_candidate_keeps_yield_and_completion_as_hard_gates(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_path = (
            scenario_path.parent
            / "tuning_configs/give_way_implicit_smpc_h4_conflict_filter_detour_allowed.json"
        )
        scenario, metadata = load_scenario_with_tuning(
            str(scenario_path), str(tuning_path)
        )
        ego = next(
            item for item in scenario["vehicle_params"] if item["role"] == "ego"
        )
        evaluation = metadata["config"]["implicit_filter_evaluation"]
        contract = metadata["config"]["innovation_contract"]

        self.assertTrue(ego["smpc_conflict_zone_filter_enabled"])
        self.assertEqual(ego["yield_supervisor_behavioural_authority_mode"], "off")
        self.assertIsNone(evaluation["maximum_absolute_lateral_error_m"])
        self.assertTrue(evaluation["require_valid_completion"])
        self.assertTrue(evaluation["require_no_native_collision"])
        self.assertEqual(evaluation["max_solver_failure_fraction"], 0.0)
        self.assertEqual(
            contract["required_behaviour"],
            "decelerate_target_first_resume_and_complete",
        )

    def test_road_tube_candidates_use_actual_route_without_target_trigger(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_root = scenario_path.parent / "tuning_configs"

        for suffix, width in (("w2", 2.0), ("w3", 3.0)):
            with self.subTest(candidate=suffix):
                scenario, metadata = load_scenario_with_tuning(
                    str(scenario_path),
                    str(
                        tuning_root
                        / f"give_way_implicit_smpc_h4_road_tube_{suffix}.json"
                    ),
                )
                ego = next(
                    item for item in scenario["vehicle_params"]
                    if item["role"] == "ego"
                )
                contract = metadata["config"]["innovation_contract"]

                self.assertEqual(
                    ego["implicit_route_corridor_half_width_m"], width
                )
                self.assertTrue(ego["smpc_conflict_zone_filter_enabled"])
                self.assertEqual(
                    contract["route_tube_geometry"],
                    "nearest segment projection of actual per-episode CARLA route",
                )
                self.assertFalse(contract["route_tube_target_dependent"])
                self.assertFalse(contract["rule_state_machine"])
                self.assertFalse(contract["post_solver_override"])
                self.assertIsNone(contract["distance_trigger_m"])

    def test_braking_candidates_match_reference_and_solver_bounds(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_root = scenario_path.parent / "tuning_configs"

        cases = (
            ("brake6_jerk6", -6.0, -6.0, 6.0),
            ("brake8_jerk10", -8.0, -10.0, 10.0),
        )
        for name, accel_min, jerk_min, jerk_max in cases:
            with self.subTest(candidate=name):
                scenario, metadata = load_scenario_with_tuning(
                    str(scenario_path),
                    str(tuning_root / f"give_way_implicit_smpc_h4_{name}.json"),
                )
                ego = next(
                    item for item in scenario["vehicle_params"]
                    if item["role"] == "ego"
                )
                contract = metadata["config"]["innovation_contract"]

                self.assertEqual(ego["smpc_accel_min_mps2"], accel_min)
                self.assertEqual(ego["smpc_accel_max_mps2"], 2.0)
                self.assertEqual(ego["smpc_jerk_min_mps3"], jerk_min)
                self.assertEqual(ego["smpc_jerk_max_mps3"], jerk_max)
                self.assertIsNone(ego["implicit_route_corridor_half_width_m"])
                self.assertTrue(ego["smpc_conflict_zone_filter_enabled"])
                self.assertTrue(contract["reference_and_solver_bounds_matched"])
                self.assertFalse(contract["rule_state_machine"])
                self.assertFalse(contract["post_solver_override"])

    def test_soft_route_tube_candidates_keep_slack_inside_optimisation(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_root = scenario_path.parent / "tuning_configs"

        for suffix, weight in (("p250", 250.0), ("p1000", 1000.0)):
            with self.subTest(candidate=suffix):
                scenario, metadata = load_scenario_with_tuning(
                    str(scenario_path),
                    str(
                        tuning_root
                        / f"give_way_implicit_smpc_h4_softtube_{suffix}.json"
                    ),
                )
                ego = next(
                    item for item in scenario["vehicle_params"]
                    if item["role"] == "ego"
                )
                contract = metadata["config"]["innovation_contract"]

                self.assertEqual(
                    ego["implicit_route_corridor_half_width_m"], 2.5
                )
                self.assertEqual(
                    ego["implicit_route_corridor_slack_weight"], weight
                )
                if suffix == "p250":
                    self.assertEqual(scenario["carla_params"]["fps"], 10)
                    self.assertAlmostEqual(ego["dt"], 0.2)
                self.assertEqual(ego["smpc_accel_min_mps2"], -6.0)
                self.assertEqual(ego["smpc_jerk_min_mps3"], -6.0)
                self.assertTrue(ego["smpc_conflict_zone_filter_enabled"])
                self.assertEqual(contract["route_tube_slack_weight"], weight)
                self.assertFalse(contract["rule_state_machine"])
                self.assertFalse(contract["post_solver_override"])

    def test_progress_reference_hard_envelope_is_target_independent(self):
        repo_root = Path(__file__).resolve().parents[4]
        scenario_path = (
            repo_root
            / "core/scripts/carla/scenarios/scenario_implicit_smpc_give_way.json"
        )
        tuning_path = (
            scenario_path.parent
            / "tuning_configs/give_way_implicit_smpc_h4_hardtube_progressref.json"
        )
        scenario, metadata = load_scenario_with_tuning(
            str(scenario_path), str(tuning_path)
        )
        ego = next(
            item for item in scenario["vehicle_params"] if item["role"] == "ego"
        )
        contract = metadata["config"]["innovation_contract"]

        self.assertEqual(ego["implicit_route_corridor_half_width_m"], 3.0)
        self.assertIsNone(ego.get("implicit_route_corridor_slack_weight"))
        self.assertTrue(ego["smpc_conflict_zone_filter_enabled"])
        self.assertFalse(contract["route_envelope_target_dependent"])
        self.assertFalse(contract["route_envelope_slack"])
        self.assertEqual(
            contract["temporal_policy"],
            "remain behind the stop half-space until the last predicted target occupancy, then release",
        )
        self.assertFalse(contract["rule_state_machine"])
        self.assertFalse(contract["post_solver_override"])


if __name__ == "__main__":
    unittest.main()
