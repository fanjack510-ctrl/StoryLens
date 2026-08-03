# BASELINE_FAILURE_COMPARISON — CHG-20260803-042

## Public pytest
- Prompt baseline: 2095 passed / 44 failed
- After Integration: 2114 passed / 48 failed / 6 collection errors
- Delta passed: +19; delta failed: +4
- Attribution: no `test_whole_book_wb22_*` failures; extra fails are pre-existing registry/version/gate/env classes (change_registry_check, version locks, live network gate, scene pipeline, etc.) + 6 collection ImportErrors (native_overview plugin / http_replay imports)
- WB-2.2 NEW FAILURES: **0**

## Vitest
- Prompt baseline: 1357 passed / 30 failed
- After: 1376 passed / 30 failed
- Same failure count; failures remain readerJourney legacy suite
- WB-2.2 NEW FAILURES: **0**

## Known preserved
- Scene `test_fake_provider_complete_pipeline`
- check_project TIMEOUT
