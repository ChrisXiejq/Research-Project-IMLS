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
