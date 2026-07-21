/**
 * Settings UX polish — local Vitest (CHG-20260721-013).
 * Presentation / IA only; no credential or budget logic changes.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage, normalizeSettingsTab } from "./SettingsPage";
import { useAdvancedSettingsStore } from "../stores/advancedSettingsStore";
import { useDeveloperModeStore } from "../stores/developerModeStore";
import { settingsApi } from "../services/settingsApi";

vi.mock("../services/settingsApi", () => ({
  settingsApi: {
    cloud: vi.fn(async () => ({ enabled: true })),
    cloudBudget: vi.fn(async () => ({
      cloud_daily_estimated_cost_limit: 20,
      cloud_daily_request_limit: 100,
      cloud_daily_token_limit: 500000,
      currency: "CNY",
    })),
    cloudUsage: vi.fn(async () => ({
      estimated_cost: 1.2,
      request_count: 7,
      total_tokens: 12000,
      remaining_estimated_cost: 18.8,
      remaining_requests: 93,
      remaining_tokens: 488000,
      date: "2026-07-21",
    })),
    diagnostics: vi.fn(async () => ({
      data_directory: "D:/StoryLens/data",
      database_path: "D:/StoryLens/data/storylens.db",
      log_directory: "D:/StoryLens/data/logs",
      app_env: "development",
    })),
    save: vi.fn(async () => ({})),
    saveCloudBudget: vi.fn(async () => ({})),
  },
}));

vi.mock("../services/providersApi", () => ({
  providersApi: {
    list: vi.fn(async () => [
      {
        name: "aliyun_qwen_plus",
        configured: true,
        connected: true,
        healthy: true,
        enabled: true,
        manual_boundary_candidate_eligible: true,
        capabilities: { cloud: true },
      },
    ]),
    configuration: vi.fn(async () => ({
      provider_name: "aliyun_qwen_plus",
      display_name: "阿里云百炼",
      plus_model: "qwen3.7-plus",
      credential_state: "configured",
      enabled: true,
      disconnected: false,
      connection_state: "connected",
    })),
    action: vi.fn(),
  },
}));

vi.mock("../services/aiServiceConfig", async () => {
  const actual = await vi.importActual<typeof import("../services/aiServiceConfig")>(
    "../services/aiServiceConfig",
  );
  return {
    ...actual,
    fetchRecommendedQwenStatus: vi.fn(async () => ({
      ok: true,
      credential_configured: true,
      provider_enabled: true,
      cloud_enabled: true,
      provider_eligible: true,
      analysis_ready: true,
      analysis_mode: "BALANCED",
      blockers: [],
      needs_cloud_consent: false,
      cloud_body_consent: true,
      config_profile: {
        runtime_mode: "browser_dev",
        data_directory: "D:/dev/data",
        packaged_data_directory_hint: "C:/Users/x/AppData/Local/StoryLens",
        isolates_sqlite_from_packaged: true,
        user_message: "开发模式隔离说明",
        credential_store: {
          type: "KeyringCredentialStore",
          available: true,
          desktop_parity: true,
        },
      },
    })),
    configureRecommendedQwenService: vi.fn(async () => ({
      ok: true,
      user_message: "验证成功",
      persisted: true,
      model_validated: true,
    })),
    repairRecommendedQwenSetup: vi.fn(),
  };
});

function renderPage(initial = "/settings") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("settings tab IA (CHG-013)", () => {
  beforeEach(() => {
    useAdvancedSettingsStore.setState({ showAdvancedSettings: false });
    useDeveloperModeStore.setState({ developerMode: false });
  });

  afterEach(() => cleanup());

  it("maps legacy URLs and hides license tab", () => {
    expect(normalizeSettingsTab("license", false)).toBe("ai");
    expect(normalizeSettingsTab("budget", false)).toBe("cost");
    expect(normalizeSettingsTab("general", false)).toBe("appearance");
    renderPage("/settings?tab=license");
    expect(screen.queryByTestId("settings-tab-license")).not.toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-ai")).toBeInTheDocument();
  });

  it("shows five ordinary tabs and developer tab when enabled", async () => {
    renderPage();
    expect(await screen.findByTestId("settings-tab-ai")).toHaveTextContent("AI与模型");
    expect(screen.getByTestId("settings-tab-data")).toHaveTextContent("数据与备份");
    expect(screen.queryByTestId("settings-tab-advanced")).not.toBeInTheDocument();
    useDeveloperModeStore.setState({ developerMode: true });
    cleanup();
    renderPage();
    expect(await screen.findByTestId("settings-tab-advanced")).toHaveTextContent("开发者设置");
    useDeveloperModeStore.setState({ developerMode: false });
  });
});

describe("AI service simplified page", () => {
  beforeEach(() => {
    useAdvancedSettingsStore.setState({ showAdvancedSettings: false });
    useDeveloperModeStore.setState({ developerMode: false });
  });
  afterEach(() => cleanup());

  it("shows compact status and one primary save action", async () => {
    renderPage("/settings?tab=ai");
    expect(await screen.findByTestId("ai-service-connection-status")).toHaveTextContent(
      "已配置，尚未验证",
    );
    expect(screen.getByTestId("ai-config-environment-banner")).toHaveTextContent("开发环境");
    expect(screen.getByTestId("ai-service-save")).toBeInTheDocument();
    expect(screen.getByTestId("cloud-body-consent")).toBeInTheDocument();
  });
});

describe("usage remaining summary", () => {
  beforeEach(() => {
    useDeveloperModeStore.setState({ developerMode: false });
  });
  afterEach(() => cleanup());

  it("emphasizes remaining quota cards", async () => {
    renderPage("/settings?tab=cost");
    expect(await screen.findByTestId("cost-remaining-cost")).toBeInTheDocument();
    expect(screen.getByTestId("cost-remaining-requests")).toBeInTheDocument();
    expect(screen.getByTestId("cost-remaining-tokens")).toBeInTheDocument();
    expect(screen.getByTestId("cost-save")).toHaveTextContent("保存上限");
  });
});

describe("data & backup", () => {
  beforeEach(() => {
    useDeveloperModeStore.setState({ developerMode: false });
  });
  afterEach(() => cleanup());

  it("hides unimplemented backup buttons", async () => {
    renderPage("/settings?tab=data");
    expect(await screen.findByTestId("data-backup-coming-soon")).toBeInTheDocument();
    expect(screen.queryByTestId("backup-library")).not.toBeInTheDocument();
    expect(screen.queryByTestId("data-import-hint")).not.toBeInTheDocument();
    expect(screen.getByTestId("open-data-dir")).toBeInTheDocument();
  });
});

describe("privacy & update", () => {
  beforeEach(() => {
    useAdvancedSettingsStore.setState({ showAdvancedSettings: false });
    useDeveloperModeStore.setState({ developerMode: false });
  });
  afterEach(() => cleanup());

  it("keeps update and telemetry without raw manifest URL for ordinary users", async () => {
    renderPage("/settings?tab=privacy");
    expect(await screen.findByTestId("check-update-button")).toBeInTheDocument();
    expect(screen.getByTestId("telemetry-settings-card")).toBeInTheDocument();
    expect(screen.queryByTestId("update-channel-select")).not.toBeInTheDocument();
    expect(screen.queryByText(/latest\.json/i)).not.toBeInTheDocument();
  });
});

describe("layout breakpoints (css contract)", () => {
  it("defines 1024/1180 responsive rules", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const css = fs.readFileSync(
      path.join(__dirname, "../components/settings/settings.css"),
      "utf8",
    );
    expect(css).toContain("max-width: 1040px");
    expect(css).toContain("@media (max-width: 1180px)");
    expect(css).toContain("@media (max-width: 1024px)");
  });
});

describe("save behavior regression smoke", () => {
  afterEach(() => cleanup());

  it("still saves cloud budget via existing API", async () => {
    renderPage("/settings?tab=cost");
    await waitFor(() => expect(screen.getByTestId("cost-limit-input")).toHaveValue(20));
    fireEvent.click(screen.getByTestId("cost-save"));
    await waitFor(() => expect(settingsApi.saveCloudBudget).toHaveBeenCalled());
  });
});
