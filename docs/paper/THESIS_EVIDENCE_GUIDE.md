# Thesis study and evidence guide

Updated: 2026-08-30

## 1. Research question

The project studies a right-hand-traffic Town05 give-way interaction in which
the ego vehicle turns left across an opposing target vehicle travelling
straight. It asks how three upstream choices—motion predictor, risk allocation
and rule-based behavioural authority—change the trajectory that CARLA actually
executes.

The system is a coupled chain:

```text
MultiPath GMM -> fixed/adaptive risk -> probability-weighted SMPC
              -> supervisor authority -> physical CARLA behaviour
```

The key methodological point is that predictor accuracy, optimiser input and
executed behaviour are different endpoints. A gain at one layer is not assumed
to survive every downstream layer.

## 2. Data and predictor design

The source protocol collects 200 CARLA rollouts. The corrected frozen model
study uses four cells per initialisation group and rollout-disjoint groups:
1--35 for fitting, 36--40 for model selection/calibration and 41--45 for
held-out evaluation. This gives 3,526 fit, 510 selection and 506 held-out
windows.

Each window combines a target-centred raster, a six-token ego–target
interaction sequence and ten future positions at 0.2 s spacing. Partial future
horizons carry an explicit validity mask. Corrected V4 applies that mask in
training, validation NLL, checkpointing, early stopping, calibration and
held-out ADE/FDE/NLL.

The 27-run matrix crosses nine model cells with three fixed seeds. It separates:

- **Capacity:** small, medium and large Transformer adapters;
- **Information:** current snapshot, partial history and full history;
- **Architecture:** capacity-matched MLP and Transformer adapters.

The baseline `head-large` cell is the task-adapted MultiPath head (B1). The
historically deployed temporal candidate is
`transformer-h1p0-large`; corrected V4 selects `mlp-h0p4-large` as P*.

## 3. Corrected offline conclusions

All 27 corrected runs pass the release and epoch-integrity gates. The uniform
80-to-120 epoch extension was frozen before held-out access. Five held-out
initialisation groups are the independent inference units, so exact two-sided
sign-flip tests have limited resolution.

The corrected evidence supports these bounded statements:

- full interaction history improves NLL over a snapshot-only input for both
  MLP and Transformer families in the tested large-capacity cells;
- the tested capacity comparison does not identify a stable medium-capacity
  optimum;
- the direct MLP-versus-Transformer offset is not identified uniformly across
  history conditions;
- the previous “no attention-specific history gain” conclusion is weakened,
  not strengthened, after mask correction;
- the full-horizon-only B0/B1 foundation comparison retains its conclusion
  because partial windows are excluded from that analysis.

The machine-readable decisions are in
`docs/paper/generated/future_mask_v4e_120/paper_outputs/claim_decisions.csv`.

## 4. Probability-weighted closed-loop design

The corrected controller uses MultiPath mode probabilities as the branch-cost
weights in the multimodal SMPC objective. The target follows an assertive
constant-speed controller that does not use ego state.

The frozen evidence contains 60 unique rollouts:

```text
Supervisor on:  B1/P* × fixed-medium/adaptive × init 126--135 = 40
Supervisor off: B1/P* × fixed-medium/adaptive × init 126--130 = 20
```

Here P* denotes the historically deployed large Transformer candidate. These
rollouts are valid evidence for that deployed stack and for the matched
authority intervention. Because corrected V4 selects a different P*, they do
not by themselves establish corrected-V4 offline-to-CARLA transfer.

## 5. Predictor and risk transfer with authority on

All 40 authority-on rollouts complete, yield in the frozen fixed-geometry gate
and avoid observed footprint collision. The deployed predictors generate
different trajectories and mode probabilities, and the audited SMPC weights
match those probabilities exactly.

Physical paired effects remain small. Transformer-adapted minus B1 completion
is 0.000 s under fixed-medium risk and -0.005 s under adaptive risk. Separation
effects are +0.0257 m and +0.0092 m, respectively; most paired intervals cross
zero. Adaptive-minus-fixed completion effects are +0.020 s for B1 and +0.015 s
for the Transformer candidate. These results show transmission into the
optimiser, but not a consistent physical advantage from predictor or risk
choice under authority on.

## 6. Supervisor-authority result

The matched authority comparison uses five initialisation groups across both
predictors and both risk policies.

- Endpoint completion is 20/20 with authority on and 20/20 with authority off.
- The stricter conflict-handling competence gate is 20/20 versus 8/20.
- Early conflict-zone entry is 0/20 versus 12/20.
- Observed footprint collision is 0/20 versus 4/20.
- Authority on applies post-solver action replacement on 26.1% of steps and
  SMPC bypass on 17.3%; authority off applies neither by construction.
- The off-arm binary outcome pattern is identical across predictor and risk
  choices within each initialisation group.

The experiment therefore supports a causal effect of the complete behavioural
authority bundle on conflict handling in these five paired initialisations.
It does not isolate any individual supervisor rule, prove population-level
safety or show that the ego cannot reach its endpoint without the supervisor.

## 7. Evidence map

Corrected offline primary evidence:

```text
docs/paper/generated/future_mask_v4e_120/
  audits/                 mask, cache, convergence and claim-contract audits
  figures/                Python-generated publication figures
  paper_outputs/          claim decisions and LaTeX table fragments
  postprocess/            frozen selection and held-out synthesis
  protocol/               pre-held-out extension and stage receipts
```

Probability-weighted closed-loop evidence:

```text
docs/paper/generated/weighted_smpc_v2_recovery/
  h2_assertive_40/        authority-on predictor/risk analysis
  supervisor_authority_assertive_joint60/  matched authority analysis
  provenance/             joint60 and arm-level integrity receipts
```

Every newly imported publication file is recorded by a
`PUBLICATION_EVIDENCE_MANIFEST.json` with byte size and SHA-256.

## 8. Claim boundaries

Allowed claims:

- future validity must be respected through the entire prediction evaluation
  pipeline;
- interaction history contains useful information in the tested dataset;
- the tested architecture/capacity results are conditional rather than a
  general ranking of MLPs and Transformers;
- probability-weighted predictor differences reach the SMPC objective but do
  not produce a consistent physical advantage under authority on;
- the complete supervisor-authority bundle materially improves conflict
  handling in the tested assertive initialisations.

Do not claim:

- Transformers are generally inferior to MLPs;
- corrected V4 P* has already been validated in CARLA;
- adaptive risk is universally better or useless;
- the supervisor is the unique cause of all upstream masking;
- zero observed events proves formal or population-level safety;
- results generalise beyond this map, manoeuvre, target policy or simulator.

