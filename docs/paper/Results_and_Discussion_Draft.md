# Results and Discussion Draft

This draft is written as dissertation prose. It should be edited into the final chapter style, but the claim boundaries should be preserved.

## 5. Results

### 5.1 Predictor sanity check

The prediction module is used as an uncertainty input to the downstream SMPC planner, rather than as the main contribution of this dissertation. The available fine-tuning history shows that the CARLA-specific prediction head converged on the validation split: the best validation top-mode ADE is reported in Table R8, with the fine-tuning history stored in `core/scripts/models/l5kit_multipath_10_carla_finetuned_head_history.json`. The closed-loop validation run also completed for both fixed-risk and adaptive-risk SMPC with low solver failure fractions.

This evidence is sufficient to justify using the predictor in closed-loop planning experiments, but it should not be overclaimed. The local repository does not yet contain a complete test-set predictor benchmark with top1 FDE, minADE/minFDE, mode-ranking accuracy, calibration, and split-leakage checks. Therefore, the dissertation should present the predictor as a sanity-checked component of the planning stack, not as an independently solved prediction problem.

### 5.2 Supervisor ablation: source of conservative early stopping

The formal supervisor ablation answers the first major experimental question: whether the conservative early stopping is caused by the SMPC risk policy or by the rule-aware supervisor. Under the full supervisor, the fixed-risk policy first stops at approximately `8.403` m from the conflict boundary, with about `8.040` s of waiting after the first stop. Under the reduced-intervention supervisor, the corresponding first stop distance decreases to approximately `5.263` m, and the waiting time drops to about `4.200` s.

The same pattern appears for the adaptive-risk policy, so the improvement cannot be attributed to adaptive risk alone. The result supports a clear interpretation: the original conservative behaviour is primarily a consequence of the shared rule-aware yield logic. This is a strong result because it separates planner-layer risk allocation from runtime safety authority.

### 5.3 Baseline progression: from early braking to close-stop v12

The v10-v12 progression establishes the final shared baseline used by the later frontier and ablation experiments. v10 makes the SMPC approach braking executable by forcing shaped-reference linearization. v11 introduces planner-ownership stress, reducing early nominal takeover by the supervisor. v12 then moves the stop clearance to 4.0 m while preserving the post-CARLA safety gate.

In v12, all fixed-risk frontier arms and the adaptive floor_weak arm pass. The adaptive arm completes in `10.100` s with a first stop distance of `4.509` m and a minimum footprint separation of `1.290` m. This validates v12 as a close-stop shared baseline. It does not, however, establish adaptive superiority, because the fixed-risk frontier also passes with similar final behaviour.

### 5.4 Fixed-risk frontier and difficulty sweeps

The target-speed and arrival-gap sweeps test whether simple scenario difficulty reveals a stable fixed-risk weakness. The coarse target-speed sweep produced one boundary event for fixed conservative at 9.0 m/s, but the fine sweep around the same speed did not reproduce it. This prevents using speed-only variation as a main proof of adaptive advantage.

The A1 arrival-gap sweep is more informative as a sensitivity study. At `arrival_offset_m3p0`, adaptive floor_weak is fast but has the lowest footprint margin. At `arrival_offset_p3p0`, adaptive has the highest safety margin but is slower than fixed aggressive and fixed medium. Therefore, arrival timing changes the trade-off surface, but it does not create a stable fixed-risk failure mode. The correct conclusion is that fixed risk must be evaluated as a frontier rather than as a single baseline.

### 5.5 Adaptive mechanism ablation

A2 tests whether the phase-aware adaptive risk mechanism is necessary for the observed final performance. The result is negative but useful. At `arrival_offset_m3p0`, full adaptive completes in `10.650` s with footprint separation `1.265` m, while fixed medium completes in `10.350` s with footprint separation `1.653` m. At `arrival_offset_p3p0`, phase-blind adaptive is faster than full adaptive with nearly the same margin.

This means phase-aware risk allocation is visible in the risk tightening buckets, but it does not reliably transfer into better final executed metrics under the shared supervisor. This negative result is important: it prevents the dissertation from overclaiming adaptive-risk dominance and motivates the later supervisor-authority experiment.

### 5.6 A3 risk-owned-yield: lowering nominal supervisor authority

A3 changes the architecture rather than the scenario difficulty. The reduced supervisor no longer takes over for nominal overlap/hold conditions; emergency braking-distance and footprint-clearance guards remain active. This tests whether risk policy differences become more visible when nominal yield ownership shifts from deterministic supervisor logic toward the SMPC/risk layer.

The experiment remains safe: all A3 runs pass the post-CARLA gate, and `yield_risk_owned_yield_enabled` is active for almost all frames. However, adaptive risk still does not dominate the fixed-risk frontier. At `arrival_offset_p3p0`, adaptive achieves the highest footprint margin, `1.852` m, but it completes in `11.450` s, while fixed medium completes in `9.850` s with a lower but still passing margin of `1.706` m.

The result supports the supervisor-authority thesis but not an adaptive-dominance thesis. Lowering nominal supervisor authority makes policy separation more meaningful and preserves safety, but fixed-risk frontier points remain competitive. Adaptive risk is best described as a high-safety trade-off point in this scenario.

### 5.7 Solver infeasibility and final safety

Solver infeasibility is reported separately from final post-CARLA safety. In v12, infeasible steps are low and phase-localized, mainly around critical pre-clearance phases. The larger sweep summaries provide solver failure fractions and final gates, but not per-step phase diagnostics for every run. The paper should therefore avoid a single aggregate feasibility statement. The correct interpretation is that solver-layer infeasibility can occur locally while the closed-loop system still passes the final safety gate.

## 6. Discussion

### 6.1 What the experiments prove

The strongest result is not that adaptive risk beats fixed risk. The strongest result is the decomposition of closed-loop give-way behaviour into planner risk allocation and runtime safety authority. The supervisor ablation shows that conservative early stopping is primarily caused by shared rule-aware yield logic. The v10-v12 progression shows that the system can be tuned from far early stops to a close-stop 4.0 m baseline while retaining safety. These results directly address the practical concerns raised during supervision.

### 6.2 Why adaptive risk does not dominate in final metrics

The fixed-risk frontier remains strong across v12, A1, A2, and A3. This is not simply a failed adaptive experiment. It shows that in a rule-constrained scenario with a runtime safety supervisor, final executed trajectories are partly compressed by shared safety logic and reference shaping. A planner can have different risk allocation internally, but that difference may not appear as a better final trajectory if the supervisor still defines the effective yield boundary.

### 6.3 Supervisor authority as the central research axis

A3 provides the most research-oriented result. By reducing nominal supervisor takeover, it tests whether risk policy differences become more visible when responsibility shifts toward the SMPC layer. The answer is mixed: the system remains safe and policy separation is visible, but fixed risk remains competitive. This supports the broader claim that adaptive risk should be evaluated together with responsibility allocation and supervisor burden, not only through final completion time and safety margin.

### 6.4 Limitations

There are three main limitations. First, the predictor evidence is currently a sanity check rather than a complete benchmark; test-set FDE, minADE/minFDE, mode ranking, and split integrity should be added if the thesis needs a stronger prediction section. Second, the experiments focus on a specific give-way scenario and a hard init01 family of difficulty variations; claims should not generalize to all intersections. Third, adaptive risk is only evaluated through the implemented phase-aware design and risk-owned-yield variant. Other adaptive risk formulations may behave differently.

### 6.5 Final thesis position

The final thesis should claim that risk-aware SMPC under rule-aware supervision can be diagnosed and tuned to produce closer, safe give-way behaviour, and that supervisor authority determines whether adaptive risk allocation is visible in closed-loop metrics. It should not claim universal adaptive-risk superiority over a fixed-risk frontier. The negative and mixed adaptive results are part of the contribution because they reveal where risk adaptation is masked by runtime safety architecture.
