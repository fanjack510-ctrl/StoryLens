import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DesktopBootstrap } from "./DesktopBootstrap";

const bootstrap = vi.fn();

vi.mock("../../services/desktopRuntime", () => ({
  bootstrapDesktopRuntime: (...args: unknown[]) => bootstrap(...args),
  listenBackendEvents: async () => () => undefined,
  isTauriRuntime: () => false,
}));

vi.mock("../../services/updaterService", () => ({
  checkForAppUpdate: async () => ({ kind: "latest", currentVersion: "0.0.0" }),
  getUpdaterSnapshot: () => ({
    phase: "idle",
    currentVersion: "",
    latestVersion: null,
    releaseNotes: "",
    progress: null,
    message: "",
    technicalDetail: null,
    lastCheckAt: null,
    channel: "stable",
  }),
  subscribeUpdater: () => () => undefined,
  loadUpdaterPreferences: () => ({
    automatic_check: true,
    automatic_download: false,
    automatic_install: false,
    channel: "stable",
    dismissed_version: null,
    remind_after: null,
    last_check_at: null,
    internal_test_mode: false,
  }),
  shouldShowUpdateDialog: () => false,
}));

vi.mock("../../services/telemetry/telemetryRuntime", () => ({
  trackAppLaunchedOncePerSession: () => undefined,
}));

describe("DesktopBootstrap", () => {
  afterEach(() => {
    cleanup();
    sessionStorage.clear();
    bootstrap.mockReset();
  });

  it("renders starting state from audit force flag", () => {
    sessionStorage.setItem("storylens.uiAudit.forceBootstrap", "starting");
    render(
      <DesktopBootstrap>
        <div>app</div>
      </DesktopBootstrap>,
    );
    expect(screen.getByTestId("desktop-bootstrap-starting")).toHaveTextContent("正在启动 StoryLens");
    expect(bootstrap).not.toHaveBeenCalled();
  });

  it("retry button re-invokes bootstrap logic after failed force state", async () => {
    sessionStorage.setItem("storylens.uiAudit.forceBootstrap", "failed");
    bootstrap.mockResolvedValue({ state: "browser_dev" });
    render(
      <DesktopBootstrap>
        <div>app</div>
      </DesktopBootstrap>,
    );
    expect(screen.getByTestId("desktop-bootstrap-error")).toBeInTheDocument();
    sessionStorage.removeItem("storylens.uiAudit.forceBootstrap");
    fireEvent.click(screen.getByTestId("desktop-bootstrap-retry"));
    expect(await screen.findByText("app")).toBeInTheDocument();
    expect(bootstrap).toHaveBeenCalled();
  });
});
