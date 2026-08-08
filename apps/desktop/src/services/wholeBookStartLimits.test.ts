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

describe("wholeBookStartLimits CHG-062", () => {
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
    expect(formatLimitGapsMessage(gaps)).toContain("当前调用限制不足");
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

  it("maps backend codes to product copy", () => {
    expect(mapWholeBookStartError("LIMIT_PROVIDER_CALLS_TOO_LOW", "x")).toContain(
      "模型调用次数",
    );
    expect(mapWholeBookStartError("REQUEST_SCHEMA_INVALID", "请求参数异常：consent_id")).toContain(
      "请求参数异常",
    );
    expect(mapWholeBookStartError("REQUEST_VALIDATION_ERROR", "请求字段校验失败。")).toBe(
      "请求参数异常",
    );
  });
});
