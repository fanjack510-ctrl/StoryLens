/** Observation lenses for Reader Journey v2 chart (presentation + series resolution). */

import type {
  JourneyCurvePoint,
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import { resolveMetricValue } from "./journeyChartScales";

export type ObservationLensId =
  | "composite"
  | "plot_progress"
  | "reading_tension"
  | "emotion"
  | "hook_payoff"
  | "pacing";

export type ObservationLensDef = {
  id: ObservationLensId;
  labelZh: string;
  /** Primary series key used for Y-domain policy. */
  primaryKey: string;
  allowsOverlayWithComposite: boolean;
  isPairedHookPayoff: boolean;
  yDomain: "0_100" | "valence_signed" | "arousal_0_100";
};

export const OBSERVATION_LENSES: ObservationLensDef[] = [
  {
    id: "composite",
    labelZh: "综合阅读",
    primaryKey: "reading_momentum",
    allowsOverlayWithComposite: false,
    isPairedHookPayoff: false,
    yDomain: "0_100",
  },
  {
    id: "plot_progress",
    labelZh: "剧情推进",
    primaryKey: "plot_progress",
    allowsOverlayWithComposite: true,
    isPairedHookPayoff: false,
    yDomain: "0_100",
  },
  {
    id: "reading_tension",
    labelZh: "阅读张力",
    primaryKey: "reading_tension",
    allowsOverlayWithComposite: true,
    isPairedHookPayoff: false,
    yDomain: "0_100",
  },
  {
    id: "emotion",
    labelZh: "情绪旅程",
    primaryKey: "arousal",
    allowsOverlayWithComposite: true,
    isPairedHookPayoff: false,
    yDomain: "arousal_0_100",
  },
  {
    id: "hook_payoff",
    labelZh: "钩子回报",
    primaryKey: "hook",
    allowsOverlayWithComposite: false,
    isPairedHookPayoff: true,
    yDomain: "0_100",
  },
  {
    id: "pacing",
    labelZh: "节奏",
    primaryKey: "pacing_speed",
    allowsOverlayWithComposite: true,
    isPairedHookPayoff: false,
    yDomain: "0_100",
  },
];

export const DEFAULT_OBSERVATION_LENS: ObservationLensId = "composite";

/** One-line hint for the active lens (shown under toolbar, not inside a menu). */
export const OBSERVATION_LENS_HINTS_ZH: Record<ObservationLensId, string> = {
  composite: "观察整章阅读动力的起伏",
  plot_progress: "观察故事状态是否持续发生变化",
  reading_tension: "观察好奇、压力与情绪投入",
  emotion: "观察情绪强度、方向及转变",
  hook_payoff: "观察问题建立、推进与兑现",
  pacing: "观察叙事速度与场景任务是否匹配",
};

export function getObservationLensHint(id: ObservationLensId | string | null | undefined): string {
  const lens = getObservationLens(id);
  return OBSERVATION_LENS_HINTS_ZH[lens.id];
}

export function getObservationLens(id: ObservationLensId | string | null | undefined): ObservationLensDef {
  const found = OBSERVATION_LENSES.find((item) => item.id === id);
  return found ?? OBSERVATION_LENSES[0];
}

export type ChartLineSpec = {
  id: string;
  labelZh: string;
  series: JourneyCurvePoint[];
  style: "solid" | "dashed";
  /** When false, points are auxiliary (Beat) and skipped by main polyline builder. */
  includeInMainPolyline: boolean;
};

/** Resolved score bag for lens binding — engagement only as legacy fallback for reading_momentum. */
export function nodeScoreRecord(node: JourneySceneNode): Record<string, number | undefined> {
  const scores = (node.scores ?? {}) as Record<string, number | undefined>;
  const engagement = node.engagement as { engagement_score?: number } | undefined;
  return {
    ...scores,
    engagement: engagement?.engagement_score,
    reading_momentum:
      scores.reading_momentum ?? engagement?.engagement_score ?? scores.curiosity,
    plot_progress:
      scores.plot_progress ??
      averageDefined(scores.information_gain, scores.curiosity, scores.tension),
    reading_tension:
      scores.reading_tension ??
      weightedAverage(
        [
          [scores.curiosity, 0.4],
          [scores.tension, 0.35],
          [scores.emotional_resonance ?? scores.emotional_investment, 0.25],
        ],
      ),
    pacing_speed: scores.pacing_speed ?? scores.tension,
    pacing_fit: scores.pacing_fit,
    hook: scores.hook,
    payoff: scores.payoff,
    emotional_investment: scores.emotional_investment ?? scores.emotional_resonance,
  };
}

/** @deprecated Use nodeScoreRecord */
function nodeScores(node: JourneySceneNode): Record<string, number | undefined> {
  return nodeScoreRecord(node);
}

function averageDefined(...values: Array<number | undefined>): number | undefined {
  const nums = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!nums.length) return undefined;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function weightedAverage(parts: Array<[number | undefined, number]>): number | undefined {
  let total = 0;
  let weight = 0;
  for (const [value, w] of parts) {
    if (typeof value === "number" && Number.isFinite(value)) {
      total += value * w;
      weight += w;
    }
  }
  if (weight <= 0) return undefined;
  return total / weight;
}

function isBeatNode(node: JourneySceneNode): boolean {
  if (node.role === "beat") return true;
  if ((node as { node_type?: string }).node_type === "beat") return true;
  if ((node as { include_in_main_curve?: boolean }).include_in_main_curve === false) return true;
  return false;
}

function pointFromNode(
  node: JourneySceneNode,
  value: number | undefined,
): JourneyCurvePoint {
  const beat = isBeatNode(node);
  return {
    scene_ordinal: node.scene_ordinal,
    value: typeof value === "number" && Number.isFinite(value) ? value : undefined,
    include_in_main_curve: !beat,
    node_type: beat ? "beat" : "scene",
  } as JourneyCurvePoint;
}

function seriesFromNodes(
  visualization: ReaderJourneyVisualization,
  pick: (node: JourneySceneNode) => number | undefined,
): JourneyCurvePoint[] {
  return visualization.scene_nodes.map((node) => pointFromNode(node, pick(node)));
}

function seriesFromCurve(
  visualization: ReaderJourneyVisualization,
  metric: keyof ReaderJourneyVisualization["curve_series"],
): JourneyCurvePoint[] {
  const series = visualization.curve_series[metric] ?? [];
  return series.map((point) => {
    const node = visualization.scene_nodes.find((n) => n.scene_ordinal === point.scene_ordinal);
    const beat = node ? isBeatNode(node) : false;
    return {
      ...point,
      include_in_main_curve: !beat,
      node_type: beat ? "beat" : "scene",
    } as JourneyCurvePoint;
  });
}

/** Build chart lines for one observation lens (never six charts). */
export function buildLensChartLines(
  visualization: ReaderJourneyVisualization,
  lensId: ObservationLensId,
  options: { overlayComposite?: boolean } = {},
): ChartLineSpec[] {
  const overlayComposite = Boolean(options.overlayComposite);
  const lens = getObservationLens(lensId);
  const lines: ChartLineSpec[] = [];

  if (lens.id === "composite") {
    lines.push({
      id: "reading_momentum",
      labelZh: "阅读动力",
      series: seriesFromNodes(visualization, (n) => nodeScores(n).reading_momentum),
      style: "solid",
      includeInMainPolyline: true,
    });
    return lines;
  }

  if (lens.id === "plot_progress") {
    lines.push({
      id: "plot_progress",
      labelZh: "剧情推进",
      series: seriesFromNodes(visualization, (n) => nodeScores(n).plot_progress),
      style: "solid",
      includeInMainPolyline: true,
    });
  } else if (lens.id === "reading_tension") {
    lines.push({
      id: "reading_tension",
      labelZh: "阅读张力",
      series: seriesFromNodes(visualization, (n) => nodeScores(n).reading_tension),
      style: "solid",
      includeInMainPolyline: true,
    });
  } else if (lens.id === "emotion") {
    lines.push({
      id: "arousal",
      labelZh: "情绪强度",
      series: seriesFromCurve(visualization, "arousal").map((point, index) => {
        const node = visualization.scene_nodes[index];
        if (!node) return point;
        const scores = nodeScores(node);
        const arousal = averageDefined(scores.arousal_start, scores.arousal_end);
        return pointFromNode(node, arousal ?? resolveMetricValue(point) ?? undefined);
      }),
      style: "solid",
      includeInMainPolyline: true,
    });
  } else if (lens.id === "hook_payoff") {
    lines.push({
      id: "hook",
      labelZh: "钩子强度",
      series: seriesFromNodes(visualization, (n) => {
        const value = nodeScores(n).hook;
        // Explicit 0 is valid; missing key stays undefined (line break, no carry-forward).
        return typeof value === "number" && Number.isFinite(value) ? value : undefined;
      }),
      style: "solid",
      includeInMainPolyline: true,
    });
    lines.push({
      id: "payoff",
      labelZh: "本场回报强度",
      series: seriesFromNodes(visualization, (n) => {
        const value = nodeScores(n).payoff;
        return typeof value === "number" && Number.isFinite(value) ? value : undefined;
      }),
      style: "dashed",
      includeInMainPolyline: true,
    });
  } else if (lens.id === "pacing") {
    // pacing_speed drives the polyline; pacing_fit is a node/segment semantic, not the same score.
    lines.push({
      id: "pacing_speed",
      labelZh: "节奏速度",
      series: seriesFromNodes(visualization, (n) => nodeScores(n).pacing_speed),
      style: "solid",
      includeInMainPolyline: true,
    });
  }

  // Overlay: composite + current lens only (max 2). Hook/payoff already paired — no third line.
  if (
    overlayComposite &&
    lens.allowsOverlayWithComposite &&
    !lens.isPairedHookPayoff &&
    lines.length === 1
  ) {
    lines.unshift({
      id: "reading_momentum",
      labelZh: "阅读动力",
      series: seriesFromNodes(visualization, (n) => nodeScores(n).reading_momentum),
      style: "dashed",
      includeInMainPolyline: true,
    });
  }

  return lines.slice(0, lens.isPairedHookPayoff ? 2 : overlayComposite ? 2 : 1);
}

/** Main polyline series excludes Beat equal-weight vertices. */
export function mainCurveSeries(series: JourneyCurvePoint[]): JourneyCurvePoint[] {
  return series.filter((point) => {
    const flag = (point as { include_in_main_curve?: boolean }).include_in_main_curve;
    if (flag === false) return false;
    if ((point as { node_type?: string }).node_type === "beat") return false;
    return true;
  });
}

export function valenceDirection(node: JourneySceneNode): "up" | "down" | "flat" {
  const start = node.scores?.valence_start;
  const end = node.scores?.valence_end;
  if (typeof start !== "number" || typeof end !== "number") return "flat";
  const delta = end - start;
  if (delta > 8) return "up";
  if (delta < -8) return "down";
  return "flat";
}

export type PacingFitLabel = "偏慢" | "合适" | "偏快";
export type PacingSegmentLabel = "加速" | "减速" | "变化不明显";

/** Role target midpoints used when backend targets are absent (legacy). */
const PACING_ROLE_BANDS: Record<string, [number, number]> = {
  setup: [35, 60],
  escalation: [55, 80],
  investigation: [40, 70],
  reveal: [50, 75],
  climax: [70, 95],
  aftermath: [25, 55],
  transition: [30, 60],
  open_end: [40, 70],
  closed_end: [30, 60],
};

/**
 * Node label for whether pacing_speed fits scene_role.
 * Prefer backend pacing_fit when present; never treat fit as identical to speed.
 */
export function pacingFitLabel(
  pacingSpeed: number,
  sceneRole: string | undefined | null,
  pacingFitScore?: number | null,
): PacingFitLabel {
  const band = PACING_ROLE_BANDS[sceneRole ?? ""] ?? [40, 70];
  if (typeof pacingFitScore === "number" && Number.isFinite(pacingFitScore)) {
    if (pacingFitScore >= 70) return "合适";
    if (pacingFitScore < 45) {
      if (pacingSpeed < (band[0] + band[1]) / 2) return "偏慢";
      return "偏快";
    }
  }
  if (pacingSpeed < band[0]) return "偏慢";
  if (pacingSpeed > band[1]) return "偏快";
  return "合适";
}

/** Segment label between scenes based on pacing_speed delta (not pacing_fit). */
export function pacingSegmentLabel(
  prevSpeed: number | null | undefined,
  currSpeed: number | null | undefined,
  threshold = 8,
): PacingSegmentLabel {
  if (
    typeof prevSpeed !== "number" ||
    typeof currSpeed !== "number" ||
    !Number.isFinite(prevSpeed) ||
    !Number.isFinite(currSpeed)
  ) {
    return "变化不明显";
  }
  const delta = currSpeed - prevSpeed;
  if (delta >= threshold) return "加速";
  if (delta <= -threshold) return "减速";
  return "变化不明显";
}

export function isLegacyUncalibratedVisualization(
  visualization: ReaderJourneyVisualization,
  options: { legacyFlag?: boolean | null; contractVersion?: string | null } = {},
): boolean {
  if (options.legacyFlag === true) return true;
  const version =
    options.contractVersion ??
    visualization.calibration_status?.scene_contract_version ??
    null;
  if (!version) return true;
  if (version.startsWith("2.")) return false;
  return true;
}

export const LEGACY_UNCALIBRATED_BANNER =
  "旧版未校准分析，仅供章内走势参考。";

export const V2_LOCAL_FIXTURE_BANNER =
  "合成测试数据：仅用于验证V2图表、数据透传和诊断规则，不代表真实小说分析结果。";

export const V2_NATIVE_REAL_BANNER = "V2真实正文分析";

export function resolveJourneyTopBanner(
  visualization: ReaderJourneyVisualization,
  options: { legacyFlag?: boolean | null; contractVersion?: string | null } = {},
): string | null {
  const sourceMode = visualization.calibration_status?.source_mode;
  const displayBanner = visualization.calibration_status?.display_banner?.trim();
  if (sourceMode === "v2_native") {
    return displayBanner || V2_NATIVE_REAL_BANNER;
  }
  if (sourceMode === "local_fixture") {
    return displayBanner || V2_LOCAL_FIXTURE_BANNER;
  }
  if (displayBanner === V2_NATIVE_REAL_BANNER) {
    return V2_NATIVE_REAL_BANNER;
  }
  if (displayBanner === V2_LOCAL_FIXTURE_BANNER) {
    return V2_LOCAL_FIXTURE_BANNER;
  }
  if (isLegacyUncalibratedVisualization(visualization, options)) {
    return LEGACY_UNCALIBRATED_BANNER;
  }
  return null;
}
