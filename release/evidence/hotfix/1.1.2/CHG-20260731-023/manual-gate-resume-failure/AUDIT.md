# CHG-023 Manual Gate — Resume Failure Audit

Frozen at HEAD `9978c61b69b264962babfcea862f701a3839913f`.

## Real state (AR2 / JR2)

| Field | Value |
|------|-------|
| analysis_run.status | succeeded |
| analysis_run.effective_status | journey_failed |
| analysis_run.journey_status | failed |
| analysis_run.journey_retryable | true |
| journey_run.status | **failed** |
| journey result exists | **NO** (`visualization=null`, `journey_result=null`) |
| task / analysis status | AnalysisRun succeeded; Journey failed |
| current_stage | reader_journey_scene_profiles |
| failure_code | PIPELINE_UNEXPECTED_ERROR |
| retryable | true |
| recovery_recommended | recovery plan `paused_recoverable` / resume_stage reader_journey (stale vs failed) |
| can_resume | progress `retryable=true`, `recovery_safe=true` |
| active task | no (completed_at set) |
| checkpoint | completed_scene_count=0 after failed resume; remaining 3 scenes |

## UI source (defect)

| Surface | Shown | Source |
|---------|-------|--------|
| Main pane | 阅读旅程已中断 / 继续分析 | `resolveJourneyPageState` maps `failed`+`retryable=true` → `interrupted` **before** `terminal_failed` |
| Right rail / task center | 阅读旅程生成失败 | composition / lifecycle `journey_failed` |
| Same Journey Run? | Yes — all bound to journey_run_id=2 / analysis_run_id=2 |

Root class: **FAILED_PRESENTED_AS_INTERRUPTED** (retryable must not rewrite failure to interruption).
