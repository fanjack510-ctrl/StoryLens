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
  dropoff_risk: "流失风险",
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
  { key: "dropoff_risk", label: "流失风险" },
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
  dropoff_risk: "连续缺少回报、节奏骤降或认知负担过高，可能降低读者继续阅读的意愿。",
};

/** Short one-line hints for MetricSelectorPanel (v4.2). Presentation only. */
export const METRIC_HINTS_ZH: Record<JourneyCurveMetric, string> = {
  engagement: "持续阅读牵引强度",
  curiosity: "好奇与求知驱动",
  tension: "紧张与冲突强度",
  payoff: "信息或情绪回报",
  hook: "继续阅读的钩子",
  dropoff_risk: "连续缺少回报、节奏骤降或认知负担过高，可能降低读者继续阅读的意愿。",
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

/** Primary metric keys for the Reader Journey segmented control (presentation only). */
export const PRIMARY_JOURNEY_METRICS = [
  "engagement",
  "arousal",
  "tension",
  "hook",
] as const satisfies readonly JourneyCurveMetric[];

/** User-facing primary metric labels (does not rename underlying metric keys). */
export const PRIMARY_METRIC_LABELS_ZH: Record<(typeof PRIMARY_JOURNEY_METRICS)[number], string> = {
  engagement: "阅读牵引",
  arousal: "情绪强度",
  tension: "节奏变化",
  hook: "钩子强度",
};

export const PRIMARY_METRIC_HINTS_ZH: Record<(typeof PRIMARY_JOURNEY_METRICS)[number], string> = {
  engagement: "读者继续阅读的动力",
  arousal: "场景带来的情绪波动",
  tension: "叙事推进速度与密度",
  hook: "悬念、问题和期待程度",
};

/** Fixed phase role explanations when backend summary is missing (not plot conclusions). */
export const PHASE_ROLE_FALLBACK_ZH: Record<string, string> = {
  入: "建立背景、人物与阅读期待",
  入局: "建立背景、人物与阅读期待",
  entry: "建立背景、人物与阅读期待",
  Entry: "建立背景、人物与阅读期待",
  推: "推动事件发展与核心冲突",
  推进: "推动事件发展与核心冲突",
  development: "推动事件发展与核心冲突",
  Development: "推动事件发展与核心冲突",
  转: "出现信息变化或事件升级",
  转折: "出现信息变化或事件升级",
  turn: "出现信息变化或事件升级",
  Turn: "出现信息变化或事件升级",
  收: "形成阶段结果并留下后续期待",
  收束: "形成阶段结果并留下后续期待",
  resolution: "形成阶段结果并留下后续期待",
  Resolution: "形成阶段结果并留下后续期待",
};

const PHASE_SHORT_TO_FULL: Record<string, string> = {
  入: "入局",
  推: "推进",
  转: "转折",
  收: "收束",
  entry: "入局",
  Entry: "入局",
  development: "推进",
  Development: "推进",
  turn: "转折",
  Turn: "转折",
  resolution: "收束",
  Resolution: "收束",
};

function isDirtyDisplayToken(value: string): boolean {
  return /^(undefined|null|NaN|\[object Object\])$/i.test(value.trim());
}

/** Empty / punctuation-only / dirty tokens are not usable phase descriptions. */
export function isEffectivePhaseSummary(raw: string | null | undefined): boolean {
  if (raw == null) return false;
  const trimmed = String(raw).trim();
  if (!trimmed || isDirtyDisplayToken(trimmed)) return false;
  // Lone period / ellipsis / dashes must never appear as phase copy.
  if (
    trimmed === "." ||
    trimmed === "..." ||
    trimmed === "…" ||
    trimmed === "。。。" ||
    /^[.。…·•\-–—_*…]+$/.test(trimmed)
  ) {
    return false;
  }
  return true;
}

/** Format raw phase title/key for ordinary UI. Never invents plot conclusions. */
export function formatJourneyPhaseLabel(raw: string | null | undefined): string {
  if (raw == null) return "未知阶段";
  const trimmed = String(raw).trim();
  if (!trimmed || isDirtyDisplayToken(trimmed)) return "未知阶段";
  if (PHASE_SHORT_TO_FULL[trimmed]) return PHASE_SHORT_TO_FULL[trimmed];
  const lower = trimmed.toLowerCase();
  if (PHASE_SHORT_TO_FULL[lower]) return PHASE_SHORT_TO_FULL[lower];
  return trimmed;
}

export function formatJourneyPhaseFallbackSummary(raw: string | null | undefined): string {
  if (raw == null) return "选择阶段或节点查看详细分析";
  const trimmed = String(raw).trim();
  const full = formatJourneyPhaseLabel(trimmed);
  return (
    PHASE_ROLE_FALLBACK_ZH[trimmed] ||
    PHASE_ROLE_FALLBACK_ZH[full] ||
    PHASE_ROLE_FALLBACK_ZH[trimmed.toLowerCase()] ||
    "选择阶段或节点查看详细分析"
  );
}

/** Prefer real summary; otherwise fixed structural fallback. Never returns "." alone. */
export function resolvePhaseSummaryDisplay(
  summary: string | null | undefined,
  title: string | null | undefined,
): string {
  if (isEffectivePhaseSummary(summary)) return String(summary).trim();
  return formatJourneyPhaseFallbackSummary(title);
}

/** Metric key → user label. Unknown keys → 未知指标 (never undefined/NaN). */
export function formatJourneyMetricLabel(metric: string | null | undefined): string {
  if (metric == null) return "未知指标";
  const key = String(metric).trim();
  if (!key || isDirtyDisplayToken(key)) return "未知指标";
  if (key in PRIMARY_METRIC_LABELS_ZH) {
    return PRIMARY_METRIC_LABELS_ZH[key as keyof typeof PRIMARY_METRIC_LABELS_ZH];
  }
  if (key in METRIC_LABELS_ZH) {
    return METRIC_LABELS_ZH[key as JourneyCurveMetric];
  }
  return "未知指标";
}

export function formatJourneyMetricHint(metric: string | null | undefined): string | null {
  if (metric == null) return null;
  const key = String(metric).trim();
  if (key in PRIMARY_METRIC_HINTS_ZH) {
    return PRIMARY_METRIC_HINTS_ZH[key as keyof typeof PRIMARY_METRIC_HINTS_ZH];
  }
  if (key in METRIC_HINTS_ZH) return METRIC_HINTS_ZH[key as JourneyCurveMetric];
  if (key in SCORE_TOOLTIPS_ZH) return SCORE_TOOLTIPS_ZH[key];
  return null;
}

export function formatJourneySelectionType(kind: string | null | undefined): string {
  if (kind == null) return "未知";
  const key = String(kind).trim().toLowerCase();
  const map: Record<string, string> = {
    phase: "阶段",
    scene: "场景",
    node: "节点",
    curve: "曲线",
    metric: "指标",
    question: "问题",
    hook: "钩子",
    payoff: "回报",
    risk: "流失风险",
  };
  return map[key] ?? "未知";
}

/** Raw risk_type codes → Chinese (presentation only; keys unchanged). */
export const RISK_TYPE_LABELS_ZH: Record<string, string> = {
  consecutive_no_payoff: "连续场景缺少有效回报",
  low_engagement: "阅读牵引持续偏低",
  high_cognitive_load: "认知负担偏高",
  dropped_question: "高强度问题未承接",
  over_fragmented_beats: "节拍过碎，节奏可能断裂",
  slow_progress: "推进过慢",
  weak_hook: "钩子偏弱",
  over_explanation: "解释过多",
  repetition: "重复拖沓",
  fragmented_scene: "场景过碎",
  low_payoff: "回报不足",
  other: "其他流失风险",
};

export function formatJourneyRiskTypeLabel(riskType: string | null | undefined): string {
  if (riskType == null) return "流失风险";
  const key = String(riskType).trim();
  if (!key) return "流失风险";
  return RISK_TYPE_LABELS_ZH[key] ?? key;
}

export function formatJourneyRiskSummary(input: {
  risk_type?: string | null;
  summary?: string | null;
  start_scene_ordinal?: number | null;
  end_scene_ordinal?: number | null;
  span?: number | null;
}): string {
  const typeLabel = formatJourneyRiskTypeLabel(input.risk_type);
  const start = input.start_scene_ordinal;
  const end = input.end_scene_ordinal ?? start;
  const span =
    typeof input.span === "number" && Number.isFinite(input.span)
      ? Math.trunc(input.span)
      : start != null && end != null
        ? Math.max(1, Math.trunc(end) - Math.trunc(start) + 1)
        : null;

  if (input.risk_type === "consecutive_no_payoff" && start != null && end != null) {
    const spanText = span != null && span > 1 ? `连续${span}个场景` : "连续场景";
    return `场景 ${start}—${end} ${spanText}缺少明显回报，可能降低阅读动力。`;
  }

  const raw = typeof input.summary === "string" ? input.summary.trim() : "";
  if (raw && !/^[a-z][a-z0-9_]*$/i.test(raw)) {
    return raw
      .replace(/\bScene\b/g, "场景")
      .replace(/\bengagement\b/gi, "阅读牵引")
      .replace(/\bpayoff\b/gi, "回报")
      .replace(/\bBeat\b/g, "节拍");
  }
  if (start != null && end != null) {
    return `场景 ${start}—${end}：${typeLabel}。`;
  }
  return typeLabel;
}

/** Compact score nouns for phase/scene cards (presentation only). */
export const METRIC_SCORE_SHORT_ZH: Record<JourneyCurveMetric, string> = {
  engagement: "牵引",
  valence: "正负",
  arousal: "唤醒",
  curiosity: "好奇",
  tension: "节奏",
  payoff: "回报",
  hook: "钩子",
  dropoff_risk: "风险",
};

/** e.g. 「节奏 66」「钩子 48」— never bare numbers. */
export function formatMetricScoreLabel(
  metric: JourneyCurveMetric,
  value: number | null | undefined,
): string {
  if (value == null || !Number.isFinite(value)) return `${METRIC_SCORE_SHORT_ZH[metric]} —`;
  return `${METRIC_SCORE_SHORT_ZH[metric]} ${Math.round(value)}`;
}

export function formatPhaseMetricScoreLabel(
  metric: string | null | undefined,
  value: unknown,
): string {
  return `${formatJourneyMetricLabel(metric)} ${formatJourneyScore(value)}`;
}

export function formatJourneyStatus(status: string | null | undefined): string {
  if (status == null) return "—";
  const key = String(status).trim();
  if (!key || isDirtyDisplayToken(key)) return "—";
  const map: Record<string, string> = {
    succeeded: "已完成",
    completed: "已完成",
    running: "生成中",
    pending: "等待生成",
    queued: "排队中",
    failed: "生成失败",
    scene_profiles_pending: "等待分析场景特征",
    scene_profiles_running: "正在分析场景特征",
    scene_profiles_completed: "场景特征分析完成",
    scene_profiles_partial: "部分完成",
    chapter_synthesis_pending: "等待汇总章节旅程",
    chapter_synthesis_running: "正在汇总章节旅程",
    journey_pending: "等待生成阅读旅程",
    journey_running: "正在生成阅读旅程",
    budget_blocked: "额度不足",
    none: "尚未生成",
    empty: "暂无结果",
    cancelled: "已取消",
  };
  const mapped = map[key] ?? map[key.toLowerCase()];
  if (mapped) return mapped;
  // Never surface raw snake_case keys in ordinary UI.
  if (/^[a-z][a-z0-9_]*$/i.test(key)) return "处理中";
  return "未知状态";
}

/** Scene ordinal → S04 style label for ordinary UI. */
export function formatJourneySceneRangeLabel(
  start: number | null | undefined,
  end?: number | null,
): string {
  const fmt = (n: number | null | undefined) => {
    if (typeof n !== "number" || !Number.isFinite(n) || n <= 0) return null;
    return `S${String(Math.trunc(n)).padStart(2, "0")}`;
  };
  const a = fmt(start);
  if (!a) return "—";
  const b = end == null || end === start ? null : fmt(end);
  return b ? `${a}—${b}` : a;
}

/** Safe numeric display; missing / non-finite → em dash. */
export function formatJourneyScore(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(Math.round(value));
  }
  if (typeof value === "string" && value.trim() && !isDirtyDisplayToken(value)) {
    const n = Number(value);
    if (Number.isFinite(n)) return String(Math.round(n));
  }
  return "—";
}

export function formatJourneySceneLabel(
  ordinal: number | null | undefined,
  title?: string | null,
): string {
  const hasOrdinal =
    typeof ordinal === "number" && Number.isFinite(ordinal) && ordinal > 0;
  const ordinalText = hasOrdinal
    ? `场景 ${String(Math.trunc(ordinal)).padStart(2, "0")}`
    : "场景";
  const name = typeof title === "string" ? title.trim() : "";
  if (name && !isDirtyDisplayToken(name) && !/^Scene\s*#?undefined$/i.test(name)) {
    return `${ordinalText} · ${name}`;
  }
  return ordinalText;
}
