
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.tools.build_supervisor_masking_gap_gate import build_gate


class SupervisorMaskingGapGateTest(unittest.TestCase):
    def _write(self, root: Path, name: str, value: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_requires_collection_without_aligned_or_factorial_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self._write(root, "contract.json", {"status": "pass"})
            evidence = self._write(root, "evidence.json", {
                "status": "pass",
                "H1_authority": {"arms": {"on": {"completion_successes": 40, "rollouts": 40}, "off": {"completion_successes": 0, "rollouts": 40}}},
                "identification_verdicts": {"same_state_alternative_commands_available": False, "non_saturated_policy_by_authority_factorial_available": False},
            })
            protocol = self._write(root, "protocol.json", {"status": "frozen_pre_outcome", "outcome_data_seen_before_freeze": False, "protocol_sha256": "a" * 64})
            result = build_gate(contract, evidence, protocol, root / "out.json")
            self.assertEqual(result["headline_decision"], "material_gap_requires_collection")
            self.assertFalse(result["identification_state"]["supervisor_specific_masking_identified"])

    def test_aligned_evidence_satisfies_masking_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = self._write(root, "contract.json", {"status": "pass"})
            evidence = self._write(root, "evidence.json", {
                "status": "pass",
                "H1_authority": {"arms": {"on": {"completion_successes": 40, "rollouts": 40}, "off": {"completion_successes": 0, "rollouts": 40}}},
                "identification_verdicts": {"same_state_alternative_commands_available": True, "non_saturated_policy_by_authority_factorial_available": False},
            })
            protocol = self._write(root, "protocol.json", {"status": "frozen_pre_outcome", "outcome_data_seen_before_freeze": False, "protocol_sha256": "b" * 64})
            result = build_gate(contract, evidence, protocol, root / "out.json")
            self.assertEqual(result["headline_decision"], "existing_evidence_sufficient")


if __name__ == "__main__":
    unittest.main()
