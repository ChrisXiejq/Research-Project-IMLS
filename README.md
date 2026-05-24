# Research-Project-IMLS

这个仓库已整合为你的毕业设计复现实验工作区，目标是复现论文：
`Predictive Control for Autonomous Driving With Uncertain, Multimodal Predictions`

## 目录说明

- `core/`：主实验代码（基于 `SMPC_MMPreds`，含 SMPC 三策略、CARLA 场景、预训练 MultiPath 资产）
- `extensions/`：来自 `confidence_aware_predictions` 的扩展模块（用于后续校准/预测侧增强）
- `docs/guides/AutoDL_现代稳定版复现手册.md`：现代稳定版复现（推荐，含 intersection 三层检查）
- `docs/paper/论文与SMPC_Intersection复现梳理.md`：**论文方法 · SMPC 流程 · 迁移与 intersection 范围**（概念与流程总览）
- `docs/architecture/`：流程图与代码架构映射
- `docs/milestones/`：实验里程碑与进展记录
- `tools/assemble_from_sources.py`：从源仓重组当前工作区的脚本

## 复现实验步骤（基础版，完整可跑）

1. 先按环境手册搭好环境（推荐 `docs/guides/AutoDL_现代稳定版复现手册.md`）。
2. 启动 CARLA 服务端（单独终端）：
   - `cd $CARLA_ROOT && ./CarlaUE4.sh -RenderOffScreen -quality-level=Low`
3. 运行三策略批量实验（客户端终端）：
   - `cd core/scripts/carla`
  - `python run_all_scenarios.py --scenario_glob "scenario_01.json" --init_glob "ego_init_*.json" --policies smpc_var_risk smpc_open_loop smpc_fixed_risk --solver_backend gurobi --risk_profile upstream_code --with_notv --with_notv_cl`
4. 汇总结果：
   - `cd core`
   - `python scripts/compute_scenario_results.py`

## 与论文对齐建议

- 先跑 `scenario_0*.json`（intersection）对齐论文核心对比（Proposed/Fixed/Open-loop）。
- 再跑 `scenario_lk*.json`（lane-change 相关）。
- 保持论文参数：`N=10`、`dt=0.2`；主复刻用 `--risk_profile upstream_code` 对齐原仓数值，严格 `epsilon=0.02` 用 `--risk_profile paper_eps_002` 单独作为消融/压力测试。

## 重要说明

- 当前 `core/` 已包含运行实验所需的 MultiPath 部署模型与 anchors。
- 现代化一键入口：`bash run_modern_reproduction.sh`
- 若你更新了源仓，执行以下命令重组：
  - `python tools/assemble_from_sources.py`
