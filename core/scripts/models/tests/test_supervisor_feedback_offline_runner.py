
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
RUNNER = REPO / "core/scripts/models/experimental/run_supervisor_feedback_r3_offline_audits.sh"


class SupervisorFeedbackOfflineRunnerTests(unittest.TestCase):
    def test_runner_has_immutable_archive_and_security_gates(self):
        text = RUNNER.read_text(encoding="utf-8")
        required = (
            "archive_sha256",
            "Unsafe archive member",
            "member.issym()",
            "SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json",
            "SUPERVISOR_FEEDBACK_02_COMPLETE.json",
            "--raw-root",
            "carla_started\": False",
            "raw_r3_modified\": False",
            "source_sha256",
            "Behaviour receipt source hashes do not match the executing sources",
        )
        for needle in required:
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_runner_does_not_start_carla_or_delete_data(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn("CarlaUE4", text)
        self.assertNotIn("rm -", text)
        self.assertNotIn("scp ", text)
        self.assertNotIn("rsync ", text)


if __name__ == "__main__":
    unittest.main()
