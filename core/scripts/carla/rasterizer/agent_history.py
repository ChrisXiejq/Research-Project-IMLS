import carla
import numpy as np
from collections import deque

class ActorInfo:
	""" Class to maintain pose history and bounding box information for a single Carla actor. """
	def __init__(self, actor, history_max_length):
		self.id = actor.id
		self.type_id = actor.type_id
		self.extent = np.array([actor.bounding_box.extent.x, actor.bounding_box.extent.y])

		self.time_history = deque(maxlen=history_max_length)
		self.pose_history = deque(maxlen=history_max_length)

	def get_snapshot(self, index):
		snapshot_dict = {}
		snapshot_dict['id']       = self.id
		snapshot_dict['time']     = self.time_history[index]
		snapshot_dict['centroid'] = self.pose_history[index][:2]
		snapshot_dict['yaw']      = self.pose_history[index][2]
		snapshot_dict['extent']   = self.extent
		return snapshot_dict

	def update(self, time, transform):
		""" Add the current time and pose to the history.
		    We save this in a RHS system vs. Carla's default LHS system.
		"""
		x_rhs   = transform.location.x
		y_rhs   = -transform.location.y
		yaw_rhs = -np.radians(transform.rotation.yaw)

		self.time_history.append(time)
		self.pose_history.append([x_rhs, y_rhs, yaw_rhs])

class AgentHistory:
	""" Class to manage pose history for the vehicle/pedestrian agents.
	    Required since snapshots only contain the current agent state and not the past.
	"""
	def __init__(self, actor_list, history_max_length=20):
		""" Initialize the ActorInfo history for each agent.
		    NOTE: we assume no agents will be created/destroyed in the episode of interest.
		"""
		if hasattr(actor_list, 'filter'):
			vehicle_actors       = actor_list.filter('vehicle*')
			walker_actors        = actor_list.filter('walker*')
			traffic_light_actors = actor_list.filter('*traffic_light*')
		else:
			vehicle_actors = [actor for actor in actor_list if actor.type_id.startswith('vehicle')]
			walker_actors = [actor for actor in actor_list if actor.type_id.startswith('walker')]
			traffic_light_actors = [actor for actor in actor_list if 'traffic_light' in actor.type_id]

		# Identify all vehicles in the scene.
		self.vehicles = {actor.id : ActorInfo(actor, history_max_length) for actor in vehicle_actors}

		# Identify pedestrians in the scene.
		self.pedestrians    = {actor.id : ActorInfo(actor, history_max_length) for actor in walker_actors}

		# Identify all traffic lights in the scene.
		self.traffic_lights = {tl_actor.id : self.process_tl_actor(tl_actor)  for tl_actor in traffic_light_actors}

	@staticmethod
	def process_tl_actor(carla_tl_actor):
		location = carla_tl_actor.get_location()
		state = carla_tl_actor.state

		if state == carla.TrafficLightState.Red:
			state_str = 'red'
		elif state == carla.TrafficLightState.Yellow:
			state_str = 'yellow'
		elif state == carla.TrafficLightState.Green:
			state_str = 'green'
		else:
			raise ValueError(f"Invalid carla traffic light state: {state}")

		return [location.x, -location.y, state_str]

	def update(self, world_snapshot, world):
		""" Update the state for each relevant actor we are monitoring, given a Carla world snapshot.
		    Note we need to pass the world object too for traffic lights, since the traffic light state
		    is not available in the world snapshot.
		"""
		time = world_snapshot.timestamp.elapsed_seconds

		for veh_id in self.vehicles.keys():
			actor_snapshot = world_snapshot.find(veh_id)
			if actor_snapshot is not None:
				self.vehicles[veh_id].update( time, actor_snapshot.get_transform() )

		for ped_id in self.pedestrians.keys():
			actor_snapshot = world_snapshot.find(ped_id)
			if actor_snapshot is not None:
				self.pedestrians[ped_id].update( time, actor_snapshot.get_transform() )

		for tl_id in self.traffic_lights.keys():
			tl_actor = world.get_actor(tl_id)
			self.traffic_lights[tl_id] = self.process_tl_actor( tl_actor )

	def query(self,
		      history_secs = [0.0],  # how many seconds back should we query for each snapshot
		      closeness_eps = 0.1    # how close in seconds is acceptable to produce a valid snapshot
		):
		""" Given a set of relative timestamps looking back, returns a dictionary of "snapshots" encoding the
		    scene over these relative timestamps.  Note history_secs is meant to be nonnegative.
		"""

		snapshots = {}
		if len(self.vehicles) == 0:
			for hsec in history_secs:
				snapshots[np.round(hsec, 2)] = {}
			return snapshots

		arbitrary_veh_key = list(self.vehicles.keys())[0]
		tms = np.array(self.vehicles[arbitrary_veh_key].time_history)
		if len(tms) == 0:
			for hsec in history_secs:
				snapshots[np.round(hsec, 2)] = {}
			return snapshots

		current_tm = tms[-1]

		if np.min(history_secs) < 0.:
			raise ValueError(f"Expected to have only nonnegative history_secs but found value: {np.min(history_secs)}")

		for hsec in history_secs:
			tm_query = current_tm - hsec
			ind_closest = np.argmin( np.abs( tms - tm_query ) )
			scene_dict = {}

			if np.abs(tms[ind_closest] - tm_query) <= closeness_eps:
				scene_dict['vehicles'] = [veh.get_snapshot(ind_closest) for veh in self.vehicles.values()]
				scene_dict['pedestrians']  = [ped.get_snapshot(ind_closest) for ped in self.pedestrians.values()]

			snapshots[np.round(hsec, 2)] = scene_dict

		return snapshots
