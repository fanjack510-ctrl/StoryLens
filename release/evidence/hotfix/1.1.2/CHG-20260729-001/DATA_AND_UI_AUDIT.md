# DATA_AND_UI_AUDIT — CHG-20260729-001

**Status:** pre-algorithm audit (no scoring formula redesign)  
**Public base:** `15d746e2815f11f9ddebaa88863968e46c75f8f9` (`hotfix/1.1.2` after CHG-041 integrate)  
**Branch:** `fix/1.1.2-reader-journey-dimension-insights`  
**Workspace:** `D:\Dstorylens-wt-hotfix-1.1.2-reader-journey-insights`

## Data chain

```
Fake / Model Result
  → Scene Profile (V1 or V2 artifact)
  → Reader Journey Result (+ deterministic_statistics.v2_scene_scores)
  → build_reader_journey_visualization
  → API ReaderJourneyResultResponse.visualization
  → analysisApi.readerJourney / readerJourneyById
  → ReaderJourneyWorkspace
  → observationLenses / lensMetricBinding
  → CanonicalJourneyChart + JourneySceneDetailPanel
```

## 1. Score field per dimension

| Label | Lens ID | Primary field | Notes |
|-------|---------|---------------|-------|
| 综合阅读 | `composite` | `reading_momentum` | Legacy fallback: `engagement.engagement_score` → `curiosity` |
| 剧情推进 | `plot_progress` | `plot_progress` | Legacy: avg(information_gain, curiosity, tension) |
| 阅读张力 | `reading_tension` | `reading_tension` | Legacy: weighted curiosity/tension/emotion |
| 情绪强度 | `emotion` | `arousal` (start/end avg) | |
| 钩子回收 | `hook_payoff` | `hook` + `payoff` | Paired series |
| 节奏速度 | `pacing` | `pacing_speed` (+ `pacing_fit`) | Legacy fallback may use `tension` |

Sources: `apps/desktop/src/components/readerJourney/observationLenses.ts`, `lensMetricBinding.ts`, `apps/api/app/services/reader_journey_v2_derivation.py`.

## 2. 综合阅读 Score

**Primary:** `reading_momentum` (V2 `compute_reading_momentum`).  
**No separate** `overall_reading_score` / `comprehensive_reading_score` wire field today.  
**Contract equivalence:** `reading_momentum` **is** the composite / overall reading score for V2.

## 3. Does 综合阅读 reuse reading_tension?

**Display: NO.** Composite lens `primaryKey` is `reading_momentum`, not `reading_tension`.  
**Formula: by design** V2 momentum includes reading_tension as one weighted input (~25%), plus plot_progress / pacing_fit / hook_payoff_fit − penalties.  
**Not a UI bug;** do not redesign weights this change.

## 4. Stage card score source

`phaseAverageForLens` → mean of the same lens series as the chart (`buildLensChartLines`).  
Fallback: `phase.average_engagement` (V2 overrides engagement with momentum).  
**Issue for this CHG:** composite phase label currently uses `readingMomentumLabelZh` →「阅读动力」, not「综合阅读」. Spec requires「综合阅读 N」.

## 5. Curve point score source

`CanonicalJourneyChart` → `buildLensChartLines` → `nodeScoreRecord(node)[field]`.  
Not raw `curve_series` (except partial arousal merge for emotion).  
V2 scores patched onto nodes in `_apply_v2_presentation_overrides`.

## 6. Right detail fields (current)

`JourneySceneDetailPanel` tabs:

1. 节点结论 — `scene_value_summary`, diagnosis, `buildSceneNarrative`, fixed bars `reading_momentum`/`curiosity`/`tension`
2. 为什么
3. 前后承接
4. 正文证据
5. 分析信息

Lens mainly affects caption + hook-payoff extras; overview prose is mostly shared.

## 7. Shared detail across six dimensions?

**YES.** Same `scene_value_summary` / narrative / score bars for all lenses. Hook-payoff adds lifecycle sections.

## 8. Generated but unused per-dimension text?

**YES.**

- Per-metric `ScoredLevelField.rationale` (Fake emits; UI unused)
- `SceneDiagnosisV2.diagnostic_evidence.notes`
- API `v2_scene_diagnoses` largely unused vs node diagnosis codes
- **No** `dimension_insights` / six independent insight fields yet

## 9. Historical Journey compatibility

| Run | Can open? | Native six insights? |
|-----|-----------|----------------------|
| V2 with `v2_scene_scores` | Yes | No until this CHG |
| Legacy v1.3 | Yes via client score fallbacks | No; derive at read time |

Enough for **deterministic legacy fallback** from `scene_value_summary`, scores, hooks/payoffs, diagnoses — without DB overwrite.  
No migration required if insights live in JSON artifact / presentation enrich.

## 10. Garbled text on result page?

**Still possible** if persisted UTF-8 junk passes validation.  
Known Fake risk: `Scene{n}推进：…` style internal summaries (`chapter_analysis_smoke_fake_transport.py`).  
No display-layer mojibake filter on journey strings.

## COMPOSITE SCORE SOURCE (freeze for this CHG)

| Field | Value |
|-------|-------|
| COMPOSITE SCORE SOURCE | `reading_momentum` (alias presentation: overall reading / 综合阅读) |
| COMPOSITE SCORE VERSION | formula_v2 / existing `compute_reading_momentum` (unchanged) |
| INPUT DIMENSIONS | plot_progress, reading_tension, pacing_fit?, hook_payoff_fit?, −clarity/cognitive/redundancy penalties |
| NULL POLICY | missing → legacy engagement_score → curiosity; still null → UI「无法判断」 / stage「综合阅读 —」 |

**Must not use:** `reading_tension_score` / `plot_progression_score` / `pacing_score` alone as composite display.

## Implementation implications (next, not done in audit)

1. Keep six Chinese dimension names unchanged.
2. Fix composite UI labels to「综合阅读」; update one-line explanation copy.
3. Scene point fit status for composite: 合适 / 偏弱 / 偏强 / 无法判断 (replace 表现有效 / 未表现明显异常 style on curve band where applicable).
4. Add six `dimension_insights` fields; Fake generates distinct texts once per scene.
5. Read-time legacy derive + `insight_source`: generated | derived_legacy | unavailable.
6. Simplify normal right panel; developer mode collapsible 技术详情.
7. Do not call real Provider; no formal DB writes; no Build/Push.
