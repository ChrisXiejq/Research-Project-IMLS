# Day 2：数据审计与 V2 协议冻结报告

> 执行日期：2026-07-31
>
> 旧数据集：`20260726_212838_prediction_dataset_collection`
>
> 服务器训练基线 commit：`5d3ebc42f4882763561b70c652a465fc957c137f`
>
> Day 2 本地起点 commit：`709c5b8b30a8e0bcba793cadb6c852da1116283e`

## 1. 结论

Day 2 完成门已通过。

1. 旧 prediction dataset 没有 init、source subrun 或复合 sample ID leakage；
2. 10,236 个 raster 引用全部存在；
3. horizon、`dt`、merged manifest 和 50 个 rollout manifest 一致；
4. base raster 已确认包含 ego occupancy/history；
5. 旧数据被正式限定为 deterministic negative-control pilot，不能用于证明 interaction-aware learning；
6. V2 interaction feature schema 已冻结；
7. 50 inits × 2 target styles × 2 ego policies 的 200-rollout collection matrix 已程序化冻结；
8. 旧 Transformer best checkpoint、history、training log、anchors 和文件哈希已登记并拉回本地。

Day 3 可以进入 deployment-equivalent GMM evaluator 与 calibration，不需要重新采集旧数据或重新训练旧模型。

## 2. 旧数据完整性审计

### 2.1 审计工具

新增：

```text
core/scripts/models/audit_prediction_dataset.py
```

服务器执行了完整模式：

```bash
python audit_prediction_dataset.py \
  --merged-dir /root/autodl-tmp/Research-Project-IMLS/core/results/20260726_212838_prediction_dataset_collection/prediction_dataset_merged \
  --result-dir /root/autodl-tmp/Research-Project-IMLS/core/results/20260726_212838_prediction_dataset_collection \
  --output-json /root/autodl-tmp/Research-Project-IMLS/core/results/20260726_212838_prediction_dataset_collection/day2_audit/legacy_dataset_audit.json \
  --check-rasters \
  --check-raster-content \
  --raster-content-samples 200
```

审计器退出状态为 `pass`，没有 failing checks。

### 2.2 计数口径

| Split | 独立 rollouts | Raw windows | 带任意未来标签 | 完整 10-step horizon |
| --- | ---: | ---: | ---: | ---: |
| Train, init 01–40 | 40 | 8,172 | 3,881 | 2,441 |
| Validation, init 41–45 | 5 | 1,034 | 485 | 305 |
| Test, init 46–50 | 5 | 1,030 | 485 | 305 |
| 总计 | 50 | 10,236 | 4,851 | 3,051 |

三种计数分别表示：

- `raw windows`：logger 写出的全部预测时刻；
- `带任意未来标签`：至少有一个有效 future step；
- `完整 horizon`：10 个 future steps 全部有效，可进入当前完整轨迹训练和正式 test metric。

因此论文中必须写“5 个 test rollouts 产生 305 个 full-horizon temporal windows”，不能写成“305 个独立测试场景”。

### 2.3 Sample identity

V1 的 `sample_id` 在每个 rollout 中从 0 重新开始。审计发现 212 个 raw sample ID 数值会跨 rollout 重复，这是预期行为，不是数据重复。

唯一 ID 定义冻结为：

```text
source_subrun + "::" + sample_id
```

使用复合 ID 后：

- train、validation、test 内均无重复；
- `all.jsonl` 与三个 split 的集合并集完全相等；
- source subrun 不跨 split；
- ego init 不跨 split；
- init 01–40 / 41–45 / 46–50 覆盖完整。

### 2.4 Horizon、时间步和 manifest

全部 samples 满足：

```text
horizon_steps = 10
dt = 0.2 s
```

检查结果：

| Check | 结果 |
| --- | --- |
| JSONL 可解析 | PASS |
| merged manifest counts | PASS |
| 50 个 rollout manifest | PASS |
| rollout manifest raw total = 10,236 | PASS |
| rollout manifest any-label total = 4,851 | PASS |
| `all.jsonl` = split union | PASS |
| horizon 一致 | PASS |
| `dt` 一致 | PASS |

### 2.5 Raster 完整性与 ego 可见性

服务器原位检查：

```text
10,236 checked
0 missing
```

代码路径也证明 raster 包含 ego：

1. `AgentHistory` 由全部 `vehicle_actors` 构造；
2. `BoxRasterizer` 将除 target 之外的车辆画为黄色；
3. ego 属于 `vehicle_actors`；
4. prediction raster 由同一个 `AgentHistory` 生成。

同时进行了像素级验证。抽查前 200 个 samples，其中 52 个 sample 的 ego 投影中心位于 raster 画布内；52/52 都在预测位置半径 25 pixels 内检测到当前时刻的黄色车辆层：

```text
eligible = 52
ego vehicle-colour hits = 52
hit rate = 1.0
```

因此 B0/B1 都不能在论文中被描述为“没有 ego 信息的 target-only raster baseline”。未来 context ablation 的严格定义必须是：

```text
相同 base raster + 相同 target history；
只删除显式 interaction sequence side channel。
```

## 3. V1 数据分布与研究边界

### 3.1 基本分布

| Split | Ego speed mean | Target speed mean | Ego-target distance mean | 有标签样本 final displacement mean |
| --- | ---: | ---: | ---: | ---: |
| Train | 3.434 m/s | 9.011 m/s | 42.028 m | 14.752 m |
| Validation | 3.462 m/s | 9.011 m/s | 42.485 m | 14.751 m |
| Test | 3.480 m/s | 9.011 m/s | 42.055 m | 14.751 m |

三个 split 的 target speed 和 label displacement 分布几乎相同，这与恒速 `StraightLineAgent` 数据生成机制一致。

### 3.2 为什么旧数据只能是 negative-control pilot

旧数据只有：

```text
target style = assertive constant-speed
ego policy = adaptive smpc_var_risk
```

target 不读取 ego state，因此：

```text
P(target future | target history, ego history)
≈ P(target future | target history)
```

即使 Transformer 在旧数据上降低 ADE/FDE，也不能据此声称模型学到了 interaction。它最多说明：

- residual adapter 有拟合能力；
- raster/target history 的表示可能改善；
- 静态 context 或额外参数容量可能改变误差；
- 但 interaction-conditioning 尚未被识别。

旧数据从现在开始固定标记为：

```text
dataset_role = deterministic_negative_control_pilot_only
```

## 4. V2 interaction sequence schema

生成器：

```text
core/scripts/models/build_prediction_dataset_v2_protocol.py
```

冻结 schema：

```text
core/scripts/models/protocols/give_way_interaction_sequence_v2.schema.json
```

### 4.1 Shape 与历史时刻

```text
history_times_s = [-1.0, -0.8, -0.6, -0.4, -0.2, 0.0]
interaction_sequence shape = [6, 12]
interaction_sequence_mask shape = [6]
```

12 个 token fields：

1. `time_offset_s`
2. `ego_rel_x_m`
3. `ego_rel_y_m`
4. `target_rel_x_m`
5. `target_rel_y_m`
6. `ego_speed_mps`
7. `target_speed_mps`
8. `relative_longitudinal_speed_mps`
9. `relative_lateral_speed_mps`
10. `sin_relative_yaw`
11. `cos_relative_yaw`
12. `ego_target_distance_m`

所有历史位置和速度统一转换到 prediction time 的 current target-local RHS frame。缺失 token 使用：

```text
features = zero-filled
mask = 0
```

模型必须使用 mask，禁止把缺失历史解释为真实零状态。

### 4.2 Normalization

正式 V2 规定：

- 只用 train split、四个 cells 的有效 tokens 计算 mean/std；
- validation/test 不参与 normalization；
- masked tokens 不参与统计；
- mean、std、feature names、history times 和 schema ID 随 checkpoint 保存；
- online CARLA 与 offline evaluator 调用同一 feature builder。

### 4.3 不允许输入模型的标签

以下字段只用于 audit、subset evaluation 和 paired statistics，不得输入 predictor：

```text
target_style
ego_policy
split
ego_init_id
```

否则模型可能直接读取行为类别，而不是从 observed history 推断 target response。

### 4.4 与当前 AgentHistory 的衔接

现有 `AgentHistory.query()` 已支持：

```text
[1.0, 0.8, 0.6, 0.4, 0.2, 0.0] s
```

且由全部 scenario vehicles 构造，因此 aligned ego/target pose history 可以稳定提取。当前 `ActorInfo` 只保存 pose，不保存 velocity；Day 4 必须增加 velocity history，或以明确的 masked finite difference 计算速度，不能用当前单帧速度复制成 6 个 tokens。

## 5. 200-rollout collection matrix

冻结 manifest：

```text
core/scripts/models/protocols/give_way_interaction_v2_collection_manifest.json
```

矩阵：

| Cell | Target style | Ego policy | Rollouts | 作用 |
| --- | --- | --- | ---: | --- |
| S0_FIXED | assertive constant-speed | fixed medium | 50 | non-reactive fixed-policy control |
| S0_ADAPTIVE | assertive constant-speed | adaptive floor_weak | 50 | non-reactive adaptive-policy control |
| S1_FIXED | defensive reactive | fixed medium | 50 | interaction-positive fixed-policy data |
| S1_ADAPTIVE | defensive reactive | adaptive floor_weak | 50 | interaction-positive adaptive-policy data |

总计：

```text
50 inits × 4 cells = 200 rollouts
train = 160
validation = 20
test = 20
```

Manifest 显式列出 200 个唯一 `rollout_id`。同一 init 的四个 cells 由 `ego_init_id` 分组，必须进入同一 split：

```text
train: 01–40
validation: 41–45
test: 46–50
```

Defensive-reactive target 的具体 trigger、release、minimum speed 和恢复参数仍标记为 `pending Day 5 development freeze`。这不是协议遗漏：Day 4 实现，Day 5 只允许用 init 01–05 冻结数值，Day 6 正式采集后禁止再调整。

## 6. 旧 Transformer 模型资产

新增：

```text
core/scripts/models/build_model_artifact_manifest.py
```

服务器检查结果：

```text
status = pass
missing assets = []
SavedModel files = 5
total model bytes = 51,379,891
```

已登记：

- Transformer best SavedModel 的全部文件 SHA-256；
- history JSON；
- training CSV；
- anchors；
- training commit；
- seed；
- normalization 行为；
- 模型角色和限制。

服务器报告与拉回本地的 checkpoint、history、log 和 anchors 哈希完全一致。

这个 artifact 被固定命名为：

```text
legacy_interaction_transformer_negative_control_pilot
```

它使用 8D 单帧 context，并将同一 context 重复到时间维；context 没有显式 z-score normalization。它不是正式 V2 interaction-sequence model。

大文件保存在 Git 忽略的：

```text
core/results/20260726_212838_prediction_dataset_collection/day2_local_assets/
```

Git 只保存 schema、manifest、审计代码和机器可读报告，不提交 123 MB JSONL 或 51 MB checkpoint。

## 7. 机器可读证据

```text
docs/paper/generated/day2/legacy_dataset_audit.json
docs/paper/generated/day2/legacy_transformer_best_artifact_manifest.json
docs/paper/generated/day2/rollout_manifests_consolidated.json
core/scripts/models/protocols/give_way_interaction_sequence_v2.schema.json
core/scripts/models/protocols/give_way_interaction_v2_collection_manifest.json
```

## 8. Day 2 checklist

- [x] merged manifest 与 JSONL metadata 已读取；
- [x] 数据审计器已实现；
- [x] split leakage 已检查；
- [x] 复合 sample ID 已冻结；
- [x] raster existence 已全量检查；
- [x] base raster 的 ego layer 已经代码与像素双重验证；
- [x] raw/any-label/full-horizon 计数已统一；
- [x] ego/target/context/label 基本分布已输出；
- [x] V1 研究角色已限定；
- [x] V2 feature schema 已冻结；
- [x] dataset version 已冻结；
- [x] 200-rollout matrix 已冻结；
- [x] Transformer best 资产已拉回并校验哈希；
- [x] Day 2 机器可读报告已保存。

## 9. Day 3 的确定入口

Day 3 不训练新模型，先修正和统一概率预测 evaluator：

1. 对齐 evaluator 与 `DeployMultiPath._make_gmm()`；
2. 新增 mixture NLL；
3. 新增二维 covariance coverage；
4. 审计 invalid covariance；
5. 增加 rollout-level aggregation；
6. 量化 `exp(abs(raw))` 对 coverage 的影响；
7. 只在 validation 上拟合 temperature/covariance scaling；
8. 建立同一 raw output 的 offline/online equivalence test。

进入 Day 3 时使用：

```text
V1 旧数据：negative-control calibration/evaluator development
V2 schema：未来正式模型的输入契约
Transformer T0：legacy pilot，不作为正式 interaction 结论
```
