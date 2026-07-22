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

/**
 * True when scene nodes still carry chart fields (scores/engagement).
 * Integrity redaction may leave nodes/phases/curves but strip scores → chart mount would throw.
 */
export function hasChartSafeJourneyNodes(data: JourneyVizSource): boolean {
  if (!hasUsableJourneyVisualization(data) || !data?.visualization) return false;
  const nodes = data.visualization.scene_nodes;
  if (!Array.isArray(nodes) || nodes.length === 0) return false;
  return nodes.every((node) => {
    if (!node || typeof node !== "object") return false;
    if ((node as { integrity_blocked?: boolean }).integrity_blocked) return false;
    const scores = (node as { scores?: unknown }).scores;
    const engagement = (node as { engagement?: unknown }).engagement;
    return (
      (scores != null && typeof scores === "object") ||
      (engagement != null && typeof engagement === "object")
    );
  });
}
