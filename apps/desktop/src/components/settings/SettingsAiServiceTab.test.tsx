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
  user_message: "已连接，可以开始分析",
  persisted: true,
  credential_configured: true,
  provider_enabled: true,
  cloud_enabled: true,
  provider_eligible: true,
  selected_provider_id: "aliyun_qwen_plus",
  connection_status: "connected",
  analysis_mode: "BALANCED",
  blockers: [],
  needs_cloud_consent: false,
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
      user_message: "保存成功，已连接，可以开始分析。",
      persisted: true,
    } as any);
  });

  afterEach(() => {
    cleanup();
  });

  it("shows eligible only when backend provider_eligible is true", async () => {
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "已连接，可以开始分析",
    );
    expect(screen.getByTestId("ai-service-status-facts")).toHaveTextContent("可用于分析：是");
  });

  it("does not show 可开始分析 when eligibility is false even if credential configured", async () => {
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue({
      ...eligibleSetup,
      ok: false,
      provider_eligible: false,
      cloud_enabled: false,
      user_message: "AI 服务已启用，但云端连接未开启",
      needs_cloud_consent: true,
    } as any);
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "云端连接未开启",
    );
    expect(screen.getByTestId("ai-service-status-facts")).toHaveTextContent("可用于分析：否");
    expect(screen.getByTestId("ai-service-repair")).toBeInTheDocument();
  });

  it("test connection calls shared configure service with persist false", async () => {
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue({
      ...eligibleSetup,
      ok: true,
      persisted: false,
      user_message: "连接测试成功（尚未保存配置）。",
    } as any);
    renderTab();
    await screen.findByTestId("ai-service-connection-status");
    fireEvent.click(screen.getByTestId("ai-service-test"));
    await waitFor(() => {
      expect(aiServiceConfig.configureRecommendedQwenService).toHaveBeenCalledWith(
        expect.objectContaining({ persist: false }),
      );
    });
    expect(screen.getByRole("status")).toHaveTextContent("尚未保存");
  });

  it("save calls the same configure service with persist true", async () => {
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
    expect(screen.getByRole("status")).toHaveTextContent("保存成功");
  });

  it("keeps status after remount from backend setup endpoint", async () => {
    const { unmount } = renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "已连接，可以开始分析",
    );
    unmount();
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "已连接，可以开始分析",
    );
    expect(aiServiceConfig.fetchRecommendedQwenStatus).toHaveBeenCalled();
  });
});
