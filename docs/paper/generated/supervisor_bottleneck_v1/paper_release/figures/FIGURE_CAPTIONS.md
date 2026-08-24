# Final paper figure captions

## Figure 1. Task-specific cross-layer evaluation architecture

The ego turns left across an oncoming priority vehicle in right-hand traffic. MultiPath outputs multimodal predictions, risk allocation parameterises SMPC, and the rule supervisor may alter references, actions or solver bypass before CARLA execution. Measurements are attached to the layer at which they are identified.

## Figure 2. Capacity, information and architecture are experimentally separated

Seed-level and mean retrospective held-out NLL for five independent initialization groups. Capacity is non-monotonic, history provides a small rapidly saturating gain in both families, and the history-gain interaction crosses zero even though the Transformer retains a small direct gap.

## Figure 3. Prediction improvements do not translate uniformly through predictor and risk choices

Panels a–c show V3 cluster-bootstrap intervals across target styles; P* improves in-loop ADE most clearly under fixed risk, whereas completion and clearance intervals overlap. Panel d shows the separate R3 population: adaptive risk occupies the favourable faster-and-larger-separation quadrant in only a subset of predictor, style and fixed-comparator cells. R3 and V3 values are not pooled.

## Figure 4. Rule-supervisor authority is active, behaviourally decisive and floor-saturating

SF4 uses 10 paired initialization groups for each risk policy and target style. Requests remain frequent in both arms, but only authority-on applies action changes or bypass. Authority-on completes 40/40 rollouts with no yield failures or adverse collisions; authority-off completes 0/40, so risk-by-authority interactions are floor-limited. The command-path panels verify a common authority effect but do not identify selective masking of a predictor or risk policy.
