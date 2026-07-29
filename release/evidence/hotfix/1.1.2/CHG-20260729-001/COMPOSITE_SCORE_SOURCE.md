# COMPOSITE SCORE SOURCE — CHG-20260729-001

**Change:** CHG-20260729-001  
**Branch:** `fix/1.1.2-reader-journey-dimension-insights`  
**Status:** frozen for this hotfix (no formula redesign)

## COMPOSITE SCORE SOURCE

| Field | Value |
|-------|-------|
| **COMPOSITE SCORE SOURCE** | `reading_momentum` |
| **Presentation alias** | `overall_reading_score` (= `reading_momentum` when present) |
| **UI label (frozen)** | `综合阅读` |
| **COMPOSITE SCORE VERSION** | `formula_v2` / existing `compute_reading_momentum` (unchanged) |
| **INPUT DIMENSIONS** | `plot_progress`, `reading_tension`, `pacing_fit?`, `hook_payoff_fit?`, minus clarity / cognitive / redundancy penalties |
| **NULL POLICY** | missing → legacy `engagement_score` → `curiosity`; still null → UI「无法判断」 / phase card「综合阅读 —」 |

## Must not use as composite display

- `reading_tension` alone
- `plot_progression_score` alone
- `pacing_speed` alone

## Relationship to 阅读张力

V2 `reading_momentum` **includes** `reading_tension` as one weighted input (~25%).  
The composite **curve and phase card** bind to `reading_momentum`; the reading_tension lens remains independent.

## Evidence

- Pre-algorithm audit: `DATA_AND_UI_AUDIT.md`
- Backend derivation: `apps/api/app/services/reader_journey_v2_derivation.py` (`compute_reading_momentum`)
- Frontend binding: `apps/desktop/src/components/readerJourney/lensMetricBinding.ts` (`fieldKey: reading_momentum`, `labelZh: 综合阅读`)
