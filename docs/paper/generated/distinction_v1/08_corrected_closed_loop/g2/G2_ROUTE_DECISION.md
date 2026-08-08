# G2 closed-loop route decision

## Decision

The project now follows **Route R: corrected prospective core**. This choice is frozen before any R3 outcome is observed and must not change because the eventual result is positive, negative or mixed.

## Why Route R is justified

R2 passed 10/10 rollouts, audited 1,874 valid prediction/control steps, observed no native collision, used all three spatial modes under the corrected mapping, kept fixed/adaptive reference and solver `A_MIN` at −3 m/s², and remained well below the solver runtime gate. The clean post-restart phase completed in about 16 minutes, so 80 rollouts are feasible with ample restart tolerance.

The earlier failed launch is retained in provenance: a persistent CARLA state caused three spawn failures before a full simulator restart. It generated no accepted scientific rollout. All ten accepted rollouts subsequently started on their first attempt.

## Frozen R3 design

R3 uses `B0/B1 × four risk policies × two target styles × five new init groups = 80 rollouts`. Init 101–105 continue the original seeded Uniform sampling stream and were generated and committed before formal outcomes. Execution is block-randomised within init, resumable, and keeps pilot, legacy and corrected result generations separate.

R2 cell values remain deployment diagnostics only. They must not be used to claim B1 superiority or adaptive-risk superiority.
