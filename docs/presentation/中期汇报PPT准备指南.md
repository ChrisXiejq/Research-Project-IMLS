# 中期汇报 PPT 准备指南

## 评分导向

根据模板和评分规则，PPT 应围绕 8 个核心问题展开：

| 模板页 | 高分要求 | 你的项目中应该突出什么 |
|---|---|---|
| Area of research | 研究领域清晰、范围聚焦 | 自动驾驶路口场景中的不确定预测与安全控制 |
| Problem | 问题明确，不要一上来讲方法 | 其它车辆未来行为不确定，自动驾驶车既要安全避让又要顺利通过路口 |
| Significance | 说明现实影响 | 路口是事故高发场景；过于保守会堵车，过于激进会危险 |
| State of the art | 批判性说明已有方法不足 | 传统 MPC 假设预测较确定；学习预测能给多种未来，但控制器如何利用不确定性仍是难点 |
| Hypothesis | 可测试，并说明成功/失败边界 | 使用多模态预测 + 风险约束 SMPC，应比开环/固定风险策略更安全、更稳定 |
| Execution plan | 步骤具体，实验与假设对应 | 先复现 CARLA intersection，再比较 no-TV、fixed-risk、variable-risk、open-loop |
| Risk analysis | 风险、影响、备用方案明确 | CARLA/Gurobi 环境、SMPC 不可行、轨迹偏离、全量实验耗时 |
| Communication | 浅显、少公式、多图 | 面向非专业老师，用图解释，不展示代码和复杂公式 |

## 建议时间控制

如果总时长是 10 分钟，建议按下面控制：

| 时间 | 内容 |
|---:|---|
| 0:00-0:45 | 标题 + 一句话说明项目 |
| 0:45-2:00 | 研究领域、问题和意义 |
| 2:00-3:20 | 现有方法和论文核心思想 |
| 3:20-4:40 | 你的复现实验流程 |
| 4:40-6:20 | 当前 preliminary results |
| 6:20-7:30 | 当前问题和调试进展 |
| 7:30-8:50 | 后续实验计划 |
| 8:50-10:00 | 风险分析 + 总结 |

原则：每页 45-75 秒，不要超过 10 页。

## 推荐 PPT 结构

### 1. Title

标题建议：

`Reproducing Risk-Aware Stochastic MPC for Autonomous Driving at Intersections`

页面内容：
- 姓名、学生号、项目名称、导师。
- 一句话 subtitle：`Using CARLA simulation to study safe autonomous driving under uncertain multimodal predictions.`

讲述重点：
- “我的项目关注自动驾驶车在路口遇到不确定其它车辆行为时，如何安全且不太保守地决策。”

### 2. Area of Research

页面图示：
- 放一个简单路口示意图：ego vehicle + target vehicle + possible future paths。

页面文字：
- Autonomous driving decision-making.
- Uncertain prediction of other road users.
- Risk-aware model predictive control.
- CARLA simulation-based evaluation.

讲述重点：
- 不要先讲 SMPC 公式。
- 先说人能理解的问题：其它车可能直行、转弯、减速，自动驾驶车必须提前考虑这些可能性。

### 3. Problem

页面图示：
- 左边：只有一条预测轨迹，控制器容易过于自信。
- 右边：多条可能未来轨迹，控制器需要权衡风险。

页面文字：
- Future motion of other vehicles is uncertain.
- A controller must avoid collisions without becoming unnecessarily conservative.
- The challenge is to convert uncertain predictions into safe control actions.

讲述重点：
- 问题不是“怎么跑 CARLA”，而是“如何把不确定预测用于安全控制”。

### 4. Significance

页面图示：
- 一个三角关系图：Safety / Efficiency / Comfort。

页面文字：
- Intersections are complex and safety-critical.
- Over-confident planning may be unsafe.
- Over-conservative planning may stop or block traffic.
- A good controller should balance safety, progress, and comfort.

讲述重点：
- 面向非专业老师：把它解释成“既不能冒险，也不能一直犹豫不走”。

### 5. State of the Art and Paper Idea

页面图示：
- 使用 `docs/architecture/SMPC.png` 或简化版流程图。

页面文字：
- Multimodal prediction gives several possible futures.
- SMPC uses these predictions inside a constrained optimisation problem.
- Variable risk allocation adapts how much risk is assigned to different future modes.

讲述重点：
- 只讲概念，不讲公式。
- 可以这样说：论文的核心思想是“预测不是一条线，而是一组可能性；控制器要用概率和风险约束来做决定。”

### 6. My Experimental Pipeline

页面图示：
- 使用 `docs/architecture/Experiment Flow.png`。
- 或者画一个更简单流程：

```text
Scenario JSON
  -> CARLA intersection simulation
  -> multimodal prediction
  -> SMPC controller
  -> vehicle action
  -> logs / video / metrics
```

页面文字：
- Ported and adapted the original experiment to my repository.
- Running CARLA 0.9.14 intersection scenarios.
- Added automatic logging, videos, debug files, and paper-style metrics.

讲述重点：
- 强调你已经搭好了完整实验链路，而不是只读论文。

### 7. Preliminary Results

页面图示：
- 用表格，不要堆太多曲线。

推荐表格：

| Policy | Meaning | Steps | Feasibility | Outcome |
|---|---|---:|---:|---|
| No-TV | No target vehicle baseline | 118 | 1.000 | Completed |
| No-TV-CL | Closed-loop no-TV baseline | 120 | 1.000 | Completed |
| Variable-risk SMPC | Main risk-aware method | 150 | 1.000 | Valid completion |
| Fixed-risk SMPC | Ablation baseline | 154 | 1.000 | Valid completion |
| Open-loop SMPC | Weaker ablation | 600 | 0.743 | Not completed |

可补充一句：
- Risk-aware closed-loop SMPC is now solver-feasible and reaches valid path-end completion; the open-loop ablation remains unstable.

讲述重点：
- 不要说“完全复现成功”。
- 要说“已有 preliminary results，baseline 成功，闭环 risk-aware SMPC 主线已经有效完成，但还需要更多初始条件验证；open-loop 仍在调试。”

### 8. Current Findings and Debug Progress

页面图示：
- 一张“Before vs After”表或箭头图。

推荐内容：

| Stage | Observation | Fix |
|---|---|---|
| Initial run | SMPC appeared infeasible at step 0 | Added solver/debug logging and fixed post-processing error |
| Later run | SMPC feasible but drifted off-route for 600 steps | Restored reference and fixed mode indexing |
| Latest run | Variable/fixed-risk SMPC reaches valid path-end completion | Tightened completion rule and earlier reference recovery |
| Remaining issue | Open-loop still runs 600 steps with low feasibility | Ongoing debugging of open-loop infeasibility/fallback |

讲述重点：
- 这页很重要，能证明你在系统性调试。
- 对非专业老师说：“我现在已经把问题从环境/求解错误，推进到控制性能调优问题。”

### 9. Execution Plan

页面图示：
- 时间线：Now -> Next 2 weeks -> Final stage。

推荐内容：
- Short term: diagnose and stabilise the open-loop ablation.
- Medium term: run a small multi-initialisation pilot before full-scale evaluation.
- Evaluation: safety distance, completion time, feasibility, solve time, comfort metrics.
- Final output: thesis-ready tables, plots, and videos.
- Parameter ablation: risk threshold, prediction horizon, control time step, and EV safety distance.
- Future algorithmic extensions: mode-probability calibration and entropy-aware dynamic risk thresholding.

讲述重点：
- 对应评分规则，计划要“可执行、分步骤、和假设对应”。
- 把复现工作和扩展工作分开讲：当前阶段重点是可信复现，扩展方向作为 future work，不要让评审误以为已经全部实现。

建议时间线：

| Stage | Main work | Output |
|---|---|---|
| Now | Finish valid reproduction of the intersection scenario | Reliable SMPC runs, videos, automatic metrics |
| Next | Run ablation studies | Tables for risk threshold, prediction horizon, time step, safety distance |
| Later | Explore algorithmic extensions | Calibration or entropy-aware risk allocation if literature and time support it |

可放在 Slide 9 的英文表述：
- `Primary goal: complete a faithful reproduction of the CARLA intersection experiment.`
- `Evaluation goal: generate thesis-ready metrics for safety, progress, feasibility, solve time, and comfort.`
- `Extension goal: investigate whether calibrated prediction probabilities or uncertainty-aware risk thresholds can improve robustness.`

## 9b. Future Work Beyond Reproduction

这部分可以放在 Slide 9 的右侧，或单独作为一小块，不建议单独占一整页，除非导师特别关心创新点。

推荐内容：

| Direction | Simple explanation | Why it may help | Current status |
|---|---|---|---|
| Mode-probability calibration | Adjust MultiPath mode probabilities after prediction | More reliable probabilities may improve risk allocation | Future work |
| Entropy-aware dynamic risk thresholding | Make risk threshold depend on prediction uncertainty | More cautious when prediction is uncertain, less conservative when prediction is clear | Future work |
| Parameter ablation | Vary risk threshold, horizon, time step, safety distance | Shows how sensitive the controller is | Planned evaluation |

讲述重点：
- 这几项是“复现完成后的扩展方向”，不是当前 preliminary results 的核心。
- 可以说：`These are planned extensions after the reproduction baseline is stable.`
- 不要承诺一定全部完成；更稳妥的说法是：`I will evaluate their feasibility with literature support and available time.`

### 10. Risk Analysis and Summary

页面图示：
- 风险表格。

推荐表格：

| Risk | Impact | Mitigation |
|---|---|---|
| CARLA/GPU instability | Experiments fail or are slow | Use AutoDL setup guide and small-matrix tests first |
| Gurobi/SMPC infeasibility | Controller cannot run | Save solver status and first-failure debug files |
| Off-route behaviour | Result not valid | Tighten completion criteria and improve reference tracking |
| Full evaluation cost | Limited time | Start with single scenario, then scale to more initialisations |

最后一句总结：
- `The reproduction pipeline is operational and preliminary results have been obtained. The next step is to improve lateral tracking and scale up the evaluation to produce thesis-ready results.`

## 图片建议

| 图片 | 用在哪页 | 路径 |
|---|---|---|
| 实验流程图 | Slide 6 | `docs/architecture/Experiment Flow.png` |
| SMPC 管线图 | Slide 5 | `docs/architecture/SMPC.png` |
| CARLA AVI 截图 | Slide 2 或 7 | 从最新 `carla_sim.avi` 截一帧 |
| 策略结果表 | Slide 7 | 使用当前 preliminary results |
| Before/After 调试表 | Slide 8 | 自制表格即可 |
| 未来计划时间线 | Slide 9 | 自制简单横向时间线 |

## 风格建议

- 每页只讲一个核心点。
- 每页最多 3-4 个 bullet。
- 不放代码。
- 不放复杂公式。
- 避免直接说 `CasADi Opti conic`, `SOC constraint`, `joint mode indexing` 等术语，除非一句话解释。
- 多用“car sees several possible futures”这种浅显比喻。
- 结果要诚实：说 preliminary，不说 final reproduction。

## 推荐开场白

`My project investigates how an autonomous vehicle can safely cross an intersection when the future behaviour of another vehicle is uncertain. Instead of assuming one predicted future, I reproduce a method that considers multiple possible futures and uses risk-aware model predictive control to choose safe actions.`

## 推荐结束语

`So far, I have built a working CARLA reproduction pipeline and obtained preliminary results. The baselines complete the intersection, and risk-aware SMPC is now solver-feasible and reaches near the goal. The main remaining work is to reduce lateral tracking error, stabilise the open-loop ablation, and scale the evaluation to more scenarios.`
