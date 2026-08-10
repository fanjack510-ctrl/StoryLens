/** Whole-book start limit checks (CHG-20260808-062 / CHG-20260810-077). */

export type WholeBookEstimateLike = {
  estimated_provider_calls?: number | null;
  estimated_input_tokens?: number | null;
  estimated_output_tokens?: number | null;
  estimated_cost_max_cny?: string | number | null;
};

export type WholeBookLimitsLike = {
  max_provider_calls: string;
  max_input_tokens: string;
  max_output_tokens: string;
  max_cost_budget_cny: string;
};

export type LimitGapKind =
  | "provider_calls"
  | "input_tokens"
  | "output_tokens"
  | "budget";

export type LimitGap = {
  kind: LimitGapKind;
  code:
    | "LIMIT_PROVIDER_CALLS_TOO_LOW"
    | "LIMIT_INPUT_TOKENS_TOO_LOW"
    | "LIMIT_OUTPUT_TOKENS_TOO_LOW"
    | "BUDGET_TOO_LOW";
  label: string;
  estimated: number;
  limit: number;
};

function parsePositiveNumber(raw: string): number | null {
  const n = Number(String(raw ?? "").trim());
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

export function compareLimitsToEstimate(
  estimate: WholeBookEstimateLike | null | undefined,
  limits: WholeBookLimitsLike,
): LimitGap[] {
  if (!estimate) return [];
  const gaps: LimitGap[] = [];

  const estCalls = Number(estimate.estimated_provider_calls ?? 0);
  const limCalls = parsePositiveNumber(limits.max_provider_calls);
  if (estCalls > 0 && (limCalls == null || limCalls < estCalls)) {
    gaps.push({
      kind: "provider_calls",
      code: "LIMIT_PROVIDER_CALLS_TOO_LOW",
      label: "预计模型调用",
      estimated: estCalls,
      limit: limCalls ?? 0,
    });
  }

  const estIn = Number(estimate.estimated_input_tokens ?? 0);
  const limIn = parsePositiveNumber(limits.max_input_tokens);
  if (estIn > 0 && (limIn == null || limIn < estIn)) {
    gaps.push({
      kind: "input_tokens",
      code: "LIMIT_INPUT_TOKENS_TOO_LOW",
      label: "预计输入 Token",
      estimated: estIn,
      limit: limIn ?? 0,
    });
  }

  const estOut = Number(estimate.estimated_output_tokens ?? 0);
  const limOut = parsePositiveNumber(limits.max_output_tokens);
  if (estOut > 0 && (limOut == null || limOut < estOut)) {
    gaps.push({
      kind: "output_tokens",
      code: "LIMIT_OUTPUT_TOKENS_TOO_LOW",
      label: "预计输出 Token",
      estimated: estOut,
      limit: limOut ?? 0,
    });
  }

  const estCostMax = Number(estimate.estimated_cost_max_cny ?? NaN);
  const limBudget = parsePositiveNumber(limits.max_cost_budget_cny);
  if (Number.isFinite(estCostMax) && estCostMax > 0) {
    if (limBudget == null || limBudget < estCostMax) {
      gaps.push({
        kind: "budget",
        code: "BUDGET_TOO_LOW",
        label: "预计最高费用",
        estimated: estCostMax,
        limit: limBudget ?? 0,
      });
    }
  }

  return gaps;
}

export function formatLimitGapsMessage(gaps: LimitGap[]): string {
  if (!gaps.length) return "";
  const lines = gaps.map((g) => {
    if (g.kind === "provider_calls") {
      return `预计需要 ${g.estimated} 次模型调用，超过当前允许上限 ${g.limit} 次。请提高调用上限或调整分析范围。`;
    }
    if (g.kind === "input_tokens") {
      return `预计需要 ${g.estimated} 输入 Token，超过当前允许上限 ${g.limit}。请提高输入 Token 上限或调整分析范围。`;
    }
    if (g.kind === "output_tokens") {
      return `预计需要 ${g.estimated} 输出 Token，超过当前允许上限 ${g.limit}。请提高输出 Token 上限或调整分析范围。`;
    }
    return `预计最高费用 ¥${g.estimated}，超过当前费用上限 ¥${g.limit}。请提高费用上限或调整分析范围。`;
  });
  return lines.join("\n\n");
}

function detailNumber(detail: unknown, key: string): number | null {
  if (!detail || typeof detail !== "object") return null;
  const raw = (detail as Record<string, unknown>)[key];
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export function mapWholeBookStartError(
  code: string,
  fallbackMessage: string,
  detail?: unknown,
): string {
  const estimatedCalls = detailNumber(detail, "estimated_provider_calls");
  const maxCalls = detailNumber(detail, "max_provider_calls");
  const estimatedIn = detailNumber(detail, "estimated_input_tokens");
  const maxIn = detailNumber(detail, "max_input_tokens");
  const estimatedOut = detailNumber(detail, "estimated_output_tokens");
  const maxOut = detailNumber(detail, "max_output_tokens");
  const estimatedCost = detailNumber(detail, "estimated_cost_max_cny");
  const maxBudget = detailNumber(detail, "max_cost_budget_cny");

  switch (code) {
    case "LIMIT_PROVIDER_CALLS_TOO_LOW":
      if (estimatedCalls != null && maxCalls != null) {
        return `预计需要 ${estimatedCalls} 次模型调用，超过当前允许上限 ${maxCalls} 次。请提高调用上限或调整分析范围。`;
      }
      return fallbackMessage.includes("预计需要")
        ? fallbackMessage
        : "预计模型调用次数超过当前允许上限。请提高调用上限或调整分析范围。";
    case "LIMIT_INPUT_TOKENS_TOO_LOW":
    case "WHOLE_BOOK_INPUT_TOKEN_BUDGET_EXCEEDED":
      if (estimatedIn != null && maxIn != null) {
        return `预计需要 ${estimatedIn} 输入 Token，超过当前允许上限 ${maxIn}。请提高输入 Token 上限或调整分析范围。`;
      }
      return fallbackMessage.includes("预计需要") ? fallbackMessage : "输入 Token 上限不足";
    case "LIMIT_OUTPUT_TOKENS_TOO_LOW":
    case "WHOLE_BOOK_OUTPUT_TOKEN_BUDGET_EXCEEDED":
      if (estimatedOut != null && maxOut != null) {
        return `预计需要 ${estimatedOut} 输出 Token，超过当前允许上限 ${maxOut}。请提高输出 Token 上限或调整分析范围。`;
      }
      return fallbackMessage.includes("预计需要") ? fallbackMessage : "输出 Token 上限不足";
    case "BUDGET_TOO_LOW":
    case "WHOLE_BOOK_BUDGET_TOO_LOW":
      if (estimatedCost != null && maxBudget != null) {
        return `预计最高费用 ¥${estimatedCost}，超过当前费用上限 ¥${maxBudget}。请提高费用上限或调整分析范围。`;
      }
      return fallbackMessage.includes("预计") ? fallbackMessage : "费用预算低于预计最高费用";
    case "CONSENT_STALE":
    case "WHOLE_BOOK_ESTIMATE_EXPIRED":
    case "WHOLE_BOOK_BOOK_CHANGED":
    case "WHOLE_BOOK_CONSENT_EXPIRED":
    case "WHOLE_BOOK_CONSENT_REQUIRED":
    case "WHOLE_BOOK_CONSENT_REVOKED":
      return "分析配置已经变化，请重新确认";
    case "WHOLE_BOOK_REAL_PROVIDER_DISABLED":
      return fallbackMessage || "真实模型分析尚未启用";
    case "REQUEST_SCHEMA_INVALID":
    case "REQUEST_VALIDATION_ERROR":
      return fallbackMessage && !fallbackMessage.includes("请求字段校验失败")
        ? fallbackMessage
        : "请求参数异常";
    case "BACKEND_OFFLINE":
    case "HTTP_ERROR":
      return fallbackMessage || "网络或服务异常，创建分析任务失败";
    default:
      return fallbackMessage || "创建分析任务失败";
  }
}
