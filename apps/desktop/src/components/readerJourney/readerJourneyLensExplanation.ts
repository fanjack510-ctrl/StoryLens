/**
 * Unified Reader Journey lens explanations — presentation only.
 * Single source of truth for ordinary-user titles, summaries, and legends.
 * Does not change formulas, scores, or NarrativeLoopView fact rules.
 */

import type { ObservationLensId } from "./observationLenses";
import type { JourneyCurveMetric } from "../../types/readerJourneyVisualization";

export type ReaderJourneyLensExplanation = {
  lens_id: ObservationLensId;
  title: string;
  /** Optional chart heading; falls back to title. */
  chart_title?: string;
  one_line_summary: string;
  how_to_read: [string, string, string];
  y_axis_semantics: string;
  high_meaning: string;
  low_meaning: string;
  caution: string;
  legend_items: Array<{ key: string; label: string }>;
  /** Stable URL metric paired with this lens (legacy metric param). */
  metric_id: JourneyCurveMetric;
};

/** Numeric lenses: one-line legend (≤1 row). */
export const NUMERIC_LENS_LEGEND: Array<{ key: string; label: string }> = [
  { key: "scene", label: "● 场景" },
  { key: "beat", label: "• 节拍" },
  { key: "selection", label: "┆ 当前选择" },
  // 阅读阻力区间 is gone from the chart; a legend that names a mark nobody draws is worse
  // than no legend — it makes the reader hunt for something that is not there.
  { key: "debt", label: "▬ 悬念欠账" },
];

/** 钩子回收 lens legend (≤1 row). */
export const HOOK_PAYOFF_LENS_LEGEND: Array<{ key: string; label: string }> = [
  { key: "raise", label: "提出疑问" },
  { key: "deepen", label: "加深悬念" },
  { key: "answer", label: "给出回应" },
  { key: "carry", label: "留到下章" },
];

export const READER_JOURNEY_LENS_EXPLANATIONS: Record<
  ObservationLensId,
  ReaderJourneyLensExplanation
> = {
  composite: {
    lens_id: "composite",
    title: "综合阅读",
    chart_title: "综合阅读",
    one_line_summary:
      "综合判断每个场景对故事理解、阅读期待、情绪体验和阅读流畅度的整体贡献；分数高低需要结合场景任务和前后位置判断。",
    how_to_read: [
      "高点：继续阅读动力偏强。",
      "低点：需结合场景作用判断，不代表写得差。",
      "阶段卡显示该阶段汇总，不等于单点。",
    ],
    y_axis_semantics: "综合阅读表现（0—100，辅以强·中·弱）",
    high_meaning: "继续阅读动力偏强",
    low_meaning: "继续阅读动力偏弱，需结合场景作用判断",
    caution: "数值高低不直接等于作品好坏。",
    legend_items: NUMERIC_LENS_LEGEND,
    metric_id: "engagement",
  },
  plot_progress: {
    lens_id: "plot_progress",
    title: "剧情推进",
    one_line_summary:
      "线越高，事件、目标或冲突向前推进得越明显；低点可能是铺垫、停顿或信息消化。",
    how_to_read: [
      "高点：故事发生了实质变化。",
      "低点：可能是铺垫、停顿或信息消化。",
      "速度快不等于剧情推进强。",
    ],
    y_axis_semantics: "故事状态变化幅度",
    high_meaning: "故事发生了实质变化",
    low_meaning: "可能是过渡、停顿或信息不足",
    caution: "数值高低不直接等于作品好坏。",
    legend_items: NUMERIC_LENS_LEGEND,
    metric_id: "curiosity",
  },
  reading_tension: {
    lens_id: "reading_tension",
    title: "阅读张力",
    one_line_summary: "线越高，读者感受到的等待、危险或不确定性越强。",
    how_to_read: [
      "高点：危险、悬念或不确定性增强。",
      "低点：可能是换气或阶段性安全。",
      "持续高位不一定好，需要有松紧变化。",
    ],
    y_axis_semantics: "担心、期待与悬念强弱",
    high_meaning: "危险、悬念或不确定性增强",
    low_meaning: "可能是换气或阶段性安全",
    caution: "数值高低不直接等于作品好坏。",
    legend_items: NUMERIC_LENS_LEGEND,
    metric_id: "tension",
  },
  emotion: {
    lens_id: "emotion",
    title: "情绪强度",
    one_line_summary:
      "线越高，当前节点带来的情绪感受越强，只表示强弱，不表示好坏。",
    how_to_read: [
      "高点：情绪反应强烈。",
      "低点：情绪较平静或尚未建立。",
      "不表示正面情绪或负面情绪。",
    ],
    y_axis_semantics: "情绪强弱（非好坏）",
    high_meaning: "情绪反应强烈",
    low_meaning: "情绪较平静或尚未建立",
    caution: "只表示强弱，不表示正面或负面。",
    legend_items: NUMERIC_LENS_LEGEND,
    metric_id: "arousal",
  },
  pacing: {
    lens_id: "pacing",
    title: "节奏速度",
    one_line_summary: "线越高，叙事推进越快；快慢需要与当前场景任务匹配。",
    how_to_read: [
      "高点：动作、信息或句子推进更快。",
      "低点：停留、观察或心理描写更多。",
      "快慢需与当前场景任务匹配。",
    ],
    y_axis_semantics: "叙述推进快慢",
    high_meaning: "动作、信息或句子推进更快",
    low_meaning: "停留、观察或心理描写更多",
    caution: "适配表示速度是否适合当前场景，不表示与曲线的距离。",
    legend_items: [
      ...NUMERIC_LENS_LEGEND,
      { key: "pacing_fit", label: "适配：合适 / 偏快 / 偏慢 / 无法判断" },
    ],
    metric_id: "engagement",
  },
  hook_payoff: {
    lens_id: "hook_payoff",
    title: "钩子回收",
    chart_title: "钩子总览",
    one_line_summary:
      "查看本章提出了哪些问题、给出了哪些回应，以及留下了什么后续期待。",
    how_to_read: [
      "顶部概览：本章提出、本章回应、继续保留、章末牵引。",
      "场景短标签只表示：提出疑问、加深悬念、给出回应、留到下章。",
      "继续保留是正常跨章状态，不代表失败。",
    ],
    y_axis_semantics: "钩子提出与回应关系（非分数曲线）",
    high_meaning: "问题已提出或得到回应",
    low_meaning: "期待仍留给后续章节",
    caution: "单章未回应不等于异常；重要钩子可跨章保留。",
    legend_items: HOOK_PAYOFF_LENS_LEGEND,
    metric_id: "hook",
  },
};

/** Overlay / 对比分析 — chart tool (not a Lens). */
export const OVERLAY_COMPARE_TITLE = "对比分析";

export const OVERLAY_COMPARE_SUMMARY =
  "选择第二个指标与当前主指标对照。确认后才进入对比模式。";

export const OVERLAY_COMPARE_HOW_TO_READ: [string, string, string] = [
  "绿色实线是当前主指标，紫色虚线是对比指标。",
  "两线同步或分离帮助对照节奏与作用，数值不能简单相减。",
  "可随时更换对比指标或退出对比。",
];

export const ALL_METRICS_LABEL = "全部指标";
export const CURRENT_PHASE_LABEL = "当前阶段";
/** @deprecated Prefer RESET_VIEW_LABEL */
export const FIT_ALL_LABEL = "重置视图";
export const RESET_VIEW_LABEL = "重置视图";
export const COMPARE_METRIC_LABEL = "选择对比指标";
export const EXIT_COMPARE_LABEL = "退出对比";
export const CHANGE_COMPARE_LABEL = "更换指标";
export const START_COMPARE_LABEL = "开始对比";
export const SAME_METRIC_EXIT_MESSAGE = "主指标与对比指标相同，对比模式已结束。";
export const PHASE_PRIMARY_ONLY_HINT_PREFIX = "阶段摘要仅显示主指标：";

export function getLensExplanation(
  lensId: ObservationLensId | string | null | undefined,
): ReaderJourneyLensExplanation {
  const key = (lensId || "composite") as ObservationLensId;
  return READER_JOURNEY_LENS_EXPLANATIONS[key] ?? READER_JOURNEY_LENS_EXPLANATIONS.composite;
}

export function lensIdFromMetric(
  metric: JourneyCurveMetric | string | null | undefined,
): ObservationLensId {
  switch (metric) {
    case "hook":
    case "payoff":
      return "hook_payoff";
    case "arousal":
    case "valence":
      return "emotion";
    case "tension":
      return "reading_tension";
    case "curiosity":
      return "plot_progress";
    case "dropoff_risk":
      return "composite";
    case "engagement":
    default:
      return "composite";
  }
}

export function metricForLens(lensId: ObservationLensId): JourneyCurveMetric {
  return getLensExplanation(lensId).metric_id;
}

export function parseLensParam(value: string | null | undefined): ObservationLensId | null {
  if (!value) return null;
  if (value in READER_JOURNEY_LENS_EXPLANATIONS) {
    return value as ObservationLensId;
  }
  return null;
}

/**
 * Single resolver for active lens from URL.
 * Prefer explicit `lens`; fall back to legacy `metric` only when lens is absent/invalid.
 */
export function resolveJourneyLensFromSearch(
  lensParam: string | null | undefined,
  metricParam: string | null | undefined,
  fallback: ObservationLensId = "composite",
): ObservationLensId {
  return parseLensParam(lensParam) ?? lensIdFromMetric(metricParam) ?? fallback;
}

/**
 * Canonical metric for a lens (URL write). When lens is authoritative and metric conflicts,
 * metric is rewritten to this value — never the reverse for a valid lens.
 */
export function canonicalMetricForLens(lensId: ObservationLensId): JourneyCurveMetric {
  return metricForLens(lensId);
}

/** Drop tautological continue-drive copy like「继续阅读」。 */
export function isTautologyContinueDrive(text: string | null | undefined): boolean {
  if (!text) return true;
  const normalized = text.replace(/\s+/g, "").trim();
  if (!normalized) return true;
  return /^(继续阅读|继续读下去|继续往下读|想继续读|继续读|保持阅读)$/.test(normalized);
}

/** Safe short title — never mid-character truncate without ellipsis. */
export function shortPlainTitle(text: string | null | undefined, maxChars = 18): string {
  const value = (text || "").trim().replace(/[?？]+$/g, (m) => (m.length > 1 ? "？" : m));
  if (!value) return "未命名";
  if (value.length <= maxChars) return value;
  return `${value.slice(0, Math.max(1, maxChars - 1))}…`;
}
