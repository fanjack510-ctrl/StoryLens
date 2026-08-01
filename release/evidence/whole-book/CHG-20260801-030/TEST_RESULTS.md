# CHG-20260801-030 Test Results

## Vitest
- `apps/desktop/src/pages/wholeBookFreeProduct.test.tsx`: 19 passed

## Pytest
- `apps/api/tests/test_whole_book_wb17_free_product_api.py`: passed (prepare product shape, missing book, route registration)
- `apps/api/tests/test_whole_book_wb18_pause_resume.py`: passed
- `apps/api/tests/test_whole_book_wb19_native_independence.py`: passed
- `apps/api/tests/test_whole_book_wb16_overview_pipeline.py`: passed

## Typecheck
- `npx tsc -p tsconfig.app.json --noEmit`: PASS

## Manual env probes (isolated DB)
- `GET /api/v1/books/1/whole-book/prepare` → 200, Sample S, latest_run completed/fixture
- `GET /api/v1/books/999999/whole-book/prepare` → 404 WHOLE_BOOK_BOOK_NOT_FOUND
- `GET /api/v1/whole-book/runs/1/overview` → completed, 9 claims, fixture
- REAL PROVIDER CALLS: 0
- Formal AppData DB not used by Wave D stack
