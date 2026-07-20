import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsAiServiceTab } from "./SettingsAiServiceTab";
import { providersApi } from "../../services/providersApi";
import { settingsApi } from "../../services/settingsApi";
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

const disconnectedProvider = {
  name: "aliyun_qwen_plus",
  default_model: "qwen3.7-plus",
  configured: true,
  connected: false,
  healthy: false,
  enabled: true,
  status: "unhealthy",
  health_state: "unhealthy",
  health_source: "configured_readiness",
  manual_selection_blockers: ["provider_disconnected"],
  capabilities: { cloud: true, enabled: true },
};

const connectedProvider = {
  ...disconnectedProvider,
  connected: true,
  healthy: true,
  status: "healthy",
  health_state: "healthy",
  manual_selection_blockers: [],
};

const disconnectedConfig = {
  provider_name: "aliyun_qwen_plus",
  display_name: "阿里云百炼",
  plus_model: "qwen3.7-plus",
  credential_state: "configured",
  enabled: true,
  disconnected: true,
  connection_state: "disconnected",
};

const connectedConfig = {
  ...disconnectedConfig,
  disconnected: false,
  connection_state: "connected",
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

describe("SettingsAiServiceTab DEFECT-UAT-002", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAdvancedSettingsStore.setState({ showAdvancedSettings: false });
    vi.mocked(settingsApi.cloud).mockResolvedValue({ enabled: true, state: "available" });
    vi.mocked(settingsApi.setCloud).mockResolvedValue({ enabled: true, state: "available" });
    vi.mocked(settingsApi.cloudUsage).mockResolvedValue({ estimated_cost: 0 });
    vi.mocked(settingsApi.cloudBudget).mockResolvedValue({
      cloud_daily_estimated_cost_limit: 20,
      cloud_daily_request_limit: 100,
      currency: "CNY",
    });
    vi.mocked(settingsApi.saveCloudBudget).mockResolvedValue({
      cloud_daily_estimated_cost_limit: 20,
    } as any);
    vi.mocked(providersApi.list).mockResolvedValue([disconnectedProvider] as any);
    vi.mocked(providersApi.configuration).mockResolvedValue(disconnectedConfig as any);
    vi.mocked(providersApi.action).mockResolvedValue({ status: "ok" } as any);
    vi.mocked(providersApi.transportDiagnostic).mockResolvedValue({
      overall_status: "ok",
      error_code: null,
      dns: { status: "ok" },
      tcp: { status: "ok" },
      tls: { status: "ok" },
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("updates to connected immediately after successful test and ends testing state", async () => {
    vi.mocked(providersApi.configuration)
      .mockResolvedValueOnce(disconnectedConfig as any) // initial query
      .mockResolvedValue(connectedConfig as any); // after persistConnected
    vi.mocked(providersApi.list).mockResolvedValue([connectedProvider] as any);

    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "尚未连接AI服务",
    );

    fireEvent.click(screen.getByTestId("ai-service-test"));
    expect(screen.getByTestId("ai-service-test")).toHaveTextContent("测试中");

    await waitFor(() => {
      expect(providersApi.action).toHaveBeenCalledWith("aliyun_qwen_plus", "connect");
    });
    await waitFor(() => {
      expect(screen.getByTestId("ai-service-connection-status")).toHaveTextContent(
        "已连接，可以开始分析",
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("ai-service-test")).toHaveTextContent("测试连接");
      expect(screen.getByTestId("ai-service-test")).toBeEnabled();
    });
    expect(screen.getByRole("status")).toHaveTextContent("连接测试成功");
  });

  it("keeps connected after remount refresh from backend configuration", async () => {
    vi.mocked(providersApi.list).mockResolvedValue([connectedProvider] as any);
    vi.mocked(providersApi.configuration).mockResolvedValue(connectedConfig as any);

    const { unmount } = renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "已连接，可以开始分析",
    );
    unmount();

    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "已连接，可以开始分析",
    );
    expect(providersApi.configuration).toHaveBeenCalled();
  });

  it("syncs disconnected state after disconnect action", async () => {
    useAdvancedSettingsStore.setState({ showAdvancedSettings: true });
    vi.mocked(providersApi.list).mockResolvedValue([connectedProvider] as any);
    vi.mocked(providersApi.configuration)
      .mockResolvedValueOnce(connectedConfig as any)
      .mockResolvedValue(disconnectedConfig as any);

    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "已连接，可以开始分析",
    );

    fireEvent.click(screen.getByTestId("ai-service-disconnect"));
    await waitFor(() => {
      expect(providersApi.action).toHaveBeenCalledWith("aliyun_qwen_plus", "disconnect");
    });
    await waitFor(() => {
      expect(screen.getByTestId("ai-service-connection-status")).toHaveTextContent(
        "尚未连接AI服务",
      );
    });
  });

  it("does not mark connected when transport test fails", async () => {
    vi.mocked(providersApi.transportDiagnostic).mockResolvedValue({
      overall_status: "failed",
      error_code: "PROVIDER_DNS_ERROR",
      user_action_hint: "检查DNS或主机名",
    });

    renderTab();
    await screen.findByTestId("ai-service-connection-status");
    fireEvent.click(screen.getByTestId("ai-service-test"));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("无法连接");
    });
    expect(providersApi.action).not.toHaveBeenCalledWith("aliyun_qwen_plus", "connect");
    expect(screen.getByTestId("ai-service-connection-status")).toHaveTextContent(
      "无法连接云端服务",
    );
    expect(screen.getByTestId("ai-service-test")).toHaveTextContent("测试连接");
  });
});
