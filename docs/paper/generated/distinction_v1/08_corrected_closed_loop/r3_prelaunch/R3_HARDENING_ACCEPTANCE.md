# R3 pre-launch hardening acceptance

R3 v3 is ready to execute. The v2 preflight passed, but its first rollout exposed a shell local-variable binding defect before any scientific rollout was launched; v3 corrects that execution-only defect and uses a fresh prospective result directory. It is the only remaining large-scale CARLA experiment in the dissertation plan. After 80/80 integrity-valid rollouts produce a passing `R3_COMPLETE.json` and verified evidence archive, the large-scale CARLA programme is closed regardless of whether H3 or H4 is supported.

## Accepted design

- Matrix: B0/B1 × three fixed policies plus adaptive × assertive/reactive × init 101–105 = 80 unique rollouts.
- Independent unit: ego initialisation group; simulator steps, prediction windows and collision callbacks are not independent samples.
- Primary efficiency: route-completion event duration from `smpc_completion.step / carla_fps`.
- Primary safety proxy: minimum oriented actual-CARLA-bbox footprint separation at 0.25 m margin per actor.
- Binary ITT guards: canonical native collision, footprint collision, fixed-geometry yield failure and completion failure.
- H3: B1-minus-B0 predictor-stack effect in eight policy/style cells.
- H4: adaptive-minus-each-fixed empirical dominance in four predictor/style strata.
- Exact paired sign-flip inference, prespecified Holm families, deterministic descriptive cluster bootstrap and all five raw init effects are emitted.

## Accepted collection semantics

Each attempt is isolated. Raw evidence is validated before atomic promotion, and each accepted rollout has a receipt binding its immutable raw-file set, attempt record and ledger. Interrupted attempts at either side of atomic promotion are recovered as the same attempt. Up to ten attempts are allowed only for predefined infrastructure failures. Unknown failures block; completed rollouts and adverse scientific outcomes are never repeated.

The matrix audit independently verifies actual solver risk identity, mode consumption, Town05/20 Hz/600-step conditions, frozen init/scenario/tuning, first states, deployed model/calibration hashes, actual actor geometry, collision identity and every receipt/raw hash. Runtime exceedance, learned-mode collapse, zero reactive activity and weak adaptive variation are reported as scientific diagnostics rather than integrity failures.

## Accepted evidence semantics

M0 v1 remains unchanged. M0 v2 was frozen before R3 outcomes and corrects the primary efficiency estimand because target exit is treatment-responsive. Completion or yield failure may censor a continuous outcome; this is valid adverse evidence and blocks universal support, not a reason to collect replacement data.

The analyzer emits all prespecified raw, contrast, binary, collision, margin-sensitivity and manipulation-check tables with fixed row counts and SHA-256 hashes. The final archive includes raw pickles, step CSVs, raw/labeled prediction logs, frozen contracts/inits, attempts, environment/source provenance and derived analysis. It is accepted only after every archive member is read back and re-hashed. `R3_COMPLETE.json` is written last.

## Verification performed

- 38/38 server-preflight-equivalent tests passed.
- 57/57 tests in the complete local `core/scripts/models/tests` suite passed.
- Shell syntax, Python compilation, CLI smoke, M0 cross-hash binding, credential scan and `git diff --check` passed.
- The R1 controller and MPC source hashes remain unchanged; the scenario-runner drift is telemetry-only.

Known limitations are frozen as reporting boundaries, not hidden: only five independent clusters, a minimum two-sided exact p-value of 0.0625, a deployed-stack rather than weight-only H3 estimand, and nominal-timing-only corrected R3. R4 is therefore `not_run`, not an outstanding requirement.
