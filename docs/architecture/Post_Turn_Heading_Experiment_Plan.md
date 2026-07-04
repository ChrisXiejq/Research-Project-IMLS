# Post-Turn Heading Experiment Plan

## Objective

Fix or explain the post-turn visual heading issue in the right-hand-traffic unsignalised give-way scenario:

- Ego vehicle turns left across an oncoming priority vehicle.
- Rule-aware SMPC must keep the validated yielding behaviour.
- After crossing the intersection, the ego should enter the selected exit lane with the vehicle body aligned to the lane direction.

This plan is a visual-quality refinement branch. It must not replace the full dissertation result lineage unless it passes the same post-CARLA safety and completion gates.

## Current Best Baselines

Use these as fixed references:

| Result | Status | Use |
|---|---|---|
| `20260628_103325_final_dissertation` | Best full-method dissertation candidate | Main full-experiment expansion baseline |
| `20260705_000040_anti_early_stop_lane_entry_check` | Safe diagnostic visual branch | Current best post-turn completion branch |

The full-experiment baseline is still `20260628_103325_final_dissertation`. The heading branch should not block full experiment expansion.

## Lessons From Failed And Successful Trials

Successful or safe:

- `20260704_151615_gentle_exit_baseline_check`
  - Required SMPC PASS.
  - No collision, yield OK, solver failure `0.000`.
  - No 600-step stagnation.
  - Heading still poor: `epsi≈0.253-0.260rad`.

- `20260705_000040_anti_early_stop_lane_entry_check`
  - Required SMPC PASS after regenerating stale gate.
  - Completion now happens after the original route goal: `s_after_route_goal≈0.590m`.
  - Heading still poor: `epsi≈0.247-0.259rad`.

Failed or ineffective:

- Strict heading completion `completion_lane_entry_heading_error=0.18`
  - Reintroduced completion failure / tail chasing.

- Static exit speed cap `3.0m/s`
  - Broke fixed-risk safety and yield behaviour.

- 18m Hermite exit shaping
  - Preserved safety but caused 600-step non-completion.

- Route-only downstream goal extension `6m`
  - Safe, but changed `epsi` by only `0.001-0.003rad`.

- Goal-anchored 12m alignment + post-clearance speed cap
  - Too strong; created path-tracking failure and 600-step non-completion.

Conclusion: the issue should not be solved by stricter termination, stronger tail shaping, or larger downstream endpoints. The next experiment must identify whether the problem comes from reference geometry, lane choice/goal yaw, or missing heading penalty during the lane-entry zone.

## Hypothesis

The vehicle is not failing because it ends too early; anti-early-stop delayed completion past the original route goal but `epsi` remained about `0.25rad`.

The likely causes are:

1. The selected route/reference yaw near the exit-lane entry is not aligned with the visually desired lane direction.
2. The controller prioritises position/lateral tracking and collision/yield recovery over final heading quality.
3. The lane-entry completion window accepts `epsi<=0.30rad`, so the video stops while heading is still visibly diagonal.

## Experiment Strategy

Run the next investigation in two stages.

### Stage A: Geometry-Only Diagnosis

Goal: determine whether the desired exit-lane yaw used by the reference is correct.

Do not modify control yet.

Add debug export around the lane-entry zone for each SMPC run:

- ego pose:
  - `x`
  - `y`
  - `psi`
  - `s`
  - `ey`
  - `epsi`
- route/reference pose at nearest arclength:
  - `ref_x`
  - `ref_y`
  - `ref_yaw`
  - `ref_s`
- CARLA map waypoint at ego location:
  - `map_wp_x`
  - `map_wp_y`
  - `map_wp_yaw`
  - `lane_id`
  - `road_id`
- completion goal pose:
  - `goal_x`
  - `goal_y`
  - `goal_yaw`
- heading residuals:
  - `ego_minus_ref_yaw`
  - `ego_minus_map_yaw`
  - `ref_minus_map_yaw`

Export this to:

```text
smpc_lane_entry_heading_diagnostics.json
smpc_lane_entry_heading_diagnostics.csv
```

Trigger diagnostics when:

- `goal_dist <= 8.0m`, or
- `s_after_route_goal >= -8.0m`, or
- completion fires.

Stage A success criteria:

- Determine whether `epsi≈0.25rad` is because ego heading differs from the reference, or because the reference itself differs from the CARLA lane yaw.

Interpretation:

- If `ego_minus_ref_yaw≈0.25rad` but `ref_minus_map_yaw≈0`, the controller is not tracking heading tightly enough.
- If `ref_minus_map_yaw≈0.25rad`, the reference/route geometry is wrong.
- If `ego_minus_map_yaw≈0.25rad` but `ego_minus_ref_yaw` and `ref_minus_map_yaw` split the error, both reference and control need mild changes.

### Stage B1: If Control Tracking Is The Main Problem

Add a bounded heading-quality objective near lane entry.

Design constraints:

- Do not change completion validity.
- Do not change yield supervisor.
- Do not affect pre-yield or hold-yield phases.
- Activate only after the priority target has cleared conflict.
- Activate only near the original route goal.

Recommended initial parameters:

```json
"lane_entry_heading_cost_enabled": true,
"lane_entry_heading_cost_goal_window": 8.0,
"lane_entry_heading_cost_weight": 0.2,
"lane_entry_heading_cost_max_abs_epsi": 0.35
```

Expected effect:

- reduce final `epsi` without forcing completion failure;
- preserve safety and solver feasibility.

Reject if:

- required SMPC does not pass;
- `solver_failure_frac > 0.05`;
- any footprint collision appears;
- completion runs to 600 steps.

### Stage B2: If Reference Geometry Is The Main Problem

Do not use large tail shaping. Instead, correct the lane-entry reference yaw locally.

Use a bounded local yaw blend:

- start: `goal_s - 6m`
- end: `goal_s + 2m`
- yaw target: CARLA map waypoint yaw of the selected exit lane
- maximum yaw correction per point: `0.12rad`

Recommended initial parameters:

```json
"lane_entry_yaw_blend_enabled": true,
"lane_entry_yaw_blend_before_goal_m": 6.0,
"lane_entry_yaw_blend_after_goal_m": 2.0,
"lane_entry_yaw_blend_max_delta": 0.12
```

This is intentionally weaker than:

- 18m Hermite shaping;
- 12m goal-anchored same-lane segment;
- downstream goal extension.

Reject if:

- fixed-risk safety regresses;
- max lateral error grows above the safe baseline;
- 600-step non-completion reappears.

## Recommended Next CARLA Run

First run Stage A only. Do not modify controller behaviour yet.

Use the current safe diagnostic branch:

```text
20260705_000040_anti_early_stop_lane_entry_check
```

Expected gate:

- required SMPC PASS;
- open-loop WARN is acceptable;
- completion by lane-entry;
- `s_after_route_goal >= 0.0`;
- `epsi` likely remains around `0.25rad`.

The run name should be:

```text
lane_entry_heading_diagnostics_check
```

## Decision Table

| Observation | Next action |
|---|---|
| reference yaw matches map yaw, ego yaw differs | Add bounded heading objective near lane entry |
| reference yaw differs from map yaw | Add local yaw blend near lane entry |
| both reference and ego differ from map yaw | Start with local yaw blend, then add small heading objective only if needed |
| heading improves but safety degrades | revert the control/path change; keep diagnostics only |
| heading does not improve but safety remains good | stop tuning; document as visual limitation and use full dissertation baseline |

## Success Criteria For A Visual-Fix Candidate

A visual-fix candidate is acceptable only if all are true:

- required `smpc_var_risk` PASS;
- required `smpc_fixed_risk` PASS;
- `solver_failure_frac=0.000` or at least `<=0.05`;
- no footprint collision;
- yield order OK;
- no 600-step completion failure;
- completion remains near the original goal;
- `abs(epsi) <= 0.20rad` at completion, or clear video evidence shows acceptable body alignment.

If `epsi` remains `0.24-0.26rad`, do not keep tuning this branch. Use `20260628_103325_final_dissertation` for full dissertation experiments.

