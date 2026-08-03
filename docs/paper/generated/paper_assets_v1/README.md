# Paper evidence package v1

This directory is the canonical source for thesis numbers, tables and figures.

## Contents

- `paper_results_manifest.json`: 210 stable result IDs with source SHA-256, locator, unit, aggregation unit and evidence role;
- `table01`–`table08`: canonical thesis tables;
- `figures/figure01`–`figure08`: editable SVG and high-resolution PNG figures;
- `figures/figure_captions.md`: canonical captions and interpretation boundaries;
- `paper_claim_evidence_matrix.csv`: hypothesis → result IDs → figure linkage;
- `paper_key_results.csv`: compact list of result IDs used by H1–H8;
- `paper_asset_inventory.csv`: file sizes and SHA-256 checksums;
- `PAPER_EVIDENCE_PACKAGE_COMPLETE.json`: final integrity gate.

## Rebuild and audit

From the repository root:

```bash
python3 core/scripts/models/build_paper_results_manifest.py
python3 core/scripts/models/build_paper_figures.py

NODE_PATH=/Users/bytedance/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules \
  /Users/bytedance/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  core/scripts/models/render_paper_figures_png.cjs \
  docs/paper/generated/paper_assets_v1/figures

python3 core/scripts/models/audit_paper_evidence_package.py
```

SVG is the canonical editable format. PNG is a high-resolution fallback for Word or presentation software. The Node/Sharp step is only needed to rebuild PNG files; all numerical tables and SVG figures use the Python standard library.

Do not edit generated numbers or figure data manually. Update a source artifact or generator and rebuild the package.
