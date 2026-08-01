/** Single source of truth for Reader Journey stage (开端/发展/收束) visuals. */

export type JourneyStageKey = "opening" | "development" | "closing" | "unknown";

export type JourneyStageVisualToken = {
  key: JourneyStageKey;
  label: string;
  /** Card / CSS --phase-band-color base (opaque) */
  cardBackground: string;
  cardBorder: string;
  /** Chart band fill — opaque; do not apply extra SVG opacity */
  chartBand: string;
  /** Left rail / scene marker strip */
  sceneMarker: string;
  /** Boundary divider stroke */
  divider: string;
};

/**
 * Frozen MG-visible palette (CHG-20260729-002 defect fix).
 * Low-saturation but clearly separable: green / warm / blue-gray.
 * Must remain opaque in chart + cards (no extra washout opacity).
 */
export const JOURNEY_STAGE_VISUAL_TOKENS: Record<JourneyStageKey, JourneyStageVisualToken> = {
  opening: {
    key: "opening",
    label: "开端",
    cardBackground: "#E4F1E8",
    cardBorder: "#9FC4AA",
    chartBand: "#E4F1E8",
    sceneMarker: "#9FC4AA",
    divider: "#7FAF8E",
  },
  development: {
    key: "development",
    label: "发展",
    cardBackground: "#F7EDD8",
    cardBorder: "#D4B779",
    chartBand: "#F7EDD8",
    sceneMarker: "#D4B779",
    divider: "#C4A35F",
  },
  closing: {
    key: "closing",
    label: "收束",
    cardBackground: "#E7EDF6",
    cardBorder: "#9EB4D1",
    chartBand: "#E7EDF6",
    sceneMarker: "#9EB4D1",
    divider: "#7E9BC0",
  },
  unknown: {
    key: "unknown",
    label: "阶段未判定",
    cardBackground: "#EDE8E6",
    cardBorder: "#D5CECB",
    chartBand: "#EDE8E6",
    sceneMarker: "#D5CECB",
    divider: "#B8B0AC",
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

/** Canonical band title — never Scene Role / segment labels. */
export function journeyStageBandTitle(key: JourneyStageKey): string {
  return journeyStageTokenByKey(key).label;
}

/** Hex colors must stay distinct without further opacity dilution. */
export function assertStageColorsVisuallyDistinct(): {
  opening: string;
  development: string;
  closing: string;
} {
  return {
    opening: JOURNEY_STAGE_VISUAL_TOKENS.opening.chartBand,
    development: JOURNEY_STAGE_VISUAL_TOKENS.development.chartBand,
    closing: JOURNEY_STAGE_VISUAL_TOKENS.closing.chartBand,
  };
}
