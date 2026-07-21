import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { FirstLaunchWizard } from "./FirstLaunchWizard";
import { useTelemetryStore } from "../../stores/telemetry";
import * as aiServiceConfig from "../../services/aiServiceConfig";

const setupQueryState = vi.hoisted(() => ({
  data: undefined as
    | {
        credential_configured: boolean;
        cloud_enabled?: boolean;
        blockers?: string[];
      }
    | undefined,
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: () => ({ data: setupQueryState.data, isLoading: false }),
}));

vi.mock("../../services/aiServiceConfig", () => ({
  configureRecommendedQwenService: vi.fn(),
  fetchRecommendedQwenStatus: vi.fn(),
}));

describe("FirstLaunchWizard telemetry opt-in", () => {
  afterEach(() => {
    cleanup();
    localStorage.removeItem("storylens.telemetry.consent");
  });

  beforeEach(() => {
    useTelemetryStore.setState({ consent: "UNKNOWN", installIdPreview: null });
    setupQueryState.data = undefined;
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockReset();
  });

  it("defaults anonymous stats off and sets DISABLED when finishing without opt-in", () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    fireEvent.click(screen.getByText("稍后配置"));
    fireEvent.click(screen.getByText("开始使用 StoryLens"));
    expect(localStorage.getItem("storylens.telemetry.consent")).toBe("DISABLED");
  });

  it("sets ENABLED when user opts in on step 3", () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    fireEvent.click(screen.getByText("稍后配置"));
    fireEvent.click(screen.getByTestId("onboarding-telemetry-opt-in").querySelector("input")!);
    fireEvent.click(screen.getByText("开始使用 StoryLens"));
    expect(localStorage.getItem("storylens.telemetry.consent")).toBe("ENABLED");
  });
});

describe("FirstLaunchWizard AI setup", () => {
  afterEach(cleanup);

  beforeEach(() => {
    setupQueryState.data = undefined;
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockReset();
  });

  it("shows step chrome without changing underlying step state machine", () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    expect(screen.getByText("步骤 1 / 3")).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-step-welcome")).toBeInTheDocument();
    expect(screen.getByText("本地优先的小说拆解工具")).toBeInTheDocument();
    fireEvent.click(screen.getByText("下一步"));
    expect(screen.getByText("步骤 2 / 3")).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-step-ai")).toBeInTheDocument();
  });

  it("uses neutral tone before any verification", () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    const status = screen.getByTestId("onboarding-connection-status");
    expect(status).toHaveAttribute("data-tone", "neutral");
    expect(status.className).toContain("onboarding-status-card--neutral");
    expect(status.className).not.toContain("onboarding-status-card--success");
    expect(status).toHaveTextContent("尚未配置");
  });

  it("disables verify without api key and without existing credential", () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    expect(screen.getByTestId("onboarding-test")).toBeDisabled();
    expect(screen.getByTestId("onboarding-save-next")).toBeDisabled();
    expect(screen.getByTestId("onboarding-next-reason")).toHaveTextContent("尚未填写 API Key");
  });

  it("keeps next disabled after model validation until analysis ready", async () => {
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue({
      ok: false,
      persisted: true,
      user_message: "模型服务验证成功\n当前模型缺少计价信息",
      credential_configured: true,
      provider_enabled: true,
      cloud_enabled: true,
      provider_eligible: false,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "partial",
      analysis_mode: "BALANCED",
      blockers: ["pricing_unavailable"],
      needs_cloud_consent: false,
      model_service_validated: true,
      analysis_ready: false,
      readiness_reasons: ["当前模型缺少计价配置"],
      error_code: "pricing_unavailable",
    });
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    fireEvent.change(screen.getByTestId("onboarding-api-key"), {
      target: { value: "sk-test-key-value" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByTestId("onboarding-test"));
    await waitFor(() => {
      expect(screen.getByTestId("onboarding-connection-status")).toHaveTextContent(
        "模型服务验证成功",
      );
    });
    expect(screen.getByTestId("onboarding-save-next")).toBeDisabled();
    expect(screen.getByTestId("onboarding-next-reason")).toHaveTextContent("计价");
    expect(screen.queryByTestId("onboarding-step-start")).not.toBeInTheDocument();
  });

  it("enables next only when analysis ready after verify and save", async () => {
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
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    fireEvent.change(screen.getByTestId("onboarding-api-key"), {
      target: { value: "sk-test-key-value" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByTestId("onboarding-test"));
    await waitFor(() => {
      expect(aiServiceConfig.configureRecommendedQwenService).toHaveBeenCalledWith(
        expect.objectContaining({ persist: true, cloudBodyConsent: true }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("onboarding-save-next")).not.toBeDisabled();
    });
    fireEvent.click(screen.getByTestId("onboarding-save-next"));
    expect(screen.getByTestId("onboarding-step-start")).toBeInTheDocument();
  });

  it("allows skip config with explicit analysis unavailable note", () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    expect(screen.getByTestId("onboarding-skip-config")).toBeInTheDocument();
    expect(screen.getByText(/完成 AI 服务配置前无法执行分析/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("onboarding-skip-config"));
    expect(screen.getByTestId("onboarding-step-start")).toBeInTheDocument();
    expect(screen.getByText(/完成 AI 服务配置前无法执行分析/)).toBeInTheDocument();
  });

  it("uses updated consent copy without hardcoding only 阿里云百炼 as destination", () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    const box = screen.getByTestId("onboarding-consent-box");
    expect(box).toHaveTextContent(
      "为完成分析，StoryLens 将应用大模型能力对所选章节正文进行分析，所选正文会发送至当前模型服务商。",
    );
    expect(box).toHaveTextContent("正文不会进入 StoryLens 匿名使用统计");
  });

  it("uses different API Key placeholders for configured vs unconfigured credentials", () => {
    setupQueryState.data = { credential_configured: false };
    const { unmount } = render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    expect(screen.getByTestId("onboarding-api-key")).toHaveAttribute(
      "placeholder",
      "粘贴你的 API Key",
    );
    unmount();

    setupQueryState.data = { credential_configured: true };
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    expect(screen.getByTestId("onboarding-api-key")).toHaveAttribute(
      "placeholder",
      "留空表示保持现有凭据",
    );
  });

  it("does not show contradictory 连接成功 and 连接失败 labels", async () => {
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue({
      ok: false,
      persisted: false,
      user_message: "模型服务验证失败",
      credential_configured: false,
      provider_enabled: false,
      cloud_enabled: false,
      provider_eligible: false,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "disconnected",
      analysis_mode: null,
      blockers: ["connection_test_failed"],
      needs_cloud_consent: false,
      model_service_validated: false,
      analysis_ready: false,
      error_code: "CREDENTIAL_INVALID",
    });
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    fireEvent.change(screen.getByTestId("onboarding-api-key"), {
      target: { value: "sk-bad" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByTestId("onboarding-test"));
    await waitFor(() => {
      expect(screen.getByTestId("onboarding-connection-status")).toHaveTextContent(
        "模型服务验证失败",
      );
    });
    const status = screen.getByTestId("onboarding-connection-status");
    expect(status).not.toHaveTextContent("连接成功");
    expect(status).not.toHaveTextContent("连接失败");
  });
});
