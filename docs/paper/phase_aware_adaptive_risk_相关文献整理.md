# Phase-Aware Adaptive Risk SMPC 相关文献整理

## 1. 整体结论

当前论文方向可以放在以下三条研究脉络的交叉点上：

```text
risk-aware / chance-constrained MPC
+ rule-aware / regulation-aware autonomous driving
+ safety supervisor / fallback / shielding
= rule-aware supervisor + phase-aware adaptive-risk SMPC
```

这说明当前方法不是孤立设计，而是有比较清晰的文献支撑：

- risk-aware MPC 文献说明：自动驾驶交互场景存在预测不确定性，不能只用 deterministic collision constraints，需要用 chance constraints、CVaR 或其他 risk-aware formulation。
- rule-aware planning 文献说明：无信号交叉口不是单纯避障问题，还涉及 right-of-way、yield rule 和交通法规合规。
- supervisor / shielding 文献说明：安全关键系统通常不会直接执行优化器或学习模型的原始输出，而会在外层加入 runtime safety layer / fallback / arbiter。

因此，你当前论文可以这样定位：

```text
本文不是单独提出一个 rule-based controller，也不是单独提出一个 stochastic MPC。
本文把交通规则相位引入 SMPC 风险分配：
target clearance 前提高 chance constraint 保守性；
target clearance 后降低保守性；
同时用 rule-aware supervisor 保证最终交通规则和 footprint safety。
```

## 2. 与本文最相关的文献分类

### 2.1 Risk-Aware / Chance-Constrained MPC

这类文献用于支撑：

- 为什么需要 stochastic MPC。
- 为什么需要 chance constraints。
- 为什么 risk allocation 可以随场景变化。
- 为什么固定风险可能过于僵硬。

### 2.2 Rule-Aware / Regulation-Aware Planning

这类文献用于支撑：

- 自动驾驶规划不只是几何避障，还要遵守交通规则。
- right-of-way / yield rule 应显式进入 decision making 或 planning。
- 交通规则可以作为 rulebook、logical specification、cost 或 supervisor 进入系统。

### 2.3 Safety Supervisor / Fallback / Shielding

这类文献用于支撑：

- 外层 supervisor 覆盖 planner 输出是合理的安全架构。
- safety fallback 不是实验作弊，而是安全关键自动驾驶系统的常见设计。
- 你的论文需要区分 solver nominal layer 和 final applied control layer。

## 3. 核心文献清单

| # | 文献 | 方向 | 与本文关系 | 建议优先级 |
| --- | --- | --- | --- | --- |
| 1 | Kai Ren et al., *Safe Chance-constrained Model Predictive Control under Gaussian Mixture Model Uncertainty*, 2024. <https://arxiv.org/html/2401.03799v1> | chance-constrained MPC, GMM uncertainty | 与当前 SMPC + multimodal prediction 最接近，可作为 stochastic MPC 和 GMM chance constraints 的核心基础。 | 必读 |
| 2 | Surya Soman, Mario Zanon, Alberto Bemporad, *Learning-Based Stochastic Model Predictive Control for Autonomous Driving at Uncontrolled Intersections*, IEEE T-ITS, 2025. <https://xplorestaging.ieee.org/document/10803909> | stochastic MPC, uncontrolled intersection | 非常贴近无信号交叉口场景，证明 stochastic MPC 用于 uncontrolled intersection 是合理方向。 | 必读 |
| 3 | Luyao Zhang et al., *An Efficient Risk-aware Branch MPC for Automated Driving that is Robust to Uncertain Vehicle Behaviors*, 2024. <https://arxiv.org/html/2403.18695v1> | risk-aware MPC, unsignalized intersection | 明确讨论 unsignalized intersection 和 uncertain vehicle behavior，可支撑根据交互风险调整保守性的思路。 | 必读 |
| 4 | Filipe Marques Barbosa, Johan Lofberg, *Stochastic Model Predictive Control with Online Risk Allocation and Feedback Gain Selection*, 2026. <https://arxiv.org/html/2604.04602v1> | online risk allocation | 直接支撑“risk allocation 不应固定，应该随系统状态变化”的理论动机。 | 必读 |
| 5 | Astghik Hakobyan, Gyeong Chan Kim, Insoon Yang, *Risk-Aware Motion Planning and Control Using CVaR-Constrained Optimization*, IEEE RA-L, 2019. <https://xplorestaging.ieee.org/document/8767973> | CVaR, risk-aware planning | 可用于说明风险不仅是 collision/no collision，而是可以调节的保守性指标。 | 高 |
| 6 | Oscar de Groot et al., *Scenario-based motion planning with bounded probability of collision*, IJRR, 2025. <https://journals.sagepub.com/doi/10.1177/02783649251315203> | bounded collision probability, Safe Horizon MPC | 支撑使用 probabilistic safety / chance constraint 来评价动态障碍物风险。 | 高 |
| 7 | Siyuan Li, Chengyuan Liu, Wen-hua Chen, *Hierarchical Decision-Making under Uncertainty: A Hybrid MDP and Chance-Constrained MPC Approach*, 2026. <https://arxiv.org/html/2603.17634v1> | hierarchical decision + chance-constrained MPC | 支撑“高层交互决策 + 低层 MPC 风险约束”的分层架构。 | 高 |
| 8 | Zekun Xing et al., *Branch-Stochastic Model Predictive Control for Motion Planning under Multi-Modal Uncertainty with Scenario Clustering*, 2026. <https://arxiv.org/html/2605.22600v1> | branch SMPC, multimodal uncertainty | 支撑多模态预测和不确定行为下的 SMPC 设计。 | 中高 |
| 9 | Shuqi Wang et al., *Chance-Constrained Neural MPC under Uncontrollable Agents via Sequential Convex Programming*, 2026. <https://arxiv.org/html/2504.03293v3> | uncontrollable agents, neural MPC | 支撑“其他交通参与者是 uncontrollable stochastic agents”的问题建模。 | 中高 |
| 10 | Xu Han et al., *Traffic Regulation-aware Path Planning with Regulation Databases and Vision-Language Models*, 2025. <https://arxiv.org/html/2503.09024> | regulation-aware planning | 支撑规划系统需要显式考虑 traffic law / regulation compliance。 | 高 |
| 11 | Keqi Shu et al., *Decision Making in Urban Traffic: A Game Theoretic Approach for Autonomous Vehicles Adhering to Traffic Rules*, IEEE T-ITS, 2025. <https://xplorestaging.ieee.org/document/10954275> | traffic-rule-aware decision making | 强调 right-of-way 和 traffic rules 在 urban interaction 中的重要性，可支撑 give-way supervisor。 | 必读 |
| 12 | Yanliang Huang et al., *Predictive Traffic Rule Compliance using Reinforcement Learning*, 2025. <https://arxiv.org/html/2503.22925v2> | predictive rule compliance | 支撑“提前预测规则违反，而不是等违规后再修正”的思路。 | 中高 |
| 13 | Kumar Manas, Mert Keser, Alois Knoll, *Integrating Legal and Logical Specifications in Perception, Prediction, and Planning for Automated Driving: A Survey of Methods*, 2025. <https://arxiv.org/html/2510.25386v1/> | legal/logical specs survey | 适合作为 Related Work 开头综述，说明 rule-aware / legal-compliant driving 是研究热点。 | 必读 |
| 14 | Kevin Kai-Chun Chang et al., *ScenicRules: An Autonomous Driving Benchmark with Multi-Objective Specifications and Abstract Scenarios*, 2026. <https://arxiv.org/html/2602.16073v2> | rulebook benchmark, prioritized objectives | 支撑 collision safety、traffic rules、efficiency 是有优先级的多目标问题。 | 高 |
| 15 | Matteo Penlington, Alessandro Zanardi, Emilio Frazzoli, *Optimization of Rulebooks via Asymptotically Representing Lexicographic Hierarchies for Autonomous Vehicles*, 2024. <https://arxiv.org/html/2409.11199v1> | rulebook, lexicographic hierarchy | 支撑你的 supervisor 优先级：安全和让行规则高于效率。 | 高 |
| 16 | Daniel Bogdoll et al., *Informed Reinforcement Learning for Situation-Aware Traffic Rule Exceptions*, 2024. <https://arxiv.org/html/2402.04168> | situation-aware rulebook | 支撑规则执行需要随场景相位变化，与 pre-clearance / post-clearance 很契合。 | 高 |
| 17 | Pengfei Lin et al., *eRSS-RAMP: A Rule-Adherence Motion Planner Based on Extended Responsibility-Sensitive Safety for Autonomous Driving*, 2024. <https://arxiv.org/html/2409.02503> | RSS, rule-adherence planner | 支撑 right-of-way、责任、安全距离等 rule-aware 约束。 | 高 |
| 18 | Chuanyun Fu et al., *Automatic Driving Passage Strategies for Signal-Free Pedestrian Crosswalks Using an Improved Responsibility-Sensitive Safety Model*, 2025. <https://onlinelibrary.wiley.com/doi/full/10.1155/atr/1037773> | signal-free conflict, RSS | 虽然是 pedestrian crosswalk，但同样是 signal-free conflict，可支撑无信号冲突区安全通行策略。 | 中 |
| 19 | Matt Vitelli et al., *SafetyNet: Safe Planning for Real-World Self-Driving Vehicles Using Machine-Learned Policies*, ICRA, 2022. <https://dl.acm.org/doi/10.1109/ICRA46639.2022.9811576> | fallback layer, safety checks | 非常适合支撑 supervisor：复杂 planner 外面加 rule-based fallback 是合理工程架构。 | 必读 |
| 20 | Piotr Spieker, Nick Le Large, Martin Lauer, *Better Safe Than Sorry: Enhancing Arbitration Graphs for Safe and Robust Autonomous Decision-Making*, 2026. <https://arxiv.org/html/2411.10170> | fallback layers, safe arbitration | 支撑最终执行命令前需要 verification / fallback layer。 | 高 |
| 21 | Pierre Haritz, David Wanke, Thomas Liebig, *Enhancing Safety for Autonomous Agents in Partly Concealed Urban Traffic Environments Through Representation-Based Shielding*, 2024. <https://arxiv.org/html/2407.04343v1/> | shielding, unsafe action override | 与你的 supervisor override 很像：agent 输出 action 后，shield 在危险时覆盖为 safe action。 | 高 |
| 22 | C. A. J. Hanselaar et al., *The Safety Shell: An Architecture to Handle Functional Insufficiencies in Automated Driving*, 2023. <https://ar5iv.labs.arxiv.org/html/2311.08413> | safety shell, arbiter, fallback | 支撑 safety shell / arbitration layer 是自动驾驶系统处理功能不足的常见架构。 | 高 |

## 4. 最推荐优先阅读的 8 篇

如果时间有限，建议优先读下面 8 篇，并在论文 Related Work 中重点引用：

1. Ren et al., 2024, *Safe Chance-constrained MPC under GMM Uncertainty*
2. Soman et al., 2025, *Learning-Based SMPC at Uncontrolled Intersections*
3. Zhang et al., 2024, *Risk-aware Branch MPC*
4. Barbosa and Lofberg, 2026, *Online Risk Allocation*
5. Han et al., 2025, *Traffic Regulation-aware Path Planning*
6. Shu et al., 2025, *Urban Traffic Decision Making Adhering to Traffic Rules*
7. Vitelli et al., 2022, *SafetyNet*
8. Lin et al., 2024, *eRSS-RAMP*

这 8 篇基本覆盖：

```text
SMPC / chance constraints
+ uncontrolled intersections
+ adaptive / online risk allocation
+ traffic-rule-aware planning
+ safety fallback layer
```

## 5. 可以怎样写 Related Work

### 5.1 Risk-Aware and Chance-Constrained Planning

可写思路：

```text
Autonomous driving in interactive scenarios requires explicitly accounting for prediction uncertainty. Chance-constrained MPC and related risk-aware formulations have been widely used to bound collision probability while avoiding the excessive conservatism of worst-case robust planning. Prior works have considered Gaussian mixture uncertainty, multi-modal prediction, CVaR-based safety risk, and online risk allocation. However, many existing formulations apply risk constraints globally or according to uncertainty models, while the traffic-rule phase of an unsignalised give-way interaction is not explicitly used to schedule risk conservatism.
```

对应引用：

- Ren et al., 2024
- Soman et al., 2025
- Zhang et al., 2024
- Barbosa and Lofberg, 2026
- Hakobyan et al., 2019
- de Groot et al., 2025

中文写法：

```text
交互式自动驾驶场景中，其他交通参与者未来行为具有显著不确定性。Chance-constrained MPC 和 risk-aware planning 通过允许受限概率的约束违反，在安全性和保守性之间取得折中。已有研究分别从 GMM 不确定性、多模态预测、CVaR 风险度量、在线风险分配等角度展开，但多数方法并未显式利用无信号让行场景中的 target-clearance phase 来动态调度风险保守程度。
```

### 5.2 Rule-Aware and Regulation-Aware Driving

可写思路：

```text
Urban driving cannot be formulated as pure collision avoidance, since right-of-way and traffic-rule compliance strongly constrain acceptable behaviours. Recent studies encode traffic regulations through rulebooks, logical specifications, regulation databases, or game-theoretic right-of-way models. These works motivate the use of a rule-aware layer in give-way intersections, where the ego vehicle must yield to a priority vehicle before entering the conflict zone.
```

对应引用：

- Han et al., 2025
- Shu et al., 2025
- Huang et al., 2025
- Manas et al., 2025
- ScenicRules, 2026
- Penlington et al., 2024
- Bogdoll et al., 2024

中文写法：

```text
城市自动驾驶规划不能只被建模为几何避障问题。尤其在无信号交叉口中，right-of-way 和 yield rule 决定了车辆行为是否合法、可解释和安全。已有研究通过 rulebook、形式化逻辑规范、交通法规数据库和博弈论模型等方式将规则合规引入 planning 或 decision making。这些工作支持本文在 give-way 场景中引入 rule-aware supervisor，用于保证 EV 在目标车清空冲突区前不会抢占优先路权。
```

### 5.3 Safety Supervisor, Fallback, and Runtime Shielding

可写思路：

```text
For safety-critical autonomous driving, it is common to separate nominal planning from runtime safety assurance. Several architectures use safety shields, fallback layers, arbitration graphs, or safety shells to verify planned actions and override unsafe commands. This supports the design choice in this work: the adaptive-risk SMPC shapes nominal interaction-aware planning, while a rule-aware supervisor guarantees final safety and traffic-rule compliance.
```

对应引用：

- SafetyNet, 2022
- Better Safe Than Sorry, 2026
- Haritz et al., 2024
- Safety Shell, 2023
- eRSS-RAMP, 2024

中文写法：

```text
在安全关键自动驾驶系统中，将 nominal planner 与 runtime safety assurance 分离是一种常见架构。已有研究使用 safety shield、fallback layer、arbitration graph 或 safety shell 对 planner 输出进行验证，并在危险情况下覆盖为安全动作。因此，本文保留 rule-aware supervisor 并不削弱 adaptive risk 的意义；相反，它使优化层风险调节和最终安全保障可以被分别解释和评估。
```

## 6. 本文相对于已有工作的创新点

可以写成：

```text
Existing risk-aware MPC methods mainly focus on uncertainty-aware collision avoidance or reducing global conservatism, while rule-aware methods often encode traffic regulations as hard constraints, rulebooks, or supervisory logic. This work connects these two directions by introducing a phase-aware adaptive risk allocation mechanism for an unsignalised give-way intersection. The proposed method increases chance-constraint conservatism before the priority target vehicle clears the conflict zone and relaxes the risk after clearance, while a rule-aware supervisor guarantees final traffic-rule safety.
```

中文版本：

```text
已有 risk-aware MPC 研究主要关注不确定性下的碰撞风险约束和整体保守性降低；已有 rule-aware planning 研究则更多将交通规则表示为硬约束、rulebook 或 supervisor。本文的区别在于将二者结合：在无信号让行交叉口中，把 target clearance 前后的交互相位显式映射为 SMPC chance constraint 的风险保守程度，使车辆在冲突前更保守、冲突解除后更放松，同时保留 rule-aware supervisor 保证最终交通规则安全。
```

## 7. 与当前实验结果的对应关系

当前实验可以用文献支撑如下：

| 当前实验设计 | 可支撑文献方向 | 解释 |
| --- | --- | --- |
| `smpc_var_risk` vs `smpc_fixed_risk` | risk allocation / chance-constrained MPC | 对照固定风险和自适应风险，说明 risk allocation 的动态性。 |
| pre-clearance floor | rule-aware + risk-aware | 目标车尚未清空冲突区时，give-way rule 要求 EV 更保守。 |
| post-clearance relaxation | reducing conservatism | 目标车清空后继续固定高保守性会影响效率，因此 adaptive risk 应放松。 |
| rule-aware supervisor | shielding / fallback / safety shell | 最终控制用 supervisor 保证 footprint safety 和交通规则合规。 |
| nominal vs final control 分析 | planner vs safety layer separation | 区分优化层贡献和安全兜底贡献，避免过度声称。 |
| risk-by-conflict-distance diagnostics | interpretable risk scheduling | 用 phase bucket 展示 adaptive risk 的机制，而不仅看最终轨迹。 |

## 8. 论文中建议避免的表述

不建议写：

```text
adaptive risk alone guarantees safe yielding
```

原因：

- 你的系统中 supervisor 仍然对 final control 起重要作用。
- 文献上 safety shield / fallback 是合理架构，但必须承认其贡献。

不建议写：

```text
adaptive risk is universally safer than fixed risk in final trajectory metrics
```

原因：

- 当前 10-init 数据显示 var/fixed 最终 safety 指标接近。
- adaptive risk 的优势主要体现在 solver risk layer 和 nominal control layer。

建议写：

```text
adaptive risk shapes the nominal interaction-aware planning behaviour, while the rule-aware supervisor guarantees final traffic-rule and footprint safety.
```

中文建议：

```text
adaptive risk 主要改变优化层的名义交互行为和 chance constraint 保守程度；rule-aware supervisor 则保证最终执行层面的交通规则和 footprint safety。
```

## 9. 可以加入论文 Related Work 的段落草稿

```text
Recent studies on autonomous driving motion planning increasingly emphasize the need to account for both uncertainty and rule compliance. Chance-constrained and risk-aware MPC methods have been proposed to handle uncertain future behaviours of surrounding agents while avoiding the excessive conservatism of deterministic robust planning. In particular, stochastic MPC under Gaussian mixture uncertainty and risk-aware branch MPC demonstrate the value of incorporating multimodal predictions into the planning optimization. Separately, regulation-aware and rulebook-based planning methods show that urban driving decisions must satisfy right-of-way and traffic-law constraints, rather than merely avoid geometric collisions. For safety-critical deployment, runtime shields, safety shells, and fallback layers are commonly used to verify or override nominal planner outputs. Motivated by these three lines of work, this dissertation proposes a phase-aware adaptive-risk SMPC framework for an unsignalised give-way intersection. The adaptive-risk layer schedules chance-constraint conservatism according to target-clearance phases, while a rule-aware supervisor ensures final rule compliance and footprint safety.
```

中文版本：

```text
近年来，自动驾驶运动规划研究逐渐强调不确定性处理和交通规则合规的结合。Chance-constrained MPC 与 risk-aware MPC 方法通过显式建模周围交通参与者未来行为的不确定性，在安全性和保守性之间取得折中；其中基于 GMM 不确定性和多模态预测的随机 MPC 方法表明，将预测不确定性纳入优化问题是可行且必要的。另一方面，regulation-aware planning 和 rulebook-based planning 研究说明，城市驾驶决策不能仅以几何避障为目标，还必须满足 right-of-way 和 traffic-law constraints。对于安全关键系统，runtime shield、safety shell 和 fallback layer 也常被用于验证或覆盖 nominal planner 的输出。受这些研究启发，本文提出面向无信号让行交叉口的 phase-aware adaptive-risk SMPC 框架：adaptive-risk 层根据 target-clearance phase 调度 chance constraint 保守程度，而 rule-aware supervisor 保证最终执行层面的交通规则合规和 footprint safety。
```

## 10. 后续建议

建议下一步做三件事：

1. 把必读 8 篇下载成 PDF，放入 `docs/literature/` 或 Zotero。
2. 在论文大纲的 Related Work 章节中按三类文献组织，而不是按年份堆叠。
3. 50-init 结果完成后，在 Results / Discussion 中明确引用 safety supervisor 文献，解释为什么 final trajectory 差异小但 solver risk layer 差异有意义。

