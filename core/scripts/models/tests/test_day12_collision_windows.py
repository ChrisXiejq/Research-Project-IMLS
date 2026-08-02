#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from audit_day6_collision_windows import classify_window, contact_episodes, sensitivity_decision


class Day12CollisionWindowTest(unittest.TestCase):
    def test_repeated_callbacks_collapse_to_contact_episodes(self) -> None:
        events = [
            {"frame": 100, "monitored_role": "target_2", "other_actor_id": 7, "other_actor_type": "traffic.light", "normal_impulse_magnitude": 2.0},
            {"frame": 100, "monitored_role": "target_2", "other_actor_id": 7, "other_actor_type": "traffic.light", "normal_impulse_magnitude": 3.0},
            {"frame": 101, "monitored_role": "target_2", "other_actor_id": 7, "other_actor_type": "traffic.light", "normal_impulse_magnitude": 1.0},
            {"frame": 105, "monitored_role": "target_2", "other_actor_id": 7, "other_actor_type": "traffic.light", "normal_impulse_magnitude": 4.0},
        ]
        episodes = contact_episodes(events)
        self.assertEqual(len(episodes), 2)
        self.assertEqual(episodes[0]["callbacks"], 3)
        self.assertEqual(episodes[0]["unique_frames"], 2)

    def test_future_overlap_and_post_collision_are_affected(self) -> None:
        sample = {
            "sample_id": 1,
            "step": 4,
            "sim_time_s": 5.0,
            "future_times_s": [5.2, 5.4, 5.6],
            "future_valid_mask": [True, True, True],
            "horizon_steps": 3,
        }
        future = classify_window(sample, [108], 20)
        self.assertTrue(future["future_collision_overlap"])
        self.assertTrue(future["collision_affected_usable"])
        post = classify_window({**sample, "sim_time_s": 6.0, "future_times_s": [6.2, 6.4, 6.6]}, [108], 20)
        self.assertTrue(post["sample_after_first_collision"])
        self.assertTrue(post["collision_affected_usable"])

    def test_decision_uses_reactive_train_fraction(self) -> None:
        summary = {
            "affected_usable_windows": 1,
            "affected_usable_by_split": {"train": 1, "val": 0, "test": 0},
            "affected_reactive_train_windows": 1,
            "reactive_train_usable_windows": 1000,
        }
        self.assertEqual(
            sensitivity_decision(summary)["decision"],
            "report_and_run_b1_seed37_filtered_sensitivity",
        )


if __name__ == "__main__":
    unittest.main()
