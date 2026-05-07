# Research-Project-IMLS

这个仓库已整合为你的毕业设计复现实验工作区，目标是复现论文：
`Predictive Control for Autonomous Driving With Uncertain, Multimodal Predictions`

## 目录说明

- `core/`：主实验代码（基于 `SMPC_MMPreds`，含 SMPC 三策略、CARLA 场景、预训练 MultiPath 资产）
- `extensions/`：来自 `confidence_aware_predictions` 的扩展模块（用于后续校准/预测侧增强）
- `docs/AutoDL_Environment_Setup.md`：你已验证过的 AutoDL 环境搭建手册
- `tools/assemble_from_sources.py`：从源仓重组当前工作区的脚本

## 复现实验步骤（基础版，完整可跑）

1. 先按 `docs/AutoDL_Environment_Setup.md` 搭好环境（CARLA、conda、Gurobi）。
2. 启动 CARLA 服务端（单独终端）：
   - `cd $CARLA_ROOT && ./CarlaUE4.sh -RenderOffScreen -quality-level=Low`
3. 运行三策略批量实验（客户端终端）：
   - `cd core/scripts/carla`
   - `python run_all_scenarios.py --scenario_glob "scenario_0*.json" --init_glob "ego_init_*.json" --policies smpc_var_risk smpc_open_loop smpc_fixed_risk --with_notv --with_notv_cl`
4. 汇总结果：
   - `cd core`
   - `python scripts/compute_scenario_results.py`

## 与论文对齐建议

- 先跑 `scenario_0*.json`（intersection）对齐论文核心对比（Proposed/Fixed/Open-loop）。
- 再跑 `scenario_lk*.json`（lane-change 相关）。
- 保持论文参数：`N=10`、`dt=0.2`、相同 risk 设定，再做你自己的 ablation。

## 重要说明

- 当前 `core/` 已包含运行实验所需的 MultiPath 部署模型与 anchors。
- 若你更新了源仓，执行以下命令重组：
  - `python tools/assemble_from_sources.py`