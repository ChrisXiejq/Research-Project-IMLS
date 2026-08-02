# Gap 3：Transformer 交互序列诊断结果

> 完成时间：2026-08-02
>
> 状态：PASS；post-selection diagnostic；不改变 Day8 的 B1/seed 37 选择。

## 1. 问题与实验设计

本实验回答的不是“Transformer 是否优于所有模型”，而是一个更具体、无法从架构名称直接推断的问题：

> T1/T2 是否实际使用了显式交互序列，还是其结果仅来自额外参数、raster 或 target history？

模型权重、validation-frozen calibration、receiver raster、target history 和 future label 全部固定，只改变六步交互序列：

- `Original`：Day8 frozen test 原始输入；
- `Zero`：valid token 替换成 train-only normalization mean，归一化后严格为零；mask 不变；
- `Shuffle`：从不同 ego init 确定性借用 sequence 与 mask，receiver 的其他输入和标签不变。

测试集包含 315 windows、20 rollouts 和 5 个独立 init groups。该实验只用于机制解释，不用于重新选模型、seed 或 calibration。

## 2. All-subset 结果

表中数值均为 `ablated − original`；正 ADE/FDE/NLL 表示破坏交互序列后性能变差。

| Variant | Ablation | Δ ADE (m) | Δ FDE (m) | Δ uncalibrated NLL | Δ calibrated NLL |
| --- | --- | ---: | ---: | ---: | ---: |
| T1 | Zero | -0.0331 | +0.0213 | +0.0221 | +2.1122 |
| T1 | Shuffle | +0.1440 | +0.2840 | +0.0848 | +4.3503 |
| T2 | Zero | +0.1985 | +0.2919 | +0.0908 | +3.8601 |
| T2 | Shuffle | +0.3497 | +0.4276 | +0.1494 | +4.0657 |

对应的原始与打乱后点误差：

| Variant | Original ADE/FDE | Shuffled ADE/FDE | 相对变化 |
| --- | ---: | ---: | --- |
| T1 | 0.9276 / 1.7042 m | 1.0717 / 1.9883 m | ADE +15.5%，FDE +16.7% |
| T2 | 0.2457 / 0.4027 m | 0.5954 / 0.8302 m | ADE +142.3%，FDE +106.2% |

所有 ablated evaluations 均保持 0 invalid covariance。

## 3. 结论

### H-sequence-use：得到支持

跨 init shuffle 在 T1、T2 上同时恶化 ADE、FDE、uncalibrated NLL 与 calibrated NLL。特别是 T2 的点误差超过翻倍，说明模型输出确实依赖交互序列与当前 receiver 场景的正确对应关系。

因此，可以否定下面这个过度简化解释：

> Transformer 分支完全忽略 interaction sequence，所有结果仅由 raster、target history 或参数量造成。

### H-sequence-uniform-benefit：不支持

T1 zero-context 的总体 ADE 反而改善 0.033 m，尽管 FDE 和两种 NLL 都恶化。这表明：

- T1 使用了序列信息，但这种使用不在所有 point metric 上形成净收益；
- shuffle 比 zero 更有识别力，因为 zero 可能成为模型学到的近似 neutral/default context；
- 不能把“模型对序列敏感”等同于“序列在每个样本、每个指标上都有帮助”。

### H-Transformer-best：仍然不支持

Gap 3 证明 T1/T2 使用交互序列，但没有改变 Day8 的模型排名：

- T1 相对 matched mean-only MLP 有小幅 attention gain；
- T2 没有超过 matched distributional MLP；
- T1/T2 都没有超过简单的 B1 adaptation。

论文应将 Transformer 定位为“可解释的候选交互编码器及机制消融”，而不是最终最优部署模型。

## 4. 子集边界

- assertive、reactive、pre-response 的 shuffle 方向总体一致；
- response-active 只有 15 windows、6 rollouts、3 init groups；
- T2 shuffle 在 response-active 上 ADE/FDE 反而下降，但 NLL 和 calibration 明显恶化；
- 该小尾部不支持独立强结论，也不能用于 test 后调参。

## 5. 对论文主线的作用

Gap 2 与 Gap 3 联合形成一个比“Transformer 更好”更严谨的模型论点：

1. V2 数据上的简单 B1 adaptation 相对 pretrained B0 显著改善离线预测；
2. Transformer 的确能够利用显式时序交互序列；
3. 但能利用序列不等于成为最优模型，额外复杂度也不保证更好的完整概率输出；
4. 即使 B1 离线最优，Day10 的闭环收益仍受 risk policy、calibration 和 supervisor/controller coupling 限制。

这使论文的机器学习部分不再只是“训练了一个 Transformer”，而是包含 matched architecture controls、input ablation、calibration audit 和 offline-to-closed-loop transfer 检验。

## 6. 证据路径

```text
docs/paper/generated/day10/gaps/context_ablation/CONTEXT_ABLATION_COMPLETE.json
docs/paper/generated/day10/gaps/context_ablation/interaction_context_ablation_summary.json
docs/paper/generated/day10/gaps/context_ablation/interaction_context_ablation_snapshot.tar.gz
```
