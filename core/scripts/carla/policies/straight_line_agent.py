import carla
import os
import sys
import numpy as np

scriptdir = os.path.abspath(__file__).split('carla')[0] + 'carla/'
sys.path.append(scriptdir)
from utils import frenet_trajectory_handler as fth
from utils.low_level_control import LowLevelControl
from utils.vehicle_geometry_utils import vehicle_name_to_lf_lr


class StraightLineAgent(object):
    """Priority vehicle controller that tracks a fixed straight path.

    This is used for the oncoming priority target in the unsignalised give-way
    experiment. The target should not make evasive turns around the ego: the
    experiment rule is that the ego yields while the target continues straight.
    """

    def __init__(self, vehicle, goal_location, nominal_speed_mps=6.0, dt=0.2):
        self.vehicle = vehicle
        self.goal_location = goal_location
        self.nominal_speed = float(nominal_speed_mps)
        self.DT = float(dt)

        start_loc = self.vehicle.get_location()
        start_tf = self.vehicle.get_transform()
        self.start_xy = np.array([float(start_loc.x), -float(start_loc.y)])
        self.goal_xy = np.array([float(goal_location.x), -float(goal_location.y)])

        path_delta = self.goal_xy - self.start_xy
        if np.linalg.norm(path_delta) > 1e-3:
            self.path_yaw = float(np.arctan2(path_delta[1], path_delta[0]))
        else:
            self.path_yaw = -float(fth.fix_angle(np.radians(start_tf.rotation.yaw)))
        self.path_tangent = np.array([np.cos(self.path_yaw), np.sin(self.path_yaw)])
        self.path_left = np.array([-np.sin(self.path_yaw), np.cos(self.path_yaw)])
        self.goal_s = float(np.dot(self.goal_xy - self.start_xy, self.path_tangent))

        self.k_lateral = 0.18
        self.k_heading = 0.85
        self.max_df = 0.22
        self.max_accel = 1.5
        self.max_decel = -2.0
        self.stop_distance = 4.0

        self.lf, self.lr = vehicle_name_to_lf_lr(self.vehicle.type_id)
        self._low_level_control = LowLevelControl(vehicle)
        self.goal_reached = False

    def done(self):
        return self.goal_reached

    def run_step(self, pred_dict):
        vehicle_loc = self.vehicle.get_location()
        vehicle_tf = self.vehicle.get_transform()
        vehicle_vel = self.vehicle.get_velocity()

        x, y = float(vehicle_loc.x), -float(vehicle_loc.y)
        psi = -float(fth.fix_angle(np.radians(vehicle_tf.rotation.yaw)))
        speed = float(np.sqrt(vehicle_vel.x**2 + vehicle_vel.y**2))
        xy = np.array([x, y])

        path_rel = xy - self.start_xy
        s = float(np.dot(path_rel, self.path_tangent))
        ey = float(np.dot(path_rel, self.path_left))
        epsi = float(fth.fix_angle(psi - self.path_yaw))

        if self.goal_s > 0.0 and s >= self.goal_s - self.stop_distance:
            self.goal_reached = True

        if self.goal_reached:
            v_des = 0.0
            a_des = self.max_decel
            df_des = 0.0
        else:
            v_des = self.nominal_speed
            a_des = float(np.clip(0.8 * (v_des - speed), self.max_decel, self.max_accel))
            df_des = float(np.clip(
                -self.k_lateral * ey - self.k_heading * epsi,
                -self.max_df,
                self.max_df,
            ))

        control = self._low_level_control.update(speed, a_des, v_des, df_des)
        z0 = np.array([x, y, psi, speed])
        u0 = np.array([a_des, df_des])
        return control, z0, u0, True, np.nan
