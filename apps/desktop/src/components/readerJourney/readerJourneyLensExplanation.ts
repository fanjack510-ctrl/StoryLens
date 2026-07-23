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
  { key: "risk", label: "■ 阅读阻力" },
];

/** 钩子回收 lens legend (≤1 row). */
export const HOOK_PAYOFF_LENS_LEGEND: Array<{ key: string; label: string }> = [
  { key: "resolved", label: "━ 已回收" },
  { key: "partial", label: "┄ 部分回收" },
  { key: "unresolved", label: "─ 未回收" },
  { key: "conflict", label: "⚠ 有冲突" },
];

export const READER_JOURNEY_LENS_EXPLANATIONS: Record<
  ObservationLensId,
  ReaderJourneyLensExplanation
> = {
  composite: {
    lens_id: "composite",
    title: "综合阅读",
    chart_title: "综合阅读动力",
    one_line_summary:
      "线越高，读者继续阅读的动力通常越强；低点需要结合场景作用判断，不代表一定写得差。",
    how_to_read: [
      "曲线节点：单个场景或节拍的综合阅读动力。",
      "阶段卡：该阶段的平均或汇总，不等于某一个节点。",
      "章节摘要：整章总体判断，不是单点分数。",
    ],
    y_axis_semantics: "强 · 中 · 弱",
    high_meaning: "继续阅读动力偏强",
    low_meaning: "继续阅读动力偏弱，需结合场景作用判断",
    caution: "数值高低不直接等于作品好坏。",
    legend_items: NUMERIC_LENS_LEGEND,
    metric_id: "engagement",
  },
  plot_progress: {
    lens_id: "plot_progress",
    title: "剧情推进",
    one_line_summary: "故事状态发生了多大变化，包括目标、冲突、信息和人物选择。",
    how_to_read: [
      "高点：故事发生了实质变化。",
      "低点：可能是过渡、停顿或信息不足。",
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
    one_line_summary: "读者有多担心、期待或想知道下一步会发生什么。",
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
    one_line_summary: "读者在当前节点感受到的情绪有多强，只表示强弱，不表示好坏。",
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
    one_line_summary: "叙述推进得有多快。快慢本身没有好坏，要看是否适合当前场景任务。",
    how_to_read: [
      "高点：动作、信息或句子推进更快。",
      "低点：停留、观察或心理描写更多。",
      "必须结合下方“节奏适配”判断是否合适。",
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
    chart_title: "钩子回收总览",
    one_line_summary:
      "先看本章回收结论，再看冲突提醒与总览线；每个钩子只有一个主状态。",
    how_to_read: [
      "实线已回收，虚线部分回收，灰线未回收。",
      "每个钩子独占一行，长说明放清单。",
      "有冲突仍先给主结论，再看冲突提醒。",
    ],
    y_axis_semantics: "钩子提出与回收关系（非分数曲线）",
    high_meaning: "问题已建立或得到回收",
    low_meaning: "问题仍在等待回收",
    caution: "识别存在分歧时，冲突是附加说明，不取代主结论。",
    legend_items: HOOK_PAYOFF_LENS_LEGEND,
    metric_id: "hook",
  },
};

/** Overlay / 对比指标 — uses composite semantics with compare-focused summary. */
export const OVERLAY_COMPARE_TITLE = "对比指标";

export const OVERLAY_COMPARE_SUMMARY =
  "选择第二条指标与当前镜头对照。未选择时不显示对比曲线。";

export const OVERLAY_COMPARE_HOW_TO_READ: [string, string, string] = [
  "两线同步：速度与作用大致一致。",
  "明显分离：需要检查快而无效或慢而有力。",
  "两条线的数值不能简单相减。",
];

export const ALL_METRICS_LABEL = "全部指标";
export const CURRENT_PHASE_LABEL = "当前阶段";
export const FIT_ALL_LABEL = "适配全图";
export const COMPARE_METRIC_LABEL = "对比指标";

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
