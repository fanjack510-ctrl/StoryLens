# CHG-20260731-025 Forensics — 查看阅读旅程

Date: 2026-07-31  
Gate failure: RC.6 installed — right-rail CTA no-op

## Literal search: `查看阅读旅程`

| Location | Component | Role |
|----------|-----------|------|
| `ChapterAnalysisProgressPanel.tsx` | `ChapterAnalysisProgressPanel` | Right-rail success card primary CTA (`data-testid=chapter-analysis-open-journey`) |
| `BookRoutePage.tsx` | complete banner | `banner-open-result` |
| `BookRoutePage.tsx` | shell primary action label | `shell-view-reading-journey` (when `view_results`) |
| `resolveSceneJourneyGate.ts` / `SceneBoundaryReviewPanel.tsx` | gate labels | boundary flow (not this defect) |

## Right-rail button (defect surface)

1. **File:** `apps/desktop/src/components/chapterAnalysis/ChapterAnalysisProgressPanel.tsx`
2. **Component:** `ChapterAnalysisProgressPanel`
3. **Props (relevant):** `onContinueReaderJourney?: () => void`, `preferJourneyResultCta?: boolean`, `presentationStatusTitle/Description`
4. **onClick:** `onClick={onContinueReaderJourney}` (no href)
5. **disabled:** none on the success CTA
6. **pointer-events:none:** none on `.chapter-analysis-success-actions` / CTA
7. **Overlay:** no transparent mask on the success card; panel is normal aside
8. **Console:** N/A in unit forensics; click invoked handler (no React error expected)
9. **URL before fix:** unchanged (stay on `view=progress`)
10. **Network before fix:** may POST journey `/resume` or silently return inside `resumeJourneyAnalysis` when already terminal — **not** result navigation
11. **Top「阅读旅程」:** `WorkspaceViewSwitcher` → `onChange("journey")` → `setResultTab("journey","user")` / `openReaderJourneyResult()`
12. **Difference:** top navigates; right rail (before) called `resumeJourneyAnalysis()` whenever `journeyRunId != null`

## Root cause

`BookRoutePage` wired:

```ts
onContinueReaderJourney={() => {
  const targetJourneyId = selectedJourneyRunId ?? journeyRunId;
  if (targetJourneyId != null) {
    resumeJourneyAnalysis(); // BUG for succeeded+result
    return;
  }
  setResultTab("journey", "user");
}}
```

Succeeded journeys always have a `journeyRunId`, so the CTA never reached navigation. Resume on a terminal succeeded run is a silent no-op / non-navigation — matches “点击完全无反应” while top nav still works.

## Fix

Canonical `openReaderJourneyResult()` (= `setResultTab("journey","user")`) shared by top nav, right-rail succeeded CTA, banner, and shell `view_results` primary.
