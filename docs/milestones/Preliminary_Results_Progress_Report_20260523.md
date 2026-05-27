# Preliminary Results and Progress Update

## Current Progress

- I have built a working CARLA intersection reproduction pipeline, including scenario execution, multimodal target-vehicle prediction, SMPC control, video output, and automatic evaluation.
- I have now extended the preliminary experiment from a single initial condition to a small multi-initialisation pilot using five ego initial conditions in the same CARLA intersection scenario.
- I have compared no-target-vehicle baselines, variable-risk SMPC, fixed-risk SMPC, and open-loop SMPC, and all 25 rollout executions completed the intersection task.
- I have added evaluation metrics suitable for later dissertation reporting, including completion time, solver feasibility, solve time, minimum distance to the target vehicle, lateral tracking error, path deviation, comfort-related measures, and diagnostic indicators for solver recovery and soft constraint usage.

## Preliminary Experiment

The current preliminary experiment uses one CARLA intersection scenario with five ego initial conditions. The key purpose is to verify that the  pipeline is stable and to identify the remaining issues before scaling to a larger evaluation.

### Task Completion and Solver Reliability

| Policy                     | Description                                                             | Completion time | Steps | Solver feasibility | Outcome                                          |
| -------------------------- | ----------------------------------------------------------------------- | --------------: | ----: | -----------------: | ------------------------------------------------ |
| No-TV baseline             | Ego follows the reference route without target-vehicle risk constraints |          5.84 s |   118 |              1.000 | Completed                                        |
| No-TV closed-loop baseline | Closed-loop baseline without target-vehicle risk constraints            |          6.01 s |   121 |              1.000 | Completed                                        |
| Variable-risk SMPC         | Risk-aware SMPC with variable risk allocation                           |          6.93 s |   140 |              0.982 | Valid completion                                 |
| Fixed-risk SMPC            | Risk-aware SMPC with fixed risk allocation                              |          7.10 s |   143 |              1.000 | Valid completion                                 |
| Open-loop SMPC             | Open-loop SMPC ablation                                                 |          5.41 s |   109 |              1.000 | Valid completion with soft-constraint assistance |

### Safety, Comfort, and Path-Deviation Metrics

| Policy                     | Minimum TV distance | Average solve time | Max lateral acceleration | Average lateral jerk | Path deviation vs No-TV |
| -------------------------- | ------------------: | -----------------: | -----------------------: | -------------------: | ----------------------: |
| No-TV baseline             |                 N/A |            0.053 s |                     9.23 |                 7.73 |                    0.00 |
| No-TV closed-loop baseline |                 N/A |            0.056 s |                     9.16 |                10.31 |                    3.59 |
| Variable-risk SMPC         |              4.06 m |            0.121 s |                     8.08 |                 5.92 |                   12.38 |
| Fixed-risk SMPC            |              4.49 m |            0.086 s |                     5.82 |                 3.32 |                   12.53 |
| Open-loop SMPC             |              4.15 m |            0.048 s |                    11.01 |                13.55 |                    2.54 |

### Completion Diagnostics for Risk-Aware SMPC

| Policy             | Mean completion step | Lateral error at completion | Remaining path distance | Distance to CARLA goal | Completion validity                  |
| ------------------ | -------------------: | --------------------------: | ----------------------: | ---------------------: | ------------------------------------ |
| Variable-risk SMPC |                  140 |                      0.71 m |                   1.4 m |                 9.69 m | Valid in all five initial conditions |
| Fixed-risk SMPC    |                  143 |                      2.31 m |                   1.2 m |                 9.25 m | Valid in all five initial conditions |
| Open-loop SMPC     |                  109 |                      0.01 m |                   6.4 m |                 7.75 m | Valid, but uses collision slack      |

## Key Results

- The no-target-vehicle baselines complete the intersection, indicating that the scenario, route, and basic control setup are working. And the variable-risk and fixed-risk SMPC controllers achieve valid completion across all five initial conditions.
- The fixed-risk SMPC controller currently gives the best balance among the closed-loop risk-aware methods, with full solver feasibility, the largest average minimum distance to the target vehicle, and relatively smooth control behaviour.
- The open-loop SMPC ablation completes the task. However, it uses a softened collision constraint in part of the run, so I treat this result as a diagnostic ablation rather than a final hard-constraint result.
- The minimum distance to the target vehicle is around 4.1-4.5 m for the SMPC policies in this pilot. This is reasonable for a preliminary reproduction, but the safety margin is still expected to improve.
- The closed-loop risk-aware SMPC controllers reduce lateral acceleration and lateral jerk compared with the no-target baselines, suggesting smoother manoeuvres during the interaction.
- I have also enabled CARLA top-down camera recording and saved bird's-eye-view trajectory videos to support visual inspection of the results.

## Current Issues

- The results are still preliminary because they are based on one intersection scenario and five initial conditions, rather than a full-scale evaluation.
- The variable-risk SMPC controller still has occasional solver failures in some initial conditions, although the rollout can recover and complete the task.
- The open-loop SMPC ablation now completes the task, but it relies on collision slack in part of the optimisation.
- The path-deviation values for variable-risk and fixed-risk SMPC remain relatively large and need further optimisation before final quantitative claims.
- There is still a difference between reaching the end of the reference path and being close to the exact CARLA goal coordinate, so I will continue reporting both path-based completion and goal-distance diagnostics.
- More initial conditions and parameter studies are needed before making final quantitative claims.

## Planned Improvements

- Reduce path deviation for the variable-risk and fixed-risk SMPC controllers.
- Further diagnose the occasional variable-risk SMPC solver failures observed in the multi-initialisation pilot.
- Continue monitoring the open-loop SMPC collision slack to distinguish soft-constraint-assisted completion from fully hard-constraint feasibility.
- Extend the evaluation to more initial conditions and possibly more intersection scenarios.
- Conduct more comprehensive ablation studies on risk threshold, prediction horizon, control time step, and safety distance.
- Explore possible extensions after the baseline is stable, such as probability calibration of multimodal predictions and uncertainty-aware dynamic risk thresholding.

