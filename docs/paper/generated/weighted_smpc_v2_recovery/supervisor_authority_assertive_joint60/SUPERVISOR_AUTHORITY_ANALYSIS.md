# Probability-weighted supervisor-authority analysis

## Protocol and units

- 60 unique formal rollouts: 40 authority-on and 20 authority-off.
- The authority contrast uses five paired initialisation groups (126--130) across two predictors and two risk policies.
- Initialisation groups, not control steps or factorial cells, are the independent resampling units.
- Every rollout uses Town05, an assertive target and the same probability-weighted SMPC objective contract.

## Main authority result

- The endpoint completion criterion is reached in 20/20 rollouts with authority on and 20/20 with authority off.
- The stricter competence gate passes 20/20 versus 8/20.
- Explicit fixed-geometry early entry occurs in 0/20 versus 12/20.
- Footprint collision occurs in 0/20 versus 4/20.
- Mean raw completion is 8.8025 s versus 7.1700 s. The faster off-arm value is not an efficiency gain because 12/20 rollouts enter before target clearance.
- Mean solver-failure fraction falls from 0.1075 to 0.0087; paired group effect -0.0988 (95% cluster bootstrap [-0.1393, -0.0583]).
- Mean maximum absolute lateral route error falls from 5.460 m (range 4.661--6.065) to 1.438 m (range 1.174--1.769).

## Mechanism

- Authority-on applies post-solver action replacement on 26.1% of control steps and SMPC bypass on 17.3%.
- Authority-off logs shadow requests on 90.3% of steps, including action requests on 84.4%, but applies none by construction.
- Solver acceptance is 98.9% with authority on and 89.4% with authority off.

## Moderation and failure pattern

- Predictor and risk changes do not alter any binary off-arm outcome within an initialisation group: True.
- Initialisations 126 and 128 have the highest initial speeds (9.83 and 9.71 m/s) and show early entry in all four predictor-risk cells without collision.
- Initialisation 127 starts approximately 2.0 m further forward and produces early entry plus footprint collision in all four cells.
- Initialisations 129 and 130 combine moderate speeds with approximately -1.9 m offsets; neither shows early entry or collision, and all four cells pass the competence gate.
- Fixed-geometry outcomes: {'ego_entered_before_target_clearance': 12, 'ego_never_entered_conflict_zone': 8}.
- This initial-condition pattern is post hoc and descriptive because only five independent groups were run with authority off.

## Interpretation boundary

The experiment disables the complete behavioural-authority bundle. It identifies the bundle's causal effect under these five paired initialisations, not the effect of any individual supervisor rule. The off arm still reaches the endpoint completion criterion in every rollout, so the supported claim is improved conflict handling, route retention and solver stability, not that driving is impossible without the supervisor.
