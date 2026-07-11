# Phase-Aware Adaptive Risk 50-init 结果表

## 1. 结果目录与结论

结果目录：

```text
core/results/20260710_164024_50init_phase_floor_final_dissertation
```

当前最佳代码 baseline：

```text
eea6c53f547304af92f697d683f3f12d8af70226
```

运行时间：

```text
03:07:43
```

后处理状态：

```text
batch_postprocess: ok
postcarla_trajectory_gate: PASS
paper_metrics_summary: generated
risk_by_conflict_distance: generated
```

总体结论：

```text
50-init full experiment 可以作为当前论文主结果。
100 条 required SMPC runs 全部 PASS。
没有 footprint collision。
没有 yield rule violation。
没有 completion failure。
phase-aware adaptive risk 在 50-init 中稳定实现：
  pre-clearance 更保守；
  post-clearance 更放松。
```

论文表述边界：

```text
可以写：
  adaptive risk 在 solver risk layer 和 nominal control layer 产生明确机制差异。

不建议写：
  adaptive risk 在所有 final trajectory safety metrics 上显著优于 fixed risk。
```

原因：

- final control 仍主要由 rule-aware supervisor 保证 safety。
- 50-init 中 var/fixed 的最终 safety metrics 非常接近。
- adaptive risk 的最强证据来自 phase-aware risk tightening 和 nominal acceleration，而不是最终轨迹距离的大幅提升。

## 2. Safety Gate 主结果表

来源：

```text
postcarla_trajectory_gate.json
```

| Policy | PASS | Solver failure max | Solver failure mean | Center dmin min / mean (m) | Footprint separation min / mean (m) | Collision | Yield OK | Completion |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `smpc_fixed_risk` | 50/50 | 0.0244 | 0.0057 | 4.4465 / 5.4112 | 0.9596 / 2.1504 | False | True | True |
| `smpc_var_risk` | 50/50 | 0.0293 | 0.0062 | 4.3771 / 5.4114 | 0.8745 / 2.1504 | False | True | True |

解释：

- 两个 policy 都达到 50/50 PASS。
- 最小 footprint separation 出现在 init 31：
  - `smpc_var_risk`: 0.8745 m
  - `smpc_fixed_risk`: 0.9596 m
- 该样本是最紧张 case，但仍无 footprint collision，且 yield rule 满足。
- solver failure 最高为 0.0293，低于 gate threshold 0.05。

## 3. Paper Metrics 汇总表

来源：

```text
df_full.csv
paper_metrics_summary.csv
```

表中 `CI95` 为 `1.96 * std / sqrt(50)`。

| Metric | `smpc_fixed_risk` mean ± CI95 | `smpc_var_risk` mean ± CI95 | Var - Fixed paired mean ± CI95 | 论文解释 |
| --- | ---: | ---: | ---: | --- |
| Completion time (s) | 10.0130 ± 0.0731 | 10.0220 ± 0.0701 | +0.0090 ± 0.0139 | 两者完成时间基本一致 |
| Feasibility percent | 0.9943 ± 0.0020 | 0.9938 ± 0.0022 | -0.0005 ± 0.0005 | adaptive risk 未造成明显可行性下降 |
| Average solve time (s) | 0.0649 ± 0.0036 | 0.0856 ± 0.0031 | +0.0207 ± 0.0045 | adaptive risk 有额外求解开销 |
| dmin_TV (m) | 5.4112 ± 0.1398 | 5.4114 ± 0.1420 | +0.0002 ± 0.0085 | 最终 TV 距离几乎相同 |
| Max lateral acceleration | 4.9906 ± 0.2081 | 4.9924 ± 0.2081 | +0.0019 ± 0.0022 | 舒适性接近 |
| Avg longitudinal jerk | 4.0898 ± 0.1341 | 4.0980 ± 0.1305 | +0.0082 ± 0.0445 | 纵向 jerk 接近 |
| Avg lateral jerk | 4.0748 ± 0.1028 | 4.0784 ± 0.1044 | +0.0036 ± 0.0246 | 横向 jerk 接近 |
| Solver failure frac | 0.0057 ± 0.0020 | 0.0062 ± 0.0022 | +0.0005 ± 0.0005 | var 略高，但远低于 gate threshold |

论文可写结论：

```text
Compared with fixed-static risk, phase-aware adaptive risk introduces a moderate computational overhead but preserves completion, feasibility, distance safety, and comfort-level metrics at comparable levels.
```

中文表述：

```text
与 fixed-static risk 相比，phase-aware adaptive risk 带来一定求解时间开销，但在 50-init 中保持了相近的完成时间、可行性、安全距离和舒适性指标。
```

## 4. Phase-Aware Risk 机制表

来源：

```text
risk_by_conflict_distance_comparison.csv
```

表中均值按 scenario/init/bucket/clearance_phase 聚合。

| Bucket / Phase | Rows | Var tightening | Fixed tightening | Var - Fixed | Var floor applied | Fixed floor applied | Nominal accel delta | Final accel delta | Supervisor override |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| approach / pre-clearance | 26 | 1.6800 | 1.6400 | +0.0400 | 1.0000 | 0.0000 | -0.0223 | -0.0001 | 0.9201 / 0.9201 |
| critical / pre-clearance | 50 | 1.7997 | 1.6400 | +0.1597 | 0.9995 | 0.0000 | -0.4001 | -0.0032 | 0.9985 / 0.9985 |
| near / pre-clearance | 3 | 1.8500 | 1.6400 | +0.2100 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 / 1.0000 |
| critical / post-clearance | 47 | 1.2816 | 1.6400 | -0.3584 | 0.0000 | 0.0000 | -0.0076 | -0.0026 | 0.0000 / 0.0000 |
| near / post-clearance | 50 | 1.2816 | 1.6400 | -0.3584 | 0.0000 | 0.0000 | -0.0005 | +0.0069 | 0.0000 / 0.0000 |

关键观察：

1. `approach / pre-clearance`：
   - var risk 比 fixed risk 高 `+0.04`。
   - var floor applied fraction 为 `1.0`。

2. `critical / pre-clearance`：
   - var risk 比 fixed risk 高约 `+0.16`。
   - nominal acceleration delta 为 `-0.4001`，说明 solver nominal layer 明显更保守。
   - final acceleration delta 接近 0，因为 supervisor override fraction 接近 1。

3. `near / pre-clearance`：
   - 样本行较少，只有 3 个 init/bucket rows。
   - floor 仍按设计生效，但论文中不宜过度强调 near pre-clearance 的统计显著性。

4. `critical / post-clearance` 和 `near / post-clearance`：
   - var risk 比 fixed risk 低 `-0.3584`。
   - supervisor override fraction 为 0。
   - 说明 target cleared 后 adaptive risk 成功放松。

论文可写结论：

```text
The adaptive-risk policy consistently applies a higher tightening before target clearance and relaxes after clearance. The most pronounced solver-layer behavioural difference appears in the pre-clearance critical phase, where the adaptive policy increases tightening from 1.64 to approximately 1.80 and yields a more conservative nominal acceleration.
```

中文表述：

```text
adaptive-risk policy 在 target clearance 前稳定施加更高风险收紧，并在 clearance 后自动放松。其中 critical / pre-clearance 阶段最能体现机制贡献：risk tightening 从 fixed baseline 的 1.64 提升到约 1.80，同时 solver nominal acceleration 平均降低约 0.40，表现出更保守的名义规划行为。
```

## 5. Worst-Case 样本检查

来源：

```text
postcarla_trajectory_gate.json
```

### 5.1 最小 footprint separation

| Rank | Init | Policy | Footprint separation (m) | Center dmin (m) | Solver failure | Collision | Yield OK |
| ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| 1 | 31 | `smpc_var_risk` | 0.8745 | 4.3771 | 0.0106 | False | True |
| 2 | 31 | `smpc_fixed_risk` | 0.9596 | 4.4465 | 0.0053 | False | True |
| 3 | 17 | `smpc_fixed_risk` | 1.0689 | 4.5384 | 0.0154 | False | True |
| 4 | 17 | `smpc_var_risk` | 1.0697 | 4.5391 | 0.0205 | False | True |
| 5 | 29 | `smpc_fixed_risk` | 1.0783 | 4.5502 | 0.0154 | False | True |
| 6 | 29 | `smpc_var_risk` | 1.0784 | 4.5503 | 0.0154 | False | True |

### 5.2 最高 solver failure

| Rank | Init | Policy | Solver failure | Footprint separation (m) | Center dmin (m) | Status |
| ---: | ---: | --- | ---: | ---: | ---: | --- |
| 1 | 19 | `smpc_var_risk` | 0.0293 | 1.6500 | 5.0195 | PASS |
| 2 | 37 | `smpc_var_risk` | 0.0245 | 1.6767 | 5.0433 | PASS |
| 3 | 10 | `smpc_var_risk` | 0.0244 | 1.5480 | 4.9323 | PASS |
| 4 | 19 | `smpc_fixed_risk` | 0.0244 | 1.6776 | 5.0448 | PASS |
| 5 | 10 | `smpc_fixed_risk` | 0.0243 | 1.5474 | 4.9318 | PASS |
| 6 | 37 | `smpc_fixed_risk` | 0.0243 | 1.6783 | 5.0449 | PASS |

解释：

- 最紧张的 footprint 样本仍有 `0.8745 m` separation，未发生 footprint collision。
- solver failure 最高为 `0.0293`，低于 `0.05` gate threshold。
- solver failure 较高的 init 在 var/fixed 中基本同步出现，说明主要来自初始条件难度，而不是 adaptive risk 单独导致。

## 6. 已发现问题与改进方案

### 6.1 阻塞性问题

无。

当前 50-init 结果可以作为论文主实验结果使用。

### 6.2 非阻塞 caveats

| Caveat | 影响 | 建议写法 / 后续处理 |
| --- | --- | --- |
| 没有 `notv` reference | `hausdorff_dist_notv` 为空 | 论文不要报告 Hausdorff-to-notv；只报告 completion、dmin、jerk、feasibility、risk diagnostics |
| `smpc_var_risk` solve time 更高 | adaptive risk 有计算开销 | 如实写成 trade-off：约 `+0.0207 s` per solve |
| pre-clearance critical supervisor override 接近 1 | final accel 差异被 supervisor 抹平 | 论文应强调 solver nominal layer，而非 final control layer |
| `near / pre-clearance` 样本较少 | near pre-clearance 统计不强 | 重点讨论 `critical / pre-clearance` 和 `post-clearance near/critical` |
| init 31 footprint separation 最小 | 最紧张样本 var 比 fixed 低约 0.085 m | 仍 PASS；可作为 worst-case safety 分析，不建议继续调参 |

## 7. 推荐论文结论段

中文：

```text
在 50 个初始条件、共 100 条 required SMPC rollout 中，phase-aware adaptive-risk policy 与 fixed-static baseline 均实现 50/50 PASS，无 footprint collision、无 yield rule violation，且均完成交叉口左转任务。与 fixed-static risk 相比，adaptive-risk policy 在 target clearance 前的 approach 和 critical phases 施加更高 chance-constraint tightening，尤其在 critical / pre-clearance 阶段将 tightening 从 1.64 提升到约 1.80，并使 solver nominal acceleration 平均降低约 0.40，表现出更保守的名义规划行为。target clearance 后，adaptive risk 自动放松到 1.2816，低于 fixed-static baseline。结果表明，本文方法能够在不破坏 rule-aware safety gate 的前提下，实现符合让行交互相位的风险调度。
```

英文：

```text
Across 50 initial conditions and 100 required SMPC rollouts, both the phase-aware adaptive-risk policy and the fixed-static baseline achieved 50/50 PASS results with no footprint collision, no yield-rule violation, and successful left-turn completion. Compared with the fixed-static baseline, the adaptive-risk policy applied higher chance-constraint tightening before target clearance, increasing the tightening from 1.64 to approximately 1.80 in the critical pre-clearance phase and producing a more conservative nominal acceleration. After target clearance, the adaptive risk relaxed to 1.2816, below the fixed-static level. These results indicate that the proposed method provides interaction-phase-aware risk scheduling without compromising the rule-aware safety gate.
```

## 8. 推荐用于论文的表格清单

建议 Results 章节使用以下三张主表：

1. Safety Gate 主表：
   - 使用本文档第 2 节。
   - 证明 50-init safety/stability/completion。

2. Paper Metrics 主表：
   - 使用本文档第 3 节。
   - 证明 adaptive risk 没有明显破坏效率、可行性和舒适性，但有求解开销。

3. Phase-Aware Risk 机制表：
   - 使用本文档第 4 节。
   - 证明你的核心贡献：pre-clearance 更保守、post-clearance 更放松。

建议 Discussion 章节使用第 5 和第 6 节：

- worst-case safety
- caveats
- supervisor 与 adaptive risk 的贡献边界

## 9. 后续 Ablation 计划

为进一步突出 adaptive risk 的贡献，后续新增 lightweight ablation：

```text
script:
  core/scripts/carla/run_give_way_10init_adaptive_risk_ablation.sh

baseline commit:
  eea6c53f547304af92f697d683f3f12d8af70226
```

该 ablation 不改变主实验参数，不替换当前 50-init 主结果。它只比较两种 adaptive risk mapping：

| Variant | Risk profile | 目的 |
| --- | --- | --- |
| `phase_floor` | `adaptive_interaction_severity` | 当前最终方法，包含 approach/critical/near pre-clearance floor |
| `no_phase_floor` | `adaptive_interaction_severity_no_floor` | 关闭 pre-clearance floor，但保留 adaptive severity 和 target-cleared relaxation |

预期用于论文的证明：

```text
phase_floor:
  pre-clearance approach/critical risk tightening > fixed risk
  post-clearance risk tightening < fixed risk

no_phase_floor:
  pre-clearance critical risk tightening 明显弱于 phase_floor，
  可证明 phase-aware floor 是形成清晰风险调度的关键组件。
```

