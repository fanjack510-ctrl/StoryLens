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

const NON_CHART_NODE_TYPES = new Set([
  "phase_summary",
  "separator",
  "annotation",
  "hook_event",
  "payoff_event",
  "diagnostic_marker",
  "redacted_placeholder",
  "legacy_summary",
]);

/**
 * Chart eligibility is decided by contract/node_type (and hard integrity block),
 * not by guessing from missing numeric fields.
 */
export function isChartEligibleNode(node: unknown): boolean {
  if (!node || typeof node !== "object") return false;
  const n = node as {
    integrity_blocked?: boolean;
    node_type?: string;
    role?: string;
  };
  if (n.integrity_blocked) return false;
  const nodeType = String(n.node_type || n.role || "scene").toLowerCase();
  if (NON_CHART_NODE_TYPES.has(nodeType)) return false;
  return true;
}

function nodeHasChartNumbers(node: unknown): boolean {
  if (!node || typeof node !== "object") return false;
  const n = node as { scores?: unknown; engagement?: unknown };
  return (
    (n.scores != null && typeof n.scores === "object") ||
    (n.engagement != null && typeof n.engagement === "object")
  );
}

/**
 * True when the visualization is safe to mount in the chart shell.
 * Non-chart nodes may omit scores/engagement. Chart-eligible nodes need numbers.
 * Hard-blocked nodes alone do not make the whole journey unmountable when mixed —
 * callers that hard-fail use integrity_status instead.
 */
export function hasChartSafeJourneyNodes(data: JourneyVizSource): boolean {
  if (!hasUsableJourneyVisualization(data) || !data?.visualization) return false;
  const nodes = data.visualization.scene_nodes;
  if (!Array.isArray(nodes) || nodes.length === 0) return false;
  const eligible = nodes.filter(isChartEligibleNode);
  if (eligible.length === 0) return true;
  return eligible.some(nodeHasChartNumbers);
}
