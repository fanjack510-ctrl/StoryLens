import { describe, expect, it } from "vitest";
import {
  formatSetupErrorBlock,
  mapSetupError,
  nextBlockedReason,
  stripRawErrorCodes,
} from "./setupErrorCopy";

describe("setupErrorCopy", () => {
  it("maps budget codes to Chinese without exposing raw codes in title", () => {
    const info = mapSetupError("BUDGET_NOT_AVAILABLE");
    expect(info.title).toContain("无法计算");
    expect(info.title).not.toContain("BUDGET_NOT_AVAILABLE");
    expect(formatSetupErrorBlock("INSUFFICIENT_BUDGET_RESERVATION")).toContain("处理方式");
  });

  it("maps model pricing missing with model name", () => {
    const text = formatSetupErrorBlock("MODEL_PRICING_NOT_FOUND", { model: "qwen3.7-plus" });
    expect(text).toContain("qwen3.7-plus");
    expect(text).not.toMatch(/BUDGET_NOT_AVAILABLE|INSUFFICIENT_BUDGET/);
  });

  it("gates next until analysis ready", () => {
    expect(
      nextBlockedReason({
        hasApiKeyInput: false,
        credentialConfigured: false,
        modelValidated: false,
        persisted: false,
        analysisReady: false,
        cloudEnabled: false,
        blockers: [],
      }),
    ).toContain("尚未填写 API Key");

    expect(
      nextBlockedReason({
        hasApiKeyInput: true,
        credentialConfigured: false,
        modelValidated: true,
        persisted: false,
        analysisReady: false,
        cloudEnabled: false,
        blockers: [],
      }),
    ).toContain("尚未保存");

    expect(
      nextBlockedReason({
        hasApiKeyInput: true,
        credentialConfigured: true,
        modelValidated: true,
        persisted: true,
        analysisReady: false,
        cloudEnabled: true,
        blockers: ["pricing_unavailable"],
      }),
    ).toContain("计价");

    expect(
      nextBlockedReason({
        hasApiKeyInput: true,
        credentialConfigured: true,
        modelValidated: true,
        persisted: true,
        analysisReady: true,
        cloudEnabled: true,
        blockers: [],
      }),
    ).toBeNull();
  });

  it("strips raw codes from user strings", () => {
    expect(stripRawErrorCodes("失败：BUDGET_NOT_AVAILABLE、INSUFFICIENT_BUDGET_RESERVATION")).not.toContain(
      "BUDGET_NOT_AVAILABLE",
    );
  });
});
