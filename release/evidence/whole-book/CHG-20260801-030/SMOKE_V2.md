# CHG-20260801-030 / CHG-029 Smoke v2

## Root cause
CHG-029 merged Wave D base `e35bc99`, but CHG-030 product fix `6d627bd` was committed **after** that tip on `integration/whole-book-v120`. Prepare alias therefore never entered the 1.1.2→1.2.0 merge.

## Source commit reused
`6d627bdfad8e4c76e51f616f7c428907e4cf9788` — cherry-picked into `integration/1.2.0-after-1.1.2` (not rewritten).

## Shared handler
- Canonical: `GET /api/v1/books/{book_id}/whole-book/free/prepare`
- Compatibility: `GET /api/v1/books/{book_id}/whole-book/prepare`
- Both call `_prepare` → `prepare_free_whole_book_analysis_v1`

## Smoke database
`C:\Users\msi\AppData\Local\Temp\storylens-chg029-smoke-v2\chg029_smoke_v2.db`

Seed (test-only): `apps/api/scripts_seed_chg029_smoke_v2.py`  
Manifest: `%TEMP%\storylens-chg029-smoke-v2\MANUAL_FIXTURES.json`  
Launcher (test-only): `release/evidence/whole-book/CHG-20260801-030/launch_chg029_smoke_api.py`

## Runtime
- UI: `http://127.0.0.1:1423`
- API: `http://127.0.0.1:8003`
- Real provider: disabled
- Formal AppData DB: not used
- Journey resume failure: launcher inject for `fail_journey_run_id` only
- Smoke fake: process-local; no external network

## Browser DOM verified
- `/books/8/whole-book` prepare → HTTP 200
- Fixture banner visible; no “无法读取数据”
- Overview + characters_events module buttons present
- Cost consent page shows prepare + consent
- Custom scene split chapter page opens with scene UI

## Task control
PAUSE/RESUME/CANCEL: AUTOMATED PASS / MANUAL NOT EXECUTED / EXC-WB-FREE-WAVE-D-001
