/**
 * Unified Reader Journey lens explanations — presentation only.
 * Does not change formulas, scores, or NarrativeLoopView fact rules.
 */

import type { ObservationLensId } from "./observationLenses";
import type { JourneyCurveMetric } from "../../types/readerJourneyVisualization";

export type ReaderJourneyLensExplanation = {
  lens_id: ObservationLensId;
  title: string;
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

const NUMERIC_LEGEND: Array<{ key: string; label: string }> = [
  { key: "scene", label: "● 场景" },
  { key: "beat", label: "• 节拍" },
  { key: "selection", label: "┆ 当前选择" },
  { key: "risk", label: "■ 阅读阻力" },
];

export const READER_JOURNEY_LENS_EXPLANATIONS: Record<
  ObservationLensId,
  ReaderJourneyLensExplanation
> = {
  composite: {
    lens_id: "composite",
    title: "综合阅读动力",
    one_line_summary: "读者是否愿意继续往下读。线越高，继续阅读的动力通常越强。",
    how_to_read: [
      "高点：当前节点更容易吸引继续阅读。",
      "低点：需要检查，但不代表一定写得差。",
      "要结合剧情推进、张力和回报一起判断。",
    ],
    y_axis_semantics: "继续阅读动力强弱",
    high_meaning: "当前节点更容易吸引继续阅读",
    low_meaning: "继续阅读动力偏弱，需要结合上下文检查",
    caution: "数值高低不直接等于作品好坏。",
    legend_items: NUMERIC_LEGEND,
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
    legend_items: NUMERIC_LEGEND,
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
    legend_items: NUMERIC_LEGEND,
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
    legend_items: NUMERIC_LEGEND,
    metric_id: "arousal",
  },
  pacing: {
    lens_id: "pacing",
    title: "节奏速度",
    one_line_summary: "叙述推进得有多快。快慢本身没有好坏，要看是否适合当前场景任务。",
    how_to_read: [
      "高点：动作、信息或句子推进更快。",
      "低点：停留、观察或心理描写更多。",
      "必须结合“节奏适配”判断是否合适。",
    ],
    y_axis_semantics: "叙述推进快慢",
    high_meaning: "动作、信息或句子推进更快",
    low_meaning: "停留、观察或心理描写更多",
    caution: "节奏适配是分类判断，不是与主线的数值距离。",
    legend_items: [
      ...NUMERIC_LEGEND,
      { key: "pacing_fit", label: "适配轨：合适 / 偏快 / 偏慢" },
    ],
    metric_id: "engagement",
  },
  hook_payoff: {
    lens_id: "hook_payoff",
    title: "钩子与回报",
    one_line_summary:
      "钩子提出读者想知道的问题，回报给出答案、结果或新的变化。连线表示它们之间的承接。",
    how_to_read: [
      "上轨表示读者开始等待的答案。",
      "下轨表示后续给出的回应。",
      "没有连线的问题仍然开放，不一定代表缺陷。",
    ],
    y_axis_semantics: "问题建立与回应关系（非双分数曲线）",
    high_meaning: "问题已建立或得到回应",
    low_meaning: "问题仍在等待回应",
    caution: "当前关系识别不一致时，不作为确定结论。",
    legend_items: [
      { key: "new_hook", label: "● 新钩子" },
      { key: "partial", label: "◐ 部分回应" },
      { key: "full", label: "● 完整兑现" },
      { key: "reversal", label: "◆ 反转式兑现" },
      { key: "transformed", label: "↗ 转化为新问题" },
      { key: "link", label: "─ 承接关系" },
    ],
    metric_id: "hook",
  },
};

/** Overlay-compare uses composite semantics with a compare-focused summary. */
export const OVERLAY_COMPARE_SUMMARY =
  "比较两个指标是否同步，例如写得很快，读者动力是否真的提高。";

export const OVERLAY_COMPARE_HOW_TO_READ: [string, string, string] = [
  "两线同步：速度与作用大致一致。",
  "明显分离：需要检查快而无效或慢而有力。",
  "两条线的数值不能简单相减。",
];

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
