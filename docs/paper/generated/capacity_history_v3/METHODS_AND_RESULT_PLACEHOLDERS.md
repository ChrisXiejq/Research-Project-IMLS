# Capacity–Information–Architecture V3

## Methods text

The V3 study separates three questions. Capacity is tested by changing trainable parameter count within each family; Information is tested by training identical-capacity models on fixed 0.0, 0.4, and 1.0 s masks over the same complete six-token examples; Architecture is tested by matched MLP/Transformer contrasts and a difference-in-differences of their history gains. Matched runs use AdamW with weight decay 1e-5, gradient-norm clipping at 10, deterministic data order, and encoder dropout 0.1. Learning rates and checkpoints are selected on validation rollout-macro NLL with patience 12; the 80-to-120-epoch common-extension gate covers both core and matched data-fraction comparisons. Formal completion requires disjoint group splits, complete group/cell support, unique sample keys, finite inputs/losses/weights, and live source/data/model hashes; debug-limited runs are smoke-only. Fresh groups are opened once after convergence, capacity, calibration, and latency gates pass. The final CARLA study crosses B1 and P* with four risk policies, two target styles, and ten paired held-out groups.

## Planned result artefacts

| Artefact | Axis | Rows/x | Columns/y | Status |
| --- | --- | --- | --- | --- |
| capacity_curves | Capacity | trainable parameters | rollout-macro NLL | RESULT PENDING |
| history_horizon_curves | Information | trained horizon (s) | rollout-macro NLL | RESULT PENDING |
| matched_architecture_table | Architecture | matched capacity/horizon | MLP vs Transformer | RESULT PENDING |
| history_gain_interaction | Architecture | encoder family | full-minus-snapshot gain | RESULT PENDING |
| response_stratified_mechanisms | Information | response stratum | task metrics | RESULT PENDING |
| b1_allocation_table | Adaptation allocation | capacity tier | B1 performance | RESULT PENDING |
| data_efficiency_curves | Adaptation allocation | rollout-group fraction | NLL | RESULT PENDING |
| calibration_summary | Calibration | model cell | temperature/covariance scale | RESULT PENDING |
| latency_pareto | Deployment | warmed batch-one latency (ms) | NLL | RESULT PENDING |
| closed_loop_cells | Predictor-risk | 160 frozen cells | outcomes | RESULT PENDING |
| model_by_risk_interaction | Predictor-risk | risk policy | P* minus B1 | RESULT PENDING |
