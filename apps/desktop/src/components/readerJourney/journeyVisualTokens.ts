/** Single source of truth for Reader Journey stage (开端/发展/收束) visuals. */

export type JourneyStageKey = "opening" | "development" | "closing" | "unknown";

export type JourneyStageVisualToken = {
  key: JourneyStageKey;
  label: string;
  /** Card / CSS --phase-band-color base */
  cardBackground: string;
  cardBorder: string;
  /** Chart band fill (opacity applied by chart) */
  chartBand: string;
  /** Left rail / scene marker strip */
  sceneMarker: string;
  /** Boundary divider stroke */
  divider: string;
};

/**
 * Semantic tokens — reuse the muted greens/warms/cools already used by phase cards.
 * Do not invent a second palette elsewhere.
 */
export const JOURNEY_STAGE_VISUAL_TOKENS: Record<JourneyStageKey, JourneyStageVisualToken> = {
  opening: {
    key: "opening",
    label: "开端",
    cardBackground: "#e8ede9",
    cardBorder: "#c5d0c8",
    chartBand: "#e8ede9",
    sceneMarker: "#c5d0c8",
    divider: "#a8b8ae",
  },
  development: {
    key: "development",
    label: "发展",
    cardBackground: "#f0ebe3",
    cardBorder: "#d9cfc0",
    chartBand: "#f0ebe3",
    sceneMarker: "#d9cfc0",
    divider: "#c4b5a0",
  },
  closing: {
    key: "closing",
    label: "收束",
    cardBackground: "#e6ebf0",
    cardBorder: "#c2ccd8",
    chartBand: "#e6ebf0",
    sceneMarker: "#c2ccd8",
    divider: "#9aabbd",
  },
  unknown: {
    key: "unknown",
    label: "阶段未判定",
    cardBackground: "#ede8e6",
    cardBorder: "#d5cecb",
    chartBand: "#ede8e6",
    sceneMarker: "#d5cecb",
    divider: "#b8b0ac",
  },
};

/** @deprecated Prefer resolveJourneyStageToken — kept for import compatibility. */
export const PHASE_BAND_COLORS = [
  JOURNEY_STAGE_VISUAL_TOKENS.opening.chartBand,
  JOURNEY_STAGE_VISUAL_TOKENS.development.chartBand,
  JOURNEY_STAGE_VISUAL_TOKENS.closing.chartBand,
  JOURNEY_STAGE_VISUAL_TOKENS.unknown.chartBand,
] as const;

const TITLE_TO_KEY: Record<string, JourneyStageKey> = {
  开端: "opening",
  入局: "opening",
  入: "opening",
  entry: "opening",
  opening: "opening",
  发展: "development",
  推进: "development",
  推: "development",
  development: "development",
  收束: "closing",
  收: "closing",
  resolution: "closing",
  closing: "closing",
  转折: "development",
  turn: "development",
};

export function resolveJourneyStageKey(
  titleOrLabel: string | null | undefined,
): JourneyStageKey {
  if (titleOrLabel == null) return "unknown";
  const trimmed = String(titleOrLabel).trim();
  if (!trimmed) return "unknown";
  if (TITLE_TO_KEY[trimmed]) return TITLE_TO_KEY[trimmed];
  const lower = trimmed.toLowerCase();
  if (TITLE_TO_KEY[lower]) return TITLE_TO_KEY[lower];
  if (trimmed.includes("开端") || trimmed.includes("入局")) return "opening";
  if (trimmed.includes("收束") || trimmed.includes("结局")) return "closing";
  if (trimmed.includes("发展") || trimmed.includes("推进")) return "development";
  return "unknown";
}

export function resolveJourneyStageToken(
  titleOrLabel: string | null | undefined,
): JourneyStageVisualToken {
  return JOURNEY_STAGE_VISUAL_TOKENS[resolveJourneyStageKey(titleOrLabel)];
}

export function journeyStageTokenByKey(key: JourneyStageKey): JourneyStageVisualToken {
  return JOURNEY_STAGE_VISUAL_TOKENS[key] ?? JOURNEY_STAGE_VISUAL_TOKENS.unknown;
}
