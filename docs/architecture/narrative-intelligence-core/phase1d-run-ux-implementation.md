# Phase 1D Agent J — Run UX Implementation

Change: `CHG-20260723-027`  
Branch: `feature/narrative-phase1d-run-ux`  
Worktree: `D:\Dstorylens-wt-narrative-run-ux`  
Baseline: `f79f199ea9dc53b8e92ae661baef3dc62007e905`

## Scope delivered

Isolated frontend prototype under `apps/desktop/src/features/wholeBook/runUx/`:

| Component | Role |
|-----------|------|
| `WholeBookPreflightView` | Preflight page shell + confirm gate |
| `WholeBookModeSelector` | Native / Enhanced modes |
| `WholeBookModuleSelector` | 11 frozen modules + dependency notes |
| `WholeBookStagePlanPreview` | Informational stage plan |
| `WholeBookRunProgressView` | Run view-state progress |
| `WholeBookStageProgressList` | Per-stage progress |
| `WholeBookRunActionBar` | pause / resume / retry / cancel (Mock) |
| `WholeBookPartialResultNotice` | Partial / retained results |
| `WholeBookBlockingReasonsPanel` | Blocking + `run_creation_enabled` |
| `WholeBookRunUxLabPage` | Isolated lab (not product nav) |

## Hard gates kept

- `run_creation_enabled=false` (client forces false; ignores payload true)
- No `POST /whole-book-runs`
- No model calls / AnalysisRun / Snapshot creation
- No force-start control
- `allowed_actions` consumed only from backend/fixture
- Product main menu **not** modified
- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` / `PRO_CAPABILITIES_SHIPPED` untouched
- `VERSION` / `release/unreleased.json` / architecture README untouched

## Client adapter

`wholeBookPreflightClient` → `POST /api/v1/books/{book_id}/whole-book-runs/preflight`

- Maps Phase 1C response → `WholeBookPreflightPageModel`
- Pass-through capability / quota / engine flags (no local recompute)
- Fail-closed on offline/network
- Does not create second Preflight DTO schema

## Related docs

- [phase1d-preflight-ux.md](./phase1d-preflight-ux.md)
- [phase1d-module-selection-ux.md](./phase1d-module-selection-ux.md)
- [phase1d-run-progress-ux.md](./phase1d-run-progress-ux.md)
- [phase1d-run-ux-verification.md](./phase1d-run-ux-verification.md)
