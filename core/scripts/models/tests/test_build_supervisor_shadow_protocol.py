import tempfile
import unittest
from pathlib import Path

from core.scripts.models.build_supervisor_shadow_protocol import (
    build_protocol,
    validate_protocol,
)


class SupervisorShadowProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]

    def test_protocol_is_frozen_and_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "protocol.json"
            payload = build_protocol(self.root, output)
            checks = validate_protocol(payload)
            self.assertTrue(all(checks.values()))
            self.assertEqual(payload["protocol"]["factual_rollout_treatments"]["planned_rollouts"], 160)
            self.assertFalse(payload["protocol"]["shadow_factorial_per_state"]["actuation_allowed"])
            self.assertEqual(len(payload["protocol"]["authority_channels"]), 7)

    def test_mutated_protocol_hash_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = build_protocol(self.root, Path(directory) / "protocol.json")
            payload["protocol"]["shadow_factorial_per_state"]["actuation_allowed"] = True
            with self.assertRaisesRegex(ValueError, "validation failed"):
                validate_protocol(payload)


if __name__ == "__main__":
    unittest.main()
