# CHG-20260731-025 Verification

## Root cause

Right-rail `onContinueReaderJourney` called `resumeJourneyAnalysis()` whenever `journeyRunId != null`. Succeeded journeys always have an id, so the CTA never navigated (silent no-op). Top nav used `setResultTab("journey")` / `openReaderJourneyResult()`.

## Fix

Canonical `openReaderJourneyResult()` shared by top nav, right-rail succeeded CTA, banner, and shell `view_results`.

## Tests

| Suite | Result |
|-------|--------|
| `vitest` `BookRoutePage.journeyNav.test.tsx` (incl. CHG-025) | PASS 7/7 |
| Playwright `e2e/chg025_right_rail_journey_cta.spec.ts` | PASS 1/1 |
| `tsc -p tsconfig.app.json --noEmit` | 0 new errors |
| Manual gate `MG-CHG-20260731-025-RIGHT-RAIL-CTA` | PASSED |

## Side effects (automated + manual)

Resume / recover / create journey / new runs / new tasks: 0 on CTA click paths.

## RC.6

Installed acceptance for RC.6 remains **FAILED** (same right-rail defect on packaged train). Correction note: `release/evidence/1.1.2-rc.6/INSTALLED_EXECUTION_ACCEPTANCE_CORRECTION.md`. RC.6 installer archive must not be rebuilt or overwritten.

## Status

**verified** for inclusion in 1.1.2 (next RC: 1.1.2-rc.7). No RC.7 build in this step.
