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

  // 调用次数、输入 / 输出 Token 三条上限已经不再拦人：它们量的是同一件事的另外三种单位，
  // 用得多就是花得多。四个数字里随便哪个填低了都会把人拦住，而屏幕上只说「额度不足」。
  it("只有费用一条能拦住开始，另外三条填多低都不拦", () => {
    const gaps = compareLimitsToEstimate(EST, {
      max_provider_calls: "1",
      max_input_tokens: "1",
      max_output_tokens: "1",
      max_cost_budget_cny: "10",
    });
    expect(gaps).toEqual([]);
  });

  it("费用不够时说清楚差在哪", () => {
    const gaps = compareLimitsToEstimate(EST, {
      max_provider_calls: "500",
      max_input_tokens: "2000000",
      max_output_tokens: "350000",
      max_cost_budget_cny: "1",
    });
    expect(gaps.map((g) => g.code)).toEqual(["BUDGET_TOO_LOW"]);
    expect(formatLimitGapsMessage(gaps)).toContain("2.5005");
  });

  it("enables start when the budget covers the estimate", () => {
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

  // 调用次数远超上限也不再拦——2444 次调用配 300 次上限，只要费用够就放行。
  // 后端仍然会按自己的护栏拒绝，那时错误码照常映射成人话（见上一条用例）。
  it("调用次数远超上限也不拦，只要费用够", () => {
    const gaps = compareLimitsToEstimate(
      { estimated_provider_calls: 2444, estimated_cost_max_cny: "2.73" },
      {
        max_provider_calls: "300",
        max_input_tokens: "2200000",
        max_output_tokens: "400000",
        max_cost_budget_cny: "10",
      },
    );
    expect(gaps).toEqual([]);
  });
});
