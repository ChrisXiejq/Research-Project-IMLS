# Day11 时序偏移稳健性结果与最终论文定位

> 完成时间：2026-08-02
>
> 状态：80/80 rollouts PASS；16/16 cells PASS；audit/analysis PASS。

## 1. 实验完整性

Day11 是 Day10 的局部稳健性扩展：

```text
B1 / B0
× fixed-medium / adaptive floor_weak
× assertive / reactive target
× target start offset -3 m / +3 m
× held-out ego init 46–50
= 80 rollouts
```

完整性结果：

- 80/80 `ran_successfully=true`；
- 16/16 cell post-CARLA gate PASS；
- 0 collision；
- 0 yield-order failure；
- 0 invalid probability/covariance；
- frozen models、calibration、controller、A3 authority、reactive parameters 和 init 不变；
- 中断只由 CARLA timeout 引起，resume 跳过所有成功 rollout；
- raw rollout 没有因最终审计修复而改变。

原 Day10 audit 要求每一个 reactive cell 都出现 response-active sample。Day11 的 `+3 m` 扰动使四个 reactive cells 都没有触发，而 `-3 m` cells 分别有 75–76 个 active samples。这正是 timing shift 改变交互机制的观测结果。最终 audit 使用合理的 factorial gate：每个 predictor×policy 在两个 offset 合并后必须实际覆盖 reactive activity；四组均 PASS。

## 2. 统计方法

虽然有 20 个配对 rollout conditions，但只有 5 个独立 ego init。正式推断因此采用：

1. 先计算每个 condition 的 paired effect；
2. 再在每个 ego init 内聚合 style/offset conditions；
3. 对 5 个 init-cluster means 做 deterministic bootstrap 与 exact sign flip；
4. 在每个预注册 inference family 内做 Holm 校正。

20 Hz simulator steps 和同一 init 下的重复 conditions 都不被当成独立样本。因为只有 5 个 init，双侧 exact p 的理论最小值为 0.0625；本实验主要报告 effect size、方向一致性和不确定性，而不是追求显著性标签。

## 3. B1 相对 B0 的闭环效果

跨两个 target styles 和两个 offsets：

| Policy | B1−B0 adjusted delay (s) | Init-cluster 95% CI | 方向一致性 | Footprint (m) | Solver failure | Supervisor active |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed-medium | -0.703 | [-1.105, -0.208] | 4/5 init 更快 | -0.083 | +0.00044 | +0.00846 |
| adaptive | -0.558 | [-0.878, -0.235] | 4/5 更快，1/5 相同 | -0.043 | +0.00119 | +0.00830 |

两种 policy 下 B1 都表现出约 0.56–0.70 s 的 clearance-adjusted efficiency gain，但同时：

- footprint margin 略小；
- solver failure 增加约 0.04–0.12 percentage points；
- supervisor active fraction 增加约 0.83–0.85 percentage points。

五个 init 的 exact p 均不可能低于 0.0625；predictor family 内 Holm 后均不显著。因此论文应写成“方向一致、效果量较大的局部稳健性证据”，不能写成大样本统计证明。

这也修正了 Day10 offset=0 的结论：B1 在单一 nominal timing 下没有跨 policy 的平均优势，但在 ±3 m 扰动合并后出现稳定的效率方向。模型收益不是 universal，也不是完全不存在，而是会随 arrival regime 和 controller response 改变。

## 4. Adaptive 相对 fixed-medium

| Predictor | Adaptive−fixed delay (s) | Footprint (m) | Solver failure | Supervisor active |
| --- | ---: | ---: | ---: | ---: |
| B1 | +0.095 | +0.119 | +0.00162 | -0.00029 |
| B0 | -0.050 | +0.078 | +0.00087 | -0.00013 |

Adaptive 没有形成稳定效率优势：

- B1 下平均慢 0.095 s；
- B0 下平均快 0.050 s；
- 两者都提高 footprint separation，但也略增 solver failure；
- 所有 policy-family Holm p 均为 1.0。

因此，原始目标“adaptive risk 普遍优于 fixed risk”继续不受支持。更准确的论点是：adaptive risk 改变 safety–feasibility trade-off，其价值依赖 predictor 和 arrival regime。

## 5. Timing shift 的机制作用

`+3 m − -3 m` 的描述性变化在四个 predictor×policy 组合中方向一致：

| 组合 | Δ adjusted delay (s) | Δ footprint (m) | Δ solver failure | Δ supervisor active |
| --- | ---: | ---: | ---: | ---: |
| B1 fixed-medium | -0.220 | +0.519 | +0.0205 | -0.0707 |
| B1 adaptive | +0.010 | +0.896 | +0.0238 | -0.0694 |
| B0 fixed-medium | -0.325 | +0.444 | +0.0197 | -0.0648 |
| B0 adaptive | -0.375 | +0.660 | +0.0214 | -0.0633 |

Timing shift 几乎不产生一致的 efficiency change，却显著改变：

- target reactive activation：`-3 m` 有 75–76 active samples，`+3 m` 为 0；
- footprint separation：增加 0.44–0.90 m；
- solver failure：增加约 2.0–2.4 percentage points；
- supervisor intervention：降低约 6.3–7.1 percentage points。

方向在 5/5 init 上一致，但 exact p 的最小值为 0.0625，且 offset family Holm 后为 1.0。它支持强机制性、局部描述结论，不支持广泛统计外推。

Policy×offset 的 footprint interaction 为：

- B1：+0.377 m；
- B0：+0.216 m。

这表明 adaptive 相对 fixed 的 margin benefit 随 arrival regime 改变，但只有 5 个 independent init，仍应作为 conditional effect 报告。

## 6. 最终假设判定

### 得到支持或部分支持

`H-data/adaptation`：扩展到受控 V2 interaction dataset 后，简单 B1 adaptation 相对 pretrained B0 显著改善同分布离线预测。

`H-sequence-use`：T1/T2 的 zero/shuffle diagnostic 证明 Transformer 确实使用显式交互序列。

`H-offline/closed-loop-coupling`：offline predictor gain 的闭环效果受 risk policy、arrival timing、solver 和 supervisor 共同调节。Day10 与 Day11 的差异直接支持这一中心论点。

`H-B1-local-robustness`：B1 在 ±3 m 局部 timing shift 下、两种 risk policy 中均呈现较大的效率改善方向，但伴随较小 margin 和更多 controller intervention。由于只有 5 个 init，该假设获得效果量层面的支持，而非确认性统计证明。

### 被否定或不支持

`H-adaptive-universal`：adaptive risk 普遍优于 fixed risk。Day5、Day10、Day11 均不支持。

`H-Transformer-best`：Transformer 是当前数据下最优模型。T1/T2 使用序列，但未超过简单 B1。

`H-complexity-guarantee`：更复杂的 interaction/distribution head 必然更好。matched controls 反驳。

`H-global-calibration-tail`：总体 validation calibration 能可靠迁移到 response-active tail。Day8/Gap2 明确反驳。

`H-offline-implies-closed-loop`：离线指标改善必然产生统一闭环收益。Day10/Day11 共同反驳。

## 7. 最终论文定位

推荐标题：

```text
Interaction-Aware Prediction and Predictor–Risk Coupling for
Give-Way Intersection Planning in CARLA
```

若希望保留研究转向叙事：

```text
From Adaptive Risk Allocation to Interaction-Aware Prediction:
A Controlled Closed-Loop Study at Give-Way Intersections
```

中心论点：

> 在 give-way planning 中，adaptive risk 的效果不能脱离 prediction distribution、arrival regime 和 runtime authority 单独评价。受控交互数据上的简单 predictor adaptation 能显著改善离线预测，并在局部 timing perturbations 下呈现闭环效率收益；Transformer 确实利用交互序列，但额外复杂度不保证最优概率预测。最终 safety–efficiency 表现由 predictor、risk policy、solver 和 supervisor 的耦合共同决定。

机器学习贡献应表述为：

1. 构建 200-rollout、paired 2×2 interaction dataset，并严格按 init 分组；
2. 比较 pretrained、simple adaptation、matched MLP 和 Transformer variants；
3. 使用 trajectory NLL、coverage、covariance audit 和 validation-only calibration，而不只报告 ADE；
4. 使用 zero/shuffle input ablation 证明 sequence use；
5. 将 frozen predictor packages 部署到 160 条正式 closed-loop rollouts（Day10 + Day11），检验 offline-to-closed-loop transfer。

论文不应宣称发明了普遍优于现有方法的新 Transformer。更有价值且证据更完整的贡献是：在严格 matched controls 下说明何时 interaction modelling 有效、何时简单 adaptation 更可靠，以及为什么 prediction gain 不会自动成为 adaptive-risk closed-loop gain。

## 8. 证据路径

```text
docs/paper/generated/day11/day11_timing_shift_snapshot.tar.gz.json
docs/paper/generated/day11/evidence/DAY11_COMPLETE.json
docs/paper/generated/day11/evidence/day11_closed_loop_audit.json
docs/paper/generated/day11/analysis/day11_analysis_summary.json
docs/paper/generated/day11/analysis/day11_rollout_metrics.csv
docs/paper/generated/day11/analysis/day11_cell_summary.csv
docs/paper/generated/day11/analysis/day11_paired_contrasts.csv
```

完整 128 MB snapshot 保留在服务器，SHA-256 为
`9928d53821be27a765d1879e0d218fca4284fa216aaccfe309f36a480bfd1ac9`。Git 仅保存可重复正式统计所需的 640 KB curated evidence，避免提交逐步日志、模型输入和其他大文件。
