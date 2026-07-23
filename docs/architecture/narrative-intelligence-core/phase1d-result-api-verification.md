# Phase 1D Result API Verification

## Registered (read-only)

| Method | Path |
|--------|------|
| GET | `/api/v1/whole-book-runs/{run_id}/results` |
| GET | `/api/v1/whole-book-runs/{run_id}/results/{module_key}` |

- Router: `apps/api/app/routers/whole_book_results.py`
- Mounted in `apps/api/app/main.py`
- Visible in OpenAPI
- Loopback / origin guard via existing middleware
- Envelope DTO only — no full body / prompt / credentials
- Does not create Run/Stage, call Engine/models, write Assets, or mutate Conflict

## Not registered

- `POST /api/v1/books/{book_id}/whole-book-runs` (create still disabled)
- `POST /api/v1/narrative-review-actions` (Phase 2E)

## Tests

- OpenAPI path presence (`test_narrative_phase1d_integration.py`)
- Index / unknown run / unknown module via isolated TestClient + fixture DB
- Agent K suite `test_narrative_phase1d_result_projection.py`
