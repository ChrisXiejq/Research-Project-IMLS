# R3 v2 最终执行与恢复指南

**状态：**pre-launch hardening 完成；等待用户在服务器执行

**唯一正式结果目录：**`/root/autodl-tmp/results/give_way_transformer/distinction_v1/r3_corrected_formal_v2`

**唯一正式 protocol：**`r3_corrected_formal_v2`

**正式规模：**2 predictor stacks × 4 risk policies × 2 target styles × 5 frozen inits = 80 rollouts

本指南对应毕业论文最后一次大规模 CARLA 数据采集。Codex 不登录服务器、不向服务器传文件、不替用户启动或轮询实验。代码只通过 Git commit 同步；用户运行并监控，完成后通知 Codex 拉取一次正式 evidence archive。

## 1. 什么叫“R3 完成”

唯一完成判据是结果根目录同时存在并通过验证的：

- `R3_COMPLETE.json`，其中 `status=pass`、`additional_large_scale_carla_required=false`；
- `analysis/R3_STUDY_STOP_GATE.json`，其中 `study_stop_gate_passed=true`；
- `r3_corrected_formal_snapshot.tar.gz` 及两个 sidecars，且 `--verify-only` 回读全部成员通过。

这表示 80 个 prespecified treatment keys 都有 integrity-valid raw evidence，每个 outcome 已观测或按冻结规则明确分类为 scientific undefined/censored，并且正式统计表、provenance 和 raw archive 可离线复算。它不要求 H3/H4 为正向，也不要求 80 个 completion time 全部 finite。

碰撞、未完成、yield failure、adaptive 不占优、reactive 没有激活、risk 没有变化、mode collapse、runtime 超阈值、null/negative/mixed effect 都是要写进论文的科学结果，不能用来重跑或删样本。只有缺文件、hash 不一致、错误 treatment、错误 solver identity、控制变量漂移、数值损坏等 integrity defect 才允许续跑同一个 R3 key。

## 2. 首次部署：只从最终 Git commit 获取代码

把 Codex 最终回复给出的 40 位 commit SHA 填入第一行。不要使用 `main` 的浮动 HEAD，也不要复制本地文件到服务器。

```bash
source /etc/network_turbo

export R3_COMMIT='<FINAL_COMMIT_SHA_FROM_CODEX>'
export R3_REPO="/root/autodl-tmp/Research-Project-IMLS-r3-${R3_COMMIT:0:7}"
export R3_ORIGIN='https://github.com/ChrisXiejq/Research-Project-IMLS.git'

if [[ -e "$R3_REPO" && ! -d "$R3_REPO/.git" ]]; then
  echo "Refusing to reuse a non-Git path: $R3_REPO" >&2
  exit 2
fi

if [[ ! -d "$R3_REPO/.git" ]]; then
  git clone "$R3_ORIGIN" "$R3_REPO"
fi

if [[ -n "$(git -C "$R3_REPO" status --porcelain --untracked-files=no)" ]]; then
  echo 'Dedicated R3 clone has tracked changes; stop and report them.' >&2
  git -C "$R3_REPO" status --short --untracked-files=no
  exit 3
fi

git -C "$R3_REPO" fetch origin "$R3_COMMIT"
git -C "$R3_REPO" checkout --detach "$R3_COMMIT"
test "$(git -C "$R3_REPO" rev-parse HEAD)" = "$R3_COMMIT"
test -z "$(git -C "$R3_REPO" status --porcelain --untracked-files=no)"
git -C "$R3_REPO" show -s --format='%H %s'
```

## 3. 冻结运行环境

这些路径沿用已经通过 R2 的服务器资产。不要修改 model、calibration、anchors、init、scenario、tuning 或结果目录。

```bash
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python
export DAY7_RESULTS=/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1
export DAY8_RESULTS=/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1
export R2_RESULTS=/root/autodl-tmp/results/give_way_transformer/distinction_v1/r2_corrected_pilot_v4
export R3_RESULTS=/root/autodl-tmp/results/give_way_transformer/distinction_v1/r3_corrected_formal_v2
export GUROBI_BUNDLE_ROOT=/root/autodl-tmp/Research-Project-IMLS/gurobi
export R3_MAX_ATTEMPTS=10
export CUDA_VISIBLE_DEVICES=0
export TF_FORCE_GPU_ALLOW_GROWTH=true
export PYTHONPATH="$CARLA_ROOT/PythonAPI/carla:$CARLA_ROOT/PythonAPI/carla/agents:$R3_REPO/core/scripts/models:${PYTHONPATH:-}"

mkdir -p /root/autodl-tmp/logs
mkdir -p "$(dirname "$R3_RESULTS")"
```

`R3_MAX_ATTEMPTS=10` 是运行前冻结的有界 infrastructure-recovery allowance。每次失败都保留；只有 allowlisted infrastructure failure 会自动续试，科学结果从不续试。

## 4. 启动专用 Town05 CARLA

R3 必须独占 `127.0.0.1:2000`。以下命令只终止位于指定 `CARLA_ROOT` 下的旧 CARLA 进程，不匹配其他路径。如果 TERM 后仍有进程，命令会停止并要求人工检查，不会强制 KILL。

```bash
mapfile -t R3_OLD_CARLA_PIDS < <(pgrep -f "$CARLA_ROOT/.*CarlaUE4" || true)
if ((${#R3_OLD_CARLA_PIDS[@]})); then
  printf 'Stopping old dedicated CARLA PIDs: %s\n' "${R3_OLD_CARLA_PIDS[*]}"
  kill -TERM "${R3_OLD_CARLA_PIDS[@]}"
  sleep 8
fi

mapfile -t R3_REMAINING_CARLA_PIDS < <(pgrep -f "$CARLA_ROOT/.*CarlaUE4" || true)
if ((${#R3_REMAINING_CARLA_PIDS[@]})); then
  echo "CARLA processes did not stop: ${R3_REMAINING_CARLA_PIDS[*]}" >&2
  exit 4
fi

nohup "$CARLA_ROOT/CarlaUE4.sh" Town05 \
  -RenderOffScreen -quality-level=Low -nosound \
  > /root/autodl-tmp/logs/carla_r3_town05.log 2>&1 &
export R3_CARLA_PID=$!
echo "$R3_CARLA_PID" > /root/autodl-tmp/logs/carla_r3_town05.pid

for _ in $(seq 1 90); do
  if "$PYTHON_BIN" - <<'PY'
import carla
c = carla.Client('127.0.0.1', 2000)
c.set_timeout(3.0)
raise SystemExit(0 if c.get_world().get_map().name.endswith('Town05') else 2)
PY
  then
    break
  fi
  sleep 2
done

"$PYTHON_BIN" - <<'PY'
import carla
c = carla.Client('127.0.0.1', 2000)
c.set_timeout(10.0)
print('CARLA server:', c.get_server_version())
print('CARLA map:', c.get_world().get_map().name)
assert c.get_world().get_map().name.endswith('Town05')
PY
```

## 5. 先执行零 rollout preflight

Preflight 会检查 exact Git SHA、clean tracked worktree、Town05、TensorFlow GPU、Gurobi、Day7/Day8/R2 assets、model/calibration hashes、M0 v1/v2 binding、80-key contract、init/scenario/tuning hashes，以及 37 项 regression/hardening/formal-analysis tests。它不会启动科学 rollout。

```bash
cd "$R3_REPO"
bash core/scripts/carla/run_r3_corrected_formal_matrix.sh --preflight-only

test -f "$R3_RESULTS/R3_PREFLIGHT_COMPLETE.json"
cat "$R3_RESULTS/R3_PREFLIGHT_COMPLETE.json"
bash core/scripts/carla/run_r3_corrected_formal_matrix.sh --list-pending
```

只有 marker 的 `status` 为 `pass` 且 `scientific_rollouts_launched` 为 `0` 才进入下一步。若 preflight 报错，停止并把完整错误交给 Codex；不要修改冻结文件或绕过 assertion。

## 6. 启动正式 R3

```bash
cd "$R3_REPO"
nohup bash core/scripts/carla/run_r3_corrected_formal_matrix.sh \
  >> "$R3_RESULTS/r3_launcher.log" 2>&1 &
export R3_RUNNER_PID=$!
echo "$R3_RUNNER_PID" | tee "$R3_RESULTS/r3_launcher.pid"
echo "R3 runner started: PID=$R3_RUNNER_PID"
```

只启动一次。Runner 有单实例 lock；同一结果目录并发启动第二个 runner 会安全退出。

## 7. 观测命令

主日志持续跟踪：

```bash
tail -F "$R3_RESULTS/r3_runner.log"
```

另开一个终端，每 20 秒查看 accepted/pending/failed/current 和最终 gate：

```bash
watch -n 20 "date; '$PYTHON_BIN' '$R3_REPO/core/scripts/models/summarize_r3_progress.py' --results-dir '$R3_RESULTS'"
```

一次性状态、runner、CARLA 和 GPU：

```bash
"$PYTHON_BIN" "$R3_REPO/core/scripts/models/summarize_r3_progress.py" \
  --results-dir "$R3_RESULTS"

test -f "$R3_RESULTS/r3_launcher.pid" \
  && ps -fp "$(cat "$R3_RESULTS/r3_launcher.pid")" || true
pgrep -af "$CARLA_ROOT/.*CarlaUE4" || true
nvidia-smi
```

查看最近 attempt 日志路径：

```bash
find "$R3_RESULTS" -path '*/_attempts/init_*/attempt_*/runner_attempt.log' \
  -type f -printf '%T@ %p\n' | sort -n | tail -n 5
```

## 8. 服务器中断后的唯一续跑方法

不要删除结果目录、canonical scenario、`_attempts`、receipt、ledger、contract 或 logs。恢复同一个 exact commit 和第 3 节环境变量，重启专用 Town05 CARLA，然后执行：

```bash
cd "$R3_REPO"
bash core/scripts/carla/run_r3_corrected_formal_matrix.sh --list-pending

nohup bash core/scripts/carla/run_r3_corrected_formal_matrix.sh \
  >> "$R3_RESULTS/r3_launcher.log" 2>&1 &
export R3_RUNNER_PID=$!
echo "$R3_RUNNER_PID" | tee "$R3_RESULTS/r3_launcher.pid"
```

Runner 会把断电边界上的 raw-complete attempt 或已 promotion attempt 认领为原 attempt，并继续下一个 pending key；不会混合两次进程的 JSONL/CSV。如果报告 `blocked_nonretryable`、frozen drift、hash mismatch 或 exhausted attempts，不要清理或强行续跑，把 `r3_runner.log`、最后一个 `runner_attempt.log` 和 `--list-pending` 输出交给 Codex。

## 9. 结束验证

Runner 退出不等于实验完成。只有以下整块全部成功才通知 Codex：

```bash
test -f "$R3_RESULTS/R3_COMPLETE.json"
cat "$R3_RESULTS/R3_COMPLETE.json"
cat "$R3_RESULTS/analysis/R3_STUDY_STOP_GATE.json"

"$PYTHON_BIN" "$R3_REPO/core/scripts/models/package_closed_loop_snapshot.py" \
  --verify-only \
  --output "$R3_RESULTS/r3_corrected_formal_snapshot.tar.gz"

sha256sum \
  "$R3_RESULTS/r3_corrected_formal_snapshot.tar.gz" \
  "$R3_RESULTS/r3_corrected_formal_snapshot.tar.gz.json" \
  "$R3_RESULTS/r3_corrected_formal_snapshot.tar.gz.files.json"

"$PYTHON_BIN" "$R3_REPO/core/scripts/models/summarize_r3_progress.py" \
  --results-dir "$R3_RESULTS" --json
```

完成后只需告诉 Codex“R3_COMPLETE 已生成并且 verify-only pass”。Codex 再拉取正式 archive/sidecars，离线复算论文表图和 H3/H4 结论。R3 marker 通过后，不再启动 R4 或其他大规模 CARLA 实验。
