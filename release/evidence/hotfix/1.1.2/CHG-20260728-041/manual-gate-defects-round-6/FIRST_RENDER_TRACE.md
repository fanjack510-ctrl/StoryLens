# FIRST_RENDER_TRACE — CHG-041 Round 6

## Flow

Confirm+Start API → BackgroundTasks `execute_reader_journey` → V2 stubs for included scenes → finalize → GET `/reader-journey-runs/{id}` → BookRoutePage `useQuery` → WorkspaceJourneyPane

## Confirm API Response

- Returns queued `journey_run_id` + revision confirm payload
- Does **not** embed final visualization / chapter result
- Does **not** seed React Query journey cache with result payload

## First visible Journey source

| Candidate | Used? |
|-----------|-------|
| A. Confirm API Response | No (queued only) |
| B. Background Task memory result | No (not returned to browser) |
| C. React Query Mutation Cache | No (confirm mutation does not write journey query) |
| D. Optimistic Update | No |
| E. Database GET API | **Yes** (invalidate + `readerJourneyById` / progress poll) |
| F. Other | Progress card during running |

## Race explaining “first paint works”

During V2 execute, stubs for scenes `[10..15]` exist briefly with `profiles==6` matching confirmed revision scenes. A GET in that window can build `visualization`. Finalize then reloads stubs via `_load_v2_profiles_from_stubs` and persists **11** profiles (bleed from run 1 scenes 5–9). Subsequent GET returns `status=succeeded` but `visualization=null`.

`FIRST_RENDER_FROM_CACHE_ONLY=false` (first paint uses GET/progress; not mutation cache).  
`FIRST_RENDER_DURABLE=false` (post-finalize payload is polluted / viz rebuild fails).
