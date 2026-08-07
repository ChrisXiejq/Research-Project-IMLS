# Distinction evidence workspace

This directory is reserved for post-audit, script-generated evidence described
in [`../../../dissertation/DISTINCTION_EXECUTION_PLAN.md`](../../../dissertation/DISTINCTION_EXECUTION_PLAN.md).

Rules:

- do not hand-edit numerical CSV/JSON outputs;
- keep legacy and corrected-control evidence separate;
- every subpackage must include its source hashes, Git SHA, command/config,
  aggregation units, sample counts and completion/audit JSON;
- exploratory or post-hoc outputs must be labelled in filenames and metadata;
- the final manifest must resolve and re-extract every cited value from its
  canonical source.

Completed S0–G1 packages:

- `00_baseline/`: repository/offsite provenance and C1–C9 checklist;
- `00_regression_gates/`: known-defect detection and regression gates;
- `01_physical_baselines/`: CV, CA and train-mean baselines plus five-init pairing;
- `02_input_ablations/`: three-seed B1 raster/history diagnostics and raw server reports;
- `03_training_budget/`: all 15 histories, parameter/latency/seed audit;
- `04_in_loop_prediction/`: exact Day10/Day11 logged-window prediction metrics;
- `05_collision_and_geometry/`: native callback taxonomy, footprint and init50 sensitivity;
- `06_split_balance/`: leakage and covariate-balance reconstruction;
- `07_ml_claim_gate/`: frozen ML contribution and prohibited wording.

The canonical human-readable handoff is
[`S0_G1_EXECUTION_REPORT_2026-08-08.md`](../../../dissertation/S0_G1_EXECUTION_REPORT_2026-08-08.md).
