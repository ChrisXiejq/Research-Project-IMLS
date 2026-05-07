import queue


class CarlaSyncMode:
    """Synchronous mode context to tick world and collect sensor data."""

    def __init__(self, world, *sensors, fps=20):
        self.world = world
        self.sensors = sensors
        self.delta_seconds = 1.0 / fps
        self._queues = []
        self._settings = None
        self.frame = None

    def __enter__(self):
        self._settings = self.world.get_settings()
        settings = self.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = self.delta_seconds
        self.frame = self.world.apply_settings(settings)

        def make_queue(register_event):
            q = queue.Queue()
            register_event(q.put)
            self._queues.append(q)

        make_queue(self.world.on_tick)
        for sensor in self.sensors:
            make_queue(sensor.listen)
        return self

    def tick(self, timeout):
        self.frame = self.world.tick()
        data = [self._retrieve_data(q, timeout) for q in self._queues]
        if not all(x.frame == self.frame for x in data):
            raise RuntimeError("Sensor frame desync detected.")
        return data

    def __exit__(self, *args, **kwargs):
        self.world.apply_settings(self._settings)

    def _retrieve_data(self, sensor_queue, timeout):
        while True:
            data = sensor_queue.get(timeout=timeout)
            if data.frame == self.frame:
                return data
