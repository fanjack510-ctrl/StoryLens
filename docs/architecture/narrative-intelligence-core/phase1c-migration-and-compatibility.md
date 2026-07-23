# Phase 1C Migration and Compatibility

## Key unification

| Source | Keys |
|--------|------|
| Backend `CANONICAL_FEATURES` / `PRO_FEATURES` | 5 canonical capability keys |
| Desktop `entitlementApi.PRO_FEATURE_KEYS` | Same 5 keys |
| Legacy VIP `license/features.ts FEATURE_KEYS` | 7 keys → mapped via `capability_legacy.py` / `legacyMapper.ts` |

Analysis modes `whole_book_native` / `whole_book_enhanced` are **not** separate capabilities — they are `WholeBookAnalysisMode` values under `whole_book_analysis`.

## Legacy mapping (many-to-one allowed)

See `capability_legacy.py` table. Multiple VIP keys may map to `whole_book_analysis`; no conflicting one-to-many targets.

## Compatibility rules

- Phase 1B entity/asset/relation APIs unchanged; no Pro gate added.
- License payload still lists 5 canonical features; capability registry adds `shipped` / `availability` metadata.
- `PRO_CAPABILITIES_SHIPPED=false` — UI must not present Pro features as shipped.

## No migration

Phase 1C-P adds no DB migrations.
