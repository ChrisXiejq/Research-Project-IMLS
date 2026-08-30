# Corrected future-mask V4 conclusion audit

## Release gates

- Offline evidence release: pass (27/27 corrected runs).
- Future mask: fail-closed in validation, checkpointing, early stopping, calibration and held-out evaluation.
- Selection: groups 36--40 only; held-out groups 41--45 were opened after the immutable freeze.
- Statistical scope: five independent held-out init groups; exact two-sided sign-flip inference is resolution-limited.
- Training budget: the pre-freeze convergence gate triggered a uniform 80-to-120 epoch amendment for all 27 runs before held-out access.

## Offline claim decisions

- `capacity_medium_observed_optimum`: **not_identifiable**
- `recent_history_captures_most_gain`: **same**
- `transformer_direct_offset_across_horizons`: **not_identifiable**
- `no_attention_specific_history_gain`: **weakened**

- `foundation_B0_B1_full_horizon_only`: **same**. The frozen foundation
  comparison used 326 full-horizon validation windows and 315 full-horizon
  test windows; zero partial windows entered its metrics.

Overall offline conclusion status: **not_identifiable**.

## P* and CARLA gate

- Old P*: `transformer-h1p0-large` / `v3__transformer-h1p0-large__lr1e-4__s37__data100`.
- Corrected P*: `mlp-h0p4-large` / `v3__mlp-h0p4-large__lr1e-4__s11__data100`.
- Exact deployment identity decision: **rerun_required**.
- Corrected offline-to-closed-loop claim allowed: **False**.
- Required action: Rerun corrected B1/P* CARLA before claiming corrected V4 offline-to-closed-loop transfer.

Historical CARLA outcomes remain valid observations for the historical V3 deployed stack; they cannot be relabelled as corrected V4 transfer evidence unless the identity gate is exact or CARLA is rerun.

## Paper update boundary

No dissertation source or existing figure was modified. Use `paper_update_map.csv`, the three LaTeX table fragments and the Python-generated figures as replacement inputs.
