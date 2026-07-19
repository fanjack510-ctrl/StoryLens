# Reader Journey Metric Selector and Overlay System v4.2

**Phase:** 1D-C1-UI-07  
**Baseline:** Reader Journey UI Final v4.2  
**Parent:** Reader Journey Resizable Workspace v4.1  
**Human UAT parent:** `READER_JOURNEY_RESIZABLE_WORKSPACE_V4_1_HUMAN_UAT_FAILED`  
**Defect:** DEFECT-UAT-009 Metric Selector Overlays Journey Content

## Problem

点击「当前指标」后，`JourneyAnchoredMenu` 以 `position:fixed` Portal 下拉覆盖 Phase 卡片、Scene 信息、旅程曲线与图表标记。

## Architecture

```
JourneyToolbar
MetricSelectorPanel  (open → in document flow)
PhaseNavigation
CanonicalJourneyChart
```

| Surface | Behavior |
|---------|----------|
| MetricSelectorPanel | `position:static` in-flow grid; max-height 280px; solid background; pushes Phase/Chart down |
| JourneyPopover / SharedPopover | Portal → `#journey-overlay-root`; fixed + flip/shift; pad ≥8px |
| Z-index tokens | content 0 / sticky toolbar 10 / popover 40 / chart tooltip 50 / modal 100 |

## Close / a11y

- Toggle trigger, Esc, outside click, option select
- `role=listbox` / `role=option` / Arrow / Enter / Space
- URL `metric` sync via existing selection wiring; no API write; no model calls

## Responsive

| Width | Metric panel |
|-------|----------------|
| ≥1440 | 3–4 column grid under toolbar |
| 1100–1439 | 2–3 columns; dock unchanged |
| <1100 | full-width in-flow accordion; secondary actions in 更多设置 |

## Rollback

1. Point `scripts/check_reader_journey_ui_freeze.py` to `reader-journey-ui-final-v4.1`
2. Remove `ui-presentation-thaw-v2-14.json` from `check_core_freeze.py` DEFAULT_THAWS
3. Restore frozen files from v4.1 hashes

## Tests / screenshots

- Unit: `phase_1dc1_ui07_metric_selector_v4_2.test.tsx`
- Playwright: `audits/single-chapter-pipeline/reader-journey-metric-selector-visual-regression-v4.2/`
