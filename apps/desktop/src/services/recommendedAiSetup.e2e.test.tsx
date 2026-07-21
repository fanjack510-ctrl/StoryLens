/**
 * Integration-style path: wizard save → settings eligible → analysis dialog
 * auto-selects provider. Uses mocks (no real Aliyun).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FirstLaunchWizard } from "../components/onboarding/FirstLaunchWizard";
import { StartAnalysisDialog } from "../components/analysis/StartAnalysisDialog";
import * as aiServiceConfig from "./aiServiceConfig";
import { providersApi } from "./providersApi";
import { analysisApi } from "./analysisApi";
import { analysisRecoveryApi } from "./analysisRecoveryApi";
import { useDeveloperModeStore } from "../stores/developerModeStore";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => vi.fn() };
});

vi.mock("./aiServiceConfig", async () => {
  const actual = await vi.importActual<typeof import("./aiServiceConfig")>("./aiServiceConfig");
  return {
    ...actual,
    configureRecommendedQwenService: vi.fn(),
    fetchRecommendedQwenStatus: vi.fn(),
  };
});

vi.mock("./providersApi", () => ({
  providersApi: { list: vi.fn(), cloud: vi.fn(), configuration: vi.fn() },
}));
vi.mock("./analysisApi", () => ({ analysisApi: { start: vi.fn(), preflight: vi.fn() } }));
vi.mock("./analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    fullPipelinePreflight: vi.fn(async () => ({
      full_expected_requests: 20,
      full_worst_requests: 40,
      remaining_requests: 100,
      remaining_tokens: 200000,
      remaining_cost: 20,
      within_budget: true,
      exceeded_dimensions: [],
    })),
  },
}));
vi.mock("./settingsApi", () => ({
  settingsApi: {
    cloudBudget: vi.fn(async () => ({
      cloud_daily_request_limit: 100,
      cloud_daily_estimated_cost_limit: 20,
      currency: "CNY",
    })),
    cloudUsage: vi.fn(async () => ({
      remaining_requests: 100,
      remaining_tokens: 200000,
      remaining_estimated_cost: 20,
    })),
  },
}));

const plus = {
  capability_schema_version: "1c-a-2",
  enabled: true,
  name: "aliyun_qwen_plus",
  default_model: "qwen3.7-plus",
  configured: true,
  connected: true,
  healthy: true,
  allow_auto_route: false,
  eligible_for_automatic_analysis: false,
  manual_boundary_candidate_eligible: true,
  manual_selection_blockers: [],
  supports_boundary_candidates: true,
  requires_boundary_review: true,
  provider_state_version: "state-1",
  capabilities: {
    cloud: true,
    enabled: true,
    sends_content_to_cloud: true,
    requires_boundary_review: true,
  },
};

describe("recommended AI setup e2e path", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.removeItem("storylens.developerMode");
    useDeveloperModeStore.setState({ developerMode: false });
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue({
      ok: true,
      persisted: true,
      user_message: "配置完成。模型服务、计价和预算检查均已通过，可以开始分析。",
      credential_configured: true,
      provider_enabled: true,
      cloud_enabled: true,
      provider_eligible: true,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "connected",
      analysis_mode: "BALANCED",
      blockers: [],
      needs_cloud_consent: false,
      model_service_validated: true,
      analysis_ready: true,
      readiness_reasons: [],
    });
    vi.mocked(providersApi.list).mockResolvedValue([plus] as any);
    vi.mocked(providersApi.cloud).mockResolvedValue({ enabled: true, state: "available" });
    vi.mocked(providersApi.configuration).mockResolvedValue({
      provider_name: "aliyun_qwen_plus",
      display_name: "阿里云百炼",
      plus_model: "qwen3.7-plus",
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
      remaining: { requests: 70, tokens: 90000, estimated_cost: 2.5 },
      worst_case_request_count: 6,
      expected_request_count: 3,
    } as any);
    vi.mocked(analysisApi.start).mockResolvedValue({ run_id: 99 } as any);
  });

  it("wizard save then analysis dialog auto-selects provider", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <FirstLaunchWizard />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    fireEvent.change(screen.getByTestId("onboarding-api-key"), {
      target: { value: "sk-e2e-test-key" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByTestId("onboarding-test"));
    await waitFor(() => {
      expect(aiServiceConfig.configureRecommendedQwenService).toHaveBeenCalledWith(
        expect.objectContaining({ persist: true }),
      );
    });
    await waitFor(() => expect(screen.getByTestId("onboarding-save-next")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("onboarding-save-next"));
    expect(await screen.findByTestId("onboarding-step-start")).toBeInTheDocument();
    cleanup();

    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <StartAnalysisDialog chapterId={7} onClose={vi.fn()} onCreated={vi.fn()} />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("start-analysis-ai-connected")).toBeInTheDocument();
    expect(screen.queryByTestId("start-analysis-provider-select")).not.toBeInTheDocument();
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
});
