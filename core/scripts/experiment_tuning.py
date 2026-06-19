#!/usr/bin/env python3
"""Shared fine-tuning configuration helpers for the CARLA give-way experiments."""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, Optional, Tuple


TUNING_METADATA_KEY = "_applied_tuning_config"


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_tuning_path(
    scenario_path: Optional[str],
    scenario_dict: Dict[str, Any],
    tuning_config_path: Optional[str],
) -> Optional[str]:
    path = tuning_config_path or scenario_dict.get("tuning_config")
    if not path:
        return None
    if os.path.isabs(path):
        return path
    base_dir = os.path.dirname(os.path.abspath(scenario_path)) if scenario_path else os.getcwd()
    return os.path.abspath(os.path.join(base_dir, path))


def _shallow_update_section(scenario: Dict[str, Any], config: Dict[str, Any], key: str) -> None:
    if key not in config:
        return
    base = dict(scenario.get(key, {}))
    base.update(config[key])
    scenario[key] = base


def _apply_vehicle_overrides(scenario: Dict[str, Any], config: Dict[str, Any]) -> None:
    vehicles = scenario.get("vehicle_params", [])
    role_overrides = config.get("vehicle_role_overrides", {})
    traffic_role_overrides = config.get("vehicle_traffic_role_overrides", {})
    index_overrides = config.get("vehicle_index_overrides", {})

    for idx, vehicle in enumerate(vehicles):
        merged = {}
        role = str(vehicle.get("role", ""))
        traffic_role = str(vehicle.get("traffic_role", ""))
        if role in role_overrides:
            merged.update(role_overrides[role])
        if traffic_role in traffic_role_overrides:
            merged.update(traffic_role_overrides[traffic_role])
        idx_key = str(idx)
        if idx_key in index_overrides:
            merged.update(index_overrides[idx_key])
        vehicle.update(merged)


def apply_tuning_config(
    scenario_dict: Dict[str, Any],
    *,
    scenario_path: Optional[str] = None,
    tuning_config_path: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return a scenario copy with fine-tuning overrides applied.

    The config is intentionally shallow and explicit. Scenario JSONs keep the
    semantic definition of the experiment, while the tuning file owns numeric
    parameters that are expected to change across CARLA trials.
    """
    scenario = copy.deepcopy(scenario_dict)
    resolved_path = _resolve_tuning_path(scenario_path, scenario, tuning_config_path)
    if not resolved_path:
        metadata = {"applied": False, "source_path": None, "config": None}
        scenario[TUNING_METADATA_KEY] = metadata
        return scenario, metadata

    config = _read_json(resolved_path)
    for section in (
        "scenario_description",
        "carla_params",
        "prediction_params",
        "drone_viz_params",
        "viz_topdown",
    ):
        _shallow_update_section(scenario, config, section)
    _apply_vehicle_overrides(scenario, config)

    metadata = {
        "applied": True,
        "source_path": resolved_path,
        "config": config,
    }
    scenario[TUNING_METADATA_KEY] = metadata
    return scenario, metadata


def load_scenario_with_tuning(
    scenario_path: str,
    tuning_config_path: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    scenario = _read_json(scenario_path)
    return apply_tuning_config(
        scenario,
        scenario_path=scenario_path,
        tuning_config_path=tuning_config_path,
    )


def tuning_snapshot_payload(scenario_dict: Dict[str, Any]) -> Dict[str, Any]:
    metadata = scenario_dict.get(TUNING_METADATA_KEY)
    if metadata is None:
        metadata = {"applied": False, "source_path": None, "config": None}
    return metadata
