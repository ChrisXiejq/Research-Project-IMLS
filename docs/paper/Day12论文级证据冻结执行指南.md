# Day12 论文级证据冻结执行指南

> 状态：**2026-08-02 全部完成。** 服务器三个完成门通过，四个关键资产包已下载到服务器之外并通过 SHA-256、大小和 tar 成员完整性验证。

## 1. Day12 当前完成情况

### 已完成：Day10 init-cluster inference

- 80 条 rollout、16 cells 和 136 个 contrasts 保持不变；
- 新 schema：`day10_paired_analysis_v3`；
- 136/136 effect means 与旧版一致；
- inference 从重复 `(init, style)` conditions 改为 5 个 init-cluster means；
- fixed-aggressive delay exact p：`0.0117 → 0.0625`；
- fixed-aggressive delay Holm p：`0.1875 → 1.0`；
- 旧版 condition-level p 值废止。

### 已完成：三水平 timing synthesis

```text
B0/B1 × fixed-medium/adaptive × assertive/reactive
× offset {-3, 0, +3 m} × init46–50
= 120 rollouts, 24 cells
```

Compatibility gate 验证了 models、calibration、anchors、normalization、init、authority、reactive/adaptive parameters 和 target speed 全部一致，且 Day11 contract 正确引用 Day10 contract SHA。

主要结果：

| Contrast（跨三个 offsets） | Adjusted delay | Footprint margin | Solver failure | Supervisor active |
| --- | ---: | ---: | ---: | ---: |
| B1−B0, fixed-medium | -0.370 s | -0.069 m | +0.00007 | +0.00496 |
| B1−B0, adaptive | -0.337 s | -0.035 m | +0.00091 | +0.00522 |
| adaptive−fixed, B1 | -0.063 s | +0.080 m | +0.00113 | +0.00103 |
| adaptive−fixed, B0 | -0.097 s | +0.046 m | +0.00028 | +0.00077 |

解释：B1 跨局部 timing range 有约 0.34–0.37 s 的效率方向，但 margin 更小、controller intervention 更高；adaptive 平均效率差很小，增加少量 margin 同时增加 solver failure。所有 inference-family Holm p 均为 1.0，因此是 effect-size/机制证据，不是 superiority 证明。

机器证据：

```text
docs/paper/generated/day10/analysis/
docs/paper/generated/day12/timing_synthesis/
```

## 2. 服务器执行内容

统一 runner 会顺序执行：

1. 对 200 条 Day6 labeled JSONL 做 collision-window attribution；
2. 在服务器复算 Day10 analysis v3；
3. 在服务器复算三水平 timing synthesis；
4. 打包 200-rollout prediction dataset；
5. 验证并打包 B0 与五个 frozen representative model packages；
6. 复制并校验 Day10/Day11 full snapshots；
7. 为每个 bundle 写 SHA-256 sidecar 和总 manifest。

资产打包以单 bundle 为断点：已完成且 sidecar hash 匹配的 bundle 会跳过；中断时只留下 `.partial`，续跑只重建未完成 bundle，不覆盖已验证产物。

## 3. 同步与启动命令

```bash
cd /root/autodl-tmp
source /etc/network_turbo
if [ ! -d /root/autodl-tmp/Research-Project-IMLS-day12/.git ]; then
  git clone https://github.com/ChrisXiejq/Research-Project-IMLS.git Research-Project-IMLS-day12
fi
cd /root/autodl-tmp/Research-Project-IMLS-day12
git pull origin main

export DAY12_RESULTS=/root/autodl-tmp/results/give_way_transformer/day12/day12_evidence_freeze_v1
mkdir -p "$DAY12_RESULTS"

nohup bash core/scripts/models/run_day12_finalize_evidence.sh \
  > "$DAY12_RESULTS/day12_launcher.log" 2>&1 &
echo $! > "$DAY12_RESULTS/day12_launcher.pid"
echo "Day12 PID=$(cat "$DAY12_RESULTS/day12_launcher.pid")"
```

持续监控：

```bash
tail -F "$DAY12_RESULTS/day12_runner.log"
```

简要检查：

```bash
ps -fp "$(cat "$DAY12_RESULTS/day12_launcher.pid")" || true
tail -n 80 "$DAY12_RESULTS/day12_runner.log"
du -sh "$DAY12_RESULTS"/* 2>/dev/null | sort -h
```

## 4. 中断续跑

服务器中断后执行完全相同的命令：

```bash
cd /root/autodl-tmp/Research-Project-IMLS-day12
export DAY12_RESULTS=/root/autodl-tmp/results/give_way_transformer/day12/day12_evidence_freeze_v1
nohup bash core/scripts/models/run_day12_finalize_evidence.sh \
  > "$DAY12_RESULTS/day12_launcher_resume.log" 2>&1 &
echo $! > "$DAY12_RESULTS/day12_launcher.pid"
```

不要删除结果目录；runner 会用 SHA-256 判断哪些 bundle 可以安全跳过。

## 5. 服务器阶段完成门

```bash
cat "$DAY12_RESULTS/collision_attribution/DAY12_COLLISION_ATTRIBUTION_COMPLETE.json"
cat "$DAY12_RESULTS/timing_synthesis/DAY12_TIMING_SYNTHESIS_COMPLETE.json"
cat "$DAY12_RESULTS/asset_backup/DAY12_ASSET_BACKUP_SERVER_STAGE_COMPLETE.json"
cat "$DAY12_RESULTS/asset_backup/day12_critical_asset_backup_manifest.json"
```

三个 marker 都必须是 `status=pass`。Asset marker 的 `offsite_copy_pending=true` 是正常的：它表示服务器归档完成，但还没有证明第二份副本已下载。

Collision attribution 的 decision rule 已在执行前冻结：

- affected usable windows = 0：不重训；
- validation/test 出现 affected window：critical review；
- 仅 training affected，且占 reactive train ≤1%：补 B1/seed37 filtered sensitivity；
- 占 reactive train >1%：审查是否需要 filtered full matrix。

## 6. 服务器执行完成后的本地工作

服务器完成后通知我。我会：

1. 拉取 collision attribution 和两个分析目录；
2. 拉取 asset manifest 和 completion marker；
3. 根据 collision overlap 自动决定是否需要补训练；
4. 下载关键 bundles 到服务器之外的备份目录；
5. 执行：

```bash
python core/scripts/models/verify_day12_offsite_backup.py \
  --backup-dir /path/to/copied/day12_asset_backup
```

只有生成 `DAY12_OFFSITE_BACKUP_VERIFIED.json` 后，Day12 资产保护门才算真正关闭。

## 7. 最终完成结果

- collision attribution：200/200 rollouts；6 个 callback-containing rollout 全部位于 reactive training split；253 callbacks 合并为 16 contact episodes、62 unique frames；只有 `target_2` 与 traffic light/static wall 接触；validation/test 上界为 0；
- Day6 没有保存 sample clock 到 CARLA global frame 的每 rollout anchor，因此不能诚实声称完成了逐窗口精确对齐；采用预先声明的保守上界，将六个 rollout 的全部 162 usable windows 计为可能受影响；
- reactive train 上界：`162/2116 = 7.656%`；全部 train 上界：`162/4036 = 4.014%`；触发 filtered full-matrix review；
- Day10 v3 服务器复算与本地结果逐字节一致；
- Day10+Day11 synthesis：120 rollouts、24 cells、160 contrasts、0 observed collision/yield failure；
- 四个备份归档合计约 654 MiB，SHA-256 全部匹配，验证 14,148 个 tar members；
- 本地仓库外副本：`/Users/bytedance/my/Dissertation/offsite_backups/day12_evidence_freeze_v1`；
- 机器完成标记：`generated/day12/asset_backup_manifest/DAY12_OFFSITE_BACKUP_VERIFIED.json`。

Day12 已关闭。由于 7.656% 是无法进一步缩小的保守 reactive-train 上界，下一步不是改写原实验，而是运行 validation-only filtered 5×3 sensitivity matrix；原 Day8 与 frozen test 始终保持 primary evidence。
