# 2026-08-25 supervisor-masking experiment and thesis handoff

This is the authoritative restart document for the next Codex task/device. Read it before changing code, running CARLA, or rewriting the thesis. Earlier handoffs remain useful for historical details but do not override the scientific corrections below.

## 1. Current objective

Reframe the dissertation around a rule-based supervisor that can enforce nominal give-way behaviour but can also reduce the decision sensitivity of the predictor--risk--controller stack. The intended paper is no longer primarily a MultiPath tuning paper. It must explain both sides of the stack:

- prediction: what MultiPath predicts, how task adaptation/history/capacity/architecture were tested, and what improved offline;
- control: how multimodal SMPC consumes prediction modes, probabilities and covariances, how risk allocation tightens constraints, and how the implemented rule-based supervisor can alter the optimiser inputs and the executed command.

Safe working title before new causal evidence:

> Rule-Based Supervision Secures Nominal Give-Way Behaviour but Limits Cross-Layer Decision Sensitivity

Do not use “masks” as an identified causal result until the same-state command-transmission experiment passes its integrity gates and supports that verdict.

## 2. Critical scientific correction from the author

The historical SF4 `monitor_only` arm completed 0/40 rollouts, while authority enabled completed 40/40. This is **not** an acceptable representation of “paper-equivalent SMPC with only the give-way rule removed”. The expected clean off baseline must retain:

- the baseline multimodal SMPC optimisation;
- normal route tracking and terminal completion;
- collision sensing as measurement only;
- the same model, risk configuration, initialisation and target behaviour;
- all non-yield controller functions needed to drive to the goal;
- only the rule-based give-way intervention removed.

For the clean off arm, safe ego-first crossing is not a yield failure. Its competence gate is route completion without collision plus controller/solver integrity; target-first crossing order is an outcome used to measure the incremental rule effect. The expectation that the paper-derived SMPC should complete collision-free is an engineering qualification gate, not a theorem implied by finite-horizon chance constraints.

SF4 toggled a bundled seven-channel authority layer and produced an outcome-floor-saturated off arm. Therefore:

- retain SF4 as diagnostic evidence that the full authority bundle has large physical and command-level effects;
- do **not** claim that a clean supervisor-off SMPC cannot finish;
- do **not** use 40/40 versus 0/40 alone as the final H1 causal proof;
- label all current H1 figures/tables under `docs/paper/generated/supervisor_masking_v2/release/` as preliminary diagnostic material pending the clean off-baseline experiment;
- redesign H1 around a clean “yield rule enabled versus yield rule disabled” treatment.

## 3. Revised hypotheses

### H1 — nominal physical give-way effect

In the Town05 right-hand-traffic scenario, the ego turns left across an opposing straight-priority target. A clean rule-based give-way intervention is expected to increase yielding and prevent adverse conflict while both enabled and disabled SMPC arms remain capable of following the route and reaching the destination when no collision prevents completion.

Primary outcomes: completion, collision/adverse collision, yield violation, minimum footprint separation, conflict-point arrival ordering, time to complete. Independent unit: prospective ego initialisation. Boundary: one CARLA 0.9.14 geometry; no formal, universal or real-road safety guarantee.

Required new contrast: identical SMPC/model/risk/target/init with only the give-way rule application toggled. The old seven-channel bundled `monitor_only` contrast is supplementary mechanism evidence, not this baseline.

Recommended decomposition: H1a qualifies the rule-absent SMPC on ego-only, time-separated and then conflicting cases; H1b tests whether rule application changes crossing order to stable target-first yielding; H1c accounts for approach--hold--release, command replacement/bypass, separation and fallback behaviour.

### H2 — predictor improvement and downstream transfer

Capacity, Information and Architecture are the three upstream subquestions:

- Capacity: does increasing parameter count improve held-out prediction, or was the Transformer merely under-capacity?
- Information: does ordered interaction history add predictive information beyond short/current state?
- Architecture: at matched history and approximately matched capacity, does attention outperform an MLP?

Existing offline/V3 evidence may establish predictor differences. The downstream question is whether those differences create distinct nominal SMPC commands and whether the supervisor attenuates the separation before execution. “Offline improvement did not become a physical advantage” is observational; “the supervisor masked it” requires same-state causal command evidence.

### H3 — risk-allocation improvement and downstream transfer

Fixed and adaptive risk allocation can produce visibly different constraint tightening while producing small nominal/executed acceleration or trajectory differences. Existing R3/V3/SF4 evidence supports compression/non-transfer, but the location of compression must be identified:

- if fixed/adaptive nominal SMPC commands are already nearly identical, the controller is insensitive and supervisor masking is not testable;
- if monitor-only commands differ but enabled commands converge at the same state, command-level supervisor masking is identified;
- if uncertainty intervals cross zero, report unresolved attenuation.

## 4. Mechanism that the thesis must explain

The implemented operator chain is:

`scene/history -> MultiPath multimodal distribution -> risk allocation -> multimodal SMPC candidate -> rule-based authority mapping -> CARLA actuation`.

The predictor returns mode probabilities, per-mode future means and per-step 2x2 covariances. Adaptive risk changes the chance-constraint probability allocation/tightening. The SMPC implementation optimises the active mode branches; do not incorrectly write its objective as a probability-weighted sum unless the implementation is changed. The complete supervisor currently has seven observable channels:

1. reference shaping;
2. forced reference linearisation;
3. lane-entry heading cost;
4. rule/SMPC bypass;
5. post-solver action and desired-speed replacement;
6. release/recovery state;
7. next-control history.

The conflict point is dynamic: ego route intersection with the target motion line. The historical 12 m value is a trigger/proximity parameter, not a fixed physical conflict zone. CARLA runs at 20 Hz; the SMPC horizon uses `N=10`, `dt=0.2 s`, hence a 2 s prediction/control horizon. Formula-to-code mappings are in `docs/paper/generated/supervisor_masking_v2/method_audit/`.

## 5. Existing evidence and its allowed wording

- F1/task foundation: B1 task adaptation strongly improves ADE/FDE and improves mixture NLL relative to pretrained B0. This is retained but is not the headline contribution.
- F4/CIA offline: capacity is non-monotonic; ordered history adds only small predictive value; the Transformer is modestly better than the matched MLP in held-out NLL. Use the exact tables, not a generic “Transformer wins” claim.
- F5/V3 closed loop: P* versus B1 and adaptive versus fixed differences are small/noisy at physical outcomes. Adaptive changes tightening by roughly 0.26, while mean nominal acceleration shifts are much smaller. This supports non-transfer/compression, not yet supervisor-specific masking.
- F2/R3 frontier: adaptive dominates only 3 of 12 declared fixed-risk comparators. Retain all 12 contrasts.
- F3/SF4: authority enabled produced 40/40 nominal completions with no yield failure/adverse collision; the bundled monitor-only arm was 0/40 and floor saturated. This proves the bundle is physically consequential in that implementation, but does not answer the clean off-baseline question and does not isolate a single channel.

Machine-readable evidence lives under `docs/paper/generated/supervisor_masking_v2/`. The gate currently says H2/H3 causal masking requires supplemental same-state command collection. Its H1 “existing evidence sufficient” verdict must be revised after the clean baseline is implemented.

## 6. Same-state shadow experiment status

Purpose: on the same factual CARLA planning state, evaluate all 2 predictor x 2 risk x 2 authority-mapping command branches while only one factual branch actuates. This distinguishes controller insensitivity from supervisor attenuation without replaying divergent long-horizon trajectories.

Implemented:

- default-off shadow launcher integration in `run_all_scenarios.py` and `run_intersection_scenario.py`;
- frozen-state replay and eight-row recording in `policies/same_state_shadow_replay.py`;
- shadow-only support in `policies/smpc_agent.py`;
- V2 protocol with four pre-outcome event anchors;
- prospective init 116--135 generation;
- analysis, provenance and integrity tests;
- Python/Matplotlib release figures and tables.

Server compatibility tests passed 19/19 before the smoke.

First excluded smoke on 2026-08-25:

- B1 / fixed-medium / assertive / init116 / camera off;
- TensorFlow used RTX 4090 and cuDNN; Gurobi backend loaded successfully;
- failed closed at loop step 7 before any shadow row was accepted;
- exact error: selected anchor lacked a valid `model_gmm` replay input;
- no formal data were produced and the failure is excluded from analysis.

Local code now fixes the bug by requiring both factual prediction validity and captured `model_gmm` replay readiness for every event anchor; invalid active states do not advance the three-valid-update dwell counter. Local targeted tests pass 18/18. This fix has not yet been re-synchronised to the server at the time of this handoff.

Important smoke gate: an enabled shadow rollout alone is insufficient. The excluded smoke must include a shadow-disabled control rollout and a shadow-enabled rollout and verify that the factual trajectories match within the predeclared deterministic tolerance, that no shadow branch actuated, that all selected states have 8 branches, and that factual command parity holds.

## 7. Server state and frozen assets

Connection (credentials intentionally omitted):

```bash
ssh -p 49524 root@connect.cqa1.seetacloud.com
```

Persistent paths:

- isolated worktree: `/root/autodl-tmp/Research-Project-IMLS-shadow-v2`
- V3 results: `/root/autodl-tmp/results/capacity_history_thesis_core_v3`
- new results root: `/root/autodl-tmp/results/supervisor_masking_v2`
- CARLA 0.9.14: `/root/autodl-tmp/carla_0.9.14`
- CARLA start script: `/root/autodl-tmp/start_carla_3d.sh`
- historical main repo (dirty; do not overwrite): `/root/autodl-tmp/Research-Project-IMLS`

At handoff, CARLA remains in screen `masking_v2_carla`; the failed smoke screen has exited. Inspect with:

```bash
screen -ls
nvidia-smi
tail -100 /root/autodl-tmp/results/supervisor_masking_v2/smoke/smoke_screen.log
```

Failed excluded smoke data are preserved under:

`/root/autodl-tmp/results/supervisor_masking_v2/smoke/init116_B1_fixed_medium_assertive`

Frozen models:

- B1: `.../training/v3__head-large__lr1e-4__s23__data100/best_model`
- P*: `.../training/v3__transformer-h1p0-large__lr1e-4__s37__data100/best_model`
- calibrations: `.../postprocess/calibration/<run>/calibration.json`
- anchors: isolated worktree `core/scripts/models/l5kit_clusters_16.npy`
- tuning: `give_way_reduced_clear_path_release_v13_risk_owned_yield.json`
- adaptive config: `adaptive_floor_weak_v1.json`

Do not change model selection, held-out data, init population, target treatments, thresholds, event anchors, risk parameters or statistical rules after observing outcomes.

## 8. Immediate next tasks in order

1. On the new device, pull both repositories and read this document plus the OpenSpec change `supervisor-masking-thesis-reframe`.
2. Synchronise the latest local code commit into the isolated server worktree; do not merge into or clean the historical dirty server repo.
3. Re-run server unit tests for shadow replay/launcher/analyser.
4. Run the paired excluded smoke: shadow disabled first, then enabled; camera off. Preserve failed attempts rather than overwriting them.
5. Pass every smoke integrity gate, including factual trajectory non-interference. If it fails, diagnose mechanism; do not relax thresholds.
6. Implement the clean H1 baseline that removes only give-way rule application while preserving paper-equivalent SMPC, route following and terminal completion. Run a small excluded smoke before freezing its formal population.
7. Amend/freeze H1 protocol prospectively, then collect the minimum statistically valid H1 formal matrix.
8. Only after both gates pass, launch the 160-rollout same-state formal matrix (B1/P* x fixed/adaptive x assertive/reactive x init116--135), preferably parallelised across independent CARLA instances/GPUs without sharing ports.
9. Materialise command-transmission analysis and update H2/H3 wording based on the predeclared decision rules.
10. Regenerate all figures strictly with Python/Matplotlib and visually inspect PNG/PDF outputs.
11. Rewrite the thesis with `nature-writing` using sections: Introduction, Literature Survey, Problem Formulation, Methodology, Experimental Design, Result Analysis, Conclusion; retain at least 25--30 verified primary references and move derivations/full tables to appendices.
12. Compile and visually audit the approximately 15-page manuscript, then commit/push both repositories.

## 9. Tests and generated artifacts

Relevant test modules:

```bash
python3 -m unittest \
  core.scripts.models.tests.test_same_state_shadow_replay \
  core.scripts.models.tests.test_shadow_launcher_integration \
  core.scripts.models.tests.test_analyze_shadow_command_transmission
```

Run the broader supervisor-masking tests before release. Also run `python3 -m py_compile` on new Python files, `bash -n` on launchers, `git diff --check`, and strict OpenSpec validation.

Key artifacts:

- protocol: `docs/paper/generated/supervisor_masking_v2/protocol/SAME_STATE_SHADOW_PROTOCOL_V2.json`
- evidence gate: `docs/paper/generated/supervisor_masking_v2/gate/EVIDENCE_GAP_DECISION.json`
- method audit: `docs/paper/generated/supervisor_masking_v2/method_audit/`
- figures/tables: `docs/paper/generated/supervisor_masking_v2/release/`
- experiment plan: `openspec/changes/supervisor-masking-thesis-reframe/`
- teacher paper: `docs/literature/01_predictive_control_uncertain_multimodal_predictions.pdf`

## 10. Writing constraints

- Do not narrate the internal daily research process, “27 runs”, selection chores or Codex history to the reader.
- Explain MultiPath, multimodal SMPC, risk allocation and every supervisor formula in plain language before notation becomes dense.
- Distinguish prediction quality, nominal controller commands, executed commands and physical outcomes.
- Use “non-transfer”, “controller compression” and “supervisor masking” as different claims with different evidence requirements.
- All result figures must be generated by Python, with units, legends, uncertainty and restrained journal styling. No AI-generated result graphics.
- The architecture figure must show the concrete research operation and measurement points, not a generic autonomous-driving block diagram.
- Keep the previous fixed-versus-adaptive risk work as supporting evidence; do not discard it.
- Treat the teacher-provided multimodal SMPC paper as the controller foundation, while making clear which supervisor mechanisms are project-specific.

## 11. Repository state at handoff

Experiment repository branch: `main`. The supervisor-masking implementation, protocols, analyses, figures, OpenSpec change, correction notice and this handoff are intended to be committed together after tests.

Paper repository branch: `main`, previous manuscript commit `8477c26`. The manuscript itself has not yet been rewritten to the corrected H1/H2/H3 story; a paper-repository handoff notice should point to this document and explicitly prevent reuse of the old 0/40 H1 interpretation.
