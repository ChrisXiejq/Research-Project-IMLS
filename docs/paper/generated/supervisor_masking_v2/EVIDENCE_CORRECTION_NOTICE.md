# Evidence correction notice — 2026-08-25

The generated H1 release in this directory is preliminary diagnostic material.

The historical SF4 `monitor_only` arm disabled a bundled seven-channel authority layer and completed 0/40 rollouts. It is not a clean “paper-equivalent SMPC with only the give-way rule removed” baseline. Therefore the existing H1 gate, verdict table, captions and H1 figure must not be used to claim that supervisor-off SMPC cannot reach the destination or that 40/40 versus 0/40 identifies the causal effect of the give-way rule.

Allowed use before replacement: the full authority bundle was physically and command-level consequential in the tested implementation. Required replacement: a prospective clean off baseline that preserves SMPC, route tracking and completion while toggling only give-way rule application.

See `docs/HANDOFF_2026-08-25_SUPERVISOR_MASKING.md`.
