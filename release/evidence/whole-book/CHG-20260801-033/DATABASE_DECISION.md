# DATABASE_DECISION

## Decision

```
DATABASE CHANGE：NOT REQUIRED
MIGRATION REQUIRED：NO
方案：A — 复用现有 Asset / Run / Evidence 表
```

## Evidence

1. `whole_book_run_stages.stage_code` / `provider_units.stage_code` are `String(64)` — **not** a DB CHECK enum (`apps/api/app/db/models.py`).  
2. Narrative assets use string `asset_type`; Lab already maps `AssetType.STRUCTURE_STAGE = "structure_stage"`.  
3. CHG-20260725-001 recorded `database_changed=false` for Structure Stages V2 Lab path.  
4. Free contract constants note stage codes are “registry-extensible; not a DB enum column”.

## Storage model (frozen)

| Concern | Mechanism |
|---|---|
| Result payload | Narrative Asset `asset_type=structure_stage` + artifact/projection (existing Lab mapper path) |
| schema_version | Asset/artifact payload carries V2 contract markers (`contract_version=v2` / package 2.0.0) |
| Query | By `run_id` + asset_type / module result projection (Lab `results/structure_stages` pattern) |
| Bind run / snapshot / revision | Existing WholeBookRun → snapshot_revision / book snapshot immutability (WB-1.2) |
| Conflict versions | Existing analysis conflict + asset versioning; **no silent overwrite** of confirmed (WB-1.10) |
| Confirmed no-overwrite | Reuse WB-1.10 rules; new analysis creates new version / conflict, never mutate confirmed |

## Code-only (not Migration)

- Extend `WHOLE_BOOK_STAGE_CODES_V1` (or Free product stage list) with `synthesize_structure_stages`  
- Register provider unit keys for structure  
- Fixture rows insert new stage_code strings into existing tables  

## Compatibility

| Item | Verdict |
|---|---|
| Old DB open | YES — additive rows only |
| v1.1.2 chapter tables | Unaffected |
| Rollback | Flip capability `whole_book.structure` back to planned; leave historical assets |
| Fixture updates | Code/fixture data only |

## Explicit non-goals

- No new `structure_stages` SQL table in WB-2.1  
- No Alembic migration in the authorized Agent 1 scope unless a later audit proves a NOT NULL column gap (none found now)
