/**
 * VIP feature-key registry and unified feature gate.
 *
 * Pages must call hasFeature(featureKey) instead of scattering `if (isVip)`.
 * This stage never locks shipped Community features: registry entries are either
 * free-available or not-enabled (not yet shipped), never vip-locked for product UI.
 */

export const FEATURE_KEYS = [
  "batch_analysis",
  "novel_rhythm_map",
  "character_arc",
  "foreshadow_tracking",
  "novel_comparison",
  "advanced_report",
  "inspiration_center",
] as const;

export type FeatureKey = (typeof FEATURE_KEYS)[number];

/**
 * Phase access for this foundation stage:
 * - free: callable / treated as available without VIP
 * - not_enabled: registered for future VIP work; not shipped, not a lock on current UI
 */
export type FeaturePhaseAccess = "free" | "not_enabled";

export type FeatureDefinition = {
  key: FeatureKey;
  label: string;
  description: string;
  phaseAccess: FeaturePhaseAccess;
};

export const FEATURE_REGISTRY: Record<FeatureKey, FeatureDefinition> = {
  batch_analysis: {
    key: "batch_analysis",
    label: "批量分析",
    description: "对多章或全书批量运行分析任务。",
    phaseAccess: "not_enabled",
  },
  novel_rhythm_map: {
    key: "novel_rhythm_map",
    label: "全书节奏图",
    description: "跨章节节奏与张力可视化。",
    phaseAccess: "not_enabled",
  },
  character_arc: {
    key: "character_arc",
    label: "角色弧光",
    description: "角色成长与关系轨迹追踪。",
    phaseAccess: "not_enabled",
  },
  foreshadow_tracking: {
    key: "foreshadow_tracking",
    label: "伏笔追踪",
    description: "伏笔埋设与回收网络。",
    phaseAccess: "not_enabled",
  },
  novel_comparison: {
    key: "novel_comparison",
    label: "作品对照",
    description: "多作品结构与节奏对照。",
    phaseAccess: "not_enabled",
  },
  advanced_report: {
    key: "advanced_report",
    label: "进阶报告",
    description: "更完整的结构化分析报告导出。",
    phaseAccess: "not_enabled",
  },
  inspiration_center: {
    key: "inspiration_center",
    label: "灵感中心",
    description: "基于分析结果的灵感与改写建议入口。",
    phaseAccess: "not_enabled",
  },
};

export type FeatureGateResult = {
  /** Whether the feature may be invoked. */
  allowed: boolean;
  /** free = available without VIP; not_enabled = not shipped this stage. */
  status: FeaturePhaseAccess;
  definition: FeatureDefinition;
};

export function isFeatureKey(value: string): value is FeatureKey {
  return (FEATURE_KEYS as readonly string[]).includes(value);
}

/**
 * Unified feature gate. Does not inspect VIP status in this stage so existing
 * Community flows cannot be locked by license state.
 *
 * Unknown keys are treated as not_enabled (not VIP-locked).
 */
export function hasFeature(featureKey: FeatureKey | string): FeatureGateResult {
  if (!isFeatureKey(featureKey)) {
    const unknown: FeatureDefinition = {
      key: "batch_analysis",
      label: String(featureKey),
      description: "未注册的功能键（本阶段按未启用处理，不作为 VIP 锁定）。",
      phaseAccess: "not_enabled",
    };
    return { allowed: false, status: "not_enabled", definition: unknown };
  }
  const definition = FEATURE_REGISTRY[featureKey];
  if (definition.phaseAccess === "free") {
    return { allowed: true, status: "free", definition };
  }
  return { allowed: false, status: "not_enabled", definition };
}

export function listVipFeatureDefinitions(): FeatureDefinition[] {
  return FEATURE_KEYS.map((key) => FEATURE_REGISTRY[key]);
}
