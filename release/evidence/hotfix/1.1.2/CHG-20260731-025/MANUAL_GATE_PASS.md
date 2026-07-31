# MANUAL GATE PASS — CHG-20260731-025

Gate: `MG-CHG-20260731-025-RIGHT-RAIL-CTA`  
Change: `CHG-20260731-025`  
Date: 2026-07-31  
Hotfix base before fix: `ed6a307e550e2f1f63a97722dcedfe8a1aa2ddc4`

## Result

**MG-CHG-20260731-025 RIGHT RAIL CTA ACCEPTANCE：PASSED**

## Checklist

| Check | Result |
|-------|--------|
| 右侧「查看阅读旅程」单击进入结果 | PASS |
| 顶部「阅读旅程」单击进入结果 | PASS |
| 两个入口目标一致 | PASS |
| Analysis Run 保持不变 | PASS |
| Journey Run 保持不变 | PASS |
| 刷新后结果正常 | PASS |
| Resume Request | 0 |
| Analysis Recover Request | 0 |
| 新 Task | 0 |
| 新 Analysis Run | 0 |
| 新 Journey Run | 0 |

## Environment (source preview)

- Frontend: `http://127.0.0.1:1480`
- API: `http://127.0.0.1:18057`
- Manual URL: `http://127.0.0.1:1480/books/1?chapter=1&analysisRun=1&journeyRun=1&view=progress`
- Isolated DB preserved (not reseeded during restore)

## Root cause (confirmed)

Right-rail completed CTA called `resumeJourneyAnalysis()` whenever `journeyRunId` was present; succeeded journeys always have an id, so the click was a silent no-op. Fix shares `openReaderJourneyResult()` with top nav.

## Related RC.6 note

RC.6 installed acceptance remains **FAILED** (right-rail CTA defect on packaged train). This gate verifies the source fix for inclusion in **1.1.2-rc.7** — not a rebuild or overwrite of RC.6.
