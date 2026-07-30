# CHG-20260730-018 — Active Journey vs Stale Recovery Audit

**Change:** CHG-20260730-018  
**Base HEAD:** `23cb98783c8cecba280c7fab9fb1b75112e724cf`  
**Scope:** Same AnalysisRun / current Journey only — do not compare progress across tasks.

## Trace (same task)

```
Journey create → Worker claim → journey_starting → journey_running
→ page poll (reader-journey + progress)
→ Recovery Plan GET /analysis-runs/{id}/recovery-plan
→ UnifiedAnalysisRecoveryCard render
```

## Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Center「正在生成阅读旅程」reads | `resolveJourneyPageState` / `journeyPageViewWithProgress === "active"` + `ReaderJourneyProgressCard` (GET progress / journey status). Also sidebar label via `mapReaderJourneyStatusToUi` when status ∈ running set. |
| 2 | Recovery Card「分析已暂停」reads | `UnifiedAnalysisRecoveryCard` title default when `mapRunToUiState(run)` is not failed; plan from `analysisRecoveryApi.recoveryPlan(run.id)` with `user_status=paused_recoverable`. Hosted by `ChapterAnalysisProgressPanel` when `shouldShowUnifiedRecovery(uiState)`, and/or journey pane when `showJourneyAwaiting`. |
| 3 | Same `analysis_run_id`? | Yes — both bound to shell `progress.run.id` / URL `analysisRun`. |
| 4 | Same `journey_run_id`? | **Not guaranteed.** Recovery plan uses `_journey_for_run` which **prefers `find_recoverable_journey_run`** (interrupted / partial) over the newest active row. Center may bind URL / progress journey. |
| 5 | Stale Recovery Plan after re-run? | Plan is computed live (no chapter-level cache store), but **query key is only `["analysis-recovery-plan", run.id]`** — React Query can keep a prior `paused_recoverable` payload for up to `refetchInterval` (4s) while journey is already active. |
| 6 | Cache key chapter_id only? | **No** — frontend key is `run.id`. Backend has no durable chapter-keyed recovery cache. |
| 7 | `status_version` invalidate plan? | Recovery plan response does **not** key off `status_version`; frontend does not invalidate on journey status change. |
| 8 | Worker claim clears paused/interrupted? | Claim moves journey `starting/queued → running`; does **not** rewrite Recovery Plan semantics. Old interrupted sibling rows can still be selected by `_journey_for_run`. |
| 9 | Resume success updates `can_resume`? | Presentation `can_resume` follows `journey_interrupted`. Recovery plan `recoverable` stays true while `journey_needed` / pause_reason set — including when status is `starting` (bug). |
| 10 | Frontend unconditional Recovery Card while active? | **Yes risk:** `shouldShowUnifiedRecovery` includes `awaiting_reader_journey_start`. If composition lags while progress view is already `active`, sidebar still mounts the card. Card itself does not hide when `plan.user_status === "running"`. |
| 11 | 「修复并继续」on running task? | Card calls `analysisRecoveryApi.recover` without checking live journey active; backend may re-enter recovery while worker already claimed. |

## Root causes (product)

1. **Backend `journey_needed`** treats statuses outside `{succeeded, queued, scene_profiles_running, chapter_synthesis_running}` as needing recovery — **`starting` / `running` / `pending` incorrectly keep `pause_reason=awaiting_reader_journey` → `user_status=paused_recoverable`.**
2. **`_journey_for_run` prefers recoverable interrupted journey** over a newer active journey on the same AnalysisRun.
3. **Frontend** shows unified recovery for `awaiting_reader_journey_start` even when the current journey page view is already active; card does not self-suppress on `user_status=running`.

## Fix direction

- Treat Journey Active = `journey_starting | journey_running | resuming | queued | starting | running | scene_profiles_running | chapter_synthesis_running | …`
- Recovery plan: active journey ⇒ `user_status=running`, clear awaiting-journey pause/blockers; prefer active journey row for plan binding.
- Frontend: never show Recovery Card / recover CTA while current journey is active; invalidate recovery-plan query on active transition.

## Non-goals

- Scene algorithm / journey algorithm / prompts  
- Cross-task progress comparison  
- Tasks-center progress math / revision logic  
- Real provider / formal DB / Build / Push / Tag / Release / VERSION
