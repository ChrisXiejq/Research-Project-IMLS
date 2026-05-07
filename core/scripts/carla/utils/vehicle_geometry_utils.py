def vehicle_name_to_lf_lr(vehicle_name):
	if vehicle_name   == "vehicle.audi.tt":
		l_f = 1.25 # guesstimated for now.
		l_r = 1.25
	elif vehicle_name in ("vehicle.mercedes-benz.coupe", "vehicle.mercedes.coupe", "vehicle.mercedes.coupe_2020"):
		l_f = 1.4  # guesstimated for now.
		l_r = 1.4
	else:
		# Fallback for unseen blueprints on newer CARLA versions.
		# Keeps experiments running even when blueprint ids differ slightly.
		l_f = 1.35
		l_r = 1.35

	return l_f, l_r
