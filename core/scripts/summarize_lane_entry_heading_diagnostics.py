#!/usr/bin/env python3
"""Print a compact summary of Stage A lane-entry heading diagnostics."""

import argparse
import csv
import os


def summarize_policy(results_dir, policy):
    scenario_dir = os.path.join(results_dir, f"scenario_uk_give_way_ego_init_01_{policy}")
    csv_path = os.path.join(scenario_dir, "smpc_lane_entry_heading_diagnostics.csv")
    if not os.path.exists(csv_path):
        return f"{policy}: missing diagnostics file"

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return f"{policy}: diagnostics file is empty"

    completion_rows = [row for row in rows if row.get("trigger") == "completion"]
    row = completion_rows[0] if completion_rows else rows[-1]
    return (
        f"{policy}: rows={len(rows)} trigger={row.get('trigger')} "
        f"step={row.get('step')} goal_dist={row.get('goal_dist')} "
        f"s_after={row.get('s_after_route_goal')} epsi={row.get('epsi')} "
        f"ego-ref={row.get('ego_minus_ref_yaw')} "
        f"ego-map={row.get('ego_minus_map_yaw')} "
        f"ref-map={row.get('ref_minus_map_yaw')}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir")
    parser.add_argument(
        "--policies",
        nargs="+",
        default=["smpc_var_risk", "smpc_fixed_risk", "smpc_open_loop"],
    )
    args = parser.parse_args()

    print("\nLane-entry heading diagnostics summary")
    print("=" * 40)
    for policy in args.policies:
        print(summarize_policy(args.results_dir, policy))
    print(f"\nDiagnostics run complete: {args.results_dir}")


if __name__ == "__main__":
    main()
