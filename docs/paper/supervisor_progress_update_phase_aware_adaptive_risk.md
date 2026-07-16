# Phase-Aware Adaptive Risk SMPC: Current Progress

## 1. Problem Formulation

This work studies an unsignalised give-way intersection in a right-hand traffic system using CARLA. The ego vehicle turns left across an oncoming straight-moving priority vehicle, so it must yield, avoid collision, complete the turn, and enter the correct lane.

The main research question is whether an SMPC planner can use interaction-dependent risk allocation to behave more cautiously during safety-critical phases, while avoiding unnecessary conservatism after the priority vehicle has left the conflict zone.

## 2. Method

The current system combines two components:

- a rule-aware supervisor that enforces right-of-way and final safety;
- an SMPC planner that handles multimodal prediction uncertainty with chance constraints.

The main comparison is:

| Policy            | Description                             |
| ----------------- | --------------------------------------- |
| `smpc_fixed_risk` | fixed-risk SMPC baseline                |
| `smpc_var_risk`   | phase-aware adaptive-variable-risk SMPC |

Only `smpc_var_risk` receives adaptive chance-constraint tightening, while the fixed-risk baseline keeps a static risk level.

## 3. Current Result

The latest main experiment shows that:

| Policy            | Solver failure max / mean | Footprint separation min / mean (m) | Collision | Yield OK | Completion |
| ----------------- | ------------------------: | ----------------------------------: | --------- | -------- | ---------- |
| `smpc_fixed_risk` |           0.0244 / 0.0057 |                     0.9596 / 2.1504 | False     | True     | True       |
| `smpc_var_risk`   |           0.0293 / 0.0062 |                     0.8745 / 2.1504 | False     | True     | True       |

Both policies passed all safety gates. The adaptive-risk policy did not introduce collision, yield-rule violation, or task-completion failure, although it has a slightly higher solver cost.

## 4. Phase-Aware Risk Evidence

The adaptive policy applies stronger risk tightening before the target vehicle clears the conflict zone, then relaxes the tightening after clearance.

| Bucket / Phase            | Adaptive tightening | Fixed tightening | Adaptive - Fixed |
| ------------------------- | ------------------: | ---------------: | ---------------: |
| approach / pre-clearance  |              1.6800 |           1.6400 |          +0.0400 |
| critical / pre-clearance  |              1.7997 |           1.6400 |          +0.1597 |
| critical / post-clearance |              1.2816 |           1.6400 |          -0.3584 |
| near / post-clearance     |              1.2816 |           1.6400 |          -0.3584 |

This supports the intended mechanism: the SMPC layer is more conservative before target clearance and less conservative after clearance.

## 5. Ablation Result

An ablation was used to test whether the pre-clearance risk floor is responsible for the stronger adaptive-risk behaviour; when the floor is disabled, the critical pre-clearance tightening gap drops substantially:

| Variant          | Critical pre-clearance var-fixed tightening gap | Floor applied fraction | Safety gate |
| ---------------- | ----------------------------------------------: | ---------------------: | ----------- |
| `phase_floor`    |                                         +0.1600 |                 1.0000 | PASS        |
| `no_phase_floor` |                                         +0.0603 |                 0.0000 | PASS        |

The gap drops from about `+0.160` to `+0.060` without the floor. This suggests that the phase-aware risk floor is the key component that makes the adaptive-risk policy clearly more cautious in the critical pre-clearance phase.

## 6. Next Steps

- Conduct more comprehensive ablation studies on the adaptive-risk design, including the phase floor, risk-tightening levels, post-clearance relaxation, and interaction-severity mapping.
- Further investigate ways to improve the performance of variable-risk SMPC, since the current fixed-risk and variable-risk policies show similar overall safety outcomes. The next goal is to make the adaptive-risk policy provide clearer benefits in safety margin, smoothness, or efficiency while preserving the current safety guarantees.

