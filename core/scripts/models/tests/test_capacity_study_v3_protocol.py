#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from capacity_study_v3_protocol import (  # noqa: E402
    CHALLENGE_TEST_GROUPS,
    CLOSED_LOOP_GROUPS,
    GENERAL_TEST_GROUPS,
    RESPONSE_ONSET_HALF_WIDTH_S,
    build_group_registry,
    classify_response_stratum,
    conflict_zone_entry_time_s,
    expected_core_run_count,
    expected_model_cells,
    THESIS_CORE_CELL_IDS,
    THESIS_CORE_RUN_COUNT,
    first_deceleration_onset_s,
    load_protocol,
    require_stage_gates,
    validate_group_registry,
    validate_nested_training_groups,
    validate_protocol,
    verify_immutable_manifest,
    write_immutable_manifest,
)


class CapacityStudyV3ProtocolTest(unittest.TestCase):
    def test_frozen_protocol_defines_exact_factorial(self):
        protocol = load_protocol()
        report = validate_protocol(protocol)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["model_cells"], 21)
        self.assertEqual(expected_core_run_count(), 189)
        cells = expected_model_cells()
        self.assertEqual(sum(row["family"] == "head" for row in cells), 3)
        self.assertEqual(sum(row["family"] == "mlp" for row in cells), 9)
        self.assertEqual(sum(row["family"] == "transformer" for row in cells), 9)
        self.assertEqual(THESIS_CORE_RUN_COUNT, 27)
        self.assertEqual(protocol["thesis_core"]["model_cell_ids"], list(THESIS_CORE_CELL_IDS))
        self.assertEqual(protocol["thesis_core"]["planned_closed_loop_rollouts"], 80)

    def test_protocol_rejects_missing_or_changed_preregistered_fields(self):
        protocol = load_protocol()
        missing = copy.deepcopy(protocol)
        missing.pop("learning_rates")
        with self.assertRaisesRegex(ValueError, "missing required field"):
            validate_protocol(missing)
        changed = copy.deepcopy(protocol)
        changed["history_horizons_s"] = [0.0, 1.0]
        with self.assertRaisesRegex(ValueError, "field drift"):
            validate_protocol(changed)
        changed_cell = copy.deepcopy(protocol)
        changed_cell["model_cells"][3]["history_mask"] = [1, 1, 1, 1, 1, 1]
        with self.assertRaisesRegex(ValueError, "model_cells"):
            validate_protocol(changed_cell)
        changed_regularization = copy.deepcopy(protocol)
        changed_regularization["optimization_protocol"]["weight_decay"] = 0.0
        with self.assertRaisesRegex(ValueError, "optimization_protocol"):
            validate_protocol(changed_regularization)
        changed_thesis = copy.deepcopy(protocol)
        changed_thesis["thesis_core"]["planned_training_runs"] = 21
        with self.assertRaisesRegex(ValueError, "thesis_core"):
            validate_protocol(changed_thesis)

    def test_group_registry_is_deterministic_disjoint_and_bounded(self):
        first = build_group_registry()
        second = build_group_registry()
        self.assertEqual(first, second)
        report = validate_group_registry(first)
        self.assertEqual(
            report["group_counts"],
            {"general_test": 10, "interaction_challenge": 20, "closed_loop": 10},
        )
        ids = {row["ego_init_id"] for row in first["records"]}
        self.assertEqual(
            ids,
            set(GENERAL_TEST_GROUPS + CHALLENGE_TEST_GROUPS + CLOSED_LOOP_GROUPS),
        )
        tampered = copy.deepcopy(first)
        tampered["records"][0]["init_speed_mps"] = 99.0
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_group_registry(tampered)

    def test_response_stratum_boundaries_are_frozen(self):
        half = RESPONSE_ONSET_HALF_WIDTH_S
        self.assertEqual(
            classify_response_stratum(
                target_style="assertive", sample_time_s=10.0,
                trigger_time_s=None, reactive_active=False,
            ),
            "assertive",
        )
        self.assertEqual(
            classify_response_stratum(
                target_style="reactive", sample_time_s=9.0,
                trigger_time_s=10.0, reactive_active=False,
            ),
            "reactive_pre_response",
        )
        for sample_time in (10.0 - half, 10.0, 10.0 + half):
            self.assertEqual(
                classify_response_stratum(
                    target_style="reactive", sample_time_s=sample_time,
                    trigger_time_s=10.0, reactive_active=True,
                ),
                "response_onset",
            )
        self.assertEqual(
            classify_response_stratum(
                target_style="reactive", sample_time_s=10.0 + half + 1.0e-6,
                trigger_time_s=10.0, reactive_active=True,
            ),
            "response_active",
        )

    def test_timing_metric_boundaries_and_undefined_cases(self):
        self.assertEqual(first_deceleration_onset_s([0.0, 0.2, 0.4], [9.0, 8.7, 8.5]), 0.4)
        self.assertIsNone(first_deceleration_onset_s([0.0, 0.2], [9.0, 8.6]))
        self.assertEqual(
            conflict_zone_entry_time_s(
                [0.0, 0.2, 0.4], [[5.0, 0.0], [4.0, 4.0], [0.0, 0.0]]
            ),
            0.2,
        )
        self.assertIsNone(conflict_zone_entry_time_s([0.0], [[5.0, 5.0]]))

    def test_immutable_gates_reject_drift_and_missing_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = ("selection", "convergence", "capacity_audit", "calibration")
            gates = {}
            for name in names:
                path = root / f"{name}.json"
                write_immutable_manifest(path, {"gate": name})
                verify_immutable_manifest(path)
                gates[name] = path
            report = require_stage_gates("general_test", gates)
            self.assertEqual(report["status"], "pass")
            with self.assertRaisesRegex(ValueError, "Missing gates"):
                require_stage_gates("challenge_test", {"selection": gates["selection"]})
            with self.assertRaisesRegex(ValueError, "Immutable manifest drift"):
                write_immutable_manifest(gates["selection"], {"gate": "changed"})
            payload = json.loads(gates["calibration"].read_text())
            payload["gate"] = "tampered"
            gates["calibration"].write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "payload hash mismatch"):
                verify_immutable_manifest(gates["calibration"])

    def test_nested_training_groups_reject_window_level_or_non_nested_sets(self):
        good = {
            "0.25": list(range(1, 11)),
            "0.50": list(range(1, 21)),
            "0.75": list(range(1, 31)),
            "1.00": list(range(1, 41)),
        }
        validate_nested_training_groups(good)
        bad = copy.deepcopy(good)
        bad["0.50"] = list(range(11, 31))
        with self.assertRaisesRegex(ValueError, "not nested"):
            validate_nested_training_groups(bad)


if __name__ == "__main__":
    unittest.main()
