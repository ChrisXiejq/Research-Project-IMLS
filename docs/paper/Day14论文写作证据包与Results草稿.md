# Day14 论文写作证据包与 Results 草稿

> 状态：2026-08-03，论文证据包 `PAPER_EVIDENCE_PACKAGE_COMPLETE.json` 已通过。本文档用于把冻结实验直接转化为论文结构，不新增实验、不重新选择模型。

## 1. 推荐标题与中心论点

推荐标题：

> **Interaction-Aware Prediction and Predictor–Risk Coupling for Give-Way Intersection Planning in CARLA**

中心论点：

> In a controlled give-way scenario, task-specific adaptation substantially improves in-distribution motion prediction, while the tested sequence and Transformer variants do not outperform the simpler adaptation baseline. More importantly, offline predictive improvement does not translate into a uniform closed-loop benefit: its effect is moderated by risk allocation, arrival timing, solver feasibility and supervisor intervention. Adaptive risk should therefore be evaluated as one point on a predictor-conditional safety–efficiency frontier rather than as a universally superior replacement for fixed risk.

这一定义保留了项目最初的 adaptive-vs-fixed planning 动机，但把机器学习模型比较、Transformer 负结果和 predictor–controller coupling 放在论文中心。

## 2. Research questions

### RQ1：任务适配能否改善 give-way 轨迹预测？

- 对照：pretrained B0；
- 实验组：simple task-adapted B1；
- primary metrics：rollout-macro mixture NLL、top-1 ADE/FDE；
- 结论：支持。B1−B0 ADE `−1.193 m`、FDE `−2.555 m`、macro NLL `−0.314 nats/step`。

### RQ2：显式交互序列和 Transformer 是否带来额外收益？

- 实验组：T1/T2；
- matched controls：B2-M/T1 为 mean-only pair，B2-D/T2 为 distributional pair；
- simple control：B1；
- 结论：序列确实被使用，但 Transformer 不是当前最优解。shuffle 使 T1/T2 macro NLL 分别恶化 `+0.0848/+0.1494`；然而 validation 和 frozen test 均由 B1 排名第一。

### RQ3：离线预测改善能否稳定转化为闭环收益？

- 对照：B0；实验组：B1；
- 条件：risk policy × target style × arrival offset；
- 结论：否。B1 的 effect 随 policy/offset 改变方向或区间跨零；因此“更好的 offline predictor 必然带来更好的 closed loop”被反驳。

### RQ4：adaptive risk 是否普遍优于 fixed-risk frontier？

- 对照不是一个 fixed 点，而是 aggressive/medium/conservative frontier；
- 结论：否。adaptive 是 frontier 上的条件性方案。在 Day10 reactive/B1 下，adaptive delay `8.59 s`、margin `1.200 m`；fixed-aggressive delay `8.34 s`、margin `1.186 m`，表现为安全—效率交换而非支配。

## 3. 实验设计摘要

### 3.1 数据与 split

| Split | Independent rollouts | Raw windows | Usable windows | Full-horizon windows |
| --- | ---: | ---: | ---: | ---: |
| Train | 160 | 9121 | 4036 | 2596 |
| Validation | 20 | 1034 | 506 | 326 |
| Test | 20 | 1075 | 495 | 315 |

- ego init 按 `1–40 / 41–45 / 46–50` 划分，避免 rollout leakage；
- sample windows 不是独立实验单位；
- validation/test 各只有 5 个独立 init groups；
- Day13 sensitivity 排除 6 个 callback-containing train rollouts 的全部 162 个 usable windows，validation/test 不变。

### 3.2 模型矩阵

| Variant | Interaction encoder | Updated output | Role |
| --- | --- | --- | --- |
| B0 | none | none | pretrained control |
| B1 | none | final base head | simple task adaptation |
| B2-M | matched MLP | mean residual | T1 capacity control |
| B2-D | matched MLP | mean, covariance, orientation, logits | T2 capacity control |
| T1 | masked Transformer | mean residual | sequence model |
| T2 | masked Transformer | full distributional residual | sequence model |

所有候选共享数据 split、base MultiPath、anchors、GMM evaluator、训练预算和三 seeds。模型选择只使用 validation macro NLL；test 只在选择冻结后执行一次。

### 3.3 闭环矩阵

- Day10 nominal：`2 predictors × 4 risk policies × 2 target styles × 5 init = 80 rollouts`；
- Day11 shifted timing：B0/B1 × fixed-medium/adaptive × ±3 m offsets × 5 init；
- Day12 synthesis：合并 nominal 与 shifted conditions，共 `120 formal rollouts`；
- 统计单位：ego-init cluster；
- uncertainty：init-cluster interval 与 exact sign-flip test；
- 由于只有 5 clusters，最小双侧 exact p 为 `0.0625`，不作传统 `p<0.05` 显著性主张。

## 4. Results 章节建议与可直接使用的英文草稿

### 4.1 Dataset integrity and controlled interaction coverage

建议引用：Table 1、Figure 1。

> The controlled collection yielded 200 CARLA rollouts. Ego initialisations were partitioned at rollout level into 160 training, 20 validation and 20 test rollouts, producing 4,036, 506 and 495 usable prediction windows, respectively. The frozen test set contained 315 full-horizon windows. No validation or test rollout was included in model fitting or selection. A subsequent collision-callback audit identified six reactive training rollouts containing target–infrastructure contacts, but no affected validation or test rollout. These training rollouts were handled through a conservative post-hoc sensitivity analysis rather than by modifying the primary experiment.

边界：不要把 windows 写成 independent scenes；不要把 253 callbacks 写成 253 次独立碰撞。

### 4.2 Offline model selection under matched controls

建议引用：Table 2、Table 3、Figure 2、Figure 3。

Validation macro NLL medians：

- B1 `1.86055`；
- B2-D `1.87274`；
- T2 `1.87789`；
- T1 `2.00883`；
- B2-M `2.02553`。

> Validation-only selection ranked the variants B1, B2-D, T2, T1 and B2-M. The same architecture ordering was recovered on the independently frozen test set. B1 achieved a test rollout-macro NLL of 1.8571 nats/step, with top-1 ADE and FDE of 0.1059 m and 0.1292 m. Relative to pretrained B0, B1 reduced ADE by 1.193 m, FDE by 2.555 m and rollout-macro NLL by 0.314 nats/step on the matched test split. Thus, task adaptation was strongly beneficial in distribution, but the tested Transformer variants did not exceed the simpler B1 adaptation.

Matched-control 解释：T1 相对 B2-M 有收益，但 T2 未超过 B2-D，因此不能概括为“Transformer 一律无效”或“attention 一律有效”。

### 4.3 Sequence use and calibration failure modes

建议引用：Table 4、Figure 4；context ablation 结果引用 `paper_key_results.csv`。

> Post-selection input ablations showed that the sequence architectures used their explicit interaction input. Shuffling the temporal context increased rollout-macro NLL by 0.0848 nats/step for T1 and 0.1494 nats/step for T2, while zeroing the T2 context increased NLL by 0.0908 nats/step. These effects establish input sensitivity, but not causal interaction understanding. Calibration also exhibited a distributional failure mode. For B1, global calibration reduced aggregate test NLL from 1.8571 to −2.0686, yet increased response-active NLL from 2.0763 to 8.5728. Because the response-active subset contained only 15 windows from six rollouts and three init groups, this tail result is reported as a limitation rather than a new selection criterion.

### 4.4 Deployment-equivalent predictor–controller chain

建议引用：Figure 8；Day9 只作 implementation gate，不写成效果实验。

> The frozen predictor was then integrated into the same prediction–risk–solver–supervisor chain used by all closed-loop conditions. This deployment gate verified valid mixture probabilities and covariances and ensured that changes in later experiments were not caused by different input or decoding contracts. The deployment smoke test was not used to estimate treatment effects.

### 4.5 Nominal closed-loop predictor–risk frontier

建议引用：Table 5、Figure 5。

> All 80 nominal formal rollouts completed without an observed footprint collision or yield-order failure. However, B1 did not uniformly dominate B0, and adaptive risk did not uniformly dominate the fixed-risk frontier. For the reactive target with B1, adaptive risk produced a mean adjusted completion delay of 8.59 s and a footprint margin of 1.200 m, compared with 8.34 s and 1.186 m under fixed-aggressive risk. The difference is therefore a local safety–efficiency trade-off rather than Pareto dominance. Zero observed collisions are reported as an event count under the tested conditions, not as evidence of zero population risk.

### 4.6 Timing-shift robustness and mechanism changes

建议引用：Table 6、Figure 6、Figure 7。

> Across all arrival offsets, B1 reduced adjusted delay relative to B0 by 0.370 s under fixed-medium risk (cluster interval −0.717 to −0.023 s) and by 0.337 s under adaptive risk (−0.665 to 0.015 s). These descriptive efficiency signals were not confirmatory after within-scope multiplicity adjustment (Holm-adjusted p=1.0). More importantly, the predictor effect varied across offsets: under fixed-medium risk, B1−B0 delay was −0.755 s at −3 m but +0.295 s at the nominal offset. This sign change rejects a uniform predictor benefit.

> Arrival timing also changed controller mechanisms. For B1, shifting from −3 m to +3 m increased footprint separation by 0.519 m under fixed-medium risk and 0.896 m under adaptive risk. At the same time, solver-failure fraction increased by 2.05 and 2.38 percentage points, while supervisor activity decreased by 7.07 and 6.94 percentage points. These simultaneous effects support a coupled safety–feasibility interpretation rather than attributing the closed-loop outcome to the supervisor alone.

### 4.7 Collision-filtered sensitivity

建议引用：Day13 summary、Figure 1、Table 8。

> Conservatively removing all 162 usable training windows from the six callback-containing rollouts did not change the validation architecture ranking: B1 remained ahead of B2-D, T2, T1 and B2-M. The B1 median validation NLL changed by only +0.00132 nats/step. The representative seed changed from 37 to 11, but the architecture-level conclusion remained stable. Test data were not accessed during this post-hoc sensitivity analysis.

## 5. Hypothesis verdicts

| ID | Verdict | 论文中的准确表述 |
| --- | --- | --- |
| H1 | Supported | task adaptation improves in-distribution prediction relative to B0 |
| H2 | Mechanistically supported | T1/T2 use sequence information; no causal-understanding claim |
| H3 | Refuted | tested Transformers do not outperform B1 under this dataset/protocol |
| H4 | Refuted | offline improvement does not yield uniform closed-loop gain |
| H5 | Refuted | adaptive does not universally dominate the fixed frontier |
| H6 | Descriptively supported | predictor effect is moderated by risk and timing; not confirmatory with five clusters |
| H7 | Refuted | callback-containing training rollouts do not determine the selected architecture |
| H8 | Supported for observed runs | reliability gates pass; zero observed events are not zero population risk |

机器可读对应关系见 `paper_claim_evidence_matrix.csv`，不得在正文中把 verdict 升级为超出 boundary 的结论。

## 6. Discussion 的三个主段落

### 6.1 Complexity is not the same as useful interaction modelling

Transformer 确实响应 sequence ablation，但 B1 仍最好。应讨论有限数据、强 pretrained base、residual adapter 任务以及 response-active 样本稀少，不能写成 Transformer 在自动驾驶预测中无效。

### 6.2 Offline accuracy and closed-loop utility are different objectives

B1 的 offline improvement 很大，但闭环 effect conditional。这是论文最重要的机器学习—控制接口发现：planner 只通过 risk、solver 和 supervisor 消费预测，因此预测误差改善不保证执行轨迹单调改善。

### 6.3 Adaptive risk is a conditional frontier mechanism

原假设“adaptive 普遍优于 fixed”被反驳，但不是项目失败。正确贡献是证明 adaptive/fixed 的相对位置依赖 predictor、target style 和 arrival regime，且 safety margin、solver feasibility、supervisor activity 会同时变化。

## 7. 必须保留的 limitations

1. 单一 Town05 give-way geometry，不能作跨地图或真实世界泛化；
2. validation/test 仅 5 个 independent init groups；
3. response-active test tail 仅 15 windows、6 rollouts、3 init groups；
4. 0 observed collision 不等于零碰撞概率；
5. timing batches 分批运行，仍可能有 residual batch effect；
6. sequence ablation 证明输入敏感性，不证明因果理解；
7. Day13 是 post-hoc sensitivity，不能替换 primary experiment；
8. supervisor、solver、risk 和 predictor 构成耦合系统，不能把任何单一组件称为唯一主因。

## 8. 论文资产清单

唯一入口：`docs/paper/generated/paper_assets_v1/README.md`。

- 数字：`paper_results_manifest.json`，210 个 result IDs；
- 数据表：8 个 canonical CSV；
- 主图：8 个 SVG + 8 个 PNG；
- 图注：`figures/figure_captions.md`；
- 假设索引：`paper_claim_evidence_matrix.csv`；
- 关键结果：`paper_key_results.csv`；
- 完整性清单：`paper_asset_inventory.csv`；
- 总完成门：`PAPER_EVIDENCE_PACKAGE_COMPLETE.json`。

## 9. 停止新增实验

当前证据已经覆盖数据完整性、matched model selection、Transformer mechanism、calibration limitation、deployment chain、nominal frontier、timing robustness、mechanism metrics、collision sensitivity 和 threats to validity。除非导师提出新的明确研究问题，否则不再调 Transformer、不根据 test 或 closed-loop 更换模型、不继续搜索能让 adaptive 获胜的场景。下一阶段应进入完整 Methods、Results、Discussion 和 Introduction/Literature Review 写作。
