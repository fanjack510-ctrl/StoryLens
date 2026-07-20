/**
 * Global Reader Journey Visualization v4.2 configuration.
 * Metric selector in-flow panel + unified overlay tokens.
 * Resizable workspace from v4.1 preserved. No id-specific branches.
 */

export const JOURNEY_VISUALIZATION_VERSION = "4.2";

/**
 * Layout breakpoints use the browser viewport width (not host/nav-subtracted width),
 * so 1440px viewport always gets a right Inspector and &lt;1180px stays narrow.
 */
export const LAYOUT_BREAKPOINTS = {
  desktopMin: 1440,
  midMin: 1180,
} as const;

export type JourneyLayoutMode = "desktop" | "mid" | "narrow";

export function resolveJourneyLayoutMode(widthPx: number): JourneyLayoutMode {
  if (widthPx >= LAYOUT_BREAKPOINTS.desktopMin) return "desktop";
  if (widthPx >= LAYOUT_BREAKPOINTS.midMin) return "mid";
  return "narrow";
}

/** Defaults / collapsed tokens (v4.1 ranges live in journeyPaneWidth.ts). */
export const SOURCE_PANE_WIDTH_PX = {
  desktop: 300,
  mid: 300,
  collapsed: 0,
} as const;

export const INSPECTOR_PANE_WIDTH_PX = {
  desktop: 360,
  collapsed: 0,
} as const;

export const INSPECTOR_BOTTOM_DOCK_HEIGHT_PX = {
  min: 240,
  max: 520,
  default: 320,
} as const;

export const LAYOUT_TOKENS = {
  toolbarHeight: 48,
  buttonHeight: 36,
  buttonGap: 8,
  sectionGap: 16,
  cardRadius: 12,
  panelPadding: 16,
  inspectorAnimMs: 180,
} as const;

/**
 * True plot-area (inner drawing) heights in px.
 * SVG height = plot area + CHART_PAD.top + CHART_PAD.bottom.
 * Desktop default: svg_height=420 → plot_area=352 (>= 340).
 */
export const PLOT_AREA_HEIGHT_PRESETS = {
  compact: 220,
  standard: 352,
  expanded: 480,
} as const;

export type ChartHeightPreset = keyof typeof PLOT_AREA_HEIGHT_PRESETS;

export const DEFAULT_CHART_HEIGHT_PRESET: ChartHeightPreset = "standard";

/** Hard shell / SVG floors for desktop default (v3.0). */
export const CHART_SHELL_MIN_HEIGHT_PX = 440;
export const SVG_HEIGHT_STANDARD_PX = 420;

/** SVG / chartHeights derived from plot-area presets (pad included). */
export const CHART_HEIGHT_PRESETS = {
  compact: PLOT_AREA_HEIGHT_PRESETS.compact + 28 + 40,
  standard: SVG_HEIGHT_STANDARD_PX,
  expanded: PLOT_AREA_HEIGHT_PRESETS.expanded + 28 + 40,
} as const;

export type YDomainMode = "fixed_0_100" | "focus_data";

export const DEFAULT_Y_DOMAIN_MODE: YDomainMode = "fixed_0_100";

export const Y_TICKS_FIXED = [0, 25, 50, 75, 100] as const;

export const CHART_PAD = {
  left: 44,
  right: 20,
  top: 28,
  bottom: 40,
} as const;

/** Layer paint order (bottom → top). */
export const CHART_LAYER_ORDER = [
  "phase_background",
  "risk_background",
  "grid",
  "curve",
  "nodes",
  "active_scene",
  "labels_tooltip",
] as const;

export const PHASE_BAND_OPACITY = {
  idle: 0.18,
  active: 0.32,
} as const;

export const RISK_BAND_OPACITY = 0.28;

export const SCENE_DENSITY = {
  fitAllMax: 15,
  panZoomMax: 30,
  /** Minimum pixels between adjacent scene centers when zoomed / long chapters. */
  minPxPerScene: 48,
  /** Medium chapters (16–30): slightly denser minimum for readable X browsing. */
  mediumMinPxPerScene: 56,
  /** Brush / interval minimum visible scene span when sceneCount > 30. */
  brushMinVisibleScenes: 8,
} as const;

/** @deprecated v4.0 removed vertical tool rail; kept for import compatibility. */
export const TOOL_RAIL_WIDTH_PX = 0;

export const UI_PREF_KEYS = {
  chartHeight: "storylens.readerJourney.chartHeight.v4_0",
  yDomainMode: "storylens.readerJourney.yDomainMode.v4_0",
  inspectorCollapsed: "storylens.readerJourney.inspectorCollapsed.v4_0",
  sourceCollapsed: "storylens.readerJourney.sourceCollapsed.v4_0",
  overviewHeight: "storylens.readerJourney.overviewHeight.v1",
  insightStripExpanded: "storylens.readerJourney.insightStripExpanded.v4_0",
  /** Global preferred widths — not scoped by book/chapter/run. */
  sourcePaneWidth: "storylens.readerJourney.sourcePaneWidth",
  inspectorPaneWidth: "storylens.readerJourney.inspectorPaneWidth",
  inspectorDockHeight: "storylens.readerJourney.inspectorDockHeight",
} as const;

export const URL_CHART_PARAMS = {
  xStart: "xStart",
  xEnd: "xEnd",
  yDomain: "yDomain",
} as const;

export function readLocalPref<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeLocalPref(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore quota / private mode */
  }
}

export function readChartHeightPreset(): ChartHeightPreset {
  const stored = readLocalPref<string>(UI_PREF_KEYS.chartHeight, DEFAULT_CHART_HEIGHT_PRESET);
  if (stored === "compact" || stored === "standard" || stored === "expanded") return stored;
  return DEFAULT_CHART_HEIGHT_PRESET;
}

export function writeChartHeightPreset(preset: ChartHeightPreset): void {
  writeLocalPref(UI_PREF_KEYS.chartHeight, preset);
}

export function readYDomainMode(): YDomainMode {
  const stored = readLocalPref<string>(UI_PREF_KEYS.yDomainMode, DEFAULT_Y_DOMAIN_MODE);
  if (stored === "fixed_0_100" || stored === "focus_data") return stored;
  return DEFAULT_Y_DOMAIN_MODE;
}

export function writeYDomainMode(mode: YDomainMode): void {
  writeLocalPref(UI_PREF_KEYS.yDomainMode, mode);
}

/** SVG height for a height preset (includes vertical padding). */
export function chartHeightPx(preset: ChartHeightPreset): number {
  if (preset === "standard") return SVG_HEIGHT_STANDARD_PX;
  return PLOT_AREA_HEIGHT_PRESETS[preset] + CHART_PAD.top + CHART_PAD.bottom;
}

export function plotAreaHeightPx(preset: ChartHeightPreset): number {
  if (preset === "standard") {
    return SVG_HEIGHT_STANDARD_PX - CHART_PAD.top - CHART_PAD.bottom;
  }
  return PLOT_AREA_HEIGHT_PRESETS[preset];
}

/**
 * Default horizontal view policy by scene count (global, not book-specific).
 * - ≤15: fit all (no X/Y scroll)
 * - 16–30: fit all initially; horizontal pan allowed
 * - >30: brush interval for readable density
 */
export function defaultViewWindow(sceneCount: number): { start: number; end: number } {
  if (sceneCount <= 0) return { start: 1, end: 1 };
  return { start: 1, end: sceneCount };
}

export function requiresBrush(sceneCount: number): boolean {
  return sceneCount > SCENE_DENSITY.panZoomMax;
}

export function allowsHorizontalPanZoom(sceneCount: number): boolean {
  return sceneCount > SCENE_DENSITY.fitAllMax;
}

export function showsZoomControls(sceneCount: number): boolean {
  return sceneCount > SCENE_DENSITY.fitAllMax;
}

export function computeChartContentWidth(
  sceneCount: number,
  viewportWidth: number,
  viewStart: number,
  viewEnd: number,
): number {
  const visible = Math.max(viewEnd - viewStart, 0) + 1;
  const pads = CHART_PAD.left + CHART_PAD.right;

  // ≤15 + fit-all: match viewport so ordinary chapters need no horizontal scroll.
  if (sceneCount <= SCENE_DENSITY.fitAllMax && viewStart === 1 && viewEnd === sceneCount) {
    return Math.max(viewportWidth, 520);
  }

  // 16–30: ensure readable min density → horizontal browse when viewport is narrow.
  if (sceneCount <= SCENE_DENSITY.panZoomMax) {
    const density = SCENE_DENSITY.mediumMinPxPerScene;
    return Math.max(
      viewportWidth,
      Math.ceil((sceneCount - 1) * density) + pads,
      720,
    );
  }

  // >30: width follows visible window density / brush selection.
  const density = Math.max(
    SCENE_DENSITY.minPxPerScene,
    viewportWidth / Math.max(visible - 1, 1),
  );
  return Math.max(
    viewportWidth,
    Math.ceil((sceneCount - 1) * density) + pads,
    720,
  );
}
