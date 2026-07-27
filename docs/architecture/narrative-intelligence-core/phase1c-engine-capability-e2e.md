# Phase 1C Engine ↔ Capability E2E

## Chain (test-level)

```
CapabilityService.evaluate_*
  → require_whole_book_run_permission
  → CapabilityDecision (backend-owned)
  → WholeBookAnalysisRequest
  → Engine.validate_request
  → Engine.build_stage_plan
```

Helper: `apps/api/app/narrative_core/services/whole_book_request_chain.py`

## Rules

1. Engine never parses License itself — only consumes evaluated `CapabilityDecision`.
2. Frontend-supplied `allowed` is ignored (`client_allowed` discarded).
3. `capability_context` is always rebuilt by backend / test override.
4. Capability denied → no Engine call, no Stage init, no Quota reserve.
5. Production defaults: endpoint disabled + shipped=false + no production Engine → never start.
6. Happy-path tests must inject allowed Decision **and** Mock Engine explicitly.

## Quota ≠ Cloud Budget

Minimal Mock path:

```
Capability → Quota evaluate/reserve → BudgetGuard → Stage execute → commit/release
```

- Guard/budget deny → no Asset / Artifact writes
- Stage failure → Quota release (idempotent)
- Stage success → Quota commit (idempotent)
- `InMemoryQuotaService.backend = memory_non_production` (not persisted)
