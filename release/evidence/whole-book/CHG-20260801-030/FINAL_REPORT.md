# CHG-20260801-030 FINAL REPORT

## Status
tested (awaiting MG-STORYLENS-1.1.2-TO-1.2.0-INTEGRATION)

## Findings
1. UI called `/api/v1/books/{id}/whole-book/prepare`.
2. Pre-CHG-030 backend only registered `/whole-book/free/prepare` → HTTP 404 / “无法读取数据”.
3. Qualified fix already existed on Wave D as `6d627bd` after merge base `e35bc99`; CHG-029 therefore missed it (omitted commit, not conflict loss).
4. Fix restored by cherry-pick into `integration/1.2.0-after-1.1.2` with shared `_prepare` handler.
5. CHG-029 smoke v2 DB rebuilt with per-scenario books (scene/journey/whole-book). Not real model output (`result_origin=fixture` / test-only seeds).

## Parent
CHG-20260731-029 remains **tested**; MANUAL UI READY restored to YES under smoke v2.
