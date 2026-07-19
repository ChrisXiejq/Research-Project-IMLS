# Phase-Aware Adaptive Risk SMPC 论文初版大纲

## 1. 论文暂定题目

中文题目候选：

```text
面向无信号交叉口让行场景的相位感知自适应风险随机模型预测控制方法
```

英文题目候选：

```text
Phase-Aware Adaptive Risk Allocation for Stochastic Model Predictive Control in Unsignalised Give-Way Intersections
```

## 2. 当前论文定位

本文研究对象是 CARLA 中右侧通行无信号让行交叉口场景：

- ego vehicle, EV：从支路或让行方向进入交叉口，并左转穿越 oncoming target vehicle 的优先通行路径。
- target vehicle, TV：直行通过交叉口，拥有优先路权。
- 任务目标：EV 必须遵守让行规则，避免车辆 footprint 碰撞，完成左转并自然进入正确车道。

本文不再主张“adaptive risk 单独让车辆安全停车”。当前更准确的系统定位是：

```text
rule-aware supervisor + phase-aware adaptive-risk SMPC
```

其中：

- rule-aware supervisor 负责交通规则约束、紧急安全兜底和最终 footprint safety。
- phase-aware adaptive risk 作用在 SMPC 优化层，根据交互相位和 conflict-zone distance 调整 chance constraint 的保守程度。
- fixed-static risk 作为公平 baseline，用于验证 adaptive risk 是否真的改变 solver 层风险配置。

## 3. 核心论点

本文核心论点可以写成：

```text
在无信号让行交叉口中，仅使用固定风险水平的 SMPC 难以同时表达“冲突前保守”和“目标车清空后放松”这两种交互需求。本文提出 phase-aware adaptive risk allocation，在 target clearance 前对 approach/critical/near conflict phases 施加更高风险收紧，在 target clearance 后自动降低风险保守性。实验表明，该机制在保持 rule-aware safety gate 通过的同时，使 solver nominal layer 呈现更符合让行逻辑的风险调节行为。
```

需要特别注意论文表述边界：

- 可以写：adaptive risk 改变 solver nominal behaviour、chance constraint tightening 和 planned acceleration。
- 可以写：supervisor 保证最终 safety，adaptive risk 负责优化层交互行为塑形。
- 不建议写：adaptive risk alone makes the vehicle yield safely。
- 不建议写：adaptive risk 在所有最终轨迹安全指标上显著优于 fixed risk。当前 10-init 数据显示两者最终 safety 接近。

## 4. 研究问题与假设

### 4.1 研究问题

RQ1：在无信号让行交叉口中，如何将 conflict-zone interaction phase 映射为 SMPC chance constraint 的风险保守程度？

RQ2：与 fixed-static risk 相比，phase-aware adaptive risk 是否能在 target clearance 前产生更保守的 solver nominal 行为？

RQ3：target clearance 后，adaptive risk 是否能自动放松，避免全程保持固定高保守性？

RQ4：在 rule-aware supervisor 存在的安全架构下，adaptive risk 的贡献应如何被公平测量和解释？

### 4.2 实验假设

H1：在 pre-clearance critical phase，`smpc_var_risk` 的 solver risk tightening 应高于 `smpc_fixed_risk`。

H2：在 post-clearance critical/near phase，`smpc_var_risk` 的 solver risk tightening 应低于 `smpc_fixed_risk`。

H3：phase-aware adaptive risk 不应引入额外不稳定性；即 solver failure、footprint collision、yield violation 不应劣化到 gate failure。

H4：由于 rule-aware supervisor 仍会在关键阶段覆盖最终控制，adaptive risk 的主要贡献应通过 solver nominal control、risk allocation 和 phase-bucket diagnostics 体现，而不是只看 final applied trajectory。

## 5. 方法设计

### 5.1 总体架构

方法由三层组成：

1. Stochastic MPC planner
2. Phase-aware adaptive risk allocation
3. Rule-aware yield supervisor

SMPC 负责生成名义控制序列；adaptive risk 根据交互状态改变 chance constraint 的 tightening；supervisor 在必要时覆盖最终加速度，确保让行规则和碰撞安全。

### 5.2 SMPC 与 chance constraint

SMPC 使用 target prediction 和 collision chance constraints 来规划 EV 控制。风险水平通过 solver 内部的 tightening / target probability 体现：

```text
risk_tightening
risk_target_prob
```

fixed-static baseline 保持固定：

```text
fixed risk tightening ~= 1.64
fixed target probability ~= 0.9495
```

adaptive-variable policy 根据 phase-aware mapping 更新 solver risk。

### 5.3 Phase-aware adaptive risk allocation

当前实现策略：

```text
target not cleared:
  approach phase: risk_tightening floor = 1.68
  critical phase: risk_tightening floor = 1.80
  near phase:     risk_tightening floor = 1.85

target cleared / released recovery:
  relaxed risk_tightening = 1.2815515655446004
```

Conflict-distance buckets：

| bucket | 条件 |
| --- | --- |
| far | `dconf > 25 m` |
| approach | `15 m < dconf <= 25 m` |
| critical | `5 m < dconf <= 15 m` |
| near | `dconf <= 5 m` |

设计意图：

- pre-clearance：EV 尚未确认 TV 清空冲突区，因此提高 chance constraint 保守性。
- post-clearance：TV 已清空冲突区，继续使用高风险收紧会导致不必要保守，因此放松到较低 tightening。
- fixed risk：保持全程固定，用于公平对照。

### 5.4 Rule-aware supervisor

Supervisor 保留在系统中，原因是论文场景是交通规则敏感场景，不能只依赖优化器在所有初始条件下自然学会让行。

Supervisor 主要承担：

- 检测 TV 是否拥有优先通行权。
- 判断 EV 是否应等待 target clearance。
- 在关键阶段进行 braking / hard stop / emergency override。
- 保证最终 trajectory 通过 footprint collision gate 和 yield gate。

这意味着最终控制可能由 supervisor 主导。因此本文必须同时报告：

- solver nominal acceleration before override
- final applied acceleration after override
- supervisor override fraction
- hard-stop override fraction
- risk tightening by phase

## 6. 实验设计

### 6.1 场景

场景文件：

```text
scenario_uk_give_way.json
```

当前主线配置：

| 项目 | 当前值 |
| --- | --- |
| TV speed | `9.0 m/s` |
| yield hard stop target distance | `12.0 m` |
| yield hard stop conflict distance | `13.0 m` |
| yield stop buffer distance | `7.0 m` |
| yield caution decel | `-4.0 m/s^2` |
| yield reference decel | `-3.75 m/s^2` |
| yield stop decel | `-5.0 m/s^2` |
| yield emergency decel | `-7.0 m/s^2` |

### 6.2 对照策略

主实验只比较两类 SMPC policy：

| policy | 含义 |
| --- | --- |
| `smpc_var_risk` | phase-aware adaptive-variable risk |
| `smpc_fixed_risk` | fixed-static risk baseline |

Open-loop 不作为主比较，因为该场景的核心是闭环让行和交互安全；open-loop 容易产生不自然轨迹，不能直接证明 adaptive risk 的贡献。

### 6.3 实验阶段

| 阶段 | 结果目录 | 作用 | 当前状态 |
| --- | --- | --- | --- |
| single-init sanity check | `20260707_193121_final_dissertation` | 验证 phase-aware floor 单 init 生效 | 已完成 |
| 5-init precheck | `20260707_195935_5init_phase_floor_final_dissertation` | 验证机制小规模稳定性 | 已完成 |
| 10-init precheck | `20260707_221143_10init_phase_floor_final_dissertation` | 扩大初始条件覆盖 | 已完成 |
| 50-init full experiment | `20260710_164024_50init_phase_floor_final_dissertation` | 最终论文主结果 | 已完成，100/100 required SMPC rollouts PASS |

当前 50-init 主实验已经冻结为论文主结果，不建议继续通过调参替换该节点。后续工作应优先围绕该节点生成论文图表、结果分析和有限机制消融。

### 6.4 指标体系

Safety / rule metrics：

- `PASS` ratio
- footprint collision
- minimum center distance
- minimum footprint separation
- yield rule satisfaction
- completion

Solver / optimization metrics：

- solver failure fraction
- average solve time
- feasibility percentage
- collision slack
- solver slack

Adaptive risk diagnostics：

- risk tightening mean/max by bucket
- target probability by bucket
- pre-clearance vs post-clearance
- floor applied fraction
- nominal acceleration before override
- final acceleration after override
- supervisor override fraction

Paper-facing trajectory metrics：

- completion time
- max lateral acceleration
- longitudinal jerk
- lateral jerk
- `dmin_TV`
- Hausdorff distance to `notv` reference, when `notv` reference exists

## 7. 当前已有结果

### 7.1 Safety gate 汇总

| 实验 | policy | pass | solver failure max | solver failure mean | center dmin min / mean (m) | footprint min / mean (m) | collision | yield ok |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1-init | fixed | 1/1 | 0.0000 | 0.0000 | 5.0458 / 5.0458 | 1.6776 / 1.6776 | False | True |
| 1-init | var | 1/1 | 0.0000 | 0.0000 | 5.0462 / 5.0462 | 1.6780 / 1.6780 | False | True |
| 5-init | fixed | 5/5 | 0.0000 | 0.0000 | 4.8741 / 5.7175 | 1.4717 / 2.5439 | False | True |
| 5-init | var | 5/5 | 0.0000 | 0.0000 | 5.0438 / 5.7549 | 1.6750 / 2.5889 | False | True |
| 10-init | fixed | 10/10 | 0.0244 | 0.0064 | 4.7661 / 5.4145 | 1.3414 / 2.1561 | False | True |
| 10-init | var | 10/10 | 0.0244 | 0.0065 | 4.7166 / 5.4051 | 1.2774 / 2.1446 | False | True |

解释：

- 1/5/10-init 中 required policies 均通过 safety gate。
- 10-init 出现少量 solver failure，但 fixed 和 var 基本同步，且低于 gate threshold。
- footprint collision 均为 False，yield rule 均满足。
- 当前结果支持“adaptive risk 未破坏 safety/stability”，但不支持“adaptive risk 在所有最终 safety distance 上显著优于 fixed”。

### 7.2 Adaptive risk 机制证据

| 实验 | phase bucket | var - fixed tightening | floor applied delta | nominal accel delta | solver failure delta | 解释 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 1-init | approach / pre-clearance | +0.0400 | +1.0000 | -0.0026 | 0.0000 | approach 阶段 risk floor 生效 |
| 1-init | critical / pre-clearance | +0.1600 | +1.0000 | -0.3565 | 0.0000 | critical 阶段更保守 |
| 1-init | critical / post-clearance | -0.3584 | 0.0000 | -0.0006 | 0.0000 | target cleared 后放松 |
| 1-init | near / post-clearance | -0.3584 | 0.0000 | +0.0016 | 0.0000 | target cleared 后放松 |
| 5-init | approach / pre-clearance | +0.0400 | +1.0000 | -0.0934 | 0.0000 | 小规模多初始条件中机制稳定 |
| 5-init | critical / pre-clearance | +0.1600 | +1.0000 | -0.3063 | 0.0000 | solver nominal acceleration 更保守 |
| 5-init | critical / post-clearance | -0.3584 | 0.0000 | +0.0061 | 0.0000 | clearance 后 adaptive risk 放松 |
| 5-init | near / post-clearance | -0.3584 | 0.0000 | +0.0040 | 0.0000 | clearance 后 adaptive risk 放松 |
| 10-init | approach / pre-clearance | +0.0400 | +1.0000 | -0.1065 | 0.0000 | approach floor 稳定生效 |
| 10-init | critical / pre-clearance | +0.1600 | +1.0000 | -0.3997 | 0.0000 | critical phase 中 var solver 更保守 |
| 10-init | near / pre-clearance | +0.2100 | +1.0000 | 0.0000 | 0.0000 | near pre-clearance 样本较少，但 floor 生效 |
| 10-init | critical / post-clearance | -0.3584 | 0.0000 | -0.0171 | 0.0000 | post-clearance 放松成立 |
| 10-init | near / post-clearance | -0.3584 | 0.0000 | -0.0003 | 0.0000 | post-clearance 放松成立 |

解释：

- H1 得到支持：pre-clearance critical 中 var risk tightening 高于 fixed。
- H2 得到支持：post-clearance critical/near 中 var risk tightening 低于 fixed。
- H3 得到初步支持：1/5/10-init 均未出现 safety gate failure。
- H4 得到支持：nominal acceleration delta 显示 solver 层行为发生变化，但 final trajectory 受 supervisor 影响较大。

## 8. 可写出的初步结论

当前数据可以支持以下结论：

1. Phase-aware adaptive risk allocation 能够稳定改变 solver risk mode。
2. 在 target clearance 前，adaptive risk 对 approach/critical/near phase 施加更高 tightening。
3. 在 target clearance 后，adaptive risk 自动放松到低于 fixed-static risk 的水平。
4. 1/5/10-init 中，该机制没有破坏 footprint safety、yield correctness 和 completion。
5. 由于 rule-aware supervisor 在关键阶段大量介入，最终轨迹差异不会像 solver nominal layer 那样明显。因此本文贡献应定位为“风险分配与名义规划行为改进”，而不是“完全替代规则监督器”。

不能直接写成的结论：

1. adaptive risk 在所有最终安全距离指标上都优于 fixed risk。
2. adaptive risk 单独保证让行。
3. 当前结果已经是最终统计显著性结论。
4. open-loop 是合理主 baseline。

## 9. 论文结构初稿

### Chapter 1 Introduction

内容：

- 无信号交叉口让行任务的重要性。
- SMPC 在不确定交互场景中的优势。
- 固定 risk allocation 的不足：无法区分 pre-clearance danger phase 和 post-clearance recovery phase。
- 本文提出 phase-aware adaptive risk allocation。

可写贡献：

1. 构建 CARLA 中右侧通行无信号 give-way intersection 的闭环 SMPC 实验框架。
2. 提出 phase-aware adaptive risk allocation，将 conflict-zone distance 和 target clearance phase 映射到 chance constraint tightening。
3. 设计 fixed-static risk 对照，保证 adaptive risk 贡献可测。
4. 提供 post-CARLA footprint safety gate 和 risk-by-conflict-distance diagnostics，用于解释 solver 层和 final control 层差异。

### Chapter 2 Background and Related Work

内容：

- Model Predictive Control
- Stochastic MPC and chance constraints
- Autonomous intersection handling
- Risk allocation in uncertain planning
- Rule-aware fallback / safety supervisor

与原 SMPC paper 的关系：

- 原 SMPC 更关注不确定预测下的 collision avoidance 和轨迹优化。
- 本文创新点不是重新发明 SMPC，而是针对无信号让行场景引入 phase-aware risk scheduling。
- 本文强调交互阶段：target not cleared vs target cleared。

### Chapter 3 Problem Formulation

内容：

- 无信号交叉口几何。
- EV/TV dynamics。
- Right-hand-traffic left-turn give-way rule。
- Conflict zone / distance-to-conflict 定义。
- Target clearance condition。
- Safety objectives：
  - no footprint collision
  - target clears before ego enters conflict zone
  - completion and lane alignment

### Chapter 4 Methodology

内容：

1. SMPC controller
2. Multimodal target prediction
3. Chance constraint tightening
4. Fixed-static risk baseline
5. Phase-aware adaptive risk mapping
6. Rule-aware yield supervisor
7. Debug and evaluation instrumentation

建议放一个系统图：

```text
Perception / state
  -> target prediction
  -> yield phase estimator
  -> adaptive risk allocation
  -> SMPC optimization
  -> nominal control
  -> rule-aware supervisor
  -> final CARLA control
```

### Chapter 5 Experimental Setup

内容：

- CARLA 0.9.14
- Gurobi 11
- `carla_modern` environment
- scenario and init files
- policies：
  - `smpc_var_risk`
  - `smpc_fixed_risk`
- risk profile：
  - `adaptive_interaction_severity`
  - phase-aware pre-clearance floor
- evaluation pipeline：
  - `postcarla_trajectory_gate.py`
  - `risk_by_conflict_distance.py`
  - `compute_scenario_results.py`

实验分组：

| Experiment | Purpose |
| --- | --- |
| single-init sanity | mechanism sanity check |
| 5-init precheck | small-scale robustness |
| 10-init precheck | broader initial condition validation |
| 50-init full | final dissertation result |

### Chapter 6 Results

建议结果章节分三层：

#### 6.1 Safety and Rule Compliance

使用 safety gate 表格，说明：

- both policies pass
- no footprint collision
- yield rules satisfied
- completion satisfied

#### 6.2 Phase-Aware Risk Allocation

使用 phase bucket 表格和图：

- pre-clearance critical：var > fixed
- post-clearance critical/near：var < fixed
- floor applied fraction：var = 1, fixed = 0

#### 6.3 Solver Nominal Behaviour

重点报告：

- nominal acceleration before override
- final acceleration after override
- supervisor override fraction

解释：

```text
adaptive risk 改变 solver nominal action；
但 final action 受 supervisor safety override 约束，因此最终轨迹指标差异较小。
```

#### 6.4 Scaling Across Initial Conditions

当前可写 1/5/10-init；50-init 跑完后加入最终表。

### Chapter 7 Discussion

讨论点：

- 为什么 fixed risk 不能表达 phase transition。
- 为什么 post-clearance 放松是合理的。
- 为什么 supervisor 不是缺陷，而是 safety-critical autonomous driving 中必要的 rule-aware fallback。
- adaptive risk 的贡献如何与 supervisor 区分。
- 当前方法是否过于依赖人工设计 floor。

### Chapter 8 Limitations and Future Work

当前改进空间：

1. 50-init full experiment 尚未完成。
2. phase-aware floor 仍是 rule-based schedule，未来可以学习化或连续化。
3. 当前只覆盖单一 intersection scenario，未覆盖更多交通密度、速度组合和遮挡。
4. supervisor 对 final control 影响较强，未来可以进一步弱化 supervisor 或引入 soft rule constraints。
5. 当前 adaptive risk 的优势主要体现在 solver layer，最终轨迹效率提升有限。
6. 未做硬件在环、VIL 或真实车辆实验。
7. 未把 open-loop 作为主 baseline，因为其轨迹不适合作为该场景的公平对照。

### Chapter 9 Conclusion

初步结论草稿：

```text
This work presents a phase-aware adaptive risk allocation strategy for SMPC in an unsignalised give-way intersection. The proposed method increases chance-constraint conservatism before the priority target vehicle clears the conflict zone and relaxes the risk after clearance. CARLA experiments show that the adaptive-risk policy preserves rule compliance and footprint safety across single-init, 5-init, and 10-init evaluations, while producing a clear pre-clearance/post-clearance risk scheduling pattern that is absent in the fixed-static baseline. These results suggest that phase-aware risk allocation is a useful mechanism for shaping interaction-aware nominal planning behaviour under a rule-aware safety supervisor.
```

## 10. 论文图表清单

建议最终论文至少包含：

| 编号 | 图表 | 当前是否可生成 | 来源 |
| --- | --- | --- | --- |
| Fig. 1 | give-way intersection scenario diagram | 可生成/手绘 | CARLA map + scenario |
| Fig. 2 | controller architecture | 可画 | 方法章节 |
| Fig. 3 | phase-aware risk mapping curve/table | 可画 | `_adaptive_risk_allocation` |
| Fig. 4 | trajectory map var vs fixed | single-init 可生成 | `scenario_result.pkl` |
| Fig. 5 | risk tightening by clearance phase | 可生成 | `risk_by_conflict_distance_summary.csv` |
| Fig. 6 | nominal vs final acceleration | 可生成 | `smpc_debug_steps.jsonl` |
| Table 1 | experiment configuration | 已有 | batch config / tuning config |
| Table 2 | safety gate summary | 已有 50-init | `postcarla_trajectory_gate.json` |
| Table 3 | phase-aware risk comparison | 已有 50-init | `risk_by_conflict_distance_comparison.csv` |
| Table 4 | model-side fine-tuning metrics | 已有 | fixed test split evaluation |
| Table 5 | limitations / ablation summary | 可写 | discussion |

## 11. 下一步工作

短期已完成：

1. 50-init control-side frozen result 已完成。
2. 10-init phase-floor ablation 已完成。
3. CARLA prediction dataset collection 已完成。
4. MultiPath fine-tuning 和 same-test-set evaluation 已完成。
5. Fine-tuned predictor 50-init closed-loop validation 已完成。
6. 核心 graphical results 已生成。

接下来主要是写作整理：

1. 写 Methodology 和 Experimental Setup。
2. 写 Results 时严格区分：
   - solver risk layer
   - nominal control layer
   - final supervisor-controlled trajectory layer
3. 写 Discussion，解释 supervisor 的必要性、adaptive risk 的真实贡献，以及为什么 fine-tuning 的主要提升体现在模型侧。
4. 生成并筛选 bird's-eye 视频，用于 qualitative demonstration。

## 12. 当前 milestone 记录

完整 milestone 记录已合并到：

```text
docs/paper/current_project_status.md
```

当前最好 integrated milestone：

```text
core/results/20260718_104740_50init_finetuned_predictor_validation
```

该结果应作为当前最新版本：SMPC+Supervisor 是控制侧提升，fine-tuned MultiPath 是模型侧提升，二者组合形成当前最好验证结果。
