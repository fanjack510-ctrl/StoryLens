# Phase 2A Mock Run Client

## Module

`apps/desktop/src/features/wholeBook/runShell/client/mockWholeBookRunClient.ts`

## Methods

| Method | Path |
|--------|------|
| `create` | `POST /api/v1/labs/whole-book-runs` |
| `get` | `GET /api/v1/labs/whole-book-runs/{run_id}` |
| `getStages` | `GET /api/v1/labs/whole-book-runs/{run_id}/stages` |
| `pause` | `POST .../pause` |
| `resume` | `POST .../resume` |
| `cancel` | `POST .../cancel` |
| `retryStage` | `POST .../stages/{stage_key}/retry` |

## Guarantees

1. Every write includes `X-StoryLens-Mock-Lab: 1`.
2. Never calls `POST /api/v1/books/{book_id}/whole-book-runs`.
3. Does not invent Run status or `allowed_actions`.
4. Does not invent Capability.
5. Network failures → `MockRunClientError(NETWORK)` fail-closed.
6. Unknown run → `MOCK_RUN_NOT_FOUND`.
7. `mock!==true` / `non_production!==true` → `MOCK_RUN_NON_MOCK_TARGET`.
8. DTO guards reject credential / prompt / full_text keys.
9. Create body never includes full novel text.

## Result Projection Client

Read-only Result API reuse:

- `GET /api/v1/whole-book-runs/{run_id}/results`
- `GET /api/v1/whole-book-runs/{run_id}/results/{module_key}?view=candidate`

Does not trigger runs; Lab always requests `view=candidate`.
