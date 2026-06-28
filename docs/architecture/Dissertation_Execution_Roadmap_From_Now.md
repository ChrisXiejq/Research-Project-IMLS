# From Current Result to Dissertation: Execution Roadmap

本文档定义从当前实验结果到毕业论文完成的完整执行计划。当前不再以盲目调参为主，而是围绕论文证据链做少量有目的的 ablation、结果整理、图表生成和章节写作。

## 1. 当前状态

当前主结果候选：

```text
core/results/20260627_212618_final_dissertation
```

当前结论：

- `smpc_fixed_risk` 和 `smpc_var_risk` 都通过 required post-CARLA gate。
- 两个 required SMPC policy 都满足：
  - `solver_failure_frac = 0.000`
  - `footprint_collision = False`
  - `completion_valid = True`
  - `target_clears_before_ego_enters = True`
- `smpc_open_loop` 不碰撞，但违反 give-way order，因此可以作为“collision avoidance alone is not enough”的关键 baseline。
- 视频视觉上可接受，因此不再继续改 `+2.75m` 起点和 `8.0m` 等待线，除非后续发现硬性错误。

当前 final method 配置应冻结：

```text
ego start_left_offset = +2.75
yield_stop_buffer_distance = 8.0
yield_release_clearance_margin = 1.0
risk_profile = adaptive_interaction_severity
deterministic approach/hold bypass
bounded 16-frame recovery-handoff bypass
```

## 2. 论文主张

建议论文主张：

```text
Rule-aware SMPC with conflict-zone interaction-severity adaptive risk allocation can produce traffic-rule-compliant give-way behaviour in a CARLA unsignalised intersection scenario. Compared with a non-rule-aware open-loop SMPC baseline, the method preserves collision safety while also satisfying priority order. Compared with earlier fixed or static risk settings, the method provides an interpretable mechanism for tightening risk during high-severity conflict-zone interaction and relaxing it after the priority vehicle clears.
```

中文表述：

```text
原始 SMPC 可以处理预测不确定性和碰撞约束，但在无信号交叉口让行场景中，单纯几何避碰不足以保证交通规则正确。本文引入 rule-aware supervisory layer，并基于 conflict-zone interaction severity 自适应调整 risk allocation，使 ego vehicle 在左转让行场景中同时满足安全、完成、让行顺序和求解稳定性要求。
```

## 3. 总体执行阶段

| 阶段 | 目标 | 主要产出 | 是否必须 |
|---|---|---|---|
| Phase 1 | 冻结 final method 和主结果 | final result analysis、配置记录、图表清单 | 必须 |
| Phase 2 | 做最小必要 ablation | 2-4 组对照实验结果 | 强烈建议 |
| Phase 3 | 生成论文图表 | result tables、paper panel、trajectory map、视频关键帧 | 必须 |
| Phase 4 | 写 Method 章节 | 算法流程、risk allocation 公式、rule-aware state machine | 必须 |
| Phase 5 | 写 Experiments / Results 章节 | 指标、对照、ablation、分析 | 必须 |
| Phase 6 | 写 Introduction / Related Work / Conclusion | 完整论文叙事 | 必须 |
| Phase 7 | 最终检查 | 可复现性、引用、图表编号、结果一致性 | 必须 |

## 4. Phase 1: 冻结 Final Method

### 目标

把 `20260627_212618_final_dissertation` 明确作为当前主结果，不再继续做无目标调参。

### 已完成材料

```text
docs/architecture/Final_Dissertation_Result_Analysis_20260627_212618.md
docs/architecture/Rule_Aware_Adaptive_Risk_SMPC_Dissertation_Plan.md
docs/architecture/Give_Way_SMPC_Experiment_Changelog.md
```

### 还需要做

1. 把主结果中的关键图复制或引用到论文素材目录。
2. 从视频中截取 4-5 个关键帧：
   - ego approaching yield line
   - ego holding upstream of conflict zone
   - target passing first
   - ego released and completing left turn
   - open-loop baseline violating yield order
3. 记录 final command 和环境：
   - CARLA 0.9.14
   - Gurobi 11
   - Conda `carla_modern`
   - `risk_profile=adaptive_interaction_severity`

### 停止条件

满足以下条件后停止调 final method：

- 视频视觉可接受。
- required policies pass gate。
- paper panel 成功生成。
- 论文需要的主要 metrics 已经整理。

当前已经满足。

## 5. Phase 2: 最小必要 Ablation 实验

下一步实验不要再围绕“让数值更好”做调参，而是回答论文问题：每个模块是否必要。

### Ablation A: Full Method

| 项目 | 内容 |
|---|---|
| Run | `20260627_212618_final_dissertation` |
| 目的 | 主方法结果 |
| 状态 | 已完成 |
| 论文用途 | Main result |

### Ablation B: No Adaptive Risk

| 项目 | 内容 |
|---|---|
| 改动 | 保留 rule-aware supervisor / bypass / final geometry，但把 `risk_profile` 改为 `rule_aware_static_risk` |
| 目的 | 验证 interaction-severity adaptive risk allocation 是否必要 |
| 预期 | 可能仍能完成，但风险收紧/放松缺少解释性；可能在 solver 或 clearance 上不如 full method |
| 优先级 | 高 |

建议命名：

```text
202606xx_no_adaptive_risk
```

实现方式：

```text
core/scripts/carla/run_give_way_no_adaptive_risk_ablation.sh
```

注意：不要直接用旧的 `upstream_code` profile 作为这个 ablation。旧 profile 会同时关闭 adaptive risk 和当前只为 rule-aware profiles 启用的 deterministic bypass，归因不干净。`rule_aware_static_risk` 才是干净的 no-adaptive-risk ablation：它保留 rule-aware supervisor / bounded bypass，只使用 static upstream risk。

### Ablation C: No Traffic-Policy Weighting

| 项目 | 内容 |
|---|---|
| 改动 | 保留 conflict-zone distance / TTC severity，但去掉 priority-rule contribution |
| 目的 | 验证 traffic policy 是否只是工程补丁，还是 severity score 的必要组成部分 |
| 预期 | 在接近冲突区时仍会变保守，但对“谁有优先权”的解释变弱 |
| 优先级 | 中高 |

如果代码改动成本高，可以先作为 documented ablation design，不一定必须跑完整 CARLA。

### Ablation D: No Bounded Recovery Handoff

| 项目 | 内容 |
|---|---|
| 改动 | 禁用 `deterministic_rule_yield_recovery_handoff`，保留 approach/hold bypass |
| 目的 | 说明 bounded recovery handoff 对 released_recovery solver stability 的作用 |
| 预期 | 可能复现 `20260627_194959` 的 recovery infeasibility |
| 优先级 | 中 |

这组可以用历史结果支持，不一定必须重复跑：

```text
20260627_194959:
  fixed-risk solver_failure_frac = 0.05172
  failures all in released_recovery
```

### Ablation E: Smaller Stop Buffer

| 项目 | 内容 |
|---|---|
| 改动 | 对比 `yield_stop_buffer_distance=6.25m` 与 `8.0m` |
| 目的 | 说明 hold-line footprint clearance 的必要性 |
| 预期 | `6.25m` 可能复现 hold 阶段 footprint collision |
| 优先级 | 中 |

可直接引用历史失败结果：

```text
20260627_205856_final_dissertation:
  fixed-risk footprint_collision = True
  collision_duration = 0.80s
  collision happened during hold_yield_line
```

### 推荐实际要跑的实验数量

最低要求：

```text
1. Full method: 已完成
2. No adaptive risk: 建议新跑
3. Open-loop baseline: 已在 full batch 中完成
```

更完整：

```text
1. Full method
2. No adaptive risk
3. No traffic-policy weighting
4. No bounded recovery handoff 或引用历史结果
5. Smaller stop buffer 或引用历史结果
```

## 6. Phase 3: 图表和结果材料

### 必须生成的表格

Table 1: Safety and Rule Compliance

```text
method
footprint_collision
center_dmin
min_footprint_separation
yield_order
completion_valid
solver_failure_frac
```

Table 2: Efficiency and Comfort

```text
method
completion_time
average_solve_time
max_lateral_acceleration
avg_longitudinal_jerk
avg_lateral_jerk
hausdorff_dist_notv
```

Table 3: Ablation Summary

```text
variant
removed_component
expected_role
observed_effect
conclusion
```

### 必须使用的图

| 图 | 文件 | 用途 |
|---|---|---|
| Main paper panel | `paper_panel.png` | 主实验综合图 |
| Trajectory map | `trajectory_map.png` | 展示路线、冲突区、让行顺序 |
| State machine diagram | 可新画 | 展示 `free_drive -> approach -> hold -> recovery` |
| Adaptive risk diagram | 可新画 | 展示 severity 与 risk tightening 的关系 |
| Video keyframes | 从 `carla_sim.avi` 截图 | 直观展示让行行为 |

### 图表原则

- 不要只报告 `PASS/FAIL`，要解释为什么。
- `smpc_open_loop` 的 WARN 是论文亮点，不是坏结果：它说明 baseline 可以避碰但不懂优先权。
- `notv` / `notv_cl` 不应被解释为交互安全 baseline，只能作为无目标参考轨迹 baseline。

## 7. Phase 4: Method 章节写作计划

建议 Method 章节结构：

```text
4.1 Problem Formulation
4.2 Original SMPC Baseline
4.3 Rule-Aware Give-Way Supervisor
4.4 Conflict-Zone Interaction Severity
4.5 Adaptive Risk Allocation
4.6 Deterministic Yield and Recovery Handoff
4.7 Implementation Details
```

### 必须写清楚的公式和逻辑

1. Conflict zone:

```text
conflict point
conflict radius
ego enter / exit time
target enter / exit time
target clears before ego enters
```

2. Interaction severity:

```text
distance to conflict zone
TTC / temporal overlap
priority relationship
yield phase
target clearance state
```

3. Adaptive risk allocation:

```text
high severity -> tighter chance constraint
target cleared -> relaxed risk
approach/hold -> conservative
recovery -> bounded relaxation
```

4. Rule-aware state machine:

```text
free_drive
cautious_approach_observed_target
approach_yield_line
hold_yield_line
released_recovery
```

5. Bounded bypass:

```text
Only deterministic rule-yield phases are bypassed.
Recovery handoff is bounded to 16 frames.
Normal driving still uses SMPC.
```

## 8. Phase 5: Experiments / Results 章节写作计划

建议 Experiments 章节结构：

```text
5.1 CARLA Scenario Setup
5.2 Baselines and Compared Methods
5.3 Evaluation Metrics
5.4 Main Result
5.5 Ablation Study
5.6 Failure Analysis and Design Lessons
```

### Baselines

| Baseline | 作用 |
|---|---|
| `notv` | 无目标理想参考 |
| `notv_cl` | 无目标闭环参考 |
| `smpc_open_loop` | 非 rule-aware baseline，展示不懂 give-way order |
| `smpc_fixed_risk` | rule-aware fixed-risk 对照 |
| `smpc_var_risk` | proposed adaptive/variable-risk method |

### Metrics

必须解释每个 metric 的意义：

- `footprint_collision`: 真实 footprint 安全，不只看中心距离。
- `center_dmin`: 与目标车中心的最小距离。
- `min_footprint_separation`: footprint 间最小间距。
- `yield_order`: target 是否先清空 conflict zone。
- `completion_time`: 完成效率。
- `solver_failure_frac`: 求解稳定性。
- `jerk / lateral acceleration`: 舒适性。
- `hausdorff_dist_notv`: 与无目标参考路线的偏离。

## 9. Phase 6: 写作顺序

不要从 Introduction 开始写。建议顺序：

1. Results
2. Experiments
3. Method
4. Related Work
5. Introduction
6. Conclusion
7. Abstract

原因：

- Results 和 Experiments 已经有数据，最容易落地。
- Method 可以围绕已经验证过的实现写，避免空泛。
- Introduction 最后写，可以反过来贴合真实贡献。

## 10. 论文时间安排

### Week 1: 固化结果和最小 ablation

目标：

- 跑或整理 `No adaptive risk` ablation。
- 决定哪些 ablation 用新实验，哪些引用历史失败结果。
- 生成最终表格草稿。

产出：

```text
ablation result directories
ablation summary table
updated changelog
```

### Week 2: 图表和 Results 章节

目标：

- 整理所有主要图表。
- 写 Results 和 Experiments 初稿。

产出：

```text
Results chapter draft
Experiments chapter draft
final tables
final figures list
```

### Week 3: Method 章节

目标：

- 写清楚 rule-aware supervisor。
- 写清楚 adaptive risk allocation。
- 画 state machine 和 risk allocation diagram。

产出：

```text
Method chapter draft
algorithm pseudocode
state-machine figure
risk-severity figure
```

### Week 4: Introduction / Related Work / Conclusion

目标：

- 完成论文叙事。
- 把实验结果和研究问题对应起来。

产出：

```text
full dissertation draft
contribution list
limitations and future work
```

### Week 5: 修改和最终检查

目标：

- 全文一致性检查。
- 图表编号和引用检查。
- 实验路径和参数可复现性检查。

产出：

```text
submission-ready dissertation draft
appendix / reproducibility notes
```

## 11. 下一步最具体任务

按优先级：

1. 在服务器跑 `No adaptive risk` 完整 batch：`bash run_give_way_no_adaptive_risk_ablation.sh`。
2. 拉取服务器最新结果。
3. 拉取并分析该 ablation。
4. 更新 `Final_Dissertation_Result_Analysis_20260627_212618.md`，加入 ablation comparison。
5. 生成 dissertation tables 的最终版。
6. 开始写 Results 章节。

建议下一个实验命名：

```text
202606xx_no_adaptive_risk_final_dissertation
```

建议实验命令方向：

```bash
python run_all_scenarios.py \
  --scenario_glob "scenario_uk_give_way.json" \
  --init_glob "ego_init_01.json" \
  --results_dir ".../no_adaptive_risk_final_dissertation" \
  --policies smpc_var_risk smpc_fixed_risk smpc_open_loop \
  --solver_backend gurobi \
  --risk_profile rule_aware_static_risk \
  --with_notv \
  --with_notv_cl \
  --postprocess_plot_scenario scenario_uk_give_way \
  --postprocess_plot_init 1
```

注意：该 ablation 必须保持 final geometry 和 rule-aware supervisor 不变，只替换 risk profile。否则无法说明差异来自 adaptive risk。

## 12. 风险控制

### 不要继续做的事

- 不要继续微调 `+2.75m` 起点。
- 不要降低 `yield_stop_buffer_distance=8.0m`。
- 不要扩大 recovery bypass。
- 不要把 `smpc_open_loop` 的 WARN 当作失败去修；它是 baseline evidence。
- 不要因为某个舒适性指标不完美而重新打开大规模调参。

### 需要警惕的事

- `smpc_var_risk` 的 footprint separation 只有 `0.135m`，不要再压缩 safety margin。
- 论文里必须承认这是 focused case study，不是大规模 benchmark。
- 如果 ablation 结果不如预期，也可以作为 evidence：说明某个模块确实必要。
- 如果 ablation 和 full method 很接近，需要强调 interpretability 和 rule-compliance evidence，而不是硬说所有数值都显著更好。

## 13. 最终交付清单

### 实验材料

- final run result directory
- ablation run result directories
- changelog
- final result analysis document
- post-CARLA gate reports
- paper metrics summaries

### 图表

- main paper panel
- trajectory map
- safety/rule compliance table
- efficiency/comfort table
- ablation table
- state-machine diagram
- adaptive-risk diagram
- video keyframes

### 论文章节

- Introduction
- Related Work
- Method
- Experiments
- Results and Discussion
- Limitations
- Conclusion
- Appendix / reproducibility notes

## 14. 成功标准

论文可以进入最终写作阶段的标准：

```text
1. final method has one visually acceptable, gate-passing CARLA run.
2. open-loop baseline demonstrates rule-order failure.
3. at least one ablation directly tests adaptive risk or rule-aware logic.
4. all main figures and tables are generated.
5. method contribution can be explained with conflict zone, traffic policy, and adaptive risk allocation.
6. limitations are stated honestly.
```

当前已经满足 1、2、5、6。下一步重点是补足 3 和 4。

## 15. 从 Small-Scale Trial 到 Full Experiment 的扩展路线

当前实验属于 small-scale controlled case study，而不是 full experiment。它已经证明核心方法在一个关键 give-way 场景中可行，但还不足以声称方法在广泛交通条件下全面有效。

### 当前结果说明什么

当前 `20260627_212618_final_dissertation` 和 `20260628_103325_final_dissertation` 都满足：

```text
required SMPC policies pass
solver_failure_frac = 0.000
footprint_collision = False
yield_order = True
paper panel generated
open-loop baseline violates give-way order
```

因此当前结果说明：

- final method 已经具备扩展到 full experiment 的基础稳定性。
- 现在不应继续围绕单个视频调参。
- 下一步可以做有控制的实验扩展，用来验证论文 claim。

### 不应该立刻做的 full experiment

不要马上扩展到大量随机地图、随机车辆、随机路线。原因：

- 当前方法是围绕一个 unsignalised left-turn give-way 场景建立的。
- 直接随机化过多因素会让失败难以归因。
- dissertation 更需要清晰证据链，而不是大量难解释的日志。

### 推荐的 full experiment 层级

#### Level 1: Method Ablation

目标：证明每个方法模块的必要性。

必须包括：

```text
1. full adaptive method
2. rule-aware static risk / no adaptive risk
3. open-loop non-rule-aware baseline
```

可引用历史结果：

```text
no recovery handoff -> 20260627_194959
smaller stop buffer -> 20260627_205856_final_dissertation
raw upstream profile -> 20260627_170746
```

#### Level 2: Controlled Scenario Sweep

目标：在同一交通语义下改变交互强度，验证 adaptive risk 是否随 severity 合理变化。

建议 sweep：

```text
target init speed: 4.5, 6.0, 7.5 m/s
ego nominal speed: 5.0, 6.0, 7.0 m/s
target spawn timing / initial gap: early, nominal, late
```

优先只改一个维度，每次保持其它参数不变。

建议最小矩阵：

```text
3 target speeds x 1 ego speed x 1 target timing = 3 runs
1 target speed x 3 ego speeds x 1 target timing = 3 runs
1 target speed x 1 ego speed x 3 target timings = 3 runs
```

合计约 9 个 controlled scenario variants。

每个 variant 至少跑：

```text
smpc_var_risk
smpc_fixed_risk
smpc_open_loop
```

如果时间充足，再加 `notv` / `notv_cl`。

#### Level 3: Robustness Repeat

目标：证明不是偶然通过。

对 final method 做 3-5 次 repeat run：

```text
same scenario
same configuration
different CARLA run timestamp / possible simulator nondeterminism
```

已有 repeat evidence：

```text
20260627_212618_final_dissertation
20260628_103325_final_dissertation
```

还可以再补 1-3 次，但优先级低于 no-adaptive-risk ablation。

#### Level 4: Extended Traffic Cases

只有在 Level 1-3 完成后才做。

可选扩展：

```text
different target arrival gap
more aggressive target speed
delayed target observation
slightly shifted conflict point
```

不建议在当前 dissertation 阶段切换到完全不同路口、UK left-hand traffic 或多目标交互，除非论文时间非常充足。

### 是否已经可以扩展到 full experiment

判断：

```text
可以扩展，但应该从 Level 1 ablation 开始，而不是直接做大规模随机实验。
```

理由：

- final method 已两次通过 full batch。
- solver failure 已经稳定为 0。
- required policies 没有 footprint collision。
- open-loop baseline 已经给出 rule-awareness 对照。
- 当前缺口不是方法能不能跑，而是论文证据链是否完整。

### 下一步实验顺序

严格按这个顺序：

```text
1. DONE: No adaptive risk ablation: rule_aware_static_risk
   result = 20260628_153117_no_adaptive_risk_final_dissertation
2. DONE: Compare against 20260628_103325_final_dissertation
   conclusion = static risk also passes, but adaptive var-risk is faster and more route-stable
3. DONE: Add ablation table to result analysis
4. NEXT: If time allows, run target-speed sweep: 4.5 / 6.0 / 7.5 m/s
5. THEN: If still有时间，再做 ego-speed 或 target-gap sweep
```

No-adaptive-risk ablation conclusion:

```text
rule_aware_static_risk preserves safety, yield order, completion, and zero solver failures in the nominal single scenario.
Adaptive interaction-severity risk allocation should therefore be claimed as an efficiency / route-stability improvement for variable-risk SMPC, not as the only reason the vehicle is safe.
The traffic-rule supervisor and bounded deterministic yield/recovery handoff remain the main source of rule compliance and solver robustness.
```

### Full Experiment 的最小可交付版本

如果论文时间紧，full experiment 最小版本可以是：

```text
Main result:
  full adaptive method, full batch, 1-2 repeat runs

Baselines:
  smpc_open_loop
  rule_aware_static_risk
  notv / notv_cl

Ablations:
  no adaptive risk
  historical no recovery handoff
  historical smaller stop buffer

Metrics:
  safety
  yield order
  solver stability
  completion
  efficiency
  comfort
```

这个版本足够支撑 dissertation 里的 focused experimental evaluation。
