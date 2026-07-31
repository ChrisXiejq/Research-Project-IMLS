# Day 1：冻结协议与服务器资产审计报告

> 审计日期：2026-07-31（Asia/Shanghai）
>
> 审计范围：本地仓库与 CARLA 云服务器的只读资产核对
>
> 执行约束：未训练模型、未启动 CARLA、未运行场景、未修改服务器文件

## 1. Day 1 结论

Day 1 完成门已通过。

现有 50-rollout prediction dataset、merged manifest、train/validation/test JSONL、10,236 个 raster、MultiPath checkpoints、Interaction Transformer checkpoints、训练日志以及已有闭环 pilot results 均存在于服务器。当前不需要重新采集数据，也不需要恢复缺失 checkpoint。

Day 2 可以直接进入 split integrity audit。由于完整数据集约 `758 MB`，而服务器数据盘尚有约 `25 GB` 空闲，建议在服务器原位执行 raster 和 JSONL 完整性检查；本地只拉取 manifest、必要 metadata、审计报告、训练日志和进入后续分析所需的模型产物。

当前主要风险是服务器仓库并非 clean worktree，且最重要的 Transformer checkpoints 是未跟踪目录。后续同步代码时必须保护服务器侧未跟踪模型和结果，禁止使用会删除远端未跟踪文件的同步方式。

## 2. 冻结的实验协议

### 2.1 正式闭环 conditions

以下十个 condition 在正式实验前保持不变：

| Condition | Ego init | Target start offset | Target speed |
| --- | ---: | ---: | ---: |
| C01 | 46 | -3.0 m | 9.0 m/s |
| C02 | 46 | +3.0 m | 9.0 m/s |
| C03 | 47 | -3.0 m | 9.0 m/s |
| C04 | 47 | +3.0 m | 9.0 m/s |
| C05 | 48 | -3.0 m | 9.0 m/s |
| C06 | 48 | +3.0 m | 9.0 m/s |
| C07 | 49 | -3.0 m | 9.0 m/s |
| C08 | 49 | +3.0 m | 9.0 m/s |
| C09 | 50 | -3.0 m | 9.0 m/s |
| C10 | 50 | +3.0 m | 9.0 m/s |

不得根据 smoke test 或正式结果删除困难 condition，亦不得再次使用 `ego_init_01` 调整模型、risk policy、supervisor 或 gate threshold。

### 2.2 Primary outcomes

1. `min_footprint_separation_m`
2. `target_clearance_adjusted_completion_delay_s`

第二个指标冻结为：

```text
ego valid completion time - target conflict-zone clearance time
```

正式 batch 前只允许补齐以下边界条件的程序化定义，不允许根据结果改变定义：

- target 未发生有效 clearance；
- ego 未完成；
- completion time 或 clearance time 缺失；
- 差值为负。

### 2.3 Secondary outcomes

- gate pass/fail；
- collision；
- yield-order violation；
- completion valid；
- completion time；
- first-stop distance；
- waiting time；
- solver failure fraction；
- failure phase；
- direct takeover fraction；
- emergency intervention fraction；
- supervisor active fraction；
- mean/P95 solve time；
- P95 jerk；
- nominal-final action mismatch。

`max jerk` 不作为冻结的主要结果。正式使用 jerk 前必须调查现有约 `176 m/s³` 的异常；若无法在两周内可靠修复，则报告 P95/RMS 并说明数值微分和控制切换限制。

### 2.4 冻结的研究比较

- 主要 predictor：M0 CARLA-finetuned MultiPath、M1 context MLP、M3 normalized-context Transformer；
- 主要 planner policy：fixed medium、adaptive `floor_weak`；
- 主要模型比较：`M3 - M0`、`M3 - M1`；
- 主要交互效应：

```text
(M3 - M0)_adaptive - (M3 - M0)_fixed_medium
```

- 主统计单位：独立 rollout，不是 temporal window；
- test split 不用于训练、模型选择、阈值选择或超参数调整。

## 3. Git 与执行快照

### 3.1 本地仓库

| 字段 | 值 |
| --- | --- |
| Repository | `Research-Project-IMLS` |
| Branch | `main` |
| Commit | `5d3ebc42f4882763561b70c652a465fc957c137f` |
| Commit time | `2026-07-26T23:27:08+08:00` |
| Commit subject | `feat: ablation` |

审计时本地 worktree 不干净：

```text
M  README.md
?? documentation work in progress
```

当时的中间计划和重复对比表已在后续文档清理中合并或删除；当前入口以 `docs/paper/README.md` 为准。

### 3.2 服务器仓库

服务器仓库路径：

```text
/root/autodl-tmp/Research-Project-IMLS
```

服务器与本地处于同一 commit：

```text
5d3ebc42f4882763561b70c652a465fc957c137f
```

服务器 branch 为 `main`，但 worktree 不干净：

```text
D  docs/paper/diagnose_supervisor_feedback_step1.py
?? core/scripts/carla/scenarios/generated/
?? core/scripts/models/l5kit_multipath_10_carla_interaction_transformer/
?? core/scripts/models/l5kit_multipath_10_carla_interaction_transformer_best/
?? core/scripts/models/l5kit_multipath_10_carla_interaction_transformer_history.json
?? core/scripts/models/l5kit_multipath_10_carla_interaction_transformer_training_log.csv
?? docs/paper/diagnose_supervisor_feedback_step1.py.disabled
?? gurobi/gurobi1103/
?? gurobi/gurobi1302/
```

以上清单是审计时刻的原始快照，其中出现的旧脚本名只用于说明当时服务器 worktree 的状态，不代表当前仓库仍依赖这些文件。

这意味着 commit SHA 能定位代码基线，但不能单独复现服务器当前模型资产。Day 2 之后必须生成模型 manifest，记录 checkpoint、训练配置、normalization、anchors、seed 和哈希。

## 4. Prediction dataset 审计

### 4.1 数据集位置与规模

服务器数据集根目录：

```text
core/results/20260726_212838_prediction_dataset_collection
```

目录总大小约：

```text
758 MB
```

采集配置：

| 字段 | 值 |
| --- | --- |
| init count | 50 |
| policy | `smpc_var_risk` |
| risk profile | `adaptive_interaction_severity` |
| raster | enabled |
| stride | 1 |
| future horizon | 10 steps |
| dt | 0.2 s |
| physical horizon | 2.0 s |

### 4.2 采集完整性

`batch_summary.txt` 显示：

- 50/50 subruns 执行成功；
- 50/50 scenarios 完成；
- 50/50 生成 result pickle；
- 每个 rollout 都存在 prediction dataset manifest；
- 没有 raster count 为零的 rollout。

Raster 汇总：

| 项目 | 数量 |
| --- | ---: |
| rollout directories | 50 |
| raster PNGs | 10,236 |
| per-rollout minimum | 193 |
| per-rollout maximum | 213 |
| zero-raster rollouts | 0 |

单场景抽查：

| Rollout | `sample_count` | `samples_with_any_future_label` |
| --- | ---: | ---: |
| init 01 | 198 | 97 |
| init 50 | 202 | 97 |

两个抽查 manifest 均为 `save_raster=1`、`stride=1`、`horizon=10`、`dt=0.2`。

### 4.3 Merged dataset

服务器目录：

```text
core/results/20260726_212838_prediction_dataset_collection/prediction_dataset_merged
```

| 文件 | 行数/样本数 | 大小 |
| --- | ---: | ---: |
| `all.jsonl` | 10,236 | 64,485,365 B |
| `train.jsonl` | 8,172 | 51,484,298 B |
| `val.jsonl` | 1,034 | 6,512,788 B |
| `test.jsonl` | 1,030 | 6,488,279 B |
| `manifest.json` | — | 3,567 B |

Manifest 中冻结的 rollout split：

| Split | Init IDs | Rollouts | Temporal windows | Valid samples |
| --- | --- | ---: | ---: | ---: |
| train | 01–40 | 40 | 8,172 | 3,881 |
| validation | 41–45 | 5 | 1,034 | 485 |
| test | 46–50 | 5 | 1,030 | 485 |
| all | 01–50 | 50 | 10,236 | 4,851 |

当前训练历史另记录可供完整 10-step future horizon 训练/评价的样本：

| Split | Full-horizon samples |
| --- | ---: |
| train | 2,441 |
| validation | 305 |
| test metrics | 305 |

`valid_sample_counts`、`samples_with_any_future_label` 与 `full-horizon samples` 是不同口径。Day 2 必须在审计脚本中显式命名并验证三种计数，论文中不得把 305 个 test temporal windows 写成 305 个独立场景。

### 4.4 本地与服务器差异

本地同名 result 目录目前只有：

```text
current_multipath_best_metrics_test.json
interaction_transformer_best_metrics_test.json
l5kit_multipath_10_carla_interaction_transformer_history.json
```

本地缺少 merged manifest、四个 JSONL、50 个 rollout manifests 和 rasters。它们没有丢失，而是仅保存在服务器。

## 5. 模型与训练产物审计

### 5.1 服务器模型

| 模型资产 | 状态 | 约大小 |
| --- | --- | ---: |
| `l5kit_multipath_10/` | 存在 | 37 MB |
| `l5kit_multipath_10_carla_finetuned_head_best/` | 存在 | 44 MB |
| `l5kit_multipath_10_carla_interaction_transformer/` | 存在 | 50 MB |
| `l5kit_multipath_10_carla_interaction_transformer_best/` | 存在 | 50 MB |

Interaction Transformer 的 final 与 best checkpoints 均包含 TensorFlow SavedModel 文件和 variables。训练日志与 history JSON 也存在。

当前 Interaction Transformer 训练配置摘要：

| 字段 | 值 |
| --- | --- |
| model family | `interaction_transformer_multipath_residual_adapter` |
| base model | CARLA-finetuned head best |
| anchors | `l5kit_clusters_16.npy` |
| epochs | 12 |
| batch size | 16 |
| learning rate | `5e-5` |
| horizon | 10 |
| context dimension | 8 |
| Transformer `d_model` | 64 |
| attention heads | 4 |
| feed-forward width | 128 |
| layers | 2 |
| residual delta scale | 0.15 |
| frozen base | true |
| best validation top-mode ADE | 0.025105983 |

### 5.2 已记录的哈希

| 资产 | SHA-256 |
| --- | --- |
| `l5kit_clusters_16.npy` | `52ab777b9bf695ed56f069b96cbce337014a47f457ed19c638abfb1cde6aa982` |
| base `saved_model.pb` | `94a2396d4a73dd6ae1726ab49b7923dd9a7135913ce9ae4caf12215b608ea9aa` |
| Transformer best `saved_model.pb` | `2616bf7df76b6183b3559acf556b6a53773c86f55e330d8a9b0027a72c49814d` |
| Transformer history JSON | `34102a6713d629351c5ef71ddbab9fd69740561f3de59950db28f1df39fabb2f` |

哈希只标识对应文件，不等价于完整 SavedModel 目录哈希。后续模型 manifest 应覆盖 variables、metadata、normalization 和 anchors。

### 5.3 本地缺口

本地已有：

- original MultiPath；
- CARLA-finetuned MultiPath best；
- fine-tuned head history；
- fine-tuned head training log。

本地缺少：

- Interaction Transformer final SavedModel；
- Interaction Transformer best SavedModel；
- 服务器上的 Interaction Transformer training log；
- 完整、可复现的 Transformer artifact manifest。

Day 2 优先拉取 Transformer best checkpoint、history、training log 和必要 metadata。final checkpoint 仅在复现或比较 best/final 时拉取。

## 6. 已有结果与运行环境

### 6.1 关键结果目录

服务器存在以下关键结果：

| 结果目录 | 约大小 | 作用 |
| --- | ---: | --- |
| `20260726_004504_init01_v12_close_stop_4p0_fixed_frontier_vs_adaptive` | 22 MB | base v12 pilot |
| `20260726_202206_init01_v13_A3_risk_owned_yield` | 68 MB | base A3 pilot |
| `20260726_233602_init01_v12_interaction_transformer_predictor` | 22 MB | Transformer v12 pilot |
| `20260726_235231_init01_v13_A3_interaction_transformer_predictor` | 68 MB | Transformer A3 pilot |

这四个关键结果目录也已存在于本地。它们继续作为 preliminary evidence，不构成 C01–C10 正式 confirmatory experiment。

服务器 `core/results` 总大小约 `3.1 GB`。

### 6.2 环境只读检查

| 资产 | 状态 |
| --- | --- |
| CARLA 0.9.14 root | 存在 |
| `CarlaUE4.sh` | 存在 |
| Conda `carla_modern` environment | 存在 |
| Gurobi 11.0.3 directory | 存在 |
| Gurobi license file | 存在，未读取内容 |
| CARLA/scenario/training processes | 审计时均未运行 |

Day 1 未激活环境，未加载模型，也未执行 Gurobi/CasADi 求解器测试。这些属于 Day 8 smoke test 的运行验证，不是 Day 1 资产存在性审计。

### 6.3 磁盘

| 文件系统 | 总量 | 已用 | 可用 | 使用率 |
| --- | ---: | ---: | ---: | ---: |
| data disk `/root/autodl-tmp` | 50 GB | 26 GB | 25 GB | 51% |
| system disk `/` | 30 GB | 25 GB | 5.9 GB | 81% |

数据盘足够支持两周实验。系统盘余量较小，后续不得把数据集、checkpoint 或 CARLA logs 写入系统盘。

## 7. 资产决策矩阵

| 资产 | 服务器 | 本地 | 决策 |
| --- | --- | --- | --- |
| merged manifest | 有 | 无 | Day 2 拉回 |
| train/val/test/all JSONL | 有 | 无 | Day 2 拉回，约 123 MB |
| 50 rollout manifests | 有 | 无 | Day 2 拉回 |
| 10,236 rasters | 有 | 无 | 保留服务器原位审计；暂不整包拉回 |
| M0 base checkpoint | 有 | 有 | 无需恢复 |
| fine-tuned M0 checkpoint | 有 | 有 | 无需恢复 |
| Transformer best checkpoint | 有 | 无 | Day 2 拉回并生成 artifact manifest |
| Transformer final checkpoint | 有 | 无 | 非必需；需要 best/final 对比时再拉 |
| Transformer history/log | 有 | history 仅部分存在 | Day 2 拉回服务器原件 |
| existing pilot results | 有 | 有 | 保留为 preliminary evidence |
| formal C01–C10 results | 无 | 无 | 计划于 Day 9–11 生成 |

结论：无资产需要重新采集或恢复；需要的是选择性拉取、完整性校验和可复现性登记。

## 8. 风险与约束

### R1：服务器未跟踪模型可能被代码同步覆盖

在同步前必须：

1. 先执行只读 `git status --short`；
2. 明确区分代码同步与 result/model artifact 同步；
3. 禁止使用带远端删除语义的盲目镜像；
4. 不覆盖服务器上的 Transformer checkpoints、training log 和 history；
5. 模型拉回本地并核对哈希后，再进行任何目录整理。

### R2：模型版本不能仅由 Git commit 标识

Transformer checkpoint 为服务器未跟踪目录。正式实验日志必须同时记录：

- Git commit；
- model identifier；
- model artifact hash；
- anchors hash；
- normalization metadata hash；
- training seed；
- dataset manifest hash。

### R3：独立 test rollout 数较小

Test 有 5 个独立 rollouts，但产生 305 个 full-horizon temporal windows。统计必须先按 rollout 聚合，frame/window 只能作为诊断单位，不得用于夸大有效样本量。

### R4：计数口径尚需程序化统一

10,236 个 raw windows、4,851 个 valid samples 和训练历史中的 full-horizon counts 并不矛盾，但当前命名不够自解释。Day 2 的审计器必须输出每个筛选阶段的计数和原因。

### R5：系统盘空间偏紧

训练输出、TensorBoard、cache 和 CARLA logs 必须写入 `/root/autodl-tmp`。Day 8 前再次检查磁盘空间。

## 9. Day 2 的确定入口

Day 2 只做数据完整性与 split audit，不开始模型训练。

顺序如下：

1. 从服务器选择性拉回：
   - merged `manifest.json`；
   - `train.jsonl`、`val.jsonl`、`test.jsonl`、`all.jsonl`；
   - 50 个 rollout `prediction_dataset_manifest.json`；
   - Transformer best checkpoint、history 和 training log；
   - collection config 与 batch summary。
2. 新增 `core/scripts/models/audit_prediction_dataset.py`。
3. 自动验证：
   - init 01–40 / 41–45 / 46–50 split；
   - episode/source subrun 不跨 split；
   - sample ID 不重复；
   - JSON 可解析；
   - 10-step horizon 与 `dt=0.2 s`；
   - raster 引用存在；
   - raw、valid、full-horizon 三级计数；
   - train/validation/test 的 context 与 label 基本统计。
4. 在服务器原位运行 raster existence audit，避免传输 758 MB 数据集。
5. 将机器可读 report 拉回本地并保存到 `docs/paper/generated/`。
6. 只有在确认无 leakage、无缺失 raster、计数可解释后，才进入 Day 3 calibration evaluator。

Day 2 完成门保持为：

```text
无 episode leakage，训练资产完整。
```

## 10. Day 1 checklist

- [x] 保存当前 local commit SHA；
- [x] 记录 local working tree 状态；
- [x] 冻结 C01–C10；
- [x] 冻结 primary/secondary metrics；
- [x] 登录服务器；
- [x] 检查 dataset、manifest、rasters、models 和 results；
- [x] 核对服务器 Git commit 和 worktree；
- [x] 核对已有结果目录和磁盘空间；
- [x] 确认未拉回本地的训练日志与 checkpoints；
- [x] 全程未修改服务器代码、未训练、未运行 CARLA。
