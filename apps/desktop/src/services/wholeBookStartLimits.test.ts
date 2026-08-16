import { describe, expect, it } from "vitest";
import {
  compareLimitsToEstimate,
  formatLimitGapsMessage,
  mapWholeBookStartError,
} from "./wholeBookStartLimits";

const EST = {
  estimated_provider_calls: 425,
  estimated_input_tokens: 1_758_000,
  estimated_output_tokens: 297_000,
  estimated_cost_max_cny: "2.5005",
};

describe("wholeBookStartLimits CHG-062/077", () => {
  it("画像确认门错误给出下一步指引", () => {
    const message = mapWholeBookStartError("PROFILE_CONFIRMATION_REQUIRED", "raw", {
      book_id: 2,
      profile_status: "none",
    });
    expect(message).toContain("作品画像");
    expect(message).toContain("确认");
  });

  it("flags provider calls / input / output too low and passes budget", () => {
    const gaps = compareLimitsToEstimate(EST, {
      max_provider_calls: "200",
      max_input_tokens: "500000",
      max_output_tokens: "100000",
      max_cost_budget_cny: "10",
    });
    expect(gaps.map((g) => g.code)).toEqual([
      "LIMIT_PROVIDER_CALLS_TOO_LOW",
      "LIMIT_INPUT_TOKENS_TOO_LOW",
      "LIMIT_OUTPUT_TOKENS_TOO_LOW",
    ]);
    expect(gaps.some((g) => g.kind === "budget")).toBe(false);
    expect(formatLimitGapsMessage(gaps)).toContain("预计需要 425 次模型调用");
    expect(formatLimitGapsMessage(gaps)).toContain("超过当前允许上限 200 次");
  });

  it("enables start when all limits cover estimate", () => {
    const gaps = compareLimitsToEstimate(EST, {
      max_provider_calls: "500",
      max_input_tokens: "2000000",
      max_output_tokens: "350000",
      max_cost_budget_cny: "10",
    });
    expect(gaps).toEqual([]);
  });

  it("maps backend codes to product copy with numbers", () => {
    expect(
      mapWholeBookStartError("LIMIT_PROVIDER_CALLS_TOO_LOW", "x", {
        estimated_provider_calls: 2444,
        max_provider_calls: 300,
      }),
    ).toBe(
      "预计需要 2444 次模型调用，超过当前允许上限 300 次。请提高调用上限或调整分析范围。",
    );
    expect(mapWholeBookStartError("REQUEST_SCHEMA_INVALID", "请求参数异常：consent_id")).toContain(
      "请求参数异常",
    );
    expect(mapWholeBookStartError("REQUEST_VALIDATION_ERROR", "请求字段校验失败。")).toBe(
      "请求参数异常",
    );
    expect(mapWholeBookStartError("WHOLE_BOOK_INPUT_TOKEN_BUDGET_EXCEEDED", "input token budget exceeded")).toBe(
      "输入 Token 上限不足",
    );
  });

  it("clearly blocks start when estimated calls exceed max calls", () => {
    const gaps = compareLimitsToEstimate(
      { estimated_provider_calls: 2444, estimated_cost_max_cny: "2.73" },
      {
        max_provider_calls: "300",
        max_input_tokens: "2200000",
        max_output_tokens: "400000",
        max_cost_budget_cny: "10",
      },
    );
    expect(gaps).toHaveLength(1);
    expect(gaps[0]?.code).toBe("LIMIT_PROVIDER_CALLS_TOO_LOW");
    expect(formatLimitGapsMessage(gaps)).toContain("2444");
    expect(formatLimitGapsMessage(gaps)).toContain("300");
  });
});
