import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { FirstLaunchWizard } from "./FirstLaunchWizard";
import { TelemetryInviteCard } from "./TelemetryInviteCard";
import { useTelemetryStore } from "../../stores/telemetry";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { providersApi } from "../../services/providersApi";
import { settingsApi } from "../../services/settingsApi";

const navigateMock = vi.fn();

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
    useNavigate: () => navigateMock,
  };
});

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-query")>("@tanstack/react-query");
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: vi.fn() }),
    useQuery: () => ({ data: setupQueryState.data, isLoading: false }),
  };
});

// 向导以前走的是一条只为通义千问写的一键路径，写死「阿里云百炼」。那条路径已经删除，
// 它现在跟设置页走同一套：保存配置 → 设为当前服务商 → 开云端 → 记下同意 → 验证。
vi.mock("../../services/providersApi", () => ({
  providersApi: {
    configuration: vi.fn(),
    save: vi.fn(),
    transportDiagnostic: vi.fn(),
    testConnection: vi.fn(),
  },
}));

vi.mock("../../services/settingsApi", () => ({
  settingsApi: {
    activeCloudProvider: vi.fn(),
    setActiveCloudProvider: vi.fn(),
    setCloud: vi.fn(),
    setCloudBodyConsent: vi.fn(),
  },
}));

function renderWizard() {
  return render(
    <MemoryRouter>
      <FirstLaunchWizard />
    </MemoryRouter>,
  );
}

describe("FirstLaunchWizard two-step flow", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    navigateMock.mockReset();
  });

  beforeEach(() => {
    useTelemetryStore.setState({ consent: "UNKNOWN", installIdPreview: null });
    useOnboardingStore.setState({ status: "pending" });
    setupQueryState.data = undefined;
    vi.mocked(providersApi.configuration).mockResolvedValue({
      display_name: "深度求索/DeepSeek",
      base_url: "https://api.deepseek.com/",
      plus_model: "deepseek-v4-flash",
      timeout_seconds: 300,
      max_retries: 3,
    } as never);
    vi.mocked(providersApi.save).mockResolvedValue({} as never);
    vi.mocked(providersApi.transportDiagnostic).mockResolvedValue({} as never);
    vi.mocked(providersApi.testConnection).mockResolvedValue({} as never);
    vi.mocked(settingsApi.setActiveCloudProvider).mockResolvedValue({} as never);
    vi.mocked(settingsApi.setCloud).mockResolvedValue({} as never);
    vi.mocked(settingsApi.setCloudBodyConsent).mockResolvedValue({ accepted: true } as never);
  });

  it("shows welcome with a single primary action", () => {
    renderWizard();
    expect(screen.getByTestId("onboarding-step-welcome")).toBeInTheDocument();
    expect(screen.getByText("欢迎使用 StoryLens")).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-start-setup")).toBeInTheDocument();
    expect(screen.queryByText("步骤 1 / 3")).not.toBeInTheDocument();
    expect(screen.queryByText("本地优先的小说拆解工具")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("button", { name: "开始设置" })).toHaveLength(1);
  });

  it("enters AI step from 开始设置", () => {
    renderWizard();
    fireEvent.click(screen.getByTestId("onboarding-start-setup"));
    expect(screen.getByTestId("onboarding-step-ai")).toBeInTheDocument();
    expect(screen.getByText("连接 AI 模型")).toBeInTheDocument();
  });

  it("completes wizard when entering library from welcome", () => {
    renderWizard();
    fireEvent.click(screen.getByTestId("onboarding-enter-library"));
    expect(useOnboardingStore.getState().status).toBe("completed");
    expect(navigateMock).toHaveBeenCalledWith("/library");
    expect(localStorage.getItem("storylens.telemetry.consent")).toBeNull();
  });

  it("shows 保存并验证 without existing credential", () => {
    setupQueryState.data = { credential_configured: false };
    renderWizard();
    fireEvent.click(screen.getByTestId("onboarding-start-setup"));
    expect(screen.getByTestId("onboarding-test")).toHaveTextContent("保存并验证");
  });

  it("shows 验证并进入书库 when credential exists", () => {
    setupQueryState.data = { credential_configured: true };
    renderWizard();
    fireEvent.click(screen.getByTestId("onboarding-start-setup"));
    expect(screen.getByTestId("onboarding-api-key")).toHaveAttribute(
      "placeholder",
      "已配置，留空表示不修改",
    );
    expect(screen.getByTestId("onboarding-test")).toHaveTextContent("验证并进入书库");
    expect(screen.getByText("Key仅保存在本机。")).toBeInTheDocument();
    expect(screen.queryByText(/Windows 凭据管理器/)).not.toBeInTheDocument();
  });

  it("enters library after successful verify", async () => {
    renderWizard();
    fireEvent.click(screen.getByTestId("onboarding-start-setup"));
    fireEvent.change(screen.getByTestId("onboarding-api-key"), {
      target: { value: "sk-test-key-value" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByTestId("onboarding-test"));
    await waitFor(() => {
      expect(useOnboardingStore.getState().status).toBe("completed");
    });
    expect(navigateMock).toHaveBeenCalledWith("/library");
    expect(screen.queryByTestId("onboarding-step-start")).not.toBeInTheDocument();
    expect(screen.queryByTestId("onboarding-telemetry-opt-in")).not.toBeInTheDocument();
  });

  it("stays on AI step when verify fails", async () => {
    vi.mocked(providersApi.testConnection).mockRejectedValue(
      Object.assign(new Error("API Key 无效，请检查后重试。"), {
        code: "PROVIDER_AUTHENTICATION_FAILED",
      }),
    );
    renderWizard();
    fireEvent.click(screen.getByTestId("onboarding-start-setup"));
    fireEvent.change(screen.getByTestId("onboarding-api-key"), {
      target: { value: "sk-bad" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByTestId("onboarding-test"));
    await waitFor(() => {
      expect(screen.getByTestId("onboarding-ai-message")).toHaveTextContent("API Key 无效");
    });
    expect(screen.getByTestId("onboarding-step-ai")).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-test")).toHaveTextContent("重新验证");
    expect(useOnboardingStore.getState().status).toBe("pending");
  });

  it("allows 稍后配置 to complete and enter library", () => {
    renderWizard();
    fireEvent.click(screen.getByTestId("onboarding-start-setup"));
    fireEvent.click(screen.getByTestId("onboarding-skip-config"));
    expect(useOnboardingStore.getState().status).toBe("completed");
    expect(navigateMock).toHaveBeenCalledWith("/library");
  });

  it("does not leak full API key into the DOM after typing", () => {
    renderWizard();
    fireEvent.click(screen.getByTestId("onboarding-start-setup"));
    fireEvent.change(screen.getByTestId("onboarding-api-key"), {
      target: { value: "sk-secret-should-not-echo" },
    });
    expect(screen.getByTestId("onboarding-api-key")).toHaveAttribute("type", "password");
    expect(document.body.textContent || "").not.toContain("sk-secret-should-not-echo");
  });

  it("uses short consent copy without telemetry wording", () => {
    renderWizard();
    fireEvent.click(screen.getByTestId("onboarding-start-setup"));
    const box = screen.getByTestId("onboarding-consent-box");
    expect(box).toHaveTextContent("分析时，允许将所选正文发送给当前模型服务商");
    expect(box).toHaveTextContent("StoryLens不会将正文上传到自己的服务器。");
    expect(box).not.toHaveTextContent("匿名使用统计");
  });
});

describe("TelemetryInviteCard", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  beforeEach(() => {
    useTelemetryStore.setState({ consent: "UNKNOWN", installIdPreview: null });
  });

  it("shows invite with no preselected choice when consent unknown", () => {
    render(<TelemetryInviteCard />);
    expect(screen.getByTestId("telemetry-invite-card")).toBeInTheDocument();
    expect(screen.getByTestId("telemetry-invite-decline")).toBeInTheDocument();
    expect(screen.getByTestId("telemetry-invite-accept")).toBeInTheDocument();
  });

  it("decline sets DISABLED and hides card", () => {
    const { rerender } = render(<TelemetryInviteCard />);
    fireEvent.click(screen.getByTestId("telemetry-invite-decline"));
    expect(localStorage.getItem("storylens.telemetry.consent")).toBe("DISABLED");
    rerender(<TelemetryInviteCard />);
    expect(screen.queryByTestId("telemetry-invite-card")).not.toBeInTheDocument();
  });

  it("accept sets ENABLED and persists across remount", () => {
    const { unmount } = render(<TelemetryInviteCard />);
    fireEvent.click(screen.getByTestId("telemetry-invite-accept"));
    expect(localStorage.getItem("storylens.telemetry.consent")).toBe("ENABLED");
    unmount();
    useTelemetryStore.setState({
      consent: "ENABLED",
      installIdPreview: null,
    });
    render(<TelemetryInviteCard />);
    expect(screen.queryByTestId("telemetry-invite-card")).not.toBeInTheDocument();
  });
});
