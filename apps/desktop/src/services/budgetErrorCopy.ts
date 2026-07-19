/** User-facing budget / cloud limit copy. Technical codes stay in diagnostics only. */

export const BUDGET_ERROR_USER_COPY: Record<string, string> = {
  INSUFFICIENT_BUDGET_RESERVATION:
    "本阶段需要的云端请求额度超过今日剩余额度。",
  CLOUD_REQUEST_LIMIT_EXCEEDED: "今日云端请求保护已达到上限。",
  CLOUD_TOKEN_LIMIT_EXCEEDED: "今日Token保护已达到上限。",
  CLOUD_COST_LIMIT_EXCEEDED: "今日费用预算已达到上限。",
  CLOUD_BUDGET_EXCEEDED: "当前云端预算不足以继续分析。",
};

export type BudgetGapDimension = "requests" | "tokens" | "estimated_cost";

export type BudgetGapView = {
  dimensions: BudgetGapDimension[];
  required?: { requests?: number; tokens?: number; estimated_cost?: number };
  remaining?: { requests?: number; tokens?: number; estimated_cost?: number };
  shortfall?: { requests?: number; tokens?: number; estimated_cost?: number };
  daily_limit?: { requests?: number; tokens?: number; estimated_cost?: number };
  used?: { requests?: number; tokens?: number; estimated_cost?: number };
  reservation?: Record<string, unknown>;
  run_id?: number;
};

export function userFacingBudgetMessage(code: string | null | undefined): string {
  if (!code) return "当前云端预算不足以继续分析。";
  return BUDGET_ERROR_USER_COPY[code] || "当前云端预算不足以继续分析。";
}

export function isBudgetReservationCode(code: string | null | undefined): boolean {
  return (
    code === "INSUFFICIENT_BUDGET_RESERVATION" ||
    code === "CLOUD_REQUEST_LIMIT_EXCEEDED" ||
    code === "CLOUD_TOKEN_LIMIT_EXCEEDED" ||
    code === "CLOUD_COST_LIMIT_EXCEEDED" ||
    code === "CLOUD_BUDGET_EXCEEDED"
  );
}

export function primaryShortageLabel(dims: string[] | null | undefined): string {
  const list = dims || [];
  if (list.includes("requests")) return "请求";
  if (list.includes("tokens")) return "Token";
  if (list.includes("estimated_cost")) return "费用";
  return "请求";
}

export function formatDimensionGaps(gap: BudgetGapView): string {
  const dims = gap.dimensions.length
    ? gap.dimensions
    : ((["requests"] as BudgetGapDimension[]));
  return dims
    .map((dim) => {
      if (dim === "requests") {
        const need = gap.required?.requests;
        const left = gap.remaining?.requests;
        if (typeof need === "number" && typeof left === "number") {
          return `云端请求不足：最多需要 ${need} 次，今日剩余 ${left} 次。`;
        }
        return BUDGET_ERROR_USER_COPY.INSUFFICIENT_BUDGET_RESERVATION;
      }
      if (dim === "tokens") {
        const need = gap.required?.tokens;
        const left = gap.remaining?.tokens;
        if (typeof need === "number" && typeof left === "number") {
          return `Token不足：最多需要 ${need}，今日剩余 ${left}。`;
        }
        return BUDGET_ERROR_USER_COPY.CLOUD_TOKEN_LIMIT_EXCEEDED;
      }
      const need = gap.required?.estimated_cost;
      const left = gap.remaining?.estimated_cost;
      if (typeof need === "number" && typeof left === "number") {
        return `费用不足：最多需要约 ${need} CNY，今日剩余约 ${left} CNY。`;
      }
      return BUDGET_ERROR_USER_COPY.CLOUD_COST_LIMIT_EXCEEDED;
    })
    .join("\n");
}

export function sufficientDimensionsNote(gap: BudgetGapView): string | null {
  const dims = new Set(gap.dimensions);
  const parts: string[] = [];
  if (!dims.has("tokens") && typeof gap.remaining?.tokens === "number") {
    parts.push("Token预算充足");
  }
  if (!dims.has("estimated_cost") && typeof gap.remaining?.estimated_cost === "number") {
    parts.push("费用预算充足");
  }
  return parts.length ? parts.join("，") + "。" : null;
}

export function techBudgetDetails(gap: BudgetGapView, code?: string | null) {
  return {
    error_code: code || "INSUFFICIENT_BUDGET_RESERVATION",
    required: gap.required,
    available: gap.remaining,
    shortfall: gap.shortfall,
    daily_limit: gap.daily_limit,
    used: gap.used,
    remaining: gap.remaining,
    reservation: gap.reservation,
    run_id: gap.run_id,
  };
}
