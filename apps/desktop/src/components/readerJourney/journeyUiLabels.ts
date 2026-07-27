/** Presentation-only label maps for Reader Journey UI. No data semantics. */

import type { JourneyCurveMetric } from "../../types/readerJourneyVisualization";

export const METRIC_LABELS_ZH: Record<JourneyCurveMetric, string> = {
  engagement: "综合阅读",
  valence: "情绪正负",
  arousal: "情绪强度",
  curiosity: "剧情推进",
  tension: "阅读张力",
  payoff: "回报",
  hook: "钩子",
  dropoff_risk: "阅读阻力",
};

/** Compact switcher labels (2.5C). Emotion maps to valence/arousal submenu. */
export const COMPACT_METRIC_SWITCHER: {
  key: JourneyCurveMetric | "emotion";
  label: string;
}[] = [
  { key: "engagement", label: "综合阅读" },
  { key: "emotion", label: "情绪" },
  { key: "curiosity", label: "剧情推进" },
  { key: "tension", label: "阅读张力" },
  { key: "payoff", label: "回应" },
  { key: "hook", label: "悬念" },
  { key: "dropoff_risk", label: "阅读阻力" },
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
  core: "核心场景",
  secondary: "过渡场景",
  beat: "过渡",
};

/** Beat / scene_role ordinary qualifiers (never show English keys). */
export const SCENE_ROLE_LABELS_ZH: Record<string, string> = {
  setup: "铺垫",
  escalation: "升级",
  investigation: "追查",
  reveal: "信息揭示",
  information: "信息揭示",
  climax: "高潮",
  aftermath: "收束",
  transition: "过渡",
  open_end: "开放收束",
  closed_end: "封闭收束",
  beat: "过渡",
  core: "核心场景",
  secondary: "过渡场景",
};

/** Ordinary response-degree labels. */
export const RESPONSE_DEGREE_LABELS_ZH: Record<string, string> = {
  partial: "部分回报",
  full: "明确回报",
  reversal: "反转回报",
  transformed: "转化回报",
  transformed_question: "转化回报",
  score_inferred: "候选回报",
};

export const READING_RESISTANCE_HOVER =
  "这里可能让部分读者暂时失去继续阅读的动力。";

export const READING_RESISTANCE_REASON_ZH: Record<string, string> = {
  weak_progress: "推进较弱",
  insufficient_response: "回应不足",
  long_transition: "过渡偏长",
  information_repeat: "信息重复",
  emotion_break: "情绪中断",
  unclear_goal: "目标不清",
  over_explanation: "说明过多",
  stalled_suspense: "悬念停滞",
  over_fragmented: "场景可能切得过细",
  推进偏弱: "推进较弱",
  推进较弱: "推进较弱",
  回应不足: "回应不足",
  过渡偏长: "过渡偏长",
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
  if (!role) return "场景";
  const key = String(role).trim().toLowerCase();
  return ROLE_LABELS_ZH[key] ?? SCENE_ROLE_LABELS_ZH[key] ?? "场景";
}

export function sceneRoleLabelZh(role: string | undefined | null): string {
  if (!role) return "";
  const key = String(role).trim().toLowerCase();
  return SCENE_ROLE_LABELS_ZH[key] ?? ROLE_LABELS_ZH[key] ?? "";
}

export function responseDegreeLabelZh(degree: string | undefined | null): string {
  if (!degree) return "回应";
  const key = String(degree).trim().toLowerCase();
  return RESPONSE_DEGREE_LABELS_ZH[key] ?? degree;
}

/** Left-rail / marker label: 阅读阻力 or 阅读阻力｜主原因. */
export function formatReadingResistanceLabel(
  reasonCodeOrZh?: string | null,
): string {
  if (!reasonCodeOrZh) return "阅读阻力";
  const key = String(reasonCodeOrZh).trim();
  const reason = READING_RESISTANCE_REASON_ZH[key] ?? (key.includes("｜") ? null : key);
  if (!reason || reason === "阅读阻力") return "阅读阻力";
  const short = reason.replace(/^阅读阻力[｜|]/, "").trim();
  return short ? `阅读阻力｜${short}` : "阅读阻力";
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
  mystery: "悬念回报",
  emotional: "情绪回报",
  information: "信息回报",
  relationship: "关系回报",
  plot: "情节回报",
  stage: "阶段回报",
  partial: "部分回报",
  full: "明确回报",
  reversal: "反转回报",
  transformed_question: "转化为新问题",
};

export const HOOK_TYPE_ZH: Record<string, string> = {
  mystery: "钩子",
  threat: "威胁钩子",
  emotional: "情绪钩子",
  information: "信息钩子",
  chapter_end: "章末钩子",
  danger: "危险钩子",
};

export const SCORE_TOOLTIPS_ZH: Record<string, string> = {
  engagement: "读者继续阅读的动力",
  curiosity: "故事状态变化幅度",
  tension: "担心、期待与悬念强弱",
  payoff: "本场对前文问题的回报强度",
  hook: "本场建立的钩子强度",
  dropoff_risk: READING_RESISTANCE_HOVER,
};

/** Short one-line hints for MetricSelectorPanel (v4.2). Presentation only. */
export const METRIC_HINTS_ZH: Record<JourneyCurveMetric, string> = {
  engagement: "继续阅读动力",
  curiosity: "剧情推进幅度",
  tension: "阅读张力强弱",
  payoff: "对前文问题的回应",
  hook: "新建立的悬念",
  dropoff_risk: READING_RESISTANCE_HOVER,
  valence: "情绪正负倾向",
  arousal: "情绪强弱",
};

export function payoffTypeZh(type: string | undefined | null): string {
  if (!type) return "回应";
  return PAYOFF_TYPE_ZH[type] ?? responseDegreeLabelZh(type);
}

export function hookTypeZh(type: string | undefined | null): string {
  if (!type) return "悬念";
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
  engagement: "综合阅读",
  arousal: "情绪强度",
  tension: "阅读张力",
  hook: "钩子",
};

export const PRIMARY_METRIC_HINTS_ZH: Record<(typeof PRIMARY_JOURNEY_METRICS)[number], string> = {
  engagement: "读者继续阅读的动力",
  arousal: "场景带来的情绪强弱",
  tension: "担心、期待与悬念强弱",
  hook: "钩子、问题和期待程度",
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
    hook: "悬念",
    payoff: "回应",
    risk: "阅读阻力",
  };
  return map[key] ?? "未知";
}

/** Raw risk_type codes → Chinese (presentation only; keys unchanged). */
export const RISK_TYPE_LABELS_ZH: Record<string, string> = {
  consecutive_no_payoff: "连续场景缺少有效回应",
  open_narrative_loop: "开放问题尚未回应",
  narrative_loop_inconsistent: "识别存在分歧",
  low_engagement: "综合阅读持续偏低",
  low_reading_momentum: "阅读动力持续偏低",
  momentum_decline: "阅读动力连续下降",
  unpaid_hook: "高悬念未回应",
  high_dropoff_risk: "阅读阻力偏高",
  reading_resistance: "阅读阻力",
  high_cognitive_load: "认知负担偏高",
  dropped_question: "高强度问题未承接",
  over_fragmented_beats: "场景可能切得过细",
  slow_progress: "推进过慢",
  weak_hook: "悬念偏弱",
  over_explanation: "说明过多",
  repetition: "信息重复",
  fragmented_scene: "场景可能切得过细",
  low_payoff: "回应不足",
  other: "其他阅读阻力",
};

export function formatJourneyRiskTypeLabel(riskType: string | null | undefined): string {
  if (riskType == null) return "阅读阻力";
  const key = String(riskType).trim();
  if (!key) return "阅读阻力";
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
    return `场景 ${start}—${end} ${spanText}缺少明显回应，可能降低阅读动力。`;
  }
  if (input.risk_type === "open_narrative_loop" || input.risk_type === "narrative_loop_inconsistent") {
    const rawLoop = typeof input.summary === "string" ? input.summary.trim() : "";
    if (rawLoop) return rawLoop;
  }

  const raw = typeof input.summary === "string" ? input.summary.trim() : "";
  if (raw && !/^[a-z][a-z0-9_]*$/i.test(raw)) {
    return raw
      .replace(/\bScene\b/g, "场景")
      .replace(/\breading_momentum\b/gi, "阅读动力")
      .replace(/\bengagement\b/gi, "阅读动力")
      .replace(/\bpayoff\b/gi, "回应")
      .replace(/\bhook\b/gi, "悬念")
      .replace(/\bBeat\b/g, "节拍")
      .replace(/流失风险/g, "阅读阻力")
      .replace(/钩子/g, "悬念")
      .replace(/回报/g, "回应");
  }
  if (start != null && end != null) {
    return `场景 ${start}—${end}：${typeLabel}。`;
  }
  return typeLabel;
}

/** Compact score nouns for phase/scene cards (presentation only). */
export const METRIC_SCORE_SHORT_ZH: Record<JourneyCurveMetric, string> = {
  engagement: "综合",
  valence: "正负",
  arousal: "情绪",
  curiosity: "推进",
  tension: "张力",
  payoff: "回报",
  hook: "钩子",
  dropoff_risk: "阻力",
};

/** e.g. 「张力 66」「悬念 48」— never bare numbers. */
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
    ? `场景${String(Math.trunc(ordinal)).padStart(2, "0")}`
    : "场景";
  const name = typeof title === "string" ? title.trim() : "";
  if (name && !isDirtyDisplayToken(name) && !/^Scene\s*#?undefined$/i.test(name)) {
    return `${ordinalText} · ${name}`;
  }
  return ordinalText;
}

/** Ordinary Scene/Beat node title — never "Scene 7 · 节拍节点". */
export function formatJourneyNodeLabel(
  ordinal: number | null | undefined,
  options: {
    role?: string | null;
    sceneRole?: string | null;
    nodeType?: string | null;
  } = {},
): string {
  const hasOrdinal =
    typeof ordinal === "number" && Number.isFinite(ordinal) && ordinal > 0;
  const pad = hasOrdinal ? String(Math.trunc(ordinal!)).padStart(2, "0") : null;
  const role = String(options.role || options.nodeType || "").toLowerCase();
  const isBeat = role === "beat" || options.nodeType === "beat";
  const qualifier =
    sceneRoleLabelZh(options.sceneRole) ||
    (isBeat ? "过渡" : roleLabelZh(options.role || (isBeat ? "beat" : "core")));
  if (!pad) {
    return isBeat ? `节拍 · ${qualifier}` : `场景 · ${qualifier}`;
  }
  return isBeat ? `节拍${pad} · ${qualifier}` : `场景${pad} · ${qualifier}`;
}
