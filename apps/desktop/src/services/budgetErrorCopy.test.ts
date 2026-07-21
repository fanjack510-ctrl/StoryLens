import { describe, expect, it } from "vitest";
import {
  BUDGET_ERROR_USER_COPY,
  formatDimensionGaps,
  primaryShortageLabel,
  sufficientDimensionsNote,
} from "./budgetErrorCopy";

describe("budgetErrorCopy", () => {
  it("maps reservation code to user-facing budget copy", () => {
    expect(BUDGET_ERROR_USER_COPY.INSUFFICIENT_BUDGET_RESERVATION).toContain("预算不足");
    expect(BUDGET_ERROR_USER_COPY.CLOUD_COST_LIMIT_EXCEEDED).toContain("费用");
    expect(BUDGET_ERROR_USER_COPY.BUDGET_NOT_AVAILABLE).toContain("无法计算");
  });

  it("formats 26 need / 13 remaining without claiming cost shortage", () => {
    const text = formatDimensionGaps({
      dimensions: ["requests"],
      required: { requests: 26, tokens: 1000, estimated_cost: 0.2 },
      remaining: { requests: 13, tokens: 164405, estimated_cost: 19.87 },
    });
    expect(text).toContain("26");
    expect(text).toContain("13");
    expect(text).not.toMatch(/费用不足/);
    expect(primaryShortageLabel(["requests"])).toBe("请求");
    expect(
      sufficientDimensionsNote({
        dimensions: ["requests"],
        remaining: { requests: 13, tokens: 164405, estimated_cost: 19.87 },
      }),
    ).toMatch(/Token预算充足/);
  });
});
