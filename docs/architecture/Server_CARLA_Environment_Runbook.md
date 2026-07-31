# 服务器 CARLA 实验环境启动手册

这个文档记录每次在 GPU/服务器上运行 CARLA + SMPC 实验前必须执行的环境配置。目标是避免因为 CasADi/Gurobi 没有正确加载而产生无效结果。

## 1. 每次启动服务器后的固定配置

```bash
cd /root/autodl-tmp/Research-Project-IMLS

conda activate carla_modern

export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export PYTHONPATH=$CARLA_ROOT/PythonAPI/carla:$CARLA_ROOT/PythonAPI/carla/agents:$PYTHONPATH

export GUROBI_HOME=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi1103/linux64
export GUROBI_VERSION=110
export GRB_LICENSE_FILE=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi.lic
export LD_LIBRARY_PATH=$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}
```

## 2. 必须先做的 solver 检查

本项目的 SMPC 使用的是：

```python
ca.Opti("conic")
```

因此要检查 CasADi 的 conic Gurobi plugin：

```bash
python -c "import casadi as ca; print(ca.__version__); print(ca.has_conic('gurobi'))"
```

期望输出：

```text
3.7.2
True
```

不要用下面这个作为本项目的通过标准：

```python
ca.has_nlpsol("gurobi")
```

它可以是 `False`，因为本项目需要的是 `conic` solver backend，不是 `nlpsol` backend。

## 3. 错误现象

如果日志或 `smpc_debug_steps.jsonl` 里出现：

```text
Plugin 'gurobi' is not found
```

这次 rollout 应该判为环境污染结果，不要用于论文或 ablation 结论。

典型表现：

- `solver_failure_frac` 接近 `0.9+`
- rollout 跑满 `600` steps
- `completion_valid=None` 或 `completion=False`
- 车辆进入 fallback control，速度上不去
- 即使没有 collision，post-CARLA gate 也会失败

## 4. 长实验前先跑 development smoke

先在单独终端启动 CARLA：

```bash
cd "$CARLA_ROOT"
./CarlaUE4.sh -RenderOffScreen -quality-level=Low
```

再在实验终端运行当前 A3 单点 development matrix：

```bash
cd /root/autodl-tmp/Research-Project-IMLS/core/scripts/carla

TARGET_START_OFFSETS="0.0" \
ENABLE_CAMERA_VIZ=0 \
PYTHON_BIN=python \
RESULTS_DIR=/root/autodl-tmp/Research-Project-IMLS/core/results/$(date +%Y%m%d_%H%M%S)_a3_development_smoke \
./run_give_way_init01_v13_risk_owned_yield.sh
```

通过标准：

- `postcarla_trajectory_gate.md` 总体为 `PASS`
- `solver_failure_frac` 低于 gate threshold；
- `completion_valid=True`；
- 没有 `Plugin 'gurobi' is not found`
- model/config/anchors 均来自预期路径；
- step-level prediction/risk/solver/supervisor 日志存在。

Smoke 只验证环境和执行链路，不计入正式结果，也不得用于调正式 test condition。

## 5. 正式实验入口

正式 dataset/model/closed-loop 命令按：

```text
docs/paper/两周_最终研究主线_数据扩展与实验执行方案.md
```

逐日冻结后执行。本 runbook 不复制正式矩阵命令，避免两处配置漂移。

每次正式 batch 前必须记录：

- `git status --short`；
- Git commit；
- dataset/model/config hashes；
- `RESULTS_DIR`；
- expected arms/conditions；
- data disk 可用空间。

Gurobi 安装包和 license 只保存在服务器，不提交 Git。
