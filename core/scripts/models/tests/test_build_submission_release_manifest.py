from pathlib import Path

from core.scripts.models.build_submission_release_manifest import build_manifest


def test_current_submission_release_is_bound_and_locatable() -> None:
    experiment_root = Path(__file__).resolve().parents[4]
    dissertation_root = experiment_root.parent / "Jiaqi-Xie-Dissertation"
    payload = build_manifest(experiment_root, dissertation_root)
    assert payload["status"] == "pass"
    assert payload["tests"]["relevant_unittest_total"] == 274
    assert all(payload["checks"].values())
    assert len(payload["bounded_limitations"]) >= 5
