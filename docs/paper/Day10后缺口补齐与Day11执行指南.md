# Day10 后证据缺口补齐与 Day11 执行指南

> 状态：冻结执行方案（2026-08-02）
>
> 原则：不改变 Day8 模型选择，不回写 Day10 结果，不根据 test/诊断结果继续调参。

## 1. 为什么需要补齐

Day1–Day10 已经形成可写的主体证据，但仍有四个会影响答辩严谨性的缺口：

1. Day10 的 raw completion time 混入了目标车清空冲突区的绝对时刻；
2. B0 没有经过与 B1 同口径的 frozen offline evaluation；
3. T1/T2 虽然是 Transformer，但尚未证明模型实际使用了交互序列；
4. Day10 只在 target offset = 0 m 下闭环评估，外推边界较窄。

补齐顺序固定如下：

```text
Gap 1 目标清空时刻校正
  -> Gap 2 B0 frozen offline bridge
  -> Gap 3 T1/T2 context ablation
  -> Gap 4 Day11 ±3 m timing-shift robustness
```

前三项不新增训练；第四项复用 Day10 的模型、校准器、A3 controller、held-out init 46–50 和评估链路。

## 2. Gap 1：目标清空时刻校正（已完成）

正式效率指标改为：

```text
target_clearance_adjusted_completion_delay
= rollout_start_time + completion_time - target_exit_time
```

分析器同时验证：

```text
rollout_start_time + completion_time == rollout_end_time
```

80 条 Day10 rollout 的时钟残差均为 0。该指标避免把不同 target style 的清空时刻差异错误归因给 ego predictor 或 risk policy。原始 completion time 保留为描述性指标，不再用于跨 style 的主效率结论。

## 3. Gap 2：B0 frozen offline bridge（已完成）

### 3.1 目的

用同一 Day7 test population 比较 B0 与 frozen B1，并同时报告两种口径：

- uncalibrated：identity decoder 下的模型适配差异；
- calibrated：各自在 validation-only 上拟合 calibration 后的部署包差异。

Day10 中 B0 仍保持 identity calibration；本实验不会事后替换 Day10 的 B0。

### 3.2 控制变量

- 数据、split、subset、anchors、horizon、batch evaluator 完全一致；
- B0 权重哈希必须等于 Day10 contract；
- calibration 只能在 validation split 拟合；
- test 只用于 reporting，不用于选择、训练或调参。

### 3.3 完成标志

```text
/root/autodl-tmp/results/give_way_transformer/day10_gaps/b0_offline_v1/B0_OFFLINE_COMPLETE.json
```

## 4. Gap 3：T1/T2 交互序列诊断（已完成）

### 4.1 实验组与对照组

对照组是 Day8 已保存的原始 frozen test 结果。实验组不训练模型，只改变序列输入：

| 组别 | 序列处理 | 其他输入/标签/权重/校准 |
| --- | --- | --- |
| Original | 不改变 | 冻结 |
| Zero | valid token 替换为 train-only normalization mean；归一化后严格为 0 | 冻结 |
| Shuffle | 从不同 ego init 确定性借用 sequence + mask | 冻结 |

Shuffle 保持 receiver 的 raster、target history 和 future label 不变，因此测量的是交互序列错配造成的性能变化，而不是重新采样测试集。

### 4.2 判定规则

若 ablated − original 的 ADE/FDE/NLL 为正，说明移除或错配交互序列使预测恶化，支持模型确实使用了序列信息。若接近 0 或为负，则不能声称 Transformer 的优势来自 interaction modelling。

这是 post-selection diagnostic，不是新的模型竞赛；任何结果都不得触发重新选择 seed 或调参。

### 4.3 完成标志

```text
/root/autodl-tmp/results/give_way_transformer/day10_gaps/context_ablation_v1/CONTEXT_ABLATION_COMPLETE.json
```

## 5. Gap 4：Day11 局部时序稳健性

### 5.1 实验矩阵

```text
2 predictors: B1, B0
x 2 risk policies: fixed-medium, adaptive floor_weak
x 2 target styles: assertive, reactive
x 2 target start offsets: -3 m, +3 m
x 5 held-out inits: 46–50
= 80 rollouts
```

不重跑 Day10 的 offset = 0 m，也不扩大到新的地图、天气或路线。±3 m 是对原有 give-way 场景的局部扰动，用来判断 predictor/risk 结论是否只在单一到达关系成立。

### 5.2 预注册比较

主要比较在运行前固定：

1. 每个 policy 下，B1 − B0，跨 offset/style 配对汇总；
2. 每个 predictor 下，adaptive − fixed-medium，跨 offset/style 配对汇总；
3. predictor × offset interaction；
4. policy × offset interaction。

分析单位是 rollout condition `(ego_init_id, target_style, target_offset)`，不是 20 Hz simulator step。主要指标沿用 Day10：

- target-clearance-adjusted completion delay；
- minimum footprint separation；
- solver failure fraction；
- supervisor active fraction。

碰撞和让行顺序仍是先决安全 gate。

### 5.3 解释边界

- 两个 offset 方向一致：支持“在 ±3 m 局部时序扰动下稳健”；
- predictor × offset 明显：模型作用依赖到达关系，应写成 conditional effect；
- adaptive × offset 明显：adaptive risk 不是普遍优势，而是场景时序相关；
- 不论结果如何，都不能外推到其他地图、天气或交通参与者类别。

## 6. 服务器执行顺序

每次更新服务器代码前：

```bash
cd /root/autodl-tmp/Research-Project-IMLS-day8
source /etc/network_turbo
git pull --ff-only origin main
```

先执行 Gap 2：

```bash
PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python \
bash core/scripts/models/run_b0_frozen_offline_evaluation.sh
```

通过完成标志后再执行 Gap 3：

```bash
PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python \
bash core/scripts/models/run_interaction_context_ablation.sh
```

Day11 需要 CARLA server 已启动、Gurobi 可用：

```bash
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
PYTHON_BIN=/root/miniconda3/envs/carla_modern/bin/python \
bash core/scripts/carla/run_day11_timing_shift_robustness.sh
```

三个 runner 都具有：完成标志短路、活进程锁、已验证输出跳过、无效旧输出拒绝覆盖。服务器中断后使用相同命令续跑即可。

## 7. 结果回传

通知本地分析前，分别确认：

```bash
cat /root/autodl-tmp/results/give_way_transformer/day10_gaps/b0_offline_v1/B0_OFFLINE_COMPLETE.json
cat /root/autodl-tmp/results/give_way_transformer/day10_gaps/context_ablation_v1/CONTEXT_ABLATION_COMPLETE.json
cat /root/autodl-tmp/results/give_way_transformer/day11/day11_timing_shift_v1/DAY11_COMPLETE.json
```

Day11 runner 会在完成审计后自动执行预注册分析。若只需重新生成分析，可执行：

```bash
python core/scripts/models/analyze_day11_timing_shift.py \
  --results-dir /root/autodl-tmp/results/give_way_transformer/day11/day11_timing_shift_v1 \
  --output-dir /root/autodl-tmp/results/give_way_transformer/day11/day11_timing_shift_v1/analysis
```

随后只需回传三个小型 snapshot 及其 `.json` manifest；模型权重、raster 和视频不会进入压缩包。
