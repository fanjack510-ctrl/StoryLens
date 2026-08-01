# CHG-20260731-029 Test Results

## Status
tested (automatic regression only; manual UI smoke pending)

## Exception retained
`EXC-WB-FREE-WAVE-D-001` — PAUSE/RESUME/CANCEL remain AUTOMATED PASS / MANUAL NOT EXECUTED

## Public pytest (core)
113 passed — suite including:

- `test_whole_book_wb18_pause_resume.py`
- `test_whole_book_wb17_free_product_api.py`
- `test_whole_book_wb19_native_independence.py`
- `test_whole_book_wb16a_product_capability.py`
- `test_whole_book_wb110_confirm_protection.py`
- `test_whole_book_wb05_provider_orch.py`
- `test_task_cancellation_chg006.py`
- `test_confirm_start_journey_race_chg013.py`
- `test_chg023_resume_client_request_id.py`
- `test_reader_journey_resume_idempotent_chg023.py`
- `test_chg041_scene_boundary_manual_review.py`
- `test_chg040_boundary_adjudication_truncation.py`
- `test_active_journey_stale_recovery_chg018.py`
- `test_journey_nav_visibility_chg017.py`

## Private pytest
19 passed — includes `tests/test_scene_boundary_hotfix_chg040.py`

## Vitest
- `wholeBookFreeProduct.test.tsx`: 15 passed
- `ReaderJourneyResumeCard.test.tsx` + `wholeBookFreeProduct`: 19 passed
- `BookRoutePage.journeyNav.test.tsx`: 7 passed (includes CHG-025 right-rail CTA)
- `WorkspaceJourneyPane.test.tsx`: 11 passed (in focused run)

## Typecheck
`npx tsc -p tsconfig.app.json --noEmit`: PASS

## Version
`scripts/version_manager.py check`: PASS → **1.2.0**

## Capability contract (post-merge)
- Free modules: 4 (`overview`, `characters_events` available; `structure`, `chapter_functions` planned)
- Pro modules planned: 8

## Constraints
- REAL PROVIDER CALLS: 0
- Formal AppData writes: 0 (tests use temp DBs)
- WB-2.1 implementation: NOT STARTED

## Manual smoke environment
See `MANUAL_SMOKE_ENV.md` — UI `http://127.0.0.1:1422` / API `http://127.0.0.1:8002` / temp DB only.
Checklist pending human execution. Task control remains MANUAL NOT EXECUTED.
