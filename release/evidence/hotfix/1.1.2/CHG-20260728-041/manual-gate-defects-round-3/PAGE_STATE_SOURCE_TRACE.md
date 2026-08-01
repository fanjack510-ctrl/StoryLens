# PAGE STATE SOURCE TRACE — Round 3

| UI | Component | Hook / Logic | Endpoint | Query Key | Input ID | Run ID (failure) | Fallback |
|----|-----------|--------------|----------|-----------|----------|------------------|----------|
| 主区「阅读旅程已中断」 | `BookRoutePage` StateView `journey-interrupted` | `resolveJourneyPageState` → `showJourneyInterrupted` | GET analysis-runs/1/reader-journey (+ progress) | `["reader-journey", book, chapter, analysisRun]` | analysisRun=1 | journey 2 failed mapped as interrupted when retryable | parent `effective_status` / progress |
| 下方「尚未生成阅读旅程」 | `resolveSceneJourneyGate` StateView | Gate when journey GET empty/error or status not matched | scene-boundaries overview + journey query | `["scene-boundaries", chapter]` + reader-journey | confirmed revision 2 | treats as no journey when `journeyRev`/status incomplete | opens scene review CTA |
| 右侧「正在生成」 | Progress inspector / `mapAnalysisUiState` | `progress.uiState` / composition | GET analysis-runs/1/progress | progress hook | analysisRun=1 | may show journey_processing from marker before fail settles | compositionUiState |
| 右侧 1/3 | Progress / journey progress card | scene counts | progress or journey progress | progress | analysisRun or journey 2 | journey2 total=3 completed=0 | — |
| 右侧「分析已暂停」 | Progress display | `runProgressDisplay` / effective_status | analysis progress | progress | analysisRun=1 | analysis run marker journey_failed | — |
| 已用时间 ~1h | Progress elapsed | AnalysisRun.started_at (fixture seed ~13:28) | progress | progress | analysisRun=1 | **NOT** journey2.started_at (null) | falls back to analysis run clock |
| 查看详情 | interrupted StateView | navigate `/tasks?run_id=${analysisRunId}` | — | — | analysisRun=1 | uses analysis run | — |
| 重新生成 | interrupted secondary | resumeJourney / recover | resume or recovery | — | journeyRunId OR analysisRun | dual path | — |
| 生成阅读旅程 | gate primary | `openSceneBoundaryReview` | — | — | — | ignores existing failed journey 2 | — |

## Verdict
Main / gate / sidebar use **different** selectors (analysisRun progress vs journey GET vs gate). No shared `resolve_current_reader_journey`.
