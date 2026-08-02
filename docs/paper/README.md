# Paper workspace

本目录保留以下 canonical 内容：

1. `两周_最终研究主线_数据扩展与实验执行方案.md`：唯一 canonical 计划；
2. `Day1_冻结协议与服务器资产审计报告.md`：协议与服务器资产冻结；
3. `Day2_数据审计与V2协议冻结报告.md`：旧数据审计、V2 schema 与 200-rollout matrix；
4. `Day3_GMM评估器与校准报告.md`：deployment-equivalent evaluator、输入契约和 calibration；
5. `Day4_V2交互数据链路与ReactiveTarget报告.md`：V2 输入链、时序交互特征和 reactive target；
6. `Day5_开发实验与Reactive参数冻结报告.md`：20-rollout 开发实验、19-gate 行为审计、云端目录规范与 frozen config；
7. `Day6_正式200Rollout采集运行指南.md`：断点续跑、配置漂移保护、服务器命令和完成标志；
8. `Day7完成与Day8训练执行指南.md`、`Day8最终Test结果与结论.md`：模型训练和最终 offline 证据；
9. `Day9部署与CARLA_Smoke执行指南.md`：冻结模型的在线部署与 smoke；
10. `Day10正式闭环矩阵执行指南.md`：B1/B0 × fixed frontier/adaptive × held-out target-style 正式矩阵；
11. `Day10正式闭环结果与结论.md`：80-rollout paired analysis、假设判定与论文主张边界；
12. `Day10后缺口补齐与Day11执行指南.md`：B0 offline bridge、Transformer context ablation 与 ±3 m timing-shift robustness；
13. `Gap2_B0冻结离线对照结果.md`：B0/B1 同口径离线比较与 response-active calibration 限制；
14. `Gap3_Transformer交互序列诊断结果.md`：T1/T2 zero/shuffle input ablation 与机制结论；
15. `Day11时序偏移稳健性结果与最终论文定位.md`：±3 m closed-loop robustness、init-cluster inference 与最终论文论点；
16. `Day11后论文级实验审计与Day12至Day14执行方案.md`：论文级证据审计、剩余缺口、Day12–Day14 收尾和写作方案；
17. `Day12论文级证据冻结执行指南.md`：collision attribution、Day10 cluster 修正、三水平 timing synthesis 与资产备份命令；
18. `Day13碰撞过滤敏感性执行指南.md`：训练集保守过滤、5 模型 × 3 seed validation-only sensitivity 与断点续跑；
19. `已完成实验与证据账本.md` 与 `generated/`：已完成证据。

论文正文尚未进入最终写作阶段，因此不保留会迅速失效的 Results draft 或重复的 Markdown 表格。正式 Results/Discussion 将在模型与闭环实验冻结后从机器可读证据生成。
