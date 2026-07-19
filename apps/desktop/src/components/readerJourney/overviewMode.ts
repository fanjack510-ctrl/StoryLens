/** Presentation-only overview view mode (does not alter selection semantics). */

export type JourneyOverviewMode = "curve" | "questions" | "diagnosis";

export const OVERVIEW_MODE_PARAM = "overview";

/** Canonical single journey-analysis overview mode (internal URL value). */
export const CANONICAL_OVERVIEW_MODE: JourneyOverviewMode = "curve";

/** Pure UI Context Inspector target — does not create a second activeScene/activePhase. */
export type JourneyInspectorType =
  | "phase"
  | "scene"
  | "question"
  | "hook"
  | "payoff"
  | "risk";

export const INSPECTOR_PARAM = "inspector";

const INSPECTOR_VALUES: JourneyInspectorType[] = [
  "phase",
  "scene",
  "question",
  "hook",
  "payoff",
  "risk",
];

/**
 * Legacy overview=questions|diagnosis are accepted for URL compat but always
 * resolve to the single journey-analysis view (curve).
 */
export function parseOverviewMode(value: string | null | undefined): JourneyOverviewMode {
  if (value === "questions" || value === "diagnosis" || value === "curve") {
    return CANONICAL_OVERVIEW_MODE;
  }
  return CANONICAL_OVERVIEW_MODE;
}

export function isLegacyOverviewMode(value: string | null | undefined): boolean {
  return value === "questions" || value === "diagnosis";
}

/** Normalize overview param to curve without dropping other params. */
export function normalizeOverviewModeParam(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  const current = next.get(OVERVIEW_MODE_PARAM);
  if (current !== CANONICAL_OVERVIEW_MODE) {
    next.set(OVERVIEW_MODE_PARAM, CANONICAL_OVERVIEW_MODE);
  }
  return next;
}

export function applyOverviewModeParam(
  params: URLSearchParams,
  mode: JourneyOverviewMode,
): URLSearchParams {
  const next = new URLSearchParams(params);
  // Product UI is a single journey-analysis view; always persist canonical mode.
  void mode;
  next.set(OVERVIEW_MODE_PARAM, CANONICAL_OVERVIEW_MODE);
  return next;
}

export function parseInspectorType(
  value: string | null | undefined,
): JourneyInspectorType | null {
  if (value && INSPECTOR_VALUES.includes(value as JourneyInspectorType)) {
    return value as JourneyInspectorType;
  }
  return null;
}

export function applyInspectorParam(
  params: URLSearchParams,
  inspector: JourneyInspectorType | null,
): URLSearchParams {
  const next = new URLSearchParams(params);
  if (inspector) next.set(INSPECTOR_PARAM, inspector);
  else next.delete(INSPECTOR_PARAM);
  return next;
}
