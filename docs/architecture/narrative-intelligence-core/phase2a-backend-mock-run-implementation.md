# Phase 2A Backend Mock Run Implementation (Agent M)

Change: `CHG-20260723-032`
Branch: `feature/narrative-phase2a-run-backend`
Baseline: Phase 2A-P HEAD (`1e8112f…`)

## Scope delivered

| Component | Path |
|-----------|------|
| Lab Authorization | `services/mock_lab_authorization_service.py` |
| Metadata helpers | `services/mock_run_metadata.py` |
| Run State Service | `services/mock_run_state_service.py` |
| Mock Run Service | `services/mock_whole_book_run_service.py` |
| Mock Executor | `services/mock_whole_book_run_executor.py` |
| Task Registry | `services/in_process_mock_run_task_registry.py` |
| Lab API Router | `routers/whole_book_mock_lab_runs.py` |
| Tests | `tests/test_narrative_phase2a_mock_run_backend.py` |

Detail docs:

- [phase2a-mock-run-service.md](./phase2a-mock-run-service.md)
- [phase2a-mock-executor-implementation.md](./phase2a-mock-executor-implementation.md)
- [phase2a-task-registry-implementation.md](./phase2a-task-registry-implementation.md)
- [phase2a-lab-api-implementation.md](./phase2a-lab-api-implementation.md)
- [phase2a-backend-verification.md](./phase2a-backend-verification.md)

## Explicit non-goals (honored)

- No real whole-book analysis / model / prompts
- No Recovery scan core (Agent O)
- No formal Quota persistence (Agent O)
- No frontend changes
- No `main.py` registration (Integration)
- No migrations / new tables / VERSION bump
- Production gates unchanged: `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`, `PRODUCTION_DEFAULT_ENGINE_ID=None`

## Reuse

Phase 1A AnalysisRun/Stages; Phase 1B Asset/Relation services; Phase 1C Mock Engine + Stage Orchestrator + adapters; Phase 1D Result API (read-only); Phase 2A-P `run_shell_contract`.
