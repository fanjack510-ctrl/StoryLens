# Reader Journey Chart Interaction v2.8

**Phase:** 1D-C1-UI-02  
**Baseline:** Reader Journey UI Final v2.8  
**Scope:** Global visualization optimization for every book / chapter / ReaderJourneyRun

## Shared architecture

All journey charts use one composition path:

1. `ReaderJourneySyncWorkspace` → `ReaderJourneyWorkspace`
2. `CanonicalJourneyChart` (sole SVG curve implementation)
3. `journeyVisualizationConfig` + `journeyChartScales` (global prefs / scales)
4. `JourneyChartToolbar` (height / Y-domain / zoom)
5. `JourneyResizableSplit` (Overview ↔ Inspector)
6. `exportJourneyPng` (default **完整旅程** PNG)

No second chart implementation and no `book_id` / `chapter_id` / `run_id` branches.

## Call graph

```text
ReaderJourneyWorkspace
├─ JourneyChartToolbar
│  ├─ height preset → localStorage storylens.readerJourney.chartHeight.v2_8
│  ├─ Y domain mode → localStorage storylens.readerJourney.yDomainMode.v2_8
│  └─ zoom actions → URL xStart/xEnd + view window
├─ CanonicalJourneyChart
│  ├─ Phase background → Risk background → Grid → Curve → Nodes → Active Scene → Tooltip
│  ├─ pan/drag (scene 16–30)
│  └─ brush (scene > 30)
├─ JourneyResizableSplit
│  ├─ drag handle / keyboard
│  ├─ collapse / expand Inspector
│  └─ restore default layout
├─ Scene / Phase navigation → Selection Transaction → Inspector / Evidence / URL
└─ exportJourneyPng(mode=full_journey)
   └─ offscreen CanonicalJourneyChart(exportFullJourney)
```

## Y axis

- Default: fixed `domain=[0,100]`, ticks `0/25/50/75/100`
- Optional user mode: focus current data
- Null / NaN / missing → line break (never coerced to 0)
- Values `<0` or `>100` raise a visible data warning (not silently clipped)

## Height

| Preset | px |
|--------|----|
| compact | 240 |
| standard | 360 (default) |
| expanded | 520 |

Stored in local UI preference only; never written into Reader Journey business data.

## Zoom / density

| Scene count | Behavior |
|-------------|----------|
| ≤ 15 | Fit all by default |
| 16–30 | Fit all initially; pan + zoom allowed |
| > 30 | Brush interval required; no forced unreadability |

Zoom only changes X density / window. Scores stay unchanged.

## PNG export

- Button **导出PNG** defaults to **完整旅程**
- Always full scene span, Y 0–100
- Independent of current zoom window and Inspector expand state
- Offscreen export root: `journey-export-full-root`
- Filename: `StoryLens_<title>_完整旅程_v2.8.png`

## Rollback

1. Point `scripts/check_reader_journey_ui_freeze.py` back to `reader-journey-ui-final-v2.7`
2. Remove `ui-presentation-thaw-v2-9.json` from `check_core_freeze.py` DEFAULT_THAWS
3. Restore frozen files from v2.7 hashes
4. Keep new modules unused or delete if unused

## Tests / fixtures

- Unit: `phase_1dc1_ui02_visualization_v2_8.test.tsx`
- Fixtures: 3 / 13 / 30 / 60 scenes with 0 / 100 / null
- Visual regression: `audits/single-chapter-pipeline/reader-journey-visual-regression-v2.8/`
