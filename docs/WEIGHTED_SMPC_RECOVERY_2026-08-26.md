# Probability-weighted SMPC recovery plan — 2026-08-26

## Scientific correction

The current controller implements

\[
J_{\mathrm{SMPC}}=J_{\mathrm{shared}}+
\sum_{j\in\mathcal J_{\mathrm{active}}}\pi_{j|t}J_j.
\]

The normalized complete joint MultiPath probabilities weight all post-split
branch tracking, input-rate and heading costs. A single policy before the tree
split has unit weight. Shared slack and route-corridor penalties are counted
once. The same probability vector weights the adaptive-risk budget. Missing,
invalid or partial probability vectors fail closed, and historical unweighted
runtime identifiers are rejected.

Dataset construction, predictor training, held-out Capacity--Information--
Architecture results, B1/P* selection, weights and calibration remain valid.
All V3, R3 and SF4 controller-dependent CARLA outcomes used an earlier
unweighted objective and are historical provenance only; they cannot enter the
final H1--H3 estimates or be pooled with the corrected results.

## Qualification gates

1. Source and unit gate: objective, probability normalization, joint-mode
   ordering, complete-branch invariant, deprecated-ID rejection and telemetry.
2. Numerical solver gate: asymmetric probability swap, uniform probabilities,
   one shared branch, and fixed/adaptive formulations.
3. Proprietary solver gate: the same tests with the production Gurobi plugin,
   followed by a production `SMPC_MMPreds` one-step smoke.
4. Excluded CARLA gate: one non-reactive target case per principal factual
   policy plus a clean rule-absent competence case; no formal initialisation is
   consumed.
5. Formal gate: freeze protocol, assets, initialisations, source hashes,
   objective contract hash, stopping rule and analysis before any successful
   formal outcome.

Gates 1 and 2 pass locally/server-side. Gate 3 is currently blocked because the
server reports no Gurobi licence. Formal CARLA execution must not start until
that environment is restored.

## Formal factual matrix

The paper-grade matrix is prospective and uses untouched initialisation groups
126--135. Camera recording remains off.

### Stage A — non-reactive priority target, 50 unique rollouts

The opposing priority target drives straight at frozen constant speed and does
not react to the ego vehicle.

- Supervisor enabled: `B1/P* × fixed-medium/adaptive × 10 groups = 40`.
- Clean rule absent: `B1 × fixed-medium × 10 groups = 10`.
- The matching enabled H1 arm is reused from the first block, giving a paired
  ten-group clean rule effect without duplicate rollouts.

This is the minimum core that answers all three hypotheses in the teacher's
non-reactive give-way setting. It must be analysed before any robustness block
is combined with the narrative.

### Stage B — reactive-target robustness, 50 additional rollouts

Repeat the same matrix with the frozen reactive target policy. Report this as a
separate context, never as extra independent samples from Stage A. This block
tests whether predictor-history value and supervisor compression persist when
the interaction is richer. The complete release therefore contains 100 unique
factual rollouts.

## Same-state shadow matrix

At four frozen pre-outcome anchors on every supervisor-enabled factual rollout,
evaluate without actuation:

`B1/P* × {fixed-aggressive, fixed-medium, fixed-conservative, adaptive}
× {clean rule enabled, clean rule absent}`.

This gives 16 aligned commands per state. It supplies the full fixed-risk
frontier for H3 and the policy-by-rule attenuation contrast for H2/H3 without
adding physical trajectories. Shadow commands must never update CARLA,
controller history or supervisor state.

## Claim gates

- H1: report nominal collision-free completion and target-first yielding only
  in the tested Town05 populations; do not claim formal safety.
- H2: first verify B1/P* differ in prediction and/or clean-rule-absent nominal
  command. If they do not, report predictor-to-SMPC compression, not supervisor
  masking. Use causal command masking only if the enabled-versus-absent paired
  attenuation contrast supports it.
- H3: compare adaptive with every declared fixed shadow comparator. Physical
  adaptive-versus-fixed-medium similarity alone is insufficient to identify
  masking.
- Never substitute historical unweighted CARLA values into corrected tables,
  figures or prose.

## Expected elapsed time

Historical runtime was approximately 85--116 seconds per factual rollout
without camera. With one GPU, qualification plus 50 core rollouts is expected
to take roughly 2.5--3.5 hours; the full 100-rollout release, shadow overhead,
audit and result materialisation is expected to take roughly 5--6 hours. With
five isolated CARLA/GPU workers, the full workflow is approximately 2--3 hours
including qualification and analysis.
