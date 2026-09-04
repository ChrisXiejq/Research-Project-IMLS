
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.analysis.plot_supervisor_bottleneck_paper_figures import build_figures


class SupervisorBottleneckPaperFigureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]

    def test_four_python_only_figures_render(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_figures(self.root, Path(directory))
            self.assertEqual(result["status"], "pass")
            self.assertTrue(result["checks"]["all_python_generated"])
            self.assertTrue(result["checks"]["all_pdf_and_png"])
            self.assertTrue(result["checks"]["no_cross_population_pooling"])
            self.assertEqual(len(result["figures"]), 4)
            self.assertTrue(all(record["caption"] for record in result["figures"]))


if __name__ == "__main__":
    unittest.main()
