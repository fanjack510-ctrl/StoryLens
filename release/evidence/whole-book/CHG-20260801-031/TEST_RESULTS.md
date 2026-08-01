# CHG-20260801-031 Test Results

## Status
tested (awaiting MG-CHG-20260801-031)

## Vitest
`wholeBookFreeProduct.layout.test.tsx` + `wholeBookFreeProduct.test.tsx`: **22 passed**

## Playwright layout script
`layout_playwright_verify.mjs` against UI `http://127.0.0.1:1424` / API `8004`:
**35/35 checks passed** across 1280×720, 1366×768, 1440×900, 1920×1080, 2560×1440.

Key 1920×1080:
- rootW=1600, navW=240, mainW=1212, claimColumns=2, claimCount=9
- limitsCols=3 on cost/consent page
- horizontal scroll ABSENT
- Pro purchase UI ABSENT

## Typecheck
`npx tsc -p tsconfig.app.json --noEmit`: PASS

## Pytest (Wave D slice)
26 passed — prepare alias, WB-1.6A/1.7/1.8/1.9

## Screenshots
- before-1920x1080.png
- after-overview-1920x1080.png
- after-cost-consent-1920x1080.png
- after-overview-1366x768.png
- after-cost-consent-1366x768.png

## Constraints
- REAL PROVIDER CALLS: 0
- FORMAL DATABASE WRITES: 0
- PRIVATE MODIFIED: NO
- WB-2.1: NOT STARTED
