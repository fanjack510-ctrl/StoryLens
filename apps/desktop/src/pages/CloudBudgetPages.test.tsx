import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "./SettingsPage";
import { settingsApi } from "../services/settingsApi";
import { providersApi } from "../services/providersApi";

vi.mock("../services/settingsApi", () => ({ settingsApi: {
  diagnostics: vi.fn(), get: vi.fn(), save: vi.fn(), cloud: vi.fn(), setCloud: vi.fn(),
  cloudBudget: vi.fn(), saveCloudBudget: vi.fn(), cloudUsage: vi.fn(), cloudPricing: vi.fn(),
} }));
vi.mock("../services/providersApi", () => ({ providersApi: {
  list: vi.fn(), cloud: vi.fn(), setCloud: vi.fn(), routing: vi.fn(), action: vi.fn(),
  deleteCredentials: vi.fn(), startLocal: vi.fn(), stopLocal: vi.fn(),
  configuration: vi.fn(), save: vi.fn(),
  transportDiagnostic: vi.fn(), connectionTestPreflight: vi.fn(), testConnection: vi.fn(),
} }));
vi.mock("../services/aiServiceConfig", async () => {
  const actual = await vi.importActual<typeof import("../services/aiServiceConfig")>(
    "../services/aiServiceConfig",
  );
  return {
    ...actual,
    fetchRecommendedQwenStatus: vi.fn(async () => ({
      ok: false,
      user_message: "尚未填写 API Key",
      persisted: true,
      credential_configured: false,
      provider_enabled: false,
      cloud_enabled: false,
      provider_eligible: false,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "unconfigured",
      analysis_mode: null,
      blockers: ["credential_missing"],
      needs_cloud_consent: false,
    })),
    configureRecommendedQwenService: vi.fn(),
    repairRecommendedQwenSetup: vi.fn(),
  };
});
vi.mock("../components/providers/AliyunForm", () => ({ AliyunForm: () => <div>API Key 不回显</div> }));

const budget = {
  cloud_request_budget_enabled: true, cloud_max_input_tokens_per_request: 16000,
  cloud_max_output_tokens_per_request: 2000, cloud_max_requests_per_run: 10,
  cloud_daily_request_limit: 30, cloud_daily_token_limit: 200000,
  cloud_daily_estimated_cost_limit: 1, currency: "CNY",
  cloud_stop_on_unknown_pricing: true, cloud_confirm_each_paid_test: true,
  pricing_configured: false, pricing_version: "unconfigured",
};
const usage = { request_count: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0,
  estimated_cost: 0, remaining_estimated_cost: 1,
  blocked_reasons: ["云端总开关已关闭", "价格未知或尚未验证"] };
const plusProvider = {
  capability_schema_version: "1c-a-2",
  name: "aliyun_qwen_plus",
  default_model: "qwen3.7-plus",
  enabled: true,
  healthy: true,
  configured: false,
  connected: false,
  capabilities: { enabled: true, cloud: true, region: "cn-beijing", default: false, manual_only: false, structured_output_mode: "json_object", sends_content_to_cloud: true, profile_name: "aliyun_qwen_plus", supports_boundary_candidates: true, requires_boundary_review: true, automatic_boundary_routing: false },
};
const renderPage = (page: React.ReactNode) => render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{page}</QueryClientProvider></MemoryRouter>);

beforeEach(() => {
  localStorage.removeItem("storylens.showAdvancedSettings");
  localStorage.removeItem("storylens.onboarding.v1");
  vi.mocked(settingsApi.diagnostics).mockResolvedValue({ fastapi: "ok", sqlite: "ok" });
  vi.mocked(settingsApi.cloud).mockResolvedValue({ enabled: false, state: "disabled" });
  vi.mocked(settingsApi.setCloud).mockResolvedValue({});
  vi.mocked(settingsApi.save).mockResolvedValue({});
  vi.mocked(settingsApi.cloudBudget).mockResolvedValue(budget);
  vi.mocked(settingsApi.saveCloudBudget).mockResolvedValue(budget);
  vi.mocked(settingsApi.cloudUsage).mockResolvedValue(usage);
  vi.mocked(settingsApi.cloudPricing).mockResolvedValue({ configured: true, valid: true, enabled: false, pricing_version: "unconfigured" });
  vi.mocked(providersApi.list).mockResolvedValue([plusProvider] as any);
  vi.mocked(providersApi.cloud).mockResolvedValue({ enabled: false, state: "disabled" });
  vi.mocked(providersApi.routing).mockResolvedValue([]);
  vi.mocked(providersApi.setCloud).mockResolvedValue({});
  vi.mocked(providersApi.configuration).mockResolvedValue({
    display_name: "阿里云百炼",
    plus_model: "qwen3.7-plus",
    credential_state: "missing",
    enabled: false,
    disconnected: true,
  });
  vi.mocked(providersApi.transportDiagnostic).mockResolvedValue({
    overall_status: "ok",
    configuration_valid: true,
    dns: { status: "ok", latency_ms: 1 },
    tcp: { status: "ok", latency_ms: 2 },
    tls: { status: "ok", latency_ms: 3, certificate_valid: true },
    proxy: { detected: false, source: null },
    ca_bundle: { status: "ok", source: "certifi" },
    request_endpoint_shape: { status: "ok", path_redacted: "/…/compatible-mode/v1/chat/completions" },
    error_code: null,
    user_action_hint: null,
    note: "传输诊断不会调用模型，不消耗Token。",
  });
  vi.mocked(providersApi.connectionTestPreflight).mockResolvedValue({
    provider: "aliyun_qwen_plus",
    configured_model: "qwen3.7-plus",
    max_output_tokens: 32,
    max_real_requests: 1,
    estimated_cost: 0.001,
    currency: "CNY",
    pricing_version: "test-pricing-v1",
    remaining_requests: 20,
    remaining_tokens: 90000,
    remaining_estimated_cost: 2.5,
    within_budget: true,
    blockers: [],
    sends_user_content: false,
  });
  vi.mocked(providersApi.testConnection).mockResolvedValue({
    status: "healthy",
    http_status: 200,
    provider: "aliyun_qwen_plus",
    configured_model: "qwen3.7-plus",
    response_model: "qwen3.7-plus-response",
    json_valid: true,
    schema_valid: true,
    input_tokens: 37,
    output_tokens: 6,
    total_tokens: 43,
    latency_ms: 120,
    invocation_id: 92,
    estimated_cost: 0.001,
    currency: "CNY",
    pricing_version: "test-pricing-v1",
    request_id: "rid#abcdef",
    retryable: false,
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("设置页结构", () => {
  it("普通模式显示含授权的标签且无高级设置", async () => {
    renderPage(<SettingsPage />);
    expect(await screen.findByTestId("settings-tabs")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-ai")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-cost")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-data")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-privacy")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-appearance")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-license")).toHaveTextContent("授权与专业版");
    expect(screen.queryByTestId("settings-tab-advanced")).not.toBeInTheDocument();
  });

  // 「开启高级设置后显示高级标签」删除：开发者模式与它的标签页已经整个删除，没有任何开关
  // 能把它打开。技术项去处见 AiConnectionPanel（接口地址 / 本地模型）与使用额度（逐项上限）。
});

describe("外观与AI服务普通模式", () => {
  it("外观页可保存且无 Demo 徽章", async () => {
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-appearance"));
    // 「演示标记」原本和开发者开关同住一个折叠里，只有开发者模式能看见；那个折叠已经删除。
    expect(screen.queryByTestId("demo-mode-switch")).not.toBeInTheDocument();
    expect(screen.queryByText("演示")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(settingsApi.save).toHaveBeenCalled());
  });

  it("AI 页不把工程字段摊在主视图上", async () => {
    // 原断言里那句 `ai-service-name === "阿里云百炼（推荐）"` 正是改版要修的东西：那一栏是
    // 写死的字符串，跟当前选中的服务商无关。现在服务商由下拉决定，工程参数收进高级设置。
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-ai"));
    expect(await screen.findByTestId("ai-connection-status")).toBeInTheDocument();
    expect(screen.queryByText("Workspace ID")).not.toBeInTheDocument();
    expect(screen.queryByText("Region")).not.toBeInTheDocument();
    expect(screen.queryByText("路由预览")).not.toBeInTheDocument();
  });

  // 「诊断详情保留原始错误码」删除：那个折叠属于开发者模式，已随之删除。错误码现在由后端
  // 翻译成人话，逐条挂在连接状态下面（见 AiConnectionPanel.test.tsx 的「拦路原因逐条列出」）。
});

describe("使用额度", () => {
  // 请求数与 Token 两个日限已经不再拦人——它们量的是同一件事的另外两种单位，用得多就是
  // 花得多。曾出现实际只花 ¥1.7、费用额度 ¥50 一分没动，却因为 Token 到顶而无法分析。
  it("只留费用一个额度入口", async () => {
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-cost"));
    await waitFor(() => expect(screen.getByTestId("cost-limit-input")).toHaveValue(1));
    expect(screen.queryByTestId("cost-request-limit-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("cost-token-limit-input")).not.toBeInTheDocument();
    // 用量仍然照常统计并显示，只是不再各自设闸。
    expect(screen.getByTestId("cost-limits-note")).toBeInTheDocument();
    expect(screen.queryByLabelText("单请求最大输入 Token")).not.toBeInTheDocument();
  });

  it("保存费用额度到后端", async () => {
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-cost"));
    const input = await screen.findByTestId("cost-limit-input");
    await waitFor(() => expect(input).toHaveValue(1));
    fireEvent.change(input, { target: { value: "8" } });
    fireEvent.click(screen.getByTestId("cost-save"));
    expect(await screen.findByText("额度设置已保存。")).toBeInTheDocument();
    expect(settingsApi.saveCloudBudget).toHaveBeenCalledWith(
      expect.objectContaining({ cloud_daily_estimated_cost_limit: 8 }),
    );
  });
  it("拒绝非法费用输入", async () => {
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-cost"));
    const input = await screen.findByTestId("cost-limit-input");
    await waitFor(() => expect(input).toHaveValue(1));
    fireEvent.change(input, { target: { value: "0" } });
    fireEvent.click(screen.getByTestId("cost-save"));
    expect(await screen.findByText(/保存失败/)).toBeInTheDocument();
    expect(settingsApi.saveCloudBudget).not.toHaveBeenCalled();
  });

  it("逐项用量上限在 AI 页的高级设置里，默认值不变", async () => {
    // 这一块原本住在「开发者设置」。开发者模式删除后它需要新家——不能放「使用额度」：
    // 那一页刚刚才把请求数与 Token 日限拿掉（见上一条），搬回去等于把那个决定推翻。
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-ai"));
    fireEvent.click(await screen.findByTestId("ai-advanced-toggle"));
    expect(await screen.findByLabelText("单请求最大输入 Token")).toHaveValue(16000);
    expect(screen.getByLabelText("单请求最大输出 Token")).toHaveValue(2000);
  });
});


// 真实连接测试 moved out of the deleted /providers page into 设置 · 开发者设置
// (components/settings/RealConnectionTest.tsx) and is covered by its own test there.
