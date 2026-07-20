import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StartAnalysisDialog } from "./StartAnalysisDialog";
import { providersApi } from "../../services/providersApi";
import { analysisApi } from "../../services/analysisApi";
import { analysisRecoveryApi } from "../../services/analysisRecoveryApi";
import { ApiError } from "../../services/apiClient";
import { useDeveloperModeStore } from "../../stores/developerModeStore";

vi.mock("../../services/providersApi", () => ({
  providersApi: { list: vi.fn(), cloud: vi.fn(), configuration: vi.fn() },
}));
vi.mock("../../services/analysisApi", () => ({ analysisApi: { start: vi.fn(), preflight: vi.fn() } }));
vi.mock("../../services/analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    fullPipelinePreflight: vi.fn(async () => ({
      full_expected_requests: 20,
      full_worst_requests: 40,
      remaining_requests: 100,
      remaining_tokens: 200000,
      remaining_cost: 20,
      within_budget: true,
      exceeded_dimensions: [],
      worst_case_tokens: 60000,
      worst_case_cost: 0.4,
      estimated_tokens: 30000,
      estimated_cost: 0.2,
    })),
  },
}));
vi.mock("../../services/settingsApi", () => ({
  settingsApi: {
    cloudBudget: vi.fn(async () => ({
      cloud_daily_request_limit: 100,
      cloud_daily_estimated_cost_limit: 20,
      currency: "CNY",
    })),
    cloudUsage: vi.fn(async () => ({
      request_count: 0,
      remaining_requests: 100,
      remaining_tokens: 200000,
      remaining_estimated_cost: 20,
      reserved_requests: 0,
    })),
  },
}));

const plus = {
  capability_schema_version: "1c-a-2", enabled: true,
  name: "aliyun_qwen_plus", default_model: "configured-plus", configured: true,
  connected: true, healthy: true, allow_auto_route: false, automatic_route_eligible: false,
  eligible_for_automatic_analysis: false, manual_boundary_candidate_eligible: true,
  manual_selection_blockers: [],
  automatic_route_blockers: ["auto_route_disabled"], manual_short_task_eligible: false,
  supports_boundary_candidates: true, requires_boundary_review: true,
  automatic_boundary_routing: false,
  eligibility_status: "eligible", evaluated_at: "2026-07-16T00:00:00Z",
  health_state: "healthy", health_source: "configured_readiness",
  health_checked_at: "2026-07-16T00:00:00Z", provider_state_version: "state-1",
  capabilities: { cloud: true, enabled: true, default: false, manual_only: false,
    structured_output_mode: "json_object", sends_content_to_cloud: true, profile_name: "plus",
    supports_boundary_candidates: true, requires_boundary_review: true,
    automatic_boundary_routing: false },
  workflow_prompts: { boundary_candidate: "v3.5", boundary_adjudication: "v1",
    scene_analysis: "v3.1", thinking: false, boundary_confirmation: "human_required" },
};
const local = { ...plus, name: "local_qwen14", manual_boundary_candidate_eligible: false,
  supports_boundary_candidates: false, requires_boundary_review: false,
  eligible_for_automatic_analysis: true, capabilities: { ...plus.capabilities, cloud: false,
    requires_boundary_review: false, supports_boundary_candidates: false } };

const longPreflight = {
  eligible: true,
  provider_state_version: "state-1",
  within_budget: true,
  exceeded_dimensions: [],
  paragraph_count: 68,
  transition_count: 67,
  detection_batch_count: 10,
  adjudication_batch_count_estimated: 1,
  expected_request_count: 11,
  worst_case_request_count: 22,
  estimated_total_tokens: 14500,
  worst_case_total_tokens: 29109,
  estimated_cost: 0.09,
  worst_case_cost: 0.19,
  currency: "CNY",
  remaining: { requests: 70, tokens: 93011, estimated_cost: 2.676 },
};

const renderDialog = (onClose = vi.fn(), onCreated = vi.fn()) =>
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <StartAnalysisDialog chapterId={7} onClose={onClose} onCreated={onCreated} />
      </QueryClientProvider>
    </MemoryRouter>,
  );

async function openCloudPlusWithConsent() {
  fireEvent.change(screen.getByLabelText("执行方式"), { target: { value: "cloud" } });
  await screen.findByRole("option", { name: /阿里云百炼/ });
  fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "aliyun_qwen_plus" } });
  fireEvent.click(screen.getByRole("checkbox"));
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("storylens.developerMode", "1");
  useDeveloperModeStore.setState({ developerMode: true });
  vi.mocked(providersApi.list).mockResolvedValue([local, plus] as any);
  vi.mocked(providersApi.cloud).mockResolvedValue({ enabled: true, state: "enabled" });
  vi.mocked(providersApi.configuration).mockResolvedValue({
    provider_name: "aliyun_qwen_plus",
    display_name: "阿里云百炼",
    plus_model: "configured-plus",
    credential_state: "configured",
    enabled: true,
    disconnected: false,
    connection_state: "connected",
  } as any);
  vi.mocked(analysisApi.preflight).mockResolvedValue({
    eligible: true,
    provider_state_version: "state-1",
    within_budget: true,
    exceeded_dimensions: [],
    paragraph_count: 10,
    transition_count: 9,
    detection_batch_count: 2,
    adjudication_batch_count_estimated: 1,
    expected_request_count: 3,
    worst_case_request_count: 6,
    estimated_total_tokens: 1000,
    worst_case_total_tokens: 2000,
    estimated_cost: 0.01,
    worst_case_cost: 0.02,
    currency: "CNY",
    remaining: { requests: 70, tokens: 90000, estimated_cost: 2.5 },
  });
  vi.mocked(analysisApi.start).mockResolvedValue({ run_id: 12 });
});
afterEach(cleanup);

describe("开始分析人工审阅入口", () => {
  it("本地模式不显示云端Provider", async () => {
    renderDialog();
    expect(await screen.findByRole("option", { name: /本地模型/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /阿里云百炼/ })).not.toBeInTheDocument();
  });
  it("云端模式显示非默认且关闭自动路由的Plus", async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText("执行方式"), { target: { value: "cloud" } });
    expect(await screen.findByRole("option", { name: /^阿里云百炼$/ })).toBeInTheDocument();
    expect(await screen.findByTestId("start-analysis-provider-hint")).toHaveTextContent(
      /已连接.*需要人工确认场景边界/,
    );
  });
  it("选择Plus显示人工确认说明和三个后端Prompt版本", async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText("执行方式"), { target: { value: "cloud" } });
    const option = await screen.findByRole("option", { name: /阿里云百炼/ });
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: (option as HTMLOptionElement).value } });
    expect(screen.getByText(/本次会先识别场景边界/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText(/v3.5/)).toBeInTheDocument();
    expect(screen.getByText(/v1$/)).toBeInTheDocument();
    expect(screen.getByText(/v3.1/)).toBeInTheDocument();
    expect(screen.queryByText("Prompt v2")).not.toBeInTheDocument();
  });
  it("创建请求携带assisted_boundary_review", async () => {
    renderDialog();
    await openCloudPlusWithConsent();
    await screen.findByTestId("stage1-budget-preview");
    fireEvent.click(screen.getByTestId("start-analysis-submit"));
    await waitFor(() => expect(analysisApi.start).toHaveBeenCalledWith(7, expect.objectContaining({
      analysis_mode: "assisted_boundary_review", provider_name: "aliyun_qwen_plus",
    })));
  });
  it("Stage1预算预览不含Scene Analysis", async () => {
    renderDialog();
    await openCloudPlusWithConsent();
    const preview = await screen.findByTestId("stage1-budget-preview");
    expect(preview).toHaveTextContent("本阶段仅识别场景边界");
    expect(preview).toHaveTextContent("不会执行 Scene Analysis");
    expect(preview).toHaveTextContent("最坏请求");
    expect(preview).toHaveTextContent("6");
    expect(screen.getByTestId("stage1-budget-grid").querySelectorAll(".budget-summary-card").length).toBeGreaterThanOrEqual(13);
  });
  it("创建前显示完整Run请求预检", async () => {
    renderDialog();
    await openCloudPlusWithConsent();
    const full = await screen.findByTestId("full-pipeline-budget-preview");
    expect(full).toHaveTextContent("完整分析预算预检");
    expect(full).toHaveTextContent("Scene Analysis");
    expect(full).toHaveTextContent("Reader Journey");
  });
  it("预算不足时禁止创建并显示维度", async () => {
    vi.mocked(analysisApi.preflight).mockResolvedValue({
      eligible: true, provider_state_version: "state-1", within_budget: false,
      exceeded_dimensions: ["tokens"], paragraph_count: 68, transition_count: 67,
      detection_batch_count: 10, adjudication_batch_count_estimated: 1,
      expected_request_count: 11, worst_case_request_count: 22,
      estimated_total_tokens: 10000, worst_case_total_tokens: 50000,
      estimated_cost: 0.1, worst_case_cost: 0.2, currency: "CNY",
      remaining: { requests: 70, tokens: 42000, estimated_cost: 2.5 },
    });
    renderDialog();
    await openCloudPlusWithConsent();
    expect(await screen.findByTestId("stage1-budget-gap")).toHaveTextContent(/Token不足/);
    expect(screen.getByTestId("start-analysis-submit")).toBeDisabled();
  });
  it("无资格时显示具体blocker", async () => {
    vi.mocked(providersApi.list).mockResolvedValue([{ ...plus, manual_boundary_candidate_eligible: false, manual_selection_blockers: ["budget_unavailable"] }] as any);
    renderDialog();
    fireEvent.change(screen.getByLabelText("执行方式"), { target: { value: "cloud" } });
    fireEvent.click(screen.getByText("技术详情"));
    expect(await screen.findByText("budget_unavailable")).toBeInTheDocument();
  });
  it("资格字段缺失时显示版本不一致而不是无阻塞", async () => {
    const missing = { ...plus } as any;
    delete missing.manual_boundary_candidate_eligible;
    vi.mocked(providersApi.list).mockResolvedValue([missing]);
    renderDialog();
    fireEvent.change(screen.getByLabelText("执行方式"), { target: { value: "cloud" } });
    fireEvent.click(screen.getByText("技术详情"));
    expect(await screen.findByText(/Provider资格信息缺失/)).toBeInTheDocument();
    expect(screen.queryByText(/无手动资格阻塞/)).not.toBeInTheDocument();
  });
  it("Provider API离线显示明确诊断", async () => {
    vi.mocked(providersApi.list).mockRejectedValue(new Error("FastAPI离线"));
    renderDialog();
    fireEvent.change(screen.getByLabelText("执行方式"), { target: { value: "cloud" } });
    fireEvent.click(screen.getByText("技术详情"));
    expect(await screen.findByText(/Provider 状态接口离线/)).toBeInTheDocument();
  });
});

describe("StartAnalysisDialog 布局与交互", () => {
  it("长预算内容时 Modal Body 可滚动且 Footer 始终存在", async () => {
    vi.mocked(analysisApi.preflight).mockResolvedValue(longPreflight);
    renderDialog();
    await openCloudPlusWithConsent();
    const body = await screen.findByTestId("start-analysis-modal-body");
    const footer = screen.getByTestId("start-analysis-modal-footer");
    expect(body.className).toContain("modal-body");
    expect(getComputedStyle(body).overflowY === "auto" || body.className.includes("modal-body")).toBe(true);
    expect(footer).toBeInTheDocument();
    expect(within(footer).getByTestId("start-analysis-submit")).toBeVisible();
    expect(within(footer).getByText("取消")).toBeVisible();
    Object.defineProperty(body, "scrollHeight", { configurable: true, value: 2400 });
    Object.defineProperty(body, "clientHeight", { configurable: true, value: 360 });
    expect(body.scrollHeight).toBeGreaterThan(body.clientHeight);
  });

  it("创建任务按钮在 DOM 中可见", async () => {
    renderDialog();
    expect(screen.getByTestId("start-analysis-submit")).toBeVisible();
  });

  it("Provider诊断展开后仍可滚动", async () => {
    vi.mocked(analysisApi.preflight).mockResolvedValue(longPreflight);
    renderDialog();
    await openCloudPlusWithConsent();
    await screen.findByTestId("stage1-budget-preview");
    fireEvent.click(screen.getByText("技术详情"));
    expect(await screen.findByText(/手动边界资格/)).toBeInTheDocument();
    const body = screen.getByTestId("start-analysis-modal-body");
    expect(body).toBeInTheDocument();
    expect(screen.getByTestId("start-analysis-modal-footer")).toBeInTheDocument();
  });

  it("1366×768 视口下按钮可见", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1366 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 768 });
    vi.mocked(analysisApi.preflight).mockResolvedValue(longPreflight);
    renderDialog();
    await openCloudPlusWithConsent();
    await screen.findByTestId("stage1-budget-preview");
    expect(screen.getByTestId("start-analysis-submit")).toBeVisible();
    expect(screen.getByText("取消")).toBeVisible();
  });

  it("checking 状态按钮禁用但不消失", async () => {
    let resolvePreflight!: (value: any) => void;
    vi.mocked(analysisApi.preflight)
      .mockResolvedValueOnce(longPreflight)
      .mockImplementationOnce(() => new Promise((resolve) => { resolvePreflight = resolve; }));
    renderDialog();
    await openCloudPlusWithConsent();
    await screen.findByTestId("stage1-budget-preview");
    fireEvent.click(screen.getByTestId("start-analysis-submit"));
    const checking = await screen.findByRole("button", { name: "正在检查预算……" });
    expect(checking).toBeDisabled();
    expect(checking).toBeVisible();
    expect(screen.getByTestId("start-analysis-modal-footer")).toBeInTheDocument();
    resolvePreflight({ ...longPreflight, eligible: true, within_budget: true });
  });

  it("创建失败后 Footer 仍可见", async () => {
    vi.mocked(analysisApi.preflight).mockResolvedValue(longPreflight);
    vi.mocked(analysisApi.start).mockRejectedValue(
      new ApiError("PROVIDER_UNHEALTHY", "健康检查失败", 503),
    );
    renderDialog();
    await openCloudPlusWithConsent();
    await screen.findByTestId("stage1-budget-preview");
    fireEvent.click(screen.getByTestId("start-analysis-submit"));
    await waitFor(() => expect(screen.getByText(/健康检查失败|PROVIDER_UNHEALTHY/)).toBeInTheDocument());
    expect(screen.getByTestId("start-analysis-modal-footer")).toBeInTheDocument();
    expect(screen.getByTestId("start-analysis-submit")).toBeVisible();
  });

  it("Escape 关闭弹窗", async () => {
    const onClose = vi.fn();
    renderDialog(onClose);
    await screen.findByRole("dialog");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("Tab 焦点可到达创建按钮", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    const submit = await waitFor(() => {
      const button = screen.getByTestId("start-analysis-submit");
      expect(button).toHaveTextContent("创建分析任务");
      expect(button).not.toBeDisabled();
      return button;
    });
    expect(dialog.contains(submit)).toBe(true);
    submit.focus();
    expect(document.activeElement).toBe(submit);
  });

  it("打开后焦点进入弹窗", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
  });

  it("关闭按钮为正方形热区", async () => {
    renderDialog();
    const close = await screen.findByRole("button", { name: "关闭" });
    expect(close.className).toContain("modal-close");
  });

  it("无可用 Provider 时真实禁用创建按钮并展示原因", async () => {
    vi.mocked(providersApi.list).mockResolvedValue([]);
    renderDialog();
    fireEvent.change(await screen.findByLabelText(/执行模式|执行方式/), { target: { value: "cloud" } });
    expect(await screen.findByTestId("start-analysis-no-provider")).toHaveTextContent(
      /尚未配置 API Key|当前没有可用/,
    );
    const submit = screen.getByTestId("start-analysis-submit");
    expect(submit).toBeDisabled();
    expect(screen.getByTestId("start-analysis-disabled-reason")).toHaveTextContent(
      /尚未配置 API Key|当前没有可用/,
    );
    fireEvent.click(submit);
    expect(analysisApi.start).not.toHaveBeenCalled();
  });

  it("均衡模式可见文案只包含一个推荐", async () => {
    renderDialog();
    const label = await screen.findByTestId("analysis-mode-label-balanced");
    expect(label).toHaveTextContent("均衡 · 推荐");
    expect(label.textContent?.match(/推荐/g)?.length).toBe(1);
    expect(label).not.toHaveTextContent("（推荐）（推荐）");
  });

  it("Provider 主视图不展示模型 ID", async () => {
    vi.mocked(providersApi.list).mockResolvedValue([plus] as any);
    renderDialog();
    fireEvent.change(await screen.findByLabelText(/执行模式|执行方式/), { target: { value: "cloud" } });
    const select = await screen.findByTestId("start-analysis-provider-select");
    expect(select).toHaveTextContent("阿里云百炼");
    expect(select).not.toHaveTextContent("configured-plus");
    expect(select).not.toHaveTextContent("aliyun_qwen_plus");
    expect(await screen.findByTestId("start-analysis-provider-hint")).toHaveTextContent(
      /已连接.*需要人工确认场景边界/,
    );
  });
});

describe("普通模式开始分析弹窗", () => {
  beforeEach(() => {
    localStorage.removeItem("storylens.developerMode");
    useDeveloperModeStore.setState({ developerMode: false });
  });

  it("无Provider下拉框", async () => {
    renderDialog();
    await screen.findByTestId("start-analysis-dialog");
    expect(screen.queryByLabelText("Provider")).not.toBeInTheDocument();
    expect(screen.queryByTestId("start-analysis-provider-select")).not.toBeInTheDocument();
  });

  it("AI服务未连接时禁用创建任务并给出明确原因", async () => {
    vi.mocked(providersApi.list).mockResolvedValue([{
      ...plus,
      connected: false,
      healthy: false,
      configured: false,
      manual_boundary_candidate_eligible: false,
      manual_selection_blockers: ["credential_missing"],
    }] as any);
    vi.mocked(providersApi.cloud).mockResolvedValue({ enabled: false, state: "disabled" });
    vi.mocked(providersApi.configuration).mockResolvedValue({
      provider_name: "aliyun_qwen_plus",
      credential_state: "missing",
      enabled: false,
      disconnected: true,
      connection_state: "disconnected",
    } as any);
    renderDialog();
    expect(await screen.findByTestId("start-analysis-ai-disconnected")).toHaveTextContent("尚未配置 API Key");
    expect(screen.getByTestId("start-analysis-goto-settings")).toHaveTextContent("去配置 AI 服务");
    expect(screen.getByTestId("start-analysis-submit")).toBeDisabled();
  });

  it("唯一可用 Provider 时自动选中真实 provider id", async () => {
    vi.mocked(providersApi.list).mockResolvedValue([plus] as any);
    vi.mocked(providersApi.cloud).mockResolvedValue({ enabled: true, state: "enabled" });
    renderDialog();
    expect(await screen.findByTestId("start-analysis-ai-connected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox"));
    await waitFor(() => expect(screen.getByTestId("start-analysis-submit")).toBeEnabled());
    fireEvent.click(screen.getByTestId("start-analysis-submit"));
    await waitFor(() =>
      expect(analysisApi.start).toHaveBeenCalledWith(
        7,
        expect.objectContaining({
          provider_name: "aliyun_qwen_plus",
          selected_provider: "aliyun_qwen_plus",
        }),
      ),
    );
  });

  it("AI服务已连接时可创建任务", async () => {
    vi.mocked(providersApi.list).mockResolvedValue([plus] as any);
    vi.mocked(providersApi.cloud).mockResolvedValue({ enabled: true, state: "enabled" });
    vi.mocked(providersApi.configuration).mockResolvedValue({
      provider_name: "aliyun_qwen_plus",
      display_name: "阿里云百炼",
      plus_model: "configured-plus",
      credential_state: "configured",
      enabled: true,
      disconnected: false,
      connection_state: "connected",
    } as any);
    renderDialog();
    expect(await screen.findByTestId("start-analysis-ai-connected")).toHaveTextContent(/阿里云百炼|qwen|configured-plus/);
    fireEvent.click(screen.getByRole("checkbox"));
    await waitFor(() => expect(screen.getByTestId("start-analysis-submit")).toBeEnabled());
  });

  it("请求额度不足时显示阻塞原因并提供临时授权创建，而非仅灰掉按钮", async () => {
    vi.mocked(providersApi.list).mockResolvedValue([plus] as any);
    vi.mocked(providersApi.cloud).mockResolvedValue({ enabled: true, state: "enabled" });
    vi.mocked(providersApi.configuration).mockResolvedValue({
      provider_name: "aliyun_qwen_plus",
      display_name: "阿里云百炼",
      plus_model: "configured-plus",
      credential_state: "configured",
      enabled: true,
      disconnected: false,
      connection_state: "connected",
    } as any);
    vi.mocked(analysisApi.preflight).mockResolvedValue({
      ...longPreflight,
      remaining: { requests: 59, tokens: 200000, estimated_cost: 20 },
    });
    vi.mocked(analysisRecoveryApi.fullPipelinePreflight).mockResolvedValue({
      full_expected_requests: 40,
      full_worst_requests: 66,
      remaining_requests: 59,
      remaining_tokens: 200000,
      remaining_cost: 20,
      within_budget: false,
      exceeded_dimensions: ["requests"],
      worst_case_tokens: 90000,
      worst_case_cost: 0.66,
      estimated_tokens: 45000,
      estimated_cost: 0.4,
    } as any);
    renderDialog();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(await screen.findByTestId("create-request-quota-block")).toBeInTheDocument();
    expect(screen.getByTestId("create-request-quota-title")).toHaveTextContent("当前技术请求额度不足");
    expect(screen.getByTestId("create-request-quota-body")).toHaveTextContent(/还差7次/);
    expect(screen.getByTestId("create-request-quota-body")).toHaveTextContent(/费用和Token预算充足/);
    expect(screen.getByTestId("create-with-recommended-allowance")).toBeEnabled();
    fireEvent.click(screen.getByTestId("create-with-recommended-allowance"));
    await waitFor(() =>
      expect(analysisApi.start).toHaveBeenCalledWith(
        7,
        expect.objectContaining({
          run_temporary_request_allowance: expect.objectContaining({
            extra_requests: 7,
            mode: "recommended_worst_case",
          }),
        }),
      ),
    );
  });

  it("主界面不直接显示内部错误码", async () => {
    vi.mocked(providersApi.list).mockResolvedValue([{
      ...plus,
      connected: false,
      health_state: "unhealthy",
      health_source: "configured_readiness",
      manual_selection_blockers: ["provider_disconnected"],
    }] as any);
    vi.mocked(providersApi.cloud).mockResolvedValue({ enabled: true, state: "enabled" });
    vi.mocked(providersApi.configuration).mockResolvedValue({
      credential_state: "configured",
      disconnected: true,
      connection_state: "disconnected",
    } as any);
    renderDialog();
    const summary = await screen.findByTestId("start-analysis-ai-summary");
    expect(summary).not.toHaveTextContent("unhealthy");
    expect(summary).not.toHaveTextContent("configured_readiness");
    expect(summary).not.toHaveTextContent("provider_disconnected");
    expect(summary).toHaveTextContent(/尚未连接|云端AI|API Key/);
  });
});
