# Distinction progress tracker

**Plan:** [`DISTINCTION_EXECUTION_PLAN.md`](DISTINCTION_EXECUTION_PLAN.md)  
**Started:** 2026-08-08  
**Current step:** M1 four-hypothesis evidence package complete; W1 manuscript integration is next
**Overall status:** S0–M1 complete; R3 passed at 80/80 and large-scale CARLA collection is permanently closed for this dissertation
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
| R3 | Corrected 80-rollout nominal matrix v2 | complete | Yes | `08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/R3_COMPLETE.json` | 80/80; analysis, stop gate and verified archive pass; no further large-scale CARLA |
| R4 | Calibration factorial | not_run | Yes | frozen scope decision | not required after stack-level estimand was fixed; future work only |
| A2 | Corrected post-R3 synthesis | complete | No | `08_corrected_closed_loop/r3_final/synthesis/A2_COMPLETE.json` | H3 2/8 directional cells; H4 3/12 dominance cells; paper tables/figures hash-bound |
| M0 | Freeze statistical analysis contract | complete | No | `09_analysis_contract/M0_AMENDMENT_COMPLETE.json` | v1 preserved; v2 primary outcomes, censoring, families, margins and study-stop rule frozen before R3 |
| M1 | Four-hypothesis evidence package | complete | No | `10_four_hypothesis_evidence/M1_COMPLETE.json` | 82 records; 0 invalid locator, value mismatch, orphan claim or legacy/corrected pooling violation |
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
| 2026-08-08 | Use event-clock completion and actual-bbox separation as R3 primaries | Target exit is treatment-responsive and cannot define the primary efficiency adjustment; hard-coded vehicle geometry is avoidable | M0 v2/R3 audit v2 |
| 2026-08-08 | Close large-scale CARLA after integrity-valid R3 | H3/H4 direction cannot be used to decide whether to collect more data; all required formal cells and evidence will already exist | M0 v2 study-stop rule |
| 2026-08-08 | Do not run R4 in this dissertation | H3 is explicitly a deployed predictor-stack contrast, not a weight-only causal contrast | scope freeze before R3 outcomes |

## Open blockers and risks

| Risk | Severity | Current treatment | Closure condition |
| --- | --- | --- | --- |
| Formal SMPC repeats top mode spatially | closed for corrected-v1 | R2 consumed distinct modes 0/1/2 in 1,874 valid steps; legacy remains labelled | R3 repeats the hard audit |
| Fixed/adaptive reference A_MIN differs | closed for corrected-v1 | R2 observed only reference/solver pair [−3,−3] | R3 repeats the hard audit |
| Legacy Day11 target–traffic-light collision | bounded historical limitation | raw event retained; R3 captures actor-identified canonical collision episodes and treats target–infrastructure contact as a scenario-context warning plus scientific outcome | R3 taxonomy and separate legacy disclosure; no outcome-dependent rerun |
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
| 2026-08-08 | M0 v2 | Prospectively hardened the R3 outcome contract without overwriting v1 | Completion event clock + actual-bbox separation primary; scientific censoring and four footprint margins frozen | `09_analysis_contract/M0_AMENDMENT_COMPLETE.json` |
| 2026-08-08 | R3 hardening | Completed transactional runner, telemetry, integrity audit, analyzer and final stop/archive gates | 38 local preflight tests; 80 raw receipts and all derived tables will be hash-bound; adverse outcomes cannot trigger extra collection | `docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_prelaunch/R3_HARDENING_ACCEPTANCE.json` |
| 2026-08-08 | R3 raw collection | Completed all prespecified treatment keys despite one CARLA restart | 80/80 accepted receipts; 7 infrastructure failures retained; zero pending or interrupted attempts | Server `r3_corrected_formal_v3/R3_ROLLOUT_*_COMPLETE.json` |
| 2026-08-08 | R3 offline repair | Added a no-CARLA finalizer for the derived-only `actor_geometry` loader incompatibility | Original Git/source manifest and all raw hashes remain frozen; only declared deserialization drift is allowed | `core/scripts/models/finalize_r3_offline.py` |
| 2026-08-08 | R3 finalization | Verified corrected formal data, analysis, stop gate and archive | 80/80 rollouts; all formal tables and integrity gates pass; `additional_large_scale_carla_required=false` | `08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3/R3_COMPLETE.json` |
| 2026-08-08 | A2 | Generated deterministic corrected synthesis, four verdicts, two figures and four tables | B1 manipulation 40/40; H3 2/8; H4 3/12; universal claims rejected without reopening collection | `08_corrected_closed_loop/r3_final/synthesis/A2_COMPLETE.json` |
| 2026-08-08 | M1 | Replaced the old non-resolving evidence index with a four-hypothesis value-audited package | 82/82 records resolve and reproduce; no orphan headline claim or legacy/corrected pooling | `10_four_hypothesis_evidence/M1_COMPLETE.json` |
