# Phase 1C API Contract

HTTP DTO skeletons only — **no live whole-book run routes** in Phase 1C-P.

## DTOs (`contracts/api_dto.py`)

- `CapabilityListItemDTO`
- `CapabilityDecisionDTO`
- `WholeBookPreflightDTO` (future)

Constant: `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED = True`

## Disabled endpoints

`POST /api/v1/whole-book-runs` (and variants) **not registered** until Agent H + Integration. Preflight/list capability routes are Agent H scope.

Errors use frozen `NarrativeCoreErrorCode` values (`WHOLE_BOOK_CAPABILITY_DENIED`, etc.).

Agent H wires routers without modifying Phase 1C-P contract modules.
