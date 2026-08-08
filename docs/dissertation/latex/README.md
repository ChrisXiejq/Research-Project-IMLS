# TMLR-format dissertation LaTeX framework

This directory is the canonical dissertation writing workspace. It uses the
official TMLR style and the project's frozen R3/A2/M1 evidence package.

Companion reading material is available one directory above:
[`论文骨架中文版.md`](../论文骨架中文版.md) and
[`论文带读版_零基础.md`](../论文带读版_零基础.md). These help with understanding
and oral explanation; they do not replace the English submission source.

## Build

From this directory:

```bash
make pdf
```

The output is `build/main.pdf`. The Makefile prefers `latexmk` and falls back
to `tectonic` when available.

## Identity and TMLR modes

`main.tex` currently uses:

```tex
\usepackage[preprint]{tmlr}
```

This is the appropriate default for an identifiable UCL dissertation written
in TMLR layout. The W1 review copy intentionally contains neutral candidate
metadata because the repository does not contain the student's verified UCL
submission details. Insert those details only during the later submission
metadata pass; do not guess them in the scientific manuscript.

For an actual double-blind TMLR submission, change the line to
`\usepackage{tmlr}`. The style will hide the author block automatically. For a
camera-ready TMLR article, use `\usepackage[accepted]{tmlr}` and complete the
month, year and OpenReview URL required by the official template. Do not edit
`tmlr.sty`, `tmlr.bst` or
`fancyhdr.sty`.

## Directory map

- `main.tex`: document order, metadata and TMLR mode.
- `macros.tex`: stable project notation.
- `sections/`: complete W1 manuscript sections.
- `appendices/`: reproducibility, supplementary results and audit material.
- `references.bib`: checked primary and official references used in W1.
- `RUBRIC_TO_STRUCTURE.md`: marking-rubric compliance map.
- `WRITING_CHECKLIST.md`: recommended drafting and finalisation order.
- `vendor/`: unmodified official TMLR style assets and their provenance.

Corrected closed-loop assets are read from
`../../paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis/`;
legacy offline/diagnostic figures remain in `paper_assets_v1/`. Headline
numbers must resolve through the M1 evidence package, not be retyped from
memory.

## Official TMLR constraints reflected here

Reference pages: [Author Guidelines](https://jmlr.org/tmlr/author-guide.html),
[Submission Instructions](https://jmlr.org/tmlr/submissions.html), and the
[official style repository](https://github.com/JmlrOrg/tmlr-style-file).

- The official style/template is mandatory and its font, margins and layout
  must not be modified.
- TMLR itself permits content-justified length; UCL module word/page rules still
  take precedence for this dissertation and must be checked separately.
- Appendices follow the references. Material placed there is supplementary to,
  not a substitute for, a self-contained main argument.
- A real TMLR submission is double blind and its PDF and supplement must be
  anonymised. Supplementary files may be PDF or ZIP and total at most 100 MB.
- A broader-impact statement is included because autonomous-driving claims can
  create safety risk if overstated.
- TMLR currently requires first-page disclosure of LLM writing assistance.
  For the UCL dissertation, follow the programme's own academic-integrity and
  AI-use disclosure rules even if they differ.

## Drafting rules

1. Keep the current title unless the central claim changes. B1 is a
   task-adapted predictor, not an interaction Transformer.
2. Treat closed-loop B1 versus B0 as a **frozen predictor-stack** comparison
   (model plus frozen calibration), not a pure weight-level causal effect.
3. Do not claim conventional `p < 0.05` significance: there are five
   independent init clusters and the minimum two-sided exact p-value is
   0.0625.
4. Keep exactly four headline hypotheses: task adaptation, Transformer added
   value, offline-to-closed-loop transfer, and adaptive-risk dominance.
   Sequence/calibration/deployment/callback analyses are supporting checks.
5. Treat corrected R3 as the sole primary closed-loop effect matrix. Keep
   Day10--13 timing/callback material explicitly secondary and never pool it
   with R3.
6. Keep appendices after the references, as required by the TMLR format.
7. Keep source free of visible drafting markers; comments beginning with
   `% EVIDENCE:` are provenance notes and may remain in source.

## Generated W1 evidence

Run the deterministic evidence exporter before building the manuscript:

```bash
python3 ../../../core/scripts/models/build_w1_latex_evidence.py
```

The generated tables and manuscript figures live under
`../../paper/generated/distinction_v1/11_w1_manuscript/`. Their completion
markers bind every input and output by SHA-256. The renderer converts the two
canonical A2 SVGs and creates a declared corrected-R3 rendering of the preserved
historical workflow figure. It requires Node.js with `sharp`; the checked PNGs
are committed so a normal LaTeX build does not depend on Node.

After compiling and manually inspecting every colour page plus the key figures
in greyscale, record the W1 gate with:

```bash
.venv-precarla/bin/python \
  core/scripts/models/audit_w1_manuscript.py \
  --visual-review-complete
```

The explicit flag prevents a later rebuild from silently claiming a visual
inspection that nobody performed.
