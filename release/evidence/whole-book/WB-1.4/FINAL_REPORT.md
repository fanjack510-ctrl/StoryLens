# WB-1.4 FINAL REPORT

## Status
tested

## Change
CHG-20260728-011

## Summary
Minimal window entity/event extraction with CountingFake fixture transport, Public secondary validation, migration `20260728_014` window-results table, and extract-fixture orchestration.

## Verification
- Public: `test_whole_book_wb14_extraction.py` PASS
- Private: `test_whole_book_window_entity_event_v1.py` PASS (10)
- Strict evidence resolution only (no fuzzy fallback)
- Sample S: 3 windows → 3 logical window calls; completed units reused
- Real provider calls: 0

## Isolation
- Temp SQLite only
- Formal AppData writes: 0
- Private engine for this Change: implemented in private worktree (CHG-011 commit)
