# Dissertation distinction readiness audit

**审计日期：** 2026-08-08  
**项目：** Research-Project-IMLS  
**状态：** 独立复核结论；优先级高于此前“14/14 PASS、无需新增实验”的表述  
**目标：** 在不把项目扩展成另一个课题的前提下，确定论文能够安全主张什么、必须修复什么，以及怎样把现有工作提升到 distinction 水平。

---

## 0. 一页结论

### 0.1 总判断

这个项目**有 distinction 潜力，但按当前论文和证据状态提交并不 distinction-safe**。

项目已经完成了一个相当扎实的实验工程：200 个数据收集 rollouts、严格的 rollout-level split、15 个训练 runs、冻结 validation selection、one-shot test、160 个正式闭环 rollouts、timing sensitivity、collision-filtered retraining，以及可追溯的表图资产。数据完整性、选模冻结和主要主表数值没有发现明显造假、split leakage、test-set reselection 或遗漏 factorial cell。

但是，当前稿件仍只有约 15 页的框架稿，存在 19 个可见 `TODO`，bibliography 只有 3 篇，Related Work 仍是提纲。同时，重新阅读关键控制、模型、统计和审计代码后发现四个会被严格评审追问的实质问题：

1. 正式单目标 SMPC 的空间碰撞约束实际重复使用 top-probability mode，而不是分别消费三个 GMM mode；
2. fixed-risk 和 adaptive-risk 的参考轨迹生成器使用不同的最小制动边界，因此原 H4 不是纯 risk-allocation 对照；
3. Day11 有一个 target–traffic-light 原生 CARLA collision，原论文只审计 ego–target footprint overlap，因而“全部 collision 为 0”的宽泛表述不成立；
4. 机器 evidence audit 主要检查文件 hash 和 evidence ID 是否存在，并没有真正解析 locator、重新读取和核对数值；66 个 JSON locators 中有 42 个按标准 JSON Pointer 无法解析。

此外，ML 论证还缺少 constant-velocity、constant-acceleration 和 train-mean 等物理基线；B1 与 Transformer 的训练参数量和适配位置也并不匹配。因此，当前证据不能证明“simple adaptation 在容量匹配后优于 Transformer”，只能证明：

> B1 是当前预算与实现下表现最好的 tested task-adaptation model；在两个真正容量近似匹配的 residual-adapter pairs 中，attention 的收益随输出参数化改变，并没有表现出一致优势。

### 0.2 最有价值的论文方向

论文不应该包装成“提出并证明一个新 Transformer”，也不应该包装成“首次发现 open-loop 指标不能预测 closed-loop 表现”。后者已经有直接先行工作。

最强、最诚实且仍然以机器学习为中心的定位是：

> **在一个冻结的小数据 give-way 协议中，任务适配带来很大的同分布总体预测提升，但显式 sequence attention 没有在两个 matched residual output scopes 上产生一致优势。部署后的日志进一步表明，总体预测提升在多数闭环条件中仍然存在，但在稀有 interaction-active tail 中明显衰减、局部反转，并被全局校准放大为严重过度自信；最终的控制收益还取决于 risk policy stack、target response 和 arrival timing。**

这比单纯报告“B1 好、Transformer 不好”更立体，也比把结果全部归因于 supervisor 更有学术价值。

### 0.3 推荐标题

> **Task-Adapted Motion Prediction under Predictor–Risk Coupling: A Controlled CARLA Give-Way Study**

中文工作标题：

> **预测器—风险耦合下的任务适配运动预测：一项受控 CARLA Give-Way 研究**

标题把 ML 放在第一位，同时不暗示提出了新的 Transformer、普适风险算法或真实道路安全保证。

### 0.4 关于“保证 distinction”

任何人都不能保证最终分数，因为分数还取决于最终文字质量、答辩、评阅人的尺度和学校流程。可以控制的是：消除会直接损害可信度的缺陷，使每个主张都与证据强度相匹配。

如果今天按现有 15 页框架稿直接提交，我对整体成熟度的判断是 **Merit 区间，约 55–65 的风险带**；实验资产本身强于当前稿件。完成本文 P0 项、补齐文献和方法、正式化现有日志分析，并对两个控制实现问题选择“披露并收窄”或“修复后重跑”，才有现实的 **70+** 竞争力。

---

## 1. 审计范围与方法

本次审计覆盖：

- `docs/dissertation/` 中的 marking rubric、TMLR LaTeX 主稿、中文骨架、带读版和写作 checklist；
- `docs/paper/` 中四份 canonical paper documents、Day14 tables/figures、result manifest 和 final audit；
- `docs/literature/` 中五篇本地核心论文及文献解读，并补查直接相关的最新 primary literature；
- 数据收集、split/normalisation、模型构建、训练、选模、校准、部署、Day10–Day14 分析和 evidence audit 代码；
- CARLA/SMPC 中 GMM mode consumption、risk policy、reference generation、solver/supervisor telemetry 和 collision logging 路径；
- `offsite_backups/day12_evidence_freeze_v1/` 中 Day10、Day11、模型和数据集快照；
- 2026-05-07 至 2026-08-03 的 Git 历史和 Day1–Day14 里程碑。

复核动作包括：

- 运行全部现有 model unit tests：19/19 PASS；
- 重新检查 dataset counts、split keys、selection freeze、正式矩阵 completeness 和主要 point estimates；
- 以 init group 为独立单位复算关键 paired effects 和 exact sign-flip 下限；
- 读取 Day10/Day11 原始 rollout summary 和 in-loop labelled prediction logs；
- 对 evidence manifest 的 locator 进行标准 JSON Pointer 可解析性检查；
- 检查正式闭环调用路径是否与论文中的系统描述一致。

19/19 tests PASS 说明已覆盖的代码行为正常，但**现有测试并未覆盖本次发现的 mode-indexing、native-collision audit 和 locator-value resolution 问题**。因此，测试通过不能替代方法层审计。

### 1.1 里程碑时间线审计

| 时间 | 实际里程碑 | 论文中应如何呈现 |
| --- | --- | --- |
| 2026-05-07 至 05-28 | 项目导入、CARLA/SMPC 兼容、交叉口与初步结果 | Background implementation and pilot reproduction |
| 2026-05-29 至 06-03 | 文献、汇报材料、初步研究定位 | Initial literature and research scoping |
| 2026-06-07 至 07-26 | give-way 场景、SMPC 行为、风险对照和早期 ablations | Pilot investigation；不要混入 frozen confirmatory protocol |
| 2026-07-31 | Day2–Day6 protocol/data pipeline 和 collection runner 冻结 | Protocol and data-generation stage |
| 2026-08-01 | Day7 dataset/model gates；Day8 训练开始 | Dataset construction and model-selection stage |
| 2026-08-02 | Day8 test、Day9 deployment、Day10–Day13 闭环/敏感性 | Frozen evaluation and robustness stage |
| 2026-08-03 | Day14 result manifest、tables/figures、TMLR skeleton | Evidence packaging and manuscript stage |
| 2026-08-08 | 本次 adversarial distinction audit | Scientific validity review and remediation stage |

`Day1–Day14` 是项目管理标签，不是十四个自然日，也不是论文的科学结构。最终正文按 protocol stages 叙述，Day labels 只留在 reproducibility appendix 或 artifact index。早期大量 generic Git messages（如 `feat: add`、`feat: ablation`）不适合作为单独审计证据；正式方法以 7 月底之后的 frozen contracts、hashes 和 manifests 为主。

---

## 2. 按 UCL rubric 的现状判断

以下不是正式评分，而是用 rubric 的 distinction 描述对当前产物做的风险评估。

| 维度 | 当前判断 | 主要优点 | 当前阻塞项 | 修复后潜力 |
| --- | --- | --- | --- | --- |
| Research gap / objectives | 60–66 | 项目演化自然，原 planning 问题保留，四个 RQ 已聚焦 | novelty 与 2025 直接先行工作重叠；中心因果措辞过强 | 70–75 |
| Related work | 35–45 | 已有五篇本地核心材料和合理提纲 | 仅 3 篇 bib、3 处引用、整章仍是 TODO | 70–78 |
| Methodology / reproducibility | 62–68 | split、freeze、hash、run contract 很强 | mode mapping、A_MIN 对照、部署范围和 aggregation 口径未准确披露 | 70–76 |
| Experiments / analysis | 65–71 | 数据量、factorial matrix、timing 和 sensitivity 丰富 | 缺物理基线；n=5 功效不足；native collision 漏审；B1/T 不公平 | 70–78 |
| Discussion / critical insight | 62–68 | 已认识到 calibration、solver、supervisor 和 timing | “refuted”“full frontier”“low-capacity”过度；尚未利用 active-tail 机制 | 72–80 |
| Presentation / professional finish | 55–63 | TMLR 排版整洁、已有 8 图 8 表资产 | 19 TODO、方法/附录未完成、引用与 artifact availability 不完整 | 70–76 |

目前最大的落差不是工作量，而是**论证纪律**：实验工程接近高水平，但稿件还没有把“事实、推断、限制、探索性发现”分开。

---

## 3. 项目真正值得突出的贡献

### 3.1 强贡献：受控且可追溯的 ML→control 证据链

项目不是只给一张 ADE 表。它把数据收集、任务适配、模型对照、校准、部署、风险策略、solver/supervisor 和执行结果连成了一条可审计链，并冻结了 model selection 和 test opening。对于 MSc 论文，这是明显优点。

### 3.2 强贡献：负向结果不是失败，而是边界识别

Transformer residual adapters 确实对 sequence ablation 敏感，却没有跨两个 matched output scopes 一致胜过 MLP residual adapters。这能排除“模型完全忽略 sequence”这一简单解释，同时说明 attention 本身不是充分条件。

### 3.3 更强的潜在贡献：interaction-active tail 机制

对 Day10/Day11 已保存的 in-loop labels 做只读初查后发现：

- 汇总层面，B1 的 top-1 ADE/FDE 在三个 arrival offsets 均远好于 B0；
- 但在 reactive/active tail，offset −3 m 时 B1 top-1 ADE 初查约为 2.149 m，反而差于 B0 的 1.119 m；
- 同一条件下 B1 deployed calibrated NLL 初查约为 30.681，而反推 uncalibrated NLL 约为 2.332；
- 0 m active tail 中 B1 ADE 略优于 B0，但 calibrated NLL 仍极差；+3 m 基本没有 active samples。

这组结果目前必须标为 **post-hoc, exploratory, pending a reproducible analysis script**，不能直接写入最终数字表。但它提供了很好的论文机制：

> 总体 task adaptation gain 并没有在闭环里简单消失；它主要由 inactive majority 保持。真正的问题集中在 behavior/timing-conditioned interaction tail，并由全局 calibration 进一步放大。

这比“offline 与 closed loop 不一致”更具体，也更能体现你的 ML 分析能力。

### 3.4 系统贡献：把 adaptive-risk 问题放回上下文

论文可以保留最初的 adaptive-vs-fixed 问题，但结论必须从“某一算法输赢”改成：在这个实现中，risk policy 是 predictor、reference generation、solver 和 supervisor 共同形成的 policy stack。当前证据显示没有观察到冻结 adaptive stack 对三个预设 fixed stacks 的统一优势。

---

## 4. 建议冻结的中心论点与四个假设

### 4.1 中心论点

英文建议：

> Under a frozen small-data give-way protocol, output-head task adaptation produced a large, sign-consistent in-distribution prediction improvement. Lightweight Transformer residual adapters used temporal context but did not provide a consistent advantage over capacity-matched MLP residuals across output parameterisations. In deployment, aggregate predictor improvement coexisted with failure in the rare interaction-active tail and with policy-, behaviour- and timing-dependent control effects. Prediction quality must therefore be evaluated together with calibration and the risk-control operating context.

中文解释：

> 在冻结的小数据 give-way 协议中，输出头任务适配带来了大幅、跨 init 方向一致的同分布预测提升。轻量 Transformer residual adapters 的确使用时间信息，但在不同输出参数化下没有稳定超过容量近似匹配的 MLP。部署后，总体预测提升与稀有交互尾部失败同时存在，控制效果又随策略、目标行为和到达时间改变。因此，预测质量必须与校准和风险—控制运行条件一起评价。

### 4.2 四个假设及当前判定

| 假设 | 最终严谨形式 | 当前判定 | 可以写到什么程度 |
| --- | --- | --- | --- |
| H1 | B1 相对冻结 B0 改善 held-out、同分布 give-way prediction | **强描述性支持** | ADE/FDE/NLL 在 5/5 init groups 方向一致；双侧 exact p=0.0625，不能写 p<0.05 |
| H2 | 在两个匹配输出范围中，用 Transformer 替代容量近似匹配的 MLP 会产生一致收益 | **未获支持** | T1 略胜 B2-M，T2 略逊 B2-D；attention effect 依赖 output parameterisation |
| H3 | B1 predictor stack 的离线优势会跨 policy/style/timing 稳定转化为闭环收益 | **未获一致支持** | 同批次 Day10 已显示 policy/style heterogeneity；Day12 timing 仅作 robustness，不作强因果 moderation |
| H4 | 冻结 adaptive policy stack 支配三个预设 fixed policy stacks | **在测试矩阵中未观察到普适支配** | 只能讨论 tested empirical operating set；当前不能把差异纯归因于 risk allocation |

统一避免使用 “proved/refuted”。建议使用：

- `strong descriptive support within the tested distribution`；
- `not supported under the tested protocol`；
- `no universal pattern/dominance was observed in the tested matrix`。

---

## 5. Critical defects：提交前必须处理

### C1. 正式 SMPC 并没有把三个空间 mode 分别传入碰撞约束

**代码证据：** `core/scripts/carla/utils/mpc_utils.py:60–81, 703–735`。

在 `N_TV == 1` 且使用正式 profiles 时，`_mode_component(...)` 对所有 joint index 都返回 0。GMM modes 预先按概率排序，因此三个 optimization branches 的空间均值和协方差都来自 top-1 mode。Adaptive stack 仍使用 mode probability 参与 risk-total constraint，但空间 collision constraints 并不是完整 top-3 multimodal geometry。

**影响：**

- 160 个闭环 rollouts 不等于完全无效；它们仍是该 legacy top-mode spatial policy stack 的真实执行结果；
- 但论文不能声称 planner 对三个 GMM spatial modes 做了完整 multimodal propagation；
- 现有 tests 没有覆盖 `_mode_component`。

**二选一：**

1. **披露路线：**保留旧结果，将 closed-loop system 明确称为 `legacy top-mode spatial SMPC interface with mixture-probability risk weighting`；所有结论限制到该实现；
2. **重跑路线：**改为 `_joint_mode_component`，增加 mode-consumption audit 和 unit tests，完成 smoke 后重新跑新的正式矩阵；修复前后的 rollout 不能合并。

### C2. Fixed/adaptive 对照混入了 reference braking bound

**代码证据：** `core/scripts/carla/policies/smpc_agent.py:524–531, 1286–1296, 1313–1329`。

fixed-risk/non-OBCA 的 reference generator 使用 `A_MIN=-4.0`，adaptive 使用 `A_MIN=-3.0`。这意味着 H4 比较的是两个 policy stacks，而不是只改变 risk allocation 的 controlled contrast。

**影响：**

- “adaptive risk 不如 fixed risk”的纯算法因果结论不成立；
- Methods 中“share the solver”不能让读者误以为 reference-generation constraints 也完全相同。

**处理：**若不重跑，全文统一用 `adaptive policy stack vs fixed policy stacks`。若希望保留 risk-allocation causal claim，必须统一 A_MIN 并重跑对应 comparison cells。

### C3. Day11 有 native environmental collision，但原 audit 没有检查它

**原始证据：** Day11 backup 中：

`B1_adaptive_reactive_offset_m3/scenario_uk_give_way_ego_init_50_smpc_var_risk/scenario_run_summary.json`

记录了 91 个 collision callbacks，角色为 `target_2` 与 `traffic.traffic_light`，分布在 20 个 unique frames。它不是 ego–target collision，但它说明该 rollout 的目标车与基础设施发生了物理接触。

**影响：**

- “footprint ego–target collision = 0”仍可成立；
- “all closed-loop collisions = 0”不成立；
- 当前 Day10/11 audit 没有读取 `extra.collision_event_count`。

**处理：**

- 新增 native collision 全矩阵 audit，区分 ego–target、target–infrastructure、ego–infrastructure；
- 把 init50 整个配对 cluster 删除做 complete-case sensitivity；初查显示主要 delay 方向不变，但 n 降为 4，双侧 exact p 最小只能到 0.125；
- 最理想做法是修复目标路线/交通灯碰撞原因后，重跑所有与该 init 匹配的 treatment cells，而不是只补一个“好看的”cell。

### C4. Evidence audit 目前只证明“文件存在”，没有证明“数字正确”

**代码证据：**

- `core/scripts/models/audit_paper_evidence_package.py:61–67, 104–123`；
- `core/scripts/models/audit_final_thesis_evidence.py:121–137`。

现有代码检查 source SHA、result ID 和 figure linkage，但不解析 `source_locator`，也不从 source 重新提取 value。`new_formal_experiment_required` 还是硬编码 `False`。66 个 JSON locators 中有 42 个无法按标准 JSON Pointer 解析。

**处理：**

- 为 JSON、CSV 增加真正的 locator resolver；
- 对每个 result ID 从 source 重新提取、类型检查、单位检查、容差比较；
- 将 old H1–H8 table 重建为当前四假设 matrix；
- 删除硬编码的“无需新实验”，改为根据 defect gate 自动产生状态。

在修复前，`14/14 PASS` 只能解释为 execution/package completeness，不得解释为 210 个结果值全部审计正确。

### C5. 缺少简单物理预测基线

当前模型表只有 B0/B1/B2/T。对于单路线、2 s horizon、assertive target 近似直行的受控场景，constant velocity 可能很强。MultiPath 原论文自身也报告 linear/constant-velocity 类基线。

**必须用冻结的现有数据补：**

- constant velocity；
- constant acceleration；
- train-mean trajectory；
- 如报告 NLL，只能用 train residuals 拟合 covariance，不能看 val/test；
- 按 aggregate、assertive、reactive、response-active 和 init-group 汇总 ADE/FDE。

该实验不需要新 CARLA。结果将决定 ML 论点的强度：

- 若 B1 明显胜过物理基线，ML value 大幅增强；
- 若 CV 接近或胜过 B1，论文必须改为“场景可预测性与 domain adaptation 诊断”，不能宣称复杂 learned prediction 必要。

### C6. B1 与 Transformer 不是公平的 complexity 对照

当前 trainable parameters：

| Variant | Trainable parameters | 可公平比较对象 |
| --- | ---: | --- |
| B1 | 1,034,208 | B0 的 task-adaptation benchmark；不与 T1/T2 作 capacity attribution |
| B2-M | 77,600 | T1 |
| T1 | 86,688 | B2-M |
| B2-D | 176,096 | T2 |
| T2 | 165,728 | B2-D |

B1 重训 base model 最后 Dense prediction head；B2/T 冻结 base，只训练受 `tanh` 限幅的 residual adapters。差异同时包括可训练参数量、适配位置、表示访问方式和输出自由度。

**必须改写：**

- 删除 B1 是 `low-capacity head` 的说法；
- B1 只能称为 `output-head task adaptation` 或 `best tested adaptation baseline`；
- architecture claim 只由 B2-M↔T1、B2-D↔T2 支撑；
- H2 判定为“不一致”，不是“Transformer 被反驳”。

### C7. 统计功效不足，不能把描述性结果写成显著因果结论

独立 cluster 只有五个，因此双侧 exact sign-flip 最小非零 p 值是 0.0625。H1 的 ADE/FDE/NLL 在 5/5 init 上都改善，是很强的方向一致性证据，但不是传统 p<0.05。

现有 n=5 percentile bootstrap interval 也容易显得过度确定。主图应显示五个 raw paired cluster effects、mean 和 exact p；bootstrap 只能明确标为 descriptive uncertainty。

不要事后改成单侧检验。不要把 simulation windows 或 steps 当独立样本扩大 n。

### C8. 当前论文不是完整论文

截至审计时：

- 约 15 页；
- 19 个可见 `TODO`；
- bibliography 仅 3 篇；
- Related Work 基本是编辑说明；
- reproducibility appendix、supplementary tables 和 evidence appendix 未完成；
- 8 张图、8 张表资产中，正文只使用了部分；
- Day9 被写成 raster/sequence deployment gate，但实际只部署 B0/B1 两输入模型，T1/T2 从未进入 CARLA。

如果不把这些内容补完，实验再多也难以达到 rubric 对 research gap、critical literature、unambiguous methodology 和 broad discussion 的 70+ 描述。

### C9. Primary adjusted delay 使用了 outcome-dependent conflict point

`core/scripts/postcarla_trajectory_gate.py:180–225` 先从每个 rollout 实际发生的 ego/target trajectories 找最近点，再用该点判定 target clear 和 adjusted delay。也就是说，所谓 conflict point 会随 predictor、policy 和实际执行轨迹改变。Day10 中该点的 x 范围初查约为 0.944 m，Day11 约为 1.413 m；按约 9 m/s 的目标速度，足以贡献约 0.10–0.16 s 的时间差，和部分 treatment effect 同量级。

**处理：**优先根据冻结道路几何定义共同的 conflict zone/line，再从已有原始轨迹重算 delay，不需要重新运行 CARLA。若原始轨迹无法完整恢复，则将 raw completion time 升为主效率结果，把当前 adjusted delay 降为 sensitivity metric。

---

## 6. 其他必须准确披露的方法边界

1. **响应事件稀少。** Reactive trigger rollout coverage 约 88%，但平均 active fraction 约 6%；frozen test response-active 只有 15 windows、6 rollouts、3 init groups。总体指标主要被 inactive/easy windows 支配。
2. **方差参数化有 1 m 未校准下限。** `std = exp(abs(raw))`，B1 的总体 ADE 远小于 1 m；validation calibration 的 covariance scale 约 0.00827，相当于 std 乘约 0.091。这是 aggregate NLL 大幅改善、active tail 过度自信的重要机制。
3. **Coverage 不是 full-mixture calibration。** 代码只计算 top-probability component 的二维 ellipse coverage，正文必须写 `top-mode elliptical coverage MAE`。
4. **训练 loss 与 architecture ranking metric 不同。** Checkpoint 由 masked window-level validation loss 选；architecture 由 full-horizon rollout-macro mixture NLL 排名。Methods 必须解释两层 selection。
5. **ADE/FDE 与 NLL 聚合口径不完全一致。** 主 ADE/FDE 是 flat window mean，主 NLL 是 rollout macro；附表应补 rollout-和 init-macro ADE/FDE。
6. **Closed-loop treatment 含 calibration。** B0 使用 identity calibration，B1 使用 validation-fitted calibration，因此 H3 是 predictor-stack effect，不是 weights-only effect。
7. **同一 init 只运行一次。** 五个 init 是设计扰动，不估计同一初始条件下 CARLA 的 run-to-run stochasticity。
8. **Offline test 与 closed loop 共用 init 46–50。** 后者没有参与选模，但不是外部独立 population replication。
9. **数据分布受旧行为策略影响。** V2 collection 使用 legacy fine-tuned predictor 驱动的 ego stack；reactive target labels 因此属于 behavior-policy/model-induced distribution。
10. **三个 fixed settings 不是完整连续 frontier。** 统一使用 `pre-specified three-point fixed-risk comparator set`、`sampled empirical frontier` 或 `tested operating set`。
11. **“preregistered”不准确。** 如无外部注册，应写 `pre-specified in a frozen Git/run contract`。
12. **资产可获得性不足。** 大数据集和模型在 offsite tar 中，但仓库 manifest 仍包含服务器绝对路径，尚无 examiner 可访问的 UCL storage/Zenodo URI。
13. **执行顺序和 timing batch 混杂。** Day10/Day11 都固定先 B1 后 B0；0 m 来自 Day10，而 ±3 m 来自 Day11。三水平 timing 趋势只能作描述性 robustness；同一 Day11 batch 内 −3 m 与 +3 m 的比较更可信。
14. **近似 footprint geometry。** Footprint 使用请求 blueprint 的硬编码尺寸和 0.25 m inflation，但实际 blueprint 可能 fallback。应核对实际 spawned blueprint，并对 inflation margin 做 sensitivity。
15. **场景命名可能误导。** `scenario_uk_give_way.json` 的实现被配置为 conventional right-hand traffic/left turn；除非地图、规则和路线证据一致，不要仅凭文件名在正文称为 UK traffic scenario。
16. **一个长度检查表达式有缺陷。** `core/scripts/models/closed_loop_metrics.py:34–40` 使用链式 `a != b != c != d`，不能覆盖所有长度不等情况；应改为集合长度检查并补 unit test。该问题尚未证明影响现有完整 rollouts，但必须关闭潜在 silent mismatch。

---

## 7. 文献与 novelty 审计

### 7.1 直接先行工作改变了 novelty 表述

Bouzidi et al., *Closing the Loop: Motion Prediction Models Beyond Open-Loop Benchmarks* (ITSC 2025) 已经系统显示：更好 open-loop accuracy 不一定带来更好 closed-loop driving，小模型也可能与大模型相当或更好。因此本文不能声称首次发现 open-loop/closed-loop mismatch。

本文可防守的新颖性是更窄的 controlled refinement：

- 同一 MultiPath backbone 上比较 pretrained、output-head adaptation 和轻量 residual adapters；
- 显式控制两个 matched MLP/Transformer pairs；
- 同时改变 predictor stack、risk operating points、assertive/reactive target 和 arrival timing；
- 记录 calibration、solver 和 supervisor 中间机制；
- 在 give-way multimodal SMPC reproduction 中展示 interaction-tail failure。

### 7.2 最终 Related Work 建议 25–35 篇 primary sources

至少覆盖以下四组：

1. **Multimodal prediction / adaptation：** MultiPath、MultiPath++、AgentFormer、Scene Transformer、Wayformer、MTR、UniTraj、domain adaptation/PEFT；
2. **Risk-aware planning：** Iterative Risk Allocation、Nair 2022/2025、Branch MPC、GMM chance-constrained MPC、belief-function SMPC；
3. **Prediction–planning coupling：** DIPP、task-relevant failure detection、regret-based prediction evaluation、Bouzidi 2024/2025、nuPlan；
4. **Calibration：** proper scoring rules、classification/regression calibration、trajectory-prediction calibration、subgroup/multicalibration。

MultiPath 的正式 PMLR publication year 应从当前 BibTeX 的 2019 修正为 2020。

优先补入的核心文献与用途如下；写作时仍需逐篇核对正式出版信息和 BibTeX：

| 主题 | Primary source | 在论文中的作用 |
| --- | --- | --- |
| Backbone | [Chai et al., MultiPath, PMLR 2020](https://proceedings.mlr.press/v100/chai20a.html) | 解释 anchor-based GMM、官方 physical/linear baseline precedent |
| Prediction | [Varadarajan et al., MultiPath++, ICRA 2022](https://doi.org/10.1109/ICRA46639.2022.9812107) | 更现代的 sparse representation/fusion 对照 |
| Interaction | [Yuan et al., AgentFormer, ICCV 2021](https://doi.org/10.1109/ICCV48922.2021.00967) | Transformer interaction trajectory prediction |
| Interaction | [Ngiam et al., Scene Transformer, ICLR 2022](https://openreview.net/forum?id=Wm3EA5OlHsG) | scene-level attention 对照 |
| Interaction | [Nayakanti et al., Wayformer, ICRA 2023](https://doi.org/10.1109/ICRA48891.2023.10160609) | 大规模 attention predictor；强调与轻量 adapter 的差别 |
| Interaction | [Shi et al., Motion Transformer, NeurIPS 2022](https://arxiv.org/abs/2209.13508) | multimodal intention/local movement modelling |
| Generalisation | [Feng et al., UniTraj, ECCV 2024](https://doi.org/10.1007/978-3-031-73254-6_7) | 跨数据集 generalisation 边界 |
| Adaptation | [Forecast-PEFT, 2024 preprint](https://arxiv.org/abs/2407.19564) | 参数高效适配背景；只能作为 preprint |
| Risk allocation | [Ono and Williams, Iterative Risk Allocation, CDC 2008](https://doi.org/10.1109/CDC.2008.4739221) | risk allocation 基础 |
| Direct lineage | [Nair et al., intersection SMPC, ITSC 2022](https://doi.org/10.1109/ITSC55140.2022.9921751) | 当前 intersection implementation 的直接方法血缘 |
| Direct lineage | [Nair et al., predictive control with multimodal predictions, TCST](https://doi.org/10.1109/TCST.2024.3451370) | adaptive/variable-risk 原始问题背景 |
| Multimodal MPC | [Chen et al., Branch MPC, RA-L 2022](https://doi.org/10.1109/LRA.2022.3156648) | 完整 multimodal planning 对照 |
| Chance constraints | [Ren et al., recursively feasible GMM MPC](https://doi.org/10.1109/TCST.2024.3477089) | 区分 formal guarantee 与 empirical separation |
| Belief/risk | [Benciolini et al., belief function SMPC, ACC 2024](https://doi.org/10.23919/ACC60939.2024.10644881) | mode probability reliability 与 risk coupling |
| Predictor→planner | [Bouzidi et al., learning-based predictors in Branch MPC, ITSC 2024](https://doi.org/10.1109/ITSC58415.2024.10919884) | prediction/planning interface |
| Direct novelty comparator | [Bouzidi et al., Closing the Loop, ITSC 2025](https://doi.org/10.1109/ITSC60802.2025.11423816) | 直接限定本文 novelty，必须在 Introduction/Discussion 使用 |
| Integrated planning | [Huang et al., DIPP](https://doi.org/10.1109/TNNLS.2023.3283542) | prediction/planning joint objectives |
| Task relevance | [Farid et al., Task-Relevant Failure Detection, CoRL](https://proceedings.mlr.press/v205/farid23a.html) | 为什么 ADE 不能表达 downstream harm |
| Task relevance | [Nakamura et al., Regret Metric, CoRL](https://proceedings.mlr.press/v270/nakamura25a.html) | planner-sensitive evaluation |
| Closed-loop benchmark | [Caesar et al., nuPlan](https://arxiv.org/abs/2106.11810) | closed-loop benchmark 背景 |
| Calibration | [Guo et al., calibration, ICML 2017](https://proceedings.mlr.press/v70/guo17a.html) | temperature scaling 背景；不是 trajectory calibration 的充分依据 |
| Regression calibration | [Kuleshov et al., ICML 2018](https://proceedings.mlr.press/v80/kuleshov18a.html) | 连续预测不确定性 |
| Regression calibration | [Levi et al., 2022](https://doi.org/10.3390/s22155540) | regression uncertainty evaluation |
| Trajectory calibration | [Wirth et al., ITSC 2019](https://doi.org/10.1109/ITSC.2019.8917499) | trajectory distribution quality |
| Proper scoring | [Gneiting and Raftery, 2007](https://doi.org/10.1198/016214506000001437) | NLL/proper scoring rule 理论 |
| Subgroup calibration | [Hébert-Johnson et al., ICML 2018](https://proceedings.mlr.press/v80/hebert-johnson18a.html) | 解释 aggregate calibration 不保证 subgroup calibration；不声称本文实现 multicalibration |

### 7.3 必须加入的两个综述表

**Table RW-A — prediction/adaptation methods**

列：work、input/backbone、interaction mechanism、dataset scale、adaptation strategy、probabilistic output、calibration、closed-loop evaluation。

**Table RW-B — prediction–planning coupling**

列：work、predictor varied、planner/risk varied、reactive agents、timing stress、calibration、solver/supervisor telemetry、main limitation。

表后可以谨慎写：

> The directly comparable studies reviewed here do not jointly report task-adapted predictor controls, a pre-specified multi-point fixed-risk comparator set, reactive target styles, timing perturbations, and solver/supervisor telemetry within one frozen implementation.

不要写未经系统综述支持的 `This is the first study ...`。

---

## 8. 下一步实验：按收益和风险排序

### P0-A. 不需要新 CARLA，必须先完成

#### A1. 物理基线

**实验组：** B1 frozen test predictions。  
**对照组：** B0、CV、CA、train-mean trajectory。  
**控制：** 同一 frozen split、相同 2 s horizon、相同有效 mask、baseline 参数只从 train 拟合。  
**指标：** top-1 ADE/FDE；可选 train-fitted Gaussian NLL；rollout/init macro；assertive/reactive/active subset。  
**输出：** 一张主表、一张五-init paired plot、JSON/CSV 和 machine audit。

#### A2. B1 输入依赖消融

B1 不消费 interaction sequence，所以不要做不存在的 B1 sequence ablation。应对 raster 和 past-state 输入分别做 frozen zero/shuffle sensitivity，并明确这是 OOD diagnostic，不是因果 attribution。

**目的：**判断 B1 是真正利用 scene representation，还是主要学习目标路线先验/输出域修正。

#### A3. 正式化 in-loop prediction analysis

Day10/Day11 每个 rollout 已保存 `prediction_dataset_labeled.jsonl`。新增可复现脚本，按：

- predictor × policy × target style × offset；
- active / inactive；
- rollout macro 和 init cluster；

计算 top-1 ADE/FDE、mixture NLL、top-mode coverage。必须同时报告 deployed calibrated 和可合法复原的 uncalibrated B1 指标，并注明不同 predictor 会诱导不同闭环 trajectory，不能把它当作 causal mediation。

这一步最可能形成论文新的核心图：**aggregate gain 与 active-tail failure 同时存在**。

#### A4. Native collision 与 complete-case sensitivity

扫描 Day10/Day11 的所有 `scenario_run_summary.json`，重新聚合 callback→unique frame→episode→actor pair。输出：

- ego–target footprint overlap；
- CARLA native ego–target；
- ego/target–infrastructure；
- 受影响 rollout 和 paired init cluster；
- 去掉受影响整个 cluster 后的全部主 contrast。

#### A5. 训练预算和公平性表

15 个 runs 中 10 个 best epoch 等于 20 的上限，另有 3 个为 19、2 个为 18。必须拉齐并画 learning curves，说明训练可能尚未完全收敛。先做只读曲线审计；若 validation curves 仍持续下降，再考虑仅用 train/validation 的 50-epoch post-hoc sensitivity，不能再次用已打开 test 选模型。

生成参数—性能—延迟表，列出 total/trainable parameters、output scope、history、best epoch、validation mean/SD、test NLL、latency。

#### A6. 修复 evidence audit

将四假设、source locators、数值重算、units、figure/table linkage 和 collision taxonomy 全部纳入 machine gate。修复后才能重新声称“evidence audit PASS”。

#### A7. 重算控制指标与几何敏感性

- 用冻结的道路几何 conflict point/zone 重算 adjusted delay；
- 以 raw completion time 作独立核对；
- 对 actual spawned blueprint dimensions 和 footprint inflation margin 做 sensitivity；
- 生成 train/validation/test speed、offset、active coverage 的 split-balance table；
- 修复 `closed_loop_metrics.py` 的长度一致性检查并增加 regression test。

### P0-B. 控制实现的决策门

在任何新 CARLA 运行前先决定论文采用哪条路线。

#### 路线 S：安全收窄，不重跑旧矩阵

适合剩余时间很短或修复后 solver smoke 不稳定的情况。

- 保留 Day10/11 为 legacy implementation evidence；
- 明确 top-mode spatial limitation；
- H4 改为 adaptive/fixed **policy-stack** comparison；
- native collision 做完整 sensitivity；
- 不声称 full multimodal SMPC 或 risk-allocation causal effect。

这条路线仍有 distinction 潜力，前提是论文把“发现实现边界并重新限定结论”写成严谨的 scientific audit，而不是隐藏问题。

#### 路线 R：修复后重跑核心矩阵

适合仍有至少 3–4 天稳定服务器窗口，并且 smoke 全通过。

先完成：

1. `_mode_component` 改为正确 single-TV/multi-TV joint-mode mapping；
2. fixed/adaptive 统一 reference-generator `A_MIN`；
3. 新增 mode-consumption telemetry，证明 modes 0/1/2 的 means/covariances 被分别消费；
4. native collision 作为 hard gate；
5. 8-arm smoke 连续通过，且 solver failure 不出现系统性恶化。

然后重新跑最小完整 nominal matrix：

| Factor | Levels |
| --- | --- |
| Predictor stack | B0, B1 |
| Risk policy | fixed-aggressive, fixed-medium, fixed-conservative, adaptive |
| Target style | assertive, reactive |
| Init groups | 46–50 |
| Total | 2 × 4 × 2 × 5 = **80 rollouts** |

这是保留 H3 和 H4 的最小新核心矩阵。旧/new implementation 不能 pool。Timing shifts 先不重跑，除非 nominal 结果稳定且时间充足。

### P1. 若还有一次额外 40-rollout 预算

做 calibration factorial，而不是训练更大的 Transformer：

- 新增 B0 + validation calibration；
- 新增 B1 + identity calibration；
- fixed-medium/adaptive × assertive/reactive × init46–50；
- 共 40 rollouts。

配合已有 B0 identity / B1 calibrated，可分解 weights、calibration 和 interaction。但若已经修复 mode/A_MIN，则四个 stacks 必须全部在同一 corrected implementation 下运行，不能把旧结果拼进新 factorial。

### P2. 可选，不是当前优先级

- 新的 held-out init groups，提高独立 cluster 数；
- event-centred collection，增加 response-active tail；
- longer-history 或完整 interaction architecture；
- cross-map/cross-junction；
- joint predictor–planner training。

这些适合 future work。当前不要再训练一个更大的 Transformer；它不能修复现有因果和基线问题。

---

## 9. 论文写作的证据结构

### 9.1 推荐章节顺序

1. **Introduction**：原 adaptive-risk 问题 → 为什么需要先审计 predictor → 中心论点和四个 RQ；
2. **Related Work**：multimodal prediction/adaptation → interaction architectures → calibration/task relevance → risk-aware planning/closed loop → precise gap；
3. **Problem Formulation**：prediction distribution、calibration、risk-control stack、measurement boundaries、scope of inference；
4. **Methodology**：scenario、data-generating policy、split、models、loss/selection/calibration、SMPC legacy/corrected implementation、statistics、audit trail；
5. **Experimental Design**：offline model experiment、baselines/ablations、deployment gate、nominal closed loop、timing robustness、post-hoc diagnostics；
6. **Results**：按 H1–H4 顺序，只报告事实；
7. **Discussion**：aggregate vs active tail 机制、公平性、对直接先行工作的增量、risk-stack interpretation、limitations；
8. **Conclusion**：一句回答每个 RQ，不出现新数字；
9. **Appendix**：hyperparameters、all cells、cluster points、artifact hashes、implementation audit。

### 9.2 推荐主表

1. Dataset/split/active coverage；
2. Model parameter、output freedom、training budget；
3. B0/B1/CV/CA/train-mean offline comparison；
4. Matched B2-M/T1 与 B2-D/T2 comparison；
5. Aggregate vs response-active calibration；
6. In-loop prediction by offset and active state；
7. Closed-loop paired effects with all five raw cluster values；
8. Native collision taxonomy and complete-case sensitivity。

### 9.3 推荐主图

- prediction→calibration→risk→solver→supervisor→execution chain，并标出测量边界；
- parameter/performance plot，避免只按模型名称排序；
- aggregate vs active-tail prediction/calibration figure；
- Day10 same-batch B1−B0 raw cluster effects by policy/style；
- tested separation–efficiency operating points，叠加 raw init points；
- implementation/evidence audit flow。

### 9.4 Results 与 Discussion 的纪律

Results 只写：发生了什么、effect 多大、每个 init 的方向、统计不确定性。  
Discussion 再写：为什么可能发生、与文献是否一致、还有哪些替代解释。

禁止把：

- association 写成 causation；
- zero observed events 写成 zero risk；
- three tested settings 写成 complete frontier；
- top-mode coverage 写成 full distribution calibration；
- T1/T2 写成对所有 Transformers 的代表；
- B1 写成 interaction-aware model；
- policy-stack comparison 写成纯 risk-allocation effect。

---

## 10. 十个工作日执行计划

### Day A1：建立新的审计基线

- 将当前 Day14 evidence 标记为 `legacy_evidence_v1`；
- 建 issue/checklist，列出 C1–C9；
- 为 mode mapping、native collision 和 locator resolver 先写 failing tests。

**完成标准：**每个 critical defect 都有 code location、owner、acceptance criterion。

### Day A2：物理基线

- 实现 CV、CA、train-mean；
- 在冻结 test 上输出 aggregate/subgroup/init-cluster metrics；
- 生成表图和 machine-readable report。

**决策：**如果 B1 不明显优于 CV/CA，立即调整 ML claim。

### Day A3：输入与训练诊断

- B1 raster/past zero/shuffle；
- 汇总 15 runs learning curves、best epochs、parameters、latency；
- 判断是否需要 validation-only longer-budget sensitivity。

### Day A4：in-loop prediction 和 native collision

- 正式实现 160-rollout in-loop prediction analysis；
- active/inactive 分层；
- native collision actor/episode audit；
- init50 complete-case sensitivity。

### Day A5：修复证据链

- 修复 42 个 invalid locators；
- 四假设 claim matrix；
- result-value resolver；
- 更新 figures，使 raw cluster points 可见。

### Day A6：控制实现 go/no-go

- 修复 mode mapping 与 A_MIN 的实验分支；
- 跑 unit tests 和 8-arm smoke；
- 根据服务器稳定性、solver behaviour 和剩余时间选择路线 S 或 R。

### Day A7–A8：只执行已通过 gate 的工作

- 路线 S：不跑 CARLA，完成所有 disclosure、敏感性和 Results tables；
- 路线 R：运行 corrected 80-rollout nominal matrix，断点续跑，旧/new 分目录。

### Day A9：完整写作

- Related Work 25–35 篇；
- 完成 Methods/Results/Discussion；
- 删除所有 TODO；
- 加 artifact availability statement。

### Day A10：反向审稿与提交检查

- 从 abstract 中每句话反查 result ID；
- 从每张表反查 source value；
- 检查四假设术语完全一致；
- 编译最终 PDF、检查图表字体和引用；
- 做一次“最苛刻 examiner”答辩演练。

---

## 11. Distinction go/no-go checklist

只有以下全部满足，才可以把论文称为 submission-ready：

- [ ] 全文无可见 TODO、placeholder 和未定义 acronym；
- [ ] bibliography 至少覆盖四个领域，关键 claim 都有 primary sources；
- [ ] 明确对比 Bouzidi et al. 2025，不声称首次发现 open/closed-loop mismatch；
- [ ] CV、CA、train-mean baselines 完成并解释；
- [ ] B1/T 参数、适配位置、输出自由度公平性写清；
- [ ] H2–H4 使用 `not supported/not observed`，不写统计 refutation；
- [ ] mode-indexing 选择披露或 corrected rerun，不能沉默；
- [ ] A_MIN 选择 policy-stack interpretation 或统一后重跑；
- [ ] Day11 target–traffic-light collision 已进入正式 audit 和 sensitivity；
- [ ] Day9 只描述 B0/B1 deployment，不声称 T1/T2 已在线部署；
- [ ] evidence locators 可解析，values 可从 sources 自动重算；
- [ ] 主图展示 raw init points，n=5 bootstrap 不伪装成 confirmatory significance；
- [ ] aggregate 与 response-active/in-loop tail 分开报告；
- [ ] 所有 safety 词汇都区分 observed event、separation proxy 和 population risk；
- [ ] 大数据/模型有 examiner 可访问 URI 或清晰 availability statement；
- [ ] 最终 PDF 满足 TMLR 格式，方法可复现，图表在打印尺寸可读。

---

## 12. 答辩时最可能被问的问题

### “你的 Transformer 为什么没有赢？”

安全回答：它确实使用了 sequence，但 active data 很少；两个 matched pairs 的结果方向不同，且多数 runs 在 epoch cap 附近停止。因此结论不是 Transformer 无效，而是当前轻量 residual design 在冻结预算下没有一致 architecture advantage。

### “B1 不是比 Transformer 参数多很多吗？”

安全回答：是。B1 是 task-adaptation benchmark，不是 capacity-matched architecture control。Attention 的公平比较只发生在 B2-M/T1 和 B2-D/T2 两对中；论文已经按这两个层次拆开。

### “为什么不用 constant velocity？”

提交前必须补上，不能只靠口头解释。

### “你的 adaptive-risk 比较公平吗？”

若不重跑：回答它比较的是冻结 policy stacks，因为 reference-generation bound 不同，不把结果归因于 risk allocation 单一组件。  
若重跑：展示统一 A_MIN 的新 contract、hash 和结果。

### “你说是 multimodal planner，为什么 collision constraints 只用 mode 0？”

若不重跑：主动披露 legacy top-mode spatial interface，并限定贡献。  
若重跑：展示 mode-consumption audit，证明三个 modes 分别进入约束。

### “没有碰撞是否证明安全？”

不证明。只能报告指定 rollouts 中的 observed ego–target footprint count；同时披露 target–traffic-light native event。真实碰撞概率、安全保证和跨地图泛化都不在当前证据范围内。

### “你的最大原创贡献是什么？”

建议回答：

> 我的贡献不是提出一个新的通用预测器，而是在一个冻结且可审计的 give-way SMPC 系统中，把 task adaptation、matched sequence adapters、calibration 和 risk-control operating context 放进同一证据链。结果进一步定位了 aggregate gain 与 interaction-active tail failure 可以同时存在，这解释了为什么很大的总体预测提升仍不能直接推出统一规划收益。

---

## 13. 最终建议

不要从头开始新课题，也不要再把主要时间投入更大的 Transformer。当前最高收益是：

1. 补物理基线与输入诊断；
2. 正式化已经存在的 in-loop prediction logs；
3. 修复 native collision 和 evidence-value audit；
4. 精确重写 B1/Transformer、统计和 adaptive-risk 的 claim；
5. 对 mode mapping 和 A_MIN 作出透明的披露/重跑选择；
6. 把 Related Work 和 Discussion 写到真正的批判性综述水平。

执行完这些后，论文的价值不再依赖某个结果必须“正向”。它会成为一篇方法边界清楚、证据链完整、能解释负向和异质性结果、并且真正把机器学习预测与自动驾驶闭环联系起来的 dissertation。这正是比简单堆模型或挑选有利结果更接近 distinction 的地方。
