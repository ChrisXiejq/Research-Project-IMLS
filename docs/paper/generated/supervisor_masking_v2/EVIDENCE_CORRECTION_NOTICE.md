# Evidence correction notice — 2026-08-26

## Probability-weighted SMPC objective correction

The current controller uses the source-consistent expected branch objective

\[
J_{\mathrm{SMPC}}=J_{\mathrm{shared}}+\sum_{j\in\mathcal J_{\mathrm{active}}}\pi_jJ_j,
\]

where the normalized joint MultiPath probabilities \(\pi_j\) weight the
post-split branch tracking and control costs.  Before the policy tree splits,
the single shared branch has unit weight.  The same normalized probability
vector enters the adaptive-risk budget.  There is no runnable unweighted
objective option, and the controller fails closed if probabilities are absent,
invalid or do not cover the complete active joint-mode set.

All historical V3, R3, SF4 and other CARLA results generated with
`corrected_joint_modes_shared_amin_v1` or
`legacy_single_tv_mode0_split_amin_v0` predate this correction.  They remain
immutable provenance and may motivate the audit, but they are not admissible
as final H1--H3 closed-loop evidence and must not be pooled with weighted-V2
results.  Dataset construction, all offline Capacity--Information--Architecture
training/evaluation, predictor selection, weights and calibration remain valid
because they do not depend on the controller objective.

Required replacement: a prospectively frozen weighted-V2 protocol, excluded
qualification runs, and new closed-loop receipts whose telemetry identifies
`multipath_joint_probability_expected_cost_v2`.

## Clean supervisor-off correction

The generated H1 release in this directory is preliminary diagnostic material.

The historical SF4 `monitor_only` arm disabled a bundled seven-channel authority layer and completed 0/40 rollouts. It is not a clean “paper-equivalent SMPC with only the give-way rule removed” baseline. Therefore the existing H1 gate, verdict table, captions and H1 figure must not be used to claim that supervisor-off SMPC cannot reach the destination or that 40/40 versus 0/40 identifies the causal effect of the give-way rule.

Allowed use before replacement: the full authority bundle was physically and command-level consequential in the tested implementation. Required replacement: a prospective clean off baseline that preserves SMPC, route tracking and completion while toggling only give-way rule application.

See `docs/HANDOFF_2026-08-25_SUPERVISOR_MASKING.md`.
