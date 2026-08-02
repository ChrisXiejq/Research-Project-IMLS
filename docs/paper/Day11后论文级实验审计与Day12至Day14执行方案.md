# Day11 后论文级实验审计与 Day12–Day14 执行方案

> 审计日期：2026-08-02
>
> 审计范围：Day1–Day11 的协议、数据、训练、离线评价、部署、正式闭环结果、机器可读证据和论文主张。
>
> 总判定：**现有实验的数量、对照和操作已经足以支撑一篇范围明确、以机器学习为中心的 UCL 毕业论文；不需要重新设计主体实验。** 最终 readiness 为 conditional pass：进入正文前必须完成 Day6 target–infrastructure collision attribution、Day10 init-cluster 推断修正、Day10/Day11 三水平 timing 分析，以及服务器不可替代资产的第二份备份。

## 1. 审计结论

### 1.1 数据与实验量是否足够

足够。当前正式证据包括：

| 阶段 | 规模 | 作用 |
| --- | ---: | --- |
| V2 数据采集 | 200 CARLA rollouts，11,230 raw samples | 构建受控 2×2 interaction dataset |
| V2 可训练数据 | 5,037 usable samples，3,237 full-horizon samples | 模型训练和统一离线评价 |
| 数据划分 | 160 train / 20 validation / 20 test rollouts；40/5/5 init groups | 防止 temporal-window leakage |
| 正式训练 | 5 variants × 3 seeds = 15 runs | 比较简单 adaptation、matched MLP 和 Transformer |
| 冻结 test | 5 个 validation-frozen representative models × 5 subsets | 独立验证模型排序、响应子集和 calibration |
| 部署 smoke | 8 rollouts | 验证 prediction→risk→solver→supervisor 链 |
| Day10 nominal closed loop | 80 rollouts | predictor × risk × target-style 主矩阵 |
| Day11 timing robustness | 80 rollouts | predictor × risk × target-style × ±3 m 稳健性 |

这不是一个“只训练一次模型并展示几条轨迹”的简单实验。它包含数据协议、分组划分、matched architectural controls、三随机种子、validation-only selection、冻结 test、输入消融、部署等价检查和 160 条正式闭环 rollout。对于定位为**受控 CARLA case study** 的毕业论文，实验操作和数据量足够。

数据不支持把论文定位成跨地图、跨城市或真实交通上的普遍 SOTA 证明。扩大措辞边界比继续堆同一地图上的 rollout 更重要。

### 1.2 证据完整性审计

本次重新检查得到：

- Day6–Day11 所有 completion marker 均为 `status=pass`；
- Day6 200/200、Day8 15/15 training、Day9 8/8 smoke、Day10 80/80、Day11 80/80 均完整；
- 对本地可用的 15 组 completion→audit/summary/preflight SHA-256 逐项复算，全部匹配；
- 本地 8 个结果 snapshot 均可正常列出和解压；
- Day10、Day11 均为 0 collision、0 yield-order failure、0 invalid probability/covariance；
- 7 项模型/审计单元测试全部通过；
- Day11 curated evidence 可独立、逐字节复现正式分析结果。

没有发现结果文件损坏、漏 cell、失败 rollout 被误计为成功、模型哈希漂移或 test 后重新选择模型的证据。审计同时发现 Day6 的 253 个 native CARLA collision callbacks 尚未完成论文级归因，详见 P1-1；它们不发生在 validation/test 或 Day10/Day11 正式闭环中，但可能影响少量 training labels。

## 2. 证据分层：论文中哪些结果可以承担什么角色

### Tier A：正式主要证据

可进入 Results 主表和主要结论：

1. Day6/Day7：V2 数据规模、split integrity 和无 leakage；
2. Day8：五模型三 seed validation、冻结 test、calibration；
3. Gap2：B0 与 B1 的同口径离线 bridge；
4. Gap3：T1/T2 zero/shuffle interaction-sequence diagnostic；
5. Day10：nominal timing 下完整 fixed frontier 与 adaptive 比较；
6. Day11：±3 m timing shift 下的局部稳健性。

### Tier B：方法验证与机制证据

适合进入 Methods、Implementation Validation 或 appendix，不承担“谁更好”的主要结论：

- Day3 evaluator/deployment equivalence；
- Day4 input contract 和 reactive smoke；
- Day5 reactive 参数冻结；
- Day9 online deployment smoke；
- solver-failure、supervisor activity 和 risk tightening 的机制日志。

### Tier C：研究动机和负向探索

只用于解释研究转向，不与正式 V2 数字混合：

- 早期 supervisor ablation；
- v12/A1/A2/A3 开发实验；
- legacy fine-tuning 和 static-context Transformer pilot；
- 使用错误 raster channel contract 得到的旧模型数值。

Tier C 可以支持“为什么原始 adaptive-vs-fixed 问题无法被简单识别”，但不能被包装成与 Day8–Day11 同等级的确认性证据。

## 3. 论文研究问题和假设的最终冻结

### RQ1：复杂 interaction architecture 是否优于简单 adaptation

`H1a`：在受控 V2 数据上，B1 simple adaptation 相对 pretrained B0 改善同分布离线预测。

- 判定：支持；B1−B0 test ADE `-1.193 m`、FDE `-2.555 m`、uncalibrated macro NLL `-0.314`。
- 边界：这是同分布、五 test-init 的结果，不是跨域泛化。

`H1b`：Transformer 的收益不只是参数量增加，并且它使用了显式 interaction sequence。

- 判定：部分支持；T1 在 5/5 test init 上优于 matched B2-M，zero/shuffle 使 T1/T2 指标恶化。
- 边界：sequence use 不等于最优预测；T2 未超过 matched B2-D。

`H1c`：Transformer 是当前任务的最佳模型。

- 判定：否定；validation 和冻结 test 均选择 B1，T1/T2 都未超过 B1。

### RQ2：离线预测收益是否稳定转化为闭环收益

`H2`：B1 相对 B0 的离线改善会产生与 risk policy 和 arrival timing 无关的单调闭环改善。

- 判定：否定。
- Day10 nominal timing 下 B1 跨策略平均 adjusted delay `+0.046 s`、margin `-0.050 m`；
- Day11 ±3 m 合并后 B1 在 fixed-medium/adaptive 下分别快 `0.703/0.558 s`，但 margin 更小、solver/supervisor activity 更高；
- 正确结论是 predictor utility 具有 policy-conditional、timing-conditional 的闭环异质性。

### RQ3：adaptive risk 是否普遍优于 fixed risk

`H3`：adaptive risk 支配完整 fixed-risk safety–efficiency frontier。

- 判定：否定。
- Day10 中 adaptive 位于 frontier 而非支配 frontier；
- Day11 中 adaptive−fixed-medium delay 接近零，且效果依 predictor 改变；
- 只选择 fixed-medium 单点对照会夸大 adaptive 的相对表现。

### RQ4：interaction tail、arrival timing 和 runtime authority 如何改变结果

`H4a`：总体 validation calibration 能迁移到 response-active tail。

- 判定：否定；B1 tail NLL 从未校准 `2.0763` 恶化到校准后 `8.5728`。

`H4b`：arrival regime 改变 prediction→risk→solver→supervisor 的作用机制。

- 判定：得到强描述性支持；+3 m 相对 -3 m 使 margin 增加 `0.44–0.90 m`、solver failure 增加约 `1.97–2.38 pp`、supervisor activity 降低约 `6.33–7.07 pp`，并让 reactive activity 从 75–76 samples 变为 0。
- 边界：只有 5 个独立 init，属于局部机制证据。

## 4. 已发现的缺陷与处理优先级

### P0：已经确认会使主体实验无效的问题

当前未发现。

没有数据泄漏、模型选择泄漏、输入契约漂移、失败 rollout 冒充成功或碰撞遗漏的迹象。

### P1：论文写作前必须修复

#### P1-1 Day6 collision callbacks 尚未完成训练数据归因

Day6 collection audit 如实记录了 253 个 native CARLA collision callbacks。重新检查本地 200-rollout summaries 后确认：

- callbacks 只出现在 6/160 个 training rollouts；validation/test 为 0；
- 全部由 `target_2` 触发，对象为 `traffic.traffic_light` 或 `static.wall`；
- 没有 ego–target collision callback；
- 253 个 callbacks 只有 62 个 unique frames，按 actor 和连续帧粗略合并约为 16 个 contact episodes；
- 其中 210 个 callbacks 集中在 S1_FIXED/init10 的持续 target–infrastructure 接触。

这说明“253”不是 253 次独立车辆碰撞，也不推翻 Day10/Day11 的 0 footprint collision。但 reactive target 在少数训练 rollout 中接触路侧设施，可能使其 collision 后的 future labels 不再代表预期 give-way behavior。

必须在服务器完整 JSONL 上做只读 attribution：

1. 将 collision frame 与 raw/labeled sample 的 history/future frame range 对齐；
2. 统计 collision 前、overlap、collision 后的 usable/full-horizon windows；
3. 检查异常 windows 是否进入 train，确认 validation/test 为零；
4. 生成不删除数据的 exclusion sensitivity evaluation；
5. 若没有 usable label 与 collision overlap，记录为无训练污染并关闭缺口；
6. 若 overlap 很少，报告比例并对冻结模型在 clean test 上保持原结果，必要时只补做 B1 的 filtered-training sensitivity；
7. 只有当 overlap 占 reactive training 的实质比例且改变 B1/B0/T1/T2 排名时，才考虑重新训练完整矩阵。

不得因为这些 rollout 表现异常而静默删除并重新声称原协议结果；任何 filtered analysis 必须标为 sensitivity analysis。

#### P1-2 Day10 pooled inferential unit 仍不够严格（本地已关闭）

Day10 的 effect mean 是正确的，但 pooled predictor/risk contrasts 把同一 init 下的 assertive 和 reactive 两个 condition delta 作为 `n=10` 做 bootstrap/sign-flip。它没有把 20 Hz step 当样本，但两种 style 共享同一个 init，不能视作完全独立。

Day12 已仿照 Day11 完成修正：

1. 保留所有 condition pairs 用于计算平均 effect；
2. 先在每个 init 内聚合 style；
3. 只对 5 个 init-cluster means 做 bootstrap 和 exact sign flip；
4. 继续在预定义 family 内做 Holm 校正；
5. 生成 Day10 analysis v3，并更新 Day10 文档中 CI、p 和方向计数。

修正后的 136 个 contrast effect means 与旧版逐项一致；所有推断均为 5 个 init groups。Fixed-aggressive delay 的 exact p 从错误的 `0.0117` 修正为理论最小值 `0.0625`，Holm p 从 `0.1875` 修正为 `1.0`。主体结论不变，旧版 p 值废止。

#### P1-3 Day10 nominal 与 Day11 ±3 m 尚未统一分析（本地已关闭）

两个 contract 的 predictors、模型树哈希、B1 calibration、anchors、normalization、init、authority regime、reactive parameters、adaptive parameters 和 target speed 全部一致；Day11 也冻结了 Day10 contract SHA。因此可以用现有数据构建 offset `{-3, 0, +3} m` 的统一分析。

Day12 已输出：

- 每个 predictor×risk×offset 的 cell mean；
- B1−B0 随 offset 的变化；
- adaptive−fixed-medium 随 offset 的变化；
- predictor×offset 和 policy×offset interaction；
- 5-init cluster bootstrap、exact sign flip、Holm adjustment；
- 明确标记 offset=0 来自 Day10 batch，±3 来自 Day11 batch，不能完全排除 batch effect。

三水平 synthesis 覆盖 120 rollouts、24 cells、160 paired contrasts，0 collision/yield failure。跨三个 offsets，B1−B0 adjusted delay 为 fixed-medium `-0.370 s`、adaptive `-0.337 s`，但 margin 分别为 `-0.069/-0.035 m`；adaptive−fixed-medium delay 仅为 B1 `-0.063 s`、B0 `-0.097 s`。所有 inference-family Holm p 均为 1.0。它强化了“局部效率信号与 controller trade-off 并存、adaptive 不普遍支配”的结论。

#### P1-4 不可替代资产目前主要保存在单台云服务器

Git 中有完整 hashes、configs、metrics 和 curated closed-loop evidence，但没有：

- Day6 完整 JSONL/raster dataset；
- Day8 的 15 个 best model weights；
- 至少五个冻结 representative model packages；
- Day11 128 MB full snapshot。

如果服务器磁盘被回收，论文数字仍可审计，但模型训练/部署无法完整复现。必须制作第二份离线或对象存储备份，至少包含：

1. Day7 merged dataset 与 split files；
2. Day8 五个冻结 representative best models，优先保证 B0、B1、T1、T2；
3. normalization、anchors、calibration、run configs；
4. Day10/Day11 full snapshots；
5. 文件级 SHA-256 manifest。

大文件不要直接提交普通 Git；应使用本地外置目录、UCL OneDrive/对象存储或 Git LFS，并在仓库只提交 manifest。

### P2：必须在论文表达中控制，不要求重跑

1. **独立样本只有 5 个 test init。** 160 个正式闭环 rollout 不是 160 个独立交通分布样本；推断必须按 init cluster。
2. **单地图、单 give-way geometry。** 不能声称跨地图泛化。
3. **target behavior 是脚本生成。** Reactive target 是人为设计的可控 interaction，不代表自然驾驶员分布。
4. **B1 与 B0 比较是 package effect。** B1 有 validation-frozen calibration，B0 是 identity calibration，不能解释成只隔离网络权重的纯因果效应。
5. **response-active tail 很小。** Test 只有 15 samples、6 rollouts、3 init groups；tail calibration 只能作为警示性负结果。
6. **0 collision 不等于证明 collision probability 为 0。** 只能说在已运行 160 条正式 rollout 中未观测到碰撞。
7. **supervisor 会吸收 predictor/controller 差异。** executed safety 与 nominal solver feasibility 必须分别报告。
8. **jerk 不适合作主要舒适性结论。** 20 Hz 数值微分和控制切换使 raw max jerk 不稳定。
9. **Day11 +3 m reactive 未触发。** 这是 timing mechanism 的结果，但 +3 m reactive cell 不能单独支持 response-active prediction quality。
10. **Day10/Day11 是同一五个 held-out init 的重复条件。** 不能把两个 day 合并后宣称独立样本增加到 10。
11. **CARLA 中断与 resume 很多。** 论文可说明只重跑技术失败、成功 rollout 由 contract/hash 保护；无需隐瞒，但不要把 wall-clock 稳定性当模型结果。

### P3：可选增强，不是当前论文完成门

如果导师明确要求更强统计确认，可以预注册一个全新的 post-hoc replication：使用从未进入 train/validation/test 的新 init groups，冻结 B0/B1、fixed-medium/adaptive、reactive parameters 和全部 controller 配置，再运行最小 balanced matrix。它必须明确标为“独立 replication”，不能与原 test 集混称。

当前不建议直接做这项扩展，原因是：

- 它仍然只增加同一地图和同一 scripted target 下的样本；
- 不能解决外部有效性；
- 论文当前的核心主张是 conditional coupling，而不是追求一个显著的 superiority p-value；
- 统计修复、统一分析和论文图表的边际价值更高。

## 5. 重排后的 Day11–Day14 方案

### Day11：已完成，冻结，不再重跑

完成门已经满足：80/80 rollouts、16/16 cells、audit/analysis PASS。除非发现 raw corruption，否则禁止改参数或重跑，以免引入结果驱动调参。

### Day12：论文级数据归因、统计修复与最终证据冻结

#### Day12-A：关闭 Day6 collision-attribution 缺口

操作：

1. 在服务器用完整 raw/labeled JSONL 将 6 个异常 rollout 的 collision frames 与 prediction windows 对齐；
2. 输出 rollout、event、window 三层审计表；
3. 量化受影响 training windows 占 all/reactive/response-active training 的比例；
4. 先做不重新训练的 clean-test/exclusion 诊断；
5. 根据冻结 decision rule 决定是否需要 B1 filtered sensitivity training。

完成门：明确回答 collision 是否进入训练标签以及比例；不再把 253 callbacks 误写成 253 次独立车辆碰撞；任何排除规则均可复现且不改原始数据。

#### Day12-B：修复 Day10 cluster inference

操作：

1. 将 Day10 analyzer 升级为 v3；
2. 同时记录 `condition_pairs` 与 `independent_init_groups=5`；
3. 复跑分析并与旧版 effect means 做自动 diff；
4. 任何 effect mean 改变都视作异常；只允许 CI/p/计数口径变化；
5. 更新 Day10 Results 文档。

完成门：80 rollouts 保持不变；所有 effect mean 与旧版一致；所有推断来自 5 个 init-cluster means。

#### Day12-C：生成三水平 timing synthesis

操作：

1. 验证 Day10/Day11 contract compatibility；
2. 合并 fixed-medium/adaptive 的 offset `-3/0/+3 m`；
3. 生成 rollout table、cell table、paired contrast table、summary JSON；
4. 检验 predictor×offset、risk×offset 和主要 mechanism changes；
5. 将跨 batch 限制写进 summary 和论文。

完成门：120 条相关 rollouts 完整；每个 contrast 以 5 个 init 为推断单位；结果可以从 curated evidence 重建。

#### Day12-D：资产保护

操作：

1. 在服务器生成 dataset/model/full-results archive；
2. 写文件级 manifest 和总 archive SHA-256；
3. 下载或同步到第二存储位置；
4. 从第二副本随机解压并验证 model tree/hash；
5. Git 只提交 manifest 和恢复说明。

完成门：关键资产至少存在服务器之外的一份已验证副本。

### Day13：把实验变成论文表格、图和可追溯数字

建立一个 `paper_results_manifest.json`，给每个论文数字稳定 ID，例如 `R_OFFLINE_B1_ADE`、`R_DAY10_B1_DELAY`、`R_DAY11_OFFSET_MARGIN`。每个 ID 必须记录 source file、filter、aggregation unit 和 value。

必须生成的表：

1. 数据集 factorial、split 和 sample-count 表；
2. 五模型 × 三 seed validation 表；
3. 冻结 test 主结果与 matched-control 表；
4. calibration 与 response-tail 表；
5. Day10 nominal predictor×risk frontier 表；
6. Day11/combined timing robustness 表；
7. hypothesis→evidence→判定表；
8. threats-to-validity 表。

必须生成的图：

1. 研究流程：adaptive-risk motivation → interaction dataset → model comparison → frozen closed loop；
2. 模型结构和 matched controls 示意图；
3. validation/test NLL、ADE/FDE 模型比较；
4. aggregate 与 response-active calibration 对比；
5. Day10 safety–efficiency frontier；
6. B1−B0 effect 随 risk/offset 的变化；
7. offset 对 margin、solver failure、supervisor activity 的机制图；
8. prediction→risk→solver→supervisor 因果链示意图。

图表规则：

- 主结果一律显示效应量和 5-init cluster interval；
- 不使用 simulator-step error bar；
- 不用柱高隐藏 paired direction；优先使用 paired dot/slope/forest plot；
- 0 collision 写成 observed count，不画成已知的零风险；
- qualitative trajectory 只能使用预先定义的代表规则，例如 median-effect init，而不能挑最好看的案例。

### Day14：按证据链写论文，而不是按时间日记写论文

建议 Results 结构：

1. **Dataset integrity and controlled interaction coverage**：Day6/7；
2. **Offline model selection under matched controls**：Day8；
3. **Sequence use and calibration failure modes**：Gap2/Gap3；
4. **Deployment-equivalent predictor–controller chain**：Day9，简短；
5. **Nominal closed-loop predictor–risk frontier**：Day10；
6. **Timing-shift robustness and mechanism changes**：Day11 + combined analysis；
7. **Hypothesis synthesis**：哪些支持、否定、仍不确定。

Discussion 应围绕三个发现，而不是逐 Day 复述：

1. 更复杂的 Transformer 确实使用 sequence，但在有限受控数据上不如简单 adaptation 稳定；
2. 强离线预测改善不保证跨 policy 的单调闭环收益；
3. adaptive risk 的价值是改变 predictor-conditional safety–feasibility frontier，而非普遍优于 fixed risk。

## 6. 最终论文中心主张与标题

推荐标题：

> **Interaction-Aware Prediction and Predictor–Risk Coupling for Give-Way Intersection Planning in CARLA**

中心主张：

> 在受控 give-way 场景中，简单的任务适配能够显著改善同分布运动预测，Transformer 也确实利用了显式交互序列，但模型复杂度和离线指标优势都不能保证统一的闭环收益。预测器的实际价值由 risk allocation、arrival timing、solver feasibility 和 supervisor intervention 共同调节；因此 adaptive risk 应作为 predictor-conditional safety–efficiency frontier 的组成部分评价，而不是被假设为固定风险策略的普遍替代。

这个定位保留了最初 adaptive-vs-fixed 的研究动机，同时把真正完成且证据最强的机器学习实验放在论文中心。

## 7. 停止规则

以下项目完成后停止新增主体实验，转入全文写作：

- Day6 collision-window attribution 与 sensitivity decision 关闭；
- Day10 init-cluster 统计修复通过；
- Day10+Day11 三水平 timing synthesis 通过；
- 关键 dataset/model/result 有第二份已验证备份；
- 论文数字 manifest、8 张核心表和 8 张核心图生成；
- 每个 hypothesis 都有明确的 evidence ID 和结论边界。

除非导师提出明确的新研究问题，否则不再：

- 重新调 Transformer；
- 根据 test/closed-loop 结果更换模型；
- 继续寻找能让 adaptive “获胜”的特定场景；
- 补做偏离机器学习主线的 v12 controller subset；
- 用更多相关 simulator steps 伪装独立样本量。
