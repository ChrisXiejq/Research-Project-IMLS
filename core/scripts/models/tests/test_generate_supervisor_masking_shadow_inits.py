import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from core.scripts.models.generate_supervisor_masking_shadow_inits import (
    R3_IDS,
    SF4_IDS,
    SHADOW_IDS,
    generate_candidates,
    sha256,
)


class SupervisorMaskingShadowInitsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]
        cls.r3 = cls.root / (
            "core/scripts/carla/scenarios/inits/distinction_r3_new/"
            "R3_INIT_GENERATION_MANIFEST.json"
        )
        cls.sf4 = cls.root / (
            "core/scripts/carla/scenarios/inits/distinction_sf4_supervisor_authority_ablation/"
            "SF4_INIT_CANDIDATE_MANIFEST.json"
        )

    def test_exact_pcg64_stream_continuity_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            manifest = generate_candidates(output, self.r3, self.sf4, self.root)
            rng = np.random.default_rng(123)
            rng.uniform(8.0, 10.0, 50)
            rng.uniform(-2.5, 2.5, 50)
            rng.uniform(8.0, 10.0, 5)
            rng.uniform(-2.5, 2.5, 5)
            rng.uniform(8.0, 10.0, 10)
            rng.uniform(-2.5, 2.5, 10)
            expected_speeds = rng.uniform(8.0, 10.0, 20)
            expected_offsets = rng.uniform(-2.5, 2.5, 20)
            self.assertEqual(manifest["numpy_bit_generator"], "PCG64")
            for row, speed, offset in zip(
                manifest["records"], expected_speeds, expected_offsets
            ):
                self.assertEqual(row["init_speed"], float(speed))
                self.assertEqual(row["start_longitudinal_offset"], float(offset))

    def test_ids_hashes_canonical_serialization_and_no_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            manifest = generate_candidates(output, self.r3, self.sf4, self.root)
            ids = [row["ego_init_id"] for row in manifest["records"]]
            self.assertEqual(ids, list(range(116, 136)))
            self.assertFalse(set(ids) & (set(range(1, 51)) | set(R3_IDS) | set(SF4_IDS)))
            for row in manifest["records"]:
                path = output / f"ego_init_{row['ego_init_id']}.json"
                self.assertEqual(sha256(path), row["sha256"])
                payload = json.loads(path.read_text())
                self.assertEqual(
                    path.read_text(), json.dumps(payload, sort_keys=True) + "\n"
                )
            self.assertEqual(
                sha256(self.r3), manifest["stream_predecessors"]["r3"]["sha256"]
            )
            self.assertEqual(
                sha256(self.sf4), manifest["stream_predecessors"]["sf4"]["sha256"]
            )

    def test_candidate_and_manifest_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            generate_candidates(output, self.r3, self.sf4, self.root)
            candidate = output / "ego_init_116.json"
            candidate.write_text('{"init_speed": 8.0, "start_longitudinal_offset": 0.0}\n')
            with self.assertRaisesRegex(SystemExit, "Frozen shadow init drift"):
                generate_candidates(output, self.r3, self.sf4, self.root)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            generate_candidates(output, self.r3, self.sf4, self.root)
            manifest = output / "SUPERVISOR_MASKING_SHADOW_INIT_CANDIDATE_MANIFEST.json"
            data = json.loads(manifest.read_text())
            data["status"] = "modified"
            manifest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
            with self.assertRaisesRegex(SystemExit, "manifest drift"):
                generate_candidates(output, self.r3, self.sf4, self.root)

    def test_predecessor_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            r3_dir = temporary / "r3"
            sf4_dir = temporary / "sf4"
            shutil.copytree(self.r3.parent, r3_dir)
            shutil.copytree(self.sf4.parent, sf4_dir)
            r3_manifest = r3_dir / self.r3.name
            sf4_manifest = sf4_dir / self.sf4.name
            r3_data = json.loads(r3_manifest.read_text())
            r3_data["records"][0]["init_speed"] += 0.1
            r3_manifest.write_text(json.dumps(r3_data, indent=2, sort_keys=True) + "\n")
            with self.assertRaisesRegex(SystemExit, "predecessor hash"):
                generate_candidates(
                    temporary / "out", r3_manifest, sf4_manifest, self.root
                )


if __name__ == "__main__":
    unittest.main()
