# REFRESH_RENDER_TRACE — CHG-041 Round 6

## URL

`/books/1?chapter=1&analysisRun=1&view=result&journeyRun=2&tab=reader-journey`

## Chain

| Step | Value |
|------|-------|
| Component | `BookRoutePage` |
| Hook | `useQuery` key `["reader-journey", bookId, chapterId, analysisRunId, journeyRunFromUrl]` |
| Query Key uses journeyRun | Yes (when URL present) |
| Endpoint (pre-fix HEAD) | `GET /api/v1/analysis-runs/{analysisRun}/reader-journey?journey_run_id=` OR by-id (uncommitted partial) |
| Request URL (intended) | `GET /api/v1/reader-journey-runs/2?book_id=1&chapter_id=1` |
| HTTP Status | 200 |
| Response safe summary | `status=succeeded`, `result_status=current`, `scene_profiles=11`, `visualization=null` |
| Repository filter | PK load by `journey_run_id`; no analysisRun required for by-id |
| Uses journeyRun | Intended yes |
| analysisRun overrides journeyRun | No on by-id path; analysis-run GET can prefer latest non-superseded if journeyRun omitted |
| Filters superseded | Analysis-run latest path excludes superseded; by-id does not |
| Requires result_status=current | No on by-id |
| Requires current confirmed revision match | Visualization uses `load_revision_scenes` (current confirmed); profile set polluted → count mismatch |

## UI effect

```ts
hasJourney = status === "succeeded" && visualization
```

`visualization=null` → `mainContentState=unavailable` → WorkspaceJourneyPane:

**当前章节尚未生成阅读旅程**

Even though run 2 exists and succeeded.
