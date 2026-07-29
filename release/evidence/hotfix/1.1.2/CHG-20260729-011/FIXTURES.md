# Fixtures A–E — CHG-20260729-011

Isolated DB: `%TEMP%\storylens-mg-chg011-workflow-consistency\database\storylens-mg-chg011.db`  
Fake Provider ON · Real Provider OFF · Formal AppData DB NOT USED

## Fixture A — Revision contamination (22 → 6)

- **Chapter 1**, analysis run **2**
- DB retains **22** scene rows on run 2 (superseded 16 + confirmed 6)
- Ordinary APIs (`/analysis-runs/2/scenes`, `/results`) return **6** confirmed-revision scenes only
- No duplicate S01/S02 ordinals in API response

Covered by: `test_workflow_consistency_chg011.py` + HTTP E2E case `A_revision_contamination`

## Fixture B — Interrupted journey 1/6, can resume

- **Chapter 2**, journey run **2**
- Status: `scene_profiles_partial` (UI: interrupted, **not** running)
- Progress: **1 / 6**, `retryable=true`, `root_error_code=JOURNEY_INTERRUPTED`
- One valid `SceneReaderJourneyProfile` for scene 1

Covered by: HTTP E2E case `B_interrupted_not_running` + `chapterAnalysisPresentation.test.ts` (interrupted excludes running)

## Fixture C — Confirm flow AI 17 → manual 6 → awaiting

- **Chapter 3**, analysis run **4**
- Model revision: **17** scenes (confirmed AI partition)
- Draft revision: **6** scenes (saved, not confirmed)
- `awaiting_confirmation=true` on `GET /chapters/3/scene-boundaries`
- Manual step: open scene-boundary-review → adjust/confirm → start journey binds new revision

Covered by: HTTP E2E case `C_awaiting_confirmation` + `SceneBoundaryReviewPanel.chg041.test.tsx`

## Fixture D — Hook rich presentation (LIVE)

- **Chapter 6**, analysis run **7**, journey run **5** (succeeded)
- Confirmed revision **9**, **6** scenes
- Persisted profiles / phases / summary encode the same reader questions as `chg005FixtureBReliableHooks`
- Seed: `seed_mg_chg011_hook_rich.py` (no Provider calls; does not wipe A–E)
- URL: http://127.0.0.1:1426/books/1?chapter=6&analysisRun=7&journeyRun=5&view=result&tab=reader-journey&lens=hook_payoff
- Precheck: `HOOK_RICH_PRESENTATION_PRECHECK.json` (verdict=1, cards=2, trajectory raise/deepen/respond/carry)

Also covered by vitest Fixture B / HookPayoffTimeline layout tests.

## Fixture E — Hook empty / uncertain

- **Chapter 5**, journey run **4** (Fake journey succeeded)
- `narrative_loops` present but FE presentation mode **uncertain/none** (smoke-fake noise)
- URL: `lens=hook_payoff` on succeeded journey

Covered by: HTTP E2E case `E_hook_empty_or_uncertain` + vitest Fixture A (`chg005FixtureANoReliableHooks`)

## Additional MG cases (same book)

| Case | Chapter | Journey | Status |
|------|---------|---------|--------|
| Running 2/6 | 4 | 3 | `scene_profiles_running` |
| Succeeded 6/6 | 5 | 4 | `succeeded` + visualization |

**Note:** API startup orphan recovery marks worker-bound journeys interrupted. After boot, run `refresh_mg_after_api_boot.py` to restore B (interrupted) and Running fixtures.
