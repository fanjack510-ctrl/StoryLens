# CHG-20260809-073 Evidence

## Architecture Before
- Whole-Book V2 still leaned on shared primitives that could carry full chapter text into final synthesis units.
- Window sizing used fixed chapter counts (legacy `build_windows(size=20)`).
- Cost/token planning was monolithic and did not enforce CONTEXT_SAFE gates.
- Intermediate assets / hierarchical consolidation / resume-by-window were incomplete for long books (e.g. 1299 chapters).

## Architecture After
SOURCE CHAPTERS
→ capacity-based WINDOW PLANNER (context limit − system/schema/output/repair/safety)
→ WINDOW EXTRACTION (structured primitives only)
→ INTERMEDIATE ASSETS (story/character/relationship/protagonist/suspense/pacing/chapter_function)
→ GROUP + TOPIC CONSOLIDATION (bounded hierarchical merge)
→ FINAL TOPIC SYNTHESIS (intermediates only; never raw full book)
→ WholeBookAnalysisV2
→ Formal Whole-Book V2 UI

## Product Code
- `apps/api/app/narrative_core/whole_book_v2/pipeline.py` (new)
- `apps/api/app/narrative_core/whole_book_v2/contracts.py`
- `apps/api/app/narrative_core/whole_book_v2/engine.py`
- `apps/api/app/narrative_core/whole_book_v2/provider_engine.py`
- `apps/api/app/narrative_core/whole_book_v2/repository.py`
- Frontend formal contracts/progress wiring (Mock route retained)

## 1299 Dry Run (deterministic, REAL PROVIDER CALLS = 0)
See `1299-dry-run.json`:
- WINDOW COUNT: 13
- ESTIMATED PROVIDER CALLS: 31
- MAX REQUEST TOKENS: 109884
- PROVIDER CONTEXT LIMIT: 128000
- SAFETY MARGIN: 8000
- CONTEXT_SAFE: YES
- NO RAW FULL BOOK FINAL REQUEST: YES

## Tests
- Backend targeted: `test_whole_book_v2_hierarchical_pipeline.py` + engine + provider_engine → 32 passed
- Frontend targeted: adapter + mock → 9 passed
- Typecheck: passed
- Production frontend build: passed

## Compatibility
- No formal user DB writes
- Intermediate assets persisted via existing `WholeBookCheckpoint` JSON
- CHG-071 / CHG-072 WIP preserved (commit deferred)
