# Documentation Index

## Canonical

- `paper/两周_最终研究主线_数据扩展与实验执行方案.md`：唯一有效的研究主线、数据扩展、模型设计、实验矩阵、结果解释和十四天计划。
- `paper/Day1_冻结协议与服务器资产审计报告.md`：2026-07-31 的服务器数据、模型、结果、Git 和磁盘审计。
- `paper/Day2_数据审计与V2协议冻结报告.md`：V1 完整性结论、V2 feature contract、200-rollout matrix 和模型资产哈希。
- `paper/Day3_GMM评估器与校准报告.md`：共享 GMM 解码、真实 sample 等价、channel mismatch 与 B1/T0 calibration。
- `paper/Day4_V2交互数据链路与ReactiveTarget报告.md`：V2 raster/interaction contract、reactive target 和四单元 CARLA smoke。
- `paper/Day5_开发实验与Reactive参数冻结报告.md`：20-rollout development smoke 与 reactive 参数冻结。
- `paper/Day6完成与Day7执行指南.md`：200-rollout 正式数据、V2 merge/split 和模型实现结果。
- `paper/Day7完成与Day8训练执行指南.md`：Day 8 三 seed 训练与 validation 协议。
- `paper/Day8最终Test结果与结论.md`：五模型最终 test、matched controls 和假设判定。
- `paper/Day9部署与CARLA_Smoke执行指南.md`：冻结 B1/B0 在线部署、校准和机制链路 smoke。
- `paper/Day10正式闭环矩阵执行指南.md`：80-rollout held-out predictor × risk × target-style 正式闭环矩阵。
- `paper/已完成实验与证据账本.md`：已完成实验的结果路径、结论强度和不可支持的论点。

## Evidence artifacts

- `paper/generated/evidence_tables/`：历史控制实验的机器可读 CSV。
- `paper/generated/figures/`：历史控制实验的 SVG 图。
- `paper/generated/day2/`：V1 dataset audit、50-rollout manifest consolidation 和 legacy Transformer artifact manifest。
- `paper/generated/day3/`：GMM equivalence、B1/T0 validation calibration 和冻结 test reports。
- `paper/generated/day4/`：V2 输入等价和四单元单-init smoke audit。
- `paper/generated/day5/`：20-rollout smoke audit 与冻结配置。
- `paper/generated/day6/`：正式 200-rollout 数据审计与完成证据。
- `paper/generated/day7/`：V2 merge/split 和模型实现证据。
- `paper/generated/day8/`：15-run validation 与一次性冻结 test 证据。
- `paper/generated/day9/`：8-arm 冻结模型 CARLA deployment smoke、最终审计与 compact snapshot。
- `paper/generated/README.md`：这些 artifacts 的范围和使用边界。

## Architecture and runtime

- `architecture/流程图与代码映射.md`：架构图与代码映射。
- `architecture/Server_CARLA_Environment_Runbook.md`：服务器环境与 smoke gate。
- `architecture/Experiment Flow.png`、`architecture/SMPC.png`：系统架构图。

## Literature and presentation

- `literature/相关文献解读_SMPC_多模态预测_自动驾驶.md`：文献阅读笔记。
- `literature/*.pdf`：论文原文。
- `presentation/`：已有 presentation、rubric 和素材。

## Maintenance rule

- 不再新增并列的“最终指导”“行动方案”或手工复制结果表。
- 新实验决策只修改 canonical 文档。
- 新结果写入 timestamp result directory，并生成机器可读 manifest/table。
- 已被替代的一次性脚本直接删除；Git 历史承担恢复职责。
