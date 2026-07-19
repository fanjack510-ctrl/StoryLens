/** Pure helpers for request-limit recovery UX (no API side effects). */

export type RequestLimitSuggestion = {
  currentDailyRequestLimit: number;
  usedRequests: number;
  remainingRequests: number;
  requiredWorstRequests: number;
  minSuggestedLimit: number;
  recommendedLimit: number;
  estimatedStageCostCap: number;
  dailyCostLimit: number;
};

export function computeRequestLimitSuggestion(input: {
  currentDailyRequestLimit: number;
  remainingRequests: number;
  requiredWorstRequests: number;
  dailyCostLimit: number;
  estimatedStageCost?: number;
}): RequestLimitSuggestion {
  const current = Math.max(1, Math.floor(input.currentDailyRequestLimit));
  const remaining = Math.max(0, Math.floor(input.remainingRequests));
  const required = Math.max(0, Math.floor(input.requiredWorstRequests));
  const used = Math.max(0, current - remaining);
  const minSuggestedLimit = Math.max(current, used + required);
  // Round up to a friendly decade with headroom (e.g. 63 → 80).
  const recommendedLimit = Math.max(
    minSuggestedLimit,
    Math.ceil((minSuggestedLimit + 10) / 10) * 10,
  );
  const estimatedStageCostCap =
    typeof input.estimatedStageCost === "number" && input.estimatedStageCost > 0
      ? Math.round(input.estimatedStageCost * 1000) / 1000
      : 0.35;
  return {
    currentDailyRequestLimit: current,
    usedRequests: used,
    remainingRequests: remaining,
    requiredWorstRequests: required,
    minSuggestedLimit,
    recommendedLimit,
    estimatedStageCostCap,
    dailyCostLimit: input.dailyCostLimit,
  };
}

export type FullPipelineEnvelope = {
  boundary: { expected: number; worst: number };
  sceneAnalysis: { expected: number; worst: number; estimatedScenes: number };
  readerJourney: { expected: number; worst: number };
  retryRepairMargin: number;
  recoveryMargin: number;
  full: { expected: number; worst: number };
};

/** Advisory full-run request envelope before Stage-1 create (matches backend margins). */
export function estimateFullPipelineRequests(stage1: {
  expected_request_count?: number | null;
  worst_case_request_count?: number | null;
  paragraph_count?: number | null;
  transition_count?: number | null;
}): FullPipelineEnvelope {
  const boundaryExpected = Math.max(0, Number(stage1.expected_request_count) || 0);
  const boundaryWorst = Math.max(
    boundaryExpected,
    Number(stage1.worst_case_request_count) || 0,
  );
  const paragraphs = Math.max(0, Number(stage1.paragraph_count) || 0);
  // Paragraph-based advisory only (transitions over-estimate scene count before review).
  const estimatedScenes = Math.max(1, Math.ceil((paragraphs || 8) / 5));
  const sceneExpected = estimatedScenes;
  const sceneWorst = 2 * estimatedScenes;
  const rjBatches = Math.ceil(estimatedScenes / 2);
  const rjExpected = rjBatches + 1;
  const rjWorst = 2 * rjBatches + 2;
  const retryRepairMargin = Math.max(2, Math.ceil(estimatedScenes * 0.25));
  const recoveryMargin = Math.max(2, Math.ceil(estimatedScenes * 0.15));
  return {
    boundary: { expected: boundaryExpected, worst: boundaryWorst },
    sceneAnalysis: {
      expected: sceneExpected,
      worst: sceneWorst,
      estimatedScenes,
    },
    readerJourney: { expected: rjExpected, worst: rjWorst },
    retryRepairMargin,
    recoveryMargin,
    full: {
      expected: boundaryExpected + sceneExpected + rjExpected,
      worst: boundaryWorst + sceneWorst + rjWorst + retryRepairMargin + recoveryMargin,
    },
  };
}

export function fullPipelineRequestShortfall(input: {
  remainingRequests: number;
  fullWorstRequests: number;
}): number {
  return Math.max(0, input.fullWorstRequests - Math.max(0, input.remainingRequests));
}

export type CreateBudgetBlockerDimension =
  | "requests"
  | "tokens"
  | "estimated_cost"
  | "provider"
  | "api_key";

export type CreateBudgetBlocker = {
  dimension: CreateBudgetBlockerDimension;
  title: string;
  userMessage: string;
  required: number | null;
  available: number | null;
  shortfall: number | null;
  estimated: number | null;
  worstCase: number | null;
};

/** Classify create-time blockers for ordinary-user recovery panel. */
export function classifyCreateBudgetBlockers(input: {
  remainingRequests: number;
  remainingTokens: number;
  remainingCost: number;
  envelope: FullPipelineEnvelope;
  stage1CostWorst?: number | null;
  providerConnected: boolean;
  apiKeyConfigured: boolean;
}): CreateBudgetBlocker[] {
  const blockers: CreateBudgetBlocker[] = [];
  if (!input.apiKeyConfigured) {
    blockers.push({
      dimension: "api_key",
      title: "尚未配置 API Key",
      userMessage: "请先配置阿里云百炼 · Qwen 的 API Key。",
      required: null,
      available: null,
      shortfall: null,
      estimated: null,
      worstCase: null,
    });
  }
  if (!input.providerConnected) {
    blockers.push({
      dimension: "provider",
      title: "Qwen 尚未连接",
      userMessage: "AI 服务尚未连接，请先完成连接测试。",
      required: null,
      available: null,
      shortfall: null,
      estimated: null,
      worstCase: null,
    });
  }
  const reqShortfall = fullPipelineRequestShortfall({
    remainingRequests: input.remainingRequests,
    fullWorstRequests: input.envelope.full.worst,
  });
  if (reqShortfall > 0) {
    blockers.push({
      dimension: "requests",
      title: "当前技术请求额度不足",
      userMessage: `本章完整分析最坏需要${input.envelope.full.worst}次云端请求，当前今日剩余${input.remainingRequests}次，还差${reqShortfall}次。`,
      required: input.envelope.full.worst,
      available: input.remainingRequests,
      shortfall: reqShortfall,
      estimated: input.envelope.full.expected,
      worstCase: input.envelope.full.worst,
    });
  }
  // Token / cost hard blockers use proportional scaling from stage-1 when available.
  const tokenPerReq =
    input.envelope.full.worst > 0 && (input.stage1CostWorst ?? 0) >= 0
      ? 1500
      : 1500;
  const worstTokens = Math.round(input.envelope.full.worst * tokenPerReq);
  if (input.remainingTokens < worstTokens) {
    const shortfall = worstTokens - input.remainingTokens;
    blockers.push({
      dimension: "tokens",
      title: "当前 Token 额度不足",
      userMessage: `完整分析最坏约需 ${worstTokens} Token，当前剩余 ${input.remainingTokens}，还差 ${shortfall}。`,
      required: worstTokens,
      available: input.remainingTokens,
      shortfall,
      estimated: Math.round(input.envelope.full.expected * tokenPerReq),
      worstCase: worstTokens,
    });
  }
  const costPerReq = 0.01;
  const worstCost = Math.round(input.envelope.full.worst * costPerReq * 1000) / 1000;
  if (input.remainingCost + 1e-9 < worstCost) {
    const shortfall = Math.round((worstCost - input.remainingCost) * 1000) / 1000;
    blockers.push({
      dimension: "estimated_cost",
      title: "当前费用额度不足",
      userMessage: `完整分析最坏约需 ${worstCost} CNY，当前剩余约 ${input.remainingCost} CNY，还差 ${shortfall} CNY。`,
      required: worstCost,
      available: input.remainingCost,
      shortfall,
      estimated: Math.round(input.envelope.full.expected * costPerReq * 1000) / 1000,
      worstCase: worstCost,
    });
  }
  return blockers;
}

export function requestOnlyShortfall(
  blockers: CreateBudgetBlocker[],
): CreateBudgetBlocker | null {
  const request = blockers.find((b) => b.dimension === "requests");
  if (!request) return null;
  const hard = blockers.some(
    (b) =>
      b.dimension === "tokens" ||
      b.dimension === "estimated_cost" ||
      b.dimension === "provider" ||
      b.dimension === "api_key",
  );
  return hard ? null : request;
}
