# Documentation Index

## Dissertation — canonical

- `paper/README.md`：当前状态与唯一文档入口；
- `paper/01_研究问题与实验方法.md`：RQs、假设、数据、模型、闭环矩阵和统计；
- `paper/02_最终结果与审计结论.md`：Day14 最终结果、hard audit 与 limitations；
- `paper/03_论文写作路线与章节大纲.md`：论文各章结构和写作顺序；
- `paper/04_复现与证据资产索引.md`：机器证据、表图与复现命令。

## Evidence artifacts

- `paper/generated/paper_assets_v1/`：论文唯一数字、表格和图片包；
- `paper/generated/final_audit/`：跨 Day6–Day14 最终审计；
- `paper/generated/day2/`–`day13/`：各阶段 canonical JSON/CSV evidence；
- `paper/generated/README.md`：生成资产范围和使用边界。

大型 snapshots 和旧 preliminary tables/figures 不再保存在活跃目录；从 Git 历史或 Day12 offsite backup 恢复。

## Architecture and runtime

- `architecture/流程图与代码映射.md`：架构图与代码映射；
- `architecture/Server_CARLA_Environment_Runbook.md`：服务器环境与 smoke gate；
- `architecture/Experiment Flow.png`、`architecture/SMPC.png`：系统架构图。

## Literature and presentation

- `literature/相关文献解读_SMPC_多模态预测_自动驾驶.md`：现有文献笔记；
- `literature/*.pdf`：论文原文；
- `presentation/`：presentation、rubric 和素材。

## Maintenance rule

- 不再新增按 Day 编号的运行/结论文档；
- 实验方法、结果审计、写作方案和资产索引分别只维护一份；
- 所有论文数字来自 `paper_results_manifest.json` 或 canonical tables；
- 服务器结果必须先生成机器完成门，再进入论文资产包；
- Git 历史和验证过的 offsite backup 承担恢复职责。
