/**
 * AI connection UI state machine — local Vitest (CHG-20260721-013 follow-up).
 */
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

const baseProvider = {
  name: "aliyun_qwen_plus",
  configured: true,
  connected: true,
  healthy: true,
  enabled: true,
  manual_boundary_candidate_eligible: true,
  capabilities: { cloud: true },
};

const baseConfig = {
  provider_name: "aliyun_qwen_plus",
  display_name: "阿里云百炼",
  plus_model: "qwen3.7-plus",
  credential_state: "configured",
  enabled: true,
  disconnected: false,
  connection_state: "connected",
};

function setupStatus(overrides: Record<string, unknown> = {}) {
  return {
    ok: false,
    user_message: "",
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
    cloud_body_consent: true,
    connection_ui_state: "CONFIGURED_NOT_VERIFIED",
    connection_ui_label: "已配置，尚未验证",
    connection_ui_reason: "请验证模型服务后再开始分析。",
    model_validated: false,
    analysis_ready: false,
    config_profile: {
      runtime_mode: "browser_dev",
      app_env: "development",
      data_directory: "D:/dev/data",
      database_path: "D:/dev/data/storylens.db",
      credential_store: { type: "KeyringCredentialStore", available: true, desktop_parity: true },
      user_message: "dev",
    },
    ...overrides,
  };
}

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

describe("AI connection UI state (CHG-013)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAdvancedSettingsStore.setState({ showAdvancedSettings: false });
    vi.mocked(settingsApi.cloud).mockResolvedValue({ enabled: true, state: "available" });
    vi.mocked(providersApi.list).mockResolvedValue([baseProvider] as any);
    vi.mocked(providersApi.configuration).mockResolvedValue(baseConfig as any);
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue(
      setupStatus() as any,
    );
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue(
      setupStatus({
        ok: true,
        connection_ui_state: "READY",
        connection_ui_label: "可以开始分析",
        connection_ui_reason: "当前配置可以连接阿里云百炼。最近验证：2026-07-22 14:35",
        validated_at_display: "2026-07-22 14:35",
        validated_model: "qwen3.7-plus",
        model_validated: true,
        analysis_ready: true,
        cloud_body_consent: true,
        user_message: "模型服务验证成功。",
      }) as any,
    );
  });

  afterEach(() => cleanup());

  it("shows configured-not-verified without claiming ready", async () => {
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "已配置，尚未验证",
    );
    expect(screen.queryByText("已就绪")).not.toBeInTheDocument();
    expect(screen.getByTestId("ai-service-save")).toHaveTextContent("验证连接");
  });

  it("shows verifying label while request in flight", async () => {
    let resolveConfig!: (v: unknown) => void;
    const ready = setupStatus({
      ok: true,
      connection_ui_state: "READY",
      connection_ui_label: "可以开始分析",
      validated_at_display: "2026-07-22 14:35",
      user_message: "模型服务验证成功。",
      cloud_body_consent: true,
      analysis_ready: true,
      model_validated: true,
    });
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveConfig = resolve;
        }) as any,
    );
    renderTab();
    await screen.findByTestId("ai-service-save");
    fireEvent.click(screen.getByTestId("ai-service-save"));
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "正在验证",
    );
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue(ready as any);
    resolveConfig(ready);
    await waitFor(() =>
      expect(screen.getByTestId("ai-service-connection-status")).toHaveTextContent(
        "可以开始分析",
      ),
    );
  });

  it("shows validated time after success and keeps single primary button", async () => {
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue(
      setupStatus({
        connection_ui_state: "READY",
        connection_ui_label: "可以开始分析",
        connection_ui_reason: "当前配置可以连接阿里云百炼。最近验证：2026-07-22 14:35",
        validated_at_display: "2026-07-22 14:35",
        validated_model: "qwen3.7-plus",
        analysis_ready: true,
        model_validated: true,
        cloud_body_consent: true,
      }) as any,
    );
    renderTab();
    expect(await screen.findByTestId("ai-service-validated-at")).toHaveTextContent(
      "2026-07-22 14:35",
    );
    expect(screen.getByTestId("ai-service-save")).toHaveTextContent("重新验证");
    expect(screen.getByTestId("ai-service-test")).toHaveClass("visually-hidden");
  });

  it("shows config-changed after fingerprint mismatch", async () => {
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue(
      setupStatus({
        connection_ui_state: "CONFIG_CHANGED",
        connection_ui_label: "配置已更改，需要重新验证",
        connection_ui_reason: "配置或凭据已变化，请重新验证模型服务。",
        validated_at_display: "2026-07-22 14:35",
      }) as any,
    );
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "配置已更改，需要重新验证",
    );
  });

  it("does not show 已就绪 when consent missing", async () => {
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue(
      setupStatus({
        connection_ui_state: "CONSENT_REQUIRED",
        connection_ui_label: "连接已验证，分析前需确认正文发送",
        connection_ui_reason: "勾选正文发送同意后即可开始分析。最近验证：2026-07-22 14:35",
        validated_at_display: "2026-07-22 14:35",
        cloud_body_consent: false,
        analysis_ready: false,
        model_validated: true,
      }) as any,
    );
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "连接已验证，分析前需确认正文发送",
    );
    expect(screen.getByTestId("cloud-body-consent")).not.toBeChecked();
    expect(screen.queryByText("已就绪")).not.toBeInTheDocument();
  });

  it("hydrates consent checkbox from persisted flag", async () => {
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue(
      setupStatus({
        cloud_body_consent: true,
        connection_ui_state: "READY",
        connection_ui_label: "可以开始分析",
        analysis_ready: true,
      }) as any,
    );
    renderTab();
    expect(await screen.findByTestId("cloud-body-consent")).toBeChecked();
  });

  it("keeps connection details collapsed and disconnect inside details", async () => {
    renderTab();
    const details = await screen.findByTestId("ai-connection-details");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByTestId("ai-service-disconnect")).toBeInTheDocument();
  });

  it("does not surface raw error codes on ordinary status line", async () => {
    vi.mocked(aiServiceConfig.fetchRecommendedQwenStatus).mockResolvedValue(
      setupStatus({
        connection_ui_state: "VERIFICATION_FAILED",
        connection_ui_label: "API Key无效",
        connection_ui_reason: "最近验证失败：2026-07-22 14:35",
        error_code: "CREDENTIAL_INVALID",
      }) as any,
    );
    renderTab();
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "API Key无效",
    );
    expect(screen.getByTestId("ai-service-connection-status")).not.toHaveTextContent(
      "CREDENTIAL_INVALID",
    );
  });
});
