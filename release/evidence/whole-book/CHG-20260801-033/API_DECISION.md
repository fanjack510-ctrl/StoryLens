# API_DECISION

## Prepare（compatibility frozen）

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/books/{book_id}/whole-book/free/prepare` | Keep |
| GET | `/api/v1/books/{book_id}/whole-book/prepare` | Keep product alias |

`PREPARE COMPATIBILITY PRESERVED：YES`

## Execution（reuse existing Free run machine）

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/books/{book_id}/whole-book/free/create` | Reuse |
| POST | `/api/v1/books/{book_id}/whole-book/runs/fixture` | Reuse / extend fixture pipeline |
| GET | `/api/v1/whole-book/runs/{run_id}/progress` | Reuse |
| POST | `.../pause` · `.../resume` · `.../cancel` | Reuse |
| GET | run detail / stages (foundation) | Reuse |

**Forbidden:** second independent task state machine for structure-only runs.

## Result — PRODUCT (frozen)

| Item | Freeze |
|---|---|
| Method | GET |
| Path | `/api/v1/whole-book/runs/{run_id}/structure` |
| Response model | StructureStagesResultV2 product envelope (see below) |
| contract version | wire `contract_version=v2` / package `2.0.0` |
| Auth / capability | `whole_book.structure` Free granted after flip |

### Response semantics

| Case | HTTP | Body |
|---|---|---|
| completed (incl. legal insufficient empty) | 200 | `{ "structure": <V2>, "result_status": "completed", "coverage_scope": ... }` |
| module failed (unrecoverable) | 200 with `result_status=failed` **or** 409/422 with STRUCTURE_* code — **freeze: 200 + `result_status=failed` + `failure_code`** for Free UX parity with progress | include code |
| conflict versions present | 200 + `result_status=conflict` + version list / current pointer | no silent pick |
| result absent (run not finished / never produced) | 404 `STRUCTURE_RESULT_ABSENT` | — |
| unknown run | 404 | — |

Evidence source remains foundation:

`GET /api/v1/whole-book/evidences/{evidence_id}/source` (existing deep-link)

## Result — LAB COMPAT (keep)

| Method | Path |
|---|---|
| GET | `/api/v1/whole-book-runs/{run_id}/results/structure_stages` |

Must remain for Lab/FakeHttp A–J. Product Desktop uses **PRODUCT** path above.

## Capability

`GET /api/v1/whole-book/product-capabilities` — after implementation, `whole_book.structure` `release_status=available`.  
`whole_book.chapter_functions` stays **planned**. Free count remains 4; Pro count 8.

## Idempotency

Continue `client_request_id` on create/fixture. Resume must not double-bill / double-call (WB-1.8).
