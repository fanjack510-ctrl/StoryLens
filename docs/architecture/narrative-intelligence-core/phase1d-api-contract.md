# Phase 1D-P API Contract

DTO / route freeze only. **Run create remains disabled.** No real models; no formal edit routes this phase.

## Existing APIs (live)

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/api/v1/capabilities` | Phase 1C |
| `GET` | `/api/v1/capabilities/{key}` | Phase 1C |
| `POST` | `/api/v1/books/{book_id}/whole-book-runs/preflight` | Read-only preflight |

## Disabled / not registered for production create

| Flag | Value |
|------|-------|
| `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` | `true` |
| `PRO_CAPABILITIES_SHIPPED` | `false` |
| `PRODUCTION_DEFAULT_ENGINE_ID` | `None` |

`POST` whole-book-runs create **must stay disabled** through Phase 1D-P.

## Future frozen routes

### Run lifecycle (future)

| Method | Path |
|--------|------|
| `POST` | `/api/v1/books/{book_id}/whole-book-runs` |
| `GET` | `/api/v1/whole-book-runs/{run_id}` |
| `GET` | `/api/v1/whole-book-runs/{run_id}/stages` |
| `POST` | `/api/v1/whole-book-runs/{run_id}/pause` |
| `POST` | `/api/v1/whole-book-runs/{run_id}/resume` |
| `POST` | `/api/v1/whole-book-runs/{run_id}/cancel` |
| `POST` | `/api/v1/whole-book-runs/{run_id}/stages/{stage_key}/retry` |

### Results (future read)

| Method | Path |
|--------|------|
| `GET` | `/api/v1/whole-book-runs/{run_id}/results` |
| `GET` | `/api/v1/whole-book-runs/{run_id}/results/{module_key}` |

### Evidence / Review / Conflict (future)

| Method | Path |
|--------|------|
| `GET` | `/api/v1/narrative-assets/{asset_id}/evidence` |
| `POST` | `/api/v1/narrative-review-actions` |
| `GET` | `/api/v1/books/{book_id}/analysis-conflicts` |

## Phase 1D-P scope

- Define DTO + route Contract only
- Do **not** open real Run creation
- Do **not** wire real models
- Do **not** add formal editing routers beyond contract stubs if any
- Agent K may add read-only result API **skeleton** later; still no live create
- Errors continue to use `NarrativeCoreErrorCode`

Shared type homes (Phase 1D-P):

- Backend: `apps/api/app/narrative_core/product_contract/`
- Frontend: `apps/desktop/src/features/wholeBook/contracts/`

See [phase1c-api-contract.md](./phase1c-api-contract.md).
