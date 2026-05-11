# AutoDL 现代稳定版复现手册

本文档对应你的"现代化优先"目标：尽量使用当前稳定版本栈，跑通论文核心流程（三策略 + intersection 场景）。  
**本文档所有步骤均经过实际验证可成功执行（2026-05-08）。**

---

## 0. 适用范围与预期

- 目标：跑通 `Proposed (smpc_var_risk)`、`Fixed-Risk (smpc_fixed_risk)`、`Open-Loop (smpc_open_loop)`。
- 代码仓库：`Research-Project-IMLS`（已集成 `SMPC_MMPreds` 核心代码）。
- CARLA 服务端版本：**0.9.14**（官方预编译包，经验证稳定）。
- Python 客户端版本：**carla==0.9.14**。
- 现实约束：升级到新版后，指标应以"趋势一致"作为主标准，不能承诺逐数值完全一致。

### 关键注意事项（血泪教训，必读）


| 问题                                                | 原因                              | 解决方案                        |
| ------------------------------------------------- | ------------------------------- | --------------------------- |
| AutoDL 容器默认 root，UE4 拒绝以 root 运行                  | UE4 硬编码安全检查                     | 创建普通用户 `carlauser` 运行 CARLA |
| AutoDL 容器缺少 NVIDIA Vulkan ICD                     | 宿主机未挂载 Vulkan 驱动层到容器            | 使用 `-nullrhi` 绕过，对本实验无影响    |
| CARLA 0.9.15 的 `tiny.carla.org` 下载链接给的是源码仓库而非预编译包 | 包结构不完整，缺少 Engine 内置资源           | 改用 **0.9.14**，有完整预编译包       |
| `-nullrhi` 对本实验无影响                                | 实验只用 CARLA 地面真值状态，不用相机/LiDAR 图像 | 放心使用                        |


---

## 1. 新实例基础检查

```bash
# 确认 GPU 可用
nvidia-smi

# 确认磁盘空间（CARLA 约 20GB，需留足）
df -h

# 进入持久盘
cd /root/autodl-tmp
```

---

## 2. 创建 Python 实验环境

> 这一节是你在 AutoDL 上已经走通的方案，优先使用。  
> 不再推荐 `conda env create -f environment.modern.yml`（在当前网络环境下容易卡在 `Solving environment`）。

### 2.1 用 `conda create` 分步创建环境

```bash
cd ~/autodl-tmp/Research-Project-IMLS
source /root/miniconda3/etc/profile.d/conda.sh

conda env remove -n carla_modern -y || true
conda create -n carla_modern python=3.8 pip numpy scipy pandas -y \
  --override-channels \
  -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main \
  -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge
```

### 2.2 正确激活环境（关键）

如果出现 `CommandNotFoundError: conda activate`，说明当前 shell 没加载 conda 脚本。必须先执行：

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate carla_modern
```

### 2.3 确认你正在目标环境中安装包（关键）

```bash
which python
which pip
python -V
```

应看到路径包含：`/root/miniconda3/envs/carla_modern/`

### 2.4 在 `carla_modern` 内安装 Python 依赖

```bash
pip install casadi tensorflow==2.13.1 opencv-python matplotlib \
  dictor requests pygame tabulate distro networkx Shapely \
  psutil xmlschema ephem six -i https://pypi.org/simple
```

安装 CARLA Python 客户端（版本必须与服务端一致，用 **0.9.14**）：

```bash
pip install carla==0.9.14 -i https://pypi.org/simple
```

### 2.5 依赖验证

```bash
python - <<'PY'
import tensorflow as tf
import casadi
import cv2
import carla
print("tf:", tf.__version__)
print("casadi:", casadi.__version__)
print("cv2:", cv2.__version__)
print("carla import ok")
PY
```

### 2.6 常见问题与处理

- `conda env create ...` 长时间卡在 `Solving environment`：改用本节的 `conda create` 分步方案。
- `CommandNotFoundError: conda activate`：先 `source /root/miniconda3/etc/profile.d/conda.sh`。
- 安装后 `import tensorflow` 失败：通常是包装到了 base 环境。重新 `conda activate carla_modern` 后再 `pip install`。
- `pip install` 很慢：可先执行 `source /etc/network_turbo` 再安装。

---

## 3. Gurobi 安装与许可（论文 `gurobi` 路径必需）

本节为 **2026-05-12 在 AutoDL 上已验证成功** 的方案：**Gurobi Optimizer 11.0.3（Linux x64）+ `gurobipy==11.0.3` + WLS 许可文件**，与当前手册中的 **`carla_modern`（Python 3.8）** 一致，无需为 Gurobi 单独再建 Python 3.10 环境。

### 3.1 为何用 11.0.3 而不是 13

- **`carla_modern` 使用 Python 3.8** 时，公共 PyPI 上的 **`gurobipy` 通常最高到 11.0.3**，无法直接 `pip install gurobipy==13.x`。
- Gurobi **13** 的安装包内往往 **不再自带** `linux64/python` 目录，需从 `https://pypi.gurobi.com/simple` 安装 `gurobipy`；在部分 AutoDL 网络环境下该索引可能解析失败。
- **结论**：在 Python 3.8 实验环境下，**优先使用 Gurobi 11.0.3 + `gurobipy==11.0.3`**；CasADi 仍通过 `solver("gurobi", ...)` 调用，与论文实现方式一致。

> **许可版本**：请确认你的 `gurobi.lic`（WLS）允许使用 **Gurobi 11**。若许可仅绑定 Gurobi 13，则不能换用 11，应改为 **Python 3.10+ 新环境 + Gurobi 13**。

### 3.2 文件放置（建议放在仓库 `gurobi/` 下，且勿提交密钥到 Git）

在仓库根目录 `Research-Project-IMLS/gurobi/` 中准备：

| 文件 | 说明 |
|------|------|
| `gurobi11.0.3_linux64.tar.gz` | 从 [Gurobi 下载页](https://www.gurobi.com/downloads/gurobi-software/) 选择 **Gurobi Optimizer → x64 Linux → 11.0.3** |
| `gurobi.lic` | 门户生成的 **WLS** 许可文件（含 `WLSACCESSID` / `WLSSECRET` / `LICENSEID` 等，**勿推送到公开仓库**） |

### 3.3 解压与定位 `linux64`

```bash
export REPO=~/autodl-tmp/Research-Project-IMLS
cd "$REPO/gurobi"
tar -xzf gurobi11.0.3_linux64.tar.gz
find "$REPO/gurobi" -maxdepth 3 -type d -name linux64
```

常见输出为：`.../gurobi1103/linux64`（以 `find` 实际结果为准，下文用该路径）。

### 3.4 环境变量（每次跑 `--solver_backend gurobi` 前执行）

将 `GUROBI_HOME` 改为上一步 `find` 给出的 **`.../linux64`** 路径：

```bash
export REPO=~/autodl-tmp/Research-Project-IMLS
export GUROBI_HOME="$REPO/gurobi/gurobi1103/linux64"
export PATH="$GUROBI_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}"
export GRB_LICENSE_FILE="$REPO/gurobi/gurobi.lic"
# CasADi Gurobi 插件：需能加载 libgurobi<GUROBI_VERSION>.so（11.0.x 一般为 libgurobi110.so）
export GUROBI_VERSION=110
```

### 3.5 安装 Python 接口 `gurobipy`

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate carla_modern
pip install -U pip
pip install gurobipy==11.0.3 -i https://pypi.org/simple
```

### 3.6 一键加载脚本（可选，放在持久盘 `autodl-tmp`）

```bash
cat > /root/autodl-tmp/load_gurobi11.sh <<'EOF'
#!/usr/bin/env bash
export REPO=/root/autodl-tmp/Research-Project-IMLS
export GUROBI_HOME="$REPO/gurobi/gurobi1103/linux64"
export PATH="$GUROBI_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}"
export GRB_LICENSE_FILE="$REPO/gurobi/gurobi.lic"
export GUROBI_VERSION=110
EOF
chmod +x /root/autodl-tmp/load_gurobi11.sh
```

之后每次实验：

```bash
source /root/autodl-tmp/load_gurobi11.sh
conda activate carla_modern
```

### 3.7 许可与求解自检（成功标志）

```bash
python - <<'PY'
import gurobipy as gp
from gurobipy import GRB
print("gurobipy", gp.gurobi.version())

m = gp.Model("smoke")
x = m.addVar(lb=0.0, name="x")
m.setObjective(x, GRB.MINIMIZE)
m.optimize()
print("status =", m.Status)
print("gurobi_ok")
PY
```

- 日志中应出现 **Gurobi Optimizer version 11.0.3**，并打印 **Academic license** / **WLS** 相关信息。
- **`status = 2`** 表示 **`GRB.OPTIMAL`（最优）**，即 Gurobi + 许可 + 动态库均正常。
- 若报 `License expired` 或许可版本不匹配，需在 Gurobi 门户更新许可或改用与许可一致的 Optimizer 主版本。

### 3.8 与 CARLA 实验衔接

```bash
source /root/autodl-tmp/load_gurobi11.sh
conda activate carla_modern
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
cd ~/autodl-tmp/Research-Project-IMLS/core/scripts/carla
python run_all_scenarios.py ... --solver_backend gurobi
```

若此时 CasADi 仍报 **`Plugin 'gurobi' is not found`** 或警告 **`Failed to load Gurobi adaptor ... GUROBI_VERSION`**：除 `LD_LIBRARY_PATH` 外必须设置 **`export GUROBI_VERSION=110`**（与 `lib/libgurobi110.so` 对应；若你安装的是其他 11.x/12.x，用 `ls $GUROBI_HOME/lib/libgurobi*.so` 看文件名中的数字段）。确认已 `source load_gurobi11.sh` 后再跑实验。

---

## 4. 安装 CARLA 服务端（经验证可用方案）

> **版本：CARLA 0.9.14**（官方预编译包，含完整 Engine 资源和 `CarlaUE4.sh`）  
> 0.9.15 的 tiny.carla.org 链接下载的是源码仓库，**不是预编译包，无法直接运行**，请勿使用。

### 4.1 安装系统依赖

```bash
apt-get update
apt-get install -y xdg-user-dirs libomp5
```

- `xdg-user-dirs`：UE4 启动时必须调用，缺失会导致进程在写日志前直接退出（`EXIT=1`）。
- `libomp5`：CARLA 0.9.14 二进制依赖的 OpenMP 运行时。

### 4.2 创建运行用户

AutoDL 容器以 root 运行，而 UE4 拒绝 root 启动，因此必须创建普通用户：

```bash
# 若 carlauser 已存在会提示 already exists，忽略即可
useradd -m -s /bin/bash carlauser
```

### 4.3 下载 CARLA 0.9.14 官方预编译包

包体积约 3.5GB，推荐用 `wget`（可断点续传）：

```bash
cd /root/autodl-tmp
wget -c -O CARLA_0.9.14.tar.gz https://tiny.carla.org/carla-0-9-14-linux
```

若网速慢，可改用 aria2 多线程下载（需先 `apt-get install -y aria2`）：

```bash
aria2c -x 16 -s 16 -k 1M -c -o CARLA_0.9.14.tar.gz https://tiny.carla.org/carla-0-9-14-linux
```

### 4.4 解压并验证

```bash
mkdir -p /root/autodl-tmp/carla_0.9.14
tar -xzf CARLA_0.9.14.tar.gz -C /root/autodl-tmp/carla_0.9.14

# 验证：必须能看到 CarlaUE4.sh
ls /root/autodl-tmp/carla_0.9.14
```

正确的目录结构应包含：`CarlaUE4.sh`、`CarlaUE4/`、`Engine/`、`PythonAPI/` 等。  
**若没有 `CarlaUE4.sh`，说明下载的不是预编译包，需重新下载。**

### 4.5 设置目录权限

carlauser 需要能访问 `/root/autodl-tmp/carla_0.9.14`：

```bash
chown -R carlauser:carlauser /root/autodl-tmp/carla_0.9.14
chmod o+x /root
chmod o+rx /root/autodl-tmp

# 初始化 xdg 用户目录
su - carlauser -c 'xdg-user-dirs-update'

# 创建 XDG 运行时目录
mkdir -p /tmp/runtime-carlauser
chown carlauser:carlauser /tmp/runtime-carlauser
```

---

## 5. 启动 CARLA 服务端（终端 A）

### 5.1 启动命令（已验证可用）

**每次启动前先清理残留进程：**

```bash
pkill -9 -f CarlaUE4 2>/dev/null; sleep 2
```

**启动 CARLA（终端 A，会阻塞，保持运行）：**

```bash
su carlauser -c '
  export HOME=/home/carlauser
  export XDG_RUNTIME_DIR=/tmp/runtime-carlauser
  cd /root/autodl-tmp/carla_0.9.14
  LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/CarlaUE4/Plugins/Carla/CarlaDependencies/lib \
  ./CarlaUE4.sh -nullrhi -nosound -world-port=2000
'
```

**参数说明：**


| 参数                    | 说明                                            |
| --------------------- | --------------------------------------------- |
| `-nullrhi`            | 跳过 GPU 渲染硬件初始化（绕过 Vulkan/OpenGL 缺失问题），对本实验无影响 |
| `-nosound`            | 禁用音频（服务器无声卡）                                  |
| `-world-port=2000`    | 服务端监听端口（默认 2000）                              |
| `LD_LIBRARY_PATH=...` | 确保 CARLA 的 Chrono 等依赖库可被找到                    |


> **为什么用 `-nullrhi` 而不是 `-RenderOffScreen`？**  
> AutoDL 容器缺少 NVIDIA Vulkan ICD（`nvidia_icd.json`），`-RenderOffScreen` 会尝试初始化 Vulkan 并失败导致秒退。  
> 本实验的 SMPC 控制器只需要 CARLA 提供车辆位置/速度状态（地面真值），不需要相机图像，所以 `-nullrhi` 完全满足需求。

### 5.2 验证服务端已就绪（终端 B）

启动后等待约 **1~2 分钟**，然后在另一个终端检查端口：

```bash
# 07D0 是 2000 的十六进制，有输出即表示端口已监听
cat /proc/net/tcp6 | awk '{print $2}' | grep -i "07D0"
```

再用 Python 做连接测试：

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate carla_modern

python3 -c "
import carla
c = carla.Client('127.0.0.1', 2000)
c.set_timeout(10.0)
w = c.get_world()
print('CARLA OK, map:', w.get_map().name)
print('Actor blueprints:', len(w.get_blueprint_library()))
"
```

看到地图名和蓝图数量（如 `203`）即表示完全就绪。

---

## 6. 客户端连通与依赖联合检查（终端 B）

```bash
cd ~/autodl-tmp/Research-Project-IMLS
source /root/miniconda3/etc/profile.d/conda.sh
conda activate carla_modern

python - <<'PY'
import carla
import tensorflow as tf
import casadi
client = carla.Client("127.0.0.1", 2000)
client.set_timeout(10.0)
world = client.get_world()
print("carla OK:", world.get_map().name)
print("tensorflow", tf.__version__)
print("casadi", casadi.__version__)
PY
```

---

## 7. 运行论文核心实验（三策略）

### 7.1 使用 Gurobi 原始路径

```bash
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14

cd ~/autodl-tmp/Research-Project-IMLS/core/scripts/carla
python run_all_scenarios.py \
  --scenario_glob "scenario_0*.json" \
  --init_glob "ego_init_*.json" \
  --policies smpc_var_risk smpc_open_loop smpc_fixed_risk \
  --solver_backend gurobi \
  --with_notv \
  --with_notv_cl
```

这是最接近论文原始 `SMPC_MMPreds` 的路径，依赖 CasADi 的 Gurobi conic 插件和有效 Gurobi 许可。

### 7.2 无 Gurobi 近似路径

```bash
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14

cd ~/autodl-tmp/Research-Project-IMLS/core/scripts/carla
python run_all_scenarios.py \
  --scenario_glob "scenario_0*.json" \
  --init_glob "ego_init_*.json" \
  --policies smpc_var_risk smpc_open_loop smpc_fixed_risk \
  --solver_backend ipopt_approx \
  --with_notv \
  --with_notv_cl
```

`ipopt_approx` 会把三种 SMPC 策略映射到 IPOPT 近似 agent，输出目录会自动带 `_ipopt_approx` 后缀，例如 `scenario_01_ego_init_01_smpc_var_risk_ipopt_approx`。报告中应明确说明该路径保留论文核心思想和趋势对比目标，但不保证与原始 Gurobi 路径逐数值一致。

### 7.3 分阶段验证：三层检查后再全量

建议不要一上来就跑全量 `scenario_0*` × `ego_init_*`，按下面三层逐级放大；**三层都通过**后再用 7.1 / 7.2 中的全量 glob。

**通用前置（Gurobi 路径时）：**

```bash
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
source /root/autodl-tmp/load_gurobi11.sh
conda activate carla_modern
cd ~/autodl-tmp/Research-Project-IMLS/core/scripts/carla
```

终端会打印本次结果根目录，例如：`Saving experiment outputs under: .../core/results/<时间戳>/`。下文用 **`<时间戳>`** 指该目录名。

#### 第一层：最小能跑通（约几分钟级）

**目的**：CARLA、导入、蓝图、预测、**CasADi + Gurobi（或 IPOPT）**整条链不崩。

```bash
python run_all_scenarios.py \
  --scenario_glob "scenario_01.json" \
  --init_glob "ego_init_01.json" \
  --policies smpc_var_risk \
  --solver_backend gurobi \
  --with_notv \
  --with_notv_cl
```

**通过标准：**

- 终端无 traceback 退出。
- 已打印 `Saving experiment outputs under: .../core/results/<时间戳>/`。
- 该时间戳下每个子目录均有 **`scenario_result.pkl`**：

```bash
cd ~/autodl-tmp/Research-Project-IMLS/core
ls results/<时间戳>/*/scenario_result.pkl
```

#### 第二层：小矩阵三策略（约几十分钟级）

**目的**：`smpc_var_risk` / `smpc_open_loop` / `smpc_fixed_risk` 与 `notv` / `notv_cl` 均能跑完。

```bash
cd ~/autodl-tmp/Research-Project-IMLS/core/scripts/carla
python run_all_scenarios.py \
  --scenario_glob "scenario_01.json" \
  --init_glob "ego_init_01.json" \
  --policies smpc_var_risk smpc_open_loop smpc_fixed_risk \
  --solver_backend gurobi \
  --with_notv \
  --with_notv_cl
```

**通过标准：**

- 共 **5** 个子目录：`notv`、`notv_cl`、以及三个策略目录名。
- 每个目录内 **`scenario_result.pkl` 存在且体积明显非 0**（可用 `ls -lh results/<时间戳>/`）。

#### 第三层：指标与轨迹是否合理（后处理）

**目的**：排除「能跑但结果空/异常」的情况。

```bash
cd ~/autodl-tmp/Research-Project-IMLS/core
MPLBACKEND=Agg python scripts/compute_scenario_results.py \
  --results_dir ./results/<时间戳> \
  --compute_metrics
```

**通过标准：** 生成 `df_full.csv`、`df_norm.csv`、`df_final.csv`，打开检查对应 policy 有行、核心列无大面积 NaN。

可选快速看图：

```bash
MPLBACKEND=Agg python scripts/compute_scenario_results.py \
  --results_dir ./results/<时间戳> \
  --make_traj_map \
  --plot_scenario scenario_01 \
  --plot_init 1 \
  --plot_policies smpc_var_risk smpc_open_loop smpc_fixed_risk notv notv_cl \
  --tv_source_policy smpc_var_risk \
  --traj_map_name smoke_traj
```

轨迹应大致合理（无瞬间飞出地图、无整条零轨迹等明显异常）。若使用 `ipopt_approx`，`--plot_policies` 中的策略名需带 `_ipopt_approx` 后缀（与目录名一致）。

#### 再跑全量

仅当上述三层均通过后，再执行 7.1 / 7.2 中的全量命令（`scenario_0*.json`、`ego_init_*.json`）。全量结束后对**新的** `<时间戳>` 目录再运行一次 `--compute_metrics`，并按需加 `--make_traj_map` / `--make_paper_panel`。

#### 实用习惯

| 习惯 | 作用 |
|------|------|
| 每次记录 `results/<时间戳>` | 与代码版本、Gurobi / 求解器配置对应，便于追溯 |
| 小检查固定 `scenario_01` + `ego_init_01` | 可重复、便于对比回归 |
| 全量前清理残留 CARLA 进程 | 减少端口占用与 spawn 碰撞（见第 10 节） |

---

## 8. 聚合结果（无图形模式）

```bash
cd ~/autodl-tmp/Research-Project-IMLS/core
MPLBACKEND=Agg python scripts/compute_scenario_results.py \
  --results_dir ./results/<本次运行时间戳目录> \
  --compute_metrics
```

输出目录：

- `core/results/<YYYYMMDD_HHMMSS>/df_full.csv`
- `core/results/<YYYYMMDD_HHMMSS>/df_norm.csv`
- `core/results/<YYYYMMDD_HHMMSS>/df_final.csv`

说明：`run_all_scenarios.py` 在未显式传入 `--results_dir` 时，会自动保存到 `core/results/YYYYMMDD_HHMMSS/`，用于保留可追溯的多次实验记录。

若要给无 Gurobi 结果生成论文风格图，策略名需要使用 `_ipopt_approx` 后缀：

```bash
cd ~/autodl-tmp/Research-Project-IMLS/core

MPLBACKEND=Agg python scripts/compute_scenario_results.py \
  --make_traj_map \
  --plot_scenario scenario_01 \
  --plot_init 1 \
  --plot_policies smpc_var_risk_ipopt_approx smpc_open_loop_ipopt_approx smpc_fixed_risk_ipopt_approx notv notv_cl \
  --tv_source_policy smpc_var_risk_ipopt_approx \
  --traj_map_name trajectory_map_ipopt_approx

MPLBACKEND=Agg python scripts/compute_scenario_results.py \
  --make_paper_panel \
  --plot_scenario scenario_01 \
  --plot_init 1 \
  --panel_proposed_policy smpc_var_risk_ipopt_approx \
  --panel_baseline_policy smpc_open_loop_ipopt_approx \
  --panel_centerline_policy notv_cl \
  --paper_panel_name paper_panel_ipopt_approx
```


---

## 9. 一键运行（可选）

仓库已提供脚本：

```bash
cd ~/autodl-tmp/Research-Project-IMLS
bash run_modern_reproduction.sh
```

---

## 10. 常见问题速查

### CARLA 启动相关


| 报错                                                            | 原因               | 解决                                 |
| ------------------------------------------------------------- | ---------------- | ---------------------------------- |
| `Refusing to run with the root privileges.`                   | 以 root 运行 UE4    | 用 `su carlauser -c '...'`          |
| `xdg-user-dir: not found` → 秒退                                | 缺少 xdg 工具        | `apt-get install -y xdg-user-dirs` |
| `libomp.so.5: cannot open shared object file`                 | 缺少 OpenMP 库      | `apt-get install -y libomp5`       |
| `WARNING: lavapipe is not a conformant vulkan implementation` | 走了 CPU 软件 Vulkan | 改用 `-nullrhi` 启动                   |
| `bind: Address already in use` → 崩溃                           | 上次 CARLA 进程残留    | `pkill -9 -f CarlaUE4 && sleep 2`  |
| 日志为空 + `EXIT=1`                                               | 在日志系统初始化前退出      | 通常是上述某个依赖缺失                        |
| `Failed to find /Engine/EngineResources/...` → Signal 11      | 下载的是源码仓库而非预编译包   | 重新下载 0.9.14 预编译包                   |


### Python 客户端相关


| 现象                                                  | 解决                                                 |
| --------------------------------------------------- | -------------------------------------------------- |
| `Version mismatch: Client=0.9.15, Simulator=0.9.14` | `pip install carla==0.9.14`，与服务端版本保持一致             |
| `import carla` 失败                                   | 确认在 `carla_modern` 环境中，`pip install carla==0.9.14` |
| 连接超时                                                | CARLA 还没启动完，多等 1~2 分钟后重试                           |
| `Plugin 'gurobi' is not found`                        | 没有 Gurobi/CasADi 插件；使用 `--solver_backend ipopt_approx`，或安装并配置 Gurobi |


---

## 11. 已完成的现代化改造

- 新增现代环境文件：`core/env_setup/environment.modern.yml`
- 新增现代依赖文件：`core/env_setup/requirements.modern.txt`
- 新增一键脚本：`run_modern_reproduction.sh`
- 移除对旧版 `examples/synchronous_mode.py` 的依赖，改为项目内置同步模块：
  - `core/scripts/carla/utils/carla_sync_mode.py`
  - 并已接入：
    - `core/scripts/carla/scenarios/run_intersection_scenario.py`
    - `core/scripts/carla/scenarios/run_lk_scenario.py`
- 结果脚本支持 CLI 参数并默认适合服务器运行：
  - `core/scripts/compute_scenario_results.py`

---

## 12. 结果对齐建议（现代化场景）

- 对齐标准优先级：
  1. 三策略排序关系是否一致（安全/保守性/效率）
  2. 轨迹行为趋势是否一致（是否碰撞、是否偏离、是否完成任务）
  3. 指标数值是否在可接受偏差范围内
- 若需要更接近论文数值，再做"参数回调"：
  - 固定随机种子、固定地图/天气、统一初始条件
  - 调整 `N`、`dt`、风险阈值到论文同设定

