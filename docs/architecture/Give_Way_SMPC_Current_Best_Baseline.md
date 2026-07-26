# Give-Way SMPC Current Best Baseline

Freeze date: 2026-07-26

## Code State

This baseline is frozen as the current best shared runtime baseline, not as a
clean git tag. Later ablation harness changes should be layered on top of this
baseline without changing the shared supervisor / stop-target / approach-braking
settings.

```text
branch: main
runtime_baseline_commit: a017793a7abe58609cd86ccc7d2e68cda3b44a41
runtime_baseline_short_commit: a017793 feat: ablation
current_ablation_harness_base: 79c27183a38856fca5e527e8d05daeb81915b15d plus current working-tree ablation updates
state: frozen runtime baseline plus A1/A2 ablation harness updates
```

Reason: the current best runtime baseline is the v12 shared planner/supervisor
lineage used for close-stop validation and the target-speed sweeps. It should be
kept fixed for ablation. A1/A2 scripts may generate scenario difficulty and
adaptive-risk ablation arms, but they must not retune supervisor strength, stop
clearance, or SMPC approach braking unless a new baseline is explicitly
re-frozen.

## Frozen Configuration

Current-best config snapshot:

```text
core/scripts/carla/scenarios/tuning_configs/give_way_reduced_clear_path_release_v12_current_best.json
```

Active config at freeze time:

```text
core/scripts/carla/scenarios/tuning_configs/give_way_reduced_clear_path_release_frozen.json
```

Key settings:

```text
yield_supervisor_mode = reduced_intervention
yield_planner_ownership_stress_enabled = true
smpc_intersection_approach_speed_shaping_enabled = true
smpc_intersection_approach_distance = 16.0
smpc_intersection_approach_speed = 5.0
smpc_intersection_approach_decel = -3.0
yield_stop_clearance_override = 4.0
yield_stop_line_creep_min_clearance_override = 4.0
target nominal/init speed = 9.0
```

## Validation Result

Current best result:

```text
core/results/20260726_004504_init01_v12_close_stop_4p0_fixed_frontier_vs_adaptive
```

All four SMPC arms passed post-CARLA gate:

| Arm | First Stop | Completion | Center dmin | Min Footprint | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| smpc_fixed_aggressive | 4.547m | 10.10s | 4.834m | 1.423m | PASS |
| smpc_fixed_medium | 4.543m | 10.55s | 4.829m | 1.417m | PASS |
| smpc_fixed_conservative | 4.520m | 10.30s | 4.760m | 1.332m | PASS |
| smpc_adaptive_floor_weak | 4.509m | 10.10s | 4.725m | 1.290m | PASS |

## Interpretation

v12 is the current best shared planner/supervisor baseline:

- it keeps safety in hard init01;
- it moves the first stop closer than v11 by about 0.33-0.38m;
- it validates that 4.0m stop clearance can work after executable SMPC approach
  braking and planner-ownership stress.

It is not strong adaptive-risk evidence by itself:

- fixed-risk frontier and adaptive-risk all pass;
- wait and clearance delay are identical across arms;
- supervisor active fraction remains similar;
- all arms have two critical/pre-clearance infeasible steps;
- adaptive/floor_weak stops closest and has the lowest nominal-final mismatch,
  but also has the smallest center/footprint safety margin.

## Next Experiment

Do not continue target-speed micro-sweeps as the immediate next step. The coarse
target-speed sweep suggested a possible `9.0m/s` fixed-conservative failure, but
the fine sweep did not reproduce it. Treat speed-only difficulty as insufficient
main evidence.

Use A1 to find a hard interaction subset:

```text
core/scripts/carla/run_give_way_init01_v12_arrival_gap_sweep.sh
```

Then run A2 mechanism ablation on the selected hard offsets:

```text
core/scripts/carla/run_give_way_init01_v12_phase_ablation.sh
```

A1/A2 must keep all v12 shared planner/supervisor settings fixed. Adaptive-risk
advantage should be claimed only if the full adaptive arm beats the fixed-risk
frontier and phase-ablation controls on safety-efficiency-feasibility trade-off,
without relying on stronger shared supervisor intervention.
