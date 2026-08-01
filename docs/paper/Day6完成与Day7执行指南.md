# Day 6 完成审计与 Day 7 执行指南

状态：Day 6 正式采集与 Day 7 真实数据/model gate 均已完成并通过。Day 7 的紧凑证据已拉取到 `docs/paper/generated/day7/`。

首次真实 model gate 已完成数据 merge，但发现 TensorFlow 2.13 无法可靠恢复嵌套在自定义复合层中的
`MultiHeadAttention` 权重。修复后 MHA/LayerNorm/FFN 已展开为标准 Keras Functional graph；
服务器针对 T1 的 23 组权重复测全部完全一致，重复推理和保存/加载最大绝对差均为 0。

最终真实 gate 结果：

- 200 个 rollout 按 init 分组为 160/20/20；
- 5,037 个至少含一个有效 future label 的样本，其中 full horizon 3,237、partial horizon 1,800；
- train/val/test 可用样本分别为 4,036/506/495；
- B1、B2-M、B2-D、T1、T2 全部通过前向、反向、保存/加载和数值检查；
- B2-M/T1 trainable 参数为 77,600/86,688，相差 10.48%；
- B2-D/T2 trainable 参数为 176,096/165,728，相差 5.89%；
- 四个 adapter 的零初始化输出与 frozen base 最大绝对差均为 0；
- 五个模型的保存/加载最大绝对差均为 0；
- 四个 adapter 的 smoke covariance audit 均为 0 个 invalid matrix。

证据哈希：

```text
manifest.json                         52a1ed4c817ab5dbb160515fb581ff3a859866230267c21cd79b92bee2a3233d
day7_split_audit.json                 78713b96ff3415bab5f960889c9878ed49b53f8f08446ef60fea6e74d8c555bf
interaction_normalization_train.json  2dd054698e0ba0ca204ecc480078603fe8b958cfd3feca201f9c7ed9ffe28b9b
day7_model_smoke.json                 26086f6e85497cd1190e8383c3d167681905ee1ccecbfed421cabcfeb5cea188
```

## 1. Day 6 最终事实

正式目录：

```text
/root/autodl-tmp/results/give_way_transformer/day6/formal/day6_formal_v2_200
```

最终状态：

- `DAY6_COMPLETE.json` 存在且 `status=pass`；
- 200/200 rollout 成功；
- 四个 cell 各 50 rollout；
- 200 prediction manifests；
- 11,230 个原始 prediction samples；
- wrapper、底层采集进程和结果锁均已退出；
- 最终 audit SHA256：`5a1c111319819c7a8f87ae0ce24a9c0eadd6556881aa96afcae4f26c47910dd2`。

Day 6 原始数据约 1.6 GB，继续保留在服务器，不提交 Git。项目新增
`package_prediction_dataset_v2_day6_snapshot.py`，只打包最终合同、审计、协议、200 个
rollout summary、200 个 prediction manifest 和 batch metadata。
该紧凑快照共 428 个文件，已拉取到 `docs/paper/generated/day6/` 并在本地复核为
200 summaries、200 manifests、`status=pass`、`error_count=0`。

## 2. Day 7 数据定义

Day 7 不按 frame 随机切分。固定 grouped split：

```text
train: init 01-40 = 160 rollouts
val:   init 41-45 = 20 rollouts
test:  init 46-50 = 20 rollouts
```

同一 init 的 `S0_FIXED/S0_ADAPTIVE/S1_FIXED/S1_ADAPTIVE` 必须位于同一 split。

训练文件只写入至少一个 `future_valid_mask=1` 的样本：

- full horizon 样本完整保留；
- partial horizon 样本保留，训练必须使用 masked loss；
- zero-label 样本只进入审计计数，不进入 train/val/test JSONL；
- interaction normalization 只使用 train split 且只统计 mask=1 的 token；
- raster 仍从不可变 Day 6 目录读取，不复制第二份图片。

## 3. Day 7 模型实现

共同输入：共享 V2 raster、target past states、`6x12` interaction sequence 和 `6` 维 mask。

| 模型 | 时序编码 | Residual head |
| --- | --- | --- |
| B1 | 无 interaction adapter；只训练原 MultiPath 最终 Dense head | 原始 MultiPath head |
| B2-M | 参数匹配 MLP | mean only |
| B2-D | 参数匹配 MLP | mean + bounded distribution |
| T1 | 轻量 Transformer | mean only |
| T2 | 轻量 Transformer | mean + bounded distribution |

约束：

- frozen MultiPath base；
- residual heads 零初始化，初始输出与 base 一致；
- mean residual 使用有界 `tanh`；
- distributional head 分组修改 std parameter、orientation 和 logits；
- std parameter 绝对值有上界，GMM covariance 必须 finite、symmetric、positive definite；
- B2-M/T1 与 B2-D/T2 trainable parameter 差异必须不超过 20%；
- evaluator 和 deployment 继续共用 `multipath_gmm_utils.py`。

## 4. 服务器同步

Day 6 worktree 保留不动，建议建立新的 Day 7 worktree：

```bash
cd /root/autodl-tmp/Research-Project-IMLS
git fetch origin
git worktree add --detach \
  /root/autodl-tmp/Research-Project-IMLS-day7 \
  origin/main
```

如果 `Research-Project-IMLS-day7` 已存在，不要覆盖或删除；先检查其 `git status` 和 HEAD。

## 5. Day 7 后台执行

```bash
export DAY7_REPO=/root/autodl-tmp/Research-Project-IMLS-day7
export DAY6_RESULTS=/root/autodl-tmp/results/give_way_transformer/day6/formal/day6_formal_v2_200
export DAY7_RESULTS=/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1
export PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python

mkdir -p "$(dirname "$DAY7_RESULTS")"
cd "$DAY7_REPO"

nohup env \
  PYTHON_BIN="$PYTHON_BIN" \
  DAY6_RESULTS="$DAY6_RESULTS" \
  DAY7_RESULTS="$DAY7_RESULTS" \
  bash core/scripts/models/run_day7_prepare_and_verify.sh \
  > "$(dirname "$DAY7_RESULTS")/day7_nohup.log" 2>&1 &

echo $! > "$(dirname "$DAY7_RESULTS")/day7_launcher.pid"
echo "Day7 PID=$(cat "$(dirname "$DAY7_RESULTS")/day7_launcher.pid")"
```

不需要 CARLA，也不需要 Gurobi。脚本可断点续跑：

- merge 完成后已有 `DAY7_COMPLETE.json`，重跑不会重建；
- model smoke 完成后已有 `DAY7_MODEL_IMPLEMENTATION_COMPLETE.json`，重跑会跳过；
- stale lock 会在确认旧 PID 不存在后自动清理；
- 不覆盖不完整的正式输出目录。

## 6. 用户自行查看

```bash
tail -f /root/autodl-tmp/results/give_way_transformer/day7/day7_runner.log
```

最终完成门：

```bash
test -f "$DAY7_RESULTS/DAY7_COMPLETE.json" \
  && test -f "$DAY7_RESULTS/DAY7_MODEL_IMPLEMENTATION_COMPLETE.json" \
  && cat "$DAY7_RESULTS/DAY7_COMPLETE.json" \
  && cat "$DAY7_RESULTS/DAY7_MODEL_IMPLEMENTATION_COMPLETE.json"
```

需要保留并在执行后拉回的紧凑结果：

```text
DAY7_COMPLETE.json
DAY7_MODEL_IMPLEMENTATION_COMPLETE.json
manifest.json
day7_split_audit.json
interaction_normalization_train.json
day7_model_smoke.json
```

`all/train/val/test.jsonl` 和 Day 6 rasters 是后续 Day 8 训练输入，保留服务器，不提交 Git。

## 7. Day 7 gate 含义

只有以下全部通过才进入 Day 8：

1. 200 rollouts 按 160/20/20 grouped split；
2. 没有 init 或 rollout leakage；
3. zero-label 样本被排除，partial labels 使用 masked loss；
4. train-only normalization 完整；
5. 四种 adapter 对真实 V2 sample 前向为 finite；
6. 零初始化与 frozen base 等价；
7. 合成小样本 loss 能下降；
8. 模型保存/加载输出等价；
9. covariance audit 通过；
10. MLP/Transformer 参数匹配在 20% 内。

以上十项在正式服务器产物中全部通过。这里的 synthetic overfit 只证明实现可训练，不能作为 Transformer 优于 MLP 或 B1 的性能证据；模型优劣必须由 Day 8 的独立 validation 与一次性 test 评价决定。
