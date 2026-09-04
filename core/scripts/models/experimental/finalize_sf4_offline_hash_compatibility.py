#!/usr/bin/env python3
"""Run the frozen SF4 analyser through an audited model-hash compatibility gate.

SF4 prospectively froze the B1 SavedModel with ``tree_sha256`` from
``prepare_sf4_supervisor_behavioural_authority.py``.  Online deployment records
the same directory with ``DeployMultiPath._artifact_hash``.  Both algorithms
hash the relative path, a NUL separator and each file digest, but the former
also appends a newline after each record.  The frozen analyser accidentally
compared these deliberately different encodings directly.

This post-collection wrapper does not edit the frozen contract, analyser, raw
rollouts or receipts.  It proves that both digests describe the current frozen
model tree, checks the contract-bound deployment preflight and every rollout
deployment manifest, then substitutes only the already-proven runtime digest
while calling the original frozen control-variable gate in memory.
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
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


SCHEMA = "sf4_b1_hash_algorithm_compatibility_v1"
EXPECTED_ROLLOUTS = 80
FROZEN_ANALYZER_RELATIVE = (
    "core/scripts/models/experimental/analyze_sf4_supervisor_behavioural_authority.py"
)


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object: %s" % path)
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def model_files(path: Path) -> List[Path]:
    if not path.is_dir():
        raise ValueError("B1 model directory is missing: %s" % path)
    files = sorted(value for value in path.rglob("*") if value.is_file())
    if not files:
        raise ValueError("B1 model directory is empty: %s" % path)
    return files


def model_tree_hashes(path: Path) -> Dict[str, Any]:
    """Return the prospective-contract and online-runtime encodings."""
    contract_digest = hashlib.sha256()
    runtime_digest = hashlib.sha256()
    total_bytes = 0
    files = model_files(path)
    for item in files:
        relative = item.relative_to(path).as_posix().encode("utf-8")
        file_digest = sha256(item).encode("ascii")
        common = relative + b"\0" + file_digest
        contract_digest.update(common + b"\n")
        runtime_digest.update(common)
        total_bytes += item.stat().st_size
    return {
        "path": str(path.resolve()),
        "files": len(files),
        "bytes": total_bytes,
        "contract_newline_record_sha256_tree": contract_digest.hexdigest(),
        "runtime_concatenated_record_sha256_tree": runtime_digest.hexdigest(),
    }


def validate_frozen_sources(repo: Path, contract: Mapping[str, Any]) -> Dict[str, str]:
    expected = ((contract.get("hashes") or {}).get("execution_sources") or {})
    if not isinstance(expected, dict) or not expected:
        raise ValueError("SF4 frozen execution-source hashes are missing")
    observed: Dict[str, str] = {}
    for relative, expected_hash in sorted(expected.items()):
        source = repo / str(relative)
        if not source.is_file():
            raise ValueError("Frozen execution source is missing: %s" % source)
        observed_hash = sha256(source)
        if observed_hash != expected_hash:
            raise ValueError("Frozen execution source drift: %s" % relative)
        observed[str(relative)] = observed_hash
    if FROZEN_ANALYZER_RELATIVE not in observed:
        raise ValueError("SF4 contract does not freeze the original analyser")
    return observed


def _deployment_identity(payload: Mapping[str, Any]) -> Tuple[str, str, str]:
    model = payload.get("model_artifact") or {}
    calibration = payload.get("calibration_artifact") or {}
    anchors = payload.get("anchors_artifact") or {}
    return (
        str(model.get("sha256_tree") or ""),
        str(calibration.get("sha256") or ""),
        str(anchors.get("sha256") or ""),
    )


def validate_identity_bridge(
    results: Path,
    repo: Path,
    contract_path: Path,
    deployment_preflight_path: Path,
    b1_model_override: Optional[Path] = None,
) -> Dict[str, Any]:
    contract = read_json(contract_path)
    if contract.get("schema_version") != (
        "sf4_supervisor_behavioural_authority_run_contract_v1"
    ):
        raise ValueError("Unexpected SF4 contract schema")
    order = contract.get("execution_order") or []
    if len(order) != EXPECTED_ROLLOUTS:
        raise ValueError("SF4 compatibility audit requires exactly 80 rollouts")
    source_hashes = validate_frozen_sources(repo, contract)
    hashes = contract.get("hashes") or {}
    if sha256(deployment_preflight_path) != hashes.get("deployment_preflight"):
        raise ValueError("Deployment preflight is not bound by the frozen contract")
    preflight = read_json(deployment_preflight_path)
    b1 = ((preflight.get("b1") or {}).get("deployment") or {})
    model_artifact = b1.get("model_artifact") or {}
    calibration_artifact = b1.get("calibration_artifact") or {}
    anchors_artifact = preflight.get("anchors") or {}
    runtime_model_hash = str(model_artifact.get("sha256_tree") or "")
    if not (
        preflight.get("status") == "pass"
        and preflight.get("selected_variant") == "B1"
        and int(preflight.get("selected_seed", -1)) == 37
        and runtime_model_hash
        and runtime_model_hash
        == str((b1.get("calibration_model_artifact") or {}).get("sha256_tree") or "")
        and calibration_artifact.get("sha256") == hashes.get("b1_calibration")
        and anchors_artifact.get("sha256") == hashes.get("anchors")
    ):
        raise ValueError("Contract-bound B1 deployment preflight identity failed")

    model_path = (
        b1_model_override.resolve()
        if b1_model_override is not None
        else Path(str(model_artifact.get("path") or "")).resolve()
    )
    observed_tree = model_tree_hashes(model_path)
    if (
        observed_tree["contract_newline_record_sha256_tree"]
        != hashes.get("b1_model_tree")
        or observed_tree["runtime_concatenated_record_sha256_tree"]
        != runtime_model_hash
        or int(model_artifact.get("files", -1)) != observed_tree["files"]
        or int(model_artifact.get("bytes", -1)) != observed_tree["bytes"]
    ):
        raise ValueError("B1 model bytes do not bridge both frozen hash algorithms")

    expected_runtime_identity = (
        runtime_model_hash,
        str(hashes.get("b1_calibration") or ""),
        str(hashes.get("anchors") or ""),
    )
    rollout_records = []
    seen = set()
    for item in order:
        cell_id = str(item.get("cell_id"))
        init_id = int(item.get("ego_init_id", -1))
        key = (cell_id, init_id)
        if key in seen:
            raise ValueError("Duplicate SF4 execution key: %r" % (key,))
        seen.add(key)
        receipt_path = results / cell_id / ("SF4_ROLLOUT_%d_COMPLETE.json" % init_id)
        receipt = read_json(receipt_path)
        if not (
            receipt.get("status") == "pass"
            and receipt.get("cell_id") == cell_id
            and int(receipt.get("ego_init_id", -1)) == init_id
        ):
            raise ValueError("Invalid SF4 receipt identity: %s" % receipt_path)
        scenario = results / cell_id / str(receipt.get("scenario_dir") or "")
        manifest_path = scenario / "prediction_deployment_manifest.json"
        manifest = read_json(manifest_path)
        if not (
            manifest.get("status") == "pass"
            and manifest.get("warmup_passed") in (True, 1, "true", "True")
            and _deployment_identity(manifest) == expected_runtime_identity
        ):
            raise ValueError("B1 runtime deployment identity drift: %s" % manifest_path)
        rollout_records.append(
            {
                "cell_id": cell_id,
                "ego_init_id": init_id,
                "receipt": str(receipt_path.relative_to(results)),
                "receipt_sha256": sha256(receipt_path),
                "deployment_manifest": str(manifest_path.relative_to(results)),
                "deployment_manifest_sha256": sha256(manifest_path),
            }
        )
    if len(seen) != EXPECTED_ROLLOUTS:
        raise ValueError("SF4 deployment audit did not observe 80 unique rollouts")

    return {
        "schema_version": SCHEMA,
        "status": "pass",
        "scope": "postcollection_analysis_compatibility_only",
        "raw_rollouts_or_receipts_modified": False,
        "contract_modified": False,
        "frozen_analyzer_modified": False,
        "scientific_treatment_or_estimand_modified": False,
        "reason": (
            "Prospective contract and online deployment used two explicit "
            "directory-record encodings for the same B1 model tree."
        ),
        "contract": {
            "path": str(contract_path),
            "sha256": sha256(contract_path),
            "b1_model_tree": hashes.get("b1_model_tree"),
        },
        "deployment_preflight": {
            "path": str(deployment_preflight_path),
            "sha256": sha256(deployment_preflight_path),
            "runtime_b1_model_tree": runtime_model_hash,
            "selected_variant": preflight.get("selected_variant"),
            "selected_seed": preflight.get("selected_seed"),
        },
        "model_tree_dual_hash_proof": observed_tree,
        "frozen_execution_sources_verified": source_hashes,
        "frozen_analyzer_sha256": source_hashes[FROZEN_ANALYZER_RELATIVE],
        "rollout_deployment_manifests_verified": len(rollout_records),
        "rollouts": rollout_records,
    }


def load_frozen_analyzer(path: Path) -> Any:
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("sf4_frozen_analyzer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load frozen SF4 analyser: %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(args: argparse.Namespace) -> Dict[str, Any]:
    results = args.results_dir.resolve()
    repo = args.repo.resolve()
    contract_path = args.contract.resolve()
    prereg_path = args.prereg.resolve()
    output = args.output_dir.resolve()
    deployment_preflight = args.deployment_preflight.resolve()
    compatibility = validate_identity_bridge(
        results,
        repo,
        contract_path,
        deployment_preflight,
        args.b1_model,
    )
    analyzer_path = repo / FROZEN_ANALYZER_RELATIVE
    analyzer = load_frozen_analyzer(analyzer_path)
    original_gate = analyzer.validate_rollout_controls
    contract_model_hash = compatibility["contract"]["b1_model_tree"]
    runtime_model_hash = compatibility["deployment_preflight"][
        "runtime_b1_model_tree"
    ]

    def compatible_gate(*gate_args: Any, **gate_kwargs: Any) -> Any:
        values = list(gate_args)
        if len(values) < 8:
            raise RuntimeError("Frozen SF4 control-gate signature changed")
        original_contract = values[7]
        if ((original_contract.get("hashes") or {}).get("b1_model_tree")) != (
            contract_model_hash
        ):
            raise ValueError("Frozen contract B1 identity changed during analysis")
        compatible_contract = copy.deepcopy(original_contract)
        compatible_contract["hashes"]["b1_model_tree"] = runtime_model_hash
        values[7] = compatible_contract
        return original_gate(*values, **gate_kwargs)

    analyzer.validate_rollout_controls = compatible_gate
    payload = analyzer.run(
        Namespace(
            results_dir=results,
            contract=contract_path,
            prereg=prereg_path,
            output_dir=output,
        )
    )
    if not (
        payload.get("status") == "pass"
        and int(payload.get("observed_rollouts", -1)) == EXPECTED_ROLLOUTS
        and payload.get("integrity_gate") == "pass"
    ):
        raise ValueError("Frozen SF4 analyser did not complete successfully")

    wrapper_path = Path(__file__).resolve()
    compatibility.update(
        {
            "analysis_status": "pass",
            "analysis_observed_rollouts": payload.get("observed_rollouts"),
            "compatibility_wrapper": {
                "path": str(wrapper_path.relative_to(repo)),
                "sha256": sha256(wrapper_path),
                "git_commit": subprocess.check_output(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
                ).strip(),
            },
            "substitution": {
                "location": "in_memory_control_gate_expected_model_digest_only",
                "from_contract_newline_record_digest": contract_model_hash,
                "to_runtime_concatenated_record_digest": runtime_model_hash,
                "all_other_frozen_analyzer_checks_unchanged": True,
            },
        }
    )
    report = output / "SF4_B1_HASH_ALGORITHM_COMPATIBILITY.json"
    atomic_json(report, compatibility)
    completion_path = output / "SF4_ANALYSIS_COMPLETE.json"
    completion = read_json(completion_path)
    completion["postcollection_hash_compatibility_gate"] = {
        "status": "pass",
        "report": report.name,
        "report_sha256": sha256(report),
        "frozen_analyzer_sha256": compatibility["frozen_analyzer_sha256"],
    }
    products = completion.setdefault("products", {})
    products[report.name] = {
        "bytes": report.stat().st_size,
        "sha256": sha256(report),
    }
    atomic_json(completion_path, completion)
    return completion


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--prereg", required=True, type=Path)
    parser.add_argument("--deployment-preflight", required=True, type=Path)
    parser.add_argument("--b1-model", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> None:
    payload = run(build_parser().parse_args())
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
