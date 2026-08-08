# Distinction progress tracker

**Plan:** [`DISTINCTION_EXECUTION_PLAN.md`](DISTINCTION_EXECUTION_PLAN.md)  
**Started:** 2026-08-08  
**Current step:** R3 in progress — code frozen and awaiting user-launched corrected 80-rollout matrix
**Overall status:** S0–G2, R1–R2 and M0 complete; R3 server execution is next
**Closed-loop route:** Route R frozen prospectively at G2

## Status legend

- `pending`: 尚未开始；
- `in_progress`: 当前唯一主步骤；
- `blocked`: 已记录具体 blocker，等待外部输入；
- `complete`: acceptance gate 已有证据通过；
- `not_run`: 经冻结决策明确不执行；
- `superseded`: 被 corrected evidence 替代，但历史资产保留。

## Master tracker

| ID | Task | Status | Requires server | Acceptance evidence | Decision/notes |
| --- | --- | --- | --- | --- | --- |
| S0 | Remediation baseline and provenance | complete | No | `00_baseline/S0_COMPLETE.json` | HEAD `74179a1`; 4 backups re-hashed; no commit made |
| S1 | Regression tests for known defects | complete | No | `00_regression_gates/S1_COMPLETE.json` | 4 tests PASS; C1/C2/C7 deliberately remain detected, not hidden |
| E1 | CV/CA/train-mean physical baselines | complete | No | `01_physical_baselines/E1_COMPLETE.json` | B1 beats all three on ADE/FDE in 5/5 test inits |
| E2 | B1 raster/past input diagnostics | complete | GPU | `02_input_ablations/E2_COMPLETE.json` | 3 shuffle seeds; raster strong, past negligible aggregate sensitivity |
| E3 | Training-budget/model-fairness audit | complete | GPU asset pull | `03_training_budget/E3_COMPLETE.json` | all 15 histories; not parameter matched; 10/15 at epoch ceiling |
| E4 | Formal in-loop prediction analysis | complete | No; uses backups | `04_in_loop_prediction/E4_COMPLETE.json` | 160 rollouts, 10,235 full windows; active-tail failure exposed |
| E5 | Collision/geometry/metric audit | complete | No | `05_collision_and_geometry/E5_COMPLETE.json` | taxonomy + margin/init50 sensitivity; fixed-zone raw replay remains G2 boundary |
| E6 | Split/covariate-balance audit | complete | No | `06_split_balance/E6_COMPLETE.json` | disjoint init split; max descriptive SMD 0.208 |
| G1 | Freeze final ML contribution | complete | No | `07_ml_claim_gate/G1_ML_CONTRIBUTION_FROZEN.json` | final ML thesis and prohibited wording frozen |
| R1 | Correct mode/A_MIN implementation | complete | No initially | `08_corrected_closed_loop/r1/R1_COMPLETE.json` | 10 tests PASS; corrected-v1 default; legacy explicit only |
| R2 | Corrected 10-rollout pilot | complete | Yes | `08_corrected_closed_loop/r2/local_verification/r2_corrected_pilot_v4/R2_LOCAL_VERIFICATION.json` | 10/10 pass; non-statistical deployment gate only |
| G2 | Freeze Route S or Route R | complete | No | `08_corrected_closed_loop/g2/G2_COMPLETE.json` | Route R frozen before R3 outcomes |
| R3 | Corrected 80-rollout nominal matrix | in_progress | Yes | 80-arm audit | code/contract/init generation ready; user launch pending |
| R4 | Calibration factorial | pending | Yes | matched factorial audit | optional, lowest experiment priority |
| M0 | Freeze statistical analysis contract | complete | No | `09_analysis_contract/M0_COMPLETE.json` | H3/H4 directions, outcomes, families and dominance rule frozen before R3 |
| M1 | Four-hypothesis evidence package | pending | No | 0 locator/value mismatch | replaces old H1–H8 |
| W1 | Full TMLR manuscript | pending | No | complete source/PDF | 0 TODO |
| Q1 | Final scientific/rubric/PDF audit | pending | No | all gates PASS | no claim patching by hand |
| V1 | Viva and submission package | pending | No | archive + viva documents | final deliverable |

## Immutable decisions

| Date | Decision | Rationale | Evidence |
| --- | --- | --- | --- |
| 2026-08-08 | Use four headline hypotheses only | Keep thesis focused; diagnostics remain secondary | distinction readiness audit |
| 2026-08-08 | Do not treat B1 vs T1/T2 as capacity-matched | Trainable parameters and adaptation locus differ | code/model audit |
| 2026-08-08 | Do not call three fixed settings a complete frontier | Only three operating points tested | literature/method audit |
| 2026-08-08 | Do not interpret 14/14 artifact checks as value audit | Locators were not resolved/recomputed | evidence audit |
| 2026-08-08 | Do not start a larger Transformer | Does not close current validity gaps | critical-path decision |
| 2026-08-08 | Describe B1 as raster-dominant, not effective target-history modelling | Three cross-init raster shuffles increase ADE by 0.270–0.293 m; past shuffles change ADE by about 0.00008 m on average | E2 |
| 2026-08-08 | Keep aggregate B1 gain but explicitly reject universal tail transfer | At -3 m response-active windows, B1-minus-B0 ADE is +1.03 m | E4 |
| 2026-08-08 | Reject universal adaptive-policy superiority | Excluding collision-affected init50 flips several small adaptive-minus-fixed effects | E5 |
| 2026-08-08 | Select Route R before formal corrected outcomes | R2 passed all deployment/numerical/runtime gates and the 80-run cost is feasible | G2 |
| 2026-08-08 | Use five newly generated R3 init groups 101–105 | Continue the original seeded in-distribution sampling stream without reusing opened test init46–50 | R3 init manifest |
| 2026-08-08 | Retain adverse formal outcomes | Collision, yield and completion failures are scientific outcomes, not retry/exclusion triggers | M0/R3 contract |

## Open blockers and risks

| Risk | Severity | Current treatment | Closure condition |
| --- | --- | --- | --- |
| Formal SMPC repeats top mode spatially | closed for corrected-v1 | R2 consumed distinct modes 0/1/2 in 1,874 valid steps; legacy remains labelled | R3 repeats the hard audit |
| Fixed/adaptive reference A_MIN differs | closed for corrected-v1 | R2 observed only reference/solver pair [−3,−3] | R3 repeats the hard audit |
| Day11 target–traffic-light collision | critical | raw event confirmed | full taxonomy + cluster sensitivity/rerun |
| 42/66 JSON locators invalid | critical | old 14/14 claim superseded | M1 value-resolving audit |
| Missing physical baselines | closed | E1 complete | B1 wins 5/5 init against CV/CA/train-mean |
| B1/T fairness | controlled limitation | E3 complete; claim narrowed | report full-configuration comparison, not architecture causality |
| Only five independent test inits | high | exact/descriptive inference | transparent statistics; no fake n |
| Manuscript has TODOs and 3 references | critical | W1 planned | 0 TODO + 25–35 checked sources |

## Execution log

每完成一次有意义的动作，在此追加一行；不删除历史。

| Timestamp | Step | Action | Result | Git SHA / artifact |
| --- | --- | --- | --- | --- |
| 2026-08-08 | Audit | Completed distinction-level adversarial review | Nine critical remediation areas and two closed-loop routes defined | `DISTINCTION_READINESS_AUDIT_2026-08-08.md` |
| 2026-08-08 | Plan | Created execution plan and tracker | S0 set as sole next step | `DISTINCTION_EXECUTION_PLAN.md` |
| 2026-08-08 | S0 | Froze repository and offsite evidence provenance | 4/4 archives hashed; dirty files snapshotted | `00_baseline/legacy_evidence_v1.json` |
| 2026-08-08 | S1 | Added regression/audit gates and fixed chained length comparison | 4 unit tests PASS; C1/C2/C7 reproduced | `00_regression_gates/S1_regression_gate_audit.json` |
| 2026-08-08 | E1 | Evaluated CV, clipped CA and train-mean baselines | B1 lower ADE/FDE for every baseline in 5/5 init groups | `01_physical_baselines/physical_baseline_init_direction_audit.json` |
| 2026-08-08 | E2 | Ran B1 raster/past diagnostics on RTX 4090 | Raster shuffle +0.284 m mean ADE; past shuffle +0.00008 m | `02_input_ablations/b1_base_input_diagnostics.json` |
| 2026-08-08 | E3 | Audited all 15 training histories and parameter counts | 10/15 boundary-selected; parameter ratios 0.075–0.170 vs B1 | `03_training_budget/model_capacity_training_budget_audit.json` |
| 2026-08-08 | E4 | Recomputed exact in-loop prediction metrics | Aggregate B1 gains; -3 m active-tail ADE and calibration failure | `04_in_loop_prediction/formal_inloop_prediction_analysis.json` |
| 2026-08-08 | E5 | Attributed collisions and ran sensitivity checks | 0 ego-target collisions; 2 target-light episodes; policy effects fragile | `05_collision_and_geometry/formal_safety_metric_sensitivity_audit.json` |
| 2026-08-08 | E6 | Reconstructed split and covariate balance | 200 rollouts, disjoint inits, no duplicate keys | `06_split_balance/split_balance_audit.json` |
| 2026-08-08 | G1 | Froze final ML contribution | ML-C1 supported; ML-C2 unsupported; ML-C3 refuted in tail | `07_ml_claim_gate/G1_ML_CONTRIBUTION_FROZEN.json` |
| 2026-08-08 | R1 | Corrected joint-mode indexing and unified A_MIN contract | 10 tests PASS; one-TV map `[0,1,2]`; fixed/adaptive solver/reference A_MIN −3 m/s² | `08_corrected_closed_loop/r1/R1_COMPLETE.json` |
| 2026-08-08 | R2 | Pulled, hashed and locally re-audited corrected pilot | 10/10 pass; 0 native collisions; 1,874 valid steps; max P95 solve 0.1038 s | `08_corrected_closed_loop/r2/local_verification/r2_corrected_pilot_v4/R2_LOCAL_VERIFICATION.json` |
| 2026-08-08 | G2 | Froze corrected prospective Route R | Decision is independent of future R3 outcome direction | `08_corrected_closed_loop/g2/G2_COMPLETE.json` |
| 2026-08-08 | M0 | Froze R3 estimands, outcomes, inference and dominance rules | Five init clusters; exact sign-flip and Holm families declared | `09_analysis_contract/M0_COMPLETE.json` |
| 2026-08-08 | R3 | Prepared resumable block-randomised corrected matrix | 80 unique keys on five new in-distribution init groups; user server launch pending | `core/scripts/carla/run_r3_corrected_formal_matrix.sh` |
