# Internal generated manuscript

This directory is retained because the evidence builders and regression audits
under `core/scripts/models/` use its stable paths.

It is **not** the dissertation submission workspace. The authoritative paper is:

```text
../../../../Jiaqi Xie Dissertation/main.tex
```

Do not manually synchronise result values into this tree. Evidence builders may
regenerate its sections. Human-facing writing guidance is in
`../../../../Jiaqi Xie Dissertation/WRITING_GUIDE_ZH.md`, and the repository
evidence map is `../../paper/THESIS_EVIDENCE_GUIDE.md`.

The internal manuscript can still be built for audit compatibility with:

```bash
make -C docs/dissertation/latex pdf
```
