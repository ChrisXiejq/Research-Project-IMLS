# Research-Project-IMLS

这个仓库已整合为你的毕业设计复现实验工作区，目标是复现论文：
`Predictive Control for Autonomous Driving With Uncertain, Multimodal Predictions`

## 目录说明

- `core/`：主实验代码（基于 `SMPC_MMPreds`，含 SMPC 三策略、CARLA give-way intersection 场景、预训练 MultiPath 资产）
- `archive/extensions_confidence_reference/`：已归档的 `confidence_aware_predictions` 参考代码；当前主线实验不依赖
- `docs/paper/Predictive_Control_for_Autonomous_Driving_With_Uncertain_Multimodal_Predictions.pdf`：原论文 PDF
- `docs/architecture/`：流程图与代码架构映射

## 当前实验入口

1. 先阅读 `docs/paper/论文实验与写作统一指导.md`。这是当前唯一 canonical 指导文档。
2. 启动 CARLA 服务端（单独终端）：
   - `cd $CARLA_ROOT && ./CarlaUE4.sh -RenderOffScreen -quality-level=Low`
3. 当前 reduced early-stop 主基准和 ablation 只使用以下入口：
   - `cd core/scripts/carla`
   - `./run_give_way_10init_supervisor_ablation.sh`
   - `./run_give_way_5init_fixed_risk_frontier.sh`
   - `./run_give_way_video_gate_frontier.sh`
4. 所有当前入口都应使用 `core/scripts/carla/scenarios/tuning_configs/give_way_reduced_clear_path_release_frozen.json`。不要恢复旧 final-dissertation batch 脚本。

## 与论文对齐建议

- 本 dissertation 复现范围只保留 CARLA intersection give-way 场景，不复现 lane-change 或 hardware/VIL。
- 当前主基准是 frozen `reduced_intervention` early-stop / clear-path-release tuning。
- `full` supervisor 只作为 supervisor masking 的对比试验，不作为主系统。
- 在完成 video gate 和 frozen reduced baseline 下的 frontier 证据前，不进入 50-init 全量实验。
- 当前主线 adaptive arm 使用 `adaptive_interaction_severity` + `floor_weak`；fixed-risk baseline 应使用 fixed-risk frontier，而不是单一 fixed-risk baseline。

## 重要说明

- 当前 `core/` 已包含运行实验所需的 MultiPath 部署模型与 anchors。
- 不再保留 `tools/assemble_from_sources.py`，避免误运行后覆盖当前已修正的 `core/` 和 `docs/`。
