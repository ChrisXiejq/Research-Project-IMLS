# Research-Project-IMLS

这个仓库是毕业设计的唯一实验工作区。当前研究聚焦：

```text
interaction- and calibration-aware trajectory prediction
× adaptive/fixed-risk SMPC
× runtime safety authority
```

## 当前文档

1. `docs/paper/两周_最终研究主线_数据扩展与实验执行方案.md`：当前唯一实验与论文 canonical 文档。
2. `docs/paper/Day1_冻结协议与服务器资产审计报告.md`：本地/服务器资产、数据、checkpoint 和 Git 状态审计。
3. `docs/paper/Day2_数据审计与V2协议冻结报告.md`：旧数据完整性、V2 interaction schema 和 200-rollout collection matrix。
4. `docs/paper/Day3_GMM评估器与校准报告.md`：部署等价 GMM evaluator、raster channel 诊断与 calibration 结果。
5. `docs/paper/Day4_V2交互数据链路与ReactiveTarget报告.md`：V2 共享输入、交互序列、reactive target 与四单元 smoke。
6. `docs/paper/已完成实验与证据账本.md`：已完成控制、预测和闭环实验的结果路径、可支持论点与限制。
7. `docs/architecture/Server_CARLA_Environment_Runbook.md`：云服务器 CARLA、CasADi 和 Gurobi 启动检查。

完整索引见 `docs/README.md`。

## 代码入口

- `core/scripts/carla/run_all_scenarios.py`：通用 CARLA batch runner。
- `core/scripts/carla/run_give_way_prediction_dataset_collection.sh`：当前 V1 prediction dataset collector；V2 collector 将按 canonical 方案新增。
- `core/scripts/carla/run_give_way_init01_fixed_frontier_vs_adaptive.sh`：单点 fixed frontier / adaptive development runner。
- `core/scripts/carla/run_give_way_init01_v13_risk_owned_yield.sh`：A3 risk-owned-yield development runner。
- `core/scripts/models/audit_prediction_dataset.py`：V1/V2 grouped-split、horizon、raster 和计数审计。
- `core/scripts/models/build_prediction_dataset_v2_protocol.py`：生成冻结的 V2 feature schema 与 200-rollout manifest。
- `core/scripts/models/multipath_gmm_utils.py`：evaluator/deployment 共用的唯一 MultiPath GMM 解码 contract。
- `core/scripts/models/evaluate_multipath_model_on_dataset.py`：accuracy、NLL、2D coverage、covariance audit、rollout aggregation 和 calibration。
- `core/scripts/models/prediction_input_contract.py`：V2 offline/online 共享 raster contract。
- `core/scripts/models/interaction_sequence.py`：V2 共享 6×12 ego-target sequence builder。
- `core/scripts/carla/run_give_way_prediction_dataset_v2.sh`：S0/S1 × fixed/adaptive V2 数据采集入口。
- `core/scripts/models/`：MultiPath 训练、部署、dataset utilities 和 evaluator。
- `core/scripts/postcarla_trajectory_gate.py`：正式闭环安全 gate。

当前保留的控制配置：

```text
give_way_reduced_clear_path_release_v12_current_best.json
give_way_reduced_clear_path_release_v13_risk_owned_yield.json
give_way_smpc_tuning.json
```

已完成的一次性 sweep/ablation runner 和旧模型 pilot runner 已删除；历史版本可从 Git 恢复，结果证据保留在账本和 `docs/paper/generated/`。

## 运行边界

- CARLA/Gurobi 正式实验在云服务器执行。
- `core/results/`、训练日志、临时模型和视频不提交 Git。
- Gurobi license 与安装包不得提交；服务器路径由环境变量配置。
- 密码、token 和 license 内容不得写入脚本、文档或命令日志。
- 正式实验必须记录 Git commit、dataset/model/config hash 和 result manifest。
