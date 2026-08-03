# Canonical thesis tables

> Generated from `paper_results_manifest.json`; do not edit values manually.

## Table 1: table01_dataset_split_counts.csv

| split | init_ids | rollouts | raw_samples | usable_samples | full_horizon_samples | partial_horizon_samples |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 1–40 | 160 | 9121 | 4036 | 2596 | 1440 |
| val | 41–45 | 20 | 1034 | 506 | 326 | 180 |
| test | 46–50 | 20 | 1075 | 495 | 315 | 180 |

## Table 2: table02_validation_5models_3seeds.csv

| variant | seed | best_epoch | validation_macro_nll | validation_top1_ade_m | reactive_top1_ade_m | latency_ms_per_sample |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B1 | 11 | 20 | 1.86086 | 0.115086 | 0.171505 | 16.7159 |
| B1 | 23 | 20 | 1.86033 | 0.118937 | 0.171275 | 16.9328 |
| B1 | 37 | 20 | 1.86055 | 0.112022 | 0.17087 | 16.3267 |
| B2-D | 11 | 20 | 1.87274 | 0.262786 | 0.412191 | 18.3709 |
| B2-D | 23 | 19 | 1.87284 | 0.264642 | 0.402024 | 17.6443 |
| B2-D | 37 | 20 | 1.87196 | 0.259166 | 0.40524 | 20.1465 |
| B2-M | 11 | 18 | 1.99704 | 0.92536 | 1.05356 | 18.319 |
| B2-M | 23 | 19 | 2.02872 | 1.09935 | 1.22552 | 16.4861 |
| B2-M | 37 | 20 | 2.02553 | 1.06293 | 1.17982 | 18.0465 |
| T1 | 11 | 19 | 2.00296 | 0.953942 | 1.06607 | 18.6889 |
| T1 | 23 | 20 | 2.00883 | 0.965192 | 1.1064 | 16.8058 |
| T1 | 37 | 20 | 2.02371 | 1.05631 | 1.17175 | 16.6064 |
| T2 | 11 | 20 | 1.87893 | 0.290117 | 0.434355 | 18.5379 |
| T2 | 23 | 18 | 1.87789 | 0.285484 | 0.432662 | 17.9948 |
| T2 | 37 | 20 | 1.87727 | 0.283028 | 0.429114 | 17.1447 |

## Table 3: table03_frozen_test_and_b0_control.csv

| variant | seed | validation_rank | test_macro_nll | test_top1_ade_m | test_top1_fde_m | test_rollouts | test_init_groups |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B1 | 37 | 1 | 1.85709 | 0.105876 | 0.129168 | 20 | 5 |
| B2-M | 37 | 5 | 2.02441 | 1.04728 | 1.73007 | 20 | 5 |
| B2-D | 11 | 2 | 1.87279 | 0.225516 | 0.383177 | 20 | 5 |
| T1 | 23 | 4 | 2.00375 | 0.927625 | 1.70424 | 20 | 5 |
| T2 | 23 | 3 | 1.87815 | 0.245689 | 0.402652 | 20 | 5 |
| B0 pretrained control | n/a | n/a | 2.17071 | 1.29879 | 2.68451 | 20 | 5 |

## Table 4: table04_calibration_aggregate_vs_response_tail.csv

| variant | subset | samples | uncalibrated_macro_nll | calibrated_macro_nll | uncalibrated_coverage_mae | calibrated_coverage_mae | top1_ade_m |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | all | 315 | 2.17071 | 0.582095 | 0.0553085 | 0.406844 | 1.29879 |
| B0 | response_active | 15 | 2.47177 | 2.95894 | 0.153722 | 0.418167 | 1.7634 |
| B1 | all | 315 | 1.85709 | -2.06857 | 0.114107 | 0.0765783 | 0.105876 |
| B1 | response_active | 15 | 2.07631 | 8.57283 | 0.107478 | 0.442611 | 0.942005 |

## Table 5: table05_day10_predictor_risk_frontier.csv

| predictor | risk_policy | target_style | rollouts | adjusted_delay_s | footprint_margin_m | solver_failure_fraction | supervisor_active_fraction | observed_collisions | yield_success_rate |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | adaptive | assertive | 5 | 8.22 | 1.24958 | 0.0038387 | 0.139163 | 0 | 1 |
| B0 | adaptive | reactive | 5 | 8.67 | 1.24704 | 0.00356766 | 0.152921 | 0 | 1 |
| B0 | fixed_aggressive | assertive | 5 | 8.33 | 1.28833 | 0.00379462 | 0.137564 | 0 | 1 |
| B0 | fixed_aggressive | reactive | 5 | 8.81 | 1.22943 | 0.00352018 | 0.153062 | 0 | 1 |
| B0 | fixed_conservative | assertive | 5 | 8.26 | 1.32232 | 0.00579064 | 0.137179 | 0 | 1 |
| B0 | fixed_conservative | reactive | 5 | 8.79 | 1.26085 | 0.00449908 | 0.153279 | 0 | 1 |
| B0 | fixed_medium | assertive | 5 | 8.23 | 1.32656 | 0.0057918 | 0.137659 | 0 | 1 |
| B0 | fixed_medium | reactive | 5 | 9.04 | 1.20366 | 0.00338669 | 0.149293 | 0 | 1 |
| B1 | adaptive | assertive | 5 | 8.51 | 1.25408 | 0.00372073 | 0.135056 | 0 | 1 |
| B1 | adaptive | reactive | 5 | 8.59 | 1.20021 | 0.00441131 | 0.155127 | 0 | 1 |
| B1 | fixed_aggressive | assertive | 5 | 8.19 | 1.25328 | 0.00383846 | 0.139151 | 0 | 1 |
| B1 | fixed_aggressive | reactive | 5 | 8.34 | 1.18563 | 0.00365527 | 0.159465 | 0 | 1 |
| B1 | fixed_conservative | assertive | 5 | 8.08 | 1.26162 | 0.00487195 | 0.140574 | 0 | 1 |
| B1 | fixed_conservative | reactive | 5 | 9.15 | 1.12466 | 0.0032598 | 0.142838 | 0 | 1 |
| B1 | fixed_medium | assertive | 5 | 8.87 | 1.25652 | 0.00438394 | 0.131112 | 0 | 1 |
| B1 | fixed_medium | reactive | 5 | 8.99 | 1.19139 | 0.0034226 | 0.151748 | 0 | 1 |

## Table 6: table06_timing_robustness_key_contrasts.csv

| scope | contrast | metric | effect | ci95_low | ci95_high | exact_p | holm_p | independent_init_groups |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| synthesis_predictor_pooled_primary | B1_minus_B0__fixed_medium__all_offsets | target_clearance_adjusted_completion_delay_s | -0.37 | -0.716667 | -0.0233333 | 0.1875 | 1 | 5 |
| synthesis_predictor_pooled_primary | B1_minus_B0__fixed_medium__all_offsets | min_footprint_separation_m | -0.0693515 | -0.198748 | 0.00360897 | 0.375 | 1 | 5 |
| synthesis_predictor_pooled_primary | B1_minus_B0__fixed_medium__all_offsets | solver_failure_fraction | 6.70049e-05 | -0.000352312 | 0.00039364 | 0.8125 | 1 | 5 |
| synthesis_predictor_pooled_primary | B1_minus_B0__fixed_medium__all_offsets | supervisor_active_fraction | 0.00495588 | -6.07643e-05 | 0.010717 | 0.25 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_m3 | target_clearance_adjusted_completion_delay_s | -0.755 | -1.5 | -0.01 | 0.1875 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_m3 | min_footprint_separation_m | -0.121245 | -0.347195 | -0.00252608 | 0.0625 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_m3 | solver_failure_fraction | 0 | 0 | 0 | 1 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_m3 | supervisor_active_fraction | 0.0113888 | -0.000876703 | 0.0246111 | 0.3125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_0 | target_clearance_adjusted_completion_delay_s | 0.295 | -0.185 | 0.815 | 0.5 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_0 | min_footprint_separation_m | -0.0411561 | -0.115977 | 0.0058892 | 0.3125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_0 | solver_failure_fraction | -0.000685974 | -0.00156 | -0.000149383 | 0.125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_0 | supervisor_active_fraction | -0.00204586 | -0.00932562 | 0.00478179 | 0.625 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_p3 | target_clearance_adjusted_completion_delay_s | -0.65 | -1.18 | -0.145 | 0.125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_p3 | min_footprint_separation_m | -0.0456538 | -0.129888 | 0.0222023 | 0.375 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_p3 | solver_failure_fraction | 0.000886989 | 0.000229864 | 0.0014824 | 0.125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__fixed_medium__offset_p3 | supervisor_active_fraction | 0.0055247 | 0.00164274 | 0.00976305 | 0.125 | 1 | 5 |
| synthesis_predictor_pooled_primary | B1_minus_B0__adaptive__all_offsets | target_clearance_adjusted_completion_delay_s | -0.336667 | -0.665 | 0.015 | 0.25 | 1 | 5 |
| synthesis_predictor_pooled_primary | B1_minus_B0__adaptive__all_offsets | min_footprint_separation_m | -0.0354984 | -0.144504 | 0.05024 | 0.6875 | 1 | 5 |
| synthesis_predictor_pooled_primary | B1_minus_B0__adaptive__all_offsets | solver_failure_fraction | 0.000912748 | 0.000364078 | 0.00148256 | 0.125 | 1 | 5 |
| synthesis_predictor_pooled_primary | B1_minus_B0__adaptive__all_offsets | supervisor_active_fraction | 0.00521977 | -0.000909997 | 0.0111548 | 0.25 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_m3 | target_clearance_adjusted_completion_delay_s | -0.75 | -1.545 | -0.04 | 0.1875 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_m3 | min_footprint_separation_m | -0.160687 | -0.435263 | 0.0532529 | 0.4375 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_m3 | solver_failure_fraction | 0 | 0 | 0 | 1 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_m3 | supervisor_active_fraction | 0.0113394 | -0.00309672 | 0.028511 | 0.375 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_0 | target_clearance_adjusted_completion_delay_s | 0.105 | -0.395 | 0.715 | 0.8125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_0 | min_footprint_separation_m | -0.0211597 | -0.0963098 | 0.024159 | 0.9375 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_0 | solver_failure_fraction | 0.000362839 | -3.43965e-05 | 0.00101314 | 0.5 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_0 | supervisor_active_fraction | -0.000949798 | -0.00898024 | 0.00563926 | 0.8125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_p3 | target_clearance_adjusted_completion_delay_s | -0.365 | -0.75 | -0.065 | 0.125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_p3 | min_footprint_separation_m | 0.0753509 | 0.0179021 | 0.116519 | 0.125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_p3 | solver_failure_fraction | 0.00237541 | 0.000917106 | 0.00408521 | 0.125 | 1 | 5 |
| synthesis_predictor_by_offset_primary | B1_minus_B0__adaptive__offset_p3 | supervisor_active_fraction | 0.00526966 | 0.00119788 | 0.00994671 | 0.125 | 1 | 5 |
| synthesis_policy_pooled_primary | adaptive_minus_fixed_medium__B1__all_offsets | target_clearance_adjusted_completion_delay_s | -0.0633333 | -0.571667 | 0.415 | 0.875 | 1 | 5 |
| synthesis_policy_pooled_primary | adaptive_minus_fixed_medium__B1__all_offsets | min_footprint_separation_m | 0.0803174 | 0.0258897 | 0.126322 | 0.125 | 1 | 5 |
| synthesis_policy_pooled_primary | adaptive_minus_fixed_medium__B1__all_offsets | solver_failure_fraction | 0.00113119 | -0.000228601 | 0.00249098 | 0.25 | 1 | 5 |
| synthesis_policy_pooled_primary | adaptive_minus_fixed_medium__B1__all_offsets | supervisor_active_fraction | 0.00102922 | -0.00252525 | 0.0045837 | 0.625 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_m3 | target_clearance_adjusted_completion_delay_s | -0.02 | -0.13 | 0.105 | 0.75 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_m3 | min_footprint_separation_m | -0.0695822 | -0.214537 | 0.0517563 | 0.375 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_m3 | solver_failure_fraction | 0 | 0 | 0 | 1 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_m3 | supervisor_active_fraction | -0.000941796 | -0.00686382 | 0.00325567 | 0.875 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_0 | target_clearance_adjusted_completion_delay_s | -0.38 | -1.085 | 0.325 | 0.4375 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_0 | min_footprint_separation_m | 0.00319471 | -0.00486601 | 0.0122342 | 0.75 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_0 | solver_failure_fraction | 0.000162749 | -8.56123e-05 | 0.000411109 | 0.5 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_0 | supervisor_active_fraction | 0.00366168 | -0.00570315 | 0.0132575 | 0.4375 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_p3 | target_clearance_adjusted_completion_delay_s | 0.21 | -0.83 | 1.415 | 0.8125 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_p3 | min_footprint_separation_m | 0.30734 | 0.127127 | 0.493363 | 0.125 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_p3 | solver_failure_fraction | 0.00323083 | -0.000606256 | 0.00706791 | 0.25 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B1__offset_p3 | supervisor_active_fraction | 0.000367794 | -0.00913233 | 0.00986792 | 1 | 1 | 5 |
| synthesis_policy_pooled_primary | adaptive_minus_fixed_medium__B0__all_offsets | target_clearance_adjusted_completion_delay_s | -0.0966667 | -0.701667 | 0.348333 | 0.9375 | 1 | 5 |
| synthesis_policy_pooled_primary | adaptive_minus_fixed_medium__B0__all_offsets | min_footprint_separation_m | 0.0464643 | 0.00557088 | 0.0890406 | 0.125 | 1 | 5 |
| synthesis_policy_pooled_primary | adaptive_minus_fixed_medium__B0__all_offsets | solver_failure_fraction | 0.000285448 | -0.00117284 | 0.00179796 | 0.75 | 1 | 5 |
| synthesis_policy_pooled_primary | adaptive_minus_fixed_medium__B0__all_offsets | supervisor_active_fraction | 0.000765335 | -0.00285568 | 0.00583431 | 1 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_m3 | target_clearance_adjusted_completion_delay_s | -0.025 | -0.295 | 0.215 | 0.8125 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_m3 | min_footprint_separation_m | -0.0301402 | -0.0725121 | -0.00276534 | 0.125 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_m3 | solver_failure_fraction | 0 | 0 | 0 | 1 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_m3 | supervisor_active_fraction | -0.000892445 | -0.00472609 | 0.0030282 | 0.6875 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_0 | target_clearance_adjusted_completion_delay_s | -0.19 | -0.375 | -0.005 | 0.25 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_0 | min_footprint_separation_m | -0.0168017 | -0.0324087 | -0.00129524 | 0.1875 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_0 | solver_failure_fraction | -0.000886065 | -0.00188542 | 3.98491e-05 | 0.375 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_0 | supervisor_active_fraction | 0.00256562 | 0.000377823 | 0.00529417 | 0.125 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_p3 | target_clearance_adjusted_completion_delay_s | -0.075 | -1.69 | 1.065 | 1 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_p3 | min_footprint_separation_m | 0.186335 | 0.0620893 | 0.31058 | 0.125 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_p3 | solver_failure_fraction | 0.00174241 | -0.00220409 | 0.00568891 | 0.625 | 1 | 5 |
| synthesis_policy_by_offset_primary | adaptive_minus_fixed_medium__B0__offset_p3 | supervisor_active_fraction | 0.000622836 | -0.00875636 | 0.0146175 | 1 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B1__fixed_medium | target_clearance_adjusted_completion_delay_s | 0.295 | -0.36 | 0.97 | 0.5 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B1__fixed_medium | min_footprint_separation_m | 0.0947834 | 0.0405277 | 0.150314 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B1__fixed_medium | solver_failure_fraction | 0.00390327 | 0.0018008 | 0.0055511 | 0.125 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B1__fixed_medium | supervisor_active_fraction | -0.0367976 | -0.053585 | -0.017974 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B1__fixed_medium | target_clearance_adjusted_completion_delay_s | -0.515 | -0.905 | 0.065 | 0.1875 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B1__fixed_medium | min_footprint_separation_m | 0.42451 | 0.284285 | 0.593591 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B1__fixed_medium | solver_failure_fraction | 0.016638 | 0.0119834 | 0.0219195 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B1__fixed_medium | supervisor_active_fraction | -0.0339028 | -0.0421339 | -0.0256718 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B1__fixed_medium | target_clearance_adjusted_completion_delay_s | -0.22 | -0.99 | 0.55 | 0.6875 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B1__fixed_medium | min_footprint_separation_m | 0.519293 | 0.341508 | 0.701857 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B1__fixed_medium | solver_failure_fraction | 0.0205413 | 0.0153505 | 0.026865 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B1__fixed_medium | supervisor_active_fraction | -0.0707004 | -0.0859603 | -0.0542058 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B1__adaptive | target_clearance_adjusted_completion_delay_s | -0.065 | -0.255 | 0.18 | 0.6875 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B1__adaptive | min_footprint_separation_m | 0.16756 | 0.0137943 | 0.350305 | 0.1875 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B1__adaptive | solver_failure_fraction | 0.00406602 | 0.00189324 | 0.00559251 | 0.125 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B1__adaptive | supervisor_active_fraction | -0.0321941 | -0.0431183 | -0.0237175 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B1__adaptive | target_clearance_adjusted_completion_delay_s | 0.075 | -1.155 | 1.555 | 0.8125 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B1__adaptive | min_footprint_separation_m | 0.728655 | 0.411541 | 1.05718 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B1__adaptive | solver_failure_fraction | 0.0197061 | 0.0155238 | 0.0236111 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B1__adaptive | supervisor_active_fraction | -0.0371967 | -0.0524482 | -0.0219452 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B1__adaptive | target_clearance_adjusted_completion_delay_s | 0.01 | -1.055 | 1.48 | 0.9375 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B1__adaptive | min_footprint_separation_m | 0.896215 | 0.454452 | 1.33798 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B1__adaptive | solver_failure_fraction | 0.0237721 | 0.0180626 | 0.0289863 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B1__adaptive | supervisor_active_fraction | -0.0693908 | -0.0935973 | -0.046544 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B0__fixed_medium | target_clearance_adjusted_completion_delay_s | -0.755 | -1.58 | 0.005 | 0.1875 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B0__fixed_medium | min_footprint_separation_m | 0.0146949 | -0.135163 | 0.113297 | 0.9375 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B0__fixed_medium | solver_failure_fraction | 0.00458924 | 0.00224912 | 0.00648879 | 0.125 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B0__fixed_medium | supervisor_active_fraction | -0.0233629 | -0.0364617 | -0.00912131 | 0.125 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B0__fixed_medium | target_clearance_adjusted_completion_delay_s | 0.43 | -0.575 | 1.44 | 0.5625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B0__fixed_medium | min_footprint_separation_m | 0.429008 | 0.271591 | 0.595861 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B0__fixed_medium | solver_failure_fraction | 0.0150651 | 0.00984985 | 0.0212363 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B0__fixed_medium | supervisor_active_fraction | -0.0414734 | -0.0456317 | -0.0354043 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B0__fixed_medium | target_clearance_adjusted_completion_delay_s | -0.325 | -1.805 | 1.21 | 0.75 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B0__fixed_medium | min_footprint_separation_m | 0.443703 | 0.324369 | 0.54966 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B0__fixed_medium | solver_failure_fraction | 0.0196543 | 0.0139976 | 0.0267101 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B0__fixed_medium | supervisor_active_fraction | -0.0648363 | -0.0816217 | -0.048051 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B0__adaptive | target_clearance_adjusted_completion_delay_s | -0.92 | -1.595 | -0.23 | 0.125 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B0__adaptive | min_footprint_separation_m | 0.0280334 | -0.0885936 | 0.121635 | 0.75 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B0__adaptive | solver_failure_fraction | 0.00370318 | 0.00184797 | 0.00464762 | 0.125 | 1 | 5 |
| synthesis_offset_primary | offset_0_minus_m3__B0__adaptive | supervisor_active_fraction | -0.0199049 | -0.034604 | -0.00520576 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B0__adaptive | target_clearance_adjusted_completion_delay_s | 0.545 | -0.265 | 1.57 | 0.4375 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B0__adaptive | min_footprint_separation_m | 0.632144 | 0.391159 | 0.873156 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B0__adaptive | solver_failure_fraction | 0.0176935 | 0.0135549 | 0.0221197 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_0__B0__adaptive | supervisor_active_fraction | -0.0434162 | -0.0528393 | -0.0324181 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B0__adaptive | target_clearance_adjusted_completion_delay_s | -0.375 | -1.205 | 0.455 | 0.4375 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B0__adaptive | min_footprint_separation_m | 0.660178 | 0.431302 | 0.884469 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B0__adaptive | solver_failure_fraction | 0.0213967 | 0.0153961 | 0.0266232 | 0.0625 | 1 | 5 |
| synthesis_offset_primary | offset_p3_minus_m3__B0__adaptive | supervisor_active_fraction | -0.063321 | -0.0763956 | -0.0500524 | 0.0625 | 1 | 5 |

## Table 7: table07_hypothesis_evidence_verdicts.csv

| hypothesis_id | claim | evidence_ids | verdict | boundary |
| --- | --- | ---: | --- | ---: |
| H1 | Task adaptation improves in-distribution prediction relative to pretrained B0. | R_TEST_B1_MINUS_B0_ADE; R_TEST_B1_MINUS_B0_FDE; R_TEST_B1_MINUS_B0_MACRO_NLL | supported | same Town05 give-way distribution |
| H2 | Explicit interaction-sequence models use the added sequence input. | R_ABLATION_T1_SHUFFLE_MACRO_NLL; R_ABLATION_T2_ZERO_MACRO_NLL; R_ABLATION_T2_SHUFFLE_MACRO_NLL | supported mechanistically | input sensitivity is not causal understanding |
| H3 | Transformer variants outperform simple B1 adaptation. | R_VAL_B1_S11_MACRO_NLL; R_TEST_B1_MACRO_NLL | refuted | finite controlled dataset and tested architectures |
| H4 | Better offline prediction produces uniform closed-loop gains. | R_TEST_B1_MINUS_B0_ADE; R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_M3_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S; R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_0_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S | refuted | effects are policy/style/timing conditional |
| H5 | Adaptive risk universally dominates the fixed-risk frontier. | R_DAY10_B1_REACTIVE_ADAPTIVE_ADJUSTED_DELAY_S; R_DAY10_B1_REACTIVE_FIXED_AGGRESSIVE_ADJUSTED_DELAY_S; R_DAY10_B1_REACTIVE_ADAPTIVE_FOOTPRINT_MARGIN_M; R_DAY10_B1_REACTIVE_FIXED_AGGRESSIVE_FOOTPRINT_MARGIN_M; R_TIMING_ADAPTIVE_MINUS_FIXED_MEDIUM_B1_OFFSET_P3_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S; R_TIMING_ADAPTIVE_MINUS_FIXED_MEDIUM_B1_OFFSET_P3_MIN_FOOTPRINT_SEPARATION_M | refuted | adaptive remains a frontier point, not a universal replacement |
| H6 | Predictor effects are moderated by risk policy and arrival timing. | R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_M3_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S; R_TIMING_B1_MINUS_B0_FIXED_MEDIUM_OFFSET_0_TARGET_CLEARANCE_ADJUSTED_COMPLETION_DELAY_S; R_TIMING_B1_MINUS_B0_ADAPTIVE_OFFSET_P3_MIN_FOOTPRINT_SEPARATION_M | descriptively supported | five init groups limit confirmatory power |
| H7 | Collision-containing training rollouts determine the selected architecture. | R_SENS_SELECTED_ARCHITECTURE_STABLE | refuted | whole-rollout conservative filter |
| H8 | The frozen deployment chain satisfies the declared reliability gates. | R_DAY10_RELIABILITY_FOOTPRINT_COLLISIONS; R_DAY10_RELIABILITY_YIELD_ORDER_FAILURES | supported for observed runs | zero observed events is not zero population risk |

## Table 8: table08_threats_to_validity.csv

| threat_id | threat | mitigation | remaining_boundary |
| --- | --- | --- | --- |
| T1 | Only five independent validation/test init groups | rollout-macro metrics, init-cluster bootstrap/sign-flip inference | minimum two-sided exact p=0.0625 |
| T2 | Single CARLA map and controlled give-way geometry | factorial target style, risk and ±3 m timing shifts | no cross-map or real-world generalisation claim |
| T3 | Day6 callback frames lack per-rollout sample-clock anchor | whole-rollout conservative exclusion and 15-run sensitivity | exact affected-window fraction remains unidentified |
| T4 | Supervisor and solver can mask predictor/controller effects | A3 authority regime plus supervisor/solver mechanism metrics | closed-loop effect remains a coupled-system property |
| T5 | Zero observed closed-loop collisions | report event count and footprint margins separately | does not estimate zero collision probability |
| T6 | Global calibration fails in response-active tail | report aggregate and response-active calibration separately | tail calibration requires more interaction data |
| T7 | Nominal and shifted timing batches ran separately | contract/hash compatibility gate and shared five init groups | residual batch effect cannot be fully excluded |
| T8 | Post-hoc filtered sensitivity reuses validation | original experiment remains primary; no filtered test evaluation | sensitivity supports robustness, not new model selection |
