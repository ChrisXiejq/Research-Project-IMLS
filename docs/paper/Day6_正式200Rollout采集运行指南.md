# Day 6 正式 200-rollout 采集运行指南

状态：脚本已实现并通过本地 preflight/resume 正向测试、服务器空数据集负向审计测试和 shell/Python 语法检查。未启动正式 CARLA 采集。

## 1. 正式入口

```text
core/scripts/carla/run_day6_formal_prediction_dataset_v2.sh
```

它保留 Day 5 已冻结的底层 runner，额外提供：

1. 固定的 50 inits × 4 cells = 200 rollouts；
2. `SKIP_COMPLETED_SUBRUNS=1` 断点续跑；
3. 原子锁，防止同一目录启动两份采集；
4. 硬崩溃后 stale lock 自动识别；
5. 13 个关键源文件、50 init、模型权重树和 anchors 哈希校验；
6. 首次运行合同与续跑配置漂移拒绝；
7. 进度、尝试、环境、单 rollout 记录和最终审计全部写入结果目录；
8. 只在 200-rollout 完整审计通过后生成 `DAY6_COMPLETE.json`。

断点判定不依赖“目录存在”。只有同时存在 `scenario_result.pkl`、`scenario_run_summary.json` 且 `ran_successfully=true` 的 rollout 才会被跳过。中途断电留下的半成品会在下次重跑时重新生成，prediction raw JSONL 会以写模式重建，不会追加旧半条轨迹。

## 2. 为什么建议新建干净 worktree

云端旧仓库 `/root/autodl-tmp/Research-Project-IMLS` 的 HEAD 较旧，且包含长期上传的未跟踪运行文件。不要对它执行 `git clean`、`git reset --hard` 或强制 pull。

本地推送后，在服务器从旧仓库创建独立干净 worktree：

```bash
cd /root/autodl-tmp/Research-Project-IMLS
git fetch origin
git worktree add --detach \
  /root/autodl-tmp/Research-Project-IMLS-day6 \
  origin/main
```

如果目标路径已存在，不要覆盖；改用一个新的显式路径，并同步修改下文 `DAY6_REPO`。

## 3. 服务器环境

```bash
export DAY6_REPO=/root/autodl-tmp/Research-Project-IMLS-day6
export DAY6_RESULTS=/root/autodl-tmp/results/give_way_transformer/day6/formal/day6_formal_v2_200
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python
export GUROBI_HOME=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi1103/linux64
export GUROBI_VERSION=110
export GRB_LICENSE_FILE=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi.lic
export LD_LIBRARY_PATH=$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}
mkdir -p "$DAY6_RESULTS"
```

脚本要求 CARLA RPC 2000 已可用。如果 CARLA 尚未启动：

```bash
nohup "$CARLA_ROOT/CarlaUE4.sh" \
  -RenderOffScreen -nosound -carla-rpc-port=2000 \
  > "$DAY6_RESULTS/carla_server.log" 2>&1 &
echo $! > "$DAY6_RESULTS/carla_server.pid"
```

等待服务启动后做一次 RPC 检查：

```bash
$PYTHON_BIN -c 'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(10); print(c.get_world().get_map().name)'
```

## 4. 正式启动命令

```bash
cd "$DAY6_REPO"
nohup env \
  CARLA_ROOT="$CARLA_ROOT" \
  PYTHON_BIN="$PYTHON_BIN" \
  GUROBI_HOME="$GUROBI_HOME" \
  GUROBI_VERSION="$GUROBI_VERSION" \
  GRB_LICENSE_FILE="$GRB_LICENSE_FILE" \
  LD_LIBRARY_PATH="$LD_LIBRARY_PATH" \
  RESULTS_DIR="$DAY6_RESULTS" \
  bash core/scripts/carla/run_day6_formal_prediction_dataset_v2.sh \
  > "$DAY6_RESULTS/day6_nohup.log" 2>&1 &
echo $! > "$DAY6_RESULTS/day6_launcher.pid"
echo "Day6 PID=$(cat "$DAY6_RESULTS/day6_launcher.pid")"
```

启动后不要改动代码、模型、init、frozen config 或结果目录。

## 5. 监看进度

```bash
tail -f "$DAY6_RESULTS/day6_runner.log"
```

快速数量检查：

```bash
find "$DAY6_RESULTS" -name scenario_run_summary.json | wc -l
find "$DAY6_RESULTS" -name prediction_dataset_manifest.json | wc -l
```

手动刷新结构化进度：

```bash
$PYTHON_BIN "$DAY6_REPO/core/scripts/models/summarize_prediction_dataset_v2_day6_progress.py" \
  --results-dir "$DAY6_RESULTS" \
  --phase manual_status
cat "$DAY6_RESULTS/day6_progress.json"
```

## 6. 服务器崩溃后续跑

1. 重启 CARLA；
2. 恢复第 3 节环境变量；
3. 完全重复第 4 节命令；
4. 必须使用同一 `DAY6_RESULTS`；
5. 不要手动删除任何 rollout。

脚本会跳过成功 rollout、重跑未完成/失败 rollout。如果源文件、模型权重、anchors、init 或 wrapper 发生变化，preflight 会拒绝在原目录续跑，避免混合两套实验。

## 7. 成功标志

不要以进程退出或目录数作为成功标志。唯一完成标志是：

```bash
test -f "$DAY6_RESULTS/DAY6_COMPLETE.json" \
  && cat "$DAY6_RESULTS/DAY6_COMPLETE.json"
```

`DAY6_COMPLETE.json` 只会在以下条件全部成立后生成：

- 200/200 rollouts；
- 每 cell 50 rollouts；
- 200 prediction manifests；
- 所有 rollout `ran_successfully=true`；
- 所有 raster 哈希和 interaction sequence 重建等价；
- 无样本键重复；
- reactive parameters 与 collection contract 无漂移；
- 160/20/20 grouped split 数量正确；
- 每条 rollout 都有 CARLA collision evidence。

碰撞结果只记录不过滤。如果某个冻结场景真实发生碰撞，不得为得到“零碰撞”而重跑。

## 8. 结果目录产物

```text
day6_runner.log
day6_nohup.log
day6_launcher.pid
day6_run_contract.json
day6_preflight_latest.json
day6_progress.json
day6_attempts.jsonl
protocol_snapshot/
S0_FIXED/
S0_ADAPTIVE/
S1_FIXED/
S1_ADAPTIVE/
prediction_dataset_manifests.txt
day6_collection_audit.json
day6_analysis_manifest.json
DAY6_COMPLETE.json
```

每个 cell 还有 `batch_events.jsonl`、`batch_subruns.json`、`batch_summary.txt`、`environment.json` 和完整单 rollout 轨迹、step CSV、pickle、prediction JSONL/raster/manifest。这些足够在采集结束后拉取紧凑审计产物并开始 Day 7 merge/split 与结果分析。
