import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UpdateAvailableDialog } from "../components/desktop/UpdateAvailableDialog";
import { SettingsPrivacyUpdateTab } from "../components/settings/SettingsPrivacyUpdateTab";
import {
  __resetUpdaterForTests,
  __setUpdaterSnapshotForTests,
  dismissAvailableUpdate,
  getUpdaterSnapshot,
} from "./updaterService";
import {
  DEFAULT_UPDATER_PREFERENCES,
  saveUpdaterPreferences,
} from "./updater/preferences";

vi.mock("../lib/useAppVersion", () => ({
  useAppVersion: () => "1.0.2",
}));


vi.mock("../components/settings/AboutAppVersion", () => ({
  AboutAppVersion: () => <div data-testid="about-version">about</div>,
}));

vi.mock("../components/settings/TelemetrySettingsCard", () => ({
  TelemetrySettingsCard: () => <div data-testid="telemetry-card">telemetry</div>,
}));

vi.mock("./runtimeCapabilities", async () => {
  const actual = await vi.importActual<typeof import("./runtimeCapabilities")>("./runtimeCapabilities");
  return {
    ...actual,
    useRuntimeInfo: () => ({
      data: {
        runtime_mode: "tauri_desktop",
        shell: "tauri_desktop",
        desktop_capabilities: {
          tauri_shell: true,
          native_updater: true,
          native_window_controls: true,
          sidecar_lifecycle: true,
        },
      },
      isLoading: false,
    }),
  };
});

const startDownload = vi.fn(async (): Promise<ReturnType<typeof getUpdaterSnapshot>> =>
  getUpdaterSnapshot(),
);
const confirmInstall = vi.fn(async (): Promise<ReturnType<typeof getUpdaterSnapshot>> =>
  getUpdaterSnapshot(),
);
const checkForAppUpdate = vi.fn(
  async (manual = false): Promise<{
    kind: "disabled" | "latest" | "available" | "error";
    currentVersion?: string;
    latestVersion?: string;
    body?: string;
    message?: string;
    downloadAndInstall?: () => Promise<void>;
  }> => {
    void manual;
    return { kind: "latest", currentVersion: "1.0.2" };
  },
);

function renderSettingsTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SettingsPrivacyUpdateTab />
    </QueryClientProvider>,
  );
}

vi.mock("./updaterService", async () => {
  const actual = await vi.importActual<typeof import("./updaterService")>("./updaterService");
  return {
    ...actual,
    startDownload: () => startDownload(),
    confirmInstall: () => confirmInstall(),
    checkForAppUpdate: (manual?: boolean) => checkForAppUpdate(manual),
  };
});

describe("UpdateAvailableDialog opt-in UX", () => {
  beforeEach(() => {
    localStorage.clear();
    __resetUpdaterForTests();
    saveUpdaterPreferences({ ...DEFAULT_UPDATER_PREFERENCES });
    startDownload.mockClear();
    confirmInstall.mockClear();
  });

  afterEach(() => {
    cleanup();
    __resetUpdaterForTests();
  });

  it("shows update dialog on available and 稍后再说 does not download", () => {
    __setUpdaterSnapshotForTests({
      phase: "available",
      currentVersion: "1.0.2",
      latestVersion: "1.0.3",
      releaseNotes: "修复更新确认流程",
      message: "发现新版本 1.0.3",
    });
    render(<UpdateAvailableDialog open />);
    expect(screen.getByTestId("update-available-dialog")).toHaveTextContent("发现新版本");
    expect(screen.getByText(/本次更新/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("update-later"));
    expect(startDownload).not.toHaveBeenCalled();
    expect(getUpdaterSnapshot().phase).toBe("dismissed");
  });

  it("立即更新 triggers download only", async () => {
    __setUpdaterSnapshotForTests({
      phase: "available",
      currentVersion: "1.0.2",
      latestVersion: "1.0.3",
      releaseNotes: "notes",
    });
    startDownload.mockImplementation(async () => {
      __setUpdaterSnapshotForTests({
        phase: "downloaded",
        currentVersion: "1.0.2",
        latestVersion: "1.0.3",
        message: "已下载",
      });
      return getUpdaterSnapshot();
    });
    render(<UpdateAvailableDialog open />);
    fireEvent.click(screen.getByTestId("update-now"));
    await waitFor(() => expect(startDownload).toHaveBeenCalledTimes(1));
    expect(confirmInstall).not.toHaveBeenCalled();
  });
});

describe("Settings version & update panel", () => {
  beforeEach(() => {
    localStorage.clear();
    __resetUpdaterForTests();
    saveUpdaterPreferences({ ...DEFAULT_UPDATER_PREFERENCES });
    checkForAppUpdate.mockClear();
  });

  afterEach(() => {
    cleanup();
    __resetUpdaterForTests();
  });

  it("shows version status and keeps update after dismiss", () => {
    __setUpdaterSnapshotForTests({
      phase: "dismissed",
      currentVersion: "1.0.2",
      latestVersion: "1.0.3",
      releaseNotes: "notes",
      lastCheckAt: "2026-07-21T01:00:00.000Z",
    });
    dismissAvailableUpdate();
    renderSettingsTab();
    expect(screen.getByTestId("settings-version-update-card")).toBeInTheDocument();
    expect(screen.getByTestId("settings-update-available-banner")).toHaveTextContent(
      "新版本 1.0.3 可用",
    );
    expect(screen.getByTestId("check-update-button")).toBeInTheDocument();
    expect(screen.getByTestId("settings-start-download-button")).toBeInTheDocument();
    expect(screen.getByTestId("settings-install-relaunch-button")).toBeInTheDocument();
    expect(screen.queryByTestId("update-channel-stable-only")).not.toBeInTheDocument();
    expect(screen.queryByTestId("update-channel-select")).not.toBeInTheDocument();
  });

  it("manual check button invokes checkForAppUpdate", async () => {
    checkForAppUpdate.mockResolvedValue({
      kind: "available",
      currentVersion: "1.0.2",
      latestVersion: "1.0.3",
      body: "notes",
      downloadAndInstall: async () => undefined,
    });
    renderSettingsTab();
    fireEvent.click(screen.getByTestId("check-update-button"));
    await waitFor(() => expect(checkForAppUpdate).toHaveBeenCalledWith(true));
  });
});
