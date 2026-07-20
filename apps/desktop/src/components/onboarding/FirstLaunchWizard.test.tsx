import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { FirstLaunchWizard } from "./FirstLaunchWizard";
import { useTelemetryStore } from "../../stores/telemetry";
import * as aiServiceConfig from "../../services/aiServiceConfig";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("../../services/aiServiceConfig", () => ({
  configureRecommendedQwenService: vi.fn(),
}));

describe("FirstLaunchWizard telemetry opt-in", () => {
  afterEach(() => {
    cleanup();
    localStorage.removeItem("storylens.telemetry.consent");
  });

  beforeEach(() => {
    useTelemetryStore.setState({ consent: "UNKNOWN", installIdPreview: null });
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
    fireEvent.click(screen.getByText("下一步"));
    expect(screen.getByText("步骤 2 / 3")).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-step-ai")).toBeInTheDocument();
  });

  it("test connection does not persist and does not finish wizard", async () => {
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue({
      ok: true,
      persisted: false,
      user_message: "连接测试成功（尚未保存配置）。",
      credential_configured: false,
      provider_enabled: false,
      cloud_enabled: false,
      provider_eligible: false,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "tested",
      analysis_mode: null,
      blockers: [],
      needs_cloud_consent: false,
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
    fireEvent.click(screen.getByTestId("onboarding-test"));
    await waitFor(() => {
      expect(aiServiceConfig.configureRecommendedQwenService).toHaveBeenCalledWith(
        expect.objectContaining({ persist: false }),
      );
    });
    expect(screen.getByTestId("onboarding-ai-message")).toHaveTextContent("尚未保存");
    expect(screen.getByTestId("onboarding-connection-status")).toHaveTextContent("连接成功");
    expect(screen.queryByTestId("onboarding-step-start")).not.toBeInTheDocument();
  });

  it("next persists setup and only advances when eligible", async () => {
    vi.mocked(aiServiceConfig.configureRecommendedQwenService).mockResolvedValue({
      ok: true,
      persisted: true,
      user_message: "保存成功，已连接，可以开始分析。",
      credential_configured: true,
      provider_enabled: true,
      cloud_enabled: true,
      provider_eligible: true,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "connected",
      analysis_mode: "BALANCED",
      blockers: [],
      needs_cloud_consent: false,
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
    fireEvent.click(screen.getByTestId("onboarding-save-next"));
    await waitFor(() => {
      expect(aiServiceConfig.configureRecommendedQwenService).toHaveBeenCalledWith(
        expect.objectContaining({ persist: true, cloudBodyConsent: true }),
      );
    });
    expect(await screen.findByTestId("onboarding-step-start")).toBeInTheDocument();
  });

  it("consent checkbox still gates save", async () => {
    render(
      <MemoryRouter>
        <FirstLaunchWizard />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("下一步"));
    fireEvent.click(screen.getByTestId("onboarding-save-next"));
    expect(await screen.findByTestId("onboarding-ai-message")).toHaveTextContent("请先确认正文发送说明");
    expect(aiServiceConfig.configureRecommendedQwenService).not.toHaveBeenCalled();
  });
});
