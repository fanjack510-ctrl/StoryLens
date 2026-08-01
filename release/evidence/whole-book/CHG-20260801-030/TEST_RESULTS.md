# CHG-20260801-030 Test Results

## Status
tested (not verified)

## Public pytest (targeted)
87 passed — includes:
- `test_whole_book_prepare_route_alias_chg030.py`
- WB-1.6 / 1.6A / 1.7 / 1.8 / 1.9 / 1.10
- CHG-006 cancel, CHG-013 confirm/start, CHG-023 resume, CHG-017 journey nav, CHG-041 scene boundary

## Private pytest
238 passed

## Vitest
`wholeBookFreeProduct.test.tsx` + `BookRoutePage.journeyNav.test.tsx`: 26 passed

## Typecheck
`npx tsc -p tsconfig.app.json --noEmit`: PASS

## Live smoke (v2)
- FREE prepare HTTP 200
- Compatibility prepare HTTP 200
- Payload match: latest_run completed/fixture
- Browser DOM: prepare 200, Sample S title, fixture banner, no 404 error UI
- Cost consent UI present
- Chapter fixture page opens

## Constraints
- REAL PROVIDER CALLS: 0
- EXTERNAL NETWORK CALLS: 0
- FORMAL DATABASE WRITES: 0
- WB-2.1: NOT STARTED
