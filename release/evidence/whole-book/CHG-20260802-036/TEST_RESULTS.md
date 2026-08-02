# CHG-20260802-036 — WB-2.1 Integration Test Results

STATUS: **tested** (not verified — pending MG-WB-2.1)

## Environment

- Public worktree: `D:\Dstorylens-wt-1.2.0-after-1.1.2`
- Private worktree: `D:\Dstorylens-private-wt-1.2.0-after-1.1.2`
- Private engine on PYTHONPATH for Public tests / smoke API
- REAL PROVIDER CALLS: 0
- EXTERNAL NETWORK CALLS: 0
- FORMAL DATABASE WRITES: 0

## Private pytest

```text
250 passed
```

## Public pytest (WB-2.1 / Wave D targeted)

```text
apps/api/tests/test_whole_book_wb21_structure_stages_a_o.py
apps/api/tests/test_structure_stages_output_contract_v2_empty_policy.py
apps/api/tests/test_narrative_phase2br1_structure_stages_v2_http_replay.py
apps/api/tests/test_whole_book_wb16a_product_capability.py
apps/api/tests/test_whole_book_wb16_overview_pipeline.py
apps/api/tests/test_whole_book_wb17_free_product_api.py

60 passed
```

Includes A–O matrix, empty policy, pause/resume/cancel, duplicate resume, confirmed no-overwrite, conflict creation, native input audit (counts 0), structure product API, capability Free 4 / Pro 8.

## Public pytest (full suite, ignore stale phase1b migration file)

```text
2095 passed, 44 failed, 54 skipped
```

Failures are dominated by pre-existing 1.2.0 baseline debt (VERSION still asserted as 1.0.5 in Phase2* locks, change_registry/git_diff gates, migration id count 16≠13). **No failures in `test_whole_book_wb21_*` / structure empty-policy / WB-1.6/1.6A/1.7 Free product suites.**

## Desktop

| Gate | Result |
|---|---|
| Typecheck | PASS |
| Vitest structure / Free product / V2 | 32 passed |
| Playwright `test:e2e:wb21-structure` | 2 passed (1366 / 1920) |
| Full Vitest | 1357 passed / 30 failed |

Full Vitest failures are confined to files **not modified** by WB-2.1 merges (mostly `readerJourney/*`, plus pre-existing BookRoute/ProgressPanel/runtime_capabilities/SceneBoundaryNavigation.chg041). Structure + Wave D Free product suite PASS.

## Smoke / DOM

- DB: `%TEMP%\storylens-wb21-integration\wb21_integration.db`
- UI `1425` / API `8005`
- Flag: `VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED=true`
- DOM verify: `DOM_VERIFY_RESULTS.json` — page_ok_all=true, purchase_ui ABSENT, structure data-states match catalog

## Contract

- Canonical: StructureStagesResultV2
- Wire: `contract_version=v2` / `2.0.0`
- V1: adapter-only
- DATABASE MIGRATION: NO
