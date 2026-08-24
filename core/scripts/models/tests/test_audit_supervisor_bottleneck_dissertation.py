from pathlib import Path

from core.scripts.models.audit_supervisor_bottleneck_dissertation import audit


def test_current_dissertation_release_passes() -> None:
    experiment_root = Path(__file__).resolve().parents[4]
    thesis_root = experiment_root.parent / "Jiaqi-Xie-Dissertation"
    report = audit(thesis_root)
    assert report["pass"], report
    assert report["checks"]["bibliography"]["entry_count"] >= 30
    assert report["checks"]["compiled_pdf"]["page_count"] is not None
