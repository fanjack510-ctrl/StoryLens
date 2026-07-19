# Reader Journey Full Plot and Tool Rail v3.0

**Phase:** 1D-C1-UI-04  
**Baseline:** Reader Journey UI Final v3.0  
**Parent:** Reader Journey Visualization v2.9 (`READER_JOURNEY_VISUALIZATION_V2_9_HUMAN_UAT_FAILED`)  
**Scope:** Full plot restoration + vertical tool rail for every book / chapter / ReaderJourneyRun

## Human UAT failure (v2.9) — root cause

Runtime size-chain diagnosis (not unit-test-only):

1. Overview grid used `minmax(420px, ~72%)` with `overflow: hidden` on overview / export-root / curve.
2. Phase nav + horizontal toolbar + legend consumed vertical chrome above the SVG.
3. When overview track height < chrome + SVG(408), the **bottom of the SVG was clipped**.
4. Y ticks **0** and **25** live at the bottom of the plot → became invisible.
5. Low-score troughs below ~50 disappeared for the same clip reason.
6. Legacy `.journey-curve-svg { height: 260px }` and `width:100%` + `height:auto` could further desync rendered height from `viewBox`.

**Direct cause of missing Y=25 / Y=0:** parent `overflow:hidden` + ratio-capped overview height cropping the SVG bottom — not missing data and not Scene-count special cases.

## Hard plot rules (desktop default)

| Constraint | Value |
|------------|-------|
| `chart_shell_height` | ≥ 440px |
| `svg_height` (standard) | **420px** |
| `plot_area_height` | ≥ 340px (standard = 352) |
| Y domain | `[0, 100]` |
| Y ticks | `[0, 25, 50, 75, 100]` |

All five ticks and all 0—100 nodes must be in the visible plot without vertical scrolling of the chart.

## Layout

1. Title / analysis chrome  
2. Phase navigation  
3. **Chart shell** = vertical tool rail (48—64px) + viewport  
4. SVG plot (hero)  
5. Scene rhythm strip **below** SVG  
6. One-line chapter summary  
7. Collapsed Inspector summary → expand on demand  

## Vertical tool rail (replaces top primary toolbar)

Actions only:

- 指标  
- 适应全部  
- 当前Phase  
- 详情  
- 导出  
- 更多设置（高度预设 / 聚焦数据 / 放大缩小 / 恢复默认）

No duplicate top toolbar buttons. System left nav unchanged. Text pane may collapse to free chart width.

## Overflow

- Chart viewport / curve container: `overflow-y: hidden` (never `auto`/`scroll` for Y).
- Overview uses **content-sized** (`auto`) rows so Inspector expand does not ratio-squeeze the plot.
- clipPath height always equals live `plotHeight`; nodes are not inside the clip.

## Density

| Scene count | Behavior |
|-------------|----------|
| ≤ 15 | Fit all; no zoom controls |
| 16–30 | Horizontal browse |
| > 30 | Brush / interval |

Y axis always full 0—100 regardless of Scene count.

## PNG

- Default **完整旅程**
- Filename: `StoryLens_<title>_完整旅程_v3.0.png`

## Rollback

1. Point `scripts/check_reader_journey_ui_freeze.py` to `reader-journey-ui-final-v2.9`
2. Remove `ui-presentation-thaw-v2-11.json` from `check_core_freeze.py` DEFAULT_THAWS
3. Restore frozen files from v2.9 hashes

## Tests / screenshots

- Unit: `phase_1dc1_ui04_visualization_v3_0.test.tsx`
- Playwright DOM: `audits/single-chapter-pipeline/reader-journey-visual-regression-v3.0/`
