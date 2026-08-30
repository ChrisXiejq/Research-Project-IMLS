import tempfile
import unittest
from pathlib import Path

from core.scripts.models.plot_supervisor_bottleneck_paper_figures import build_figures


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
