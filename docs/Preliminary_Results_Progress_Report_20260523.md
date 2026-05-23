# Preliminary Results and Progress Report

## Project Goal

Reproduce the CARLA intersection experiment from *Predictive Control for Autonomous Driving with Uncertain Multimodal Predictions*, focusing on multimodal prediction-aware stochastic MPC (SMPC) and its comparison against no-target-vehicle baselines.

## Current Experimental Setup

| Item | Current Setting |
|---|---|
| Simulator | CARLA 0.9.14, Town05 intersection |
| Scenario | `scenario_01.json` with `ego_init_01.json` |
| Solver | CasADi conic optimisation with Gurobi |
| Risk profile | `upstream_code` reproduction setting |
| Output | Trajectory logs, solver/debug files, and CARLA RGB videos (`carla_sim.avi`) |
| Best result directory | `core/results/20260523_155612` |

## Preliminary Closed-Loop Results

| Policy | Meaning | Ego Steps | Feasible Fraction | Outcome |
|---|---|---:|---:|---|
| `notv` | No target vehicle baseline | 118 | 1.000 | Completed |
| `notv_cl` | No target vehicle closed-loop baseline | 120 | 1.000 | Completed |
| `smpc_var_risk` | SMPC with variable risk allocation | 121 | 1.000 | Near-goal completion |
| `smpc_fixed_risk` | SMPC with fixed risk allocation | 123 | 1.000 | Near-goal completion |
| `smpc_open_loop` | Open-loop SMPC ablation | 600 | 0.907 | Did not complete |

## Completion Diagnostics for Risk-Aware SMPC

| Policy | Completion Step | Distance to Goal | Lateral Error `ey` | Remaining Path `s_to_end` | Completion Trigger |
|---|---:|---:|---:|---:|---|
| `smpc_var_risk` | 121 | 7.88 m | 5.71 m | 5.0 m | Goal-distance threshold |
| `smpc_fixed_risk` | 123 | 7.79 m | 5.82 m | 4.0 m | Goal-distance threshold |

## Key Progress

- The full CARLA intersection pipeline is now operational, including simulation, prediction, SMPC control, logging, debugging, and video output.
- The no-target-vehicle baselines complete the route reliably, confirming that the scenario, reference path, and basic control pipeline are working.
- The closed-loop risk-aware SMPC policies are now solver-feasible throughout the run (`feasible fraction = 1.0`).
- A previous failure mode where risk-aware SMPC drifted far off-route for 600 steps has been substantially improved: the latest variable/fixed-risk SMPC runs now reach within 8 m of the goal in around 121-123 steps.
- Instrumentation has been added to diagnose solver status, lateral deviation, reference regeneration, completion metrics, and first-failure context.

## Current Limitations and Next Steps

- The latest `smpc_var_risk` and `smpc_fixed_risk` results are strong preliminary results, but not final reproduction results: completion is triggered by goal distance, while lateral error remains around 5.7-5.8 m.
- The `smpc_open_loop` ablation remains unstable, with an early `INF_OR_UNBD` solver failure and no successful completion.
- Next work will tighten the completion criterion, improve lateral/reference tracking after avoidance manoeuvres, and then extend evaluation beyond the current single scenario-initialisation pair.

## Summary

At this stage, I have obtained preliminary closed-loop results showing that the reproduced intersection pipeline works, baseline controllers complete the scenario, and closed-loop risk-aware SMPC is now feasible and reaches near the goal. The remaining challenge is to reduce lateral deviation and stabilise the open-loop ablation before running larger-scale quantitative evaluation.
