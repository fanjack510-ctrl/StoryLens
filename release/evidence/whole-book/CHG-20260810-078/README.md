# CHG-20260810-078 Evidence

## Root cause (source)
- Formal route `/books/:bookId/whole-book` previously rendered legacy `WholeBookFreeProductPage`.
- Approved V2 IA lived primarily under `/dev/whole-book-v2-mock`.
- Formal Free create executed `execute_minimal_pipeline_v1` (not hierarchical V2).

## Formal route (screenshots)
See `ROUTE.txt` and `screenshots/01-overview.png` … `07-assessment.png`.
Route: `/books/42/whole-book` (formal product; not `/dev/whole-book-v2-mock`).

## Engine
New formal Free runs: `execute_hierarchical_v2_pipeline_v1` (`whole_book_v2_hierarchical` / `2.1.0`).
`execute_minimal_pipeline_v1` is not used for new formal V2 runs.

## REAL PROVIDER CALLS
0 (deterministic / mocked gateway only).
