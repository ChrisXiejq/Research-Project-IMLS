#!/usr/bin/env python3
"""Freeze the R1 corrected closed-loop implementation contract."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

from distinction_analysis_utils import atomic_write_json, sha256_file


CORRECTED = "corrected_joint_modes_shared_amin_v1"
LEGACY = "legacy_single_tv_mode0_split_amin_v0"


def isolated_mode_functions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "_joint_mode_component",
            "_mode_component",
            "_mode_consumption_map",
        }
    ]
    namespace = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<r1-mode-contract>", "exec"), namespace)
    return namespace["_mode_component"], namespace["_mode_consumption_map"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    mpc_path = repo / "core/scripts/carla/utils/mpc_utils.py"
    agent_path = repo / "core/scripts/carla/policies/smpc_agent.py"
    scenario_path = repo / "core/scripts/carla/scenarios/run_intersection_scenario.py"
    metrics_path = repo / "core/scripts/evaluation/closed_loop_metrics.py"
    test_path = repo / "core/scripts/models/tests/test_distinction_regression_gates.py"

    mode, mode_map = isolated_mode_functions(mpc_path)
    formal_profiles = (
        "upstream_code",
        "fixed_frontier_medium",
        "adaptive_interaction_severity",
    )
    one_tv = {
        profile: [mode(j, 0, 3, 1, profile) for j in range(3)]
        for profile in formal_profiles
    }
    two_tv = mode_map(3, 2)
    legacy_one_tv = [mode(j, 0, 3, 1, legacy_mode_indexing=True) for j in range(3)]

    agent = agent_path.read_text(encoding="utf-8")
    scenario = scenario_path.read_text(encoding="utf-8")
    metrics = metrics_path.read_text(encoding="utf-8")
    gates = {
        "corrected_single_tv_mode_mapping": {
            "status": "pass" if all(value == [0, 1, 2] for value in one_tv.values()) else "fail",
            "mapping_by_profile": one_tv,
        },
        "corrected_multi_tv_base_k_mapping": {
            "status": "pass"
            if two_tv == [[j % 3, (j // 3) % 3] for j in range(9)]
            else "fail",
            "mapping": two_tv,
        },
        "legacy_requires_explicit_flag": {
            "status": "pass" if legacy_one_tv == [0, 0, 0] else "fail",
            "legacy_version": LEGACY,
            "mapping_when_explicitly_enabled": legacy_one_tv,
        },
        "corrected_is_scenario_default": {
            "status": "pass"
            if f'control_implementation_version : str = "{CORRECTED}"' in scenario
            and "control_implementation_version=vehicle_params.control_implementation_version" in scenario
            else "fail",
            "default_version": CORRECTED,
        },
        "shared_acceleration_bound": {
            "status": "pass"
            if "self._solver_a_min = -4.0 if self._legacy_control_implementation else -3.0" in agent
            and "A_MIN=self._solver_a_min" in agent
            and "return self._ref_gen_a_min, self._ref_gen_a_max" in agent
            else "fail",
            "corrected_reference_A_MIN": -3.0,
            "corrected_solver_A_MIN": -3.0,
            "units": "m/s^2",
        },
        "per_step_mode_and_tensor_hash_telemetry": {
            "status": "pass"
            if all(
                token in agent
                for token in (
                    'payload["mode_consumption"]',
                    '"spatial_mode_index"',
                    '"mean_sha256"',
                    '"covariance_sha256"',
                )
            )
            else "fail",
        },
        "all_equal_length_guard": {
            "status": "pass" if "len(set(lengths.values())) != 1" in metrics else "fail",
        },
        "no_implicit_legacy_profile_switch": {
            "status": "pass"
            if not re.search(r"n_tvs\s*==\s*1\s+and\s+normalized\s+in", mpc_path.read_text(encoding="utf-8"))
            else "fail",
        },
    }
    failures = [name for name, value in gates.items() if value["status"] != "pass"]
    sources = (mpc_path, agent_path, scenario_path, metrics_path, test_path)
    payload = {
        "schema_version": "r1_corrected_control_contract_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass" if not failures else "fail",
        "stage": "R1",
        "implementation_version": CORRECTED,
        "legacy_version": LEGACY,
        "formal_result_generation": "distinction_corrected_v1",
        "legacy_result_generation": "legacy_pre_r1_read_only",
        "failures": failures,
        "gates": gates,
        "source_sha256": {
            str(path.relative_to(repo)): sha256_file(path)
            for path in sources
        },
        "git_head_at_audit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
    }
    contract = output / "R1_CORRECTED_CONTROL_CONTRACT.json"
    atomic_write_json(contract, payload)
    atomic_write_json(
        output / "R1_COMPLETE.json",
        {
            "schema_version": "r1_complete_v1",
            "stage": "R1",
            "status": payload["status"],
            "implementation_version": CORRECTED,
            "contract": contract.name,
            "contract_sha256": sha256_file(contract),
            "failures": failures,
        },
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
