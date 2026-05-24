# Preliminary Results and Progress Update

## Current Progress

- I have built a working CARLA intersection reproduction pipeline, including scenario execution, multimodal target-vehicle prediction, SMPC control, video output, and automatic evaluation.
- I have built and run the priliminary single-intersection  case and compared no-target-vehicle baselines, variable-risk SMPC, fixed-risk SMPC, and open-loop SMPC.
- I have added evaluation metrics suitable for later dissertation reporting, including completion time, feasibility, solve time, minimum distance to the target vehicle, lateral tracking error, and comfort-related measures.

## Preliminary Experiment

The current preliminary experiment uses one CARLA intersection scenario with one initial condition. The key purpose is to verify that the  pipeline works and that the main closed-loop SMPC controllers can complete the task before scaling to more initial conditions.

### Task Completion and Solver Reliability

| Policy                     | Description                                                             | Completion time | Steps | Solver feasibility | Outcome           |
| -------------------------- | ----------------------------------------------------------------------- | --------------: | ----: | -----------------: | ----------------- |
| No-TV baseline             | Ego follows the reference route without target-vehicle risk constraints |          5.85 s |   118 |              1.000 | Completed         |
| No-TV closed-loop baseline | Closed-loop baseline without target-vehicle risk constraints            |          5.95 s |   120 |              1.000 | Completed         |
| Variable-risk SMPC         | Risk-aware SMPC with variable risk allocation                           |          7.45 s |   150 |              1.000 | Valid completion  |
| Fixed-risk SMPC            | Risk-aware SMPC with fixed risk allocation                              |          7.65 s |   154 |              1.000 | Valid completion  |
| Open-loop SMPC             | Open-loop SMPC ablation                                                 |         29.95 s |   600 |              0.743 | Need optimisation |

### Safety, Comfort, and Path-Deviation Metrics

| Policy                     | Minimum TV distance | Average solve time | Max lateral acceleration | Average lateral jerk | Path deviation vs No-TV |
| -------------------------- | ------------------: | -----------------: | -----------------------: | -------------------: | ----------------------: |
| No-TV baseline             |                 N/A |            0.045 s |                    13.12 |                12.20 |                    0.00 |
| No-TV closed-loop baseline |                 N/A |            0.045 s |                    13.12 |                14.70 |                    3.57 |
| Variable-risk SMPC         |              4.88 m |            0.127 s |                     6.73 |                 3.42 |                   14.93 |
| Fixed-risk SMPC            |              4.77 m |            0.086 s |                     6.64 |                 3.38 |                   15.90 |
| Open-loop SMPC             |              1.88 m |            0.056 s |                     8.61 |                 0.95 |                    8.62 |

### Completion Diagnostics for Closed-Loop Risk-Aware SMPC

| Policy             | Completion step | Lateral error at completion | Remaining path distance | Distance to CARLA goal | Completion validity |
| ------------------ | --------------: | --------------------------: | ----------------------: | ---------------------: | ------------------- |
| Variable-risk SMPC |             150 |                      3.98 m |                   0.0 m |                 9.73 m | Valid               |
| Fixed-risk SMPC    |             154 |                      3.96 m |                   0.0 m |                10.64 m | Valid               |

## Key Results

- The no-target-vehicle baselines complete the intersection, indicating that the scenario, route, and basic control setup are working.
- The variable-risk and fixed-risk SMPC controllers are now feasible throughout the run and achieve valid completion of the intersection task.
- The minimum distance to the target vehicle is around 4.8 m for the closed-loop risk-aware SMPC controllers, compared with around 1.9 m for the open-loop SMPC ablation, although this safety margin is still expected to be larger.
- The closed-loop risk-aware SMPC controllers reduce maximum lateral acceleration and average lateral jerk compared with the no-target baselines, suggesting smoother manoeuvres during the interaction.
- The path-deviation values for variable-risk and fixed-risk SMPC remain relatively large and need further optimisation.
- However, in general the current  preliminary results show that the closed-loop risk-aware SMPC formulation can improve safety compared with the open-loop ablation.
- I have also enabled CARLA top-down camera recording and saved bird's-eye-view trajectory videos to support visual inspection of the results.

## Current Issues

- The results are still preliminary because they are based on one scenario-initialisation pair only.
- The open-loop SMPC ablation remains unstable: it fails to complete the task and has a lower solver feasibility rate.
- There is still a difference between reaching the end of the reference path and being close to the exact CARLA goal coordinate, so I will continue reporting both path-based completion and goal-distance diagnostics.
- More initial conditions and parameter studies are needed before making final quantitative claims.

## Planned Improvements

- Stabilise and further diagnose the open-loop SMPC ablation, and run a small multi-initialisation pilot experiment before moving to full-scale evaluation.
- Extend the evaluation to more initial conditions and possibly more intersection scenarios.
- Conduct parameter ablation studies on risk threshold, prediction horizon, control time step, and safety distance.
- Explore possible extensions after the reproduction baseline is stable, such as probability calibration of multimodal predictions and uncertainty-aware dynamic risk thresholding.

