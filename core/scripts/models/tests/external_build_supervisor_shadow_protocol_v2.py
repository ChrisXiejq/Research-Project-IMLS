import tempfile
import unittest
from pathlib import Path

from core.scripts.models.build_supervisor_shadow_protocol import build_protocol as build_v1
from core.scripts.models.build_supervisor_shadow_protocol_v2 import build_protocol, validate_protocol


class SupervisorShadowProtocolV2Test(unittest.TestCase):
    def test_event_anchor_amendment_preserves_design_and_avoids_outcome_selection(self):
        repo = Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            v1_path = tmp / "v1.json"
            build_v1(repo, v1_path)
            payload = build_protocol(repo, v1_path, tmp / "v2.json")
            checks = validate_protocol(payload)
            self.assertTrue(all(checks.values()))
            schedule = payload["protocol"]["eligibility_schedule"]
            self.assertEqual(schedule["planned_state_upper_bound"], 640)
            self.assertFalse(schedule["buffered_past_actor_state_replay"])


if __name__ == "__main__":
    unittest.main()
