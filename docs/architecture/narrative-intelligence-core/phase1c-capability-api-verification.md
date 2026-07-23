# Phase 1C Capability API Verification

## Routes

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/capabilities` | List + nested metadata/decision |
| GET | `/api/v1/capabilities/{key}` | Detail; unknown → 404 `CAPABILITY_UNKNOWN` |
| POST | `/api/v1/books/{book_id}/whole-book-runs/preflight` | Read-only (Integration) |

Loopback / local-origin middleware applies. No license secrets, credentials, or exception stacks in payloads.

## Decision payload (snake_case wire)

- `capability_key`, `allowed`, `availability`, `reason_code`, `display_message`
- `supported_modes`, `quota`, `usage`, `remaining`
- `offline_status`, `license_status`, `evaluated_at`

Frontend `allowed` must equal backend Decision `allowed` (DTO mapper only; never recompute in components).

## Metadata (whole_book_analysis)

| Field | Value |
|-------|-------|
| requires_license | true |
| shipped | false |
| preview_visible | true |
| availability | preview |
| supported_modes | whole_book_native, whole_book_enhanced |

Default Decision: `allowed=false`, `reason_code=CAPABILITY_NOT_SHIPPED`.

## Reason codes

- Unknown capability key → `CAPABILITY_UNKNOWN`
- Unsupported analysis mode → `CAPABILITY_MODE_NOT_SUPPORTED`
- Mode is **not** a CapabilityKey

## Frontend alignment

- Client base: `/api/v1/capabilities` (no second path family)
- DTO guards accept `CAPABILITY_MODE_NOT_SUPPORTED`
- Presentation state `mode_not_supported`
- `preview_visible` shows preview affordance; start remains disabled unless `allowed===true`
- `narrative_asset_library` foundation note: not paywall-locked
- Fixture: `backendPayload.fixture.ts` mirrors `capability_api_payloads.py`
