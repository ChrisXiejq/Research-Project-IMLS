# Documentation Index

This folder is organised by document purpose. Use this file as the entry point.

## Current Status

- `paper/current_project_status.md`  
  Canonical status and milestone summary. This is the main source for current best results, fine-tuned predictor validation, phase-aware risk evidence, graphical results, and paper-safe claims.

## Paper Writing

- `paper/phase_aware_adaptive_risk_论文初版大纲.md`  
  Dissertation outline and chapter-level writing plan.
- `paper/phase_aware_adaptive_risk_相关文献整理.md`  
  Related-work notes focused on phase-aware adaptive-risk SMPC.
- `paper/supervisor_progress_update_phase_aware_adaptive_risk.md`  
  Short supervisor update note.
- `paper/supervisor_progress_update_phase_aware_adaptive_risk.docx`  
  Editable supervisor update attachment.

## Results and Figures

- `paper/figures/`  
  Frozen control-side paper figures.
- `paper/generate_core_figures.py`  
  Generates frozen control-side SVG figures.
- `paper/generate_finetuned_predictor_validation_figures.py`  
  Generates post-hoc SVG figures for fine-tuned predictor validation runs.
- `paper/generate_original_paper_style_results.py`  
  Generates result tables and figures following the reference paper's Table-I style.
- `paper/generate_original_paper_style_timeseries.py`  
  Generates original-paper-style multi-panel closed-loop time-series SVG figures from `smpc_debug_steps.jsonl`.
- `paper/original_paper_style_results/`  
  Original-paper-style result package, including CSV tables, aggregate SVG figures, multi-panel time-series SVG figures, and the comparison analysis against the reference paper.

## Architecture and Experiment History

- `architecture/UK_Give_Way_Intersection_Scenario.md`  
  Scenario design and CARLA give-way intersection notes.
- `architecture/流程图与代码映射.md`  
  Mapping between architecture diagrams and code.
- `architecture/Give_Way_SMPC_Experiment_Changelog.md`  
  Detailed historical changelog. Use for traceability, not as the current status source.
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

Obsolete intermediate plans, old result tables, 10-init-only model validation notes, and temporary contribution-strengthening notes have been merged into `paper/current_project_status.md` and removed from this folder.
