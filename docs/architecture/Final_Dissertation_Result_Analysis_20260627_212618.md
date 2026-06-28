# Final Dissertation Result Analysis: `20260627_212618_final_dissertation`

## 1. Run Identity

This document summarises the current best full dissertation-batch candidate for the rule-aware adaptive-risk SMPC give-way experiment.

```text
Result directory:
core/results/20260627_212618_final_dissertation

Scenario:
scenario_uk_give_way.json / ego_init_01.json

Traffic setting:
Right-hand-traffic unsignalised intersection.
The ego vehicle turns left and must give way to an oncoming straight-going priority target vehicle.

Solver:
Gurobi

Risk profile:
adaptive_interaction_severity

Policies:
notv
notv_cl
smpc_var_risk
smpc_fixed_risk
smpc_open_loop
```

The run generated the expected postprocess artifacts:

```text
core/results/20260627_212618_final_dissertation/paper_panel.png
core/results/20260627_212618_final_dissertation/paper_panel.svg
core/results/20260627_212618_final_dissertation/trajectory_map.png
core/results/20260627_212618_final_dissertation/trajectory_map.svg
core/results/20260627_212618_final_dissertation/paper_metrics_summary.md
core/results/20260627_212618_final_dissertation/postcarla_trajectory_gate.md
```

## 2. Final Method Configuration

The run uses the final dissertation-method configuration after the geometry, release, recovery, and hold-line clearance fixes.

| Component | Final setting | Purpose |
|---|---:|---|
| Ego visual start offset | `+2.75m` | Places the ego vehicle in the visually accepted left-turn start lane position. |
| `yield_stop_buffer_distance` | `8.0m` | Moves the hold pose upstream to avoid footprint overlap while the target passes. |
| `yield_release_clearance_margin` | `1.0m` | Requires the target to clear beyond the nominal conflict radius before release. |
| `yield_conflict_radius` | `4.0m` | Defines the conflict-zone radius used by the give-way rule gate. |
| `yield_reference_decel` | `-3.75m/s^2` | Produces a smoother but sufficiently strong yield reference profile. |
| `yield_recovery_speed` | `4.0m/s` | Allows the ego to recover after yielding without overly aggressive acceleration. |
| `yield_recovery_accel` | `1.2m/s^2` | Bounds recovery acceleration to preserve solver feasibility. |
| Risk profile | `adaptive_interaction_severity` | Tightens or relaxes risk according to conflict-zone interaction severity. |
| Rule-aware bypass | approach/hold + bounded recovery handoff | Handles deterministic traffic-rule yielding outside the SMPC solve where appropriate. |

Important: the deterministic bypass is bounded and phase-specific. It does not replace the full trajectory planner.

```text
smpc_fixed_risk:
  deterministic_rule_yield_control: 55 frames, steps 18-72
  deterministic_rule_yield_recovery_handoff: 16 frames, steps 73-88

smpc_var_risk:
  deterministic_rule_yield_control: 56 frames, steps 18-73
  deterministic_rule_yield_recovery_handoff: 16 frames, steps 74-89
```

## 3. Post-CARLA Gate Result

The post-CARLA trajectory gate reports `Overall: WARN`, but this is not a failure of the proposed method. The warning is caused by the non-required `smpc_open_loop` baseline violating give-way order. The required policies are `smpc_fixed_risk` and `smpc_var_risk`, and both pass.

| Policy | Required | Gate status | Solver failure frac | Footprint collision | Center dmin | Min footprint separation | Give-way order |
|---|---:|---|---:|---|---:|---:|---|
| `smpc_fixed_risk` | Yes | PASS | `0.000` | False | `4.142m` | `0.347m` | True |
| `smpc_var_risk` | Yes | PASS | `0.000` | False | `3.897m` | `0.135m` | True |
| `smpc_open_loop` | No | WARN | `0.000` | False | `9.512m` | `5.878m` | False |
| `notv` | No | WARN | n/a | n/a | n/a | n/a | n/a |
| `notv_cl` | No | WARN | n/a | n/a | n/a | n/a | n/a |

The key traffic-rule timing result is:

| Policy | Target exit time | Ego enter time | Target clears first |
|---|---:|---:|---|
| `smpc_fixed_risk` | `4010.487s` | `4011.787s` | True |
| `smpc_var_risk` | `3970.613s` | `3972.013s` | True |
| `smpc_open_loop` | `4050.478s` | `4046.728s` | False |

This is the most important qualitative result: the proposed rule-aware SMPC variants satisfy the traffic priority relation, while the open-loop SMPC baseline can remain collision-free but still violate the give-way rule.

## 4. Aggregate Performance Metrics

| Policy | Completion time | Feasibility | Avg solve time | dmin TV | Max lateral acc. | Avg longitudinal jerk | Avg lateral jerk | Hausdorff vs notv | Solver failure frac |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `notv` | `7.95s` | `1.000` | `0.0416s` | n/a | `2.718` | `9.423` | `1.753` | `0.000` | n/a |
| `notv_cl` | `8.20s` | `1.000` | `0.0376s` | n/a | `2.718` | `9.313` | `2.439` | `3.577` | n/a |
| `smpc_fixed_risk` | `11.60s` | `1.000` | `0.0601s` | `4.142m` | `2.901` | `3.542` | `1.568` | `4.120` | `0.000` |
| `smpc_var_risk` | `12.55s` | `1.000` | `0.0816s` | `3.897m` | `2.898` | `3.297` | `1.495` | `4.064` | `0.000` |
| `smpc_open_loop` | `29.95s` | `1.000` | `0.0612s` | `9.512m` | `6.272` | `0.397` | `1.990` | `33.646` | `0.000` |

Interpretation:

- `smpc_fixed_risk` and `smpc_var_risk` both complete the interaction, satisfy the give-way rule, avoid footprint collision, and have zero solver failures.
- `smpc_var_risk` has slightly lower center and footprint clearance than fixed risk, but it remains collision-free and valid.
- `smpc_open_loop` produces a large route deviation and violates traffic priority despite avoiding collision.
- The proposed rule-aware variants are slower than `notv` and `notv_cl`, which is expected because the ego vehicle must yield to a priority target.
- The proposed rule-aware variants have much lower longitudinal jerk than `notv` / `notv_cl`, because yielding replaces the abrupt unblocked trajectory with a controlled stop-and-release interaction.

## 5. Completion Diagnostics

| Policy | Completion valid | Completion step | Goal distance | Completion lateral error | Remaining route margin | Max abs lateral error |
|---|---:|---:|---:|---:|---:|---:|
| `smpc_fixed_risk` | True | `233` | `7.918m` | `-3.155m` | `7.0m` | `3.169m` |
| `smpc_var_risk` | True | `252` | `7.914m` | `-3.068m` | `7.0m` | `3.093m` |
| `smpc_open_loop` | n/a | n/a | n/a | n/a | n/a | `15.735m` |

The completion metrics support the claim that the proposed method remains on a valid route after the yield interaction. The open-loop baseline has very large lateral deviation, which reinforces that a collision-free trajectory is not sufficient for a high-quality give-way behaviour.

## 6. Main Dissertation Claims Supported by This Run

### Claim 1: Traffic-rule awareness is necessary in an unsignalised give-way interaction.

Evidence:

- `smpc_open_loop` avoids footprint collision but violates the give-way order.
- `smpc_fixed_risk` and `smpc_var_risk` both satisfy `target_clears_before_ego_enters=True`.

This supports the dissertation argument that physical collision avoidance and traffic-rule compliance are different requirements. A planner can be safe in a narrow geometric sense while still being behaviourally wrong.

### Claim 2: The proposed rule-aware SMPC architecture preserves safety and completion.

Evidence:

- Both required SMPC policies pass the post-CARLA gate.
- Both have `solver_failure_frac=0.000`.
- Both have `footprint_collision=False`.
- Both have valid completion.
- Both satisfy yield order.

This supports the claim that adding the rule-aware supervisor and adaptive risk allocation does not make the CARLA rollout infeasible or unsafe.

### Claim 3: Interaction-severity-aware risk allocation gives an interpretable mechanism for changing constraint conservatism.

Evidence:

- The run uses `risk_profile=adaptive_interaction_severity`.
- The risk profile is conditioned on the traffic-policy relationship and the conflict-zone interaction state.
- The supervisor applies stricter behaviour while the ego approaches or holds before the conflict zone, and relaxes after the priority target has cleared.

This supports the methodological contribution: risk allocation is no longer a fixed reproduction parameter only; it is linked to interaction severity and traffic priority.

### Claim 4: Deterministic traffic-rule phases should be handled by a bounded rule-aware layer rather than forced through every SMPC solve.

Evidence:

- Earlier runs showed solver infeasibility during deterministic stop/hold and early recovery phases.
- This final run has zero solver failures for both required SMPC policies.
- Bypass is bounded:
  - approach/hold only while priority yielding is active,
  - exactly 16 frames for early recovery handoff,
  - no bypass in normal open-loop driving.

This supports the system-design argument that deterministic rule compliance and stochastic trajectory optimisation should be combined, not treated as the same problem.

### Claim 5: The final hold-line clearance fix is necessary for footprint-level safety.

Evidence:

- `20260627_205856_final_dissertation` failed because fixed risk collided during `hold_yield_line`.
- Increasing `yield_stop_buffer_distance` from `6.25m` to `8.0m` moves the waiting pose upstream.
- In `20260627_212618_final_dissertation`, fixed risk has no footprint collision and its minimum footprint separation improves to `0.347m`.

This supports the practical design conclusion that the give-way stop line must be defined using footprint-level safety, not only center-distance or nominal conflict-zone clearance.

## 7. Suggested Dissertation Tables

### Table A: Safety and Rule Compliance

| Method | Collision-free | Yield order valid | Solver failure frac | Completion valid | Main interpretation |
|---|---:|---:|---:|---:|---|
| `smpc_fixed_risk` | Yes | Yes | `0.000` | Yes | Rule-aware fixed-risk SMPC passes all required checks. |
| `smpc_var_risk` | Yes | Yes | `0.000` | Yes | Proposed adaptive/variable-risk method passes all required checks. |
| `smpc_open_loop` | Yes | No | `0.000` | n/a | Collision avoidance alone does not enforce traffic priority. |
| `notv` | n/a | n/a | n/a | n/a | Unobstructed reference behaviour only. |
| `notv_cl` | n/a | n/a | n/a | n/a | Closed-loop no-target reference behaviour only. |

### Table B: Efficiency and Comfort

| Method | Completion time | Avg solve time | Max lateral acc. | Avg longitudinal jerk | Avg lateral jerk |
|---|---:|---:|---:|---:|---:|
| `notv` | `7.95s` | `0.0416s` | `2.718` | `9.423` | `1.753` |
| `notv_cl` | `8.20s` | `0.0376s` | `2.718` | `9.313` | `2.439` |
| `smpc_fixed_risk` | `11.60s` | `0.0601s` | `2.901` | `3.542` | `1.568` |
| `smpc_var_risk` | `12.55s` | `0.0816s` | `2.898` | `3.297` | `1.495` |
| `smpc_open_loop` | `29.95s` | `0.0612s` | `6.272` | `0.397` | `1.990` |

### Table C: Conflict-Zone Clearance

| Method | Center dmin | Min footprint separation | Target exits before ego enters |
|---|---:|---:|---:|
| `smpc_fixed_risk` | `4.142m` | `0.347m` | Yes |
| `smpc_var_risk` | `3.897m` | `0.135m` | Yes |
| `smpc_open_loop` | `9.512m` | `5.878m` | No |

The open-loop result is intentionally useful: it has large geometric clearance but violates the temporal priority rule. This cleanly separates traffic-rule compliance from pure geometric distance.

## 8. Figures and Videos to Use

Use these artifacts for the dissertation:

| Artifact | Suggested use |
|---|---|
| `paper_panel.png` | Main combined result figure for the experiment section. |
| `trajectory_map.png` | Trajectory comparison and conflict-zone explanation. |
| `postcarla_trajectory_gate.md` | Safety and rule-compliance audit trail. |
| `paper_metrics_summary.md` | Source for quantitative tables. |
| `scenario_uk_give_way_ego_init_01_smpc_var_risk/carla_sim.avi` | Video evidence for proposed variable-risk policy. |
| `scenario_uk_give_way_ego_init_01_smpc_fixed_risk/carla_sim.avi` | Video evidence for fixed-risk rule-aware policy. |
| `scenario_uk_give_way_ego_init_01_smpc_open_loop/carla_sim.avi` | Video evidence for baseline rule violation. |

Recommended video keyframes:

1. Ego approaches the yield line.
2. Ego holds upstream of the conflict zone.
3. Target vehicle passes the conflict zone first.
4. Ego releases and completes the left turn.
5. Open-loop baseline enters before the target clears, illustrating rule violation.

## 9. Limitations and Caveats

This run is strong enough to support the dissertation result section, but the following caveats should be stated clearly:

- The evaluation currently uses one main CARLA scenario and one initial condition. It is a focused case study rather than a broad statistical benchmark.
- `smpc_var_risk` has a small but positive footprint separation margin (`0.135m`). The method passes, but the margin is tight enough that the `8.0m` hold-line buffer should not be reduced.
- The `Overall: WARN` gate status should be explained: it is caused by non-required baselines (`notv`, `notv_cl`, and `smpc_open_loop`), while required SMPC policies pass.
- The open-loop baseline is valuable as a rule-compliance contrast, but it is not a final driving policy because it violates give-way order.
- The deterministic bypass should be described as a bounded traffic-rule control layer, not as a replacement for SMPC.

## 10. Recommended Next Experiments

The next experiments should be ablations that test the dissertation contribution, not more blind tuning.

| Ablation | Change | Purpose |
|---|---|---|
| Full method | Current `20260627_212618_final_dissertation` configuration | Main result. |
| No adaptive risk | Keep rule-aware supervisor, use `rule_aware_static_risk` | Test whether interaction-severity risk allocation improves feasibility/safety tradeoff without disabling rule-aware bypass. |
| No traffic-policy weighting | Keep conflict-zone distance/TTC, remove priority-rule contribution | Test whether traffic policy matters beyond geometry. |
| No bounded recovery handoff | Disable early recovery handoff bypass | Show why deterministic release handoff improves solver stability. |
| Smaller stop buffer | Compare `6.25m` vs `8.0m` using prior results | Explain why footprint-level hold-line clearance is needed. |

## 11. Completed No-Adaptive-Risk Ablation

Run:

```text
20260628_153117_no_adaptive_risk_final_dissertation
```

Configuration:

```text
risk_profile = rule_aware_static_risk
tight = 1.64
target_prob = 0.949497
```

This ablation keeps the rule-aware supervisor, deterministic yield bypass, bounded recovery handoff, final `+2.75m` visual geometry, `8.0m` stop buffer, and `1.0m` release clearance margin. Only the interaction-severity adaptive risk update is disabled.

Key result:

| Method | Gate | Center dmin | Completion time | Solver failure | Forced ref. linearization | Main interpretation |
|---|---:|---:|---:|---:|---:|---|
| Adaptive `smpc_var_risk` repeat `20260628_103325` | PASS | `4.060m` | `11.55s` | `0.000` | `0.194` | Faster and more route-stable. |
| Static-risk `smpc_var_risk` ablation `20260628_153117` | PASS | `4.285m` | `12.70s` | `0.000` | `0.247` | Safe, but slower and needs more reference recovery. |
| Adaptive `smpc_fixed_risk` repeat `20260628_103325` | PASS | `4.137m` | `11.55s` | `0.000` | `0.194` | Stable rule-aware fixed-risk baseline. |
| Static-risk `smpc_fixed_risk` ablation `20260628_153117` | PASS | `4.154m` | `11.50s` | `0.000` | `0.190` | Essentially unchanged, as expected for fixed-risk behaviour. |

Debug evidence:

| Run | Policy | Adaptive enabled | Tightening range | Risk phase evidence |
|---|---|---:|---:|---|
| Adaptive repeat | `smpc_var_risk` | `232/232` | `1.282-1.727` | `nominal`, `medium`, `relaxed_after_clearance` |
| Static ablation | `smpc_var_risk` | `0/255` | `1.640-1.640` | `static_profile` |

Conclusion:

The no-adaptive-risk ablation does not fail in the validated single scenario, so the dissertation should not claim that static risk is unsafe here. The stronger and defensible claim is narrower: with the same rule-aware traffic supervisor, adaptive interaction-severity risk allocation improves the variable-risk controller's efficiency and route stability while preserving safety, yield order, completion, and zero solver failures.

## 12. Suggested Results-Section Narrative

A concise results narrative for the dissertation:

> The final rule-aware adaptive-risk SMPC configuration successfully completed the unsignalised give-way interaction in CARLA. Both fixed-risk and variable-risk SMPC variants passed the post-CARLA gate with zero solver failures, no footprint collision, valid completion, and correct give-way ordering. In contrast, the open-loop SMPC baseline remained collision-free but entered the conflict zone before the priority target had cleared it, demonstrating that geometric collision avoidance alone is insufficient for traffic-rule-compliant behaviour. The final method therefore supports the central claim of this dissertation: traffic-rule awareness and conflict-zone interaction severity should be incorporated into SMPC for priority-sensitive urban interactions.

## 13. Dissertation Conclusion Supported by This Run

The result supports the following final conclusion:

```text
Rule-aware SMPC with conflict-zone interaction-severity adaptive risk allocation can produce a traffic-rule-compliant give-way behaviour in a CARLA unsignalised intersection scenario. The method preserves completion, avoids footprint collision, maintains zero solver failures in the validated run, and corrects the key weakness of a non-rule-aware open-loop baseline: violation of priority order despite collision-free motion.
```
