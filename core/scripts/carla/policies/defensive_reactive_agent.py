"""Defensive straight-going target used for the V2 interaction dataset.

The target remains on its frozen straight route.  It reduces speed only when
the ego and target have similar predicted arrival times at the route conflict
point, uses hysteresis to avoid toggling, never commands a full stop before the
conflict, and recovers to nominal speed after clearance.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np

scriptdir = os.path.abspath(__file__).split("carla")[0] + "carla/"
sys.path.append(scriptdir)
from policies.straight_line_agent import StraightLineAgent
from utils import frenet_trajectory_handler as fth


class DefensiveReactiveAgent(StraightLineAgent):
    def __init__(
        self,
        vehicle,
        goal_location,
        *,
        conflict_point_rhs,
        nominal_speed_mps=9.0,
        dt=0.2,
        caution_speed_mps=4.5,
        minimum_speed_mps=2.5,
        activation_distance_m=10.0,
        release_clearance_m=5.0,
        arrival_time_gap_s=0.5,
        closest_approach_time_s=4.0,
        closest_approach_distance_m=6.0,
        release_hold_s=0.8,
    ):
        super().__init__(
            vehicle,
            goal_location,
            nominal_speed_mps=nominal_speed_mps,
            dt=dt,
        )
        self.conflict_point = np.asarray(conflict_point_rhs, dtype=float)
        self.caution_speed = float(caution_speed_mps)
        self.minimum_speed = float(minimum_speed_mps)
        self.activation_distance = float(activation_distance_m)
        self.release_clearance = float(release_clearance_m)
        self.arrival_time_gap = float(arrival_time_gap_s)
        self.closest_approach_time = float(closest_approach_time_s)
        self.closest_approach_distance = float(closest_approach_distance_m)
        self.release_hold = float(release_hold_s)
        self.max_decel = -2.0
        self._active = False
        self._inactive_time = 0.0
        self._released_latched = False
        self._diagnostics = self._empty_diagnostics()

    def _empty_diagnostics(self):
        return {
            "style": "defensive_reactive",
            "active": False,
            "triggered_this_step": False,
            "released_this_step": False,
            "released_latched": False,
            "transition_reason": "none",
            "target_conflict_distance_m": None,
            "ego_conflict_distance_m": None,
            "target_ttc_s": None,
            "ego_ttc_s": None,
            "arrival_time_gap_s": None,
            "closest_approach_time_s": None,
            "closest_approach_distance_m": None,
            "desired_speed_mps": self.nominal_speed,
        }

    @staticmethod
    def _finite_or_none(value):
        return float(value) if math.isfinite(float(value)) else None

    def parameters(self):
        return {
            "controller": "DefensiveReactiveAgent",
            "conflict_point_rhs_m": self.conflict_point.tolist(),
            "nominal_speed_mps": self.nominal_speed,
            "caution_speed_mps": self.caution_speed,
            "minimum_speed_mps": self.minimum_speed,
            "activation_distance_m": self.activation_distance,
            "release_clearance_m": self.release_clearance,
            "arrival_time_gap_s": self.arrival_time_gap,
            "closest_approach_time_s": self.closest_approach_time,
            "closest_approach_distance_m": self.closest_approach_distance,
            "release_hold_s": self.release_hold,
            "max_accel_mps2": self.max_accel,
            "max_decel_mps2": self.max_decel,
            "conflict_geometry": "ego_reference_route_target_motion_line",
            "episode_semantics": "single_trigger_latched_release",
            "hazard_combination": "ttc_conflict_and_closest_approach",
            "parameter_status": "day5_development_candidate",
        }

    def diagnostics(self):
        return dict(self._diagnostics)

    def _interaction_metrics(self, ego_state, target_xy, target_velocity, target_speed):
        ego_xy = np.asarray([ego_state["x"], ego_state["y_rhs"]], dtype=float)
        ego_velocity = np.asarray(
            [ego_state["vx_rhs"], ego_state["vy_rhs"]], dtype=float
        )
        ego_speed = float(ego_state["speed"])

        target_conflict_signed = float(
            np.dot(self.conflict_point - target_xy, self.path_tangent)
        )
        target_distance = max(0.0, target_conflict_signed)
        ego_to_conflict = self.conflict_point - ego_xy
        ego_distance = float(np.linalg.norm(ego_to_conflict))
        ego_closing_speed = (
            float(np.dot(ego_velocity, ego_to_conflict / max(ego_distance, 1.0e-6)))
            if ego_distance > 1.0e-6
            else 0.0
        )
        target_ttc = (
            target_distance / max(target_speed, 0.1)
            if target_conflict_signed >= 0.0
            else -abs(target_conflict_signed) / max(target_speed, 0.1)
        )
        ego_ttc = (
            ego_distance / max(ego_closing_speed, 0.1)
            if ego_closing_speed > 0.0
            else float("inf")
        )
        relative_position = ego_xy - target_xy
        relative_velocity = ego_velocity - target_velocity
        rel_speed_sq = float(np.dot(relative_velocity, relative_velocity))
        closest_time = (
            float(np.clip(-np.dot(relative_position, relative_velocity) / rel_speed_sq, 0.0, self.closest_approach_time))
            if rel_speed_sq > 1.0e-6
            else 0.0
        )
        closest_distance = float(
            np.linalg.norm(relative_position + closest_time * relative_velocity)
        )
        return {
            "target_conflict_signed": target_conflict_signed,
            "target_distance": target_distance,
            "ego_distance": ego_distance,
            "target_ttc": target_ttc,
            "ego_ttc": ego_ttc,
            "arrival_gap": abs(target_ttc - ego_ttc),
            "closest_time": closest_time,
            "closest_distance": closest_distance,
            "ego_speed": ego_speed,
        }

    def run_step(self, pred_dict):
        vehicle_loc = self.vehicle.get_location()
        vehicle_tf = self.vehicle.get_transform()
        vehicle_vel = self.vehicle.get_velocity()
        x, y = float(vehicle_loc.x), -float(vehicle_loc.y)
        speed = float(np.linalg.norm([vehicle_vel.x, vehicle_vel.y]))
        psi = -float(fth.fix_angle(np.radians(vehicle_tf.rotation.yaw)))
        target_xy = np.asarray([x, y], dtype=float)
        target_velocity = np.asarray(
            [float(vehicle_vel.x), float(-vehicle_vel.y)], dtype=float
        )

        path_rel = target_xy - self.start_xy
        route_s = float(np.dot(path_rel, self.path_tangent))
        if self.goal_s > 0.0 and route_s >= self.goal_s:
            self.goal_reached = True

        ego_state = pred_dict.get("ego_actor_state")
        triggered = False
        released = False
        transition_reason = "none"
        metrics = None
        if ego_state:
            metrics = self._interaction_metrics(
                ego_state,
                target_xy,
                target_velocity,
                speed,
            )
            before_conflict = metrics["target_conflict_signed"] >= -self.release_clearance
            within_zone = (
                metrics["target_distance"] <= self.activation_distance
                and metrics["ego_distance"] <= self.activation_distance
            )
            ttc_conflict = (
                metrics["target_ttc"] >= 0.0
                and math.isfinite(metrics["ego_ttc"])
                and metrics["arrival_gap"] <= self.arrival_time_gap
            )
            closest_conflict = (
                metrics["closest_time"] <= self.closest_approach_time
                and metrics["closest_distance"] <= self.closest_approach_distance
            )
            hazard = (
                before_conflict
                and within_zone
                and ttc_conflict
                and closest_conflict
            )
            if hazard and not self._released_latched:
                self._inactive_time = 0.0
                if not self._active:
                    self._active = True
                    triggered = True
                    transition_reason = "hazard_trigger"
            elif self._active:
                self._inactive_time += self.DT
                cleared = metrics["target_conflict_signed"] < -self.release_clearance
                if cleared or self._inactive_time >= self.release_hold:
                    self._active = False
                    self._inactive_time = 0.0
                    self._released_latched = True
                    released = True
                    transition_reason = (
                        "target_cleared_conflict" if cleared else "hazard_absent_hold"
                    )

        desired_speed = self.caution_speed if self._active else self.nominal_speed
        if metrics is not None and metrics["target_conflict_signed"] >= 0.0:
            desired_speed = max(desired_speed, self.minimum_speed)
        acceleration = float(
            np.clip(0.8 * (desired_speed - speed), self.max_decel, self.max_accel)
        )
        control = self._low_level_control.update(
            speed,
            acceleration,
            desired_speed,
            0.0,
        )
        self._diagnostics = {
            "style": "defensive_reactive",
            "active": self._active,
            "triggered_this_step": triggered,
            "released_this_step": released,
            "released_latched": self._released_latched,
            "transition_reason": transition_reason,
            "target_conflict_distance_m": self._finite_or_none(
                metrics["target_conflict_signed"] if metrics else float("nan")
            ),
            "ego_conflict_distance_m": self._finite_or_none(
                metrics["ego_distance"] if metrics else float("nan")
            ),
            "target_ttc_s": self._finite_or_none(
                metrics["target_ttc"] if metrics else float("nan")
            ),
            "ego_ttc_s": self._finite_or_none(
                metrics["ego_ttc"] if metrics else float("nan")
            ),
            "arrival_time_gap_s": self._finite_or_none(
                metrics["arrival_gap"] if metrics else float("nan")
            ),
            "closest_approach_time_s": self._finite_or_none(
                metrics["closest_time"] if metrics else float("nan")
            ),
            "closest_approach_distance_m": self._finite_or_none(
                metrics["closest_distance"] if metrics else float("nan")
            ),
            "desired_speed_mps": desired_speed,
        }
        z0 = np.asarray([x, y, psi, speed])
        u0 = np.asarray([acceleration, 0.0])
        return control, z0, u0, True, np.nan
