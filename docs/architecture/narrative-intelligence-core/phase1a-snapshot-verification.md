# Phase 1A Snapshot Verification

**Change:** CHG-20260723-012  
**Date:** 2026-07-23

## Directed tests run

```text
python -m pytest ^
  apps/api/tests/test_narrative_migration_ledger.py ^
  apps/api/tests/test_narrative_hash_backfill.py ^
  apps/api/tests/test_narrative_snapshot_service.py ^
  apps/api/tests/test_narrative_phase1p_contract.py -q
```

Result: **26 passed**

## Coverage checklist

| # | Case | Status |
|---|------|--------|
| 1 | baseline_1_0_5 legal registration | PASS |
| 2 | Illegal baseline rejected | PASS |
| 3 | Migration checksum consistent | PASS |
| 4 | Checksum conflict fails | PASS |
| 5 | Migration re-apply idempotent | PASS |
| 6 | Hash backfill | PASS |
| 7 | CRLF/LF hash consistent | PASS |
| 8 | Book aggregate hash stable | PASS |
| 9 | Snapshot create success | PASS |
| 10 | Snapshot integrity validate | PASS |
| 11 | Snapshot paragraph restore | PASS |
| 12 | Offset OOB detection | PASS |
| 13 | Paragraph hash mismatch detection | PASS |
| 14 | Same content snapshot reuse | PASS |
| 15 | Content change → new snapshot | PASS |
| 16 | BUILDING not completed | PASS |
| 17 | FAILED not completed | PASS |
| 18 | Concurrent / unique constraint | PASS |
| 19 | Legacy DB upgrade path | PASS |
| 20 | SQLite foreign keys | PASS |
| 21 | SQLite integrity (unique) | PASS |
| 22 | `version_manager check` | PASS (1.0.5) |
| 23 | `change_registry check` | PASS |
| 24 | `git diff --check` | PASS |

## Not run (forbidden for Agent A)

- Full pytest suite  
- Frontend tests  
- Windows build / smoke  
- push / merge / publish  

## Integration notes

See Agent A final report section J for Protocol gaps (book aggregate title fields vs `calculate_book_content_hash` signature).
