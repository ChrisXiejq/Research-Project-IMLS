from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import carla
import os
import sys

import cv2
import numpy as np
import random
import pickle
import traceback

scriptdir = os.path.abspath(__file__).split('carla')[0] + 'carla/'
sys.path.append(scriptdir)
from utils.carla_sync_mode import CarlaSyncMode
from utils import experiment_logging as exp_log
from policies.static_agent import StaticAgent
from policies.smpc_agent import SMPCAgent
from policies.mpc_agent import MPCAgent
from policies.bl_smpc_agent import BLSMPCAgent
from policies.ipopt_smpc_agent import IPOPTSMPCAgent

from rasterizer.agent_history import AgentHistory
from rasterizer.sem_box_rasterizer import SemBoxRasterizer
from utils.frenet_trajectory_handler import fix_angle
from utils.vehicle_geometry_utils import vehicle_name_to_lf_lr, resolve_vehicle_blueprint

scriptdir = os.path.abspath(__file__).split('scripts')[0] + 'scripts/'
sys.path.append(scriptdir)
from models.deploy_multipath_model import DeployMultiPath

"""
Simulation parameter classes.
"""
@dataclass(frozen=True)
class CarlaParams:
    # Carla world settings + intersection definition.
    map_str               : str # e.g. "Town05"
    weather_str           : str # e.g. "ClearNoon"
    fps                   : int # what fps to run the simulator in synchronous mode
    intersection_csv_loc  : str # file location of the csv defining the intersection

    # Carla client settings.
    ip_addr        : str   = "localhost"
    port           : int   = 2000
    timeout_period : float = 120.0

    # Scenario semantics.  These fields are logged and used to make the
    # traffic-control interpretation explicit for reproduction reports.
    side_of_road    : str = "left"          # "left" for UK-style traffic, "right" otherwise
    traffic_control : str = "unsignalised"  # "unsignalised" or "signalised"
    priority_rule   : str = ""              # e.g. "turning_gives_way_to_oncoming_straight"

@dataclass(frozen=True)
class DroneVizParams:
    # Parameters for the "drone": camera used to capture Carla scene.
    # By default, this represents a top down view.
    # XY must be specified, as it varies with the choice of intersection.
    x          : float
    y          : float
    z          : float =  50.
    roll       : float =   0.
    pitch      : float = -90.
    yaw        : float =   0.
    img_width  : int   = 1920
    img_height : int   = 1080
    fov        : int   = 90

    # Parameters for how to handle OpenCV img corresponding to the drone.
    visualize_opencv      : bool = True # show OpenCV window as the simulation is occuring
    save_avi              : bool = True # whether to save OpenCV visualization as a video
    overlay_gmm           : bool = True # whether to show the confidence ellipses for predicted agents.
    overlay_ego_info      : bool = True # add a string with text about ego's state/control.
    overlay_mode_probs    : bool = True # add a string with the mode probabilities.
    overlay_traj_hist     : bool = True # add the trajectory history for each agent

    # Photorealistic top-down: RGB camera rigidly attached above ego (needs real rendering,
    # e.g. ``-RenderOffScreen``; not meaningful with ``-nullrhi``). When True, world-fixed
    # ``x,y,z`` are ignored for placement; GMM / traj / mode overlays are skipped (wrong frame).
    attach_to_ego        : bool = False
    ego_cam_x_offset_m   : float = 0.0
    ego_cam_y_offset_m   : float = 0.0
    ego_cam_height_m     : float = 22.0
    ego_cam_pitch_deg    : float = -90.0
    ego_cam_yaw_deg      : float = 0.0

@dataclass(frozen=True)
class VehicleParams:
    # High level vehicle/policy selection.
    role          : str # either "ego" [dynamic, our agent], "static" [nonmoving vehicle], or "target" [dynamic vehicle, other agent]
    vehicle_type  : str # currently use one of {"vehicle.audi.tt", "vehicle.mercedes-benz.coupe"}
    vehicle_color : str # currently use "246, 246, 246" for static, "186, 0, 0" for ego, and "65, 63, 197" for dynamic
    policy_type   : str # {"static", mpc", "smpc", "blsmpc"} -> which control policy to use for this agent

    # Initial state and goal location selection.
    intersection_start_node_idx : int        # {0, 1, 2, 3} -> corresponds to a direction in the intersection_json above
    intersection_goal_node_idx  : int        # {0, 1, 2, 3} -> corresponds to a direction in the intersection_json above
    start_left_offset           : float      # how far to move the car's start pose in its local left (i.e. lateral axis) direction (m)
    goal_left_offset            : float      # how far to move the car's goal pose in its local left (i.e. lateral axis) direction (m)
    start_longitudinal_offset   : float      # how far to move the car's start pose in its local fwd (i.e. longitudinal axis) direction (m)
    goal_longitudinal_offset    : float      # how far to move the car's goal pose in its local fwd (i.e. longitudinal axis) direction (m)
    nominal_speed               : float      # how fast the car should travel if unobstructed / not turning
    init_speed                  : float      # the car's initial speed in simulation (m/s)

    # General MPC parameters.  Some of these can be ignored (e.g. n_modes if using MPCAgent).
    N         : int   = 10  # horizon of the MPC solution
    dt        : float = 0.2 # timestep of the discretization used (s)
    num_modes : int   = 3   # number of GMM modes considered by MPC (prioritizing most probable ones first)

    # SMPC specific parameters (ignored for any other policy_type).
    smpc_config : str = "full" # "var_risk", "open_loop", "fixed_risk"
    solver_backend : str = "gurobi" # "gurobi" or "ipopt_approx"
    risk_profile : str = "upstream_code" # "upstream_code", "paper_eps_002", "adaptive_interaction_severity", or "rule_aware_static_risk"
    collision_d_min : float = 0.5
    collision_ellipse_half_length : float = 3.8
    collision_ellipse_half_width : float = 1.8
    reference_regen_max_lateral_error : float = 1.5
    yield_stop_enabled : bool = True
    yield_stop_speed : float = 0.2
    yield_reference_min_speed : float = 0.8
    yield_reference_decel : float = -3.75
    yield_stop_decel : float = -5.0
    yield_conflict_radius : float = 4.0
    yield_stop_buffer_distance : float = 8.0
    yield_brake_distance_margin : float = 3.5
    yield_wait_steer_lookahead_distance : float = 6.0
    yield_wait_steer_gain : float = 1.0
    yield_ttc_margin : float = 0.8
    yield_activation_distance : float = 12.0
    yield_hold_distance : float = 3.0
    yield_release_time : float = 0.3
    yield_release_clearance_margin : float = 1.0
    yield_observed_caution_enabled : bool = True
    yield_observed_caution_distance : float = 12.0
    yield_observed_caution_min_target_speed : float = 0.5
    yield_steer_damping : float = 0.25
    yield_recovery_enabled : bool = True
    yield_recovery_steps : int = 60
    yield_recovery_regen_period : int = 2
    yield_recovery_max_lateral_error : float = 12.0
    yield_recovery_speed : float = 4.0
    yield_recovery_accel : float = 1.2
    completion_s_margin : float = 2.0
    completion_goal_dist : float = 4.0
    completion_lateral_error : float = 1.5
    completion_heading_error : float = 0.10
    completion_lane_entry_goal_dist : float = 1.0
    completion_lane_entry_heading_error : float = 0.30
    completion_exit_alignment_min_s_after_goal : float = 4.0
    post_goal_reference_extension_m : float = 12.0
    route_goal_extension_m : float = 0.0
    exit_alignment_path_enabled : bool = True
    exit_alignment_path_length : float = 12.0
    exit_alignment_distance_after_goal : float = 6.0
    exit_alignment_post_clearance_speed : float = 4.5
    exit_alignment_post_clearance_goal_window : float = 10.0

    # Traffic-rule metadata.  ``traffic_role`` is descriptive.  ``obey_traffic_lights``
    # enables an optional safety override for signalised scenarios; the UK give-way
    # scenario leaves this disabled so that yielding comes from SMPC risk constraints.
    traffic_role : str = ""
    obey_traffic_lights : bool = False
    stop_for_yellow : bool = True

@dataclass(frozen=True)
class PredictionParams:
    # Model parameter locations, given relative to <ROOTDIR>/scripts/models/
    model_weights         : str = "l5kit_multipath_10/"
    model_anchors         : str = "l5kit_clusters_16.npy"

    # Flag to render traffic lights on rasterized image for prediction.
    render_traffic_lights : bool = False

    # TODO: future work includes things like how often to update preds (if not at the Carla fps).

"""
Util functions for Carla. # TODO: move this elsewhere.
"""
def load_intersection(intersection_csv):
    with open(intersection_csv, 'r') as f:
        lines = f.readlines()

    intersection = []

    for line in lines:
        if '#' in line:
            continue # comment
        data = line.replace(" ", "").split(",")
        start_pose = [float(data[0]), float(data[1]), int(data[2])]
        goal_pose  = [float(data[3]), float(data[4]), int(data[5])]
        intersection.append( [start_pose, goal_pose] )

    return intersection

def get_vehicle_policy(vehicle_params, vehicle_actor, goal_transform, n_tv_max=None):
    if vehicle_params.policy_type == "static":
        return StaticAgent(vehicle_actor, goal_transform.location)
    elif vehicle_params.policy_type == "mpc":

        return MPCAgent(vehicle_actor, goal_transform.location, \
                        N=vehicle_params.N,
                        dt=vehicle_params.dt,
                        N_modes=vehicle_params.num_modes,
                        nominal_speed_mps=vehicle_params.nominal_speed)
    elif vehicle_params.policy_type == "blsmpc":
        return BLSMPCAgent(vehicle_actor, goal_transform.location, \
                        N=vehicle_params.N,
                        dt=vehicle_params.dt,
                        N_modes=vehicle_params.num_modes,
                        nominal_speed_mps=vehicle_params.nominal_speed)
    elif vehicle_params.policy_type == "smpc":
        if vehicle_params.solver_backend == "ipopt_approx":
            return IPOPTSMPCAgent(vehicle_actor, goal_transform.location,
                                  N=vehicle_params.N,
                                  dt=vehicle_params.dt,
                                  N_modes=vehicle_params.num_modes,
                                  nominal_speed_mps=vehicle_params.nominal_speed,
                                  approx_config=vehicle_params.smpc_config)

        if vehicle_params.solver_backend != "gurobi":
            raise ValueError(f"Unsupported solver backend: {vehicle_params.solver_backend}")

        if vehicle_params.smpc_config.endswith("OAinner"):
            return SMPCAgent(vehicle_actor, goal_transform.location, \
                            N=vehicle_params.N,
                            dt=vehicle_params.dt,
                            N_modes=vehicle_params.num_modes,
                            nominal_speed_mps=vehicle_params.nominal_speed,
                            smpc_config=vehicle_params.smpc_config.split("_OAinner")[0],
                            CAIA=True,
                            n_tv_max=n_tv_max,
                            risk_profile=vehicle_params.risk_profile,
                            collision_d_min=vehicle_params.collision_d_min,
                            collision_ellipse_half_length=vehicle_params.collision_ellipse_half_length,
                            collision_ellipse_half_width=vehicle_params.collision_ellipse_half_width,
                            reference_regen_max_lateral_error=vehicle_params.reference_regen_max_lateral_error,
                            yield_stop_enabled=vehicle_params.yield_stop_enabled,
                            yield_stop_speed=vehicle_params.yield_stop_speed,
                            yield_reference_min_speed=vehicle_params.yield_reference_min_speed,
                            yield_reference_decel=vehicle_params.yield_reference_decel,
                            yield_stop_decel=vehicle_params.yield_stop_decel,
                            yield_conflict_radius=vehicle_params.yield_conflict_radius,
                            yield_stop_buffer_distance=vehicle_params.yield_stop_buffer_distance,
                            yield_brake_distance_margin=vehicle_params.yield_brake_distance_margin,
                            yield_wait_steer_lookahead_distance=vehicle_params.yield_wait_steer_lookahead_distance,
                            yield_wait_steer_gain=vehicle_params.yield_wait_steer_gain,
                            yield_ttc_margin=vehicle_params.yield_ttc_margin,
                            yield_activation_distance=vehicle_params.yield_activation_distance,
                            yield_hold_distance=vehicle_params.yield_hold_distance,
                            yield_release_time=vehicle_params.yield_release_time,
                            yield_release_clearance_margin=vehicle_params.yield_release_clearance_margin,
                            yield_observed_caution_enabled=vehicle_params.yield_observed_caution_enabled,
                            yield_observed_caution_distance=vehicle_params.yield_observed_caution_distance,
                            yield_observed_caution_min_target_speed=vehicle_params.yield_observed_caution_min_target_speed,
                            yield_steer_damping=vehicle_params.yield_steer_damping,
                            yield_recovery_enabled=vehicle_params.yield_recovery_enabled,
                            yield_recovery_steps=vehicle_params.yield_recovery_steps,
                            yield_recovery_regen_period=vehicle_params.yield_recovery_regen_period,
                            yield_recovery_max_lateral_error=vehicle_params.yield_recovery_max_lateral_error,
                            yield_recovery_speed=vehicle_params.yield_recovery_speed,
                            yield_recovery_accel=vehicle_params.yield_recovery_accel,
                            completion_s_margin=vehicle_params.completion_s_margin,
                            completion_goal_dist=vehicle_params.completion_goal_dist,
                            completion_lateral_error=vehicle_params.completion_lateral_error,
                            completion_heading_error=vehicle_params.completion_heading_error,
                            completion_lane_entry_goal_dist=vehicle_params.completion_lane_entry_goal_dist,
                            completion_lane_entry_heading_error=vehicle_params.completion_lane_entry_heading_error,
                            completion_exit_alignment_min_s_after_goal=vehicle_params.completion_exit_alignment_min_s_after_goal,
                            post_goal_reference_extension_m=vehicle_params.post_goal_reference_extension_m,
                            route_goal_extension_m=vehicle_params.route_goal_extension_m,
                            exit_alignment_path_enabled=vehicle_params.exit_alignment_path_enabled,
                            exit_alignment_path_length=vehicle_params.exit_alignment_path_length,
                            exit_alignment_distance_after_goal=vehicle_params.exit_alignment_distance_after_goal,
                            exit_alignment_post_clearance_speed=vehicle_params.exit_alignment_post_clearance_speed,
                            exit_alignment_post_clearance_goal_window=vehicle_params.exit_alignment_post_clearance_goal_window)
        elif vehicle_params.smpc_config.endswith("obca"):
            return SMPCAgent(vehicle_actor, goal_transform.location, \
                            N=vehicle_params.N,
                            dt=vehicle_params.dt,
                            N_modes=vehicle_params.num_modes,
                            nominal_speed_mps=vehicle_params.nominal_speed,
                            smpc_config=vehicle_params.smpc_config.split("_obca")[0][:-2],
                            obca=True,
                            obca_mode=int(vehicle_params.smpc_config.split("_obca")[0][-1]),
                            n_tv_max=n_tv_max,
                            risk_profile=vehicle_params.risk_profile,
                            collision_d_min=vehicle_params.collision_d_min,
                            collision_ellipse_half_length=vehicle_params.collision_ellipse_half_length,
                            collision_ellipse_half_width=vehicle_params.collision_ellipse_half_width,
                            reference_regen_max_lateral_error=vehicle_params.reference_regen_max_lateral_error,
                            yield_stop_enabled=vehicle_params.yield_stop_enabled,
                            yield_stop_speed=vehicle_params.yield_stop_speed,
                            yield_reference_min_speed=vehicle_params.yield_reference_min_speed,
                            yield_reference_decel=vehicle_params.yield_reference_decel,
                            yield_stop_decel=vehicle_params.yield_stop_decel,
                            yield_conflict_radius=vehicle_params.yield_conflict_radius,
                            yield_stop_buffer_distance=vehicle_params.yield_stop_buffer_distance,
                            yield_brake_distance_margin=vehicle_params.yield_brake_distance_margin,
                            yield_wait_steer_lookahead_distance=vehicle_params.yield_wait_steer_lookahead_distance,
                            yield_wait_steer_gain=vehicle_params.yield_wait_steer_gain,
                            yield_ttc_margin=vehicle_params.yield_ttc_margin,
                            yield_activation_distance=vehicle_params.yield_activation_distance,
                            yield_hold_distance=vehicle_params.yield_hold_distance,
                            yield_release_time=vehicle_params.yield_release_time,
                            yield_release_clearance_margin=vehicle_params.yield_release_clearance_margin,
                            yield_observed_caution_enabled=vehicle_params.yield_observed_caution_enabled,
                            yield_observed_caution_distance=vehicle_params.yield_observed_caution_distance,
                            yield_observed_caution_min_target_speed=vehicle_params.yield_observed_caution_min_target_speed,
                            yield_steer_damping=vehicle_params.yield_steer_damping,
                            yield_recovery_enabled=vehicle_params.yield_recovery_enabled,
                            yield_recovery_steps=vehicle_params.yield_recovery_steps,
                            yield_recovery_regen_period=vehicle_params.yield_recovery_regen_period,
                            yield_recovery_max_lateral_error=vehicle_params.yield_recovery_max_lateral_error,
                            yield_recovery_speed=vehicle_params.yield_recovery_speed,
                            yield_recovery_accel=vehicle_params.yield_recovery_accel,
                            completion_s_margin=vehicle_params.completion_s_margin,
                            completion_goal_dist=vehicle_params.completion_goal_dist,
                            completion_lateral_error=vehicle_params.completion_lateral_error,
                            completion_heading_error=vehicle_params.completion_heading_error,
                            completion_lane_entry_goal_dist=vehicle_params.completion_lane_entry_goal_dist,
                            completion_lane_entry_heading_error=vehicle_params.completion_lane_entry_heading_error,
                            completion_exit_alignment_min_s_after_goal=vehicle_params.completion_exit_alignment_min_s_after_goal,
                            post_goal_reference_extension_m=vehicle_params.post_goal_reference_extension_m,
                            route_goal_extension_m=vehicle_params.route_goal_extension_m,
                            exit_alignment_path_enabled=vehicle_params.exit_alignment_path_enabled,
                            exit_alignment_path_length=vehicle_params.exit_alignment_path_length,
                            exit_alignment_distance_after_goal=vehicle_params.exit_alignment_distance_after_goal,
                            exit_alignment_post_clearance_speed=vehicle_params.exit_alignment_post_clearance_speed,
                            exit_alignment_post_clearance_goal_window=vehicle_params.exit_alignment_post_clearance_goal_window)
        else :
            return SMPCAgent(vehicle_actor, goal_transform.location, \
                            N=vehicle_params.N,
                            dt=vehicle_params.dt,
                            N_modes=vehicle_params.num_modes,
                            nominal_speed_mps=vehicle_params.nominal_speed,
                            smpc_config=vehicle_params.smpc_config,
                            n_tv_max=n_tv_max,
                            risk_profile=vehicle_params.risk_profile,
                            collision_d_min=vehicle_params.collision_d_min,
                            collision_ellipse_half_length=vehicle_params.collision_ellipse_half_length,
                            collision_ellipse_half_width=vehicle_params.collision_ellipse_half_width,
                            reference_regen_max_lateral_error=vehicle_params.reference_regen_max_lateral_error,
                            yield_stop_enabled=vehicle_params.yield_stop_enabled,
                            yield_stop_speed=vehicle_params.yield_stop_speed,
                            yield_reference_min_speed=vehicle_params.yield_reference_min_speed,
                            yield_reference_decel=vehicle_params.yield_reference_decel,
                            yield_stop_decel=vehicle_params.yield_stop_decel,
                            yield_conflict_radius=vehicle_params.yield_conflict_radius,
                            yield_stop_buffer_distance=vehicle_params.yield_stop_buffer_distance,
                            yield_brake_distance_margin=vehicle_params.yield_brake_distance_margin,
                            yield_wait_steer_lookahead_distance=vehicle_params.yield_wait_steer_lookahead_distance,
                            yield_wait_steer_gain=vehicle_params.yield_wait_steer_gain,
                            yield_ttc_margin=vehicle_params.yield_ttc_margin,
                            yield_activation_distance=vehicle_params.yield_activation_distance,
                            yield_hold_distance=vehicle_params.yield_hold_distance,
                            yield_release_time=vehicle_params.yield_release_time,
                            yield_release_clearance_margin=vehicle_params.yield_release_clearance_margin,
                            yield_observed_caution_enabled=vehicle_params.yield_observed_caution_enabled,
                            yield_observed_caution_distance=vehicle_params.yield_observed_caution_distance,
                            yield_observed_caution_min_target_speed=vehicle_params.yield_observed_caution_min_target_speed,
                            yield_steer_damping=vehicle_params.yield_steer_damping,
                            yield_recovery_enabled=vehicle_params.yield_recovery_enabled,
                            yield_recovery_steps=vehicle_params.yield_recovery_steps,
                            yield_recovery_regen_period=vehicle_params.yield_recovery_regen_period,
                            yield_recovery_max_lateral_error=vehicle_params.yield_recovery_max_lateral_error,
                            yield_recovery_speed=vehicle_params.yield_recovery_speed,
                            yield_recovery_accel=vehicle_params.yield_recovery_accel,
                            completion_s_margin=vehicle_params.completion_s_margin,
                            completion_goal_dist=vehicle_params.completion_goal_dist,
                            completion_lateral_error=vehicle_params.completion_lateral_error,
                            completion_heading_error=vehicle_params.completion_heading_error,
                            completion_lane_entry_goal_dist=vehicle_params.completion_lane_entry_goal_dist,
                            completion_lane_entry_heading_error=vehicle_params.completion_lane_entry_heading_error,
                            completion_exit_alignment_min_s_after_goal=vehicle_params.completion_exit_alignment_min_s_after_goal,
                            post_goal_reference_extension_m=vehicle_params.post_goal_reference_extension_m,
                            route_goal_extension_m=vehicle_params.route_goal_extension_m,
                            exit_alignment_path_enabled=vehicle_params.exit_alignment_path_enabled,
                            exit_alignment_path_length=vehicle_params.exit_alignment_path_length,
                            exit_alignment_distance_after_goal=vehicle_params.exit_alignment_distance_after_goal,
                            exit_alignment_post_clearance_speed=vehicle_params.exit_alignment_post_clearance_speed,
                            exit_alignment_post_clearance_goal_window=vehicle_params.exit_alignment_post_clearance_goal_window)
    else:
        raise ValueError(f"Unsupported policy type: {vehicle_params.policy_type}")

def get_intersection_transform(intersection, vehicle_params, endpoint_str, spawn_height=1.0, side_of_road="right"):
    node_idx            = None
    endpoint_idx        = None
    left_offset         = None
    longitudinal_offset = None

    if endpoint_str == "start":
        endpoint_idx        = 0
        node_idx            = vehicle_params.intersection_start_node_idx
        left_offset         = vehicle_params.start_left_offset
        longitudinal_offset = vehicle_params.start_longitudinal_offset

    elif endpoint_str == "goal":
        endpoint_idx        = 1
        node_idx            = vehicle_params.intersection_goal_node_idx
        left_offset         = vehicle_params.goal_left_offset
        longitudinal_offset = vehicle_params.goal_longitudinal_offset
    else:
        raise ValueError(f"Invalid endpoint:{endpoint_str}.  Expected start or goal.")

    # Extract the pose from the intersection definition.
    x, y, yaw_deg = intersection[node_idx][endpoint_idx]
    yaw_rad = np.radians(float(yaw_deg))

    # Translate the pose given the longitudinal offset.
    x += longitudinal_offset * np.cos(yaw_rad)
    y += longitudinal_offset * np.sin(yaw_rad)

    # Translate the pose laterally.  The legacy reproduction used yaw-pi/2,
    # which places vehicles on the right-hand lane in the Town05 intersection
    # used here.  For the UK scenario, side_of_road="left" intentionally flips
    # that sign so positive offsets select the visually left-hand lane.
    lateral_sign = 1.0 if str(side_of_road).lower() == "left" else -1.0
    lateral_dir_yaw = yaw_rad + lateral_sign * np.pi/2.
    x += left_offset * np.cos( lateral_dir_yaw )
    y += left_offset * np.sin( lateral_dir_yaw )

    # Make the Carla transform.
    loc = carla.Location(x = x, y = y, z = spawn_height)
    rot = carla.Rotation(yaw=yaw_deg)
    return carla.Transform(loc, rot)

def transform_to_local_frame(motion_hist_array):
    # TODO: clean up / document / move.
    local_x, local_y, local_yaw = motion_hist_array[-1, 1:]

    R_local_to_world    = np.array([[np.cos(local_yaw), -np.sin(local_yaw)],\
                                    [np.sin(local_yaw),  np.cos(local_yaw)]])
    t_local_to_world    = np.array([local_x, local_y])

    R_world_to_local =  R_local_to_world.T
    t_world_to_local = -R_local_to_world.T @ t_local_to_world

    for t in range(motion_hist_array.shape[0]):
        xy_global = motion_hist_array[t, 1:3]
        xy_local  = R_world_to_local @ xy_global + t_world_to_local
        motion_hist_array[t, 1:3] = xy_local

        pose_diff = motion_hist_array[t, 3] - local_yaw

        if ~np.isnan(pose_diff):
            motion_hist_array[t, 3] = fix_angle(pose_diff)

    return motion_hist_array, R_local_to_world, t_local_to_world

def get_target_agent_history(agent_history, target_agent_id):
    # TODO: clean up / document / move.
    snapshot = agent_history.query(history_secs = [1.0, 0.8, 0.6, 0.4, 0.2, 0.0])

    tms   = []
    poses = []

    for k in [1.0, 0.8, 0.6, 0.4, 0.2, 0.0]:
        tms.append(k)
        snapshot_key = np.round(k, 2)
        if(len(snapshot[snapshot_key]) == 0):
            poses.append([None, None, None])
        else:
            found_target = False
            for entry in snapshot[snapshot_key]['vehicles']:
                if entry['id'] == target_agent_id:
                    pose = entry['centroid']
                    pose.append(entry['yaw'])
                    poses.append( pose )
                    found_target = True
                    break
            if not found_target:
                poses.append([None, None, None])
    tms = [-v if v > 0. else 0. for v in tms]
    motion_hist_array = np.column_stack((tms, poses)).astype(np.float32)

    return transform_to_local_frame(motion_hist_array)

def get_actor_position_rhs(actor):
    location = actor.get_location()
    return np.array([location.x, -location.y])

"""
Main class to simulate and run parametrized scenarios.
"""
class RunIntersectionScenario:
    def __init__(self,
                 carla_params        : CarlaParams,
                 drone_viz_params    : DroneVizParams,
                 vehicle_params_list : List[VehicleParams],
                 prediction_params   : PredictionParams,
                 savedir : str):
        # Make the output directory available while policies are created so debug
        # instrumentation can write into the scenario subrun folder.
        self.savedir = savedir
        os.makedirs(self.savedir, exist_ok=True)
        try:
            self.side_of_road = carla_params.side_of_road
            self.traffic_control = carla_params.traffic_control
            self.priority_rule = carla_params.priority_rule
            self._setup_carla_world(carla_params)
            self._setup_vehicles(vehicle_params_list, carla_params)
            self.use_camera = drone_viz_params.visualize_opencv or drone_viz_params.save_avi
            if self.use_camera:
                self._setup_camera(drone_viz_params)
            self._setup_predictions(prediction_params)
        except Exception as e:
            self._destroy_created_actors()
            print("Failed to setup the scenario!")
            raise e

        # For logging results + videos.

        # Needed for Sync mode loop.
        self.timeout   = carla_params.timeout_period
        self.carla_fps = carla_params.fps
        self.max_iters = self.carla_fps*30 # limit scenario run to 30 seconds max

        # Needed for OpenCV/Carla world visualization.
        self.viz_params = drone_viz_params
        self.mode_rgb_colors = [(255, 0, 255), (255, 255, 0), (0, 255, 255)] # TODO: autogenerate

    def _traffic_light_state_name(self, actor):
        """Return a compact CARLA traffic-light state string, if one applies."""
        try:
            if not actor.is_at_traffic_light():
                return None
            traffic_light = actor.get_traffic_light()
            if traffic_light is None:
                return None
            return str(traffic_light.get_state()).split(".")[-1]
        except Exception:
            return "unknown"

    def _apply_optional_traffic_light_rule(self, actor, control, vehicle_params):
        """Optional red/yellow stop override for explicitly signalised scenarios."""
        state = self._traffic_light_state_name(actor)
        forced_stop = False
        if vehicle_params.obey_traffic_lights and state in {"Red", "Yellow"}:
            if state == "Red" or vehicle_params.stop_for_yellow:
                control.throttle = 0.0
                control.brake = 1.0
                control.hand_brake = False
                forced_stop = True
        return control, state, forced_stop

    def run_scenario(self):
        # Return flag to indicate if this ran to completion.
        ran_successfully = False
        rows_buffer: List[Dict[str, Any]] = []
        run_error: Optional[str] = None
        log = exp_log.get_logger()
        policy_types = [type(p).__name__ for p in self.vehicle_policies]
        log.info(
            "Intersection rollout start savedir=%s max_iters=%s fps=%s policies=%s",
            os.path.abspath(self.savedir),
            self.max_iters,
            self.carla_fps,
            policy_types,
        )
        bd = exp_log.batch_dir()
        if bd:
            exp_log.append_jsonl(
                bd,
                {
                    "event": "scenario_rollout_start",
                    "kind": "intersection",
                    "savedir": os.path.abspath(self.savedir),
                    "policy_types": policy_types,
                    "ego_N": self.ego_N,
                    "ego_num_modes": self.ego_num_modes,
                },
            )

        # Video Setup
        writer = None
        if self.viz_params.save_avi:
            avi_name = os.path.join(self.savedir, "carla_sim.avi")
            writer   = cv2.VideoWriter(avi_name, cv2.VideoWriter_fourcc(*'MJPG'), self.carla_fps, (self.viz_params.img_width, self.viz_params.img_height))

        # Data Logging Setup
        self.results_dict = {}
        for ind_vehicle, vehicle in enumerate(self.vehicle_actors):
            key = f"{vehicle.attributes['role_name']}_{ind_vehicle}"
            l_f, l_r = vehicle_name_to_lf_lr(vehicle.type_id) # e.g. "vehicle.audi.tt"
            self.results_dict[key] = {"l_f"              : l_f,
                                      "l_r"              : l_r,
                                      "state_trajectory" : [],
                                      "input_trajectory" : [],
                                      "feasibility"      : [],
                                      "solve_times"      : [],
                                      "collision_probs"  : []}

        try:
            sensors = [self.drone] if self.use_camera else []
            with CarlaSyncMode(self.world, *sensors, fps=self.carla_fps) as sync_mode:
                # Run simulation a couple steps to allow the initial velocities to be processed.

                # Set initial velocity for all vehicle agents.
                for veh_actor, init_speed in zip(self.vehicle_actors, self.vehicle_init_speeds):
                    yaw_carla = veh_actor.get_transform().rotation.yaw
                    carla_vel = carla.Vector3D(x=init_speed*np.cos(np.radians(yaw_carla)) ,
                                               y=init_speed*np.sin(np.radians(yaw_carla)) ,
                                               z=0.)
                    veh_actor.set_target_velocity(carla_vel)

                for _ in range(2):
                    sync_mode.tick(timeout=self.timeout)

                # Loop until all vehicles have reached their goal or we've exceeded self.max_iters.
                for loop_step in range(self.max_iters):
                    tick_data = sync_mode.tick(timeout=self.timeout)
                    snap = tick_data[0]
                    img = tick_data[1] if self.use_camera else None

                    # Handle predictions.
                    self.agent_history.update(snap, self.world)
                    tvs_positions, tvs_mode_probs, tvs_mode_dists, tvs_valid_pred = self._make_predictions()
                    pred_dict={ "tvs_positions": tvs_positions,
                                "tvs_mode_dists": tvs_mode_dists,
                                "tvs_mode_probs": tvs_mode_probs,
                                "tvs_valid_pred": tvs_valid_pred}

                    # Run policies for each agent.
                    t_elapsed = snap.elapsed_seconds
                    completed = True
                    ego_feasible = None
                    ego_solve_time = None
                    ego_control = None
                    ego_traffic_light_state = None
                    ego_traffic_light_forced_stop = False

                    for idx_act, (act, policy) in enumerate(zip(self.vehicle_actors, self.vehicle_policies)):
                        policy_result = policy.run_step(pred_dict)
                        if len(policy_result) == 6:
                            control, z0, u0, is_feasible, solve_time, collision_prob = policy_result
                        else:
                            control, z0, u0, is_feasible, solve_time = policy_result
                            collision_prob = np.nan
                        control, traffic_light_state, traffic_light_forced_stop = self._apply_optional_traffic_light_rule(
                            act,
                            control,
                            self.vehicle_params_list[idx_act],
                        )
                        if idx_act == self.ego_vehicle_idx:
                            ego_feasible = bool(is_feasible) if not isinstance(is_feasible, (float, np.floating)) else bool(is_feasible)
                            try:
                                ego_solve_time = float(solve_time)
                            except (TypeError, ValueError):
                                ego_solve_time = float("nan")
                            ego_control = control
                            ego_traffic_light_state = traffic_light_state
                            ego_traffic_light_forced_stop = traffic_light_forced_stop
                        if not policy.done():
                            z0 = np.append(t_elapsed, z0) # add the Carla timestamp
                            act_key = f"{act.attributes['role_name']}_{idx_act}"
                            self.results_dict[act_key]["state_trajectory"].append(z0)
                            self.results_dict[act_key]["input_trajectory"].append(u0)
                            self.results_dict[act_key]["feasibility"].append(is_feasible)
                            self.results_dict[act_key]["solve_times"].append(solve_time)
                            self.results_dict[act_key]["collision_probs"].append(collision_prob)

                        # true at the end of the loop only if all agents are done or if iter_ctr>=max_iters
                        completed = completed and policy.done()
                        act.apply_control(control)

                        if idx_act == self.ego_vehicle_idx:
                            # Keep track of ego's information for rendering.
                            ego_vel   = act.get_velocity()
                            ego_speed = np.linalg.norm([ego_vel.x, ego_vel.y])
                            ego_ctrl  = control

                    pred0 = bool(tvs_valid_pred[0]) if tvs_valid_pred else False
                    if ego_control is not None:
                        step_row = {
                            "step": loop_step,
                            "sim_time_s": float(t_elapsed),
                            "ego_feasible": ego_feasible,
                            "ego_solve_time_s": ego_solve_time,
                            "ego_throttle": float(ego_control.throttle),
                            "ego_brake": float(ego_control.brake),
                            "ego_steer": float(ego_control.steer),
                            "ego_traffic_light_state": ego_traffic_light_state,
                            "ego_traffic_light_forced_stop": bool(ego_traffic_light_forced_stop),
                            "traffic_control": self.traffic_control,
                            "side_of_road": self.side_of_road,
                            "priority_rule": self.priority_rule,
                            "pred_valid_tv0": pred0,
                        }
                        exp_log.append_step_row(self.savedir, rows_buffer, step_row, flush_every=25)

                    if self.use_camera:
                        # Get drone camera image.
                        img_drone = np.frombuffer(img.raw_data, dtype=np.uint8)
                        img_drone = np.reshape(img_drone, (img.height, img.width, 4))
                        img_drone = img_drone[:, :, :3]
                        img_drone = cv2.resize(img_drone, (self.viz_params.img_width, self.viz_params.img_height), interpolation = cv2.INTER_AREA)

                        # Handle overlays on drone camera image.
                        if self.viz_params.overlay_ego_info and ego_ctrl is not None:
                            ego_str = f"EGO - v:{ego_speed:.3f}, th: {ego_ctrl.throttle:.2f}, bk: {ego_ctrl.brake:.2f}, st: {ego_ctrl.steer:.2f}"
                            cv2.putText(img_drone, ego_str, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                        # World-fixed drone uses hardcoded world->pixel maps for GMM/traj; skip when camera follows ego.
                        if not getattr(self, "_ego_follow_cam", False):
                            if self.viz_params.overlay_gmm:
                                if tvs_valid_pred[0]:  # TODO: generalize this to multiple TVs.
                                    self._viz_gmm(img_drone, tvs_mode_dists)

                            if self.viz_params.overlay_traj_hist:
                                self._viz_traj_hist(img_drone)

                            if self.viz_params.overlay_mode_probs:
                                if tvs_valid_pred[0]:  # TODO: generalize this to multiple TVs.
                                    cv2.putText(img_drone, "Mode probabilities: ", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                                    for prob_idx, mode_prob in enumerate(tvs_mode_probs[0]):
                                        cv2.putText(
                                            img_drone,
                                            f"{mode_prob:.3f}",
                                            (360 + prob_idx * 100, 100),
                                            cv2.FONT_HERSHEY_SIMPLEX,
                                            1,
                                            self.mode_rgb_colors[prob_idx],
                                            2,
                                        )

                        # Handle visualization / saving to video.
                        if self.viz_params.visualize_opencv:
                            cv2.imshow("Drone", img_drone); cv2.waitKey(1)

                        if self.viz_params.save_avi:
                            writer.write(img_drone)

                    if completed:
                        # All cars reached their destinations, end before self.max_iters.
                        break

                # Save results and mark successful completion.
                for act_key in self.results_dict:
                    for arr_key in ["state_trajectory",
                                    "input_trajectory",
                                    "feasibility",
                                    "solve_times",
                                    "collision_probs"]:
                        self.results_dict[act_key][arr_key] = np.array(self.results_dict[act_key][arr_key])
                try:
                    from utils.map_viz_export import try_export_map_viz_snapshot

                    try_export_map_viz_snapshot(self.world, self.results_dict, self.savedir)
                except Exception as exc:
                    log.warning("map_viz_snapshot export skipped: %s", exc)
                pkl_name = os.path.join(self.savedir, "scenario_result.pkl")
                pickle.dump(self.results_dict, open(pkl_name, "wb"))
                ran_successfully = True

        except Exception:
            run_error = traceback.format_exc()
            log.exception("Intersection scenario failed savedir=%s", os.path.abspath(self.savedir))
            raise
        finally:
            exp_log.flush_step_csv(self.savedir, rows_buffer)
            extra: Dict[str, Any] = {"policy_types": policy_types}
            try:
                extra["map"] = self.world.get_map().name
            except Exception:
                pass
            try:
                exp_log.write_scenario_run_summary(
                    self.savedir,
                    scenario_kind="intersection",
                    ran_successfully=ran_successfully,
                    max_iters=self.max_iters,
                    carla_fps=self.carla_fps,
                    results_dict=getattr(self, "results_dict", None),
                    error=run_error,
                    extra=extra,
                )
            except Exception as exc:
                log.error("write_scenario_run_summary failed: %s", exc)
            if bd:
                exp_log.append_jsonl(
                    bd,
                    {
                        "event": "scenario_rollout_end",
                        "kind": "intersection",
                        "savedir": os.path.abspath(self.savedir),
                        "ran_successfully": ran_successfully,
                        "had_error": run_error is not None,
                    },
                )
            if writer:
                writer.release()
            for actor in self.vehicle_actors:
                actor.destroy()
            if self.use_camera:
                self.drone.destroy()
            cv2.destroyAllWindows()

        return ran_successfully

    def _make_predictions(self):
        if len(self.tv_vehicle_idxs) == 0:
            ego_location = self.vehicle_actors[self.ego_vehicle_idx].get_location()
            ego_x, ego_y = ego_location.x, -ego_location.y
            curr_target_vehicle_position = [1000 + ego_x, 1000 + ego_y]
            tvs_positions = [curr_target_vehicle_position]
            tvs_mode_probs = [ np.ones(self.ego_num_modes) / self.ego_num_modes ]
            tvs_mode_dists = [[np.stack([[curr_target_vehicle_position]*self.ego_N]*self.ego_num_modes)],
                              [np.stack([[np.identity(2)]*self.ego_N]*self.ego_num_modes)]]
            tvs_valid_pred = [False]
        else:
            # TODO: clean up and generalize this to many target vehicles.
            target_actor = self.vehicle_actors[self.tv_vehicle_idxs[0]]
            target_agent_id = target_actor.id
            past_states_tv, R_target_to_world, t_target_to_world = \
                get_target_agent_history(self.agent_history, target_agent_id)

            if np.any(np.isnan(past_states_tv)) or np.any(np.isnan(R_target_to_world)) or np.any(np.isnan(t_target_to_world)):
                curr_target_vehicle_position = get_actor_position_rhs(target_actor)
            else:
                curr_target_vehicle_position = R_target_to_world @ past_states_tv[-1, 1:3] + t_target_to_world
            tvs_positions = [curr_target_vehicle_position]

            if np.any(np.isnan(past_states_tv)):
                # Not enough data for predictions to be made.
                tvs_mode_probs = [ np.ones(self.ego_num_modes) / self.ego_num_modes ]
                tvs_mode_dists = [[np.stack([[curr_target_vehicle_position]*self.ego_N]*self.ego_num_modes)],
                                  [np.stack([[0.1*np.identity(2)]*self.ego_N]*self.ego_num_modes)]]
                tvs_valid_pred = [False]
            else:
                img_tv = self.rasterizer.rasterize(self.agent_history, target_agent_id)
                gmm_pred_tv = self.pred_model.predict_instance(img_tv, past_states_tv[:-1])
                gmm_pred_tv.transform(R_target_to_world, t_target_to_world)
                gmm_pred_tv=gmm_pred_tv.get_top_k_GMM(self.ego_num_modes)
                
                tvs_mode_probs = [gmm_pred_tv.mode_probabilities]
                tvs_mode_dists = [[gmm_pred_tv.mus[:, :self.ego_N, :]], [gmm_pred_tv.sigmas[:, :self.ego_N, :, :]]]
                tvs_valid_pred = [True]

        return tvs_positions, tvs_mode_probs, tvs_mode_dists, tvs_valid_pred

    def _setup_carla_world(self, carla_params):
        client = carla.Client(carla_params.ip_addr, carla_params.port)
        client.set_timeout(carla_params.timeout_period)
        current_world = client.get_world()
        current_map = current_world.get_map().name.split("/")[-1]
        if current_map == carla_params.map_str:
            self.world = current_world
        else:
            try:
                self.world = client.load_world(carla_params.map_str)
            except RuntimeError:
                # In headless/offscreen mode map loading can be slow on cold start.
                client.set_timeout(max(carla_params.timeout_period, 300.0))
                self.world = client.load_world(carla_params.map_str)
        self.world.set_weather(getattr(carla.WeatherParameters, "ClearNoon"))
        self._destroy_stale_scenario_actors()

    def _destroy_stale_scenario_actors(self):
        scenario_roles = {"ego", "static", "drone"}
        stale_actors = []
        for actor in self.world.get_actors():
            role_name = actor.attributes.get("role_name", "")
            if role_name in scenario_roles or role_name.startswith("target"):
                stale_actors.append(actor)

        if stale_actors:
            print(f"Destroying {len(stale_actors)} stale CARLA scenario actors before setup.")
            for actor in stale_actors:
                actor.destroy()
            self.world.wait_for_tick()

    def _destroy_created_actors(self):
        for actor in getattr(self, "vehicle_actors", []):
            if actor is not None and actor.is_alive:
                actor.destroy()
        drone = getattr(self, "drone", None)
        if drone is not None and drone.is_alive:
            drone.destroy()

    def _setup_camera(self, drone_viz_params):
        bp_library = self.world.get_blueprint_library()
        bp_drone  = bp_library.find('sensor.camera.rgb')

        self._ego_follow_cam = bool(getattr(drone_viz_params, "attach_to_ego", False))

        # TODO: compute these, hardcoded for now (world-fixed drone overlay math only).
        self.A_world_to_drone = np.array([[    0., -19.2],
                                          [-19.2,      0.]])
        self.b_world_to_drone = np.array([ 960., 1116.])

        bp_drone.set_attribute('image_size_x', str(drone_viz_params.img_width))
        bp_drone.set_attribute('image_size_y', str(drone_viz_params.img_height))
        bp_drone.set_attribute('fov', str(drone_viz_params.fov))
        bp_drone.set_attribute('role_name', 'drone')

        if self._ego_follow_cam:
            ego = self.vehicle_actors[self.ego_vehicle_idx]
            cam_loc = carla.Location(
                x=float(drone_viz_params.ego_cam_x_offset_m),
                y=float(drone_viz_params.ego_cam_y_offset_m),
                z=float(drone_viz_params.ego_cam_height_m),
            )
            cam_ori = carla.Rotation(
                roll=float(drone_viz_params.roll),
                pitch=float(drone_viz_params.ego_cam_pitch_deg),
                yaw=float(drone_viz_params.ego_cam_yaw_deg),
            )
            rel_tf = carla.Transform(cam_loc, cam_ori)
            self.drone = self.world.spawn_actor(
                bp_drone,
                rel_tf,
                attach_to=ego,
                attachment_type=carla.AttachmentType.Rigid,
            )
        else:
            cam_loc = carla.Location(x=drone_viz_params.x,
                                     y=drone_viz_params.y,
                                     z=drone_viz_params.z)
            cam_ori = carla.Rotation(roll=drone_viz_params.roll,
                                     pitch=drone_viz_params.pitch,
                                     yaw=drone_viz_params.yaw)
            cam_transform = carla.Transform(cam_loc, cam_ori)
            self.drone = self.world.spawn_actor(bp_drone, cam_transform)

    def _setup_vehicles(self, vehicle_params_list, carla_params):
        intersection_fname = os.path.join( os.path.dirname(os.path.abspath(__file__)),
                                           carla_params.intersection_csv_loc )
        intersection = load_intersection(intersection_fname)
        bp_library = self.world.get_blueprint_library()

        self.vehicle_actors   = []
        self.vehicle_policies = []
        self.vehicle_params_list = list(vehicle_params_list)
        self.vehicle_colors   = []
        self.vehicle_init_speeds = []
        ego_vehicle_idxs  = []
        tv_vehicle_idxs   = []
        # Must match _make_predictions: one GMM stack per ``role == "target"`` vehicle.
        n_tv_max_mpc = max(1, sum(1 for vp in vehicle_params_list if vp.role == "target"))

        for idx, vp in enumerate(vehicle_params_list):
            veh_bp = resolve_vehicle_blueprint(vp.vehicle_type, bp_library)
            veh_bp.set_attribute("color", vp.vehicle_color)
            veh_bp.set_attribute("role_name", vp.role)
            self.vehicle_colors.append([int(x) for x in vp.vehicle_color.split(", ")])

            if vp.role == "ego":
                ego_vehicle_idxs.append(idx)
            elif vp.role == "static":
                pass
            elif vp.role == "target":
                tv_vehicle_idxs.append(idx)
            else:
                raise ValueError(f"Invalid vehicle role selection : {vp.role}")

            start_transform = get_intersection_transform(intersection, vp, "start", side_of_road=carla_params.side_of_road)
            goal_transform  = get_intersection_transform(intersection, vp, "goal", side_of_road=carla_params.side_of_road)

            veh_actor  = self.world.spawn_actor(veh_bp, start_transform)
            if vp.role == "ego":
                veh_policy = get_vehicle_policy(
                    vp, veh_actor, goal_transform, n_tv_max=n_tv_max_mpc)
                if hasattr(veh_policy, "set_debug_context"):
                    veh_policy.set_debug_context(
                        self.savedir,
                        label=getattr(vp, "smpc_config", vp.policy_type),
                    )
            else:
                veh_policy = get_vehicle_policy(vp, veh_actor, goal_transform)

            self.vehicle_actors.append(veh_actor)
            self.vehicle_policies.append(veh_policy)
            self.vehicle_init_speeds.append(vp.init_speed)

        if len(ego_vehicle_idxs) != 1:
            raise RuntimeError(f"Invalid number of ego vehicles spawned: {len(ego_vehicle_idxs)}")
        self.ego_vehicle_idx = ego_vehicle_idxs[0]
        self.ego_N           = vehicle_params_list[self.ego_vehicle_idx].N
        self.ego_num_modes   = vehicle_params_list[self.ego_vehicle_idx].num_modes

        # Note: this can be empty, as checked in the _make_predictions code.
        self.tv_vehicle_idxs = tv_vehicle_idxs

    def _setup_predictions(self, prediction_params):
        traffic_light_actors = list(self.world.get_actors().filter('*traffic_light*'))
        self.agent_history = AgentHistory(list(self.vehicle_actors) + traffic_light_actors)
        self.rasterizer    = SemBoxRasterizer(self.world.get_map().get_topology(), render_traffic_lights=\
                                                 prediction_params.render_traffic_lights)
        prefix             = os.path.abspath(__file__).split('carla')[0] + 'models/'
        self.pred_model    = DeployMultiPath(prefix+prediction_params.model_weights, \
                                             np.load(prefix+prediction_params.model_anchors))

        # Try to do a sample prediction, initialize and check GPU model is working fine.
        blank_image = np.zeros((self.rasterizer.sem_rast.raster_height,
                                self.rasterizer.sem_rast.raster_width,
                                3), dtype=np.uint8)
        zero_traj   = np.column_stack(( np.arange(-1.0, 0.00, 0.2),
                                        np.zeros((5,3))
                                      )).astype(np.float32)
        self.pred_model.predict_instance(image_raw   = blank_image,
                                         past_states = zero_traj)

    def _viz_gmm(self, img, tvs_mode_dists, mdist_sq_thresh=5.991):
        mus    = tvs_mode_dists[0][0] # N_modes by N by 2
        sigmas = tvs_mode_dists[1][0] # N_modes by N by 2 by 2

        # Note: we reverse mode_dists and colors s.t. least probable mode is plotted first.
        # zip_obj = zip( reversed(mus), reversed(sigmas), reversed(self.mode_rgb_colors) )
        zip_obj = zip( mus, sigmas, self.mode_rgb_colors )

        for mean_traj, covar_traj, color in zip_obj:
            color = color[::-1] # rgb to bgr
            for (mean_xy, covar_xy) in zip(mean_traj, covar_traj):
                mu_px    = self.A_world_to_drone @ mean_xy + self.b_world_to_drone
                center_x = int(mu_px[0])
                center_y = int(mu_px[1])
                covar_px = self.A_world_to_drone @ covar_xy @ self.A_world_to_drone.T
                evals_px, evecs_px = np.linalg.eigh(covar_px)

                length_ax1 = int( np.sqrt(mdist_sq_thresh * evals_px[0]) ) # half the first axis diameter in pixels
                length_ax2 = int( np.sqrt(mdist_sq_thresh * evals_px[1]) ) # half the second axis diameter in pixels
                ang_1 = -np.degrees( np.arctan2(evecs_px[1,0], evecs_px[0,0]) ) # -ang since cv2.ellipse uses clockwise angle
                cv2.ellipse( img, (center_x, center_y), (length_ax1, length_ax2), ang_1, 0, 360, color, thickness=2)

    def _viz_traj_hist(self, img, radius=2):
        for idx_act, (act, act_color) in enumerate(zip(self.vehicle_actors,self.vehicle_colors)):
            act_key = f"{act.attributes['role_name']}_{idx_act}"
            act_traj = self.results_dict[act_key]["state_trajectory"]
            act_color = act_color[::-1] # rgb to bgr

            for act_st in act_traj:
                act_xy = np.array(act_st[1:3])
                act_px = self.A_world_to_drone @ act_xy + self.b_world_to_drone
                center_x = int(act_px[0])
                center_y = int(act_px[1])
                cv2.circle(img, (center_x, center_y), radius, act_color, thickness=-1)
