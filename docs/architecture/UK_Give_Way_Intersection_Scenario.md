# UK Give-Way Intersection Scenario Notes

This note explains the current intersection scenario and the new UK give-way scenario configuration.

## 1. Is the Current Scenario Signalised?

The UK give-way experiment should be treated as **unsignalised** from the controller's perspective.

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

The lane layout is consistent with a **left-hand-traffic / UK-style** interpretation:

- Eastbound traffic uses the northern lane.
- Westbound traffic uses the southern lane.
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
| Ego vehicle | `0 -> 3` | Turning vehicle that should give way |

The new scenario is explicitly documented as:

- UK left-hand-traffic style.
- Unsignalised.
- Turning vehicle should give way to the straight-going vehicle.

## 5. What Changed Compared With `scenario_01.json`?

The main change is the target-vehicle timing:

| Setting | `scenario_01.json` | `scenario_uk_give_way.json` | Purpose |
|---|---:|---:|---|
| Target start longitudinal offset | `-15.0` | `0.0` | Bring the straight-going target closer to the conflict zone |
| Target nominal speed | `10.0` | `11.0` | Make the priority vehicle interaction more visible |
| Target init speed | `12.0` | `11.0` | Keep a consistent straight-going priority vehicle speed |
| Ego nominal speed | `10.0` | `7.0` | Encourage the turning ego to plan more cautiously |

The route relation is intentionally kept similar to the original scenario so that the new experiment remains close to the paper reproduction setting while becoming more appropriate for a UK give-way interpretation.

## 6. Important Limitation

The scenario configuration alone does **not** hard-code a traffic-law rule such as "ego must stop and yield".

Instead, the expected yielding behaviour should emerge from:

- target-vehicle prediction,
- SMPC collision-avoidance constraints,
- risk allocation,
- ego control optimisation.

This is useful for the dissertation because the experiment can be described as testing whether risk-aware SMPC can produce appropriate give-way behaviour in an unsignalised UK-style intersection.

The step-level logs now record `traffic_control`, `side_of_road`, `priority_rule`, `ego_traffic_light_state`, and whether a traffic-light stop override was applied. For the UK give-way scenario, `ego_traffic_light_forced_stop` should remain `false`; if the ego yields, that behaviour comes from the SMPC decision process.

## 7. Recommended Test Command

Before starting CARLA, run the lightweight pre-CARLA validation locally:

```bash
cd /Users/bytedance/my/Dissertation/Research-Project-IMLS

python3 -m venv .venv-precarla
.venv-precarla/bin/python -m pip install -r core/env_setup/requirements.precarla.txt
.venv-precarla/bin/python core/scripts/precarla_validate_uk_give_way.py
```

For a more complete local gate before using CARLA, run:

```bash
.venv-precarla/bin/python core/scripts/precarla_comprehensive_eval.py
```

This writes detailed JSON and Markdown reports to `core/results/precarla_comprehensive_eval/`. The comprehensive evaluation checks the base scenario, Gymnasium API compliance, nominal conflict timing, speed perturbations, and safety-gap sensitivity. The CARLA run should only be started when the comprehensive gate has no `FAIL` outcomes.

The same script can still be run without the virtual environment by adding `--skip_gym_check`; that mode uses only the Python standard library:

```bash
python3 core/scripts/precarla_validate_uk_give_way.py --skip_gym_check
```

This script reads the same `scenario_uk_give_way.json` and `intersection_01.csv` files as the CARLA experiment. It checks the scenario semantics, runs a simplified kinematic timing test, and, when Gymnasium is installed, validates the simplified environment with Gymnasium's `check_env`. The expected result is that:

- the scenario is declared `unsignalised`,
- the side of road is `left`,
- ego is the turning give-way vehicle,
- target is the priority oncoming straight vehicle,
- target reaches the conflict point before ego,
- a simple give-way delay increases the minimum separation.
- the Gymnasium rollout confirms that the give-way action improves minimum separation compared with the no-yield action.

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
  --with_notv_cl \
  --enable_camera_viz
```

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

For the first validation run, it is better to omit `--enable_camera_viz` unless a video is needed, because video recording slows down the experiment.

## 8. What to Check in the Results

The key question is whether the ego turning vehicle slows or adjusts its trajectory before crossing the path of the straight-going target vehicle.

Useful outputs:

- `carla_sim.avi`: visual inspection of whether ego yields.
- `smpc_debug_steps.jsonl`: relative distance, solver status, and control behaviour.
- `paper_metrics_summary.md`: completion, feasibility, minimum TV distance, and path deviation.
- `trajectory_map.png`: top-down trajectory comparison.

Key metrics:

- `dmin_TV`: should not become too small.
- `completion_valid`: should remain true.
- `solver_failure_frac`: should remain close to zero.
- `max_abs_ey_debug`: should not grow too large.
- `collision_slack_significant_frac`: especially important for open-loop.

## 9. How to Explain It to the Supervisor

Suggested wording:

> I checked the implementation and the current agents do not obey traffic lights, so the experiment is best interpreted as an unsignalised intersection. I have therefore added a clearer UK-style give-way scenario, where the ego vehicle is the turning vehicle and the target vehicle is the priority straight-going vehicle. The aim is to test whether the risk-aware SMPC controller can generate appropriate yielding behaviour from prediction and collision-risk constraints, rather than from a hard-coded traffic-light rule.
