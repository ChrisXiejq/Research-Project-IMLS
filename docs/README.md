# Documentation Index

This folder is organised by document purpose. Use this file as the entry point.

## Current Status

- `paper/论文实验与写作统一指导.md`
  当前唯一 canonical 指导文档。包含老师反馈、最终论点、baseline 设计、实验路线、文献借鉴、paper-safe claims 和 50-init decision gate。后续实验和论文写作优先参考此文件。

## Paper Writing

- `paper/论文实验与写作统一指导.md`
  同时作为论文大纲、Related Work 组织方式和 Results / Discussion 写作边界。

## Results and Figures

- `paper/generate_finetuned_predictor_validation_figures.py`  
  Generates post-hoc SVG figures for fine-tuned predictor validation runs.
- `paper/generate_formal_supervisor_ablation_report.py`
  Generates the formal supervisor ablation report and CSV summaries for full vs reduced-intervention supervisor analysis.
- `paper/generate_fixed_risk_frontier_report.py`
  Generates the fixed-risk frontier report and CSV summaries. Use this with the frozen reduced early-stop baseline to compare fixed aggressive/medium/conservative against `adaptive_floor_weak`.
- `paper/diagnose_supervisor_feedback_step1.py`
  Post-hoc diagnostic script for supervisor feedback issues: conservative stopping, supervisor masking, and infeasibility phases.
- `paper/diagnose_multipath_sanity_step3.py`
  Fine-tuned predictor sanity diagnostics.

## Architecture and Experiment History

- `architecture/UK_Give_Way_Intersection_Scenario.md`  
  Scenario design and CARLA give-way intersection notes.
- `architecture/流程图与代码映射.md`  
  Mapping between architecture diagrams and code.
- `architecture/Give_Way_SMPC_Experiment_Changelog.md`  
  Detailed historical changelog. Use for traceability, not as the current status source.
- `architecture/Server_CARLA_Environment_Runbook.md`
  Server startup commands and mandatory CasADi/Gurobi conic-solver preflight for CARLA/SMPC experiments.
- `architecture/Experiment Flow.png`, `architecture/SMPC.png`  
  Architecture diagrams.

## Literature

- `literature/相关文献解读_SMPC_多模态预测_自动驾驶.md`  
  Main literature reading notes.
- `literature/*.pdf`  
  Source papers.

## Presentation

- `presentation/`  
  Presentation slides, marking rubric, lecture note, and visual assets.

## Cleanup Policy

Obsolete intermediate plans, old original-paper-style generated tables/figures, outdated scripts, older English guidance, the separate action guide, and the separate phase-aware literature note have been merged into `paper/论文实验与写作统一指导.md` and removed from this folder. Historical experiment details remain in `architecture/Give_Way_SMPC_Experiment_Changelog.md`; current decisions should follow the unified Chinese guidance document in `paper/`.
