import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";

type JourneyVizSource = {
  status?: string | null;
  visualization?: ReaderJourneyVisualization | null;
} | null | undefined;

/**
 * True when a succeeded journey has chart-usable visualization data
 * (non-empty scenes, phases, and at least one metric series with points).
 */
export function hasUsableJourneyVisualization(data: JourneyVizSource): boolean {
  if (!data || data.status !== "succeeded" || !data.visualization) return false;
  const viz = data.visualization;
  if (!Array.isArray(viz.scene_nodes) || viz.scene_nodes.length === 0) return false;
  if (!Array.isArray(viz.phases) || viz.phases.length === 0) return false;
  const series = viz.curve_series;
  if (!series || typeof series !== "object") return false;
  return Object.values(series).some((points) => Array.isArray(points) && points.length > 0);
}
