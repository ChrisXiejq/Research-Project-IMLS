# Day 7 完成审计与 Day 8 Validation-only 训练执行指南

状态：Day 7 已完成并通过；Day 8 第一阶段正在服务器执行，支持从已完成的 variant/seed 和 validation 子集断点续跑。

2026-08-01 首次正式运行发现 validation 的 `pre_response` 定义没有任何 full-horizon 样本。实测覆盖为：assertive full 150、reactive full 176，其中 response-active 24、released 152；pre-response 为 0。B1 seed 11 的训练及 all/assertive/reactive 评价均已通过，失败只发生在空子集评价。

修复后的规则是：all/assertive/reactive 为必需子集；pre-response/response-active 为可选诊断子集。可选子集为空时写入带原因和零样本数的 `status=not_applicable` 证据，不重新定义该子集、不伪造指标，也不把它用于模型排序。该事实作为数据时序覆盖限制写入最终汇总。

中期 8-run 审计进一步发现 V1 evaluator 的 `source_subrun` 键会把 S0/S1 同名 rollout 合并。V2 evaluator 改用 `cell_id::source_subrun` 识别 20 个真实 validation rollouts，并单独用 `ego_init_id` 报告 5 个 paired clustering units。旧的逐样本指标仍有效，但所有 calibration 和 rollout-macro 指标会自动按 V2 重算；已有模型无需重训。详细中期结果见 `docs/paper/Day8中期模型性能审计_8runs.md`。

## 1. Day 7 结论

Day 7 两个完成门均为 `pass`。真实数据事实为：

- 200 个 rollout，按 init grouped split 为 train/val/test = 160/20/20；
- 5,037 个可用 masked-label 样本，train/val/test = 4,036/506/495；
- full horizon 3,237，partial horizon 1,800；
- 同一 init 的四个实验 cell 完全共置，split 间无 init leakage；
- normalization 只使用 train split；
- B1、B2-M、B2-D、T1、T2 全部通过真实样本前向、合成小样本反向、保存/加载和 covariance audit；
- B2-M/T1 参数差异 10.48%，B2-D/T2 参数差异 5.89%，均小于预注册的 20% 上限。

Day 7 只证明五种实现“正确且可训练”，不证明 Transformer 性能更好。特别是 synthetic overfit loss 不能进入论文性能对比。

## 2. Day 8 第一阶段做什么

固定矩阵：

```text
B1 / B2-M / B2-D / T1 / T2
× seeds 11 / 23 / 37
= 15 个独立训练运行
```

每个运行：

1. 只读 Day 7 固定 train/val JSONL；
2. train 同时保留 full 与 partial horizon，并使用 masked MultiPath NLL；
3. 使用 validation masked NLL 保存最佳 checkpoint；
4. server 中断后由 Keras epoch backup 恢复 optimizer、epoch 和权重；
5. 最佳权重恢复后保存可部署 SavedModel；
6. validation 上拟合 temperature 与 covariance scale；
7. 输出 all、assertive、reactive、pre-response、response-active 五组 validation 指标；
8. 生成三 seed 架构汇总和代表 seed；
9. 不读取 test 指标。

其中可选诊断子集若在固定 validation 中没有 full-horizon 样本，会输出 `not_applicable`；这不会中止其余正式矩阵。

正式矩阵前会自动运行一个 `T2, seed=11, 32 train/16 val` 的单 epoch preflight，并用 8 个 validation 样本验证 SavedModel 恢复、四输入 evaluator 和 calibration 路径。preflight 通过后才进入 15 个正式运行；preflight 数据不进入正式汇总。

架构排序的第一指标固定为：

```text
三 seed 的 validation rollout-macro uncalibrated trajectory mixture NLL/step 中位数
```

第二指标依次为 reactive top-1 ADE 和 pre-response top-1 ADE。校准参数会在 validation 上拟合并报告，但不用于架构排名，避免不同模型各自在同一 validation 上校准后再反向影响模型选择。代表 seed 取最接近该架构三 seed 中位数的 seed，不取偶然最好的 seed。

只有在本阶段汇总完成并冻结 `variant + representative seed + calibration` 后，才执行一次性 test。脚本在本阶段不会访问 test 指标。

## 3. 断点续跑设计

- 每个 `variant/seed` 独立写入结果目录；
- `BackupAndRestore` 每个 epoch 保存可恢复状态；
- `best.weights.h5` 只按 validation loss 更新；
- `TRAINING_COMPLETE.json` 最后写入；存在且为 `pass` 的运行会跳过；
- validation 子集 JSON 逐个检查，已有合法 `pass` 文件会跳过；
- runner 有 PID lock；进程不存在时会清理 stale lock；
- `day8_run_contract.json` 阻止 epochs、batch size、learning rate、输入路径等在续跑时漂移；
- 最终完成标志为 `DAY8_VALIDATION_COMPLETE.json`；
- 自动生成不含 SavedModel/weights 的紧凑证据包 `day8_validation_snapshot.tar.gz`。
- 每次正式训练和 validation evaluator 前强制检查 TensorFlow GPU；GPU 不可见时停止并保留 checkpoint，禁止静默退回 CPU。

## 4. 同步并建立 Day 8 worktree

先在本地 push 包含 Day 8 脚本的提交，然后在服务器执行：

```bash
cd /root/autodl-tmp/Research-Project-IMLS
git fetch origin
git worktree add --detach \
  /root/autodl-tmp/Research-Project-IMLS-day8 \
  origin/main
```

如果 Day 8 worktree 已存在，不要删除，改为：

```bash
cd /root/autodl-tmp/Research-Project-IMLS-day8
git status --short
git fetch origin
git checkout --detach origin/main
```

只有 `git status --short` 没有未提交内容时才执行最后一行。

## 5. 启动命令

```bash
export DAY8_REPO=/root/autodl-tmp/Research-Project-IMLS-day8
export DAY7_RESULTS=/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1
export DAY8_RESULTS=/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1
export PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python

mkdir -p "$(dirname "$DAY8_RESULTS")"
cd "$DAY8_REPO"

nohup env \
  PYTHON_BIN="$PYTHON_BIN" \
  DAY7_RESULTS="$DAY7_RESULTS" \
  DAY8_RESULTS="$DAY8_RESULTS" \
  bash core/scripts/models/run_day8_train_and_validate.sh \
  > "$(dirname "$DAY8_RESULTS")/day8_nohup.log" 2>&1 &

echo $! > "$(dirname "$DAY8_RESULTS")/day8_launcher.pid"
echo "Day8 PID=$(cat "$(dirname "$DAY8_RESULTS")/day8_launcher.pid")"
```

Day 8 不需要启动 CARLA 或 Gurobi。

## 6. 查看状态与续跑

查看日志：

```bash
tail -f /root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1/day8_runner.log
```

查看完成数：

```bash
find /root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1/runs \
  -name TRAINING_COMPLETE.json | wc -l
```

服务器中断后，重新执行第 5 节完全相同的 `nohup` 命令。不要更改 result path、epochs、batch size、learning rate 或 patience。

最终检查：

```bash
export DAY8_RESULTS=/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1
test -f "$DAY8_RESULTS/DAY8_VALIDATION_COMPLETE.json" \
  && cat "$DAY8_RESULTS/DAY8_VALIDATION_COMPLETE.json"

test -f "$DAY8_RESULTS/day8_validation_snapshot.tar.gz.json" \
  && cat "$DAY8_RESULTS/day8_validation_snapshot.tar.gz.json"
```

运行完成后只需把以上两个输出发回。随后拉取紧凑快照，复核三 seed 稳定性、matched MLP/Transformer 对照和各行为子集，冻结模型选择，再生成只允许运行一次的 test 脚本。
