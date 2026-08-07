import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "../components/layout/AppShell";
import { SettingsDataStorageTab } from "../components/settings/SettingsDataStorageTab";
import { SettingsPrivacyUpdateTab } from "../components/settings/SettingsPrivacyUpdateTab";
import {
  canUseNativeUpdater,
  isLocalWebProduction,
  isLocalWebShell,
  type RuntimeInfo,
} from "./runtimeCapabilities";

vi.mock("./apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./apiClient")>();
  return {
    ...actual,
    api: vi.fn(async (path: string) => {
      if (path === "/health") {
        return { status: "ok", database: "ok" };
      }
      if (path === "/api/v1/runtime") {
        return {
          runtime_mode: "browser_local_production",
          shell: "browser_local_production",
          application_version: "1.0.3",
          data_directory: "C:\\Users\\x\\AppData\\Local\\StoryLens",
          database_path: "C:\\Users\\x\\AppData\\Local\\StoryLens\\database\\storylens.db",
          frontend_origin: "http://127.0.0.1:8765",
          user_label: "本地网页版",
          desktop_capabilities: {
            tauri_shell: false,
            native_updater: false,
            native_window_controls: false,
            sidecar_lifecycle: false,
          },
          web_capabilities: {
            browser_zoom: true,
            file_picker_import: true,
            drag_drop_import: true,
            open_data_folder_via_api: true,
            clipboard_copy: true,
            local_only: true,
          },
          is_local_web_production: true,
        } satisfies RuntimeInfo;
      }
      if (path === "/api/v1/system/diagnostics") {
        return {
          data_directory: "C:\\Users\\x\\AppData\\Local\\StoryLens",
          database_path: "C:\\Users\\x\\AppData\\Local\\StoryLens\\database\\storylens.db",
          app_env: "production",
        };
      }
      throw new Error(`unexpected ${path}`);
    }),
  };
});

vi.mock("./desktopRuntime", () => ({
  isTauriRuntime: () => false,
}));

vi.mock("../lib/useAppVersion", () => ({
  useAppVersion: () => "1.0.3",
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={ui} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("local web runtime capabilities (CHG-015)", () => {
  it("recognizes browser_local_production", () => {
    const info = {
      runtime_mode: "browser_local_production",
      shell: "browser_local_production",
    } as RuntimeInfo;
    expect(isLocalWebShell(info)).toBe(true);
    expect(isLocalWebProduction(info)).toBe(true);
    expect(canUseNativeUpdater(info)).toBe(false);
  });

  it("shows local web brand and hides native updater controls", async () => {
    wrap(
      <div>
        <SettingsPrivacyUpdateTab />
        <SettingsDataStorageTab />
      </div>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("app-brand-label")).toHaveTextContent("本地网页版");
    });
    expect(screen.getByTestId("settings-web-update-hint")).toHaveTextContent(
      "网页版更新随本地 StoryLens 服务更新",
    );
    expect(screen.queryByTestId("check-update-button")).toBeNull();
    expect(screen.getByTestId("data-runtime-mode")).toHaveTextContent("本地网页版");
    expect(screen.getByTestId("data-storage-local")).toHaveTextContent("本机");
  });
});
