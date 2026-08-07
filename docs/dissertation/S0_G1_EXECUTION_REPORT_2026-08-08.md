# S0–G1 执行与科研结论报告

**日期：** 2026-08-08  
**范围：** `DISTINCTION_EXECUTION_PLAN.md` 中 S0、S1、E1–E6、G1  
**总状态：** 已完成；没有启动新的 CARLA 正式 rollout，也没有把 legacy 与 corrected-control 结果混合。

## 1. 最终冻结的机器学习主张

> 在冻结的小数据 give-way 协议中，B1 output-head task adaptation 相对 B0 和三种简单基线获得了大的整体域内预测提升；但该模型的收益主要依赖 raster，几乎没有表现出对显式 past-state 的有效利用。轻量 Transformer residual adapters 没有相对对应 MLP adapters 建立一致优势，而且模型比较并非 parameter matched。部署日志进一步显示，整体预测提升没有延伸到最困难的 -3 m response-active 尾部，因此论文贡献应写成“平均性能、输入机制、交互尾部与控制耦合之间的分层证据”，而不是“Transformer 或 adaptive risk 普遍更优”。

机器可读冻结记录：[`G1_ML_CONTRIBUTION_FROZEN.json`](../paper/generated/distinction_v1/07_ml_claim_gate/G1_ML_CONTRIBUTION_FROZEN.json)。

## 2. 各步骤完成结果

### S0 — Provenance

- 冻结 HEAD：`74179a18df0e7db695c26fda5402868bdc3432b6`，当时与 `origin/main` 一致；
- 重新计算 4 个 offsite archive 的 SHA-256 和成员数；
- 保存 dirty worktree 状态、diff hash 和变更文件快照；
- C1–C9 全部进入显式 remediation checklist；
- 未执行 Git commit/push，避免未经用户单独授权提交现有论文改动。

### S1 — Regression gates

- 新增 JSON pointer、collision episode、全长度一致性和 legacy/new 隔离测试，4/4 PASS；
- 修复 `closed_loop_metrics.py` 中错误的 chained inequality；
- 成功复现而没有掩盖三个关键问题：formal one-TV mode 映射为 `[0,0,0]`、fixed/adaptive reference A_MIN 为 `-4/-3`、旧 manifest 66 个 JSON pointer 中 42 个失效；
- C1/C2 的实现修复留到 R1，因为直接修改后不能继续引用旧闭环结果为 corrected evidence。

### E1 — Physical baselines

冻结测试集 315 个 full-horizon windows，20 rollouts、5 init groups：

| 方法 | rollout-macro ADE (m) | rollout-macro FDE (m) |
| --- | ---: | ---: |
| B1 | 0.106 | 0.129 |
| CV | 0.610 | 1.203 |
| clipped CA | 1.410 | 3.493 |
| train-mean trajectory | 0.463 | 0.542 |

B1 对三种基线的 ADE 和 FDE 都是 **5/5 init 同方向更好**。因此 H1 不再只是“比预训练模型好”，而是超过了简单运动学和路线先验。但该结论仍限于同一 Town05 give-way 分布。

### E2 — B1 input diagnostics

使用 3 个冻结 cross-init shuffle seeds：

- raster shuffle 的 ADE 增量为 `+0.271` 至 `+0.293 m`，均值 `+0.284 m`；
- raster channel-mean replacement 令 ADE 从 `0.106` 上升到 `5.110 m`；
- past-state shuffle 的平均 ADE 变化只有约 `+0.00008 m`，三个 seed 也不全为正；
- past-state train-mean replacement 的 ADE 变化为 `-0.001 m`；
- response-active 子集只有 15 个 windows，past shuffle 有小幅退化，但它是 post-hoc tail diagnostic，不能推翻整体“past 利用很弱”的判断。

论文应把 B1 写为 **raster-dominant task adaptation**，不能写成有效学习显式 target temporal history。

### E3 — Capacity/training budget

- 15/15 histories 已拉回并审计；
- B1 trainable parameters 为 `1,034,208`；B2-M/T1/T2/B2-D 只有 B1 的约 `7.5%/8.4%/16.0%/17.0%`；
- 10/15 runs 的 best epoch 等于 20-epoch 上限，存在 budget censoring；
- T1 在 mean-output pair 中略优于 B2-M，但 T2 在 distributional pair 中劣于 B2-D，因此 Transformer 没有一致优势；
- 结论必须是 complete model/training configurations 的比较，不能解释为 attention 的因果收益。

### E4 — Formal in-loop prediction

重算 160 个正式 rollout 中 10,235 个 full-horizon logged windows：

- aggregate 下 B1 在 -3/0/+3 m 的 ADE 均优于 B0，配对条件中方向比例均为 100%；
- -3 m response-active 下，B1 ADE `2.149 m`，B0 ADE `1.119 m`，B1-minus-B0 为 **+1.030 m**；
- 同一尾部 B1 calibrated rollout-macro NLL 为 `30.681`，B0 为 `2.508`，显示 validation-fitted covariance shrinkage 在分布偏移尾部严重过度自信；
- B1 的 uncalibrated NLL 在该尾部仍比 B0 略好，说明主要失败是 top-mode choice 与 calibration shift 的组合，不是所有模式都没有信息。

这给论文提供最重要的“立体性”：平均域内提升是真实的，但不能保证关键交互尾部。

### E5 — Safety and metric sensitivity

- 160 个正式 rollout 的 native sensor 日志只有 1 个受影响 rollout；
- 91 callbacks 去重后为 20 frames、2 episodes；全部是 target–traffic-light，vehicle actor callbacks 为 0；
- oriented-footprint replay 在 0.25 m/actor margin 下 0/160 collision，最小 separation `0.605 m`；基于保守 Minkowski bound，增加到 0.50 m/actor 仍可证为无重叠；
- 去掉 collision-affected init50 后，B1-minus-B0 的主要方向稳定；但 adaptive-minus-fixed 的多个很小效应翻转；
- 当前 yield conflict point 是由 realised trajectories 逐 rollout 选取，存在 outcome-dependent geometry。offsite 包不含 `scenario_result.pkl`，所以固定 route point replay 未在本阶段完成。正文只能把 160/160 yield order 当 descriptive gate，不能当无偏连续效应。

### E6 — Split audit

- 200 rollouts、50 init × 4 cells 完整；
- train/val/test init sets 完全不重叠；
- 11,230 sample keys 无重复；
- full-horizon counts 为 2,596/326/315；
- 六个窗口协变量的最大 train-vs-held-out 描述性 SMD 为 `0.208`，没有发现明显 covariate collapse。

## 3. 四个论文假设的 G1 状态

| Hypothesis | G1 verdict | 论文写法 |
| --- | --- | --- |
| H1：B1 改善 held-out give-way prediction | 支持 | 强描述性结论；强调超过 B0 和 3 个简单 baseline，5/5 init 同方向 |
| H2：Transformer 相对对应 MLP 有一致优势 | 不支持 | 作为重要负结果；同时披露非 parameter-matched 与 epoch censoring |
| H3：离线优势稳定转化到所有闭环 operating contexts | 不支持 | aggregate 改善与 -3 m active-tail failure 并列呈现 |
| H4：adaptive policy stack 普遍支配 fixed stacks | 不支持 | 微小效应对 init50 敏感，且 A_MIN/mode mapping 阻止纯 risk attribution |

## 4. 论文现在禁止使用的表述

- “Transformer 是最佳或最优架构”；
- “B1 改善所有 give-way 交互”；
- “adaptive risk 普遍优于 fixed risk”；
- “零观察碰撞证明系统安全”；
- “结果证明了 attention/architecture 的因果效果”；
- “B1 有效利用了完整 temporal history”。

## 5. 下一决策点

S0–G1 已足以冻结 ML 主线。下一步不是继续换模型，而是进入 G2：

1. R1 修复 one-TV mode mapping，并统一 fixed/adaptive reference A_MIN；
2. 为 fixed route-defined conflict point 增加 raw-trajectory metric；
3. 只运行 corrected smoke/pilot；
4. 根据与结果方向无关的 feasibility gate，选择：
   - Route S：保留 legacy closed-loop 为带限制的系统案例；或
   - Route R：运行新的 corrected 80-rollout matrix，并与 legacy 完全隔离。

无论选择哪条 route，G1 中的 ML 结论不再改变，也不允许使用 test set 重新选择模型。
