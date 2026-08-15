# SF4 Complete Supervisor Behavioural-Authority Ablation

Status: integrity and implementation/manipulation gates passed for all 80 prespecified rollouts.

The primary DID is `(adaptive-fixed-medium)_on - (adaptive-fixed-medium)_off`.
Its failure-penalised completion-time estimate is 0.020000 s (cluster-bootstrap 95% CI -0.260000 to 0.337500; exact two-sided sign-flip sensitivity value=0.919921875 under a symmetric cluster-effect assumption; this is not randomisation inference).
The 30 s penalty uses the union of native CARLA collision and zero-margin physical bounding-box overlap, the fixed-route-geometry yield outcome, and noncompletion. The stricter 0.25 m-per-actor margin violation and realised-trajectory yield rule are separate diagnostics and never silently redefine the primary endpoint.

Authority-on any-channel/post-action/applied fractions: 0.608280 / 0.225502 / 0.225502. Authority-off any-channel/post-action/applied fractions: 0.639172 / 0.552170 / 0.000000.

Observed first-stage activity status: `active`. Zero activity is retained as a scientific outcome and never triggers rerunning or replacement.
At least one measured behavioural channel was requested; all risk/style-specific request frequencies and intensities remain reported.

## Controller acceptance and raw solver status

Across 18552 factual SMPC attempts, 17822 commands were controller-accepted and 730 used the fallback/nonaccepted path; 0 raw return statuses were unavailable. Effective rule-SMPC-bypass steps are excluded from this denominator. `is_opt` is treated only as controller acceptance (including accepted `SUBOPTIMAL` solutions), never as strict solver optimality or feasibility; raw return statuses are reported separately.

## Server-side computational wall time

Timing status: `pass`. Ego-policy `run_step` wall time is measured with `time.perf_counter` over active-planning invocations, includes risk allocation, solver update/solve and supervisor, and excludes the separately recorded shared prediction pipeline and other-agent policies.
Authority-on/off rollout-mean ego-policy P50: 126.900723 / 119.696601 ms; P95: 315.547676 / 279.305506 ms; P99: 413.329171 / 385.100978 ms. These are server-specific diagnostics, not deployment or real-time guarantees. Paired effects and DID use ego-init clusters, never per-step pseudo-replication.
Authority-on/off rollout-mean shared-prediction P50: 205.019207 / 165.813632 ms; P95: 298.410676 / 330.607246 ms; P99: 343.060064 / 366.822721 ms. The prediction pipeline is common to both authority arms and is reported separately from `policy.run_step`; their sum is not relabelled as a measured end-to-end loop latency.

Nominal conflict clear, actual path release and footprint-buffered clear are distinct clocks. Missing exploratory event clocks remain missing; they are never substituted or imputed.

Collision, controller fallback/non-acceptance, raw solver return status, yield failure and noncompletion remain scientific outcomes. The result concerns the complete application authority of the corrected reduced_intervention rule-aware supervisor inside the frozen B1/estimator/risk/SMPC stack, not the historical full supervisor configuration; prediction, the estimator, adaptive-risk allocation, collision monitoring and SMPC constraints remain present in both arms.
