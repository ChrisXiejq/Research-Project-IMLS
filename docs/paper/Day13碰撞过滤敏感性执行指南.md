# Day13 碰撞 rollout 过滤敏感性执行指南

> 定位：这是 Day12 collision audit 触发的 **post-hoc training-data sensitivity**，不是新的主体研究问题，也不替代原始 Day8 model selection。

## 1. 为什么需要做

Day12 确认 6 个 reactive training rollouts 存在 target–infrastructure callbacks。它们不进入 validation/test，且不涉及 ego–target collision，但 Day6 没有保存 sample timestamp 与 CARLA global frame 的 per-rollout anchor，所以无法可靠区分碰撞前后窗口。

采用最保守规则：排除这 6 个 rollout 的全部 162 个 usable training windows：

- reactive train：`162/2116 = 7.656%`；
- all train：`162/4036 = 4.014%`；
- validation/test：完全不改，必须保持 byte-identical；
- 原始 Day8 和 frozen test：保持 primary，不覆盖、不重新选择。

只补 B1 单 seed 无法回答“过滤后是否改变架构排名”，因此运行与 Day8 完全匹配的 `5 variants × 3 seeds` validation matrix。test split 不执行评估，也不用于 filtered model selection。

## 2. 冻结假设与判定

`H13-Sensitivity`：保守删除 callback-containing training rollouts 后，validation-only selected architecture 仍为 B1。

- 若仍选择 B1：原 offline architecture conclusion 对保守过滤稳健；
- 若选择其他模型：原结论对训练数据过滤敏感，必须如实降级；
- representative seed 可变化，不单独视为架构结论失败；
- 无论结果如何，都不根据 sensitivity 重新打开原 frozen test 或替换 Day10 predictor。

## 3. 已实现的复现保护

1. 从 Day12 CSV 自动读取且严格要求恰好 6 个 reactive train rollout；
2. 排除数量必须等于 Day12 上界 162，否则立即失败；
3. 重算 filtered-train interaction normalization；
4. validation/test 必须与原 Day7 byte-identical；
5. 训练矩阵继承 Day8 的 5 variants、3 seeds、epoch backup、完成标记和 stale-lock 恢复；
6. sensitivity analyzer 要求 15/15 matched runs、`test_accessed=false`；
7. 已完成 run 会跳过，服务器中断后执行同一命令即可。

## 4. 服务器同步与启动

```bash
cd /root/autodl-tmp/Research-Project-IMLS-day12
source /etc/network_turbo
git pull --ff-only origin main

export PYTHON_BIN=/root/miniconda3/bin/python
export DAY7_RESULTS=/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1
export DAY8_RESULTS=/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1
export DAY12_RESULTS=/root/autodl-tmp/results/give_way_transformer/day12/day12_evidence_freeze_v1
export DAY13_RESULTS=/root/autodl-tmp/results/give_way_transformer/day13/day13_collision_filtered_v1

mkdir -p "$DAY13_RESULTS"
nohup bash core/scripts/models/run_day13_collision_filtered_sensitivity.sh \
  > "$DAY13_RESULTS/day13_launcher.log" 2>&1 &
echo $! > "$DAY13_RESULTS/day13_launcher.pid"
echo "Day13 PID=$(cat "$DAY13_RESULTS/day13_launcher.pid")"
```

## 5. 监控与续跑

```bash
tail -F "$DAY13_RESULTS/day13_runner.log"
```

简要状态：

```bash
ps -fp "$(cat "$DAY13_RESULTS/day13_launcher.pid")" || true
find "$DAY13_RESULTS/filtered_validation/runs" -name TRAINING_COMPLETE.json | wc -l
tail -n 100 "$DAY13_RESULTS/day13_runner.log"
```

服务器中断后，不删除任何目录，重新执行第 4 节同一条 `nohup` 命令。训练使用 epoch backup；已完成 training/evaluation artifacts 会被跳过。

## 6. 完成门

```bash
cat "$DAY13_RESULTS/filtered_day7/day13_filter_audit.json"
cat "$DAY13_RESULTS/filtered_validation/DAY8_VALIDATION_COMPLETE.json"
cat "$DAY13_RESULTS/analysis/DAY13_FILTERED_SENSITIVITY_COMPLETE.json"
cat "$DAY13_RESULTS/DAY13_COMPLETE.json"
```

必须同时满足：

- filtered train = 3,874 usable windows；excluded = 162；
- validation/test SHA 与 original Day7 一致；
- validation matrix = 15/15 runs；
- `test_accessed=false`；
- completion status = pass。

完成后只需通知我。我会拉取小型 audit/summary/CSV，判断 B1 排名是否稳健，然后进入论文数字 manifest、核心表格和图的生成，不需要拉取全部 sensitivity model weights。
