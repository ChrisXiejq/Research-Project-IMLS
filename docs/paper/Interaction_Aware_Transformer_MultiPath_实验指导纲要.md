# Interaction-aware Transformer-MultiPath 实验指导纲要

## 1. 研究动机

当前 v12/A1/A2/A3 结果表明，variable-risk SMPC 在 shared rule-aware safety supervisor 下没有稳定带来优于 fixed-risk frontier 的最终闭环指标。这不应简单写成 adaptive risk 失败，而应进一步追问：闭环效果受限于 risk allocation，还是受限于 prediction model 对交互不确定性的表达。

本阶段把研究深化为：

> 当 variable-risk allocation 被 runtime supervisor 掩盖时，interaction-aware trajectory prediction 能否提升 risk-aware SMPC 的闭环有效性？

该方向把论文从工程调参推进到模型层研究：SMPC 的 chance constraint 依赖预测分布，如果 MultiPath predictor 没有显式使用 ego-target interaction context，那么 risk allocation 再精细也可能无法产生稳定闭环收益。

## 2. 核心假设

### H-M1：当前 MultiPath 的闭环瓶颈不只在 risk allocation

已有结果：

- v12 close-stop baseline 安全通过，但 fixed frontier 和 adaptive floor_weak 差异很小。
- A2 phase-aware adaptive ablation 没有形成稳定 final-metric 优势。
- A3 risk-owned-yield 降低 nominal supervisor authority 后仍没有让 adaptive 稳定支配 fixed frontier。

解释：

- 仅改变 risk budget 不足以保证闭环收益。
- planner-facing prediction uncertainty 可能没有充分表达 ego-target interaction phase。

### H-M2：加入 ego-target interaction context 可以改善 prediction quality

模型升级：

- baseline：current CARLA-finetuned MultiPath。
- upgrade：Interaction-aware Transformer-MultiPath residual adapter。

新增 context：

- target-local ego relative position；
- ego speed；
- target speed；
- ego-target speed difference；
- ego-target yaw relation；
- ego-target distance。

期望离线指标：

- top1 ADE / FDE 下降；
- minADE / minFDE 不劣化；
- top-prob mode is best fraction 提升；
- mode entropy / best-mode probability 更合理。

### H-M3：更好的 interaction-aware prediction 应该减少 planner/supervisor mismatch

闭环指标不只看 completion time，还要看：

- supervisor active fraction；
- direct takeover fraction；
- solver failure fraction；
- min footprint separation；
- first stop distance；
- delay after target clearance。

如果 interaction-aware predictor 提升离线预测，但闭环仍无明显改善，则可形成强讨论结论：

> 在该 give-way safety architecture 中，prediction model capacity alone is not sufficient; runtime supervisor authority remains the dominant closed-loop boundary.

## 3. 模型设计

采用低风险 residual adapter，而不是推翻现有 MultiPath：

```text
image + target past states -> frozen base MultiPath -> raw MultiPath output
target past states + interaction context -> Transformer encoder -> residual output
final output = base MultiPath output + delta_scale * residual
```

优点：

- 输出接口保持 MultiPath GMM contract 不变；
- SMPC 不需要理解 Transformer，只接收原来的 mode probabilities / means / covariances；
- 旧 2-input MultiPath 模型仍可运行；
- 新 3-input interaction model 可直接通过同一 evaluator 和 CARLA planner 比较。

已新增代码入口：

- `core/scripts/models/finetune_interaction_transformer_multipath_carla.py`
- `core/scripts/models/run_interaction_transformer_multipath_carla.sh`
- `core/scripts/models/prediction_dataset_utils.py` 中的 `interaction_context_from_sample`
- `core/scripts/models/deploy_multipath_model.py` 自动兼容 2-input / 3-input 模型
- `core/scripts/carla/scenarios/run_intersection_scenario.py` 在线推理时传入 interaction context

## 4. 实验任务顺序

### Task M0：恢复或重新生成 prediction dataset

目标：得到包含 raster、past states、ego_state、target_state、future label 的 `prediction_dataset_merged`。

优先使用已有服务器结果目录：

```text
core/results/20260717_232553_prediction_dataset_collection
```

若该目录不可用，重新收集：

```bash
cd /root/autodl-tmp/Research-Project-IMLS/core/scripts/carla

RESULTS_DIR=/root/autodl-tmp/Research-Project-IMLS/core/results/$(date +%Y%m%d_%H%M%S)_prediction_dataset_collection \
PYTHON_BIN=python \
INIT_COUNT=50 \
POLICIES="smpc_var_risk" \
SAVE_RASTER=1 \
LOG_STRIDE=1 \
LOG_HORIZON=10 \
bash ./run_give_way_prediction_dataset_collection.sh
```

成功标准：

- `prediction_dataset_labeled.jsonl` 存在；
- `prediction_dataset_merged/train.jsonl`
- `prediction_dataset_merged/val.jsonl`
- `prediction_dataset_merged/test.jsonl`
- `prediction_dataset_merged/manifest.json`

### Task M1：离线 predictor benchmark

目标：补齐当前论文缺失的 predictor FDE / minADE / mode ranking evidence。

运行：

```bash
cd /root/autodl-tmp/Research-Project-IMLS/core/scripts/models

RESULT_DIR=/root/autodl-tmp/Research-Project-IMLS/core/results/20260717_232553_prediction_dataset_collection \
MERGED_DIR=/root/autodl-tmp/Research-Project-IMLS/core/results/20260717_232553_prediction_dataset_collection/prediction_dataset_merged \
BASE_MODEL=/root/autodl-tmp/Research-Project-IMLS/core/scripts/models/l5kit_multipath_10_carla_finetuned_head_best \
OUTPUT_MODEL=/root/autodl-tmp/Research-Project-IMLS/core/scripts/models/l5kit_multipath_10_carla_interaction_transformer \
EPOCHS=12 \
BATCH_SIZE=16 \
LEARNING_RATE=5e-5 \
FREEZE_BASE=true \
bash ./run_interaction_transformer_multipath_carla.sh
```

输出：

- `current_multipath_best_metrics_test.json`
- `interaction_transformer_best_metrics_test.json`
- `l5kit_multipath_10_carla_interaction_transformer_best`
- `l5kit_multipath_10_carla_interaction_transformer_history.json`

判断：

- 若 interaction model 的 top1 FDE、top1 ADE、mode-ranking 有改善，则进入闭环实验。
- 若 offline 指标不改善，先不要跑 CARLA，调整模型或学习率。

### Task M2：v12 close-stop 小矩阵闭环实验

目标：检验模型层升级是否能在 shared supervisor 下影响闭环指标。

最小矩阵：

| Predictor | Policy | Supervisor |
|---|---|---|
| current MultiPath | fixed medium | v12 reduced_intervention |
| current MultiPath | adaptive floor_weak | v12 reduced_intervention |
| interaction Transformer-MultiPath | fixed medium | v12 reduced_intervention |
| interaction Transformer-MultiPath | adaptive floor_weak | v12 reduced_intervention |

关键指标：

- gate status；
- completion time；
- first stop distance；
- min footprint separation；
- supervisor active fraction；
- solver failure fraction。

### Task M3：A3 risk-owned-yield 小矩阵闭环实验

目标：在降低 nominal supervisor authority 后，观察 interaction-aware predictor 是否让 planner-level 差异更可见。

最小矩阵同 M2，但 tuning config 使用 A3：

```text
give_way_reduced_clear_path_release_v13_risk_owned_yield.json
```

优先测试：

- `arrival_offset_m3p0`
- `arrival_offset_p0p0`
- `arrival_offset_p3p0`

### Task M4：TV speed 作为 stress axis

TV speed 可以使用，但只作为模型升级 stress test，不作为主线。

推荐点：

- 8.8 m/s
- 9.2 m/s
- 9.6 m/s

研究问题：

> interaction-aware predictor 是否在更高 TV speed 或更紧 arrival timing 下，比 current MultiPath 更能减少 supervisor intervention 或 solver failure？

## 5. 论文回收方式

### 支持性结果

如果 offline + closed-loop 都改善：

- claim：variable-risk alone is insufficient, but interaction-aware prediction improves the planner-facing uncertainty used by SMPC。
- 论文贡献从 risk allocation 扩展为 model-aware risk-aware planning。

### 混合结果

如果 offline 改善但 closed-loop 不改善：

- claim：prediction accuracy alone does not guarantee closed-loop planning gain under strong safety supervision。
- 这会强化 supervisor authority / planner-supervisor responsibility allocation 主线。

### 负结果

如果 offline 也不改善：

- claim：当前 CARLA give-way dataset 的交互多样性不足，Transformer capacity 未被有效利用。
- 后续应扩展 prediction dataset，而不是继续调 SMPC risk。

## 6. 当前阶段最明确下一步

1. 在服务器确认或重新生成 `prediction_dataset_merged`。
2. 跑 `run_interaction_transformer_multipath_carla.sh`。
3. 拉取两个 predictor metrics JSON 和 history JSON。
4. 若 offline 指标成立，再跑 v12/A3 最小闭环矩阵。
