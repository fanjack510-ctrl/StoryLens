/**
 * Central analysis mode presets for ordinary settings UX.
 * Maps user-facing tiers to provider + budget parameters (single source).
 */

export type AnalysisModePresetId = "FAST" | "BALANCED" | "QUALITY" | "CUSTOM";

export type AnalysisModePreset = {
  id: AnalysisModePresetId;
  /** User-facing label (includes recommendation marker when applicable). */
  label: string;
  shortLabel: string;
  recommended: boolean;
  providerId: string;
  /** Primary model written to provider `plus_model` for routing. */
  modelId: string;
  flashModel: string;
  maxModel: string;
  timeoutSeconds: number;
  maxRetries: number;
  cloudMaxOutputTokensPerRequest: number;
  cloudMaxInputTokensPerRequest: number;
  cloudMaxRequestsPerRun: number;
  /** Rough list price hint for UI only (CNY per chapter, not billing). */
  estimatedCostPerChapterCny: number;
};

export const DEFAULT_ANALYSIS_MODE: AnalysisModePresetId = "BALANCED";

export const ANALYSIS_MODE_PRESETS: Record<
  Exclude<AnalysisModePresetId, "CUSTOM">,
  AnalysisModePreset
> = {
  FAST: {
    id: "FAST",
    label: "快速",
    shortLabel: "快速",
    recommended: false,
    providerId: "aliyun_qwen_plus",
    modelId: "qwen3.6-flash",
    flashModel: "qwen3.6-flash",
    maxModel: "qwen3.7-max",
    timeoutSeconds: 180,
    maxRetries: 2,
    cloudMaxOutputTokensPerRequest: 2500,
    cloudMaxInputTokensPerRequest: 12000,
    cloudMaxRequestsPerRun: 35,
    estimatedCostPerChapterCny: 0.35,
  },
  BALANCED: {
    id: "BALANCED",
    label: "均衡（推荐）",
    shortLabel: "均衡",
    recommended: true,
    providerId: "aliyun_qwen_plus",
    modelId: "qwen3.7-plus",
    flashModel: "qwen3.6-flash",
    maxModel: "qwen3.7-max",
    timeoutSeconds: 300,
    maxRetries: 3,
    cloudMaxOutputTokensPerRequest: 4000,
    cloudMaxInputTokensPerRequest: 16000,
    cloudMaxRequestsPerRun: 50,
    estimatedCostPerChapterCny: 0.85,
  },
  QUALITY: {
    id: "QUALITY",
    label: "高质量",
    shortLabel: "高质量",
    recommended: false,
    providerId: "aliyun_qwen_plus",
    modelId: "qwen3.7-max",
    flashModel: "qwen3.6-flash",
    maxModel: "qwen3.7-max",
    timeoutSeconds: 420,
    maxRetries: 3,
    cloudMaxOutputTokensPerRequest: 6000,
    cloudMaxInputTokensPerRequest: 20000,
    cloudMaxRequestsPerRun: 60,
    estimatedCostPerChapterCny: 1.6,
  },
};

const STORAGE_KEY = "storylens.analysisModePreset";

export function readStoredAnalysisMode(): AnalysisModePresetId {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "FAST" || raw === "BALANCED" || raw === "QUALITY" || raw === "CUSTOM") {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_ANALYSIS_MODE;
}

export function writeStoredAnalysisMode(id: AnalysisModePresetId) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

export function presetFor(id: AnalysisModePresetId): AnalysisModePreset | null {
  if (id === "CUSTOM") return null;
  return ANALYSIS_MODE_PRESETS[id];
}

export function ordinaryModeOptions(): AnalysisModePreset[] {
  return [ANALYSIS_MODE_PRESETS.FAST, ANALYSIS_MODE_PRESETS.BALANCED, ANALYSIS_MODE_PRESETS.QUALITY];
}

export function applyPresetToProviderConfig<T extends Record<string, unknown>>(
  existing: T,
  mode: Exclude<AnalysisModePresetId, "CUSTOM">,
): T {
  const p = ANALYSIS_MODE_PRESETS[mode];
  return {
    ...existing,
    plus_model: p.modelId,
    flash_model: p.flashModel,
    max_model: p.maxModel,
    timeout_seconds: p.timeoutSeconds,
    max_retries: p.maxRetries,
  };
}

export function applyPresetToCloudBudget<T extends Record<string, unknown>>(
  existing: T,
  mode: Exclude<AnalysisModePresetId, "CUSTOM">,
): T {
  const p = ANALYSIS_MODE_PRESETS[mode];
  return {
    ...existing,
    cloud_max_output_tokens_per_request: p.cloudMaxOutputTokensPerRequest,
    cloud_max_input_tokens_per_request: p.cloudMaxInputTokensPerRequest,
    cloud_max_requests_per_run: p.cloudMaxRequestsPerRun,
  };
}
