# Day 3：GMM 评估器、校准与部署等价报告

> 执行日期：2026-07-31
>
> 数据：V1 deterministic negative-control dataset
>
> 独立 rollouts：validation 5，test 5
>
> 每个 split 的 full-horizon windows：305

## 1. 结论

Day 3 的 evaluator 完成门已通过，但旧模型的正式部署门未通过。

已经实现并验证：

1. evaluator 与 `DeployMultiPath` 使用同一 MultiPath raw-output decoder；
2. 同一合成 raw output 的 probabilities、means 和 covariances 等价；
3. 同一真实 raster sample 的预处理输入、probabilities、means 和 covariances 完全等价；
4. mixture trajectory NLL 与 pointwise mixture NLL；
5. 2D 1σ/2σ/3σ covariance coverage；
6. finite、symmetric、positive-definite covariance audit；
7. rollout-level macro aggregation；
8. validation-only temperature 与 covariance scaling；
9. test-side calibration fitting 已在代码中强制禁止；
10. B1 和 T0 均能生成完整 accuracy + calibration report。

Day 3 同时发现一个此前未识别的关键缺陷：

```text
V1 raster logger 使用 cv2.imwrite；
旧训练/evaluator 使用 TensorFlow RGB decoder；
在线 CARLA 直接使用 rasterizer 内存数组；
因此旧训练输入与在线部署输入通道顺序不一致。
```

旧报告中的约 `0.026 m` ADE 是 training-loader contract 下的 offline 指标，不是 deployment-equivalent 指标。使用与在线 CARLA 完全一致的输入后：

```text
B1 test ADE = 0.819 m
T0 test ADE = 0.595 m
```

T0 仍相对 B1 改善，但两个旧 checkpoint 都不能作为正式 V2 模型结论。正式 B1 必须在 V2 共享 raster/feature builder 下重新训练或 fine-tune。

## 2. 唯一 GMM 解码 contract

共享实现：

```text
core/scripts/models/multipath_gmm_utils.py
```

部署与离线 evaluator 均调用：

```text
decode_multipath_raw(...)
```

### 2.1 Raw output

MultiPath 输出：

```text
K × T × [dx, dy, raw_std_1, raw_std_2, theta]
+ K mode logits
```

当前模型：

```text
K = 16
model T = 25
evaluation T = first 10 steps
raw output width = 2,016
```

### 2.2 Means

```text
mu[k,t] = anchor[k,t] + [dx, dy]
```

### 2.3 Probabilities

未校准：

```text
p = softmax(logits)
```

temperature calibration：

```text
p_tau = softmax(logits / tau)
```

`tau` 只允许由 validation rollouts 选择。

### 2.4 Covariances

历史 contract：

```text
std_1 = exp(abs(raw_std_1))
std_2 = exp(abs(raw_std_2))
R = rotation(theta)
Sigma = R diag(std_1², std_2²) Rᵀ
```

post-hoc covariance scale：

```text
Sigma_calibrated = c × Sigma
```

这里 `c` 明确定义为完整 2×2 covariance matrix 的 multiplier，而不是 standard-deviation multiplier。

## 3. 等价验证

### 3.1 Shared decoder 对历史 TensorFlow 公式

确定性合成 raw tensor：

| Quantity | 最大绝对差 |
| --- | ---: |
| Probability | `1.49e-8` |
| Mean | `0` |
| Covariance | `1.58e-6` |

差异仅来自 NumPy/TensorFlow 浮点运算顺序。

### 3.2 Offline wrapper 对 deployment wrapper

identity 和非 identity calibration 两组：

| Quantity | 最大绝对差 |
| --- | ---: |
| Probability | `0` |
| Mean | `0` |
| Covariance | `0` |

### 3.3 真实 sample

验证 sample：

```text
split = validation
source_subrun = scenario_uk_give_way_ego_init_41_smpc_var_risk
sample_id = 0
```

应用 B1 validation calibration 后：

| Quantity | 最大绝对差 |
| --- | ---: |
| ResNet preprocessed raster | `0` |
| Probability | `0` |
| Mean | `0` |
| Covariance | `0` |

这满足 Day 3 的核心完成门：

```text
同一真实 sample 的 evaluator 与 deployment 数值一致。
```

## 4. Raster channel mismatch

### 4.1 形成过程

`SemBoxRasterizer` 生成内存数组，颜色变量按 RGB 语义命名。在线部署直接执行：

```text
in-memory raster
→ ResNet preprocess_input
→ model
```

V1 logger 则执行：

```text
in-memory raster
→ cv2.imwrite
```

OpenCV 将输入解释为 BGR。旧训练 loader 再执行：

```text
tf.image.decode_png
```

TensorFlow 将文件解释为 RGB，因此返回数组的第一/第三通道相对原在线数组互换。

### 4.2 为什么旧 offline 数字异常好

旧 fine-tuning 和旧 evaluator 使用相同的 RGB-decoded disk raster，因此内部彼此一致，可以得到：

```text
B1 ADE ≈ 0.0268 m
T0 ADE ≈ 0.0256 m
```

但这个 contract 不等于在线 CARLA。旧数字仍可作为“训练 loader 内部拟合”诊断，不能作为 deployment-equivalent accuracy。

### 4.3 Day 3 修正

V1 deployment-equivalent evaluator 使用：

```text
cv2.imread
```

它能恢复由 `cv2.imwrite` 写入的原始 channel bytes，再使用与在线相同的 ResNet preprocessing。

正式 V2 必须在 manifest 中记录 raster channel contract，并在 Day 4 建立共享 loader/equivalence test。禁止继续使用未声明语义的通用 PNG decoder。

## 5. 指标定义

### 5.1 Trajectory mixture NLL

同一 mode 被视为整个 horizon 的 latent mode：

```text
NLL_i = -1/T log Σ_k p_k Π_t N(y_t; mu_k,t, Sigma_k,t)
```

每个 rollout 先对其 windows 求均值，再对独立 rollouts 做 macro mean。Calibration grid 只优化 validation rollout macro NLL。

### 5.2 Pointwise mixture NLL

诊断指标：

```text
-1/T Σ_t log Σ_k p_k N(y_t; mu_k,t, Sigma_k,t)
```

它允许每个 timestep 隐式切换 mode，不作为 primary NLL。

### 5.3 2D coverage

top-probability mode 的 Mahalanobis distance 与 2D chi-square thresholds 比较：

| 名称 | Threshold | Nominal coverage |
| --- | ---: | ---: |
| 1σ | 2.30 | 0.6827 |
| 2σ | 6.18 | 0.9545 |
| 3σ | 11.83 | 0.9973 |

Coverage MAE 是三个 empirical coverage 与 nominal coverage 绝对误差的均值。

### 5.4 Covariance gate

每个 2×2 covariance 必须：

- finite；
- symmetric；
- determinant > 0；
- minimum eigenvalue > 0。

B1/T0 validation/test 的 invalid covariance count 均为 0。

## 6. B1 deployment-equivalent 结果

### 6.1 Validation-selected calibration

只使用 init 41–45：

```text
temperature tau = 1.7817974363
covariance multiplier c = 0.0752120619
```

搜索目标：

```text
validation rollout-macro trajectory mixture NLL per step
```

### 6.2 Accuracy

| Split | Top-1 ADE | Top-1 FDE | Rollout-macro P90 FDE |
| --- | ---: | ---: | ---: |
| Validation | 0.820 m | 1.568 m | 2.445 m |
| Test | 0.819 m | 1.565 m | 2.443 m |

### 6.3 NLL 与 coverage

| Split | State | Trajectory NLL/step | Coverage MAE | 1σ | 2σ | 3σ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Validation | raw | 2.068 | 0.0646 | 0.848 | 0.952 | 0.971 |
| Validation | calibrated | 0.458 | 0.2824 | 0.389 | 0.629 | 0.770 |
| Test | raw | 2.069 | 0.0651 | 0.850 | 0.952 | 0.971 |
| Test | calibrated | 0.460 | 0.2821 | 0.390 | 0.627 | 0.771 |

NLL 明显改善，但 marginal coverage 显著恶化。原因是单一 `c` 为了提高 joint trajectory likelihood 把 covariance 缩得过小，而错误均值和 horizon-dependent residual 不能由一个 global scale 修复。

因此 B1 calibration 的正确结论不是“校准成功”，而是：

> Validation-only NLL scaling was numerically stable but did not jointly calibrate marginal 2D coverage under the legacy input mismatch.

## 7. T0 Transformer 对照

### 7.1 Validation-selected calibration

```text
temperature tau = 2.2449240966
covariance multiplier c = 0.0752120619
```

### 7.2 Accuracy

| Split | Top-1 ADE | Top-1 FDE | Rollout-macro P90 FDE |
| --- | ---: | ---: | ---: |
| Validation | 0.584 m | 1.022 m | 1.158 m |
| Test | 0.595 m | 1.047 m | 1.164 m |

相对 B1 test：

```text
ADE reduction ≈ 27.3%
FDE reduction ≈ 33.1%
rollout-macro P90 FDE reduction ≈ 52.4%
```

这说明 Transformer residual adapter 的模型方向仍有信号，但绝对误差和输入 mismatch 使其不能成为正式 interaction 证据。

### 7.3 NLL 与 coverage

| Split | State | Trajectory NLL/step | Coverage MAE | 1σ | 2σ | 3σ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Validation | raw | 2.037 | 0.1080 | 0.972 | 0.981 | 0.989 |
| Validation | calibrated | 0.492 | 0.2024 | 0.401 | 0.732 | 0.894 |
| Test | raw | 2.039 | 0.1064 | 0.968 | 0.980 | 0.988 |
| Test | calibrated | 0.489 | 0.2065 | 0.402 | 0.725 | 0.889 |

T0 calibration 同样改善 NLL、恶化 coverage。它的 test calibrated NLL `0.489` 还略差于 B1 的 `0.460`，因此不能把点误差下降写成 distribution quality 的全面改善。

## 8. `exp(abs(raw))` 的量化

### 8.1 B1

Test raw axis standard deviation：

```text
mean = 1.014 m
p90 = 1.033 m
theoretical minimum = 1.0 m
```

点预测 FDE 已达到约 1.565 m，因此 raw covariance 的 1σ/2σ/3σ coverage 分别为：

```text
0.850 / 0.952 / 0.971
```

它不是 uniformly correct：1σ over-coverage，3σ under-coverage。

### 8.2 T0

Test raw axis standard deviation：

```text
mean = 1.053 m
p90 = 1.113 m
```

Coverage：

```text
0.968 / 0.980 / 0.988
```

相对 nominal，T0 在 1σ 尤其明显 over-cover。`exp(abs(raw))` 的 minimum-1-m constraint 会掩盖均值误差和 head quality，不能被直接解释为可靠 uncertainty。

## 9. Calibration 结论

Day 3 证明了三个不同问题必须分开：

1. covariance 是否数学合法；
2. mixture NLL 是否改善；
3. marginal 2D coverage 是否接近 nominal。

B1/T0 都满足数学合法性，但 validation-NLL-optimal global scale 不能同时改善 coverage。因此正式 T2：

- 仍以 validation rollout-macro mixture NLL 作为 primary；
- 同时设置 coverage non-regression gate；
- 必须报告 horizon-wise coverage；
- global scale 失败时允许 horizon-wise covariance scale；
- 不允许因为 NLL 改善就声称 uncertainty calibration 成功；
- calibration 参数必须随模型 artifact 保存并由 deployment 加载。

## 10. 对正式实验设计的影响

### 10.1 B1 重新定义

旧 checkpoint 改名为：

```text
B1-legacy-channel-mismatch
```

正式 B1 必须：

1. 使用 V2 canonical raster contract；
2. 使用与 online deployment 相同的 feature builder；
3. 在 V2 grouped train split 上 fine-tune；
4. validation 选择 checkpoint/calibration；
5. test 只评一次；
6. 与 B2-M/B2-D/T1/T2 使用相同 evaluator。

这不是扩大课题，而是修复所有模型公平比较所必需的输入一致性。

### 10.2 T0 的角色

T0 仍只作为历史 pilot：

- 它证明 residual Transformer 可以改变点预测；
- 它相对 B1 在 deployment-equivalent test 上有方向正确的 point improvement；
- 但它没有真实 temporal interaction sequence；
- 它和 B1 都受旧 channel mismatch 影响；
- 它的 distribution calibration 没有通过 coverage gate。

### 10.3 对论文论点的强化

Day 3 支持一个比“Transformer 误差更低”更严谨的论点：

> Predictor improvements relevant to adaptive-risk planning require an end-to-end numerical contract: identical raster semantics, identical GMM decoding, rollout-level evaluation, and uncertainty checks that distinguish likelihood from marginal coverage.

这直接连接原 adaptive-risk 主题，因为 SMPC 消费的是 probabilities 和 covariances，而不只是 ADE。

## 11. 代码与机器可读证据

代码：

```text
core/scripts/models/multipath_gmm_utils.py
core/scripts/models/evaluate_multipath_model_on_dataset.py
core/scripts/models/deploy_multipath_model.py
core/scripts/models/verify_multipath_gmm_equivalence.py
core/scripts/models/verify_multipath_sample_equivalence.py
core/scripts/evaluation/gmm_prediction.py
```

报告：

```text
docs/paper/generated/day3/gmm_evaluator_deployment_equivalence.json
docs/paper/generated/day3/b1_real_sample_evaluator_deployment_equivalence.json
docs/paper/generated/day3/b1_validation_calibration.json
docs/paper/generated/day3/b1_validation_accuracy_calibration.json
docs/paper/generated/day3/b1_test_accuracy_calibration.json
docs/paper/generated/day3/t0_validation_calibration.json
docs/paper/generated/day3/t0_validation_accuracy_calibration.json
docs/paper/generated/day3/t0_test_accuracy_calibration.json
```

## 12. Day 3 checklist

- [x] evaluator/deployment 共用 GMM decoder；
- [x] historical TensorFlow formula parity；
- [x] synthetic raw-output equivalence；
- [x] real raster sample input/output equivalence；
- [x] raster channel mismatch 已定位；
- [x] mixture trajectory NLL；
- [x] pointwise mixture NLL；
- [x] 2D 1σ/2σ/3σ coverage；
- [x] invalid covariance audit；
- [x] rollout-level aggregation；
- [x] `exp(abs(raw))` 已量化；
- [x] validation-only temperature/covariance scaling；
- [x] test calibration fitting 已程序化禁止；
- [x] B1 完整 report；
- [x] T0 同协议诊断；
- [x] calibration failure 已按指标如实报告。

## 13. Day 4 的确定入口

Day 4 必须优先修复输入契约，再实现 reactive target：

1. 定义 V2 raster channel contract；
2. 实现 offline/online 共用 raster loader/preprocessor；
3. 修改 V2 logger，确保 disk raster 解码后与 online array 相同；
4. 增加逐像素 equivalence test；
5. 实现 aligned ego-target pose/velocity history；
6. 记录 6×12 interaction sequence 和 mask；
7. 实现 defensive-reactive target；
8. 记录 trigger/release/TTC/desired speed/actual speed；
9. 新增 V2 单场景 collection smoke。

阻断规则：

```text
raster offline/online 不一致：不采集正式 V2；
interaction feature offline/online 不一致：不训练；
旧 B1/T0 数字不得进入正式模型主表。
```
