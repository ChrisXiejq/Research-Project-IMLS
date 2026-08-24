# Capacity–Information–Architecture V3: results and claim boundary

## Evidence gates

- Offline training: 27/27 valid runs; maximum cached/full absolute error 0.
- Retrospective held-out evaluation: 27 retained runs over 5 independent groups (41--45).
- Formal CARLA matrix: 80/80 rollout gates passed.
- Convergence: 3 boundary-limited runs; no post-outcome budget extension.

## Claim-safe conclusions

### 1. Capacity

At 1.0 s history, small-to-large Transformer scaling changed rollout-macro NLL by 0.000413 in the preregistered direction, but the tier ordering was non-monotonic and the Holm-adjusted p value was 0.364. The data therefore do not support a strong capacity-limitation explanation.

### 2. Information

Training with 1.0 s rather than current-token-only interaction input improved NLL by 0.004026 for the MLP and 0.003728 for the Transformer. All five paired groups had the preregistered direction, while exact multiplicity-adjusted tests remained underpowered; the 0.4 s condition captured nearly all of the gain.

### 3. Architecture

The matched Transformer reduced NLL relative to the MLP at both 0.0 s (0.007006) and 1.0 s (0.006708). However, its history gain was not larger (difference-in-differences -0.000298, 95% interval -0.001411 to 0.000620), so the evidence supports a bounded encoder-family advantage, not an attention-specific extraction advantage.

### 4. Adaptation Allocation

Large B1 had higher retrospective held-out NLL than the matched full-history Transformer by 0.026988. This compares complete task-adaptation allocations and is not a pure architecture effect.

### 5. Predictor Risk

The model-by-risk interaction was -0.313 s for completion time and 0.027 m for minimum separation; both paired-group intervals crossed zero. P* improved in-loop top-1 ADE under fixed-medium risk by 0.037 m, but this predictive difference did not produce a demonstrated change in the co-primary physical outcomes.

## Evidence boundary

Selection used groups 36--40 only. Groups 41--45 are retrospective held-out evidence and do not constitute a fresh confirmatory test.
The five-group offline exact tests have coarse attainable p values, so interval direction and paired consistency are reported alongside multiplicity-adjusted decisions. Zero observed collisions do not establish equality between configurations or license a broader conclusion outside this matrix.
