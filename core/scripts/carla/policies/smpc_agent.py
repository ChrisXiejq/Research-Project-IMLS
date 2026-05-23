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
        self.d_min=1.0
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
        self.reference_regen_max_lateral_error = 2.0

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
                                          N_TV_MAX=n_tvm)


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
            "completed_by_s_margin": bool(s >= end_s - self.completion_s_margin and lateral_ok),
            "completed_by_goal_dist": bool(goal_dist <= self.completion_goal_dist),
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
            }
            if abs(ey) > self.reference_regen_max_lateral_error:
                # Do not let a large lateral deviation become the new reference.
                self.feas_ref_states_new = self.feas_ref_states.copy()
                self.feas_ref_inputs_new = self.feas_ref_inputs.copy()
                reference_status["restored_global_reference"] = True
                reference_status["forced_reference_linearization"] = True
                reference_status["skip_reason"] = "lateral_error_too_large"
            elif self.time%5==0 and self.ref_horizon>self.t_ref+1:
                self.reference_regeneration(x,y,psi,speed)
                reference_status["regenerated"] = True
            elif self.time%5==0:
                reference_status["skip_reason"] = "near_reference_end"
    



            t_ref_new=np.argmin(np.linalg.norm(self.feas_ref_states_new[:,:2]-np.hstack((x,y)), axis=1))
            if self.prev_opt and self.time%1==0 and not reference_status["forced_reference_linearization"]:
                l_states, l_inputs = self.linearization_traj(x,y,psi,speed)

            else:
                l_states=self.feas_ref_states_new[t_ref_new:t_ref_new+self.N+1,:]
                l_inputs=self.feas_ref_inputs_new[t_ref_new:t_ref_new+self.N+1,:]


            ## TV shapes estimate along prediction horizon

            Rs_ev=[np.array([[np.cos(l_states[t,2]),np.sin(l_states[t,2])],[-np.sin(l_states[t,2]), np.cos(l_states[t,2])]]) for t in range(1,self.N+1)]


            tv_theta=[[np.arctan2(np.diff(target_vehicle_gmm_preds[0][k][j,:,1]), np.diff(target_vehicle_gmm_preds[0][k][j,:,0])) for j in range(self.N_modes)] for k in range(N_TV)]
            tv_R=[[[np.array([[np.cos(tv_theta[k][j][i]), np.sin(tv_theta[k][j][i])],[-np.sin(tv_theta[k][j][i]), np.cos(tv_theta[k][j][i])]]) for i in range(self.N-1)] for j in range(self.N_modes)] for k in range(N_TV)]
            if self.CA_inner_approx:
                tv_Q=np.array([[1./(3.6+self.d_min)**2, 0.],[0., 1./(1.2+self.d_min)**2]])
                tv_shape_matrices=[[[ tv_R[k][j][i].T@tv_Q@tv_R[k][j][i] for i in range(self.N-1)] for j in range(self.N_modes)] for k in range(N_TV)]
            elif not self.obca_flag:
                v_Q=np.array([[1./(2.1)**2, 0.],[0., 1./(1.1)**2]])
                tv_shape_matrices=[[[ np.identity(2) for i in range(self.N-1)] for j in range(self.N_modes)] for k in range(N_TV)]
                for k in range(N_TV):
                    for j in range(self.N_modes):
                        for i in range(self.N-1):
                            m_eval, m_evec= np.linalg.eigh(Rs_ev[i].T@v_Q@Rs_ev[i])
                            m_sqrt=m_evec@np.diag(np.sqrt(m_eval))@m_evec.T
                            m_sqrt_inv=m_evec@np.diag(np.sqrt(m_eval)**(-1))@m_evec.T
                            s_eval, s_evec= np.linalg.eigh(m_sqrt_inv@tv_R[k][j][i].T@v_Q@tv_R[k][j][i]@m_sqrt_inv)
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
