# Integrated dissertation experiment and story audit

**Status:** PASS. The complete story uses five separately gated evidence blocks. Their scalar levels and independent units are not pooled.

## Scenario fixed in the paper

The task is a Town05 unsignalised give-way interaction under right-hand traffic. The ego vehicle turns left across the path of an opposing target that proceeds straight. The ego must yield before the conflict zone and resume after clearance.

## Evidence blocks

1. **F1 foundation adaptation:** B0 versus B1; groups 46--50; 20 rollouts; 315 overlapping windows; 5 paired groups. This establishes B1 as a strong task-adapted reference. The old 0.98%-to-100% number is withdrawn because it was a mode-ranking hit rate, not trajectory accuracy.
2. **F2 broad predictor-risk matrix:** B0/B1 x adaptive/fixed-aggressive/fixed-medium/fixed-conservative x two styles x groups 101--105. B1 is jointly faster and no worse in separation in 2/8 cells; adaptive risk dominates a fixed comparator in 3/12 cells.
3. **F3 supervisor authority:** B1 x adaptive/fixed-medium x authority on/off x two styles x ten groups. Authority produces a large common benefit but does not demonstrate selective masking of the adaptive-minus-fixed contrast.
4. **F4 V3 offline decomposition:** 9 cells x 3 seeds; groups 1--35 fit, 36--40 selection/calibration, 41--45 retrospective held-out. This is the authoritative Capacity, Information and Architecture ablation.
5. **F5 V3 selected-model deployment:** B1/P* x fixed-medium/adaptive x two styles x groups 81--90. This prospectively tests transfer of validation-selected P* and its interaction with risk.

## Integrated H1--H4

- **H1 Capacity:** At 1.0 s history, greater Transformer trainable capacity reduces held-out rollout-macro NLL with a coherent capacity trend.
- **H2 Information:** At matched large capacity, older explicit interaction tokens add predictive information beyond the current interaction state for both encoder families.
- **H3 Architecture:** At matched capacity and information, attention extracts more history value than an MLP, requiring a favourable history-gain interaction in addition to direct model gaps.
- **H4 Closed-loop utility:** Closed-loop utility: (a) validation-selected P* retains its prediction advantage and improves CARLA completion/separation relative to B1; (b) adaptive risk offers a better efficiency-separation operating point than fixed risk in the give-way task.

## Licensed story

The pretrained foundation is substantially misaligned with the bounded give-way distribution, and task-specific adaptation corrects that mismatch. Within the task-trained sequence family, explicit recent interaction history adds a small, saturating gain; capacity is not the persuasive explanation and the direct Transformer advantage is not attention-specific. The validation-frozen best sequence model remains predictively distinguishable in CARLA, but neither it nor adaptive risk is uniformly superior on physical outcomes. Risk, SMPC and the active supervisor compress, reverse or preserve model differences according to the decision context.

## Non-negotiable evidence boundaries

- Do not pool historical groups 46--50, R3 groups 101--105, SF4 groups, V3 groups 41--45, or V3 CARLA groups 81--90 as a single independent sample.
- Use F1 to justify B1 as a strong task-adapted reference, not as a V3 H1 capacity result.
- Use F2 for the broad adaptive-versus-three-fixed frontier and F5 for the prospectively frozen best-model transfer test.
- Use F3 only to test supervisor mechanism; authority-off is not a recommended controller.
- All universal superiority, safety, equivalence and cross-map claims remain prohibited.
