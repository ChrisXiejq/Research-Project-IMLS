# Day 9 冻结模型部署与 CARLA Smoke 执行指南

更新日期：2026-08-02

## 1. Day 9 的目标

Day 9 只验证部署和机制链路，不产生正式论文 outcome，也不允许调模型、calibration、risk policy 或 supervisor。完成后才决定 Day 10 正式矩阵能否启动。

Day 8 已选择 B1 / seed 37，而不是 Transformer。因此 Day 9 不再把失败 offline gate 的 T1/T2 部署为正式候选。Smoke 使用：

```text
predictor: B1 frozen / B0 pretrained bridge
risk: fixed medium / adaptive floor_weak
target: assertive / defensive reactive
ego init: 01（train init，仅用于 development smoke）
authority: A3 risk-owned-yield
```

共 2 × 2 × 2 = 8 个 rollouts。B0 只用于判断 Day 10 的 fine-tuning bridge 是否可执行；正式模型仍是 B1。

## 2. 本次修复的部署缺口

此前 offline evaluator 会加载 validation calibration，但 CARLA CLI 只接收 model 和 anchors，在线 `DeployMultiPath` 会静默使用 identity calibration。若不修复，Day 8 与 Day 9 不具备 deployment equivalence。

现在在线入口新增并强制审计：

- `--prediction_model_calibration`；
- calibration 必须声明 `fit_split=val`；
- calibration 内记录的 model tree hash 必须等于实际加载模型；
- model、anchors、calibration、参数和 normalization 语义写入每个 rollout 的 `prediction_deployment_manifest.json`；
- B1 必须匹配 Day 8 freeze 的 model/calibration hash；
- B0 明确使用 identity calibration，不允许误载 B1 calibration；
- SavedModel 加载失败时立即报错，不再捕获后继续运行。

B1 是两输入模型，因此 interaction normalization 对它是 `not_applicable`。共享 raster 使用 ResNet preprocessing，past states 不做额外 normalization。这不是缺失，而是 B1 的冻结输入契约。

## 3. 自动完成门

Runner 会依次检查：

1. Day 8 complete 和无 test-selection leakage；
2. B1/seed 37 model tree hash；
3. B1 validation calibration hash、参数和 anchors hash；
4. B1/B0 SavedModel 加载、GPU forward 和 GMM warm-up；
5. probability 有限、非负、和为 1；
6. covariance 有限、对称、正定；
7. 8/8 CARLA rollouts 成功；
8. 8/8 post-CARLA trajectory gate 为 PASS；
9. prediction→risk mode→solver→supervisor step-level 链路完整；
10. reactive arms 确实包含 response-active samples；
11. 无 solver exception、NaN/Inf 或 invalid covariance；
12. 输出 `DAY9_COMPLETE.json` 和 compact snapshot。

任一检查失败时不会生成 Day 9 pass 标志。

## 4. 服务器执行

以下假设工作仓库仍为：

```text
/root/autodl-tmp/Research-Project-IMLS-day8
```

先同步新提交：

```bash
cd /root/autodl-tmp/Research-Project-IMLS-day8
git pull --ff-only origin main
git log -1 --oneline
```

确认 CARLA 已在另一个终端运行：

```bash
cd /root/autodl-tmp/carla_0.9.14
./CarlaUE4.sh -RenderOffScreen -quality-level=Low
```

实验终端执行：

```bash
cd /root/autodl-tmp/Research-Project-IMLS-day8

export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python
export DAY8_RESULTS=/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1
export DAY9_RESULTS=/root/autodl-tmp/results/give_way_transformer/day9/day9_smoke_v1

export GUROBI_HOME=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi1103/linux64
export GUROBI_VERSION=110
export GRB_LICENSE_FILE=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi.lic
export LD_LIBRARY_PATH="$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}"

mkdir -p "$(dirname "$DAY9_RESULTS")"

nohup env \
  CARLA_ROOT="$CARLA_ROOT" \
  PYTHON_BIN="$PYTHON_BIN" \
  DAY8_RESULTS="$DAY8_RESULTS" \
  DAY9_RESULTS="$DAY9_RESULTS" \
  GUROBI_HOME="$GUROBI_HOME" \
  GUROBI_VERSION="$GUROBI_VERSION" \
  GRB_LICENSE_FILE="$GRB_LICENSE_FILE" \
  LD_LIBRARY_PATH="$LD_LIBRARY_PATH" \
  bash core/scripts/carla/run_day9_deployment_smoke.sh \
  > "$DAY9_RESULTS.launcher.log" 2>&1 &

echo $! > "$DAY9_RESULTS.launcher.pid"
echo "Day9 PID=$(cat "$DAY9_RESULTS.launcher.pid")"
```

如果服务器的 Gurobi 实际安装在 day8 worktree 下，应只把三个 Gurobi 路径改为真实位置，不得改其他实验参数。

## 5. 监控和续跑

持续监控：

```bash
tail -F "$DAY9_RESULTS/day9_runner.log"
```

检查完成数：

```bash
find "$DAY9_RESULTS" -name scenario_run_summary.json -type f | wc -l
```

服务器或 runner 中断时，保持完全相同的环境变量和 `DAY9_RESULTS`，重新执行同一条 `nohup` 命令。成功 rollout 会由 `--skip_completed_subruns` 跳过；冻结 contract 发生变化时脚本会拒绝续跑。

若脚本提示已有 invalid output，不要删除文件，先把日志发给我诊断。

## 6. 完成检查与回传

```bash
cat "$DAY9_RESULTS/DAY9_COMPLETE.json"
cat "$DAY9_RESULTS/day9_smoke_snapshot.tar.gz.json"
```

只有 `DAY9_COMPLETE.json` 的 `status` 为 `pass` 且 `observed_arms` 为 8，Day 9 才完成。随后通知我，我会拉取：

```text
day9_smoke_snapshot.tar.gz
day9_smoke_snapshot.tar.gz.json
DAY9_COMPLETE.json
```

并分析 B1/B0 的 predictor × risk × target-style 机制差异，冻结 Day 10 矩阵。
