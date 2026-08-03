# Day13 结果与论文数字 Manifest

> 状态：2026-08-02 完成。Day13 server gate、论文数字 Manifest 和 8 张 canonical tables 均为 `pass`。

## 1. Day13 回答了什么

Day12 发现 6 个 reactive training rollouts 含 target–infrastructure callback。因为原始采集没有保存可将 callback frame 精确对齐到 prediction window 的 anchor，Day13 使用最保守处理：删除这些 rollout 的全部 162 个 usable training windows，但保持 validation/test byte-identical。

重新训练与 Day8 完全相同的 5 个 variants × 3 个 seeds 后：

| 指标 | 原始 Day8 | Day13 filtered | 判定 |
| --- | ---: | ---: | --- |
| train usable windows | 4036 | 3874 | 排除 162（4.0139%） |
| validation runs | 15/15 | 15/15 | matched matrix |
| selected architecture | B1 | B1 | 稳定 |
| architecture ranking | B1 > B2-D > T2 > T1 > B2-M | B1 > B2-D > T2 > T1 > B2-M | 完全不变 |
| B1 median validation macro NLL | 1.86055 | 1.86218 | paired median Δ +0.00132 |
| B1 reactive ADE paired median Δ | — | +0.00318 m | 很小的负向变化 |
| test accessed | 否 | 否 | selection/test separation 保持 |

结论：callback-containing training rollouts 没有决定 B1 的架构选择。representative seed 从 37 变为 11 是 seed-level 变化，不是 architecture-level instability。Day13 是 post-hoc sensitivity；原始 Day8 validation selection、frozen test 和 Day10/Day11 closed loop 仍是 primary evidence。

## 2. 唯一论文数字入口

生成命令：

```bash
python3 core/scripts/models/build_paper_results_manifest.py
```

输出目录：

```text
docs/paper/generated/paper_assets_v1/
```

完成门：

- `PAPER_TABLES_COMPLETE.json`: `status=pass`；
- 10 个被实际引用的机器证据源；
- 210 个稳定 result IDs；
- 8 张 canonical CSV tables；
- Manifest SHA-256：以完成门中的 `manifest_sha256` 为准。

每个 result ID 保存：数值、metric、unit、source file、source SHA-256、source locator、filter、aggregation unit 和 evidence role。论文正文中的数值主张必须引用 result ID 或 canonical table row，不能从旧 Markdown 手抄。

## 3. 八张核心表的用途

1. `table01_dataset_split_counts.csv`：数据量、rollout split 和有效窗口；
2. `table02_validation_5models_3seeds.csv`：无 test leakage 的 5×3 模型选择；
3. `table03_frozen_test_and_b0_control.csv`：一次性 frozen test 与 pretrained B0 bridge；
4. `table04_calibration_aggregate_vs_response_tail.csv`：aggregate calibration 与 interaction-tail failure；
5. `table05_day10_predictor_risk_frontier.csv`：nominal closed-loop safety–efficiency frontier；
6. `table06_timing_robustness_key_contrasts.csv`：±3 m timing moderation、cluster CI 与 exact p；
7. `table07_hypothesis_evidence_verdicts.csv`：H1–H8 的论点、稳定证据 ID、判定与边界；
8. `table08_threats_to_validity.csv`：论文必须主动陈述的剩余限制与 mitigation。

Markdown 预览 `paper_tables.md` 由生成器自动产生，不能手工改数字。

## 4. 当前最终叙事

最稳健的论文论点不是“Transformer 或 adaptive risk 全面更好”，而是：

> 在受控 give-way 交互中，任务适配能显著改善同分布轨迹预测，但这种离线改善不会自动转化为统一闭环收益；其效果受到 risk policy、arrival timing、solver 和 supervisor 的共同调节。简单适配 B1 优于所测试的 Transformer variants，而 adaptive risk 是安全—效率 frontier 上的一个条件性方案，不是对 fixed frontier 的普遍支配者。

这条叙事同时保留了项目从 planning/adaptive-risk 出发、转向模型改造、再回到 coupled closed-loop evaluation 的完整发展过程，也允许负向假设成为研究贡献，而不是把不支持的结果隐藏掉。

## 5. 写作纪律

- Day8 original/frozen test、Day10 nominal、Day11 timing shift 是 primary；Day13 只标注 sensitivity；
- 统计独立单位是 5 个 ego-init clusters，不是 simulator steps 或 windows；
- exact p 在 5 clusters 下最小双侧值为 0.0625，不能声称传统 `p<0.05` 显著；
- `0 collision` 写成 observed count/gate result，不能写成零碰撞概率；
- T1/T2 ablation 支持“使用 sequence input”，不支持“学到因果 interaction”；
- aggregate calibration 改善不能外推到仅 15 windows 的 response-active tail；
- 不用 Day13 filtered validation 重新选择 test model，也不替换已冻结闭环 predictor。

## 6. 下一步

1. 8 张 canonical figures 已生成，包含 SVG 与 PNG；
2. Results 章节骨架和英文草稿见 `Day14论文写作证据包与Results草稿.md`；
3. H1–H8 已映射到稳定 result IDs、表格、图片和 claim boundary；
4. `PAPER_EVIDENCE_PACKAGE_COMPLETE.json` 已执行数字引用与来源完整性审计。
