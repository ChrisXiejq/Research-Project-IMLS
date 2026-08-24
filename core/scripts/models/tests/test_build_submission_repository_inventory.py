import unittest

from core.scripts.models.build_submission_repository_inventory import (
    classify_dissertation_path,
    classify_experiment_path,
    _sanitize_remote,
)


class SubmissionRepositoryInventoryTest(unittest.TestCase):
    def test_experiment_categories_cover_current_scientific_roles(self):
        expected = {
            "core/scripts/models/generate_capacity_history_v3_results.py": "v3_canonical",
            "docs/paper/generated/capacity_history_v3/final/result.csv": "v3_canonical",
            "core/scripts/carla/policies/conflict_zone_safety_filter.py": "implicit_filter_exploratory",
            "tmp/pdfs/page.png": "reproducible_cache",
            "openspec/changes/supervisor-bottleneck-thesis/tasks.md": "new_thesis_work",
            "docs/paper/generated/supervisor_bottleneck_v1/result.json": "generated_evidence",
        }
        for path, category in expected.items():
            with self.subTest(path=path):
                self.assertEqual(classify_experiment_path(path), category)

    def test_dissertation_categories_cover_submission_roles(self):
        expected = {
            "main.tex": "manuscript_source",
            "main.pdf": "generated_final_pdf",
            "figures/capacity/figure.png": "manuscript_figure",
            "output/main.log": "reproducible_build_output",
            "Supervisor Progress Update - 2026-08-23.md": "progress_document",
            "项目全流程中文说明.md": "progress_document",
        }
        for path, category in expected.items():
            with self.subTest(path=path):
                self.assertEqual(classify_dissertation_path(path), category)

    def test_unknown_paths_fail_closed(self):
        self.assertEqual(classify_experiment_path("mystery.bin"), "unresolved")
        self.assertEqual(classify_dissertation_path("mystery.bin"), "unresolved")

    def test_http_remote_credentials_are_removed(self):
        self.assertEqual(
            _sanitize_remote("https://token@example.com/owner/repo.git"),
            "https://example.com/owner/repo.git",
        )
        self.assertEqual(
            _sanitize_remote("git@github.com:owner/repo.git"),
            "git@github.com:owner/repo.git",
        )


if __name__ == "__main__":
    unittest.main()
