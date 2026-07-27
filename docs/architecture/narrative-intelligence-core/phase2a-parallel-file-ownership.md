# Phase 2A Parallel File Ownership

Baseline: `VERSION=1.0.5` @ `b755f50506a759fdc2cf2841aa6bfe789d95099a` (`integration/narrative-phase1d`).

Machine-readable: [phase2a-parallel-file-ownership.json](./phase2a-parallel-file-ownership.json).

## Phase 2A-P (CHG-031)

Owns contract freeze only:

- `apps/api/app/narrative_core/run_shell_contract/`
- `apps/desktop/src/features/wholeBook/runShell/contracts/`
- `apps/api/tests/test_narrative_phase2ap_contract.py`
- all `phase2a-*.md` contract docs listed in the JSON
- CHG-031…035 registration

## Agent M — Backend Mock Run (CHG-032)

Branch: `feature/narrative-phase2a-run-backend`  
Worktree: `D:\Dstorylens-wt-narrative-run-backend`

- Mock Run Service / Executor / Task Registry / Lab API / Stage Orchestrator wiring
- **Must not** modify frontend
- **Must not** own recovery scan core (Agent O)

## Agent N — Frontend Mock Run Lab (CHG-033)

Branch: `feature/narrative-phase2a-run-frontend`  
Worktree: `D:\Dstorylens-wt-narrative-run-frontend`

- Lab UI, client, polling, progress, controls, partial results
- **Must not** modify backend run implementation

## Agent O — Recovery & Reliability (CHG-034)

Branch: `feature/narrative-phase2a-recovery`  
Worktree: `D:\Dstorylens-wt-narrative-run-recovery`

- Recovery, idempotency, concurrency, audit, quota/budget, fault injection
- **Must not** modify formal frontend layout

## Integration (CHG-035)

Branch: `integration/narrative-phase2a`  
Worktree: `D:\Dstorylens-wt-narrative-phase2a-integration`

- Merge M/N/O, Lab route registration in `main.py`, Product E2E, startup recovery hooks, Change Registry, README, integration tests

## Shared risk files

| Path | Risk | Owner |
|------|------|-------|
| `apps/api/app/main.py` | Lab router vs production isolation | Integration |
| `apps/api/app/db/models.py` | No new columns; metadata JSON only | Read-only |
| `whole_book_stage_orchestrator.py` | Mock wiring must not open production runs | M + Integration review |
| `wholeBook/runUx/` | Lab must stay out of formal nav | N isolated |
| `contracts/api_dto.py` | `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` stays true | Read-only |

## Forbidden for all Phase 2A agents

Real engine/model/prompts; flip ship/run gates; migrations/new tables; Celery/Redis/queues/WebSocket; VERSION/tag/baseline; push/build/publish; stash restore.
