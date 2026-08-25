/**
 * Settings UX polish — local Vitest (CHG-20260721-013).
 * Presentation / IA only; no credential or budget logic changes.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage, normalizeSettingsTab } from "./SettingsPage";
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

// 「隐私与更新」这一屏在桌面和网页两种运行时下长得不一样：没有原生更新器时，
// 整块更新界面换成一句「网页版更新随本地服务更新」。这个测试问的是**桌面版**
// 那一屏（它断言的 check-update-button 只在桌面路径里），所以运行时得说自己是桌面。
// 之前没有这个桩，jsdom 里 canUseNativeUpdater 退回 isTauriRuntime() = false，
// 于是测试在网页那条分支上找一个桌面才有的按钮，必然找不到。
vi.mock("../services/runtimeCapabilities", async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    "../services/runtimeCapabilities",
  );
  return {
    ...actual,
    canUseNativeUpdater: () => true,
  };
});

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
  });

  afterEach(() => cleanup());

  it("maps legacy URLs and keeps license tab", () => {
    expect(normalizeSettingsTab("license", false)).toBe("license");
    expect(normalizeSettingsTab("budget", false)).toBe("cost");
    expect(normalizeSettingsTab("general", false)).toBe("appearance");
    renderPage("/settings?tab=license");
    expect(screen.getByTestId("settings-tab-license")).toBeInTheDocument();
  });

  it("设置只有六个标签，没有开发者那一个", async () => {
    // 「开发者设置」已经删除——它的开关、它的标签页、它背后的模式，一个都不剩。
    renderPage();
    expect(await screen.findByTestId("settings-tab-ai")).toHaveTextContent("AI与模型");
    expect(screen.getByTestId("settings-tab-data")).toHaveTextContent("数据与备份");
    expect(screen.getByTestId("settings-tab-license")).toHaveTextContent("授权与专业版");
    expect(screen.queryByTestId("settings-tab-advanced")).not.toBeInTheDocument();
  });
});

describe("AI service simplified page", () => {
  beforeEach(() => {
  });
  afterEach(() => cleanup());

  it("一张状态卡、一个主按钮", async () => {
    renderPage("/settings?tab=ai");
    // 状态文案由后端给，这里只确认它渲染出来了；具体措辞的断言在 AiConnectionPanel.test.tsx。
    expect(await screen.findByTestId("ai-connection-status")).toBeInTheDocument();
    expect(screen.getByTestId("ai-save")).toBeInTheDocument();
    // 改版前这一页有两个 API Key 输入框、两组保存/验证按钮。现在只有一套。
    expect(screen.queryByTestId("ai-service-save")).not.toBeInTheDocument();
  });
});

describe("usage remaining summary", () => {
  beforeEach(() => {
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
