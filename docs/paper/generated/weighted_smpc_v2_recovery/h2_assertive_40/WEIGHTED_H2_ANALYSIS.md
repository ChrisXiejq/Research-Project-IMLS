# Probability-weighted H2 assertive-only analysis

## Integrity

- Formal matrix: 40/40 completed; four cells, ten paired initialization groups per cell.
- Target behaviour: assertive constant speed; supervisor authority: on; CARLA map: Town05.
- Weighted objective: 5,890 audited solver rows; no contract mismatch.
- Physical outcomes: 40/40 completion, 40/40 give-way compliance, 0 footprint collisions.
- Solver non-success: 83/5,890 rows; 78 occur before a valid prediction during observed-target caution and 5 during clear-path release. Every such step receives the declared fallback and supervisor action replacement.

## Primary paired effects

- Fixed medium: completion +0.0000 s (95% paired bootstrap [-0.0200, +0.0250]); separation +0.0257 m ([-0.0021, +0.0552]).
- Adaptive: completion -0.0050 s (95% paired bootstrap [-0.0200, +0.0100]); separation +0.0092 m ([-0.0017, +0.0206]).
- Adaptive risk with Retrained MultiPath: completion +0.0200 s ([-0.0150, +0.0650]); separation -0.0068 m ([-0.0321, +0.0125]).
- Adaptive risk with Transformer-adapted MultiPath: completion +0.0150 s ([-0.0150, +0.0500]); separation -0.0233 m ([-0.0457, -0.0022]).

## Interpretation boundary

The deployed predictors produce different mode probabilities and trajectory means, and those probabilities exactly equal the audited SMPC branch-cost weights. The treatment therefore reaches the corrected controller. The physical contrasts remain small and most paired intervals cross zero. These data support transmission of the predictor intervention into the optimiser, but not a consistent completion-time or separation benefit. Mode entropy is a deployment manipulation check, not an in-loop accuracy score.

## Provenance

- Protocol core SHA256: `309853ede3b0169b34893817a6c497d116f1d928c8924010df4a45747b874ade`
- FORMAL_COMPLETE SHA256: `3ac397930489e5afb24b24e9090d03d3e198eba7c97f431d132fabca0454fe3f`
- Server integrity SHA256: `264c6343d45888ba86e924099f52f980a6181af07d2b0e6d49dcc791f54667b3`
