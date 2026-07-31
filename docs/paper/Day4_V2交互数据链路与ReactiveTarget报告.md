# Day 4：V2 交互数据链路与 Reactive Target 报告

> 执行日期：2026-07-31
>
> 实现 commit：`1c558326f066a906da4838add08266249dddf232`
>
> 云端 smoke：`/root/autodl-tmp/day4_v2_smoke_1c55832`
>
> 范围：init 01，S0/S1 × fixed/adaptive 各 1 个 rollout

## 1. Day 4 结论

Day 4 完成门已通过：

```text
代码可以生成 S0/S1 × fixed/adaptive 的单场景 V2 sample；
在线生成与离线读取的 raster 和 interaction feature 数值一致。
```

具体证据：

1. 四个 cell 均完成一个真实 CARLA rollout；
2. 四个 rollout 均生成 V2 JSONL、PNG raster 和 manifest；
3. 共生成 211 个 prediction windows；
4. 所有样本都包含 `6×12` interaction sequence 和长度为 6 的 mask；
5. smoke 中全部 token 有效；
6. 全部 raster 的离线读取 hash 与在线写入前 byte hash 一致；
7. 全部 interaction sequence 均可由原始对齐 world states 精确重建；
8. synthetic raster 的 pixel 与 ResNet-preprocessed tensor 往返差均为 0；
9. 真实 S1 adaptive sample 的 raster hash、sequence 和 mask 等价检查通过；
10. defensive-reactive target 在 fixed/adaptive 两条轨迹中都发生 trigger 和 release，没有停车。

Day 4 只证明数据链和行为机制可执行。Reactive 参数仍是 provisional，必须在 Day 5 使用 init 01–05 调试并冻结，不能把本次单 init smoke 当作行为效果结论。

## 2. V2 raster contract

冻结 ID：

```text
semantic_raster_cv2_bytes_resnet_caffe_v2
```

统一路径：

```text
SemBoxRasterizer in-memory uint8 bytes
→ cv2.imwrite(PNG)
→ cv2.imread(IMREAD_COLOR)
→ shared preprocess_resnet_raster
→ model
```

共享实现：

```text
core/scripts/models/prediction_input_contract.py
```

在线部署、离线 evaluator、fine-tuning loader 和真实 sample equivalence test 已改为调用同一模块。禁止 V2 loader 使用会隐式解释为 RGB 的通用 PNG decoder。

### 2.1 数值等价

| 检查 | 结果 |
| --- | ---: |
| Synthetic PNG pixel max abs diff | `0` |
| Synthetic preprocessed tensor max abs diff | `0` |
| Synthetic raster SHA-256 equal | `true` |
| Real sample stored/loaded raster SHA-256 equal | `true` |

每个 V2 sample 同时记录：

```text
raster_contract_id
raster_uint8_sha256
raster_relpath
```

因此后续 merge/audit 可以检测图片丢失、损坏或错误读取。

## 3. Interaction sequence

共享实现：

```text
core/scripts/models/interaction_sequence.py
```

### 3.1 时间轴

```text
[-1.0, -0.8, -0.6, -0.4, -0.2, 0.0] s
```

输出：

```text
interaction_sequence:      [6, 12]
interaction_sequence_mask: [6]
```

### 3.2 每个 token 的 12 个字段

```text
time_offset_s
ego_rel_x_m
ego_rel_y_m
target_rel_x_m
target_rel_y_m
ego_speed_mps
target_speed_mps
relative_longitudinal_speed_mps
relative_lateral_speed_mps
sin_relative_yaw
cos_relative_yaw
ego_target_distance_m
```

坐标系为 prediction time 的 current-target-local RHS frame。所有历史位置和速度均使用当前 target pose 变换，避免每个 token 使用不同局部坐标系。

### 3.3 历史速度与对齐

`AgentHistory` 现在同时保存：

```text
timestamp
RHS pose
RHS velocity = [CARLA vx, -CARLA vy]
```

每个 actor 独立匹配最近 timestamp，不再使用任意一个 vehicle 的数组 index 强制索引其他 actor。对齐容差为 `0.1 s`。

若 ego 或 target 任一状态缺失：

```text
mask = 0
12 个 feature 全部填 0
```

### 3.4 可审计性

V2 sample 不只保存最终 feature，还保存：

```text
interaction_history_world
```

离线侧重新调用同一个 `build_interaction_sequence()`，而不是信任已保存数组。本次 211 个样本的重建最大绝对差均为 0。

`target_style`、`ego_policy`、`cell_id` 和 `ego_init_id` 只作 metadata/audit/subset evaluation，禁止作为 predictor input。

## 4. Defensive-reactive target

实现：

```text
core/scripts/carla/policies/defensive_reactive_agent.py
```

它保持 priority target 的直线路径，不调用预测模型，只使用 actor 当前物理状态。

### 4.1 Trigger 输入

每步计算：

```text
target signed distance to conflict
ego distance to conflict
target TTC
ego TTC
arrival-time gap
constant-velocity closest-approach time
constant-velocity closest-approach distance
```

当双方位于 activation zone，且 arrival timing 或 closest approach 表明冲突时进入 active 状态。

### 4.2 行为约束

当前 provisional 参数：

| 参数 | Day 4 值 |
| --- | ---: |
| nominal speed | `9.0 m/s` |
| caution desired speed | `4.5 m/s` |
| minimum desired speed before conflict | `2.5 m/s` |
| activation distance | `30 m` |
| arrival-time gap | `2.0 s` |
| closest-approach horizon | `4.0 s` |
| closest-approach distance | `6.0 m` |
| max deceleration | `-2.0 m/s²` |
| release hold | `0.8 s` |
| post-conflict release clearance | `5.0 m` |

这些值没有冻结。Day 5 必须根据 init 01–05 的 trigger coverage、实际减速、抖动和安全性决定是否修改。

### 4.3 每步记录

`scenario_steps.csv` 新增：

```text
target0_reactive_active
target0_reactive_triggered_this_step
target0_reactive_released_this_step
target0_reactive_target_conflict_distance_m
target0_reactive_ego_conflict_distance_m
target0_reactive_target_ttc_s
target0_reactive_ego_ttc_s
target0_reactive_arrival_time_gap_s
target0_reactive_closest_approach_time_s
target0_reactive_closest_approach_distance_m
target0_reactive_desired_speed_mps
target0_speed
target0_throttle
target0_brake
```

同一步控制完成后，相关 diagnostics 也写入 prediction sample，避免记录上一步状态。

## 5. 四单元真实 CARLA smoke

运行入口：

```text
core/scripts/carla/run_give_way_prediction_dataset_v2.sh
```

Day 4 使用：

```text
INIT_START=1
INIT_END=1
LOG_STRIDE=4
```

四个 cell：

| Cell | Target | Ego policy | Rollout | Samples | Valid tokens |
| --- | --- | --- | ---: | ---: | ---: |
| S0_FIXED | assertive constant-speed | fixed medium | 1 | 52 | 312 |
| S0_ADAPTIVE | assertive constant-speed | adaptive floor_weak | 1 | 51 | 306 |
| S1_FIXED | defensive reactive | fixed medium | 1 | 54 | 324 |
| S1_ADAPTIVE | defensive reactive | adaptive floor_weak | 1 | 54 | 324 |
| Total |  |  | 4 | 211 | 1,266 |

四个 rollout 的 `ran_successfully=true`。S0 fixed/adaptive 与 S1 fixed/adaptive 均能沿原有预测与 SMPC 链路运行。

### 5.1 Reactive diagnostics

| Metric | S1 fixed | S1 adaptive |
| --- | ---: | ---: |
| Trigger events | 2 | 2 |
| Release events | 2 | 2 |
| Active steps | 44 | 44 |
| Minimum actual speed while active | `8.0018 m/s` | `8.0018 m/s` |

当前 rule 能响应 ego，并存在 trigger/release hysteresis；但实际减速仅约 `1 m/s`。这可能不足以形成明显的 future-trajectory separation，也出现一次 rollout 内二次 trigger。它不是代码缺陷，但属于 Day 5 必须检查和调参的实验设计风险。

## 6. 新增审计器

### 6.1 输入等价

```text
core/scripts/models/verify_prediction_input_contract.py
```

检查：

- synthetic raster pixel/preprocess equivalence；
- synthetic sequence/mask reconstruction；
- 真实 sample 必需字段；
- 真实 raster byte hash；
- 真实 sequence/mask reconstruction；
- masked token zero-fill。

### 6.2 四单元 smoke audit

```text
core/scripts/models/audit_prediction_dataset_v2_smoke.py
```

检查：

- 四个预期 cell；
- target style 与 ego policy 映射；
- 每个 rollout 非空；
- 所有 V2 required fields；
- 所有 raster hash；
- 所有 interaction features；
- trigger/release/active/minimum-speed diagnostics。

本次输出：

```text
status = pass
errors = []
```

## 7. Day 5 必须完成的参数冻结

只允许使用 init 01–05：

1. 运行 5 inits × 4 cells；
2. 对 S1 统计至少一次 trigger 的 rollout 比例；
3. 统计 active-time fraction，避免永不触发或几乎全程 active；
4. 检查每次 trigger/release 的间隔，防止短周期反复切换；
5. 检查 target 最低速度、加速度和 jerk；
6. 检查 S1 相对对应 S0 的 future displacement separation；
7. 检查 collision、minimum clearance 和 rollout completion；
8. 若实际减速仍过弱，优先延长 active duration或调整 release hysteresis，而不是使用更激烈的最大减速度；
9. 参数冻结后写入 protocol manifest；
10. Day 6 正式 50-init 数据采集不得再改参数。

建议 Day 5 的主要可接受区间：

```text
S1 trigger rollout coverage: 20%–80%
active time fraction:        5%–35%
minimum target speed:        > 2.5 m/s
collision count:             0
短周期 re-trigger:           需要消除或给出明确物理解释
S1/S0 future separation:     必须明显大于记录噪声
```

这些范围是 development gate，不是论文结果。

## 8. 机器可读证据

```text
docs/paper/generated/day4/day4_input_contract_real_sample.json
docs/paper/generated/day4/day4_v2_smoke_audit.json
```

云端完整 raster、JSONL、scenario results 和 step logs 保留在：

```text
/root/autodl-tmp/day4_v2_smoke_1c55832
```

## 9. 论文边界

Day 4 可以支持：

```text
The V2 collection pipeline exposes aligned ego-target history without using
treatment labels as model inputs, and preserves identical raster bytes and
feature construction between online generation and offline loading.
```

Day 4 不能支持：

- reactive target 参数已最优；
- interaction-aware Transformer 已提高预测；
- adaptive risk 优于 fixed risk；
- S1 是自然驾驶行为；
- 单 init 的 trigger 次数可以推广到 50 inits。
