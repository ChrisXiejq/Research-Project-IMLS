
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
from pathlib import Path

from core.scripts.models.tools.audit_supervisor_bottleneck_dissertation import audit


def test_current_dissertation_release_passes() -> None:
    experiment_root = Path(__file__).resolve().parents[4]
    thesis_root = experiment_root.parent / "Jiaqi-Xie-Dissertation"
    report = audit(thesis_root)
    assert report["pass"], report
    assert report["checks"]["bibliography"]["entry_count"] >= 30
    assert report["checks"]["compiled_pdf"]["page_count"] is not None
