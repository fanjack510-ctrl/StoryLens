/** Presentation-only label maps for Reader Journey UI. No data semantics. */

import type { JourneyCurveMetric } from "../../types/readerJourneyVisualization";

export const METRIC_LABELS_ZH: Record<JourneyCurveMetric, string> = {
  engagement: "阅读牵引",
  valence: "情绪正负",
  arousal: "情绪唤醒",
  curiosity: "好奇",
  tension: "紧张",
  payoff: "回报",
  hook: "钩子",
  dropoff_risk: "掉线风险",
};

/** Compact switcher labels (2.5C). Emotion maps to valence/arousal submenu. */
export const COMPACT_METRIC_SWITCHER: {
  key: JourneyCurveMetric | "emotion";
  label: string;
}[] = [
  { key: "engagement", label: "阅读牵引" },
  { key: "emotion", label: "情绪" },
  { key: "curiosity", label: "好奇" },
  { key: "tension", label: "紧张" },
  { key: "payoff", label: "回报" },
  { key: "hook", label: "钩子" },
  { key: "dropoff_risk", label: "风险" },
];

/** Quick metric shortcuts (2.5.2). Underlying metrics unchanged. */
export const QUICK_METRIC_KEYS: JourneyCurveMetric[] = [
  "engagement",
  "curiosity",
  "tension",
];

/** Extra metrics behind「更多指标」. */
export const MORE_METRIC_KEYS: JourneyCurveMetric[] = [
  "payoff",
  "hook",
  "dropoff_risk",
  "valence",
  "arousal",
];

/** Single metric selector menu (2.6). Underlying metric values unchanged. */
export const ALL_METRIC_KEYS: JourneyCurveMetric[] = [
  "engagement",
  "curiosity",
  "tension",
  "payoff",
  "hook",
  "dropoff_risk",
  "valence",
  "arousal",
];

export const ROLE_LABELS_ZH: Record<string, string> = {
  core: "核心节点",
  secondary: "次级节点",
  beat: "节拍节点",
};

/** Internal lifecycle / status enums → Chinese UI labels. */
export const LIFECYCLE_STATUS_ZH: Record<string, string> = {
  carried_from_previous: "承接前文",
  created_here: "本场新增",
  created: "本场新增",
  carried: "承接前文",
  transformed: "问题升级",
  partially_answered: "部分回答",
  answered: "已回答",
  deferred: "暂时搁置",
  dropped: "后续未承接",
  open: "场末开放",
};

/** Question Inspector lifecycle → compact Chinese (2.7). */
export const QUESTION_LIFECYCLE_ZH: Record<string, string> = {
  created: "新建",
  created_here: "新建",
  carried: "延续",
  carried_from_previous: "延续",
  partially_answered: "部分回答",
  answered: "回答",
  transformed: "转化",
  open: "悬而未决",
  deferred: "悬而未决",
  dropped: "悬而未决",
};

export function roleLabelZh(role: string | undefined | null): string {
  if (!role) return "节点";
  return ROLE_LABELS_ZH[role] ?? role;
}

export function lifecycleLabelZh(status: string | undefined | null): string {
  if (!status) return "—";
  return LIFECYCLE_STATUS_ZH[status] ?? status;
}

export function questionLifecycleZh(status: string | undefined | null): string {
  if (!status) return "悬而未决";
  return QUESTION_LIFECYCLE_ZH[status] ?? lifecycleLabelZh(status);
}

export const PAYOFF_TYPE_ZH: Record<string, string> = {
  mystery: "悬念兑现",
  emotional: "情绪回报",
  information: "信息回报",
  relationship: "关系回报",
  plot: "情节回报",
  stage: "阶段回报",
};

export const HOOK_TYPE_ZH: Record<string, string> = {
  mystery: "悬念钩子",
  threat: "威胁钩子",
  emotional: "情绪钩子",
  information: "信息钩子",
  chapter_end: "章尾钩子",
};

export const SCORE_TOOLTIPS_ZH: Record<string, string> = {
  engagement: "预测读者对本场的持续阅读牵引强度",
  curiosity: "本场激发的好奇与求知驱动",
  tension: "本场紧张与冲突强度",
  payoff: "本场兑现信息/情绪回报的强度",
  hook: "本场留下继续阅读钩子的强度",
  dropoff_risk: "本场导致读者掉线的风险",
};

/** Short one-line hints for MetricSelectorPanel (v4.2). Presentation only. */
export const METRIC_HINTS_ZH: Record<JourneyCurveMetric, string> = {
  engagement: "持续阅读牵引强度",
  curiosity: "好奇与求知驱动",
  tension: "紧张与冲突强度",
  payoff: "信息或情绪回报",
  hook: "继续阅读的钩子",
  dropoff_risk: "读者掉线风险",
  valence: "情绪正负倾向",
  arousal: "情绪唤醒程度",
};

export function payoffTypeZh(type: string | undefined | null): string {
  if (!type) return "回报";
  return PAYOFF_TYPE_ZH[type] ?? type;
}

export function hookTypeZh(type: string | undefined | null): string {
  if (!type) return "钩子";
  return HOOK_TYPE_ZH[type] ?? type;
}
