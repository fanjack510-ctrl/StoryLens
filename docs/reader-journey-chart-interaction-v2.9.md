# Reader Journey Chart Interaction v2.9

**Phase:** 1D-C1-UI-03  
**Baseline:** Reader Journey UI Final v2.9  
**Parent:** Reader Journey Visualization v2.8 (`READER_JOURNEY_VISUALIZATION_V2_8_HUMAN_UAT_FAILED`)  
**Scope:** Canonical journey view restoration for every book / chapter / ReaderJourneyRun

## Why

v2.8 engineering gates passed, but Human UAT failed: expand mode did not grow the real plot area, the curve was crushed by chrome/Inspector, chart interior scrolled vertically, and layout modes added complexity without restoring a readable full journey.

v2.9 restores the standard template where **the journey curve is the page hero**.

## Shared architecture (unchanged composition)

1. `ReaderJourneySyncWorkspace` → `ReaderJourneyWorkspace`
2. `CanonicalJourneyChart` (sole SVG curve implementation)
3. `journeyVisualizationConfig` + `journeyChartScales`
4. `JourneyChartToolbar` (simplified primary + 更多图表设置)
5. `JourneyResizableSplit` (Inspector default collapsed + summary bar)
6. `exportJourneyPng` (default **完整旅程** PNG)

No second chart page. No `book_id` / `chapter_id` / `run_id` branches.

## Default page order

1. Title + export PNG  
2. Phase navigation  
3. Metric + primary toolbar  
4. Full journey curve (hero)  
5. One-line collapsible chapter summary  
6. Collapsed Inspector summary → expanded detail on demand  

## Plot size

| Preset | plot_area_height | SVG height (pad included) |
|--------|------------------|---------------------------|
| compact | 220 | 288 |
| **standard (default)** | **340** | **408** |
| expanded | 480 | 548 |

Adjustments change SVG `height` / `viewBox` / `innerHeight`, not only an outer wrapper.

Chart containers use `overflow-y: hidden` (never `auto`/`scroll`). Y axis 0—100 always visible.

## Toolbar

**Primary:** 当前指标 · 适应全部 · 当前Phase · 展开详情 · 导出PNG  

**更多图表设置:** 紧凑/标准/展开 · 聚焦数据 · 放大/缩小（仅 Scene>15） · 恢复默认  

## Density

| Scene count | Behavior |
|-------------|----------|
| ≤ 15 | Fit all; no zoom controls; no X/Y scroll for ordinary chapters |
| 16–30 | Fit all initially; horizontal browse allowed |
| > 30 | Brush interval |

## PNG

- Default **完整旅程**
- Full scene span, Y 0—100
- Independent of viewport zoom and Inspector state
- Filename: `StoryLens_<title>_完整旅程_v2.9.png`

## Rollback

1. Point `scripts/check_reader_journey_ui_freeze.py` back to `reader-journey-ui-final-v2.8`
2. Remove `ui-presentation-thaw-v2-10.json` from `check_core_freeze.py` DEFAULT_THAWS
3. Restore frozen files from v2.8 hashes

## Tests / fixtures

- Unit: `phase_1dc1_ui03_visualization_v2_9.test.tsx`
- Fixtures: 3 / 13 / 30 / 60 scenes
- DOM screenshots: `audits/single-chapter-pipeline/reader-journey-visual-regression-v2.9/`
