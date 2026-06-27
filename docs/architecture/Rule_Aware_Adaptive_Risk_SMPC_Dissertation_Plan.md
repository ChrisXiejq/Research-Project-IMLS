# Rule-Aware Adaptive-Risk SMPC Dissertation Plan

This document defines the dissertation direction, experimental scheme, implementation route, and evaluation plan for the give-way SMPC project. It should be read together with:

- `docs/architecture/UK_Give_Way_Intersection_Scenario.md`
- `docs/architecture/Give_Way_SMPC_Experiment_Changelog.md`

The current experiment has moved from parameter tuning toward the dissertation contribution: rule-aware SMPC with interaction-severity-adaptive risk allocation and a bounded deterministic recovery handoff after rule-compliant yielding.

## Current Milestone

The current dissertation candidate run is:

```text
core/results/20260627_201840
```

This run should be used as the current final-method dissertation candidate for the proposed method.

Key configuration:

- `risk_profile=adaptive_interaction_severity`
- policies: `smpc_var_risk`, `smpc_fixed_risk`, `notv`, `notv_cl`
- ego visual start geometry: `start_left_offset=+2.75`, confirmed by video inspection
- unified mild adaptive risk allocation
- deterministic rule-yield SMPC solve bypass during `approach_yield_line` and `hold_yield_line`
- bounded deterministic recovery-handoff bypass during the first low-speed `released_recovery` frames after the priority target has cleared the conflict zone

Key result:

- both required SMPC policies pass the post-CARLA gate,
- `solver_failure_frac=0.000` for both `smpc_var_risk` and `smpc_fixed_risk`,
- no footprint collision,
- valid completion,
- target vehicle clears the conflict zone before ego enters,
- `smpc_fixed_risk` center clearance is `4.227m`, `smpc_var_risk` center clearance is `4.147m`,
- both policies complete in about `11.10s`,
- the recovery-handoff bypass is bounded to `16` early `released_recovery` frames and does not replace the full recovery phase.

This candidate supports the dissertation argument that deterministic traffic-rule yielding should be handled by a rule-aware supervisory layer, while SMPC and adaptive risk allocation handle interaction-aware planning outside deterministic stop/hold and short recovery-handoff windows.

Earlier milestone `core/results/20260627_155115` remains useful as the first dissertation-quality proof that rule-yield bypass removes approach/hold infeasibility. The newer `20260627_201840` supersedes it as the final-method candidate because it also uses the user-confirmed `+2.75m` visual start geometry and fixes the released-recovery solver failures.

## 1. Dissertation Topic

Working title:

**Rule-Aware Stochastic Model Predictive Control with Interaction-Severity-Adaptive Risk Allocation for Autonomous Vehicle Give-Way Behaviour at Unsignalised Intersections**

Short version:

**Rule-Aware Adaptive-Risk SMPC for Left-Turn Give-Way Interaction**

The dissertation studies an unsignalised intersection where the ego vehicle turns left across an oncoming straight-going priority vehicle. The original SMPC framework is extended by adding traffic-rule awareness and an adaptive risk allocation mechanism driven by interaction severity.

## 2. Traffic Setting

The final experiment should use the current right-hand-traffic interpretation:

- Ego vehicle: left-turning vehicle.
- Target vehicle: oncoming straight-going priority vehicle.
- Rule: the turning vehicle gives way to the oncoming straight-going vehicle.
- Intersection: unsignalised.

This is acceptable for the dissertation because the research contribution is not tied to UK traffic law. The contribution is the general priority-aware interaction mechanism. Right-hand traffic is also more consistent with the current implementation, existing CARLA videos, and tuning history.

The dissertation should describe the scenario as a representative international right-hand-traffic give-way case. A UK left-hand-traffic transfer can be mentioned as future work, not as the main experiment.

## 3. Research Gap

The original SMPC-style method handles uncertainty and multimodal predictions, but the interaction does not explicitly encode a traffic-rule priority relation. In a left-turn give-way scenario, a geometrically safe trajectory is not enough: the ego vehicle must also respect the priority vehicle's right of way.

Existing risk allocation can also be too static. The same risk threshold is applied during different interaction phases, even though the severity changes:

- far from the conflict zone,
- approaching the yield line,
- holding while the priority vehicle crosses,
- recovering after the priority vehicle clears the zone.

This motivates a rule-aware SMPC layer and an adaptive risk allocation rule based on interaction severity.

## 4. Main Thesis Claim

The main claim is:

**A rule-aware SMPC controller with interaction-severity-adaptive risk allocation can produce safer, more rule-compliant, and more behaviourally reasonable give-way manoeuvres than fixed-risk SMPC or ordinary variable-risk SMPC in an unsignalised left-turn interaction.**

The expected advantage is not only collision avoidance. The method should also improve:

- rule compliance,
- conflict-zone ordering,
- post-yield recovery,
- excessive conservativeness,
- solver behaviour during high-risk interaction phases,
- interpretability of parameter tuning.

## 5. Research Hypotheses

### H1: Rule Awareness

Compared with rule-free or open-loop SMPC baselines, rule-aware SMPC improves traffic-rule compliance. The priority vehicle should clear the conflict zone before the ego vehicle enters it.

### H2: Adaptive Risk Allocation

Compared with fixed-risk allocation and ordinary variable-risk allocation, interaction-severity-adaptive risk allocation gives a more principled safety-efficiency tradeoff. It tightens chance constraints when interaction severity is high and relaxes them after the priority vehicle has cleared the conflict zone.

### H3: Behavioural Quality

The adaptive method should reduce unnecessary conservative behaviour. In particular, the ego vehicle should not stop too early when the interaction is not yet severe, and it should accelerate more naturally after the priority vehicle clears the conflict zone.

### H4: Engineering Robustness

The adaptive method should preserve safety and completion while keeping solver failures and infeasible phases no worse than the best existing rule-aware baseline.

## 6. Method Overview

The proposed method has three layers.

### 6.1 Base SMPC Layer

This is the existing multimodal prediction SMPC formulation. It handles:

- vehicle dynamics,
- reference tracking,
- target-vehicle multimodal predictions,
- chance-constrained collision avoidance,
- fixed-risk or variable-risk allocation.

### 6.2 Rule-Aware Give-Way Layer

The existing rule-aware supervisor defines:

- route-level conflict point,
- yield line / stop point,
- priority relationship,
- approach-yield phase,
- hold-yield phase,
- released-recovery phase.

This layer ensures the turning ego vehicle gives way to the oncoming straight-going vehicle when the target is approaching or occupying the conflict zone.

### 6.3 Interaction-Severity-Adaptive Risk Layer

This is one dissertation contribution. The controller computes an interaction severity score:

```text
S(t) in [0, 1]
```

The score is based on:

- ego distance to the conflict zone,
- ego TTC to the conflict zone,
- target TTC to the conflict zone,
- priority state,
- whether the target has cleared the conflict zone,
- whether a temporal overlap risk exists.

The risk profile then maps severity to chance-constraint conservativeness:

```text
target_prob(t) = p_low + S(t) * (p_high - p_low)
tightening(t) = Phi^{-1}(target_prob(t))
```

High severity means stricter constraints. Low severity means relaxed constraints.

## 7. Interaction Severity Definition

The first implementation should use a simple interpretable score:

```text
S(t) = clip(
    w_d * D(t)
  + w_t * T(t)
  + w_p * P(t)
  + w_o * O(t),
  0,
  1
)
```

where:

- `D(t)` is distance severity. It increases as the ego vehicle approaches the conflict zone.
- `T(t)` is TTC severity. It increases when ego and target arrival times are close.
- `P(t)` is priority severity. It is high when the target has priority and has not cleared the conflict zone.
- `O(t)` is overlap severity. It is high when the existing yield logic detects overlap risk or close hold.

Recommended initial weights:

```text
w_d = 0.35
w_t = 0.25
w_p = 0.25
w_o = 0.15
```

Recommended phases:

```text
S < 0.40        low
0.40 <= S < 0.75 medium
S >= 0.75       high
target cleared  cleared
```

The implementation has already passed the logging-only and adaptive-control validation stages. The score should still be reported in the dissertation because it explains why the controller tightens during approach/hold and relaxes after the target clears.

## 8. Adaptive Risk Mapping

The final method uses the risk profile:

```text
risk_profile = adaptive_interaction_severity
```

Implemented probability mapping:

```text
p_low  = upstream_code target probability
p_high = paper_eps_002 target probability
target_prob(t) = p_low + S(t) * (p_high - p_low)
```

This means:

- low severity approximately reproduces upstream SMPC behaviour,
- high severity approaches the stricter paper-style chance constraint,
- target-cleared phase relaxes the constraint again.

The implementation updates risk parameters through the existing SMPC parameter path rather than rebuilding the optimisation problem. The final version also uses a bounded deterministic bypass for traffic-rule phases where solving the SMPC problem is not the meaningful control objective:

- `approach_yield_line` / `hold_yield_line`: deterministic rule-yield control.
- early low-speed `released_recovery`: deterministic recovery handoff after the priority target has cleared.

The recovery handoff is intentionally bounded and should not be expanded without new evidence.

## 9. Baselines

The final dissertation should compare at least:

| Method | Purpose |
|---|---|
| `no_tv` / no target | Proves the ego route and controller can complete the turn without interaction. |
| `smpc_open_loop` | Weak baseline without closed-loop interaction robustness. |
| `smpc_fixed_risk` | Fixed risk allocation baseline. |
| `smpc_var_risk` | Existing variable risk allocation baseline. |
| `rule_aware_smpc_fixed_risk` | Tests the value of the traffic-rule supervisor. |
| `rule_aware_smpc_var_risk` | Current best rule-aware baseline. |
| `rule_aware_smpc_adaptive_risk` | Main proposed dissertation method, represented by `20260627_201840`. |

The existing best tuning should be preserved as the baseline:

```text
yield_reference_decel = -3.75
yield_reference_min_speed = 0.8
yield_stop_buffer_distance = 6.25
yield_brake_distance_margin = 3.5
SMPC_MMPreds.A_MIN = -4.0
RefTrajGenerator.A_MIN:
  smpc_var_risk = -3.0
  smpc_fixed_risk = -4.0
```

Rejected configurations in the changelog should not be repeated unless there is a new reason.

For the next paper-panel run, use the reproducible script:

```bash
cd /root/autodl-tmp/Research-Project-IMLS/core/scripts/carla
source /root/autodl-tmp/load_gurobi11.sh
conda activate carla_modern
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
bash run_give_way_final_dissertation_batch.sh
```

This script runs `notv`, `notv_cl`, `smpc_open_loop`, `smpc_var_risk`, and `smpc_fixed_risk` with `risk_profile=adaptive_interaction_severity`, then runs the post-CARLA trajectory gate. It is intended to generate both the final-method results and the missing open-loop baseline needed by paper-panel postprocessing.

## 10. Ablation Studies

The dissertation should include ablations to show that the adaptive mechanism is meaningful:

| Ablation | Question |
|---|---|
| full adaptive severity | Main method. |
| without priority term | Does traffic-rule priority matter? |
| without TTC term | Does temporal conflict prediction matter? |
| without clearance relaxation | Does relaxing after target clears improve efficiency? |
| distance-only severity | Is distance alone enough? |
| fixed high conservativeness | Is always being strict too conservative? |

These ablations make the contribution stronger than pure parameter tuning.

## 11. Experimental Scenario Matrix

Run the main methods over a controlled matrix:

| Factor | Values |
|---|---|
| target speed | slow / nominal / fast |
| ego initial distance | near / nominal / far |
| prediction uncertainty | low / nominal / high |
| initial time gap | ego arrives early / similar arrival / target arrives early |
| risk profile | fixed / variable / adaptive |

The nominal scenario should remain the current right-hand-traffic give-way scenario. Perturbations should be limited and documented.

## 12. Metrics

The final analysis should report:

### Safety

- footprint collision,
- centre minimum distance,
- footprint minimum separation,
- conflict-zone overlap.

### Rule Compliance

- target clears before ego enters conflict zone,
- ego stops or slows before yield line when target has priority,
- violation rate.

### Efficiency

- completion rate,
- time to complete the turn,
- time from target-cleared to ego recovery,
- waiting time at yield line.

### Comfort

- maximum acceleration,
- maximum deceleration,
- longitudinal jerk,
- lateral acceleration,
- steering-rate behaviour.

### Solver Health

- solver failure fraction,
- consecutive solver failures,
- failure phase distribution,
- solve time.

### Adaptive-Risk Behaviour

- severity score over time,
- target probability over time,
- risk phase over time,
- relation between target-cleared event and risk relaxation.

## 13. Expected Experimental Conclusions

The expected result pattern is:

- Open-loop or rule-free baselines may complete the path but cannot reliably guarantee yield-order correctness.
- Fixed-risk SMPC is safe but may be conservative or slow to recover.
- Ordinary variable-risk SMPC has adaptive optimisation variables but lacks explicit traffic-rule semantics.
- Rule-aware SMPC improves give-way correctness.
- Interaction-severity-adaptive risk allocation makes the behaviour more interpretable and should improve post-clear recovery without losing safety.

The dissertation should not claim universal superiority in every metric. A realistic claim is:

**The proposed method improves rule compliance and behavioural interpretability while maintaining safety and producing a better safety-efficiency tradeoff in the tested give-way scenario.**

## 14. Implementation Roadmap

### Stage 1: Severity Logging

Add interaction severity computation to the existing rule-aware yield evaluation.

Log:

- `severity_score`,
- `severity_phase`,
- `distance_factor`,
- `ttc_factor`,
- `priority_factor`,
- `overlap_factor`,
- `target_cleared_conflict`,
- `ego_ttc_to_conflict`,
- `target_ttc_to_conflict`.

No control behaviour changes in this stage.

### Stage 2: Severity Plotting and Validation

Use existing CARLA debug JSONL logs to plot severity against:

- ego distance to conflict,
- target distance to conflict,
- yield phase,
- target-cleared event,
- solver failures,
- speed profile.

The severity should be high during approach/hold and low after clearance.

### Stage 3: Adaptive Risk Profile

Implemented `adaptive_interaction_severity` as a risk profile. It passes adaptive tightening and target probability into the existing SMPC risk-allocation parameter path.

### Stage 4: CARLA Experiments

Run:

```text
smpc_fixed_risk
smpc_var_risk
smpc_open_loop
rule_aware_smpc_adaptive_risk
```

The immediate experimental improvement is to run the final dissertation batch with `smpc_open_loop` included, so that paper panels and baseline tables can be generated from one comparable run. Then run the ablation matrix.

### Stage 5: Result Tables and Dissertation Figures

Generate:

- trajectory plots,
- conflict-zone timeline,
- severity-over-time plot,
- target probability over time,
- speed/acceleration/jerk plots,
- method comparison table,
- ablation table.

## 15. Dissertation Structure

### Chapter 1: Introduction

- Motivation: unsignalised intersection interaction.
- Problem: autonomous vehicles need both probabilistic safety and traffic-rule compliance.
- Contribution summary.

### Chapter 2: Literature Review

- MPC and SMPC for autonomous driving.
- Chance constraints and risk allocation.
- Multimodal prediction.
- Rule-aware planning and priority handling.

### Chapter 3: Baseline SMPC Framework

- Vehicle model.
- Reference tracking.
- Multimodal target prediction.
- Collision chance constraints.
- Fixed and variable risk allocation.

### Chapter 4: Rule-Aware Give-Way SMPC

- Right-hand-traffic scenario definition.
- Conflict zone and yield line.
- Priority relation.
- Rule-aware state machine.
- Post-yield recovery.

### Chapter 5: Interaction-Severity-Adaptive Risk Allocation

- Severity score definition.
- Distance/TTC/priority/clearance terms.
- Mapping severity to risk threshold.
- Integration with SMPC chance constraints.

### Chapter 6: Experimental Setup

- CARLA setup.
- Scenario configuration.
- Baselines.
- Metrics.
- Parameter settings.

### Chapter 7: Results and Discussion

- Safety and rule compliance.
- Efficiency and recovery.
- Comfort.
- Solver health.
- Ablation study.
- Limitations.

### Chapter 8: Conclusion

- Summary of findings.
- Contributions.
- Future work: UK left-hand traffic transfer, multi-vehicle scenarios, real-time solver improvements.

## 16. Immediate Next Actions

1. Treat `20260627_201840` as the current final-method dissertation candidate.
2. Run `run_give_way_final_dissertation_batch.sh` on the server to regenerate a full comparable run with `smpc_open_loop` included.
3. Pull that run and verify the post-CARLA gate, paper panel, and baseline metrics.
4. Produce result tables comparing final method, open-loop, no-target, fixed-risk, and variable-risk behaviours.
5. Only after the baseline table is stable, consider ablations such as removing priority, TTC, or clearance-relaxation terms.
