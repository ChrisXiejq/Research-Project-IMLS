# Phase-Aware Adaptive Risk SMPC Ablation Design

## 1. Purpose

The frozen main experiment already shows that the final system is safe and stable:

```text
main result:
  core/results/20260710_164024_50init_phase_floor_final_dissertation

code base:
  frozen-main-50init-phase-aware-risk-20260716
  eea6c53f547304af92f697d683f3f12d8af70226
```

The purpose of the ablation study is therefore not to replace the main result. It is to explain why the phase-aware adaptive-risk design is meaningful:

```text
rule-aware supervisor:
  guarantees final right-of-way and footprint safety.

phase-aware adaptive risk:
  changes the SMPC solver-layer chance-constraint conservatism and nominal planning behaviour.
```

The ablation should answer four questions:

1. Is the pre-clearance risk floor necessary?
2. Is post-clearance risk relaxation necessary?
3. Are the floor values and severity mapping robust to reasonable parameter changes?
4. Does the mechanism remain valid under moderate interaction-severity changes?

## 2. Fixed Experimental Protocol

All ablations should keep the following fixed unless the ablation explicitly says otherwise:

| Item | Fixed setting |
| --- | --- |
| Scenario | `scenario_uk_give_way.json` |
| Initial states | `paper_intersection_50/ego_init_*.json` |
| Policies | `smpc_var_risk`, `smpc_fixed_risk` |
| Supervisor | unchanged rule-aware supervisor |
| TV speed | frozen main setting |
| Main code base | `frozen-main-50init-phase-aware-risk-20260716` |
| Postprocess | `postcarla_trajectory_gate.py`, `risk_by_conflict_distance.py`, `compute_scenario_results.py` |

The fixed-risk baseline must remain static. It must not receive adaptive `risk_tightening` or adaptive `target_prob` updates.

Recommended scale:

| Stage | Init count | Purpose |
| --- | ---: | --- |
| quick screen | 5 | catch obvious failures |
| main ablation | 10 | dissertation mechanism evidence |
| confirmation | 20 or 50 | only for final selected variants |

## 3. Primary Ablation Matrix

These variants are the most important. They directly support the thesis argument.

| Variant | Meaning | Required code status | Main expected evidence |
| --- | --- | --- | --- |
| `phase_floor` | final method: pre-clearance floor + post-clearance relaxation | already available | adaptive risk is stricter before clearance and relaxed after clearance |
| `no_phase_floor` | disable pre-clearance floor, keep severity mapping and post-clearance relaxation | already available | critical pre-clearance tightening gap should drop |
| `no_post_clearance_relaxation` | keep pre-clearance floor, but remove post-clearance relaxation | needs new risk profile | post-clearance adaptive risk should no longer be clearly lower than fixed risk |
| `no_phase_awareness` | keep adaptive severity only, but remove both pre-clearance floor and post-clearance relaxation | needs new risk profile | risk schedule becomes less interpretable |
| `static_risk_supervisor_only` | rule-aware supervisor with static risk | partly available through static profile / fixed-risk baseline | isolates the contribution of supervisor-only safety |

Current completed evidence:

| Variant | Critical pre-clearance var-fixed tightening gap | Floor applied fraction | Safety gate |
| --- | ---: | ---: | --- |
| `phase_floor` | `+0.1600` | `1.0000` | PASS |
| `no_phase_floor` | `+0.0603` | `0.0000` | PASS |

Interpretation:

```text
The pre-clearance risk floor is necessary to make the adaptive-risk conservatism explicit and stable in the critical phase.
```

## 4. Parameter Sensitivity Matrix

After the primary ablation, run controlled sensitivity tests. These are not meant to find a new main result. They show that the chosen design is reasonable.

### 4.1 Pre-Clearance Floor Strength

Use the same phase-aware structure but vary the floor strength:

| Variant | Approach floor | Critical floor | Near floor | Purpose |
| --- | ---: | ---: | ---: | --- |
| `floor_weak` | `1.66` | `1.72` | `1.78` | test whether a weak floor is enough |
| `floor_default` | `1.68` | `1.80` | `1.85` | frozen method |
| `floor_strong` | `1.72` | `1.88` | `1.95` | test whether stronger risk becomes too conservative |

Expected result:

```text
weak:
  smaller critical pre-clearance gap; may be less convincing.

default:
  clear critical pre-clearance gap with stable safety.

strong:
  larger gap but may increase solve time, solver failure, or unnecessary conservatism.
```

Recommended conclusion if results match:

```text
The default floor is a balanced setting: strong enough to create a clear critical-phase mechanism, but not so strong that it destabilises the solver.
```

### 4.2 Post-Clearance Relaxation Strength

Vary the relaxed tightening after target clearance:

| Variant | Post-clearance tightening | Equivalent target probability | Purpose |
| --- | ---: | ---: | --- |
| `relax_strong` | `1.2816` | `0.90` | frozen method |
| `relax_mild` | about `1.44` | about `0.925` | test weaker relaxation |
| `no_relax` | `1.64` | about `0.95` | test no post-clearance relaxation |

Expected result:

```text
relax_strong:
  adaptive risk clearly below fixed after clearance.

relax_mild:
  smaller post-clearance difference, but still phase-aware.

no_relax:
  removes the "less conservative after clearance" part of the claim.
```

This ablation supports the second half of the thesis claim:

```text
adaptive risk is not simply "more conservative"; it is phase-aware.
```

### 4.3 Severity Mapping Gain

Vary the mild tightening scale:

| Variant | Mild tightening scale | Purpose |
| --- | ---: | --- |
| `severity_low_gain` | `0.20` | weak severity response |
| `severity_default_gain` | `0.35` | frozen method |
| `severity_high_gain` | `0.50` | stronger severity response |

Expected result:

```text
low gain:
  less nominal planning response before floor is applied.

default gain:
  balanced nominal response.

high gain:
  may improve nominal caution but can increase solve time or feasibility cost.
```

This ablation is useful if the thesis needs to show that adaptive severity mapping contributes beyond a hard-coded floor.

## 5. Interaction-Severity Robustness Matrix

These runs test whether the mechanism remains valid when the interaction is slightly easier or harder.

| Variant | Change | Purpose |
| --- | --- | --- |
| `tv_speed_low` | slower priority target | easier/longer interaction |
| `tv_speed_default` | frozen main setting | main result |
| `tv_speed_high` | faster priority target | shorter clearance window |
| `hard_init_subset` | selected worst-case initial states such as init 17, 19, 31, 37 | stress-test tight cases |

Recommended scale:

```text
TV speed sensitivity:
  10-init first, then 20-init only if useful.

Hard-init subset:
  selected 5-8 initial states.
```

Expected result:

```text
The exact final safety margins may vary, but the phase-aware risk pattern should remain:
  pre-clearance: adaptive tightening > fixed tightening
  post-clearance: adaptive tightening < fixed tightening
```

## 6. Supervisor-Boundary Ablation

This should be handled carefully. The supervisor is not a nuisance variable; it is part of the proposed safe system.

Do not use a "supervisor disabled" run as the main paper comparison unless it is clearly labelled as diagnostic and expected to be unsafe.

Recommended supervisor-boundary evidence:

| Diagnostic | Purpose |
| --- | --- |
| nominal acceleration vs final acceleration | shows solver-layer contribution before supervisor override |
| supervisor override fraction by phase | explains why final control metrics are close |
| final safety gate | shows the combined system remains safe |

Optional diagnostic-only variant:

| Variant | Meaning | Risk |
| --- | --- | --- |
| `reduced_supervisor_diagnostic` | reduce or delay supervisor intervention to expose solver-layer differences | can create unsafe or visually poor runs |

Use this only if the thesis needs an explanatory figure. Do not replace the frozen main result with it.

## 7. Metrics to Report

### 7.1 Safety Gate Metrics

Always report:

- PASS ratio
- footprint collision
- yield-rule satisfaction
- completion
- minimum footprint separation
- minimum centre distance
- solver failure fraction

Acceptance:

```text
Primary ablation variants must PASS safety gates.
Parameter sensitivity variants may be reported as trade-offs if a strong setting increases solver cost, but unsafe variants should not be promoted.
```

### 7.2 Mechanism Metrics

Main paper evidence should focus on:

- `risk_tightening_mean` by bucket and clearance phase
- `var_minus_fixed_risk_tightening_mean`
- `preclearance_floor_applied_frac`
- `raw_tightening_before_floor_mean`
- `nominal_accel_mean`
- `final_accel_mean`
- `supervisor_override_frac`

The most important rows are:

```text
approach / pre_clearance
critical / pre_clearance
critical / post_clearance
near / post_clearance
```

Avoid overclaiming `near / pre_clearance` because the current sample count is small.

### 7.3 Efficiency and Smoothness Metrics

Report as secondary trade-offs:

- average solve time
- feasibility percentage
- completion time
- longitudinal jerk
- lateral jerk

Do not make these the main evidence unless the effect is consistent across 20-init or 50-init.

## 8. Recommended Execution Order

### Stage A: Complete the Primary Mechanism Ablation

Already completed:

```text
phase_floor
no_phase_floor
```

Still useful to add:

```text
no_post_clearance_relaxation
no_phase_awareness
```

Run first with 10 init. If both pass and produce clear mechanism differences, optionally confirm with 20 init.

### Stage B: Parameter Sensitivity

Run only 10 init:

```text
floor_weak
floor_default
floor_strong
relax_mild
no_relax
severity_low_gain
severity_high_gain
```

This stage should answer:

```text
Is the chosen phase-aware mapping reasonable, or did it only work because of one arbitrary value?
```

### Stage C: Robustness

Run a small robustness set:

```text
target-speed sensitivity:
  low / default / high

hard-init subset:
  selected difficult initial states from 50-init result
```

This stage should answer:

```text
Does the phase-aware pattern remain visible when interaction severity changes?
```

### Stage D: Final Confirmation

Pick only the most important final set:

```text
phase_floor
no_phase_floor
no_post_clearance_relaxation
```

Run 20-init or 50-init only if the dissertation needs stronger statistical support. Otherwise 10-init is enough for mechanism ablation because the frozen 50-init main result already establishes system stability.

## 9. Implementation Status

The current code now supports the primary ablation profiles:

```text
adaptive_interaction_severity
adaptive_interaction_severity_no_floor
adaptive_interaction_severity_no_relax
adaptive_interaction_severity_no_phase_awareness
rule_aware_static_risk
```

The adaptive-risk mapping is parameterised through `adaptive_risk_config` and passed from:

```text
run_all_scenarios.py
  -> VehicleParams
  -> SMPCAgent
  -> _adaptive_risk_allocation()
```

Supported override keys include:

```text
variant_name
relaxed_after_clearance_tight
approach_preclearance_floor
critical_preclearance_floor
near_preclearance_floor
mild_tightening_scale
post_clearance_relaxation_enabled
preclearance_floor_enabled
approach_floor
hold_floor
cautious_floor
observe_floor
```

Default values remain exactly equal to the frozen method when no override is provided.

The comprehensive script is:

```text
core/scripts/carla/run_give_way_10init_comprehensive_adaptive_risk_ablation.sh
```

Recommended server commands:

```bash
# Primary four-variant mechanism ablation.
VARIANT_SET=primary INIT_COUNT=10 \
  ./run_give_way_10init_comprehensive_adaptive_risk_ablation.sh

# Parameter sensitivity set.
VARIANT_SET=sensitivity INIT_COUNT=10 \
  ./run_give_way_10init_comprehensive_adaptive_risk_ablation.sh

# Full set, only if enough server time is available.
VARIANT_SET=all INIT_COUNT=10 \
  ./run_give_way_10init_comprehensive_adaptive_risk_ablation.sh
```

Do not change the fixed-risk baseline logic.

## 10. Paper Claim Supported by the Ablation

If the expected results hold, the paper can claim:

```text
The phase-aware adaptive-risk design is not just a tuned static-risk value.
The pre-clearance floor is necessary for explicit critical-phase conservatism,
and the post-clearance relaxation is necessary to avoid remaining conservative
after the priority vehicle has cleared the conflict zone.
```

The claim should remain bounded:

```text
The ablation demonstrates mechanism and interpretability at the solver layer.
It does not claim that adaptive risk alone guarantees final traffic-rule safety;
that guarantee comes from the rule-aware supervisor.
```
