/** Frontend runtime capability adapter — prefer /api/v1/runtime over ad-hoc __TAURI__ checks. */

import { useQuery } from "@tanstack/react-query";
import { api } from "./apiClient";
import { isTauriRuntime } from "./desktopRuntime";

export type RuntimeMode =
  | "tauri_desktop"
  | "browser_local_dev"
  | "browser_local_production";

export type RuntimeInfo = {
  runtime_mode: RuntimeMode;
  config_runtime_mode?: string;
  shell: RuntimeMode;
  application_version: string;
  data_directory: string;
  database_path: string;
  frontend_origin: string;
  serve_frontend?: boolean;
  bind_host?: string;
  user_label: string;
  desktop_capabilities: {
    tauri_shell: boolean;
    native_updater: boolean;
    native_window_controls: boolean;
    sidecar_lifecycle: boolean;
  };
  web_capabilities: {
    browser_zoom: boolean;
    file_picker_import: boolean;
    drag_drop_import: boolean;
    open_data_folder_via_api: boolean;
    clipboard_copy: boolean;
    local_only: boolean;
  };
  security?: {
    loopback_only: boolean;
    credentials_never_returned: boolean;
    body_not_persisted_in_browser: boolean;
  };
  is_local_web_production?: boolean;
};

const FALLBACK_DESKTOP: RuntimeInfo = {
  runtime_mode: "tauri_desktop",
  shell: "tauri_desktop",
  application_version: "",
  data_directory: "",
  database_path: "",
  frontend_origin: "",
  user_label: "StoryLens",
  desktop_capabilities: {
    tauri_shell: true,
    native_updater: true,
    native_window_controls: true,
    sidecar_lifecycle: true,
  },
  web_capabilities: {
    browser_zoom: false,
    file_picker_import: true,
    drag_drop_import: true,
    open_data_folder_via_api: true,
    clipboard_copy: true,
    local_only: true,
  },
};

const FALLBACK_WEB_DEV: RuntimeInfo = {
  ...FALLBACK_DESKTOP,
  runtime_mode: "browser_local_dev",
  shell: "browser_local_dev",
  user_label: "本地网页版",
  desktop_capabilities: {
    tauri_shell: false,
    // Dev/Vitest keeps updater controls visible; service no-ops without Tauri.
    // Production web payload sets native_updater=false.
    native_updater: true,
    native_window_controls: false,
    sidecar_lifecycle: false,
  },
  web_capabilities: {
    ...FALLBACK_DESKTOP.web_capabilities,
    browser_zoom: true,
  },
};

export function fallbackRuntimeInfo(): RuntimeInfo {
  return isTauriRuntime() ? FALLBACK_DESKTOP : FALLBACK_WEB_DEV;
}

export async function fetchRuntimeInfo(): Promise<RuntimeInfo> {
  try {
    return await api<RuntimeInfo>("/api/v1/runtime");
  } catch {
    return fallbackRuntimeInfo();
  }
}

export function useRuntimeInfo() {
  return useQuery({
    queryKey: ["runtime"],
    queryFn: fetchRuntimeInfo,
    staleTime: 60_000,
  });
}

export function isLocalWebShell(info?: RuntimeInfo | null): boolean {
  const mode = info?.runtime_mode || info?.shell;
  return mode === "browser_local_dev" || mode === "browser_local_production";
}

export function isLocalWebProduction(info?: RuntimeInfo | null): boolean {
  return (info?.runtime_mode || info?.shell) === "browser_local_production";
}

export function canUseNativeUpdater(info?: RuntimeInfo | null): boolean {
  if (info) return Boolean(info.desktop_capabilities?.native_updater);
  return isTauriRuntime();
}
