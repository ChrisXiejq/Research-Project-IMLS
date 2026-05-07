# AutoDL 保守复现环境手册（SMPC_MMPreds）

本手册目标：在 AutoDL 上优先跑通论文代码仓库 `SMPC_MMPreds` 的最小可行闭环。

适用策略：**保守路径**（尽量贴近原仓库依赖），先跑通再优化。

---

## 0. 目标与范围

- 当前阶段目标：
  - 跑通环境
  - 跑通一个场景（单策略）
  - 验证 `scenario_result.pkl` 产出
- 当前阶段不做：
  - 训练 MultiPath
  - 升级新版本依赖
  - 大规模批量实验

---

## 0.1 路径约定（AutoDL 持久盘）

你要求所有内容放在持久盘，后续统一使用：

- 工作根目录：`~/autodl-tmp`
- 项目目录：`~/autodl-tmp/SMPC_MMPreds`
- CARLA 目录：`~/autodl-tmp/carla_0.9.10`

> 下文默认你在 root 用户下执行，且 `~/autodl-tmp` 为持久盘。

## 1. 实例与镜像选择

建议：

- 系统：Ubuntu 20.04
- 镜像：**Miniconda 基础镜像**（不要预置 TensorFlow 2.5 那类）
- GPU：任意支持 CUDA 的 NVIDIA 卡
- 磁盘：建议 >= 40GB

> 原因：仓库依赖偏老（Python 3.7 / TF 2.2 / CARLA 0.9.10），Miniconda 基础镜像最稳。

---

## 2. 基础检查

```bash
nvidia-smi
uname -a
python3 --version
conda --version
```

预期：

- `nvidia-smi` 正常显示 GPU
- `conda` 可用

---

## 3. 拉代码

```bash
cd ~/autodl-tmp
git clone https://github.com/shn66/SMPC_MMPreds.git
git clone https://github.com/govvijaycal/confidence_aware_predictions.git
```

说明：

- 当前只强依赖 `SMPC_MMPreds`
- 第二个仓库用于后续预测模型追溯与扩展

---

## 4. 安装系统依赖

```bash
sudo apt-get update
sudo apt-get install -y \
  wget unzip tmux htop git \
  libglib2.0-0 libsm6 libxext6 libxrender-dev libx11-6 \
  libslicot-dev libgmp3-dev \
  xvfb ffmpeg
```

---

## 5. 安装 CARLA 0.9.10

已验证成功（AutoDL）：

```bash
cd ~/autodl-tmp
rm -f CARLA_0.9.10.tar.gz
wget -O CARLA_0.9.10.tar.gz https://tiny.carla.org/carla-0-9-10-linux
ls -lh CARLA_0.9.10.tar.gz
file CARLA_0.9.10.tar.gz
mkdir -p ~/autodl-tmp/carla_0.9.10
tar -xzf CARLA_0.9.10.tar.gz -C ~/autodl-tmp/carla_0.9.10 --strip-components=1
ls ~/autodl-tmp/carla_0.9.10 | head
```

配置环境变量：

```bash
echo 'export CARLA_ROOT=$HOME/autodl-tmp/carla_0.9.10' >> ~/.bashrc
source ~/.bashrc
```

本次包结构下（已验证）Python API 在 `$CARLA_ROOT/carla`：

```bash
echo $CARLA_ROOT
export CARLA_API_ROOT="$CARLA_ROOT/carla"
export PYTHONPATH="$CARLA_API_ROOT:$PYTHONPATH"
export PYTHONPATH="$CARLA_API_ROOT/dist/carla-0.9.10-py3.7-linux-x86_64.egg:$PYTHONPATH"

# 持久化
sed -i '/CARLA_API_ROOT/d' ~/.bashrc
sed -i '/carla-0.9.10-py3.7-linux-x86_64.egg/d' ~/.bashrc
echo 'export CARLA_API_ROOT=$CARLA_ROOT/carla' >> ~/.bashrc
echo 'export PYTHONPATH=$CARLA_API_ROOT:$PYTHONPATH' >> ~/.bashrc
echo 'export PYTHONPATH=$CARLA_API_ROOT/dist/carla-0.9.10-py3.7-linux-x86_64.egg:$PYTHONPATH' >> ~/.bashrc
source ~/.bashrc

python - <<'PY'
import carla
print("carla import ok")
PY
```

---

## 6. 创建 Conda 环境（AutoDL 修正版，已避开 solver 卡死）

```bash
cd ~/autodl-tmp/SMPC_MMPreds
conda install -n base -c conda-forge mamba -y
mamba env create -f env_setup/environment.autodl.yml
conda activate carla_conf
```

再安装 pip 依赖（分两步，减少失败面）：

```bash
pip install tensorflow-gpu==2.2.0
pip install -r env_setup/requirements.txt
pip install pytope
```

基础导入检查：

```bash
python -c "import tensorflow as tf; print(tf.__version__)"
python -c "import casadi; print(casadi.__version__)"
python -c "import carla; print('carla import ok')"
```

---

## 7. 安装并验证 Gurobi（关键）

> 没有 Gurobi license，SMPC 核心无法跑通。

```bash
conda activate carla_conf
pip install gurobipy
```

确认 license 已配置后测试：

```bash
python - <<'PY'
import gurobipy as gp
m = gp.Model()
x = m.addVar(lb=0.0)
m.setObjective(x, gp.GRB.MINIMIZE)
m.optimize()
print("gurobi ok")
PY
```

---

## 8. 组件级可行性验证（不进 CARLA）

### 8.1 验证 MultiPath 模型加载

```bash
cd ~/autodl-tmp/SMPC_MMPreds
python - <<'PY'
import os, numpy as np
from scripts.models.deploy_multipath_model import DeployMultiPath
prefix = os.path.abspath("scripts/models")
m = DeployMultiPath(
    os.path.join(prefix, "l5kit_multipath_10"),
    np.load(os.path.join(prefix, "l5kit_clusters_16.npy"))
)
print("multipath deploy load ok")
PY
```

### 8.2 验证 SMPC 类可初始化

```bash
python - <<'PY'
from scripts.carla.utils.mpc_utils import SMPC_MMPreds
s = SMPC_MMPreds(N=10, DT=0.2, N_modes_MAX=3)
print("SMPC_MMPreds init ok")
PY
```

---

## 9. 启动 CARLA（建议 tmux 两个窗口）

### 窗口 A：CARLA 服务端

```bash
cd $CARLA_ROOT
./CarlaUE4.sh -RenderOffScreen -quality-level=Low
```

如遇显示相关报错：

```bash
xvfb-run -s "-screen 0 1024x768x24" ./CarlaUE4.sh -quality-level=Low
```

### 窗口 B：运行脚本

```bash
conda activate carla_conf
cd ~/autodl-tmp/SMPC_MMPreds/scripts/carla
python run_all_scenarios.py
```

---

## 10. 最小成功标准（你先只看这三条）

运行后确认：

- `~/autodl-tmp/SMPC_MMPreds/results/.../scenario_result.pkl` 存在
- 没有立刻崩溃到 Python traceback
- 日志里能看到迭代步与求解信息

只要满足以上，即可判定“环境可行性验证通过”。

---

## 11. 三策略验证（下一步）

脚本内已包含：

- `smpc_var_risk`
- `smpc_open_loop`
- `smpc_fixed_risk`

统计汇总：

```bash
cd ~/autodl-tmp/SMPC_MMPreds
python scripts/compute_scenario_results.py
```

---

## 12. 常见错误快速定位

### A. `ModuleNotFoundError: carla`

- 检查 `CARLA_ROOT` 是否正确
- 检查 `PYTHONPATH` 是否包含 `.egg` 路径
- 检查 conda 环境是否已激活

### B. `gurobi`/license 错误

- 先修 license，再继续
- `gurobi ok` 测试必须通过

### C. TF/CUDA 不匹配

- 若你用了非 Miniconda 基础镜像，容易出现
- 优先换镜像重建，避免无底洞排错

### D. CARLA 连接超时

- 确认 CarlaUE4 进程还在
- 端口是否 2000 被占用
- 客户端和服务端是否在同一机器

### E. `ERROR: Redirection (301) without location`

- 这是代理对 S3 跳转处理异常
- 不要再用 `carla-releases.s3...` 直链
- 改用 `https://tiny.carla.org/carla-0-9-10-linux`

### F. `404 Not Found` 或 `gzip: not in gzip format`

- 大概率是下载到了错误页而不是真实压缩包
- 删除坏文件后重下：

```bash
cd ~/autodl-tmp
rm -f CARLA_0.9.10.tar.gz
wget -O CARLA_0.9.10.tar.gz https://tiny.carla.org/carla-0-9-10-linux
ls -lh CARLA_0.9.10.tar.gz
file CARLA_0.9.10.tar.gz
```

- 只有 `file` 显示为 `gzip compressed data` 才执行 `tar -xzf`

---

## 13. 你每次执行后回报格式（建议）

请按这个格式发我，我会快速定位并更新本手册：

1. 执行到第几步
2. 你执行的命令（原样复制）
3. 报错完整输出（从第一行 traceback 到最后一行）
4. 你当前 `conda env list` 输出
5. 你当前 `echo $CARLA_ROOT` 与 `python -V`

---

## 14. 变更记录

- v1：初版保守路径环境手册（可执行）

