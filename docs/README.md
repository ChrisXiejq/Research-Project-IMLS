# Documentation Index

This folder is organised by document purpose. Use this file as the entry point.

## Current Status

- `paper/dissertation_guidance_after_supervisor_feedback.md`
  Canonical dissertation guidance after the supervisor feedback. This is the main source for the final research goal, hypotheses, experiment plan, paper-safe claims, and 50-init decision gate.
- `paper/next_experiment_action_guide_after_supervisor_feedback.md`
  Operational action guide for the next experimental stage. Use this for concrete experiment sequencing, commands, and current evidence tracking.

## Paper Writing

- `paper/phase_aware_adaptive_risk_相关文献整理.md`  
  Related-work notes focused on phase-aware adaptive-risk SMPC.

## Results and Figures

- `paper/generate_finetuned_predictor_validation_figures.py`  
  Generates post-hoc SVG figures for fine-tuned predictor validation runs.
- `paper/generate_formal_supervisor_ablation_report.py`
  Generates the formal supervisor ablation report and CSV summaries for full vs reduced-intervention supervisor analysis.
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

Obsolete intermediate plans, old original-paper-style generated tables/figures, and outdated scripts have been merged into `paper/dissertation_guidance_after_supervisor_feedback.md` and removed from this folder. Historical experiment details remain in `architecture/Give_Way_SMPC_Experiment_Changelog.md`; current decisions should follow the two guidance documents in `paper/`.
