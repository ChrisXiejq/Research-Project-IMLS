# Historical evidence artifacts

这里保存研究转向模型优化之前的控制实验 CSV 与 SVG：

- supervisor ablation；
- v11/v12 baseline progression；
- target-speed replication；
- A1 arrival-gap；
- A2 phase ablation；
- A3 risk-owned-yield；
- predictor sanity；
- solver infeasibility。

这些文件是 historical/preliminary evidence，不是未来 V2 interaction dataset 或正式 Transformer 实验的输出。

`day2/` 保存旧 prediction dataset 的全量完整性审计、50 个 rollout manifests 的合并副本，以及 legacy Transformer best checkpoint 的哈希 manifest。它们是 Day 2 gate 的机器可读证据。

`day3/` 保存 synthetic/real-sample evaluator-deployment equivalence、B1/T0 validation-only calibration 参数，以及修正 raster channel contract 后的一次性 test reports。

`day4/` 保存 V2 raster/interaction online-offline equivalence，以及 S0/S1 × fixed/adaptive 单-init CARLA smoke audit。

`day5/` 保存 init01–05 四单元 20-rollout 的 19-gate 完整冻结审计，以及覆盖模型、行为参数、runner/scenario/tuning/init 文件哈希的 frozen collection config。云端对应路径为 `/root/autodl-tmp/results/give_way_transformer/day5/final/`。

解释和论文 claim 以：

```text
../已完成实验与证据账本.md
../Day2_数据审计与V2协议冻结报告.md
../Day3_GMM评估器与校准报告.md
../Day4_V2交互数据链路与ReactiveTarget报告.md
../Day5_开发实验与Reactive参数冻结报告.md
../两周_最终研究主线_数据扩展与实验执行方案.md
```

为准。不要直接根据单个 CSV/figure 扩大结论。
