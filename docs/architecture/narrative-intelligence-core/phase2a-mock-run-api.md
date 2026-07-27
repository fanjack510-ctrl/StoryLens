# Phase 2A Mock Run API

## Lab routes (dev/test + Lab enabled)

- POST /api/v1/labs/whole-book-runs
- GET /api/v1/labs/whole-book-runs/{run_id}
- GET /api/v1/labs/whole-book-runs/{run_id}/stages
- POST .../pause | resume | cancel
- POST .../stages/{stage_key}/retry

## Production

POST /api/v1/books/{book_id}/whole-book-runs remains **disabled** (`WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`).

## Rules

Register/execute only in development/test with Lab enabled; writes require loopback + Lab marker; reject non-mock runs; no full body in/out; no prompt/credential; OpenAPI tags labs/non-production; pause/resume/retry/cancel idempotent; Result reads reuse read-only Result API.
