import { describe, expect, it } from "vitest";
import {
  buildAiServiceViewModel,
  mapTransportOrHttpError,
  mapUserStatusLabel,
  resolveProviderConnected,
  HIDDEN_PRIMARY_STATUS_CODES,
} from "./aiServiceViewModel";

describe("aiServiceViewModel", () => {
  it("maps internal codes to user labels", () => {
    expect(mapUserStatusLabel("provider_not_configured")).toBe("尚未配置AI服务");
    expect(mapUserStatusLabel("credential_missing")).toBe("尚未填写API Key");
    expect(mapUserStatusLabel("provider_disabled")).toBe("API Key 已保存，但 AI 服务未启用");
    expect(mapUserStatusLabel("cloud_disabled")).toBe("AI 服务已启用，但云端连接未开启");
    expect(mapUserStatusLabel("provider_disconnected")).toBe("尚未连接AI服务");
    expect(mapUserStatusLabel("dns_failed")).toBe("无法连接云端服务，请检查网络或代理设置");
    expect(mapUserStatusLabel("auth_failed")).toBe("API Key 无效，请检查后重新测试。");
    expect(mapUserStatusLabel("healthy")).toBe("配置完成，可以开始分析");
    expect(mapUserStatusLabel("awaiting_provider_recovery")).toBe(
      "云端服务暂时波动，系统正在自动恢复",
    );
  });

  it("healthy connected provider can start analysis", () => {
    const vm = buildAiServiceViewModel({
      provider: {
        name: "aliyun_qwen_plus",
        default_model: "qwen3.7-plus",
        configured: true,
        connected: true,
        healthy: true,
        enabled: true,
        health_state: "healthy",
        health_source: "configured_readiness",
        manual_boundary_candidate_eligible: true,
        capabilities: { enabled: true, cloud: true },
      },
      configuration: {
        display_name: "阿里云百炼",
        plus_model: "qwen3.7-plus",
        credential_state: "configured",
        enabled: true,
        disconnected: false,
        connection_state: "connected",
      },
      cloudEnabled: true,
      providerEligible: true,
    });
    expect(vm.serviceDisplayName).toBe("阿里云百炼");
    expect(vm.userStatusCode).toBe("healthy");
    expect(vm.canStartAnalysis).toBe(true);
    expect(vm.diagnostics.healthSource).toBe("configured_readiness");
  });

  it("does not treat connected config as analyzable when eligibility is false", () => {
    const vm = buildAiServiceViewModel({
      provider: {
        name: "aliyun_qwen_plus",
        configured: true,
        connected: true,
        healthy: true,
        enabled: true,
        manual_boundary_candidate_eligible: false,
        manual_selection_blockers: ["cloud_master_switch_off"],
        capabilities: { enabled: true, cloud: true },
      },
      configuration: {
        credential_state: "configured",
        enabled: true,
        disconnected: false,
        connection_state: "connected",
      },
      cloudEnabled: false,
      providerEligible: false,
    });
    expect(vm.canStartAnalysis).toBe(false);
    expect(vm.userStatusCode).toBe("cloud_disabled");
  });

  it("prefers configuration connection_state over stale provider.connected", () => {
    expect(
      resolveProviderConnected({
        provider: { connected: false },
        configuration: {
          disconnected: false,
          connection_state: "connected",
          credential_state: "configured",
        },
      }),
    ).toBe(true);

    const vm = buildAiServiceViewModel({
      provider: {
        name: "aliyun_qwen_plus",
        configured: true,
        connected: false,
        healthy: false,
        enabled: true,
        health_state: "unhealthy",
        manual_selection_blockers: ["provider_disconnected"],
        manual_boundary_candidate_eligible: true,
        capabilities: { enabled: true, cloud: true },
      },
      configuration: {
        credential_state: "configured",
        enabled: true,
        disconnected: false,
        connection_state: "connected",
      },
      cloudEnabled: true,
      providerEligible: true,
    });
    expect(vm.userStatusCode).toBe("healthy");
    expect(vm.canStartAnalysis).toBe(true);
  });

  it("does not treat failed transport as connected", () => {
    const vm = buildAiServiceViewModel({
      provider: {
        name: "aliyun_qwen_plus",
        configured: true,
        connected: false,
        healthy: false,
        enabled: true,
        manual_selection_blockers: ["provider_disconnected"],
        capabilities: { enabled: true, cloud: true },
      },
      configuration: {
        credential_state: "configured",
        disconnected: true,
        connection_state: "disconnected",
      },
      cloudEnabled: true,
      connectionErrorCode: "PROVIDER_DNS_ERROR",
    });
    expect(vm.userStatusCode).toBe("dns_failed");
    expect(vm.canStartAnalysis).toBe(false);
  });

  it("keeps raw codes only in diagnostics", () => {
    const vm = buildAiServiceViewModel({
      provider: {
        name: "aliyun_qwen_plus",
        configured: false,
        connected: false,
        healthy: false,
        enabled: false,
        health_state: "unhealthy",
        health_source: "configured_readiness",
        manual_selection_blockers: ["provider_not_configured"],
      },
      cloudEnabled: false,
    });
    expect(HIDDEN_PRIMARY_STATUS_CODES.some((c) => vm.userStatusLabel.includes(c))).toBe(false);
    expect(vm.diagnostics.rawCodes.join(" ")).toMatch(
      /provider_not_configured|unhealthy|configured_readiness/,
    );
  });

  it("maps 401/403 and DNS errors", () => {
    expect(mapTransportOrHttpError({ status: 401, code: "AUTHENTICATION_FAILED" }).userLabel).toBe(
      "API Key 无效，请检查后重新测试。",
    );
    expect(mapTransportOrHttpError({ code: "PROVIDER_DNS_ERROR" }).userLabel).toContain(
      "无法连接云端服务",
    );
  });
});
