# Phase 2A Integration Report

**Change:** CHG-20260723-035
**Branch:** `integration/narrative-phase2a`
**Worktree:** `D:\Dstorylens-wt-narrative-phase2a-integration`
**Base:** `1e8112f0de5a0c37085023ca75747555514f3b05` (Phase 2A-P CHG-031 verified)
**VERSION:** 1.0.5 (unchanged)

## Scope

Cherry-pick Agent M → Agent O → Agent N, wire composition root in `main.py`, register Lab router conditionally, run product E2E tests, document boundaries.
**Not in scope:** real Engine/model/Prompt, formal Run create, migrations, VERSION bump, push/build/publish.

## Merge order (cherry-pick)

1. **Agent M** (`feature/narrative-phase2a-run-backend`) — backend mock run service, executor, task registry, Lab API router
2. **Agent O** (`feature/narrative-phase2a-recovery`) — idempotency, concurrency, recovery, audit, quota/budget, fault injection
3. **Agent N** (`feature/narrative-phase2a-run-frontend`) — Mock Lab UI/client/polling/controls/partial results

Cherry-picks applied on integration branch; agent worktrees untouched.

## Integration-only deliverables

| Area | Integration ownership |
|------|----------------------|
| Composition root | `mock_whole_book_run_runtime.py` — wires M + O services |
| `main.py` | `mount_mock_lab_if_enabled`, lifespan `MockRunStartupRecoveryAdapter.reconcile()` |
| E2E | `test_narrative_phase2a_integration.py` |
| Docs | This report + companion integration docs (CHG-035) |

## Corrections at merge boundary

- Lab router registration deferred from Agent M → Integration (`main.py`)
- Startup recovery adapter wired in lifespan; reconcile only, no silent resume
- Metadata envelope nested under `mock_whole_book_run_metadata` in `validated_output`
- Frontend fixtures reused from `runShell/__tests__/fixtures.ts` (no duplicate fixture set)

## Production isolation (unchanged)

- `WHOLE_BOOK_MOCK_LAB_ENABLED=false` (default)
- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
- `PRODUCTION_DEFAULT_ENGINE_ID=None`
- `PRO_CAPABILITIES_SHIPPED=false`
- Lab router absent when `environment=production` or Lab flag false
- No migrations / Pattern tables / VERSION bump

See also: [phase2a-production-isolation-verification.md](./phase2a-production-isolation-verification.md), [phase2a-known-limitations.md](./phase2a-known-limitations.md).
