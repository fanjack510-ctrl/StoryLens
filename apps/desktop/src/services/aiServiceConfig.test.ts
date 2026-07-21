import { describe, expect, it, vi, beforeEach } from "vitest";
import {
  configureRecommendedQwenService,
  fetchRecommendedQwenStatus,
} from "./aiServiceConfig";

vi.mock("./apiClient", () => ({
  api: vi.fn(),
}));

import { api } from "./apiClient";

describe("configureRecommendedQwenService", () => {
  beforeEach(() => {
    vi.mocked(api).mockReset();
    localStorage.clear();
  });

  it("posts to the shared desktop ai-setup endpoint", async () => {
    vi.mocked(api).mockResolvedValue({
      ok: true,
      persisted: true,
      user_message: "保存成功",
      credential_configured: true,
      provider_enabled: true,
      cloud_enabled: true,
      provider_eligible: true,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "connected",
      analysis_mode: "BALANCED",
      blockers: [],
      needs_cloud_consent: false,
    });
    const result = await configureRecommendedQwenService({
      apiKey: "sk-test-key-value",
      analysisMode: "BALANCED",
      cloudBodyConsent: true,
      persist: true,
    });
    expect(api).toHaveBeenCalledWith(
      "/api/v1/desktop/ai-setup/recommended-qwen",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          api_key: "sk-test-key-value",
          analysis_mode: "BALANCED",
          cloud_body_consent: true,
          persist: true,
        }),
      }),
    );
    expect(result.provider_eligible).toBe(true);
    expect(localStorage.getItem("storylens.analysisModePreset")).toBe("BALANCED");
    expect(JSON.stringify(localStorage)).not.toContain("sk-test-key-value");
  });

  it("verify-only path sets persist false", async () => {
    vi.mocked(api).mockResolvedValue({
      ok: true,
      persisted: false,
      user_message: "API Key 与模型服务验证成功。验证成功，保存配置后还需检查分析预算和计价信息。",
      credential_configured: false,
      provider_enabled: false,
      cloud_enabled: false,
      provider_eligible: false,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "tested",
      analysis_mode: null,
      blockers: [],
      needs_cloud_consent: false,
      model_validated: true,
      analysis_ready: false,
    });
    const result = await configureRecommendedQwenService({
      apiKey: "sk-test-key-value",
      analysisMode: "FAST",
      cloudBodyConsent: false,
      persist: false,
    });
    expect(result.persisted).toBe(false);
    expect(result.user_message).toContain("保存配置后");
  });

  it("fetchRecommendedQwenStatus uses GET", async () => {
    vi.mocked(api).mockResolvedValue({
      ok: true,
      persisted: true,
      user_message: "配置完成，可以开始分析",
      credential_configured: true,
      provider_enabled: true,
      cloud_enabled: true,
      provider_eligible: true,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "connected",
      analysis_mode: "BALANCED",
      blockers: [],
      needs_cloud_consent: false,
    });
    await fetchRecommendedQwenStatus();
    expect(api).toHaveBeenCalledWith("/api/v1/desktop/ai-setup/recommended-qwen");
  });
});
