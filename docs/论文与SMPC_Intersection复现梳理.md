# 论文思想与方法 · SMPC 仓库流程 · 迁移与 Intersection 复现

本文档说明：**论文与 SMPC_MMPreds 在做什么**、**官方仓库如何跑通一条实验**、**Research-Project-IMLS 如何承接同一套思想与流程**，以及为 **CARLA 0.9.14 / Ubuntu 22.04 / 现代 Python 环境** 做了哪些**不改变核心优化思想**的适配。  
你的复现范围：**仅 intersection 路口场景**（`scenario_0*.json`、`ego_init_*.json`）。

**流程图 ↔ 代码（答辩/论文用对照表）：** 见 [流程图与代码映射.md](./流程图与代码映射.md)（对应 `Experiment Flow.png` 与 `SMPC.png`）。

---

## 1. 论文层面的思想与方法（与代码对应）

论文题目对应的工作可概括为一条闭环管线（与 `SMPC_MMPreds` 实现一致）：

### 1.1 不确定性与多模态预测

- **他车未来轨迹**用 **GMM（多模态高斯混合）** 表示：每个模态一条均值轨迹 + 时变协方差，并带有模态概率。
- 预测模型来自 **confidence_aware_predictions** 路线（训练与导出与仿真侧分离）；仿真侧使用 **部署好的 MultiPath** 权重与 anchors，在栅格化语义图上做前向推理（见 `core/scripts/models/`、`PredictionParams`）。

### 1.2 在预测之上做「随机 / 机会约束」式 MPC（SMPC）

- 自车在 **LTV 动力学** 下跟踪参考路径，同时对他车各 **GMM 模态** 施加 **避碰相关约束**（SOC / 风险形式，实现在 `mpc_utils.py` 的 `SMPC_MMPreds` 族中）。
- **多模态联合假设**：多个 target 时，联合索引覆盖各车模态的乘积空间；实现中通过联合索引解码到每辆车的模态（见 `_joint_mode_component`，与 \(N_{\mathrm{modes}}^{N_{\mathrm{TV}}}\) 的乘积结构一致）。
- **发布代码复刻边界**：上游 `SMPC_MMPreds` 的 intersection 实验实际只使用 1 个 target vehicle；其历史索引 `int(m/N_TV)*(v==1) + (m%N_TV)*(v==0)` 在 `N_TV=1` 时会把所有 joint mode 映射到 target `mode 0`。本仓库在 `--risk_profile upstream_code` 下保留该行为以贴近发布代码；`paper_eps_002` 等消融口径保留数学 joint-mode 解码。

### 1.3 三种 SMPC 策略（论文对比的核心）

在 ego 上通过 `smpc_config` 切换（与 `run_all_scenarios.py` 中 `--policies` 一致）：

| 策略名 | 含义（实现侧） | 典型代码路径 |
|--------|----------------|----------------|
| **smpc_var_risk** | 可变风险 / 文中 Proposed 一类表述 | `SMPC_MMPreds`，`fixed_risk=False` |
| **smpc_fixed_risk** | 固定风险权重 | `SMPC_MMPreds`，`fixed_risk=True` |
| **smpc_open_loop** | 开环风险弱化形式 | `SMPC_MMPreds_OL`（`smpc_agent.py` 中 `ol_flag=True`） |

另：**target 车**常用 **MPC** 沿自身路径行驶；**notv / notv_cl** 为基线对照，不改变上述 SMPC 数学，仅用于实验对比。

### 1.4 求解器层面（与论文实验一致的路径）

- 原文 SMPC 栈使用 **CasADi `Opti("conic")` + Gurobi** 求解锥规划形式。
- 本工作区在 **`--solver_backend gurobi`** 下保持与 **SMPC_MMPreds** 相同的 **Gurobi 注册方式与参数块**（`p_opts_grb` / `s_opts_grb` 及 OBCA 分支中的参数顺序与上游一致）。  
- 为避免混淆，本工作区显式区分两种风险数值口径：**`--risk_profile upstream_code`** 对齐原仓代码中的 `TIGHTENING=1.64`，用于稳定复刻闭环实验；**`--risk_profile paper_eps_002`** 对应论文文字中的 `epsilon=0.02`，更保守，可作为压力测试/消融结果单独报告。
- **`ipopt_approx`** 仅为**无许可证或插件不可用时的近似复现路径**，不属于论文主线的同一求解器配置；写论文结果时应明确区分。

---

## 2. SMPC_MMPreds 官方仓库在做什么（流程）

依据上游 `README.md` 与目录结构，**一条完整 intersection 实验**在逻辑上等价于：

```
场景 JSON + 路口 CSV
    → run_all_scenarios.py 选择 scenario / ego_init
        → RunIntersectionScenario
            → 起 CARLA 世界、刷车辆、加载预测模型
            → 每帧：AgentHistory 更新 → _make_predictions() → pred_dict
            → 各车 policy.run_step(pred_dict)
                → ego: SMPCAgent → mpc_utils 中 SMPC_MMPreds / OL
                → target: MPCAgent 等
            → 记录轨迹 / 可行性 / 求解时间 → scenario_result.pkl
```

**关键脚本与目录（与上游一致，现位于你的 `core/scripts/` 下）：**

| 组件 | 路径 | 作用 |
|------|------|------|
| 批量入口 | `carla/run_all_scenarios.py` | 遍历 scenario / init / policy，写 `results/<timestamp>/...` |
| 路口仿真 | `carla/scenarios/run_intersection_scenario.py` | 世界 setup、预测、同步循环、日志 |
| 控制策略 | `carla/policies/smpc_agent.py` 等 | ego SMPC / target MPC |
| 优化核 | `carla/utils/mpc_utils.py` | `SMPC_MMPreds`、`SMPC_MMPreds_OL`、OBCA 等 |
| 预测 | `evaluation/gmm_prediction.py` + `models/deploy_multipath_model.py` | 与 SMPC 主线一致 |
| 后处理 | `compute_scenario_results.py` | 聚合指标与作图（可与上游略有扩展） |

**confidence_aware_predictions** 仓库：负责**预测训练与部分评估工具**；仿真闭环的「主 fork」在 **SMPC_MMPreds**。你的 `extensions/` 中子树与上游 CAP 的对应拷贝用于扩展/对齐训练侧，**intersection 闭环主路径仍以 `core/scripts` 为准**。

---

## 3. 迁移到 Research-Project-IMLS 的对应关系

### 3.1 目录映射

| SMPC_MMPreds | Research-Project-IMLS |
|--------------|------------------------|
| `SMPC_MMPreds/scripts/` | `Research-Project-IMLS/core/scripts/` |
| `SMPC_MMPreds/env_setup/` | `core/env_setup/`（另含 `environment.modern.yml` 等现代环境文件） |
| CAP 部分模块 | `extensions/confidence_*`（由 `tools/assemble_from_sources.py` 从本机 CAP 路径拷贝） |

### 3.2 思想与方法：保持不变的部分

- **MPC/SMPC 问题结构**：动力学线性化、SOC 避碰、三策略分支、Gurobi 调用方式与上游对齐的部分。
- **预测输入输出接口**：`pred_dict` → `mus` / `sigmas` 与 `mpc_utils` 中参数更新一致。
- **Intersection 主循环**：`RunIntersectionScenario.run_scenario` 与上游设计一致（预测 → `run_step` → 记录）。

### 3.3 为「可在你环境跑通」增加的适配层（不改变 Gurobi 核数学）

| 类别 | 说明 |
|------|------|
| **CARLA 0.9.14** | Python API 路径、`GlobalRoutePlanner` 构造兼容、蓝图解析（`resolve_vehicle_blueprint`）等 |
| **Ubuntu 22.04 / 驱动** | 无头渲染、`-nullrhi` 等见 `docs/AutoDL_现代稳定版复现手册.md` |
| **Python / Conda** | `environment.modern.yml`、`requirements.modern.txt` 等 |
| **场景与 OL 规模** | `n_tv_max` 由场景中 `target` 数量注入，使 **预测列表长度与 OL 中 \(N_{\mathrm{TV}}\)** 一致（intersection 典型为 1） |
| **无 Gurobi 时的可选路径** | `--solver_backend ipopt_approx` + `ipopt_smpc_agent.py`（论文主结果仍应以 Gurobi 为准） |

---

## 4. 你只做的实验：Intersection 复现清单

### 4.1 环境与 CARLA

按 **`docs/AutoDL_现代稳定版复现手册.md`**（或 `AutoDL_Modern_Setup.md`）完成：

- `CARLA_ROOT` 指向 **0.9.14** 客户端与 **同版本** 服务端；
- Conda 环境（如 `carla_modern`）、Gurobi 许可与 `GUROBI_VERSION` 等与手册一致。

### 4.2 三层检查与全量（手册 §7.3）

1. **最小**：`scenario_01.json` + `ego_init_01.json` + 单策略 + Gurobi。  
2. **小矩阵**：三 `smpc_*` + `notv` / `notv_cl`。  
3. **指标**：`compute_scenario_results.py --compute_metrics`（及可选轨迹图）。  
4. **全量**：`scenario_0*.json` × `ego_init_*.json`。

命令块以手册为准，此处不重复粘贴。

### 4.3 与论文叙述对齐时的表述建议

- 主结果：**Gurobi + CasADi conic + 三策略 + intersection 场景**。  
- 配置：**默认 `N=10`、`dt=0.2`、`num_modes` 与场景 JSON / `VehicleParams` 一致**；主复刻建议使用 `--risk_profile upstream_code`，严格论文风险口径使用 `--risk_profile paper_eps_002` 另列说明。

---

## 5. 若从上游重新同步 `core/` 时

```bash
# 在 Dissertation 根目录，且本机存在同级 SMPC_MMPreds、confidence_aware_predictions
python Research-Project-IMLS/tools/assemble_from_sources.py
```

然后需**重新合并**你为 CARLA 0.9.14 / Ubuntu 22 所做的适配（或保留本仓库为「已迁移」主干，仅选择性覆盖文件）。建议用 `git diff` 对照 `SMPC_MMPreds/scripts` 与 `core/scripts` 审阅后再覆盖。

---

## 6. 小结

| 层级 | 你的目标 | 本仓库状态 |
|------|----------|------------|
| **思想** | 多模预测 + SMPC 三策略 + intersection 闭环 | 与 SMPC 设计一致 |
| **方法** | Gurobi 锥规划主路径 | 与 SMPC 对齐；IPOPT 为可选退路 |
| **配置** | 尽量接近上游 | OL/闭环路默认超参与 SMPC 一致；`upstream_code` 保留发布代码的单 TV mode indexing；ego 的 `N`/`dt`/`num_modes` 来自 JSON |
| **环境** | CARLA 0.9.14 + Ubuntu 22 + 现代 Python | 见 AutoDL 手册与 `env_setup` |

更细的命令与排错仍以 **`docs/AutoDL_现代稳定版复现手册.md`** 为操作真值；本文负责**概念—流程—迁移边界**的完整梳理。
