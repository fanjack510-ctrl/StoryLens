# StoryLens 1.1.0 — Native Overview Error Codes

**Status:** Frozen (STEP 2.1)  
**Change:** CHG-20260725-003  
**Implementation:** `apps/api/app/narrative_core/contracts/whole_book_overview_errors.py`

## Related docs

- [Contract](./storylens-1.1.0-native-overview-contract.md)
- [State machine](./storylens-1.1.0-native-overview-state-machine.md)
- [Database](./storylens-1.1.0-native-overview-database.md)
- [Architecture](../architecture/storylens-whole-book-architecture.md)
- [Public/Private boundary](../architecture/storylens-public-private-boundary.md)
- [1.1.0 scope](../releases/storylens-1.1.0-scope.md)
- [ADR-001](../architecture/adr/ADR-001-single-business-database.md) · [ADR-002](../architecture/adr/ADR-002-whole-book-native-source-of-truth.md) · [ADR-003](../architecture/adr/ADR-003-unified-narrative-assets.md) · [ADR-004](../architecture/adr/ADR-004-whole-book-runtime-and-analysis-passes.md) · [ADR-005](../architecture/adr/ADR-005-long-text-index-strategy.md)

## Envelope

```json
{
  "error": {
    "code": "PRO_LICENSE_REQUIRED",
    "message": "用户可理解的信息",
    "retryable": false,
    "details": {},
    "run_id": null,
    "stage_key": null,
    "window_index": null
  }
}
```

Each code freezes: HTTP status, `retryable`, user message, whether to keep the Run, whether Retry is allowed, whether user action is required.

## Code table

| Code | HTTP | retryable | keep_run | allow_retry | requires_user_action |
|------|------|-----------|----------|-------------|----------------------|
| `PRO_LICENSE_REQUIRED` | 403 | no | no | no | yes |
| `BOOK_NOT_FOUND` | 404 | no | no | no | yes |
| `BOOK_CONTENT_EMPTY` | 422 | no | no | no | yes |
| `BOOK_HAS_ACTIVE_TASK` | 409 | no | yes | no | yes |
| `SNAPSHOT_INVALID` | 409 | no | yes | no | yes |
| `SNAPSHOT_CONTENT_CHANGED` | 409 | no | yes | no | yes |
| `PROVIDER_NOT_CONFIGURED` | 422 | no | no | no | yes |
| `PROVIDER_UNAVAILABLE` | 503 | yes | yes | yes | no |
| `PROVIDER_TIMEOUT` | 504 | yes | yes | yes | no |
| `PROVIDER_RATE_LIMITED` | 429 | yes | yes | yes | no |
| `PROVIDER_OUTPUT_INVALID` | 422 | yes | yes | yes | no |
| `PROVIDER_OUTPUT_EMPTY` | 422 | yes | yes | yes | no |
| `CITATION_INVALID` | 422 | yes | yes | yes | no |
| `EVIDENCE_INVALID` | 422 | yes | yes | yes | no |
| `RUN_ALREADY_ACTIVE` | 409 | no | yes | no | yes |
| `RUN_NOT_FOUND` | 404 | no | no | no | no |
| `RUN_NOT_RETRYABLE` | 409 | no | yes | no | yes |
| `RUN_NOT_RESUMABLE` | 409 | no | yes | no | yes |
| `RUN_ALREADY_COMPLETED` | 409 | no | yes | no | no |
| `WINDOW_BUILD_FAILED` | 500 | yes | yes | yes | no |
| `WINDOW_EXECUTION_FAILED` | 500 | yes | yes | yes | no |
| `MATERIALIZATION_FAILED` | 500 | yes | yes | yes | no |
| `PROJECTION_FAILED` | 500 | yes | yes | yes | no |
| `DATABASE_WRITE_FAILED` | 500 | yes | yes | yes | no |
| `COST_LIMIT_EXCEEDED` | 402 | no | yes | no | yes |
| `USER_CONSENT_REQUIRED` | 422 | no | no | no | yes |
| `PRIVATE_ENGINE_UNAVAILABLE` | 503 | yes | yes | yes | no |
| `PRIVATE_ENGINE_INCOMPATIBLE` | 409 | no | yes | no | yes |

Arbitrary string exceptions are not allowed as the product error surface.
