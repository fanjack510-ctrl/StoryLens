# Phase 2A Lab API Implementation

## Router

`apps/api/app/routers/whole_book_mock_lab_runs.py`

Prefix: `/api/v1/labs/whole-book-runs`
OpenAPI tags: `labs`, `non-production`, `mock-whole-book-run`

## Routes

| Method | Path |
|--------|------|
| POST | `/api/v1/labs/whole-book-runs` |
| GET | `/api/v1/labs/whole-book-runs/{run_id}` |
| GET | `/api/v1/labs/whole-book-runs/{run_id}/stages` |
| POST | `.../pause` \| `resume` \| `cancel` |
| POST | `.../stages/{stage_key}/retry` |

## Guards

- Write (and Lab reads) require loopback + `X-StoryLens-Mock-Lab: 1`
- Lab enabled + allowed environment via service authorize
- Non-mock runs → `MOCK_RUN_NON_MOCK_TARGET`
- No novel body in/out; no prompt/credential; no stack traces in errors
- Production create path remains disabled (`WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`)

## Integration Issue

**Not registered in `apps/api/app/main.py`** — Integration ownership (`CHG-20260723-035`).
Constant: `INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION`.
Tests mount the router directly via `FastAPI.include_router`.
