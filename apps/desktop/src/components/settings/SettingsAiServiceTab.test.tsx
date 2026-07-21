import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsAiServiceTab } from "./SettingsAiServiceTab";
import { providersApi } from "../../services/providersApi";
import { settingsApi } from "../../services/settingsApi";
import * as aiServiceConfig from "../../services/aiServiceConfig";
import { useAdvancedSettingsStore } from "../../stores/advancedSettingsStore";

vi.mock("../../services/providersApi", () => ({
  providersApi: {
    list: vi.fn(),
    configuration: vi.fn(),
    save: vi.fn(),
    action: vi.fn(),
    transportDiagnostic: vi.fn(),
  },
}));

vi.mock("../../services/settingsApi", () => ({
  settingsApi: {
    cloud: vi.fn(),
    setCloud: vi.fn(),
    cloudUsage: vi.fn(),
    cloudBudget: vi.fn(),
    saveCloudBudget: vi.fn(),
  },
}));

vi.mock("../../services/aiServiceConfig", async () => {
  const actual = await vi.importActual<typeof import("../../services/aiServiceConfig")>(
    "../../services/aiServiceConfig",
  );
  return {
    ...actual,
    fetchRecommendedQwenStatus: vi.fn(),
    configureRecommendedQwenService: vi.fn(),
    repairRecommendedQwenSetup: vi.fn(),
  };
});

const eligibleProvider = {
  name: "aliyun_qwen_plus",
  default_model: "qwen3.7-plus",
  configured: true,
  connected: true,
  healthy: true,
  enabled: true,
  status: "healthy",
  health_state: "healthy",
  health_source: "configured_readiness",
  manual_boundary_candidate_eligible: true,
  manual_selection_blockers: [],
  capabilities: { cloud: true, enabled: true },
};

const connectedConfig = {
  provider_name: "aliyun_qwen_plus",
  display_name: "阿里云百炼",
  plus_model: "qwen3.7-plus",
  credential_state: "configured",
  enabled: true,
  disconnected: false,
  connection_state: "connected",
};

const eligibleSetup = {
  ok: true,
  user_message: "配置完成，可以开始分析",
  persisted: true,
  credential_configured: true,
  provider_enabled: true,
  cloud_enabled: true,
  provider_eligible: true,
  analysis_ready: true,
  model_validated: true,
  selected_provider_id: "aliyun_qwen_plus",
  connection_status: "connected",
  analysis_mode: "BALANCED",
  blockers: [],
  needs_cloud_consent: false,
  cloud_body_consent: true,
  config_profile: {
    runtime_mode: "browser_dev",
    app_env: "development",
    data_directory: "D:/dev/data",
    database_path: "D:/dev/data/storylens.db",
    isolates_sqlite_from_packaged: true,
    packaged_data_directory_hint: "C:/Users/x/AppData/Local/StoryLens",
    credential_store: {
      type: "KeyringCredentialStore",
      available: true,
      machine_scoped: true,
      returns_secret_to_api: false,
      shares_with_packaged: true,
      desktop_parity: true,
    },
    user_message: "当前为浏览器开发模式。配置库与正式版隔离。",
  },
};

function renderTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <SettingsAiServiceTab />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("SettingsAiServiceTab recommended setup", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAdvancedSettingsStore.setState({ showAdvancedSettings: false });
    vi.mocked(settingsApi.cloud).mockResolvedValue({ enabled: true, state: "available" });
    vi.mocked(providersApi.list).mockResolvedValue([eligibleProvider] as any);
    vi.mocked(providersApi.configuration).mockResolvedValue(connectedConfig as any);
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue(eligibleSetup as any);
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue({
      ...eligibleSetup,
      user_message: "配置完成。模型服务、计价和预算检查均已通过，可以开始分析。",
      persisted: true,
    } as any);
  });

  afterEach(() => {
    cleanup();
  });

  it("shows eligible only when backend provider_eligible is true", async () => {
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "当前可用于分析",
    );
    expect(screen.getByTestId("ai-service-status-facts")).toHaveTextContent("最终分析就绪：是");
    expect(screen.getByTestId("ai-service-status-facts")).toHaveTextContent("云端分析：已开启");
  });

  it("does not show ready when eligibility is false even if credential configured", async () => {
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue({
      ...eligibleSetup,
      ok: false,
      provider_eligible: false,
      analysis_ready: false,
      cloud_enabled: false,
      blockers: ["cloud_master_switch_off"],
      user_message: "云端模型服务尚未开启",
      needs_cloud_consent: true,
    } as any);
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "当前不可用于分析",
    );
    expect(screen.getByTestId("ai-service-status-facts")).toHaveTextContent("最终分析就绪：否");
    expect(screen.getByTestId("ai-service-status-facts")).toHaveTextContent("云端分析：未开启");
    expect(screen.getByTestId("ai-service-repair")).toBeInTheDocument();
  });

  it("shows pricing blocker as the readiness reason", async () => {
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue({
      ...eligibleSetup,
      ok: false,
      provider_eligible: false,
      analysis_ready: false,
      blockers: ["pricing_unavailable"],
      user_message: "当前模型缺少计价信息",
    } as any);
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "当前模型缺少计价信息",
    );
    expect(screen.getByTestId("ai-service-readiness-detail")).toHaveTextContent("处理方式");
    expect(screen.getByTestId("ai-service-readiness-detail")).not.toHaveTextContent(
      "BUDGET_NOT_AVAILABLE",
    );
  });

  it("verify model service calls shared configure with persist false", async () => {
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue({
      ...eligibleSetup,
      ok: true,
      persisted: false,
      analysis_ready: false,
      model_validated: true,
      user_message: "API Key 与模型服务验证成功。验证成功，保存配置后还需检查分析预算和计价信息。",
    } as any);
    renderTab();
    await screen.findByTestId("ai-service-connection-status");
    expect(screen.getByTestId("ai-service-test")).toHaveTextContent("验证模型服务");
    fireEvent.click(screen.getByTestId("ai-service-test"));
    await waitFor(() => {
      expect(aiServiceConfig.configureRecommendedQwenService).toHaveBeenCalledWith(
        expect.objectContaining({ persist: false }),
      );
    });
    expect(screen.getByRole("status")).toHaveTextContent("验证成功");
  });

  it("verify and save calls configure with persist true", async () => {
    renderTab();
    await screen.findByTestId("ai-service-connection-status");
    fireEvent.click(screen.getByTestId("cloud-body-consent"));
    fireEvent.change(screen.getByTestId("ai-api-key-input"), {
      target: { value: "sk-new-key-value" },
    });
    fireEvent.click(screen.getByTestId("ai-service-save"));
    await waitFor(() => {
      expect(aiServiceConfig.configureRecommendedQwenService).toHaveBeenCalledWith(
        expect.objectContaining({
          persist: true,
          apiKey: "sk-new-key-value",
          cloudBodyConsent: true,
        }),
      );
    });
    expect(screen.getByRole("status")).toHaveTextContent("配置完成");
  });

  it("keeps status after remount from backend setup endpoint", async () => {
    const { unmount } = renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "当前可用于分析",
    );
    unmount();
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "当前可用于分析",
    );
    expect(aiServiceConfig.fetchRecommendedQwenStatus).toHaveBeenCalled();
  });

  it("keeps backend cloud_enabled=true after init (no false default overwrite)", async () => {
    renderTab();
    expect(await screen.findByTestId("ai-service-status-facts")).toHaveTextContent("云端分析：已开启");
    expect(screen.getByTestId("ai-service-status-facts")).toHaveTextContent("Provider：已启用");
    expect(screen.getByTestId("ai-config-environment-banner")).toHaveTextContent(
      "当前为浏览器开发模式",
    );
  });

  it("shows env mismatch hint when credentials exist but switches off in isolated profile", async () => {
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue({
      ...eligibleSetup,
      ok: false,
      cloud_enabled: false,
      provider_enabled: false,
      provider_eligible: false,
      analysis_ready: false,
      blockers: ["cloud_master_switch_off"],
      needs_cloud_consent: true,
    } as any);
    renderTab();
    expect(await screen.findByTestId("ai-service-env-mismatch-hint")).toBeInTheDocument();
    expect(screen.getByTestId("ai-service-status-facts")).toHaveTextContent("凭据状态：已配置");
    expect(screen.getByTestId("ai-service-status-facts")).toHaveTextContent("云端分析：未开启");
  });

  it("shows rate_limited details without incomplete-config copy", async () => {
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue({
      ...eligibleSetup,
      ok: false,
      persisted: false,
      error_code: "RATE_LIMITED",
      http_status: 429,
      error_category: "rate_limited",
      retryable: true,
      user_message:
        "AI 服务配置已完成；Provider 已启用；模型请求受到服务商限流。HTTP status：429；error_category：rate_limited；retryable：true。",
    } as any);
    renderTab();
    await screen.findByTestId("ai-service-connection-status");
    fireEvent.click(screen.getByTestId("ai-service-test"));
    expect(await screen.findByTestId("ai-service-rate-limited-detail")).toHaveTextContent(
      "error_category：rate_limited",
    );
    expect(screen.getByTestId("ai-service-rate-limited-detail")).toHaveTextContent("429");
    expect(screen.queryByText(/分析配置尚未完成/)).not.toBeInTheDocument();
    expect(screen.queryByText(/云端模型服务尚未开启/)).not.toBeInTheDocument();
  });
});
