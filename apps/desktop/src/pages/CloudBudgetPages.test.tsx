import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "./SettingsPage";
import { ProvidersPage } from "./ProvidersPage";
import { settingsApi } from "../services/settingsApi";
import { providersApi } from "../services/providersApi";
import { useDeveloperModeStore } from "../stores/developerModeStore";
import { useAdvancedSettingsStore } from "../stores/advancedSettingsStore";

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
  localStorage.removeItem("storylens.developerMode");
  localStorage.removeItem("storylens.showAdvancedSettings");
  localStorage.removeItem("storylens.onboarding.v1");
  useDeveloperModeStore.setState({ developerMode: false });
  useAdvancedSettingsStore.setState({ showAdvancedSettings: false });
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
  it("普通模式显示六个标签且无高级设置", async () => {
    renderPage(<SettingsPage />);
    expect(await screen.findByTestId("settings-tabs")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-ai")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-cost")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-data")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-privacy")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-license")).toBeInTheDocument();
    expect(screen.getByTestId("settings-tab-appearance")).toBeInTheDocument();
    expect(screen.queryByTestId("settings-tab-advanced")).not.toBeInTheDocument();
  });

  it("开启高级设置后显示高级标签", async () => {
    useAdvancedSettingsStore.setState({ showAdvancedSettings: true });
    renderPage(<SettingsPage />);
    expect(await screen.findByTestId("settings-tab-advanced")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("settings-tab-advanced"));
    expect(await screen.findByTestId("settings-panel-advanced")).toBeInTheDocument();
    expect(await screen.findByTestId("advanced-provider-list")).toBeInTheDocument();
  });
});

describe("外观与AI服务普通模式", () => {
  it("外观页可保存且无 Demo 徽章", async () => {
    useAdvancedSettingsStore.setState({ showAdvancedSettings: true });
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-appearance"));
    expect(screen.getByTestId("demo-mode-switch")).toBeInTheDocument();
    expect(screen.queryByText("演示")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(settingsApi.save).toHaveBeenCalled());
  });

  it("普通模式不显示Provider工程字段", async () => {
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-ai"));
    expect(await screen.findByTestId("ai-service-status-card")).toBeInTheDocument();
    expect(screen.getByTestId("ai-service-name")).toHaveValue("阿里云百炼（推荐）");
    expect(screen.queryByText("Workspace ID")).not.toBeInTheDocument();
    expect(screen.queryByText("Base URL")).not.toBeInTheDocument();
    expect(screen.queryByText("Region")).not.toBeInTheDocument();
    expect(screen.queryByText("路由预览")).not.toBeInTheDocument();
    expect(screen.queryByText(/aliyun_qwen_plus/)).not.toBeInTheDocument();
  });

  it("诊断详情保留原始错误码", async () => {
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-ai"));
    fireEvent.click(await screen.findByTestId("ai-service-diagnostics-toggle"));
    const diag = await screen.findByTestId("ai-service-diagnostics");
    expect(diag.textContent).toMatch(/providerId|aliyun_qwen_plus/);
  });
});

describe("使用费用", () => {
  it("显示费用、请求与 Token 额度入口且无高级单请求字段", async () => {
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-cost"));
    await waitFor(() => expect(screen.getByTestId("cost-limit-input")).toHaveValue(1));
    expect(screen.getByTestId("cost-request-limit-input")).toHaveValue(30);
    expect(screen.getByTestId("cost-token-limit-input")).toHaveValue(200000);
    expect(screen.queryByLabelText("单请求最大输入 Token")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("启用云端AI")).not.toBeInTheDocument();
  });

  it("保存费用与请求 Token 额度到后端", async () => {
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-cost"));
    await waitFor(() => expect(screen.getByTestId("cost-limit-input")).toHaveValue(1));
    fireEvent.change(screen.getByTestId("cost-request-limit-input"), { target: { value: "80" } });
    fireEvent.change(screen.getByTestId("cost-token-limit-input"), { target: { value: "300000" } });
    fireEvent.click(screen.getByTestId("cost-save"));
    expect(await screen.findByText("额度设置已保存。")).toBeInTheDocument();
    expect(settingsApi.saveCloudBudget).toHaveBeenCalledWith(
      expect.objectContaining({
        cloud_daily_estimated_cost_limit: 1,
        cloud_daily_request_limit: 80,
        cloud_daily_token_limit: 300000,
      }),
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

  it("拒绝非法请求额度输入", async () => {
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-cost"));
    const input = await screen.findByTestId("cost-request-limit-input");
    await waitFor(() => expect(input).toHaveValue(30));
    fireEvent.change(input, { target: { value: "0" } });
    fireEvent.click(screen.getByTestId("cost-save"));
    expect(await screen.findByText(/每日请求额度必须为正整数/)).toBeInTheDocument();
    expect(settingsApi.saveCloudBudget).not.toHaveBeenCalled();
  });

  it("高级预算字段仅高级设置可见且默认值不变", async () => {
    useAdvancedSettingsStore.setState({ showAdvancedSettings: true });
    renderPage(<SettingsPage />);
    fireEvent.click(await screen.findByTestId("settings-tab-advanced"));
    expect(await screen.findByLabelText("单请求最大输入 Token")).toHaveValue(16000);
    expect(screen.getByLabelText("单请求最大输出 Token")).toHaveValue(2000);
  });
});

describe("Provider 预算摘要", () => {
  it("显示预算、Token和剩余预算摘要", async () => { renderPage(<ProvidersPage />); expect(await screen.findByText("云端请求保护")).toBeInTheDocument(); expect(screen.getByText("今日 Token")).toBeInTheDocument(); expect(screen.getByText("剩余预算")).toBeInTheDocument(); });
  it("价格未知时显示具体禁用原因", async () => { renderPage(<ProvidersPage />); await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("价格未知或尚未验证")); });
  it("真实连接测试按钮即使门禁阻止也提供确认反馈", async () => {
    renderPage(<ProvidersPage />);
    const button = await screen.findByRole("button", { name: "真实连接测试" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(await screen.findByRole("dialog", { name: "执行真实连接测试" })).toBeInTheDocument();
  });
  it("达到费用上限时仍可打开确认框查看预算", async () => {
    vi.mocked(settingsApi.cloudUsage).mockResolvedValue({ ...usage, estimated_cost: 1, remaining_estimated_cost: 0, blocked_reasons: ["今日估算费用已达到上限"] });
    vi.mocked(providersApi.connectionTestPreflight).mockResolvedValue({
      provider: "aliyun_qwen_plus", configured_model: "qwen3.7-plus",
      max_output_tokens: 32, max_real_requests: 1, estimated_cost: 0.001,
      currency: "CNY", pricing_version: "v1", remaining_requests: 0,
      remaining_tokens: 0, remaining_estimated_cost: 0, within_budget: false,
      blockers: ["INSUFFICIENT_BUDGET_RESERVATION"], sends_user_content: false,
    });
    renderPage(<ProvidersPage />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("今日估算费用已达到上限"));
    fireEvent.click(screen.getByRole("button", { name: "真实连接测试" }));
    expect(await screen.findByText(/当前不可测试/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认并测试" })).toBeDisabled();
  });
  it("显示传输诊断按钮与零费用提示", async () => {
    renderPage(<ProvidersPage />);
    expect(await screen.findByTestId("transport-diagnostic-button")).toBeInTheDocument();
    expect(screen.getByText(/传输诊断不会调用模型，不消耗Token/)).toBeInTheDocument();
    expect(screen.getByText(/可能产生少量Token费用/)).toBeInTheDocument();
  });
  it("传输诊断展示DNS/TCP/TLS结果", async () => {
    renderPage(<ProvidersPage />);
    fireEvent.click(await screen.findByTestId("transport-diagnostic-button"));
    expect(await screen.findByTestId("transport-diagnostic-result")).toHaveTextContent("DNS");
    expect(screen.getByTestId("transport-diagnostic-result")).toHaveTextContent("TCP");
    expect(screen.getByTestId("transport-diagnostic-result")).toHaveTextContent("TLS");
    expect(providersApi.transportDiagnostic).toHaveBeenCalledWith("aliyun_qwen_plus");
  });
  it("后端离线时显示错误", async () => {
    vi.mocked(providersApi.transportDiagnostic).mockRejectedValue(new Error("FastAPI离线"));
    renderPage(<ProvidersPage />);
    fireEvent.click(await screen.findByTestId("transport-diagnostic-button"));
    expect(await screen.findByTestId("transport-diagnostic-error")).toHaveTextContent(/离线|失败/);
  });
});

describe("真实连接测试交互", () => {
  it("点击打开二次确认框，取消不发送模型请求", async () => {
    renderPage(<ProvidersPage />);
    fireEvent.click(await screen.findByTestId("paid-connection-test-button"));
    const dialog = await screen.findByRole("dialog", { name: "执行真实连接测试" });
    expect(dialog).toHaveTextContent("原创最小JSON请求");
    expect(dialog).toHaveTextContent("不发送用户小说正文");
    expect(dialog).toHaveTextContent("qwen3.7-plus");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("dialog", { name: "执行真实连接测试" })).not.toBeInTheDocument();
    expect(providersApi.testConnection).not.toHaveBeenCalled();
  });

  it("确认后显示checking、running并在期间禁用按钮", async () => {
    let resolveTest!: (value: any) => void;
    vi.mocked(providersApi.testConnection).mockImplementation(
      () => new Promise((resolve) => { resolveTest = resolve; }),
    );
    renderPage(<ProvidersPage />);
    fireEvent.click(await screen.findByTestId("paid-connection-test-button"));
    const confirmButton = screen.getByRole("button", { name: "确认并测试" });
    await waitFor(() => expect(confirmButton).toBeEnabled());
    fireEvent.click(confirmButton);
    expect(await screen.findByText(/正在检查Provider和预算/)).toBeInTheDocument();
    expect(screen.getByTestId("paid-connection-test-button")).toBeDisabled();
    expect(await screen.findByText(/正在发送原创最小测试请求/)).toBeInTheDocument();
    resolveTest({
      status: "healthy", http_status: 200, provider: "aliyun_qwen_plus",
      configured_model: "qwen3.7-plus", response_model: "qwen3.7-plus-response",
      json_valid: true, schema_valid: true, input_tokens: 37, output_tokens: 6,
      total_tokens: 43, latency_ms: 120, invocation_id: 92, estimated_cost: 0.001,
      currency: "CNY", pricing_version: "v1", request_id: "rid#abc", retryable: false,
    });
    expect(await screen.findByText("真实连接测试结果：成功")).toBeInTheDocument();
  });

  it("成功结果展示HTTP、模型、Token与Invocation", async () => {
    renderPage(<ProvidersPage />);
    fireEvent.click(await screen.findByTestId("paid-connection-test-button"));
    await screen.findByText("当前剩余预算");
    fireEvent.click(screen.getByRole("button", { name: "确认并测试" }));
    const result = await screen.findByTestId("real-connection-test-result");
    expect(result).toHaveTextContent("HTTP");
    expect(result).toHaveTextContent("qwen3.7-plus-response");
    expect(result).toHaveTextContent("总Token");
    expect(result).toHaveTextContent("43");
    expect(result).toHaveTextContent("Invocation");
    expect(result).toHaveTextContent("#92");
  });

  it("失败展示结构化中文错误且按钮恢复", async () => {
    vi.mocked(providersApi.testConnection).mockRejectedValue({
      code: "PROVIDER_CONNECT_TIMEOUT",
      message: "timeout",
      status: 502,
      requestId: "rid#failed",
      retryable: true,
      userActionHint: "稍后重试",
    });
    renderPage(<ProvidersPage />);
    fireEvent.click(await screen.findByTestId("paid-connection-test-button"));
    await screen.findByText("当前剩余预算");
    fireEvent.click(screen.getByRole("button", { name: "确认并测试" }));
    const error = await screen.findByTestId("real-connection-test-error");
    expect(error).toHaveTextContent("连接云端Provider超时");
    expect(error).toHaveTextContent("PROVIDER_CONNECT_TIMEOUT");
    expect(error).toHaveTextContent("HTTP：502");
    expect(error).toHaveTextContent("是否可重试：是");
    expect(screen.getByTestId("paid-connection-test-button")).toBeEnabled();
  });

  it("传输诊断结果与真实测试结果互不覆盖", async () => {
    renderPage(<ProvidersPage />);
    fireEvent.click(await screen.findByTestId("transport-diagnostic-button"));
    await screen.findByText("传输诊断结果");
    fireEvent.click(screen.getByTestId("paid-connection-test-button"));
    await screen.findByText("当前剩余预算");
    fireEvent.click(screen.getByRole("button", { name: "确认并测试" }));
    await screen.findByText("真实连接测试结果：成功");
    expect(screen.getByText("传输诊断结果")).toBeInTheDocument();
    expect(screen.getByTestId("transport-diagnostic-result")).toHaveTextContent("DNS");
  });

  it("防止双击并且重新渲染不自动重复请求", async () => {
    renderPage(<ProvidersPage />);
    fireEvent.click(await screen.findByTestId("paid-connection-test-button"));
    await screen.findByText("当前剩余预算");
    const confirmButton = screen.getByRole("button", { name: "确认并测试" });
    fireEvent.click(confirmButton);
    fireEvent.click(confirmButton);
    await screen.findByText("真实连接测试结果：成功");
    expect(providersApi.testConnection).toHaveBeenCalledTimes(1);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(providersApi.testConnection).toHaveBeenCalledTimes(1);
  });
});
