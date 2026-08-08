# Paper evidence and writing guide

The experiment phase is complete. Corrected R3 finished all 80 prespecified
rollouts, A2 produced the closed-loop synthesis, and M1 value-audited the four
headline hypotheses. Large-scale CARLA collection is closed for this
dissertation; R4 is frozen as `not_run`.

## Read in this order

1. [`01_研究问题与实验方法.md`](01_研究问题与实验方法.md) — final thesis,
   hypotheses, estimands and design;
2. [`02_最终结果与审计结论.md`](02_最终结果与审计结论.md) — final numerical
   verdicts and claim boundaries;
3. [`03_论文写作路线与章节大纲.md`](03_论文写作路线与章节大纲.md) — chapter
   structure and writing order;
4. [`04_复现与证据资产索引.md`](04_复现与证据资产索引.md) — canonical
   artifacts and reproduction commands;
5. [`../dissertation/FINAL_TO_SUBMISSION_PLAN.md`](../dissertation/FINAL_TO_SUBMISSION_PLAN.md)
   — the sole active route to submission.

## Canonical evidence

- `generated/distinction_v1/10_four_hypothesis_evidence/`: primary
  claim-to-value entry point;
- `generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis/`:
  corrected R3 tables, figures and synthesis;
- other `generated/distinction_v1/` stages: provenance, controls, audits and
  prospective contracts.

`generated/paper_assets_v1/` and Day10--13 artifacts are retained for
provenance and secondary diagnostics. They are not the primary corrected
closed-loop evidence and must never be pooled with R3.

Generated evidence is immutable. Change the generating script and rerun its
audit instead of editing a table, figure, JSON or result value by hand.
