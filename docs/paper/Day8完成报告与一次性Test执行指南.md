# Day 8 完成报告与一次性 Test 执行指南

更新日期：2026-08-01

完成状态（2026-08-02）：一次性 test 已完成，`DAY8_COMPLETE.json` 为 `pass`，闭环模型保持 B1 / seed 37。最终结果见 `Day8最终Test结果与结论.md`。

## 1. 当前结论

Day 8 的 5 个模型、3 个随机种子，共 15/15 个正式训练与 validation 评价均已通过。验证证据已拉取到：

```text
docs/paper/generated/day8/final_validation/
```

validation 阶段没有访问 test。根据预注册的主要排序指标，最终闭环候选冻结为 **B1 / seed 37**。当前证据不支持“Transformer 是最佳模型”，但支持一个更细致且有论文价值的结论：

- T1 相对参数匹配的 mean-only MLP（B2-M）有稳定的小幅改善，说明时序 attention 在 mean residual 路径上具有增益；
- T2 相对参数匹配的 distributional MLP（B2-D）没有改善，说明 attention 本身不足以改善完整概率分布；
- B1 明显优于两个 Transformer，说明在当前小规模、受控 give-way 数据上，较简单的 head fine-tuning 具有更好的精度、稳定性和部署价值；
- 因此论文应报告“结构复杂度与数据/任务匹配”的负结果，而不能把 Transformer 包装成最终优解。

## 2. 最终 validation 结果

以下均为三个随机种子的中位数，模型排序使用未校准的 rollout-macro trajectory mixture NLL/step；数值越低越好。

| 排名 | 模型 | 代表 seed | rollout NLL | all ADE (m) | reactive ADE (m) | response-active ADE (m) | calibrated coverage MAE |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | B1 | 37 | 1.8606 | 0.1151 | 0.1713 | 0.5673 | 0.0881 |
| 2 | B2-D | 11 | 1.8727 | 0.2628 | 0.4052 | 0.7772 | 0.0722 |
| 3 | T2 | 23 | 1.8779 | 0.2855 | 0.4327 | 0.7795 | 0.0702 |
| 4 | T1 | 23 | 2.0088 | 0.9652 | 1.1064 | 1.4583 | 0.4586 |
| 5 | B2-M | 37 | 2.0255 | 1.0629 | 1.1798 | 1.4581 | 0.6037 |

所有 15 个模型的 calibrated invalid covariance 均为 0。B1 的三 seed 很稳定：rollout NLL 范围为 1.8603–1.8609，all ADE 范围为 0.1120–0.1189 m，reactive ADE 范围为 0.1709–0.1715 m。

Matched controls 的中位数差值为：

| 对比 | Δ rollout NLL | Δ all ADE (m) | Δ reactive ADE (m) | 判断 |
| --- | ---: | ---: | ---: | --- |
| T1 − B2-M | -0.0167 | -0.0977 | -0.0734 | T1 小幅优于 matched MLP |
| T2 − B2-D | +0.0052 | +0.0227 | +0.0274 | T2 小幅劣于 matched MLP |

`pre_response` 在 validation split 中为零样本，已按预注册规则标为 `not_applicable`，没有重定义 subset 或用其他样本替代；test split 中则有 60 个 pre-response samples，来自 4 个 rollouts、2 个 init groups。由于不同 split 的状态覆盖不均衡，subset 结果必须同时报告样本数和独立 init 数量。

## 3. 冻结和 test 协议

test 只允许执行一次，流程如下：

1. 校验 validation completion marker、summary hash、15 个训练结果与 validation 未访问 test 的声明；
2. 仅按 validation 为五个模型各冻结一个代表 seed；
3. 在第一次读取 test 前锁定闭环模型 B1 / seed 37；
4. 五个冻结模型分别评价 `all/assertive/reactive/pre_response/response_active`；
5. 只加载 validation 拟合的 temperature 和 covariance scale，严禁在 test 上 calibration；
6. test ranking 只用于最终报告，不能改变闭环模型、重训、调参或选择 checkpoint；
7. 中断后跳过已经通过 hash、split、subset 和 calibration 检查的结果，安全续跑；
8. 完成后生成 compact snapshot，不复制模型权重。

五个模型均进入一次性 test 的原因是：只测试 B1 无法报告 Transformer 与 matched MLP 的独立泛化结果；全部测试后再挑最优模型则构成 test-set selection。当前协议同时保留完整 ML 对照和无泄漏模型选择。

## 4. 服务器执行指令

先同步包含本指南所述脚本的新提交。随后在服务器执行：

```bash
cd /root/autodl-tmp/Research-Project-IMLS-day8
git pull --ff-only origin main

export DAY7_RESULTS=/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1
export DAY8_RESULTS=/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1
export PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python

nohup env \
  DAY7_RESULTS="$DAY7_RESULTS" \
  DAY8_RESULTS="$DAY8_RESULTS" \
  PYTHON_BIN="$PYTHON_BIN" \
  bash core/scripts/models/run_day8_frozen_test_once.sh \
  > "$DAY8_RESULTS/final_test_launcher.log" 2>&1 &

echo $! > "$DAY8_RESULTS/final_test_launcher.pid"
```

持续查看进度：

```bash
tail -F "$DAY8_RESULTS/final_test_v1/day8_test_runner.log"
```

服务器或进程中断后，使用完全相同的 `export`，再次执行 `nohup` 命令即可。脚本不会重复已经通过完整冻结检查的 subset，也不会覆盖异常结果。

最终完成检查：

```bash
cat "$DAY8_RESULTS/DAY8_COMPLETE.json"
cat "$DAY8_RESULTS/final_test_v1/DAY8_TEST_COMPLETE.json"
cat "$DAY8_RESULTS/final_test_v1/day8_frozen_test_snapshot.tar.gz.json"
```

只有 `DAY8_COMPLETE.json` 的 `status` 为 `pass` 才表示 Day 8 完整结束。运行完成后，应拉取以下三个文件：

```text
final_test_v1/day8_frozen_test_snapshot.tar.gz
final_test_v1/day8_frozen_test_snapshot.tar.gz.json
DAY8_COMPLETE.json
```

## 5. Day 9 输入

Day 9 只能部署已在 test 前冻结的 B1 / seed 37。test 结果无论是否出现其他模型更优，都不能改变这个选择。Day 9 首先做模型加载、calibration、prediction-control logging 和 CARLA smoke，不直接开始正式闭环矩阵。
