# Day 8 最终 Test 结果与结论

完成日期：2026-08-02

## 1. 完成状态与证据完整性

Day 8 已完整结束：

- validation：5 variants × 3 seeds = 15/15 runs；
- test：5 个 validation-frozen representative models × 5 subsets = 25/25 evaluations；
- `DAY8_COMPLETE.json`：`status=pass`；
- test 在模型和 calibration 冻结后访问；
- `test_used_for_selection=false`；
- 最终闭环模型仍为 B1 / seed 37；
- 所有 test 结果的 invalid covariance 均为 0；
- compact snapshot 共 28 个文件，不含模型权重；
- 本地下载 SHA-256 与服务器 manifest 均为 `0186bc9d4a27aaeca0d7a20ae2ea1fbaf101de5cbaa04877d8527e2a5d36d2d9`。

本地证据目录：

```text
docs/paper/generated/day8/final_validation/
docs/paper/generated/day8/final_test/
```

## 2. 最终 test 排名

每个模型只测试 validation 阶段预先冻结的代表 seed。Primary metric 是未校准的 rollout-macro trajectory mixture NLL/step，越低越好。

| 排名 | 模型 | seed | test NLL | all ADE (m) | all FDE (m) | reactive ADE (m) | reactive FDE (m) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | B1 | 37 | 1.8571 | 0.1059 | 0.1292 | 0.1627 | 0.2031 |
| 2 | B2-D | 11 | 1.8728 | 0.2255 | 0.3832 | 0.3550 | 0.6439 |
| 3 | T2 | 23 | 1.8781 | 0.2457 | 0.4027 | 0.3684 | 0.6317 |
| 4 | T1 | 23 | 2.0037 | 0.9276 | 1.7042 | 1.0486 | 2.0119 |
| 5 | B2-M | 37 | 2.0244 | 1.0473 | 1.7301 | 1.1446 | 2.0208 |

Test 排名与 validation 排名完全一致。B1 同时在 primary NLL、all ADE/FDE 和 reactive ADE/FDE 上最好，因此 validation-only 选择得到了独立 test 支持。

## 3. Matched-control 假设结果

为了区分“Transformer 的时序归纳偏置”与“增加参数量”的影响，主要 matched comparisons 为 T1 vs B2-M、T2 vs B2-D。

| 对比（Transformer − MLP） | Δ test NLL | Δ all ADE (m) | Δ reactive ADE (m) | 结论 |
| --- | ---: | ---: | ---: | --- |
| T1 − B2-M | -0.0207 | -0.1197 | -0.0960 | T1 优于 mean-only matched MLP |
| T2 − B2-D | +0.0054 | +0.0202 | +0.0134 | T2 未优于 distributional matched MLP |

按 5 个独立 test init group 做配对检查：

- T1 的 NLL 和 ADE 均在 5/5 init 上优于 B2-M；
- T2 的 NLL 在 0/5 init 上优于 B2-D；
- T2 的 ADE 仅在 1/5 init 上优于 B2-D；
- B1 的 NLL 和 ADE 均在 5/5 init 上优于 B2-D，也均在 5/5 init 上优于 T2。

样本量只有 5 个独立 test init，不能把上述方向一致性解释为大样本统计显著性，但它表明结论并非由单个 test init 驱动。

## 4. Validation-to-test 泛化

冻结 representative seed 的 test 指标均接近或略优于各自 validation 指标：

| 模型 | Δ all NLL（test − val） | Δ all ADE (m) | Δ reactive ADE (m) |
| --- | ---: | ---: | ---: |
| B1 | -0.0035 | -0.0061 | -0.0082 |
| B2-M | -0.0011 | -0.0156 | -0.0353 |
| B2-D | +0.0000 | -0.0373 | -0.0572 |
| T1 | -0.0051 | -0.0376 | -0.0578 |
| T2 | +0.0003 | -0.0398 | -0.0642 |

没有发现明显的 validation-to-test collapse。由于 validation 和 test 均来自同一受控 CARLA 数据生成协议，这只能支持同分布泛化，不能外推到自然交通或其他地图。

## 5. Calibration 结果与重要限制

All-subset 的 validation-frozen calibration 结果为：

| 模型 | calibrated NLL | calibrated coverage MAE |
| --- | ---: | ---: |
| B1 | -2.0686 | 0.0766 |
| B2-M | -1.3507 | 0.5943 |
| B2-D | -1.4549 | 0.0766 |
| T1 | -1.2874 | 0.3845 |
| T2 | -1.0722 | 0.0576 |

B1 的总体 calibrated NLL 最好；T2 的总体 coverage MAE 最低，但这不足以抵消其更差的 NLL 和轨迹误差。

需要明确报告一个 tail-calibration 负结果：test `response_active` 仅含 15 samples、6 rollouts、3 init groups，validation-frozen calibration 在该 subset 上使所有模型的 NLL 变差。例如 B1 的未校准 NLL 为 2.0763，校准后为 8.5728。这说明用总体 validation NLL 拟合的单一 temperature/covariance scale 对响应活跃尾部并不稳健，且很小的 covariance scale 会造成尾部过度自信。

该结果不能用于 test 后重新拟合 calibration，也不能改变已经冻结的 Day 9 部署配置。正确做法是在论文中作为限制和后续工作报告，并在 Day 9 smoke 中重点审计预测 covariance 到 risk controller 的传递。

## 6. 最终假设判定

### H-Transformer-capacity

“Transformer 的优势只是参数量增加造成的。”

部分否定。T1 在所有 5 个 test init 上优于参数匹配的 B2-M，说明 mean-only 路径存在时序 attention 增益；但 T2 未优于 B2-D，因此这个优势不适用于完整 distributional residual。

### H-Transformer-best

“时序 Transformer 是当前 give-way prediction 的最优模型。”

否定。T1/T2 均未超过 B1，且 T2 未超过 matched distributional MLP。

### H-simple-adaptation

“在有限、受控的 give-way 数据中，较简单的 head fine-tuning 比新增复杂 interaction adapter 更可靠。”

得到 validation 和独立 test 的一致支持。B1 在精度、概率 NLL、三 seed 稳定性和推理延迟上形成最强综合结果。

### H-tail-calibration

“总体 validation calibration 能可靠迁移到 response-active tail。”

不支持。总体 calibration 有效，但 response-active test subset 出现明显恶化。

## 7. 论文主张边界

可以主张：

1. supervisor masking 暴露了 planning-only 比较的识别问题，从而推动研究转向 predictor–controller interaction；
2. 单纯增加模型复杂度并不保证 give-way prediction 改善；
3. attention 对 mean-only adapter 有可复现的小幅增益，但 distributional Transformer 没有超过 matched MLP；
4. 简单 B1 adaptation 在当前数据规模和任务中表现最好，并获得独立 test 支持；
5. aggregate calibration 与 interaction-tail calibration 存在明显差异，这为后续闭环风险实验提供了具体机制问题。

不能主张：

1. Transformer 普遍无效；
2. B1 在所有自动驾驶场景中最优；
3. 五个 test init 足以证明广泛统计显著性；
4. 离线预测改善必然转化为闭环安全或效率改善；
5. 根据 test tail 结果重新调 calibration 后仍属于无泄漏实验。

## 8. Day 9 的冻结输入

Day 9 部署输入固定为：

```text
variant = B1
seed = 37
model = DAY8_RESULTS/runs/B1/seed_37/best_model
calibration = DAY8_RESULTS/runs/B1/seed_37/calibration.json
```

Day 9 首先完成部署 smoke、输入 normalization、calibration 加载、模型输出、prediction-control logging 和 covariance-to-risk 链路检查。不得因为 test 结果重新训练、调参或更换模型。
