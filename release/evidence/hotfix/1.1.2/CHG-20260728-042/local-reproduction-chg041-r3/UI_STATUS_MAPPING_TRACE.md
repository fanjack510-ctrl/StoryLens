# UI STATUS MAPPING TRACE — Journey Run 2

## Observed

| Region | Copy |
|--------|------|
| Main | 阅读旅程生成失败 |
| Sidebar | 分析已暂停 |

## Sources

### Main — 阅读旅程生成失败

| Field | Value |
|-------|-------|
| Component | `BookRoutePage` → `StateView` `data-testid=journey-failed` |
| Hook | `useQuery` reader-journey + `resolveJourneyPageState` |
| Endpoint | `GET /api/v1/analysis-runs/{id}/reader-journey?journey_run_id=2` (and/or by-id) |
| Input status | Journey `failed` (`retryable=0`) |
| Mapper | `resolveJourneyPageState` → `terminal_failed` |
| Output | title「阅读旅程生成失败」 |

### Sidebar — 分析已暂停

| Field | Value |
|-------|-------|
| Component | `ChapterAnalysisProgressPanel` |
| Hook | same page; `uiState` prop from `BookRoutePage` |
| Endpoint | Analysis progress for run 1 **plus** journey-selected overrides |
| Input status | Journey failed/interrupted branch forces `uiState="partial"` |
| Mapper | `uiStateLabel("partial")` / `currentWorkLabel` →「分析已暂停」 |
| Code | `BookRoutePage.tsx`: `showJourneyTerminalFailed \|\| showJourneyInterrupted` → `"partial"` |

## Answers

1. Same Journey Run intended via selector/URL `journeyRun=2` for main; sidebar
   still renders AnalysisRun shell with **overridden** uiState from journey flags.
2. Main status: Journey `failed` → terminal failed copy.
3. Sidebar status label: `partial` → paused copy (not literal Journey `paused`).
4. Yes — failed mapped to paused **label** via `partial`.
5. Recovery capability not required; mapping is unconditional on failed/interrupted.
6. AnalysisRun itself is `succeeded` (scene pipeline); paused text is **not** from
   an AnalysisRun `paused` column (FIELD_NOT_PRESENT).

## Root-cause category

**A. FAILED_MAPPED_TO_PAUSED** (Round-3 sidebar uiState override)

Secondary: sidebar chrome still AnalysisRun-oriented (**B** partial).
