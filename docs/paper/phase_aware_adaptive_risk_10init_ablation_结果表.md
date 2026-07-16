# Phase-Aware Adaptive Risk 10-init Ablation 结果表

## 1. 结果目录与结论

结果目录：

```text
core/results/20260711_120356_10init_adaptive_risk_ablation
```

运行时间：

```text
01:14:09
```

ablation 对比：

| Variant | Risk profile | 含义 |
| --- | --- | --- |
| `phase_floor` | `adaptive_interaction_severity` | 当前最终方法，包含 phase-aware pre-clearance floor |
| `no_phase_floor` | `adaptive_interaction_severity_no_floor` | 保留 adaptive severity 和 target-cleared relaxation，但关闭 pre-clearance floor |

核心结论：

```text
10-init ablation 可用。
两组 variant 都 PASS，没有 collision / yield violation / completion failure。
phase-aware floor 的贡献非常清楚：
  critical / pre-clearance 的 var-fixed tightening gap
  从 no-floor 的约 +0.060 提升到 phase-floor 的 +0.160。
```

这说明：

```text
adaptive severity mapping 本身会带来轻微 pre-clearance 保守性；
phase-aware floor 是让该保守性在 critical phase 明确、稳定、可解释的关键组件。
```

## 2. Safety Gate

来源：

```text
postcarla_trajectory_gate.json
```

| Variant | Policy | PASS | Solver failure max / mean | Center dmin min / mean (m) | Footprint separation min / mean (m) | Collision | Yield OK | Completion |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| `phase_floor` | `smpc_fixed_risk` | 10/10 | 0.0245 / 0.0070 | 4.7398 / 5.3871 | 1.3061 / 2.1229 | False | True | True |
| `phase_floor` | `smpc_var_risk` | 10/10 | 0.0243 / 0.0064 | 4.7651 / 5.3975 | 1.3300 / 2.1345 | False | True | True |
| `no_phase_floor` | `smpc_fixed_risk` | 10/10 | 0.0244 / 0.0069 | 4.7727 / 5.4123 | 1.3491 / 2.1527 | False | True | True |
| `no_phase_floor` | `smpc_var_risk` | 10/10 | 0.0244 / 0.0065 | 4.7451 / 5.4106 | 1.3125 / 2.1503 | False | True | True |

解释：

- ablation 没有破坏安全 gate。
- 两组 variant 都可以作为论文消融实验结果。
- safety metric 差异不应作为主结论；主结论应放在 risk scheduling 机制上。

## 3. Phase-Aware Risk 消融表

来源：

```text
risk_by_conflict_distance_comparison.csv
```

### 3.1 `phase_floor`

| Bucket / Phase | Rows | Var tightening | Fixed tightening | Var - Fixed | Var floor applied | Nominal accel delta | Supervisor override |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| approach / pre-clearance | 6 | 1.6800 | 1.6400 | +0.0400 | 1.0000 | -0.0655 | 0.8869 / 0.8869 |
| critical / pre-clearance | 10 | 1.8000 | 1.6400 | +0.1600 | 1.0000 | -0.4218 | 0.9976 / 1.0000 |
| near / pre-clearance | 2 | 1.8500 | 1.6400 | +0.2100 | 1.0000 | 0.0000 | 1.0000 / 1.0000 |
| critical / post-clearance | 8 | 1.2816 | 1.6400 | -0.3584 | 0.0000 | +0.0103 | 0.0000 / 0.0000 |
| near / post-clearance | 10 | 1.2816 | 1.6400 | -0.3584 | 0.0000 | +0.0004 | 0.0000 / 0.0000 |

### 3.2 `no_phase_floor`

| Bucket / Phase | Rows | Var tightening | Fixed tightening | Var - Fixed | Var floor applied | Nominal accel delta | Supervisor override |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| approach / pre-clearance | 6 | 1.6742 | 1.6400 | +0.0342 | 0.0000 | -0.0633 | 0.8869 / 0.8869 |
| critical / pre-clearance | 10 | 1.7003 | 1.6400 | +0.0603 | 0.0000 | -0.4045 | 0.9976 / 0.9976 |
| near / pre-clearance | 2 | 1.7315 | 1.6400 | +0.0915 | 0.0000 | 0.0000 | 1.0000 / 1.0000 |
| critical / post-clearance | 8 | 1.2816 | 1.6400 | -0.3584 | 0.0000 | -0.0026 | 0.0000 / 0.0000 |
| near / post-clearance | 10 | 1.2816 | 1.6400 | -0.3584 | 0.0000 | -0.0008 | 0.0000 / 0.0000 |

### 3.3 Floor 增益

| Bucket / Phase | Phase-floor var tightening - No-floor var tightening | 解释 |
| --- | ---: | --- |
| approach / pre-clearance | +0.0058 | approach 中 adaptive severity 已接近 floor，因此 floor 增益较小 |
| critical / pre-clearance | +0.0997 | 核心证据：critical phase 的保守性被 floor 明确抬高 |
| near / pre-clearance | +0.1185 | near pre-clearance 样本少，只作为辅助证据 |
| critical / post-clearance | 0.0000 | clearance 后两者一致放松，不受 floor 影响 |
| near / post-clearance | 0.0000 | clearance 后两者一致放松，不受 floor 影响 |

## 4. Paper Metrics

来源：

```text
df_full.csv
paper_metrics_summary.csv
```

### 4.1 `phase_floor`

| Metric | Fixed mean | Var mean | Var - Fixed paired mean | 解释 |
| --- | ---: | ---: | ---: | --- |
| Completion time | 10.0050 | 10.0150 | +0.0100 | 基本一致 |
| Feasibility percent | 0.9930 | 0.9936 | +0.0005 | 基本一致 |
| Average solve time | 0.0735 | 0.0844 | +0.0109 | var 有额外求解开销 |
| dmin_TV | 5.3871 | 5.3975 | +0.0104 | 基本一致 |
| Avg longitudinal jerk | 4.0519 | 4.2905 | +0.2386 | 10-init 小样本中 var 略高 |
| Solver failure frac | 0.0070 | 0.0064 | -0.0005 | 基本一致 |

### 4.2 `no_phase_floor`

| Metric | Fixed mean | Var mean | Var - Fixed paired mean | 解释 |
| --- | ---: | ---: | ---: | --- |
| Completion time | 10.0500 | 10.0450 | -0.0050 | 基本一致 |
| Feasibility percent | 0.9931 | 0.9935 | +0.0005 | 基本一致 |
| Average solve time | 0.0670 | 0.0866 | +0.0196 | var 有额外求解开销 |
| dmin_TV | 5.4123 | 5.4106 | -0.0017 | 基本一致 |
| Avg longitudinal jerk | 4.2440 | 4.1485 | -0.0955 | 基本一致 |
| Solver failure frac | 0.0069 | 0.0065 | -0.0005 | 基本一致 |

## 5. 论文可写结论

中文：

```text
为验证 phase-aware pre-clearance floor 的必要性，本文进一步进行了 10-init 消融实验。实验保留相同的 scenario、initial states、rule-aware supervisor 和 target-cleared relaxation，仅关闭 adaptive risk 中的 pre-clearance tightening floor。结果显示，两组 ablation 均保持 10/10 PASS，说明 floor 不会破坏基础安全性和可行性。相比 no-floor variant，phase-floor variant 将 critical / pre-clearance 阶段的 var-fixed tightening gap 从约 +0.060 提升至 +0.160，而 post-clearance 阶段两者均放松至 1.2816。这表明 phase-aware floor 是形成清晰、稳定、可解释的 pre-clearance 风险保守性的关键组件。
```

英文：

```text
To evaluate the contribution of the phase-aware pre-clearance floor, a 10-init ablation was conducted with the same scenario, initial states, rule-aware supervisor, and target-clearance relaxation, while disabling only the pre-clearance tightening floor. Both ablation variants achieved 10/10 PASS results, indicating that the floor does not compromise safety or feasibility. Compared with the no-floor variant, the phase-floor variant increased the var-minus-fixed tightening gap in the critical pre-clearance phase from approximately +0.060 to +0.160, while both variants relaxed to 1.2816 after target clearance. This demonstrates that the phase-aware floor is the key component that makes the pre-clearance risk conservatism explicit, stable, and interpretable.
```

## 6. 是否需要继续改

不建议继续改主实验参数。

当前结果已经形成清晰链条：

```text
50-init main result:
  证明最终方法稳定、安全、可扩展。

10-init ablation:
  证明 phase-aware pre-clearance floor 是 adaptive risk 贡献更清晰的关键机制。
```

如果后续还要增强论文，可以做图而不是继续调参：

- `critical/pre-clearance` risk tightening bar plot。
- selected init 的 `risk_tightening vs time`。
- selected init 的 `nominal_accel vs final_accel`，解释 supervisor 与 adaptive risk 的分工。

