# Phase 2A Lab Router Security

**Change:** CHG-20260723-035 (Integration wiring)
**Contract:** [phase2a-mock-lab-security.md](./phase2a-mock-lab-security.md)

## Flag default

`WHOLE_BOOK_MOCK_LAB_ENABLED` default **false**. Release and production builds stay closed without explicit env override.

## Environment gate

Lab HTTP surface mounts only when **all** hold:

| Gate | Rule |
|------|------|
| Environment | `development` or `test` only — `production` always denies router registration |
| Lab flag | `WHOLE_BOOK_MOCK_LAB_ENABLED=true` |
| Loopback | Request client host ∈ `{127.0.0.1, ::1, localhost, testclient}` |
| Marker header | `X-StoryLens-Mock-Lab: 1` on mutating Lab requests |
| Engine | `MockWholeBookAnalysisEngine` (`mock_whole_book_v0`), `non_production=true` |

Authorization is enforced again inside `MockLabAuthorizationService` per request even when router is mounted.

## Conditional router (`main.py`)

```text
mount_mock_lab_if_enabled(app)
  → should_register_mock_lab_router(env, lab_enabled)
  → create_mock_lab_runtime(..., set_as_default=True)
  → app.include_router(whole_book_mock_lab_runs.router)
```

When gates fail: router **not** mounted; OpenAPI has no `/api/v1/labs/whole-book-runs/*` paths.

## Production OpenAPI absence

Integration tests assert:

- Lab paths present only when `environment=test` + Lab enabled
- Lab paths **absent** when `environment=production`
- Formal create path `POST /api/v1/books/{book_id}/whole-book-runs` not registered
- Phase 1D read-only result routes remain registered once
- Review write route remains absent

## Startup logging

`log_lab_startup_status` logs enabled/disabled, environment, router_registered — never credentials or novel content.

## Unchanged production gates

- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
- `PRODUCTION_DEFAULT_ENGINE_ID=None`
- `PRO_CAPABILITIES_SHIPPED=false`
