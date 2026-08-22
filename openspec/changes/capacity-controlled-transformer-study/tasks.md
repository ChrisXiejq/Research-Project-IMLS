## 1. Freeze the V3 Scientific Protocol

- [x] 1.1 Revise the source-controlled V3 protocol to define the nine thesis-core cells, 27 runs, fixed `1e-4` learning rate, 35/5/5 group split, 80-rollout online matrix, three estimands, metrics, multiplicity, evidence status, and result branches, and verify a schema test rejects any missing or altered field.
- [x] 1.2 Implement a deterministic, non-overlapping group registry for general-test groups 51--60, interaction-challenge groups 61--80, and closed-loop groups 81--90, and verify hashes, geometry bounds, four-cell pairing, unique group counts, and disjointness from groups 1--50.
- [x] 1.3 Freeze response strata and task-specific metric definitions, including the response-onset band, deceleration-onset rule, conflict-zone geometry, entry-time rule, and undefined-case handling, and verify hand-built boundary fixtures are classified exactly as specified.
- [x] 1.4 Implement immutable manifests and completion gates for collection, training, validation selection, calibration, general-test access, challenge-test access, deployment, and formal CARLA execution, and verify incomplete or hash-mismatched prerequisites block every downstream stage.

## 2. Implement Capacity- and History-Controlled Model Families

- [x] 2.1 Implement zero-initialised low-rank final-head adaptation for small and medium B1 tiers while retaining the exact full-head B1 large tier, and verify initial outputs match B0 numerically and gradients are confined to declared trainable weights.
- [x] 2.2 Generalise interaction-sequence construction to emit frozen 0.0-, 0.4-, and 1.0-second horizon masks over the common six-slot tensor while requiring complete six-token eligibility, and verify all horizons preserve identical example IDs, labels, base inputs, and shapes.
- [x] 2.3 Generalise full-distribution MLP and Transformer residual builders for every horizon and capacity tier without changing V2 defaults, and verify zero-residual identity, serialization round trips, full mixture-logit/mean/covariance output contracts, and one-valid-token Transformer masking.
- [x] 2.4 Implement deterministic parameter-count search and a frozen capacity manifest for targets 0.17M, 0.50M, and 1.034208M, and verify every horizon-matched MLP/Transformer pair and every large-versus-B1 count passes the five-percent tolerance before run manifests can be emitted.
- [x] 2.5 Add focused contract tests for trainable-variable ownership, parameter counting, horizon masks, invalid capacity/head configurations, masked-token invariance, deterministic inference, covariance validity, and historical V2 compatibility, and verify the complete model test suite passes.

## 3. Implement Training and Validation Selection

- [x] 3.1 Add a V3 crash-safe trainer supporting family, capacity tier, history horizon, learning rate, seed, data fraction, 80/120-epoch budgets, patience 12, deterministic input order, and semantic resume auditing, and verify smoke training plus incompatible-resume tests pass.
- [x] 3.2 Add manifest-driven orchestration for the nine thesis-core cells at fixed learning rate and three seeds, and verify dry-run output contains exactly 27 unique runs with complete primary contrast coverage and missing-run-only resume.
- [ ] 3.3 Implement groups-36--40 checkpoint validation with rollout-macro NLL and grouped metadata under the fixed learning rate, and verify synthetic fixtures cannot access groups 41--45 and deterministic deployment ties follow the frozen rule.
- [ ] 3.4 Revise the convergence audit to report final-five-epoch boundary limitation without post-outcome budget extension, and verify boundary fixtures remain visible in evidence and do not mutate the 80-epoch protocol.
- [x] 3.5 Implement hash-bound B0 output/penultimate-feature extraction, cached-equivalent B1/MLP/Transformer training, full-model reconstruction and parity auditing, plus deterministic six-GPU disjoint sharding, and verify stale caches, parity drift, duplicate shards, and incompatible resume all hard-fail.

## 4. Implement Calibration and Three-Axis Evaluation

- [x] 4.1 Extend validation-only temperature and covariance-scale calibration to every retained seed, and verify calibration cannot read either fresh-test path and every model/calibration pair is hash-bound.
- [ ] 4.2 Revise the selection-freeze manifest for the globally fixed learning rate, retained seed checkpoints, deployment representatives, convergence/capacity/cache audits, calibration hashes, and source/data provenance, and verify the groups-41--45 evaluator fails before the gate and after any drift.
- [ ] 4.3 Implement the one-pass groups-41--45 retrospective held-out evaluator for every retained seed and trained thesis-core horizon, and verify labels, base inputs, sample membership, rollout grouping, horizon masks, and retrospective-evidence labels match the frozen contracts.
- [x] 4.4 Implement Capacity effects, MLP/Transformer Information effects, horizon dose-response curves, direct matched Architecture effects, and the history-gain difference-in-differences, and verify synthetic known-effect fixtures recover correct signs, pairings, confidence intervals, and multiplicity-adjusted decisions.
- [x] 4.5 Implement target speed-profile RMSE, response-onset timing error, conflict-zone entry-time error, conflict-zone probability mass, and assertive/pre-response/onset/active stratification, and verify analytic trajectory fixtures produce exact expected values and undefined cases remain explicit.
- [x] 4.6 Implement grouped statistical synthesis that macro-averages by rollout, pairs by initialisation, resamples independent groups, and reports seed variability separately and jointly, and verify duplicated windows cannot increase the nominal independent-unit count.
- [x] 4.7 Implement reproducible training-compute and warmed batch-one latency measurement on declared hardware, and verify reports include warm-up count, measured count, hardware/runtime metadata, parameter/FLOP summaries, and Pareto membership.
- [x] 4.8 Preserve zeroed and shuffled frozen-history diagnostics only in an appendix namespace, and verify the main claim generator cannot cite them as primary Capacity, Information, or Architecture evidence.

## 5. Collect and Execute the Offline Study

- [x] 5.1 Derive, review, and freeze group-complete datasets for groups 1--35 fitting, 36--40 selection/calibration, and 41--45 retrospective held-out evaluation, and verify hashes, four-cell completeness, and pairwise disjointness.
- [ ] 5.2 Audit groups 41--45 for independent-group and assertive/pre-response/onset/active support, and verify sparse strata remain explicit and every output is labelled retrospective held-out evidence.
- [x] 5.3 Generate and seal the frozen-backbone cache from the derived split, and verify every sample has matching B0 output, penultimate feature, labels, interaction tensors, sample ID, and source/data/model hashes.
- [ ] 5.4 Execute the 21 endpoint/core runs first and then the six 0.4-second dose-response runs across six disjoint GPU shards, and verify all 27 planned runs have valid completion markers, histories, model/cache/data hashes, parity reports, and parameter reports.
- [ ] 5.5 Run groups-36--40 checkpoint evaluation, convergence audit, per-seed calibration, and selection freeze without opening groups 41--45, and verify an independent no-held-out-access audit passes.
- [ ] 5.6 Run the one-pass groups-41--45 evaluation and complete offline synthesis, and verify Capacity, Information, Architecture, B1 allocation, interaction-metric, seed/group-support, retrospective-label, and completion-hash outputs are present.

## 6. Implement and Execute the Predictor-by-Risk Study

- [x] 6.1 Generalise deployment loading and CARLA prediction logging to validation-selected `P*` from either the MLP or Transformer family while preserving B1 and historical deployment contracts, and verify both candidate-family paths provide offline-online numerical parity plus solver-compatible probabilities, means, and covariances.
- [ ] 6.2 Build and freeze the 80-cell manifest crossing B1/`P*`, fixed-medium/adaptive risk, two target styles, and groups 81--90, and verify exact matrix completeness, the frozen groups-36--40 selection rule, shared nuisance settings, supervisor-on authority, and non-overlap with groups 1--45.
- [x] 6.3 Implement dual-predictor deployment preflight for hashes, shapes, covariance validity, joint-mode mapping, calibration, latency, solver behaviour, and crash-safe resume, and verify any failed check blocks formal collection.
- [ ] 6.4 Execute or deliver server-ready resumable commands for all 80 formal rollouts and audit every cell and log before writing the aggregate completion gate, and verify duplicate, missing, contaminated, or contract-drifted cells prevent completion.
- [ ] 6.5 Implement and run paired model-within-risk contrasts and model-by-risk difference-in-differences for completion, separation, failures, fallback, solver activity, supervisor activity, and in-loop prediction diagnostics, and verify synthetic fixtures recover known interactions and the real report preserves null and adverse outcomes.

## 7. Generate Dissertation Evidence

- [x] 7.1 Implement a provenance-indexed evidence generator with separate Capacity, Information, Architecture, adaptation-allocation, and predictor-risk claim rules, and verify unsupported attention, safety, equivalence, foundation-mismatch, or universal-superiority wording is rejected.
- [ ] 7.2 Generate thesis-ready 1.0-second capacity curves, large-model history-horizon curves, matched large MLP/Transformer tables, history-gain interaction plots, response-stratified mechanism tables, B1 allocation tables, calibration summaries, latency Pareto plots, 80-cell closed-loop tables, and model-by-risk interaction figures, and verify every value resolves to an indexed source field, unit, and evidence-status label.
- [x] 7.3 Generate methods text and planned table/figure placeholders before execution, then gate final numerical prose on offline and closed-loop completion, and verify missing evidence yields explicit placeholders instead of fabricated or stale conclusions.
- [ ] 7.4 After all gates pass, update the dissertation narrative around the three questions—capacity sufficiency, incremental interaction information, and attention-specific extraction—before connecting the validation-selected predictor to risk-moderated closed-loop behaviour, and verify the compiled PDF visually and cross-check every new scalar against the evidence index.

## 8. End-to-End Verification

- [ ] 8.1 Run the complete relevant Python tests and protocol validators, and verify no regression to historical V2, R3, SF4, figure, deployment, or paper-evidence behaviour.
- [x] 8.2 Run dry-run orchestration from empty and partially completed fixtures across six shards, and verify deterministic IDs, no duplicated work, safe resume, exactly 27 runs, disjoint groups, and correct blocking at every scientific gate.
- [x] 8.3 Run `openspec validate capacity-controlled-transformer-study --strict` after the revision and reconcile implementation status with every specification scenario, verifying every checked task has corresponding code, test, or evidence.
