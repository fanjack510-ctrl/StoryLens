# TARGETED_TESTS — CHG-20260807-054

## Wiring suite

`apps/api/tests/test_whole_book_chg054_real_provider_path.py`

| # | Case | Result |
|---|---|---|
| 1 | Real ON + provider valid → no CAPABILITY_DISABLED | PASS |
| 2 | Real OFF → REAL_PROVIDER_DISABLED | PASS |
| 3 | Provider unavailable → explicit error | PASS |
| 4 | Consent invalid → reject | PASS |
| 5 | Revision changed → reject old consent | PASS |
| 6/9 | Formal create four modules same run/snapshot | PASS |
| 7 | Fixture preview independent when real ON | PASS |
| 8 | Fake/fixture path unchanged (via regressions) | PASS |
| 10 | Resume completed units not duplicated | PASS |

Command: `pytest apps/api/tests/test_whole_book_chg054_real_provider_path.py -q` → **8 passed**

## Directed regressions

- `test_whole_book_wb17_free_product_api.py`
- `test_whole_book_wb221_e2e_stabilization.py`
- `test_whole_book_wb05_provider_orch.py`
- `test_whole_book_prepare_route_alias_chg030.py`
- `test_whole_book_wb16_overview_pipeline.py`
- `test_whole_book_wb21_structure_stages_a_o.py`
- `test_whole_book_wb22_chapter_functions_a_y.py`
- `test_whole_book_wb14_extraction.py`

Result: **all PASS** (no Public full pytest)
