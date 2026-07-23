# Phase 2A Run Shell Overview

Freeze target: Mock Whole-Book Run Shell lifecycle (CHG-20260723-031).

## Product goal

Complete body Snapshot → Preflight → Mode/Modules → Create Mock Book Scope Run → AnalysisRunStage init → Mock Engine staged execution → Checkpoint → Stage Artifact → Candidate Asset/Relation → Partial Projection → Run Progress → Pause/Resume/Retry/Cancel → Interrupt recovery → Mock result page.

## Explicitly NOT

- Real novel analysis / model calls / real prompts
- Formal Pro ship / commercial quota
- Formal background job platform (Celery/Redis/queues)

## Production gates (unchanged)

- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
- `PRO_CAPABILITIES_SHIPPED=false`
- `PRODUCTION_DEFAULT_ENGINE_ID=None`

## New Lab gate

- `WHOLE_BOOK_MOCK_LAB_ENABLED` default `false`
- Independent of production ship flags
- See [phase2a-mock-lab-security.md](./phase2a-mock-lab-security.md)

## Contract packages

- Backend: `apps/api/app/narrative_core/run_shell_contract/`
- Frontend: `apps/desktop/src/features/wholeBook/runShell/contracts/`

## Parallel agents

| Agent | Change | Branch | Worktree |
|-------|--------|--------|----------|
| Phase 2A-P | CHG-031 | feature/narrative-phase2a-run-shell-contract | D:\\Dstorylens-wt-narrative-phase2a-contract |
| M | CHG-032 | feature/narrative-phase2a-run-backend | D:\\Dstorylens-wt-narrative-run-backend |
| N | CHG-033 | feature/narrative-phase2a-run-frontend | D:\\Dstorylens-wt-narrative-run-frontend |
| O | CHG-034 | feature/narrative-phase2a-recovery | D:\\Dstorylens-wt-narrative-run-recovery |
| Integration | CHG-035 | integration/narrative-phase2a | D:\\Dstorylens-wt-narrative-phase2a-integration |

All M/N/O/Integration branches fork from Phase 2A-P final HEAD.
