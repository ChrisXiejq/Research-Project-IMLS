#!/usr/bin/env python3
"""CARLA Town05 spawn-only preflight for SF4 authority init106--115 candidates.

No policy, predictor, risk allocator, or treatment is executed.  The script
reproduces the scenario's actor transforms and attempts each complete spawn set
on a dedicated empty CARLA world, then immediately destroys the actors.  This
is the prospective eligibility check required by the candidate manifest.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def load_intersection(path: Path) -> list[list[list[float]]]:
    rows: list[list[list[float]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            values = next(csv.reader([raw], skipinitialspace=True))
            if len(values) != 6:
                raise ValueError(f"Invalid intersection row: {raw!r}")
            parsed = [float(value) for value in values]
            rows.append([parsed[:3], parsed[3:]])
    return rows


def transform_values(
    intersection: list[list[list[float]]], vehicle: dict[str, Any]
) -> dict[str, float]:
    x, y, yaw_deg = intersection[int(vehicle["intersection_start_node_idx"])][0]
    yaw_rad = math.radians(float(yaw_deg))
    longitudinal = float(vehicle["start_longitudinal_offset"])
    lateral = float(vehicle["start_left_offset"])
    x += longitudinal * math.cos(yaw_rad)
    y += longitudinal * math.sin(yaw_rad)
    # Scenario is frozen right-hand traffic, matching get_intersection_transform.
    lateral_yaw = yaw_rad - math.pi / 2.0
    x += lateral * math.cos(lateral_yaw)
    y += lateral * math.sin(lateral_yaw)
    return {"x": x, "y": y, "z": 1.0, "yaw_deg": float(yaw_deg)}


def effective_scenario(
    scenario_path: Path, tuning_path: Path, init_path: Path
) -> dict[str, Any]:
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    tuning = json.loads(tuning_path.read_text(encoding="utf-8"))
    scenario["carla_params"] = {
        **scenario.get("carla_params", {}),
        **tuning.get("carla_params", {}),
    }
    role_overrides = tuning.get("vehicle_role_overrides", {})
    vehicles = []
    init = json.loads(init_path.read_text(encoding="utf-8"))
    for source in scenario.get("vehicle_params", []):
        vehicle = {**source, **role_overrides.get(source.get("role"), {})}
        if source.get("role") == "ego":
            vehicle.update(init)
        vehicles.append(vehicle)
    scenario["vehicle_params"] = vehicles
    return scenario


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--carla-root", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--tuning", required=True, type=Path)
    parser.add_argument("--init-dir", required=True, type=Path)
    parser.add_argument("--init-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=2000, type=int)
    parser.add_argument("--timeout", default=15.0, type=float)
    args = parser.parse_args()

    carla_api = args.carla_root.resolve() / "PythonAPI" / "carla"
    sys.path.insert(0, str(carla_api))
    carla_scripts = Path(__file__).resolve().parents[2] / "carla"
    sys.path.insert(0, str(carla_scripts))
    try:
        import carla  # type: ignore
        from utils.vehicle_geometry_utils import resolve_vehicle_blueprint
    except Exception as error:
        raise SystemExit(f"CARLA import preflight failed: {error}") from error

    scenario_path = args.scenario.resolve()
    tuning_path = args.tuning.resolve()
    init_dir = args.init_dir.resolve()
    manifest_path = args.init_manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_ids = list(range(106, 116))
    observed_ids = [int(item["ego_init_id"]) for item in manifest.get("records", [])]
    if manifest.get("status") != "candidate_requires_town05_spawn_preflight":
        raise SystemExit("Init manifest is not in the required candidate state")
    if observed_ids != expected_ids:
        raise SystemExit(f"Expected init106--115 in order, got {observed_ids}")

    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout)
    world = client.get_world()
    map_name = str(world.get_map().name)
    if not map_name.endswith("Town05"):
        raise SystemExit(f"SF4 spawn preflight requires Town05, got {map_name}")
    occupied = [
        {"id": int(actor.id), "type_id": str(actor.type_id)}
        for actor in world.get_actors()
        if str(actor.type_id).startswith(("vehicle.", "sensor."))
    ]
    if occupied:
        raise SystemExit(
            "SF4 spawn preflight requires a dedicated empty CARLA world; "
            f"found {len(occupied)} vehicle/sensor actors"
        )

    intersection_path = scenario_path.parent / json.loads(
        scenario_path.read_text(encoding="utf-8")
    )["carla_params"]["intersection_csv_loc"]
    intersection = load_intersection(intersection_path)
    records = []
    all_pass = True
    for init_id in expected_ids:
        init_path = init_dir / f"ego_init_{init_id}.json"
        scenario = effective_scenario(scenario_path, tuning_path, init_path)
        actors = []
        actor_records = []
        error = None
        try:
            library = world.get_blueprint_library()
            for index, vehicle in enumerate(scenario["vehicle_params"]):
                blueprint = resolve_vehicle_blueprint(vehicle["vehicle_type"], library)
                blueprint.set_attribute("color", str(vehicle["vehicle_color"]))
                blueprint.set_attribute("role_name", str(vehicle["role"]))
                values = transform_values(intersection, vehicle)
                transform = carla.Transform(
                    carla.Location(x=values["x"], y=values["y"], z=values["z"]),
                    carla.Rotation(yaw=values["yaw_deg"]),
                )
                actor = world.try_spawn_actor(blueprint, transform)
                if actor is None:
                    raise RuntimeError(
                        f"spawn returned None for init{init_id} actor index {index}"
                    )
                actors.append(actor)
                extent = actor.bounding_box.extent
                actor_records.append(
                    {
                        "actor_index": index,
                        "role": vehicle["role"],
                        "requested_blueprint": vehicle["vehicle_type"],
                        "effective_blueprint": actor.type_id,
                        "transform": values,
                        "bounding_box_extent_m": {
                            "x": float(extent.x),
                            "y": float(extent.y),
                            "z": float(extent.z),
                        },
                    }
                )
            world.wait_for_tick(args.timeout)
        except Exception as caught:
            error = f"{type(caught).__name__}: {caught}"
            all_pass = False
        finally:
            for actor in reversed(actors):
                try:
                    actor.destroy()
                except Exception:
                    pass
            if actors:
                world.wait_for_tick(args.timeout)
        records.append(
            {
                "ego_init_id": init_id,
                "status": "pass" if error is None else "fail",
                "init_sha256": sha256(init_path),
                "actors": actor_records,
                "error": error,
            }
        )

    payload = {
        "schema_version": "sf4_town05_spawn_preflight_v1",
        "status": "pass" if all_pass else "fail",
        "formal_rollouts_launched": 0,
        "treatment_executed": False,
        "map": map_name,
        "dedicated_empty_world_verified": True,
        "candidate_ids": expected_ids,
        "scenario_sha256": sha256(scenario_path),
        "tuning_sha256": sha256(tuning_path),
        "init_manifest_sha256": sha256(manifest_path),
        "intersection_sha256": sha256(intersection_path),
        "records": records,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(args.output.resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(0 if all_pass else 4)


if __name__ == "__main__":
    main()
