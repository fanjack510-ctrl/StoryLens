# CTA CONFLICT TRACE — Round 3

Simultaneously observed:
1. **查看详情** — interrupted StateView primary (`/tasks?run_id=1`)
2. **重新生成** — interrupted StateView secondary (resume/recover)
3. **生成阅读旅程** — `resolveSceneJourneyGate` `confirmed_no_journey` primary (`openSceneBoundaryReview`)

Cause: `showJourneyInterrupted` true AND gate `showGate` true because gate conditions allow `failed`/`confirmed_no_journey` while interrupted banner also mounts (ordering / dual flags).

Gate show condition excludes `showJourneyActive` but **does not** exclude `showJourneyInterrupted` / `showJourneyTerminalFailed` in all paths — actually code says:
```
!showJourneyActive && !(gate.kind === "ready" && hasJourney)
```
It does NOT exclude interrupted → duplicate CTAs.

Fix: single CTA resolver from unified journey selection; never mount gate when interrupted/failed/active already rendered.
