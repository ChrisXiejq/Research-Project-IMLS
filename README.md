# Research-Project-IMLS

这个仓库已整合为你的毕业设计复现实验工作区，目标是复现论文：
`Predictive Control for Autonomous Driving With Uncertain, Multimodal Predictions`

## 目录说明

- `core/`：主实验代码（基于 `SMPC_MMPreds`，含 SMPC 三策略、CARLA give-way intersection 场景、预训练 MultiPath 资产）
- `archive/extensions_confidence_reference/`：已归档的 `confidence_aware_predictions` 参考代码；当前主线实验不依赖
- `docs/paper/Predictive_Control_for_Autonomous_Driving_With_Uncertain_Multimodal_Predictions.pdf`：原论文 PDF
- `docs/architecture/`：流程图与代码架构映射

## 复现实验步骤（基础版，完整可跑）

1. 先按环境手册搭好环境（推荐 `docs/guides/AutoDL_现代稳定版复现手册.md`）。
2. 启动 CARLA 服务端（单独终端）：
   - `cd $CARLA_ROOT && ./CarlaUE4.sh -RenderOffScreen -quality-level=Low`
3. 运行三策略批量实验（客户端终端）：
   - `cd core/scripts/carla`
   - `./run_give_way_final_dissertation_batch.sh`
4. 汇总结果：
   - 主线脚本会自动运行 `core/scripts/postcarla_trajectory_gate.py`

## 与论文对齐建议

- 本 dissertation 复现范围只保留 CARLA intersection give-way 场景，不复现 lane-change 或 hardware/VIL。
- 当前单 init 入口是 `core/scripts/carla/scenarios/inits/ego_init_01.json`。
- 50-init 全量入口是 `core/scripts/carla/scenarios/inits/paper_intersection_50/ego_init_*.json`，通过 `core/scripts/carla/run_give_way_50init_final_dissertation_batch.sh` 运行。
- 当前主线使用 `adaptive_interaction_severity` risk profile；严格 `epsilon=0.02` 只作为可选压力测试/消融口径，不混入主线 baseline。

## 重要说明

- 当前 `core/` 已包含运行实验所需的 MultiPath 部署模型与 anchors。
- 不再保留 `tools/assemble_from_sources.py`，避免误运行后覆盖当前已修正的 `core/` 和 `docs/`。
