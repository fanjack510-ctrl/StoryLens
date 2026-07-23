# Phase 1D Read-only Result API

## Routes

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/api/v1/whole-book-runs/{run_id}/results` | Result Index (module statuses) |
| `GET` | `/api/v1/whole-book-runs/{run_id}/results/{module_key}` | Module Envelope |

Query on module route:

- `view=canonical` (default)
- `view=candidate` (explicit)

## Implementation

Router module: `apps/api/app/routers/whole_book_results.py`

Guarantees:

- read-only; no Run/Stage creation
- no Engine / model calls
- no Asset mutation / auto-confirm
- unknown module → `WHOLE_BOOK_MODULE_NOT_SUPPORTED`
- non-book Run → `INVALID_RUN_SCOPE`
- missing Run → typed error
- response strips `prompt` / `credential` / `full_text` / `body`
- loopback security remains app middleware when mounted

## Integration Issue (CHG-030)

Router is **implemented but not registered** in `apps/api/app/main.py`.

Reason: shared registration entry is Integration ownership. Agent K must not modify `main.py`.

Integration should:

```python
from app.routers.whole_book_results import router as whole_book_results_router
app.include_router(whole_book_results_router)
```

Until then, tests mount the router on a local FastAPI app.

## Compatibility

Even while `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`, existing/test book-scope Runs can be projected read-only.
