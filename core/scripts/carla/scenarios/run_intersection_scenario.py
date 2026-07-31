from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import carla
import os
import sys

import cv2
import numpy as np
import random
import pickle
import json
import traceback

scriptdir = os.path.abspath(__file__).split('carla')[0] + 'carla/'
sys.path.append(scriptdir)
from utils.carla_sync_mode import CarlaSyncMode
from utils import experiment_logging as exp_log
from policies.static_agent import StaticAgent
from policies.smpc_agent import SMPCAgent
from policies.mpc_agent import MPCAgent
from policies.straight_line_agent import StraightLineAgent
from policies.defensive_reactive_agent import DefensiveReactiveAgent
from policies.bl_smpc_agent import BLSMPCAgent

from rasterizer.agent_history import AgentHistory
from rasterizer.sem_box_rasterizer import SemBoxRasterizer
from utils.frenet_trajectory_handler import fix_angle
from utils.vehicle_geometry_utils import vehicle_name_to_lf_lr, resolve_vehicle_blueprint

scriptdir = os.path.abspath(__file__).split('scripts')[0] + 'scripts/'
sys.path.append(scriptdir)
from models.deploy_multipath_model import DeployMultiPath
from models.prediction_dataset_utils import interaction_context_from_sample
from models.interaction_sequence import (
    FEATURE_SCHEMA_ID,
    HISTORY_TIMES_S,
    aligned_history_from_agent_history,
    assert_logged_feature_equivalence,
    build_interaction_sequence,
)
from models.prediction_input_contract import (
    RASTER_CONTRACT_ID,
    raster_contract_metadata,
    raster_array_sha256,
    save_logged_raster,
)

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
    policy_type   : str # {"static", "straight", "mpc", "smpc", "blsmpc"} -> which control policy to use for this agent

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
    solver_backend : str = "gurobi"
    risk_profile : str = "upstream_code" # "upstream_code", "paper_eps_002", adaptive risk variants, or "rule_aware_static_risk"
    adaptive_risk_config : Optional[Dict[str, Any]] = None
    collision_d_min : float = 0.5
    collision_ellipse_half_length : float = 3.8
    collision_ellipse_half_width : float = 1.8
    reference_regen_max_lateral_error : float = 1.5
    yield_stop_enabled : bool = True
    yield_stop_speed : float = 0.2
    yield_caution_speed : float = 3.5
    yield_creep_speed : float = 1.5
    yield_stop_line_creep_enabled : bool = True
    yield_stop_line_creep_speed : float = 0.8
    yield_stop_line_creep_deadband : float = 0.35
    yield_stop_line_creep_clearance_slack : float = 0.75
    yield_stop_line_creep_accel : float = 0.6
    yield_stop_line_creep_safety_margin : float = 0.25
    yield_stop_line_creep_min_clearance_override : float = 0.0
    yield_dynamic_stop_clearance_enabled : bool = False
    yield_stop_clearance_slack : float = 1.0
    yield_stop_min_clearance_margin : float = 0.5
    yield_stop_clearance_override : float = 0.0
    yield_caution_decel : float = -4.0
    yield_reference_min_speed : float = 0.8
    yield_reference_decel : float = -3.75
    yield_stop_decel : float = -5.0
    yield_emergency_brake_enabled : bool = True
    yield_emergency_decel : float = -7.0
    yield_emergency_jerk_limit : float = 10.0
    yield_emergency_conflict_margin : float = 1.25
    yield_hard_stop_target_distance : float = 12.0
    yield_hard_stop_conflict_distance : float = 13.0
    yield_conflict_radius : float = 4.0
    yield_stop_buffer_distance : float = 7.0
    yield_footprint_clearance_margin : float = 1.5
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
    smpc_intersection_approach_speed_shaping_enabled : bool = False
    smpc_intersection_approach_distance : float = 16.0
    smpc_intersection_approach_speed : float = 5.0
    smpc_intersection_approach_decel : float = -3.0
    yield_planner_ownership_stress_enabled : bool = False
    yield_risk_owned_yield_enabled : bool = False
    yield_steer_damping : float = 0.25
    yield_recovery_enabled : bool = True
    yield_recovery_steps : int = 180
    yield_recovery_regen_period : int = 2
    yield_recovery_max_lateral_error : float = 12.0
    yield_recovery_speed : float = 5.5
    yield_recovery_accel : float = 1.8
    yield_supervisor_mode : str = "full"
    completion_s_margin : float = 6.0
    completion_goal_dist : float = 8.0
    completion_lateral_error : float = 4.0
    completion_heading_error : float = 0.18
    completion_lane_entry_goal_dist : float = 1.0
    completion_lane_entry_heading_error : float = 0.30
    completion_lane_entry_min_s_after_route_goal : float = 0.0
    completion_exit_alignment_min_s_after_goal : float = 4.0
    post_goal_reference_extension_m : float = 0.0
    route_goal_extension_m : float = 0.0
    exit_alignment_path_enabled : bool = False
    exit_alignment_path_length : float = 10.0
    exit_alignment_distance_after_goal : float = 0.0
    exit_alignment_post_clearance_speed : float = 4.0
    exit_alignment_post_clearance_goal_window : float = 0.0
    lane_entry_heading_cost_enabled : bool = False
    lane_entry_heading_cost_goal_window : float = 8.0
    lane_entry_heading_cost_weight : float = 0.2
    lane_entry_heading_cost_max_abs_epsi : float = 0.35

    # Traffic-rule metadata.  ``traffic_role`` is descriptive.  ``obey_traffic_lights``
    # enables an optional safety override for signalised scenarios; the UK give-way
    # scenario leaves this disabled so that yielding comes from SMPC risk constraints.
    traffic_role : str = ""
    obey_traffic_lights : bool = False
    stop_for_yellow : bool = True

    # V2 target behavior. Values remain provisional until Day 5 development
    # smoke on init 01-05 freezes the reactive rule.
    target_style : str = "assertive_constant_speed"
    reactive_caution_speed : float = 4.5
    reactive_minimum_speed : float = 2.5
    reactive_activation_distance : float = 30.0
    reactive_release_clearance : float = 5.0
    reactive_arrival_time_gap : float = 2.0
    reactive_closest_approach_time : float = 4.0
    reactive_closest_approach_distance : float = 6.0
    reactive_release_hold : float = 0.8

@dataclass(frozen=True)
class PredictionParams:
    # Model parameter locations, given relative to <ROOTDIR>/scripts/models/
    model_weights         : str = "l5kit_multipath_10/"
    model_anchors         : str = "l5kit_clusters_16.npy"

    # Flag to render traffic lights on rasterized image for prediction.
    render_traffic_lights : bool = False

    # Optional prediction dataset logging for calibration/fine-tuning.
    prediction_logging_enabled : bool = False
    prediction_logging_stride : int = 1
    prediction_logging_horizon : int = 10
    prediction_logging_save_raster : bool = False
    prediction_dataset_metadata : Optional[Dict[str, Any]] = None

    # TODO: future work includes things like how often to update preds (if not at the Carla fps).

def resolve_model_asset_path(model_root: str, asset_path: str) -> str:
    if os.path.isabs(asset_path):
        return asset_path
    return os.path.join(model_root, asset_path)

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

def get_vehicle_policy(
    vehicle_params,
    vehicle_actor,
    goal_transform,
    n_tv_max=None,
    conflict_point_rhs=None,
):
    if vehicle_params.policy_type == "static":
        return StaticAgent(vehicle_actor, goal_transform.location)
    elif vehicle_params.policy_type == "straight":
        return StraightLineAgent(vehicle_actor, goal_transform.location,
                                 nominal_speed_mps=vehicle_params.nominal_speed,
                                 dt=vehicle_params.dt)
    elif vehicle_params.policy_type == "defensive_reactive":
        if conflict_point_rhs is None:
            raise ValueError("defensive_reactive target requires a route conflict point")
        return DefensiveReactiveAgent(
            vehicle_actor,
            goal_transform.location,
            conflict_point_rhs=conflict_point_rhs,
            nominal_speed_mps=vehicle_params.nominal_speed,
            dt=vehicle_params.dt,
            caution_speed_mps=vehicle_params.reactive_caution_speed,
            minimum_speed_mps=vehicle_params.reactive_minimum_speed,
            activation_distance_m=vehicle_params.reactive_activation_distance,
            release_clearance_m=vehicle_params.reactive_release_clearance,
            arrival_time_gap_s=vehicle_params.reactive_arrival_time_gap,
            closest_approach_time_s=vehicle_params.reactive_closest_approach_time,
            closest_approach_distance_m=vehicle_params.reactive_closest_approach_distance,
            release_hold_s=vehicle_params.reactive_release_hold,
        )
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
                            yield_caution_speed=vehicle_params.yield_caution_speed,
                            yield_creep_speed=vehicle_params.yield_creep_speed,
                            yield_stop_line_creep_enabled=vehicle_params.yield_stop_line_creep_enabled,
                            yield_stop_line_creep_speed=vehicle_params.yield_stop_line_creep_speed,
                            yield_stop_line_creep_deadband=vehicle_params.yield_stop_line_creep_deadband,
                            yield_stop_line_creep_clearance_slack=vehicle_params.yield_stop_line_creep_clearance_slack,
                            yield_stop_line_creep_accel=vehicle_params.yield_stop_line_creep_accel,
                            yield_stop_line_creep_safety_margin=vehicle_params.yield_stop_line_creep_safety_margin,
                            yield_stop_line_creep_min_clearance_override=vehicle_params.yield_stop_line_creep_min_clearance_override,
                            yield_dynamic_stop_clearance_enabled=vehicle_params.yield_dynamic_stop_clearance_enabled,
                            yield_stop_clearance_slack=vehicle_params.yield_stop_clearance_slack,
                            yield_stop_min_clearance_margin=vehicle_params.yield_stop_min_clearance_margin,
                            yield_stop_clearance_override=vehicle_params.yield_stop_clearance_override,
                            yield_caution_decel=vehicle_params.yield_caution_decel,
                            yield_reference_min_speed=vehicle_params.yield_reference_min_speed,
                            yield_reference_decel=vehicle_params.yield_reference_decel,
                            yield_stop_decel=vehicle_params.yield_stop_decel,
                            yield_emergency_brake_enabled=vehicle_params.yield_emergency_brake_enabled,
                            yield_emergency_decel=vehicle_params.yield_emergency_decel,
                            yield_emergency_jerk_limit=vehicle_params.yield_emergency_jerk_limit,
                            yield_emergency_conflict_margin=vehicle_params.yield_emergency_conflict_margin,
                            yield_hard_stop_target_distance=vehicle_params.yield_hard_stop_target_distance,
                            yield_hard_stop_conflict_distance=vehicle_params.yield_hard_stop_conflict_distance,
                            yield_conflict_radius=vehicle_params.yield_conflict_radius,
                            yield_stop_buffer_distance=vehicle_params.yield_stop_buffer_distance,
                            yield_footprint_clearance_margin=vehicle_params.yield_footprint_clearance_margin,
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
                            smpc_intersection_approach_speed_shaping_enabled=vehicle_params.smpc_intersection_approach_speed_shaping_enabled,
                            smpc_intersection_approach_distance=vehicle_params.smpc_intersection_approach_distance,
                            smpc_intersection_approach_speed=vehicle_params.smpc_intersection_approach_speed,
                            smpc_intersection_approach_decel=vehicle_params.smpc_intersection_approach_decel,
                            yield_planner_ownership_stress_enabled=vehicle_params.yield_planner_ownership_stress_enabled,
                            yield_risk_owned_yield_enabled=vehicle_params.yield_risk_owned_yield_enabled,
                            yield_steer_damping=vehicle_params.yield_steer_damping,
                            yield_recovery_enabled=vehicle_params.yield_recovery_enabled,
                            yield_recovery_steps=vehicle_params.yield_recovery_steps,
                            yield_recovery_regen_period=vehicle_params.yield_recovery_regen_period,
                            yield_recovery_max_lateral_error=vehicle_params.yield_recovery_max_lateral_error,
                            yield_recovery_speed=vehicle_params.yield_recovery_speed,
                            yield_recovery_accel=vehicle_params.yield_recovery_accel,
                            yield_supervisor_mode=vehicle_params.yield_supervisor_mode,
                            completion_s_margin=vehicle_params.completion_s_margin,
                            completion_goal_dist=vehicle_params.completion_goal_dist,
                            completion_lateral_error=vehicle_params.completion_lateral_error,
                            completion_heading_error=vehicle_params.completion_heading_error,
                            completion_lane_entry_goal_dist=vehicle_params.completion_lane_entry_goal_dist,
                            completion_lane_entry_heading_error=vehicle_params.completion_lane_entry_heading_error,
                            completion_lane_entry_min_s_after_route_goal=vehicle_params.completion_lane_entry_min_s_after_route_goal,
                            completion_exit_alignment_min_s_after_goal=vehicle_params.completion_exit_alignment_min_s_after_goal,
                            post_goal_reference_extension_m=vehicle_params.post_goal_reference_extension_m,
                            route_goal_extension_m=vehicle_params.route_goal_extension_m,
                            exit_alignment_path_enabled=vehicle_params.exit_alignment_path_enabled,
                            exit_alignment_path_length=vehicle_params.exit_alignment_path_length,
                            exit_alignment_distance_after_goal=vehicle_params.exit_alignment_distance_after_goal,
                            exit_alignment_post_clearance_speed=vehicle_params.exit_alignment_post_clearance_speed,
                            exit_alignment_post_clearance_goal_window=vehicle_params.exit_alignment_post_clearance_goal_window,
                            lane_entry_heading_cost_enabled=vehicle_params.lane_entry_heading_cost_enabled,
                            lane_entry_heading_cost_goal_window=vehicle_params.lane_entry_heading_cost_goal_window,
                            lane_entry_heading_cost_weight=vehicle_params.lane_entry_heading_cost_weight,
                            lane_entry_heading_cost_max_abs_epsi=vehicle_params.lane_entry_heading_cost_max_abs_epsi,
                            adaptive_risk_config=vehicle_params.adaptive_risk_config)
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
                            yield_caution_speed=vehicle_params.yield_caution_speed,
                            yield_creep_speed=vehicle_params.yield_creep_speed,
                            yield_stop_line_creep_enabled=vehicle_params.yield_stop_line_creep_enabled,
                            yield_stop_line_creep_speed=vehicle_params.yield_stop_line_creep_speed,
                            yield_stop_line_creep_deadband=vehicle_params.yield_stop_line_creep_deadband,
                            yield_stop_line_creep_clearance_slack=vehicle_params.yield_stop_line_creep_clearance_slack,
                            yield_stop_line_creep_accel=vehicle_params.yield_stop_line_creep_accel,
                            yield_stop_line_creep_safety_margin=vehicle_params.yield_stop_line_creep_safety_margin,
                            yield_stop_line_creep_min_clearance_override=vehicle_params.yield_stop_line_creep_min_clearance_override,
                            yield_dynamic_stop_clearance_enabled=vehicle_params.yield_dynamic_stop_clearance_enabled,
                            yield_stop_clearance_slack=vehicle_params.yield_stop_clearance_slack,
                            yield_stop_min_clearance_margin=vehicle_params.yield_stop_min_clearance_margin,
                            yield_stop_clearance_override=vehicle_params.yield_stop_clearance_override,
                            yield_caution_decel=vehicle_params.yield_caution_decel,
                            yield_reference_min_speed=vehicle_params.yield_reference_min_speed,
                            yield_reference_decel=vehicle_params.yield_reference_decel,
                            yield_stop_decel=vehicle_params.yield_stop_decel,
                            yield_emergency_brake_enabled=vehicle_params.yield_emergency_brake_enabled,
                            yield_emergency_decel=vehicle_params.yield_emergency_decel,
                            yield_emergency_jerk_limit=vehicle_params.yield_emergency_jerk_limit,
                            yield_emergency_conflict_margin=vehicle_params.yield_emergency_conflict_margin,
                            yield_hard_stop_target_distance=vehicle_params.yield_hard_stop_target_distance,
                            yield_hard_stop_conflict_distance=vehicle_params.yield_hard_stop_conflict_distance,
                            yield_conflict_radius=vehicle_params.yield_conflict_radius,
                            yield_stop_buffer_distance=vehicle_params.yield_stop_buffer_distance,
                            yield_footprint_clearance_margin=vehicle_params.yield_footprint_clearance_margin,
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
                            smpc_intersection_approach_speed_shaping_enabled=vehicle_params.smpc_intersection_approach_speed_shaping_enabled,
                            smpc_intersection_approach_distance=vehicle_params.smpc_intersection_approach_distance,
                            smpc_intersection_approach_speed=vehicle_params.smpc_intersection_approach_speed,
                            smpc_intersection_approach_decel=vehicle_params.smpc_intersection_approach_decel,
                            yield_planner_ownership_stress_enabled=vehicle_params.yield_planner_ownership_stress_enabled,
                            yield_risk_owned_yield_enabled=vehicle_params.yield_risk_owned_yield_enabled,
                            yield_steer_damping=vehicle_params.yield_steer_damping,
                            yield_recovery_enabled=vehicle_params.yield_recovery_enabled,
                            yield_recovery_steps=vehicle_params.yield_recovery_steps,
                            yield_recovery_regen_period=vehicle_params.yield_recovery_regen_period,
                            yield_recovery_max_lateral_error=vehicle_params.yield_recovery_max_lateral_error,
                            yield_recovery_speed=vehicle_params.yield_recovery_speed,
                            yield_recovery_accel=vehicle_params.yield_recovery_accel,
                            yield_supervisor_mode=vehicle_params.yield_supervisor_mode,
                            completion_s_margin=vehicle_params.completion_s_margin,
                            completion_goal_dist=vehicle_params.completion_goal_dist,
                            completion_lateral_error=vehicle_params.completion_lateral_error,
                            completion_heading_error=vehicle_params.completion_heading_error,
                            completion_lane_entry_goal_dist=vehicle_params.completion_lane_entry_goal_dist,
                            completion_lane_entry_heading_error=vehicle_params.completion_lane_entry_heading_error,
                            completion_lane_entry_min_s_after_route_goal=vehicle_params.completion_lane_entry_min_s_after_route_goal,
                            completion_exit_alignment_min_s_after_goal=vehicle_params.completion_exit_alignment_min_s_after_goal,
                            post_goal_reference_extension_m=vehicle_params.post_goal_reference_extension_m,
                            route_goal_extension_m=vehicle_params.route_goal_extension_m,
                            exit_alignment_path_enabled=vehicle_params.exit_alignment_path_enabled,
                            exit_alignment_path_length=vehicle_params.exit_alignment_path_length,
                            exit_alignment_distance_after_goal=vehicle_params.exit_alignment_distance_after_goal,
                            exit_alignment_post_clearance_speed=vehicle_params.exit_alignment_post_clearance_speed,
                            exit_alignment_post_clearance_goal_window=vehicle_params.exit_alignment_post_clearance_goal_window,
                            lane_entry_heading_cost_enabled=vehicle_params.lane_entry_heading_cost_enabled,
                            lane_entry_heading_cost_goal_window=vehicle_params.lane_entry_heading_cost_goal_window,
                            lane_entry_heading_cost_weight=vehicle_params.lane_entry_heading_cost_weight,
                            lane_entry_heading_cost_max_abs_epsi=vehicle_params.lane_entry_heading_cost_max_abs_epsi,
                            adaptive_risk_config=vehicle_params.adaptive_risk_config)
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
                            yield_caution_speed=vehicle_params.yield_caution_speed,
                            yield_creep_speed=vehicle_params.yield_creep_speed,
                            yield_stop_line_creep_enabled=vehicle_params.yield_stop_line_creep_enabled,
                            yield_stop_line_creep_speed=vehicle_params.yield_stop_line_creep_speed,
                            yield_stop_line_creep_deadband=vehicle_params.yield_stop_line_creep_deadband,
                            yield_stop_line_creep_clearance_slack=vehicle_params.yield_stop_line_creep_clearance_slack,
                            yield_stop_line_creep_accel=vehicle_params.yield_stop_line_creep_accel,
                            yield_stop_line_creep_safety_margin=vehicle_params.yield_stop_line_creep_safety_margin,
                            yield_stop_line_creep_min_clearance_override=vehicle_params.yield_stop_line_creep_min_clearance_override,
                            yield_dynamic_stop_clearance_enabled=vehicle_params.yield_dynamic_stop_clearance_enabled,
                            yield_stop_clearance_slack=vehicle_params.yield_stop_clearance_slack,
                            yield_stop_min_clearance_margin=vehicle_params.yield_stop_min_clearance_margin,
                            yield_stop_clearance_override=vehicle_params.yield_stop_clearance_override,
                            yield_caution_decel=vehicle_params.yield_caution_decel,
                            yield_reference_min_speed=vehicle_params.yield_reference_min_speed,
                            yield_reference_decel=vehicle_params.yield_reference_decel,
                            yield_stop_decel=vehicle_params.yield_stop_decel,
                            yield_emergency_brake_enabled=vehicle_params.yield_emergency_brake_enabled,
                            yield_emergency_decel=vehicle_params.yield_emergency_decel,
                            yield_emergency_jerk_limit=vehicle_params.yield_emergency_jerk_limit,
                            yield_emergency_conflict_margin=vehicle_params.yield_emergency_conflict_margin,
                            yield_hard_stop_target_distance=vehicle_params.yield_hard_stop_target_distance,
                            yield_hard_stop_conflict_distance=vehicle_params.yield_hard_stop_conflict_distance,
                            yield_conflict_radius=vehicle_params.yield_conflict_radius,
                            yield_stop_buffer_distance=vehicle_params.yield_stop_buffer_distance,
                            yield_footprint_clearance_margin=vehicle_params.yield_footprint_clearance_margin,
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
                            smpc_intersection_approach_speed_shaping_enabled=vehicle_params.smpc_intersection_approach_speed_shaping_enabled,
                            smpc_intersection_approach_distance=vehicle_params.smpc_intersection_approach_distance,
                            smpc_intersection_approach_speed=vehicle_params.smpc_intersection_approach_speed,
                            smpc_intersection_approach_decel=vehicle_params.smpc_intersection_approach_decel,
                            yield_planner_ownership_stress_enabled=vehicle_params.yield_planner_ownership_stress_enabled,
                            yield_risk_owned_yield_enabled=vehicle_params.yield_risk_owned_yield_enabled,
                            yield_steer_damping=vehicle_params.yield_steer_damping,
                            yield_recovery_enabled=vehicle_params.yield_recovery_enabled,
                            yield_recovery_steps=vehicle_params.yield_recovery_steps,
                            yield_recovery_regen_period=vehicle_params.yield_recovery_regen_period,
                            yield_recovery_max_lateral_error=vehicle_params.yield_recovery_max_lateral_error,
                            yield_recovery_speed=vehicle_params.yield_recovery_speed,
                            yield_recovery_accel=vehicle_params.yield_recovery_accel,
                            yield_supervisor_mode=vehicle_params.yield_supervisor_mode,
                            completion_s_margin=vehicle_params.completion_s_margin,
                            completion_goal_dist=vehicle_params.completion_goal_dist,
                            completion_lateral_error=vehicle_params.completion_lateral_error,
                            completion_heading_error=vehicle_params.completion_heading_error,
                            completion_lane_entry_goal_dist=vehicle_params.completion_lane_entry_goal_dist,
                            completion_lane_entry_heading_error=vehicle_params.completion_lane_entry_heading_error,
                            completion_lane_entry_min_s_after_route_goal=vehicle_params.completion_lane_entry_min_s_after_route_goal,
                            completion_exit_alignment_min_s_after_goal=vehicle_params.completion_exit_alignment_min_s_after_goal,
                            post_goal_reference_extension_m=vehicle_params.post_goal_reference_extension_m,
                            route_goal_extension_m=vehicle_params.route_goal_extension_m,
                            exit_alignment_path_enabled=vehicle_params.exit_alignment_path_enabled,
                            exit_alignment_path_length=vehicle_params.exit_alignment_path_length,
                            exit_alignment_distance_after_goal=vehicle_params.exit_alignment_distance_after_goal,
                            exit_alignment_post_clearance_speed=vehicle_params.exit_alignment_post_clearance_speed,
                            exit_alignment_post_clearance_goal_window=vehicle_params.exit_alignment_post_clearance_goal_window,
                            lane_entry_heading_cost_enabled=vehicle_params.lane_entry_heading_cost_enabled,
                            lane_entry_heading_cost_goal_window=vehicle_params.lane_entry_heading_cost_goal_window,
                            lane_entry_heading_cost_weight=vehicle_params.lane_entry_heading_cost_weight,
                            lane_entry_heading_cost_max_abs_epsi=vehicle_params.lane_entry_heading_cost_max_abs_epsi,
                            adaptive_risk_config=vehicle_params.adaptive_risk_config)
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


def get_route_conflict_point_rhs(
    start_a,
    goal_a,
    start_b=None,
    goal_b=None,
    *,
    ego_route_points_rhs=None,
):
    """Return the target-line conflict point in the right-handed world frame.

    A turning ego route must be represented by its generated reference path.
    Intersecting the start-to-goal chord with the target line places the
    conflict point outside the actual turn in the Town05 give-way scenario.
    The route-aware branch deliberately mirrors SMPCAgent's
    ``ego_route_target_motion_line`` geometry.

    ``start_b``/``goal_b`` remain as a compatibility fallback for straight
    routes only.
    """

    p = np.asarray([start_a.location.x, -start_a.location.y], dtype=float)
    r = np.asarray(
        [goal_a.location.x - start_a.location.x, -(goal_a.location.y - start_a.location.y)],
        dtype=float,
    )
    r_norm = float(np.linalg.norm(r))
    if r_norm < 1.0e-8:
        raise ValueError("Target route has zero length")
    target_dir = r / r_norm

    if ego_route_points_rhs is not None:
        ego_route = np.asarray(ego_route_points_rhs, dtype=float)
        if ego_route.ndim != 2 or ego_route.shape[0] < 2 or ego_route.shape[1] < 2:
            raise ValueError("ego_route_points_rhs must have shape [N>=2, >=2]")
        ego_xy = ego_route[:, :2]
        progress = (ego_xy - p) @ target_dir
        projected = p + progress[:, None] * target_dir[None, :]
        distances = np.linalg.norm(ego_xy - projected, axis=1)
        return projected[int(np.argmin(distances))]

    if start_b is None or goal_b is None:
        raise ValueError("A route-aware ego path or a straight route line is required")
    q = np.asarray([start_b.location.x, -start_b.location.y], dtype=float)
    s = np.asarray(
        [goal_b.location.x - start_b.location.x, -(goal_b.location.y - start_b.location.y)],
        dtype=float,
    )
    cross = float(r[0] * s[1] - r[1] * s[0])
    if abs(cross) < 1.0e-8:
        raise ValueError("Target and ego route centre lines are parallel")
    q_minus_p = q - p
    t = float((q_minus_p[0] * s[1] - q_minus_p[1] * s[0]) / cross)
    return p + t * r


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
        self.completion_tail_iters = max(1, int(round(self.carla_fps * 1.0)))

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

    def _json_safe(self, value):
        if isinstance(value, np.ndarray):
            return self._json_safe(value.tolist())
        if isinstance(value, (np.floating, float)):
            value = float(value)
            return value if np.isfinite(value) else None
        if isinstance(value, (np.integer, int)):
            return int(value)
        if isinstance(value, (np.bool_, bool)):
            return bool(value)
        if isinstance(value, list):
            return [self._json_safe(v) for v in value]
        if isinstance(value, tuple):
            return [self._json_safe(v) for v in value]
        if isinstance(value, dict):
            return {str(k): self._json_safe(v) for k, v in value.items()}
        return value

    def _actor_state_for_prediction_log(self, actor):
        tf = actor.get_transform()
        vel = actor.get_velocity()
        return {
            "x": float(tf.location.x),
            "y_rhs": float(-tf.location.y),
            "yaw_deg": float(tf.rotation.yaw),
            "yaw_rad_rhs": float(-np.radians(tf.rotation.yaw)),
            "vx_rhs": float(vel.x),
            "vy_rhs": float(-vel.y),
            "speed": float(np.linalg.norm([vel.x, vel.y])),
        }

    def _append_prediction_jsonl(self, filename, payload):
        with open(os.path.join(self._prediction_log_dir, filename), "a", encoding="utf-8") as f:
            f.write(json.dumps(self._json_safe(payload), separators=(",", ":")) + "\n")

    def _record_prediction_sample(
        self,
        target_actor,
        target_vehicle_idx,
        target_agent_id,
        img_tv,
        past_states_tv,
        R_target_to_world,
        t_target_to_world,
        gmm_pred_tv,
    ):
        if not getattr(self, "_prediction_logging_enabled", False):
            return
        loop_step = int(getattr(self, "_current_loop_step", -1))
        if loop_step < 0 or loop_step % self._prediction_logging_stride != 0:
            return

        sample_id = len(self._prediction_samples)
        raster_relpath = None
        raster_uint8_sha256 = None
        if self._prediction_logging_save_raster:
            raster_relpath = f"rasters/sample_{sample_id:06d}.png"
            raster_path = os.path.join(self._prediction_log_dir, raster_relpath)
            canonical_raster = save_logged_raster(raster_path, img_tv)
            raster_uint8_sha256 = raster_array_sha256(canonical_raster)

        aligned_history = aligned_history_from_agent_history(
            self.agent_history,
            self.vehicle_actors[self.ego_vehicle_idx].id,
            target_agent_id,
            history_times_s=HISTORY_TIMES_S,
        )
        interaction = build_interaction_sequence(
            aligned_history,
            history_times_s=HISTORY_TIMES_S,
        )
        target_params = self.vehicle_params_list[target_vehicle_idx]
        target_policy = self.vehicle_policies[target_vehicle_idx]
        if hasattr(target_policy, "parameters"):
            target_style_parameters = target_policy.parameters()
        else:
            target_style_parameters = {
                "controller": type(target_policy).__name__,
                "nominal_speed_mps": float(target_params.nominal_speed),
            }
        target_diagnostics = (
            target_policy.diagnostics()
            if hasattr(target_policy, "diagnostics")
            else {
                "style": "assertive_constant_speed",
                "active": False,
                "triggered_this_step": False,
                "released_this_step": False,
            }
        )

        sample = dict(getattr(self, "_prediction_dataset_metadata", {}))
        sample.update({
            "sample_id": sample_id,
            "step": loop_step,
            "sim_time_s": float(getattr(self, "_current_sim_time", np.nan)),
            "target_vehicle_idx": int(target_vehicle_idx),
            "target_actor_id": int(target_agent_id),
            "raster_relpath": raster_relpath,
            "raster_contract_id": RASTER_CONTRACT_ID,
            "raster_uint8_sha256": raster_uint8_sha256,
            "past_states_local": np.asarray(past_states_tv[:-1], dtype=float),
            "history_times_s": list(HISTORY_TIMES_S),
            "feature_schema_id": FEATURE_SCHEMA_ID,
            "interaction_history_world": aligned_history,
            "interaction_sequence": interaction.values,
            "interaction_sequence_mask": interaction.mask,
            "target_to_world_R": np.asarray(R_target_to_world, dtype=float),
            "target_to_world_t": np.asarray(t_target_to_world, dtype=float),
            "mode_probabilities": np.asarray(gmm_pred_tv.mode_probabilities, dtype=float),
            "pred_mus_world": np.asarray(gmm_pred_tv.mus[:, :self.ego_N, :], dtype=float),
            "pred_sigmas_world": np.asarray(gmm_pred_tv.sigmas[:, :self.ego_N, :, :], dtype=float),
            "ego_state": self._actor_state_for_prediction_log(self.vehicle_actors[self.ego_vehicle_idx]),
            "target_state": self._actor_state_for_prediction_log(target_actor),
            "target_style": str(target_params.target_style),
            "target_style_parameters": target_style_parameters,
            "target_reactive_diagnostics": target_diagnostics,
            "target_speed_mps": float(target_params.nominal_speed),
            "target_start_offset_m": float(target_params.start_longitudinal_offset),
            "prediction_horizon_steps": int(self._prediction_logging_horizon),
            "horizon_steps": int(self._prediction_logging_horizon),
            "dt_s": float(self.vehicle_params_list[self.ego_vehicle_idx].dt),
            "dt": float(self.vehicle_params_list[self.ego_vehicle_idx].dt),
            "model_weights": getattr(self, "_prediction_model_weights", None),
            "model_anchors": getattr(self, "_prediction_model_anchors", None),
        })
        sample["interaction_context"] = interaction_context_from_sample(sample).tolist()
        assert_logged_feature_equivalence(sample)
        self._prediction_samples.append(sample)

    def _flush_prediction_sample_after_controls(self, loop_step):
        """Attach same-step target diagnostics, then persist the pending sample."""

        if not self._prediction_samples:
            return
        sample = self._prediction_samples[-1]
        sample_id = int(sample["sample_id"])
        if int(sample["step"]) != int(loop_step) or sample_id in self._prediction_raw_written:
            return
        target_idx = int(sample["target_vehicle_idx"])
        target_actor = self.vehicle_actors[target_idx]
        target_policy = self.vehicle_policies[target_idx]
        sample["target_state"] = self._actor_state_for_prediction_log(target_actor)
        sample["target_actual_speed_mps"] = sample["target_state"]["speed"]
        if hasattr(target_policy, "diagnostics"):
            sample["target_reactive_diagnostics"] = target_policy.diagnostics()
        self._append_prediction_jsonl("prediction_dataset_raw.jsonl", sample)
        self._prediction_raw_written.add(sample_id)

    def _interp_xy_at_times(self, trajectory, query_times):
        trajectory = np.asarray(trajectory)
        if trajectory.ndim != 2 or trajectory.shape[0] < 2 or trajectory.shape[1] < 3:
            return [[None, None] for _ in query_times], [False for _ in query_times]
        times = trajectory[:, 0].astype(float)
        xy = trajectory[:, 1:3].astype(float)
        labels = []
        valid = []
        for query_time in query_times:
            if query_time < times[0] or query_time > times[-1]:
                labels.append([None, None])
                valid.append(False)
                continue
            labels.append([
                float(np.interp(query_time, times, xy[:, 0])),
                float(np.interp(query_time, times, xy[:, 1])),
            ])
            valid.append(True)
        return labels, valid

    def _finalize_prediction_dataset(self):
        if not getattr(self, "_prediction_logging_enabled", False):
            return
        labeled_path = os.path.join(self._prediction_log_dir, "prediction_dataset_labeled.jsonl")
        open(labeled_path, "w", encoding="utf-8").close()
        valid_count = 0
        for sample in self._prediction_samples:
            target_idx = int(sample["target_vehicle_idx"])
            target_role = self.vehicle_actors[target_idx].attributes.get("role_name", "target")
            target_key = f"{target_role}_{target_idx}"
            target_traj = self.results_dict.get(target_key, {}).get("state_trajectory", [])
            horizon = min(int(sample["horizon_steps"]), self.ego_N)
            dt = float(sample["dt"])
            query_times = [float(sample["sim_time_s"]) + (k + 1) * dt for k in range(horizon)]
            future_xy, future_valid = self._interp_xy_at_times(target_traj, query_times)
            labeled = dict(sample)
            labeled["future_times_s"] = query_times
            labeled["future_xy_world"] = future_xy
            labeled["future_valid_mask"] = future_valid
            valid_count += int(any(future_valid))
            self._append_prediction_jsonl("prediction_dataset_labeled.jsonl", labeled)

        manifest = {
            "enabled": True,
            "dataset_metadata": getattr(self, "_prediction_dataset_metadata", {}),
            "sample_count": len(self._prediction_samples),
            "samples_with_any_future_label": valid_count,
            "raw_jsonl": "prediction_dataset_raw.jsonl",
            "labeled_jsonl": "prediction_dataset_labeled.jsonl",
            "save_raster": bool(self._prediction_logging_save_raster),
            "stride": int(self._prediction_logging_stride),
            "horizon": int(self._prediction_logging_horizon),
            "ego_N": int(self.ego_N),
            "ego_num_modes": int(self.ego_num_modes),
            "dt": float(self.vehicle_params_list[self.ego_vehicle_idx].dt),
            "model_weights": getattr(self, "_prediction_model_weights", None),
            "model_anchors": getattr(self, "_prediction_model_anchors", None),
            "raster_contract": raster_contract_metadata(),
            "feature_schema_id": FEATURE_SCHEMA_ID,
            "history_times_s": list(HISTORY_TIMES_S),
            "interaction_sequence_shape": [len(HISTORY_TIMES_S), 12],
        }
        with open(os.path.join(self._prediction_log_dir, "prediction_dataset_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(self._json_safe(manifest), f, indent=2)

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

                dynamic_completed_at = None
                # Loop until all non-static vehicles have reached their goal or we've exceeded self.max_iters.
                for loop_step in range(self.max_iters):
                    tick_data = sync_mode.tick(timeout=self.timeout)
                    snap = tick_data[0]
                    img = tick_data[1] if self.use_camera else None

                    # Handle predictions.
                    self._current_loop_step = loop_step
                    self._current_sim_time = float(snap.elapsed_seconds)
                    self.agent_history.update(snap, self.world)
                    tvs_positions, tvs_mode_probs, tvs_mode_dists, tvs_valid_pred = self._make_predictions()
                    pred_dict={ "tvs_positions": tvs_positions,
                                "tvs_mode_dists": tvs_mode_dists,
                                "tvs_mode_probs": tvs_mode_probs,
                                "tvs_valid_pred": tvs_valid_pred,
                                "ego_actor_state": self._actor_state_for_prediction_log(
                                    self.vehicle_actors[self.ego_vehicle_idx]
                                )}

                    # Run policies for each agent.
                    t_elapsed = snap.elapsed_seconds
                    dynamic_completed = True
                    ego_feasible = None
                    ego_solve_time = None
                    ego_control = None
                    ego_traffic_light_state = None
                    ego_traffic_light_forced_stop = False
                    target0_control = None

                    for idx_act, (act, policy) in enumerate(zip(self.vehicle_actors, self.vehicle_policies)):
                        vehicle_role = self.vehicle_params_list[idx_act].role
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
                        if self.tv_vehicle_idxs and idx_act == self.tv_vehicle_idxs[0]:
                            target0_control = control
                        policy_done = policy.done()
                        if not policy_done:
                            z0 = np.append(t_elapsed, z0) # add the Carla timestamp
                            act_key = f"{act.attributes['role_name']}_{idx_act}"
                            self.results_dict[act_key]["state_trajectory"].append(z0)
                            self.results_dict[act_key]["input_trajectory"].append(u0)
                            self.results_dict[act_key]["feasibility"].append(is_feasible)
                            self.results_dict[act_key]["solve_times"].append(solve_time)
                            self.results_dict[act_key]["collision_probs"].append(collision_prob)

                        # Static parked actors should not keep the rollout/video alive.
                        if vehicle_role != "static":
                            dynamic_completed = dynamic_completed and policy_done
                        act.apply_control(control)

                        if idx_act == self.ego_vehicle_idx:
                            # Keep track of ego's information for rendering.
                            ego_vel   = act.get_velocity()
                            ego_speed = np.linalg.norm([ego_vel.x, ego_vel.y])
                            ego_ctrl  = control

                    self._flush_prediction_sample_after_controls(loop_step)
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
                        if self.tv_vehicle_idxs:
                            target0 = self.vehicle_actors[self.tv_vehicle_idxs[0]]
                            target0_tf = target0.get_transform()
                            target0_vel = target0.get_velocity()
                            step_row.update({
                                "target0_x": float(target0_tf.location.x),
                                "target0_y_rhs": float(-target0_tf.location.y),
                                "target0_yaw_deg": float(target0_tf.rotation.yaw),
                                "target0_speed": float(np.linalg.norm([target0_vel.x, target0_vel.y])),
                            })
                            if target0_control is not None:
                                step_row.update({
                                    "target0_throttle": float(target0_control.throttle),
                                    "target0_brake": float(target0_control.brake),
                                    "target0_steer": float(target0_control.steer),
                                })
                            target0_policy = self.vehicle_policies[self.tv_vehicle_idxs[0]]
                            if hasattr(target0_policy, "diagnostics"):
                                diagnostics = target0_policy.diagnostics()
                                step_row.update({
                                    f"target0_reactive_{key}": value
                                    for key, value in diagnostics.items()
                                })
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

                    if dynamic_completed:
                        if dynamic_completed_at is None:
                            dynamic_completed_at = loop_step
                        if loop_step - dynamic_completed_at >= self.completion_tail_iters:
                            # All moving cars reached their destinations; keep a short visual tail
                            # and end before the fixed 30s cap.
                            break
                    else:
                        dynamic_completed_at = None

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
                self._finalize_prediction_dataset()
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
                    extra={**extra, "completion_tail_iters": self.completion_tail_iters},
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
                interaction_sample = {
                    "ego_state": self._actor_state_for_prediction_log(self.vehicle_actors[self.ego_vehicle_idx]),
                    "target_state": self._actor_state_for_prediction_log(target_actor),
                    "target_to_world_R": np.asarray(R_target_to_world, dtype=float),
                }
                interaction_context = interaction_context_from_sample(interaction_sample)
                gmm_pred_tv = self.pred_model.predict_instance(
                    img_tv,
                    past_states_tv[:-1],
                    interaction_context=interaction_context,
                )
                gmm_pred_tv.transform(R_target_to_world, t_target_to_world)
                gmm_pred_tv=gmm_pred_tv.get_top_k_GMM(self.ego_num_modes)
                self._record_prediction_sample(
                    target_actor,
                    self.tv_vehicle_idxs[0],
                    target_agent_id,
                    img_tv,
                    past_states_tv,
                    R_target_to_world,
                    t_target_to_world,
                    gmm_pred_tv,
                )
                
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
        self.vehicle_policies = [None] * len(vehicle_params_list)
        self.vehicle_params_list = list(vehicle_params_list)
        self.vehicle_colors   = []
        self.vehicle_init_speeds = []
        ego_vehicle_idxs  = []
        tv_vehicle_idxs   = []
        # Must match _make_predictions: one GMM stack per ``role == "target"`` vehicle.
        n_tv_max_mpc = max(1, sum(1 for vp in vehicle_params_list if vp.role == "target"))

        route_transforms = []
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

            route_transforms.append((start_transform, goal_transform))
            self.vehicle_actors.append(veh_actor)
            self.vehicle_init_speeds.append(vp.init_speed)

        if len(ego_vehicle_idxs) != 1:
            raise RuntimeError(f"Invalid number of ego vehicles spawned: {len(ego_vehicle_idxs)}")
        self.ego_vehicle_idx = ego_vehicle_idxs[0]
        # Construct the ego policy first so defensive targets use the exact
        # generated ego reference route, not a geometrically invalid turn chord.
        policy_creation_order = [self.ego_vehicle_idx] + [
            idx for idx in range(len(vehicle_params_list))
            if idx != self.ego_vehicle_idx
        ]
        for idx in policy_creation_order:
            vp = vehicle_params_list[idx]
            veh_actor = self.vehicle_actors[idx]
            _, goal_transform = route_transforms[idx]
            conflict_point = None
            if vp.policy_type == "defensive_reactive":
                target_start, target_goal = route_transforms[idx]
                ego_policy = self.vehicle_policies[self.ego_vehicle_idx]
                ego_route = getattr(ego_policy, "feas_ref_states", None)
                if ego_route is None:
                    raise RuntimeError(
                        "defensive_reactive target requires the ego policy's "
                        "generated reference route"
                    )
                conflict_point = get_route_conflict_point_rhs(
                    target_start,
                    target_goal,
                    ego_route_points_rhs=ego_route,
                )
            veh_policy = get_vehicle_policy(
                vp,
                veh_actor,
                goal_transform,
                n_tv_max=n_tv_max_mpc if vp.role == "ego" else None,
                conflict_point_rhs=conflict_point,
            )
            if vp.role == "ego":
                if hasattr(veh_policy, "set_debug_context"):
                    veh_policy.set_debug_context(
                        self.savedir,
                        label=getattr(vp, "smpc_config", vp.policy_type),
                    )
            self.vehicle_policies[idx] = veh_policy

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
        self._prediction_model_weights = prediction_params.model_weights
        self._prediction_model_anchors = prediction_params.model_anchors
        self._prediction_model_weights_resolved = resolve_model_asset_path(prefix, prediction_params.model_weights)
        self._prediction_model_anchors_resolved = resolve_model_asset_path(prefix, prediction_params.model_anchors)
        self._prediction_logging_enabled = bool(prediction_params.prediction_logging_enabled)
        self._prediction_logging_stride = max(1, int(prediction_params.prediction_logging_stride))
        self._prediction_logging_horizon = max(1, int(prediction_params.prediction_logging_horizon))
        self._prediction_logging_save_raster = bool(prediction_params.prediction_logging_save_raster)
        self._prediction_dataset_metadata = dict(
            prediction_params.prediction_dataset_metadata or {}
        )
        self._prediction_samples = []
        self._prediction_raw_written = set()
        self._prediction_log_dir = os.path.join(self.savedir, "prediction_dataset")
        if self._prediction_logging_enabled:
            os.makedirs(self._prediction_log_dir, exist_ok=True)
            if self._prediction_logging_save_raster:
                os.makedirs(os.path.join(self._prediction_log_dir, "rasters"), exist_ok=True)
            open(os.path.join(self._prediction_log_dir, "prediction_dataset_raw.jsonl"), "w", encoding="utf-8").close()
            with open(os.path.join(self._prediction_log_dir, "prediction_dataset_config.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "model_weights": prediction_params.model_weights,
                        "model_anchors": prediction_params.model_anchors,
                        "model_weights_resolved": self._prediction_model_weights_resolved,
                        "model_anchors_resolved": self._prediction_model_anchors_resolved,
                        "render_traffic_lights": bool(prediction_params.render_traffic_lights),
                        "stride": self._prediction_logging_stride,
                        "horizon": self._prediction_logging_horizon,
                        "save_raster": self._prediction_logging_save_raster,
                        "dataset_metadata": self._prediction_dataset_metadata,
                        "raster_contract": raster_contract_metadata(),
                        "feature_schema_id": FEATURE_SCHEMA_ID,
                        "history_times_s": list(HISTORY_TIMES_S),
                    },
                    f,
                    indent=2,
                )
        self.pred_model    = DeployMultiPath(self._prediction_model_weights_resolved, \
                                             np.load(self._prediction_model_anchors_resolved))

        # Try to do a sample prediction, initialize and check GPU model is working fine.
        blank_image = np.zeros((self.rasterizer.sem_rast.raster_height,
                                self.rasterizer.sem_rast.raster_width,
                                3), dtype=np.uint8)
        zero_traj   = np.column_stack(( np.arange(-1.0, 0.00, 0.2),
                                        np.zeros((5,3))
                                      )).astype(np.float32)
        self.pred_model.predict_instance(image_raw   = blank_image,
                                         past_states = zero_traj,
                                         interaction_context=np.zeros((8,), dtype=np.float32))

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
