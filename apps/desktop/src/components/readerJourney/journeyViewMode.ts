/**
 * Journey-internal view mode (secondary nav).
 * Must not be confused with WorkspaceTab (text | scene | journey).
 */
export type JourneyViewMode = "compare" | "journey" | "text";

/** Legacy pageMode values still used inside selection state / SyncWorkspace. */
export type JourneyPageModeAlias = "sync" | "journey" | "reading";

export const JOURNEY_VIEW_PARAM = "journeyView";
export const LEGACY_MODE_PARAM = "mode";
export const DEFAULT_JOURNEY_VIEW: JourneyViewMode = "compare";

export function parseJourneyViewMode(value: string | null | undefined): JourneyViewMode {
  if (value === "compare" || value === "journey" || value === "text") return value;
  return DEFAULT_JOURNEY_VIEW;
}

export function journeyViewToPageMode(view: JourneyViewMode): JourneyPageModeAlias {
  if (view === "compare") return "sync";
  if (view === "text") return "reading";
  return "journey";
}

export function pageModeToJourneyView(mode: JourneyPageModeAlias): JourneyViewMode {
  if (mode === "sync") return "compare";
  if (mode === "reading") return "text";
  return "journey";
}

export function parseLegacyPageMode(value: string | null | undefined): JourneyPageModeAlias {
  if (value === "journey" || value === "reading" || value === "sync") return value;
  return "sync";
}

/**
 * Prefer journeyView=; fall back to legacy mode=; illegal → compare/sync.
 */
export function resolveJourneyPageModeFromSearch(
  params: URLSearchParams | { get: (k: string) => string | null },
): JourneyPageModeAlias {
  const journeyView = params.get(JOURNEY_VIEW_PARAM);
  if (journeyView != null && journeyView !== "") {
    return journeyViewToPageMode(parseJourneyViewMode(journeyView));
  }
  return parseLegacyPageMode(params.get(LEGACY_MODE_PARAM));
}

export function applyJourneyViewToSearchParams(
  params: URLSearchParams,
  pageMode: JourneyPageModeAlias,
): URLSearchParams {
  const next = params;
  const view = pageModeToJourneyView(pageMode);
  next.set(JOURNEY_VIEW_PARAM, view);
  // Keep legacy mode= for older bookmarks / local tests.
  next.set(LEGACY_MODE_PARAM, pageMode);
  return next;
}
