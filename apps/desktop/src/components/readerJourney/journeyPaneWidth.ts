/**
 * Reader Journey Resizable Workspace v4.1 — pane width/height clamp helpers.
 * preferredWidth is persisted; effectiveWidth is temporary clamp for the current viewport.
 */

export const SPLITTER_WIDTH_PX = 8;
export const SPLITTER_HIT_AREA_PX = 12;
export const MAIN_PANE_MIN_WIDTH_PX = 640;

export const SOURCE_PANE_WIDTH_RANGE = {
  min: 220,
  default: 300,
  max: 480,
} as const;

export const INSPECTOR_PANE_WIDTH_RANGE = {
  min: 300,
  default: 360,
  max: 520,
} as const;

export const INSPECTOR_DOCK_HEIGHT_RANGE = {
  min: 240,
  default: 320,
  max: 520,
} as const;

export const PANE_RESIZE_STEP_PX = 8;
export const PANE_RESIZE_STEP_LARGE_PX = 24;

export function sanitizePreferredWidth(
  value: unknown,
  range: { min: number; max: number; default: number },
): number {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return range.default;
  if (n < range.min || n > range.max) return range.default;
  return Math.round(n);
}

export function clampPreferredToRange(
  preferred: number,
  range: { min: number; max: number },
): number {
  return Math.min(range.max, Math.max(range.min, Math.round(preferred)));
}

/**
 * Max width a side pane may take while keeping Main >= MAIN_PANE_MIN_WIDTH_PX
 * and avoiding page-level horizontal overflow.
 */
export function maxSidePaneWidth(
  workspaceWidth: number,
  otherSideEffective: number,
  splitterCount: number,
): number {
  if (workspaceWidth <= 0) return 0;
  const reserved =
    MAIN_PANE_MIN_WIDTH_PX + otherSideEffective + splitterCount * SPLITTER_WIDTH_PX;
  return Math.max(0, Math.floor(workspaceWidth - reserved));
}

/**
 * Effective width for layout. May be temporarily below range.min when the
 * viewport is too narrow — preferred is never overwritten by this clamp.
 */
export function effectivePaneWidth(
  preferred: number,
  range: { min: number; max: number },
  maxAllowed: number,
  collapsed: boolean,
): number {
  if (collapsed) return 0;
  const inRange = clampPreferredToRange(preferred, range);
  if (maxAllowed <= 0) return 0;
  return Math.min(inRange, maxAllowed);
}

export function effectiveDockHeight(
  preferred: number,
  range: { min: number; max: number },
  maxAllowed: number,
  collapsed: boolean,
): number {
  if (collapsed) return 0;
  const inRange = clampPreferredToRange(preferred, range);
  if (maxAllowed <= 0) return Math.min(inRange, range.min);
  return Math.min(inRange, maxAllowed, range.max);
}
