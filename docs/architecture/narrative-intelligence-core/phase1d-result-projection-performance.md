# Phase 1D Result Projection Performance

## Target bounds

| Dimension | Bound |
|-----------|-------|
| Chapters | 100 / 500 / 1000 supported at Index level (chapter list not eagerly expanded) |
| Visible Assets | default max **100** |
| Visible Relations | default max **250** |
| Evidence | lazy index / counts only |
| Payload items | capped (`MAX_PAYLOAD_ITEMS` / chapter functions up to 1000) |

## Design choices

1. Batch load AssetVersion / RelationVersion with `selectinload(evidence)` — avoid per-row evidence queries
2. Result Index returns evidence **counts**, not full Evidence rows
3. Module endpoints are independently readable
4. In-memory projection cache per service instance (`refresh_projection` clears it)
5. No FTS5, no new DB, no Pattern tables
6. Evidence index API returns hash/role refs only — never paragraph body text

## Verification

`test_query_count_bound_no_obvious_n_plus_one` seeds 40 storyline assets and asserts repository call counter stays well below N (no obvious N+1).
