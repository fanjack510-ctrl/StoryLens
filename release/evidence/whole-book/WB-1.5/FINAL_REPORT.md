# WB-1.5 FINAL REPORT

## Status
tested

## Change
CHG-20260728-012

## Summary
Conservative cross-window character merge and narrative entity/asset/evidence/relation materialization with idempotent checkpoint `minimal_asset_materialization_v1`.

## Verification
- `test_whole_book_wb15_materialization.py` PASS
- 林川 / 林先生 exact alias merge
- Second materialization: entity/asset/evidence/relation counts unchanged
- Checkpoint payload contains no full text
- Confirmed-entity overwrite path guarded; Real provider: 0

## Compatibility notes
- Relations: structural `character_profile` asset endpoints + `contract_endpoints` in attributes_json
- Evidence quotes: `evidence_label` + offset slice on source API

## Isolation
- Temp SQLite only
- Formal AppData writes: 0
