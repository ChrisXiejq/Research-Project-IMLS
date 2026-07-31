# Day 5 开发实验与 Reactive 参数冻结报告

日期：2026-07-31

开发数据：init 01–05

实验矩阵：5 inits × 2 target styles × 2 ego policies = 20 rollouts

行为代码版本：`6b71ccc`
云端有效结果：`/root/autodl-tmp/results/give_way_transformer/day5/final/day5_final_6b71ccc`

## 1. 结论

Day 5 已完成，defensive-reactive target 参数可以冻结并进入 Day 6 正式采集。

最终审计：

```text
status: pass
rollouts: 20/20
logged prediction samples: 1055
audit gates: 19/19
native CARLA collision events: 0
reactive trigger rollout coverage: 80%
mean reactive active fraction: 5.29%
minimum target speed: 4.124 m/s
trigger onset range: 0.75–0.85 s
maximum trigger count per rollout: 1
minimum full-rate centroid clearance: 3.800 m
median paired S1–S0 maximum target separation: 4.880 m
```

全部 19 个冻结 gate 为 true，包括 raster/sequence 等价、单次 trigger、trigger/release 成对、非首步触发、trigger timing variation、速度恢复、控制命令无抖动、原生零碰撞、S1–S0 separation 和参数一致性。

证据：

```text
docs/paper/generated/day5/day5_final_6b71ccc_audit.json
docs/paper/generated/day5/day5_final_6b71ccc_frozen_config.json
```

## 2. Day 4 正确性复核

Day 4 的输入数据链结论仍成立：

1. 在线 raster 与保存后 `cv2.imread` 的 canonical bytes 完全相同；
2. ResNet preprocessing tensor 完全相同；
3. 6×12 interaction sequence 可由原始 history 精确重建；
4. mask、速度、坐标变换和同控制步 diagnostics 对齐有效。

但 Day 4 的 reactive 行为证据存在一个实质性几何错误：原实现用 ego 起点—终点直线弦与 target 直线求交。ego 是左转车辆，该弦不等于真实参考路线。旧 trigger/release 数值因此不能用作行为冻结证据。

Day 5 前置修复：

1. 冲突点改为 SMPC 同源的 `ego_reference_route_target_motion_line`；
2. 当前 Town05 route conflict point 约为 `[28.48, 3.55] m`；
3. release 后锁存，不允许同一次穿越再次 trigger；
4. 为 ego/target 加入 CARLA 原生 collision sensor；
5. 修复 full-rate pickle 状态列定义为 `[timestamp, x, y, yaw, speed]`；
6. paired S1–S0 按 rollout-relative time 对齐，不使用 CARLA 全局 uptime。

因此，对 Day 4 的最终判断是：输入链正确，旧 reactive 参数实验无效；经 Day 5 几何、状态机和审计修复后，行为链正确。

## 3. 为什么拒绝旧参数

Day 4 provisional 参数为：

```text
activation_distance_m = 30.0
arrival_time_gap_s = 2.0
hazard = TTC OR closest approach
```

在 init01–05 的 S1_FIXED pilot 中，5/5 rollout 都在首个控制步 trigger。虽然每条轨迹只有一次 trigger，active fraction 约 20%，也没有碰撞，但该机制等价于“场景一开始立即减速”，不能形成有意义的 interaction timing variation。

因此旧参数被拒绝，相关云端目录已带 `PILOT_IMMEDIATE_TRIGGER` 后缀隔离，禁止用于训练或论文统计。

## 4. 参数选择方法

参数不是通过反复跑 S1 追求好看结果选择的。使用已完成的 10 条 S0 counterfactual 轨迹，对 activation distance、arrival gap 和 hazard conjunction 做离线扫描。

选择原则预先固定为：

1. trigger coverage 不是 0，也不是所有条件全程 active；
2. trigger 不发生在首步；
3. onset 随 init timing 改变；
4. 至少保留一个未触发 counterfactual；
5. target 不停车、能恢复且不碰撞；
6. S1 future 与 S0 有超过数值噪声的分离。

离线扫描预测当前候选在 10 个 S1 配对中触发 8 个，onset 为 0.75–0.85 s，init03 不触发。正式 Day 5 结果与预测完全一致。

## 5. 冻结参数

```text
controller: DefensiveReactiveAgent
nominal_speed_mps: 9.0
caution_speed_mps: 4.5
minimum_speed_mps: 2.5
activation_distance_m: 10.0
release_clearance_m: 5.0
arrival_time_gap_s: 0.5
closest_approach_time_s: 4.0
closest_approach_distance_m: 6.0
release_hold_s: 0.8
max_accel_mps2: 1.5
max_decel_mps2: -2.0
conflict_geometry: ego_reference_route_target_motion_line
episode_semantics: single_trigger_latched_release
hazard_combination: ttc_conflict_and_closest_approach
```

哈希：

```text
reactive_parameters_sha256:
188ea5a1e3a34cde06eed16e779a252058476c5ab3d3dfda3a870000d92e77d5

collection_config_sha256:
b047c70f238501f4c6de5b359dc18dc0db821da8d7bb8ab65501d8c2785e3b05

formal_init_set_sha256:
768228e53474e97eac574511a31265d193182dd3d96313b368c967c2f1b3dcc6
```

完整 collection hash 还覆盖：

- prediction model weights 与 anchors；
- stride、horizon、raster logging 和 dt；
- adaptive risk mapping；
- collection/batch/scenario runner、reactive/straight-line target agent、raster/history、prediction deployment/input contract、GMM、scenario、intersection geometry 和 tuning config 等 13 个关键源文件哈希；
- 正式 50 个 init 文件的组合哈希；
- 四个 cells 和 200-rollout 设计。

Day 6 开始后不得再调整上述行为参数。

## 6. 行为结果

10 个 S1 rollout 中 8 个触发，两个未触发均为 init03 在 fixed/adaptive 两种 ego policy 下的配对 counterfactual。

触发 onset：

```text
0.75, 0.80, 0.85 s
range = 0.10 s
```

这说明 rule 不是按固定 rollout 时刻执行。相同 init03 在两个 ego policy 下都不触发，也说明 S1 style 标签本身不会强制减速。

active fraction 的总体平均值为 5.29%，没有 rollout 全程 active。每条触发轨迹最多一次 trigger，并有恰好一次对应 release。最低速度 4.124 m/s，高于冻结下限 2.5 m/s；所有 reactive rollout 最终速度均恢复至至少 8.0 m/s。

## 7. 安全结果

20 条 rollout 的 CARLA 原生 collision event 总数为 0。

full-rate state trajectory 的最小 ego-target centroid clearance 为 3.800 m。该值作为 proximity diagnostic；碰撞结论以 CARLA collision sensor 为主证据。

## 8. S1–S0 future separation

按相同 ego policy、相同 init 和 rollout-relative time 对齐 target trajectory：

```text
10 paired contrasts
median maximum separation = 4.880 m
```

init03 的 separation 约为 `5e-5–8e-5 m`，符合未触发 counterfactual 的数值噪声水平。其他触发配对的最大 separation 为 1.343–5.200 m。

因此数据同时包含：

1. 明确的 interaction-positive trajectory change；
2. 不发生 response 的 matched counterfactual；
3. fixed/adaptive ego distributions；
4. pre-response 与 active-response windows。

这比“所有 reactive 标签都减速”的数据更适合检验 Transformer 是否利用时序 interaction，而不是读取 style shortcut。

## 9. 对论文论点的边界

Day 5 可以支持：

1. 构建了受控、ego-state-dependent 的 reactive data extension；
2. 该 extension 安全、可重复，并形成明显 future separation；
3. 数据包含未触发 counterfactual，可用于排除简单 style shortcut；
4. 正式 Transformer 实验具备可识别的 interaction signal。

Day 5 不能单独支持：

1. Transformer 已经提高预测性能；
2. adaptive risk 优于 fixed risk；
3. reactive controller 是人类驾驶模型；
4. 结果可推广到所有路口或交通参与者。

这些结论必须分别由 Day 6–10 的正式数据、模型训练、held-out evaluation 和闭环 sanity check 提供。

## 10. 云端目录与完整性复核

2026-07-31 将散落在 `/root/autodl-tmp/` 顶层的 Day 4/5 产物移入统一根目录：

```text
/root/autodl-tmp/results/give_way_transformer/
├── day4/
│   ├── final/
│   └── artifacts/
└── day5/
    ├── final/
    ├── development/
    │   ├── candidates/
    │   ├── pilots/
    │   └── smoke/
    ├── failed/
    ├── artifacts/
    └── logs/infrastructure/
```

整理只使用不覆盖移动，没有删除数据。移动后从新路径重跑完整审计，结果仍为 `status=pass`、20/20 rollouts、1,055 samples、19/19 gates 和 0 errors。`/root/autodl-tmp/` 顶层已无 Day4/Day5/audit/frozen 散落条目。

额外防抖动复核显示：

1. target throttle 与 brake 同时激活步数为 0；
2. propulsion–braking 直接反转次数为 0；
3. 触发轨迹的 active state 与 desired speed 都恰好发生一次下降和一次恢复；
4. 未触发轨迹的上述转移次数为 0。

20 Hz CARLA wheel-speed 有 S0/S1 共有的高频波动，因此原始速度差分的 acceleration/jerk 峰值不作为执行器物理界限证据。防抖动结论以互斥 actuator command、state transition 和 desired-speed transition 为主。因而 Day 5 对“正式数据采集前的 reactive 行为与配置冻结”已完全完成；它不支持人类舒适性或驾驶真实性 claim。

## 11. 下一步

进入 Day 6：

```text
50 inits × 4 cells = 200 formal rollouts
```

必须使用 frozen config，启用 resume；技术失败只能用完全相同配置重跑。正式采集开始后禁止使用 test split 调参，也禁止修改 reactive behavior。
