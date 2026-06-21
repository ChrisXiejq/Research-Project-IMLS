# Give-Way Intersection Scenario Notes

This note explains the current intersection scenario and the revised give-way scenario configuration. The experiment has been simplified to a conventional right-hand-traffic setting: the ego vehicle left-turns across an oncoming straight-going target vehicle.

For tuning history and measured effects, see `docs/architecture/Give_Way_SMPC_Experiment_Changelog.md`. Before changing yield/recovery parameters, consult that changelog to avoid repeating rejected configurations and to choose the next direction from prior evidence.

## 1. Is the Current Scenario Signalised?

The give-way experiment should be treated as **unsignalised** from the controller's perspective.

Evidence from the code:

- `PredictionParams.render_traffic_lights` is `False` by default.
- `scenario_uk_give_way.json` sets `traffic_control` to `unsignalised`.
- Both the ego vehicle and target vehicle set `obey_traffic_lights` to `false`.
- Vehicle behaviour is controlled by the policy assigned to each actor, such as `mpc`, `smpc`, `blsmpc`, or `static`, not by a traffic-light phase.

Therefore, if the supervisor describes the experiment as an **unsignalised intersection**, that is a reasonable interpretation.

The code now also supports an optional signalised interpretation for future experiments:

- `VehicleParams.obey_traffic_lights` enables a red/yellow stop override per vehicle.
- `RunIntersectionScenario._apply_optional_traffic_light_rule(...)` checks CARLA's current traffic-light state and forces full braking on red, or on yellow if `stop_for_yellow` is enabled.
- `run_all_scenarios.py` enables traffic-light rasterisation by default when a scenario declares `traffic_control` as `signalised`.

This optional support is deliberately disabled in `scenario_uk_give_way.json`, because the dissertation experiment should test whether SMPC yields from prediction and collision-risk constraints, not from a hard-coded traffic-light stop.

## 2. What Does `intersection_01.csv` Represent?

The file `core/scripts/carla/scenarios/intersection_01.csv` defines four directed road arms:

| Node | Direction | Interpretation |
|---|---|---|
| `0` | West to east | Straight lane from west approach |
| `1` | South to north | Straight lane from south approach |
| `2` | East to west | Straight lane from east approach |
| `3` | North to south | Straight lane from north approach |

The revised scenario uses a **right-hand-traffic** interpretation:

- Eastbound traffic uses the southern lane.
- Westbound traffic uses the northern lane.
- Northbound traffic uses the western lane.
- Southbound traffic uses the eastern lane.

## 3. What Was the Previous Main Scenario?

The previous main scenario, `scenario_01.json`, uses:

| Vehicle | Route | Meaning |
|---|---|---|
| Target vehicle | `2 -> 2` | Oncoming straight-going vehicle |
| Ego vehicle | `0 -> 3` | Turning vehicle crossing the oncoming straight path |

This already creates a conflict between a turning ego vehicle and a straight-going target vehicle. However, the timing was inherited from the original reproduction setting, and the target vehicle could start relatively far from the conflict region. As a result, the interaction did not always clearly show the turning vehicle yielding to the straight-going vehicle.

## 4. New Scenario: `scenario_uk_give_way.json`

A new scenario has been added:

`core/scripts/carla/scenarios/scenario_uk_give_way.json`

This keeps the original paper-style intersection geometry but makes the traffic-rule interpretation clearer:

| Vehicle | Route | Role |
|---|---|---|
| Target vehicle | `2 -> 2` | Priority oncoming straight-going vehicle |
| Ego vehicle | `0 -> 3` | Left-turning vehicle that should give way |

This is intended to mimic the supervisor-style sketch:

```text
                 north arm
                    |
                    |
west arm  EV --->   +   <--- TV  east arm
             left turn across the oncoming path
```

In code, that sketch is represented as:

- EV / ego: `intersection_start_node_idx = 0`, `intersection_goal_node_idx = 3`.
  The ego vehicle comes from the left/west approach and left-turns across the oncoming straight-going target path.
- TV / target: `intersection_start_node_idx = 2`, `intersection_goal_node_idx = 2`.
  The target vehicle comes from the right/east approach and continues straight through the junction.
- The moving vehicles use lane-centre-scale lateral offsets rather than the old full half-road-width offset:
  `ego = +1.85m`, `target = +1.85m`.
  This keeps the vehicles in the intended CARLA-view lanes and avoids placing the ego on the kerb.

The new scenario is explicitly documented as:

- Conventional right-hand-traffic style.
- Unsignalised.
- Left-turning vehicle should give way to the straight-going vehicle.

## 4.1 Fine-Tuning Configuration

The scenario file defines the traffic semantics and route topology. Numeric parameters that are expected to change during CARLA tuning are centralised in:

```text
core/scripts/carla/scenarios/tuning_configs/give_way_smpc_tuning.json
```

This config currently owns the main fine-tuning knobs:

- ego nominal speed,
- target nominal/init speed,
- SMPC horizon `N`, discretisation `dt`, and `num_modes`,
- `collision_d_min`,
- `collision_ellipse_half_length`,
- `collision_ellipse_half_width`,
- `reference_regen_max_lateral_error`,
- yield-stop supervisor parameters (`yield_stop_*`),
- post-yield recovery parameters (`yield_recovery_*`),
- post-CARLA gate thresholds used to judge the result.

`run_all_scenarios.py` automatically applies the scenario-level `tuning_config` path unless `--no_tuning_config` is provided. Every batch result writes `applied_tuning_configs.json`, and every subrun directory writes `fine_tune_config.json`, so each CARLA rollout can be traced back to the exact parameter config used.

## 5. What Changed Compared With `scenario_01.json`?

The main change is the target-vehicle timing:

| Setting | `scenario_01.json` | Current scenario + fine-tune config | Purpose |
|---|---:|---:|---|
| Target start longitudinal offset | `-15.0` | `0.0` | Bring the straight-going target closer to the conflict zone |
| Ego route | `0 -> 3` | `0 -> 3` | Keep the visual left-turn branch that was clearly visible in CARLA |
| Target nominal speed | `10.0` | `6.0` | Keep the priority vehicle in the conflict zone long enough for a give-way interaction |
| Target init speed | `12.0` | `6.0` | Match the target's initial motion to the slower priority-vehicle timing |
| Ego nominal speed | `10.0` | `6.0` | Make the simplified timing gate produce a clear no-yield conflict and a safe give-way alternative |
| Moving vehicle lateral offset | `3.7` | `ego +1.85`, `target +1.85` | Place vehicles near the intended right-hand lane centres rather than on the kerb/road edge |
| Ego SMPC collision envelope | upstream hard-coded ellipse | `half_length=3.8m`, `half_width=1.8m`, `d_min=0.5m` | Keep the chance-constraint vehicle body approximation conservative while reducing the over-yielding seen with `d_min=1.0m` and `d_min=1.5m` |
| SMPC reference-regeneration guard | `1.5m` internal default | `1.5m` | Safety-first setting after `2.5m` and `4.0m` allowed unsafe conflict-zone behaviour in CARLA |
| Rule-aware yielding state machine | not present | enabled, `yield_stop_speed=0.2m/s`, `yield_reference_min_speed=0.8m/s`, `yield_reference_decel=-3.75m/s^2`, `yield_stop_decel=-5.0m/s^2`, `yield_stop_buffer_distance=6.25m`, `yield_brake_distance_margin=3.5m` | Define a fixed route-level conflict zone and a physically reachable stop point before it, then move through cautious approach, hold, release, and recovery phases |
| Ego post-yield recovery | not present | enabled, `yield_recovery_speed=4.0m/s` as a short recovery speed cap | After the priority target clears the conflict zone, rebuild a rejoin reference and resume the turn without remaining slow for the rest of the route |

The route relation is intentionally kept close to the original intersection setting. After inspecting the CARLA video, the experiment is simplified to the visual left-turn case rather than continuing to force a UK-style right-turn interpretation.

The CARLA transform now uses `side_of_road="right"` and lane-centre-scale offsets. The scenario uses `1.85m` rather than the previous `3.7m` full half-road-width offset, because `3.7m` can push the vehicle to the road edge or kerb in the CARLA view.

The `ego_init_01` CARLA rollout now uses `init_speed=6.0m/s`. The previous `9.36m/s` initial speed placed the ego about `2.45m` before the stop point while requiring more than `14m` of braking distance, so even an immediately active cautious-yield controller could not stop before the yield line. The stop buffer is set to `6.25m`: this keeps the activation distance at `12.0m`, stays closer to the conflict zone than the `6.5m` trial, and avoids the var-risk solver regression seen with the `6.0m` trial. The optimisation reference now tests `yield_reference_decel=-3.75m/s^2` with `yield_reference_min_speed=0.8m/s`, a modestly stronger profile intended to reduce var-risk approach speed after `A_MIN=-4.0m/s^2` improved fixed-risk but left var-risk unchanged. The SMPC optimiser allows `A_MIN=-4.0m/s^2`, and the feasible reference generator is explicitly constructed with the same acceleration bounds so its local linearisation inputs are not silently capped at `-3.0m/s^2`. The final control override still allows `yield_stop_decel=-5.0m/s^2`. The release condition also waits until the priority target has cleared the configured conflict radius, preventing recovery from starting while the target is still inside the conflict zone.

## 6. Important Limitation

The scenario configuration alone does **not** hard-code a traffic-light rule, and the controller must not assume an unseen target vehicle exists. Full priority yielding is still gated by the predictor: the ego only treats the target as a confirmed straight-going priority vehicle after an observed target has a valid multimodal prediction. The latest CARLA run showed that waiting for the first valid prediction can be too late, so the state machine now has an earlier `cautious_approach_observed_target` phase. This phase uses only observed target positions across frames to estimate a moving target line; if that observed line intersects the ego route near the conflict zone, the ego conservatively brakes before prediction is ready, without declaring full target priority.

Once the target prediction is valid, the state machine defines a fixed conflict point from the ego global left-turn route and the target's current/predicted straight motion line, then places an ego stop point before that conflict point. While the straight-going target is approaching or occupying the conflict zone, the turning ego enters `approach_yield_line` once its distance to the stop point is below `v^2 / (2 |a_min|) + margin`, then transitions to `hold_yield_line` near the stop point. During these phases it brakes toward the stop point and uses route lookahead steering for the intended left turn. The pre-solve SMPC reference is shaped with a braking-distance speed profile, `v_ref <= sqrt(v_ref_min^2 + 2 |a_min| d_remaining)`, rather than being instantly capped to `yield_stop_speed`; `v_ref_min=0.8m/s` is the current best measured setting, while the control override still performs the final near-stop at `yield_stop_speed=0.2m/s`. The observed-caution and activation distances are both kept near the conflict zone (`12m`) so the ego rolls forward initially and only yields when the interaction becomes visually relevant. After the target clears the zone, `released_recovery` uses a moderate cap (`4.0m/s`) so the ego accelerates through the turn without reintroducing the recovery-phase infeasibility seen in the faster trial.

Instead, the expected yielding behaviour should emerge from:

- target-vehicle prediction,
- SMPC collision-avoidance constraints,
- risk allocation,
- ego control optimisation,
- observed target tracking for non-oracle cautious approach before predictor warm-up,
- the route-defined rule-aware yielding state machine that preserves the right-of-way rule when the optimiser would otherwise keep moving through the turn,
- the post-yield recovery supervisor that prevents a safe near-stop yield from becoming a deadlock.

This is useful for the dissertation because the experiment can be described as testing whether risk-aware SMPC, with a minimal rule-preserving safety layer, can produce appropriate give-way behaviour in an unsignalised intersection.

The step-level logs now record `traffic_control`, `side_of_road`, `priority_rule`, `ego_traffic_light_state`, and whether a traffic-light stop override was applied. For this give-way scenario, `ego_traffic_light_forced_stop` should remain `false`; if the ego yields, that behaviour comes from the SMPC decision process.

## 7. Recommended Test Command

Before starting CARLA, run the lightweight pre-CARLA validation locally:

```bash
cd /Users/bytedance/my/Dissertation/Research-Project-IMLS

python3 -m venv .venv-precarla
.venv-precarla/bin/python -m pip install -r core/env_setup/requirements.precarla.txt
.venv-precarla/bin/python core/scripts/precarla_validate_uk_give_way.py
```

For a more complete local pre-CARLA scenario gate before using CARLA, run:

```bash
.venv-precarla/bin/python core/scripts/precarla_comprehensive_eval.py
```

This writes detailed JSON and Markdown reports to `core/results/precarla_comprehensive_eval/`. The comprehensive evaluation checks the base scenario, Gymnasium API compliance, nominal conflict timing, speed perturbations, safety-gap sensitivity, and whether the SMPC collision envelope covers the conservative CARLA-like vehicle footprint. This gate only proves that the scenario has a reasonable give-way solution; it does **not** prove that the closed-loop SMPC controller will find or execute that solution.

The Python/Gymnasium gate is footprint-aware. It uses conservative CARLA-like rectangles for the moving vehicle body, inflates them with a small safety margin, and then checks for oriented-rectangle overlap. This matters because two vehicle centres can be several metres apart while their bodies still overlap visually in CARLA.

The same script can still be run without the virtual environment by adding `--skip_gym_check`; that mode uses only the Python standard library:

```bash
python3 core/scripts/precarla_validate_uk_give_way.py --skip_gym_check
```

This script reads the same `scenario_uk_give_way.json` and `intersection_01.csv` files as the CARLA experiment. It checks the scenario semantics, runs a simplified kinematic timing test, and, when Gymnasium is installed, validates the simplified environment with Gymnasium's `check_env`. The expected result is that:

- the scenario is declared `unsignalised`,
- the side of road is `right`,
- ego is the turning give-way vehicle,
- target is the priority oncoming straight vehicle,
- target reaches the conflict point before ego,
- a simple give-way delay increases the centre-point minimum separation,
- the no-yield rollout creates an inflated-footprint conflict,
- the give-way rollout avoids inflated-footprint overlap,
- the Gymnasium rollout confirms that the give-way action improves both centre-point distance and footprint separation compared with the no-yield action.

This is not a replacement for CARLA, MultiPath, or SMPC. It is a fast sanity check to confirm that the experimental setup is geometrically and behaviourally meaningful before running the expensive CARLA simulation.

For a quick single-initialisation test:

```bash
cd /root/autodl-tmp/Research-Project-IMLS/core/scripts/carla

python run_all_scenarios.py \
  --scenario_glob "scenario_uk_give_way.json" \
  --init_glob "ego_init_01.json" \
  --policies smpc_var_risk smpc_fixed_risk smpc_open_loop \
  --solver_backend gurobi \
  --risk_profile upstream_code \
  --with_notv \
  --with_notv_cl
```

This writes the original CARLA drone-view `carla_sim.avi` because `scenario_uk_give_way.json` has `drone_viz_params.save_avi=true`, and the batch runner now preserves that setting by default. Use `--disable_camera_viz` only for a faster headless run without AVI output. Avoid `--render_topdown_mp4` when the dissertation figure/video should use the original CARLA bird-eye style.

For a small pilot:

```bash
cd /root/autodl-tmp/Research-Project-IMLS/core/scripts/carla

python run_all_scenarios.py \
  --scenario_glob "scenario_uk_give_way.json" \
  --init_glob "ego_init_0[1-5].json" \
  --policies smpc_var_risk smpc_fixed_risk smpc_open_loop \
  --solver_backend gurobi \
  --risk_profile upstream_code \
  --with_notv \
  --with_notv_cl
```

For a faster first validation run where no video is needed, add `--disable_camera_viz`; otherwise keep the default so each successful subrun writes `carla_sim.avi`.

After pulling a CARLA result directory back to the local machine, run the post-CARLA trajectory gate:

```bash
.venv-precarla/bin/python core/scripts/postcarla_trajectory_gate.py core/results/<timestamp>
```

This is the hard safety gate for deciding whether to move from a 1-init sanity check to a 5-init preliminary pilot. It reads each `scenario_result.pkl`, interpolates the ego and target trajectories onto a common time grid, and replays conservative CARLA-like oriented rectangle footprints. The required default policies are `smpc_var_risk` and `smpc_fixed_risk`; both must:

- complete validly,
- avoid footprint-level collision with every target vehicle,
- respect turning-gives-way semantics: the straight-going target must clear the inferred conflict zone before the turning ego enters it,
- keep `solver_failure_frac <= 0.05`,
- log `collision_envelope` in `smpc_debug_setup.json`, so stale server code/config is caught.

Temporary ego slowing or stopping before the conflict zone is allowed and should not be treated as a failure. The rule is about priority and safety: the turning vehicle must not force itself into the conflict zone ahead of the straight-going vehicle.

If the pulled result contains `applied_tuning_configs.json` or per-subrun `fine_tune_config.json`, the post-CARLA gate reads the `postcarla_gate` thresholds from that config. Command-line arguments still override the config when an explicit sensitivity check is needed.

The script writes:

- `postcarla_trajectory_gate.json`
- `postcarla_trajectory_gate.md`

under the same CARLA timestamp result directory.

## 8. What to Check in the Results

The key question is whether the ego turning vehicle slows, stops, or adjusts its trajectory before crossing the path of the straight-going target vehicle. Maintaining motion is not required; yielding priority is required.

Useful outputs:

- `carla_sim.avi`: visual inspection of whether ego yields.
- `smpc_debug_steps.jsonl`: relative distance, solver status, and control behaviour.
- `paper_metrics_summary.md`: completion, feasibility, minimum TV distance, and path deviation.
- `trajectory_map.png`: top-down trajectory comparison.

Key metrics:

- `dmin_TV`: should not become too small.
- `postcarla_trajectory_gate.md`: authoritative footprint-level pass/fail after CARLA.
- `completion_valid`: should remain true.
- `solver_failure_frac`: should remain close to zero.
- `max_abs_ey_debug`: should not grow too large.
- `collision_slack_significant_frac`: especially important for open-loop.

## 9. How to Explain It to the Supervisor

Suggested wording:

> I checked the implementation and the current agents do not obey traffic lights, so the experiment is best interpreted as an unsignalised intersection. I have therefore simplified the scenario to a conventional right-hand-traffic give-way case, where the ego vehicle left-turns across the priority straight-going target vehicle. The aim is to test whether the risk-aware SMPC controller can generate appropriate yielding behaviour from prediction and collision-risk constraints, rather than from a hard-coded traffic-light rule.
