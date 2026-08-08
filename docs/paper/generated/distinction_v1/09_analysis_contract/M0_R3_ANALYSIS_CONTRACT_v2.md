# R3 analysis contract v2 — outcome/statistics hardening amendment

This document prospectively amends, but does not replace, `M0_R3_ANALYSIS_CONTRACT.json`. The original file remains byte-for-byte intact (SHA-256 `81f61798087ce7aac4c76fbe4e6c539a9bc40a45617f823233640589f6d796db`). Before corrected R3 outcomes are read, v2 fixes a causal defect in v1's efficiency estimand: target exit can respond to treatment, so target-exit-adjusted lag cannot be the primary efficiency outcome. V2 instead uses ego route-completion duration, whose measurement definition is not conditioned on another treatment-responsive actor.

## Experimental unit and scope

The independent unit is one ego initialisation group (`101`–`105`), not a simulator step, prediction window or collision callback. R3 is the complete paired nominal matrix: 2 predictor stacks × 4 risk policies × 2 target styles × 5 inits = 80 rollouts. H3 is explicitly nominal-only (`target_offset_m = 0`). Legacy, pilot and timing-shift results may be discussed as separate sensitivity evidence but must never be pooled with R3.

## Executable timing definitions

- **Ego route-completion duration:** `smpc_completion.json.step / scenario_run_summary.json.carla_fps`, only when `completion_valid=true`. This is the primary event clock because it includes the `run_step()` that sets `goal_reached`.
- **Ego completion timestamp:** rollout start timestamp plus the valid route-completion duration.
- **Target fixed-zone exit:** `target_exit_time_s` from the single route-projected fixed-geometry yield rule (4.0 m radius).
- **Post-clearance completion lag:** ego completion timestamp minus target fixed-zone exit timestamp. This is the canonical executable name for original M0's `fixed_geometry_adjusted_delay_s`, retained only as a secondary interaction decomposition.
- **Fixed-geometry yield gap:** ego fixed-zone entry minus target fixed-zone exit. Positive means target exit preceded ego entry before the separate 0.2 s binary tolerance is applied.
- **Footprint separation:** minimum oriented-rectangle separation under the frozen 0.25 m per-actor inflation; higher is better. Every row also records the actual actor blueprint/bounding-box geometry used.

The primary efficiency outcome is **ego route-completion duration** (lower is better), paired with **minimum footprint separation** (higher is better). Post-clearance lag is a timing decomposition, not causal covariate adjustment: target exit may respond to treatment and a smaller lag can arise because the target clears later. It therefore cannot establish efficiency.

## Missingness and binary failures

`df_full.csv completion_time` is last-minus-first logged trajectory time and can be one tick shorter because the completion state is not appended after `goal_reached`; it is only a consistency check against the event-clock duration. A discrepancy beyond the frozen timestamp tolerance is an integrity defect.

Observed invalid completion censors completion time and post-clearance lag. Missing target exit censors target-exit elapsed time and lag. Missing ego entry or target exit censors yield gap. Nothing is imputed. A paired continuous effect exists only when both treatment values are finite; every missing init and reason is emitted. Prespecified censoring caused by an observed failure is a valid scientific result that blocks the universal claim, not missing experimental evidence. Missing or corrupt telemetry is instead an integrity defect.

Native collision, footprint collision, fixed-geometry yield failure and completion failure are rollout-binary intent-to-treat outcomes. Collision callbacks are additionally collapsed to descriptive frame-contiguous episodes, but neither callbacks nor episodes increase the sample size. An unknown binary outcome remains unknown and makes a universal no-excess claim unresolved; it is never silently coded as success or failure.

Native collision episodes use the hardened audit's canonical unordered actor-pair taxonomy, which merges mirrored sensor callbacks before category and rollout counts are formed. Footprint margins `0.0`, `0.25`, `0.35` and `0.50` m per actor are frozen sensitivity settings. The analyzer emits 320 rollout-margin rows and recomputes the 12 H4 dominance decisions at every margin (48 rows); `0.25` remains primary and margins are never searched for a favourable result.

## H3 and H4

H3 compares B1 minus B0 separately in every policy × style cell. Its two Holm families contain eight contrasts each: one family for ego route-completion duration and one for footprint separation. Universal directional support requires the correct mean direction in all eight cells and no excess observed failures. With five clusters, the smallest non-zero two-sided exact p-value is 0.0625; H3 must therefore be described as nominal-condition directional consistency, not conventional confirmatory significance.

H4 compares adaptive minus each of three fixed policies within each predictor × style stratum. Each stratum-outcome combination is a three-test Holm family (eight families). Adaptive dominates one comparator only when ego route-completion duration is no worse, separation is no worse, at least one outcome is strictly better, all five outcome pairs are complete, and all binary no-excess guards are observed and satisfied. Universal H4 support requires all 12 comparator-level dominance decisions.

Numerical dominance tolerances are 0.05 s for timing (one simulator sample) and 1e-6 m for separation. They are numerical-resolution rules, not practical-equivalence or non-inferiority margins.

## Small-sample inference

Every table retains the five raw init effects. The formal p-value is the two-sided exhaustive sign-flip p-value. Holm adjustment is confined to the prespecified families above. A 20,000-replicate percentile cluster bootstrap of the mean is reported descriptively, using global seed `20260808` and a deterministic SHA-256-derived seed for each contrast/metric. `p>0.05` is never called equivalence.

## Manipulation checks and completion meaning

The analyzer recomputes full-horizon in-loop ADE/FDE/minADE/NLL and reports rollout-macro matched B1-minus-B0 checks. Because closed-loop windows can diverge, these are descriptive manipulation checks. It also reports step-weighted risk tightening and adaptive-solver use for all arms. Weak or failed predictor/risk manipulation, collisions, null effects and non-dominance are scientific results; they do not make the analyzer fail. Top-level `status` in `R3_ANALYSIS_COMPLETE.json` denotes analysis integrity and completeness only. The study-stop gate closes after 80/80 integrity-valid rollouts when every outcome is observed or classified as undefined for a prespecified scientific reason; it does not demand 80 finite primary outcomes.
