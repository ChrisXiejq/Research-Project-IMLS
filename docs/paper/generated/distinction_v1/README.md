# Distinction evidence workspace

This directory contains the complete post-audit, script-generated evidence
chain. The active writing route is
[`../../../paper/THESIS_EVIDENCE_GUIDE.md`](../../../paper/THESIS_EVIDENCE_GUIDE.md);
the execution plan is retained as its historical protocol record.

Rules:

- do not hand-edit numerical CSV/JSON outputs;
- keep legacy and corrected-control evidence separate;
- every subpackage must include its source hashes, Git SHA, command/config,
  aggregation units, sample counts and completion/audit JSON;
- exploratory or post-hoc outputs must be labelled in filenames and metadata;
- the final manifest must resolve and re-extract every cited value from its
  canonical source.

Completed packages:

- `00_baseline/`: repository/offsite provenance and C1–C9 checklist;
- `00_regression_gates/`: known-defect detection and regression gates;
- `01_physical_baselines/`: CV, CA and train-mean baselines plus five-init pairing;
- `02_input_ablations/`: three-seed B1 raster/history diagnostics and raw server reports;
- `03_training_budget/`: all 15 histories, parameter/latency/seed audit;
- `04_in_loop_prediction/`: exact Day10/Day11 logged-window prediction metrics;
- `05_collision_and_geometry/`: native callback taxonomy, footprint and init50 sensitivity;
- `06_split_balance/`: leakage and covariate-balance reconstruction;
- `07_ml_claim_gate/`: frozen ML contribution and prohibited wording.
- `08_corrected_closed_loop/`: R1/R2/G2, corrected R3 raw evidence and A2
  synthesis;
- `09_analysis_contract/`: prospective M0 analysis and study-stop contract;
- `10_four_hypothesis_evidence/`: final M1 value-resolving evidence package.
- `11_w1_manuscript/`: deterministic LaTeX tables, corrected manuscript
  figures and the W1 source/build/visual completion gate.
- `12_q1_final_audit/`: detached clean-checkout, scientific manuscript and
  submission-release readiness receipts. Scientific Q1 passes; human metadata
  remains pending.

Use `10_four_hypothesis_evidence/` for headline claims and
`08_corrected_closed_loop/r3_final/synthesis/` for corrected closed-loop
tables and figures.
