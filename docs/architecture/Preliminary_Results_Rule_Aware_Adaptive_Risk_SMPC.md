# Preliminary Results: Rule-Aware Adaptive-Risk SMPC for Give-Way Interaction

## 1. Status of the Current Results

The strongest validated result so far is the final-method CARLA batch:

```text
core/results/20260628_103325_final_dissertation
```

This run should be treated as the best current quantitative result because it repeats the final method after the main milestone run and passes all required post-CARLA gates. The earlier run:

```text
core/results/20260627_212618_final_dissertation
```

is also valid and should be used as repeatability evidence. The most recent completion-alignment experiments are not yet final results because they are still being used to refine visual route completion and post-turn lane alignment.

The current evidence is sufficient for a preliminary results section. It is not yet sufficient for a final dissertation results section because the post-turn visual completion geometry is still being refined.

## 2. Experimental Setting

The experiment uses a right-hand-traffic unsignalised intersection. The ego vehicle turns left across an oncoming priority vehicle travelling straight. The traffic rule is:

```text
The left-turning ego vehicle must give way to the oncoming straight-going target vehicle.
```

The proposed method combines:

- rule-aware yielding supervision,
- conflict-zone based give-way logic,
- stochastic MPC with multimodal target prediction,
- adaptive interaction-severity risk allocation,
- bounded deterministic bypass during deterministic yield and early recovery phases.

The primary risk profile for the proposed method is:

```text
adaptive_interaction_severity
```

The main ablation profile is:

```text
rule_aware_static_risk
```

This ablation keeps the rule-aware supervisor but disables adaptive interaction-severity risk updates.

## 3. Main Validated Result

The best current final-method run is:

```text
20260628_103325_final_dissertation
```

Post-CARLA gate result:

| Policy | Required | Gate | Center dmin | Footprint collision | Yield order | Solver failure frac |
|---|---:|---|---:|---|---|---:|
| `smpc_fixed_risk` | Yes | PASS | `4.137m` | False | True | `0.000` |
| `smpc_var_risk` | Yes | PASS | `4.060m` | False | True | `0.000` |
| `smpc_open_loop` | No | WARN | `9.497m` | False | False | `0.000` |

The important observation is that `smpc_open_loop` remains collision-free but violates the traffic priority order. In contrast, both rule-aware SMPC variants satisfy the give-way order and avoid footprint collision.

## 4. Quantitative Performance

Aggregate metrics from `20260628_103325_final_dissertation`:

| Policy | Completion time | Feasibility | Avg solve time | dmin TV | Max lateral acc. | Avg longitudinal jerk | Avg lateral jerk | Solver failure frac |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `notv` | `7.95s` | `1.000` | `0.045s` | n/a | `2.718` | `9.425` | `1.753` | n/a |
| `notv_cl` | `8.20s` | `1.000` | `0.042s` | n/a | `2.718` | `9.313` | `2.439` | n/a |
| `smpc_fixed_risk` | `11.55s` | `1.000` | `0.041s` | `4.137m` | `2.909` | `3.487` | `1.596` | `0.000` |
| `smpc_var_risk` | `11.55s` | `1.000` | `0.057s` | `4.060m` | `2.902` | `3.475` | `1.644` | `0.000` |
| `smpc_open_loop` | `29.95s` | `1.000` | `0.036s` | `9.497m` | `6.272` | `0.375` | `2.040` | `0.000` |

The proposed rule-aware SMPC variants are slower than the no-target baselines, which is expected because the ego must yield. However, they reduce longitudinal jerk compared with the no-target references and avoid the large lateral deviation seen in open-loop SMPC.

## 5. Rule Compliance Result

The strongest preliminary result is the separation between geometric collision avoidance and traffic-rule compliance.

`smpc_open_loop`:

- no footprint collision,
- large center clearance,
- but the ego enters the conflict zone before the priority target clears.

Rule-aware SMPC:

- no footprint collision,
- valid target-first yield order,
- zero solver failures,
- valid completion in the validated final-method runs.

This supports the claim that collision avoidance alone is insufficient for socially and legally correct give-way behaviour. A planner must also encode traffic priority.

## 6. No-Adaptive-Risk Ablation

The no-adaptive-risk ablation run is:

```text
20260628_153117_no_adaptive_risk_final_dissertation
```

This run uses:

```text
risk_profile = rule_aware_static_risk
```

It keeps the rule-aware supervisor but disables adaptive interaction-severity risk allocation.

| Policy | Gate | Center dmin | Completion time | Yield order | Solver failure frac |
|---|---|---:|---:|---|---:|
| `smpc_fixed_risk` | PASS | `4.154m` | `11.50s` | True | `0.000` |
| `smpc_var_risk` | PASS | `4.285m` | `12.70s` | True | `0.000` |
| `smpc_open_loop` | WARN | `9.509m` | `29.95s` | False | `0.000` |

The ablation does not fail. Therefore, the dissertation should not claim that adaptive risk is required for basic safety in this nominal scenario. The more accurate claim is:

```text
The rule-aware supervisor is the primary factor for traffic-rule compliance.
Adaptive interaction-severity risk allocation provides an interpretable
phase-dependent risk mechanism and can improve efficiency or path stability
under selected interaction conditions while preserving safety.
```

Compared with the static-risk ablation, the adaptive run improves the variable-risk completion time in the nominal repeat:

| Method | `smpc_var_risk` completion time | `smpc_var_risk` max lateral error |
|---|---:|---:|
| Adaptive risk | `11.55s` | `3.147m` |
| Static risk ablation | `12.70s` | `3.840m` |

This supports a preliminary efficiency and path-stability benefit for adaptive risk, but not a universal clearance improvement.

## 7. Target-Speed Sweep

The first controlled full-experiment expansion is:

```text
20260628_155621_target_speed_sweep
```

The tested target speeds are:

```text
4.5m/s, 6.0m/s, 7.5m/s
```

Across all tested speeds, all required rule-aware SMPC policies pass the reconstructed post-CARLA gate:

| Target speed | Risk profile | `smpc_fixed_risk` | `smpc_var_risk` | Open-loop |
|---:|---|---|---|---|
| `4.5m/s` | Adaptive | PASS | PASS | WARN, yield-order failure |
| `4.5m/s` | Static risk | PASS | PASS | not run |
| `6.0m/s` | Adaptive | PASS | PASS | WARN, yield-order failure |
| `6.0m/s` | Static risk | PASS | PASS | not run |
| `7.5m/s` | Adaptive | PASS | PASS | WARN, yield-order failure |
| `7.5m/s` | Static risk | PASS | PASS | not run |

This result supports preliminary robustness across controlled changes in interaction severity. It also reinforces the open-loop contrast: the open-loop policy can remain collision-free but repeatedly violates the give-way order.

## 8. Preliminary Claims Supported

The current results support four preliminary claims.

First, rule awareness is necessary. Open-loop SMPC can avoid collision but still violate the priority rule.

Second, the proposed rule-aware SMPC architecture preserves safety and feasibility in the validated nominal runs. Both required SMPC variants pass with zero solver failures and no footprint collision.

Third, adaptive interaction-severity risk allocation is a plausible improvement over static risk allocation, especially for efficiency and path stability, but the current evidence does not justify claiming that it always improves clearance.

Fourth, the method generalises beyond a single nominal target speed in a controlled sweep. This is enough to motivate full-experiment expansion, but not enough to claim broad statistical robustness.

## 9. Limitations

The current results are preliminary for three reasons.

First, the experiment is still small-scale. It includes nominal validation, one no-adaptive-risk ablation, and a target-speed sweep, but not yet a full target-gap or multi-initial-condition sweep.

Second, the visual post-turn completion geometry is still being refined. Recent experiments with stricter completion and altered goal offsets exposed route-end and post-turn lane-alignment issues. These runs should not be included as final quantitative evidence.

Third, adaptive risk has not yet been shown to dominate static risk across all metrics. Static risk can sometimes produce larger raw clearance. The dissertation should frame adaptive risk as interpretable and condition-dependent rather than universally better.

## 10. Preliminary Conclusion

The preliminary experiments show that a rule-aware SMPC planner can produce collision-free, solver-feasible, and traffic-rule-compliant give-way behaviour in a CARLA unsignalised intersection. The open-loop baseline demonstrates that collision avoidance alone does not guarantee correct priority behaviour. The no-adaptive-risk ablation indicates that the rule-aware supervisor is the main factor behind give-way compliance, while adaptive interaction-severity risk allocation provides an interpretable mechanism that can improve efficiency and path stability in selected cases.

These results are sufficient for a preliminary results section. The next step toward final dissertation results is to validate the latest post-turn completion geometry and then rerun the final batch plus the target-speed sweep under the final visual configuration.
