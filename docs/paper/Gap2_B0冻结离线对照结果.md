# Gap 2：B0 冻结离线对照结果

> 完成时间：2026-08-02
>
> 状态：PASS；post-selection reporting only；Day8/Day10 选择不变。

## 1. 实验完整性

- B0 权重与 Day10 frozen contract 的 SHA-256 tree 一致；
- B0 calibration 只在 Day7 validation split 拟合；
- B0 与 B1 使用相同 test split、subsets、anchors、horizon 和 evaluator；
- test 没有用于训练、调参或重新选择模型；
- 正式 closed-loop predictor 仍为 `B1 / seed 37`；
- summary 在本地由原始 JSON 确定性重建并逐字节一致。

B0 validation-only calibration：

```text
temperature = 2.5198420998
covariance_scale = 0.0937915568
```

## 2. 全部 test 数据结果

Test 包含 315 个 full-horizon windows、20 个 rollouts、5 个独立 init groups。

| Metric | B0 pretrained | B1 adapted | B1 − B0 | 方向 |
| --- | ---: | ---: | ---: | --- |
| top-1 ADE (m) | 1.2988 | 0.1059 | -1.1929 | B1 更好 |
| top-1 FDE (m) | 2.6845 | 0.1292 | -2.5553 | B1 更好 |
| uncalibrated rollout-macro NLL | 2.1707 | 1.8571 | -0.3136 | B1 更好 |
| calibrated rollout-macro NLL | 0.5821 | -2.0686 | -2.6507 | B1 更好 |
| calibrated coverage MAE | 0.4068 | 0.0766 | -0.3303 | B1 更好 |

因此，B1 相对原始 pretrained B0 的离线改善不是只来自 seed 选择或只在一个 target style 出现。assertive 与 reactive subset 的 ADE、FDE、uncalibrated NLL 和 calibrated NLL 方向均支持 B1。

论文可以写成：

> 在新增的受控交互数据分布上，冻结的简单 B1 adaptation 相对原始 pretrained predictor 大幅降低点预测误差，并改善总体 rollout-level likelihood；但这种 offline gain 没有在 Day10 中转化为跨 risk-policy 的单调闭环收益。

这正好加强论文的 predictor–controller coupling 主线，而不是证明“模型离线更好，所以闭环必然更好”。

## 3. Response-active tail 负结果

`response_active` 只有 15 windows、6 rollouts、3 个 init groups，必须单独报告且避免过度统计解释：

| Metric | B0 | B1 | B1 − B0 |
| --- | ---: | ---: | ---: |
| top-1 ADE (m) | 1.7634 | 0.9420 | -0.8214 |
| top-1 FDE (m) | 4.7083 | 1.2450 | -3.4633 |
| uncalibrated NLL | 2.4718 | 2.0763 | -0.3955 |
| calibrated NLL | 2.9589 | 8.5728 | +5.6139 |
| calibrated coverage MAE | 0.4182 | 0.4426 | +0.0244 |

B1 在 response-active tail 上仍有更好的 point accuracy 和未校准 NLL，但总体 validation 拟合的 calibration 使其 tail NLL 严重恶化。这与 Day8 已发现的 tail-calibration failure 完全一致，不是 Gap 2 新产生的冲突。

正确结论是：

- B1 学到了更准确的 conditional mean/trajectory；
- 单一 global temperature/covariance scale 不能可靠覆盖稀少的响应活跃尾部；
- 不得使用这些 test-tail 结果重新拟合 calibration；
- closed-loop 中需要把 calibration 视为 predictor package 的组成部分，而不能只引用 ADE。

## 4. 对论文假设的影响

### 得到支持

`H-adaptation`：在 V2 受控交互数据上进行有限的 B1 adaptation，相对原始 pretrained B0 能显著改善同分布离线预测表现。

`H-offline/closed-loop gap`：明显的 offline prediction gain 并不保证跨 risk policy 的 closed-loop gain。Gap 2 与 Day10 联合提供了这一结论，而不是互相矛盾。

### 不得到支持

`H-global-calibration-tail`：总体 validation calibration 能稳定迁移到 response-active tail。该假设继续被否定。

### 仍不能判断

`H-sequence-use`：T1/T2 的结果是否来自真实交互序列。该问题由 Gap 3 的 zero/shuffle diagnostic 判断。

## 5. 证据路径

```text
docs/paper/generated/day10/gaps/b0_offline/B0_OFFLINE_COMPLETE.json
docs/paper/generated/day10/gaps/b0_offline/b0_frozen_offline_summary.json
docs/paper/generated/day10/gaps/b0_offline/b0_frozen_offline_snapshot.tar.gz
```
