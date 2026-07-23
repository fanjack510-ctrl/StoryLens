# Phase 1D Preflight → Result E2E

Fixture-only product chain (no models, no production Run create):

1. Create test Book + COMPLETED Snapshot  
2. Read-only Preflight (`POST .../preflight`)  
3. Select Native + partial Modules → dependency auto-fill notes  
4. Assert `effective_run_creation_enabled=false`  
5. Create **fixture** Book Run + RunStages + mock Assets/Relations/Evidence  
6. Result Index → module statuses (partial/completed/blocked)  
7. Module Envelope (canonical default; candidate explicit)  
8. Evidence index (hash only) + Structure Map projection  
9. Assert no Pattern ORM tables; SQLite integrity OK  

Implemented in `apps/api/tests/test_narrative_phase1d_integration.py` and  
`apps/desktop/src/features/wholeBook/phase1dIntegration.test.tsx`.

## Run creation semantics

| Flag | Source |
|------|--------|
| `backend_run_creation_enabled` | Transport DTO `run_creation_enabled` (preserved) |
| `client_run_creation_enabled` | `RUN_CREATE_ENABLED_IN_CLIENT=false` |
| `effective_run_creation_enabled` | backend AND client |
| `run_creation_enabled` | alias of effective (legacy) |

UI disable uses **effective**. Blocking reasons remain backend reasons.
