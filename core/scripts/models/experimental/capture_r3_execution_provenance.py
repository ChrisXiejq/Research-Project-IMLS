#!/usr/bin/env python3
"""Capture allowlisted R3 environment and critical-source provenance."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import hashlib
import importlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CRITICAL_SOURCES = (
    "core/scripts/carla/experimental/run_r3_corrected_formal_matrix.sh",
    "core/scripts/carla/run_all_scenarios.py",
    "core/scripts/carla/scenarios/run_intersection_scenario.py",
    "core/scripts/carla/policies/smpc_agent.py",
    "core/scripts/carla/utils/mpc_utils.py",
    "core/scripts/evaluation/closed_loop_metrics.py",
    "core/scripts/postcarla_trajectory_gate.py",
    "core/scripts/models/experimental/audit_r3_corrected_matrix.py",
    "core/scripts/models/experimental/analyze_r3_corrected_formal.py",
    "core/scripts/models/experimental/r3_attempt_manager.py",
    "core/scripts/models/experimental/summarize_r3_progress.py",
    "core/scripts/models/tools/package_closed_loop_snapshot.py",
    "core/scripts/models/experimental/capture_r3_execution_provenance.py",
    "core/scripts/models/tests/test_distinction_regression_gates.py",
    "core/scripts/models/tests/test_r3_corrected_gates.py",
    "core/scripts/models/tests/test_r3_formal_analysis.py",
    "core/scripts/models/tests/test_r3_runner_hardening.py",
)
R1_ALLOWED_INSTRUMENTATION_DRIFT = {
    "core/scripts/carla/scenarios/run_intersection_scenario.py",
}
SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(?:password|passwd|secret|access[_-]?token|api[_-]?key)[\"']?\s*[:=]"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)https?://[^\s/:]+:[^\s/@]+@"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def freeze_json(path: Path, payload: dict[str, Any]) -> None:
    """Write once; on resume require identical semantics and preserve bytes."""

    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
        without_time = lambda value: {key: item for key, item in value.items() if key != "captured_at_utc"}
        if without_time(previous) != without_time(payload):
            raise RuntimeError(f"Frozen R3 provenance drift: {path}")
        return
    atomic_json(path, payload)


def assert_no_sensitive_text(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, sort_keys=True)
    matches = [pattern.pattern for pattern in SENSITIVE_PATTERNS if pattern.search(rendered)]
    if matches:
        raise ValueError(f"Sensitive credential-like text detected in provenance payload: {matches}")


def command(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *arguments], text=True).strip()


def module_version(name: str) -> str | None:
    try:
        module = importlib.import_module(name)
    except Exception:
        return None
    value = getattr(module, "__version__", None)
    return str(value) if value is not None else "installed_version_not_exposed"


def gpu_inventory() -> list[dict[str, str]]:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        return []
    rows = []
    for line in output.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) == 3:
            rows.append({"name": fields[0], "driver_version": fields[1], "memory_total_mib": fields[2]})
    return rows


def carla_inventory(host: str, port: int) -> dict[str, Any]:
    try:
        import carla  # type: ignore

        client = carla.Client(host, port)
        client.set_timeout(10.0)
        world = client.get_world()
        return {
            "client_version": str(client.get_client_version()),
            "server_version": str(client.get_server_version()),
            "map": str(world.get_map().name),
        }
    except Exception as error:
        raise RuntimeError(f"Unable to capture CARLA version/map provenance: {type(error).__name__}: {error}") from error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--r1-contract", required=True, type=Path)
    parser.add_argument("--environment-output", required=True, type=Path)
    parser.add_argument("--source-output", required=True, type=Path)
    parser.add_argument("--carla-host", default="127.0.0.1")
    parser.add_argument("--carla-port", default=2000, type=int)
    args = parser.parse_args()
    repo = args.repo.resolve()
    tracked_status = command(repo, "status", "--porcelain", "--untracked-files=no")
    if tracked_status:
        raise SystemExit(f"R3 requires a clean tracked worktree; tracked changes found:\n{tracked_status}")
    head = command(repo, "rev-parse", "HEAD")
    sources = {}
    for relative in CRITICAL_SOURCES:
        path = repo / relative
        if not path.is_file():
            raise FileNotFoundError(f"Missing critical R3 source: {relative}")
        sources[relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    r1 = json.loads(args.r1_contract.read_text(encoding="utf-8"))
    r1_hashes = r1.get("source_sha256") or {}
    r1_drift = {
        relative: {
            "r1_sha256": expected,
            "r3_sha256": sources.get(relative, {}).get("sha256"),
            "classification": (
                "allowed_instrumentation_only"
                if relative in R1_ALLOWED_INSTRUMENTATION_DRIFT
                else "prohibited_algorithm_or_test_drift"
            ),
        }
        for relative, expected in r1_hashes.items()
        if sources.get(relative, {}).get("sha256") != expected
    }
    prohibited = [relative for relative, item in r1_drift.items() if item["classification"].startswith("prohibited")]
    if prohibited:
        raise SystemExit(f"Critical R1 algorithm-source drift detected: {prohibited}")
    source_payload = {
        "schema_version": "r3_execution_source_manifest_v2",
        "status": "pass",
        "git_commit": head,
        "tracked_worktree_clean": True,
        "critical_sources": sources,
        "r1_source_contract_sha256": sha256(args.r1_contract.resolve()),
        "r1_source_drift": r1_drift,
        "r1_drift_policy": {
            "allowed_paths": sorted(R1_ALLOWED_INSTRUMENTATION_DRIFT),
            "meaning": "Telemetry/instrumentation additions only; predictor and controller algorithms remain frozen.",
        },
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    environment_payload = {
        "schema_version": "r3_environment_v2",
        "status": "pass",
        "git_commit": head,
        "tracked_worktree_clean": True,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "package_versions": {
            name: module_version(name)
            for name in ("numpy", "tensorflow", "casadi", "carla")
        },
        "gpus": gpu_inventory(),
        "carla": carla_inventory(args.carla_host, args.carla_port),
        "dedicated_carla_instance_required": True,
        "concurrent_jobs_on_port_2000_prohibited": True,
        "credential_capture_policy": "strict_allowlist_no_environment_dump_no_git_remotes",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    assert_no_sensitive_text(source_payload)
    assert_no_sensitive_text(environment_payload)
    freeze_json(args.source_output.resolve(), source_payload)
    freeze_json(args.environment_output.resolve(), environment_payload)
    print(json.dumps({"status": "pass", "git_commit": head, "r1_source_drift": r1_drift}, indent=2))


if __name__ == "__main__":
    main()
