# Dissertation paper workspace

The canonical TMLR-format dissertation source is maintained in
[`../dissertation/latex/`](../dissertation/latex/). This directory remains the
source of frozen methods, evidence, figures and audit records used by that
manuscript.

> 当前阶段：**Day14 已完成，实验与证据冻结结束，进入正式论文写作。**
>
> 最后审计：14/14 hard checks PASS；无需新增正式实验；8 项方法边界必须在论文中明确。

## Canonical documents

本目录只保留四份人工维护的论文文档：

1. [`01_研究问题与实验方法.md`](01_研究问题与实验方法.md)：最终标题、研究问题、假设、数据、模型、闭环矩阵与统计方法；
2. [`02_最终结果与审计结论.md`](02_最终结果与审计结论.md)：最终结果、假设判定、方法审计、缺陷与结论边界；
3. [`03_论文写作路线与章节大纲.md`](03_论文写作路线与章节大纲.md)：按证据链组织的详细章节结构和写作顺序；
4. [`04_复现与证据资产索引.md`](04_复现与证据资产索引.md)：机器证据、表格、图片、生成命令与引用规则。

机器生成内容统一位于 [`generated/`](generated/README.md)，其中论文写作唯一数字入口是 [`generated/paper_assets_v1/`](generated/paper_assets_v1/README.md)。

## Frozen rules

- 不再根据 test 或 closed-loop 结果重新选模型；
- 不再寻找能让 adaptive risk “获胜”的特定场景；
- 不把 simulator steps 或 prediction windows 当作独立实验样本；
- 不声称 Transformer、adaptive risk 或 B1 在场景外普遍最优；
- 每个定量主张必须来自 `paper_results_manifest.json` 的 result ID 或 canonical table；
- 原 Day1–Day14 运行日志式文档已从活跃目录移除，可从 Git 历史提交 `558b9e8` 恢复。
