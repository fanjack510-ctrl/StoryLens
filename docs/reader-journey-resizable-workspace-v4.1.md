# Reader Journey Resizable Workspace v4.1

**Phase:** 1D-C1-UI-06  
**Baseline:** Reader Journey UI Final v4.1  
**Parent:** Reader Journey Workspace Layout v4.0 (`READER_JOURNEY_WORKSPACE_LAYOUT_V4_0_READY_FOR_HUMAN_UAT`)  
**Scope:** Global resizable three-pane workspace for every book / chapter / AnalysisRun / ReaderJourneyRun

## Human UAT finding (v4.0)

Source | Main | Inspector existed, but left/right pane widths were fixed. Authors could not balance body text length, chart width, and inspector density.

## Architecture

```
grid-template-columns:
  var(--source-pane-width)
  var(--splitter-left-width)
  minmax(640px, 1fr)
  var(--splitter-right-width)
  var(--inspector-pane-width)
```

| Pane | min | default | max |
|------|-----|---------|-----|
| Source | 220 | 300 | 480 |
| Inspector | 300 | 360 | 520 |
| Main | 640 (floor) | 1fr | — |
| Bottom Dock height (mid) | 240 | 320 | 520 |

Splitter visual width 8px; hit target ≥12px; Pointer Events + `setPointerCapture`; keyboard Arrow/Shift/Home/End/Enter; double-click restores that pane’s default.

## Preferences

- `storylens.readerJourney.sourcePaneWidth`
- `storylens.readerJourney.inspectorPaneWidth`
- `storylens.readerJourney.inspectorDockHeight`

Global UI prefs (not per book/chapter/run). Illegal values fall back to defaults. Window shrink applies temporary **effective** clamp; **preferred** is preserved and restored when space returns.

## Responsive

| Width | Behavior |
|-------|----------|
| ≥1440 | Three columns + both vertical splitters |
| 1100–1439 | Source↔Main vertical splitter; Inspector bottom dock + horizontal splitter |
| <1100 | Tabs only; no splitters |

## Scroll / Chart

v4.0 scroll ownership preserved. Chart continues to follow Main width via ResizeObserver (`requestAnimationFrame` coalesced during drag). Y 0–100, plotHeight 352, SVG height 420 unchanged. PNG export unaffected by pane widths.

## Rollback

1. Point `scripts/check_reader_journey_ui_freeze.py` to `reader-journey-ui-final-v4.0`
2. Remove `ui-presentation-thaw-v2-13.json` from `check_core_freeze.py` DEFAULT_THAWS
3. Restore frozen files from v4.0 hashes

## Tests / screenshots

- Unit: `phase_1dc1_ui06_resizable_workspace_v4_1.test.tsx`
- Playwright: `audits/single-chapter-pipeline/reader-journey-resizable-visual-regression-v4.1/`
