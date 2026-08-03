# Generated evidence

本目录只保存机器生成或从服务器拉取的可复现证据，不保存人工写作草稿。

## Thesis-ready package

```text
paper_assets_v1/
```

这是论文数字、8 张表、8 张 SVG/PNG、captions、claim matrix 和 checksums 的唯一入口。

## Final cross-stage audit

```text
final_audit/FINAL_THESIS_EVIDENCE_AUDIT.json
```

该审计交叉检查 Day6–Day14 的关键 completion/count/split/selection/integrity invariants。

## Stage evidence

- `day2/`：legacy dataset/input problems；
- `day3/`：GMM evaluator、raster contract 与 calibration；
- `day4/`–`day5/`：V2 pipeline 和 collection freeze；
- `day6/`：200-rollout collection evidence；
- `day7/`：merge/split/normalization/model implementation gates；
- `day8/`：15-run validation、frozen selection 与 one-shot test；
- `day9/`：deployment smoke，仅作 implementation gate；
- `day10/`：nominal closed-loop matrix、B0 offline bridge、context ablation；
- `day11/`：timing-shift matrix；
- `day12/`：three-offset synthesis、collision audit 和 backup verification；
- `day13/`：collision-filtered validation sensitivity。

大型 tar snapshots、partial Day8 reports 和旧 preliminary figures/tables 已从活跃目录移除；它们可由 Git 历史或 Day12 offsite backup 恢复。

解释规则以顶层四份 canonical documents 为准，禁止根据单个 CSV 扩大结论。
