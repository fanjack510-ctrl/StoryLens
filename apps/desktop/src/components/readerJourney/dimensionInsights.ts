/** Lens → dimension insight key mapping and display helpers. */

import type { ObservationLensId } from "./observationLenses";
import { getObservationLens } from "./observationLenses";
import type { JourneySceneNode } from "../../types/readerJourneyVisualization";

export type DimensionInsightKey =
  | "overall_reading"
  | "plot_progression"
  | "reading_tension"
  | "emotional_intensity"
  | "hook_payoff"
  | "pacing_speed";

export type DimensionInsightsMap = Partial<Record<DimensionInsightKey, string | null>>;

export const DIMENSION_INSIGHT_UNAVAILABLE = "当前维度暂无可靠洞察";

const LENS_TO_INSIGHT_KEY: Record<ObservationLensId, DimensionInsightKey> = {
  composite: "overall_reading",
  plot_progress: "plot_progression",
  reading_tension: "reading_tension",
  emotion: "emotional_intensity",
  hook_payoff: "hook_payoff",
  pacing: "pacing_speed",
};

export function insightKeyForLens(lensId: ObservationLensId): DimensionInsightKey {
  return LENS_TO_INSIGHT_KEY[lensId];
}

export function dimensionInsightTitle(lensId: ObservationLensId): string {
  const label = getObservationLens(lensId).labelZh;
  return `${label}洞察`;
}

export function resolveDimensionInsightText(
  node: JourneySceneNode,
  lensId: ObservationLensId,
): string {
  const key = insightKeyForLens(lensId);
  const insights = node.dimension_insights;
  const text = insights?.[key];
  if (typeof text === "string" && text.trim()) {
    return text.trim();
  }
  return DIMENSION_INSIGHT_UNAVAILABLE;
}

export function hasDimensionInsight(node: JourneySceneNode, lensId: ObservationLensId): boolean {
  const key = insightKeyForLens(lensId);
  const text = node.dimension_insights?.[key];
  return typeof text === "string" && text.trim().length > 0;
}
