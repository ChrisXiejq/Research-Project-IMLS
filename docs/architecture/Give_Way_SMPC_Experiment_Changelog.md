# Give-Way SMPC Experiment Changelog

This file records each give-way SMPC tuning change, the amount changed, observed effect, and the next decision. Before changing the experiment again, read this file first and avoid repeating a configuration that has already been tested.

## Current Rule

- Do not tune by memory only. Every tuning change must add or update one row in this changelog.
- Record both the parameter delta and the observed result directory.
- Compare against the nearest previous run, not only against the gate threshold.
- Keep `yield_activation_distance` and `yield_observed_caution_distance` fixed unless the changelog shows reference-profile tuning has stopped helping.
- Treat solver failures by phase:
  - `released_recovery` failures: tune recovery speed/accel or rejoin reference.
  - `approach_yield_line` failures: tune stop buffer or braking reference profile.
  - `hold_yield_line` failures: tune `yield_reference_min_speed` before moving the stop line or trigger distance.

## Key Metrics

- Required policies: `smpc_var_risk`, `smpc_fixed_risk`.
- Gate threshold: `solver_failure_frac <= 0.050`.
- Safety must remain true: completion valid, no footprint collision, target clears before ego enters conflict zone.

## Change History

| Run / state | Change | Parameters | Observed effect | Decision |
|---|---|---|---|---|
| `20260620_223238` | Smooth braking-distance reference profile introduced before the later min-speed/recovery tuning. | `yield_stop_buffer_distance=8.0` era, smooth reference profile; exact current-style `yield_reference_decel` not yet separated. | Safe yield and completion passed. Solver failure was just above threshold: `var=0.055`, `fixed=0.055`. Footprint separation: `var=2.776m`, `fixed=2.839m`. | Good safety baseline, but EV behavior was visually too conservative/slow after yield. |
| `20260620_231320` | Tried making EV less conservative and faster after TV clears. | `yield_stop_buffer_distance=5.0`, `yield_recovery_speed=5.0`, `yield_recovery_accel=1.5`, activation/caution stayed near `12.0`. | Safety/completion still passed, but solver failure regressed badly: `var=0.165`, `fixed=0.083`. Footprint separation fell to `var=1.389m`, `fixed=2.149m`. | Do not repeat this aggressive combination. Stop line too close and recovery too aggressive. |
| `20260620_234829` | Backed off to a more stable stop line and slower recovery. | `yield_stop_buffer_distance=6.5`, `yield_recovery_speed=4.0`, `yield_recovery_accel=1.2`, release waits for target cleared. | Improved solver failure: `var=0.064`, `fixed=0.069`. Safety/completion passed. Footprint separation improved to about `3.0m`. | Effective direction. Remaining failures were in approach/hold, not recovery. |
| `20260621_153823` | Tried lowering parking distance slightly for visual naturalness. | `yield_stop_buffer_distance=6.0`, activation/caution unchanged at `12.0`, recovery unchanged. | Regressed: `var=0.099`, `fixed=0.069`. Footprint separation worsened to `var=1.981m`, `fixed=2.398m`. | Do not continue lowering stop buffer. `6.0m` is too close for var-risk feasibility. |
| `20260621_161906` | Split the difference and softened reference decel. | `yield_stop_buffer_distance=6.25`, `yield_reference_decel=-4.0`, `yield_reference_min_speed=0.8`. | Improved over `6.0m`: `var=0.090`, `fixed=0.070`. Safety passed, but still above threshold. | Direction helped but not enough; remaining failures in approach/hold. |
| `20260621_164134` | Further softened reference decel. | `yield_reference_decel=-3.5`, `yield_reference_min_speed=0.8`, stop buffer stayed `6.25`. | Clear improvement: `var=0.066`, `fixed=0.066`. Footprint separation `var=2.557m`, `fixed=2.545m`. | Best balanced tested run so far. Keep `-3.5` as baseline unless a new change beats it. |
| `20260621_181839` | Tried even softer reference decel. | `yield_reference_decel=-3.0`, `yield_reference_min_speed=0.8`, stop buffer stayed `6.25`. | Not worthwhile: `var=0.065` was only marginally better, but `fixed=0.075` regressed. Safety/completion still passed. | Do not continue softening decel. Revert to `-3.5`. |
| Local pending after `20260621_181839` | Based on hold-phase failures, keep the best decel and raise hold reference floor. | `yield_reference_decel=-3.5`, `yield_reference_min_speed=1.0`, stop buffer `6.25`, activation/caution `12.0`, recovery `4.0/1.2`. | Local profile simulation passes; pre-CARLA gate passes `32 PASS / 0 WARN / 0 FAIL`. CARLA result pending. | Next server run should test whether hold failures drop without hurting fixed-risk. |

## Rejected Directions

- `yield_stop_buffer_distance=5.0` with fast recovery: caused high solver failure (`var=0.165`).
- `yield_stop_buffer_distance=6.0`: made video less conservative but worsened `var_risk` solver failure.
- `yield_reference_decel=-3.0`: did not materially improve `var_risk` and worsened `fixed_risk`.
- Increasing `yield_activation_distance` / `yield_observed_caution_distance`: not tested after user preference; avoid unless reference-profile tuning cannot reduce failures.

## Next Candidate Changes

Evaluate these only after the current pending run (`yield_reference_min_speed=1.0`, `yield_reference_decel=-3.5`):

1. If `hold_yield_line` failures decrease and approach failures dominate, keep `yield_reference_min_speed=1.0` and consider a small `yield_brake_distance_margin` adjustment.
2. If `fixed_risk` regresses, revert `yield_reference_min_speed` to `0.8` and consider `yield_reference_min_speed=0.9`.
3. If both policies remain around `0.06`, inspect first-failure KKT/debug setup before changing geometry again.
