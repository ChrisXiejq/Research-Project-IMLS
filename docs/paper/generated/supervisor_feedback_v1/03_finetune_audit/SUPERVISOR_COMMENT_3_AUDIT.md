# Supervisor feedback item 3: fine-tuning audit

**Status:** pass. The old report's 0.98%-to-100% number was the fraction of
prediction windows for which the top-probability mode matched the oracle-best
(minimum-error) mode. It was not a thresholded trajectory-accuracy endpoint.
That headline interpretation is withdrawn and is not evidence for trajectory
quality. It is replaced by a validation-frozen, rollout-disjoint NLL/ADE/FDE
evaluation.

## Frozen test at one aggregation level

At rollout-macro aggregation, B0 has NLL
2.170712, ADE
1.282672 m and FDE 2.644311 m.
B1 has NLL 1.857094, ADE
0.099658 m and FDE 0.120895 m.
All three metrics favour B1 in each of 5/5 held-out init groups.
The smallest attainable two-sided exact sign-flip value with five groups is
0.0625. It is a sensitivity analysis under a symmetric paired-cluster-effect
assumption, not treatment-randomisation inference; overlapping windows are not
counted as independent evidence.

## Why the result is not “100% accuracy”

The old mode-ranking hit rate was fragile to the narrow split, concentration
of the oracle-best mode and overlapping-window aggregation. The corrected
endpoints are continuous displacement and probabilistic forecasting metrics,
not accuracy percentages. Their large aggregate gain is bounded to one Town05
distribution. Only 15/315 full-horizon test windows are
response-active, and the globally fitted B1 calibration worsens NLL in that
small tail despite improving aggregate NLL.

## Physical baselines

The rebuilt physical-baseline tables compare ADE/FDE at the common held-out
init-group aggregation. MultiPath mixture NLL is not subtracted from the
physical baselines' diagonal-Gaussian NLL because they are different
estimands.

## Frozen limitations

- Inference is bounded to the frozen Town05 give-way distribution; there is no cross-map or real-road claim.
- The five held-out ego initialisations, not the 315 overlapping full-horizon windows, are the independent paired units.
- Only 15/315 full-horizon test windows (4.76%) are response-active, so the aggregate result is dominated by non-active interaction periods.
- B1 exposes 1,034,208 trainable parameters; the tested adapter configurations expose substantially fewer, so architecture-only causality is not identified.
- 10/15 training runs selected the final allowed epoch; all three B1 seeds reached that boundary.
- B1 is raster-dominant: raster shuffle changes aggregate ADE by 0.284098 m on average, whereas past-state shuffle changes it by only 0.000080 m.
- The response-active calibration finding is based on 15 windows from six rollouts and three init groups and is therefore a tail diagnostic, not a stable population estimate.
- Physical-baseline NLL is intentionally not contrasted with MultiPath NLL because their probabilistic models define different estimands.
