# Phase 2A Production Isolation Verification

**Change:** CHG-20260723-035
**Test:** `test_production_gates_unchanged`, security/OpenAPI matrix in `test_narrative_phase2a_integration.py`

## Gates still closed (evidence)

| Gate | Expected | Verified by |
|------|----------|-------------|
| `WHOLE_BOOK_MOCK_LAB_ENABLED` | default `false` | contract constant + integration assert |
| Lab router in production | not mounted | `test_security_production_env_no_lab_router` |
| Lab router when flag false | not mounted | `test_security_lab_disabled_no_write` |
| Formal Run create | disabled | `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`; create path absent from OpenAPI |
| Production default engine | `None` | `PRODUCTION_DEFAULT_ENGINE_ID is None` |
| Pro capabilities shipped | `false` | unchanged from Phase 1C |
| Mock engine in production registry | refused | factory/registry guards unchanged |
| Review write HTTP | not registered | OpenAPI absent `/api/v1/narrative-review-actions` |
| Pattern tables | none | no migration in Phase 2A Integration |
| VERSION | `1.0.5` | no bump in integration work |

## Request-level deny paths (Lab enabled in test only)

| Deny condition | Error family |
|----------------|--------------|
| Non-loopback client | `MOCK_LAB_LOOPBACK_REQUIRED` |
| Missing `X-StoryLens-Mock-Lab: 1` | `MOCK_LAB_REQUEST_MARKER_REQUIRED` |
| Active book conflict | concurrency guard |
| Budget exceeded (fault hook) | budget deny before write |

## What Integration added without opening production

- Conditional Lab router (dev/test + flag)
- Composition root for mock services
- Startup reconcile (mark interrupted only)
- E2E tests with in-process mock engine

## What Integration did not do

- Enable formal whole-book Run create
- Register real Engine or model Provider calls
- Ship Pro capabilities
- Add migrations or Pattern schema
- Bump VERSION / build / publish / push

See [phase1c-mock-production-isolation.md](./phase1c-mock-production-isolation.md) for Phase 1C baseline; Phase 2A Lab inherits and extends mock-only boundaries.
