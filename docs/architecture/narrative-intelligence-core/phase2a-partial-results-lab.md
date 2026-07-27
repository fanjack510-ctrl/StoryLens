# Phase 2A Partial Results Lab

## Module

`apps/desktop/src/features/wholeBook/runShell/lab/MockPartialResultsPanel.tsx`

## Behavior

- Shown when ≥1 module is available / completed / partial.
- Explicit markers: `partial`, `completed`, `candidate`, `mock / non-production`.
- `stale` rendered distinctly from `failed`.
- Evidence Drawer opened on demand (read-only).
- Structure Map uses read-only projection (fixture adapter if no live projection).
- Module fetch uses `view=candidate` — no auto-canonical.
- Result API does not trigger runs.
- Failed modules do not hide completed siblings.
- `cancelled` / `interrupted` run statuses remain readable for candidates.

This stage does **not** ship a formal product result page.
