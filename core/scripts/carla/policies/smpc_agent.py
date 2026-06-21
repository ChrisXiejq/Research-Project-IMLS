import carla
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
                 yield_reference_min_speed=0.8,
                 yield_reference_decel=-3.75,
                 yield_stop_decel=-5.0,
                 yield_conflict_radius=4.0,
                 yield_stop_buffer_distance=6.25,
                 yield_brake_distance_margin=3.5,
                 yield_wait_steer_lookahead_distance=6.0,
                 yield_wait_steer_gain=1.0,
                 yield_ttc_margin=0.8,
                 yield_activation_distance=12.0,
                 yield_hold_distance=3.0,
                 yield_release_time=0.3,
                 yield_observed_caution_enabled=True,
                 yield_observed_caution_distance=12.0,
                 yield_observed_caution_min_target_speed=0.5,
                 yield_steer_damping=0.25,
                 yield_recovery_enabled=True,
                 yield_recovery_steps=60,
                 yield_recovery_regen_period=2,
                 yield_recovery_max_lateral_error=12.0,
                 yield_recovery_speed=4.0,
                 yield_recovery_accel=1.2,
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
        self.yield_reference_min_speed = float(yield_reference_min_speed)
        self.yield_reference_decel = float(yield_reference_decel)
        self.yield_stop_decel = float(yield_stop_decel)
        self.yield_conflict_radius = float(yield_conflict_radius)
        self.yield_stop_buffer_distance = float(yield_stop_buffer_distance)
        self.yield_brake_distance_margin = float(yield_brake_distance_margin)
        self.yield_wait_steer_lookahead_distance = float(yield_wait_steer_lookahead_distance)
        self.yield_wait_steer_gain = float(yield_wait_steer_gain)
        self.yield_ttc_margin = float(yield_ttc_margin)
        self.yield_activation_distance = float(yield_activation_distance)
        self.yield_hold_distance = float(yield_hold_distance)
        self.yield_release_time = float(yield_release_time)
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
        if self.yield_reference_min_speed < self.yield_stop_speed:
            raise ValueError(
                "yield_reference_min_speed must be >= yield_stop_speed, "
                f"got {self.yield_reference_min_speed} < {self.yield_stop_speed}"
            )
        if self.yield_reference_decel >= 0.0:
            raise ValueError(f"yield_reference_decel must be negative, got {self.yield_reference_decel}")
        if self.yield_stop_decel >= 0.0:
            raise ValueError(f"yield_stop_decel must be negative, got {self.yield_stop_decel}")
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
        if self.yield_brake_distance_margin < 0.0:
            raise ValueError(
                f"yield_brake_distance_margin must be non-negative, got {self.yield_brake_distance_margin}"
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
        # Used by SMPC_MMPreds_OL (N_TV_MAX); intersection runner passes target count.
        self._n_tv_max_ol = n_tv_max
        self.risk_profile = risk_profile

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





        self.control_prev = np.zeros((2,1))
        self.prev_opt=False
        self.prev_nom_inputs=[]
        self._yield_stop_seen = False
        self._yield_stop_active_prev = False
        self._yield_recovery_steps_remaining = 0
        self._rule_yield_phase = "idle"
        self._yield_geometry = None
        self._observed_target_tracks = {}
        self.reference_regeneration()

        self.warm_start={}
        self.debug_savedir = None
        self.debug_label = smpc_config
        self._debug_setup_written = False
        self._debug_first_failure_written = False
        self._debug_completion_written = False
        self.completion_s_margin = 6.0
        self.completion_goal_dist = 8.0
        self.completion_lateral_error = 4.0

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
        if not self.ol_flag:
            if not self.obca_flag:
                self.SMPC=smpc.SMPC_MMPreds(N=self.N, DT=self.dt, N_modes_MAX=self.N_modes, NS_BL_FLAG=self.ns_bl_flag, fixed_risk=self.fixed_risk,
                                    L_F=self.lf, L_R=self.lr, fps=self.fps, N_TV_MAX=n_tv_mpc,
                                    risk_profile=self.risk_profile)
            else:
                self.SMPC=smpc.SMPC_MMPreds_OBCA(N=self.N, DT=self.dt, N_modes_MAX=self.N_modes, NS_BL_FLAG=self.ns_bl_flag,
                                        L_F=self.lf, L_R=self.lr, fps=self.fps, pol_mode=self.obca_mode, N_TV_MAX=n_tv_mpc)
        else:
            n_tvm = self._n_tv_max_ol if self._n_tv_max_ol is not None else 2
            self.SMPC=smpc.SMPC_MMPreds_OL(N=self.N, DT=self.dt, N_modes_MAX=self.N_modes,
                                          L_F=self.lf, L_R=self.lr, fps=self.fps,
                                          N_TV_MAX=n_tvm,
                                          risk_profile=self.risk_profile)


        self.goal_reached = False # flags when the end of the path is reached and agent should stop

    def set_debug_context(self, savedir, label=None):
        self.debug_savedir = savedir
        if label is not None:
            self.debug_label = label

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
                "activation_rule": "distance_to_stop <= v^2/(2*abs(decel)) + brake_distance_margin",
                "pre_solve_reference_profile": "yield reference uses v_ref <= sqrt(v_ref_min^2 + 2*abs(reference_decel)*remaining_distance_to_stop); final near-stop control is handled by the yield controller, not by an instantaneous near-stop optimisation reference",
            },
            "yield_stop_supervisor": {
                "enabled": self.yield_stop_enabled,
                "stop_speed": self.yield_stop_speed,
                "reference_min_speed": self.yield_reference_min_speed,
                "reference_decel": self.yield_reference_decel,
                "decel": self.yield_stop_decel,
                "conflict_radius": self.yield_conflict_radius,
                "stop_buffer_distance": self.yield_stop_buffer_distance,
                "brake_distance_margin": self.yield_brake_distance_margin,
                "wait_steer_lookahead_distance": self.yield_wait_steer_lookahead_distance,
                "wait_steer_gain": self.yield_wait_steer_gain,
                "ttc_margin": self.yield_ttc_margin,
                "activation_distance": self.yield_activation_distance,
                "hold_distance": self.yield_hold_distance,
                "release_time": self.yield_release_time,
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
            "psi_lin", "v_lin", "a_lin", "df_lin", "probs",
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
        lateral_ok = bool(ey is not None and abs(float(ey)) <= self.completion_lateral_error)
        goal_dist_ok = bool(goal_dist <= self.completion_goal_dist)
        return {
            "end_s": end_s,
            "s_to_end": s_to_end,
            "goal_dist": goal_dist,
            "completion_s_margin": self.completion_s_margin,
            "completion_goal_dist": self.completion_goal_dist,
            "completion_lateral_error": self.completion_lateral_error,
            "lateral_ok": lateral_ok,
            "ey": ey,
            "epsi": epsi,
            "goal_dist_ok": goal_dist_ok,
            "completed_by_s_margin": bool(s >= end_s - self.completion_s_margin and lateral_ok),
            "completed_by_goal_dist": bool(goal_dist_ok and lateral_ok),
        }




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
            route = self.planner.trace_route(init_waypoint.transform.location, goal.transform.location)

            # # Convert the high-level route into a path parametrized by arclength distance s (i.e. Frenet frame).
            # # Generate a refernece by fitting a velocity profile with specified nominal speed and time discretization.

            way_s, way_xy, way_yaw = fth.extract_path_from_waypoints(route)
            self.frenet_traj = fth.FrenetTrajectoryHandler(way_s, way_xy, way_yaw, s_resolution=1.)
            self.nominal_speed = self.nominal_speed_mps
            self.lat_accel_max = 2. # maximum lateral acceleration (m/s^2), for slowing down at turns

            self.fit_velocity_profile()

            self.ref_horizon= self.reference.shape[0]-1
            self.ref_dict={'x_ref':self.reference[1:,1], 'y_ref':self.reference[1:,2], 'psi_ref':self.reference[1:,3], 'v_ref':self.reference[1:,4],
                            'x0'  : self.reference[0,1],  'y0'  : self.reference[0,2],  'psi0'  : self.reference[0,3],  'v0'  : self.reference[0,4], 'acc_prev' : self.control_prev[0], 'df_prev' : self.control_prev[1]}
            self.ref_dict['psi_ref'] = fth.fix_angle( self.ref_dict['psi_ref'] - self.ref_dict['psi0']) + self.ref_dict['psi0']
            self.feas_ref_gen=smpc.RefTrajGenerator(N=self.ref_horizon, DT=self.dt, L_F=self.lf, L_R=self.lr)
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



            self.feas_ref_gen=smpc.RefTrajGenerator(N=self.ref_horizon-self.t_ref-1, DT=self.dt, L_F=self.lf, L_R=self.lr)

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
        target_cleared_conflict = target_distance_to_conflict < -self.yield_conflict_radius
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

        max_brake = max(abs(self.yield_stop_decel), 1e-3)
        brake_distance = (float(speed) ** 2) / (2.0 * max_brake)
        brake_activation_distance = brake_distance + self.yield_brake_distance_margin
        braking_distance_required = ego_dist_to_stop <= brake_activation_distance
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
        cautious_candidate = (
            self.yield_observed_caution_enabled
            and not allow_priority_yield
            and source == "observed_track"
            and target_approaching_conflict
            and target_speed_est >= self.yield_observed_caution_min_target_speed
            and ego_dist_to_conflict <= self.yield_observed_caution_distance
            and not_far_past_conflict
        )
        active = (
            allow_priority_yield
            and target_has_priority
            and approaching_stop_line
            and not_far_past_conflict
            and (braking_distance_required or overlap_risk or close_hold)
        ) or cautious_candidate
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

        if active and not allow_priority_yield:
            reason = "observed_target_cautious_approach"
        elif active and braking_distance_required:
            reason = "braking_distance_yield"
        elif active:
            reason = "target_has_priority_before_stop_line"
        else:
            reason = "no_active_yield_needed"

        return {
            "active": bool(active),
            "phase": phase,
            "priority_rule": "turning_gives_way_to_oncoming_straight",
            "reason": reason,
            "target_index": int(target_idx),
            "target_mode": int(mode),
            "prediction_valid": valid_flags,
            "prediction_source": source,
            "priority_from_prediction": bool(allow_priority_yield),
            "cautious_candidate": bool(cautious_candidate),
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
            "target_distance_to_conflict": target_distance_to_conflict,
            "target_ttc_to_conflict": target_ttc_to_conflict,
            "target_speed_est": target_speed_est,
            "target_motion_line_min_distance": target_motion_line_min_distance,
            "target_approaching_conflict": bool(target_approaching_conflict),
            "target_cleared_conflict": bool(target_cleared_conflict),
            "target_enter_time": target_enter_time,
            "target_exit_time": target_exit_time,
            "target_has_priority": bool(target_has_priority and allow_priority_yield),
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
                if target_priority_distance < -self.yield_conflict_radius:
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
                if target_priority_distance < -self.yield_conflict_radius:
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

    def _apply_rule_aware_yield_control(self, yield_status, u0, v_des, speed):
        u0_flat = np.asarray(u0, dtype=float).reshape(-1)
        v_des_float = float(np.asarray(v_des, dtype=float).reshape(-1)[0])

        if yield_status.get("active"):
            distance_to_stop = max(float(yield_status.get("ego_distance_to_stop", 0.0)), 0.5)
            required_stop_decel = -(float(speed) ** 2) / (2.0 * distance_to_stop)
            a_des = max(
                self.yield_stop_decel,
                min(float(u0_flat[0]), required_stop_decel),
            )
            wait_steer_ref = float(yield_status.get("wait_steer_ref", 0.0)) * self.yield_wait_steer_gain
            wait_steer_ref = float(np.clip(wait_steer_ref, self.SMPC.DF_MIN, self.SMPC.DF_MAX))
            damped_steer = self.yield_steer_damping * float(u0_flat[1])
            df_des = wait_steer_ref if abs(wait_steer_ref) >= 0.03 else damped_steer
            u0_new = np.array([a_des, df_des], dtype=float)
            v_des_new = min(v_des_float, self.yield_stop_speed)
            self.control_prev = u0_new
            self._yield_stop_seen = True
            self._yield_stop_active_prev = True
            self._yield_recovery_steps_remaining = 0
            yield_status["applied"] = {
                "mode": (
                    "observed_target_cautious_control"
                    if yield_status.get("phase") == "cautious_approach_observed_target"
                    else "yield_line_control"
                ),
                "a_des": float(u0_new[0]),
                "df_des": float(u0_new[1]),
                "v_des": float(v_des_new),
                "required_stop_decel": float(required_stop_decel),
                "wait_steer_ref": float(wait_steer_ref),
                "damped_steer": float(damped_steer),
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
            restart_accel = 0.0
            if float(speed) < self.yield_recovery_speed:
                restart_accel = min(
                    self.yield_recovery_accel,
                    max(0.2, 0.4 * (self.yield_recovery_speed - float(speed))),
                )
            u0_new = np.array([
                min(
                    self.yield_recovery_accel,
                    max(float(u0_flat[0]), restart_accel),
                ),
                float(u0_flat[1]),
            ], dtype=float)
            v_des_new = min(
                max(v_des_float, self.yield_stop_speed),
                self.yield_recovery_speed,
            )
            self.control_prev = u0_new
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
            }
        else:
            u0_new = np.asarray(u0, dtype=float).reshape(-1)
            v_des_new = v_des
            recovery_status["applied"] = None
        recovery_status["steps_remaining_after"] = int(self._yield_recovery_steps_remaining)
        self._yield_stop_active_prev = False
        yield_status["recovery"] = recovery_status
        return u0_new, v_des_new, yield_status

    def _apply_rule_aware_reference_profile(
        self,
        t_ref_new,
        yield_status,
        recovery_active_for_reference,
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
        if not yield_active and not recovery_active_for_reference:
            return ref_status

        self.feas_ref_states_new = np.asarray(self.feas_ref_states_new, dtype=float).copy()
        self.feas_ref_inputs_new = np.asarray(self.feas_ref_inputs_new, dtype=float).copy()

        if yield_active:
            start_idx = int(max(0, min(t_ref_new, len(self.feas_ref_states_new) - 1)))
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

        self.feas_ref_states_new[:, 3] = np.minimum(
            self.feas_ref_states_new[:, 3],
            self.yield_recovery_speed,
        )
        self.feas_ref_inputs_new[:, 0] = np.clip(
            self.feas_ref_inputs_new[:, 0],
            self.yield_stop_decel,
            self.yield_recovery_accel,
        )
        ref_status.update({
            "mode": "post_yield_rejoin_reference",
            "speed_cap": float(self.yield_recovery_speed),
            "accel_upper_bound": float(self.yield_recovery_accel),
            "profile": {
                "type": "constant_recovery_cap",
                "recovery_speed": float(self.yield_recovery_speed),
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
        reached_end = reached_end and completion_metrics["lateral_ok"]
        reached_end = reached_end or completion_metrics["completed_by_s_margin"]
        reached_end = reached_end or completion_metrics["completed_by_goal_dist"]

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
                l_states=self.feas_ref_states_new[t_ref_new:t_ref_new+self.N+1,:]
                l_inputs=self.feas_ref_inputs_new[t_ref_new:t_ref_new+self.N+1,:]


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
                         'x_ref': self.feas_ref_states_new[t_ref_new:t_ref_new+self.SMPC.N+1,0].T,
                         'y_ref': self.feas_ref_states_new[t_ref_new:t_ref_new+self.SMPC.N+1,1].T ,
                         'psi_ref': self.feas_ref_states_new[t_ref_new:t_ref_new+self.SMPC.N+1,2].T ,
                         'v_ref': self.feas_ref_states_new[t_ref_new:t_ref_new+self.SMPC.N+1,3].T ,
                         'a_ref': self.feas_ref_inputs_new[t_ref_new:t_ref_new+self.SMPC.N+1,0].T ,
                         'df_ref': self.feas_ref_inputs_new[t_ref_new:t_ref_new+self.SMPC.N+1,1].T ,
                         'x_lin': l_states[:,0].T,
                         'y_lin': l_states[:,1].T ,
                         'psi_lin': l_states[:,2].T,
                         'v_lin': l_states[:,3].T ,
                         'a_lin': l_inputs[:,0].T ,
                         'df_lin': l_inputs[:,1].T,
                         'mus'  : [target_vehicle_gmm_preds[0][k] for k in range(N_TV)],     'sigmas' : [target_vehicle_gmm_preds[1][k] for k in range(N_TV)], 'acc_prev' : self.control_prev[0], 'df_prev' : self.control_prev[1],       'tv_shapes': tv_shape_matrices, 'Rs_ev': Rs_ev }

            if target_vehicle_mode_probs is not None:
                probs = np.asarray(target_vehicle_mode_probs[:N_TV], dtype=float)
                if probs.shape == (N_TV, self.N_modes):
                    probs = probs / np.sum(probs, axis=1, keepdims=True)
                    joint_probs = probs[0]
                    for mode_probs in probs[1:]:
                        joint_probs = np.outer(joint_probs, mode_probs).reshape(-1)
                    update_dict["probs"] = joint_probs / np.sum(joint_probs)



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



            if self.ol_flag:

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
