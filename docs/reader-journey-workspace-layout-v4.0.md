# Reader Journey Workspace Layout v4.0

**Phase:** 1D-C1-UI-05  
**Baseline:** Reader Journey UI Final v4.0  
**Parent:** Reader Journey Visualization v3.0 (`READER_JOURNEY_VISUALIZATION_V3_0_HUMAN_UAT_FAILED`)  
**Scope:** Whole-workspace layout refactor — Source | Main | Inspector — for every book / chapter / ReaderJourneyRun

## Human UAT failure (v3.0) — root cause

1. Vertical tool rail used single-char labels（指/全/P/详/出）with 56px width + ellipsis.
2. Inspector lived in a vertical `JourneyResizableSplit` under the chart, competing for the same column.
3. System nav + SourcePane + tool rail formed three left chrome layers.
4. Multiple vertical scroll owners (App main, Source, Workspace, Inspector).
5. Local CSS patches could not establish a unified responsive architecture.

Audit: `audits/single-chapter-pipeline/reader-journey-layout-audit-v4.0.json`

## Architecture

```
grid-template-columns:
  var(--source-pane-width)   /* 300 / 270 / 0 */
  minmax(720px, 1fr)
  var(--inspector-pane-width) /* 360 / 0 */
```

| Breakpoint | Layout |
|------------|--------|
| ≥ 1440px | Source + Main + right Inspector dock |
| 1100–1439px | Source + Main; Inspector bottom dock (pushes content) |
| < 1100px | In-page tabs: 正文 / 旅程 / 详情 |

Inspector is **never** `position:absolute/fixed` over the plot.

## Chart card order

1. Horizontal toolbar（当前指标 / 适应全部 / 当前Phase / 查看详情 / 导出PNG / 更多设置）
2. Phase navigation（horizontal scroll only）
3. Plot（v3.0 floors preserved）
4. Scene navigator below SVG
5. Current Scene summary when Inspector collapsed → 「查看详情」opens dock

## Scroll ownership

- Workspace: `overflow: hidden`
- SourcePane / MainPane / InspectorPane: independent `overflow-y: auto`
- Chart: `overflow-y: hidden` (X browse only when Scene density requires)

## PNG

- Default **完整旅程**
- Filename: `StoryLens_<title>_完整旅程_v4.0.png`
- Export shell excludes App nav, Source, Inspector, and buttons

## Rollback

1. Point `scripts/check_reader_journey_ui_freeze.py` to `reader-journey-ui-final-v3.0`
2. Remove `ui-presentation-thaw-v2-12.json` from `check_core_freeze.py` DEFAULT_THAWS
3. Restore frozen files from v3.0 hashes

## Tests / screenshots

- Unit: `phase_1dc1_ui05_workspace_layout_v4_0.test.tsx`
- Playwright: `audits/single-chapter-pipeline/reader-journey-visual-regression-v4.0/`
