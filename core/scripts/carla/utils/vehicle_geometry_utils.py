# Scenario JSON may name blueprints that exist only in newer CARLA builds.
# Try these ids in order until blueprint_library.find() succeeds (e.g. 0.9.14).
_VEHICLE_BLUEPRINT_FALLBACKS = {
    "vehicle.mercedes-benz.coupe": (
        "vehicle.mercedes.coupe_2020",
        "vehicle.mercedes.coupe",
        "vehicle.mercedes-benz.coupe_2020",
        "vehicle.audi.tt",
    ),
}


def resolve_vehicle_blueprint(requested_id, blueprint_library):
    """Return a vehicle blueprint that exists in this CARLA build."""
    candidates = (requested_id,) + _VEHICLE_BLUEPRINT_FALLBACKS.get(requested_id, ())
    last_err = None
    for bid in candidates:
        try:
            bp = blueprint_library.find(bid)
            if bid != requested_id:
                print(f"[blueprint] '{requested_id}' not found; using '{bid}'")
            return bp
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(
        f"No vehicle blueprint found for {requested_id!r}; tried {candidates!r}. "
        f"Last error: {last_err!r}"
    ) from last_err


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
