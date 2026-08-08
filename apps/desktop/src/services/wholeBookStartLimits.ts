/** Whole-book start limit checks (CHG-20260808-062). */

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
    if (g.kind === "budget") {
      return `${g.label}：¥${g.estimated}\n当前上限：¥${g.limit}`;
    }
    return `${g.label}：${g.estimated.toLocaleString()}\n当前上限：${g.limit.toLocaleString()}`;
  });
  return `当前调用限制不足，无法开始分析。\n\n${lines.join("\n\n")}`;
}

export function mapWholeBookStartError(code: string, fallbackMessage: string): string {
  switch (code) {
    case "LIMIT_PROVIDER_CALLS_TOO_LOW":
      return "模型调用次数上限低于本次分析预计需求";
    case "LIMIT_INPUT_TOKENS_TOO_LOW":
    case "WHOLE_BOOK_INPUT_TOKEN_BUDGET_EXCEEDED":
      return "输入 Token 上限不足";
    case "LIMIT_OUTPUT_TOKENS_TOO_LOW":
    case "WHOLE_BOOK_OUTPUT_TOKEN_BUDGET_EXCEEDED":
      return "输出 Token 上限不足";
    case "BUDGET_TOO_LOW":
    case "WHOLE_BOOK_BUDGET_TOO_LOW":
      return "费用预算低于预计最高费用";
    case "CONSENT_STALE":
    case "WHOLE_BOOK_ESTIMATE_EXPIRED":
    case "WHOLE_BOOK_BOOK_CHANGED":
    case "WHOLE_BOOK_CONSENT_EXPIRED":
      return "分析配置已经变化，请重新确认";
    case "REQUEST_SCHEMA_INVALID":
    case "REQUEST_VALIDATION_ERROR":
      return fallbackMessage && !fallbackMessage.includes("请求字段校验失败")
        ? fallbackMessage
        : "请求参数异常";
    default:
      return fallbackMessage || "创建分析任务失败";
  }
}
