# CAPABILITY_GATE — CHG-20260807-054

## Before

`create_free_whole_book_analysis_v1`:

1. `!real_provider_enabled()` → `WHOLE_BOOK_REAL_PROVIDER_DISABLED`
2. else → **always** `WHOLE_BOOK_CAPABILITY_DISABLED`（硬 stub）

## After

Formal Create allowed **iff**:

| Condition | Enforcement |
|---|---|
| Free product enabled | `_require_free_product_enabled` |
| Capability Free tier | `require_capability_access` ×4 modules |
| Real Provider flag ON | else `WHOLE_BOOK_REAL_PROVIDER_DISABLED` |
| Consent valid (book/estimate/snapshot/revision) | `validate_whole_book_consent` |
| Provider config valid + API Key available | `resolve_formal_provider_row` → else `WHOLE_BOOK_REAL_PROVIDER_DISABLED` |
| Snapshot/revision from `create_or_reuse_book_snapshot_v1` | consent binds snapshot |

## Explicit non-behaviors

- No silent Fake / Fixture fallback on formal create
- No auto model/provider switch
- Fixture Preview remains separate (`create_fixture_*` + Fixture transports)

## Stub status

`WHOLE_BOOK_CAPABILITY_DISABLED` hard stub in formal create: **REMOVED**
