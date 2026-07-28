# WB-1.5 FINAL REPORT

## Status
tested

## Change
CHG-20260728-012

## Summary
Conservative cross-window materialization: entity merge (林川/林先生), narrative assets, evidence, relations with ORM compatibility adapters.

## Verification
- `test_whole_book_wb15_materialization.py`: 4 passed
- Repeat materialization idempotent (checkpoint reuse)
- Real provider calls: 0

## Compatibility adapters
- Entity↔entity relations via structural character_profile assets + contract_endpoints in attributes_json
- Evidence quotes in evidence_label; offsets + paragraph_content_hash for source API
