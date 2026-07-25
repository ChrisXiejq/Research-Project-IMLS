# 导师反馈后的下一阶段实验行动指南

这个文档是后续实验、代码修改和结果分析的方向约束。后续不要再单纯堆更多 50-init aggregate result，而是要围绕导师指出的问题，把当前 best milestone 解释清楚，并找出下一版方法真正可以改进的地方。

## 0. 决策门槛：每次判断都必须回到导师反馈

后续每一次判断、代码修改、服务器运行和结果解释，都必须先确认它服务于导师反馈中的至少一个问题：

1. 解释并减少 conservative early stop：ego 不应在距离 conflict point 很远时被不必要地强制停车，而应在安全前提下继续谨慎接近，并在 target vehicle 清空 ego path 后及时释放。
2. 解释 feasibility / infeasibility：如果 feasibility 指 MPC optimisation feasibility，就不能只报告 aggregate percentage，必须分析 infeasible step 发生在哪些 rollout、phase、distance-to-conflict 和 policy 下。
3. 验证 fine-tuned prediction 结果可信度：`0.98% -> 100%` 的 mode-ranking 提升不能直接当作通用预测能力提升，必须通过 split、metric、same-test-set 和 leakage sanity check 支撑。
4. 隔离 supervisor contribution：如果 fixed-risk 和 adaptive-risk 的 final trajectory 很相似，必须判断是不是 shared supervisor / safety filter 主导了最终行为，并通过 ablation 量化这一点。

当前总目标不是单纯让某一次 rollout 更好看，而是形成可写进论文的证据链：

```text
先证明原始 conservative behaviour 主要来自哪里，
再证明 reduced-intervention supervisor 能减少不必要接管但仍保持 safety，
再在 supervisor 影响被量化或削弱后，证明 adaptive-risk 相比固定风险族的可解释优势。
```

因此，任何“为了拉开 var/fixed 差距而削弱 hard safety guard”的改动都不符合目标。adaptive-risk 的优势必须来自风险分配、clearance 后风险释放、solver-layer 行为或更困难场景下的 safety/performance trade-off，而不是来自破坏 baseline 或取消安全约束。

借鉴原论文 `Predictive Control for Autonomous Driving With Uncertain, Multimodal Predictions` 后，本文后续主张需要调整为更严谨的版本：

```text
原论文证明的是：在没有外层 rule-aware supervisor 抹平最终动作的 SMPC 架构中，优化 risk levels 相比单一 fixed risk 能提升 feasibility、comfort 和 safety/performance trade-off。

本文要证明的是：在更接近安全部署的 give-way 场景中，adaptive-risk 的贡献需要和 rule-aware supervisor 分层解释。adaptive-risk 不应只和一个固定 epsilon baseline 比，而应和 fixed-risk frontier 比；如果它在相同 safety / infeasibility 水平下减少 supervisor intervention、改善 solver feasibility、缩短 post-clearance delay 或保持更好的 safety-performance Pareto trade-off，就构成 proposal 的优势。
```

因此，后续不再追求“adaptive-risk 在单个 fixed-risk baseline 上 final trajectory 大幅胜出”这个脆弱结论。新的 proof target 是：

```text
Adaptive variable risk provides a better risk-allocation mechanism than a family of fixed-risk baselines, while the supervisor analysis explains why final executed trajectories may still look similar in a rule-constrained give-way scenario.
```

## 1. 当前起点

当前 best milestone：

```text
fine-tuned MultiPath predictor
+ phase-aware adaptive-risk SMPC
+ rule-aware supervisor
```

对应结果目录：

```text
core/results/20260718_104740_50init_finetuned_predictor_validation
```

当前可以保留的主叙事：

- 控制侧：从 single SMPC 提升到 SMPC+Supervisor，保证 give-way 规则、footprint safety 和 closed-loop safety。
- 模型侧：发现 MultiPath 在 CARLA give-way 场景里有 mode ranking / probability calibration 问题，并通过 fine-tuning 明显改善。
- 集成结果：fine-tuned predictor 放回 closed-loop 后，50-init 全部通过 safety gate。
- adaptive-risk 机制仍然可解释：target clearance 前更保守，clearance 后放松。

当前主要短板：

- ego 过早停车，行为偏保守；
- fixed-risk 和 adaptive-risk 最终轨迹很接近；
- adaptive-risk 增加计算成本，但 aggregate 指标提升不明显；
- feasibility 只报百分比不够，需要分析 infeasible step；
- fine-tuning 结果提升太大，需要做 sanity check，避免被质疑有数据泄漏或 metric 问题。

当前阶段判断：

- 已经有初步证据说明 shared supervisor 会显著影响 final behaviour，但还不能说已经足够隔离 supervisor 影响；
- reduced-intervention supervisor 已经完成当前 5-init 稳定候选验证，当前冻结版本为 `20260725_023251_5init_reduced_clear_path_release`；
- formal 5-init supervisor ablation 已完成，结果目录为 `core/results/20260725_125938_5init_formal_supervisor_ablation`；
- formal ablation 已经足够支撑“full supervisor 强烈主导 conservative early-stop，并掩盖 fixed/adaptive final behaviour 差异”，但还不足以支撑“adaptive-risk 在最终轨迹上显著优于 fixed-risk”；
- 当前尚未可靠证明 adaptive-risk / var-risk 相比 fixed-risk 的优势，因为 promising reduced 版本下两者 final trajectory 仍然接近，且当前 fixed-risk baseline 还不是 fixed-risk frontier；
- aggressive 地减少 supervisor 接管可以制造少量 var/fixed 差异，但如果带来 solver infeasibility、video behaviour artifact 或 post-turn lane keeping 回归，不能作为论文证据；
- 下一阶段停止继续调 reduced supervisor，把当前冻结版本作为 stable reduced condition，转向 adaptive-risk intensity / scenario difficulty sweep、fixed-risk frontier baseline 和必要的 fine-tuning sanity 补充；
- 在完成导师四条反馈对应的证据链前，不进入新的 50-init milestone 实验。

## 2. 导师反馈对应的研究问题

### Q1. ego 为什么停得太早？

现象：

ego 在距离 conflict point 还比较远时就停住，并且等 target 完全通过 intersection 后才继续走。这个行为比真实驾驶更保守。

要回答的问题：

```text
早停是 SMPC/risk constraints 导致的，还是 supervisor / yield logic 导致的？
```

需要看的证据：

- nominal SMPC acceleration vs final executed acceleration；
- supervisor active flag；
- solver bypass reason；
- ego distance to conflict point；
- target cleared flag；
- risk tightening；
- solver feasible / infeasible 状态。

判断规则：

- 如果 nominal SMPC 还想继续走，但 final action 被改成刹车，说明 supervisor 主导。
- 如果 nominal SMPC 本身已经强刹车，说明 conservatism 主要来自 SMPC/risk constraints。
- 如果 target 已经基本 clear 但 ego 仍然等待，说明 clearance/release logic 太保守。

### Q2. adaptive-risk 的贡献是不是被 supervisor 掩盖了？

现象：

fixed-risk + supervisor 和 adaptive-risk + supervisor 的 final trajectory 和 aggregate metrics 很接近。

要回答的问题：

```text
adaptive-risk 是否在 solver layer 有贡献，但被同一个 supervisor filter 后，最终执行轨迹被抹平？
```

需要看的证据：

- fixed-risk 和 adaptive-risk 的 supervisor active fraction；
- nominal-final acceleration difference；
- solver-layer risk tightening；
- final executed trajectory difference；
- safety margin、completion time、stop distance、waiting time。

### Q2b. adaptive-risk 是否优于 fixed-risk frontier？

原论文的 `Proposed` 不是靠交通规则 supervisor 取胜，而是通过优化 multimodal chance constraints 的 risk levels，让 optimizer 在 feasibility、comfort、safety 和 mobility 之间取得更好的折中。为了借鉴这个优势，本文不能只比较一个固定的 `smpc_fixed_risk`，而应该比较一组 fixed-risk baselines。

要回答的问题：

```text
adaptive-risk 是否在相同或更好的 safety / feasibility 水平下，优于一组 fixed-risk risk-level settings，而不是只优于一个固定 baseline？
```

需要看的证据：

- fixed-risk conservative / medium / aggressive 的 feasibility、safety margin、completion time、release delay；
- adaptive-risk 是否处在 fixed-risk Pareto frontier 之上或更靠近优选区域；
- adaptive-risk 是否用动态 risk allocation 实现了 fixed-risk 难以同时做到的行为：
  - pre-clearance 更保守；
  - post-clearance 更快 release；
  - solver infeasibility 不增加或更少；
  - supervisor active / bypass fraction 更低；
  - nominal-final action delta 更小。

判断规则：

- 如果 adaptive-risk 只比一个 fixed-risk baseline 好，但 fixed-risk sweep 中存在另一个 fixed setting 同时更安全、更快，则不能声称 proposal 有优势。
- 如果 fixed conservative 安全但太慢、fixed aggressive 快但 infeasible 或 supervisor intervention 增加，而 adaptive-risk 在两者之间形成更好的 safety-performance compromise，则可以声称 proposal 有优势。
- 如果 adaptive-risk 的优势主要存在于 solver layer，但 final layer 被 supervisor 抹平，仍可写成“adaptive risk improves optimizer-level risk allocation, while rule-aware supervisor masks final action differences in safety-critical phases”。

### Q3. infeasible step 什么时候发生，为什么发生？

现象：

现在只报 `99.37% feasibility`，信息量不够。

要回答的问题：

```text
infeasible step 是否集中在某些 phase、某些 init、某些距离或某个 policy？
```

需要看的证据：

- 每个 policy 的 infeasible step 数；
- 受影响 rollout 数；
- infeasible step 出现在 approach / pre-clearance / post-clearance 哪个阶段；
- infeasible 时 ego 距 conflict point 多远；
- fixed-risk 和 adaptive-risk 是否在同一批 step 失败；
- infeasible 后 supervisor/fallback 如何处理。

### Q4. fine-tuning 结果是否可信？

现象：

`top-probability mode is best: 0.98% -> 100%` 提升非常大，导师合理地建议检查实现和 evaluation。

要回答的问题：

```text
fine-tuning 结果是否存在 split leakage、metric mismatch、label transform 错误或 evaluation 不一致？
```

必须检查：

- train/val/test 是否按 init split，而不是随机 sample split；
- test init 是否没有出现在 train/val；
- pretrained 和 fine-tuned 是否用完全相同的 test samples；
- metric 是否真的是 top-probability mode，而不是 oracle minADE mode；
- input/raster 是否没有包含 future label；
- 做 shuffled-label 或 mismatched-label sanity check；
- 同时报告 top-1 ADE/FDE 和 minADE/minFDE，说明问题是 mode ranking，而不是没有可用 mode。

## 3. 下一阶段主方向

下一阶段方向固定为：

```text
先诊断 conservative early-stop，
再量化 supervisor 对最终动作的影响，
再做 supervisor ablation，
同时分析 infeasibility，
最后验证 fine-tuning evaluation 是否可靠。
```

写法要谨慎：不是削弱安全，而是减少不必要接管。

推荐表述：

> 下一步我会先判断 early stopping 是由 conservative supervisor intervention 还是 SMPC risk constraints 引起的。之后会测试 reduced-intervention supervisor，在保留 hard safety guard 的前提下，让 phase-aware adaptive-risk SMPC 对 executed trajectory 有更直接的影响。

## 4. 实验路线

### Step 1. 基于当前 best 50-init 做 post-hoc 诊断

先用已有日志，不重跑 CARLA。

输入：

```text
core/results/20260718_104740_50init_finetuned_predictor_validation
```

输出：

- early-stop diagnostic table；
- supervisor intervention summary；
- nominal-final acceleration difference summary；
- infeasibility diagnostic table；
- 中文诊断报告。

关键指标：

| 指标 | 目的 |
|---|---|
| first stop distance to conflict | 判断 ego 是否停得太早 |
| waiting time after stop | 判断等待是否过长 |
| delay after target clearance | 判断释放是否太慢 |
| supervisor active fraction | 衡量 supervisor 接管程度 |
| solver bypass fraction | 衡量 deterministic yield logic 是否绕开 SMPC |
| nominal-final acceleration delta | 衡量 final action 被改动多少 |
| infeasible phase | 解释 feasibility loss 发生在哪 |

Step 1 的结论要回答：

```text
当前 conservative behaviour 主要来自 supervisor/yield logic、SMPC risk constraints，还是 clearance/release logic？
```

当前完成状态：

```text
已完成
```

诊断脚本：

```text
docs/paper/diagnose_supervisor_feedback_step1.py
```

诊断输出：

```text
core/results/20260718_104740_50init_finetuned_predictor_validation/diagnostics_after_supervisor_feedback/
```

主要输出文件：

- `step1_diagnostic_report.md`
- `rollout_diagnostics.csv`
- `infeasible_steps.csv`

当前 Step 1 结论：

- early stop 主要不是 adaptive-risk 本身单独造成，而是由 shared rule-aware yield / supervisor logic 主导；
- fixed-risk 和 adaptive-risk 的第一次停车距离、等待时间和 clearance 后释放延迟非常接近；
- supervisor active fraction 约为 `0.224-0.226`，solver bypass fraction 约为 `0.220-0.222`；
- supervisor active 时 final acceleration 与 nominal acceleration 的平均差异约为 `4.31-4.33 m/s^2`，说明接管强度较高；
- infeasible steps 在 fixed-risk 和 adaptive-risk 中数量相同，且集中在 `critical/pre-clearance`；
- 下一步优先做 reduced-intervention supervisor ablation，而不是先修改 adaptive-risk 公式。

### Step 2. 10-init supervisor ablation

先小规模跑，不直接上 50-init。

实验矩阵：

| SMPC policy | Supervisor setting | 目的 |
|---|---|---|
| fixed-risk | full supervisor | 当前 baseline |
| adaptive-risk | full supervisor | 当前 proposed |
| fixed-risk | reduced-intervention supervisor | 减少接管后的 baseline |
| adaptive-risk | reduced-intervention supervisor | 关键 proposed 诊断 |
| fixed-risk | no supervisor / diagnostic-only | 可选，只做诊断 |
| adaptive-risk | no supervisor / diagnostic-only | 可选，只做诊断 |

`reduced-intervention supervisor` 应保留：

- collision hard guard；
- footprint safety guard；
- near-conflict emergency braking；
- route/lane validity check。

可以放松：

- far-distance forced stopping；
- overly early yield braking；
- target clear 后释放过慢；
- 会掩盖 SMPC 行为差异的非必要 rule/comfort shaping。

当前实现状态：

```text
代码已实现，并已完成多轮 1-init/5-init 诊断性 supervisor ablation。
```

已实现内容：

- `SMPCAgent` 新增 `yield_supervisor_mode`：
  - `full`：默认值，保持当前 best milestone 行为不变；
  - `reduced_intervention`：保留 hard safety guard，但减少远距离 deterministic yield 接管和 post-clearance recovery handoff。
- `VehicleParams` 已支持传入 `yield_supervisor_mode`。
- 新增运行脚本：

```text
core/scripts/carla/run_give_way_10init_supervisor_ablation.sh
```

该脚本会运行两个子实验：

```text
full_supervisor
reduced_intervention_supervisor
```

每个子实验都跑：

```text
smpc_var_risk
smpc_fixed_risk
```

并自动生成：

- post-CARLA safety gate；
- risk-by-conflict-distance diagnostics；
- Step 1 同款 supervisor feedback diagnostic report。

当前 Step 2 阶段性结论：

- `full supervisor` 可以保持当前 best milestone 的安全性，但会强烈主导 final behaviour，导致 fixed-risk 和 adaptive-risk 的 executed trajectory 接近；
- 初始 `reduced_intervention` 版本证明减少 supervisor 接管是有价值的，但过弱时会带来 completion robustness 问题；
- 当前 promising reduced early-stop candidate 将第一次停车距离从 full 的约 `7.3m` 改善到约 `4.2m`，等待时间和 clearance 后释放延迟也下降，说明它确实回应了导师关于 conservative behaviour 的反馈；
- 但当前 promising reduced 版本下 fixed-risk 和 adaptive-risk 仍然非常接近，还不能证明 adaptive-risk 优势；
- 更 aggressive 的 var/fixed separation 版本虽然让 first stop 更靠近 conflict point，并出现少量 var/fixed 差异，但 `solver_failure_frac` 超过 gate 阈值，因此不能作为正式结果；
- 后续小回退版本 `20260725_003211_1init_reduced_stable_boundary_video` 虽然视频显示 ego 在 target 几乎离开时仍 hard-stop，并且 target clear 后仍原地停顿数秒，但它暴露了一个有价值的问题：如果 ego 进入冲突区时 target 已经驶过、前方路径已经 clear，就不应该机械地停一次；
- 当前策略不是简单回到更早停车，而是沿 `20260725_003211` 暴露出的方向修复 clearance/release logic：保留谨慎接近，但增加 clear-path late-stop veto，让 reduced supervisor 在 target nominally passed 时及时释放。
- 更精确的原则是：停车不是 mandatory manoeuvre。只有当 TV 与 EV 预计路径仍存在冲突，或者 EV 已经进入冲突区但 TV 还没驶过时，才应停车；如果 TV 已经越过 EV 的预计冲突/停车区域，EV 应继续谨慎通过，而不是为了让行逻辑机械停车。
- `20260725_005822_1init_reduced_clear_path_release_video` 说明 clear-path release 方向有效，但实现方式有两个不可接受的问题：ego 在 target 离开后仍有 near-zero-speed 停顿，且 release 分支绕开了原有 post-yield recovery / rejoin reference，导致转弯后没有稳定进入正确车道；
- 因此 clear-path release 不能作为一条独立控制分支绕开 recovery。正确方向是：target nominally passed 时提前进入 `released_recovery`，但仍复用已有 `post_yield_rejoin_reference` 和 recovery handoff，保留转弯后正确车道保持。
- 当前冻结 reduced supervisor candidate：

```text
core/results/20260725_023251_5init_reduced_clear_path_release
```

冻结理由：

- 5-init / 10 rollouts 全部 safety gate PASS；
- `completion=True`、`yield_ok=True`、`footprint_collision=False`；
- 转弯后 lane/heading completion 正常，`forced_reference_linearization_frac=0`；
- 上一轮失败的 `init_02` / `init_05` critical pre-clearance infeasibility 已被压到 gate 阈值内：
  - `init_02 fixed: 0.079 -> 0.000`
  - `init_02 var: 0.073 -> 0.000`
  - `init_05 fixed: 0.070 -> 0.004`
  - `init_05 var: 0.057 -> 0.005`
- 平均 `delay_after_clearance` 约 `1.4s`，比原始 conservative full supervisor 更适合作为 reduced-intervention 诊断条件；
- 该版本仍保留 hard safety hold 和 post-yield rejoin / lane recovery，没有为了 release 速度破坏安全或车道保持。

冻结含义：

- 后续不再为了单个 1-init video 或更小 first-stop distance 继续微调 supervisor；
- 该版本作为 `reduced_intervention` 的 stable condition 参与 ablation；
- 如果后续发现严重 non-regression，再回到该冻结点重新诊断，而不是继续叠加局部规则。

当前是否已经足够隔离 supervisor：

```text
已完成第一层正式隔离，但还没完成 adaptive-risk 贡献隔离。
```

已经完成的是第一层正式隔离：`full` vs `reduced_intervention`。这能说明 shared supervisor 确实会掩盖 solver-layer 差异，但还不足以量化 adaptive-risk 本身的贡献。后续至少需要以下证据之一：

- final action 与 nominal SMPC action 的差异在 reduced supervisor 下明显减小；
- fixed-risk 与 adaptive-risk 的 nominal behaviour 本身有差异，但 full supervisor 把 final behaviour 抹平；
- reduced supervisor 下 adaptive-risk 在 safety margin、post-clearance release、smoothness、completion time 或 intervention fraction 上出现稳定优势；
- diagnostic-only / hard-safety-only supervisor 结果表明 adaptive-risk 的优势存在于 solver layer，而不是 supervisor 规则制造出来的。

Formal 5-init supervisor ablation 已完成：

```text
core/results/20260725_125938_5init_formal_supervisor_ablation
```

正式报告：

```text
core/results/20260725_125938_5init_formal_supervisor_ablation/formal_supervisor_ablation_analysis/formal_supervisor_ablation_report.md
```

核心结论：

- full 和 reduced-intervention supervisor 都通过 post-CARLA safety gate；
- reduced supervisor 在 fixed-risk 下把 first-stop distance 从 `8.403m` 降到 `5.263m`，waiting time 从 `8.040s` 降到 `4.200s`，clearance delay 从 `3.720s` 降到 `1.440s`；
- reduced supervisor 在 adaptive-risk 下把 first-stop distance 从 `8.402m` 降到 `5.263m`，waiting time 从 `8.120s` 降到 `4.160s`，clearance delay 从 `3.720s` 降到 `1.400s`；
- supervisor active fraction 和 solver bypass fraction 同时下降，说明原 conservative early-stop 主要由 full supervisor / yield logic 主导；
- reduced supervisor 下仍有少量 infeasible steps，集中在 `critical/pre-clearance` 的 `approach_yield_line` 和 `cautious_approach_observed_target`，但仍低于 gate 阈值；
- fixed-risk 与 adaptive-risk 的 final behaviour 差异仍然很小，因此这个结果是 supervisor contribution evidence，不是 var-risk superiority evidence。

当前是否已经证明 adaptive-risk / var-risk 优势：

```text
还没有。
```

当前只能说：

- adaptive-risk 的 phase-aware 风险释放机制仍然可解释；
- 原 full-supervisor milestone 的 aggregate safety result 可保留；
- reduced supervisor 让方法更接近导师期望的 realistic cautious approach；
- 但 adaptive-risk 相对 fixed-risk 的优势还需要通过更清晰的 ablation 或更有区分度的 scenario/risk-intensity sweep 来证明。

### Step 2b. 借鉴原论文后的 revised proof strategy

原论文的 intersection 结果能证明 `Proposed` 优于 `Fixed Risk`，关键在于：

- final executed control 基本来自 SMPC，没有外层 rule-aware supervisor 把 fixed/proposed 的动作过滤成相似轨迹；
- `Proposed` 优化 risk levels，`Fixed Risk` 固定 risk level，因此差异直接体现在 feasibility、comfort、safety 和 mobility 指标上；
- 评价指标直接服务于 optimizer-level contribution：SMPC feasibility、collision probability、trajectory deviation、jerk、solve time；
- fixed-risk baseline 是一个 ablation，但不是一组 fixed epsilon frontier。

本文不能简单照搬原论文结论，因为 give-way 场景有 right-of-way 规则，supervisor 是合理且必要的。本文应融合原论文思路，把 proposal 优势改成以下三层证明：

```text
Layer 1: Supervisor masking evidence
full supervisor 会把 fixed/adaptive final behaviour 抹平；reduced supervisor 能减少不必要接管但保留 safety。

Layer 2: Optimizer-level risk-allocation evidence
在相同 predictor、同一 reduced supervisor、同一 init/difficulty 下，adaptive-risk 在 solver layer 显示 phase-aware risk tightening/release，并降低 infeasibility 或 nominal-final mismatch。

Layer 3: Fixed-risk frontier / Pareto evidence
adaptive-risk 不只和一个 fixed-risk 比，而是和 conservative/medium/aggressive fixed-risk settings 比。如果它在 safety、feasibility、release delay、completion time、supervisor intervention 之间形成更好的 Pareto trade-off，就构成 proposal 优势。
```

后续可写论文主张：

```text
Compared with a family of fixed-risk SMPC baselines, the proposed phase-aware adaptive-risk SMPC allocates conservatism according to the give-way interaction phase. In safety-critical pre-clearance phases, the rule-aware supervisor may mask final-action differences, but solver-layer diagnostics and fixed-risk frontier analysis show that adaptive risk provides a more favourable safety-performance trade-off without weakening traffic-rule safety.
```

后续不能写：

```text
adaptive-risk universally dominates fixed-risk in final trajectory metrics.
```

因为当前 formal supervisor ablation 已经显示 final trajectory 很容易被 shared supervisor 主导。

### Step 3. fine-tuning sanity check

在继续把 100% mode-ranking 作为强结果前，需要先验证 evaluation pipeline。

输出：

- split integrity report；
- same-test-set metric report；
- input/label leakage checklist；
- shuffled-label 或 mismatched-label sanity test；
- pretrained vs fine-tuned mode probability examples。

可接受的最终说法：

```text
在确认 split 和 evaluation 一致后，fine-tuning 明显改善了 held-out CARLA split 上的 top-probability mode ranking。
```

不要说：

```text
预测问题已经完全解决，或者 fine-tuning 必然带来显著 closed-loop safety 提升。
```

当前完成状态：

```text
已完成第一轮无 GPU sanity check。
```

诊断脚本：

```text
docs/paper/diagnose_multipath_sanity_step3.py
```

诊断输出：

```text
core/results/20260717_232553_prediction_dataset_collection/prediction_dataset_merged/sanity_check_step3/
```

当前结论：

- 未发现 split 泄漏、样本重复或 raster 缺失这类阻塞性问题；
- pretrained 和 fine-tuned 使用同一 test split，样本数均为 `305`；
- pretrained 的 `minADE` 已经较低，但 `top1 ADE/FDE` 很差，说明主要问题是 mode probability ranking；
- fine-tuned 后 `top1 ADE == minADE`，说明最高概率 mode 被校准到了几何最佳 mode；
- 但 test split 的最佳 mode 全部集中在 mode 7，场景多样性有限，所以不能把 `100%` 表述为通用预测能力完全解决；
- 合理叙事是：模型侧 fine-tuning 改善了 CARLA held-out split 上的 mode ranking / probability calibration。

GPU 需求判断：

- split/metrics/leakage sanity check 不需要 GPU；
- 重新跑 SavedModel test evaluation 可用 CPU，但 GPU 更快；
- 重新 fine-tune、shuffled-label training、更多模型对照才需要 GPU。

### Step 4. 如果 10-init 结果有希望，再跑 50-init

只有当 Step 1 和 Step 2 说明 reduced supervisor 有潜力时，才考虑昂贵的 50-init。

当前约束：

```text
在完成导师四条反馈对应的诊断和 ablation 前，不进入新的 50-init milestone 实验。
```

50-init 前必须完成：

- supervisor contribution ablation，证明 full/reduced supervisor 对 final behaviour 的影响；当前 5-init formal ablation 已完成；
- solver-layer 与 final-layer 分离分析，说明 adaptive-risk 的贡献是否被 supervisor 抹平；当前 formal report 已完成第一版；
- infeasibility phase analysis，解释剩余 infeasible steps 发生在哪些 phase / init / policy；当前 formal report 已完成第一版；
- fixed-risk frontier baseline，至少覆盖 conservative / medium / aggressive 三档 fixed-risk setting，避免只赢一个弱 baseline；
- fine-tuning sanity 的可写论文版本，避免过度声称 `100%`；
- 至少一个 adaptive-risk vs fixed-risk frontier 的稳定、可解释优势，或明确说明优势只存在于 solver layer / 特定难度区间。

候选新 milestone：

```text
fine-tuned MultiPath
+ phase-aware adaptive-risk SMPC
+ reduced-intervention safety supervisor
```

升级为新 milestone 的条件：

- 50-init safety gate 全部通过；
- 无 footprint collision；
- 无 give-way violation；
- early-stop distance 降低或无效等待时间缩短；
- adaptive-risk 相比 fixed-risk frontier 至少在一个行为指标或 trade-off 上更清楚：
  - worst-case footprint separation；
  - SMPC feasibility / infeasibility fraction；
  - conflict approach smoothness；
  - completion time；
  - supervisor intervention fraction；
  - nominal-final action consistency；
  - post-clearance release delay。

## 5. 后续图表重点

下一批 graphical results 应该少做普通柱状图，多做行为诊断图。

优先图表：

1. early-stop diagnosis：
   - first stop distance；
   - target clearance time；
   - ego restart time。

2. supervisor dominance：
   - supervisor active fraction by policy/phase；
   - nominal-final acceleration difference。

3. infeasibility analysis：
   - infeasible steps by phase；
   - affected rollout IDs；
   - infeasible distance to conflict。

4. supervisor ablation：
   - full supervisor 下 fixed vs adaptive；
   - reduced supervisor 下 fixed vs adaptive。

5. representative time-series：
   - 当前 conservative case；
   - reduced-intervention 后的改善 case；
   - risk tightening；
   - nominal/final acceleration；
   - target clearance；
   - supervisor active flag。

6. fixed-risk frontier / Pareto plot：
   - fixed-risk conservative / medium / aggressive；
   - adaptive-risk selected setting；
   - x-axis 可用 completion time / post-clearance delay；
   - y-axis 可用 safety margin / infeasible fraction / supervisor active fraction；
   - 标出被 Pareto dominated 的 fixed settings 和 adaptive-risk 的位置。

7. fine-tuning sanity：
   - pretrained vs fine-tuned top-1/minADE；
   - mode probability examples；
   - split integrity summary。

## 6. 代码修改约束

后续代码修改遵守这些规则：

- 不要在新 50-init safety pass 前替代当前 best milestone。
- 不要把 no-supervisor 当最终方法；它只能做 contribution diagnostic。
- 不要为了让 adaptive-risk 更明显而取消 hard safety guard。
- fixed-risk baseline 必须保持静态，不能被 adaptive-risk 改动污染；但必须扩展为 fixed-risk frontier，而不是只保留单个 fixed-risk baseline。
- adaptive-risk 的改动必须独立、可开关、可记录。
- 不要只优化 aggregate metrics；必须加入 stop distance、waiting time、post-clearance delay 等行为指标。
- 不要声称直接超过 reference paper，因为场景和架构不同。
- fine-tuning 没做 sanity check 前，不要过度声称 100% mode-ranking。

## 7. 立即执行任务

当前优先级：

1. 已冻结当前 `reduced_intervention` candidate：
   - 冻结结果目录：`core/results/20260725_023251_5init_reduced_clear_path_release`；
   - 不再继续为了单次视频效果、first-stop distance 或 var/fixed 表面差异调 supervisor；
   - 保留当前 best full supervisor milestone 作为安全 baseline；
   - 当前 frozen reduced 只作为 stable reduced condition，用来回答导师关于 conservative behaviour 和 supervisor dominance 的问题。

2. 已完成正式 supervisor contribution ablation：
   - 结果目录：`core/results/20260725_125938_5init_formal_supervisor_ablation`；
   - 报告：`formal_supervisor_ablation_analysis/formal_supervisor_ablation_report.md`；
   - 结论：reduced supervisor 明显减少 early-stop、等待和 post-clearance delay，同时 full supervisor 确实掩盖 fixed/adaptive final differences；
   - 限制：adaptive-risk final-layer 优势仍弱，不能把该 ablation 写成 var-risk 胜利。

3. 当前正在做 adaptive-risk intensity sweep：
   - 固定 `YIELD_SUPERVISOR_MODE=reduced_intervention`；
   - 先跑 `INIT_COUNT=5`，不要直接上 50-init；
   - 第一轮用 `VARIANT_SET=sensitivity`，比较 risk floor、post-clearance relaxation 和 severity gain；
   - 每个 variant 都同时跑 `smpc_var_risk` 和 `smpc_fixed_risk`；
   - 观察重点是 safety margin、completion time、post-clearance release、supervisor intervention fraction、solver-layer vs final-layer action consistency；
   - 该实验的作用是筛选 adaptive-risk 设置和判断 solver-layer contribution，不足以单独证明 proposal 优于 fixed-risk frontier；
   - 如果所有 final-layer 差异仍小，就把结论写成 supervisor masking / scenario not discriminative，而不是继续调 supervisor。

推荐 5-init 命令：

```bash
conda activate carla_modern

export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export PYTHONPATH=$CARLA_ROOT/PythonAPI/carla:$CARLA_ROOT/PythonAPI/carla/agents:$PYTHONPATH

export GUROBI_HOME=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi1103/linux64
export GUROBI_VERSION=110
export GRB_LICENSE_FILE=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi.lic
export LD_LIBRARY_PATH=$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}

cd /root/autodl-tmp/Research-Project-IMLS/core/scripts/carla

YIELD_SUPERVISOR_MODE=reduced_intervention \
VARIANT_SET=sensitivity \
INIT_COUNT=5 \
ENABLE_CAMERA_VIZ=0 \
PYTHON_BIN=python \
RESULTS_DIR=/root/autodl-tmp/Research-Project-IMLS/core/results/$(date +%Y%m%d_%H%M%S)_5init_reduced_varrisk_sensitivity \
./run_give_way_10init_comprehensive_adaptive_risk_ablation.sh
```

4. 当前 sensitivity sweep 完成后，新增 fixed-risk frontier baseline：
   - 目的：借鉴原论文 `Proposed vs Fixed Risk` 的思想，但把 fixed baseline 扩展为一组 fixed-risk settings，避免只赢一个弱 baseline；
   - 固定同一个 `reduced_intervention` supervisor、同一个 predictor、同一组 init；
   - fixed-risk 至少三档：
     - conservative：更高 tightening / 更低允许风险，预期更安全但更慢、更易 early stop；
     - medium：当前默认 fixed-risk；
     - aggressive：更低 tightening / 更高允许风险，预期更快但可能 infeasible 或需要更多 supervisor 接管；
   - adaptive-risk 选择 sensitivity sweep 中最合理的一档，而不是为了赢 baseline 事后任意调参；
   - 判断方式不是单一指标胜负，而是 Pareto trade-off：
     - same safety 下 completion / release delay 是否更好；
     - same completion 下 safety margin / infeasible fraction 是否更好；
     - same infeasibility 下 supervisor active / bypass fraction 是否更低；
     - solver-layer risk allocation 是否符合 pre-clearance tighten / post-clearance relax 的机制解释。

5. 对后续所有代表性 video 保留 qualitative behaviour gate：
   - ego 应该在检测到 oncoming target 后继续谨慎接近，而不是远距离停车；
   - ego 不应在 target 几乎已经离开、前方路径视觉上已 clear 时才突然 hard-stop；
   - target clear 后 ego 应尽快 release，不应出现数秒 near-zero-speed 停顿；
   - ego 转弯后必须进入正确车道并保持直行；如果 release 版本破坏 post-turn lane keeping，即使 safety gate PASS 也不能升级；
   - 如果 quantitative gate PASS 但 video gate FAIL，该版本只能作为反例，不进入 milestone。

6. 对 var-risk sweep 和 fixed-risk frontier 结果强制输出 solver-layer 与 final-layer 分离指标：
   - nominal SMPC acceleration；
   - final executed acceleration；
   - nominal-final acceleration delta；
   - supervisor active fraction；
   - solver bypass fraction；
   - stop distance、waiting time、delay after target clearance；
   - fixed-risk vs adaptive-risk 的 trajectory/control difference。

7. 对 var-risk sweep 和 fixed-risk frontier 单独做 infeasibility phase analysis：
   - 按 `policy`、`supervisor mode`、`phase`、`distance_to_conflict`、`solver status` 聚合；
   - 区分 critical/pre-clearance、hold-yield-line、post-clearance recovery；
   - 解释 infeasible 后 supervisor/fallback 是否保证 safety。

8. 补充 fine-tuning sanity 的最终证据：
   - 保留当前第一轮无 GPU sanity check 结论；
   - 如时间允许，补 shuffled-label / mismatched-label sanity test 或更多 held-out examples；
   - 论文中避免把 `100%` 说成通用预测能力完全解决，只说改善了当前 held-out CARLA split 的 mode ranking / probability calibration。

9. 完成上述任务后，再决定是否进入 50-init：
   - 如果 reduced condition 在 ablation 中有清晰价值，且 var-risk 相对 fixed-risk frontier 有至少一个稳定优势，再跑 50-init 验证新 milestone；
   - 如果 var-risk 优势只存在于 solver layer，也可以不急于 50-init，而是把结论写成 supervisor masking / limitation；
   - 不允许在这些证据缺失时，为了补 aggregate table 直接进入 50-init。

## 8. 后续工作规则

之后每次问问题、改代码、跑实验，都先检查是否服务于以下目标之一：

- 解释 early conservative stopping；
- 量化 supervisor contribution；
- 分离 SMPC nominal behaviour 和 supervisor filtered behaviour；
- 分析 infeasibility；
- 验证 fine-tuning evaluation 是否可信；
- 证明 adaptive-risk / var-risk 在被正确隔离 supervisor 影响后，相比 fixed-risk 至少有一个稳定、可解释的优势；
- 生成支持上述结论的 graphical evidence。

不服务于这些目标的工作，默认降级为低优先级。
