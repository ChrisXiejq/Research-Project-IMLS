# Supervisor Meeting Q&A Preparation

This document prepares concise answers for a progress meeting about the dissertation project. The answers are written in a style suitable for oral discussion with the supervisor: clear, honest, and not over-claiming final results.

## 1. What are you working on?

### Short Answer

I am working on autonomous driving decision-making under uncertainty. More specifically, I am reproducing and extending a CARLA intersection experiment where an ego vehicle must cross an intersection safely while another target vehicle has uncertain future behaviour.

### Expanded Answer

My project focuses on how a self-driving car can make safe sequential decisions when it is not completely sure what another vehicle will do next. In the current experiment, the target vehicle's future motion is represented as several possible trajectories rather than a single deterministic prediction. The ego vehicle then uses a risk-aware stochastic model predictive control method to choose safe control actions.

At this stage, my main work is to build a reliable reproduction pipeline for the original paper's CARLA intersection scenario, run preliminary experiments, compare different control policies, and identify the remaining gaps before scaling up the evaluation.

### Simple Explanation

In simple terms, I am studying how a self-driving car can cross a junction safely when another car may move in several possible ways.

## 2. What is the core research problem?

### Short Answer

The core problem is how to turn uncertain, multimodal predictions of other vehicles into safe and efficient control actions.

### Expanded Answer

Many modern prediction models can produce several possible future trajectories for surrounding vehicles. However, prediction alone does not solve the driving problem. The controller still needs to decide what action is safe enough when different futures are possible.

If the ego vehicle trusts only one predicted future, it may become over-confident and unsafe. If it considers all possible futures too conservatively, it may stop unnecessarily or fail to make progress. Therefore, the challenge is to balance safety, progress, and comfort under prediction uncertainty.

## 3. What is your core idea?

### Short Answer

The core idea is to combine multimodal prediction with risk-aware stochastic MPC, so that the controller can reason about several possible futures and allocate risk across them.

### Expanded Answer

The prediction model provides a Gaussian mixture representation of the target vehicle's future motion. Each mode has a probability, a mean trajectory, and a covariance. These outputs are passed into the SMPC controller, where they are used to build probabilistic collision-avoidance constraints.

The controller does not simply assume that the most likely future will happen. Instead, it uses chance constraints and risk allocation to decide how much collision risk is allowed for different predicted modes and time steps. This should help the ego vehicle avoid unsafe decisions while also reducing unnecessary conservatism.

### Very Simple Version

The car imagines several possible futures of the other car, then chooses an action that is safe enough for those futures.

## 4. What paper are you reproducing?

### Short Answer

The main reproduced paper is *Predictive Control for Autonomous Driving with Uncertain, Multi-modal Predictions*.

### Expanded Answer

This paper proposes a stochastic MPC formulation for autonomous driving with uncertain multimodal predictions. It uses multimodal predictions of target vehicles, represents prediction uncertainty using Gaussian mixture models, and incorporates those predictions into chance-constrained collision avoidance.

My project follows the paper's CARLA intersection setting and compares similar policy variants, including variable-risk SMPC, fixed-risk SMPC, open-loop SMPC, and no-target-vehicle baselines.

## 5. What is the data source in your experiment?

### Short Answer

The experiment uses CARLA simulation data generated online during the intersection rollout, together with scenario configuration files and multimodal target-vehicle predictions.

### Expanded Answer

The data does not come from a static dataset during the main control loop. Instead, CARLA generates the driving scene, vehicle states, and interactions at each simulation step. The scenario JSON files define the map, route, vehicle settings, initial conditions, and policy type.

During each rollout, the system records the ego vehicle and target vehicle states. The target vehicle history is used by the prediction module to produce multimodal future predictions. These predictions are then used by SMPC to solve the control problem.

## 6. Where is the prediction model used?

### Short Answer

The prediction model is used between state observation and SMPC planning. It predicts several possible future trajectories of the target vehicle.

### Expanded Answer

At each simulation step, the system observes the current and recent past states of the target vehicle. The prediction module then outputs several possible future trajectories, each with a probability and uncertainty estimate. These outputs are passed into the SMPC controller as Gaussian mixture model information.

The SMPC uses this information to build collision-avoidance constraints. Therefore, the prediction model is not the final controller; it provides uncertain future information that the controller uses for planning.

## 7. Where are GMM and risk parameters used?

### Short Answer

The GMM parameters are used to represent target-vehicle prediction uncertainty, and the SMPC risk parameters are used to convert that uncertainty into probabilistic safety constraints.

### Expanded Answer

The GMM contains three key pieces of information:

- Mode probabilities: how likely each possible future is.
- Mean trajectories: where the target vehicle is expected to be in each mode.
- Covariances: how uncertain the target vehicle's position is.

These values are used inside the collision-avoidance chance constraints. The SMPC risk profile defines the tightening level and target probability used to make these constraints safer. In my current experiments, I mainly use the `upstream_code` risk profile, which is closer to the original implementation.

## 8. What experiments have you run so far?

### Short Answer

I have built and run a small multi-initialisation CARLA intersection pilot experiment comparing five policies across five ego initial conditions.

### Expanded Answer

The latest pilot experiment includes:

- One CARLA intersection scenario.
- Five ego initial conditions.
- Five policy variants.
- Twenty-five total rollouts.

The policies are:

- No-target-vehicle baseline.
- No-target-vehicle closed-loop baseline.
- Variable-risk SMPC.
- Fixed-risk SMPC.
- Open-loop SMPC.

The goal of this pilot is not to claim final reproduction, but to verify that the pipeline works and to identify which parts need further tuning before larger-scale experiments.

## 9. What are your current preliminary results?

### Short Answer

The current pipeline works, and the main closed-loop SMPC controllers can complete the intersection task in the pilot experiment. However, path deviation and occasional solver issues still need improvement.

### Expanded Answer

In the latest multi-initialisation pilot, all rollouts completed the intersection task. The closed-loop variable-risk and fixed-risk SMPC controllers are now able to complete the task, which shows that the main reproduction pipeline is operational.

However, the results are still preliminary. The variable-risk SMPC sometimes has solver failures, and both variable-risk and fixed-risk SMPC still show relatively large path deviation. The open-loop SMPC also completes in the latest version, but it uses collision slack, so I should interpret it carefully as a diagnostic or softened baseline rather than a fully strict hard-constraint result.

## 10. What are the main evaluation metrics?

### Short Answer

I evaluate task completion, solver feasibility, solve time, safety distance, path deviation, and comfort-related metrics.

### Expanded Answer

The main metrics are:

- Completion time: how long the vehicle takes to finish.
- Feasibility rate: how often the SMPC solver succeeds.
- Average solve time: computational cost per control step.
- Minimum distance to the target vehicle: safety margin.
- Path deviation: how far the controlled trajectory deviates from the baseline route.
- Lateral acceleration and jerk: comfort and smoothness.
- Completion diagnostics: whether the vehicle truly reaches the path end without large lateral error.
- Slack usage: whether the controller relies on softened constraints.

These metrics are chosen because they match the paper's evaluation style and also reveal practical problems in reproduction.

## 11. What is novel or valuable in your current work?

### Short Answer

The current value is mainly in building a working reproduction pipeline, adding systematic evaluation and debugging, and preparing a foundation for further algorithmic extensions.

### Expanded Answer

At the current stage, I would not claim a major new algorithm yet. The main contribution so far is reproduction-oriented:

- I built a complete CARLA intersection pipeline in my repository.
- I connected scenario execution, prediction, SMPC control, video output, logging, and automatic metrics.
- I added detailed diagnostics for solver failure, completion validity, reference tracking, and slack usage.
- I reproduced the main policy comparison structure of the paper.
- I identified specific gaps between the current implementation and a faithful final reproduction.

This is important because it moves the project from reading and planning into an executable experimental platform.

## 12. What is the difference between variable-risk, fixed-risk, and open-loop SMPC?

### Variable-Risk SMPC

Variable-risk SMPC is closest to the proposed method in the paper. It allows risk to be allocated differently across modes and time steps, so the controller can be less conservative where risk is lower and more cautious where risk is higher.

### Fixed-Risk SMPC

Fixed-risk SMPC is an ablation baseline. It uses a more fixed or uniform risk allocation rather than optimising how risk should be distributed. This helps test whether variable risk allocation actually improves performance.

### Open-Loop SMPC

Open-loop SMPC is a weaker ablation baseline. It does not exploit feedback in the same way as the closed-loop policy. It is useful for showing why feedback policies matter under multimodal uncertainty.

In my current implementation, the open-loop version required additional softening through collision slack, so it needs to be interpreted carefully.

## 13. What problems have you found?

### Short Answer

The main problems are path deviation, occasional solver infeasibility, and the interpretation of the softened open-loop baseline.

### Expanded Answer

The first issue is that the closed-loop SMPC policies can complete the task, but their path deviation is still larger than expected. This suggests that reference tracking and linearisation may need further tuning.

The second issue is occasional solver failure, especially in the variable-risk setting. Some failures appear as `INF_OR_UNBD`, which may indicate tight constraints, numerical issues, or difficult geometry around the predicted target vehicle.

The third issue is open-loop SMPC. The latest open-loop version can complete the task, but it relies on collision slack. This makes it useful for diagnosis, but I should not present it as a fully strict reproduction of the original hard-constraint open-loop baseline.

## 14. How close are you to the original paper?

### Short Answer

The experimental direction and pipeline are aligned with the original paper, but I have not yet fully reproduced the paper's final quantitative results.

### Expanded Answer

The project follows the same high-level structure as the original paper: CARLA intersection, multimodal target-vehicle prediction, risk-aware SMPC, and policy comparisons.

However, there are still differences. My current results are based on a small pilot rather than the full evaluation scale. Some engineering modifications have been added for debugging and stability, such as stricter completion diagnostics and open-loop collision slack. The path-deviation values also need improvement before claiming quantitative agreement with the paper.

Therefore, I would describe the current state as a working preliminary reproduction pipeline, not a final faithful reproduction.

## 15. What do you want to do beyond the paper?

### Short Answer

Beyond reproduction, I am considering probability calibration and uncertainty-aware dynamic risk adjustment.

### Expanded Answer

One possible extension is mode-probability calibration. Since the SMPC controller relies on predicted mode probabilities, unreliable probabilities may lead to poor risk allocation. Calibrating these probabilities could make the risk-aware controller more reliable.

Another possible extension is entropy-aware dynamic risk thresholding. If the prediction model is very uncertain and gives similar probabilities to several modes, the controller could become more cautious. If the prediction is clear, the controller could behave less conservatively.

These extensions are still planned future work. I will only implement them after the reproduction baseline is stable enough.

## 16. Why are these extensions reasonable?

### Short Answer

They directly address the reliability of prediction probabilities, which is important because risk allocation depends on them.

### Expanded Answer

The original method assumes that multimodal probabilities are useful for allocating risk. However, in real prediction models, probabilities may be miscalibrated or uncertain. If the controller trusts unreliable probabilities too much, it may underestimate dangerous low-probability events or become too aggressive.

Therefore, probability calibration and uncertainty-aware risk thresholds are natural extensions. They keep the same overall framework but improve the way prediction uncertainty is used by the controller.

## 17. What are your next steps?

### Short Answer

My next steps are to improve tracking behaviour, reduce solver failures, separate strict and softened open-loop baselines, and then scale up the evaluation.

### Expanded Answer

The next steps are:

1. Tune tracking and reference handling to reduce path deviation.
2. Investigate variable-risk solver failures, especially `INF_OR_UNBD` cases.
3. Keep the softened open-loop version for diagnostics but also preserve a strict open-loop baseline for fair comparison.
4. Run larger experiments after the five-initialisation pilot becomes stable.
5. Conduct parameter ablation studies on risk threshold, horizon length, time step, and safety distance.
6. If time allows, test probability calibration or entropy-aware risk thresholding.

## 18. What experiments will provide enough evidence?

### Short Answer

I need larger-scale evaluation across more initial conditions and parameter settings, with consistent metrics for safety, feasibility, progress, and comfort.

### Expanded Answer

Evidence should come from:

- Multiple initial conditions, not just one.
- Several policy variants under the same scenarios.
- Repeated comparison against no-target and fixed-risk baselines.
- Metrics showing safety, task completion, computation time, and smoothness.
- Ablation studies showing whether risk threshold, prediction horizon, and control time step affect performance.

If variable-risk SMPC consistently improves safety or feasibility compared with fixed-risk and open-loop baselines, that would support the hypothesis.

## 19. What could go wrong?

### Short Answer

The main risks are CARLA instability, solver infeasibility, long experiment time, and not achieving close quantitative agreement with the paper.

### Expanded Answer

CARLA and GPU-based simulation can be unstable or slow. To reduce this risk, I first run small pilot experiments before scaling up.

SMPC can become infeasible under difficult constraints. To handle this, I save detailed debug logs, including solver status, failure steps, reference information, and slack usage.

The experiments can be time-consuming. Therefore, I scale gradually from one initial condition to five, then to larger settings.

Finally, the reproduction may not perfectly match the original paper. If that happens, I will clearly explain the implementation differences, report the gaps, and focus on systematic analysis rather than over-claiming.

## 20. If the supervisor asks: "What is your main contribution?"

### Suggested Answer

At the current stage, my main contribution is the construction and validation of a reproduction pipeline for risk-aware SMPC with multimodal predictions in CARLA. I have integrated scenario execution, prediction, SMPC control, logging, video output, and automatic evaluation. I have also identified the key remaining issues, especially path deviation, solver stability, and the strictness of the open-loop baseline.

The final contribution should include a faithful reproduction, a structured evaluation across multiple settings, and potentially a small extension related to uncertainty-aware risk adjustment.

## 21. If the supervisor asks: "What is the hypothesis?"

### Suggested Answer

My hypothesis is that using multimodal prediction with risk-aware SMPC should allow the ego vehicle to make safer and more reliable decisions at intersections than simpler baselines that either ignore target vehicles, use fixed risk allocation, or use open-loop planning.

I plan to test this by comparing completion, solver feasibility, minimum distance to the target vehicle, path deviation, solve time, and comfort metrics across different initial conditions.

## 22. If the supervisor asks: "What is your innovation?"

### Suggested Answer

At this stage, I would separate reproduction from innovation. The current work is mainly a reproduction and validation effort. The innovation I am considering beyond the paper is to make the risk allocation more aware of prediction reliability, for example through probability calibration or entropy-aware dynamic risk thresholds.

This would extend the original idea by not only using mode probabilities, but also considering how reliable or ambiguous those probabilities are.

## 23. If the supervisor asks: "Why not use a simpler method?"

### Suggested Answer

A simpler method may work if the target vehicle follows a predictable path. However, at intersections, the target vehicle may have several plausible future behaviours. A single-trajectory planner can be over-confident, while a very conservative robust planner may stop unnecessarily.

SMPC is useful because it provides a structured way to balance safety and progress under uncertainty.

## 24. If the supervisor asks: "How will you know whether it works?"

### Suggested Answer

I will compare it against baselines under the same scenarios. If the risk-aware SMPC achieves valid completion, maintains a safer distance to the target vehicle, keeps high solver feasibility, and does not become too slow or too conservative, then it provides evidence that the method is working.

I will also compare path deviation and comfort metrics, because simply reaching the goal is not enough if the vehicle deviates too much or uses unrealistic control actions.

## 25. If the supervisor asks: "What is your final dissertation story?"

### Suggested Answer

The dissertation story is:

1. Autonomous vehicles must make decisions under uncertain future behaviour of other road users.
2. Multimodal prediction models can represent several possible futures, but prediction alone is not enough.
3. Risk-aware SMPC provides a way to convert these uncertain predictions into safe control actions.
4. I reproduce the CARLA intersection experiment to evaluate this idea.
5. I compare variable-risk SMPC, fixed-risk SMPC, open-loop SMPC, and no-target baselines.
6. I analyse safety, feasibility, progress, comfort, and path deviation.
7. If time allows, I extend the work by making risk adjustment more aware of prediction uncertainty.

## 26. One-Minute Meeting Summary

I am working on autonomous driving decision-making under uncertainty. The problem is that other vehicles may have several possible future behaviours, especially at intersections, and a self-driving car needs to make safe decisions without becoming overly conservative.

My current work reproduces a paper that combines multimodal target-vehicle prediction with risk-aware stochastic MPC. I have built the CARLA intersection pipeline, connected prediction, SMPC control, logging, video output, and automatic evaluation. I have run a small multi-initialisation pilot comparing no-target baselines, variable-risk SMPC, fixed-risk SMPC, and open-loop SMPC.

The main closed-loop SMPC controllers can now complete the task, which shows that the reproduction pipeline is working. However, the results are still preliminary. I need to reduce path deviation, improve solver stability, and carefully separate strict open-loop results from softened diagnostic results.

Beyond reproduction, I am considering extensions such as probability calibration and entropy-aware risk adjustment, so that the controller can respond not only to predicted probabilities but also to how uncertain those probabilities are.

## 27. Two-Minute Meeting Summary

My project studies autonomous driving decision-making under uncertainty. I focus on a CARLA intersection scenario where an ego vehicle needs to cross safely while a target vehicle has uncertain future motion. The key difficulty is that the target vehicle may follow several possible trajectories, so planning with only one predicted future can be unsafe or over-confident.

The main paper I am reproducing proposes risk-aware stochastic MPC with multimodal predictions. The prediction model gives a Gaussian mixture representation of the target vehicle's future motion, including mode probabilities, mean trajectories, and covariance. The SMPC controller then uses this information inside chance constraints and risk allocation to compute safe control actions.

So far, I have built a complete reproduction pipeline in my repository. It includes CARLA scenario execution, multimodal prediction, SMPC control, video output, debug logging, and automatic paper-style metrics. I have also run a small multi-initialisation pilot with five initial conditions and five policies: no-target baseline, no-target closed-loop baseline, variable-risk SMPC, fixed-risk SMPC, and open-loop SMPC.

The current results show that the pipeline works and the main closed-loop SMPC controllers can complete the intersection task. However, there are still important issues. The path deviation is larger than expected, variable-risk SMPC has occasional solver failures, and the open-loop baseline currently uses collision slack, so it should be interpreted carefully.

My next steps are to improve tracking and solver stability, run larger-scale evaluations, conduct parameter ablations, and potentially explore uncertainty-aware risk adjustment as an extension beyond the original paper.

