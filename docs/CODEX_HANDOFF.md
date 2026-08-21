# Research-Project-IMLS — Codex 权威交接文档

最后更新：2026-08-22  
实验仓库基线：`9c6d51790d59aac33f9fa85168b256805b3ec5ee`  
论文仓库基线：`d0ead9326ddc29a10bbb1049d65e1efa7998e2ad`

本文件供下一位 Codex 接手整个毕业设计。它说明研究问题、实验过程、冻结结果、证据入口、当前缺口和下一步顺序。若本文件与机器生成结果冲突，以 completion marker、CSV/JSON 和生成代码为准；不得手工修改生成证据以迎合正文。

## 1. 五分钟接手摘要

项目已经完成主要机器学习训练、corrected R3 闭环矩阵和 SF4 supervisor-authority 机制实验。**目前不计划新增大型 CARLA 仿真。**工作重心已经从实验执行转为：

1. 重建 post-SF4 证据与论文审计链；
2. 利用现有 raw telemetry 完成剩余机制审计；
3. 把实验完整、准确地写入最终 TMLR/UCL dissertation；
4. 完成引用、英文、格式、图表、PDF 和 rubric 审计。

论文唯一主线是：

> 在受控 CARLA give-way 场景中，简单任务适配可以显著改善离线运动预测，但更复杂的时序模型、离线预测提升和 adaptive risk 都不会自动产生一致的闭环收益；预测、校准、risk allocation、SMPC 求解/fallback 和 supervisor authority 共同决定最终执行行为。

机器学习是主轴。控制与 supervisor 不是第二篇并列论文，而是用于检验机器学习改进是否真正具有系统价值的下游机制链。

当前冻结结论：

- H1：支持；B1 显著优于 B0。
- H2：不支持测试配置下的 Transformer 一致增益。
- H3：只有条件性转化；2/8 个 policy × style 单元同时改善完成与 separation。
- H4：adaptive risk 不普遍支配 fixed risk；3/12 个预定义比较满足 dominance。
- SF4：supervisor authority 对两种 risk 都有巨大的共同作用，但没有证据表明它选择性抹平 adaptive–fixed-medium 的差异。

## 2. 接手后先读什么

按以下顺序阅读，不要从历史 Day 文档或随机生成目录开始：

1. `README.md`：仓库范围和代码入口；
2. `docs/paper/THESIS_EVIDENCE_GUIDE.md`：权威科学主线、H1–H4 和证据位置；
3. 本文件：跨仓库工作状态、风险和下一步；
4. `docs/architecture/Server_CARLA_Environment_Runbook.md`：只有在确需服务器复现时阅读；
5. 相邻论文仓库 `../Jiaqi Xie Dissertation/PROJECT_STATUS.md`；
6. 相邻论文仓库 `../Jiaqi Xie Dissertation/WRITING_GUIDE_ZH.md`；
7. 最终提交正文 `../Jiaqi Xie Dissertation/main.tex`。

不要把以下内容当作当前权威入口：

- `docs/paper/generated/paper_assets_v1/`：pre-SF4 旧资产；
- Day10–Day13 的旧闭环结果：只作 provenance/secondary diagnostics；
- `docs/dissertation/latex/`：内部生成稿，仅供证据脚本兼容，不是提交稿；
- M1/W1 中标记为 `partial_pre_sf4` 的 receipt：它们明确不是最终 post-SF4 release gate。

## 3. 两个仓库的职责

### 3.1 实验仓库

路径：`Research-Project-IMLS`

包含：

- CARLA、prediction、SMPC、supervisor 实现；
- 数据/模型协议和分析脚本；
- 机器生成的 JSON、CSV、TeX、图表与完成标记；
- 文献、架构图和服务器 runbook。

当前状态：

- 分支：`main`；
- HEAD：`9c6d51790d59aac33f9fa85168b256805b3ec5ee`；
- `main` 有 300 个可审计提交；
- 工作树在本次交接文档修改前为 clean；
- 仓库历史已清理无用本地分支，体积约 588 MB；
- 不需要重写 `main` 历史，也不要 force-push。

### 3.2 论文仓库

路径：`../Jiaqi Xie Dissertation`

唯一权威提交源：

- `main.tex`：英文正文；
- `main.bib`：参考文献；
- `figures/`：正文图；
- `main.pdf`：最近一次阅读副本；
- `PROJECT_STATUS.md`：论文仓库交接；
- `WRITING_GUIDE_ZH.md`：中文版科学主线。

当前论文仓库 HEAD：`d0ead9326ddc29a10bbb1049d65e1efa7998e2ad`。

不要在 `Research-Project-IMLS/docs/dissertation/latex/` 中继续写最终论文。需要改提交内容时，只改相邻论文仓库。

## 4. 研究是怎样一步步形成的

下面的 Day/R/SF 标签只用于工程交接，最终论文不得按这些标签叙述。

### 4.1 起点：adaptive risk 与 fixed risk

项目最初希望证明 adaptive risk 在 give-way 场景优于 fixed risk。初步闭环轨迹非常接近，并且共享 supervisor 可能主导最终行为。这使原始的单一正向命题无法直接成立，也暴露出三个更深问题：

- predictor 是否足够适配当前交互任务；
- 更强 predictor 是否真的改变规划；
- risk、solver/fallback 和 supervisor 如何调节这种变化。

### 4.2 Day1–Day5：协议、数据和行为条件冻结

这一阶段完成：

- 旧实验与配置审计；
- rollout-disjoint split 和数据 schema；
- B0/B1 evaluator/deployment 解码一致性；
- give-way interaction 数据管线；
- assertive/reactive target style 与场景条件冻结；
- 原生碰撞记录和模型/配置 provenance gate。

重要遗产：后续比较不是从零开始的新任务，而是对原 adaptive-vs-fixed 研究的逐层诊断。

### 4.3 Day6：正式 prediction dataset

完成 200 个 Town05 give-way 数据采集 rollouts，并按初始化组做互斥划分：

```text
160 train + 20 validation + 20 frozen test
```

预测 horizon 为 2 s。不得把重叠窗口视为独立总体样本；主聚合单位是 rollout/init group。

当前本地 `core/results/` 只保留相关 prediction dataset collection。其他早期本地视频、调参和 debug 结果已经移到仓库外隔离归档；论文证据不依赖这些本地旧目录。

### 4.4 Day7–Day8：模型实现、训练和冻结测试

模型族：

- B0：预训练 MultiPath control；
- B1：任务适配 final prediction head；
- B2-M：mean-scope MLP residual control；
- B2-D：distribution-scope MLP residual control；
- T1：与 B2-M 匹配作用域的 Transformer residual；
- T2：与 B2-D 匹配作用域的 Transformer residual。

五个可训练 variants 使用 seeds 11、23、37。模型选择只用 validation rollout-macro NLL，随后只做一次 frozen-test evaluation。

训练与模型比较的重要边界：

- MLP–Transformer 配对控制了冻结基座、数据、split、seed 和输出作用域；
- B1 与 residual adapters 不是严格参数匹配；
- B1 约 1.034M trainable parameters，adapters 约 77k–176k；
- 10/15 训练运行在 20 epoch 上限选中 checkpoint；
- 因此 H2 只能否定“测试配置下的一致增量价值”，不能否定 Transformer 一般能力。

### 4.5 Day9–Day13：部署、初始闭环和鲁棒性审计

这一阶段完成：

- 冻结真实输入的 deployment smoke；
- 初始闭环矩阵与分析；
- B0 offline 对照；
- Transformer zero/shuffle context ablations；
- reactive activity 和 offset 审计；
- collision attribution、timing synthesis；
- collision-filtered sensitivity。

这些结果建立了方法和诊断基础，但早期闭环实现后来被 corrected R3 取代。不得把旧 Day10–Day13 与 R3 混为同一个 primary population，也不得合并样本量。

### 4.6 S0–G1：Distinction protocol hardening

完成并冻结：

- baseline/config/model hashes；
- 物理基线；
- raster/history input ablations；
- training budget audit；
- in-loop prediction manipulation；
- split balance/leakage audit；
- collision/geometry metric boundary；
- prospective H1–H4 analysis contract。

### 4.7 R1–R3：corrected closed-loop formal matrix

R1/R2 用于 corrected implementation 和 pilot/hardening。最终 primary closed-loop evidence 是 R3：

```text
2 predictors × 4 risk policies × 2 target styles × 5 paired init groups
= 80 rollouts
```

风险策略：fixed aggressive、fixed medium、fixed conservative、adaptive。  
目标风格：assertive、reactive。  
主要连续结果：event-clock completion time、minimum physical footprint separation。  
二元 guards：native collision、physical overlap、yield failure、completion failure。

R3 80/80 完成；R4 被有意设为 `not_run`，避免 outcome-selected 扩样。

### 4.8 W1/Q1：pre-SF4 论文与科学审计

W1 生成论文表图，Q1 完成当时的科学 gate。但其 completion receipts 仍写明 `pre-sf4` 或 `human release inputs pending`。它们不是最终论文 release gate，下一步必须重建 post-SF4 证据链。

### 4.9 SF1–SF4：逐条回应 supervisor feedback

老师提出四个主要问题：

1. 车辆 approach/stop/release 过于保守；
2. adaptive risk 成本高但收益不明显，应分析 infeasibility；
3. 旧 fine-tuning “0.98%→100%” 结果可疑；
4. 共享 supervisor 可能掩盖 adaptive/fixed 差异。

已完成的回应：

- 旧 0.98%→100% 指标已撤回；它是 mode-ranking/matching statistic，不是轨迹预测准确率。
- B0/B1 重新以 rollout-macro NLL/ADE/FDE 和 paired init evidence 评估。
- solver audit 区分 factual attempts、raw return status、controller acceptance、fallback 和 bypass。
- SF4 正式切换完整 supervisor behavioural application authority，而非只改标签。
- SF4 完成 80 个 preregistered rollouts。

仍需诚实保留的缺口：

- 老师第 1 条没有被一套完整、平衡的 approach/stop/release inferential table 彻底闭环。当前 canonical behavioural table 中很多事件时钟因 complete-block 缺失而为 `--`；不得把 provisional 或不完整时序数字写成正式结论。
- 老师第 2 条已经通过 SF4 的 factual solver accounting 显著加强，但 `supervisor_feedback_v1/02_cost_feasibility` 的旧 marker 仍是 `partial_raw_required`。最终论文应引用更新后的 SF4 raw-status 证据，不要宣称旧 marker 已自动变为 complete。
- 老师第 4 条得到机制检验，但 authority-off 大面积失败形成 floor saturation。因此 near-zero DID 是“没有观察到选择性 masking 的证据”，不是 risk policies 等价的证明。

## 5. 冻结实验结果

### 5.1 H1：task adaptation

Frozen-test rollout-macro：

| Model | NLL (nats/step) | ADE (m) | FDE (m) |
|---|---:|---:|---:|
| B0 | 2.170712 | 1.282672 | 2.644311 |
| B1 | 1.857094 | 0.099658 | 0.120895 |

五个 held-out initialization groups 的 NLL/ADE/FDE 方向均支持 B1。B1 也优于 constant velocity、clipped constant acceleration 和 train-mean route 三个物理基线。

边界：response-active tail 很小，且暴露 calibration 风险。不能把总体改善写成对所有关键交互尾部的普遍改善。

### 5.2 H2：Transformer incremental value

关键 NLL：

- B2-M：2.024409；T1：2.003746；
- B2-D：1.872789；T2：1.878148；
- B1：1.857094。

T1 略优于 matched MLP，T2 略差于 matched MLP，两者都没有超过 B1。Zero/shuffle sequence ablations 会使 Transformer 变差，说明时序分支实际被使用；负向结果不是实现完全失效。

### 5.3 H3：offline-to-closed-loop translation

- 40/40 B0–B1 in-loop paired checks 保持 B1 预测优势；
- 只有 2/8 个 risk-policy × target-style 单元同时满足更快 completion 且 separation 不差；
- 因此 offline gain 的闭环价值是条件性的。

重要混杂边界：B1 deployment stack 使用 validation-frozen calibration，B0 不使用，因此 H3 是完整 B0-stack vs B1-stack effect，不是纯 weights-only causal effect。

### 5.4 H4：adaptive risk dominance

- adaptive risk 仅在 3/12 个预定义 predictor × style × fixed-comparator contrasts 中满足 empirical Pareto dominance；
- R3 80/80 没有观测到 native collision、physical collision、yield failure 或 completion failure；
- 这些零事件产生 binary ceiling，不是安全证明；主要区分指标是 continuous separation 和 completion；
- adaptive risk 是 context-dependent operating point，不是普适赢家。

### 5.5 SF4：supervisor behavioural authority

设计：

```text
B1 × {adaptive, fixed medium}
× {authority on, authority off}
× {assertive, reactive}
× 10 paired init groups
= 80 rollouts
```

结果：

- authority on：40/40 completion success，0 yield failure，0 adverse collision；
- authority off：0/40 completion success，38/40 yield failure，21/40 adverse physical collision，其中 16/40 有 native collision callback；
- authority on-minus-off failure-penalised completion：adaptive −18.630 s，fixed medium −18.650 s；
- adaptive-minus-fixed completion DID：+0.020 s，95% cluster-bootstrap interval [−0.260, +0.337] s；
- separation DID：−0.007 m，interval [−0.047, +0.027] m。

正确解释：supervisor authority 对两种风险策略都产生巨大共同作用；实验没有支持“supervisor 选择性抹平一个本来很大的 adaptive 优势”。

错误解释：

- 不能写 adaptive 与 fixed 等价；
- 不能写 supervisor 是所有相似轨迹的唯一原因；
- 不能把 authority-off collapse 当作正常 operating regime；
- 不能把 supervisor 当成一个单一末端刹车开关。它是 reference shaping、linearisation/heading cost、rule bypass、post-solver action、release/recovery 和 next-step history 等行为权限的 bundle。

### 5.6 Solver/fallback

SF4 factual accounting：

- 18,552 factual SMPC attempts；
- 17,822 commands accepted；
- 730 `INF_OR_UNBD` 后进入 fallback/nonaccepted path；
- authority on：7,695 attempts，7,582 accepted，113 fallback；
- authority off：10,857 attempts，10,240 accepted，617 fallback。

“controller accepted” 不等于数学上的严格 optimizer feasibility；必须保留 raw return status。Rollout completion 也不能替代 solver-status accounting。

服务器诊断显示 authority-on 下 adaptive 相对 fixed-medium 增加 ego-policy P50 wall time 约 15.152 ms。该时间包含 risk allocation、optimisation 和 supervision，仅适用于该服务器，不是 end-to-end real-time guarantee。

## 6. 消融实验地图

接手者写论文时必须围绕“固定什么、改变什么、测量什么”组织，不要只是列模型名。

| 层级 | 固定内容 | 改变内容 | 回答的问题 |
|---|---|---|---|
| Protocol | 场景、split、评估代码 | 无 treatment；做 hash/leakage/balance audit | 结果是否可追溯 |
| Task adaptation | B0 representation、anchors、输入、数据 | B0 vs B1 head adaptation | 简单任务适配是否有效 |
| Physical baselines | test trajectories/horizon | CV、CA、train-mean route | 学习结果是否超过简单运动学 |
| Input ablation | B1 权重和 test set | raster/history mean/shuffle | 模型使用了什么输入 |
| Calibration | model/test protocol | raw vs validation-fitted；aggregate vs tail | 概率收益是否可信 |
| Architecture | frozen B0、data、split、seeds、paired scope | MLP vs Transformer residual | 时序复杂度是否有额外价值 |
| Sequence | frozen T1/T2 | zero/shuffle tokens | Transformer 是否真正使用序列 |
| Robustness | pipeline | filtered data、budget/capacity | 排序是否由污染或预算导致 |
| R3 predictor | risk/style/init/controller/supervisor | full B0 stack vs full B1 stack | 离线收益是否进入闭环 |
| R3 risk | predictor/style/init/controller/supervisor | adaptive vs fixed frontier | adaptive 是否普适占优 |
| Target moderator | 其他 treatment | assertive vs reactive | 交互风格是否调节效果 |
| SF4 authority | B1/risk interface/SMPC/init/style | full authority on vs off | supervisor 是否具有行为权威 |
| Mechanism | 已有 telemetry | 按 solver/fallback/outcome 分组 | 为什么产生失败或保守行为 |

现有消融足够支持限定后的主线，但不足以证明跨地图泛化、Transformer 一般优劣、individual supervisor channel causality、formal SMPC safety 或 adaptive/fixed equivalence。

## 7. 权威证据和代码入口

### 7.1 R3 primary evidence

```text
docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/
docs/paper/generated/distinction_v1/10_four_hypothesis_evidence/
```

优先文件：

```text
.../r3_corrected_formal_v3/R3_COMPLETE.json
.../r3_corrected_formal_v3/analysis/R3_ANALYSIS_COMPLETE.json
.../r3_corrected_formal_v3/analysis/r3_analysis_summary.json
.../r3_final/synthesis/table_final_hypothesis_verdicts.csv
.../10_four_hypothesis_evidence/M1_EVIDENCE_MANIFEST.json
```

### 7.2 Supporting ML evidence

```text
docs/paper/generated/distinction_v1/01_physical_baselines/
docs/paper/generated/distinction_v1/02_input_ablations/
docs/paper/generated/distinction_v1/03_training_budget/
docs/paper/generated/distinction_v1/04_in_loop_prediction/
docs/paper/generated/distinction_v1/06_split_balance/
docs/paper/generated/day8/final_validation/
docs/paper/generated/day8/final_test/
docs/paper/generated/day10/gaps/context_ablation/
docs/paper/generated/day13/
```

### 7.3 SF4 and supervisor feedback

```text
docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/SF4_COMPLETE.json
docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/analysis/SF4_ANALYSIS_COMPLETE.json
docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/analysis/sf4_rollout_outcomes.csv
docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/analysis/sf4_primary_and_direct_effects.tex
docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/analysis/sf4_controller_acceptance_and_solver_status.tex
docs/paper/generated/supervisor_feedback_v1/02_cost_feasibility/
docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/
```

### 7.4 主要实现

```text
core/scripts/carla/run_all_scenarios.py
core/scripts/carla/scenarios/run_intersection_scenario.py
core/scripts/carla/policies/smpc_agent.py
core/scripts/carla/policies/supervisor_action_filter.py
core/scripts/models/multipath_gmm_utils.py
core/scripts/models/prediction_input_contract.py
core/scripts/models/interaction_sequence.py
core/scripts/models/evaluate_multipath_model_on_dataset.py
core/scripts/models/analyze_r3_corrected_formal.py
core/scripts/models/analyze_sf4_supervisor_behavioural_authority.py
core/scripts/models/audit_supervisor_finetune_feedback.py
core/scripts/models/build_r3_paper_synthesis.py
core/scripts/models/build_m1_evidence_package.py
core/scripts/models/build_supervisor_feedback_paper_integration.py
```

若数字需要修正，修改 generator/analysis code 并重新生成，不要直接改 generated CSV/JSON/TeX。

## 8. 当前论文状态

`../Jiaqi Xie Dissertation/main.tex` 目前约 1,048 行、7,139 个粗略单词，已经包含 Abstract、Introduction、Literature Review、Problem Formulation、Methodology、Experimental Design、Results and Analysis、Conclusion 和 Reproducibility Appendix。SF4 已进入实验设计、结果和结论。

这是一份完整 working draft，但不是可直接提交的 Distinction final。

### 8.1 已做好的部分

- H1–H4 的实验逻辑和主要数值已经进入正文；
- R3 manipulation、translation 和 risk frontier 已写；
- SF4 direct authority effects、DID 和 solver accounting 已写；
- 三张主要结果图已经进入提交仓库；
- TMLR style 文件和编译入口已建立；
- 论文与实验仓库职责已经分开。

### 8.2 下一位 Codex 必须优先处理的缺陷

1. **Abstract/Introduction 英文明显未完成**：已知有 `confucted`、`futhur`、`beyong`、主谓一致、时态和术语错误，不能只改三个拼写后就宣告完成。
2. **主线标题尚未冻结**：当前标题 `A Controlled Give-Way Intersection Study With Prediction and Risk Allocation` 比核心贡献更泛。优先考虑 `From Prediction Accuracy to Executed Behaviour: Task Adaptation in a Risk-Aware CARLA Give-Way Stack`。
3. **缺少独立 Discussion section**：当前解释主要混在 Results 中，rubric 所要求的影响、边界、替代解释和更广泛意义没有形成独立章节。
4. **Related Work 偏薄**：`main.bib` 只有 11 个 entries，其中 3 个是模板遗留且正文未用；有效领域引用覆盖不足。必须扩展并做批判性综合，不是堆引用。
5. **post-SF4 evidence release chain 未重建**：M1/W1 多个 marker 仍为 `partial_pre_sf4`。应修改 generator 并生成新的 post-SF4 completion/audit，而不是手改 marker。
6. **老师第 1 条反馈未完全闭环**：canonical approach/stop/release 表很多 endpoint 因观测不完整而缺失。需要从已有 raw telemetry 做严谨离线审计；若仍无法形成完整比较，就在论文中明确 limitation，不要伪造“已解决”。
7. **SF4 解释需增加 floor-saturation 限制**：authority-off 0/40 完成、21/40 adverse collision。Near-zero DID 不能写成 equivalence 或完全无 masking。
8. **H3 必须标记 stack-level effect**：B1 含 validation-frozen calibration，B0 不含，不能写成纯 weights-only effect。
9. **图表覆盖不足**：目前正文只有三张结果图；至少考虑补一张系统因果链图和一张 SF4 authority/fallback 图。
10. **PDF 需要重新构建与视觉审计**：不要假设现存 `main.pdf` 与最终源文件、引用和图表完全同步。

## 9. 下一步执行顺序

### P0：科学证据闭环

1. 在两个仓库分别记录 clean status 和 HEAD；
2. 逐项比对正文数字与 canonical CSV/JSON；
3. 更新 evidence generators，使 M1/W1 或新的 final marker 明确包含 SF4；
4. 用已有 SF4 raw telemetry 完成 failure timeline 与 conservative-behaviour availability audit；
5. 生成 claim-boundary audit：每个强结论必须对应证据、estimand 和 limitation；
6. 只有发现真实数据/实现错误会改变 headline result 时，才考虑补跑 CARLA。

### P1：论文重构与写作

1. 冻结标题和一句话中心论点；
2. 重写 Abstract 和 Introduction，使 prediction-to-execution translation 成为唯一主线；
3. 扩充 Related Work，覆盖 multimodal prediction/calibration、Transformer interaction models、task-informed prediction evaluation、risk-aware/chance-constrained SMPC、recursive feasibility/fallback 和 safety supervisors；
4. 将 Results 中的解释分离：Results 报证据，独立 Discussion 解释机制、负向结果、替代解释和应用边界；
5. 增加 architecture/coupling 图、SF4 authority/fallback 图及必要表格；
6. 逐章按 UCL rubric 检查 research gap、critical literature、reproducibility、controls/statistics 和 discussion impact。

### P2：提交级验证

1. 全文英文 copy-edit；
2. 引用 key 与 bibliography 完整性检查；
3. TMLR 格式、页边距、匿名化和 UCL 要求检查；
4. `tectonic main.tex --keep-logs`；
5. 逐页检查 PDF：溢出、孤行、图表字体、caption、引用、页码；
6. 最终数字冻结后再提交 `main.pdf`；
7. 在论文仓库更新 `PROJECT_STATUS.md`，记录最终提交 commit。

## 10. 服务器协作原则

用户已经明确要求：

- 不要通过 `scp`、编辑器同步或其他方式直接向服务器推送文件；
- 本地修改经验证并获授权后 commit/push，用户在服务器 `git pull`；
- 服务器执行命令由 Codex 提供，用户负责启动和持续监控；
- 只有用户明确要求检查/拉取时，Codex 才读取服务器状态或结果；
- 不在仓库、文档、脚本或日志中写密码、token、license。

服务器拉取 Git 前可能需要：

```bash
source /etc/network_turbo
```

CARLA 正式场景必须是 Town05。Town10HD_Opt 是错误地图；此前曾因启动脚本、旧进程和 `load_world` 不生效反复出错。若未来确需复现，必须先确认：

```text
map = Carla/Maps/Town05
experiment actors = 0
CasADi conic Gurobi plugin = True
```

服务器环境与命令只以 `docs/architecture/Server_CARLA_Environment_Runbook.md` 为入口，不从聊天历史复制过时命令。

## 11. 本地环境与仓库清理状态

为缩小仓库，本地已执行可恢复清理：

- 33 个旧 `core/results` 目录、旧视频/debug outputs、可重建 `.venv-precarla`、缓存和非-best 临时模型被移到仓库外隔离目录；
- 正式 prediction dataset、B0 和 B1-best 模型保留；
- 废弃本地 Git 分支 `backup-before-clean-large-file` 已删除；
- 该分支中的 2.25 GB `core/results.zip` 历史对象已回收；
- `main` commit hashes 和 tags 未改变；
- `git fsck --full` 通过。

隔离目录位于：

```text
/Users/bytedance/my/Dissertation/Research-Project-IMLS_cleanup_archive_20260822
```

它不属于仓库，也不是论文依赖。不要在代码或论文中引用这个绝对路径。

注意：`docs/paper/THESIS_EVIDENCE_GUIDE.md` 中的复现命令仍使用 `.venv-precarla/bin/python`，但该可重建虚拟环境目前不在仓库目录。执行脚本前必须按实际任务创建隔离环境或选择兼容 Python；不要因为路径缺失而修改机器证据。

## 12. 禁止事项

- 不新增另一套 Day-numbered narrative 文档；更新本文件、`THESIS_EVIDENCE_GUIDE.md` 或论文仓库的 `PROJECT_STATUS.md`。
- 不把 legacy Day10–Day13 闭环数据与 corrected R3 合并。
- 不手改 generated evidence 的数字或 status。
- 不为追求正向故事改假设、选择性扩样或隐藏 H2/H3/H4 的负向结果。
- 不声称 Transformer 普遍无效、adaptive risk 无用或 supervisor 是唯一主因。
- 不把零观测碰撞写成安全证明。
- 不把 controller acceptance 写成严格 optimiser feasibility。
- 不把 SF4 near-zero DID 写成 statistical equivalence。
- 不把 supervisor-off 当作只关闭一个 safety filter；它关闭的是完整行为权限 bundle。
- 不在没有明确科学缺口的情况下再启动大型 CARLA matrix。
- 不重写 `main` Git 历史或 force-push。

## 13. 下一位 Codex 的首个工作回合

建议第一回合只完成以下任务：

1. 读取本文件和两个权威状态文件；
2. 确认两个仓库没有未归属修改；
3. 对 `main.tex` 做一次不改数值的结构/语言 audit；
4. 设计 post-SF4 final evidence marker 和 failure/behaviour offline audit；
5. 向用户报告：哪些任务只需本地完成，哪些可能需要服务器，但不要自动开启新仿真；
6. 经用户同意后，按 P0 → P1 → P2 顺序推进。

最终完成定义不是“代码能跑”或“PDF 能编译”，而是：

- H1–H4/SF4 每个正文数字都能定位到 canonical evidence；
- 所有 claim 都有正确边界；
- supervisor 四条反馈得到回答或明确 limitation；
- 独立 Discussion、critical literature、reproducibility 和 PDF presentation 达到 rubric 要求；
- 不再需要大型 CARLA 实验；
- 最终论文仓库有清晰、可复现的提交版本。

