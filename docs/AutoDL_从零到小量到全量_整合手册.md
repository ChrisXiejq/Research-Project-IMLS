# AutoDL：从零配置 → 小量检查 → 全量检查（整合版）

本文档基于 [AutoDL_现代稳定版复现手册.md](./AutoDL_现代稳定版复现手册.md) 整理，**不替代原文**：原文保留全部背景说明、参数解释与排错细节；本整合版只做三件事——**一条通畅的配置主线**、**去重后的命令**、**小量到全量的递进顺序**。

---

## 适用范围（与原文一致）

- **仅 intersection**：`scenario_0*.json`、`ego_init_*.json`，`run_all_scenarios.py` + `run_intersection_scenario.py`。
- **三策略**：`smpc_var_risk`、`smpc_open_loop`、`smpc_fixed_risk`。
- **栈**：CARLA **0.9.14** 服务端 + `carla==0.9.14` 客户端；Python **3.8** 环境 `carla_modern`；论文主路径为 **Gurobi 11.0.3 + gurobipy 11.0.3**（与原文第 3 节一致）。

---

## 路径约定（避免删错目录）

| 含义 | 路径示例 |
|------|-----------|
| 仓库根 | `~/autodl-tmp/Research-Project-IMLS`（持久盘，下文记为 `$REPO`） |
| CARLA 根 | `~/autodl-tmp/carla_0.9.14`（下文记为 `$CARLA_ROOT`） |
| 实验脚本目录 | `$REPO/core/scripts/carla` |
| 结果根目录 | `$REPO/core/results/<时间戳>/`（运行后终端会打印 `Saving experiment outputs under: ...`） |

**错误示例**：`/core/results/...` 表示磁盘根下的目录，**不是**项目内 `core/results`。

---

## 阶段 0：新实例基础检查

```bash
nvidia-smi
df -h
cd /root/autodl-tmp
```

---

## 阶段 1：Python 环境（从零）

```bash
export REPO=~/autodl-tmp/Research-Project-IMLS
cd "$REPO"
source /root/miniconda3/etc/profile.d/conda.sh

conda env remove -n carla_modern -y || true
conda create -n carla_modern python=3.8 pip numpy scipy pandas -y \
  --override-channels \
  -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main \
  -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge

conda activate carla_modern
which python && which pip && python -V
# 应看到路径含 /root/miniconda3/envs/carla_modern/

pip install casadi tensorflow==2.13.1 opencv-python matplotlib \
  dictor requests pygame tabulate distro networkx Shapely \
  psutil xmlschema ephem six -i https://pypi.org/simple
pip install carla==0.9.14 -i https://pypi.org/simple
```

**依赖自检（无需 CARLA 服务端）：**

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

常见问题：`CommandNotFoundError: conda activate` → 每次新 shell 先 `source /root/miniconda3/etc/profile.d/conda.sh`。`pip` 装到 base → 确认已 `conda activate carla_modern` 再安装。

---

## 阶段 2：Gurobi（论文主路径；与原文 §3 一致）

1. 在 `$REPO/gurobi/` 放置 `gurobi11.0.3_linux64.tar.gz` 与 WLS 许可 `gurobi.lic`（勿提交密钥）。
2. 解压并确认 `linux64` 路径（常见为 `gurobi1103/linux64`），见原文 **§3.3**。
3. **推荐**：一次性写入加载脚本（按你机器上实际 `GUROBI_HOME` 修改 `gurobi1103` 若不同）：

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

4. 安装 Python 接口：

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate carla_modern
pip install -U pip
pip install gurobipy==11.0.3 -i https://pypi.org/simple
```

5. **Gurobi 许可与求解自检**（成功应见 version 11.0.3、`status = 2`）：

```bash
source /root/autodl-tmp/load_gurobi11.sh
conda activate carla_modern
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

许可版本与为何选 11.0.3 见原文 **§3.1**。CasADi 报 `Plugin 'gurobi' is not found` / `GUROBI_VERSION` 见原文 **§3.8**。

---

## 阶段 3：CARLA 0.9.14 服务端（从零）

```bash
apt-get update
apt-get install -y xdg-user-dirs libomp5
useradd -m -s /bin/bash carlauser 2>/dev/null || true

cd /root/autodl-tmp
wget -c -O CARLA_0.9.14.tar.gz https://tiny.carla.org/carla-0-9-14-linux

mkdir -p /root/autodl-tmp/carla_0.9.14
tar -xzf CARLA_0.9.14.tar.gz -C /root/autodl-tmp/carla_0.9.14
ls /root/autodl-tmp/carla_0.9.14   # 必须含 CarlaUE4.sh

chown -R carlauser:carlauser /root/autodl-tmp/carla_0.9.14
chmod o+x /root
chmod o+rx /root/autodl-tmp
su - carlauser -c 'xdg-user-dirs-update'
mkdir -p /tmp/runtime-carlauser
chown carlauser:carlauser /tmp/runtime-carlauser
```

**终端 A（保持运行，启动前清理残留）：**

```bash
pkill -9 -f CarlaUE4 2>/dev/null; sleep 2
su carlauser -c '
  export HOME=/home/carlauser
  export XDG_RUNTIME_DIR=/tmp/runtime-carlauser
  cd /root/autodl-tmp/carla_0.9.14
  LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/CarlaUE4/Plugins/Carla/CarlaDependencies/lib \
  ./CarlaUE4.sh -nullrhi -nosound -world-port=2000
'
```

**终端 B（等待 1～2 分钟后，端口 + Python 连通一次做完）：**

```bash
cat /proc/net/tcp6 | awk '{print $2}' | grep -i "07D0" || true

source /root/miniconda3/etc/profile.d/conda.sh
conda activate carla_modern
python3 - <<'PY'
import carla
import tensorflow as tf
import casadi
c = carla.Client("127.0.0.1", 2000)
c.set_timeout(10.0)
w = c.get_world()
print("CARLA OK, map:", w.get_map().name)
print("blueprints:", len(w.get_blueprint_library()))
print("tensorflow", tf.__version__, "casadi", casadi.__version__)
PY
```

参数含义、`-nullrhi` 原因、CARLA 排错表见原文 **§5、§10**。

---

## 阶段 4：每次跑实验前的「统一环境块」（只复制这一段）

以下假定：**终端 A 已启动 CARLA**；**终端 B** 跑客户端与脚本。

**Gurobi 论文路径：**

```bash
export REPO=~/autodl-tmp/Research-Project-IMLS
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
source /root/miniconda3/etc/profile.d/conda.sh
conda activate carla_modern
source /root/autodl-tmp/load_gurobi11.sh
cd "$REPO/core/scripts/carla"
```

**若暂时无 Gurobi**（近似退路，结果目录名会带 `_ipopt_approx`，报告需说明），将上块中 **去掉** `source .../load_gurobi11.sh`，并在下文命令中把 `--solver_backend gurobi` 改为 `--solver_backend ipopt_approx`。

---

## 阶段 5：小量实验检查（三层递进）

固定小矩阵：`scenario_01.json` × `ego_init_01.json`。每次运行后记下终端打印的 **`<时间戳>`**，下文用该目录做检查。

### 5.1 第一层（最小冒烟）

**目的**：整条链不崩（CARLA、预测、CasADi、Gurobi 或 IPOPT 近似）。

```bash
# 已执行「阶段 4 统一环境块」后：
python run_all_scenarios.py \
  --scenario_glob "scenario_01.json" \
  --init_glob "ego_init_01.json" \
  --policies smpc_var_risk \
  --solver_backend gurobi \
  --with_notv \
  --with_notv_cl
```

**通过：** 无 traceback；`core/results/<时间戳>/` 下各子目录均有 `scenario_result.pkl`。

```bash
ls "$REPO/core/results/<时间戳>"/*/scenario_result.pkl
```

### 5.2 第二层（小矩阵三策略 + 基线）

**目的**：三 SMPC 与 `notv`、`notv_cl` 均能跑完。

```bash
python run_all_scenarios.py \
  --scenario_glob "scenario_01.json" \
  --init_glob "ego_init_01.json" \
  --policies smpc_var_risk smpc_open_loop smpc_fixed_risk \
  --solver_backend gurobi \
  --with_notv \
  --with_notv_cl
```

**通过：** `results/<时间戳>/` 下共 **5** 个策略目录；`ls -lh` 下各 `scenario_result.pkl` 非空。

### 5.3 第三层（指标与轨迹合理性）

**目的**：排除「能跑但结果异常」。

```bash
cd "$REPO/core"
MPLBACKEND=Agg python scripts/compute_scenario_results.py \
  --results_dir "./results/<时间戳>" \
  --compute_metrics
```

**通过：** 生成 `df_full.csv`、`df_norm.csv`、`df_final.csv`，核心列无大面积 NaN。

可选轨迹图（与原文命令一致，策略名随求解器调整；`ipopt_approx` 时策略名需加 `_ipopt_approx` 后缀）：

```bash
MPLBACKEND=Agg python scripts/compute_scenario_results.py \
  --results_dir "./results/<时间戳>" \
  --make_traj_map \
  --plot_scenario scenario_01 \
  --plot_init 1 \
  --plot_policies smpc_var_risk smpc_open_loop smpc_fixed_risk notv notv_cl \
  --tv_source_policy smpc_var_risk \
  --traj_map_name smoke_traj
```

**仅当 5.1～5.3 均通过**，再进入全量。

---

## 阶段 6：全量实验 + 聚合

### 6.1 全量跑 intersection（Gurobi）

```bash
# 已执行「阶段 4 统一环境块」后：
python run_all_scenarios.py \
  --scenario_glob "scenario_0*.json" \
  --init_glob "ego_init_*.json" \
  --policies smpc_var_risk smpc_open_loop smpc_fixed_risk \
  --solver_backend gurobi \
  --with_notv \
  --with_notv_cl
```

### 6.2 全量无 Gurobi（可选）

```bash
python run_all_scenarios.py \
  --scenario_glob "scenario_0*.json" \
  --init_glob "ego_init_*.json" \
  --policies smpc_var_risk smpc_open_loop smpc_fixed_risk \
  --solver_backend ipopt_approx \
  --with_notv \
  --with_notv_cl
```

### 6.3 对新时间戳做指标聚合

```bash
cd "$REPO/core"
MPLBACKEND=Agg python scripts/compute_scenario_results.py \
  --results_dir "./results/<本次全量时间戳>" \
  --compute_metrics
```

论文风格图（`ipopt_approx` 时策略名带后缀）见原文 **§8** 中 `--make_traj_map` / `--make_paper_panel` 示例。

---

## 可选：仓库一键脚本

```bash
cd ~/autodl-tmp/Research-Project-IMLS
bash run_modern_reproduction.sh
```

脚本行为以仓库内实际内容为准；若与手动分阶段冲突，**以本文「阶段 4～6」的手动顺序为准**更易排错。

---

## 极简排错索引（详情回原文 §10）

| 现象 | 优先处理 |
|------|-----------|
| UE4 拒绝 root | `su carlauser -c '...'` 启动 CARLA |
| `xdg-user-dir` / 秒退 | `apt-get install -y xdg-user-dirs` |
| `libomp.so.5` | `apt-get install -y libomp5` |
| 端口占用 | `pkill -9 -f CarlaUE4 && sleep 2` |
| 客户端与服务端版本不一致 | `pip install carla==0.9.14` |
| 无 Gurobi 插件 | `--solver_backend ipopt_approx` 或按阶段 2 配置 Gurobi |

---

## 现代化改造清单与结果对齐建议

见原文 **§11、§12**（本整合版不重复展开）。

---

**文档关系**：详细步骤、血泪注意事项、下载镜像与许可说明 → [AutoDL_现代稳定版复现手册.md](./AutoDL_现代稳定版复现手册.md)。
