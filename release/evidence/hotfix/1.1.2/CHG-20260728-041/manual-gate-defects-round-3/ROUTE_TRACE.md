# ROUTE TRACE — CHG-041 Round 3

## Observed URL
`/books/1?chapter=1&analysisRun=1&view=result&tab=reader-journey`
Missing: `journeyRun`

## Confirm+Start handler
`SceneBoundaryReviewPanel.confirmMutation.onSuccess`
→ `onConfirmed({ journeyStarted, journeyRunId: result.journey_run_id, revisionId })`

## BookRoutePage.onConfirmed
When `journeyStarted`:
```
params.set("view","result")
params.set("tab","reader-journey")
params.set("journeyRun", String(journeyRunId))  // only if truthy
```

## Binding after navigation (BUG)
`boundJourneyRunId` =
`progress.run?.journey_run_id ?? appliedJourneyMetaRef.journeyId ?? journey.data?.journey_run_id`

**Never reads** `searchParams.get("journeyRun")`.

## Journey query
`GET /api/v1/analysis-runs/{analysisRunId}/reader-journey`
Orders by `ReaderJourneyRun.id DESC` — returns latest for analysis run (here id=2), but:
- Does not filter by confirmed revision
- Serialization for failed/incomplete journeys spam-errors (visualization) → query error → gate falls through to "尚未生成"

## Classification
- A: No snake/camel mismatch on confirm response (`journey_run_id` OK)
- B: Navigation helper can set journeyRun, but consumer ignores it
- D/E: Several `setSearchParams` rebuilds focus on analysisRun; auto-open journey effect does not re-set journeyRun from binding
- G: Primary selection is analysisRun-scoped latest journey, not URL/revision selector
