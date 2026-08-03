# TMLR-format dissertation LaTeX framework

This directory is the canonical dissertation writing workspace. It uses the
official TMLR style and the project's frozen Day14 evidence package.

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
in TMLR layout. Replace the placeholder name, candidate number, programme,
email and supervisor before submission.

For an actual double-blind TMLR submission, change the line to
`\usepackage{tmlr}`. The style will hide the author block automatically. For a
camera-ready TMLR article, use `\usepackage[accepted]{tmlr}` and complete the
month, year and OpenReview URL. Do not edit `tmlr.sty`, `tmlr.bst` or
`fancyhdr.sty`.

## Directory map

- `main.tex`: document order, metadata and TMLR mode.
- `macros.tex`: project notation and visible drafting markers.
- `sections/`: complete section-level writing skeleton.
- `appendices/`: reproducibility, supplementary results and audit material.
- `references.bib`: verified starter references plus a literature-review TODO.
- `RUBRIC_TO_STRUCTURE.md`: marking-rubric compliance map.
- `WRITING_CHECKLIST.md`: recommended drafting and finalisation order.
- `vendor/`: unmodified official TMLR style assets and their provenance.

Figures are read directly from
`../../paper/generated/paper_assets_v1/figures/`; no duplicate figure copies
are maintained here. Numerical claims must be copied from the canonical
tables/evidence package, not retyped from memory.

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
4. Distinguish primary experiments from post-selection diagnostics and Day13
   sensitivity analysis.
5. Keep appendices after the references, as required by the TMLR format.
6. Delete every `\TODO{...}` before final submission; comments beginning with
   `% EVIDENCE:` are provenance notes and may remain in source.
