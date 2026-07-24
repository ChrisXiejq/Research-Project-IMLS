import carla
import csv
import json
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import pdb
from matplotlib.patches import Ellipse

CARLA_ROOT = os.getenv("CARLA_ROOT")
if CARLA_ROOT is None:
    raise ValueError("CARLA_ROOT must be defined.")

sys.path.insert(0, CARLA_ROOT + "/PythonAPI/carla")
sys.path.append(CARLA_ROOT + "/PythonAPI/carla/agents/")
from navigation.global_route_planner import GlobalRoutePlanner

scriptdir = os.path.abspath(__file__).split('scripts')[0] + 'scripts/'
sys.path.append(scriptdir)
from evaluation.gmm_prediction import GMMPrediction

scriptdir = os.path.abspath(__file__).split('carla')[0] + 'carla/'
sys.path.append(scriptdir)
from utils import frenet_trajectory_handler as fth
from utils import mpc_utils as smpc
from utils.low_level_control import LowLevelControl
from utils.vehicle_geometry_utils import vehicle_name_to_lf_lr

class SMPCAgent(object):
    """ Implementation of an agent using multimodal predictions and stochastic MPC for control. """

    def __init__(self,
                 vehicle,                  # Vehicle object that this agent controls
                 goal_location,            # desired goal location used to generate a path
                 nominal_speed_mps =8.0, # sets desired speed (m/s) for tracking path
                 dt =0.2,
                 N=8,                   # time discretization (s) used to generate a reference
                 N_modes = 2,
                 smpc_config = "var_risk",
                 CAIA=False,
                 obca=False,
                 obca_mode=2,
                 fps=5,
                 n_tv_max=None,
                 risk_profile="upstream_code",
                 collision_d_min=0.5,
                 collision_ellipse_half_length=3.8,
                 collision_ellipse_half_width=1.8,
                 reference_regen_max_lateral_error=1.5,
                 yield_stop_enabled=True,
                 yield_stop_speed=0.2,
                 yield_caution_speed=3.5,
                 yield_creep_speed=1.5,
                 yield_caution_decel=-4.0,
                 yield_reference_min_speed=0.8,
                 yield_reference_decel=-3.75,
                 yield_stop_decel=-5.0,
                 yield_emergency_brake_enabled=True,
                 yield_emergency_decel=-7.0,
                 yield_emergency_jerk_limit=10.0,
                 yield_emergency_conflict_margin=1.25,
                 yield_hard_stop_target_distance=12.0,
                 yield_hard_stop_conflict_distance=13.0,
                 yield_conflict_radius=4.0,
                 yield_stop_buffer_distance=7.0,
                 yield_footprint_clearance_margin=1.5,
                 yield_brake_distance_margin=3.5,
                 yield_wait_steer_lookahead_distance=6.0,
                 yield_wait_steer_gain=1.0,
                 yield_ttc_margin=0.8,
                 yield_activation_distance=12.0,
                 yield_hold_distance=3.0,
                 yield_release_time=0.3,
                 yield_release_clearance_margin=1.0,
                 yield_observed_caution_enabled=True,
                 yield_observed_caution_distance=12.0,
                 yield_observed_caution_min_target_speed=0.5,
                 yield_steer_damping=0.25,
                 yield_recovery_enabled=True,
                 yield_recovery_steps=180,
                 yield_recovery_regen_period=2,
                 yield_recovery_max_lateral_error=12.0,
                 yield_recovery_speed=5.5,
                 yield_recovery_accel=1.8,
                 yield_supervisor_mode="full",
                 completion_s_margin=6.0,
                 completion_goal_dist=8.0,
                 completion_lateral_error=4.0,
                 completion_heading_error=0.18,
                 completion_lane_entry_goal_dist=1.0,
                 completion_lane_entry_heading_error=0.30,
                 completion_lane_entry_min_s_after_route_goal=0.0,
                 completion_exit_alignment_min_s_after_goal=4.0,
                 post_goal_reference_extension_m=0.0,
                 route_goal_extension_m=0.0,
                 exit_alignment_path_enabled=False,
                 exit_alignment_path_length=10.0,
                 exit_alignment_distance_after_goal=0.0,
                 exit_alignment_post_clearance_speed=4.0,
                 exit_alignment_post_clearance_goal_window=0.0,
                 lane_entry_heading_cost_enabled=False,
                 lane_entry_heading_cost_goal_window=8.0,
                 lane_entry_heading_cost_weight=0.2,
                 lane_entry_heading_cost_max_abs_epsi=0.35,
                 adaptive_risk_config=None,
                 ):
        self.vehicle = vehicle
        self.map    = vehicle.get_world().get_map()
        self.dt      = dt
        self.goal_location = goal_location
        self.nominal_speed_mps  = nominal_speed_mps
        self.N=N
        self.N_modes=N_modes
        try:
            # CARLA >= 0.9.13 constructor takes (map, sampling_resolution).
            self.planner = GlobalRoutePlanner(self.map, 0.5)
        except TypeError:
            # Older CARLA versions require a DAO object and explicit setup().
            from navigation.global_route_planner_dao import GlobalRoutePlannerDAO
            self.planner = GlobalRoutePlanner(GlobalRoutePlannerDAO(self.map, 0.5))
            self.planner.setup()
        self.lf, self.lr = vehicle_name_to_lf_lr(self.vehicle.type_id)
        self._low_level_control = LowLevelControl(vehicle)
        self.time=0
        self.t_ref=0
        self.fps=fps
        self.d_min=float(collision_d_min)
        self.collision_ellipse_half_length=float(collision_ellipse_half_length)
        self.collision_ellipse_half_width=float(collision_ellipse_half_width)
        self.reference_regen_max_lateral_error = float(reference_regen_max_lateral_error)
        self.yield_stop_enabled = bool(yield_stop_enabled)
        self.yield_stop_speed = float(yield_stop_speed)
        self.yield_caution_speed = float(yield_caution_speed)
        self.yield_creep_speed = float(yield_creep_speed)
        self.yield_caution_decel = float(yield_caution_decel)
        self.yield_reference_min_speed = float(yield_reference_min_speed)
        self.yield_reference_decel = float(yield_reference_decel)
        self.yield_stop_decel = float(yield_stop_decel)
        self.yield_emergency_brake_enabled = bool(yield_emergency_brake_enabled)
        self.yield_emergency_decel = float(yield_emergency_decel)
        self.yield_emergency_jerk_limit = float(yield_emergency_jerk_limit)
        self.yield_emergency_conflict_margin = float(yield_emergency_conflict_margin)
        self.yield_hard_stop_target_distance = float(yield_hard_stop_target_distance)
        self.yield_hard_stop_conflict_distance = float(yield_hard_stop_conflict_distance)
        self.yield_conflict_radius = float(yield_conflict_radius)
        self.yield_stop_buffer_distance = float(yield_stop_buffer_distance)
        self.yield_footprint_clearance_margin = float(yield_footprint_clearance_margin)
        self.yield_brake_distance_margin = float(yield_brake_distance_margin)
        self.yield_wait_steer_lookahead_distance = float(yield_wait_steer_lookahead_distance)
        self.yield_wait_steer_gain = float(yield_wait_steer_gain)
        self.yield_ttc_margin = float(yield_ttc_margin)
        self.yield_activation_distance = float(yield_activation_distance)
        self.yield_hold_distance = float(yield_hold_distance)
        self.yield_release_time = float(yield_release_time)
        self.yield_release_clearance_margin = float(yield_release_clearance_margin)
        self.yield_observed_caution_enabled = bool(yield_observed_caution_enabled)
        self.yield_observed_caution_distance = float(yield_observed_caution_distance)
        self.yield_observed_caution_min_target_speed = float(yield_observed_caution_min_target_speed)
        self.yield_steer_damping = float(yield_steer_damping)
        self.yield_recovery_enabled = bool(yield_recovery_enabled)
        self.yield_recovery_steps = int(yield_recovery_steps)
        self.yield_recovery_regen_period = int(yield_recovery_regen_period)
        self.yield_recovery_max_lateral_error = float(yield_recovery_max_lateral_error)
        self.yield_recovery_speed = float(yield_recovery_speed)
        self.yield_recovery_accel = float(yield_recovery_accel)
        self.yield_supervisor_mode = str(yield_supervisor_mode or "full").strip().lower()
        if self.yield_supervisor_mode not in {"full", "reduced_intervention"}:
            raise ValueError(
                "yield_supervisor_mode must be 'full' or 'reduced_intervention', "
                f"got {yield_supervisor_mode!r}"
            )
        self.completion_s_margin = float(completion_s_margin)
        self.completion_goal_dist = float(completion_goal_dist)
        self.completion_lateral_error = float(completion_lateral_error)
        self.completion_heading_error = float(completion_heading_error)
        self.completion_lane_entry_goal_dist = float(completion_lane_entry_goal_dist)
        self.completion_lane_entry_heading_error = float(completion_lane_entry_heading_error)
        self.completion_lane_entry_min_s_after_route_goal = float(completion_lane_entry_min_s_after_route_goal)
        self.completion_exit_alignment_min_s_after_goal = float(completion_exit_alignment_min_s_after_goal)
        self.post_goal_reference_extension_m = float(post_goal_reference_extension_m)
        self.route_goal_extension_m = float(route_goal_extension_m)
        self.exit_alignment_path_enabled = bool(exit_alignment_path_enabled)
        self.exit_alignment_path_length = float(exit_alignment_path_length)
        self.exit_alignment_distance_after_goal = float(exit_alignment_distance_after_goal)
        self.exit_alignment_post_clearance_speed = float(exit_alignment_post_clearance_speed)
        self.exit_alignment_post_clearance_goal_window = float(exit_alignment_post_clearance_goal_window)
        self.lane_entry_heading_cost_enabled = bool(lane_entry_heading_cost_enabled)
        self.lane_entry_heading_cost_goal_window = float(lane_entry_heading_cost_goal_window)
        self.lane_entry_heading_cost_weight = float(lane_entry_heading_cost_weight)
        self.lane_entry_heading_cost_max_abs_epsi = float(lane_entry_heading_cost_max_abs_epsi)
        self._route_goal_s = None
        self._lane_entry_heading_diagnostics = []
        self._lane_entry_heading_diag_steps = set()
        if self.d_min < 0.0:
            raise ValueError(f"collision_d_min must be non-negative, got {self.d_min}")
        if self.collision_ellipse_half_length <= 0.0 or self.collision_ellipse_half_width <= 0.0:
            raise ValueError(
                "collision_ellipse_half_length and collision_ellipse_half_width must be positive, "
                f"got {self.collision_ellipse_half_length}, {self.collision_ellipse_half_width}"
            )
        if self.reference_regen_max_lateral_error <= 0.0:
            raise ValueError(
                "reference_regen_max_lateral_error must be positive, "
                f"got {self.reference_regen_max_lateral_error}"
            )
        if self.yield_stop_speed < 0.0:
            raise ValueError(f"yield_stop_speed must be non-negative, got {self.yield_stop_speed}")
        if self.yield_caution_speed < self.yield_stop_speed:
            raise ValueError(
                "yield_caution_speed must be >= yield_stop_speed, "
                f"got {self.yield_caution_speed} < {self.yield_stop_speed}"
            )
        if self.yield_creep_speed < self.yield_stop_speed:
            raise ValueError(
                "yield_creep_speed must be >= yield_stop_speed, "
                f"got {self.yield_creep_speed} < {self.yield_stop_speed}"
            )
        if self.yield_caution_decel >= 0.0:
            raise ValueError(f"yield_caution_decel must be negative, got {self.yield_caution_decel}")
        if self.yield_reference_min_speed < self.yield_stop_speed:
            raise ValueError(
                "yield_reference_min_speed must be >= yield_stop_speed, "
                f"got {self.yield_reference_min_speed} < {self.yield_stop_speed}"
            )
        if self.yield_reference_decel >= 0.0:
            raise ValueError(f"yield_reference_decel must be negative, got {self.yield_reference_decel}")
        if self.yield_stop_decel >= 0.0:
            raise ValueError(f"yield_stop_decel must be negative, got {self.yield_stop_decel}")
        if self.yield_emergency_decel >= 0.0:
            raise ValueError(f"yield_emergency_decel must be negative, got {self.yield_emergency_decel}")
        if abs(self.yield_emergency_decel) < abs(self.yield_stop_decel):
            raise ValueError(
                "yield_emergency_decel must be at least as strong as yield_stop_decel, "
                f"got {self.yield_emergency_decel} vs {self.yield_stop_decel}"
            )
        if self.yield_emergency_jerk_limit <= 0.0:
            raise ValueError(
                f"yield_emergency_jerk_limit must be positive, got {self.yield_emergency_jerk_limit}"
            )
        if self.yield_emergency_conflict_margin < 0.0:
            raise ValueError(
                "yield_emergency_conflict_margin must be non-negative, "
                f"got {self.yield_emergency_conflict_margin}"
            )
        if self.yield_hard_stop_target_distance < 0.0:
            raise ValueError(
                "yield_hard_stop_target_distance must be non-negative, "
                f"got {self.yield_hard_stop_target_distance}"
            )
        if self.yield_hard_stop_conflict_distance < self.yield_conflict_radius:
            raise ValueError(
                "yield_hard_stop_conflict_distance must be >= yield_conflict_radius, "
                f"got {self.yield_hard_stop_conflict_distance} < {self.yield_conflict_radius}"
            )
        if abs(self.yield_reference_decel) > abs(self.yield_stop_decel):
            raise ValueError(
                "yield_reference_decel must be no stronger than yield_stop_decel, "
                f"got {self.yield_reference_decel} vs {self.yield_stop_decel}"
            )
        if self.yield_conflict_radius <= 0.0:
            raise ValueError(f"yield_conflict_radius must be positive, got {self.yield_conflict_radius}")
        if self.yield_stop_buffer_distance <= 0.0:
            raise ValueError(
                f"yield_stop_buffer_distance must be positive, got {self.yield_stop_buffer_distance}"
            )
        if self.yield_footprint_clearance_margin < 0.0:
            raise ValueError(
                "yield_footprint_clearance_margin must be non-negative, "
                f"got {self.yield_footprint_clearance_margin}"
            )
        if self.yield_brake_distance_margin < 0.0:
            raise ValueError(
                f"yield_brake_distance_margin must be non-negative, got {self.yield_brake_distance_margin}"
            )
        if self.yield_release_clearance_margin < 0.0:
            raise ValueError(
                "yield_release_clearance_margin must be non-negative, "
                f"got {self.yield_release_clearance_margin}"
            )
        if self.yield_wait_steer_lookahead_distance < 0.0:
            raise ValueError(
                "yield_wait_steer_lookahead_distance must be non-negative, "
                f"got {self.yield_wait_steer_lookahead_distance}"
            )
        if self.yield_observed_caution_distance < 0.0:
            raise ValueError(
                "yield_observed_caution_distance must be non-negative, "
                f"got {self.yield_observed_caution_distance}"
            )
        if self.yield_observed_caution_min_target_speed < 0.0:
            raise ValueError(
                "yield_observed_caution_min_target_speed must be non-negative, "
                f"got {self.yield_observed_caution_min_target_speed}"
            )
        if not 0.0 <= self.yield_steer_damping <= 1.0:
            raise ValueError(f"yield_steer_damping must be in [0, 1], got {self.yield_steer_damping}")
        if self.yield_recovery_steps < 0:
            raise ValueError(f"yield_recovery_steps must be non-negative, got {self.yield_recovery_steps}")
        if self.yield_recovery_regen_period <= 0:
            raise ValueError(
                f"yield_recovery_regen_period must be positive, got {self.yield_recovery_regen_period}"
            )
        if self.yield_recovery_max_lateral_error < self.reference_regen_max_lateral_error:
            raise ValueError(
                "yield_recovery_max_lateral_error must be >= reference_regen_max_lateral_error, "
                f"got {self.yield_recovery_max_lateral_error} < {self.reference_regen_max_lateral_error}"
            )
        if self.yield_recovery_speed < self.yield_stop_speed:
            raise ValueError(
                f"yield_recovery_speed must be >= yield_stop_speed, got {self.yield_recovery_speed}"
            )
        if self.completion_s_margin < 0.0:
            raise ValueError(f"completion_s_margin must be non-negative, got {self.completion_s_margin}")
        if self.completion_goal_dist <= 0.0:
            raise ValueError(f"completion_goal_dist must be positive, got {self.completion_goal_dist}")
        if self.completion_lateral_error <= 0.0:
            raise ValueError(
                f"completion_lateral_error must be positive, got {self.completion_lateral_error}"
            )
        if self.completion_heading_error <= 0.0:
            raise ValueError(
                f"completion_heading_error must be positive, got {self.completion_heading_error}"
            )
        if self.completion_lane_entry_goal_dist <= 0.0:
            raise ValueError(
                "completion_lane_entry_goal_dist must be positive, "
                f"got {self.completion_lane_entry_goal_dist}"
            )
        if self.completion_lane_entry_heading_error <= 0.0:
            raise ValueError(
                "completion_lane_entry_heading_error must be positive, "
                f"got {self.completion_lane_entry_heading_error}"
            )
        if self.completion_lane_entry_min_s_after_route_goal < 0.0:
            raise ValueError(
                "completion_lane_entry_min_s_after_route_goal must be non-negative, "
                f"got {self.completion_lane_entry_min_s_after_route_goal}"
            )
        if self.completion_exit_alignment_min_s_after_goal < 0.0:
            raise ValueError(
                "completion_exit_alignment_min_s_after_goal must be non-negative, "
                f"got {self.completion_exit_alignment_min_s_after_goal}"
            )
        if self.post_goal_reference_extension_m < 0.0:
            raise ValueError(
                "post_goal_reference_extension_m must be non-negative, "
                f"got {self.post_goal_reference_extension_m}"
            )
        if self.route_goal_extension_m < 0.0:
            raise ValueError(
                "route_goal_extension_m must be non-negative, "
                f"got {self.route_goal_extension_m}"
            )
        if self.exit_alignment_path_length < 0.0:
            raise ValueError(
                f"exit_alignment_path_length must be non-negative, got {self.exit_alignment_path_length}"
            )
        if self.exit_alignment_distance_after_goal < 0.0:
            raise ValueError(
                "exit_alignment_distance_after_goal must be non-negative, "
                f"got {self.exit_alignment_distance_after_goal}"
            )
        if self.exit_alignment_post_clearance_speed <= 0.0:
            raise ValueError(
                "exit_alignment_post_clearance_speed must be positive, "
                f"got {self.exit_alignment_post_clearance_speed}"
            )
        if self.exit_alignment_post_clearance_goal_window < 0.0:
            raise ValueError(
                "exit_alignment_post_clearance_goal_window must be non-negative, "
                f"got {self.exit_alignment_post_clearance_goal_window}"
            )
        if self.lane_entry_heading_cost_goal_window < 0.0:
            raise ValueError(
                "lane_entry_heading_cost_goal_window must be non-negative, "
                f"got {self.lane_entry_heading_cost_goal_window}"
            )
        if self.lane_entry_heading_cost_weight < 0.0:
            raise ValueError(
                "lane_entry_heading_cost_weight must be non-negative, "
                f"got {self.lane_entry_heading_cost_weight}"
            )
        if self.lane_entry_heading_cost_max_abs_epsi <= 0.0:
            raise ValueError(
                "lane_entry_heading_cost_max_abs_epsi must be positive, "
                f"got {self.lane_entry_heading_cost_max_abs_epsi}"
            )
        # Used by SMPC_MMPreds_OL (N_TV_MAX); intersection runner passes target count.
        self._n_tv_max_ol = n_tv_max
        self.risk_profile = risk_profile
        if adaptive_risk_config is None:
            adaptive_risk_config = {}
        if not isinstance(adaptive_risk_config, dict):
            raise TypeError(
                "adaptive_risk_config must be a dict or None, "
                f"got {type(adaptive_risk_config).__name__}"
            )
        self.adaptive_risk_config = dict(adaptive_risk_config)

        self.fixed_risk=False
        self.obca_flag=obca
        self.obca_mode=obca_mode
        self.CA_inner_approx=CAIA  # if true, model EV as circle for robustifying collision avoidance constraint against EV heading error
        if smpc_config=="var_risk":
            self.ol_flag=False
            self.ns_bl_flag=True
        elif smpc_config=="open_loop":
            self.ol_flag=True
            self.ns_bl_flag=False
        elif smpc_config=='fixed_risk':
            self.fixed_risk=True
            self.ns_bl_flag=True
            self.ol_flag=False

        else:
            raise ValueError(f"Invalid SMPC config: {smpc_config}")

        # reference_regeneration() is called before the SMPC solver object is
        # constructed. Keep policy-specific feasible-reference bounds here:
        # fixed-risk benefited from a stronger local braking reference, while
        # var-risk regressed when its reference generator used -4.0 globally.
        if self.fixed_risk and not self.obca_flag:
            self._ref_gen_a_min = -4.0
        else:
            self._ref_gen_a_min = -3.0
        self._ref_gen_a_max = 2.0





        self.control_prev = np.zeros((2,1))
        self.prev_opt=False
        self.prev_nom_inputs=[]
        self._yield_stop_seen = False
        self._yield_stop_active_prev = False
        self._yield_recovery_steps_remaining = 0
        self._rule_yield_phase = "idle"
        self._yield_last_applied_accel = None
        self._yield_geometry = None
        self._observed_target_tracks = {}
        self.reference_regeneration()

        self.warm_start={}
        self.debug_savedir = None
        self.debug_label = smpc_config
        self._debug_setup_written = False
        self._debug_first_failure_written = False
        self._debug_completion_written = False

        # Debugging: see the reference solution.

        # plt.subplot(411)
        # # import pdb; pdb.set_trace()
        # plt.plot(self.reference[:,0], self.reference[:,1], 'kx')
        # plt.plot(self.reference[:,0], self.feas_ref_states[:self.reference.shape[0],0], 'r')

        # plt.ylabel('x')
        # plt.subplot(412)
        # plt.plot(self.reference[:,0], self.reference[:,2], 'kx')
        # plt.plot(self.reference[:,0], self.feas_ref_states[:self.reference.shape[0],1], 'r')
        # plt.ylabel('y')
        # plt.subplot(413)
        # plt.plot(self.reference[:,0], self.reference[:,3], 'kx')
        # plt.plot(self.reference[:,0], self.feas_ref_states[:self.reference.shape[0],2], 'r')
        # plt.ylabel('yaw')
        # plt.subplot(414)
        # plt.plot(self.reference[:,0], self.reference[:,4], 'kx')
        # plt.plot(self.reference[:,0], self.feas_ref_states[:self.reference.shape[0],3], 'r')
        # plt.ylabel('v')

        # plt.figure()
        # plt.subplot(211)
        # plt.plot(self.reference[:-1,0], self.feas_ref_inputs[:self.reference.shape[0]-1,0])
        # plt.ylabel('acc')
        # plt.subplot(212)
        # plt.plot(self.reference[:-1,0], self.feas_ref_inputs[:self.reference.shape[0]-1,1])
        # plt.ylabel('df')
        # plt.show()

        # MPC initialization (might take a while....)
        n_tv_mpc = n_tv_max if n_tv_max is not None else 1
        solver_risk_profile = (
            "adaptive_interaction_severity"
            if (self.risk_profile or "").lower() in {
                "adaptive_interaction_severity_no_floor",
                "adaptive_interaction_severity_no_relax",
                "adaptive_interaction_severity_no_phase_awareness",
            }
            else self.risk_profile
        )
        if not self.ol_flag:
            if not self.obca_flag:
                self.SMPC=smpc.SMPC_MMPreds(N=self.N, DT=self.dt, N_modes_MAX=self.N_modes, NS_BL_FLAG=self.ns_bl_flag, fixed_risk=self.fixed_risk,
                                    L_F=self.lf, L_R=self.lr, fps=self.fps, N_TV_MAX=n_tv_mpc,
                                    risk_profile=solver_risk_profile)
            else:
                self.SMPC=smpc.SMPC_MMPreds_OBCA(N=self.N, DT=self.dt, N_modes_MAX=self.N_modes, NS_BL_FLAG=self.ns_bl_flag,
                                        L_F=self.lf, L_R=self.lr, fps=self.fps, pol_mode=self.obca_mode, N_TV_MAX=n_tv_mpc)
        else:
            n_tvm = self._n_tv_max_ol if self._n_tv_max_ol is not None else 2
            self.SMPC=smpc.SMPC_MMPreds_OL(N=self.N, DT=self.dt, N_modes_MAX=self.N_modes,
                                          L_F=self.lf, L_R=self.lr, fps=self.fps,
                                          N_TV_MAX=n_tvm,
                                          risk_profile=solver_risk_profile)


        self.goal_reached = False # flags when the end of the path is reached and agent should stop

    def set_debug_context(self, savedir, label=None):
        self.debug_savedir = savedir
        if label is not None:
            self.debug_label = label

    def _reference_generator_accel_bounds(self):
        solver = getattr(self, "SMPC", None)
        if solver is not None and self.fixed_risk and not self.obca_flag:
            return (
                getattr(solver, "A_MIN", self._ref_gen_a_min),
                getattr(solver, "A_MAX", self._ref_gen_a_max),
            )
        return self._ref_gen_a_min, self._ref_gen_a_max

    def _debug_json_safe(self, value):
        if isinstance(value, np.ndarray):
            return self._debug_json_safe(value.tolist())
        if isinstance(value, (np.floating, float)):
            value = float(value)
            return value if np.isfinite(value) else None
        if isinstance(value, (np.integer, int)):
            return int(value)
        if isinstance(value, (np.bool_, bool)):
            return bool(value)
        if isinstance(value, dict):
            return {str(k): self._debug_json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._debug_json_safe(v) for v in value]
        return value

    def _debug_array_summary(self, value, max_items=6):
        try:
            arr = np.asarray(value)
        except Exception as exc:
            return {"error": repr(exc), "type": type(value).__name__}
        summary = {
            "shape": list(arr.shape),
            "dtype": str(arr.dtype),
            "size": int(arr.size),
        }
        if arr.size == 0:
            return summary
        try:
            finite = np.isfinite(arr.astype(float))
            summary.update({
                "finite_frac": float(np.mean(finite)),
                "nan_count": int(np.isnan(arr.astype(float)).sum()),
                "min": float(np.nanmin(arr.astype(float))),
                "max": float(np.nanmax(arr.astype(float))),
                "mean": float(np.nanmean(arr.astype(float))),
                "head": arr.reshape(-1)[:max_items].tolist(),
            })
        except Exception:
            summary["head"] = arr.reshape(-1)[:max_items].tolist()
        return self._debug_json_safe(summary)

    def _debug_write_json(self, filename, payload):
        if not self.debug_savedir:
            return
        try:
            os.makedirs(self.debug_savedir, exist_ok=True)
            path = os.path.join(self.debug_savedir, filename)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._debug_json_safe(payload), f, indent=2, sort_keys=True)
        except Exception:
            pass

    def _debug_append_jsonl(self, filename, payload):
        if not self.debug_savedir:
            return
        try:
            os.makedirs(self.debug_savedir, exist_ok=True)
            path = os.path.join(self.debug_savedir, filename)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._debug_json_safe(payload), sort_keys=True) + "\n")
        except Exception:
            pass

    def _write_lane_entry_heading_diagnostics(self):
        if not self.debug_savedir:
            return
        try:
            os.makedirs(self.debug_savedir, exist_ok=True)
            json_path = os.path.join(self.debug_savedir, "smpc_lane_entry_heading_diagnostics.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(
                    self._debug_json_safe(self._lane_entry_heading_diagnostics),
                    f,
                    indent=2,
                    sort_keys=True,
                )

            csv_path = os.path.join(self.debug_savedir, "smpc_lane_entry_heading_diagnostics.csv")
            fieldnames = [
                "step", "debug_label", "trigger", "x", "y", "psi", "speed", "s", "ey", "epsi",
                "goal_dist", "s_after_route_goal", "ref_s", "ref_x", "ref_y", "ref_yaw",
                "map_wp_x", "map_wp_y", "map_wp_yaw", "map_lane_id", "map_road_id",
                "goal_x", "goal_y", "goal_yaw", "ego_minus_ref_yaw",
                "ego_minus_map_yaw", "ref_minus_map_yaw", "completed_by_lane_entry",
                "completion_heading_ok", "completion_lateral_ok",
            ]
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for row in self._lane_entry_heading_diagnostics:
                    writer.writerow({key: row.get(key) for key in fieldnames})
        except Exception:
            pass

    def _record_lane_entry_heading_diagnostics(
        self,
        *,
        x,
        y,
        psi,
        speed,
        s,
        ey,
        epsi,
        vehicle_wp,
        completion_metrics,
        trigger,
    ):
        if not self.debug_savedir:
            return
        try:
            step = int(self.time)
            trigger_key = (step, str(trigger))
            if trigger_key in self._lane_entry_heading_diag_steps:
                return
            self._lane_entry_heading_diag_steps.add(trigger_key)

            traj = self.frenet_traj.trajectory
            ref_idx = int(np.argmin(np.abs(traj[:, 0] - float(s))))
            ref_s = float(traj[ref_idx, 0])
            ref_x = float(traj[ref_idx, 1])
            ref_y = float(traj[ref_idx, 2])
            ref_yaw = float(traj[ref_idx, 3])

            map_wp_x = map_wp_y = map_wp_yaw = None
            map_lane_id = map_road_id = None
            if vehicle_wp is not None:
                map_loc = vehicle_wp.transform.location
                map_wp_x = float(map_loc.x)
                map_wp_y = float(-map_loc.y)
                map_wp_yaw = float(-fth.fix_angle(np.radians(vehicle_wp.transform.rotation.yaw)))
                map_lane_id = int(vehicle_wp.lane_id)
                map_road_id = int(vehicle_wp.road_id)

            goal_wp = self.map.get_waypoint(
                self.goal_location,
                project_to_road=True,
                lane_type=(carla.LaneType.Driving),
            )
            goal_yaw = None
            if goal_wp is not None:
                goal_yaw = float(-fth.fix_angle(np.radians(goal_wp.transform.rotation.yaw)))

            payload = {
                "step": step,
                "debug_label": self.debug_label,
                "trigger": str(trigger),
                "x": float(x),
                "y": float(y),
                "psi": float(psi),
                "speed": float(speed),
                "s": float(s),
                "ey": float(ey),
                "epsi": float(epsi),
                "goal_dist": completion_metrics.get("goal_dist"),
                "s_after_route_goal": completion_metrics.get("s_after_route_goal"),
                "ref_s": ref_s,
                "ref_x": ref_x,
                "ref_y": ref_y,
                "ref_yaw": ref_yaw,
                "map_wp_x": map_wp_x,
                "map_wp_y": map_wp_y,
                "map_wp_yaw": map_wp_yaw,
                "map_lane_id": map_lane_id,
                "map_road_id": map_road_id,
                "goal_x": float(self.goal_location.x),
                "goal_y": float(-self.goal_location.y),
                "goal_yaw": goal_yaw,
                "ego_minus_ref_yaw": float(fth.fix_angle(float(psi) - ref_yaw)),
                "ego_minus_map_yaw": None if map_wp_yaw is None else float(fth.fix_angle(float(psi) - map_wp_yaw)),
                "ref_minus_map_yaw": None if map_wp_yaw is None else float(fth.fix_angle(ref_yaw - map_wp_yaw)),
                "completed_by_lane_entry": bool(completion_metrics.get("completed_by_lane_entry", False)),
                "completion_heading_ok": bool(completion_metrics.get("heading_ok", False)),
                "completion_lateral_ok": bool(completion_metrics.get("lateral_ok", False)),
            }
            self._lane_entry_heading_diagnostics.append(payload)
            self._write_lane_entry_heading_diagnostics()
        except Exception:
            pass

    def _debug_write_setup_once(self):
        if self._debug_setup_written:
            return
        self._debug_setup_written = True
        payload = {
            "agent": "SMPCAgent",
            "debug_label": self.debug_label,
            "ol_flag": self.ol_flag,
            "fixed_risk": self.fixed_risk,
            "obca_flag": self.obca_flag,
            "ns_bl_flag": self.ns_bl_flag,
            "risk_profile": self.risk_profile,
            "N": self.N,
            "N_modes": self.N_modes,
            "fps": self.fps,
            "dt": self.dt,
            "n_tv_max_ol": self._n_tv_max_ol,
            "vehicle_type": self.vehicle.type_id,
            "lf": self.lf,
            "lr": self.lr,
            "collision_envelope": {
                "d_min": self.d_min,
                "ellipse_half_length": self.collision_ellipse_half_length,
                "ellipse_half_width": self.collision_ellipse_half_width,
            },
            "reference_regeneration": {
                "max_lateral_error": self.reference_regen_max_lateral_error,
            },
            "lane_entry_heading_cost": {
                "enabled": self.lane_entry_heading_cost_enabled,
                "goal_window": self.lane_entry_heading_cost_goal_window,
                "weight": self.lane_entry_heading_cost_weight,
                "max_abs_epsi": self.lane_entry_heading_cost_max_abs_epsi,
                "activation": "target_cleared_conflict and near_original_goal",
                "applies_to": "SMPC_MMPreds var/fixed risk only; open-loop and yield supervisor unchanged",
            },
            "completion": {
                "s_margin": self.completion_s_margin,
                "goal_dist": self.completion_goal_dist,
                "lateral_error": self.completion_lateral_error,
                "heading_error": self.completion_heading_error,
                "lane_entry_goal_dist": self.completion_lane_entry_goal_dist,
                "lane_entry_heading_error": self.completion_lane_entry_heading_error,
                "lane_entry_min_s_after_route_goal": self.completion_lane_entry_min_s_after_route_goal,
                "exit_alignment_min_s_after_goal": self.completion_exit_alignment_min_s_after_goal,
                "post_goal_reference_extension_m": self.post_goal_reference_extension_m,
                "route_goal_extension_m": self.route_goal_extension_m,
                "exit_alignment_path_enabled": self.exit_alignment_path_enabled,
                "exit_alignment_path_length": self.exit_alignment_path_length,
                "exit_alignment_distance_after_goal": self.exit_alignment_distance_after_goal,
                "exit_alignment_post_clearance_speed": self.exit_alignment_post_clearance_speed,
                "exit_alignment_post_clearance_goal_window": self.exit_alignment_post_clearance_goal_window,
            },
            "rule_aware_yield": {
                "priority_rule": "turning_gives_way_to_oncoming_straight",
                "state_machine": [
                    "free_drive",
                    "cautious_approach_observed_target",
                    "observe_priority_target",
                    "approach_yield_line",
                    "hold_yield_line",
                    "released_recovery",
                ],
                "conflict_zone_source": "fixed_ego_route_target_motion_line_intersection",
                "oracle_guard": "full priority yielding requires a valid multimodal prediction; before prediction is valid, only an observed moving target track may trigger cautious approach",
                "activation_rule": "priority yield uses distance_to_stop <= v^2/(2*abs(decel)) + brake_distance_margin; observed-track cautious approach also activates on this braking-distance trigger before MultiPath is valid",
                "pre_solve_reference_profile": "yield reference uses v_ref <= sqrt(v_ref_min^2 + 2*abs(reference_decel)*remaining_distance_to_stop); final near-stop control is handled by the yield controller, not by an instantaneous near-stop optimisation reference",
                "solver_bypass": "adaptive profile bypasses deterministic approach/hold and the first low-speed released_recovery handoff frames after the priority target has cleared",
                "release_clearance_buffer": "released_recovery starts only after the priority target has moved beyond conflict_radius + release_clearance_margin, so rule-order clearance also respects vehicle footprint clearance",
            },
            "yield_stop_supervisor": {
                "enabled": self.yield_stop_enabled,
                "mode": self.yield_supervisor_mode,
                "stop_speed": self.yield_stop_speed,
                "caution_speed": self.yield_caution_speed,
                "creep_speed": self.yield_creep_speed,
                "caution_decel": self.yield_caution_decel,
                "reference_min_speed": self.yield_reference_min_speed,
                "reference_decel": self.yield_reference_decel,
                "decel": self.yield_stop_decel,
                "emergency_brake_enabled": self.yield_emergency_brake_enabled,
                "emergency_decel": self.yield_emergency_decel,
                "emergency_jerk_limit": self.yield_emergency_jerk_limit,
                "emergency_conflict_margin": self.yield_emergency_conflict_margin,
                "hard_stop_target_distance": self.yield_hard_stop_target_distance,
                "hard_stop_conflict_distance": self.yield_hard_stop_conflict_distance,
                "emergency_rule": (
                    "hard-stop yield + target not cleared + braking_distance_required; "
                    "observed-track yield rolls at caution/creep speed until target priority is "
                    "confirmed by prediction, unless target-distance or conflict-distance hard-stop "
                    "thresholds are reached"
                ),
                "conflict_radius": self.yield_conflict_radius,
                "stop_buffer_distance": self.yield_stop_buffer_distance,
                "footprint_clearance_margin": self.yield_footprint_clearance_margin,
                "brake_distance_margin": self.yield_brake_distance_margin,
                "wait_steer_lookahead_distance": self.yield_wait_steer_lookahead_distance,
                "wait_steer_gain": self.yield_wait_steer_gain,
                "ttc_margin": self.yield_ttc_margin,
                "activation_distance": self.yield_activation_distance,
                "hold_distance": self.yield_hold_distance,
                "release_time": self.yield_release_time,
                "release_clearance_margin": self.yield_release_clearance_margin,
                "observed_caution_enabled": self.yield_observed_caution_enabled,
                "observed_caution_distance": self.yield_observed_caution_distance,
                "observed_caution_min_target_speed": self.yield_observed_caution_min_target_speed,
                "steer_damping": self.yield_steer_damping,
                "recovery_enabled": self.yield_recovery_enabled,
                "recovery_steps": self.yield_recovery_steps,
                "recovery_regen_period": self.yield_recovery_regen_period,
                "recovery_max_lateral_error": self.yield_recovery_max_lateral_error,
                "recovery_speed": self.yield_recovery_speed,
                "recovery_accel": self.yield_recovery_accel,
            },
            "smpc": {
                "class": type(self.SMPC).__name__,
                "N": getattr(self.SMPC, "N", None),
                "DT": getattr(self.SMPC, "DT", None),
                "N_modes": getattr(self.SMPC, "N_modes", None),
                "N_TV_max": getattr(self.SMPC, "N_TV_max", None),
                "t_bar_max": getattr(self.SMPC, "t_bar_max", None),
                "tight": getattr(self.SMPC, "tight", None),
                "target_prob": getattr(self.SMPC, "target_prob", None),
                "A_MIN": getattr(self.SMPC, "A_MIN", None),
                "A_MAX": getattr(self.SMPC, "A_MAX", None),
                "V_MIN": getattr(self.SMPC, "V_MIN", None),
                "V_MAX": getattr(self.SMPC, "V_MAX", None),
                "DF_MIN": getattr(self.SMPC, "DF_MIN", None),
                "DF_MAX": getattr(self.SMPC, "DF_MAX", None),
            },
            "reference_generator": {
                "A_MIN": self._reference_generator_accel_bounds()[0],
                "A_MAX": self._reference_generator_accel_bounds()[1],
            },
        }
        self._debug_write_json("smpc_debug_setup.json", payload)

    def _debug_prediction_summary(self, positions, preds, probs):
        payload = {
            "positions": self._debug_array_summary(positions),
            "mode_probs": self._debug_array_summary(probs),
        }
        try:
            payload["mus"] = self._debug_array_summary(preds[0])
            payload["sigmas"] = self._debug_array_summary(preds[1])
        except Exception as exc:
            payload["prediction_error"] = repr(exc)
        return payload

    def _debug_update_summary(self, update_dict):
        keys = [
            "dx0", "dy0", "dpsi0", "dv0", "x_tv0", "y_tv0", "x_ref", "y_ref",
            "psi_ref", "v_ref", "a_ref", "df_ref", "x_lin", "y_lin",
            "psi_lin", "v_lin", "a_lin", "df_lin", "heading_cost_weights", "probs",
        ]
        return {key: self._debug_array_summary(update_dict[key])
                for key in keys if key in update_dict}

    def _debug_solver_summary(self, sol_dict):
        debug = sol_dict.get("debug", {}) if isinstance(sol_dict, dict) else {}
        payload = {
            "optimal": sol_dict.get("optimal") if isinstance(sol_dict, dict) else None,
            "solve_time": sol_dict.get("solve_time") if isinstance(sol_dict, dict) else None,
            "v_next": sol_dict.get("v_next") if isinstance(sol_dict, dict) else None,
            "u_control": self._debug_array_summary(sol_dict.get("u_control")) if isinstance(sol_dict, dict) else None,
            "debug": debug,
        }
        return payload

    def _debug_record_step(self, payload, is_failure=False):
        self._debug_append_jsonl("smpc_debug_steps.jsonl", payload)
        if is_failure:
            self._debug_write_json("smpc_debug_latest_failure.json", payload)
            if not self._debug_first_failure_written:
                self._debug_first_failure_written = True
                self._debug_write_json("smpc_first_failure.json", payload)

    def _completion_metrics(self, s, x, y, ey=None, epsi=None):
        goal_xy = np.array([self.goal_location.x, -self.goal_location.y], dtype=float)
        end_s = float(self.frenet_traj.trajectory[-1, 0])
        goal_dist = float(np.linalg.norm(np.array([x, y], dtype=float) - goal_xy))
        s_to_end = float(end_s - s)
        route_goal_s = self._route_goal_s
        if route_goal_s is None and self.post_goal_reference_extension_m > 0.0:
            route_goal_s = max(0.0, end_s - self.post_goal_reference_extension_m)
        s_after_route_goal = None if route_goal_s is None else float(s - route_goal_s)
        lateral_ok = bool(ey is not None and abs(float(ey)) <= self.completion_lateral_error)
        heading_ok = bool(epsi is not None and abs(float(epsi)) <= self.completion_heading_error)
        goal_dist_ok = bool(goal_dist <= self.completion_goal_dist)
        lane_entry_goal_ok = bool(goal_dist <= self.completion_lane_entry_goal_dist)
        lane_entry_heading_ok = bool(
            epsi is not None and abs(float(epsi)) <= self.completion_lane_entry_heading_error
        )
        lane_entry_s_ok = bool(
            s_after_route_goal is not None
            and s_after_route_goal >= self.completion_lane_entry_min_s_after_route_goal
        )
        lane_entry_ok = bool(lane_entry_goal_ok and lateral_ok and lane_entry_heading_ok and lane_entry_s_ok)
        exit_alignment_s_ok = bool(
            s_after_route_goal is not None
            and s_after_route_goal >= self.completion_exit_alignment_min_s_after_goal
        )
        exit_alignment_ok = bool(exit_alignment_s_ok and lateral_ok and heading_ok)
        pose_ok = bool(lateral_ok and heading_ok)
        return {
            "end_s": end_s,
            "route_goal_s": route_goal_s,
            "s_after_route_goal": s_after_route_goal,
            "s_to_end": s_to_end,
            "goal_dist": goal_dist,
            "completion_s_margin": self.completion_s_margin,
            "completion_goal_dist": self.completion_goal_dist,
            "completion_lateral_error": self.completion_lateral_error,
            "completion_heading_error": self.completion_heading_error,
            "completion_lane_entry_goal_dist": self.completion_lane_entry_goal_dist,
            "completion_lane_entry_heading_error": self.completion_lane_entry_heading_error,
            "completion_lane_entry_min_s_after_route_goal": self.completion_lane_entry_min_s_after_route_goal,
            "completion_exit_alignment_min_s_after_goal": self.completion_exit_alignment_min_s_after_goal,
            "lateral_ok": lateral_ok,
            "heading_ok": heading_ok,
            "lane_entry_goal_ok": lane_entry_goal_ok,
            "lane_entry_heading_ok": lane_entry_heading_ok,
            "lane_entry_s_ok": lane_entry_s_ok,
            "lane_entry_ok": lane_entry_ok,
            "exit_alignment_s_ok": exit_alignment_s_ok,
            "exit_alignment_ok": exit_alignment_ok,
            "ey": ey,
            "epsi": epsi,
            "goal_dist_ok": goal_dist_ok,
            "completed_by_s_margin": bool(s >= end_s - self.completion_s_margin and pose_ok),
            "completed_by_goal_dist": bool(goal_dist_ok and pose_ok),
            "completed_by_lane_entry": lane_entry_ok,
            "completed_by_exit_alignment": exit_alignment_ok,
        }

    def _horizon_slice_with_tail_padding(self, arr, start_idx, length):
        """Return a fixed-length horizon slice, repeating the tail near route end."""
        arr = np.asarray(arr)
        start_idx = int(max(0, min(start_idx, max(len(arr) - 1, 0))))
        sliced = arr[start_idx:start_idx + int(length)]
        if sliced.shape[0] == 0:
            sliced = arr[-1:]
        missing = int(length) - int(sliced.shape[0])
        if missing > 0:
            tail = np.repeat(sliced[-1:], missing, axis=0)
            sliced = np.concatenate((sliced, tail), axis=0)
        return sliced

    def _lane_entry_heading_cost_profile(self, t_ref_new, yield_status, epsi):
        weights = np.zeros(int(getattr(self.SMPC, "N", self.N)), dtype=float)
        status = {
            "enabled": bool(self.lane_entry_heading_cost_enabled),
            "active": False,
            "reason": "disabled",
            "goal_window": float(self.lane_entry_heading_cost_goal_window),
            "weight": float(self.lane_entry_heading_cost_weight),
            "max_abs_epsi": float(self.lane_entry_heading_cost_max_abs_epsi),
            "active_count": 0,
            "max_weight": 0.0,
        }
        if not self.lane_entry_heading_cost_enabled:
            return weights, status
        if self.ol_flag or self.obca_flag:
            status["reason"] = "unsupported_policy"
            return weights, status
        if self.lane_entry_heading_cost_weight <= 0.0:
            status["reason"] = "zero_weight"
            return weights, status
        if self.lane_entry_heading_cost_goal_window <= 0.0:
            status["reason"] = "zero_goal_window"
            return weights, status
        if not bool(yield_status.get("target_cleared_conflict", False)):
            status["reason"] = "target_not_cleared"
            return weights, status
        if epsi is None or abs(float(epsi)) > self.lane_entry_heading_cost_max_abs_epsi:
            status["reason"] = "epsi_outside_bound"
            status["epsi"] = None if epsi is None else float(epsi)
            return weights, status

        horizon_states = self._horizon_slice_with_tail_padding(
            self.feas_ref_states_new,
            t_ref_new + 1,
            int(getattr(self.SMPC, "N", self.N)),
        )
        ref_xy = np.asarray(horizon_states[:, :2], dtype=float)
        goal_xy = np.array([self.goal_location.x, -self.goal_location.y], dtype=float)
        goal_dist = np.linalg.norm(ref_xy - goal_xy.reshape(1, 2), axis=1)
        active_mask = goal_dist <= self.lane_entry_heading_cost_goal_window
        if not np.any(active_mask):
            status["reason"] = "horizon_outside_goal_window"
            status["min_horizon_goal_dist"] = float(np.min(goal_dist)) if goal_dist.size else None
            return weights, status

        ramp = 1.0 - np.clip(goal_dist / self.lane_entry_heading_cost_goal_window, 0.0, 1.0)
        weights[active_mask] = self.lane_entry_heading_cost_weight * ramp[active_mask]
        active_indices = np.flatnonzero(weights > 0.0)
        status.update({
            "active": True,
            "reason": "target_cleared_near_goal",
            "epsi": float(epsi),
            "active_count": int(active_indices.size),
            "max_weight": float(np.max(weights)) if weights.size else 0.0,
            "min_horizon_goal_dist": float(np.min(goal_dist)) if goal_dist.size else None,
            "first_active_index": int(active_indices[0]),
            "last_active_index": int(active_indices[-1]),
        })
        return weights, status


    def _apply_exit_alignment_path_shaping(self, way_s, way_xy, way_yaw):
        """Apply a gentle same-lane straight tail near the route goal.

        Keep the safe baseline geometry: a short final straight cue without the
        aggressive goal-anchored segment that caused 600-step non-completion.
        """
        if (
            not self.exit_alignment_path_enabled
            or self.exit_alignment_path_length <= 0.0
            or len(way_s) < 3
        ):
            return way_s, way_xy, way_yaw

        route_end_s = float(way_s[-1])
        alignment_len = min(float(self.exit_alignment_path_length), max(route_end_s - 1.0, 0.0))
        if alignment_len <= 1e-6:
            return way_s, way_xy, way_yaw

        tail_xy = np.asarray(way_xy[-1], dtype=float)
        tail_yaw = float(way_yaw[-1])
        tail_dir = np.array([np.cos(tail_yaw), np.sin(tail_yaw)], dtype=float)
        alignment_start_xy = tail_xy - alignment_len * tail_dir
        alignment_start_s = route_end_s - alignment_len

        keep_mask = way_s < alignment_start_s
        keep_s = way_s[keep_mask]
        keep_xy = way_xy[keep_mask]
        keep_yaw = way_yaw[keep_mask]
        if len(keep_s) == 0:
            keep_xy = way_xy[:1]
            keep_yaw = way_yaw[:1]

        shaped_xy = np.vstack((keep_xy, alignment_start_xy, tail_xy))
        shaped_yaw = np.concatenate((keep_yaw, np.array([tail_yaw, tail_yaw], dtype=float)))

        step_dist = np.linalg.norm(np.diff(shaped_xy, axis=0), axis=1)
        valid_steps = step_dist > 1e-3
        if not np.all(valid_steps):
            keep_indices = np.concatenate(([True], valid_steps))
            shaped_xy = shaped_xy[keep_indices]
            shaped_yaw = shaped_yaw[keep_indices]
            step_dist = np.linalg.norm(np.diff(shaped_xy, axis=0), axis=1)
        shaped_s = np.concatenate(([0.0], np.cumsum(step_dist)))
        return shaped_s, shaped_xy, shaped_yaw

    def _extended_route_goal_location(self, goal_waypoint):
        """Return a downstream route-planning goal while preserving the task goal."""
        base_location = goal_waypoint.transform.location
        if self.route_goal_extension_m <= 0.0:
            return base_location

        yaw_rad = np.radians(float(goal_waypoint.transform.rotation.yaw))
        return carla.Location(
            x=base_location.x + self.route_goal_extension_m * np.cos(yaw_rad),
            y=base_location.y + self.route_goal_extension_m * np.sin(yaw_rad),
            z=base_location.z,
        )

    def _s_at_original_goal(self, way_s, way_xy):
        goal_xy = np.array([self.goal_location.x, -self.goal_location.y], dtype=float)
        if len(way_s) == 0:
            return None
        nearest_idx = int(np.argmin(np.linalg.norm(np.asarray(way_xy) - goal_xy.reshape(1, 2), axis=1)))
        return float(way_s[nearest_idx])




    def fit_velocity_profile(self):
        t_fits = [0.]
        traj = self.frenet_traj.trajectory

        for state, next_state in zip(traj[:-1, :], traj[1:, :]):
            s, x, y, yaw, curv = state
            sn, xn, yn, yawn, curvn = next_state

            v_curr = min( self.nominal_speed, np.sqrt(self.lat_accel_max / max(0.01, np.abs(curv))) )

            t_fits.append( (sn - s) / v_curr + t_fits[-1] )

        # Interpolate the points at time discretization dt.
        t_disc    = np.arange(t_fits[0], t_fits[-1] + self.dt/2, self.dt)
        s_disc    = np.interp(t_disc, t_fits, traj[:,0])
        x_disc    = np.interp(t_disc, t_fits, traj[:,1])
        y_disc    = np.interp(t_disc, t_fits, traj[:,2])
        yaw_disc  = np.interp(t_disc, t_fits, traj[:,3])
        curv_disc = np.interp(t_disc, t_fits, traj[:,4])
        v_disc    = np.diff(s_disc) / np.diff(t_disc)
        v_disc    = np.insert(v_disc, -1, v_disc[-1]) # repeat the last speed




        self.reference = np.column_stack((t_disc, x_disc, y_disc, yaw_disc, v_disc))


    def reference_regeneration(self, *state):
        if self.time==0:
            # Get the high-level route using Carla's API (basically A* search over road segments).

            init_waypoint = self.map.get_waypoint(self.vehicle.get_location(), project_to_road=True, lane_type=(carla.LaneType.Driving))
            goal          = self.map.get_waypoint(self.goal_location, project_to_road=True, lane_type=(carla.LaneType.Driving))
            route_goal_location = self._extended_route_goal_location(goal)
            route = self.planner.trace_route(init_waypoint.transform.location, route_goal_location)

            # # Convert the high-level route into a path parametrized by arclength distance s (i.e. Frenet frame).
            # # Generate a refernece by fitting a velocity profile with specified nominal speed and time discretization.

            way_s, way_xy, way_yaw = fth.extract_path_from_waypoints(route)
            way_s, way_xy, way_yaw = self._apply_exit_alignment_path_shaping(way_s, way_xy, way_yaw)
            self._route_goal_s = self._s_at_original_goal(way_s, way_xy)
            if self._route_goal_s is None:
                self._route_goal_s = float(way_s[-1])
            if self.post_goal_reference_extension_m > 0.0 and len(way_s) >= 1:
                extension_s = np.arange(
                    1.0,
                    self.post_goal_reference_extension_m + 0.5,
                    1.0,
                    dtype=float,
                )
                if extension_s.size > 0:
                    tail_xy = way_xy[-1]
                    tail_yaw = way_yaw[-1]
                    extension_xy = tail_xy + np.column_stack((
                        extension_s * np.cos(tail_yaw),
                        extension_s * np.sin(tail_yaw),
                    ))
                    way_s = np.concatenate((way_s, way_s[-1] + extension_s))
                    way_xy = np.vstack((way_xy, extension_xy))
                    way_yaw = np.concatenate((way_yaw, np.full(extension_s.shape, tail_yaw)))
            self.frenet_traj = fth.FrenetTrajectoryHandler(way_s, way_xy, way_yaw, s_resolution=1.)
            self.nominal_speed = self.nominal_speed_mps
            self.lat_accel_max = 2. # maximum lateral acceleration (m/s^2), for slowing down at turns

            self.fit_velocity_profile()

            self.ref_horizon= self.reference.shape[0]-1
            self.ref_dict={'x_ref':self.reference[1:,1], 'y_ref':self.reference[1:,2], 'psi_ref':self.reference[1:,3], 'v_ref':self.reference[1:,4],
                            'x0'  : self.reference[0,1],  'y0'  : self.reference[0,2],  'psi0'  : self.reference[0,3],  'v0'  : self.reference[0,4], 'acc_prev' : self.control_prev[0], 'df_prev' : self.control_prev[1]}
            self.ref_dict['psi_ref'] = fth.fix_angle( self.ref_dict['psi_ref'] - self.ref_dict['psi0']) + self.ref_dict['psi0']
            ref_a_min, ref_a_max = self._reference_generator_accel_bounds()
            self.feas_ref_gen=smpc.RefTrajGenerator(
                N=self.ref_horizon,
                DT=self.dt,
                L_F=self.lf,
                L_R=self.lr,
                A_MIN=ref_a_min,
                A_MAX=ref_a_max,
            )
            self.feas_ref_gen.update(self.ref_dict)
            self.feas_ref_dict=self.feas_ref_gen.solve()
            self.feas_ref_states=self.feas_ref_dict['z_opt']

            self.feas_ref_states=np.vstack((self.feas_ref_states, np.array([self.feas_ref_states[-1,:]]*(self.N+1))))
            self.feas_ref_inputs=self.feas_ref_dict['u_opt']
            self.feas_ref_inputs=np.vstack((self.feas_ref_inputs, np.array([self.feas_ref_inputs[-1,:]]*(self.N+1))))
            self.feas_ref_states_new=self.feas_ref_states
            self.feas_ref_inputs_new=self.feas_ref_inputs

        else:

            x,y,psi,speed=state
            self.feas_ref_states_new=[]
            self.feas_ref_inputs_new=[]



            ref_a_min, ref_a_max = self._reference_generator_accel_bounds()
            self.feas_ref_gen=smpc.RefTrajGenerator(
                N=self.ref_horizon-self.t_ref-1,
                DT=self.dt,
                L_F=self.lf,
                L_R=self.lr,
                A_MIN=ref_a_min,
                A_MAX=ref_a_max,
            )

            self.ref_dict={'x_ref':self.feas_ref_states[self.t_ref+1:self.ref_horizon,0], 'y_ref':self.feas_ref_states[self.t_ref+1:self.ref_horizon,1], 'psi_ref':self.feas_ref_states[self.t_ref+1:self.ref_horizon,2], 'v_ref':self.feas_ref_states[self.t_ref+1:self.ref_horizon,3],
                            'x0'  : x,  'y0'  : y,  'psi0'  : psi,  'v0'  : speed, 'acc_prev' : self.control_prev[0], 'df_prev' : self.control_prev[1]}
            self.ref_dict['psi_ref'] = fth.fix_angle( self.ref_dict['psi_ref'] - self.ref_dict['psi0']) + self.ref_dict['psi0']
            self.ref_dict['warm_start']={'z_ws': np.vstack((np.array([[x,y,psi,speed]]),self.feas_ref_states[self.t_ref+1:self.ref_horizon,:])),
                                         'u_ws': np.array([[self.control_prev[0],self.control_prev[1]]]*self.feas_ref_gen.N) }
            self.feas_ref_gen.update(self.ref_dict)
            self.feas_ref_dict=self.feas_ref_gen.solve()
            self.feas_ref_states_new=self.feas_ref_dict['z_opt']

            self.feas_ref_states_new=np.vstack((self.feas_ref_states_new, np.array([self.feas_ref_states_new[-1,:]]*(self.N+1))))
            self.feas_ref_inputs_new=self.feas_ref_dict['u_opt']

            if len(self.feas_ref_inputs_new.shape)!=1:
                self.feas_ref_inputs_new=np.vstack((self.feas_ref_inputs_new, np.array([self.feas_ref_inputs_new[-1,:]]*(self.N+1)))).reshape((-1,2))
            else:
                self.feas_ref_inputs_new=np.array([self.feas_ref_inputs_new]*(self.N+1)).reshape((self.N+1,2))

            self.feas_ref_states_new=self.feas_ref_states_new
            self.feas_ref_inputs_new=self.feas_ref_inputs_new


    def linearization_traj(self, *state):
                x,y,psi,speed=state
                states=[np.array([x,y,psi,speed])]
                for t in range(self.N):
                    if t==self.N-1:
                        control=self.prev_nom_inputs[0][:,-1]
                    else:
                        control=self.prev_nom_inputs[0][:,t+1]
                    beta=np.arctan((self.lr/(self.lr+self.lf)*np.tan(control[1])))
                    x_next=states[t][0]+self.dt*(states[t][3]*np.cos(states[t][2]+beta))
                    y_next=states[t][1]+self.dt*(states[t][3]*np.sin(states[t][2]+beta))
                    psi_next=states[t][2]+self.dt*(states[t][3]/self.lr*np.sin(beta))
                    v_next  =states[t][3]+self.dt*control[0]
                    states.append(np.array([x_next,y_next,psi_next,v_next]))

                l_states=np.array(states).reshape((self.N+1,-1))
                l_inputs=self.prev_nom_inputs[0][:,1:].T
                l_inputs=np.vstack((l_inputs,np.array([l_inputs[-1,:]]*2)))

                return l_states, l_inputs



    def done(self):
        return self.goal_reached

    def _path_distance_to_index(self, xy_path, idx):
        if idx <= 0 or len(xy_path) < 2:
            return 0.0
        idx = int(min(idx, len(xy_path) - 1))
        diffs = np.diff(np.asarray(xy_path[:idx + 1], dtype=float), axis=0)
        return float(np.sum(np.linalg.norm(diffs, axis=1)))

    def _zone_interval_from_path(self, xy_path, center_xy, radius):
        xy_path = np.asarray(xy_path, dtype=float)
        if xy_path.size == 0:
            return None, None
        dist = np.linalg.norm(xy_path - np.asarray(center_xy, dtype=float), axis=1)
        inside = np.flatnonzero(dist <= radius)
        if len(inside) == 0:
            return None, None
        return int(inside[0]), int(inside[-1])

    def _path_cumulative_distance(self, xy_path):
        xy_path = np.asarray(xy_path, dtype=float)
        if len(xy_path) == 0:
            return np.array([], dtype=float)
        if len(xy_path) == 1:
            return np.array([0.0], dtype=float)
        diffs = np.diff(xy_path, axis=0)
        seg = np.linalg.norm(diffs, axis=1)
        return np.concatenate(([0.0], np.cumsum(seg)))

    def _index_at_path_distance(self, cumulative_distance, target_distance):
        if len(cumulative_distance) == 0:
            return 0
        idx = int(np.searchsorted(cumulative_distance, float(target_distance), side="left"))
        return int(np.clip(idx, 0, len(cumulative_distance) - 1))

    def _as_xy_array(self, value):
        arr = np.asarray(value, dtype=float).reshape(-1)
        if arr.size < 2 or not np.all(np.isfinite(arr[:2])):
            return None
        return arr[:2]

    def _target_motion_line(self, target_path, target_position=None):
        target_path = np.asarray(target_path, dtype=float)
        points = []
        current_xy = self._as_xy_array(target_position)
        if current_xy is not None:
            points.append(current_xy)
        if target_path.ndim == 2 and target_path.shape[1] >= 2:
            points.extend(target_path[:, :2])
        if len(points) < 2:
            return None, None, None
        points = np.asarray(points, dtype=float)
        valid = np.all(np.isfinite(points), axis=1)
        points = points[valid]
        if len(points) < 2:
            return None, None, None

        origin = points[0]
        direction = points[-1] - origin
        norm = float(np.linalg.norm(direction))
        if norm < 1e-6:
            diffs = np.diff(points, axis=0)
            norms = np.linalg.norm(diffs, axis=1)
            if len(norms) == 0 or np.max(norms) < 1e-6:
                return None, None, points
            direction = diffs[int(np.argmax(norms))]
            norm = float(np.linalg.norm(direction))
        return origin, direction / norm, points

    def _route_defined_yield_geometry(self, target_path, target_position=None):
        ego_global_path = np.asarray(self.feas_ref_states[:self.ref_horizon + 1, :2], dtype=float)
        target_path = np.asarray(target_path, dtype=float)
        target_origin, target_dir, target_support_path = self._target_motion_line(
            target_path,
            target_position=target_position,
        )
        if len(ego_global_path) < 2 or target_origin is None or target_dir is None:
            return None

        if self._yield_geometry is None:
            ego_rel = ego_global_path - target_origin
            target_progress = ego_rel @ target_dir
            projected_target_points = target_origin + target_progress[:, None] * target_dir[None, :]
            line_dist = np.linalg.norm(ego_global_path - projected_target_points, axis=1)
            ego_conflict_idx = int(np.argmin(line_dist))
            target_conflict_point = projected_target_points[ego_conflict_idx]
            min_dist = float(line_dist[ego_conflict_idx])
            cumulative = self._path_cumulative_distance(ego_global_path)
            conflict_s = float(cumulative[ego_conflict_idx])
            stop_s = max(0.0, conflict_s - self.yield_stop_buffer_distance)
            stop_idx = self._index_at_path_distance(cumulative, stop_s)
            steer_s = min(
                conflict_s,
                float(cumulative[stop_idx]) + self.yield_wait_steer_lookahead_distance,
            )
            steer_idx = self._index_at_path_distance(cumulative, steer_s)
            input_idx = int(min(steer_idx, len(self.feas_ref_inputs) - 1))
            self._yield_geometry = {
                "source": "ego_route_target_motion_line",
                "conflict_point": ego_global_path[ego_conflict_idx].copy(),
                "target_conflict_point": target_conflict_point.copy(),
                "conflict_index": int(ego_conflict_idx),
                "stop_point": ego_global_path[stop_idx].copy(),
                "stop_index": int(stop_idx),
                "steer_index": int(steer_idx),
                "conflict_s": conflict_s,
                "stop_s": float(cumulative[stop_idx]),
                "stop_buffer_distance": self.yield_stop_buffer_distance,
                "wait_steer_ref": float(self.feas_ref_inputs[input_idx, 1]),
                "init_min_path_distance": min_dist,
            }

        geometry = dict(self._yield_geometry)
        conflict_point = np.asarray(geometry["conflict_point"], dtype=float)
        target_conflict_point = np.asarray(geometry.get("target_conflict_point", conflict_point), dtype=float)
        target_dist = np.linalg.norm(target_support_path - target_conflict_point, axis=1)
        target_conflict_idx = int(np.argmin(target_dist))
        geometry["target_conflict_index"] = target_conflict_idx
        geometry["min_path_distance"] = float(target_dist[target_conflict_idx])
        geometry["target_enter_index"], geometry["target_exit_index"] = self._zone_interval_from_path(
            target_support_path,
            target_conflict_point,
            self.yield_conflict_radius,
        )
        target_progress_to_conflict = float((target_conflict_point - target_origin) @ target_dir)
        target_step_dist = np.linalg.norm(np.diff(target_support_path, axis=0), axis=1)
        target_speed_est = float(np.mean(target_step_dist[: min(3, len(target_step_dist))]) / max(self.dt, 1e-3)) if len(target_step_dist) else 0.0
        geometry["target_conflict_point"] = target_conflict_point
        geometry["target_distance_to_conflict"] = target_progress_to_conflict
        geometry["target_speed_est"] = target_speed_est
        geometry["target_motion_line_min_distance"] = float(geometry["init_min_path_distance"])
        return geometry

    def _update_observed_target_tracks(self, target_vehicle_positions, N_TV):
        tracks = {}
        if target_vehicle_positions is None:
            self._observed_target_tracks = tracks
            return tracks
        for k in range(min(N_TV, len(target_vehicle_positions))):
            current_xy = self._as_xy_array(target_vehicle_positions[k])
            if current_xy is None:
                continue
            previous = self._observed_target_tracks.get(k, {})
            prev_xy = previous.get("position")
            velocity = None
            speed = 0.0
            if prev_xy is not None:
                delta = current_xy - np.asarray(prev_xy, dtype=float)
                velocity = delta / max(self.dt, 1e-3)
                speed = float(np.linalg.norm(velocity))
            tracks[k] = {
                "position": current_xy,
                "velocity": velocity,
                "speed": speed,
            }
        self._observed_target_tracks = tracks
        return tracks

    def _observed_target_path(self, track):
        position = track.get("position")
        velocity = track.get("velocity")
        if position is None or velocity is None:
            return None
        speed = float(np.linalg.norm(velocity))
        if speed < self.yield_observed_caution_min_target_speed:
            return None
        direction = velocity / max(speed, 1e-6)
        horizon = max(self.N, 2)
        times = np.arange(horizon, dtype=float) * self.dt
        return np.asarray(position, dtype=float)[None, :] + times[:, None] * speed * direction[None, :]

    def _interaction_severity_score(
        self,
        ego_dist_to_conflict,
        ego_ttc_to_conflict,
        target_ttc_to_conflict,
        target_has_priority,
        target_approaching_conflict,
        target_cleared_conflict,
        overlap_risk,
        close_hold,
        allow_priority_yield,
    ):
        """Interpretable severity signal for adaptive risk allocation."""
        activation_distance = max(float(self.yield_activation_distance), 1.0)
        distance_factor = 1.0 - np.clip(max(float(ego_dist_to_conflict), 0.0) / activation_distance, 0.0, 1.0)

        ttc_gap = abs(float(ego_ttc_to_conflict) - float(target_ttc_to_conflict))
        ttc_window = max(2.0 * float(self.yield_ttc_margin), 1.0)
        ttc_factor = 1.0 - np.clip(ttc_gap / ttc_window, 0.0, 1.0)
        if not target_approaching_conflict:
            ttc_factor *= 0.5

        priority_factor = 0.0
        if target_has_priority and allow_priority_yield:
            priority_factor = 1.0
        elif target_approaching_conflict:
            priority_factor = 0.5

        overlap_factor = 1.0 if overlap_risk else (0.8 if close_hold else 0.0)

        if target_cleared_conflict:
            score = 0.0
            phase = "cleared"
        else:
            score = (
                0.35 * distance_factor
                + 0.25 * ttc_factor
                + 0.25 * priority_factor
                + 0.15 * overlap_factor
            )
            score = float(np.clip(score, 0.0, 1.0))
            if score >= 0.75:
                phase = "high"
            elif score >= 0.40:
                phase = "medium"
            else:
                phase = "low"

        return {
            "score": float(score),
            "phase": phase,
            "distance_factor": float(distance_factor),
            "ttc_factor": float(ttc_factor),
            "priority_factor": float(priority_factor),
            "overlap_factor": float(overlap_factor),
            "weights": {
                "distance": 0.35,
                "ttc": 0.25,
                "priority": 0.25,
                "overlap": 0.15,
            },
            "logging_only": True,
        }

    def _adaptive_risk_allocation(self, yield_status):
        profile = (self.risk_profile or "upstream_code").lower()
        upstream_tight = float(smpc.UPSTREAM_CODE_TIGHTENING)
        upstream_prob = float(smpc.UPSTREAM_CODE_TARGET_PROB)
        adaptive_profiles = {
            "adaptive_interaction_severity",
            "adaptive_interaction_severity_no_floor",
            "adaptive_interaction_severity_no_relax",
            "adaptive_interaction_severity_no_phase_awareness",
        }
        if profile not in adaptive_profiles:
            static_tight = float(getattr(self.SMPC, "tight", upstream_tight))
            static_prob = float(getattr(self.SMPC, "target_prob", upstream_prob))
            return {
                "enabled": False,
                "risk_profile": self.risk_profile,
                "tightening": static_tight,
                "target_prob": static_prob,
                "phase": "static_profile",
            }

        raw_score = float(yield_status.get("severity_score", 0.0) or 0.0)
        yield_phase = yield_status.get("phase", "free_drive")
        target_cleared = bool(yield_status.get("target_cleared_conflict", False))
        cfg = getattr(self, "adaptive_risk_config", {}) or {}
        relaxed_tight = float(
            cfg.get("relaxed_after_clearance_tight", 1.2815515655446004)
        )  # Phi^{-1}(0.90), used only after target clearance by default.
        high_tight = float(smpc.PAPER_INTERSECTION_TIGHTENING)
        nominal_to_high_span = high_tight - upstream_tight
        profile_default_preclearance_floor = profile in {
            "adaptive_interaction_severity",
            "adaptive_interaction_severity_no_relax",
        }
        profile_default_post_clearance_relaxation = profile in {
            "adaptive_interaction_severity",
            "adaptive_interaction_severity_no_floor",
        }
        use_preclearance_floor = bool(
            cfg.get("preclearance_floor_enabled", profile_default_preclearance_floor)
        )
        use_post_clearance_relaxation = bool(
            cfg.get(
                "post_clearance_relaxation_enabled",
                profile_default_post_clearance_relaxation,
            )
        )
        variant_name = str(cfg.get("variant_name", profile))
        policy_map = str(
            cfg.get(
                "policy_map",
                (
                    "phase_aware_preclearance_floor"
                    if use_preclearance_floor and use_post_clearance_relaxation
                    else variant_name
                ),
            )
        )
        mild_tightening_scale = float(cfg.get("mild_tightening_scale", 0.35))
        approach_preclearance_floor = float(cfg.get("approach_preclearance_floor", 1.68))
        critical_preclearance_floor = float(cfg.get("critical_preclearance_floor", 1.80))
        near_preclearance_floor = float(cfg.get("near_preclearance_floor", 1.85))
        ego_distance_to_conflict = yield_status.get("ego_distance_to_conflict")
        try:
            ego_distance_to_conflict = float(ego_distance_to_conflict)
        except (TypeError, ValueError):
            ego_distance_to_conflict = None

        phase_floor = 0.0
        if yield_phase == "approach_yield_line":
            phase_floor = float(cfg.get("approach_floor", 0.35))
        elif yield_phase == "hold_yield_line":
            phase_floor = float(cfg.get("hold_floor", 0.45))
        elif yield_phase == "cautious_approach_observed_target":
            phase_floor = float(cfg.get("cautious_floor", 0.25))
        elif yield_phase == "observe_priority_target":
            phase_floor = float(cfg.get("observe_floor", 0.20))

        distance_bucket = "unknown"
        preclearance_tight_floor = None
        preclearance_floor_reason = None
        if ego_distance_to_conflict is not None:
            if ego_distance_to_conflict > 25.0:
                distance_bucket = "far"
            elif ego_distance_to_conflict > 15.0:
                distance_bucket = "approach"
            elif ego_distance_to_conflict > 5.0:
                distance_bucket = "critical"
            else:
                distance_bucket = "near"

        if use_preclearance_floor and not target_cleared and yield_phase != "released_recovery":
            if distance_bucket == "approach":
                preclearance_tight_floor = approach_preclearance_floor
                preclearance_floor_reason = "approach_preclearance"
            elif distance_bucket == "critical":
                preclearance_tight_floor = critical_preclearance_floor
                preclearance_floor_reason = "critical_preclearance"
            elif distance_bucket == "near":
                preclearance_tight_floor = near_preclearance_floor
                preclearance_floor_reason = "near_preclearance"

        if target_cleared or yield_phase == "released_recovery":
            effective_score = 0.0
            risk_scale = 0.0
            if use_post_clearance_relaxation:
                tightening = relaxed_tight
                raw_tightening = relaxed_tight
                risk_phase = "relaxed_after_clearance"
            else:
                tightening = upstream_tight
                raw_tightening = upstream_tight
                risk_phase = "static_after_clearance"
        else:
            effective_score = float(np.clip(max(raw_score, phase_floor), 0.0, 1.0))
            # The rule supervisor already enforces deterministic yielding in approach/hold.
            # Keep chance-constraint tightening mild unless the measured interaction
            # severity itself becomes critical; otherwise these phases become infeasible.
            if effective_score >= 0.85:
                risk_scale = 0.70 + 0.30 * effective_score
            else:
                risk_scale = mild_tightening_scale * effective_score
            raw_tightening = upstream_tight + risk_scale * nominal_to_high_span
            if preclearance_tight_floor is not None:
                tightening = max(raw_tightening, min(float(preclearance_tight_floor), high_tight))
            else:
                tightening = raw_tightening
            if effective_score >= 0.85:
                risk_phase = "high"
            elif effective_score >= 0.45:
                risk_phase = "medium"
            else:
                risk_phase = "nominal"
            if preclearance_tight_floor is not None and tightening > raw_tightening + 1.0e-9:
                risk_phase = f"{risk_phase}_floor"

        preclearance_floor_active = bool(
            preclearance_tight_floor is not None
            and not (target_cleared or yield_phase == "released_recovery")
        )
        preclearance_floor_raised = bool(
            preclearance_floor_active and float(tightening) > float(raw_tightening) + 1.0e-9
        )
        target_prob = float(smpc._standard_normal_cdf(tightening))
        return {
            "enabled": True,
            "risk_profile": self.risk_profile,
            "adaptive_risk_variant": variant_name,
            "phase": risk_phase,
            "policy_map": policy_map,
            "yield_phase": yield_phase,
            "distance_bucket": distance_bucket,
            "ego_distance_to_conflict": ego_distance_to_conflict,
            "raw_severity_score": raw_score,
            "effective_severity_score": effective_score,
            "phase_floor": float(phase_floor),
            "risk_scale": float(risk_scale),
            "preclearance_tight_floor": (
                None if preclearance_tight_floor is None else float(preclearance_tight_floor)
            ),
            "preclearance_floor_reason": preclearance_floor_reason,
            "preclearance_floor_active": preclearance_floor_active,
            "preclearance_floor_applied": preclearance_floor_raised,
            "preclearance_floor_raised_tightening": preclearance_floor_raised,
            "raw_tightening_before_floor": float(raw_tightening),
            "tightening": float(tightening),
            "target_prob": target_prob,
            "target_cleared_conflict": target_cleared,
            "mapping": {
                "relaxed_after_clearance_tight": relaxed_tight,
                "nominal_tight": upstream_tight,
                "high_tight": high_tight,
                "policy_map": policy_map,
                "preclearance_floor_enabled": use_preclearance_floor,
                "post_clearance_relaxation_enabled": use_post_clearance_relaxation,
                "adaptive_risk_variant": variant_name,
                "distance_buckets": {
                    "far": "dconf > 25m",
                    "approach": "15m < dconf <= 25m",
                    "critical": "5m < dconf <= 15m",
                    "near": "dconf <= 5m",
                },
                "approach_preclearance_floor": approach_preclearance_floor,
                "critical_preclearance_floor": critical_preclearance_floor,
                "near_preclearance_floor": near_preclearance_floor,
                "approach_floor": 0.35,
                "hold_floor": 0.45,
                "cautious_floor": 0.25,
                "observe_floor": 0.20,
                "mild_tightening_scale": mild_tightening_scale,
                "critical_score_threshold": 0.85,
            },
        }

    def _rule_yield_smpc_bypass_reason(self, yield_status, speed):
        """Return why the rule supervisor should replace an SMPC solve, if any."""
        if (self.risk_profile or "").lower() not in {
            "adaptive_interaction_severity",
            "adaptive_interaction_severity_no_floor",
            "adaptive_interaction_severity_no_relax",
            "adaptive_interaction_severity_no_phase_awareness",
            "rule_aware_static_risk",
        }:
            return None
        if self.ol_flag or self.obca_flag:
            return None
        if not bool(yield_status.get("priority_from_prediction", False)):
            return None

        phase = yield_status.get("phase")
        if self.yield_supervisor_mode == "reduced_intervention":
            if (
                bool(yield_status.get("active", False))
                and bool(yield_status.get("direct_takeover_required", False))
                and phase in {"approach_yield_line", "hold_yield_line"}
            ):
                return "reduced_intervention_hard_safety_yield_control"
            recovery_reason = self._recovery_handoff_reason(
                yield_status,
                speed,
                prefix="reduced_intervention",
                max_handoff_steps=4,
                speed_threshold=max(1.2, 2.0 * float(self.yield_stop_speed)),
            )
            if recovery_reason is not None:
                return recovery_reason
            return None

        if (
            bool(yield_status.get("active", False))
            and phase in {"approach_yield_line", "hold_yield_line"}
        ):
            return "deterministic_rule_yield_control"

        if not self.yield_recovery_enabled or self.yield_recovery_steps <= 0:
            return None
        if not bool(yield_status.get("target_cleared_conflict", False)):
            return None

        return self._recovery_handoff_reason(
            yield_status,
            speed,
            prefix="deterministic_rule_yield",
        )

    def _recovery_handoff_reason(
        self,
        yield_status,
        speed,
        prefix,
        max_handoff_steps=None,
        speed_threshold=None,
    ):
        """Return a short post-clearance rejoin handoff reason, if needed."""
        phase = yield_status.get("phase")
        default_handoff_steps = min(
            15,
            max(1, int(np.ceil(0.25 * float(self.yield_recovery_steps)))),
        )
        handoff_steps = (
            default_handoff_steps
            if max_handoff_steps is None
            else max(1, min(default_handoff_steps, int(max_handoff_steps)))
        )
        recovery_handoff_start = bool(self._yield_stop_seen and self._yield_stop_active_prev)
        early_recovery_phase = (
            phase == "released_recovery"
            and self._yield_recovery_steps_remaining
            >= max(0, self.yield_recovery_steps - handoff_steps)
        )
        low_speed_limit = (
            max(2.0, 0.5 * float(self.yield_recovery_speed))
            if speed_threshold is None
            else float(speed_threshold)
        )
        low_speed_handoff = float(speed) <= low_speed_limit
        if (recovery_handoff_start or early_recovery_phase) and low_speed_handoff:
            return f"{prefix}_recovery_handoff"
        return None

    def _should_bypass_smpc_for_rule_yield(self, yield_status, speed):
        """Skip SMPC solves for deterministic rule-supervised yield steps."""
        return self._rule_yield_smpc_bypass_reason(yield_status, speed) is not None

    def _evaluate_yield_geometry(
        self,
        x,
        y,
        speed,
        ego_global_path,
        ego_global_s,
        ego_global_idx,
        target_idx,
        mode,
        target_path,
        geometry,
        valid_flags,
        source,
        allow_priority_yield,
    ):
        ego_route_s = float(ego_global_s[ego_global_idx])
        conflict_point = np.asarray(geometry["conflict_point"], dtype=float)
        stop_point = np.asarray(geometry["stop_point"], dtype=float)
        target_conflict_point = np.asarray(geometry["target_conflict_point"], dtype=float)
        conflict_s = float(geometry["conflict_s"])
        stop_s = float(geometry["stop_s"])
        target_conflict_idx = int(geometry["target_conflict_index"])
        target_enter_idx = geometry["target_enter_index"]
        target_exit_idx = geometry["target_exit_index"]
        target_distance_to_conflict = float(geometry["target_distance_to_conflict"])
        target_speed_est = float(geometry["target_speed_est"])
        target_motion_line_min_distance = float(geometry["target_motion_line_min_distance"])
        ego_dist_to_stop = stop_s - ego_route_s
        ego_dist_to_conflict = conflict_s - ego_route_s
        ego_ttc_to_stop = max(ego_dist_to_stop, 0.0) / max(float(speed), max(self.yield_stop_speed, 0.2))
        ego_ttc_to_conflict = max(ego_dist_to_conflict, 0.0) / max(float(speed), max(self.yield_stop_speed, 0.2))
        target_ttc_to_conflict = max(target_distance_to_conflict - self.yield_conflict_radius, 0.0) / max(
            target_speed_est,
            max(self.yield_stop_speed, 0.2),
        )
        target_nominally_cleared_conflict = target_distance_to_conflict < -self.yield_conflict_radius
        ego_required_clearance = self.yield_conflict_radius + self.yield_footprint_clearance_margin
        target_release_clearance_distance = self.yield_conflict_radius + max(
            self.yield_release_clearance_margin,
            self.yield_footprint_clearance_margin,
        )
        target_cleared_conflict = target_distance_to_conflict < -target_release_clearance_distance
        target_approaching_conflict = (
            target_motion_line_min_distance <= self.yield_conflict_radius
            and not target_cleared_conflict
        )
        if target_enter_idx is None:
            target_enter_time = target_ttc_to_conflict
            target_exit_time = target_ttc_to_conflict + (2.0 * self.yield_conflict_radius / max(target_speed_est, 0.2))
            target_has_priority = target_approaching_conflict
        else:
            target_enter_time = float(target_enter_idx) * self.dt
            target_exit_time = float(target_exit_idx) * self.dt
            target_has_priority = target_approaching_conflict
        priority_confirmed = bool(target_has_priority and allow_priority_yield)

        max_brake = max(abs(self.yield_stop_decel), 1e-3)
        brake_distance = (float(speed) ** 2) / (2.0 * max_brake)
        brake_activation_distance = brake_distance + self.yield_brake_distance_margin
        braking_distance_required = ego_dist_to_stop <= brake_activation_distance
        emergency_conflict_clearance = max(
            self.yield_conflict_radius + self.yield_emergency_conflict_margin,
            ego_required_clearance,
        )
        emergency_safe_stop_s = conflict_s - emergency_conflict_clearance
        ego_dist_to_emergency_stop = emergency_safe_stop_s - ego_route_s
        emergency_braking_distance_required = ego_dist_to_emergency_stop <= brake_activation_distance
        ego_inside_footprint_clearance = ego_dist_to_conflict < ego_required_clearance
        reduced_max_brake = max(
            abs(self.yield_emergency_decel if self.yield_emergency_brake_enabled else self.yield_stop_decel),
            1e-3,
        )
        reduced_brake_distance = (float(speed) ** 2) / (2.0 * reduced_max_brake)
        reduced_brake_activation_distance = reduced_brake_distance + min(
            self.yield_brake_distance_margin,
            0.5,
        )
        reduced_emergency_braking_distance_required = (
            ego_dist_to_emergency_stop <= reduced_brake_activation_distance
        )
        reduced_conflict_hold = (
            target_has_priority
            and ego_dist_to_conflict <= max(ego_required_clearance + 0.75, self.yield_conflict_radius + 1.0)
        )
        overlap_risk = (
            target_has_priority
            and target_enter_time <= ego_ttc_to_conflict + self.yield_ttc_margin
            and target_exit_time >= ego_ttc_to_stop - self.yield_ttc_margin
        )
        close_hold = (
            target_has_priority
            and ego_dist_to_stop <= self.yield_hold_distance
        )
        approaching_stop_line = ego_dist_to_stop <= self.yield_activation_distance
        not_far_past_conflict = ego_dist_to_conflict >= -self.yield_conflict_radius
        observed_caution_distance_trigger = ego_dist_to_conflict <= self.yield_observed_caution_distance
        observed_caution_braking_trigger = braking_distance_required
        hard_stop_target_close = target_distance_to_conflict <= self.yield_hard_stop_target_distance
        hard_stop_conflict_close = ego_dist_to_conflict <= self.yield_hard_stop_conflict_distance
        hard_stop_stop_line_braking = braking_distance_required and priority_confirmed
        cautious_candidate = (
            self.yield_observed_caution_enabled
            and not allow_priority_yield
            and source == "observed_track"
            and target_approaching_conflict
            and target_speed_est >= self.yield_observed_caution_min_target_speed
            and (observed_caution_distance_trigger or observed_caution_braking_trigger)
            and not_far_past_conflict
        )
        if self.yield_supervisor_mode == "reduced_intervention":
            reduced_overlap_guard = (
                overlap_risk and ego_dist_to_conflict <= self.yield_activation_distance
            )
            active = (
                allow_priority_yield
                and target_has_priority
                and not target_cleared_conflict
                and not_far_past_conflict
                and (
                    reduced_emergency_braking_distance_required
                    or reduced_conflict_hold
                    or reduced_overlap_guard
                    or ego_inside_footprint_clearance
                )
            ) or (
                cautious_candidate
                and (
                    reduced_emergency_braking_distance_required
                    or ego_dist_to_conflict <= self.yield_activation_distance
                )
            )
            hard_stop_required = (
                active
                and not target_cleared_conflict
                and (
                    reduced_emergency_braking_distance_required
                    or ego_inside_footprint_clearance
                    or reduced_conflict_hold
                )
            )
            reduced_direct_takeover_required = bool(hard_stop_required)
            reduced_direct_takeover_margin = 0.0
            direct_takeover_required = bool(hard_stop_required)
        else:
            active = (
                allow_priority_yield
                and target_has_priority
                and approaching_stop_line
                and not_far_past_conflict
                and (braking_distance_required or overlap_risk or close_hold)
            ) or cautious_candidate
            hard_stop_required = (
                active
                and not target_cleared_conflict
                and (hard_stop_stop_line_braking or hard_stop_target_close or hard_stop_conflict_close)
            )
            reduced_direct_takeover_required = False
            reduced_direct_takeover_margin = 0.0
            direct_takeover_required = bool(hard_stop_required)
        if active and not allow_priority_yield:
            phase = "cautious_approach_observed_target"
        elif active and ego_dist_to_stop <= self.yield_hold_distance:
            phase = "hold_yield_line"
        elif active:
            phase = "approach_yield_line"
        elif target_has_priority and ego_dist_to_stop > self.yield_activation_distance:
            phase = "observe_priority_target"
        elif self._yield_recovery_steps_remaining > 0:
            phase = "released_recovery"
        else:
            phase = "free_drive"

        if active and not allow_priority_yield and observed_caution_braking_trigger:
            reason = "observed_target_braking_distance_caution"
        elif active and not allow_priority_yield:
            reason = "observed_target_cautious_approach"
        elif active and braking_distance_required:
            reason = "braking_distance_yield"
        elif active:
            reason = "target_has_priority_before_stop_line"
        else:
            reason = "no_active_yield_needed"

        interaction_severity = self._interaction_severity_score(
            ego_dist_to_conflict,
            ego_ttc_to_conflict,
            target_ttc_to_conflict,
            target_has_priority,
            target_approaching_conflict,
            target_cleared_conflict,
            overlap_risk,
            close_hold,
            allow_priority_yield,
        )

        return {
            "active": bool(active),
            "supervisor_mode": self.yield_supervisor_mode,
            "phase": phase,
            "priority_rule": "turning_gives_way_to_oncoming_straight",
            "reason": reason,
            "severity_score": interaction_severity["score"],
            "severity_phase": interaction_severity["phase"],
            "interaction_severity": interaction_severity,
            "target_index": int(target_idx),
            "target_mode": int(mode),
            "prediction_valid": valid_flags,
            "prediction_source": source,
            "priority_from_prediction": bool(allow_priority_yield),
            "priority_confirmed": bool(priority_confirmed),
            "cautious_candidate": bool(cautious_candidate),
            "observed_caution_distance_trigger": bool(observed_caution_distance_trigger),
            "observed_caution_braking_trigger": bool(observed_caution_braking_trigger),
            "hard_stop_required": bool(hard_stop_required),
            "direct_takeover_required": bool(direct_takeover_required),
            "hard_stop_stop_line_braking": bool(hard_stop_stop_line_braking),
            "hard_stop_target_close": bool(hard_stop_target_close),
            "hard_stop_conflict_close": bool(hard_stop_conflict_close),
            "hard_stop_target_distance_threshold": float(self.yield_hard_stop_target_distance),
            "hard_stop_conflict_distance_threshold": float(self.yield_hard_stop_conflict_distance),
            "min_path_distance": float(geometry["min_path_distance"]),
            "conflict_point": conflict_point.tolist(),
            "target_conflict_point": target_conflict_point.tolist(),
            "stop_point": stop_point.tolist(),
            "yield_geometry_source": geometry["source"],
            "ego_global_index": int(ego_global_idx),
            "ego_route_s": ego_route_s,
            "ego_conflict_index": int(geometry["conflict_index"]),
            "ego_stop_index": int(geometry["stop_index"]),
            "target_conflict_index": int(target_conflict_idx),
            "wait_steer_index": int(geometry["steer_index"]),
            "wait_steer_ref": float(geometry["wait_steer_ref"]),
            "stop_s": stop_s,
            "conflict_s": conflict_s,
            "ego_distance_to_stop": ego_dist_to_stop,
            "ego_distance_to_conflict": ego_dist_to_conflict,
            "ego_ttc": ego_ttc_to_conflict,
            "ego_ttc_to_stop": ego_ttc_to_stop,
            "brake_distance": brake_distance,
            "brake_activation_distance": brake_activation_distance,
            "brake_distance_margin": self.yield_brake_distance_margin,
            "braking_distance_required": bool(braking_distance_required),
            "reduced_brake_distance": float(reduced_brake_distance),
            "reduced_brake_activation_distance": float(reduced_brake_activation_distance),
            "reduced_emergency_braking_distance_required": bool(
                reduced_emergency_braking_distance_required
            ),
            "reduced_conflict_hold": bool(reduced_conflict_hold),
            "reduced_direct_takeover_required": bool(reduced_direct_takeover_required),
            "reduced_direct_takeover_margin": float(reduced_direct_takeover_margin),
            "ego_required_clearance": float(ego_required_clearance),
            "ego_inside_footprint_clearance": bool(ego_inside_footprint_clearance),
            "footprint_clearance_margin": float(self.yield_footprint_clearance_margin),
            "emergency_conflict_clearance": float(emergency_conflict_clearance),
            "emergency_safe_stop_s": float(emergency_safe_stop_s),
            "ego_distance_to_emergency_stop": float(ego_dist_to_emergency_stop),
            "emergency_braking_distance_required": bool(emergency_braking_distance_required),
            "target_distance_to_conflict": target_distance_to_conflict,
            "target_ttc_to_conflict": target_ttc_to_conflict,
            "target_speed_est": target_speed_est,
            "target_motion_line_min_distance": target_motion_line_min_distance,
            "target_approaching_conflict": bool(target_approaching_conflict),
            "target_nominally_cleared_conflict": bool(target_nominally_cleared_conflict),
            "target_cleared_conflict": bool(target_cleared_conflict),
            "target_release_clearance_distance": float(target_release_clearance_distance),
            "target_release_clearance_margin": float(self.yield_release_clearance_margin),
            "target_enter_time": target_enter_time,
            "target_exit_time": target_exit_time,
            "target_has_priority": bool(priority_confirmed),
            "observed_target_potential_priority": bool(target_approaching_conflict and not allow_priority_yield),
            "overlap_risk": bool(overlap_risk),
            "close_hold": bool(close_hold),
            "approaching_stop_line": bool(approaching_stop_line),
            "not_far_past_conflict": bool(not_far_past_conflict),
        }

    def _rule_aware_yield_decision(
        self,
        x,
        y,
        speed,
        t_ref_new,
        target_vehicle_gmm_preds,
        target_vehicle_mode_probs,
        target_vehicle_positions,
        target_vehicle_valid_pred,
        N_TV,
    ):
        status = {
            "enabled": self.yield_stop_enabled,
            "active": False,
            "reason": None,
            "target_index": None,
            "target_mode": None,
        }
        if not self.yield_stop_enabled:
            status["reason"] = "disabled"
            return status
        if self.ol_flag:
            status["reason"] = "open_loop_policy"
            return status
        observed_tracks = self._update_observed_target_tracks(target_vehicle_positions, N_TV)
        if target_vehicle_valid_pred is not None:
            valid_flags = [bool(v) for v in target_vehicle_valid_pred[:N_TV]]
        else:
            valid_flags = [True] * N_TV
        has_valid_prediction = any(valid_flags)

        ego_global_path = np.asarray(self.feas_ref_states[:self.ref_horizon + 1, :2], dtype=float)
        ego_global_s = self._path_cumulative_distance(ego_global_path)
        if len(ego_global_path) < 2 or len(ego_global_s) < 2:
            status["reason"] = "short_global_ego_reference"
            status["prediction_valid"] = valid_flags
            return status
        ego_global_idx = int(np.argmin(np.linalg.norm(ego_global_path - np.array([x, y], dtype=float), axis=1)))

        if N_TV <= 0 or target_vehicle_gmm_preds is None:
            status["reason"] = "no_target_prediction"
            status["prediction_valid"] = valid_flags
            return status

        means_all = np.asarray(target_vehicle_gmm_preds[0])
        if means_all.size == 0:
            status["reason"] = "empty_target_prediction"
            status["prediction_valid"] = valid_flags
            return status

        best = None
        if has_valid_prediction:
            for k in range(min(N_TV, len(means_all))):
                if k < len(valid_flags) and not valid_flags[k]:
                    continue
                target_modes = np.asarray(means_all[k])
                if target_modes.ndim < 3:
                    continue
                if target_vehicle_mode_probs is not None:
                    probs = np.asarray(target_vehicle_mode_probs[k], dtype=float)
                    mode = int(np.nanargmax(probs)) if probs.size else 0
                    mode = min(mode, target_modes.shape[0] - 1)
                else:
                    mode = 0
                target_path = np.asarray(target_modes[mode, :, :2], dtype=float)
                if len(target_path) < 2:
                    continue
                target_position = None
                if target_vehicle_positions is not None and k < len(target_vehicle_positions):
                    target_position = target_vehicle_positions[k]
                geometry = self._route_defined_yield_geometry(
                    target_path,
                    target_position=target_position,
                )
                if geometry is None:
                    continue
                target_priority_distance = geometry["target_distance_to_conflict"]
                release_clearance_distance = self.yield_conflict_radius + max(
                    self.yield_release_clearance_margin,
                    self.yield_footprint_clearance_margin,
                )
                if target_priority_distance < -release_clearance_distance:
                    target_priority_distance = float("inf")
                candidate = (target_priority_distance, k, mode, target_path, geometry, "prediction", True)
                if best is None or candidate[0] < best[0]:
                    best = candidate
        else:
            for k, track in observed_tracks.items():
                target_path = self._observed_target_path(track)
                if target_path is None:
                    continue
                geometry = self._route_defined_yield_geometry(
                    target_path,
                    target_position=track.get("position"),
                )
                if geometry is None:
                    continue
                target_priority_distance = geometry["target_distance_to_conflict"]
                release_clearance_distance = self.yield_conflict_radius + max(
                    self.yield_release_clearance_margin,
                    self.yield_footprint_clearance_margin,
                )
                if target_priority_distance < -release_clearance_distance:
                    target_priority_distance = float("inf")
                candidate = (target_priority_distance, k, 0, target_path, geometry, "observed_track", False)
                if best is None or candidate[0] < best[0]:
                    best = candidate

        if best is None:
            status["reason"] = "no_valid_target_path" if has_valid_prediction else "no_valid_target_prediction"
            status["prediction_valid"] = valid_flags
            if observed_tracks:
                status["observed_tracks"] = {
                    int(k): {
                        "speed": float(v.get("speed", 0.0)),
                        "has_velocity": v.get("velocity") is not None,
                    }
                    for k, v in observed_tracks.items()
                }
            return status

        _, target_idx, mode, target_path, geometry, source, allow_priority_yield = best
        status.update(self._evaluate_yield_geometry(
            x,
            y,
            speed,
            ego_global_path,
            ego_global_s,
            ego_global_idx,
            target_idx,
            mode,
            target_path,
            geometry,
            valid_flags,
            source,
            allow_priority_yield,
        ))
        self._rule_yield_phase = status.get("phase", "free_drive")
        return status

    def _reduced_recovery_stabilization_active(
        self,
        lateral_error=None,
        heading_error=None,
        completion_metrics=None,
    ):
        """Keep reduced mode from drifting near route completion after target clearance."""
        if self.yield_supervisor_mode != "reduced_intervention":
            return False
        if not (self.yield_recovery_enabled and self._yield_recovery_steps_remaining > 0):
            return False
        lateral_abs = abs(float(lateral_error)) if lateral_error is not None else 0.0
        heading_abs = abs(float(heading_error)) if heading_error is not None else 0.0
        s_after_goal = None
        if completion_metrics is not None:
            s_after_goal = completion_metrics.get("s_after_route_goal")
        near_goal = bool(s_after_goal is not None and float(s_after_goal) >= -8.0)
        lateral_guard = max(2.0, 0.5 * float(self.completion_lateral_error))
        heading_guard = max(0.12, 0.75 * float(self.completion_heading_error))
        return bool(near_goal or lateral_abs >= lateral_guard or heading_abs >= heading_guard)

    def _apply_rule_aware_yield_control(
        self,
        yield_status,
        u0,
        v_des,
        speed,
        lateral_error=None,
        heading_error=None,
        completion_metrics=None,
    ):
        u0_flat = np.asarray(u0, dtype=float).reshape(-1)
        v_des_float = float(np.asarray(v_des, dtype=float).reshape(-1)[0])

        if yield_status.get("active"):
            distance_to_stop = max(float(yield_status.get("ego_distance_to_stop", 0.0)), 0.5)
            required_stop_decel = -(float(speed) ** 2) / (2.0 * distance_to_stop)
            hard_stop_required = bool(yield_status.get("hard_stop_required", False))
            direct_takeover_required = bool(yield_status.get("direct_takeover_required", hard_stop_required))
            if self.yield_supervisor_mode == "reduced_intervention" and not direct_takeover_required:
                guard_speed = (
                    self.yield_creep_speed
                    if float(yield_status.get("ego_distance_to_conflict", np.inf))
                    <= max(float(yield_status.get("ego_required_clearance", self.yield_conflict_radius)), self.yield_conflict_radius)
                    else self.yield_caution_speed
                )
                v_des_new = min(v_des_float, float(guard_speed))
                self._yield_last_applied_accel = None
                self._yield_stop_active_prev = False
                yield_status["applied"] = {
                    "mode": "preclearance_reference_only_guard",
                    "a_des": float(u0_flat[0]),
                    "df_des": float(u0_flat[1]) if len(u0_flat) > 1 else 0.0,
                    "v_des": float(v_des_new),
                    "required_stop_decel": float(required_stop_decel),
                    "hard_stop_required": bool(hard_stop_required),
                    "direct_takeover_required": False,
                    "guard_speed": float(guard_speed),
                    "note": "SMPC final control preserved; reduced supervisor only shaped reference/speed target.",
                }
                yield_status["recovery"] = {
                    "enabled": self.yield_recovery_enabled,
                    "active": False,
                    "started": False,
                    "applied": None,
                    "steps_remaining_after": int(self._yield_recovery_steps_remaining),
                }
                return u0_flat, v_des_new, yield_status
            nominal_a_des = max(
                self.yield_stop_decel,
                min(float(u0_flat[0]), required_stop_decel),
            )
            emergency_active = bool(
                self.yield_emergency_brake_enabled
                and hard_stop_required
                and not bool(yield_status.get("target_cleared_conflict", False))
                and bool(yield_status.get("braking_distance_required", False))
                and float(yield_status.get("ego_distance_to_conflict", 0.0)) >= -self.yield_conflict_radius
            )
            previous_accel = (
                float(self._yield_last_applied_accel)
                if self._yield_last_applied_accel is not None
                else float(u0_flat[0])
            )
            max_accel_drop = self.yield_emergency_jerk_limit * self.dt
            emergency_unlimited_a_des = self.yield_emergency_decel if emergency_active else nominal_a_des
            emergency_jerk_limited_a_des = max(
                self.yield_emergency_decel,
                previous_accel - max_accel_drop,
            )
            if emergency_active:
                # Never let the jerk limiter make emergency braking weaker than
                # the nominal yield brake computed above.
                a_des = min(nominal_a_des, emergency_jerk_limited_a_des)
            else:
                if hard_stop_required:
                    a_des = nominal_a_des
                else:
                    rolling_speed = (
                        self.yield_creep_speed
                        if float(yield_status.get("ego_distance_to_stop", np.inf)) <= self.yield_hold_distance
                        else self.yield_caution_speed
                    )
                    if float(speed) > rolling_speed + 0.25:
                        a_des = max(
                            self.yield_caution_decel,
                            min(float(u0_flat[0]), self.yield_caution_decel),
                        )
                    else:
                        a_des = max(0.0, float(u0_flat[0]))
            wait_steer_ref = float(yield_status.get("wait_steer_ref", 0.0)) * self.yield_wait_steer_gain
            wait_steer_ref = float(np.clip(wait_steer_ref, self.SMPC.DF_MIN, self.SMPC.DF_MAX))
            damped_steer = self.yield_steer_damping * float(u0_flat[1])
            df_des = wait_steer_ref if abs(wait_steer_ref) >= 0.03 else damped_steer
            steering_mode = (
                "wait_steer_ref"
                if abs(wait_steer_ref) >= 0.03
                else "damped_steer"
            )
            df_des = float(np.clip(df_des, self.SMPC.DF_MIN, self.SMPC.DF_MAX))
            u0_new = np.array([a_des, df_des], dtype=float)
            if hard_stop_required:
                v_des_new = min(v_des_float, self.yield_stop_speed)
            else:
                rolling_speed = (
                    self.yield_creep_speed
                    if float(yield_status.get("ego_distance_to_stop", np.inf)) <= self.yield_hold_distance
                    else self.yield_caution_speed
                )
                v_des_new = min(max(v_des_float, rolling_speed), rolling_speed)
            self.control_prev = u0_new
            self._yield_last_applied_accel = float(u0_new[0])
            self._yield_stop_seen = True
            self._yield_stop_active_prev = True
            self._yield_recovery_steps_remaining = 0
            if not hard_stop_required:
                applied_mode = "rolling_caution_yield_control"
            elif yield_status.get("phase") == "cautious_approach_observed_target":
                applied_mode = "hard_stop_observed_target_control"
            else:
                applied_mode = "hard_stop_yield_line_control"
            yield_status["applied"] = {
                "mode": applied_mode,
                "a_des": float(u0_new[0]),
                "df_des": float(u0_new[1]),
                "v_des": float(v_des_new),
                "required_stop_decel": float(required_stop_decel),
                "nominal_a_des": float(nominal_a_des),
                "hard_stop_required": bool(hard_stop_required),
                "direct_takeover_required": bool(direct_takeover_required),
                "rolling_speed_target": float(
                    self.yield_stop_speed
                    if hard_stop_required
                    else (
                        self.yield_creep_speed
                        if float(yield_status.get("ego_distance_to_stop", np.inf)) <= self.yield_hold_distance
                        else self.yield_caution_speed
                    )
                ),
                "wait_steer_ref": float(wait_steer_ref),
                "damped_steer": float(damped_steer),
                "steering_mode": steering_mode,
                "emergency_brake": {
                    "enabled": self.yield_emergency_brake_enabled,
                    "active": bool(emergency_active),
                    "reason": (
                        "target_not_cleared_and_braking_distance_required"
                        if emergency_active
                        else "not_required"
                    ),
                    "decel_limit": float(self.yield_emergency_decel),
                    "jerk_limit": float(self.yield_emergency_jerk_limit),
                    "dt": float(self.dt),
                    "max_accel_drop_per_step": float(max_accel_drop),
                    "previous_accel": float(previous_accel),
                    "unlimited_a_des": float(emergency_unlimited_a_des),
                    "jerk_limited_a_des": float(emergency_jerk_limited_a_des),
                    "final_a_des": float(u0_new[0]),
                    "safe_conflict_clearance": float(
                        yield_status.get("emergency_conflict_clearance", np.nan)
                    ),
                    "ego_distance_to_emergency_stop": float(
                        yield_status.get("ego_distance_to_emergency_stop", np.nan)
                    ),
                    "emergency_braking_distance_required": bool(
                        yield_status.get("emergency_braking_distance_required", False)
                    ),
                },
            }
            yield_status["recovery"] = {
                "enabled": self.yield_recovery_enabled,
                "active": False,
                "started": False,
                "applied": None,
                "steps_remaining_after": int(self._yield_recovery_steps_remaining),
            }
            return u0_new, v_des_new, yield_status

        yield_status["applied"] = None
        recovery_started = False
        if (
            self.yield_recovery_enabled
            and self._yield_stop_seen
            and self._yield_stop_active_prev
            and self.yield_recovery_steps > 0
        ):
            self._yield_recovery_steps_remaining = max(
                self._yield_recovery_steps_remaining,
                self.yield_recovery_steps,
            )
            recovery_started = True

        recovery_active_for_control = bool(
            self.yield_recovery_enabled and self._yield_recovery_steps_remaining > 0
        )
        recovery_status = {
            "enabled": self.yield_recovery_enabled,
            "started": recovery_started,
            "active": recovery_active_for_control,
            "steps_remaining_before": int(self._yield_recovery_steps_remaining),
            "speed": self.yield_recovery_speed,
            "accel": self.yield_recovery_accel,
        }
        if recovery_active_for_control:
            reduced_stabilization = self._reduced_recovery_stabilization_active(
                lateral_error=lateral_error,
                heading_error=heading_error,
                completion_metrics=completion_metrics,
            )
            reduced_mode = self.yield_supervisor_mode == "reduced_intervention"
            reduced_handoff_steps = 4
            recovery_steps_elapsed = max(
                0,
                int(self.yield_recovery_steps) - int(self._yield_recovery_steps_remaining),
            )
            reduced_control_handoff = bool(
                reduced_mode
                and (
                    recovery_started
                    or recovery_steps_elapsed < reduced_handoff_steps
                    or reduced_stabilization
                )
            )
            if reduced_mode and not reduced_control_handoff:
                u0_new = np.asarray(u0, dtype=float).reshape(-1)
                v_des_new = v_des
                self._yield_last_applied_accel = None
                self._yield_recovery_steps_remaining = max(
                    0,
                    self._yield_recovery_steps_remaining - 1,
                )
                self._rule_yield_phase = "released_recovery"
                yield_status["phase"] = "released_recovery"
                recovery_status["applied"] = {
                    "mode": "post_yield_reference_only",
                    "reduced_stabilization": False,
                    "reduced_control_handoff": False,
                    "recovery_steps_elapsed": int(recovery_steps_elapsed),
                    "reduced_handoff_steps": int(reduced_handoff_steps),
                    "v_des": float(np.asarray(v_des_new, dtype=float).reshape(-1)[0]),
                }
                recovery_status["steps_remaining_after"] = int(self._yield_recovery_steps_remaining)
                self._yield_stop_active_prev = False
                yield_status["recovery"] = recovery_status
                return u0_new, v_des_new, yield_status
            recovery_speed_cap = (
                min(float(self.yield_recovery_speed), 4.0)
                if reduced_stabilization
                else float(self.yield_recovery_speed)
            )
            recovery_accel_cap = (
                min(float(self.yield_recovery_accel), 0.8)
                if reduced_stabilization
                else float(self.yield_recovery_accel)
            )
            restart_accel = 0.0
            if float(speed) < recovery_speed_cap:
                restart_accel = min(
                    recovery_accel_cap,
                    max(0.2, 0.4 * (recovery_speed_cap - float(speed))),
                )
            elif reduced_stabilization:
                restart_accel = min(0.0, float(u0_flat[0]))
            u0_new = np.array([
                min(
                    recovery_accel_cap,
                    max(float(u0_flat[0]), restart_accel),
                ),
                float(u0_flat[1]),
            ], dtype=float)
            if reduced_stabilization and float(speed) > recovery_speed_cap:
                u0_new[0] = min(float(u0_new[0]), 0.0)
            v_des_new = min(
                max(v_des_float, self.yield_stop_speed),
                recovery_speed_cap,
            )
            self.control_prev = u0_new
            self._yield_last_applied_accel = float(u0_new[0])
            self._yield_recovery_steps_remaining = max(
                0,
                self._yield_recovery_steps_remaining - 1,
            )
            self._rule_yield_phase = "released_recovery"
            yield_status["phase"] = "released_recovery"
            recovery_status["applied"] = {
                "mode": "post_yield_recovery",
                "a_des": float(u0_new[0]),
                "df_des": float(u0_new[1]),
                "v_des": float(v_des_new),
                "restart_accel": float(restart_accel),
                "reduced_stabilization": bool(reduced_stabilization),
                "reduced_control_handoff": bool(reduced_control_handoff),
                "recovery_steps_elapsed": int(recovery_steps_elapsed),
                "reduced_handoff_steps": int(reduced_handoff_steps),
                "recovery_speed_cap": float(recovery_speed_cap),
                "recovery_accel_cap": float(recovery_accel_cap),
            }
        else:
            u0_new = np.asarray(u0, dtype=float).reshape(-1)
            v_des_new = v_des
            recovery_status["applied"] = None
            self._yield_last_applied_accel = None
        recovery_status["steps_remaining_after"] = int(self._yield_recovery_steps_remaining)
        self._yield_stop_active_prev = False
        yield_status["recovery"] = recovery_status
        return u0_new, v_des_new, yield_status

    def _apply_rule_aware_reference_profile(
        self,
        t_ref_new,
        yield_status,
        recovery_active_for_reference,
        lateral_error=None,
        heading_error=None,
        completion_metrics=None,
    ):
        """Shape the pre-solve reference without making the SMPC problem infeasible.

        During yield, the reference should decelerate toward the yield line instead of
        instantly becoming a near-stop trajectory. During recovery, the reference stays
        capped at the low rejoin speed.
        """
        yield_active = bool(yield_status.get("active"))
        ref_status = {
            "mode": None,
            "yield_active": yield_active,
            "recovery_active": recovery_active_for_reference,
            "speed_cap": None,
            "accel_upper_bound": None,
            "profile": None,
        }
        post_clearance_alignment_active = bool(
            yield_status.get("target_cleared_conflict", False)
            and self.exit_alignment_post_clearance_goal_window > 0.0
        )
        if not yield_active and not recovery_active_for_reference and not post_clearance_alignment_active:
            return ref_status

        self.feas_ref_states_new = np.asarray(self.feas_ref_states_new, dtype=float).copy()
        self.feas_ref_inputs_new = np.asarray(self.feas_ref_inputs_new, dtype=float).copy()

        if yield_active:
            start_idx = int(max(0, min(t_ref_new, len(self.feas_ref_states_new) - 1)))
            hard_stop_required = bool(yield_status.get("hard_stop_required", False))
            if (
                self.yield_supervisor_mode == "reduced_intervention"
                and not bool(yield_status.get("direct_takeover_required", hard_stop_required))
            ):
                hard_stop_required = False
            if not hard_stop_required:
                rolling_speed = (
                    self.yield_creep_speed
                    if float(yield_status.get("ego_distance_to_stop", np.inf)) <= self.yield_hold_distance
                    else self.yield_caution_speed
                )
                self.feas_ref_states_new[start_idx:, 3] = np.minimum(
                    self.feas_ref_states_new[start_idx:, 3],
                    rolling_speed,
                )
                if start_idx > 0:
                    self.feas_ref_states_new[:start_idx, 3] = np.minimum(
                        self.feas_ref_states_new[:start_idx, 3],
                        rolling_speed,
                    )
                self.feas_ref_inputs_new[:, 0] = np.clip(
                    self.feas_ref_inputs_new[:, 0],
                    self.yield_caution_decel,
                    self.yield_recovery_accel,
                )
                ref_status.update({
                    "mode": "rolling_caution_yield_reference",
                    "speed_cap": float(rolling_speed),
                    "accel_upper_bound": float(self.yield_recovery_accel),
                    "profile": {
                        "type": "rolling_caution_or_creep",
                        "hard_stop_required": False,
                        "ego_distance_to_stop": float(yield_status.get("ego_distance_to_stop", np.nan)),
                        "rolling_speed": float(rolling_speed),
                        "caution_speed": float(self.yield_caution_speed),
                        "creep_speed": float(self.yield_creep_speed),
                        "caution_decel": float(self.yield_caution_decel),
                    },
                })
                return ref_status
            reference_xy = self.feas_ref_states_new[start_idx:, :2]
            if len(reference_xy) >= 2:
                step_dist = np.linalg.norm(np.diff(reference_xy, axis=0), axis=1)
                path_dist_from_ego = np.concatenate(([0.0], np.cumsum(step_dist)))
            else:
                path_dist_from_ego = np.array([0.0])
            distance_to_stop = max(float(yield_status.get("ego_distance_to_stop", 0.0)), 0.0)
            remaining_to_stop = np.maximum(distance_to_stop - path_dist_from_ego, 0.0)
            max_decel = max(abs(self.yield_reference_decel), 1e-3)
            speed_profile = np.sqrt(
                self.yield_reference_min_speed ** 2 + 2.0 * max_decel * remaining_to_stop
            )
            speed_profile = np.maximum(speed_profile, self.yield_reference_min_speed)
            end_idx = start_idx + len(speed_profile)
            self.feas_ref_states_new[start_idx:end_idx, 3] = np.minimum(
                self.feas_ref_states_new[start_idx:end_idx, 3],
                speed_profile,
            )
            if start_idx > 0:
                self.feas_ref_states_new[:start_idx, 3] = np.minimum(
                    self.feas_ref_states_new[:start_idx, 3],
                    speed_profile[0],
                )
            self.feas_ref_inputs_new[:, 0] = np.clip(
                self.feas_ref_inputs_new[:, 0],
                self.yield_stop_decel,
                0.0,
            )
            ref_status.update({
                "mode": "yield_line_deceleration_reference",
                "speed_cap": float(speed_profile[0]),
                "accel_upper_bound": 0.0,
                "profile": {
                    "type": "braking_distance",
                    "distance_to_stop": float(distance_to_stop),
                    "start_speed_cap": float(speed_profile[0]),
                    "end_speed_cap": float(speed_profile[-1]),
                    "stop_speed": float(self.yield_stop_speed),
                    "reference_min_speed": float(self.yield_reference_min_speed),
                    "reference_decel": float(self.yield_reference_decel),
                    "decel": float(self.yield_stop_decel),
                },
            })
            return ref_status

        if post_clearance_alignment_active:
            goal_xy = np.array([self.goal_location.x, -self.goal_location.y], dtype=float)
            ref_xy = np.asarray(self.feas_ref_states_new[:, :2], dtype=float)
            goal_dist = np.linalg.norm(ref_xy - goal_xy.reshape(1, 2), axis=1)
            mask = goal_dist <= self.exit_alignment_post_clearance_goal_window
            if np.any(mask):
                self.feas_ref_states_new[mask, 3] = np.minimum(
                    self.feas_ref_states_new[mask, 3],
                    self.exit_alignment_post_clearance_speed,
                )
                ref_status.update({
                    "mode": "post_clearance_exit_alignment_reference",
                    "speed_cap": float(self.exit_alignment_post_clearance_speed),
                    "profile": {
                        "type": "goal_window_speed_cap_after_target_clearance",
                        "goal_window": float(self.exit_alignment_post_clearance_goal_window),
                        "capped_points": int(np.count_nonzero(mask)),
                        "target_cleared_conflict": True,
                    },
                })
                if not recovery_active_for_reference:
                    return ref_status

        reduced_stabilization = self._reduced_recovery_stabilization_active(
            lateral_error=lateral_error,
            heading_error=heading_error,
            completion_metrics=completion_metrics,
        )
        recovery_speed_cap = (
            min(float(self.yield_recovery_speed), 4.0)
            if reduced_stabilization
            else float(self.yield_recovery_speed)
        )
        recovery_accel_cap = (
            min(float(self.yield_recovery_accel), 0.8)
            if reduced_stabilization
            else float(self.yield_recovery_accel)
        )
        self.feas_ref_states_new[:, 3] = np.minimum(
            self.feas_ref_states_new[:, 3],
            recovery_speed_cap,
        )
        self.feas_ref_inputs_new[:, 0] = np.clip(
            self.feas_ref_inputs_new[:, 0],
            self.yield_stop_decel,
            recovery_accel_cap,
        )
        ref_status.update({
            "mode": "post_yield_rejoin_reference",
            "speed_cap": float(recovery_speed_cap),
            "accel_upper_bound": float(recovery_accel_cap),
            "profile": {
                "type": "constant_recovery_cap",
                "recovery_speed": float(recovery_speed_cap),
                "nominal_recovery_speed": float(self.yield_recovery_speed),
                "reduced_stabilization": bool(reduced_stabilization),
            },
        })
        return ref_status

    def run_step(self, pred_dict):
        vehicle_loc   = self.vehicle.get_location()
        vehicle_wp    = self.map.get_waypoint(vehicle_loc)
        vehicle_tf    = self.vehicle.get_transform()
        vehicle_vel   = self.vehicle.get_velocity()
        vehicle_accel = self.vehicle.get_acceleration()
        speed_limit   = self.vehicle.get_speed_limit()

        target_vehicle_positions=pred_dict["tvs_positions"]
        target_vehicle_gmm_preds=pred_dict["tvs_mode_dists"]
        target_vehicle_mode_probs=pred_dict.get("tvs_mode_probs")
        target_vehicle_valid_pred=pred_dict.get("tvs_valid_pred")
        self._debug_write_setup_once()



        N_TV=len(target_vehicle_positions)




        # Get the vehicle's current pose in a RH coordinate system.
        x, y = vehicle_loc.x, -vehicle_loc.y
        psi = -fth.fix_angle(np.radians(vehicle_tf.rotation.yaw))

        # Look up the projection of the current pose to Frenet frame.
        s, ey, epsi = \
            self.frenet_traj.convert_global_to_frenet_frame(x, y, psi)
        curv = self.frenet_traj.get_curvature_at_s(s)

        # Get the current speed and longitudinal acceleration.
        speed = np.sqrt(vehicle_vel.x**2 + vehicle_vel.y**2)
        accel = np.cos(psi) * vehicle_accel.x - np.sin(psi)*vehicle_accel.y

        control = carla.VehicleControl()
        control.hand_brake = False
        control.manual_gear_shift = False

        z0=np.array([x,y,psi,speed])
        u0=np.array([self.SMPC.A_MIN, 0.])
        v_des = np.clip(z0[-1] + self.SMPC.A_MIN * self.SMPC.DT, self.SMPC.V_MIN, self.SMPC.V_MAX)
        is_opt=False
        solve_time=np.nan
        collision_prob=np.nan




        self.t_ref=np.argmin(np.linalg.norm(self.feas_ref_states[:,:2]-np.hstack((x,y)), axis=1))



        completion_metrics = self._completion_metrics(s, x, y, ey=ey, epsi=epsi)
        reached_end = self.frenet_traj.reached_trajectory_end(s, resolution=5.)
        reached_end = reached_end and completion_metrics["lateral_ok"] and completion_metrics["heading_ok"]
        reached_end = reached_end or completion_metrics["completed_by_s_margin"]
        reached_end = reached_end or completion_metrics["completed_by_goal_dist"]
        reached_end = reached_end or completion_metrics["completed_by_lane_entry"]
        reached_end = reached_end or completion_metrics["completed_by_exit_alignment"]

        diag_triggers = []
        goal_dist_for_diag = completion_metrics.get("goal_dist")
        s_after_route_goal_for_diag = completion_metrics.get("s_after_route_goal")
        if goal_dist_for_diag is not None and goal_dist_for_diag <= 8.0:
            diag_triggers.append("goal_dist_le_8m")
        if (
            s_after_route_goal_for_diag is not None
            and s_after_route_goal_for_diag >= -8.0
        ):
            diag_triggers.append("s_after_route_goal_ge_minus_8m")
        if reached_end and not self.goal_reached:
            diag_triggers.append("completion")
        for diag_trigger in diag_triggers:
            self._record_lane_entry_heading_diagnostics(
                x=x,
                y=y,
                psi=psi,
                speed=speed,
                s=s,
                ey=ey,
                epsi=epsi,
                vehicle_wp=vehicle_wp,
                completion_metrics=completion_metrics,
                trigger=diag_trigger,
            )

        if self.goal_reached or reached_end:
            # Stop if the end of the path is reached and signal completion.
            self.goal_reached = True
            if self.debug_savedir is not None and not self._debug_completion_written:
                self._debug_completion_written = True
                self._debug_write_json("smpc_completion.json", {
                    "agent": "SMPCAgent",
                    "debug_label": self.debug_label,
                    "step": int(self.time),
                    "vehicle_state": {
                        "x": x,
                        "y": y,
                        "psi": psi,
                        "speed": speed,
                        "s": s,
                        "ey": ey,
                        "epsi": epsi,
                    },
                    "completion": completion_metrics,
                })

        else:
            # Run SMPC Preds.
            reference_status = {
                "regenerated": False,
                "restored_global_reference": False,
                "forced_reference_linearization": False,
                "skip_reason": None,
                "reference_regen_max_lateral_error": self.reference_regen_max_lateral_error,
                "post_yield_recovery": {
                    "active": bool(self.yield_recovery_enabled and self._yield_recovery_steps_remaining > 0),
                    "steps_remaining": int(self._yield_recovery_steps_remaining),
                    "max_lateral_error": self.yield_recovery_max_lateral_error,
                    "regen_period": self.yield_recovery_regen_period,
                },
            }
            recovery_active_for_reference = bool(
                self.yield_recovery_enabled and self._yield_recovery_steps_remaining > 0
            )
            active_reference_guard = (
                self.yield_recovery_max_lateral_error
                if recovery_active_for_reference
                else self.reference_regen_max_lateral_error
            )
            reference_status["active_lateral_error_guard"] = active_reference_guard
            should_regenerate_reference = (
                recovery_active_for_reference
                and self.time % self.yield_recovery_regen_period == 0
            ) or self.time % 5 == 0
            if abs(ey) > active_reference_guard:
                # Do not let a large lateral deviation become the new reference.
                self.feas_ref_states_new = self.feas_ref_states.copy()
                self.feas_ref_inputs_new = self.feas_ref_inputs.copy()
                reference_status["restored_global_reference"] = True
                reference_status["forced_reference_linearization"] = True
                reference_status["skip_reason"] = "lateral_error_too_large"
            elif should_regenerate_reference and self.ref_horizon>self.t_ref+1:
                self.reference_regeneration(x,y,psi,speed)
                reference_status["regenerated"] = True
                if recovery_active_for_reference:
                    reference_status["skip_reason"] = "post_yield_recovery_regen"
            elif should_regenerate_reference:
                reference_status["skip_reason"] = "near_reference_end"




            t_ref_new=np.argmin(np.linalg.norm(self.feas_ref_states_new[:,:2]-np.hstack((x,y)), axis=1))
            pre_solve_yield_status = self._rule_aware_yield_decision(
                x,
                y,
                speed,
                t_ref_new,
                target_vehicle_gmm_preds,
                target_vehicle_mode_probs,
                target_vehicle_positions,
                target_vehicle_valid_pred,
                N_TV,
            )
            yield_active_for_reference = bool(pre_solve_yield_status.get("active"))
            reference_status["rule_aware_reference"] = self._apply_rule_aware_reference_profile(
                t_ref_new,
                pre_solve_yield_status,
                recovery_active_for_reference,
                lateral_error=ey,
                heading_error=epsi,
                completion_metrics=completion_metrics,
            )
            if (
                self.prev_opt
                and self.time%1==0
                and not reference_status["forced_reference_linearization"]
                and not yield_active_for_reference
                and not recovery_active_for_reference
            ):
                l_states, l_inputs = self.linearization_traj(x,y,psi,speed)

            else:
                l_states = self._horizon_slice_with_tail_padding(
                    self.feas_ref_states_new, t_ref_new, self.N + 1
                )
                l_inputs = self._horizon_slice_with_tail_padding(
                    self.feas_ref_inputs_new, t_ref_new, self.N + 1
                )


            ## TV shapes estimate along prediction horizon

            Rs_ev=[np.array([[np.cos(l_states[t,2]),np.sin(l_states[t,2])],[-np.sin(l_states[t,2]), np.cos(l_states[t,2])]]) for t in range(1,self.N+1)]


            tv_theta=[[np.arctan2(np.diff(target_vehicle_gmm_preds[0][k][j,:,1]), np.diff(target_vehicle_gmm_preds[0][k][j,:,0])) for j in range(self.N_modes)] for k in range(N_TV)]
            tv_R=[[[np.array([[np.cos(tv_theta[k][j][i]), np.sin(tv_theta[k][j][i])],[-np.sin(tv_theta[k][j][i]), np.cos(tv_theta[k][j][i])]]) for i in range(self.N-1)] for j in range(self.N_modes)] for k in range(N_TV)]
            collision_Q=np.array([
                [1.0 / (self.collision_ellipse_half_length + self.d_min) ** 2, 0.0],
                [0.0, 1.0 / (self.collision_ellipse_half_width + self.d_min) ** 2],
            ])
            if self.CA_inner_approx:
                tv_shape_matrices=[[[ tv_R[k][j][i].T@collision_Q@tv_R[k][j][i] for i in range(self.N-1)] for j in range(self.N_modes)] for k in range(N_TV)]
            elif not self.obca_flag:
                tv_shape_matrices=[[[ np.identity(2) for i in range(self.N-1)] for j in range(self.N_modes)] for k in range(N_TV)]
                for k in range(N_TV):
                    for j in range(self.N_modes):
                        for i in range(self.N-1):
                            m_eval, m_evec= np.linalg.eigh(Rs_ev[i].T@collision_Q@Rs_ev[i])
                            m_sqrt=m_evec@np.diag(np.sqrt(m_eval))@m_evec.T
                            m_sqrt_inv=m_evec@np.diag(np.sqrt(m_eval)**(-1))@m_evec.T
                            s_eval, s_evec= np.linalg.eigh(m_sqrt_inv@tv_R[k][j][i].T@collision_Q@tv_R[k][j][i]@m_sqrt_inv)
                            temp=s_evec@np.diag(np.power(np.sqrt(s_eval)**(-1)+1., 2)**(-1))@s_evec.T
                            tv_shape_matrices[k][j][i]=m_sqrt@temp@m_sqrt
            else:
                tv_shape_matrices = tv_R





            update_dict={  'dx0':x-l_states[0,0],     'dy0':y-l_states[0,1],         'dpsi0':psi-l_states[0,2],       'dv0':speed-l_states[0,3],
                         'x_tv0': [target_vehicle_positions[k][0] for k in range(N_TV)],        'y_tv0': [target_vehicle_positions[k][1] for k in range(N_TV)],
                         'x_ref': self._horizon_slice_with_tail_padding(self.feas_ref_states_new[:, 0], t_ref_new, self.SMPC.N + 1).T,
                         'y_ref': self._horizon_slice_with_tail_padding(self.feas_ref_states_new[:, 1], t_ref_new, self.SMPC.N + 1).T ,
                         'psi_ref': self._horizon_slice_with_tail_padding(self.feas_ref_states_new[:, 2], t_ref_new, self.SMPC.N + 1).T ,
                         'v_ref': self._horizon_slice_with_tail_padding(self.feas_ref_states_new[:, 3], t_ref_new, self.SMPC.N + 1).T ,
                         'a_ref': self._horizon_slice_with_tail_padding(self.feas_ref_inputs_new[:, 0], t_ref_new, self.SMPC.N + 1).T ,
                         'df_ref': self._horizon_slice_with_tail_padding(self.feas_ref_inputs_new[:, 1], t_ref_new, self.SMPC.N + 1).T ,
                         'x_lin': l_states[:,0].T,
                         'y_lin': l_states[:,1].T ,
                         'psi_lin': l_states[:,2].T,
                         'v_lin': l_states[:,3].T ,
                         'a_lin': l_inputs[:,0].T ,
                         'df_lin': l_inputs[:,1].T,
                         'mus'  : [target_vehicle_gmm_preds[0][k] for k in range(N_TV)],     'sigmas' : [target_vehicle_gmm_preds[1][k] for k in range(N_TV)], 'acc_prev' : self.control_prev[0], 'df_prev' : self.control_prev[1],       'tv_shapes': tv_shape_matrices, 'Rs_ev': Rs_ev }

            heading_cost_weights, heading_cost_status = self._lane_entry_heading_cost_profile(
                t_ref_new,
                pre_solve_yield_status,
                epsi,
            )
            update_dict["heading_cost_weights"] = heading_cost_weights

            if target_vehicle_mode_probs is not None:
                probs = np.asarray(target_vehicle_mode_probs[:N_TV], dtype=float)
                if probs.shape == (N_TV, self.N_modes):
                    probs = probs / np.sum(probs, axis=1, keepdims=True)
                    joint_probs = probs[0]
                    for mode_probs in probs[1:]:
                        joint_probs = np.outer(joint_probs, mode_probs).reshape(-1)
                    update_dict["probs"] = joint_probs / np.sum(joint_probs)

            adaptive_risk = self._adaptive_risk_allocation(pre_solve_yield_status)
            solver_uses_adaptive_risk = bool(
                adaptive_risk.get("enabled")
                and not self.fixed_risk
                and not self.ol_flag
                and not self.obca_flag
            )
            base_solver_tight = float(getattr(self.SMPC, "tight", smpc.UPSTREAM_CODE_TIGHTENING))
            base_solver_target_prob = float(
                getattr(self.SMPC, "target_prob", smpc.UPSTREAM_CODE_TARGET_PROB)
            )
            solver_risk_mode = "adaptive_variable" if solver_uses_adaptive_risk else "fixed_static"
            solver_current_tight = (
                float(adaptive_risk["tightening"]) if solver_uses_adaptive_risk else base_solver_tight
            )
            solver_current_target_prob = (
                float(adaptive_risk["target_prob"]) if solver_uses_adaptive_risk else base_solver_target_prob
            )
            solver_risk_allocation = None
            if solver_uses_adaptive_risk:
                solver_risk_allocation = dict(adaptive_risk)
                solver_risk_allocation["solver_applied"] = True
                solver_risk_allocation["solver_risk_mode"] = solver_risk_mode
                update_dict["risk_tightening"] = solver_current_tight
                update_dict["risk_target_prob"] = solver_current_target_prob
                update_dict["adaptive_risk_allocation"] = solver_risk_allocation



            debug_payload = {
                "agent": "SMPCAgent",
                "debug_label": self.debug_label,
                "step": int(self.time),
                "policy_flags": {
                    "ol_flag": self.ol_flag,
                    "fixed_risk": self.fixed_risk,
                    "obca_flag": self.obca_flag,
                    "ns_bl_flag": self.ns_bl_flag,
                },
                "risk": {
                    "risk_profile": self.risk_profile,
                    "tight": getattr(self.SMPC, "tight", None),
                    "target_prob": getattr(self.SMPC, "target_prob", None),
                    "solver_risk_mode": solver_risk_mode,
                    "solver_uses_adaptive_risk": bool(solver_uses_adaptive_risk),
                    "solver_current_tight": solver_current_tight,
                    "solver_current_target_prob": solver_current_target_prob,
                    "applied_tight": solver_current_tight,
                    "applied_target_prob": solver_current_target_prob,
                    "diagnostic_adaptive": adaptive_risk,
                    "adaptive": (
                        dict(adaptive_risk, solver_applied=True, solver_risk_mode=solver_risk_mode)
                        if solver_uses_adaptive_risk
                        else dict(adaptive_risk, solver_applied=False, solver_risk_mode=solver_risk_mode)
                    ),
                },
                "collision_envelope": {
                    "d_min": self.d_min,
                    "ellipse_half_length": self.collision_ellipse_half_length,
                    "ellipse_half_width": self.collision_ellipse_half_width,
                },
                "vehicle_state": {
                    "x": x,
                    "y": y,
                    "psi": psi,
                    "speed": speed,
                    "accel": accel,
                    "s": s,
                    "ey": ey,
                    "epsi": epsi,
                    "curv": curv,
                    "speed_limit": speed_limit,
                    "control_prev": self.control_prev,
                },
                "reference": {
                    "t_ref": self.t_ref,
                    "t_ref_new": t_ref_new,
                    "ref_horizon": self.ref_horizon,
                    "status": reference_status,
                    "l_states": self._debug_array_summary(l_states),
                    "l_inputs": self._debug_array_summary(l_inputs),
                },
                "completion": completion_metrics,
                "lane_entry_heading_cost": heading_cost_status,
                "prediction": self._debug_prediction_summary(
                    target_vehicle_positions,
                    target_vehicle_gmm_preds,
                    target_vehicle_mode_probs,
                ),
                "prediction_valid": target_vehicle_valid_pred,
                "update": self._debug_update_summary(update_dict),
            }
            if N_TV > 0:
                try:
                    debug_payload["relative_geometry_tv0"] = {
                        "dx_ego_minus_tv": x - update_dict["x_tv0"][0],
                        "dy_ego_minus_tv": y - update_dict["y_tv0"][0],
                        "distance": float(np.hypot(x - update_dict["x_tv0"][0], y - update_dict["y_tv0"][0])),
                    }
                except Exception as exc:
                    debug_payload["relative_geometry_tv0"] = {"error": repr(exc)}

            if 'ws' in self.warm_start.keys() and self.obca_flag:
                update_dict.update({'ws': self.warm_start['ws']})



            bypass_reason = self._rule_yield_smpc_bypass_reason(pre_solve_yield_status, speed)
            bypass_smpc_for_rule_yield = bypass_reason is not None
            debug_payload["solver_bypass"] = {
                "enabled": bool(bypass_smpc_for_rule_yield),
                "reason": bypass_reason if bypass_smpc_for_rule_yield else "not_applicable",
                "yield_phase": pre_solve_yield_status.get("phase"),
                "yield_active": bool(pre_solve_yield_status.get("active")),
                "recovery_steps_remaining": int(self._yield_recovery_steps_remaining),
            }

            if bypass_smpc_for_rule_yield:
                t_bar=2
                i=(N_TV-1)*(self.SMPC.t_bar_max)+t_bar
                debug_payload["solver_problem"] = {
                    "backend_class": type(self.SMPC).__name__,
                    "problem_id": i,
                    "N_TV": N_TV,
                    "t_bar": t_bar,
                    "t_bar_max": self.SMPC.t_bar_max,
                    "n_joint_modes": int(self.N_modes ** N_TV),
                    "n_active_modes": int(1 + (-1 + self.N_modes ** N_TV) * (t_bar > 0)),
                    "bypassed": True,
                }
                a_lin0 = float(np.asarray(update_dict["a_lin"], dtype=float).reshape(-1)[0])
                df_lin0 = float(np.asarray(update_dict["df_lin"], dtype=float).reshape(-1)[0])
                previous_steer = float(np.asarray(self.control_prev, dtype=float).reshape(-1)[1])
                u_seed = np.array([0.0, previous_steer], dtype=float)
                u_control = np.array([u_seed[0] - a_lin0, u_seed[1] - df_lin0], dtype=float)
                v_next = float(speed)
                is_opt = True
                solve_time = 0.0
                collision_prob = np.nan
                self.prev_opt = False
                debug_payload["solver"] = {
                    "bypassed": True,
                    "optimal": True,
                    "solve_time": solve_time,
                    "collision_prob": collision_prob,
                    "reason": bypass_reason,
                    "risk_profile": self.risk_profile,
                    "solver_risk_mode": solver_risk_mode,
                    "current_tight": solver_current_tight,
                    "current_target_prob": solver_current_target_prob,
                    "adaptive_risk_allocation": solver_risk_allocation,
                    "diagnostic_adaptive_risk": adaptive_risk,
                }

            elif self.ol_flag:

                debug_payload["solver_problem"] = {
                    "backend_class": type(self.SMPC).__name__,
                    "problem_id": "open_loop",
                    "N_TV": N_TV,
                }
                try:
                    self.SMPC.update(update_dict)
                    sol_dict=self.SMPC.solve()
                except Exception as exc:
                    debug_payload["solver"] = {"exception": repr(exc)}
                    self._debug_record_step(debug_payload, is_failure=True)
                    raise

                u_control = sol_dict['u_control'] # 2x1 vector, [a_optimal, df_optimal]
                v_next    = sol_dict['v_next']
                is_opt    = sol_dict['optimal']
                solve_time=sol_dict['solve_time']
                collision_prob = sol_dict.get('collision_prob', np.nan)
                debug_payload["solver"] = self._debug_solver_summary(sol_dict)


            else:


                t_bar=2 # fix robust horizon for policy tree
                i=(N_TV-1)*(self.SMPC.t_bar_max)+t_bar  # pick correct id# of parameterized MPC problem
                debug_payload["solver_problem"] = {
                    "backend_class": type(self.SMPC).__name__,
                    "problem_id": i,
                    "N_TV": N_TV,
                    "t_bar": t_bar,
                    "t_bar_max": self.SMPC.t_bar_max,
                    "n_joint_modes": int(self.N_modes ** N_TV),
                    "n_active_modes": int(1 + (-1 + self.N_modes ** N_TV) * (t_bar > 0)),
                }
                try:
                    self.SMPC.update(i, update_dict)
                    sol_dict=self.SMPC.solve(i)
                except Exception as exc:
                    debug_payload["solver"] = {"exception": repr(exc)}
                    self._debug_record_step(debug_payload, is_failure=True)
                    raise



                u_control = sol_dict['u_control'] # 2x1 vector, [a_optimal, df_optimal]
                v_next    = sol_dict['v_next']
                is_opt=sol_dict['optimal']
                solve_time=sol_dict['solve_time']
                collision_prob = sol_dict.get('collision_prob', np.nan)
                debug_payload["solver"] = self._debug_solver_summary(sol_dict)
                self.warm_start={}
                if is_opt and self.obca_flag:
                    self.warm_start={'ws': [sol_dict['h_opt'],sol_dict['K_opt'],sol_dict['M_opt'],sol_dict['lmbd_opt'],sol_dict['nu_opt']]}

                self.prev_opt=is_opt
                if self.prev_opt:
                    self.prev_nom_inputs=sol_dict['nom_u_ev']
                # self.prev_opt=False


            self.control_prev=np.array([u_control[0]+update_dict['a_lin'][0],u_control[1]+update_dict['df_lin'][0]])
            u0=self.control_prev
            v_des=v_next
            yield_status = pre_solve_yield_status
            u0, v_des, yield_status = self._apply_rule_aware_yield_control(
                yield_status,
                u0,
                v_des,
                speed,
                lateral_error=ey,
                heading_error=epsi,
                completion_metrics=completion_metrics,
            )
            debug_payload["yield_stop_supervisor"] = yield_status
            debug_payload["rule_aware_yield"] = yield_status
            debug_payload["applied"] = {
                "is_opt": is_opt,
                "solve_time": solve_time,
                "collision_prob": collision_prob,
                "u0": u0,
                "u_control": u_control,
                "v_des": v_des,
                "control_prev_after": self.control_prev,
            }
            self._debug_record_step(debug_payload, is_failure=not bool(is_opt))


            print(f"\toptimal?: {is_opt}")
            print(f"\tv_next: {v_next}")
            print(f"\tsteering: {u0[1]}")
            print(f"state: {z0}")
            print(f"control: {u0}")




            ## Debugging: Plot expected hyperplanes for obstacle avoidance along the prediction horizon

            # if self.time%10 ==0 and is_opt:
            #     for i, c in zip( range(len(sol_dict["nom_z_ev"])), ['r', 'g', 'b']):
            #         arr = sol_dict["nom_z_ev"][i]
            #         arr_lin=sol_dict["z_lin"]
            #         arr_ref=sol_dict['z_ref']
            #         arr_tv= sol_dict['z_tv_ref']
            #         shape=tv_shape_matrices[0][0]
            #         # pdb.set_trace()
            #         # x_ref=[arr_tv[0,t+1]+(x-arr_tv[0,t+1])/np.sqrt((np.array([x-arr_tv[0,t+1], y-arr_tv[1,t+1]])).T@shape[t]@(np.array([x-arr_tv[0,t+1], y-arr_tv[1,t+1]]))) for t in range(self.N)]
            #         # y_ref=[arr_tv[0,t+1]+(x-arr_tv[0,t+1])/np.sqrt((np.array([x-arr_tv[0,t+1], y-arr_tv[1,t+1]])).T@shape[t]@(np.array([x-arr_tv[0,t+1], y-arr_tv[1,t+1]]))) for t in range(self.N)]

            #         plt.subplot(3, 1, 1+i)
            #         plt.legend()
            #         plt.plot(arr[0,:], arr[1,:], color=c, marker='*')
            #         plt.plot(arr_lin[0,:], arr_lin[1,:], 'k-')
            #         plt.plot(arr_ref[0,:], arr_ref[1,:], 'k.')
            #         plt.plot(arr_tv[0,:], arr_tv[1,:], 'y.')
            #         delx=0.06*(np.arange(10)-4.5)
            #         for t in range(self.N):

            #             if t==self.N-1:
            #                 shapet=shape[t-1]
            #                 theta_el=tv_theta[0][0][t-1]
            #             else:
            #                 print(sol_dict['eval_oa'][t,:]@(arr[:2,t]-arr_tv[:,t+1])-1.0)
            #                 shapet=shape[t]
            #                 theta_el=tv_theta[0][0][t]

            #             x_ref=arr_tv[0,t+1]+(x-arr_tv[0,t+1])/np.sqrt((np.array([x-arr_tv[0,t+1], y-arr_tv[1,t+1]])).T@shapet@(np.array([x-arr_tv[0,t+1], y-arr_tv[1,t+1]])))
            #             y_ref=arr_tv[1,t+1]+(y-arr_tv[1,t+1])/np.sqrt((np.array([x-arr_tv[0,t+1], y-arr_tv[1,t+1]])).T@shapet@(np.array([x-arr_tv[0,t+1], y-arr_tv[1,t+1]])))
            #             zQ=np.array([x_ref-arr_tv[0,t+1], y_ref-arr_tv[1,t+1]]).T@shapet
            #             x_plt=delx+x_ref
            #             y_plt=(-zQ[0]*delx)/zQ[1]+y_ref
            #             # pdb.set_trace()
            #             plt.plot(x_plt, y_plt, label ='%s line' % t)
            #             plt.plot([x, arr_tv[0,t+1]], [y, arr_tv[1,t+1]], 'r--')
            #             plt.arrow(x_ref, y_ref, zQ[0]*1, zQ[1]*1)

            #             ax = plt.gca()
            #             ax.add_patch(Ellipse((arr_tv[0,t+1],
            #                                   arr_tv[1,t+1]),
            #                                   2*(3+self.d_min),
            #                                   2*(1+self.d_min),
            #                                   theta_el,
            #                                   fill=False,
            #                                   color='c')
            #                         )

            #         plt.axis('equal')
            #     plt.legend()
            #     plt.show()
                # pdb.set_trace()

        self.time+=1
        control = self._low_level_control.update(speed,      # v_curr
                                                 u0[0], # a_des
                                                 v_des, # v_des
                                                 u0[1]) # df_des

        return control, z0, u0, is_opt, solve_time, collision_prob
