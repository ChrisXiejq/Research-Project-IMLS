# Day 10 正式闭环结果与结论

完成日期：2026-08-02

## 1. 完成状态

Day 10 已完整结束并通过审计：

- 16/16 cells、80/80 rollouts 成功；
- B1 / B0 × fixed aggressive / medium / conservative / adaptive × assertive / reactive × init46–50；
- 80/80 完成 give-way，80/80 无 footprint collision，80/80 target 先清空冲突区；
- 0 invalid probability、0 invalid covariance；
- 最大单 rollout solver failure fraction 为 1.00%，低于冻结的 5% gate；
- 最小 footprint separation 为 0.825 m，高于 post-CARLA 0.25 m margin；
- reactive arms 共覆盖 272 个 response-active samples；
- 原始 snapshot SHA256 为 `6307146c6bbddd57fdaba657432491790a052848033d5eddafc162217a96f2e3`。

断点续跑没有覆盖旧结果。合同 provenance 记录了从 `9aeed8c` 到 `915b0e2` 的快进修复，且 `raw_rollouts_preserved=true`。

## 2. 分析方法

正式分析单位是 paired `(ego_init_id, target_style)`，不把 20 Hz simulator steps 当作独立样本。报告：

1. B1−B0，同 risk、style、init 配对；
2. adaptive−每个 fixed frontier point，同 predictor、style、init 配对；
3. predictor × target-style 与 predictor × risk 的 difference-in-differences；
4. 冻结的 primary outcomes：target-clearance-adjusted completion delay 与 footprint separation；
5. completion time、solver failure 和 supervisor intervention 作为 secondary/mechanism outcomes；
6. deterministic paired bootstrap 95% CI、exact sign-flip p-value 和同一 inference scope 内 Holm 校正。

样本量仍只有 5 个 held-out init、每种 target style 各 5 个条件。统计量用于给出效果量和不确定性，不把未校正的单个 `p<0.05` 扩大成普遍规律。

## 3. Predictor 主结果

跨全部 risk 与 target styles 的描述性平均：

| Predictor | Clearance-adjusted delay (s) | Completion time (s) | Min footprint separation (m) | Solver failure fraction | Supervisor active fraction |
| --- | ---: | ---: | ---: | ---: | ---: |
| B0 pretrained | 8.544 | 10.635 | 1.266 | 0.00427 | 0.14502 |
| B1 fine-tuned + frozen calibration | 8.590 | 10.689 | 1.216 | 0.00395 | 0.14438 |
| B1−B0 | +0.046 | +0.054 | -0.050 | -0.00033 | -0.00063 |

B1 没有形成跨 risk policy 的整体 closed-loop 优势。平均 completion 几乎相同但略慢，footprint margin 小 5.0 cm，solver failure 略低 0.033 percentage points，supervisor intervention 几乎相同。所有差异都远小于场景/策略条件造成的变化。

模型效果明显依赖 risk policy：

| Risk policy | B1−B0 adjusted delay (s) | B1−B0 footprint (m) | B1−B0 supervisor fraction | Delay exact p / Holm p |
| --- | ---: | ---: | ---: | ---: |
| fixed aggressive | -0.305 | -0.039 | +0.0040 | 0.0117 / 0.1875 |
| fixed medium | +0.295 | -0.041 | -0.0020 | 0.5117 / 1.0000 |
| fixed conservative | +0.090 | -0.098 | -0.0035 | 0.9805 / 1.0000 |
| adaptive | +0.105 | -0.021 | -0.0010 | 0.8906 / 1.0000 |

在 fixed-aggressive 下，B1 的 clearance-adjusted delay 平均小 0.305 s，但同时 margin 小 3.9 cm、supervisor active fraction 高 0.40 percentage points。delay 与 supervisor intervention 的未校正 exact p 均为 0.0117；两者在预定义 predictor 主结果 family 内做 Holm 校正后均为 0.1875，因此只能作为值得在 Day 11 复核的条件性信号，不能写成确认性优势。

## 4. Target responsiveness 是否放大模型效果

B1−B0 的平均绝对差异在 reactive 条件下略大：

| Metric | Assertive mean absolute delta | Reactive mean absolute delta |
| --- | ---: | ---: |
| Clearance-adjusted delay | 0.513 s | 0.665 s |
| Footprint separation | 0.057 m | 0.078 m |
| Solver failure fraction | 0.00070 | 0.00064 |
| Supervisor active fraction | 0.00693 | 0.00849 |

但是 signed predictor × target interaction 没有得到统计确认：adjusted-delay difference-in-differences 为 `-0.213 s`、exact p=0.625；footprint 为 `-0.019 m`、p=0.375；四个 primary outcomes 的 Holm p 均为 1.0。

因此 H10-ML 只有弱描述性支持：reactive behavior 在 completion、separation 和 intervention 三项上放大了 predictor package 的变化幅度，但放大的不是一致正向收益，而且 5 个 init 的不确定性很大。

## 5. Adaptive 与完整 fixed frontier

按 predictor 聚合两种 target styles：

| Predictor | Risk | Adjusted delay (s) | Completion (s) | Footprint separation (m) | Solver failure | Supervisor active |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| B0 | fixed aggressive | 8.570 | 10.660 | 1.259 | 0.00366 | 0.14531 |
| B0 | fixed medium | 8.635 | 10.725 | 1.265 | 0.00459 | 0.14348 |
| B0 | fixed conservative | 8.525 | 10.615 | 1.292 | 0.00514 | 0.14523 |
| B0 | adaptive | 8.445 | 10.540 | 1.248 | 0.00370 | 0.14604 |
| B1 | fixed aggressive | 8.265 | 10.365 | 1.219 | 0.00375 | 0.14931 |
| B1 | fixed medium | 8.930 | 11.025 | 1.224 | 0.00390 | 0.14143 |
| B1 | fixed conservative | 8.615 | 10.715 | 1.193 | 0.00407 | 0.14171 |
| B1 | adaptive | 8.550 | 10.650 | 1.227 | 0.00407 | 0.14509 |

Adaptive 不是普遍优于 fixed 的方案：

- 对 B0，adaptive 最快，但 margin 低于三个 fixed points；这是效率换取少量 safety margin，不是 dominance；
- 对 B1，adaptive 比 fixed-medium 和 fixed-conservative 的 cell mean 更快且 margin 略高，但 fixed-aggressive 仍快 0.285 s；
- adaptive−fixed 的 paired intervals 大多跨 0，不能声称稳定优势；
- adaptive 的价值必须写成 predictor-conditional frontier position，而不是“adaptive 优于 fixed”。

H10-Risk 的方法论假设得到支持：只与 fixed-medium 单点比较会给出偏乐观结论；完整 frontier 会显示 aggressive point 仍然重要。

## 6. Predictor × risk interaction

B1−B0 adjusted-delay effect 从 fixed-aggressive 的 `-0.305 s` 变化到 fixed-medium 的 `+0.295 s`，跨度为 0.600 s；这说明 offline 选择的 predictor package 不会产生与 risk policy 无关的单调收益。

不过 predictor × risk 的 primary interaction 在 multiplicity control 后均未确认。唯一未校正 `p<0.05` 的 interaction 是 adaptive 相对 fixed-medium 的 solver-failure difference-in-differences `+0.00105`，exact p=0.0469；其绝对量只有 0.105 percentage points，且 Holm p=0.5625，不构成实际或统计上的强证据。

因此 H10-Interaction 的结论是：存在清楚的描述性 effect heterogeneity，但当前 5-init 设计不足以确认特定 interaction contrast。Day 11 应预注册复核 fixed-medium/adaptive 的 timing-shift transfer，而不是根据 Day 10 结果改 policy 参数。

## 7. 假设判定

| Hypothesis | 判定 | 论文表达 |
| --- | --- | --- |
| H10-ML | 弱描述性支持，未确认 | reactive 条件放大了部分 predictor 差异，但没有一致正向 closed-loop gain |
| H10-Risk | 支持 | adaptive 必须相对完整 fixed frontier 判断；单点 baseline 会误导 |
| H10-Interaction | 描述性支持，确认性证据不足 | predictor effect 随 risk 改变，但 interaction CI 宽且 Holm 后不显著 |
| H10-Reliability | 支持 | 80/80 安全完成，数值有效，solver failure 全部低于 5% |

## 8. 对论文主线的意义

Day 8 与 Day 10 合在一起形成了可写且比“adaptive 一定更好”更严谨的主张：

> 在有限的受控 give-way 数据中，更复杂的 Transformer 并未超过简单 B1 adaptation；即使 B1 在冻结的五种训练候选中最好，这种 validation-only 模型选择也没有稳定转化为相对 B0、跨 risk policy 的闭环收益。Predictor 的闭环效用由 target responsiveness、risk allocation 和 runtime intervention 共同调节，因此 motion prediction 必须同时按 distribution quality、deployment equivalence 和 policy-conditional closed-loop utility 评价。

这是 machine-learning-centered 的结果，因为核心问题不是 supervisor 本身，而是：模型结构/训练得到的 offline improvement 在 prediction→risk→solver→supervisor 链上如何被放大、改变或吸收。

必须保留两个边界：

1. Day 10 比较的是完整部署 predictor package：B1 包含 validation-frozen calibration，B0 使用 identity calibration。因此它不能被写成只隔离 neural-network weight fine-tuning 的纯因果效应；
2. 五个 held-out init 足够完成受控 paired study，但不足以声称跨地图、跨交通分布的普遍泛化。

## 9. 机器可读证据

```text
generated/day10/evidence/DAY10_COMPLETE.json
generated/day10/evidence/day10_closed_loop_audit.json
generated/day10/evidence/day10_run_contract.json
generated/day10/evidence/*/df_full.csv
generated/day10/evidence/*/postcarla_trajectory_gate.json
generated/day10/evidence/*/risk_by_conflict_distance_summary.csv
generated/day10/analysis/day10_rollout_metrics.csv
generated/day10/analysis/day10_cell_summary.csv
generated/day10/analysis/day10_paired_contrasts.csv
generated/day10/analysis/day10_analysis_summary.json
```

原始 125 MB snapshot 因超过 GitHub 单文件限制只保留在本机和服务器结果目录，不提交 Git；其 SHA256 已在本报告冻结。仓库中的逐 rollout evidence 与 derived tables 足以复现本报告统计。快照打包器已修复，未来重打包会自动包含 `df_full.csv`。
