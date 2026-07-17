# 当前实验节点、Git 节点与 Retrain 可行性判断

## 1. 当前最好实验节点

当前主实验已经冻结，不再继续调主参数。冻结范围如下：

```text
frozen main result:
  core/results/20260710_164024_50init_phase_floor_final_dissertation

frozen mechanism ablation:
  core/results/20260711_120356_10init_adaptive_risk_ablation

frozen dissertation claim:
  rule-aware supervisor guarantees final traffic-rule and footprint safety;
  phase-aware adaptive-variable risk changes the SMPC solver-layer
  chance-constraint conservatism and nominal planning behaviour.
```

当前最好的主实验节点是：

```text
main result:
  core/results/20260710_164024_50init_phase_floor_final_dissertation

experiment type:
  50-init phase-aware adaptive risk final dissertation run

main comparison:
  smpc_var_risk
  smpc_fixed_risk

status:
  100/100 required SMPC rollouts PASS
  no footprint collision
  no yield-rule violation
  successful completion
```

该节点应作为当前论文主结果。它证明当前最终方法在 50 个 initial conditions 下稳定成立。

当前最好的机制消融节点是：

```text
ablation result:
  core/results/20260711_120356_10init_adaptive_risk_ablation

experiment type:
  10-init adaptive risk ablation

comparison:
  phase_floor
  no_phase_floor

status:
  both variants PASS
```

该节点用于证明 `phase-aware pre-clearance risk floor` 的贡献：

```text
critical / pre-clearance:
  with phase floor:    var - fixed tightening ≈ +0.160
  without phase floor: var - fixed tightening ≈ +0.060
```

因此当前论文证据链是：

```text
50-init main result:
  证明最终方法安全、稳定、可扩展。

10-init ablation:
  证明 phase-aware risk floor 是让 adaptive risk 贡献清晰可解释的关键机制。
```

## 2. 当前 Git 节点

冻结主实验对应的代码节点：

```text
tag:
  phase-aware-risk-50init-best-base-20260710
  frozen-main-50init-phase-aware-risk-20260716

commit:
  eea6c53f547304af92f697d683f3f12d8af70226

short:
  eea6c53

commit message:
  feat: add
```

当前工作区最新代码节点：

```text
HEAD:
  2b9e145

latest commit message:
  feat: add sea factor
```

说明：

```text
主实验冻结和复现实验应优先引用:
  frozen-main-50init-phase-aware-risk-20260716
  或 phase-aware-risk-50init-best-base-20260710
  -> eea6c53f547304af92f697d683f3f12d8af70226

当前 HEAD 已经包含后续开发变化，不应直接等同于 frozen 50-init result。
```

本轮冻结后的论文图表位于：

```text
docs/paper/figures/
```

## 3. 如果下一步演进是 Retrain 模型，首先要明确目标

当前系统使用的是已部署的 MultiPath 风格预测模型：

```text
model weights:
  core/scripts/models/l5kit_multipath_10/

anchors:
  core/scripts/models/l5kit_clusters_16.npy

runtime wrapper:
  core/scripts/models/deploy_multipath_model.py

CARLA integration:
  core/scripts/carla/scenarios/run_intersection_scenario.py
```

目前仓库中有推理模型和部署封装，但没有一条完整、可直接运行的主线训练脚本。因此，`retrain` 不是简单改一个参数，而是一个独立子项目。

在当前论文阶段，retrain 的合理目标不应该是“替代已验证的主实验”，而应是以下三者之一：

```text
目标 A：预测校准
  让 mode probability / covariance 更符合当前 give-way intersection 场景。

目标 B：场景适配
  让模型更熟悉当前 CARLA 右行无信号让行路口。

目标 C：论文扩展
  作为 future work 或 additional experiment，说明更好的 prediction model 可能进一步提升 adaptive risk。
```

不建议把 retrain 作为当前主论文必须项，因为当前 50-init 主结果和 10-init ablation 已经足够支撑当前论文主线。

## 4. 推荐路线：先做轻量校准，不直接完整重训

如果你想让 adaptive risk 的贡献进一步自然化，最推荐的不是马上 full retrain，而是做 prediction calibration / output adaptation：

```text
1. 记录当前预测输出和真实 TV future。
2. 评估 prediction ADE / FDE / NLL / calibration。
3. 对 mode probability 做 temperature scaling。
4. 对 covariance 做 scale calibration。
5. 保持 DeployMultiPath 接口不变。
6. 重新跑 10-init / 50-init，比较 closed-loop 结果。
```

优点：

```text
工作量小；
不破坏当前主线代码；
不需要完整训练数据管线；
能和 adaptive risk 逻辑自然连接，因为 adaptive risk 依赖 prediction uncertainty / interaction severity。
```

预计工作量：

```text
轻量校准:
  3-7 天

需要新增:
  prediction log extraction
  prediction metric script
  probability / covariance calibration module
  10-init validation
```

## 5. 如果坚持 Full Retrain，需要做什么

完整 retrain 至少包括以下步骤。

### Step 1：定义训练数据来源

可选数据源：

```text
1. 原始 L5Kit / nuScenes 数据
   优点：数据量大，更接近 MultiPath 原始训练设定。
   缺点：和当前 CARLA give-way 场景存在 domain gap。

2. 当前 CARLA intersection rollout 数据
   优点：最贴合论文场景。
   缺点：数据量小，需要大量 rollout 才能训练稳定。

3. 混合路线
   先使用原始数据保持泛化能力，再用 CARLA intersection 数据 fine-tune。
```

当前最合理的是第 3 种：

```text
pretrained MultiPath + CARLA give-way fine-tuning / calibration
```

### Step 2：补齐数据采集

需要从 CARLA rollout 中记录：

```text
target vehicle past states;
target vehicle future trajectory labels;
rasterized scene image;
ego pose and coordinate transform;
intersection/lane context;
prediction timestamp;
current mode probabilities, means, covariances;
ground-truth future over the same horizon.
```

要注意：

```text
训练标签必须和 DeployMultiPath 的输出坐标系、时间步长、prediction horizon 对齐。
```

### Step 3：构造 Dataset

需要把 CARLA log 转成训练样本：

```text
input:
  raster image
  past_states

label:
  future XY trajectory
  best anchor id
  residual to anchor
  covariance / likelihood target
```

这一步通常是 retrain 中最耗时的部分，因为坐标系、采样频率、anchor 对齐最容易出错。

### Step 4：恢复或重建训练代码

当前部署代码注释中指向原始训练来源：

```text
https://github.com/govvijaycal/confidence_aware_predictions/blob/main/scripts/models/multipath.py
```

需要确认：

```text
模型结构是否和当前 SavedModel 完全一致；
输出 tensor shape 是否和 DeployMultiPath._make_gmm() 兼容；
anchors 数量和 horizon 是否匹配；
TensorFlow/Keras 版本是否兼容。
```

### Step 5：训练 / 微调 / 导出

训练目标通常包括：

```text
anchor classification loss;
trajectory residual regression loss;
negative log likelihood or covariance loss;
regularization / calibration loss.
```

导出后必须保持接口兼容：

```text
tf.keras.models.load_model(model_path, compile=False)
pred = model.predict_on_batch([img, past_states])
DeployMultiPath._make_gmm(pred)
```

### Step 6：闭环验证

不能只看 prediction metrics，还必须重新跑 CARLA closed-loop：

```text
1-init sanity check;
5-init precheck;
10-init comparison;
50-init final validation if replacing main result.
```

需要同时看：

```text
prediction ADE / FDE / NLL;
mode probability calibration;
solver failure;
footprint separation;
yield order;
completion;
risk_by_conflict_distance phase summary;
supervisor intervention fraction.
```

## 6. Full Retrain 工作量评估

粗略工作量：

```text
只做 prediction output calibration:
  3-7 天

CARLA 数据采集 + prediction metric pipeline:
  1-2 周

在现有模型基础上 fine-tune 并保持接口兼容:
  2-4 周

从零整理数据、恢复训练代码、完整 retrain、再跑 closed-loop 50-init:
  4-8 周，甚至更久
```

主要风险：

```text
1. 当前仓库没有完整训练主线；
2. CARLA 数据量可能不足，容易 overfit；
3. 预测模型变了以后，所有 50-init 主结果需要重跑；
4. 新模型可能改善 prediction metrics，但不一定改善 closed-loop safety；
5. 如果新预测 covariance 更激进，可能增加 solver failure；
6. dissertation 时间成本较高，容易偏离当前已经闭环的主贡献。
```

## 7. 我的建议

当前阶段不建议把 full retrain 作为下一步主线。更稳妥的路线是：

```text
1. 保留当前 50-init + 10-init ablation 作为论文主结果；
2. 先写 Results / Discussion；
3. 把 retrain 写成 future work；
4. 如果还有时间，只做 lightweight prediction calibration；
5. calibration 成功后，把它作为 additional experiment，而不是替换主实验。
```

可以向导师这样解释：

```text
The current contribution is mainly on rule-aware supervision and phase-aware adaptive risk allocation in the SMPC layer. Retraining the prediction model is a possible extension, but it would require a separate data and training pipeline. For the current dissertation scope, I plan to keep the validated 50-init closed-loop results as the main evidence, and treat prediction-model retraining or calibration as future work or an optional additional study.
```
