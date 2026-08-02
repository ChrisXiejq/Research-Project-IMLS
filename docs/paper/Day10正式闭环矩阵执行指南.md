# Day 10 A3 正式闭环矩阵执行指南

更新日期：2026-08-02

## 1. 研究问题与冻结假设

Day 10 不再追求“adaptive 一定优于 fixed”或“更复杂模型一定更好”。正式问题是：

> validation-only 选择的 B1 fine-tuned predictor 相对 B0 pretrained predictor 的 offline 改善，是否会在 held-out give-way 条件下改变安全—效率—可靠性结果；这种模型效果是否受 fixed-risk frontier、adaptive risk 和 target responsiveness 调节？

预注册假设：

1. **H10-ML**：B1 与 B0 的闭环差异在 reactive 条件下大于 assertive 条件；方向由 held-out 数据决定，不预设 B1 全面占优。
2. **H10-Risk**：adaptive 的结果必须相对 aggressive/medium/conservative 三点 fixed frontier 判断，而非只和 fixed-medium 单点比较。
3. **H10-Interaction**：predictor × risk policy 存在可检测的机制差异；offline 指标改善不必单调转化为 completion 或 safety 改善。
4. **H10-Reliability**：所有正式 arms 应满足 completion/safety gate，prediction 数值有效，且 solver failure fraction 不超过冻结的 5%。

Transformer 仍是论文的模型改造实验，但 Day 8 显示 T1/T2 未超过 B1 gate。test 后强行部署 Transformer 会构成选择偏差；因此闭环使用 B1 与 B0，论文将 Transformer 结果报告为结构改造不充分的 negative evidence。

## 2. 正式矩阵与控制变量

```text
predictor: B1 seed37 / B0 pretrained
risk: fixed aggressive / fixed medium / fixed conservative / adaptive floor_weak
target: assertive / defensive reactive
ego init: 46,47,48,49,50（held-out）
authority: A3 risk-owned-yield
offset: 0.0 m
target nominal speed: 9.0 m/s
total: 2 × 4 × 2 × 5 = 80 rollouts
```

固定项包括 Town05 场景、ego init files、anchors、normalization、B1 validation calibration、B0 identity calibration、A3 tuning、reactive parameters、prediction horizon、logging stride、post-CARLA threshold 和 Git commit。只允许三个预注册因素变化：predictor、risk policy、target style。

分析单位是 `(ego_init_id, target_style)` paired condition，不把 simulator steps 当独立样本。正式比较包括：

- B1−B0：同 risk、同 init、同 style 配对；
- adaptive−每个 fixed frontier point：同 predictor、同 init、同 style 配对；
- predictor × risk 与 predictor × target-style interaction；
- safety（collision/yield/min footprint separation）、efficiency（completion time）、reliability（solver failure）、mechanism（risk tightening/supervisor intervention）。

Day 9 暴露的 20 Hz 数值微分限制仍存在，因此不把 raw max jerk 作为人体舒适性硬结论；jerk 仅作 secondary descriptive metric。

## 3. 自动完成门

Runner 会冻结并审计：

1. Day 7/8/9 completion；
2. B1/B0 model、B1 validation calibration、anchors 与 normalization；
3. init46–50、tuning、reactive parameters 和 Git commit hashes；
4. 16 cells、80 rollouts，不允许缺失或重复；
5. 每个 rollout 的 target style/offset/speed/cell/risk labels；
6. prediction probabilities/covariances 与 debug finite checks；
7. prediction→risk mode→solver→supervisor 链；
8. solver failure 与 post-CARLA 独立计数一致；
9. completion、collision、give-way order 和 5% solver gate；
10. reactive cells 至少实际覆盖 response-active samples；
11. 生成 `DAY10_COMPLETE.json`、audit 和 compact snapshot。

## 4. 服务器启动

先同步提交；Day 10 运行期间不要再 `git pull`，否则 frozen contract 会拒绝续跑。

```bash
cd /root/autodl-tmp/Research-Project-IMLS-day8
git pull --ff-only origin main
git log -1 --oneline

export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python
export DAY7_RESULTS=/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1
export DAY8_RESULTS=/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1
export DAY9_RESULTS=/root/autodl-tmp/results/give_way_transformer/day9/day9_smoke_v1
export DAY10_RESULTS=/root/autodl-tmp/results/give_way_transformer/day10/day10_formal_v1

export GUROBI_HOME=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi1103/linux64
export GUROBI_VERSION=110
export GRB_LICENSE_FILE=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi.lic
export LD_LIBRARY_PATH="$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}"

mkdir -p "$(dirname "$DAY10_RESULTS")"
nohup env \
  CARLA_ROOT="$CARLA_ROOT" PYTHON_BIN="$PYTHON_BIN" \
  DAY7_RESULTS="$DAY7_RESULTS" DAY8_RESULTS="$DAY8_RESULTS" \
  DAY9_RESULTS="$DAY9_RESULTS" DAY10_RESULTS="$DAY10_RESULTS" \
  GUROBI_HOME="$GUROBI_HOME" GUROBI_VERSION="$GUROBI_VERSION" \
  GRB_LICENSE_FILE="$GRB_LICENSE_FILE" LD_LIBRARY_PATH="$LD_LIBRARY_PATH" \
  bash core/scripts/carla/run_day10_formal_closed_loop.sh \
  > "$DAY10_RESULTS.launcher.log" 2>&1 &

echo $! > "$DAY10_RESULTS.launcher.pid"
echo "Day10 PID=$(cat "$DAY10_RESULTS.launcher.pid")"
```

## 5. 监控、续跑与完成

```bash
tail -F "$DAY10_RESULTS/day10_runner.log"
```

另一个终端查看 rollout 数量：

```bash
find "$DAY10_RESULTS" -name scenario_run_summary.json -type f | wc -l
```

服务器中断后，保持同一 Git commit、环境变量和 `DAY10_RESULTS`，原样重跑 `nohup` 命令；`--skip_completed_subruns` 会跳过成功项。不得删除失败证据、修改 contract 或根据中期趋势调参。

首次中断审计记录：Day 10 在 16 个成功 rollout 后因 CARLA `world.apply_settings` 超时停止；第 17 个目录明确记录 `ran_successfully=false`，因此不被 resume skip。随后发现 v1 contract 错误冻结了包含 GPU 浮点 warm-up 诊断的整个 preflight JSON 字节哈希，同一模型与配置在重跑 preflight 时也会产生无意义 hash drift。v2 contract 仅冻结 model/calibration/anchors/normalization、warm-up input hashes 和数值 checks 等稳定语义字段。一次性 migration 只在旧、新合同除 preflight hash/Git 外完全相同，且 Git diff 仅包含 runner/audit/docs 修复时允许；它记录旧/新 commit、观测 hash 和 changed files 到 `day10_contract_resume_provenance.json`，保留已有 16 个 raw rollouts。模型、控制器、scenario、tuning 或 init 的任何变化仍会拒绝续跑。

最终检查：

```bash
cat "$DAY10_RESULTS/DAY10_COMPLETE.json"
cat "$DAY10_RESULTS/day10_formal_snapshot.tar.gz.json"
```

只有 `status=pass`、`observed_cells=16`、`observed_rollouts=80` 才算 Day 10 完成。完成后通知我拉取 snapshot，进行 paired statistics、interaction analysis、论文表格和图形生成。
