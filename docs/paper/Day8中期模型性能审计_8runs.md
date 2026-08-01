# Day 8 中期模型性能审计（8/15 runs）

审计时间：2026-08-01

证据快照：`docs/paper/generated/day8/partial_8runs_20260801/`

## 1. 当前覆盖

已完成并具有 validation 结果：

- B1：seeds 11/23/37；
- B2-M：seeds 11/23/37；
- B2-D：seeds 11/23；
- B2-D seed 37 正在训练；
- T1/T2 尚未开始。

因此当前结果可以判断 B1 与两个 MLP control 的质量，但还不能回答 Transformer 是否优于参数匹配 control。

## 2. 指标定义与“怎样算好”

模型选择不能只看 training loss。固定 validation 指标顺序为：

1. rollout-macro uncalibrated trajectory mixture NLL/step：主要模型排序指标，越低越好；
2. top-1 ADE/FDE：轨迹均值精度，越低越好；
3. reactive 与 response-active ADE/FDE：核心交互场景指标，越低越好；
4. calibration 后 NLL 与 coverage MAE：概率质量，越低越好；
5. invalid covariance：必须为 0；
6. 三 seed 稳定性：结论方向必须一致，不能依赖单个最优 seed；
7. matched comparison：T1 对 B2-M，T2 对 B2-D；
8. inference latency：必须在同一硬件状态下重测后比较；
9. 最终闭环指标：碰撞/近失、成功率、效率与 intervention，离线好不等于闭环一定好。

若 Transformer 只优于 matched MLP、但不优于 B1，可以支持“时序编码比容量匹配 MLP 更有效”，但不能支持“Transformer 是最佳部署模型”。若 T1/T2 同时稳定优于 matched MLP 和 B1，且 calibration/covariance/latency gate 通过，才是强正结果。

## 3. 当前中位数结果

下表为已完成 seeds 的 validation 中位数；B2-D 目前只有两个 seed，因此仍是临时结果。

| Variant | seeds | all ADE m | all FDE m | all rollout NLL | reactive ADE m | reactive FDE m | active ADE m | active FDE m | calibrated coverage MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B1 | 3 | 0.115 | 0.142 | 1.862 | 0.171 | 0.218 | 0.567 | 0.764 | 0.088 |
| B2-M | 3 | 1.063 | 1.756 | 2.027 | 1.180 | 2.115 | 1.458 | 3.233 | 0.604 |
| B2-D | 2 | 0.264 | 0.480 | 1.874 | 0.396 | 0.771 | 0.772 | 1.587 | 0.070 |

所有现有结果的 invalid covariance 均为 0。

B1 三 seed 很稳定：all ADE 范围 0.112–0.119 m，rollout NLL 范围 1.8615–1.8621。B2-M 三 seed 同样稳定，但稳定地显著差于 B1。B2-D 的 calibration coverage 略优于 B1，但点预测、reactive 和 active 指标均明显更差，不能仅凭 coverage 选中。

按相同 validation 条件配对，B2-M 在所有可比组上均差于 B1；B2-D 当前两个 seed 也均差于 B1。这说明目前的正信号来自 B1 head fine-tuning，而不是 MLP interaction adapter。

## 4. Calibration 解释

当前 validation 拟合得到的 covariance scale 很小：

- B1：0.00827；
- B2-M/B2-D：0.01286。

它们意味着 covariance 需缩小约 98.7%–99.2%，标准差乘数约为 0.091–0.113。说明原始 MultiPath covariance 在本 CARLA 局部场景中过宽。校准后 NLL 大幅下降并不代表轨迹均值变好；ADE/FDE 不会因 covariance scale 自动改善。因此模型选择仍须同时检查 point accuracy 和 calibration。

B2-M 的 NLL 校准后改善，但 coverage MAE 反而约 0.60，说明“用 validation NLL 搜索校准参数”不能挽救其概率覆盖质量。

## 5. 发现的评价聚合缺陷

V1 evaluator 只用 `source_subrun` 作为 rollout key。S0/S1 的同 init、同 ego policy 名称相同，导致 all subset 的 20 个 rollout 被合并为 10 个键。逐样本 ADE/FDE/NLL 和 covariance audit 不受影响，但：

- rollout-macro 聚合键不严格；
- calibration 的 rollout macro fit 使用了 10 个合并键；
- `independent_rollouts=10` 标签不正确。

修复后的 V2 evaluator 使用：

```text
rollout key = cell_id :: source_subrun
paired clustering unit = ego_init_id
```

预期 all/assertive/reactive 分别为 20/10/10 rollouts，并均来自 5 个 validation init groups。所有已有模型只需重新运行 validation/calibration，不需要重训。

## 6. 是否继续及是否调参

结论：需要继续 T1/T2，否则核心 Transformer 假设无法检验；但不应在 T1/T2 之前改变 architecture、learning rate 或 epoch 上限。

推荐顺序：

1. 暂停当前 CPU 训练；
2. 恢复 GPU/NVML；
3. 更新 V2 evaluator；
4. 从 B2-D seed 37 的 epoch backup 续跑；
5. 完成 T1/T2 三 seed；
6. 自动重新生成全部模型的 V2 calibration 与 validation subsets；
7. 再决定模型选择和是否需要有边界的 epoch-extension sensitivity；
8. 在模型冻结前不访问 test。

B1 三 seed 的最佳 epoch 都在 epoch 20，validation loss 仍缓慢下降。这个现象值得在正式矩阵完成后考虑只针对最终候选做预注册的 epoch-extension sensitivity，但现在修改 epoch 会破坏五模型公平比较。

## 7. 运行环境异常

服务器最初使用 RTX 4090，随后 NVML 报错且 TensorFlow 出现 `CUDA_ERROR_NO_DEVICE`。B2-D seed 37 已退回 CPU，单 epoch 约 4 分钟。已有 prediction metrics 仍可读取，但：

- 当前继续训练明显更慢；
- 不同运行的 latency 不可直接比较；
- 最终 latency 必须在 GPU 状态稳定后统一重测；
- 为减少硬件路径混杂，建议恢复 GPU 后再续跑剩余训练。

runner 已增加强制 GPU gate：每个正式训练和每次 validation evaluator 启动前都要求 TensorFlow 能看到至少一个 GPU。GPU 再次掉线时脚本会停止并保留 epoch backup，而不会静默切换到 CPU。
