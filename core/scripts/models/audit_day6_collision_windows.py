#!/usr/bin/env python3
"""Attribute Day 6 CARLA collision callbacks to prediction-label windows.

The Day 6 collection deliberately retained every completed rollout, including
native CARLA collision-sensor callbacks.  This audit distinguishes repeated
callbacks from contact episodes and determines whether any collision time falls
inside, or precedes, a usable prediction label window.  It never mutates the
immutable Day 6 dataset.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


CELLS = ("S0_FIXED", "S0_ADAPTIVE", "S1_FIXED", "S1_ADAPTIVE")
EXPECTED_ROLLOUTS = 200
HISTORY_SECONDS = 1.0


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSON") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def infer_init_id(path: Path) -> int:
    marker = "_ego_init_"
    if marker not in path.name:
        raise ValueError(f"Cannot infer init id from {path}")
    return int(path.name.split(marker, 1)[1].split("_", 1)[0])


def split_for_init(init_id: int) -> str:
    if 1 <= init_id <= 40:
        return "train"
    if 41 <= init_id <= 45:
        return "val"
    if 46 <= init_id <= 50:
        return "test"
    raise ValueError(f"Unexpected init id {init_id}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path}")
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def contact_episodes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated sensor callbacks on adjacent frames by actor pair."""

    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        key = (
            str(event.get("monitored_role")),
            int(event.get("other_actor_id", -1)),
            str(event.get("other_actor_type")),
        )
        grouped[key].append(event)
    episodes: list[dict[str, Any]] = []
    for (role, actor_id, actor_type), actor_events in sorted(grouped.items()):
        by_frame: dict[int, list[float]] = defaultdict(list)
        for event in actor_events:
            by_frame[int(event["frame"])].append(float(event.get("normal_impulse_magnitude", 0.0)))
        frames = sorted(by_frame)
        runs: list[list[int]] = []
        for frame in frames:
            if not runs or frame - runs[-1][-1] > 1:
                runs.append([frame])
            else:
                runs[-1].append(frame)
        for episode_index, run in enumerate(runs, 1):
            impulses = [value for frame in run for value in by_frame[frame]]
            episodes.append(
                {
                    "monitored_role": role,
                    "other_actor_id": actor_id,
                    "other_actor_type": actor_type,
                    "episode_index_for_actor": episode_index,
                    "start_frame": min(run),
                    "end_frame": max(run),
                    "unique_frames": len(run),
                    "callbacks": sum(len(by_frame[frame]) for frame in run),
                    "max_impulse": max(impulses),
                }
            )
    return episodes


def sample_frame(value: float, fps: int) -> tuple[int, float]:
    scaled = value * fps
    rounded = int(round(scaled))
    return rounded, abs(scaled - rounded)


def classify_window(sample: dict[str, Any], event_frames: list[int], fps: int) -> dict[str, Any]:
    sim_time = float(sample["sim_time_s"])
    current_frame, current_residual = sample_frame(sim_time, fps)
    history_start = current_frame - int(round(HISTORY_SECONDS * fps))
    valid_future_times = [
        float(time_value)
        for time_value, valid in zip(
            sample.get("future_times_s") or [], sample.get("future_valid_mask") or []
        )
        if bool(valid)
    ]
    future_frames = [sample_frame(value, fps)[0] for value in valid_future_times]
    future_residual = max(
        [sample_frame(value, fps)[1] for value in valid_future_times] or [0.0]
    )
    future_end = max(future_frames) if future_frames else current_frame
    history_overlap = any(history_start <= frame <= current_frame for frame in event_frames)
    future_overlap = any(current_frame < frame <= future_end for frame in event_frames)
    first_event = min(event_frames) if event_frames else None
    post_collision = first_event is not None and current_frame > first_event
    usable = bool(valid_future_times)
    full_horizon = len(valid_future_times) == int(sample.get("horizon_steps", 10))
    collision_affected = usable and (history_overlap or future_overlap or post_collision)
    return {
        "sample_id": int(sample["sample_id"]),
        "sample_step": int(sample["step"]),
        "sample_frame_inferred": current_frame,
        "history_start_frame_inferred": history_start,
        "future_end_frame_inferred": future_end,
        "frame_lattice_max_residual": max(current_residual, future_residual),
        "valid_future_steps": len(valid_future_times),
        "usable": usable,
        "full_horizon": full_horizon,
        "history_collision_overlap": history_overlap,
        "future_collision_overlap": future_overlap,
        "sample_after_first_collision": post_collision,
        "collision_affected_usable": collision_affected,
    }


def sensitivity_decision(summary: dict[str, Any]) -> dict[str, Any]:
    affected = int(summary["affected_usable_windows"])
    affected_test = int(summary["affected_usable_by_split"].get("test", 0))
    affected_val = int(summary["affected_usable_by_split"].get("val", 0))
    affected_reactive_train = int(summary["affected_reactive_train_windows"])
    reactive_train = int(summary["reactive_train_usable_windows"])
    fraction = affected_reactive_train / reactive_train if reactive_train else 0.0
    if affected_val or affected_test:
        decision = "critical_holdout_contamination_review_required"
    elif affected == 0:
        decision = "no_label_overlap_no_retraining_required"
    elif fraction <= 0.01:
        decision = "report_and_run_b1_seed37_filtered_sensitivity"
    else:
        decision = "material_reactive_train_overlap_full_filtered_matrix_review"
    return {
        "decision": decision,
        "frozen_thresholds": {
            "any_val_or_test_affected": "critical review",
            "zero_affected_usable_windows": "no retraining",
            "reactive_train_affected_fraction_lte_0.01": "B1 seed37 sensitivity",
            "reactive_train_affected_fraction_gt_0.01": "full filtered-matrix review",
        },
        "reactive_train_affected_fraction": fraction,
    }


def audit(day6_root: Path, output_dir: Path) -> dict[str, Any]:
    complete_path = day6_root / "DAY6_COMPLETE.json"
    complete = read_json(complete_path)
    if complete.get("status") != "pass" or int(complete.get("rollout_count", -1)) != EXPECTED_ROLLOUTS:
        raise ValueError("Day 6 completion marker is not a passing 200-rollout contract")

    rollout_rows: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    usable_by_split: Counter[str] = Counter()
    affected_by_split: Counter[str] = Counter()
    reactive_train_usable = 0
    affected_reactive_train = 0
    observed_rollouts = 0

    for cell in CELLS:
        scenario_dirs = sorted((day6_root / cell).glob("scenario_*"))
        if len(scenario_dirs) != 50:
            raise ValueError(f"{cell}: expected 50 scenario directories, found {len(scenario_dirs)}")
        for scenario_dir in scenario_dirs:
            observed_rollouts += 1
            init_id = infer_init_id(scenario_dir)
            split = split_for_init(init_id)
            summary_path = scenario_dir / "scenario_run_summary.json"
            labeled_path = scenario_dir / "prediction_dataset" / "prediction_dataset_labeled.jsonl"
            summary = read_json(summary_path)
            if summary.get("ran_successfully") is not True or not labeled_path.is_file():
                raise ValueError(f"Incomplete Day 6 rollout: {scenario_dir}")
            fps = int(summary["carla_fps"])
            events = list(summary.get("extra", {}).get("collision_events") or [])
            declared_count = int(summary.get("extra", {}).get("collision_event_count", -1))
            if declared_count != len(events):
                raise ValueError(f"Collision callback count mismatch: {summary_path}")
            frames = sorted({int(event["frame"]) for event in events})
            episodes = contact_episodes(events)
            classified = [classify_window(sample, frames, fps) for sample in read_jsonl(labeled_path)]
            max_residual = max((row["frame_lattice_max_residual"] for row in classified), default=0.0)
            if max_residual > 1.0e-3:
                raise ValueError(
                    f"{scenario_dir}: sim_time is not aligned to CARLA frame lattice ({max_residual})"
                )
            usable = [row for row in classified if row["usable"]]
            affected = [row for row in usable if row["collision_affected_usable"]]
            usable_by_split[split] += len(usable)
            affected_by_split[split] += len(affected)
            if cell.startswith("S1") and split == "train":
                reactive_train_usable += len(usable)
                affected_reactive_train += len(affected)
            rollout_rows.append(
                {
                    "cell": cell,
                    "ego_init_id": init_id,
                    "split": split,
                    "scenario_dir": scenario_dir.name,
                    "collision_callbacks": len(events),
                    "unique_collision_frames": len(frames),
                    "contact_episodes": len(episodes),
                    "monitored_roles": ";".join(sorted({str(e["monitored_role"]) for e in events})),
                    "other_actor_types": ";".join(sorted({str(e["other_actor_type"]) for e in events})),
                    "labeled_samples": len(classified),
                    "usable_windows": len(usable),
                    "full_horizon_windows": sum(row["full_horizon"] for row in usable),
                    "history_overlap_windows": sum(row["history_collision_overlap"] for row in usable),
                    "future_overlap_windows": sum(row["future_collision_overlap"] for row in usable),
                    "post_collision_windows": sum(row["sample_after_first_collision"] for row in usable),
                    "affected_usable_windows": len(affected),
                }
            )
            for episode_number, episode in enumerate(episodes, 1):
                episode_rows.append(
                    {
                        "cell": cell,
                        "ego_init_id": init_id,
                        "split": split,
                        "scenario_dir": scenario_dir.name,
                        "rollout_episode_index": episode_number,
                        **episode,
                        "start_time_s_inferred": episode["start_frame"] / fps,
                        "end_time_s_inferred": episode["end_frame"] / fps,
                    }
                )
            if events:
                for row in classified:
                    window_rows.append(
                        {
                            "cell": cell,
                            "ego_init_id": init_id,
                            "split": split,
                            "scenario_dir": scenario_dir.name,
                            **row,
                        }
                    )

    if observed_rollouts != EXPECTED_ROLLOUTS:
        raise ValueError(f"Expected {EXPECTED_ROLLOUTS} rollouts, observed {observed_rollouts}")
    event_rollouts = [row for row in rollout_rows if row["collision_callbacks"] > 0]
    actor_types = sorted(
        {
            actor_type
            for row in event_rollouts
            for actor_type in str(row["other_actor_types"]).split(";")
            if actor_type
        }
    )
    monitored_roles = sorted(
        {
            role
            for row in event_rollouts
            for role in str(row["monitored_roles"]).split(";")
            if role
        }
    )
    totals = {
        "observed_rollouts": observed_rollouts,
        "rollouts_with_callbacks": len(event_rollouts),
        "collision_callbacks": sum(row["collision_callbacks"] for row in event_rollouts),
        "unique_collision_frames": sum(row["unique_collision_frames"] for row in event_rollouts),
        "contact_episodes": sum(row["contact_episodes"] for row in event_rollouts),
        "monitored_roles": monitored_roles,
        "other_actor_types": actor_types,
        "usable_windows": sum(usable_by_split.values()),
        "usable_by_split": dict(usable_by_split),
        "affected_usable_windows": sum(affected_by_split.values()),
        "affected_usable_by_split": dict(affected_by_split),
        "reactive_train_usable_windows": reactive_train_usable,
        "affected_reactive_train_windows": affected_reactive_train,
    }
    decision = sensitivity_decision(totals)
    status = "pass" if not any(role.startswith("ego") for role in monitored_roles) else "review"
    payload = {
        "schema_version": "day12_day6_collision_window_audit_v1",
        "status": status,
        "immutable_source": True,
        "source": {
            "day6_complete_sha256": sha256(complete_path),
            "day6_results": str(day6_root),
        },
        "totals": totals,
        "sensitivity_decision": decision,
        "interpretation": [
            "Native CARLA callbacks are not independent collision episodes.",
            "A window is affected if its history/future overlaps a callback or its current time follows the first callback in that rollout.",
            "No raw sample or rollout is deleted by this audit.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "day12_collision_rollouts.csv", rollout_rows)
    if episode_rows:
        write_csv(output_dir / "day12_collision_episodes.csv", episode_rows)
    if window_rows:
        write_csv(output_dir / "day12_collision_windows.csv", window_rows)
    summary_path = output_dir / "day12_collision_window_audit.json"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    complete_payload = {
        "schema_version": "day12_collision_attribution_complete_v1",
        "status": status,
        "audit_sha256": sha256(summary_path),
        "sensitivity_decision": decision["decision"],
    }
    (output_dir / "DAY12_COLLISION_ATTRIBUTION_COMPLETE.json").write_text(
        json.dumps(complete_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day6-results", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.day6_results.resolve(), args.output_dir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
