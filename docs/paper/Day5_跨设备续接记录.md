# Day 5 跨设备续接记录

> 状态更新：本交接记录中的“停止点”已过时。Day 5 已于 2026-07-31 完成；结果已统一移至 `/root/autodl-tmp/results/give_way_transformer/`，最新结论以 `Day5_开发实验与Reactive参数冻结报告.md` 为准。

更新时间：2026-07-31  
本地分支：`main`  
最新实现提交：`6b71ccc`

## 1. 当前停止点

任务已按用户要求停止。停止时没有主动启动新的最终 Day 5 批次。

最后一次已确认的有效实验是单 rollout 候选验证：

```text
云端目录：
/root/autodl-tmp/results/give_way_transformer/day5/development/candidates/day5_candidate_clean_6b71ccc

代码版本：
6b71ccc

cell / init：
S1_FIXED / init01
```

结果：

```text
ran_successfully: true
trigger_count: 1
trigger_time: 0.80 s（相对 rollout 首个记录步）
release_count: 1
active_fraction: 0.06338
minimum target speed: 4.1236 m/s
native CARLA collision_event_count: 0
```

原计划的统一 20-rollout 最终 Day 5 目录：

```text
/root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc
```

在 SSH 连接被服务器重置后，启动命令没有得到执行确认。因此续接时必须先只读检查该目录和相关进程，不能假设它已启动，也不能直接重复启动。

## 2. Day 4 正确性结论

### 仍然成立的部分

Day 4 的以下数据链已由真实 CARLA 样本验证：

1. raster 在线输入与 PNG 离线读取字节等价；
2. ResNet preprocessing 在线/离线等价；
3. 6×12 interaction sequence 可从原始 history 完全重建；
4. sequence mask、速度和坐标变换链有效；
5. target diagnostics 与同一控制步对齐；
6. 四个 V2 cells 均能生成 manifest、JSONL 和 raster。

证据：

```text
docs/paper/generated/day4/day4_input_contract_real_sample.json
docs/paper/generated/day4/day4_v2_smoke_audit.json
docs/paper/Day4_V2交互数据链路与ReactiveTarget报告.md
```

### 已发现并修复的问题

Day 4 原 reactive 行为证据不能继续作为有效参数证据，原因有两个：

1. 冲突点用“ego 起点—终点直线弦”与 target 直线求交；对左转路线不正确。
2. release 后可以再次触发，因此单次过路出现两次 trigger/release。

修复：

1. 冲突点改为与 SMPC 一致的 `ego reference route—target motion line` 最近点；
2. 当前 Town05 冲突点约为 `[28.48, 3.55] m`；
3. reactive episode 使用 single-trigger、latched-release；
4. 加入 CARLA 原生 collision sensor；
5. Day 5 audit 同时检查数据契约、行为、separation 和碰撞事件。

对应提交：

```text
cdfe421 feat: add Day 5 reactive freeze audit
f818589 feat: record native CARLA collision evidence
6b71ccc fix: calibrate Day 5 reactive trigger
```

## 3. Day 5 参数选择过程

### 被拒绝的旧候选

旧参数：

```text
activation_distance_m: 30.0
arrival_time_gap_s: 2.0
hazard: TTC OR closest approach
```

在 5 个 S1_FIXED rollout 中均于第一个控制步触发。虽然没有重复 trigger，active fraction 约 20%，但它本质上接近“立即减速脚本”，不能提供有意义的 interaction timing variation，因此未冻结。

### 当前候选

当前代码默认值：

```text
nominal_speed_mps: 9.0
caution_speed_mps: 4.5
minimum_speed_mps: 2.5
activation_distance_m: 10.0
release_clearance_m: 5.0
arrival_time_gap_s: 0.5
closest_approach_time_s: 4.0
closest_approach_distance_m: 6.0
release_hold_s: 0.8
max_decel_mps2: -2.0
hazard combination: TTC AND closest approach
episode semantics: single-trigger latched-release
```

该候选来自已完成的 10 条 S0 counterfactual 轨迹离线阈值扫描，不是盲目试参。扫描预测：

```text
trigger coverage: 8/10
trigger onset: 0.75–0.85 s（触发轨迹）
init03: 预计不触发
```

init01 的真实 S1_FIXED 验证结果与预测一致，见第 1 节。

## 4. 云端实验目录分类

### 有效、可保留的证据

```text
/root/autodl-tmp/results/give_way_transformer/day5/development/smoke/day5_route_smoke_cdfe421
/root/autodl-tmp/results/give_way_transformer/day5/development/smoke/day5_collision_sensor_smoke_f818589
/root/autodl-tmp/results/give_way_transformer/day5/development/candidates/day5_candidate_clean_6b71ccc
```

用途：

- `day5_route_smoke_cdfe421`：route-aware conflict point 和 single-trigger smoke；
- `day5_collision_sensor_smoke_f818589`：四单元原生碰撞传感器 smoke，4 个 collision count 均为 0；
- `day5_candidate_clean_6b71ccc`：当前候选 init01 真实验证。

### 无效 pilot，禁止进入训练/论文统计

目录名已包含失败原因，包括：

```text
day5_route_smoke_cdfe421_FAILED_MISSING_GUROBI_VERSION
day5_route_smoke_cdfe421_S0_ADAPTIVE_INVALID_ORPHAN
day5_development_cdfe421_PILOT_NO_COLLISION_SENSOR
day5_collision_sensor_smoke_f818589_INFRA_TIMEOUT
day5_development_f818589_PILOT_IMMEDIATE_TRIGGER
day5_candidate_6b71ccc_FAILED_BAD_TUNING_PATH
day5_candidate_6b71ccc_FAILED_STALE_SPAWN
day5_candidate_6b71ccc_FAILED_PHANTOM_SPAWN_2
```

这些目录不要删除，以保留审计记录；但任何 dataset merge 或论文统计都必须显式排除。

## 5. 换设备后的恢复步骤

### 5.1 同步 Git

当前设备的 `main` 比 `origin/main` 超前。先在当前设备推送：

```bash
cd /Users/bytedance/my/Dissertation/Research-Project-IMLS
git push origin main
```

在新设备：

```bash
git clone <repository-url>
cd Research-Project-IMLS
git checkout main
git pull --ff-only origin main
git log --oneline -6
```

必须看到 `6b71ccc` 及更新的 handoff 提交。

### 5.2 恢复对话上下文

优先在新设备使用同一 Codex/OpenAI 账号打开原任务。若任务历史不可见，把本文件路径和以下指令发给新的 Codex：

```text
请完整阅读 docs/paper/Day5_跨设备续接记录.md、
docs/paper/两周_最终研究主线_数据扩展与实验执行方案.md、
docs/paper/Day4_V2交互数据链路与ReactiveTarget报告.md，
从 Day 5 停止点继续。先只读检查云端状态，不要立即重跑。
```

### 5.3 云端只读恢复检查

不要把 SSH 密码写入仓库或命令脚本。登录后先检查：

```bash
pgrep -af 'CarlaUE4|run_all_scenarios.py|run_give_way_prediction_dataset_v2.sh'
find /root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc \
  -name scenario_run_summary.json 2>/dev/null | wc -l
test -f /root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc.log \
  && tail -n 40 /root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc.log
```

解释：

1. 若没有 Day 5 进程且目录不存在/完成数为 0：可以启动最终批次；
2. 若进程存在：先监控，不要启动第二份；
3. 若目录有部分成功 rollout 且没有进程：使用原目录和 `SKIP_COMPLETED_SUBRUNS=1` resume；
4. 若发现失败 rollout：先按失败原因判断是否技术失败，再移动该 subrun 后用完全相同配置重跑。

### 5.4 云端环境

按以下环境恢复：

```bash
cd /root/autodl-tmp/Research-Project-IMLS
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export GUROBI_HOME=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi1103/linux64
export GUROBI_VERSION=110
export GRB_LICENSE_FILE=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi.lic
export LD_LIBRARY_PATH=$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}
export PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python
```

必须先做 CARLA RPC health check；仅看到进程不代表服务可用。

### 5.5 最终 Day 5 批次

只在确认没有重复进程后执行：

```bash
RESULTS_DIR=/root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc \
INIT_START=1 \
INIT_END=5 \
PREDICTION_GIT_COMMIT=6b71ccc \
LOG_STRIDE=4 \
SKIP_COMPLETED_SUBRUNS=1 \
nohup bash core/scripts/carla/run_give_way_prediction_dataset_v2.sh \
  > /root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc.log 2>&1 &
```

完成后运行：

```bash
PYTHONPATH=core/scripts/models \
$PYTHON_BIN core/scripts/models/audit_prediction_dataset_v2_day5.py \
  --results-dir /root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc \
  --output-json /root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc_audit.json \
  --frozen-config-json /root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc_frozen_config.json \
  --expected-git-commit 6b71ccc
```

只有 audit `status=pass` 时才允许：

1. 把 audit 和 frozen config 下载到 `docs/paper/generated/day5/`；
2. 将 protocol manifest 中的 reactive 参数从 pending 改为 frozen；
3. 生成并记录 collection config SHA-256；
4. 把 Day 5 标为完成；
5. 进入 Day 6 正式 200-rollout collection。

## 6. 续接时必须再次确认的门

```text
20/20 rollout matrix complete
all manifests have git_commit = 6b71ccc
raster hash and sequence equivalence pass
trigger coverage within planned development interval
no rollout has more than one trigger/release
mean active fraction within planned interval
minimum target speed > 2.5 m/s
native CARLA collision event count = 0
S1–S0 paired target future separation > noise floor
all S1 samples expose one identical reactive parameter hash
```

如果 trigger coverage 超出计划区间，不能为了“让结果好看”继续反复调参。应先判断是否仍满足“非立即、非全程、跨 init 时序不同、存在未触发 counterfactual”的研究设计要求，并在文档中预先定义接受/拒绝理由。
