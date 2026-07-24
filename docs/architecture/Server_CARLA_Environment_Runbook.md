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

## 4. 长实验前先跑 1-init smoke test

正式跑 5-init、10-init 或 50-init 前，先跑：

```bash
cd /root/autodl-tmp/Research-Project-IMLS/core/scripts/carla

SUPERVISOR_MODES="full" \
INIT_COUNT=1 \
ENABLE_CAMERA_VIZ=0 \
PYTHON_BIN=python \
RESULTS_DIR=/root/autodl-tmp/Research-Project-IMLS/core/results/$(date +%Y%m%d_%H%M%S)_1init_full_supervisor_smoke \
./run_give_way_10init_supervisor_ablation.sh
```

通过标准：

- `postcarla_trajectory_gate.md` 总体为 `PASS`
- `solver_failure_frac = 0.000` 或明显低于 gate threshold
- `completion=True`
- 没有 `Plugin 'gurobi' is not found`

已确认的正常 smoke test：

```text
core/results/20260724_222517_1init_full_supervisor_smoke
```

## 5. 正式 5-init supervisor ablation 模板

```bash
cd /root/autodl-tmp/Research-Project-IMLS

conda activate carla_modern

export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export PYTHONPATH=$CARLA_ROOT/PythonAPI/carla:$CARLA_ROOT/PythonAPI/carla/agents:$PYTHONPATH

export GUROBI_HOME=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi1103/linux64
export GUROBI_VERSION=110
export GRB_LICENSE_FILE=/root/autodl-tmp/Research-Project-IMLS/gurobi/gurobi.lic
export LD_LIBRARY_PATH=$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}

cd core/scripts/carla

SUPERVISOR_MODES="full reduced_intervention" \
INIT_COUNT=5 \
ENABLE_CAMERA_VIZ=0 \
PYTHON_BIN=python \
RESULTS_DIR=/root/autodl-tmp/Research-Project-IMLS/core/results/$(date +%Y%m%d_%H%M%S)_5init_supervisor_ablation \
./run_give_way_10init_supervisor_ablation.sh
```

