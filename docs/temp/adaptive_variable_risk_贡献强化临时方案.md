# Adaptive Variable Risk 贡献强化临时方案

## 基线快照

这份方案锚定当前稳定仓库状态：

```text
stable commit: 7348b14fae287ba1bba8ee1accb9ada717c4372b
short commit:  7348b14
git tag:       stable-giveway-baseline-20260707
working tree:  生成本方案时为 clean
```

如果后续实验改坏，可以用 tag 回到当前稳定版本：

```bash
git switch -c recover-stable-giveway stable-giveway-baseline-20260707
```

如果已经保存好需要保留的实验结果，并且想强制回退当前分支：

```bash
git reset --hard stable-giveway-baseline-20260707
```

当前主线行为应该作为稳定 baseline 保持不变：

```text
TV speed = 9.0 m/s
yield_hard_stop_target_distance = 12.0 m
yield_hard_stop_conflict_distance = 13.0 m
yield_stop_buffer_distance = 7.0 m
yield_caution_decel = -4.0 m/s^2
yield_reference_decel = -3.75 m/s^2
yield_stop_decel = -5.0 m/s^2
yield_emergency_decel = -7.0 m/s^2
policies = smpc_var_risk, smpc_fixed_risk
video tail cleanup = enabled
```

## 目标

现在不应该把论文结论写成 “adaptive-variable-risk 单独导致 EV 安全让行”。当前系统更准确的定义是：

```text
rule-aware SMPC baseline
```

其中：

```text
adaptive-variable-risk:
  作用在 SMPC 优化层，改变 chance constraint 的保守程度

yield supervisor / hard stop / emergency brake:
  作为交通规则和 footprint safety 的安全兜底
```

因此本阶段目标是：

```text
保持当前主线安全表现不变
让 adaptive-variable-risk 在数据上更可测、更可解释
通过 ablation 证明在弱化 hard-stop 遮蔽时 adaptive risk 的独立贡献
```

## 核心论文表述

推荐写法：

```text
Adaptive variable risk 根据 conflict-zone interaction severity 调整 SMPC chance constraints 的风险保守程度。在稳定安全 baseline 中，rule-aware yield supervisor 被保留为 fallback，因此最终视频轨迹可能与 fixed risk 接近；但优化层的 risk allocation、planned margin 和 supervisor intervention statistics 可以揭示 adaptive risk 是否实际发挥作用。
```

不要写成：

```text
adaptive risk alone makes the vehicle stop
```

更严谨的写法是：

```text
adaptive risk shapes the planned interaction behaviour, while the supervisor guarantees traffic-rule safety
```

## Stage 1：不改变行为，只增强诊断

第一阶段不改控制逻辑，不改变视频表现，也不改变 safety gate。只增加日志和 postprocess。

需要从 `smpc_debug_steps.jsonl` 和 `scenario_steps.csv` 中提取或派生这些逐步指标：

```text
step
policy
ego_distance_to_conflict
target_distance_to_conflict
yield_phase
hard_stop_required
yield_supervisor_active
applied_control_mode
solver_nominal_accel_before_override
solver_nominal_steer_before_override
final_applied_accel_after_override
final_applied_steer_after_override
adaptive_risk_enabled
risk_tightening
risk_target_prob
raw_severity_score
effective_severity_score
risk_phase
target_cleared_conflict
planned_min_center_distance_to_target
actual_footprint_separation
solver_success
```

然后输出聚合指标：

```text
supervisor_active_frac
hard_stop_override_frac
rolling_caution_frac
emergency_brake_frac
mean risk_tightening by conflict-distance bucket
mean target_prob by conflict-distance bucket
mean nominal accel before override by bucket
mean final accel after override by bucket
solver failure by bucket
min footprint separation by bucket
```

建议的 conflict-distance 分段：

```text
far:       dconf > 25 m
approach: 15 m < dconf <= 25 m
critical: 5 m < dconf <= 15 m
near:      dconf <= 5 m
```

预期证据：

```text
ego dconf 越小，adaptive risk tightening 越强
target clearance 之后，risk tightening 放松
var risk 在 critical zone 的 tightening 高于 fixed risk
如果最终控制很像，需要说明是否因为 supervisor override 正在主导
```

这是最安全的第一步，因为它应该不改变当前最好的视频和 safety gate。

## Stage 1C：Phase-Aware Risk Floor 实现

当前 corrected single-init baseline 已经证明 fixed-static 和 adaptive-variable 的 solver risk 模式被正确分离：

```text
smpc_var_risk:
  solver_risk_mode = adaptive_variable
  solver_uses_adaptive_risk = 1

smpc_fixed_risk:
  solver_risk_mode = fixed_static
  solver_uses_adaptive_risk = 0
```

但 20260707_190600 的 risk-by-conflict-distance 统计显示，旧的 adaptive mapping 在 critical / near bucket 中可能比 fixed-static 更宽松。因此，Stage 1C 将 adaptive risk 从单纯 interaction-severity-aware 改成：

```text
phase-aware pre-clearance floor + target-cleared relaxation
```

具体实现位置：

```text
core/scripts/carla/policies/smpc_agent.py
  _adaptive_risk_allocation()

core/scripts/risk_by_conflict_distance.py
  phase-floor diagnostics and comparison columns
```

映射规则：

```text
target not cleared 且 yield_phase != released_recovery:
  far:       no extra floor
  approach: tightening >= 1.68
  critical: tightening >= 1.80
  near:     tightening >= 1.85

target cleared 或 released_recovery:
  tightening = 1.2815515655446004  # Phi^{-1}(0.90)
```

这个设计要证明的不是 “距离越近 risk 一定越大” 这种过强命题，而是：

```text
在 target clearance 之前，adaptive-variable-risk 对接近冲突区的 phase 施加比 fixed-static 更保守的 chance constraint；
在 target clearance 之后，adaptive-variable-risk 允许比 fixed-static 更快放松，从而减少不必要保守性。
```

新增诊断字段：

```text
raw_tightening_before_floor
preclearance_tight_floor
preclearance_floor_active
preclearance_floor_applied
preclearance_floor_reason
```

其中 `risk_by_conflict_distance.py` 只在 solver 实际使用 adaptive risk 时统计 floor active/applied，避免 fixed-static policy 的 diagnostic mapping 被误读为实际 solver 约束。

下一步必须先跑 single-init sanity check，而不是直接跑 5-init：

```text
期望 smpc_var_risk:
  solver_failure = 0
  footprint collision = False
  yield_ok = True
  approach/critical/near preclearance_floor_applied_frac > 0
  critical/near risk_tightening_mean > fixed_static 1.64

期望 smpc_fixed_risk:
  solver_failure = 0
  preclearance_floor_applied_frac = 0
  solver_risk_mode = fixed_static
```

## Stage 2：Soft-First SMPC 增强

只有 Stage 1 证明 adaptive-risk 信号可测之后，才进入这一阶段。

不要直接关闭 hard stop。更合理的做法是让 SMPC 在 fallback 触发前承担更多工作：

```text
保持 hard-stop / emergency fallback threshold 不变
保持最终 safety supervisor 开启
只在 critical dconf bucket 里增强 adaptive risk tightening
通过 SMPC reference generation 更早降低参考速度，而不是直接改 final override
记录 hard-stop intervention fraction 是否下降
```

候选 adaptive-risk 映射：

```text
far:
  tightening 接近 upstream value

approach:
  mild tightening

critical:
  更强地插值到 paper epsilon=0.02 对应 tightening

near or overlap-risk:
  允许最强 tightening，但必须保留 solver failure guard

after target clearance:
  relaxed tightening
```

接受标准：

```text
required policies PASS
single-init sanity check 中 solver_failure = 0
footprint collision = False
yield_ok = True
min footprint separation 和稳定 baseline 接近
hard_stop_override_frac 下降，或 hard-stop 前 nominal SMPC braking 更强
视频表现仍自然
```

拒绝标准：

```text
任何 footprint collision
yield order regression
任一 required policy 出现 solver failure
转弯后 lane-entry regression
停车或转向视觉上明显不自然
```

## Stage 3：Soft-Yield 诊断消融

这一阶段不是主 baseline，只用于证明 adaptive-risk 的独立贡献。

实验分组：

```text
mainline:
  smpc_var_risk + rule-aware yield supervisor
  smpc_fixed_risk + rule-aware yield supervisor

diagnostic ablation:
  smpc_var_risk + weakened hard-stop fallback
  smpc_fixed_risk + weakened hard-stop fallback
```

可能的 weakened fallback 设置：

```text
保留 yield detection 和 route-following steering
保留真正 imminent collision 的 emergency fallback
延迟或减弱 hard-stop final-control override
增强 pre-solve reference decel 和 adaptive risk tightening
```

论文中可以这样使用：

```text
如果 weakened override 下 var risk 比 fixed risk 有更大的 planned margin 或更高 pass stability，则支持 adaptive-risk 贡献。
如果两者都失败，则说明高速度 unsignalised give-way 场景中仅靠 risk allocation 不足以稳定保证交通规则安全，因此需要 rule-aware safety fallback。
```

## Stage 4：多 init 证据

单 init 稳定后，再扩展：

```text
5-init precheck
10-init precheck
50-init full experiment
```

主对比只保留：

```text
smpc_var_risk vs smpc_fixed_risk
```

`smpc_open_loop` 不作为主对比，因为它在当前 CARLA 场景里不是一个有意义的 closed-loop give-way controller。

最终报告指标：

```text
completion rate
yield pass rate
footprint collision rate
min footprint separation
center dmin
solver failure rate
completion time
comfort metrics
supervisor intervention fraction
hard-stop override fraction
risk tightening by conflict-distance bucket
```

## 推荐下一步

优先实现 Stage 1：

```text
1. 新增一个 postprocess 脚本，读取 smpc_debug_steps.jsonl 和 scenario_steps.csv
2. 输出 risk_by_conflict_distance.csv
3. 输出 var-risk vs fixed-risk 的 summary markdown
4. 不改任何控制逻辑
5. 用当前 single-init baseline 跑一次验证
```

这样可以在不冒险破坏当前最好 baseline 的情况下，直接为 adaptive-variable-risk 的机制贡献提供数据证据。

## Stage 1 实现状态

已实现行为不变的 postprocess：

```text
core/scripts/risk_by_conflict_distance.py
```

它会自动扫描结果目录下的 `smpc_var_risk` 和 `smpc_fixed_risk` 子目录，读取：

```text
smpc_debug_steps.jsonl
scenario_steps.csv
postcarla_trajectory_gate.json
```

并输出：

```text
risk_by_conflict_distance.csv
risk_by_conflict_distance_summary.csv
risk_by_conflict_distance_summary.json
risk_by_conflict_distance_summary.md
```

该脚本已接入：

```text
core/scripts/carla/run_give_way_final_dissertation_batch.sh
core/scripts/carla/run_give_way_50init_final_dissertation_batch.sh
```

当前实现只做诊断分析，不改变控制逻辑、车辆轨迹或 safety gate。

## Stage 1 现状分析

已用 Stage 1 脚本分析以下关键结果：

```text
20260706_000724_final_dissertation  当前最稳 milestone，TV≈6，target_distance=12.0，conflict_distance=13.5
20260706_235540_final_dissertation  TV=9，target_distance=12.0，conflict_distance=13.0
20260707_001331_final_dissertation  TV=9，target_distance=11.5，conflict_distance=13.0
20260707_102456_final_dissertation  TV=9，target_distance=11.75，conflict_distance=13.0
```

### 1. 主线结果中 supervisor 遮蔽很明显

在最关键的 `critical` conflict-distance bucket 里，最终控制被 yield supervisor 覆盖的比例较高：

```text
20260706_000724:
  smpc_var_risk   final_control_overridden_frac ≈ 0.624
  smpc_fixed_risk final_control_overridden_frac ≈ 0.627

20260706_235540:
  smpc_var_risk   final_control_overridden_frac ≈ 0.525
  smpc_fixed_risk final_control_overridden_frac ≈ 0.512

20260707_102456:
  smpc_var_risk   final_control_overridden_frac ≈ 0.519
  smpc_fixed_risk final_control_overridden_frac ≈ 0.519
```

这说明：在真正接近 conflict zone 的阶段，约一半到三分之二的最终控制由 rule-aware supervisor 决定。因此视频里 `var risk` 和 `fixed risk` 看起来接近是合理的，不是数据异常。

### 2. 当前主线的 var/fixed risk tightening 差异太小

在 `critical` bucket 中，`smpc_var_risk` 和 `smpc_fixed_risk` 的 `risk_tightening_mean` 非常接近：

```text
20260706_000724:
  fixed ≈ 1.5535
  var   ≈ 1.5519

20260706_235540:
  fixed ≈ 1.4977
  var   ≈ 1.5034

20260707_102456:
  fixed ≈ 1.5006
  var   ≈ 1.5006
```

这说明当前 `smpc_fixed_risk` 并不是一个足够“静态”的 fixed-risk 对照。它仍然记录到了和 adaptive profile 几乎相同的 tightening/target_prob，因此不能直接用这个字段证明 var-risk 优越性。

这可能来自两种情况之一，需要下一步核查代码：

```text
1. fixed-risk policy 仍然走了同一个 adaptive_interaction_severity 风险映射；
2. fixed-risk 只在 solver 内部固定了部分参数，但 debug 输出仍然记录了全局 adaptive profile 的 applied_tight / target_prob。
```

无论是哪种情况，当前 Stage 1 已经证明：如果论文要突出 adaptive-variable-risk，必须先把 `risk profile used by solver` 和 `yield supervisor used by controller` 两个概念在日志里拆开。

### 3. `11.5` sensitivity 体现了一点 var-risk 优势，但不能作为主 baseline

`20260707_001331` 中：

```text
smpc_var_risk:
  critical solver_failure_frac = 0.000
  release dconf 更接近目标停车距离

smpc_fixed_risk:
  critical solver_failure_frac ≈ 0.0123
```

这说明在更激进的 target-distance threshold 下，`var risk` 的稳定性可能优于 `fixed risk`。但这组配置让 fixed-risk 出现 solver failure，因此不适合作为主 baseline，只适合作为 adaptive-risk sensitivity / ablation 证据。

### 4. 当前最稳主线仍应保持保守

目前主线应继续采用：

```text
TV speed = 9.0
yield_hard_stop_target_distance = 12.0
yield_hard_stop_conflict_distance = 13.0
smpc_open_loop removed
video tail cleanup enabled
policies = smpc_var_risk, smpc_fixed_risk
```

理由：

```text
1. target_distance=11.5/11.75 虽然能制造 var/fixed 差异，但 fixed-risk 出现 solver failure；
2. target_distance=12.0 更适合进入 5-init / 10-init precheck；
3. adaptive-risk 贡献应通过诊断和 ablation 证明，不应该通过牺牲主线稳定性来证明。
```

## 修缮后的计划

### Revised Stage 1A：核查并修正 fixed-risk 诊断口径

当前最高优先级不是继续调停车距离，而是确认 `smpc_fixed_risk` 的日志是否真的反映 fixed risk。

需要检查：

```text
core/scripts/carla/policies/smpc_agent.py
```

重点看：

```text
policy_flags.fixed_risk
risk_profile
risk.applied_tight
risk.applied_target_prob
solver.debug.adaptive_risk_allocation
solver.debug.current_tight
solver.debug.current_target_prob
```

目标是让日志明确区分：

```text
solver_risk_mode:
  adaptive_variable
  fixed_static

solver_current_tight:
  真正传入 solver 的 tight

solver_current_target_prob:
  真正传入 solver 的 target_prob

diagnostic_severity_score:
  只用于分析，不代表 fixed-risk solver 实际使用 adaptive risk
```

如果 fixed-risk 目前确实仍走 adaptive risk，则需要修正 fixed-risk 对照；如果只是 debug 字段混淆，则只修正日志字段，不改控制行为。

### Revised Stage 1B：增强 summary 的对比解释

`risk_by_conflict_distance.py` 下一步应增加一个更论文友好的对比表：

```text
var_minus_fixed_risk_tightening_mean
var_minus_fixed_nominal_accel_mean
var_minus_fixed_solver_failure_frac
var_minus_fixed_supervisor_override_frac
var_minus_fixed_min_footprint_separation
```

这能直接回答：

```text
adaptive risk 是否在 critical bucket 更保守？
adaptive risk 是否减少 solver failure？
adaptive risk 是否减少 supervisor 接管？
adaptive risk 是否带来更大安全裕度？
```

### Revised Stage 2：主线不变，做 soft-first 轻量增强前先设门槛

只有满足以下条件，才进入 Stage 2：

```text
1. fixed-risk 诊断口径已经核查清楚；
2. var/fixed 的 solver risk fields 能明确区分；
3. 主线 TV=9 target_distance=12.0 conflict_distance=13.0 单 init 仍 PASS 且 solver_failure=0；
4. Stage 1 summary 能自动输出 var-vs-fixed 对比。
```

Stage 2 不应直接削弱 hard stop。只允许做：

```text
增强 pre-solve adaptive risk tightening
增强 SMPC reference speed cap 的诊断可见性
记录 hard-stop 前 SMPC nominal braking 是否增强
```

如果 Stage 2 导致：

```text
fixed-risk solver failure
var-risk solver failure
footprint margin 明显下降
视频里停车或转向变差
```

则立即回退，不进入 full experiment。

### Revised Stage 3：把 11.5 作为 sensitivity，不作为主线

`target_distance=11.5` 的结果应该保留为机制敏感性证据：

```text
它显示在更紧的 supervisor threshold 下，var-risk 可以保持 solver clean，而 fixed-risk 出现 solver failure。
```

但论文主 baseline 不应采用该配置，因为主 baseline 需要两个 required policies 都稳定。

### Revised Stage 4：多 init 前置条件

进入 5-init / 10-init 前必须满足：

```text
1. 当前主线单 init PASS；
2. risk_by_conflict_distance summary 自动生成；
3. fixed-risk 诊断口径清楚；
4. post-CARLA gate 和 risk-by-distance summary 能一起解释结果；
5. stable tag 保持可回滚。
```

多 init 初期建议只跑：

```text
5-init precheck:
  smpc_var_risk
  smpc_fixed_risk

不跑:
  smpc_open_loop
```

5-init 通过后再扩展 10-init。50-init 放在最后。

## Stage 1A / 1B 实现状态

### Stage 1A 已执行

核查结果：

```text
原实现中，smpc_agent.py 会无条件把 _adaptive_risk_allocation 的
risk_tightening / risk_target_prob 写入 update_dict。

由于 mpc_utils.py 的 SMPC_MMPreds.update() 会优先读取 update_dict 中的
risk_tightening / risk_target_prob，因此 smpc_fixed_risk 实际也可能接收
adaptive tightening。
```

这说明问题不是单纯的日志命名混淆，而是 fixed-risk 对照口径不够严格。

已修正：

```text
core/scripts/carla/policies/smpc_agent.py
```

现在逻辑为：

```text
smpc_var_risk:
  solver_risk_mode = adaptive_variable
  solver_uses_adaptive_risk = True
  adaptive risk_tightening / target_prob 写入 solver update_dict

smpc_fixed_risk:
  solver_risk_mode = fixed_static
  solver_uses_adaptive_risk = False
  不再把 adaptive risk_tightening / target_prob 写入 solver update_dict
  仍保留 diagnostic_adaptive，用于记录同一时刻的 severity 映射
```

新日志中应重点检查：

```text
risk.solver_risk_mode
risk.solver_uses_adaptive_risk
risk.solver_current_tight
risk.solver_current_target_prob
risk.diagnostic_adaptive
solver.debug.current_tight
solver.debug.current_target_prob
```

预期：

```text
smpc_var_risk:
  risk.solver_risk_mode = adaptive_variable
  risk.solver_uses_adaptive_risk = true

smpc_fixed_risk:
  risk.solver_risk_mode = fixed_static
  risk.solver_uses_adaptive_risk = false
```

### Stage 1B 已执行

已增强：

```text
core/scripts/risk_by_conflict_distance.py
```

新增输出：

```text
risk_by_conflict_distance_comparison.csv
```

`risk_by_conflict_distance_summary.md` 中新增：

```text
Var Risk Minus Fixed Risk
```

新增对比字段：

```text
var_minus_fixed_risk_tightening_mean
var_minus_fixed_diagnostic_risk_tightening_mean
var_minus_fixed_nominal_accel_mean
var_minus_fixed_final_accel_mean
var_minus_fixed_solver_failure_frac
var_minus_fixed_supervisor_override_frac
var_minus_fixed_hard_stop_override_frac
var_minus_fixed_min_footprint_separation
```

解释口径：

```text
risk_tightening_mean:
  新日志中表示真正传给 solver 的 risk tightening。

diagnostic_risk_tightening_mean:
  表示 adaptive severity mapping 在该时刻会给出的 tightening；
  对 fixed-risk 来说这是诊断值，不代表 solver 实际使用。
```

旧结果回归：

```text
20260707_102456_final_dissertation 可以重新生成 summary/comparison。
旧日志没有 solver_risk_mode 字段，因此显示 unknown，这是预期现象。
下一次 CARLA 运行后，新结果应显示 adaptive_variable / fixed_static。
```

### 下一步

重新跑一次当前主线 single-init：

```text
TV speed = 9.0
yield_hard_stop_target_distance = 12.0
yield_hard_stop_conflict_distance = 13.0
policies = smpc_var_risk, smpc_fixed_risk
```

重点验证：

```text
1. 两个 required policies 是否仍 PASS；
2. solver_failure 是否为 0；
3. smpc_fixed_risk 是否不再显示 solver_uses_adaptive_risk；
4. risk_by_conflict_distance_comparison.csv 是否显示 var/fixed solver risk 差异；
5. 视频表现是否保持稳定。
```

## Corrected Risk-Comparison Milestone

已将以下结果定义为新的机制分析 milestone：

```text
result: 20260707_190600_final_dissertation
code commit: 9e3ffddee6dacbea22c97fc83f1df096e4516d66
short commit: 9e3ffdd
tag: corrected-risk-comparison-20260707
```

它的定位不是“视觉停车距离最优”，而是：

```text
第一个完成 fixed-static vs adaptive-variable 正确对照的 milestone。
```

结果：

```text
smpc_var_risk:
  PASS
  solver_failure = 0.000
  solver_risk_mode = adaptive_variable
  solver_uses_adaptive_risk = 1
  center dmin ≈ 5.046m
  min footprint separation ≈ 1.678m

smpc_fixed_risk:
  PASS
  solver_failure = 0.000
  solver_risk_mode = fixed_static
  solver_uses_adaptive_risk = 0
  center dmin ≈ 5.046m
  min footprint separation ≈ 1.678m
```

关键解释：

```text
两者最终轨迹仍然相似，不是因为 adaptive/fixed 没有分开，
而是因为 critical bucket 中 yield supervisor 覆盖最终控制的比例仍约 0.512。
```

因此这次结果支持：

```text
fixed-risk 对照口径已经修正；
rule-aware supervisor 遮蔽了部分最终轨迹差异；
adaptive risk 的贡献需要通过 solver risk、nominal control 和多 init 统计证明。
```

## 修缮后的论文论点

### 论文主问题

本论文不应证明：

```text
adaptive-variable-risk 单独让 EV 在无信号路口安全停车让行。
```

更准确的主问题应是：

```text
在 multimodal prediction SMPC 框架下，如何把交通规则优先级、conflict-zone interaction severity
和 chance-constraint risk allocation 结合起来，使 EV 能在无信号 give-way 路口稳定、安全、可解释地让行？
```

### 核心论点

推荐主论点：

```text
This dissertation reproduces and adapts the intersection SMPC setting to a right-hand-traffic
unsignalised give-way scenario, and extends the baseline with a rule-aware safety supervisor
and interaction-severity-aware adaptive risk allocation. The supervisor guarantees traffic-rule
safety, while adaptive risk allocation modulates the optimiser's chance-constraint conservatism
according to the interaction phase. The contribution of adaptive risk is evaluated separately
from supervisor intervention using corrected fixed-static baselines and conflict-distance
bucket diagnostics.
```

中文表述：

```text
本实验复现并改造了原 SMPC intersection 场景，将其落到右行制无信号让行路口。
系统由两层组成：rule-aware yield supervisor 负责交通规则和 footprint safety 兜底；
adaptive-variable-risk 负责在 SMPC 优化层根据 interaction severity 动态调整 chance constraint
保守程度。论文不把最终停车行为完全归因于 adaptive risk，而是通过 corrected fixed-static
对照、conflict-distance 分段统计和 sensitivity/ablation 来证明 adaptive risk 的优化层贡献。
```

### 相比原 SMPC 论文的定位

可以主张的复现部分：

```text
1. 复现 intersection 类型任务，而不是 lane change 或 hardware/VIL；
2. 保留 multimodal prediction + SMPC chance constraints 的核心思想；
3. 使用 paper ego_init_01 和迁移的 paper 50 initial conditions 作为扩展基础；
4. 比较 SMPC variable/adaptive risk 与 fixed/static risk。
```

可以主张的扩展/创新部分：

```text
1. 将原 intersection 设置改造成右行制 unsignalised give-way 语义：
   EV 左转让行，TV 直行优先。

2. 引入 rule-aware yield supervisor：
   解决纯 SMPC 在 CARLA closed-loop 中可能无法稳定满足交通规则的问题。

3. 引入 footprint-aware post-CARLA safety gate：
   不只看中心距离，还 replay footprint collision。

4. 修正 fixed-risk 对照口径：
   fixed-risk 不再接收 adaptive risk_tightening / target_prob。

5. 引入 risk-by-conflict-distance 诊断：
   把 optimizer risk、nominal control、final supervisor override 分开统计，
   避免把 supervisor 的贡献误归因给 adaptive risk。
```

不能直接主张的内容：

```text
1. 不能说 adaptive risk 单独导致安全让行；
2. 不能说当前单 init 已证明 adaptive risk 明显优于 fixed risk；
3. 不能说 adaptive risk 是单调随 ego conflict distance 变近而更严格。
```

当前数据实际显示：

```text
approach bucket:
  var risk tightening ≈ 1.676
  fixed risk tightening = 1.640
  var slightly more conservative

critical bucket:
  var risk tightening ≈ 1.498
  fixed risk tightening = 1.640
  var less conservative

near bucket:
  var risk tightening ≈ 1.282
  fixed risk tightening = 1.640
  var further relaxed
```

所以正确解释是：

```text
adaptive_interaction_severity 不是纯 distance-monotonic profile。
它会根据 interaction severity、target clearance 和 phase 动态调整风险；
当目标车已经接近或完成清场时，adaptive risk 会放松，而不是继续机械收紧。
```

## 后续对照实验设计

### Experiment A：Corrected Single-Init Baseline

目的：

```text
证明 corrected fixed-static vs adaptive-variable 对照已经成立，并且两个策略都能通过主线 single-init。
```

配置：

```text
TV speed = 9.0
yield_hard_stop_target_distance = 12.0
yield_hard_stop_conflict_distance = 13.0
policies = smpc_var_risk, smpc_fixed_risk
```

已完成：

```text
20260707_190600_final_dissertation
```

结论：

```text
两者均 PASS，solver_failure=0；
但最终轨迹相似，因为 critical supervisor override≈0.512。
```

论文用途：

```text
作为机制分析和后续多 init 的 corrected baseline。
```

### Experiment B：5-init / 10-init Corrected Aggregate

目的：

```text
判断 corrected fixed-static 与 adaptive-variable 在多个 initial conditions 下是否出现统计差异。
```

指标：

```text
completion rate
yield pass rate
footprint collision rate
solver failure rate
min footprint separation
center dmin
completion time
comfort metrics
critical bucket solver risk
critical bucket nominal accel
critical bucket supervisor override fraction
```

可能结果解释：

```text
如果 var risk 成功率更高或 solver failure 更低：
  支持 adaptive risk 提升稳定性。

如果 var/fixed 都通过且最终轨迹接近：
  支持 rule-aware SMPC baseline 稳定，但 adaptive risk 优势在强 supervisor 下不明显。

如果 fixed risk 失败而 var risk 通过：
  强支持 adaptive-variable-risk 的实用价值。

如果两者都失败：
  说明当前 supervisor/risk 配置还不足以扩展到 harder initial conditions。
```

### Experiment C：Supervisor-Intervention Analysis

目的：

```text
证明最终轨迹差异为什么小，以及 adaptive risk 的贡献是否被 supervisor 遮蔽。
```

使用已有输出：

```text
risk_by_conflict_distance_summary.md
risk_by_conflict_distance_comparison.csv
```

需要报告：

```text
critical bucket final_control_overridden_frac
hard_stop_override_frac
solver risk tightening
nominal_accel_before_override
final_accel_after_override
```

预期结论：

```text
当 override fraction 高时，视频和 final trajectory 差异会变小；
adaptive risk 的贡献应从 nominal control / solver risk 统计中观察。
```

### Experiment D：Target-Distance Sensitivity / Harder Setting

目的：

```text
在更紧的 supervisor threshold 下观察 var/fixed 差异。
```

已有候选：

```text
20260707_001331_final_dissertation
target_distance = 11.5
```

观察：

```text
var risk solver_failure = 0
fixed risk 出现 solver_failure
```

论文用途：

```text
作为 sensitivity evidence，而不是主 baseline。
```

注意：

```text
不能用它替代主线，因为主线要求两个 required policies 都稳定。
```

### Experiment E：Soft-Yield Ablation

只在 A/B/C 完成后考虑。

目的：

```text
减弱 supervisor 遮蔽，观察 adaptive risk 独立贡献。
```

原则：

```text
不直接删除 emergency fallback；
只延迟或减弱 hard-stop final-control override；
保留真正 imminent collision 的 safety fallback。
```

接受标准：

```text
var risk 比 fixed risk 有更低 solver failure、更大 planned margin 或更少 supervisor intervention；
不能出现 footprint collision 或 yield order regression。
```

## 立即执行路线

当前已经完成：

```text
1. 修正 fixed-risk 对照；
2. 增加 risk-by-conflict-distance 诊断；
3. 验证 20260707_190600 corrected single-init baseline；
4. 确认当前 adaptive risk 是 interaction-severity-aware，而不是 distance-monotonic。
```

下一步应执行：

```text
1. 给当前 corrected milestone 打 tag；
2. 把 20260707_190600 记录进 changelog；
3. 保持控制逻辑不再继续调参；
4. 跑 5-init corrected aggregate；
5. 用 risk_by_conflict_distance_summary 和 comparison 文件分析多 init 结果。
```

已生成 5-init precheck 脚本：

```text
core/scripts/carla/run_give_way_5init_final_dissertation_batch.sh
```

该脚本使用：

```text
scenario_glob = scenario_uk_give_way.json
init_glob = paper_intersection_50/ego_init_0[1-5].json
policies = smpc_var_risk, smpc_fixed_risk
risk_profile = adaptive_interaction_severity
camera = disabled by default
plots = disabled
postcarla_trajectory_gate = enabled
risk_by_conflict_distance = enabled
```

它是 10-init / 50-init 前的下一步执行入口。
