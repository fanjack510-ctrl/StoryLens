# Phase 1B — Entity / Alias Verification (Agent D)

**Change:** CHG-20260723-017  
**Date:** 2026-07-23  
**VERSION:** `1.0.5` (unchanged)  
**Baseline HEAD at start:** `633ba93239f727474eaa27c769608870c0ffe12b`

## Commands run

```text
D:\Dstorylens\.venv\Scripts\python.exe -m pytest ^
  apps/api/tests/test_narrative_entity_alias.py -q

python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

Full pytest suite / frontend tests / build / publish / push: **not** run (out of Agent D scope).

## Coverage checklist

| # | Case | Result |
|---|------|--------|
| 1 | Migration 006 execute | PASS |
| 2 | Migration 006 idempotent | PASS |
| 3 | Old Phase 1A DB upgrade | PASS |
| 4 | Create different Entity types | PASS |
| 5 | Empty canonical_name fails | PASS |
| 6 | Entity Lock / Unlock | PASS |
| 7 | Entity Archive | PASS |
| 8 | Add candidate Alias | PASS |
| 9 | Alias confirm | PASS |
| 10 | Alias reject | PASS |
| 11 | Alias Lock | PASS |
| 12 | Duplicate normalized_alias idempotent | PASS |
| 13 | Same alias → different entities returns ambiguous | PASS |
| 14 | Rejected alias excluded from formal match | PASS |
| 15 | book_id isolation | PASS |
| 16 | source_run / source_snapshot preserved | PASS |
| 17 | merge_entities explicitly unsupported | PASS |
| 18 | merge failure leaves DB unchanged | PASS |
| 19 | SQLite foreign keys | PASS |
| 20 | SQLite unique integrity | PASS |
| 21 | version_manager check | (recorded at commit time) |
| 22 | change_registry check | (recorded at commit time) |
| 23 | git diff --check | (recorded at commit time) |

Additional: concurrent identical alias candidate inserts converge on one row (unique + savepoint).

## Integration Issues filed

1. **II-ENTITY-001 — Missing `superseded_by_entity_id` on `narrative_entities`**  
   Asset/Relation stable rows carry `superseded_by_*_id`; Entity does not. Safe `merge_entities` and full supersede-with-target cannot be implemented without a coordinated schema Change. Agent D returns `ENTITY_MERGE_NOT_SUPPORTED` and does not mutate rows.

2. **II-ENTITY-002 — Additive Entity/Alias error codes**  
   Agent D added `ENTITY_INVALID_NAME`, `ENTITY_NOT_ACTIVE`, `ENTITY_MERGE_NOT_SUPPORTED`, `ALIAS_LOCKED` to `errors.py` (shared additive surface). Integration should confirm no collisions with Agent E/F additions on merge.

3. **II-ENTITY-003 — Normalization uses `lower()` not `casefold()`**  
   Frozen `normalize_entity_name` in `asset_key.py` uses `.lower()`. For ASCII this matches casefold; exotic Unicode casefold differences are deferred. Do not fork a second normalizer in services without Contract update.

4. **II-ENTITY-004 — Protocol surface lag**  
   `contracts/entity.py` lists a subset of methods; Agent D also implements `get_entity`, `list_entities`, `archive_entity`, `supersede_entity`, `lock_alias`, `unlock_alias`, `list_entity_aliases`, and returns `AliasLookupResult` from `find_entity_by_alias`. Integration may refresh the Protocol/DTO freeze in a later Change.

## Non-goals verified absent

- No `models.py` table-structure edits  
- No Asset / Relation / Conflict / Snapshot / Run Stage / Pattern Map changes  
- No VERSION bump, `release/unreleased.json` edits, architecture README edits  
- No build / publish / push / stash restore  
- No model calls, prompts, or AI alias disambiguation  
- No historical character backfill  
- Migrations 007–010 untouched in ownership sense (runner still contains them; only 006 migrator refined)
