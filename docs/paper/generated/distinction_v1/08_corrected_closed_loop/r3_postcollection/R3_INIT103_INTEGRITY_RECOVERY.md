# R3 init103 单键完整性恢复说明

## 触发原因

第一次离线审计覆盖了全部 80 个正式 rollout，且 80/80 均通过单 rollout 完整性检查，但矩阵级审计拒绝完成：

- `matrix:first_state_consistency:init103:ego`
- `matrix:fixed_geometry_consistency:init103`

异常唯一定位到 `B0_fixed_conservative_assertive / init103`。另外 15 个处理组的 ego 首状态和固定冲突几何形成一致簇；异常样本的 ego 首记录前移约 0.472 m，而其第二条记录与另外 15 组的首记录一致。这符合 20 Hz CARLA 控制循环相差一个仿真 tick 的启动相位异常。target 首状态没有相同偏移。

## 科研处理原则

不能在看到结果后放宽预先冻结的 `0.1` 首状态一致性阈值或 `1e-3 m` 固定几何阈值。恢复必须满足以下约束：

1. 保留被拒绝 rollout、receipt、attempt ledger 和失败审计，不删除或覆盖原始证据；
2. 只允许补跑同一个 treatment key：`B0_fixed_conservative_assertive / init103`；
3. 其余 79 个 accepted rollout 保持原字节和原 receipt；
4. 继续使用原始采集提交 `8ccecf848b87b6fa2936e081d9f6943cd7f5a449`，不得用修改后的控制代码生成替代样本；
5. 补跑原因只来自完整性检查，不来自碰撞、效率、yield 或模型优劣等科学结果；
6. 新样本完成后重新生成完整 80-rollout 原始清单，并从头运行全部离线指标、矩阵审计、统计分析与证据归档。

## 工具行为

`core/scripts/models/prepare_r3_integrity_recovery.py` 默认只读。它会先自动证明上述唯一的一步相位特征。只有显式加入 `--apply` 后，才会：

- 将原 cell 原子移动到 `_integrity_recovery/<recovery_id>/quarantined_cell`；
- 将 init101、102、104、105 的原始 evidence 移回正式 cell；
- 将 init103 的被拒绝 evidence 留在 quarantine；
- 归档第一次失败审计及旧的离线派生 marker；
- 写入 `R3_INTEGRITY_RECOVERY_PREPARED.json`；
- 使冻结采集 runner 看到恰好 1 个 pending key。

该操作是可恢复的；服务器中断后重复执行同一 `--apply` 命令即可继续或验证已完成布局。

## 论文披露

实验方法/局限性中应披露：矩阵审计在分析前检测到一次 CARLA 20 Hz 启动相位完整性异常；研究保留了原始异常证据，并依据同键、与科学结果无关的完整性规则补采一次。最终统计只使用通过冻结完整性门槛的 80 个 treatment keys，被隔离样本不作为额外独立重复或用于挑选有利结果。
