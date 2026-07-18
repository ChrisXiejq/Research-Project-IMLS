# Fine-Tuned MultiPath Predictor: 10-Init Closed-Loop Validation

## Experiment Node

- Closed-loop validation result:
  `core/results/20260718_100757_10init_finetuned_predictor_validation`
- Prediction model:
  `core/scripts/models/l5kit_multipath_10_carla_finetuned_head_best`
- Scenario:
  unsignalised give-way intersection, 10 initial conditions
- Policies:
  `smpc_fixed_risk`, `smpc_var_risk`

This experiment changes only the prediction model. The SMPC risk profile remains
`adaptive_interaction_severity`.

## Prediction-Side Result

Same-test-set SavedModel evaluation shows that CARLA-domain head fine-tuning
substantially improves top-probability trajectory quality:

| Model | Top-1 ADE (m) | minADE (m) | Top-1 FDE (m) | minFDE (m) | Top-prob mode is best |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pretrained MultiPath | 4.0337 | 0.2215 | 7.5259 | 0.4102 | 0.98% |
| Fine-tuned head | 0.0271 | 0.0271 | 0.0366 | 0.0366 | 100.00% |

Interpretation: the pretrained model already contains a near-correct mode
(`minADE = 0.2215 m`), but often assigns the highest probability to a wrong
mode. The fine-tuned head mainly improves CARLA-domain mode ranking and
probability calibration.

## Closed-Loop Safety Result

| Policy | PASS | Solver failure max / mean | Footprint separation min / mean (m) | Collision | Yield OK |
| --- | ---: | ---: | ---: | --- | --- |
| `smpc_fixed_risk` | 10/10 | 0.0244 / 0.0064 | 1.3628 / 2.1445 | False | True |
| `smpc_var_risk` | 10/10 | 0.0244 / 0.0064 | 1.3127 / 2.1536 | False | True |

The fine-tuned predictor does not break the closed-loop safety gates. Both
policies complete all 10 initial conditions with no footprint collision and no
yield-rule violation.

## Phase-Aware Risk Behaviour

The adaptive-risk mechanism remains active with the fine-tuned predictor:

| Bucket / Phase | Adaptive tightening | Fixed tightening | Adaptive - Fixed | Floor applied |
| --- | ---: | ---: | ---: | ---: |
| approach / pre-clearance | 1.6800 | 1.6400 | +0.0400 | 1.0000 |
| critical / pre-clearance | 1.8000 | 1.6400 | +0.1600 | 1.0000 |
| near / pre-clearance | 1.8500 | 1.6400 | +0.2100 | 1.0000 |
| critical / post-clearance | 1.2816 | 1.6400 | -0.3584 | 0.0000 |
| near / post-clearance | 1.2816 | 1.6400 | -0.3584 | 0.0000 |

This confirms that the phase-aware risk schedule still behaves as intended:
more conservative before target clearance and more relaxed after clearance.

## Paper Use

This result can be used as a model-side extension rather than replacing the
frozen 50-init main SMPC result. The safest claim is:

> CARLA-domain fine-tuning improves MultiPath mode ranking and probability
> calibration, and a 10-init closed-loop validation shows that the fine-tuned
> predictor remains compatible with the phase-aware adaptive-risk SMPC pipeline.

It should not yet be claimed as a new 50-init main result unless a larger
closed-loop validation is also run.
